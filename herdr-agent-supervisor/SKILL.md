---
name: herdr-agent-supervisor
description: "EXPERIMENTAL. The agent supervisor for workers running inside herdr. Load ONLY when a user directly tells you to — never on your own initiative. Like tmux-agent-supervisor, this skill replaces your role: it narrows you to supervising other agents (observe, nudge, route, unblock) and nothing else — you do not author or review code while supervising. Use this one when the workers are herdr agents (Claude Code, Codex, Pi in herdr panes); supervision runs through the `supervisr` CLI, which wraps herdr's control API and adds token-efficient, cursor-based transcript observation, plus herdr's own blocked-dialog detection and persistence. For workers in bare tmux panes, separate processes, or HTTP ports without herdr, use tmux-agent-supervisor instead. Do not load this because you are curious what another agent is doing; a worker tempted to watch its peers should tell its own supervisor."
---

# herdr-agent-supervisor — agent supervision on herdr

This skill is **self-contained**: its `core.md` (the supervisor stance) and
`workers.md` (per-kind notes) live in this directory. It does not depend on any
`tmux-*` skill; the `tmux-agent-supervisor` skill is only mentioned as the
non-herdr alternative, never read from here.

## Required reading before you supervise — MANDATORY

Read both, in full, before running any `supervisr` command:

1. **The `herdr` skill** (`../herdr/SKILL.md`). supervisr sits on top of herdr and
   hands the rest of herdr — topology, worktrees, sessions, the raw agent/pane
   commands — back to you for setup-time work. You cannot use that half competently
   without the herdr skill, and you will misread what supervisr wraps versus what it
   leaves to herdr. This is not optional background; it is the substrate. If the
   `herdr` skill is not installed alongside this one, load it from the herdr repo
   (`skills/herdr/SKILL.md` at your installed herdr version) first.
2. **This skill's own supporting files:**
   - `./core.md` — the supervisor *stance* (stance ladder, don't-perturb, nudge/idle
     taxonomy, verification ladder, reporting principles, `/compact` rule,
     compaction orientation, completion/teardown). supervisr changes the transport,
     not the stance.
   - `./heartbeat.md` — scheduling the supervisor loop (cron/loop cadence, the
     `supervisr events` accelerator) and the full cycle-reporting discipline.
   - `./workers.md` and the per-kind `./workers/<kind>.md` for each kind you will
     supervise (Claude / Codex / Pi) — the per-kind quirks and, importantly, the
     **context-window handling that differs by model and decides when you compact**.

supervisr is the third layer: **herdr** (control the terminals and agents) →
**this skill's `core.md` + `heartbeat.md` + `workers/`** (how to be a supervisor) →
**supervisr** (the token-efficient, transcript-aware toolset that joins the two).
Skipping either lower layer means you will drive the tool without knowing the
substrate or the role.

## What is different from the tmux supervisor

(The `tmux-agent-supervisor` skill is the separate, non-herdr sibling — read
this row as "how herdr changes the job," not as a dependency.)

| | tmux supervisor (`superv`) | supervisr (this skill) |
|---|---|---|
| where workers live | tmux panes / HTTP ports | herdr agents |
| who tracks them | a `superv` registry you populate | herdr's `agent list` — no registry |
| busy/idle | transcript turn-state only | herdr's semantic status **+** transcript turn-state |
| **blocked at a permission dialog** | invisible (looks busy) | herdr detects it — the biggest single win |
| observation | `superv watch` (cursor, truncated) | `supervisr watch` (same model, ported) |
| send / wait | tmux send-keys / file poll | herdr `agent.prompt` / event hub |
| survival | dies with tmux | herdr persists across detach/restart |

The token-efficiency contract is identical: **route with `sweep`, read deltas
with `watch`, never re-read history or screen-scrape.** That is why this skill
exists — herdr's own `agent read` is a full-screen re-send with no cursor.

## Setup

See `setup.md`. In one line: `herdr integration install <kind>` for each worker
kind (this is how herdr learns session ids — mandatory), then
`supervisr setup statusline` for Claude context %, then `supervisr doctor`.

## The rule that keeps you efficient

**Every command you run while supervising is a `supervisr` command.** Raw `herdr`
is for one-time topology only (`workspace`, `tab`, `pane split`, `worktree`,
`integration install`). The reason: herdr's `agent read` re-sends the whole
screen (80–1000 lines, no delta) and `agent prompt` / `agent wait` have sharp
edges (`agent read` is a token trap, prompt refuses blocked agents, wait is
single-target). `supervisr` gives you the cursor-based, blocked-aware, scope-aware
versions. Pass `--verbose` to see the underlying herdr call for anything.

Where a command is a thin wrapper (send, answer, wait, interrupt, screen,
explain, stop), it passes straight through to herdr and adds no logic of its
own — `send` is herdr's `agent.prompt` (with herdr's own effect-gate and settle
wait under `--wait`); readiness, blocked-refusal, and "did it take effect" are
herdr's answers, surfaced honestly, never reimplemented. supervisr adds logic
only where herdr structurally cannot: the transcript (observation, cursors,
ctx%), scope, and answering a startup trust dialog.

## Scope — which agents you see

A filter over `herdr agent list`, computed fresh each call. No registration.

- **default:** your own workspace (`$HERDR_WORKSPACE_ID`), excluding your own pane.
- `--tab ID` narrow · `--owned` only agents you dispatched/adopted · `--all` the whole herdr session · `--repo` workspaces sharing your git repo (herdr worktree provenance) · `--workspace ID` · `--session NAME` a different herdr server.

One herdr **workspace = one task** (the equivalent of a tmux session): your
supervisor pane plus its workers, all in one sidebar. Multiple worktrees for one
task are just panes with different cwds in that workspace. Agent **names are
unique across the whole herdr session**, so name workers by task (`auth-impl`,
`auth-review`) — a bare `reviewer` collides across tasks.

## The loop

```
supervisr sweep                 # one line per agent; verdict, unread, ctx%, latest intent
supervisr watch <name>          # only for rows with unread>0 or a status worth reading
# decide, then:
supervisr send <name> "..."     # nudge via herdr; refuses blocked; --wait to confirm+settle
```

`sweep` is your routing view — cheap, never moves a cursor. Read through `watch`
only what `sweep` flags. `watch` keeps the same cursor contract
exactly: detailed if it fits, else a compact overview that advances the cursor
only through what it showed and tells you to run again until `OBSERVATION
COMPLETE`. Follow that; never reach for the pane instead.

**Blocked.** When `sweep` shows `BLOCKED`, the trailing text is the dialog
herdr matched. `supervisr screen <name>` shows the full dialog (bounded).
Then `supervisr answer <name> enter|esc|y|n|2|"text"` for routine approvals the
user pre-authorized, or escalate. Never answer a dialog you do not recognize.
This is the case `superv` was blind to — use it.

**Verdict disagreements.** `sweep` shows `?` (e.g. `idle?`, `stalled?`) when
herdr's screen status and the transcript turn-state disagree — herdr says idle
but the transcript has a pending tool call, or working but the transcript has
been quiet for minutes. That disagreement is the cue to `supervisr screen` and
look, exactly as core.md warns a mechanical verdict is a cue, not a conclusion.

## Heartbeat and events

One global recurring self-nudge, torn down only at a `core.md` steady-state
no-action condition. The scheduling mechanics (cron/loop by harness, the 2-min
cache-window cadence, don't-ramp, the `pi-loop` `maxFires` override) and the full
cycle-reporting discipline are in **`heartbeat.md`** — read it. In brief: use your
harness's scheduler (`CronCreate` for Claude, `LoopCreate` for Pi) with the
canonical prompt at a fixed ~2-minute cadence.

herdr adds one genuinely new, non-anti-pattern tool: **`supervisr events`**, which
streams one line per status transition of the agents in scope from herdr's event
hub (`EVENT alice blocked`). Unlike a `Monitor` that polls for a guessed text
pattern, it fires on herdr's authoritative state, so it is not a wrong-premise
trap. Run it under a background Monitor as an *accelerator* between heartbeats,
with the recurring heartbeat as the backstop; park it on already-running workers.
Details in `heartbeat.md`.

## Dispatch

```
supervisr dispatch <name> --kind claude|codex|pi \
  [--cwd PATH | --worktree BRANCH [--base REF]] \
  [--new-tab LABEL | --split right|down | --pane ID] \
  [--trust-folder] [--prompt "..." | --file brief.md] [--wait]
```

One command: make/choose the location (a new tab by default, named after the agent), start the agent (with defaults below), stamp
an ownership token, wait for readiness (handling Claude's folder-trust dialog
with `--trust-folder`), optionally send the first prompt and wait for the reply.
`--worktree` uses `git worktree add` (not herdr's worktree command), so one task
can hold several checkouts in one workspace.

**Launch defaults are deliberate choices, shown in `--help` and overridable:**
model `claude-fable-5` / `gpt-5.6-sol` (codex) / `openai-codex/gpt-5.6-sol` (pi);
effort `xhigh` everywhere; permissions bypassed (`--dangerously-skip-permissions`
/ `--yolo`); placement is a new tab per agent. Override per dispatch with `--model`,
`--effort`, and `--new-tab <label>` / `--split right|down` / `--pane <id>`.

`supervisr adopt <name>` takes over an agent someone else started (cursor at the
current tail, or `--count N` to leave N unread; plus the ownership token) —
including a Claude session that predates supervisr in your own workspace.

## Command reference

Observe (never perturbs): `sweep` · `status <t>` · `watch <t> [--count N|--reset|--full|--force]` · `detail <t> <locator> [--raw --force]` · `recent <t> [--kind messages|tools|errors]` · `screen <t> [--lines N]` · `explain <t>`
Act: `send <t> "msg"|--file P [--wait]` (thin pass-through to herdr agent.prompt) · `answer <t> <keys|text>` · `interrupt <t> [--hard]`
Wait: `wait [t...] [--until ...] [--timeout S]` · `events [t...] [--until ...]`
Lifecycle: `dispatch …` · `adopt <t> [--count N]` · `stop <t> [--close-pane]` · `forget <t>`
Bookkeeping: `note <t> "…" --tag T` · `notes <t>` · `doctor` · `setup statusline`

Targets are a herdr agent **name** or **pane id**. `--json` on read commands;
`--verbose` prints the herdr call.

## Recovery after context loss

Cursors, notes, and the session cache are on disk, unaffected by compaction.
`supervisr sweep` reorients you (it re-derives scope from herdr, so it needs no
memory of who your workers are), then `supervisr watch` each flagged worker for
the delta. Do not re-read history.

## Known limits

- `events` can miss the first transitions of an agent that appears *and*
  changes state within the same rescope window; park it on running agents and
  lean on the heartbeat for freshly dispatched ones.
- Transcript formats are the agents' internal formats; a major version change in
  an agent could require an adapter update (`supervisr doctor` will show
  `no-transcript` / errors if so).
