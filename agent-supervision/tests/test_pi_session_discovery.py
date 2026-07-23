#!/usr/bin/env python3
"""Contract tests for deterministic Pi session discovery in `superv register`.

The defect these tests pin down: `superv register --kind pi` used to associate
a tmux pane with a session JSONL by "newest mtime in the cwd's session
directory". With two Pi agents in one cwd (an intended, normal setup), or with
a stale transcript next to a not-yet-flushed fresh one, that heuristic binds a
pane to another agent's transcript.

Contract:
  1. Registration binds a pane to a session only through an exact identity:
     `--session-id <id>` (the id the worker was launched with) or an explicit
     `--path`. Recency never decides.
  2. Without an explicit identity, registration FAILS CLOSED with a
     diagnostic; it never auto-selects a candidate and never writes a record.
  3. A session id resolves to exactly one file (filename-stem id AND header id
     must both match); ambiguity across project dirs is resolved only by the
     pane's cwd matching the session header cwd, else registration fails.
  4. A session file already bound to another registered worker cannot be
     bound again (two supervisor handles on one transcript is the defect).
  5. When a bound session file disappears, watch/status fail with a clear
     error instead of silently rebinding to whatever file is newest.

Everything runs against a throwaway HOME with a fake `tmux` on PATH, so no
live registry, session store, or tmux server is touched.

Run:  python3 skills/agent-supervision/tests/test_pi_session_discovery.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SUPERV = Path(__file__).resolve().parent.parent / "scripts" / "superv"

FAKE_TMUX = """#!/usr/bin/env bash
# Minimal tmux stand-in for superv registration tests.
# display-message -pt <target> <fmt> answers from env: FAKE_PANE_PATH / FAKE_PANE_PID.
args="$*"
case "$args" in
  *display-message*pane_current_path*) printf '%s\\n' "${FAKE_PANE_PATH:?}" ;;
  *display-message*pane_pid*)          printf '%s\\n' "${FAKE_PANE_PID:-$$}" ;;
  *capture-pane*)                      printf '' ;;
  *list-panes*)                        printf '' ;;
  *) exit 0 ;;
esac
"""


def pi_dir_key(cwd: str) -> str:
    return "--" + cwd.strip("/").replace("/", "-") + "--"


def write_session(
    sessions_root: Path,
    cwd: str,
    session_id: str,
    *,
    ts: str,
    assistant_text: str,
    mtime: float,
    flat_dir: Path = None,
) -> Path:
    """Create a minimal valid pi session JSONL with a controlled mtime."""
    d = flat_dir if flat_dir is not None else sessions_root / pi_dir_key(cwd)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{ts}_{session_id}.jsonl"
    header = {"type": "session", "version": 3, "id": session_id,
              "timestamp": ts.replace("-", ":", 5), "cwd": cwd}
    user = {"type": "message", "id": "u1", "parentId": None,
            "timestamp": "2026-07-23T00:00:01.000Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "hello"}]}}
    asst = {"type": "message", "id": "a1", "parentId": "u1",
            "timestamp": "2026-07-23T00:00:02.000Z",
            "message": {"role": "assistant",
                        "content": [{"type": "text", "text": assistant_text}],
                        "stopReason": "stop",
                        "usage": {"input": 10, "output": 5, "cacheRead": 0,
                                  "cacheWrite": 0, "totalTokens": 15}}}
    with path.open("w", encoding="utf-8") as f:
        for e in (header, user, asst):
            f.write(json.dumps(e) + "\n")
    os.utime(path, (mtime, mtime))
    return path


class SupervPiDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="superv-pi-test-")
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.state_root = Path(self.tmp.name) / "superv-state"
        self.sessions_root = self.home / ".pi" / "agent" / "sessions"
        self.cwd = str(Path(self.tmp.name) / "worktree")
        Path(self.cwd).mkdir()
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        tmux = bin_dir / "tmux"
        tmux.write_text(FAKE_TMUX)
        tmux.chmod(0o755)
        self.env = dict(os.environ)
        self.env.update({
            "HOME": str(self.home),
            "PATH": f"{bin_dir}:{self.env['PATH']}",
            "AGENT_SUPERVISION_ROOT": str(self.state_root),
            "FAKE_PANE_PATH": self.cwd,
            "FAKE_PANE_PID": str(os.getpid()),
        })

    def tearDown(self):
        self.tmp.cleanup()

    def superv(self, *args: str):
        return subprocess.run(
            [sys.executable, str(SUPERV), *args],
            capture_output=True, text=True, env=self.env, timeout=60,
        )

    def record(self, worker_id: str) -> dict:
        p = self.state_root / "workers" / f"{worker_id}.json"
        self.assertTrue(p.exists(), f"expected registry record at {p}")
        return json.loads(p.read_text())

    def assert_no_record(self, worker_id: str):
        p = self.state_root / "workers" / f"{worker_id}.json"
        self.assertFalse(p.exists(), f"registration must not write a record on failure ({p})")

    def two_agents_fixture(self):
        """Two sessions in ONE cwd; 'beta' has the newer mtime."""
        now = time.time()
        a = write_session(self.sessions_root, self.cwd, "alpha",
                          ts="2026-07-23T10-00-00-000Z", assistant_text="ALPHA SPEAKING",
                          mtime=now - 600)
        b = write_session(self.sessions_root, self.cwd, "beta",
                          ts="2026-07-23T10-05-00-000Z", assistant_text="BETA SPEAKING",
                          mtime=now - 5)
        return a, b

    # -- 1. exact binding despite adversarial mtimes --------------------------

    def test_session_id_binds_exact_file_despite_newer_sibling(self):
        a, b = self.two_agents_fixture()
        r = self.superv("register", "w-alpha", "--kind", "pi", "--tmux", "s:w.0",
                        "--session-id", "alpha")
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        rec = self.record("w-alpha")
        self.assertEqual(rec["persisted"]["path"], str(a))
        self.assertEqual(rec["extra"]["session_id"], "alpha")

        r2 = self.superv("register", "w-beta", "--kind", "pi", "--tmux", "s:w2.0",
                         "--session-id", "beta")
        self.assertEqual(r2.returncode, 0, f"stderr: {r2.stderr}")
        self.assertEqual(self.record("w-beta")["persisted"]["path"], str(b))

    def test_registration_order_against_mtime_order_isolated_watch(self):
        """Both agents register (order chosen against mtime order); each watch
        sees only its own transcript."""
        self.two_agents_fixture()
        self.superv("register", "w-alpha", "--kind", "pi", "--tmux", "s:w.0",
                    "--session-id", "alpha")
        self.superv("register", "w-beta", "--kind", "pi", "--tmux", "s:w2.0",
                    "--session-id", "beta")
        wa = self.superv("watch", "w-alpha", "--count", "5")
        wb = self.superv("watch", "w-beta", "--count", "5")
        self.assertIn("ALPHA SPEAKING", wa.stdout)
        self.assertNotIn("BETA SPEAKING", wa.stdout)
        self.assertIn("BETA SPEAKING", wb.stdout)
        self.assertNotIn("ALPHA SPEAKING", wb.stdout)

    # -- 2. fail closed without explicit identity -----------------------------

    def test_register_without_identity_fails_closed(self):
        a, b = self.two_agents_fixture()
        r = self.superv("register", "w-any", "--kind", "pi", "--tmux", "s:w.0")
        self.assertNotEqual(r.returncode, 0,
                            "register without --session-id/--path must fail closed, "
                            f"but succeeded with: {r.stdout}")
        self.assert_no_record("w-any")
        self.assertIn("--session-id", r.stderr)
        # candidates are listed for the operator but never chosen
        self.assertIn("alpha", r.stderr)
        self.assertIn("beta", r.stderr)

    def test_single_stale_file_is_not_auto_bound(self):
        """Launch-timing trap: a fresh pi has no JSONL yet (pi flushes on its
        first assistant reply); the only file on disk is a stale transcript.
        Registration without identity must not bind it."""
        write_session(self.sessions_root, self.cwd, "stale",
                      ts="2026-07-20T10-00-00-000Z", assistant_text="OLD RUN",
                      mtime=time.time() - 86400)
        r = self.superv("register", "w-fresh", "--kind", "pi", "--tmux", "s:w.0")
        self.assertNotEqual(r.returncode, 0)
        self.assert_no_record("w-fresh")

    # -- 3. session id not on disk yet (lazy flush) ---------------------------

    def test_session_id_before_first_flush_fails_with_wait_hint(self):
        write_session(self.sessions_root, self.cwd, "stale",
                      ts="2026-07-20T10-00-00-000Z", assistant_text="OLD RUN",
                      mtime=time.time() - 86400)
        r = self.superv("register", "w-new", "--kind", "pi", "--tmux", "s:w.0",
                        "--session-id", "gamma")
        self.assertNotEqual(r.returncode, 0)
        self.assert_no_record("w-new")
        self.assertIn("gamma", r.stderr)
        self.assertIn("first assistant reply", r.stderr)

    # -- 4. same id in two project dirs ---------------------------------------

    def test_same_id_two_cwds_disambiguated_by_pane_cwd(self):
        other_cwd = str(Path(self.tmp.name) / "other-worktree")
        Path(other_cwd).mkdir()
        now = time.time()
        write_session(self.sessions_root, other_cwd, "delta",
                      ts="2026-07-23T09-00-00-000Z", assistant_text="OTHER PROJECT",
                      mtime=now - 30)
        mine = write_session(self.sessions_root, self.cwd, "delta",
                             ts="2026-07-23T08-00-00-000Z", assistant_text="MY PROJECT",
                             mtime=now - 3000)
        r = self.superv("register", "w-delta", "--kind", "pi", "--tmux", "s:w.0",
                        "--session-id", "delta")
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        self.assertEqual(self.record("w-delta")["persisted"]["path"], str(mine))

    def test_id_found_only_under_foreign_cwd_fails(self):
        other_cwd = str(Path(self.tmp.name) / "other-worktree")
        Path(other_cwd).mkdir()
        write_session(self.sessions_root, other_cwd, "epsilon",
                      ts="2026-07-23T09-00-00-000Z", assistant_text="OTHER PROJECT",
                      mtime=time.time() - 30)
        r = self.superv("register", "w-eps", "--kind", "pi", "--tmux", "s:w.0",
                        "--session-id", "epsilon")
        self.assertNotEqual(r.returncode, 0)
        self.assert_no_record("w-eps")
        self.assertIn(other_cwd, r.stderr)

    def test_suffix_id_does_not_false_match(self):
        """id 'b' must not match a file for id 'a_b' (glob suffix trap)."""
        write_session(self.sessions_root, self.cwd, "a_b",
                      ts="2026-07-23T10-00-00-000Z", assistant_text="AB",
                      mtime=time.time() - 10)
        r = self.superv("register", "w-b", "--kind", "pi", "--tmux", "s:w.0",
                        "--session-id", "b")
        self.assertNotEqual(r.returncode, 0)
        self.assert_no_record("w-b")

    # -- 5. duplicate transcript guard ----------------------------------------

    def test_second_worker_cannot_bind_same_transcript(self):
        self.two_agents_fixture()
        r1 = self.superv("register", "w-one", "--kind", "pi", "--tmux", "s:w.0",
                         "--session-id", "alpha")
        self.assertEqual(r1.returncode, 0, f"stderr: {r1.stderr}")
        r2 = self.superv("register", "w-two", "--kind", "pi", "--tmux", "s:w2.0",
                         "--session-id", "alpha")
        self.assertNotEqual(r2.returncode, 0,
                            "binding a second worker to the same transcript must fail")
        self.assert_no_record("w-two")
        self.assertIn("w-one", r2.stderr)

    # -- 6. explicit --path still works and is validated ----------------------

    def test_path_override_binds_and_records_session_id(self):
        a, _ = self.two_agents_fixture()
        r = self.superv("register", "w-path", "--kind", "pi", "--tmux", "s:w.0",
                        "--path", str(a))
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        rec = self.record("w-path")
        self.assertEqual(rec["persisted"]["path"], str(a))
        self.assertEqual(rec["extra"]["session_id"], "alpha")

    def test_path_rejects_non_session_file(self):
        bogus = Path(self.tmp.name) / "not-a-session.jsonl"
        bogus.write_text('{"type":"something-else"}\n')
        r = self.superv("register", "w-bogus", "--kind", "pi", "--tmux", "s:w.0",
                        "--path", str(bogus))
        self.assertNotEqual(r.returncode, 0)
        self.assert_no_record("w-bogus")

    def test_path_and_session_id_must_agree(self):
        a, b = self.two_agents_fixture()
        r = self.superv("register", "w-x", "--kind", "pi", "--tmux", "s:w.0",
                        "--path", str(a), "--session-id", "beta")
        self.assertNotEqual(r.returncode, 0)
        self.assert_no_record("w-x")

    # -- 7. custom session dir (pi --session-dir) -----------------------------

    def test_session_dir_flag_binds_in_flat_dir(self):
        flat = Path(self.tmp.name) / "flat-sessions"
        now = time.time()
        write_session(self.sessions_root, self.cwd, "noise",
                      ts="2026-07-23T10-06-00-000Z", assistant_text="NOISE",
                      mtime=now - 1)  # newer noise in the DEFAULT root
        mine = write_session(self.sessions_root, self.cwd, "zeta",
                             ts="2026-07-23T10-00-00-000Z", assistant_text="FLAT",
                             mtime=now - 500, flat_dir=flat)
        r = self.superv("register", "w-flat", "--kind", "pi", "--tmux", "s:w.0",
                        "--session-id", "zeta", "--session-dir", str(flat))
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        rec = self.record("w-flat")
        self.assertEqual(rec["persisted"]["path"], str(mine))
        self.assertEqual(rec["persisted"]["session_dir"], str(flat))

    # -- 8. no silent rebinding after the bound file disappears ---------------

    def test_watch_fails_loud_when_bound_file_vanishes(self):
        a, b = self.two_agents_fixture()
        self.superv("register", "w-alpha", "--kind", "pi", "--tmux", "s:w.0",
                    "--session-id", "alpha")
        a.unlink()
        w = self.superv("watch", "w-alpha", "--count", "5")
        self.assertNotEqual(w.returncode, 0,
                            "watch must fail when the bound transcript is gone, "
                            f"got stdout: {w.stdout}")
        self.assertNotIn("BETA SPEAKING", w.stdout,
                         "watch must never fall back to a sibling transcript")

    def test_legacy_record_without_session_id_also_fails_loud(self):
        """Records written before this change have no extra.session_id; if
        their file vanishes they must fail too, not rebind by recency."""
        a, b = self.two_agents_fixture()
        workers = self.state_root / "workers"
        workers.mkdir(parents=True, exist_ok=True)
        legacy = {
            "id": "w-legacy", "kind": "pi",
            "live": {"type": "tmux", "target": "s:w.0"},
            "send": {"type": "tmux", "target": "s:w.0"},
            "persisted": {"type": "jsonl", "path": str(a), "cwd": self.cwd},
            "extra": {},
            "created_at": "2026-07-23T00:00:00Z", "updated_at": "2026-07-23T00:00:00Z",
        }
        (workers / "w-legacy.json").write_text(json.dumps(legacy))
        a.unlink()
        w = self.superv("watch", "w-legacy", "--count", "5")
        self.assertNotEqual(w.returncode, 0)
        self.assertNotIn("BETA SPEAKING", w.stdout)
        s = self.superv("status", "w-legacy")
        self.assertNotIn("BETA", s.stdout)

    # -- 9. flag validation ----------------------------------------------------

    def test_session_flags_rejected_for_other_kinds(self):
        r = self.superv("register", "w-c", "--kind", "claude", "--tmux", "s:w.0",
                        "--session-id", "nope")
        self.assertNotEqual(r.returncode, 0)
        r2 = self.superv("register", "w-oc", "--kind", "opencode",
                         "--oc-session", "ses_x", "--session-dir", "/tmp/x")
        self.assertNotEqual(r2.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
