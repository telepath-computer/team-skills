---
name: herdr-protocol-alpha
description: "Run the default setup workflow inside herdr: confirm a repo and task, dispatch an idle triad (supervisor + idle worker + idle reviewer) into a herdr workspace with `supervisr`, read the supervision skills, then wait for explicit delegation before any implementation or review. The herdr-native counterpart to tmux-protocol-alpha. Use when the user asks for the default task-setup workflow and the agents run inside herdr."
---

# Herdr Protocol Alpha

**Depends on:** herdr-agent-supervisor, herdr-agent-triad.

Use this skill when the user asks for the herdr default setup workflow, or for "protocol alpha" while running inside herdr (`HERDR_ENV=1`). For the tmux/`superv` version, use `tmux-protocol-alpha`.

Herdr Protocol Alpha is **setup-only**. It prepares the workspace and an idle triad, then stops and waits for explicit instructions before any implementation, planning, repo inspection, or review begins.

The mechanical setup is two `supervisr dispatch` calls (owned by the `herdr-agent-triad` skill). Your job is to give them the right inputs, then prepare yourself to supervise. Concretely:

1. Confirm the **repo** and **task** (both required).
2. **Dispatch the idle triad** into your workspace, with an isolated checkout per `supervisr dispatch --worktree` when the task wants one.
3. **Read the supervision skills in full** (your job — the tooling cannot do it for you).
4. Confirm the ready state and **wait** for the user to delegate.

Protocol Alpha does **not** start the actual work.

---

## Step 1 — Confirm the required inputs

Do not dispatch until both are known:

1. **Repo** — the canonical repository to work from.
2. **Task** — the task label, description, or slug (used to name the branch/worktree and to frame the idle prompts — it is a naming hint, **not** authorization to act).

If either is missing or ambiguous, **stop and ask the user** (see [Stop conditions](#stop-conditions)).

You must also be inside herdr, in the workspace that will hold the triad. If `HERDR_ENV` is not set, stop — this is the tmux case; use `tmux-protocol-alpha`.

---

## Step 2 — Dispatch the idle triad

Dispatch a worker and a reviewer into your workspace, **idle** (idle setup prompts only, per `herdr-agent-triad`). When the task wants an isolated checkout, let `dispatch` create the worktree:

```bash
supervisr dispatch worker   --kind pi     --worktree thopter/<task-slug> --prompt "<worker idle prompt>"
supervisr dispatch reviewer --kind claude                                 --prompt "<reviewer idle prompt>"
```

`dispatch` creates/opens the worktree (`git worktree add` under `<repo>/../wt/<repo>/<slug>`), opens a tab for the agent, starts it with the deliberate defaults, waits for herdr to mark it interactive-ready (pass `--trust-folder` to accept the first-run trust dialog), sends the idle prompt, and reports the session id. The `herdr-agent-triad` skill is authoritative for the flags, defaults, naming rules, and the exact idle-prompt contents; follow it — you read it in full in Step 3.

Slugify the task the same way throughout (lowercase, non-alphanumeric runs → `-`, trim). If you want a short branch name from a long prose task, choose the slug explicitly.

---

## Step 3 — Read the supervision skills in full (your job, not the tooling's)

Dispatching sets the stage. It does **not** make you competent to supervise. Before any supervision action — `supervisr sweep`/`status`, delegation, nudges, notes, heartbeats — you must have read each of these, and every downstream file each one points to, **in full, end to end. NO SKIMMING.**

```text
the herdr-agent-supervisor skill   (and, via its Required-reading block: the herdr skill, and herdr-agent-supervisor/core.md for the supervisor stance)
the herdr-agent-triad skill
```

**Invoke `herdr-agent-supervisor` via the Skill tool** — do not merely Read it. Invoked skills are re-injected in full after a context compaction; plain Read-tool content is compressed into a lossy summary. A compaction of your own context invalidates all prior downstream reads: when the re-injected `herdr-agent-supervisor/SKILL.md` reappears, treat it as the trigger to re-run the full read chain before any further supervisory action.

You can do this reading while the idle triad sits waiting; the triad does nothing until you delegate, so use the window to prepare.

### Verification gate before you supervise or delegate

Before you inspect status, send the worker a task, send the reviewer a review request, nudge, or arm a heartbeat, you must honestly answer **yes** to all of:

1. Did I invoke `herdr-agent-supervisor` via the Skill tool, and read every file its Required-reading block names (the `herdr` skill and `herdr-agent-supervisor/core.md`), end to end — and redone both since my last compaction, if any?
2. Did I read `herdr-agent-triad/SKILL.md` end to end?

If any answer is no — or "I read part of it," or "I'll come back to it" — **STOP** and read it in full. The tools ingest these in seconds; there is no efficiency argument for skipping, and the cost of skipping lands on the user.

---

## Step 4 — Confirm ready state and wait

1. Confirm the setup — repo, worktree path(s), branch, workspace, agent names, and reported session ids (`supervisr sweep`).
2. Relay that ready state to the user.
3. **Wait** for explicit user instructions before delegating any work.

---

## Setup-only rule

The task in a Protocol Alpha request is setup context only — used to name the slug, branch, worktree, and a human-readable label. It is **not** permission to tell the worker to implement or the reviewer to inspect. Do not ask the worker to plan, inspect the repo, edit, or run tests; do not ask the reviewer to inspect, read diffs, or review. After setup, stop and wait unless the user explicitly says to begin or delegate.

---

## Stop conditions

Stop and ask the user before proceeding if:

- the repo is unknown, or cannot be found;
- the task is unknown;
- you are not inside herdr (`HERDR_ENV` unset) — this is the tmux case;
- the canonical repo has unsafe state (unexpected uncommitted changes) and `--worktree` would branch from it;
- a triad for this task already exists in the workspace and it is unclear whether to reuse or tear it down;
- the user appears to expect implementation or review but the task is still vague.

The judgment calls — a vague task, an ambiguous reuse, a user who seems to expect work to start — are yours.

---

## Later delegation and teardown

Actual work starts only after a separate explicit instruction to begin or delegate. When authorized, the supervisor sends concrete task instructions to the worker and concrete review requests to the reviewer. Delegation style — what a dispatch or review request contains and, more importantly, what it must leave to the agent — is owned by `herdr-agent-supervisor` (core.md: "State the condition, not the answer" and "Delegate the judgment, not just the lookup"); this skill adds nothing to it.

Teardown is `supervisr stop <name> --close-pane` per agent, plus `git worktree remove` for any checkout `dispatch` created. herdr persistence means stepping away is just detaching herdr; the agents keep running and a restart resumes them — there is no pause/resume CLI. Teardown never closes the supervisor; the user does that.

## Operating principle

```text
Herdr Protocol Alpha = repo + task -> [supervisr dispatch: worktree + idle worker + idle reviewer] + [you: read skills] -> ready state
Setup is not execution.
A task name authorizes naming, not implementation.
The tools set the stage; you must still read the skills before you supervise.
```
