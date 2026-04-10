from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

from zcore.config import get_nested, load_config
from zcore.runtime import RuntimePaths
from zcore.utils.prompts import load_prompt_template
from zcore.utils.tokens import estimate_tokens, get_context_window


@dataclass
class TokenAnalysis:
    total_tokens: int
    context_window: int
    usage_pct: float
    tokens_remaining: int
    should_compact: bool
    urgency: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["usage_pct"] = round(self.usage_pct, 2)
        return payload


@dataclass
class CompactResult:
    summary: str
    preserved_messages: list[dict[str, Any]]
    original_token_count: int
    compacted_token_count: int
    compression_ratio: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["compression_ratio"] = round(self.compression_ratio, 4)
        return payload


class ContextEngine:
    MAX_OUTPUT_TOKENS = 20_000
    WARNING_THRESHOLD_TOKENS = 20_000
    DEFAULT_BUFFER_TOKENS = 13_000
    DEFAULT_COMPACT_THRESHOLD_PCT = 80
    PRESERVED_TAIL_MESSAGES = 5
    COMPACT_HEAD_MESSAGES = 4
    COMPACT_TAIL_MESSAGES = 8
    COMPACT_MIN_MESSAGE_BUDGET = 512

    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or RuntimePaths.discover()
        self.config = load_config(self.paths)
        self.buffer_tokens = int(
            get_nested(self.config, "context", "buffer_tokens", default=self.DEFAULT_BUFFER_TOKENS)
        )
        self.compact_threshold_pct = int(
            get_nested(
                self.config,
                "context",
                "compact_threshold_pct",
                default=self.DEFAULT_COMPACT_THRESHOLD_PCT,
            )
        )

    def analyze(self, messages: list[dict[str, Any]], model: str) -> TokenAnalysis:
        total_tokens = self._estimate_messages_tokens(messages, model)
        context_window = get_context_window(model)
        tokens_remaining = max(context_window - total_tokens, 0)
        usage_pct = (total_tokens / context_window * 100.0) if context_window else 0.0

        hard_limit_threshold = max(context_window - self.MAX_OUTPUT_TOKENS - self.buffer_tokens, 0)
        early_warning_threshold = max(hard_limit_threshold - self.WARNING_THRESHOLD_TOKENS, 0)
        pct_threshold = max(int(context_window * (self.compact_threshold_pct / 100.0)), 0)
        thresholds = [value for value in (early_warning_threshold, pct_threshold) if value > 0]
        compact_threshold = min(thresholds) if thresholds else hard_limit_threshold
        should_compact = total_tokens >= compact_threshold

        if total_tokens >= hard_limit_threshold or usage_pct >= 90:
            urgency = "critical"
        elif should_compact or usage_pct >= max(self.compact_threshold_pct - 5, 1):
            urgency = "warning"
        else:
            urgency = "normal"

        return TokenAnalysis(
            total_tokens=total_tokens,
            context_window=context_window,
            usage_pct=usage_pct,
            tokens_remaining=tokens_remaining,
            should_compact=should_compact,
            urgency=urgency,
        )

    def should_compact(self, messages: list[dict[str, Any]], model: str) -> bool:
        return self.analyze(messages, model).should_compact

    def get_compact_prompt(
        self,
        messages: list[dict[str, Any]],
        *,
        max_prompt_tokens: int | None = None,
        target_model: str = "sonnet",
    ) -> str:
        base_prompt = load_prompt_template("compact.md")
        transcript_messages = messages
        trimming_applied = False
        if max_prompt_tokens is not None:
            transcript_messages, trimming_applied = self._trim_messages_to_budget(
                messages,
                max_prompt_tokens=max_prompt_tokens,
                model=target_model,
                prompt_prefix=base_prompt,
            )

        transcript = self._serialize_messages(transcript_messages)
        if trimming_applied:
            transcript = (
                "[Transcript trimmed to fit Ghost Agent context window. "
                "Head, tail, and sampled middle messages were preserved.]\n\n"
                + transcript
            )
        return f"{base_prompt}\n\n## Conversation Transcript\n\n{transcript}\n"

    def apply_compact(
        self,
        messages: list[dict[str, Any]],
        model: str = "sonnet",
        *,
        ghost_agent=None,
        session_id: str | None = None,
    ) -> CompactResult:
        analysis = self.analyze(messages, model)
        preserved_messages = self._preserve_tail(messages)
        heuristic_summary = self._heuristic_summary(messages, analysis)

        mode = "fallback"
        reason = "heuristic_only"
        summary = heuristic_summary

        if ghost_agent is not None:
            prompt_budget = None
            prompt_model = model
            if hasattr(ghost_agent, "max_prompt_tokens"):
                prompt_budget = ghost_agent.max_prompt_tokens()
            if hasattr(ghost_agent, "prompt_model"):
                prompt_model = ghost_agent.prompt_model()
            response = ghost_agent.generate(
                self.get_compact_prompt(messages, max_prompt_tokens=prompt_budget, target_model=prompt_model),
                fallback_text=heuristic_summary,
            )
            summary = str(response.get("text", "")).strip() or heuristic_summary
            mode = str(response.get("mode", mode))
            reason = str(response.get("reason", reason))

        compacted_token_count = estimate_tokens(
            summary + "\n" + self._serialize_messages(preserved_messages),
            model,
        )
        original_token_count = analysis.total_tokens
        compression_ratio = (
            compacted_token_count / original_token_count if original_token_count else 0.0
        )

        return CompactResult(
            summary=summary,
            preserved_messages=preserved_messages,
            original_token_count=original_token_count,
            compacted_token_count=compacted_token_count,
            compression_ratio=compression_ratio,
            metadata={
                "mode": mode,
                "reason": reason,
                "session_id": session_id,
                "analysis": analysis.to_dict(),
            },
        )

    def _estimate_messages_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        return estimate_tokens(self._serialize_messages(messages), model)

    def _serialize_messages(self, messages: list[dict[str, Any]]) -> str:
        blocks: list[str] = []
        for index, message in enumerate(messages, start=1):
            role = str(message.get("role", "unknown"))
            content = self._message_content(message)
            if not content:
                continue
            blocks.append(f"### Message {index} ({role})\n{content}")
        return "\n\n".join(blocks)

    def _message_content(self, message: dict[str, Any]) -> str:
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        return json.dumps(content, ensure_ascii=False, indent=2).strip()

    def _preserve_tail(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tail = messages[-self.PRESERVED_TAIL_MESSAGES :]
        return [dict(message) for message in tail]

    def _heuristic_summary(self, messages: list[dict[str, Any]], analysis: TokenAnalysis) -> str:
        primary_request = self._first_non_empty_message(messages, "user") or "No explicit user request captured."
        decisions = self._collect_tagged_messages(messages, "[decision]") or [
            "No explicit decision markers found in the transcript."
        ]
        progress = self._recent_messages(messages, limit=3) or ["No concrete progress messages captured."]
        blockers = self._collect_blockers(messages)
        current_state = self._recent_messages(messages, limit=2) or ["No recent state available."]
        next_steps = self._derive_next_steps(messages, blockers)

        sections = [
            "## 1. Primary Request and Intent",
            primary_request,
            "",
            "## 2. Key Technical Decisions Made",
            self._as_bullets(decisions),
            "",
            "## 3. Current Progress",
            self._as_bullets(progress + [f"Token analysis: {analysis.total_tokens}/{analysis.context_window} tokens."]),
            "",
            "## 4. Open Issues and Blockers",
            self._as_bullets(blockers),
            "",
            "## 5. Exact Current State",
            self._as_bullets(current_state),
            "",
            "## 6. Immediate Next Steps",
            self._as_bullets(next_steps),
        ]
        return "\n".join(sections).strip() + "\n"

    def _first_non_empty_message(self, messages: list[dict[str, Any]], role: str) -> str:
        for message in messages:
            if str(message.get("role", "")).lower() != role:
                continue
            content = self._message_content(message)
            if content:
                return content[:600]
        return ""

    def _collect_tagged_messages(self, messages: list[dict[str, Any]], tag: str) -> list[str]:
        collected: list[str] = []
        tag_lower = tag.lower()
        for message in messages:
            content = self._message_content(message)
            if not content:
                continue
            if tag_lower in content.lower():
                collected.append(content[:400])
        return collected[:5]

    def _recent_messages(self, messages: list[dict[str, Any]], limit: int) -> list[str]:
        lines: list[str] = []
        for message in messages[-limit:]:
            role = str(message.get("role", "unknown"))
            content = self._message_content(message)
            if content:
                lines.append(f"{role}: {content[:400]}")
        return lines

    def _collect_blockers(self, messages: list[dict[str, Any]]) -> list[str]:
        markers = ("blocker", "todo", "fixme", "error", "failed", "待完成", "阻塞")
        blockers: list[str] = []
        for message in messages:
            content = self._message_content(message)
            lowered = content.lower()
            if content and any(marker in lowered for marker in markers):
                blockers.append(content[:400])
        return blockers[:5] or ["No explicit blockers identified."]

    def _derive_next_steps(self, messages: list[dict[str, Any]], blockers: list[str]) -> list[str]:
        if blockers and blockers[0] != "No explicit blockers identified.":
            return [f"Resolve blocker: {blockers[0][:180]}"]

        recent_user = self._first_non_empty_message(list(reversed(messages)), "user")
        if recent_user:
            return [f"Continue with the most recent user request: {recent_user[:180]}"]
        return ["Continue implementation from the latest working state."]

    def _as_bullets(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items if item) or "- None"

    def _trim_messages_to_budget(
        self,
        messages: list[dict[str, Any]],
        *,
        max_prompt_tokens: int,
        model: str,
        prompt_prefix: str,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not messages:
            return [], False

        prefix_tokens = estimate_tokens(prompt_prefix + "\n\n## Conversation Transcript\n\n", model)
        available_tokens = max(max_prompt_tokens - prefix_tokens, self.COMPACT_MIN_MESSAGE_BUDGET)
        serialized_full = self._serialize_messages(messages)
        if estimate_tokens(serialized_full, model) <= available_tokens:
            return [dict(message) for message in messages], False

        selected_indices: list[int] = []
        for index in range(min(self.COMPACT_HEAD_MESSAGES, len(messages))):
            selected_indices.append(index)
        tail_start = max(len(messages) - self.COMPACT_TAIL_MESSAGES, 0)
        for index in range(tail_start, len(messages)):
            if index not in selected_indices:
                selected_indices.append(index)

        middle_candidates = [
            index
            for index in self._sample_middle_indices(len(messages))
            if index not in selected_indices
        ]

        prioritized_indices = self._prioritize_indices(selected_indices, middle_candidates, len(messages))
        max_slots = max(available_tokens // self.COMPACT_MIN_MESSAGE_BUDGET, 2)
        chosen_indices = prioritized_indices[:max_slots]
        ordered_indices = sorted(chosen_indices)
        trimmed: list[dict[str, Any]] = []
        used_tokens = 0
        inserted_gap_notice = False

        for position, index in enumerate(ordered_indices):
            if trimmed and index > ordered_indices[position - 1] + 1 and not inserted_gap_notice:
                gap_notice = {
                    "role": "system",
                    "content": "[Earlier middle messages omitted for compact pre-trimming.]",
                }
                notice_tokens = estimate_tokens(self._serialize_messages([gap_notice]), model)
                if used_tokens + notice_tokens <= available_tokens:
                    trimmed.append(gap_notice)
                    used_tokens += notice_tokens
                    inserted_gap_notice = True

            message = dict(messages[index])
            message_tokens = estimate_tokens(self._serialize_messages([message]), model)
            remaining_slots = max(len(ordered_indices) - position - 1, 0)
            reserve_for_remaining = remaining_slots * self.COMPACT_MIN_MESSAGE_BUDGET
            current_budget = max(available_tokens - used_tokens - reserve_for_remaining, self.COMPACT_MIN_MESSAGE_BUDGET)

            fitted_message = message
            fitted_tokens = message_tokens
            if message_tokens > current_budget:
                fitted_message = self._truncate_message_content(message, current_budget, model)
                fitted_tokens = estimate_tokens(self._serialize_messages([fitted_message]), model)

            if fitted_tokens > max(available_tokens - used_tokens, 0):
                continue

            trimmed.append(fitted_message)
            used_tokens += fitted_tokens

        if not trimmed:
            shortened = self._truncate_message_content(dict(messages[-1]), available_tokens, model)
            return [shortened], True

        return trimmed, True

    def _sample_middle_indices(self, length: int) -> list[int]:
        start = self.COMPACT_HEAD_MESSAGES
        end = max(length - self.COMPACT_TAIL_MESSAGES, start)
        if end <= start:
            return []

        span = end - start
        if span <= 6:
            return list(range(start, end))

        checkpoints = [0.15, 0.35, 0.55, 0.75, 0.9]
        indices = {start + min(int(span * point), span - 1) for point in checkpoints}
        return sorted(indices)

    def _prioritize_indices(
        self,
        selected_indices: list[int],
        middle_candidates: list[int],
        length: int,
    ) -> list[int]:
        priority: list[int] = []
        anchors = [0, length - 1]
        for index in anchors + selected_indices + middle_candidates:
            if 0 <= index < length and index not in priority:
                priority.append(index)
        return priority

    def _truncate_message_content(self, message: dict[str, Any], token_budget: int, model: str) -> dict[str, Any]:
        content = self._message_content(message)
        if not content:
            return message

        if token_budget <= self.COMPACT_MIN_MESSAGE_BUDGET:
            max_chars = min(len(content), 180)
            head = content[: max_chars // 2]
            tail = content[-max_chars // 2 :] if len(content) > max_chars else ""
            message["content"] = head + "\n...[truncated]...\n" + tail
            return message

        low = 0
        high = len(content)
        best = content[: min(len(content), 100)] + "\n...[truncated]...\n" + content[-100:]
        max_iterations = 40  # O(log n) guard: 2^40 > any realistic content length
        for _ in range(max_iterations):
            if low > high:
                break
            middle = (low + high) // 2
            head_len = max(middle // 3, 40)
            tail_len = max(middle - head_len, 40)
            candidate = content[:head_len] + "\n...[truncated]...\n" + content[-tail_len:]
            candidate_tokens = estimate_tokens(self._serialize_messages([{**message, "content": candidate}]), model)
            if candidate_tokens <= token_budget:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1

        message["content"] = best
        return message
