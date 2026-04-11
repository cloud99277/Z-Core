from __future__ import annotations

import importlib.util
import io
import json
import os
import unittest
from contextlib import redirect_stderr
from unittest import mock

from tests.helpers import TestHome, run_zcore
from zcore.cli.main import main
from zcore.engines.memory import MemoryEngine
from zcore.models.memory import MemoryEntry
from zcore.runtime import RuntimePaths
from zcore.rag import RagDependencyError


HAS_LANCEDB = importlib.util.find_spec("lancedb") is not None


class RagIntegrationTests(unittest.TestCase):
    def test_rag_dependency_message_is_friendly(self) -> None:
        from zcore import rag

        with mock.patch("importlib.import_module", side_effect=ImportError("missing")):
            with self.assertRaises(rag.RagDependencyError) as ctx:
                rag.ensure_available()
        self.assertIn("pip install zcore[rag]", str(ctx.exception))

    def test_memory_search_all_gracefully_degrades_without_rag(self) -> None:
        with TestHome() as ctx:
            with mock.patch.dict(
                os.environ,
                {
                    "HOME": str(ctx.home),
                    "ZCORE_HOME": str(ctx.home / ".zcore"),
                    "AI_MEMORY_DIR": str(ctx.home / ".ai-memory"),
                },
                clear=False,
            ):
                paths = RuntimePaths.discover()
                paths.ensure_runtime_dirs()
                engine = MemoryEngine(paths)
                engine.write(MemoryEntry(type="fact", content="L2 memory only", topic="general"))

                with mock.patch("zcore.rag.search_knowledge", side_effect=RagDependencyError("RAG dependencies missing")):
                    payload = engine.search_all("L2", limit=5)

        self.assertEqual(payload["meta"]["l3_status"], "unavailable")
        self.assertEqual(len(payload["l2"]), 1)
        self.assertEqual(payload["l2"][0]["content"], "L2 memory only")

    def test_knowledge_cli_returns_friendly_error_when_rag_missing(self) -> None:
        stderr = io.StringIO()
        with mock.patch("zcore.rag.search_knowledge", side_effect=ImportError("Run 'pip install zcore[rag]'")):
            with redirect_stderr(stderr):
                exit_code = main(["knowledge", "search", "--query", "test"])
        self.assertEqual(exit_code, 1)
        self.assertIn("zcore[rag]", stderr.getvalue())

    @unittest.skipIf(not HAS_LANCEDB, "lancedb not installed")
    def test_knowledge_index_requires_path_or_config(self) -> None:
        with TestHome() as ctx:
            proc = run_zcore("knowledge", "index", "--json", home=ctx.home)
        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertIn("Knowledge source directory not configured", payload["error"])


if __name__ == "__main__":
    unittest.main()
