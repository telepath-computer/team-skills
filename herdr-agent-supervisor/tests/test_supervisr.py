"""Offline unit tests for supervisr — no herdr, no live agents.

Run: python3 -m pytest tests/ -q   (or: python3 tests/test_supervisr.py)

Covers the parts that are pure logic: scope selection, the merged verdict,
cursor-based incremental reads, truncation, and one round-trip per adapter
against a synthetic transcript.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(ROOT))

# Route all state at a temp dir before importing anything that reads it.
_TMP = tempfile.mkdtemp(prefix="supervisr-test-")
os.environ["SUPERVISR_STATE_ROOT"] = _TMP

from supervisrlib import state  # noqa: E402
from supervisrlib.adapters import Source  # noqa: E402
from supervisrlib.adapters import claude as claude_ad  # noqa: E402
from supervisrlib.adapters import codex as codex_ad  # noqa: E402
from supervisrlib.adapters import pi as pi_ad  # noqa: E402
from supervisrlib.herdr import Context, Scope  # noqa: E402
from supervisrlib.render import clip_overview, unique_prefixes  # noqa: E402


def snapshot(agents):
    ws = {}
    for a in agents:
        ws.setdefault(a["workspace_id"], {"workspace_id": a["workspace_id"]})
    return {"agents": agents, "workspaces": list(ws.values())}


def agent(name, pane, ws="w1", tab="w1:t1", kind="claude", status="working", tokens=None):
    return {"name": name, "pane_id": pane, "workspace_id": ws, "tab_id": tab,
            "agent": kind, "agent_status": status, "tokens": tokens or {}}


class ScopeTests(unittest.TestCase):
    def ctx(self, ws="w1", pane="w1:p1"):
        c = Context()
        c.workspace_id, c.pane_id, c.tab_id = ws, pane, "w1:t1"
        return c

    def test_default_workspace_excludes_self(self):
        snap = snapshot([agent("me", "w1:p1"), agent("a", "w1:p2"), agent("other", "w2:p1", ws="w2")])
        got = Scope(self.ctx()).select(snap)
        self.assertEqual([x["name"] for x in got], ["a"])

    def test_include_self(self):
        snap = snapshot([agent("me", "w1:p1"), agent("a", "w1:p2")])
        got = Scope(self.ctx(), include_self=True).select(snap)
        self.assertEqual({x["name"] for x in got}, {"me", "a"})

    def test_all_crosses_workspaces(self):
        snap = snapshot([agent("me", "w1:p1"), agent("a", "w1:p2"), agent("b", "w2:p1", ws="w2")])
        got = Scope(self.ctx(), all_agents=True).select(snap)
        self.assertEqual({x["name"] for x in got}, {"a", "b"})

    def test_tab_narrows(self):
        snap = snapshot([agent("a", "w1:p2", tab="w1:t1"), agent("b", "w1:p3", tab="w1:t2")])
        got = Scope(self.ctx(), tab="w1:t2").select(snap)
        self.assertEqual([x["name"] for x in got], ["b"])

    def test_owned_requires_my_token(self):
        snap = snapshot([agent("mine", "w1:p2", tokens={"supervisr_owner": "w1:p1"}),
                         agent("theirs", "w1:p3", tokens={"supervisr_owner": "w9:p9"}),
                         agent("nobody", "w1:p4")])
        got = Scope(self.ctx(), owned=True).select(snap)
        self.assertEqual([x["name"] for x in got], ["mine"])

    def test_no_workspace_raises(self):
        snap = snapshot([agent("a", "w1:p2")])
        c = self.ctx(ws=None, pane=None)
        with self.assertRaises(ValueError):
            Scope(c).select(snap)


class VerdictTests(unittest.TestCase):
    def setUp(self):
        from supervisrlib.cli import Supervisr
        self.v = Supervisr.verdict

    def test_blocked_wins(self):
        self.assertEqual(self.v(agent("a", "p", status="blocked"), {"turn": "idle", "persisted_age_s": 0}), "BLOCKED")

    def test_stalled(self):
        self.assertEqual(self.v(agent("a", "p", status="working"), {"turn": "busy", "persisted_age_s": 900}), "stalled?")

    def test_working(self):
        self.assertEqual(self.v(agent("a", "p", status="working"), {"turn": "busy", "persisted_age_s": 5}), "working")

    def test_done_vs_idle(self):
        self.assertEqual(self.v(agent("a", "p", status="done"), {"turn": "idle", "persisted_age_s": 5}), "done")
        self.assertEqual(self.v(agent("a", "p", status="idle"), {"turn": "idle", "persisted_age_s": 5}), "idle")

    def test_idle_but_transcript_busy(self):
        # herdr thinks idle, transcript has a pending tool result → disagreement flagged
        self.assertEqual(self.v(agent("a", "p", status="idle"), {"turn": "busy", "persisted_age_s": 60}), "idle?")


class RenderTests(unittest.TestCase):
    def test_clip_preserves_tail(self):
        text = "start " + "x" * 200 + " END"
        out, cut = clip_overview(text, 40, preserve_tail=True)
        self.assertTrue(cut)
        self.assertTrue(out.startswith("start"))
        self.assertIn("END", out)

    def test_unique_prefixes_disambiguate(self):
        ids = ["abcd1234", "abcd5678", "zzzz0000"]
        pref = unique_prefixes(ids, minimum=2)
        self.assertNotEqual(pref["abcd1234"], pref["abcd5678"])


class ClaudeAdapterTests(unittest.TestCase):
    def _write(self, entries):
        d = Path(_TMP) / "claude"
        d.mkdir(exist_ok=True)
        p = d / "sess.jsonl"
        p.write_text("\n".join(json.dumps(e) for e in entries))
        return Source("claude", "sess", path=p)

    def transcript(self):
        return [
            {"type": "user", "uuid": "u1", "timestamp": "2026-01-01T00:00:00Z",
             "message": {"role": "user", "content": "do the thing"}},
            {"type": "assistant", "uuid": "a1", "timestamp": "2026-01-01T00:00:01Z",
             "message": {"role": "assistant", "stop_reason": "tool_use", "content": [
                 {"type": "thinking", "thinking": "**Planning**\n\nI will read the file."},
                 {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/x.py"}}],
                 "usage": {"input_tokens": 100, "cache_read_input_tokens": 900, "cache_creation_input_tokens": 0}}},
            {"type": "user", "uuid": "u2", "timestamp": "2026-01-01T00:00:02Z",
             "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "t1", "content": "print('hi')"}]}},
            {"type": "assistant", "uuid": "a2", "timestamp": "2026-01-01T00:00:03Z",
             "message": {"role": "assistant", "stop_reason": "end_turn", "content": [
                 {"type": "text", "text": "Done."}],
                 "usage": {"input_tokens": 200, "cache_read_input_tokens": 1200, "cache_creation_input_tokens": 0}}},
        ]

    def test_cursor_incremental(self):
        src = self._write(self.transcript())
        state.reset_cursor(src.sid)
        first, cur = claude_ad.read_persisted(src, count=None, use_cursor=True)
        # bootstrap without cursor returns the recent tail (<= default)
        self.assertTrue(first)
        state.save_cursor(src.sid, cur)
        again, _ = claude_ad.read_persisted(src, use_cursor=True)
        self.assertEqual(again, [])  # nothing new since cursor

    def test_tool_call_visible_and_intent(self):
        src = self._write(self.transcript())
        state.reset_cursor(src.sid)
        entries, cur = claude_ad.read_persisted(src, count=10, use_cursor=False)
        rendered = "\n".join(e.render() for e in entries)
        self.assertIn("tool: Read", rendered)
        self.assertIn("intent: Planning", rendered)
        self.assertIn("Done.", rendered)

    def test_turn_state_and_ctx(self):
        entries = claude_ad.visible(claude_ad.load_entries(self._write(self.transcript()).path))
        self.assertEqual(claude_ad.turn_state(entries), "idle")  # last is end_turn assistant
        self.assertEqual(claude_ad.last_context_tokens(entries), 1400)

    def test_context_window_from_sidecar(self):
        src = self._write(self.transcript())
        d = Path(_TMP) / "claude-ctx"
        d.mkdir(exist_ok=True, parents=True)
        (d / f"{state.safe_key(src.sid)}.json").write_text(json.dumps(
            {"context_window": {"context_window_size": 1000000, "total_input_tokens": 1400}}))
        window, used, source = claude_ad.context_window(src.sid, None)
        self.assertEqual(window, 1000000)
        self.assertEqual(source, "statusline")


class PiCodexSmokeTests(unittest.TestCase):
    def test_pi_active_branch(self):
        d = Path(_TMP) / "pi"
        d.mkdir(exist_ok=True)
        p = d / "1_sess.jsonl"
        rows = [
            {"type": "session", "id": "sess", "cwd": "/x"},
            {"type": "message", "id": "m1", "parentId": None, "timestamp": 1,
             "message": {"role": "user", "content": "hi"}},
            {"type": "message", "id": "m2", "parentId": "m1", "timestamp": 2,
             "message": {"role": "assistant", "stopReason": "end_turn",
                         "content": [{"type": "text", "text": "hello"}]}},
        ]
        p.write_text("\n".join(json.dumps(r) for r in rows))
        active = pi_ad.load_active(p)
        self.assertEqual([e["id"] for e in active], ["m1", "m2"])
        self.assertEqual(pi_ad.turn_state(active), "idle")

    def test_codex_raw_index_cursor(self):
        d = Path(_TMP) / "codex"
        d.mkdir(exist_ok=True)
        p = d / "rollout-2026-01-01-sess.jsonl"
        rows = [
            {"type": "session_meta", "payload": {"id": "sess", "cwd": "/x"}},
            {"type": "response_item", "timestamp": "t", "payload": {"type": "message", "role": "user",
                                                                    "content": [{"type": "input_text", "text": "go"}]}},
            {"type": "response_item", "timestamp": "t", "payload": {"type": "message", "role": "assistant",
                                                                    "content": [{"type": "output_text", "text": "ok"}]}},
        ]
        p.write_text("\n".join(json.dumps(r) for r in rows))
        src = Source("codex", "sess", path=p)
        state.reset_cursor(src.sid)
        entries, cur = codex_ad.read_persisted(src, count=10, use_cursor=False)
        self.assertIn("last_raw_idx", cur)
        self.assertIn("go", "\n".join(e.render() for e in entries))


if __name__ == "__main__":
    unittest.main(verbosity=2)
