from __future__ import annotations

import importlib.util


def missing_dependency_reason(*modules: str) -> str | None:
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    if not missing:
        return None
    return f"missing optional dependencies: {', '.join(missing)}"
