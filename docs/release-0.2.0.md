# Z-Core 0.2.0 Release Notes

## Summary

`0.2.0` is the first standalone release of Z-Core as an independent repository.

It packages the full V2 runtime middleware extracted from the original KitClaw codebase into a publishable Python project with:

- 9 runtime engines
- 35 CLI commands
- zero runtime dependencies beyond Python 3.11+
- a standalone regression suite
- publish-ready packaging metadata

## Highlights

- Standalone repository extraction completed for `zcore/`, `tests/`, and `v2/`
- Session, memory, context, workflow, governance, observability, and agent-setup flows all ship in one CLI
- Official package version frozen at `0.2.0`
- README and V2 docs aligned to standalone `Z-Core` naming
- Packaging metadata expanded for distribution workflows

## Release Readiness Fixes

- Fixed `RuntimePaths.discover()` so isolated `HOME` environments resolve runtime paths correctly
- Removed legacy test bootstrap assumptions about old `rag-engine` / `governance` directories
- Replaced stale KitClaw-specific publish/install references in release-facing docs

## Verification

Validated in the project virtual environment with:

```bash
python -m unittest discover tests -v
python -m build
python -m twine check dist/*
```

Expected outcome for this release:

- `39` unittest cases pass
- both wheel and sdist artifacts build successfully
- package metadata and README render cleanly for distribution

## Notes

- The `v2/` directory remains intentionally included as the design and delivery record for the extracted runtime
- Historical references to KitClaw inside design artifacts are preserved where they describe origin or project history, but publish-facing install guidance now targets Z-Core directly
