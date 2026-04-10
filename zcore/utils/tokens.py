from __future__ import annotations

import math
import re


DEFAULT_CONTEXT_WINDOW = 200_000

_MODEL_ALIASES = {
    "sonnet": "sonnet",
    "claude-3-7-sonnet": "sonnet",
    "claude-3.7-sonnet": "sonnet",
    "claude-sonnet": "sonnet",
    "opus": "opus",
    "claude-opus": "opus",
    "haiku": "haiku",
    "gpt-4o": "gpt-4o",
    "gpt4o": "gpt-4o",
    "gpt-4-turbo": "gpt-4-turbo",
    "gpt4-turbo": "gpt-4-turbo",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-pro": "gemini-2.5-pro",
    "gemini-flash": "gemini-2.5-flash",
}

_CONTEXT_WINDOWS = {
    "sonnet": 200_000,
    "opus": 200_000,
    "haiku": 200_000,
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.5-flash": 1_000_000,
}


def normalize_model_name(model: str) -> str:
    lowered = model.strip().lower()
    if lowered in _MODEL_ALIASES:
        return _MODEL_ALIASES[lowered]

    for alias, normalized in _MODEL_ALIASES.items():
        if alias in lowered:
            return normalized
    return lowered or "sonnet"


def get_context_window(model: str) -> int:
    normalized = normalize_model_name(model)
    return _CONTEXT_WINDOWS.get(normalized, DEFAULT_CONTEXT_WINDOW)


def _estimate_with_tiktoken(text: str, model: str) -> int | None:
    try:
        import tiktoken
    except ImportError:
        return None

    normalized = normalize_model_name(model)
    try:
        if normalized in {"gpt-4o", "gpt-4-turbo"}:
            encoding = tiktoken.encoding_for_model(normalized)
        else:
            try:
                encoding = tiktoken.get_encoding("o200k_base")
            except ValueError:
                encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        return None


def _estimate_with_character_mix(text: str) -> int:
    if not text.strip():
        return 0

    chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    whitespace_chars = sum(1 for char in text if char.isspace())
    other_chars = max(len(text) - chinese_chars - ascii_chars, 0)
    word_count = len(re.findall(r"\b[\w-]+\b", text, flags=re.UNICODE))

    english_estimate = max((ascii_chars - whitespace_chars) / 4, word_count * 0.75)
    estimate = chinese_chars * 1.5 + english_estimate + other_chars * 1.2
    return max(1, int(math.ceil(estimate)))


def estimate_tokens(text: str, model: str = "sonnet") -> int:
    encoded = _estimate_with_tiktoken(text, model)
    if encoded is not None:
        return encoded
    return _estimate_with_character_mix(text)
