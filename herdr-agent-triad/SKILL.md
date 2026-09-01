---
name: herdr-agent-triad
description: "Launch a three-agent triad inside herdr with the current agent as supervisor, a Pi worker by default, and a Claude reviewer by default; worker and reviewer start idle and receive task instructions only after explicit supervisor delegation. The herdr-native counterpart to tmux-agent-triad — workers are herdr agents dispatched with `supervisr`, not tmux windows. Use when the user asks to launch a triad and the agents run inside herdr."
---

# Herdr Agent Triad

**Depends on:** herdr-agent-supervisor (self-contained — it carries its own `core.md` stance and requires the `herdr` skill).

Use this skill when the user asks to launch an agent triad and you are running inside herdr (`HERDR_ENV=1`). For a triad in bare tmux panes without herdr, use `tmux-agent-triad` instead.

An agent triad has three roles:

1. **Supervisor** — the current agent, unless the user says otherwise.
2. **Worker** — an idle implementation agent available for later delegation.
3. **Reviewer** — an idle review agent available for later review requests.

The supervisor coordinates both. The worker and reviewer are not told about each other and do not coordinate directly.

## Required dependency

Before supervising a triad, **read and apply the `herdr-agent-supervisor` skill in full** — its `SKILL.md` and everything its "Required reading" block points to (the `herdr` skill, and this skill's own `core.md`). Everything below assumes you know the `supervisr` command set and the supervisor discipline. Do not dispatch, send, or supervise until that read is done.

## What is different from tmux-agent-triad

There is **no `triad` CLI here**, and there is nothing to install. herdr already owns the machinery that the tmux `triad` script had to build: panes, windows, persistence across detach/restart, name registration, and lifecycle. The triad is just:

- **one herdr workspace** = the task (the supervisor's own workspace);
- the worker and reviewer each get **their own tab** in it, started with `supervisr dispatch`;
- herdr persists them, so there is no pause/resume dance — detaching and reattaching herdr is enough, and a server restart resumes the agents.

So "launch a triad" is two `supervisr dispatch` calls plus the idle-prompt discipline below.

## Launch

Run from inside the workspace that will hold the triad (your supervisor pane's workspace). Dispatch each agent **idle** — with an idle setup prompt, not a task:

```bash
# Worker: Pi by default. --prompt carries only the idle setup framing (see below).
supervisr dispatch worker --kind pi --prompt "<worker idle prompt>"

# Reviewer: Claude by default.
supervisr dispatch reviewer --kind claude --prompt "<reviewer idle prompt>"
```

`supervisr dispatch` opens a new tab in your workspace (named after the agent), starts the agent with the deliberate launch defaults (model, `xhigh` effort, permissions bypassed — see the herdr-agent-supervisor skill), stamps an ownership token, waits for herdr to mark the pane interactive-ready (clearing a folder-trust dialog with `--trust-folder`), sends the idle prompt, and reports the session id. After both, `supervisr sweep` shows the triad.

**Names.** herdr agent names are unique across the whole herdr session, not per workspace. `worker`/`reviewer` are fine for a single triad; if you run more than one triad in a session, name by task (`auth-worker`, `auth-reviewer`). Pick the names yourself and pass them to `dispatch`.

**Worktrees.** If the task wants an isolated checkout, add `--worktree <branch>` to `dispatch` (it runs `git worktree add` under `<repo>/../wt/<repo>/<branch>` by default). Several worktrees for one task are just several dispatched panes with different `--worktree`/`--cwd` — all in the one workspace. This is the herdr-native alternative to `herdr-start-worktree` + tmux windows.

**Placement.** Each dispatched agent gets its own tab by default, labelled with the agent name — a supervisor watching several agents wants to switch between full-height views, not shrink its own pane. Override with `--new-tab <label>` to name the tab, `--split right|down` to split the current pane instead, or `--pane <id>` to use an existing idle shell pane.

**Model / effort overrides.** Same flags as `dispatch`: `--model`, `--effort`. Defaults: Pi `openai-codex/gpt-5.6-sol:xhigh`, Claude `claude-fable-5`, effort `xhigh`.

## Setup is not delegation

Launching a triad is setup only. Dispatch the worker and reviewer **idle**.

- Do not give the worker a task to perform during setup.
- Do not give the reviewer a review target during setup.
- A one-line task blurb, worktree name, or repo name is **not** authorization to begin implementation, planning, inspection, or review.

The supervisor delegates real work later only when: the task is clear; the supervisor is ready with concrete instructions; the user has explicitly authorized starting work (or clearly asked for delegation now); and the prompt states the outcome, where the work lives, and the outside constraints clearly enough to act on — delegation style is owned by `herdr-agent-supervisor` (core.md, "Delegate the judgment, not just the lookup"); a brief is not a specification.

## Isolation rule: do not introduce the agents to each other

- Do **not** tell the worker about the reviewer.
- Do **not** tell the reviewer about the worker as a reachable peer.
- Do **not** encourage either launched agent to load a supervision skill, discover other agents, or message anyone. A worker or reviewer that starts driving its own review loop is a supervision leak — the supervisor is the only coordinator (see the "delegating supervision to a worker" anti-pattern in `herdr-agent-supervisor/core.md`).

The supervisor knows both agents and routes information between them. Each launched agent gets a minimal role-specific idle prompt framing the supervisor as its only point of contact.

## Initial worker idle prompt

Tell the worker only:

- its assigned name;
- that it is an implementation worker for the supervisor;
- that it should wait for explicit instructions from the supervisor;
- that it must not inspect the repo, plan, edit files, run tests, or begin work until instructed;
- optionally, the worktree path it should be prepared to use later.

Do not include the task description unless intentionally delegating now. Do not mention the reviewer.

## Initial reviewer idle prompt

Tell the reviewer only:

- its assigned name;
- that it is a reviewer for the supervisor;
- that it should wait for an explicit review request from the supervisor;
- that it must not inspect the repo, read diffs, run tests, or begin reviewing until instructed;
- optionally, the worktree path it should be prepared to inspect later.

Do not include the task or review target unless intentionally requesting review now. Do not mention the worker. The reviewer does not take over implementation unless the supervisor explicitly asks.

## Default roles and kinds

Unless the user says otherwise: supervisor = current agent (often Claude); worker = Pi; reviewer = Claude. Claude is usually preferred for the supervisor role for coordination quality and human-friendly status updates; Pi is equally capable of scheduled supervision. Detect the actual current agent kind and follow the supervisor skill accordingly.

## Supervising the triad

One supervisor loop covers both agents. Route with `supervisr sweep`, read deltas with `supervisr watch`, nudge with `supervisr send`. Heartbeat or nudge only the agents that actually have delegated work in flight — a reviewer sitting as idle capacity usually needs no heartbeat until a concrete review request goes out. Keep per-agent notes with `supervisr note`. Everything about pacing, verification, blocked handling, and heartbeat lifecycle is in the herdr-agent-supervisor skill (its `core.md`).

## Teardown

- To end one agent: `supervisr stop <name> --close-pane` (keeps its cursor/notes; `supervisr forget <name>` drops them).
- Worktree cleanup, if you used `--worktree`, is `git worktree remove` — herdr does not delete checkouts.
- herdr persistence means "stepping away" is just detaching herdr (`ctrl+a q` if you rebound the prefix, else `ctrl+b q`); the agents keep running and a server restart resumes them. There is no pause/resume CLI to run.

## Operating principle

```text
Supervisor coordinates.
Worker waits until delegated, then implements.
Reviewer waits until requested, then evaluates.
Worker and reviewer do not coordinate directly.
Setup is not execution.
One workspace = one triad; dispatch is idle until the supervisor delegates.
```
