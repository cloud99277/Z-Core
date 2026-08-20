#!/usr/bin/env python3
"""Audit or actively ingest Markdown changes from a knowledge root.

The default ``audit`` mode is intentionally read-only. It inspects missing
frontmatter and emits a minimized JSON event without revealing the configured
root, document paths, or document contents. The legacy mutation path remains
available only through the explicit ``--mode active`` flag.

This stays stdlib-only so it can run in WSL/Linux without extra packages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


_SCRIPT_DIR = Path(__file__).resolve().parent
_KITCLAW_DIR = _SCRIPT_DIR.parent.parent.parent  # core-skills/memory-manager/scripts/ → kitclaw/

DEFAULT_ROOT = str(Path.home() / "knowledge-base")
DEFAULT_FRONTMATTER_SCRIPT = str(_SCRIPT_DIR / "ensure-knowledge-frontmatter.py")
DEFAULT_INDEXER_PYTHON = str(_KITCLAW_DIR / "rag-engine" / ".venv" / "bin" / "python3")
DEFAULT_INDEXER_SCRIPT = str(_KITCLAW_DIR / "rag-engine" / "knowledge_index.py")
DEFAULT_DB_PATH = str(Path.home() / ".lancedb" / "knowledge")
WATCH_LABEL = "kitclaw-l3-watch"
AUDIT_SCHEMA = "zcore.knowledge.watcher-audit/v1"
AUDIT_MODE = "audit"
ACTIVE_MODE = "active"

STOP_REQUESTED = False


def handle_signal(signum, _frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    print(f"[{WATCH_LABEL}] received signal {signum}, shutting down...", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit a knowledge root by default; active ingestion requires --mode active."
    )
    parser.add_argument("--root", default=DEFAULT_ROOT, help=f"Knowledge root (default: {DEFAULT_ROOT})")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds (default: 2)")
    parser.add_argument("--debounce", type=float, default=3.0, help="Quiet period before ingest (default: 3)")
    parser.add_argument(
        "--mode",
        choices=(AUDIT_MODE, ACTIVE_MODE),
        default=AUDIT_MODE,
        help="audit is read-only and the default; active permits legacy metadata/index writes",
    )
    parser.add_argument(
        "--frontmatter-script",
        default=DEFAULT_FRONTMATTER_SCRIPT,
        help=f"Frontmatter completion script (default: {DEFAULT_FRONTMATTER_SCRIPT})",
    )
    parser.add_argument(
        "--indexer-python",
        default=DEFAULT_INDEXER_PYTHON,
        help=f"Python executable for indexer (default: {DEFAULT_INDEXER_PYTHON})",
    )
    parser.add_argument(
        "--indexer-script",
        default=DEFAULT_INDEXER_SCRIPT,
        help=f"Indexer script path (default: {DEFAULT_INDEXER_SCRIPT})",
    )
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help=f"LanceDB path (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--no-initial-sync", action="store_true", help="Skip the startup audit or active ingest")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one audit cycle and exit (or one active ingest only with --mode active)",
    )
    return parser.parse_args()


def validate_paths(args: argparse.Namespace) -> Path:
    root = Path(args.root).expanduser()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Error: knowledge root not found: {root}")

    required_paths = [args.frontmatter_script]
    if args.mode == ACTIVE_MODE:
        required_paths.extend([args.indexer_python, args.indexer_script])
    missing = [path for path in required_paths if not Path(path).expanduser().exists()]
    if missing:
        raise SystemExit(f"Error: required path(s) not found: {', '.join(missing)}")

    return root


def build_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        stat = path.stat()
        snapshot[str(path.relative_to(root))] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def diff_snapshots(
    previous: dict[str, tuple[int, int]],
    current: dict[str, tuple[int, int]],
) -> tuple[list[str], list[str], list[str]]:
    previous_keys = set(previous)
    current_keys = set(current)
    created = sorted(current_keys - previous_keys)
    deleted = sorted(previous_keys - current_keys)
    modified = sorted(
        path for path in (previous_keys & current_keys) if previous[path] != current[path]
    )
    return created, modified, deleted


def run_command(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)


def source_revision(root: Path, snapshot: dict[str, tuple[int, int]]) -> str:
    """Return a content-derived revision without exposing paths or contents."""
    digest = hashlib.sha256()
    for relative_path in sorted(snapshot):
        path = root / relative_path
        try:
            content_digest = hashlib.sha256(path.read_bytes()).digest()
        except OSError:
            # A concurrent edit is represented by the next watcher cycle.
            continue
        digest.update(relative_path.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(content_digest)
    return digest.hexdigest()


def parse_missing_frontmatter_count(result: subprocess.CompletedProcess[str]) -> tuple[str, int | None]:
    """Convert the inspection result into a non-sensitive status and count."""
    if result.returncode != 0:
        return "failed", None
    try:
        payload = json.loads(result.stdout)
        count = payload["count"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return "invalid_result", None
    if not isinstance(count, int) or count < 0:
        return "invalid_result", None
    return "ok", count


def build_audit_event(
    root: Path,
    snapshot: dict[str, tuple[int, int]],
    reason: str,
    changes: tuple[int, int, int],
    frontmatter_status: str,
    missing_frontmatter: int | None,
) -> dict[str, object]:
    """Build the public audit payload without corpus locations or document metadata."""
    created, modified, deleted = changes
    return {
        "schema": AUDIT_SCHEMA,
        "mode": AUDIT_MODE,
        "reason": reason,
        "documents": len(snapshot),
        "source_revision_sha256": source_revision(root, snapshot),
        "changes": {"created": created, "modified": modified, "deleted": deleted},
        "frontmatter": {"status": frontmatter_status, "missing": missing_frontmatter},
    }


def run_audit(
    root: Path,
    args: argparse.Namespace,
    reason: str,
    snapshot: dict[str, tuple[int, int]],
    changes: tuple[int, int, int] = (0, 0, 0),
) -> bool:
    """Inspect frontmatter without mutation and emit exactly one minimized event."""
    frontmatter_cmd = [
        sys.executable,
        str(Path(args.frontmatter_script).expanduser()),
        "--root",
        str(root),
        "--json",
    ]
    frontmatter_result = run_command(frontmatter_cmd)
    frontmatter_status, missing_frontmatter = parse_missing_frontmatter_count(frontmatter_result)
    event = build_audit_event(
        root,
        snapshot,
        reason,
        changes,
        frontmatter_status,
        missing_frontmatter,
    )
    print(json.dumps(event, sort_keys=True, separators=(",", ":")), flush=True)
    return frontmatter_status == "ok"


def run_active_ingest(root: Path, args: argparse.Namespace, reason: str) -> bool:
    """Run the legacy writer path after the caller explicitly selected active mode."""
    print(f"[{WATCH_LABEL}] ingest start ({reason})", flush=True)

    frontmatter_cmd = [
        sys.executable,
        str(Path(args.frontmatter_script).expanduser()),
        "--root",
        str(root),
        "--apply",
    ]
    frontmatter_result = run_command(frontmatter_cmd)
    if frontmatter_result.returncode != 0:
        print(f"[{WATCH_LABEL}] frontmatter step failed", file=sys.stderr, flush=True)
        if frontmatter_result.stdout.strip():
            print(frontmatter_result.stdout.strip(), file=sys.stderr, flush=True)
        if frontmatter_result.stderr.strip():
            print(frontmatter_result.stderr.strip(), file=sys.stderr, flush=True)
        return False

    env = os.environ.copy()
    env["PRODUCTION"] = "true"
    index_cmd = [
        str(Path(args.indexer_python).expanduser()),
        str(Path(args.indexer_script).expanduser()),
        "--update",
        str(root),
        "--db-path",
        str(Path(args.db_path).expanduser()),
    ]
    index_result = run_command(index_cmd, env=env)
    if index_result.returncode != 0:
        print(f"[{WATCH_LABEL}] index step failed", file=sys.stderr, flush=True)
        if index_result.stdout.strip():
            print(index_result.stdout.strip(), file=sys.stderr, flush=True)
        if index_result.stderr.strip():
            print(index_result.stderr.strip(), file=sys.stderr, flush=True)
        return False

    print(f"[{WATCH_LABEL}] ingest complete", flush=True)
    return True


def watch(root: Path, args: argparse.Namespace) -> int:
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    previous = build_snapshot(root)
    if args.once:
        if args.mode == AUDIT_MODE:
            succeeded = run_audit(root, args, reason="once", snapshot=previous)
        elif not args.no_initial_sync:
            succeeded = run_active_ingest(root, args, reason="initial_sync")
        else:
            succeeded = True
        return 0 if succeeded else 1

    if not args.no_initial_sync:
        if args.mode == AUDIT_MODE:
            run_audit(root, args, reason="initial_sync", snapshot=previous)
        else:
            run_active_ingest(root, args, reason="initial_sync")

    pending = False
    pending_since = 0.0
    pending_created: set[str] = set()
    pending_modified: set[str] = set()
    pending_deleted: set[str] = set()

    if args.mode == ACTIVE_MODE:
        print(
            f"[{WATCH_LABEL}] watching {root} (interval={args.interval}s, debounce={args.debounce}s)",
            flush=True,
        )

    while not STOP_REQUESTED:
        time.sleep(args.interval)
        current = build_snapshot(root)
        created, modified, deleted = diff_snapshots(previous, current)
        previous = current

        if created or modified or deleted:
            pending = True
            pending_since = time.monotonic()
            pending_created.update(created)
            pending_modified.update(modified)
            pending_deleted.update(deleted)
            if args.mode == ACTIVE_MODE:
                print(
                    f"[{WATCH_LABEL}] change detected: "
                    f"{len(created)} created, {len(modified)} modified, {len(deleted)} deleted",
                    flush=True,
                )
            continue

        if pending and (time.monotonic() - pending_since) >= args.debounce:
            changes = (
                len(pending_created),
                len(pending_modified),
                len(pending_deleted),
            )
            if args.mode == AUDIT_MODE:
                run_audit(root, args, reason="changes", snapshot=current, changes=changes)
            else:
                summary = f"{changes[0]} created, {changes[1]} modified, {changes[2]} deleted"
                run_active_ingest(root, args, reason=summary)
            previous = build_snapshot(root)
            pending = False
            pending_created.clear()
            pending_modified.clear()
            pending_deleted.clear()

    if args.mode == ACTIVE_MODE:
        print(f"[{WATCH_LABEL}] stopped", flush=True)
    return 0


def main() -> int:
    args = parse_args()
    root = validate_paths(args)
    return watch(root, args)


if __name__ == "__main__":
    raise SystemExit(main())
