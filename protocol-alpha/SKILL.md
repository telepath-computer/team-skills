---
name: protocol-alpha
description: "Run the default setup workflow: confirm a repo and task, run `triad up` to create the task worktree and launch an idle triad with a recorded state file, read the supervision skills, then wait for explicit delegation before any implementation or review."
---

# Protocol Alpha

**Depends on:** agent-supervision, start-worktree, agent-triad.

Use this skill when the user asks for `protocol-alpha`, "Protocol Alpha", or the default initial workflow for setting up a task.

Protocol Alpha is **setup-only**. It prepares the workspace and agent structure, then stops and waits for explicit instructions before any implementation, planning, repo inspection, or review begins.

The mechanical setup is done by the `triad` CLI (owned by the `agent-triad` skill). Your job is to give it the right inputs, then prepare yourself to supervise. Concretely:

1. Confirm the **repo** and **task** (Protocol Alpha needs both).
2. **Run `triad up`.** It creates/reuses the worktree, launches the idle agents, and records a state file that later powers one-command teardown.
3. **Read the supervision skills in full** (this is your job — the CLI does not and cannot do it for you).
4. Confirm the ready state and **wait** for the user to delegate.

Protocol Alpha does **not** start the actual work.

---

## Step 1 — Confirm the required inputs

Do not run `triad up` until both are known:

1. **Repo** — the canonical repository to work from.
2. **Task** — the task label, task description, or task slug.

The task is required so the CLI can derive the task slug, worktree path, and branch name. The task supplied when invoking Protocol Alpha is a **naming hint** for the feature branch/worktree, not a complete task specification ready to be acted on. Knowing the task does not authorize implementation or review. The CLI slugifies mechanically: `refactor top-k query logic` becomes `refactor-top-k-query-logic`. If you want a shorter semantic slug such as `top-k-refactor`, pass that slug as `--task`.

If either input is missing or ambiguous, **stop and ask the user**. See [Stop conditions](#stop-conditions).

Examples of sufficient setup information:

```text
repo: carryall
task: refactor top-k query logic
```

```text
repo: ~/workspace/carryall
task: top-k-refactor
```

A repo name given without a path is resolved under the parent repos directory (default `~/workspace`). If the user gives a path such as `~/workspace/carryall`, split it for the CLI: `--parent ~/workspace --repo carryall`.

---

## Step 2 — Run `triad up`

This is the canonical way to perform Protocol Alpha setup. Run it inside tmux. The current directory does not affect repo resolution; pass `--parent` if the parent repos directory is not `~/workspace`:

```bash
triad up --repo <name> --task "<prose or slug>"
```

Common options (the **agent-triad** skill is authoritative for the full flag set and exact behavior):

| Option | Purpose |
|---|---|
| `--base REF` | Base the new branch on a specific ref instead of `origin/<default>` (e.g. a branch, tag, or commit the user named). |
| `--parent DIR` | Parent repos directory (default `~/workspace`). |
| `--session NAME` | tmux session to launch into (default: the current session); use only when the user explicitly asks for a different session. |
| `--worker-kind` / `--reviewer-kind` | Override the default `pi` worker / `claude` reviewer. |
| `--no-worker` / `--no-reviewer` | Skip launching one role; then Step 3 still reads the relevant docs for the agent kinds that actually launched, and Step 4 reports the skipped role clearly. |
| `--allow-dirty` | Proceed even if the canonical repo has uncommitted changes (default: abort). |
| `--dry-run` | Print the plan without making changes. |

`triad up` enforces several [stop conditions](#stop-conditions) itself (missing inputs, not in tmux, repo not found, dirty repo, existing state for this id, reused worktree on the wrong branch) and exits with a clear error rather than proceeding. Hard failures abort; readiness-marker timeouts warn and continue, so inspect the named window if you see such a warning. If it errors, fix the cause or surface it to the user — do not work around it by doing the setup by hand unless the user asks.

For the exact mechanical steps `triad up` performs — so you can verify its output and explain it — see the **agent-triad** skill, which owns the `triad` CLI. You read it in full in Step 3, so you already have those details.

---

## Step 3 — Read the supervision skills in full (your job, not the CLI's)

The CLI sets the stage. It does **not** make you competent to supervise. `triad up` is the one permitted CLI-mediated launch/registration carve-out before this read. Before any other supervision action — including `triad status`, `superv status`, delegation, nudges, notes, or heartbeats — you must have read each of these skills, and every downstream file each one tells you to read, **in full, end to end. NO SKIMMING. NO "I'LL CHECK THE REST LATER."**

```text
the agent-supervision skill
the start-worktree skill
the agent-triad skill
```

Each entry is the entry point to a skill, not the whole skill. Each skill's own `SKILL.md` is authoritative about which downstream files form the rest of that skill — **follow those instructions exactly**. If `agent-supervision/SKILL.md` says read X, Y, Z — read X, Y, Z, in full.

**For `agent-supervision` specifically: INVOKE it via the Skill tool** (`Skill(skill: "agent-supervision")`) — do not merely Read the file. Invoked skills are tracked by the harness and re-injected in full after a context compaction; plain Read-tool content is not, it gets compressed into lossy summary. Then read every downstream file its `SKILL.md` mandates, end to end, exactly as before — invocation loads only the index, not the chain. **A compaction of your own context invalidates all prior downstream reads**: when the re-injected `agent-supervision/SKILL.md` appears after a compaction, treat it as the trigger to re-run the full bootstrap read chain before any further supervisory action.

You can do this reading while the idle triad sits waiting; there is no rush that justifies skipping it. The triad does nothing until you delegate, so use this window to prepare.

### Why this is non-negotiable

The model running this skill (you) has a documented tendency to treat skill-loading as a checkbox to clear before getting to the "real work." This is wrong. The skill-loading **is** the work. Concretely: a recent Protocol Alpha invocation skipped one of the agent-supervision downstream files — the supervisor-pacing doc — and the result was that the worker sat idle for 90 minutes waiting on the supervisor, who had no idea how to pace check-ins. The user, who had written that doc carefully and comprehensively to prevent exactly that failure, was rightly angry.

Every file in every skill exists because the skill author put it there to catch a specific failure mode. Skipping any of them is not an efficiency win — it is a guaranteed downstream failure whose cost lands on the user.

### Verification gate before you supervise or delegate

Before you inspect status, send the worker a task, send the reviewer a review request, send a nudge, or arm a heartbeat, you must be able to honestly answer **yes** to all of:

1. Did I invoke the `agent-supervision` skill via the Skill tool, and then read every file its `SKILL.md` told me to read, end to end — and re-done both since my last compaction, if any?
2. Did I read `start-worktree/SKILL.md` end to end, and then read every file that doc told me to read, end to end?
3. Did I read `agent-triad/SKILL.md` end to end, and then read every file that doc told me to read, end to end?

If the answer to any of these is no — or "I read part of it," or "I read the relevant sections," or "I'll come back to it" — **STOP**. Go read the file in full. Do not delegate or supervise until every answer is an honest yes.

The Read tool can ingest these files in seconds. There is no efficiency argument for skipping them. Skipping is pure carelessness, and the cost lands on the user, not on you.

---

## Step 4 — Confirm ready state and wait

After `triad up` reports success:

1. Confirm the CLI's report — repo, worktree path, branch, tmux session, agent names, state-file path, and any readiness warnings. After the Step 3 read gate, use `triad status <id>` or `triad status --here` if you need to verify live registration/status.
2. Relay that ready state to the user.
3. **Wait** for explicit user instructions before delegating any work.

---

## Setup-only rule

A one-line task description in a Protocol Alpha request is setup context only. It is used for naming:

- task slug
- branch name
- worktree path
- human-readable setup label

It is **not** permission to tell the worker to implement anything. It is **not** permission to tell the reviewer to inspect or review anything.

Do not ask the worker to plan, inspect the repository, edit files, run tests, or start work. Do not ask the reviewer to inspect the repository, read diffs, run tests, or start review.

After setup, stop and wait unless the user explicitly says to begin or delegate the task.

---

## Stop conditions

Stop and ask the user (or let `triad up` abort) before proceeding if:

- the repo is unknown
- the task is unknown
- the operator/supervisor session's current directory violates the `start-worktree` starting-directory rule and the user has not confirmed continuing; task agents launched by `triad up` deliberately start inside their task worktree and are exempt
- the canonical repo cannot be found
- the canonical repo has unsafe state, such as unexpected uncommitted changes
- the process is not inside tmux and the user has not approved an alternative
- the branch/worktree already exists and it is unclear whether to reuse it
- an active, paused, creating, failed, or otherwise existing triad state is already recorded for this repo+task and it is unclear whether to resume, reuse, or tear it down
- the user appears to expect implementation or review but the actual task is still vague

`triad up` enforces the mechanical subset of these by aborting. The judgment calls — a vague task, an ambiguous reuse, a user who seems to expect work to start — remain yours.

---

## Later delegation, growth, and teardown

Actual work starts only after a separate explicit instruction to begin or delegate.

When the user later authorizes work, the supervisor sends concrete task instructions to the worker and concrete review requests to the reviewer. Each delegation prompt should include a clear task/target, relevant context, constraints, expected output, and reporting instructions — per `agent-supervision`.

The triad lifecycle beyond setup — adding capacity (`triad add`), stepping away and returning (`triad pause` / `triad resume`), and cleanup after merge (`triad down`) — is driven by the `triad` CLI. The **agent-triad** skill is authoritative for how each command behaves, its guards, and its flags; consult it when you reach those steps. Two workflow points worth restating here, because they are the supervisor's judgment rather than the CLI's: re-orient resumed agents before any new delegation (what elapsed, whether the last instruction still holds, the worktree path), and remember that teardown **never** closes the supervisor — the user does that themselves (Ctrl-D).

---

## What `triad up` does

The exact mechanical steps `triad up` performs — inputs and guards, worktree creation and reuse, the state file it writes, the idle worker/reviewer launch with role-isolated prompts, and what it deliberately does *not* do (read the skills for you, delegate the task, or arm a heartbeat) — are documented in the **agent-triad** skill, which owns the `triad` CLI. That skill is authoritative; Protocol Alpha does not duplicate it. You read agent-triad in full in Step 3, so you already have those details when you need to verify `triad up`'s output, explain it, or reproduce a step by hand.

---

## Failure recovery and adoption

If `triad up` fails partway, it leaves status `create_failed` and kills any unregistered orphan window it created during the failed launch. Standard recovery is: fix the cause, run `triad down <id>`, then re-run `triad up` (the worktree/branch are cheap to reuse if present). Do not run implementation/review work from a failed setup state.

If a new supervisor adopts an existing triad, first identify it with `triad ls` / `triad status <id>` after completing the Step 3 read gate, then read any per-agent notes under `~/.agent-supervision/notes/<name>.md` before sending messages.

## Operating principle

```text
Protocol Alpha = repo + task label -> [triad up: worktree + idle agents + state file] + [you: read skills] -> ready state
Setup is not execution.
A task name authorizes naming, not implementation.
The CLI sets the stage; you must still read the skills before you supervise.
Teardown is one command (triad down) — but the supervisor's lifecycle belongs to the user.
```
