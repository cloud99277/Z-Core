import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WATCHER_SCRIPT = ROOT / "skills" / "core" / "memory-manager" / "scripts" / "watch-knowledge-base.py"
FRONTMATTER_SCRIPT = ROOT / "skills" / "core" / "memory-manager" / "scripts" / "ensure-knowledge-frontmatter.py"


def load_watcher_module():
    spec = importlib.util.spec_from_file_location("knowledge_watcher", WATCHER_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load knowledge watcher module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KnowledgeWatcherAuditTests(unittest.TestCase):
    def test_audit_mode_is_the_default(self) -> None:
        watcher = load_watcher_module()
        with patch.object(watcher.sys, "argv", [str(WATCHER_SCRIPT)]):
            args = watcher.parse_args()
        self.assertEqual(args.mode, watcher.AUDIT_MODE)

    def test_audit_command_never_requests_mutation(self) -> None:
        watcher = load_watcher_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "corpus"
            root.mkdir()
            note = root / "note.md"
            note.write_text("# Fixture\n", encoding="utf-8")
            args = type("Args", (), {"frontmatter_script": str(FRONTMATTER_SCRIPT)})()
            result = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps({"count": 1}), stderr=""
            )

            with patch.object(watcher, "run_command", return_value=result) as run_command:
                succeeded = watcher.run_audit(
                    root,
                    args,
                    reason="once",
                    snapshot=watcher.build_snapshot(root),
                )

            self.assertTrue(succeeded)
            command = run_command.call_args.args[0]
            self.assertNotIn("--apply", command)
            self.assertNotIn("--update", command)
            self.assertEqual(command[-1], "--json")

    def test_audit_once_returns_failure_when_frontmatter_audit_fails(self) -> None:
        watcher = load_watcher_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            args = type(
                "Args",
                (),
                {"once": True, "mode": watcher.AUDIT_MODE, "no_initial_sync": False},
            )()

            with (
                patch.object(watcher.signal, "signal"),
                patch.object(watcher, "run_audit", return_value=False) as run_audit,
            ):
                result = watcher.watch(root, args)

            self.assertEqual(result, 1)
            run_audit.assert_called_once_with(root, args, reason="once", snapshot={})

    def test_active_once_returns_failure_when_ingest_fails(self) -> None:
        watcher = load_watcher_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            args = type(
                "Args",
                (),
                {"once": True, "mode": watcher.ACTIVE_MODE, "no_initial_sync": False},
            )()

            with (
                patch.object(watcher.signal, "signal"),
                patch.object(watcher, "run_active_ingest", return_value=False) as run_active_ingest,
            ):
                result = watcher.watch(root, args)

            self.assertEqual(result, 1)
            run_active_ingest.assert_called_once_with(root, args, reason="initial_sync")

    def test_audit_once_preserves_source_and_never_runs_indexer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            corpus_root = temporary_root / "private-corpus"
            corpus_root.mkdir()
            source = corpus_root / "confidential-note.md"
            source.write_text("# Private Fixture\n\nUnchanged content.\n", encoding="utf-8")
            source_hash_before = hashlib.sha256(source.read_bytes()).hexdigest()

            marker = temporary_root / "indexer-was-run"
            indexer_script = temporary_root / "fake-indexer.py"
            indexer_script.write_text(
                "from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('ran', encoding='utf-8')\n",
                encoding="utf-8",
            )

            process = subprocess.run(
                [
                    sys.executable,
                    str(WATCHER_SCRIPT),
                    "--mode",
                    "audit",
                    "--once",
                    "--root",
                    str(corpus_root),
                    "--frontmatter-script",
                    str(FRONTMATTER_SCRIPT),
                    "--indexer-python",
                    sys.executable,
                    "--indexer-script",
                    str(indexer_script),
                    "--db-path",
                    str(marker),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(source_hash_before, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertFalse(marker.exists(), "audit mode must not execute the indexer")

            event = json.loads(process.stdout)
            self.assertEqual(event["schema"], "zcore.knowledge.watcher-audit/v1")
            self.assertEqual(event["mode"], "audit")
            self.assertEqual(event["documents"], 1)
            self.assertEqual(event["frontmatter"], {"missing": 1, "status": "ok"})
            self.assertNotIn(str(corpus_root), process.stdout)
            self.assertNotIn(str(corpus_root), process.stderr)
            self.assertNotIn(source.name, process.stdout)


if __name__ == "__main__":
    unittest.main()
