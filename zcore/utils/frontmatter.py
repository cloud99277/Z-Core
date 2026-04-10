from __future__ import annotations

import re
from typing import Any

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?)(?:\n---\s*(?:\n|$))", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, Any]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    lines = match.group("body").splitlines()
    result, index = _parse_block(lines, 0, 0)
    _skip_blank(lines, index)
    if not isinstance(result, dict):
        raise ValueError("Frontmatter root must be a mapping")
    return result


def _parse_block(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    index = _skip_blank(lines, index)
    if index >= len(lines):
        return {}, index
    current_indent = _indent_of(lines[index])
    if current_indent < indent:
        return {}, index
    if _content_of(lines[index]).startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_dict(lines, index, indent)


def _parse_dict(lines: list[str], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        index = _skip_blank(lines, index)
        if index >= len(lines):
            break
        line = lines[index]
        if _indent_of(line) < indent:
            break
        if _indent_of(line) != indent:
            raise ValueError(f"Unexpected indentation in frontmatter: {line!r}")
        content = _content_of(line)
        if content.startswith("- "):
            break
        key, has_value, value_text = _split_mapping(content)
        index += 1
        if has_value:
            if value_text in {"|", ">"}:
                value, index = _parse_block_scalar(lines, index, indent + 2, folded=value_text == ">")
            else:
                value = _parse_inline_value(value_text)
        else:
            next_index = _skip_blank(lines, index)
            if next_index >= len(lines) or _indent_of(lines[next_index]) <= indent:
                value = {}
                index = next_index
            else:
                value, index = _parse_block(lines, next_index, indent + 2)
        result[key] = value
    return result, index


def _parse_list(lines: list[str], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        index = _skip_blank(lines, index)
        if index >= len(lines):
            break
        line = lines[index]
        if _indent_of(line) < indent:
            break
        if _indent_of(line) != indent:
            raise ValueError(f"Unexpected indentation in list: {line!r}")
        content = _content_of(line)
        if not content.startswith("- "):
            break
        item_text = content[2:].strip()
        index += 1
        if not item_text:
            item, index = _parse_block(lines, index, indent + 2)
            result.append(item)
            continue
        if _looks_like_mapping(item_text):
            key, has_value, value_text = _split_mapping(item_text)
            item: dict[str, Any] = {}
            if has_value:
                if value_text in {"|", ">"}:
                    value, index = _parse_block_scalar(lines, index, indent + 4, folded=value_text == ">")
                else:
                    value = _parse_inline_value(value_text)
                item[key] = value
            else:
                item[key] = {}
            if index < len(lines):
                next_index = _skip_blank(lines, index)
                if next_index < len(lines) and _indent_of(lines[next_index]) > indent:
                    nested, index = _parse_block(lines, next_index, indent + 2)
                    if isinstance(nested, dict):
                        if not has_value or item[key] == {}:
                            item[key] = nested
                        else:
                            item.update(nested)
                    else:
                        raise ValueError("List item mapping cannot contain nested list without a key")
            result.append(item)
            continue
        result.append(_parse_inline_value(item_text))
    return result, index


def _parse_block_scalar(lines: list[str], index: int, indent: int, *, folded: bool) -> tuple[str, int]:
    values: list[str] = []
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            values.append("")
            index += 1
            continue
        current_indent = _indent_of(line)
        if current_indent < indent:
            break
        values.append(line[indent:])
        index += 1
    if folded:
        chunks: list[str] = []
        paragraph: list[str] = []
        for value in values:
            if value == "":
                if paragraph:
                    chunks.append(" ".join(part.strip() for part in paragraph if part.strip()))
                    paragraph = []
                chunks.append("")
            else:
                paragraph.append(value)
        if paragraph:
            chunks.append(" ".join(part.strip() for part in paragraph if part.strip()))
        return "\n".join(chunk for chunk in chunks if chunk != "" or len(chunks) == 1).strip(), index
    return "\n".join(values).rstrip(), index


def _parse_inline_value(text: str) -> Any:
    stripped = _strip_comment(text).strip()
    if stripped == "":
        return ""
    if stripped[0] in "\"'" and stripped[-1] == stripped[0]:
        return stripped[1:-1]
    if stripped in {"true", "false"}:
        return stripped == "true"
    if stripped in {"null", "None", "~"}:
        return None
    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1].strip()
        if not inner:
            return []
        return [_parse_inline_value(part.strip()) for part in _split_inline_list(inner)]
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    if re.fullmatch(r"-?\d+\.\d+", stripped):
        return float(stripped)
    return stripped


def _split_inline_list(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            continue
        if char == ",":
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        items.append("".join(current).strip())
    return items


def _split_mapping(content: str) -> tuple[str, bool, str]:
    match = re.match(r"([^:]+):(.*)$", content)
    if not match:
        raise ValueError(f"Invalid frontmatter line: {content!r}")
    key = match.group(1).strip()
    value_text = match.group(2).lstrip()
    return key, value_text != "", value_text


def _looks_like_mapping(content: str) -> bool:
    if ":" not in content:
        return False
    if content.startswith(("http://", "https://")):
        return False
    key, _, _ = _split_mapping(content)
    return bool(key)


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _content_of(line: str) -> str:
    return line.lstrip(" ")


def _skip_blank(lines: list[str], index: int) -> int:
    while index < len(lines):
        content = _content_of(lines[index]).strip()
        if content and not content.startswith("#"):
            break
        index += 1
    return index


def _strip_comment(text: str) -> str:
    quote: str | None = None
    for idx, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "#":
            if idx == 0 or text[idx - 1].isspace():
                return text[:idx].rstrip()
    return text
