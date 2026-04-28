from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from zcore.adapters.claude_adapter import ClaudeAdapter
from zcore.adapters.hermes_adapter import HermesAdapter


class AdapterTests(unittest.TestCase):
    def test_claude_discover_empty_directory(self):
        with tempfile.TemporaryDirectory() as tempdir:
            adapter = ClaudeAdapter(Path(tempdir) / "projects")

            self.assertEqual(adapter.discover(), [])

    def test_claude_discover_and_ingest_jsonl_session(self):
        with tempfile.TemporaryDirectory() as tempdir:
            projects = Path(tempdir) / "projects" / "-home-yangyy-projects"
            projects.mkdir(parents=True)
            path = projects / "abc.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "user",
                                "sessionId": "s1",
                                "cwd": "/home/yangyy/projects",
                                "timestamp": "2026-04-27T01:00:00Z",
                                "message": {"role": "user", "content": "hello"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "assistant",
                                "sessionId": "s1",
                                "cwd": "/home/yangyy/projects",
                                "timestamp": "2026-04-27T01:01:00Z",
                                "message": {"role": "assistant", "content": "hi"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            adapter = ClaudeAdapter(Path(tempdir) / "projects")

            discovered = adapter.discover()
            session = adapter.ingest("s1")

        self.assertEqual(discovered[0]["source_session_id"], "s1")
        self.assertIsNotNone(session)
        self.assertEqual(session.messages[1]["content"], "hi")

    def test_claude_skips_progress_and_system_messages(self):
        with tempfile.TemporaryDirectory() as tempdir:
            projects = Path(tempdir) / "projects" / "-home-yangyy"
            projects.mkdir(parents=True)
            (projects / "abc.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"type": "progress", "message": {"role": "assistant", "content": "skip"}}),
                        json.dumps({"type": "system", "message": {"role": "system", "content": "skip"}}),
                        json.dumps(
                            {
                                "type": "user",
                                "sessionId": "s1",
                                "timestamp": "2026-04-27T01:00:00Z",
                                "message": {"role": "user", "content": "keep"},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            session = ClaudeAdapter(Path(tempdir) / "projects").ingest("s1")

        self.assertIsNotNone(session)
        self.assertEqual(session.messages, [{"role": "user", "content": "keep"}])

    def test_claude_duplicate_session_ids_are_addressed_by_path_hash(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project_dir = Path(tempdir) / "projects" / "-home-yangyy"
            subagent_dir = project_dir / "same-session" / "subagents"
            subagent_dir.mkdir(parents=True)
            first = project_dir / "same-session.jsonl"
            second = subagent_dir / "agent-a.jsonl"
            first.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "same-session",
                        "cwd": "/home/yangyy",
                        "timestamp": "2026-04-27T01:00:00Z",
                        "message": {"role": "user", "content": "top-level"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            second.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "same-session",
                        "cwd": "/home/yangyy",
                        "timestamp": "2026-04-27T01:01:00Z",
                        "message": {"role": "user", "content": "subagent"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            adapter = ClaudeAdapter(Path(tempdir) / "projects")

            discovered = adapter.discover()
            ids = [item["source_session_id"] for item in discovered]
            ingested = [adapter.ingest(session_id) for session_id in ids]

        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)
        self.assertTrue(all(str(session_id).startswith("same-session#") for session_id in ids))
        self.assertEqual({session.messages[0]["content"] for session in ingested if session}, {"top-level", "subagent"})
        self.assertEqual({session.metadata["claude_session_id"] for session in ingested if session}, {"same-session"})

    def test_claude_file_errors_stay_local_to_session_metadata(self):
        with tempfile.TemporaryDirectory() as tempdir:
            projects = Path(tempdir) / "projects" / "-home-yangyy"
            projects.mkdir(parents=True)
            (projects / "bad.jsonl").write_text(
                "{not json}\n"
                + json.dumps(
                    {
                        "type": "user",
                        "sessionId": "bad",
                        "message": {"role": "user", "content": "valid after bad line"},
                    }
                ),
                encoding="utf-8",
            )
            (projects / "good.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "good",
                        "message": {"role": "user", "content": "clean"},
                    }
                ),
                encoding="utf-8",
            )
            adapter = ClaudeAdapter(Path(tempdir) / "projects")

            bad = adapter.ingest("bad")
            good = adapter.ingest("good")

        self.assertTrue(bad.metadata["errors"])
        self.assertEqual(good.metadata["errors"], [])

    def test_hermes_discover_empty_directory(self):
        with tempfile.TemporaryDirectory() as tempdir:
            adapter = HermesAdapter(Path(tempdir) / "sessions")

            self.assertEqual(adapter.discover(), [])

    def test_hermes_discover_and_ingest_session_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sessions = Path(tempdir) / "sessions"
            sessions.mkdir()
            (sessions / "session_20260413_234516_512af7.json").write_text(
                json.dumps(
                    {
                        "session_id": "20260413_234516_512af7",
                        "model": "xiaomi/mimo-v2-pro",
                        "platform": "cli",
                        "session_start": "2026-04-13T23:45:16",
                        "last_updated": "2026-04-13T23:45:22",
                        "messages": [
                            {"role": "user", "content": "hello"},
                            {"role": "assistant", "content": "hi"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            adapter = HermesAdapter(sessions)
            discovered = adapter.discover()
            session = adapter.ingest("20260413_234516_512af7")

        self.assertEqual(discovered[0]["metadata"]["model"], "xiaomi/mimo-v2-pro")
        self.assertIsNotNone(session)
        self.assertEqual(session.metadata["platform"], "cli")

    def test_hermes_ignores_request_dump_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sessions = Path(tempdir) / "sessions"
            sessions.mkdir()
            (sessions / "request_dump_1.json").write_text("{}", encoding="utf-8")

            self.assertEqual(HermesAdapter(sessions).discover(), [])

    def test_claude_extracts_text_from_list_content(self):
        with tempfile.TemporaryDirectory() as tempdir:
            projects = Path(tempdir) / "projects" / "-home-yangyy"
            projects.mkdir(parents=True)
            (projects / "abc.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "user",
                                "sessionId": "s1",
                                "timestamp": "2026-04-27T01:00:00Z",
                                "message": {"role": "user", "content": "explain this code"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "assistant",
                                "sessionId": "s1",
                                "timestamp": "2026-04-27T01:01:00Z",
                                "message": {
                                    "role": "assistant",
                                    "content": [
                                        {"type": "text", "text": "Here is the explanation."},
                                        {"type": "tool_use", "id": "t1", "name": "read_file", "input": {}},
                                        {"type": "text", "text": "And some more details."},
                                    ],
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            session = ClaudeAdapter(Path(tempdir) / "projects").ingest("s1")

        self.assertIsNotNone(session)
        self.assertEqual(len(session.messages), 2)
        self.assertIn("Here is the explanation.", session.messages[1]["content"])
        self.assertIn("And some more details.", session.messages[1]["content"])
        self.assertNotIn("tool_use", session.messages[1]["content"])
