from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from zcore.runtime import RuntimePaths

if TYPE_CHECKING:
    from zcore.rag._knowledge_search import SearchResult


RAG_INSTALL_HINT = "RAG dependencies missing. Run 'pip install zcore[rag]' to enable L3 capabilities."


class RagDependencyError(ImportError):
    """Raised when optional RAG dependencies are unavailable."""


def ensure_available() -> None:
    try:
        importlib.import_module("lancedb")
    except ImportError as exc:
        raise RagDependencyError(RAG_INSTALL_HINT) from exc


def is_available() -> bool:
    try:
        ensure_available()
    except RagDependencyError:
        return False
    return True


def get_indexer(paths: RuntimePaths | None = None, config: dict[str, object] | None = None):
    ensure_available()
    from zcore.rag._knowledge_index import KnowledgeIndexer

    return KnowledgeIndexer(paths=paths, config=config)


def index_knowledge(
    *,
    source_dir: str,
    paths: RuntimePaths | None = None,
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    return get_indexer(paths=paths, config=config).index(source_dir)


def search_knowledge(
    query: str,
    *,
    limit: int = 10,
    paths: RuntimePaths | None = None,
    config: dict[str, object] | None = None,
) -> list["SearchResult"]:
    ensure_available()
    from zcore.rag._knowledge_search import search_knowledge as _search_knowledge

    return _search_knowledge(query, limit=limit, paths=paths, config=config)


__all__ = [
    "RAG_INSTALL_HINT",
    "RagDependencyError",
    "ensure_available",
    "get_indexer",
    "index_knowledge",
    "is_available",
    "search_knowledge",
]
