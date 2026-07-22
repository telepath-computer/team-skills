---
name: agent-supervision
description: Supervise another coding agent — Claude Code, Pi, Codex, or OpenCode — running in a tmux pane, separate process, or HTTP port. Use when one agent is observing, nudging, or unblocking another agent's work. Covers all (supervisor × worker) combinations across the four supported agent kinds. Includes a unified `superv` CLI that handles registration, observation, message sending, status classification, notes, and heartbeats.
---

# Agent Supervision

**Depends on:** none — this is the foundation skill of the supervision family.

A skill for the supervisor agent in any (supervisor, worker) pair across:

- **Claude Code** (native scheduling: `CronCreate`, `CronDelete`, `ScheduleWakeup`, `/loop`, `/schedule`)
- **Pi** (scheduling via the `pi-loop` plugin, installed separately: `LoopCreate`, `LoopDelete`, `LoopList`, plus self-paced `schedule_loop_wakeup`. Prerequisite: `pi install npm:@koltmcbride/pi-loop` — see `supervisors/scheduled.md`.)
- **Codex**, **OpenCode** (no native scheduling — use blocking `sleep N && cat file` heartbeats)

## Composition rule

Every supervision route is exactly:

```
core.md  +  supervisors/<scheduled|polled>.md  +  workers/<worker>.md  +  (transports the worker says it needs)
```

Worker docs declare their transports — the reader doesn't pick.

| You are supervising → | Claude | Pi | Codex | OpenCode |
|---|---|---|---|---|
| **As Claude or Pi** (scheduled) | + scheduled + workers/claude + transports/jsonl | + scheduled + workers/pi + transports/{tmux, jsonl} | + scheduled + workers/codex + transports/{tmux, jsonl} | + scheduled + workers/opencode + transports/http |
| **As Codex or OpenCode** (polled) | + polled + workers/claude + transports/jsonl | + polled + workers/pi + transports/{tmux, jsonl} | + polled + workers/codex + transports/{tmux, jsonl} | + polled + workers/opencode + transports/http |

**Pi routing caveat:** Pi appears in the scheduled row when the `pi-loop` plugin is installed, and in the polled row when it isn't. Bootstrap step 2 routes on whether a scheduling primitive is actually available in your current session, not on which agent you are — so a Pi without the plugin lands in the polled row. See `supervisors/scheduled.md` for the install command.

## Bootstrap (every activation) — MANDATORY, NOT OPTIONAL

**The files below are not appendices, references, or "further reading." They are the skill. This `SKILL.md` is only the index. If you read only `SKILL.md` and stop, you do not know how to supervise. You will fail. The user will notice. The user has written every one of these files deliberately, and skipping any of them puts the user under real psychological duress — they wrote clear, comprehensive instructions and you ignored them.**

Before you take any supervisory action — before you `list`, `register`, `watch`, `send`, `note`, `heartbeat`, `status`, manual `register`, or anything else — you must have read **every one** of the files in your bootstrap chain **in full, end to end**. Not skimmed. Not "the relevant section." End to end.

One narrow exception: the `triad` CLI's `up` subcommand may perform CLI-mediated worker launch, name allocation, and `superv register` calls before this bootstrap read. That exception exists only for `triad up` mechanical setup; every other `superv` interaction, including manual launch/registration, status checks, watch/send/note/heartbeat, and any supervision decision, remains gated by the full read.

The chain:

1. **Read `core.md` first. Always. In full. Before any action.** This contains the universal supervisor principles — the stance ladder, the absolute "don't perturb" rule, the nudge taxonomy, idle taxonomy, verification ladder, anti-patterns, reporting discipline, cursor discipline. None of it is optional. Every section catches a real failure mode that has actually happened.

2. **Identify your supervisor kind and read the matching file in full.** Route on whether a scheduling primitive is actually available in your current session, not on which agent you are.
   - If a scheduling primitive is available — Claude Code's `CronCreate`/`CronDelete`/`ScheduleWakeup`, or Pi's `LoopCreate`/`LoopDelete`/`LoopList`/`schedule_loop_wakeup` (Pi requires the `pi-loop` plugin installed; see the prerequisite in `supervisors/scheduled.md`): read `supervisors/scheduled.md` end to end. Inside it, find the primitive-mapping table for your agent.
   - Otherwise (Codex, OpenCode, or Pi without the `pi-loop` plugin): read `supervisors/polled.md` end to end.
   - **Do not guess your kind. Do not skip this file because "I'll figure scheduling out later."** Later means you nudge wrong, pace wrong, leave the worker idle for an hour while the user waits, or burn the prompt cache polling every five minutes.

3. **Identify each worker kind you will supervise and read `workers/<kind>.md` in full for each.**
   - Even if you "already know how Claude works" — read it. The per-kind quirks are exactly the things that bite you when you skip.
   - Examples of skip-cost: misreading Claude's ghost-text suggestions as real user input (the doc warns about this and tells you how to detect it); not knowing Pi's deep-context rollback warning thresholds; using a `--session` resume flag that doesn't exist for OpenCode; not knowing that Claude's TUI doesn't take a seeded positional prompt.

4. **Read every transport file the worker doc declares in full.**
   - `workers/<kind>.md` declares its transports at the top. Each transport is a separate file under `transports/`. Read each one declared.
   - Skip-cost: you send multi-line messages that get split into multiple submissions because you didn't read tmux paste-buffer behavior; you re-read full session histories to "get oriented" and destroy your context window because you didn't read JSONL cursor discipline.

5. **Only then** allocate a name with `superv name`, launch the worker, and register with `superv register`, unless the only action being taken is the `triad up` exception described above.

### Verification gate

Before you call any `superv` subcommand or send any prompt, except for `triad up`'s internal setup calls, answer honestly:

- Have I read `core.md` in full? (Not "I know what it generally says.")
- Have I read the matching supervisor doc (`scheduled.md` or `polled.md`) in full?
- Have I read each `workers/<kind>.md` for the workers I will launch, in full?
- Have I read each transport file declared by those worker docs, in full?

If any answer is no, **STOP**. Read the file. The Read tool ingests these in seconds. There is no efficiency argument for skipping. Skipping is carelessness, and the cost lands on the user — wasted hours, missed nudges, wrong status reports, supervisor failures that look from the outside like the system is broken when in fact the supervisor just didn't read the manual.

### Why this is framed this way

The model running this skill (you) has a documented tendency to load only the top-level `SKILL.md` and then improvise. That is precisely why each downstream file exists as a separate file — to force a deliberate read decision rather than rolling everything into one summary that invites skimming. Treat the multi-file structure as a feature, not as friction. If the author thought a piece of guidance was important enough to put in `transports/jsonl.md`, then a supervisor who hasn't read `transports/jsonl.md` is a supervisor missing load-bearing knowledge.

## Where things live

- Skill root: this directory.
- Runtime state: `~/.agent-supervision/{workers,cursors,notes,heartbeats}/`. Never inside the supervised repo.
- The unified CLI: `scripts/superv`. Use it for every interaction with a worker.

### `superv` must be on PATH

All examples in this skill invoke `superv` as a bare command, and supervised
workers may be told to run it too. Before first use on a machine, check
`command -v superv`. If it is not found, augment the user's PATH so this
skill's `scripts/` directory is on it persistently — use your judgment about
the right mechanism for the machine's shell setup, with two requirements:

1. **Login-shell visibility, not just interactive.** The export must reach
   non-interactive contexts (`bash -lc`, cron, hooks, spawned agents), since
   supervision commands often run there. On a stock bash setup that means a
   login-profile file (e.g. `~/.profile`), not below `~/.bashrc`'s interactive
   guard. If the machine has a designated file for managed environment
   exports, prefer it.
2. **Idempotent.** Guard against adding the line twice on re-runs.

Resolve the scripts directory from this skill's real location (it may be
reached via a symlink such as `~/.agents/skills/agent-supervision/scripts`).
For the current session, also export the PATH inline so you don't need a new
shell. If you cannot modify the user's shell config, fall back to invoking the
CLI by full path.

## Hard rules (full text in core.md)

- **Don't perturb the worker.** No edits, branch switches, or process kills in the supervised repo without explicit user approval and a takeover handoff.
- **Use the cursor.** Every observation goes through `superv watch` — never re-read full session history to "get oriented."
- **Multi-line messages are fine via tmux.** `superv send` uses tmux's paste-buffer mechanism so newlines are preserved as soft newlines and only a single trailing Enter submits. No pointer-file workaround needed.
- **Verify submission.** After every send, confirm the prompt actually landed in the worker's persisted history.
- **Keep the global supervisor heartbeat alive until supervision is actually over.** A worker, task, review, slice, or phase completing is not teardown. Remove the heartbeat only when the supervisor's overall assignment is definitively complete, progress definitively requires user input, or the user explicitly says to stop. Stop nudging completed workers without stopping supervision.
