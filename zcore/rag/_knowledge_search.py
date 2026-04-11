from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from zcore.config import get_nested
from zcore.rag._knowledge_index import EmbeddingEngine, TABLE_NAME, _import_lancedb
from zcore.runtime import RuntimePaths


@dataclass
class SearchResult:
    chunk_id: str
    text: str
    score: float
    source_file: str
    heading_path: list[str]
    line_range: str
    metadata: dict[str, object]
    fallback: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if not payload["fallback"]:
            payload.pop("fallback", None)
        return payload


def _df_to_results(df) -> list[SearchResult]:
    results: list[SearchResult] = []
    for _, row in df.iterrows():
        raw_heading = row.get("heading_path", "[]")
        try:
            heading_path = json.loads(raw_heading) if isinstance(raw_heading, str) else list(raw_heading)
        except (json.JSONDecodeError, TypeError):
            heading_path = []

        score = 0.0
        if "_distance" in row:
            score = round(max(0.0, 1.0 - float(row["_distance"])), 4)
        elif "_score" in row:
            score = round(float(row["_score"]), 4)

        metadata: dict[str, object] = {}
        for field in ("tags", "scope", "author", "date", "title"):
            value = row.get(field, "")
            if value:
                metadata[field] = value

        results.append(
            SearchResult(
                chunk_id=str(row.get("chunk_id", "")),
                text=str(row.get("text", "")),
                score=score,
                source_file=str(row.get("source_file", "")),
                heading_path=heading_path,
                line_range=f"L{row.get('start_line', 0)}-L{row.get('end_line', 0)}",
                metadata=metadata,
            )
        )
    return results


def _open_table(paths: RuntimePaths):
    lancedb = _import_lancedb()
    db = lancedb.connect(str(paths.knowledge_db_path))
    try:
        return db.open_table(TABLE_NAME)
    except Exception as exc:
        raise FileNotFoundError(
            f"No knowledge index found at {paths.knowledge_db_path}. Run `zcore knowledge index --path <dir>` first."
        ) from exc


def _search_vector(table, query_vector: list[float], limit: int) -> list[SearchResult]:
    return _df_to_results(table.search(query_vector).limit(limit).to_pandas())


def _search_fts(table, query: str, limit: int) -> list[SearchResult]:
    try:
        return _df_to_results(table.search(query, query_type="fts").limit(limit).to_pandas())
    except Exception:
        return []


def _search_hybrid(table, query: str, query_vector: list[float], limit: int) -> list[SearchResult]:
    vector_results = _search_vector(table, query_vector, limit * 2)
    fts_results = _search_fts(table, query, limit * 2)
    if not fts_results:
        for result in vector_results[:limit]:
            result.fallback = "fts_unavailable"
        return vector_results[:limit]

    scores: dict[str, float] = {}
    merged: dict[str, SearchResult] = {}
    k = 60

    for rank, result in enumerate(vector_results):
        scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1.0 / (k + rank + 1)
        merged.setdefault(result.chunk_id, result)
    for rank, result in enumerate(fts_results):
        scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1.0 / (k + rank + 1)
        merged.setdefault(result.chunk_id, result)

    ranked_ids = sorted(scores.keys(), key=lambda item: scores[item], reverse=True)[:limit]
    results: list[SearchResult] = []
    for chunk_id in ranked_ids:
        result = merged[chunk_id]
        result.score = round(scores[chunk_id], 6)
        results.append(result)
    return results


def search_knowledge(
    query: str,
    *,
    limit: int = 10,
    paths: RuntimePaths | None = None,
    config: dict[str, object] | None = None,
) -> list[SearchResult]:
    needle = query.strip()
    if not needle:
        return []

    resolved_paths = paths or RuntimePaths.discover()
    resolved_config = config or {}
    table = _open_table(resolved_paths)
    mode = str(get_nested(resolved_config, "knowledge", "search_mode", default="hybrid"))
    model_name = str(get_nested(resolved_config, "knowledge", "embedding_model", default="BAAI/bge-small-zh-v1.5"))
    embedding_mode = str(get_nested(resolved_config, "knowledge", "embedding_mode", default="local"))

    if mode == "fts":
        return _search_fts(table, needle, limit)

    engine = EmbeddingEngine(mode=embedding_mode, model_name=model_name)
    query_vector = engine.embed_query(needle)
    if mode == "vector":
        return _search_vector(table, query_vector, limit)
    return _search_hybrid(table, needle, query_vector, limit)
