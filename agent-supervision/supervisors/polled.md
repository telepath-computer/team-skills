# Supervisor — Polled (Codex, OpenCode, or Pi without the `pi-loop` plugin)

You do not have native scheduling available. Use blocking `sleep N && cat <file>` as your timer. The bash call blocks tool execution; when it fires, the file's contents arrive as tool output — read them and act.

This file covers three cases: Codex and OpenCode (which have no scheduling primitive at all), and Pi without the `pi-loop` plugin installed (which has one available, just not installed yet — install it with `pi install npm:@koltmcbride/pi-loop` if you want the scheduled path in `supervisors/scheduled.md` instead).

## The global heartbeat instruction file

The polled heartbeat is the supervisor's global self-nudge, semantically identical to the scheduled loop. It remains alive across workers, reviews, tasks, slices, phases, and handoffs. A worker ID in the current `superv heartbeat <id>` storage path is only a mechanical anchor for the timer file; it does not scope the supervisor heartbeat to that worker.

The prompt file lives at `~/.agent-supervision/heartbeats/<id>.md` and contains only the canonical supervisor-heartbeat prompt from `core.md`, verbatim. Preserve that generic message rather than rewriting it around the anchor worker or current task. Timer and anchor metadata live separately in `<id>.state.json`, so `sleep N && cat <prompt-file>` injects no mechanical or task-specific content.

`superv heartbeat <id> --bump` rewrites this file with the next backoff value and prints the suggested `sleep N && cat <path>` command. You run the printed command.

## Adaptive backoff schedule

- Start: **30s** for the first heartbeat after kickoff or correction.
- Increase by **30s per cycle**.
- Cap at **240s** (4 minutes).
- Reset to 30s after sending a nudge or correction (so you verify it landed quickly).
- Do **not** use hyperactive intervals like 2–10 seconds for normal supervision.

`superv heartbeat <id> --bump` handles the schedule automatically.

## Six-step heartbeat workflow

On each wake-up, do these in order:

1. **Reassess globally** — use conversation context and durable supervision state to identify what currently needs attention.
2. **Observe relevant workers** — for each relevant worker, read persisted deltas with `superv watch <id>`, use `--live` when needed, and classify with `superv status <id>`.
3. **Interpret** — distinguish running, idle, stalled, broken, needs-correction, and worker-complete states. Worker completion is not supervisor completion.
4. **Verify claims read-only** — `git status`, `git log`, file reads. Never mutate the worker's repo.
5. **Act intelligently** — wait, nudge, correct, dispatch, review, transition, escalate, or conclude according to the overall goal. A heartbeat fire does not require sending a worker message. Use `superv note` for significant decisions, blockers, corrections, approvals, completions/handoffs, transitions, context-management events, and interventions—not routine cycle status.
6. **Re-arm unless supervision-level teardown applies** — `superv heartbeat <anchor-id> --bump` and run the printed `sleep && cat` command.

## State classifications

`superv status` produces the four mechanical verdicts. The other two require agent judgment after reading recent persisted entries.

**Mechanical (from `superv status`):**

- **RUNNING** — transcript turn-state is `busy`.
- **IDLE** — transcript turn-state is `idle` and persisted age is under 10min. Probably waiting; might be done.
- **STALLED** — transcript turn-state is `idle` and persisted age is over 10min. Investigate.
- **BROKEN** — transcript turn-state is `unknown` or live channel is unreachable (tmux pane gone, http error). Don't try to nudge.

**Agent judgment (after `superv watch` + interpretation):**

- **NEEDS_CORRECTION** — worker is making progress but in a wrong direction. Detect by reading recent entries and matching against the anti-pattern catalog (timeout inflation, "known issue" papering, step-skipping, etc.).
- **WORKER_COMPLETE** — the worker's current assignment is met, validations have actually run, and no blocker remains within that assignment. Verify claims read-only (`git status`, test runs, file inspection), stop nudging completed work, and reassess what the supervisor should do next. This state does not tear down the global heartbeat.

## Heartbeat reply: what to write at the end of each cycle

After each heartbeat, end your turn with a **one- to two-sentence reply** that does two things:

1. Describe what progressed across the relevant supervision cycle and your next action.
2. **Explicitly state whether you are re-arming the global heartbeat or stopping it**, and which command you ran to do so.

This is not a tool call, not a file write — it's just your text response, which serves three readers:

- **The user** glances at recent replies to see what's happening without reading the worker's transcript.
- **You on the next cycle** see your prior replies in context, so you can tell whether the worker has been idle for one cycle or several, and whether you've already nudged.
- **You on this cycle**, while writing the line, are forced to confirm out loud whether you re-armed. This is the discipline that catches the most common polled-supervisor failure: forgetting to schedule the next `sleep && cat`.

Good examples (note the re-arm clause at the end of each):

> Worker is mid-test-run on slice 1.4; transcript turn-state is busy and recent commits look correct. Re-arming with sleep 90 && cat <hb>.

> Worker has been idle 3 cycles since the last commit and never ran the tests it said it would. Sent a nudge; re-arming with sleep 30 && cat <hb> to verify it lands.

> Worker reported its assignment complete and the tree is clean with 12/12 tests passing. Stopped nudging that worker, dispatched the required review, and re-armed the global heartbeat with sleep 30 && cat <hb>.

> Worker increased the test timeout from 30s to 120s instead of investigating the hang — timeout-inflation anti-pattern. Sent a correction to revert and add diagnostic logging; re-arming with sleep 30 && cat <hb>.

The polled supervisor's single biggest failure mode is forgetting the re-arm. Forcing every reply to say "re-arming with X" or "not re-arming because Y" makes the omission impossible to do silently. If you find yourself writing a reply and realize you have nothing to put in the re-arm clause — that's the moment you would have forgotten. Run the command now, then write the clause.

For durable observations beyond the running pulse — significant decisions, interventions, blockers — use `superv note <id> "..." --tag supervisor`. That writes to disk and survives compaction, conversation reset, or supervisor handoff. Reach for it when something would be useful in a post-mortem, not for routine cycle-by-cycle status.

## Verification: subagent mechanism

The general verification ladder lives in `core.md`. Rung 2 (spawn a subagent) requires using whatever subagent capability your supervisor environment provides. The exact tool name, syntax, and isolation behavior differ per agent — and they evolve, so check your environment's current documentation rather than trusting a snapshot here.

What you need to know about your environment before using Rung 2:

1. **What's the subagent invocation?** A built-in tool, an MCP tool, or a shell command (e.g., spawning another instance of the same agent)?
2. **Does it support isolation?** Specifically, does it run the subagent against a clean checkout of a committed git ref so it cannot touch the worker's working tree? Some agents have a built-in flag for this; some require manual `git worktree add` + a `--cd <worktree>` flag on the subagent invocation.
3. **What does the subagent inherit from your environment?** Env vars, cwd, network access, sandboxing — these affect the side-effect risk per core.md's Class A/B/C taxonomy.

Specifics to check (treat as starting points, not authoritative):

- **Codex** has subagent capability built in; check `codex --help` and the Codex docs for the current invocation, and confirm whether isolation is built-in or needs to be assembled with `git worktree add` + `codex exec --cd`.
- **OpenCode** supports subagents through its agent-mode features; check OpenCode docs for the current syntax and isolation story.

Pi *with* the `pi-loop` plugin installed is a scheduled supervisor — see `supervisors/scheduled.md`. A Pi without the plugin has no scheduling primitive available and stays here; the rest of this file applies. (Install the plugin with `pi install npm:@koltmcbride/pi-loop` if you'd rather take the scheduled path.)

If your environment's subagent does not provide isolation and you can't easily wrap it with a manual worktree, **prefer Rung 1 (ask the worker)** for verification. Rung 3 (worker checkpoints, then subagent against the new HEAD) is a strong fallback when Rung 1 isn't appropriate.

If you're not sure what your environment's subagent does, find out before using Rung 2 — don't guess. The cost of a few minutes reading docs is far less than the cost of a research subagent silently mutating the worker's tree.

## Supervisor-heartbeat teardown

Do not tear down when a worker, task, review, slice, or phase completes, or merely because all current workers are idle. Stop nudging completed workers and continue supervising the overall assignment.

Tear down only when the supervisor's overall assignment is definitively complete, progress definitively requires user input, or the user explicitly says to stop:

1. `superv heartbeat <anchor-id> --teardown` — removes the instruction file.
2. Stop running `sleep && cat`. Without a re-arm, the loop ends naturally.
3. Record the overall outcome or user-input blocker when useful.

## Why this works

- **Durable + live** — combines saved session history with current state.
- **No keystroke collision** — nothing is typed into the supervisor's own pane.
- **Instructions are an artifact** — editable and inspectable; you don't have to remember them.
- **Self-sustaining** — the file tells you to schedule the next loop.
- **Interruptible** — the user can break the `sleep` (Ctrl+C / Escape) and take over anytime.
