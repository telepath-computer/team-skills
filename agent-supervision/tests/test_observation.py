#!/usr/bin/env python3
"""Observation contracts for all four superv transcript adapters.

All integration cases use a temporary HOME and AGENT_SUPERVISION_ROOT. No live
worker, registry, tmux server, or OpenCode server is contacted.
"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

SUPERV = Path(__file__).resolve().parent.parent / "scripts" / "superv"


def load_superv(name="superv_observation_test"):
    loader = importlib.machinery.SourceFileLoader(name, str(SUPERV))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ObservationIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="superv-observation-")
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.state = self.root / "state"
        self.home.mkdir()
        (self.state / "workers").mkdir(parents=True)
        (self.state / "cursors").mkdir(parents=True)
        self.env = dict(os.environ)
        self.env.update({"HOME": str(self.home), "AGENT_SUPERVISION_ROOT": str(self.state)})

    def tearDown(self):
        self.tmp.cleanup()

    def run_superv(self, *args):
        return subprocess.run([sys.executable, str(SUPERV), *args], env=self.env,
                              text=True, capture_output=True, timeout=30)

    def register_path(self, worker, kind, path, **extra):
        record = {
            "id": worker,
            "kind": kind,
            "live": {},
            "send": {},
            "persisted": {"type": "jsonl", "path": str(path)},
            "extra": extra,
        }
        (self.state / "workers" / f"{worker}.json").write_text(json.dumps(record))

    def set_cursor(self, worker, cursor):
        (self.state / "cursors" / f"{worker}.json").write_text(json.dumps(cursor))

    def write_pi_overflow(self):
        path = self.root / "pi.jsonl"
        session_id = "pi-test"
        entries = [{"type": "session", "version": 3, "id": session_id,
                    "timestamp": "2026-08-10T00:00:00.000Z", "cwd": str(self.root)}]
        parent = None
        first_id = "00000000"
        entries.append({"type": "message", "id": first_id, "parentId": parent,
                        "timestamp": "2026-08-10T00:00:01.000Z",
                        "message": {"role": "user", "content": [{"type": "text", "text": "start"}]}})
        parent = first_id
        expected_commands = []
        for number in range(90):
            eid = f"{number + 1:08x}"
            commands = [f"inspect-{number}-a --path /workspace/component-{number}/alpha",
                        f"inspect-{number}-b --pattern remediation-{number}"]
            expected_commands.extend(command.split()[0] for command in commands)
            entries.append({
                "type": "message", "id": eid, "parentId": parent,
                "timestamp": f"2026-08-10T00:{number // 60:02d}:{(number + 2) % 60:02d}.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": f"**Checking remediation item {number}**"},
                        *[{"type": "toolCall", "id": f"call-{number}-{index}", "name": "bash",
                           "arguments": {"command": command}} for index, command in enumerate(commands, 1)],
                    ],
                    "stopReason": "toolUse",
                    "usage": {"input": 1000, "cacheRead": 0, "output": 10},
                    "provider": "test", "model": "model-test",
                },
            })
            parent = eid
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        return path, first_id, expected_commands

    def test_pi_overflow_pages_without_refusal_and_enumerates_every_call(self):
        path, first_id, expected_commands = self.write_pi_overflow()
        self.register_path("pi-worker", "pi", path, session_id="pi-test")
        self.set_cursor("pi-worker", {"session_path": str(path), "last_entry_id": first_id})

        combined = []
        for _ in range(10):
            result = self.run_superv("watch", "pi-worker")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("refusing to print", result.stderr + result.stdout)
            combined.append(result.stdout)
            if "INCOMPLETE OBSERVATION" not in result.stdout:
                self.assertIn("OBSERVATION COMPLETE", result.stdout)
                break
            self.assertIn("You MUST run this command again", result.stdout)
        else:
            self.fail("overflow pagination never reached OBSERVATION COMPLETE")

        output = "\n".join(combined)
        for command in expected_commands:
            self.assertEqual(output.count(command), 1, f"missing or duplicated tool call {command}")
        self.assertNotIn("90 tool calls", output)
        self.assertIn("/thinking/1 intent", output)

    def test_cursor_count_reads_oldest_unread_entries(self):
        path, first_id, _ = self.write_pi_overflow()
        self.register_path("pi-count", "pi", path, session_id="pi-test")
        self.set_cursor("pi-count", {"session_path": str(path), "last_entry_id": first_id})
        result = self.run_superv("watch", "pi-count", "--count", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("id=00000001", result.stdout)
        self.assertIn("id=00000002", result.stdout)
        self.assertNotIn("id=0000002d", result.stdout)
        cursor = json.loads((self.state / "cursors" / "pi-count.json").read_text())
        self.assertEqual(cursor["last_entry_id"], "00000002")

    def test_reset_count_deliberately_restarts_at_recent_tail(self):
        path, first_id, _ = self.write_pi_overflow()
        self.register_path("pi-reset", "pi", path, session_id="pi-test")
        self.set_cursor("pi-reset", {"session_path": str(path), "last_entry_id": first_id})
        result = self.run_superv("watch", "pi-reset", "--reset", "--count", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("id=00000059", result.stdout)
        self.assertIn("id=0000005a", result.stdout)
        self.assertNotIn("id=00000001", result.stdout)
        cursor = json.loads((self.state / "cursors" / "pi-reset.json").read_text())
        self.assertEqual(cursor["last_entry_id"], "0000005a")

    def write_claude_fixture(self):
        path = self.root / "claude.jsonl"
        shared = "aaaaaaaa"
        ids = [shared + "-1111-4111-8111-111111111111", shared + "-2222-4222-8222-222222222222"]
        entries = [
            {"type": "assistant", "uuid": ids[0], "timestamp": "2026-08-10T01:00:00Z",
             "message": {"role": "assistant", "stop_reason": "tool_use",
                         "usage": {"input_tokens": 100000, "cache_read_input_tokens": 20000,
                                   "cache_creation_input_tokens": 30000}, "content": [
                 {"type": "thinking", "thinking": "", "signature": "opaque"},
                 {"type": "tool_use", "id": "tool-a", "name": "Read", "input": {"file_path": "/tmp/a"}},
                 {"type": "tool_use", "id": "tool-b", "name": "Grep", "input": {"pattern": "ledger"}},
             ]}},
            {"type": "user", "uuid": ids[1], "timestamp": "2026-08-10T01:00:01Z",
             "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "tool-a", "content": "x" * 100_000},
                 {"type": "tool_result", "tool_use_id": "tool-b", "content": "found ledger"},
             ]}},
        ]
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        return path, ids

    def test_claude_empty_thinking_is_hidden_and_multiple_tools_are_enumerated(self):
        path, _ = self.write_claude_fixture()
        self.register_path("claude-worker", "claude", path)
        result = self.run_superv("watch", "claude-worker", "--count", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("intent:", result.stdout)
        self.assertEqual(result.stdout.count("toolUse:"), 2)
        self.assertIn("Read", result.stdout)
        self.assertIn("Grep", result.stdout)

    def test_claude_ambiguous_prefix_fails_loudly(self):
        path, _ = self.write_claude_fixture()
        self.register_path("claude-detail", "claude", path)
        result = self.run_superv("detail", "claude-detail", "aaaaaaaa")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ambiguous claude entry id prefix", result.stderr)

    def test_claude_detail_is_bounded_and_omits_opaque_thinking_signature(self):
        path, ids = self.write_claude_fixture()
        self.register_path("claude-bounded", "claude", path)
        result = self.run_superv("detail", "claude-bounded", ids[0])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(len(result.stdout), 12_500)
        self.assertNotIn("opaque", result.stdout)
        result2 = self.run_superv("detail", "claude-bounded", ids[1] + "/result/1")
        self.assertEqual(result2.returncode, 0, result2.stderr)
        self.assertLess(len(result2.stdout), 12_500)
        self.assertIn("content shortened", result2.stdout)

    def test_codex_legacy_cursor_migrates_and_new_tool_shapes_are_visible(self):
        path = self.root / "codex.jsonl"
        entries = [
            {"type": "session_meta", "timestamp": "2026-08-10T02:00:00Z", "payload": {"cwd": str(self.root)}},
            {"type": "response_item", "timestamp": "2026-08-10T02:00:01Z", "payload": {
                "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "starting"}]}},
            {"type": "response_item", "timestamp": "2026-08-10T02:00:02Z", "payload": {
                "type": "custom_tool_call", "call_id": "call-patch", "name": "apply_patch", "input": "*** Update File: a.ts"}},
            {"type": "response_item", "timestamp": "2026-08-10T02:00:03Z", "payload": {
                "type": "custom_tool_call_output", "call_id": "call-patch", "output": "Success"}},
            {"type": "response_item", "timestamp": "2026-08-10T02:00:04Z", "payload": {
                "type": "web_search_call", "status": "completed", "action": {"type": "find_in_page", "pattern": "quota"}}},
        ]
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        self.register_path("codex-worker", "codex", path)
        # Previous schema: visible index zero was the assistant message at raw index one.
        self.set_cursor("codex-worker", {"session_path": str(path), "last_idx": 0})
        result = self.run_superv("watch", "codex-worker")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("apply_patch", result.stdout)
        self.assertIn("custom_tool_call_output", result.stdout)
        self.assertIn("web_search", result.stdout)
        self.assertIn("codex-r2", result.stdout)
        cursor = json.loads((self.state / "cursors" / "codex-worker.json").read_text())
        self.assertEqual(cursor["cursor_version"], 2)
        self.assertEqual(cursor["last_raw_idx"], 4)

    def test_recent_query_does_not_move_cursor(self):
        path, first_id, _ = self.write_pi_overflow()
        self.register_path("pi-recent", "pi", path, session_id="pi-test")
        original = {"session_path": str(path), "last_entry_id": first_id}
        self.set_cursor("pi-recent", original)
        result = self.run_superv("recent", "pi-recent", "--kind", "messages", "--count", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("did not move the watch cursor", result.stdout)
        self.assertEqual(json.loads((self.state / "cursors" / "pi-recent.json").read_text()), original)

    def test_status_reports_exact_unread_count_for_pi_and_claude(self):
        pi_path, first_id, _ = self.write_pi_overflow()
        self.register_path("pi-unread", "pi", pi_path, session_id="pi-test")
        self.set_cursor("pi-unread", {"session_path": str(pi_path), "last_entry_id": first_id})
        pi_result = self.run_superv("status", "pi-unread")
        self.assertEqual(pi_result.returncode, 0, pi_result.stderr)
        self.assertIn("unread=90", pi_result.stdout)

        claude_path, ids = self.write_claude_fixture()
        self.register_path("claude-unread", "claude", claude_path)
        self.set_cursor("claude-unread", {"session_path": str(claude_path), "last_entry_id": ids[0]})
        claude_result = self.run_superv("status", "claude-unread")
        self.assertEqual(claude_result.returncode, 0, claude_result.stderr)
        self.assertIn("unread=1", claude_result.stdout)
        self.assertIn("ctx=150k/?", claude_result.stdout)

    def test_status_reports_exact_unread_count_for_codex(self):
        path = self.root / "codex-status.jsonl"
        entries = [
            {"type": "session_meta", "timestamp": "2026-08-10T02:00:00Z", "payload": {"cwd": str(self.root)}},
            {"type": "response_item", "timestamp": "2026-08-10T02:00:01Z", "payload": {
                "type": "message", "role": "user", "content": [{"type": "input_text", "text": "start"}]}},
            {"type": "response_item", "timestamp": "2026-08-10T02:00:02Z", "payload": {
                "type": "custom_tool_call", "call_id": "call-a", "name": "shell", "input": "pwd"}},
            {"type": "event_msg", "timestamp": "2026-08-10T02:00:03Z", "payload": {
                "type": "token_count", "info": {"last_token_usage": {"input_tokens": 120000},
                "model_context_window": 200000}}},
        ]
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        self.register_path("codex-status", "codex", path)
        self.set_cursor("codex-status", {"session_path": str(path), "cursor_version": 2, "last_raw_idx": 1})
        result = self.run_superv("status", "codex-status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("unread=1", result.stdout)
        self.assertIn("ctx=120k/200k(60%)", result.stdout)
        raw = self.run_superv("detail", "codex-status", "call-a", "--raw", "--force")
        self.assertEqual(raw.returncode, 0, raw.stderr)
        self.assertIn('"call_id": "call-a"', raw.stdout)

    def test_sweep_is_non_mutating_and_includes_latest_intent(self):
        path, first_id, _ = self.write_pi_overflow()
        self.register_path("pi-sweep", "pi", path, session_id="pi-test")
        original = {"session_path": str(path), "last_entry_id": first_id}
        self.set_cursor("pi-sweep", original)
        claude_path, _ = self.write_claude_fixture()
        self.register_path("claude-sweep", "claude", claude_path)
        result = self.run_superv("sweep")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 2)
        self.assertIn("id=pi-sweep", result.stdout)
        self.assertIn("id=claude-sweep", result.stdout)
        self.assertIn("unread=90", result.stdout)
        self.assertIn('latest_intent="Checking remediation item 89"', result.stdout)
        self.assertEqual(json.loads((self.state / "cursors" / "pi-sweep.json").read_text()), original)
        self.assertFalse((self.state / "cursors" / "claude-sweep.json").exists())

    def test_raw_detail_requires_explicit_double_override(self):
        path, ids = self.write_claude_fixture()
        self.register_path("claude-raw", "claude", path)
        refused = self.run_superv("detail", "claude-raw", ids[0], "--raw")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("requires both --raw and --force", refused.stderr)
        self.assertNotIn("opaque", refused.stdout + refused.stderr)
        force_only = self.run_superv("detail", "claude-raw", ids[0], "--force")
        self.assertNotEqual(force_only.returncode, 0)
        self.assertIn("requires both --raw and --force", force_only.stderr)
        allowed = self.run_superv("detail", "claude-raw", ids[0], "--raw", "--force")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertIn('"signature": "opaque"', allowed.stdout)

    def test_pi_bash_child_locator_and_raw_tool_locator_are_resolvable(self):
        path = self.root / "pi-bash.jsonl"
        entries = [
            {"type": "session", "version": 3, "id": "pi-bash", "timestamp": "2026-08-10T00:00:00Z", "cwd": str(self.root)},
            {"type": "message", "id": "00000001", "parentId": None, "timestamp": "2026-08-10T00:00:01Z",
             "message": {"role": "user", "content": [{"type": "text", "text": "run"}]}},
            {"type": "message", "id": "00000002", "parentId": "00000001", "timestamp": "2026-08-10T00:00:02Z",
             "message": {"role": "bashExecution", "command": "printf hello", "output": "hello", "exitCode": 0}},
        ]
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        self.register_path("pi-bash", "pi", path, session_id="pi-bash")
        bounded = self.run_superv("detail", "pi-bash", "00000002/tool/1")
        self.assertEqual(bounded.returncode, 0, bounded.stderr)
        self.assertIn("printf hello", bounded.stdout)
        raw = self.run_superv("detail", "pi-bash", "00000002/tool/1", "--raw", "--force")
        self.assertEqual(raw.returncode, 0, raw.stderr)
        self.assertIn('"command": "printf hello"', raw.stdout)

    def test_pi_status_resolves_model_context_window(self):
        path = self.root / "pi-status.jsonl"
        entries = [
            {"type": "session", "version": 3, "id": "pi-status", "timestamp": "2026-08-10T00:00:00Z", "cwd": str(self.root)},
            {"type": "message", "id": "00000001", "parentId": None, "timestamp": "2026-08-10T00:00:01Z",
             "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}], "stopReason": "stop",
                         "provider": "provider-x", "model": "model-x",
                         "usage": {"input": 227000, "cacheRead": 0, "output": 1}}},
        ]
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries) + '{"type":"message"')
        models_dir = self.home / ".pi" / "agent"
        models_dir.mkdir(parents=True)
        (models_dir / "models-store.json").write_text(json.dumps({"provider-x": {"models": [{"id": "model-x", "contextWindow": 272000}]}}))
        self.register_path("pi-status", "pi", path, session_id="pi-status")
        result = self.run_superv("status", "pi-status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ctx=227k/272k(83%)", result.stdout)
        self.assertIn("unread=1", result.stdout)


class FormattingContractTest(unittest.TestCase):
    def test_overview_truncation_is_character_wise_after_whitespace_normalization(self):
        module = load_superv(f"superv_format_{uuid.uuid4().hex}")
        line = module.OverviewLine("id", "12:00:00", "assistant",
                                   "first\n\nimportant conclusion at the end", limit=24, preserve_tail=True)
        rendered = line.render()
        self.assertNotIn("\n", rendered)
        self.assertIn("first", rendered)
        self.assertIn("at the end", rendered)
        self.assertIn("…", rendered)

    def test_claude_and_codex_compactions_have_visible_markers(self):
        module = load_superv(f"superv_compaction_{uuid.uuid4().hex}")
        claude = module.claude_format({
            "type": "system", "subtype": "compact_boundary", "uuid": "c" * 36,
            "timestamp": "2026-08-10T00:00:00Z",
            "compactMetadata": {"preTokens": 250000, "postTokens": 80000},
        }, "cccccccc")
        codex = module.codex_format({
            "type": "event_msg", "timestamp": "2026-08-10T00:00:00Z",
            "payload": {"type": "context_compacted"},
        }, 12)
        self.assertIn("compaction", claude.render_overview())
        self.assertIn("from=250k", claude.render_overview())
        self.assertIn("compaction", codex.render_overview())


    def test_compaction_boundaries_do_not_reuse_stale_context_counts(self):
        module = load_superv(f"superv_compaction_ctx_{uuid.uuid4().hex}")
        pi_before = {"type": "message", "message": {"role": "assistant",
                     "usage": {"input": 200000, "cacheRead": 0}}}
        pi_boundary = {"type": "compaction"}
        self.assertIsNone(module.pi_last_context_tokens_from_entries([pi_before, pi_boundary]))
        pi_after = {"type": "message", "message": {"role": "assistant",
                    "usage": {"input": 25000, "cacheRead": 5000}}}
        self.assertEqual(module.pi_last_context_tokens_from_entries([pi_before, pi_boundary, pi_after]), 30000)

        claude_before = {"type": "assistant", "message": {"role": "assistant", "stop_reason": "end_turn",
                         "usage": {"input_tokens": 180000}}}
        claude_boundary = {"type": "system", "subtype": "compact_boundary"}
        self.assertIsNone(module.claude_last_context_tokens_from_entries([claude_before, claude_boundary]))
        self.assertEqual(module.claude_turn_state_from_entries([claude_before, claude_boundary]), "idle")

        codex_before = {"type": "event_msg", "payload": {"type": "token_count", "info": {
                        "last_token_usage": {"input_tokens": 150000}, "model_context_window": 200000}}}
        codex_boundary = {"type": "event_msg", "payload": {"type": "context_compacted"}}
        self.assertEqual(module.codex_last_context_tokens_from_entries([codex_before, codex_boundary]), (None, None))

    def test_file_backed_status_parses_each_session_once(self):
        module = load_superv(f"superv_parse_once_{uuid.uuid4().hex}")
        module.load_cursor = lambda worker: None
        with tempfile.TemporaryDirectory(prefix="superv-parse-once-") as directory:
            root = Path(directory)
            pi_path = root / "pi.jsonl"
            pi_path.write_text("\n".join([
                json.dumps({"type": "session", "version": 3, "id": "s", "cwd": directory}),
                json.dumps({"type": "message", "id": "12345678", "parentId": None,
                            "message": {"role": "assistant", "content": [], "stopReason": "stop"}}),
            ]) + "\n")
            claude_path = root / "claude.jsonl"
            claude_path.write_text(json.dumps({"type": "assistant", "uuid": "c" * 36,
                                                "message": {"role": "assistant", "content": [],
                                                            "stop_reason": "end_turn"}}) + "\n")
            codex_path = root / "codex.jsonl"
            codex_path.write_text(json.dumps({"type": "response_item", "payload": {
                "type": "message", "role": "assistant", "content": []}}) + "\n")

            counts = {"pi": 0, "claude": 0, "codex": 0}
            original_pi = module.pi_load_active
            original_claude = module.claude_load_entries
            original_codex = module.codex_load_entries
            def load_pi(path):
                counts["pi"] += 1
                return original_pi(path)
            def load_claude(path):
                counts["claude"] += 1
                return original_claude(path)
            def load_codex(path):
                counts["codex"] += 1
                return original_codex(path)
            module.pi_load_active = load_pi
            module.claude_load_entries = load_claude
            module.codex_load_entries = load_codex
            for kind, path in (("pi", pi_path), ("claude", claude_path), ("codex", codex_path)):
                rec = {"id": kind, "kind": kind, "persisted": {"path": str(path)}, "extra": {}}
                module.ADAPTERS[kind].status_signals(rec)
            self.assertEqual(counts, {"pi": 1, "claude": 1, "codex": 1})

    def test_failures_remain_explicit_in_all_four_adapter_overviews(self):
        module = load_superv(f"superv_errors_{uuid.uuid4().hex}")
        pi = module.pi_format({"type": "message", "id": "12345678", "timestamp": "2026-08-10T00:00:00Z",
                               "message": {"role": "bashExecution", "command": "false", "output": "bad", "exitCode": 7}})
        claude = module.claude_format({"type": "user", "uuid": "c" * 36, "timestamp": "2026-08-10T00:00:00Z",
                                      "message": {"role": "user", "content": [{"type": "tool_result",
                                      "tool_use_id": "tool-x", "is_error": True, "content": "failed read"}]}}, "cccccccc")
        codex = module.codex_format({"type": "response_item", "timestamp": "2026-08-10T00:00:00Z",
                                     "payload": {"type": "function_call_output", "call_id": "call-x",
                                     "status": "failed", "output": "permission error"}}, 2)
        opencode = module.oc_format_message({"info": {"id": "msg_x", "role": "assistant"}, "parts": [{
            "type": "tool", "tool": "read", "state": {"status": "failed", "input": {}, "error": "denied"}}]}, 0)
        self.assertIn("exit=7", pi.render_overview())
        self.assertIn("ERROR", claude.render_overview())
        self.assertIn("status=failed", codex.render_overview())
        self.assertIn("status=failed", opencode.render_overview())
        self.assertIn("denied", opencode.render_overview())


class OpenCodeAdapterTest(unittest.TestCase):
    def test_multiple_tools_are_individually_visible_and_prefixes_fail_closed(self):
        module = load_superv(f"superv_oc_{uuid.uuid4().hex}")
        messages = [
            {"info": {"id": "msg_aaaaaaaa11111111", "role": "assistant", "time": {"created": 1, "completed": 2}},
             "parts": [
                 {"type": "reasoning", "text": ""},
                 {"type": "tool", "tool": "read", "state": {"status": "completed", "input": {"path": "/tmp/a"}, "output": "A"}},
                 {"type": "tool", "tool": "grep", "state": {"status": "completed", "input": {"pattern": "ledger"}, "output": "found"}},
             ]},
            {"info": {"id": "msg_aaaaaaaa22222222", "role": "user", "time": {"created": 3}},
             "parts": [{"type": "text", "text": "continue"}]},
        ]
        module.http_get = lambda path, directory="/", timeout=10: messages
        module.load_cursor = lambda worker: None
        rec = {"id": "oc", "kind": "opencode", "extra": {"session_id": "ses_x", "directory": "/tmp"}}
        rendered, _ = module.OpenCodeAdapter.read_persisted(rec, count=2, use_cursor=False)
        overview = module.render_overview(rendered)
        self.assertEqual(overview.count(" tool "), 2)
        self.assertIn("read", overview)
        self.assertIn("grep", overview)
        self.assertNotIn("intent", overview)
        with self.assertRaisesRegex(ValueError, "ambiguous opencode message id prefix"):
            module.OpenCodeAdapter.detail(rec, "msg_aaaaaaaa")

    def test_status_fetches_messages_once_and_raw_detail_resolves_child(self):
        module = load_superv(f"superv_oc_status_{uuid.uuid4().hex}")
        messages = [
            {"info": {"id": "msg_bbbbbbbb11111111", "role": "assistant",
                      "time": {"created": 1, "completed": 2},
                      "tokens": {"input": 75000, "cache": {"read": 25000}}},
             "parts": [
                 {"type": "reasoning", "text": "Checking the final report"},
                 {"type": "tool", "tool": "read", "state": {
                     "status": "completed", "input": {"path": "/tmp/report"}, "output": "done"}},
             ]},
        ]
        calls = []
        def fake_get(path, directory="/", timeout=10):
            calls.append(path)
            if path.endswith("/message"):
                return messages
            return {"time": {"updated": int(module.time.time() * 1000)}}
        module.http_get = fake_get
        module.load_cursor = lambda worker: {"session_id": "ses_x", "last_msg_count": 0}
        rec = {"id": "oc", "kind": "opencode",
               "extra": {"session_id": "ses_x", "directory": "/tmp", "context_window_tokens": 200000}}
        signals = module.OpenCodeAdapter.status_signals(rec)
        line = module.status_line(rec, signals, include_latest=True)
        self.assertEqual(calls.count("/session/ses_x/message"), 1)
        self.assertIn("unread=1", line)
        self.assertIn("ctx=100k/200k(50%)", line)
        self.assertIn('latest_intent="Checking the final report"', line)
        raw = module.OpenCodeAdapter.raw_detail(rec, "msg_bbbbbbbb/result/1")
        self.assertEqual(raw["state"]["output"], "done")


if __name__ == "__main__":
    unittest.main(verbosity=2)
