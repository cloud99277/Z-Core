from __future__ import annotations

import importlib
import json
from pathlib import Path

from zcore.adapters.base import SourceAdapter
from zcore.models.harvester import HarvestResult, HarvestedSession
from zcore.runtime import RuntimePaths
from zcore.utils.privacy import load_ingest_ignore, redact_text, should_ignore


class HarvesterEngine:
    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or RuntimePaths.discover()
        self.adapters: dict[str, SourceAdapter] = {}
        self.harvest_dir = self.paths.base_dir / "harvested"
        self.index_path = self.harvest_dir / "index.json"
        self._auto_register_known_adapters()

    def register_adapter(self, adapter: SourceAdapter) -> None:
        self.adapters[adapter.name()] = adapter

    def discover(self, source: str | None = None, project: str | None = None) -> list[dict[str, object]]:
        sessions: list[dict[str, object]] = []
        for adapter in self._selected_adapters(source):
            for item in adapter.discover(project=project):
                record = dict(item)
                record.setdefault("source", adapter.name())
                sessions.append(record)
        return sessions

    def ingest(
        self,
        source: str | None = None,
        project: str | None = None,
        *,
        dry_run: bool = False,
    ) -> dict[str, object]:
        index = self._load_index()
        ignore_patterns = load_ingest_ignore(self.paths.base_dir / "ingest-ignore")
        results: list[dict[str, object]] = []
        totals = {"discovered": 0, "ingested": 0, "skipped": 0, "errors": 0}

        for adapter in self._selected_adapters(source):
            discovered = adapter.discover(project=project)
            result = HarvestResult(source=adapter.name(), discovered=len(discovered), ingested=0, skipped=0)
            for item in discovered:
                session_path = str(item.get("path") or "")
                if session_path and should_ignore(session_path, ignore_patterns):
                    result.skipped += 1
                    continue
                session_id = str(
                    item.get("source_session_id")
                    or item.get("session_id")
                    or item.get("id")
                    or ""
                )
                if not session_id:
                    result.skipped += 1
                    result.errors.append("missing session id")
                    continue
                key = self._index_key(adapter.name(), session_id)
                if key in index:
                    result.skipped += 1
                    continue
                try:
                    harvested = adapter.ingest(session_id)
                except Exception as exc:  # Adapter failures should not abort the whole harvest.
                    result.errors.append(f"{session_id}: {type(exc).__name__}: {exc}")
                    continue
                if harvested is None:
                    result.skipped += 1
                    continue
                sanitized = self._redact_session(harvested)
                if not dry_run:
                    self._write_session(sanitized)
                    index[key] = {
                        "source": sanitized.source,
                        "source_session_id": sanitized.source_session_id,
                        "project": sanitized.project,
                        "started_at": sanitized.started_at,
                    }
                result.ingested += 1
            results.append(result.to_dict())
            totals["discovered"] += result.discovered
            totals["ingested"] += result.ingested
            totals["skipped"] += result.skipped
            totals["errors"] += len(result.errors)

        if not dry_run:
            self._write_index(index)

        return {"dry_run": dry_run, "results": results, "totals": totals}

    def status(self) -> dict[str, object]:
        index = self._load_index()
        return {
            "harvest_dir": str(self.harvest_dir),
            "index_path": str(self.index_path),
            "harvested_count": len(index),
            "adapters": {
                name: self._adapter_health(adapter)
                for name, adapter in sorted(self.adapters.items())
            },
        }

    def _auto_register_known_adapters(self) -> None:
        for module_name, class_name in (
            ("zcore.adapters.claude_adapter", "ClaudeAdapter"),
            ("zcore.adapters.hermes_adapter", "HermesAdapter"),
        ):
            try:
                module = importlib.import_module(module_name)
                adapter_cls = getattr(module, class_name)
                self.register_adapter(adapter_cls())
            except Exception:
                continue

    def _selected_adapters(self, source: str | None) -> list[SourceAdapter]:
        if source is None:
            return [self.adapters[name] for name in sorted(self.adapters)]
        adapter = self.adapters.get(source)
        return [adapter] if adapter is not None else []

    def _adapter_health(self, adapter: SourceAdapter) -> dict[str, object]:
        try:
            payload = adapter.health_check()
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return payload

    def _load_index(self) -> dict[str, object]:
        if not self.index_path.exists():
            return {}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_index(self, index: dict[str, object]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _write_session(self, session: HarvestedSession) -> Path:
        source_dir = self.harvest_dir / session.source
        source_dir.mkdir(parents=True, exist_ok=True)
        path = source_dir / f"{self._safe_filename(session.source_session_id)}.json"
        path.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def _redact_session(self, session: HarvestedSession) -> HarvestedSession:
        return HarvestedSession(
            source=session.source,
            source_session_id=session.source_session_id,
            project=redact_text(session.project),
            started_at=session.started_at,
            ended_at=session.ended_at,
            messages=[
                {
                    "role": str(message.get("role", "")),
                    "content": redact_text(str(message.get("content", ""))),
                }
                for message in session.messages
            ],
            summary=redact_text(session.summary),
            metadata=self._redact_metadata(session.metadata),
        )

    def _redact_metadata(self, value: object) -> object:
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, list):
            return [self._redact_metadata(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._redact_metadata(item) for key, item in value.items()}
        return value

    def _index_key(self, source: str, session_id: str) -> str:
        return f"{source}:{session_id}"

    def _safe_filename(self, value: str) -> str:
        return "".join(char if char.isalnum() or char in "._-" else "_" for char in value).strip("._") or "session"
