from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from zcore.config import get_nested
from zcore.rag._md_chunker import MarkdownChunk, scan_directory
from zcore.runtime import RuntimePaths


TABLE_NAME = "knowledge_chunks"


def _import_lancedb():
    import lancedb  # pyright: ignore[reportMissingImports]

    return lancedb


@dataclass
class EmbeddingEngine:
    mode: str = "local"
    model_name: str = "BAAI/bge-small-zh-v1.5"

    def __post_init__(self) -> None:
        self._model = None
        self._dimension = None
        self._is_bge = "bge" in self.model_name.lower()

    def _init_local(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for knowledge indexing. Run 'pip install zcore[rag]'."
            ) from exc
        self._model = SentenceTransformer(self.model_name)
        self._dimension = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._model is None:
            self._init_local()
        assert self._model is not None
        vectors = self._model.encode(texts, show_progress_bar=len(texts) > 50)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, query: str) -> list[float]:
        text = query
        if self._is_bge:
            text = "为这个句子生成表示以用于检索相关文章：" + query
        return self.embed([text])[0]


def _to_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)


def _file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _chunks_to_records(chunks: list[MarkdownChunk], vectors: list[list[float]]) -> list[dict[str, object]]:
    now = datetime.now(UTC).isoformat()
    records: list[dict[str, object]] = []
    for chunk, vector in zip(chunks, vectors):
        file_path = Path(chunk.source_file)
        metadata = chunk.metadata
        title = str(metadata.get("title", "") or (chunk.heading_path[0] if chunk.heading_path else ""))
        records.append(
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "vector": vector,
                "source_file": chunk.source_file,
                "heading_path": json.dumps(chunk.heading_path, ensure_ascii=False),
                "level": chunk.level,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "tags": _to_str(metadata.get("tags", "")),
                "scope": _to_str(metadata.get("scope", "")),
                "author": _to_str(metadata.get("author", "")),
                "date": _to_str(metadata.get("date", "")),
                "title": title,
                "indexed_at": now,
                "file_hash": _file_hash(file_path) if file_path.exists() else "",
                "schema_version": "1.0",
            }
        )
    return records


class KnowledgeIndexer:
    def __init__(self, *, paths: RuntimePaths | None = None, config: dict[str, object] | None = None):
        self.paths = paths or RuntimePaths.discover()
        self.config = config or {}
        self.db_path = self.paths.knowledge_db_path
        self.embedding_mode = str(get_nested(self.config, "knowledge", "embedding_mode", default="local"))
        self.embedding_model = str(
            get_nested(self.config, "knowledge", "embedding_model", default="BAAI/bge-small-zh-v1.5")
        )

    def index(self, source_dir: str) -> dict[str, object]:
        source_path = Path(source_dir).expanduser().resolve()
        if not source_path.is_dir():
            raise ValueError(f"Knowledge source directory not found: {source_dir}")

        chunks = scan_directory(str(source_path))
        if not chunks:
            return {
                "ok": True,
                "source_dir": str(source_path),
                "db_path": str(self.db_path),
                "indexed_chunks": 0,
                "indexed_files": 0,
                "table": TABLE_NAME,
            }

        engine = EmbeddingEngine(mode=self.embedding_mode, model_name=self.embedding_model)
        vectors = engine.embed([chunk.text for chunk in chunks])
        records = _chunks_to_records(chunks, vectors)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        lancedb = _import_lancedb()
        db = lancedb.connect(str(self.db_path))
        try:
            db.drop_table(TABLE_NAME)
        except Exception:
            pass
        db.create_table(TABLE_NAME, data=records)

        indexed_files = len({chunk.source_file for chunk in chunks})
        return {
            "ok": True,
            "source_dir": str(source_path),
            "db_path": str(self.db_path),
            "indexed_chunks": len(chunks),
            "indexed_files": indexed_files,
            "table": TABLE_NAME,
        }
