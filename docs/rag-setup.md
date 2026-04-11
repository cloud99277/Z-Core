# RAG Setup

Z-Core keeps the base package dependency-free. L3 knowledge retrieval is exposed through the optional `rag` extra.

## Install

```bash
pip install zcore[rag]
```

For editable local development:

```bash
pip install -e ".[rag]"
```

## Configure

```bash
zcore init
zcore config set knowledge.source_dir /path/to/knowledge
```

Default config section:

```toml
[knowledge]
source_dir = ""
embedding_mode = "local"
embedding_model = "BAAI/bge-small-zh-v1.5"
search_mode = "hybrid"
```

`ZCORE_KNOWLEDGE_DB` overrides the default database location. Otherwise Z-Core uses `~/.lancedb/knowledge`.

## Index And Search

```bash
zcore knowledge index --path /path/to/knowledge
zcore knowledge search --query "memory engine" --limit 5
zcore knowledge search --query "memory engine" --limit 5 --json
```

If `knowledge.source_dir` is already set, `zcore knowledge index` can run without `--path`.

## Memory Search Integration

`zcore memory search` always returns L2 topic memories first. When `zcore[rag]` is installed and the knowledge index exists, it appends L3 knowledge hits. If the optional stack is missing, the command degrades cleanly and still returns L2.
