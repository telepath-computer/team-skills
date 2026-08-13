#!/usr/bin/env python3
"""Experimental await contracts using only temporary transcript fixtures."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SUPERV = Path(__file__).resolve().parent.parent / "scripts" / "superv"


class AwaitIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="superv-await-")
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.state = self.root / "state"
        self.home.mkdir()
        (self.state / "workers").mkdir(parents=True)
        self.env = dict(os.environ)
        self.env.update({
            "HOME": str(self.home),
            "AGENT_SUPERVISION_ROOT": str(self.state),
            "SUPERV_AWAIT_POLL_INTERVAL": "0.01",
        })

    def tearDown(self):
        self.tmp.cleanup()

    def register(self, worker, kind, path):
        record = {
            "id": worker,
            "kind": kind,
            "live": {},
            "send": {},
            "persisted": {"type": "jsonl", "path": str(path)},
            "extra": {},
        }
        (self.state / "workers" / f"{worker}.json").write_text(json.dumps(record))

    def set_cursor(self, worker, cursor):
        (self.state / "cursors").mkdir(parents=True, exist_ok=True)
        (self.state / "cursors" / f"{worker}.json").write_text(json.dumps(cursor))

    def run_await(self, worker):
        return subprocess.run(
            [sys.executable, str(SUPERV), "await", worker], env=self.env,
            text=True, capture_output=True, timeout=5,
        )

    def start_await(self, worker):
        return subprocess.Popen(
            [sys.executable, str(SUPERV), "await", worker], env=self.env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    @staticmethod
    def append(path, entry):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
            handle.flush()

    def test_idle_at_start_exits_loudly_without_returning_message(self):
        path = self.root / "pi-idle.jsonl"
        path.write_text("".join(json.dumps(entry) + "\n" for entry in [
            {"type": "session", "version": 3, "id": "s", "cwd": str(self.root)},
            {"type": "message", "id": "u1", "parentId": None,
             "message": {"role": "user", "content": [{"type": "text", "text": "work"}]}},
            {"type": "message", "id": "a1", "parentId": "u1",
             "message": {"role": "assistant", "content": [{"type": "text", "text": "SECRET RESULT"}],
                         "stopReason": "stop"}},
        ]))
        self.register("pi-idle", "pi", path)

        result = self.run_await("pi-idle")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "ATTENTION pi-idle: IDLE\nRun: superv watch pi-idle\n")
        self.assertNotIn("SECRET RESULT", result.stdout)
        self.assertFalse((self.state / "cursors" / "pi-idle.json").exists())

    def test_pi_busy_waits_for_terminal_turn(self):
        path = self.root / "pi-busy.jsonl"
        path.write_text("".join(json.dumps(entry) + "\n" for entry in [
            {"type": "session", "version": 3, "id": "s", "cwd": str(self.root)},
            {"type": "message", "id": "u1", "parentId": None,
             "message": {"role": "user", "content": [{"type": "text", "text": "work"}]}},
        ]))
        self.register("pi-busy", "pi", path)
        process = self.start_await("pi-busy")
        armed = process.stdout.readline()
        self.append(path, {"type": "message", "id": "a1", "parentId": "u1",
                           "message": {"role": "assistant", "content": [{"type": "text", "text": "PRIVATE DONE"}],
                                       "stopReason": "stop"}})
        remainder, stderr = process.communicate(timeout=5)
        stdout = armed + remainder

        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn("AWAIT pi-busy: CURRENTLY BUSY", stdout)
        self.assertIn("ATTENTION pi-busy: IDLE", stdout)
        self.assertNotIn("PRIVATE DONE", stdout)

    def test_observed_pi_compaction_is_not_redelivered_on_rearm(self):
        path = self.root / "pi-observed-compact.jsonl"
        entries = [
            {"type": "session", "version": 3, "id": "s", "cwd": str(self.root)},
            {"type": "message", "id": "u1", "parentId": None,
             "message": {"role": "user", "content": [{"type": "text", "text": "work"}]}},
            {"type": "message", "id": "a1", "parentId": "u1",
             "message": {"role": "assistant", "content": [{"type": "toolCall", "id": "call1", "name": "bash"}],
                         "stopReason": "toolUse"}},
            {"type": "message", "id": "t1", "parentId": "a1",
             "message": {"role": "toolResult", "content": [{"type": "text", "text": "ok"}]}},
            {"type": "compaction", "id": "c1", "parentId": "t1", "summary": "SECRET SUMMARY"},
            {"type": "message", "id": "u2", "parentId": "c1",
             "message": {"role": "user", "content": [{"type": "text", "text": "continue"}]}},
            {"type": "message", "id": "a2", "parentId": "u2",
             "message": {"role": "assistant", "content": [{"type": "toolCall", "id": "call2", "name": "bash"}],
                         "stopReason": "toolUse"}},
        ]
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        self.register("pi-observed-compact", "pi", path)

        first = self.run_await("pi-observed-compact")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("ATTENTION pi-observed-compact: COMPACTION", first.stdout)

        # The supervisor follows every await alert with watch. Its cursor now
        # proves that this compaction has already received attention.
        self.set_cursor("pi-observed-compact", {
            "session_path": str(path), "last_entry_id": "a2",
        })
        process = self.start_await("pi-observed-compact")
        armed = process.stdout.readline()
        self.append(path, {"type": "message", "id": "t2", "parentId": "a2",
                           "message": {"role": "toolResult", "content": [{"type": "text", "text": "ok"}]}})
        self.append(path, {"type": "message", "id": "a3", "parentId": "t2",
                           "message": {"role": "assistant", "content": [{"type": "text", "text": "PRIVATE DONE"}],
                                       "stopReason": "stop"}})
        remainder, stderr = process.communicate(timeout=5)
        stdout = armed + remainder

        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn("AWAIT pi-observed-compact: CURRENTLY BUSY", stdout)
        self.assertIn("ATTENTION pi-observed-compact: IDLE", stdout)
        self.assertEqual(stdout.count("COMPACTION"), 0)
        self.assertNotIn("SECRET SUMMARY", stdout)
        self.assertNotIn("PRIVATE DONE", stdout)

    def test_pi_compaction_interrupts_busy_wait(self):
        path = self.root / "pi-compact.jsonl"
        path.write_text("".join(json.dumps(entry) + "\n" for entry in [
            {"type": "session", "version": 3, "id": "s", "cwd": str(self.root)},
            {"type": "message", "id": "u1", "parentId": None,
             "message": {"role": "user", "content": [{"type": "text", "text": "work"}]}},
        ]))
        self.register("pi-compact", "pi", path)
        process = self.start_await("pi-compact")
        armed = process.stdout.readline()
        self.append(path, {"type": "compaction", "id": "c1", "parentId": "u1",
                           "summary": "SECRET COMPACTION SUMMARY", "tokensBefore": 250000})
        remainder, stderr = process.communicate(timeout=5)
        stdout = armed + remainder

        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn("ATTENTION pi-compact: COMPACTION", stdout)
        self.assertNotIn("SECRET COMPACTION SUMMARY", stdout)

    def test_claude_busy_waits_for_terminal_turn(self):
        path = self.root / "claude-busy.jsonl"
        path.write_text(json.dumps({
            "type": "user", "uuid": "u1", "message": {"role": "user", "content": "work"},
        }) + "\n")
        self.register("claude-busy", "claude", path)
        process = self.start_await("claude-busy")
        armed = process.stdout.readline()
        self.append(path, {"type": "assistant", "uuid": "a1", "message": {
            "role": "assistant", "content": [{"type": "text", "text": "SECRET CLAUDE RESULT"}],
            "stop_reason": "end_turn",
        }})
        remainder, stderr = process.communicate(timeout=5)
        stdout = armed + remainder

        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn("AWAIT claude-busy: CURRENTLY BUSY", stdout)
        self.assertIn("ATTENTION claude-busy: IDLE", stdout)
        self.assertNotIn("SECRET CLAUDE RESULT", stdout)

    def test_claude_compact_boundary_and_summary_are_one_attention_event(self):
        path = self.root / "claude.jsonl"
        path.write_text("".join(json.dumps(entry) + "\n" for entry in [
            {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "work"}},
            {"type": "system", "subtype": "compact_boundary", "uuid": "c1"},
            {"type": "user", "uuid": "s1", "isCompactSummary": True,
             "message": {"role": "user", "content": "SECRET SYNTHETIC SUMMARY"}},
        ]))
        self.register("claude-compact", "claude", path)

        result = self.run_await("claude-compact")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "ATTENTION claude-compact: COMPACTION\nRun: superv watch claude-compact\n")
        self.assertNotIn("SECRET SYNTHETIC SUMMARY", result.stdout)

    def test_observed_codex_compaction_is_not_redelivered_on_rearm(self):
        path = self.root / "codex-observed-compact.jsonl"
        entries = [
            {"type": "session_meta", "payload": {"id": "s", "cwd": str(self.root)}},
            {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "t1"}},
            {"type": "compacted", "payload": {"summary": "SECRET SUMMARY"}},
            {"type": "event_msg", "payload": {"type": "context_compacted"}},
            {"type": "response_item", "payload": {"type": "reasoning", "summary": []}},
        ]
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        self.register("codex-observed-compact", "codex", path)

        first = self.run_await("codex-observed-compact")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("ATTENTION codex-observed-compact: COMPACTION", first.stdout)

        # `watch` has consumed through the post-compaction reasoning entry.
        self.set_cursor("codex-observed-compact", {
            "session_path": str(path), "cursor_version": 2, "last_raw_idx": 4,
        })
        process = self.start_await("codex-observed-compact")
        armed = process.stdout.readline()
        self.append(path, {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "t1"}})
        remainder, stderr = process.communicate(timeout=5)
        stdout = armed + remainder

        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn("AWAIT codex-observed-compact: CURRENTLY BUSY", stdout)
        self.assertIn("ATTENTION codex-observed-compact: IDLE", stdout)
        self.assertEqual(stdout.count("COMPACTION"), 0)
        self.assertNotIn("SECRET SUMMARY", stdout)

    def test_codex_assistant_text_is_not_terminal_before_task_complete(self):
        path = self.root / "codex.jsonl"
        path.write_text("".join(json.dumps(entry) + "\n" for entry in [
            {"type": "session_meta", "payload": {"id": "s", "cwd": str(self.root)}},
            {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "t1"}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "SECRET INTERMEDIATE"}]}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "bash"}},
        ]))
        self.register("codex-busy", "codex", path)
        process = self.start_await("codex-busy")
        armed = process.stdout.readline()
        self.append(path, {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "t1"}})
        remainder, stderr = process.communicate(timeout=5)
        stdout = armed + remainder

        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn("AWAIT codex-busy: CURRENTLY BUSY", stdout)
        self.assertIn("ATTENTION codex-busy: IDLE", stdout)
        self.assertNotIn("SECRET INTERMEDIATE", stdout)

    def test_stream_shrink_exits_for_resync(self):
        path = self.root / "claude-shrink.jsonl"
        path.write_text(json.dumps({
            "type": "user", "uuid": "u1", "message": {"role": "user", "content": "work"},
        }) + "\n")
        self.register("claude-shrink", "claude", path)
        process = self.start_await("claude-shrink")
        armed = process.stdout.readline()
        path.write_text("")
        remainder, stderr = process.communicate(timeout=5)
        stdout = armed + remainder

        self.assertEqual(process.returncode, 2)
        self.assertIn("ATTENTION claude-shrink: STREAM RESYNC REQUIRED", stdout)
        self.assertIn("changed or shrank", stderr)

    def test_opencode_fails_closed(self):
        path = self.root / "unused"
        self.register("oc", "opencode", path)
        result = self.run_await("oc")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not yet support opencode", result.stderr)


if __name__ == "__main__":
    unittest.main()
