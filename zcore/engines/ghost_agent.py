from __future__ import annotations

import json
import os
from urllib import error, parse, request

from zcore.config import get_nested, load_config
from zcore.engines.observability import ObservabilityEngine
from zcore.runtime import RuntimePaths
from zcore.utils.privacy import redact_text
from zcore.utils.tokens import estimate_tokens, get_context_window


class GhostAgent:
    """Small-model backend stub with explicit non-LLM fallback behavior."""
    DEFAULT_MAX_OUTPUT_TOKENS = 4096
    PROMPT_SAFETY_MARGIN = 2048
    PRICING_PER_1M_TOKENS = {
        ("google", "gemini-2.5-flash"): (0.3, 2.5),
        ("anthropic", "claude-3-5-haiku-latest"): (0.8, 4.0),
        ("openai", "gpt-4o-mini"): (0.15, 0.6),
    }

    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or RuntimePaths.discover()
        self.config = load_config(self.paths)

    def availability(self) -> dict[str, object]:
        enabled = bool(get_nested(self.config, "llm_backend", "enabled", default=False))
        provider = str(get_nested(self.config, "llm_backend", "provider", default="google"))
        model = str(get_nested(self.config, "llm_backend", "model", default="gemini-2.5-flash"))

        if not enabled:
            return {
                "enabled": False,
                "available": False,
                "provider": provider,
                "model": model,
                "mode": "fallback",
                "reason": "llm_backend.disabled",
            }

        if provider == "ollama":
            return {
                "enabled": True,
                "available": True,
                "provider": provider,
                "model": model,
                "mode": "local",
                "reason": "",
            }

        api_key = (
            os.environ.get("KITCLAW_LLM_API_KEY")
            or os.environ.get("ZCORE_LLM_API_KEY")
            or str(get_nested(self.config, "llm_backend", "api_key", default=""))
        ).strip()

        if not api_key:
            return {
                "enabled": True,
                "available": False,
                "provider": provider,
                "model": model,
                "mode": "fallback",
                "reason": "missing_api_key",
            }

        return {
            "enabled": True,
            "available": True,
            "provider": provider,
            "model": model,
            "mode": "remote",
            "reason": "",
        }

    def call(self, prompt: str) -> str:
        return str(self.generate(prompt).get("text", ""))

    def prompt_model(self) -> str:
        return str(get_nested(self.config, "llm_backend", "model", default="gemini-2.5-flash"))

    def max_prompt_tokens(self) -> int:
        context_window = get_context_window(self.prompt_model())
        max_output_tokens = self.DEFAULT_MAX_OUTPUT_TOKENS
        budget = context_window - max_output_tokens - self.PROMPT_SAFETY_MARGIN
        return max(budget, 1024)

    def generate(
        self,
        prompt: str,
        fallback_text: str | None = None,
        *,
        session_id: str | None = None,
        skill_name: str | None = None,
    ) -> dict[str, object]:
        status = self.availability()
        if not status["available"]:
            return {
                "text": fallback_text or self._fallback_text(prompt),
                "mode": "fallback",
                "reason": str(status["reason"]),
            }

        timeout = int(get_nested(self.config, "llm_backend", "timeout", default=30))
        retry_max = int(get_nested(self.config, "llm_backend", "retry_max", default=2))
        fallback_on_failure = bool(get_nested(self.config, "llm_backend", "fallback_on_failure", default=True))
        provider = str(status["provider"])
        sanitized_prompt = self._truncate_prompt_to_budget(self._sanitize_text(prompt))
        input_tokens = estimate_tokens(sanitized_prompt, self.prompt_model())
        observability = ObservabilityEngine(self.paths)

        last_error: Exception | None = None
        for _ in range(retry_max + 1):
            try:
                response = self._perform_request(provider, sanitized_prompt, timeout=timeout)
                text = self._extract_text_from_response(response, provider).strip()
                if text:
                    output_tokens = estimate_tokens(text, self.prompt_model())
                    observability.log_cost(
                        provider,
                        self.prompt_model(),
                        input_tokens,
                        output_tokens,
                        self._estimate_cost_usd(provider, self.prompt_model(), input_tokens, output_tokens),
                        session_id=session_id,
                        skill_name=skill_name,
                    )
                    return {"text": text, "mode": "llm", "reason": ""}
                last_error = ValueError("empty_response")
            except (OSError, ValueError, error.HTTPError, error.URLError) as exc:
                last_error = exc

        observability.log_cost(
            provider,
            self.prompt_model(),
            input_tokens,
            0,
            0.0,
            session_id=session_id,
            skill_name=skill_name,
        )
        if not fallback_on_failure and last_error is not None:
            return {
                "text": "",
                "mode": "error",
                "reason": f"{type(last_error).__name__}: {last_error}",
            }

        return {
            "text": fallback_text or self._fallback_text(prompt),
            "mode": "fallback",
            "reason": f"request_failed:{type(last_error).__name__}" if last_error else "request_failed",
        }

    def _estimate_cost_usd(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        input_rate, output_rate = self.PRICING_PER_1M_TOKENS.get((provider, model), (0.0, 0.0))
        cost = ((input_tokens / 1_000_000) * input_rate) + ((output_tokens / 1_000_000) * output_rate)
        return round(cost, 8)

    def compact_messages(self, messages: list[dict[str, object]], model: str = "sonnet") -> dict[str, object]:
        from zcore.engines.context import ContextEngine

        engine = ContextEngine(self.paths)
        result = engine.apply_compact(messages, model=model, ghost_agent=self)
        return {
            "mode": result.metadata["mode"],
            "summary": result.summary,
            "reason": result.metadata["reason"],
        }

    def extract_memories(self, messages: list[dict[str, object]]) -> dict[str, object]:
        status = self.availability()
        entries = []
        for message in messages:
            content = str(message.get("content", "")).strip()
            lowered = content.lower()
            if any(marker in lowered for marker in ("[decision]", "[action]", "[learning]", "[fact]", "[preference]")):
                entries.append({"content": redact_text(content), "source": "heuristic"})
        return {
            "mode": "fallback" if not status["available"] else "stub",
            "entries": entries,
            "reason": str(status["reason"]),
        }

    def _perform_request(self, provider: str, prompt: str, *, timeout: int) -> dict[str, object]:
        req = self._build_request(provider, prompt)
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _build_request(self, provider: str, prompt: str) -> request.Request:
        model = str(get_nested(self.config, "llm_backend", "model", default="gemini-2.5-flash"))
        endpoint = str(get_nested(self.config, "llm_backend", "endpoint", default="")).strip()
        api_key = self._api_key()
        headers = {"Content-Type": "application/json"}

        if provider == "google":
            base = endpoint.rstrip("/") or "https://generativelanguage.googleapis.com"
            url = (
                f"{base}/v1beta/models/{parse.quote(model, safe='')}:generateContent"
                f"?key={parse.quote(api_key)}"
            )
            body = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
            }
        elif provider == "anthropic":
            url = endpoint or "https://api.anthropic.com/v1/messages"
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
            body = {
                "model": model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
        elif provider == "openai":
            url = endpoint or "https://api.openai.com/v1/chat/completions"
            headers["Authorization"] = f"Bearer {api_key}"
            body = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
            }
        elif provider == "ollama":
            base = endpoint.rstrip("/") or "http://localhost:11434"
            url = f"{base}/api/generate"
            body = {
                "model": model,
                "prompt": prompt,
                "stream": False,
            }
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        return request.Request(url, data=data, headers=headers, method="POST")

    def _api_key(self) -> str:
        return (
            os.environ.get("KITCLAW_LLM_API_KEY")
            or os.environ.get("ZCORE_LLM_API_KEY")
            or str(get_nested(self.config, "llm_backend", "api_key", default=""))
        ).strip()

    def _sanitize_text(self, text: str) -> str:
        if not bool(get_nested(self.config, "privacy", "redact_before_send", default=True)):
            return text

        patterns = get_nested(self.config, "privacy", "redact_patterns", default=None)
        redact_file_paths = bool(get_nested(self.config, "privacy", "redact_file_paths", default=True))
        return redact_text(text, patterns=patterns, redact_file_paths=redact_file_paths)

    def _fallback_text(self, prompt: str) -> str:
        cleaned = self._sanitize_text(prompt).strip()
        if not cleaned:
            return "Ghost Agent fallback: no prompt content available."
        return f"Ghost Agent fallback summary:\n{cleaned[:1200]}"

    def _truncate_prompt_to_budget(self, prompt: str) -> str:
        budget = self.max_prompt_tokens()
        model = self.prompt_model()
        if estimate_tokens(prompt, model) <= budget:
            return prompt

        marker = "\n\n[Prompt trimmed to fit Ghost Agent context window.]\n\n"
        head_chars = max(len(prompt) // 3, 1000)
        tail_chars = max(len(prompt) // 2, 2000)
        candidate = prompt[:head_chars] + marker + self._tail_with_anchor(prompt, tail_chars)

        while estimate_tokens(candidate, model) > budget and (head_chars > 80 or tail_chars > 120):
            head_chars = max(int(head_chars * 0.8), 80)
            tail_chars = max(int(tail_chars * 0.8), 120)
            candidate = prompt[:head_chars] + marker + self._tail_with_anchor(prompt, tail_chars)

        if estimate_tokens(candidate, model) <= budget:
            return candidate

        head_chars = 120
        tail_chars = 240
        candidate = prompt[:head_chars] + marker + self._tail_with_anchor(prompt, tail_chars)
        while estimate_tokens(candidate, model) > budget and (head_chars > 40 or tail_chars > 80):
            head_chars = max(int(head_chars * 0.75), 40)
            tail_chars = max(int(tail_chars * 0.75), 80)
            candidate = prompt[:head_chars] + marker + self._tail_with_anchor(prompt, tail_chars)
        return candidate

    def _tail_with_anchor(self, prompt: str, tail_chars: int) -> str:
        start = max(len(prompt) - tail_chars, 0)
        for _ in range(2):
            boundary = prompt.rfind("\n", 0, start)
            if boundary == -1:
                return prompt
            start = boundary
        return prompt[start + 1 :]

    def _extract_text_from_response(self, payload: dict[str, object], provider: str) -> str:
        if provider == "google":
            candidates = payload.get("candidates", [])
            if isinstance(candidates, list):
                for candidate in candidates:
                    content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
                    parts = content.get("parts", []) if isinstance(content, dict) else []
                    texts = [
                        str(part.get("text", "")).strip()
                        for part in parts
                        if isinstance(part, dict) and part.get("text")
                    ]
                    if texts:
                        return "\n".join(texts)
        elif provider == "anthropic":
            content = payload.get("content", [])
            if isinstance(content, list):
                texts = [
                    str(item.get("text", "")).strip()
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                ]
                if texts:
                    return "\n".join(texts)
        elif provider == "openai":
            choices = payload.get("choices", [])
            if isinstance(choices, list):
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    message = choice.get("message", {})
                    content = message.get("content", "") if isinstance(message, dict) else ""
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                    if isinstance(content, list):
                        texts = [
                            str(item.get("text", "")).strip()
                            for item in content
                            if isinstance(item, dict) and item.get("text")
                        ]
                        if texts:
                            return "\n".join(texts)
        elif provider == "ollama":
            response_text = payload.get("response", "")
            if isinstance(response_text, str) and response_text.strip():
                return response_text.strip()
            message = payload.get("message", {})
            if isinstance(message, dict):
                content = message.get("content", "")
                if isinstance(content, str):
                    return content.strip()

        raise ValueError(f"Unable to extract text from {provider} response")
