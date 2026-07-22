---
name: agent-triad
description: Launch a three-agent tmux triad with the current agent as supervisor, a Pi worker by default, and a Claude reviewer by default; worker and reviewer start idle and receive task instructions only after explicit supervisor delegation.
---

# Agent Triad

**Depends on:** agent-supervision, start-worktree.

Use this skill when the user asks to launch or set up an agent triad.

An agent triad has three roles:

1. **Supervisor** — the current agent, unless the user says otherwise.
2. **Worker** — an idle implementation agent available for later delegation.
3. **Reviewer** — an idle review agent available for later review requests.

The supervisor coordinates both agents. The worker and reviewer should not be told about each other and should not coordinate directly.

## Required dependency

Before supervising a triad, read and apply the `agent-supervision` skill. The only exception is the canonical `triad up` path: that CLI may perform mechanical launch/name-allocation/registration before the bootstrap read. Do not perform any other `superv` action until the `agent-supervision` bootstrap chain has been read in full.

Read the **agent-supervision** skill in full — its `SKILL.md` and the entire bootstrap chain that doc points to — then follow its bootstrap instructions for the relevant supervisor and launched-agent kinds.

Use the `agent-supervision` mechanisms for registering, observing, messaging, status classification, notes, and heartbeats.

## The `triad` CLI — canonical lifecycle mechanism

`scripts/triad` is the standard way to create, grow, inspect, pause/resume, and tear down a triad. It records a per-triad state file at `~/.triads/<repo>--<task-slug>/triad.json` (override the root with `TRIADS_DIR`) — written by `up`, appended by `add`, updated by `pause`/`resume`, and consumed by `down` — so teardown uses recorded windows, registrations, worktrees, and branches.

```bash
triad up     --repo R --task T [--base REF] [--worker-kind pi] [--reviewer-kind claude] [--pi-model M] [--claude-model M] [--dry-run] ...
triad add    <id>|--here --role ROLE --kind pi|claude|codex [--name N] [--pi-model M] [--claude-model M]   # role+kind REQUIRED, no defaults
triad pause  <id>|--here
triad resume <id>|--here
triad down   <id>|--here [--force] [--delete-remote] [--dry-run]
triad ls
triad status <id>|--here
```

- `up` creates/reuses the task worktree (per `start-worktree` path, branch-name, and remote-base conventions; it checks canonical-repo dirtiness and verifies reused worktrees are on the expected branch), launches the idle worker + reviewer in new tmux windows, registers them with `superv`, sends role-isolated idle prompts, and writes the state file. It writes status `creating` first and flips to `active` only after all requested agents launch.
- `add` launches one more idle agent into the same session + worktree and records it in state, so it is included in any future teardown. Role and kind must be explicit, and the triad must be `active` (resume a paused triad before adding).
- `pause` kills every agent's tmux window by the recorded tmux window id while preserving its persisted session (wraps `superv pause` per agent), marking the triad `paused` only if all agents pause successfully. Pausing mid-turn discards the in-flight turn, so operators typically pause at a quiet moment — the tool does not check or block. Worktree and branch are untouched; failed partial pauses are visible as `pause_failed`.
- `resume` re-launches every paused agent with its original session id and cwd (wraps `superv resume`), restoring full prior context, and marks the triad `active` only if all agents resume successfully. If the recorded tmux session is gone, it resumes into the current session and updates state. Re-orient resumed agents before delegating new work: state what elapsed, whether the last in-flight instruction is still valid, and restate the worktree path. Failed partial resumes are visible as `resume_failed`.
- `down` tears down **only the supervised agents recorded in state** (unregister `--purge` + kill the recorded window id), removes the worktree, deletes the local branch, optionally deletes the remote branch (`--delete-remote`), and archives state + a teardown log to `~/.triads/.archive/` only after destructive cleanup succeeds. It **refuses** if the worktree is dirty or the branch has unmerged commits (checks merge/ff ancestry, then fails closed unless `gh` finds exactly one merged PR whose `headRefOid` equals the current local branch tip) unless `--force`. It **never** kills the supervisor window or the tmux session — the operator closes the supervisor themselves (Ctrl-D).
- `--here` resolves the triad whose recorded tmux session matches the current one.

A failed teardown leaves the state directory in place with status `teardown_failed` and the log beside it, so `triad down <id>` can be re-run after fixing the cause. Successful teardown archives the state under `~/.triads/.archive/`; archives are inert and may be deleted when no longer useful. All operations are scoped to ids/paths recorded in state — the CLI never globs shared directories.

## Task slugging

`triad up` slugifies `--task` mechanically: lowercase it, replace every run of non-alphanumeric characters with `-`, then trim leading/trailing hyphens. For example, `refactor top-k query logic` becomes `refactor-top-k-query-logic`, not the shorter semantic slug `top-k-refactor`. If the user gives a long prose task but you want a short branch/worktree name, pass the chosen short slug as `--task` explicitly.

## Setup is not delegation

Launching a triad is setup only.

Do not give the worker a task to perform during triad setup.

Do not give the reviewer a review target during triad setup.

The launched agents should begin idle, waiting for future instructions from the supervisor. A one-line task description, setup label, repo name, or worktree name is not authorization to begin implementation, planning, inspection, or review.

The supervisor may delegate actual work later only when:

1. the task has been discussed enough to be clear;
2. the supervisor is ready to give concrete instructions;
3. the user has explicitly authorized starting work, or the user's request clearly asks for delegation now; and
4. the worker/reviewer prompt is specific enough to act on safely.

Do not delegate vague initial task blurbs.

## Default agent kinds

Unless the user says otherwise:

```text
Supervisor: current agent, often Claude
Worker:     Pi
Reviewer:   Claude
```

Claude is usually preferred for the supervisor role because it is strong at ongoing coordination and human-friendly status updates. Pi is now equally capable of scheduled/looping supervision (via its loop plugin), so the supervisor choice is no longer gated on who has scheduling primitives — pick by coordination style and report quality. The supervisor is not always Claude, so detect the actual current agent kind and follow `agent-supervision` accordingly.

### Pi model selection

A bare `pi` invocation inherits whatever model and reasoning level were last used interactively, which makes triad launches non-reproducible while you are experimenting. So `triad up`/`triad add` always launch pi-kind agents with an explicit `--model`. The default is `openai-codex/gpt-5.6-sol:xhigh`. Override it per-shell with the `TRIAD_PI_MODEL` env var, or per-invocation with the `--pi-model` flag. (Codex launches with its own explicit invocation; see the Claude section below for claude-kind model pinning.)

Known Pi models (each string encodes the model and the reasoning level):

| Ask | `--pi-model` value |
|---|---|
| GPT-5.6 Sol (default) | `openai-codex/gpt-5.6-sol:xhigh` |
| GPT-5.5 | `openai-codex/gpt-5.5:xhigh` |
| GLM 5.2 | `fireworks/accounts/fireworks/models/glm-5p2:xhigh` |
| GLM 5.2 Fast | `fireworks/accounts/fireworks/routers/glm-5p2-fast:medium` |

So if the user asks for a "GLM Pi worker", launch it with:

```bash
triad up --repo R --task T --pi-model fireworks/accounts/fireworks/models/glm-5p2:xhigh
# or, adding one to an existing triad:
triad add <id>|--here --role worker --kind pi --pi-model fireworks/accounts/fireworks/models/glm-5p2:xhigh
```

**Reasoning level on Fast models:** prefer `:medium` over `:xhigh`. The point of a fast router model is speed; `xhigh` reasoning defeats it. The `:xhigh` default is for the non-fast GPT/GLM models where reasoning depth is the value.

### Claude model selection

A bare `claude` invocation inherits whatever model the user's Claude config currently selects as the default. If someone flips the global default (e.g. to Opus) — in the config, or mid-session in another Claude TUI — every subsequent bare `claude` launch silently follows it, including triad-launched reviewer/worker agents. To make triad launches reproducible and immune to that, `triad up`/`triad add` always launch claude-kind agents with an explicit `--model`. The default is `fable`. Override it per-shell with the `TRIAD_CLAUDE_MODEL` env var, or per-invocation with the `--claude-model` flag. Pass `--claude-model ''` (empty string) to launch with no `--model` flag at all and inherit Claude's configured default.

So if the user asks for an Opus reviewer despite the Fable default:

```bash
triad up --repo R --task T --reviewer-kind claude --claude-model opus
# or, adding one to an existing triad:
triad add <id>|--here --role reviewer --kind claude --claude-model opus
```

## Tmux session model

All triad agents should run inside the same tmux session.

Typical setup:

1. The user starts or enters one tmux session.
2. The current agent is the supervisor in an existing tmux window.
3. The supervisor creates a new tmux window for the worker.
4. The supervisor creates a new tmux window for the reviewer.
5. Each new window is named after that agent's assigned first name.

Do not create a separate tmux session unless the user explicitly asks.

If not inside tmux, stop and ask the user how they want to proceed.

## Naming rules

Each launched agent gets a simple first name. The tmux window should be named exactly after that first name (lowercase).

`superv` owns the name pool and the registry is machine-global (not scoped to one tmux session). Multiple triads across different tmux sessions share the same namespace.

**Use `superv name` to allocate names.** It returns the next unused name from the built-in pool by checking the registry. Do not pick names manually or by inspecting tmux windows — that misses agents registered in other sessions.

```bash
name1=$(superv name)   # e.g. "alice"
# ... launch and register alice ...
name2=$(superv name)   # e.g. "bob" (alice is now taken)
# ... launch and register bob ...
```

The pool (in priority order): alice, bob, carol, dave, frank, grace, helen, iris, jack, kate, liam, mary, nina, owen, paul, rose, sam, tom, charlie, ed, bill, adam, mike, kyle, john, ivy, rachel, ronnie, allison, amy, andrew.

Do not use `Vera`; that name is reserved even though it is not in the current pool.

Before launching agents:

1. Call `superv name` to get the first available name.
2. Create tmux window with that name (lowercase).
3. Launch agent in the window.
4. `superv register <name> --kind <kind> --tmux <session>:<name>.0`
5. Repeat for the second agent.

`superv register` will reject the name if another supervisor registered it between your `superv name` call and your register call — in that case, kill the unregistered orphan window and call `superv name` again for the next available. The `triad` CLI does this retry/cleanup automatically.

## Isolation rule: do not introduce agents to each other

Do **not** tell the worker about the reviewer.

Do **not** tell the reviewer about the worker as a directly reachable peer.

Do **not** encourage either launched agent to load the `agent-supervision` skill, discover other agents, or send direct messages.

Rationale: if worker and reviewer know about each other, they may try to coordinate directly, load monitoring tools, or message each other. That creates confusion and can get out of hand. The supervisor is the only coordinator.

The supervisor may internally know both agents and route information between them, but each launched agent should receive a minimal role-specific setup prompt that frames the supervisor as their only point of contact.

## Initial worker setup prompt

The worker's initial prompt should set it up as idle capacity, not start work.

Tell the worker only:

- its assigned name;
- that it is an implementation worker for the supervisor;
- that it should wait for explicit instructions from the supervisor;
- that it must not inspect the repo, plan, edit files, run tests, or begin work until instructed;
- optionally, the worktree path it should be prepared to use later.

Do not include the task description unless the supervisor is intentionally delegating concrete implementation work now.

Do not mention the reviewer.

Do not mention the broader triad unless necessary; if necessary, only say that the current agent is supervising.

## Initial reviewer setup prompt

The reviewer's initial prompt should set it up as idle review capacity, not start review.

Tell the reviewer only:

- its assigned name;
- that it is a reviewer for the supervisor;
- that it should wait for an explicit review request from the supervisor;
- that it must not inspect the repo, read diffs, run tests, or begin reviewing until instructed;
- optionally, the worktree path it should be prepared to inspect later.

Do not include the task description or review target unless the supervisor is intentionally requesting concrete review now.

Do not mention the worker as another agent.

The reviewer should not take over implementation unless the supervisor explicitly asks.

## Supervising a triad

After the bootstrap read, supervise each recorded agent by id. A single supervisor loop may cover all active triad agents; heartbeat or nudge only the agents that actually have delegated work in flight. Reviewers that are merely idle capacity usually do not need heartbeats until a concrete review request is sent. Keep notes/cursors per agent id, following `agent-supervision`.

If adopting an existing triad after a supervisor restart, run `triad status <id>` or `triad status --here`, complete the full bootstrap read chain again, then read any per-agent notes under `~/.agent-supervision/notes/<name>.md` before sending messages.

## Later delegation

When the supervisor later delegates to the worker, the prompt should include a clear task, relevant context, constraints, expected output, and reporting instructions.

When the supervisor later asks the reviewer to review, the prompt should include a concrete review target, such as a diff, branch, PR, files, or worktree state, plus review criteria and reporting instructions.

## Launch procedure

When asked to launch a triad, use the CLI — it performs the entire mechanical sequence (worktree, name allocation, windows, launch, registration, idle prompts, state file):

```bash
triad up --repo <name> --task "<prose or slug>"
```

Then read `agent-supervision/SKILL.md` and the dependency docs it points to (mandatory before any supervision action beyond this CLI-mediated setup), and report that the triad is ready and waiting for delegation.

The manual sequence below is what `triad up` does internally — fall back to it only if the CLI is unavailable or a step needs manual repair:

1. Confirm the current process is inside a tmux session; determine the session name.
2. Inspect current tmux windows and registered agents.
3. Allocate unused first names via `superv name` (registering each agent before allocating the next).
4. Launch the worker in a new tmux window in the same session.
5. Launch the reviewer in a new tmux window in the same session.
6. Register both agents through `agent-supervision`.
7. Send each agent only its idle setup prompt, following the isolation rule.
8. Record everything in `~/.triads/<id>/triad.json` so teardown can run from state.

## Operating principle

```text
Supervisor coordinates.
Worker waits until delegated, then implements.
Reviewer waits until requested, then evaluates.
Worker and reviewer do not coordinate directly.
Setup is not execution.
```
