from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class MarkdownChunk:
    text: str
    heading_path: list[str] = field(default_factory=list)
    level: int = 0
    source_file: str = ""
    start_line: int = 0
    end_line: int = 0
    metadata: dict[str, object] = field(default_factory=dict)
    chunk_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
    try:
        import frontmatter  # pyright: ignore[reportMissingImports]
    except ImportError:
        frontmatter = None

    if frontmatter is not None:
        post = frontmatter.loads(content)
        return dict(post.metadata), post.content

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}, content

    metadata: dict[str, object] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata, content[match.end() :]


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


def _split_large_chunk(text: str, max_size: int) -> list[str]:
    if len(text) <= max_size:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines():
        line_len = len(line) + 1
        if line.strip() == "" and current_len >= max_size // 2:
            parts.append("\n".join(current))
            current = []
            current_len = 0
            continue
        current.append(line)
        current_len += line_len
    if current:
        parts.append("\n".join(current))
    return parts or [text]


def chunk_markdown(
    content: str,
    *,
    source_file: str,
    metadata: dict[str, object] | None = None,
    min_size: int = 50,
    max_size: int = 2000,
    max_heading_level: int = 3,
) -> list[MarkdownChunk]:
    metadata = metadata or {}
    lines = content.splitlines()
    heading_stack: list[tuple[int, str]] = []
    chunks: list[MarkdownChunk] = []
    current_lines: list[str] = []
    current_start = 1

    def flush(end_line: int) -> None:
        nonlocal current_lines, current_start
        text = "\n".join(current_lines).strip()
        if not text:
            current_lines = []
            return
        heading_path = [f"{'#' * level} {title}" for level, title in heading_stack]
        chunk_level = heading_stack[-1][0] if heading_stack else 0
        for segment in _split_large_chunk(text, max_size):
            segment = segment.strip()
            if not segment:
                continue
            chunks.append(
                MarkdownChunk(
                    text=segment,
                    heading_path=list(heading_path),
                    level=chunk_level,
                    source_file=source_file,
                    start_line=current_start,
                    end_line=end_line,
                    metadata=dict(metadata),
                )
            )
        current_lines = []

    for index, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            if level <= max_heading_level:
                flush(index - 1)
                current_start = index
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))
        current_lines.append(line)
    flush(len(lines))

    if len(chunks) > 1:
        merged: list[MarkdownChunk] = [chunks[0]]
        for chunk in chunks[1:]:
            if len(merged[-1].text) < min_size:
                merged[-1].text += "\n\n" + chunk.text
                merged[-1].end_line = chunk.end_line
            else:
                merged.append(chunk)
        if len(merged) > 1 and len(merged[-1].text) < min_size:
            merged[-2].text += "\n\n" + merged[-1].text
            merged[-2].end_line = merged[-1].end_line
            merged.pop()
        chunks = merged

    for chunk in chunks:
        path_str = "::".join(chunk.heading_path) if chunk.heading_path else "_root_"
        raw_id = f"{source_file}::{path_str}::{chunk.start_line}"
        chunk.chunk_id = hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:12]
    return chunks


def parse_file(filepath: str, *, min_size: int = 50, max_size: int = 2000) -> list[MarkdownChunk]:
    path = Path(filepath)
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(content)
    return chunk_markdown(
        body,
        source_file=str(path),
        metadata=metadata,
        min_size=min_size,
        max_size=max_size,
    )


def scan_directory(
    directory: str,
    *,
    extensions: list[str] | None = None,
    min_size: int = 50,
    max_size: int = 2000,
) -> list[MarkdownChunk]:
    root = Path(directory)
    if not root.is_dir():
        return []
    allowed = extensions or [".md", ".markdown"]
    chunks: list[MarkdownChunk] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in allowed:
            chunks.extend(parse_file(str(path), min_size=min_size, max_size=max_size))
    return chunks
