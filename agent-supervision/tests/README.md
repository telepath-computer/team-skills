# agent-supervision tests

Run:

```bash
python3 skills/agent-supervision/tests/test_pi_session_discovery.py
```

Stdlib-only (`unittest`); no pytest, no network, no real agents.

## Isolation model — and a hard rule about tmux

The suite never executes the real `tmux` binary or launches any agent
process. Each test runs `superv` as a subprocess with:

- a fake `tmux` shell stub prepended to `PATH` (answers `display-message`
  queries from env vars; inert for everything else),
- `HOME` pointed at a temp dir (fixture pi session store lives there),
- `AGENT_SUPERVISION_ROOT` pointed at a temp dir (private registry).

Session transcripts are fabricated JSONL fixtures with controlled mtimes.
Blast radius: temp dirs only.

**Do not write live-tmux test harnesses for this skill without an explicitly
reviewed isolation design.** A past end-to-end script exported `TMUX_TMPDIR`
for a "private" server but inherited the parent `TMUX` environment variable —
tmux clients resolve the server from `$TMUX` first, so the script's cleanup
`tmux kill-server` destroyed the operator's real server and every supervised
session in it. If a live harness is ever genuinely needed, minimum bar:
`unset TMUX`, address one explicit socket via `tmux -S <path>` on every call,
verify the effective socket (`tmux display-message -p '#{socket_path}'`)
before anything destructive, and never use server-wide kills — especially not
in an EXIT trap.
