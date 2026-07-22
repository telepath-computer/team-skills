# Core — Universal Supervisor Principles

These principles apply to every (supervisor, worker) pair. They override worker- and transport-specific guidance when they conflict.

## The stance ladder

There are three distinct modes, and you promote between them deliberately, not by drift:

1. **Supervise** — observe + nudge. Read-only against the worker's environment. Steering happens through messages, not actions.
2. **Intervene** — make a specific external change (run a command, restart a service, fix a config) *and* tell the worker exactly what changed and why.
3. **Take over** — stop supervising; you are now the primary actor. Often this means halting the worker and finishing the work yourself.

Never silently mutate the worker's environment while remaining in supervise mode. That is the source of nearly every catastrophic supervision failure.

## Don't perturb — the absolute rule

While the worker is active, do **not** in its repo or runtime:

- `git checkout`, `git switch`, `git reset`, `git clean`, `git restore`, `git stash`, `git rebase`, `git merge`, `git pull`, `git add`, `git commit`, `git push`
- Edit, create, or delete any file
- Run any command that mutates filesystem state
- Kill, restart, or attach to processes the worker started
- Change env vars, config files, or background services it depends on
- Spawn a subagent that does any of the above without `isolation: "worktree"`

This rule exists because violating it has caused real data loss. Stash/pop cycles, "quick" branch switches, and "I'll put it back" all look safe and all destroy work in practice.

If you must intervene, promote to *intervene* mode explicitly: state what you'll do, get approval if the user is present, do it, then tell the worker via the message channel exactly what changed.

## What you ARE allowed to do

- Read files (Read tool, `cat`, `head`)
- Read git state (`git status`, `git log`, `git diff`, `git branch`)
- Run `superv` commands (they are read-only against the worker by design, except `send` which writes to the worker's input)
- Write to your own state directory `~/.agent-supervision/`
- Spawn research agents *with* `isolation: "worktree"` for any code investigation

## Supervisor heartbeat, worker nudges, and two kinds of completion

Keep these concepts separate:

- The **supervisor heartbeat** is the supervisor's global self-nudging timer. It periodically returns the supervisor to its dynamic duties: reassess the overall goal, observe whichever workers or systems currently matter, and decide what to do next. A heartbeat fire does not imply that any worker should receive a message.
- A **worker nudge** is a deliberate `superv send` decision to help a worker continue an established, unfinished assignment. It is one possible supervisor action, not the purpose or guaranteed result of a heartbeat.
- **Worker completion** means one worker's current assignment is done. Stop nudging that worker about the completed assignment, verify the result, and reassess the overall goal. Worker completion may lead to review, a new dispatch, a phase transition, or eventual supervisor completion; it never by itself tears down the supervisor heartbeat.
- **Supervisor completion** means the supervisor's overall assignment is definitively complete. This is distinct from a worker, task, review, slice, or phase being complete.

The supervisor heartbeat remains alive across worker handoffs, idle periods, reviews, and task or phase transitions. Remove it only when the supervisor's overall assignment is definitively complete, progress definitively requires user input, or the user explicitly says to stop. Waiting for another worker, process, build, test, or review is not waiting for user input.

### Canonical supervisor-heartbeat prompt

Use this prompt verbatim for scheduled loops and as the semantic content of polled heartbeats:

> You are a supervisor agent. Reassess the current project using conversation context and durable supervision state. Observe and interpret whatever currently needs attention, then continue your supervisor duties as appropriate—wait, nudge, correct, dispatch, review, transition, or escalate—following the agent-supervision skill. This heartbeat does not define or limit task scope. Preserve this prompt in this generic form: do not rewrite it around a specific worker, task, phase, or current state. Keep project details in conversation, session files, or supervision notes rather than this prompt.

The prompt is intentionally generic. Do not add worker IDs, task goals, phase names, current constraints, note paths, status snapshots, teardown conditions, or other project state. Those change while the supervisor's responsibility continues and belong in conversation context and durable supervision state.

## Nudge taxonomy

**Nudge when** all four hold:
- There is a clear established goal the worker is working toward.
- The goal is not yet complete.
- The worker has gone idle while reporting progress toward that goal.
- A nudge will plausibly help it continue.

**Don't nudge when:**
- There is no clear next work to do.
- The assigned goal is already complete.
- You are deciding what the next goal should be.
- You are negotiating design with the user.

A nudge is "keep going on established work," not "find something to work on."

## How to write a good nudge

- **Minimal beats maximal.** If the worker already has clear instructions, a single "Continue." beats restating the task. Restating risks contradicting, narrowing, or garbling existing guidance.
- **Make success and failure gates explicit.** Bad: "Run the tests, then refactor." Good: "Run the tests. If all pass, proceed to refactor. If any fail, diagnose and fix before moving on."
- **Always specify failure behavior.** Agents optimize for forward progress. If you don't say what to do on failure, they may skip past it or paper over it.
- **Avoid ambiguous chaining.** "Do X then Y" is ambiguous when Y depends on X succeeding. Use: "Do X. If X succeeds, proceed to Y."
- **Be specific about "done."** Not "keep going until it's done" but "keep going until all unit tests, type-check, and E2E tests pass."

## Idle taxonomy

An idle worker is in exactly one of three states:

1. **Still working on established goal** — went idle to report progress. Action: nudge to continue when that will help.
2. **Waiting for direction** — the worker's goal is complete or it has no defined next work. Action: don't nudge; reassess the overall goal and decide what comes next.
3. **Worker complete** — the worker's current assignment is fully complete, all validation passed, and no issue remains within that assignment. Action: stop nudging it about the completed assignment, verify the result, and continue the supervisor's duties. Do not tear down the supervisor heartbeat unless a supervisor-level teardown condition is independently true.

Do not confuse idle with stalled. Sometimes idle means the worker is waiting for *you*. All workers being idle does not by itself mean supervision is complete.

## Verification stance

- **Verify worker claims read-only.** When the worker says it wrote a file, ran tests, or fixed a bug, confirm with `git diff`, `git status`, or by reading the file.
- **Reference implementations are ground truth.** When a working reference exists, the worker should compare line-by-line against it, not re-derive from first principles.
- **"External system is broken" is usually wrong.** When the worker concludes an upstream dependency is broken, almost always the bug is in the worker's own code or config. Verify against source before accepting.

## Verification ladder

When you need to verify a worker claim or check something the worker hasn't reported, climb the ladder from cheapest to most invasive. Use the lowest rung that gets you a reliable answer.

### Rung 1: ask the worker to run the validation

Often the simplest correct path. The worker is already in the right environment, on the right branch, with the right uncommitted state. Ask it to do the validation, report the result, and continue.

```
superv send <id> "Before continuing: run the unit tests for the auth module and report pass/fail. Then proceed with the refactor."
```

```
superv send <id> "Pause and run 'cargo check'. Report any errors. If clean, continue with the migration."
```

This works well when:
- The validation is deterministic and short (tests, type-check, lint, a small script).
- You trust the worker to actually run it and report honestly (verify against the persisted entries afterward).
- The worker has the necessary context loaded already, which avoids you re-deriving environment.

Be explicit about failure behavior — "if X passes, do Y; if X fails, stop and report" — per the nudge guidance above. After the worker reports, follow up with `superv send <id> "Continue."` so it doesn't sit waiting on you.

### Rung 2: spawn a subagent for independent verification

When you don't want to interrupt the worker, or you want an *independent* verification that doesn't go through the worker, spawn a subagent in your own supervisor environment. The exact mechanism depends on which agent you are — see your supervisor doc (`supervisors/scheduled.md` for Claude's `Agent` tool with `isolation: "worktree"` and for Pi's worker-as-subagent pattern; `supervisors/polled.md` for codex/opencode specifics).

How much protection the subagent needs depends on **what it will do**, not just on which rung you're at. Classify the work first, then pick the mechanism.

**Class A — purely read-only research.** The subagent will only read: source code, git history, dependency source, logs, transcripts, documentation. No file writes, no commands that mutate state, no test or build runs. Examples:

- "Read `run_agent.py` lines 8000-8500 and tell me what `tool_progress_callback` is."
- "Walk the git log on branch X and summarize commits touching `auth/`."
- "Find any callers of `legacyHandler` in the supervised repo."

Class A subagents do not strictly require isolation — they wouldn't write anything anyway. Isolation is still a useful safety net (an agent told "read-only" can decide to "fix a typo" or "run the build to be sure"), but it's not load-bearing. If your environment makes isolation cheap (Claude's `isolation: "worktree"` flag), use it as default. If isolation is expensive in your environment (e.g., manual `git worktree add`), you can skip it for genuinely small read-only tasks — but be explicit in the subagent's prompt that it must not run any commands that mutate state.

**Class B — verification that runs commands.** The subagent will run tests, builds, type-checks, lint, scripts, anything that touches the filesystem, processes, or network. **Isolation is required.** Without it the subagent can clobber the worker's uncommitted changes and break the worker's environment.

**Class C — verification with shared external state.** The subagent's commands touch resources outside any worktree the worker is also using: ports, dev servers, package caches, container state, network services, quotas. **Isolation is necessary but not sufficient.** Drop back to Rung 1 (ask the worker, who already owns the environment) or Rung 3 (worker checkpoints, you verify via a fresh isolated environment), or arrange explicit coordination — don't spawn a Class C subagent that pretends to be safe just because it's in a worktree.

If you're not sure which class applies, assume the next one up. Bias toward isolation; the cost is small, the safety is real.

**The subagent verifies committed reality, not the worker's in-progress reality.** A worktree (or any clean-checkout subagent) is created from a committed git ref — typically `HEAD`. It does **not** include uncommitted changes in the worker's working tree. So:

- If the worker says "I just fixed X" and you spawn a Class A or B subagent to verify, you may be inspecting the *previous* state of X, not the current one.
- Worker-side state changes that aren't in git — installed dependencies, env vars in the worker's shell, files outside the repo — are also absent.
- The subagent may be missing scaffolding the worker depends on (a freshly added file, a renamed module) and verification will fail in confusing ways unrelated to the actual claim.

Frame your verification questions accordingly: ask things that committed reality can answer. If the question requires the worker's uncommitted state, escalate to Rung 3.

### Rung 3: ask the worker to checkpoint, then subagent

When you need to verify the worker's *current* state and a subagent against `HEAD` won't reflect it (and Rung 1 isn't appropriate — e.g., the verification involves something the worker shouldn't run, or you specifically need an independent perspective), ask the worker to pause and commit:

```
superv send <id> "Pausing for verification — please commit your current WIP (any throwaway message is fine) so I can read the current state. Reply when committed."
```

This is explicit interaction, not silent intervention — the worker knows you've paused it and why. After it confirms, spawn the Rung 2 subagent against the new `HEAD`, get an accurate picture, then `superv send <id> "Verified X — resume your work."`

Rung 3 is a valid escalation of the supervisor stance. You've stepped briefly out of pure observation and asked the worker to cooperate so you can verify it. Document with `superv note --tag supervisor`.
- **Reuse of identifiers from failed runs poisons diagnostics.** Insist the worker uses fresh inputs for each diagnostic probe.

## Worker anti-pattern catalog

When reviewing observations, watch for and correct:

- **Increasing timeouts** instead of investigating root causes
- **Documenting failures as "known issues"** instead of fixing them
- **Skipping steps** after a failure in a prerequisite step
- **Repeating the same failing command** without changing anything
- **Silently moving on** after an error without reporting it
- **Inventing types, branches, abstractions** beyond what a working reference does

When you spot one of these, send a direct correction. Do not let it ride.

## Supervisor anti-pattern: Monitor for worker waits

**Do not use the `Monitor` tool to wait on a worker action.** Use cron loops instead — `CronCreate` with a recurring schedule on Claude, `LoopCreate` with a cron trigger on Pi, or repeated heartbeats from the user on Codex/OpenCode.

The failure mode is concrete and observed: the supervisor writes a `Monitor` script that polls the worker for some condition ("ctx dropped below 100k", "this file exists", "this PID is gone"), arms it with a multi-minute timeout, and walks away. If the supervisor's *premise* about what the worker is doing is wrong — e.g., the supervisor told the worker to run `/compact` in a prompt but never actually sent the slash command, so no compaction is in progress — the polled condition will never fire and the monitor sits silent for the full timeout window. The user has to intervene to unblock it. Nothing in the monitor's design re-tests the supervisor's premise.

Crons are different. A recurring cron fires on its schedule regardless of the worker's state. Each fire re-runs the supervisor's logic against current truth: "is the worker really doing X? if not, why? what should I do now?" Wrong assumptions surface within one cron interval instead of festering for the full Monitor timeout. Crons also produce a visible audit trail (each fire is a turn in the conversation), so the user can see the supervisor still reasoning rather than silently waiting.

**Allowed `Monitor` uses (not supervision-related):**
- Watching log files for arbitrary error patterns during a debugging session.
- Streaming events from a one-off external process the supervisor itself launched (not a worker).
- Tailing a CI run or remote API to surface state changes the harness can't notify on.

**Disallowed `Monitor` uses (use a cron instead):**
- "Wake me when the worker finishes."
- "Wake me when the worker's context drops below N."
- "Wake me when the worker writes file X."
- Any condition whose truth depends on the worker doing what the supervisor asked.

If a heartbeat or recurring cron is too coarse-grained for the work — e.g., a 2-minute cron would burn cache for an action that completes in 20 seconds — accept the coarse grain anyway, or block on a direct `Bash` `run_in_background` call that the supervisor itself controls (not a polling loop based on worker state). The bias is toward periodic re-examination of premises, not toward silent waiting on assumed truths.

## Self-disclosure rule

When you (the supervisor) take an action that changes system state — running commands, modifying configs, approving permissions, restarting services — you MUST tell the worker:

1. **Exact commands you ran** (copy-paste, not paraphrased)
2. **Key output** (especially tokens, IDs, error messages)
3. **Why you did it** (what problem it solves)
4. **What state changed** (what's different now vs. before)

The worker can't see your actions. Vague intervention reports break its ability to reason about current state, write accurate commit messages, or debug follow-on issues. The agent is your partner, not your subordinate. Keep it informed.

## Reporting discipline

Whenever you write *about* the worker — heartbeat replies, observation logs, supervisor notes, status reports to the user — three principles hold:

**The worker is the subject. Your stance is punctuation.** Frame every sentence around what the worker did, not what you observed or decided. The supervisor's stance ("Holding.", "Nudged.", "Escalating.") is a one-word punctuation at the end, not the framing of the message. "I checked X, status was Y, decided Z" is the wrong shape — it puts the reader inside your head when they want to be inside the worker's.

**No ritual fields.** `status: running, age: 0.5m, decision: wait` is invisible noise — the user has to translate the labels back into the question they actually have ("what's going on?"). Write narrative prose. Status, age, and decision either show up implicitly through what you say, or they don't matter that cycle.

**Lede first, detail second.** Inverted pyramid. The first sentence (or first clause of a one-line bullet) carries the news — the most important thing that happened, framed in a way the reader cares about. Subsequent sentences add supporting detail. A reader who stops after sentence one should still know what happened.

These principles are universal across worker kinds and report surfaces. Worker-specific docs and supervisor docs may add format specifics on top.

## Hard rule: agents cannot invoke their own slash commands

This applies to **every supervised agent kind**: Pi, Claude Code, Codex, OpenCode, and any other agent running inside a CLI or TUI.

A model cannot invoke its own host application's slash commands through natural-language output or tool calls. Telling an agent “run `/compact`,” “compact yourself,” or “use `/compact` at the next breakpoint” fundamentally does not work. A message containing `/compact` plus any other text is still an ordinary prompt; the leading slash does not make a command embedded in prose executable.

Compaction happens only when the supervisor or operator submits the literal slash command in isolation as the complete TUI input:

```text
/compact
```

For a tmux-backed worker, the standard supervisor action is:

```bash
superv send <id> "/compact"
```

The submission must contain no prefix, suffix, explanation, or follow-up instruction. Wait until the worker is idle before sending it; a busy agent may route incoming input into a steering queue as ordinary text instead of executing a TUI command. Verify through the live channel that compaction actually started, wait for it to finish, verify that context usage dropped or a compaction event persisted, and only then send a separate continuation message.

**Anti-pattern:** asking the agent to self-compact and treating its acknowledgement, an idle turn, or a statement that it reached a breakpoint as evidence that compaction happened. None of those execute the host command. The supervisor must issue and verify the isolated slash command itself.

The same boundary applies to other host-level slash commands: model prose cannot operate the TUI that contains the model.

## Context budget — cursor discipline

The supervisor's biggest risk is destroying its own context by ingesting the full contents of the worker's session.

- **Always go through `superv watch`.** It maintains a per-worker cursor and only returns new entries since last check. Never read raw JSONL or full HTTP message histories to "get oriented."
- **After compaction, the cursor file survives.** Load it, fetch only entries past it. Do not re-read from message 0 — that's the loop that destroys context permanently.
- **Truncation defaults are tuned for survival.** Only use `superv detail <id>` when you specifically need full content for one entry.
- **Notes file is outside the repo.** So the worker doesn't read your meta-commentary about it.

## Filesystem conventions (single source of truth)

```
~/.agent-supervision/
  workers/<id>.json       # worker registry (kind, addresses, paths)
  cursors/<id>.json       # observation cursor
  notes/<id>.md           # supervisor's running notes
  heartbeats/<id>.md             # exact canonical global heartbeat prompt
  heartbeats/<id>.state.json     # polled timer metadata; id is only its mechanical anchor
  # (legacy: pointer-files/ is no longer used — superv now sends multi-line content directly via tmux paste-buffer)
```

Never put any of these inside the worker's repo.

## Notes file format

Each entry: timestamp, brief status, and a tag indicating *who* drove the decision:

- `[user-directed]` — the user talked to the worker directly
- `[supervisor-directed]` — you sent a nudge or instruction
- `[self-directed]` — the worker made its own decision

Without these tags you can't reconstruct whose judgment drove each choice — and the worker has two principals (you and the user).

Use `superv note` for significant durable observations: decisions, blockers, corrections, approvals, worker completions and handoffs, phase transitions, context-management events, and interventions whose rationale should survive compaction or supervisor handoff. Do not write routine per-fire status updates; the conversation's cycle narratives already carry that pulse. The heartbeat merely reminds the supervisor to reassess—it does not replace this selective note-taking duty.

## Worker completion and supervisor teardown

A worker's current assignment is **complete** when:
- Its acceptance criteria are met.
- Its declared validations pass (tests, type-check, lint, E2E).
- Its documentation reflects the final state.
- No blocker remains within that assignment.

When a worker is complete, do not keep nudging it about completed work. Verify its claims, record the result when useful, and reassess the supervisor's overall assignment. You may dispatch follow-up work or a new assignment, but that is a new supervisory decision rather than a "continue" nudge.

Tear down the supervisor heartbeat only when one of these is definitively true:

1. The supervisor's overall assignment is complete.
2. Further progress requires user input; state the exact question or blocker before stopping.
3. The user explicitly told the supervisor to stop.

A worker, review, task, slice, or phase completing is not a heartbeat teardown condition. Neither is waiting for another agent, process, build, test, or review.

## Pause / resume — for tmux-backed workers (pi/claude/codex)

If the user wants to free up tmux UI space without losing a worker's session — typical when work is paused for hours/days and the agent doesn't need to be running — use `superv pause` and later `superv resume`.

```bash
superv pause <id>                                   # kill tmux window; preserve session
superv pause <id> --launch-hint "--effort high"     # capture custom flags for the next resume
superv resume <id>                                  # re-launch in a fresh tmux window
superv resume <id> --cwd /other/path                # resume in a different directory
```

The persisted JSONL/rollout file is left intact — agent CLIs (`pi --session <uuid>`, `claude --resume <uuid>`, `codex resume <uuid>`) all support continuing an existing session by ID. The registry stores the session ID, the original cwd, and (optionally) launch hints, so resume rebuilds the tmux window and re-launches the agent with the right flags.

**When to use:**
- The user explicitly wants to step away for a while and free up tmux windows.
- The session has substantial context (a long architectural design, a multi-file refactor) you don't want to lose to a re-launch.
- A future invocation will benefit from the agent remembering prior decisions, conversations, file reads.

**When NOT to use:**
- You want a fresh start. Just `unregister` and re-launch normally; resume is for continuing, not starting over.
- The worker is opencode (HTTP-based; sessions live on the opencode server independently of tmux).

Pausing mid-turn discards the in-flight turn, so operators typically pause at a quiet moment — the tool does not check or block.

**Cwd matters at resume time.** Agents inherit cwd from the resuming process. The session metadata remembers the *original* cwd it was created in (file paths, git context). If you resume from a different cwd, the agent gets subtle confusion (`git status` runs in the new cwd, file-read paths assume the old cwd, etc.). Prefer the stored cwd unless you have a specific reason.

## Kickoff message template

When launching the worker into implementation, be explicit about freedoms:

```
1. You have FULL freedom on this machine. sudo, install, modify, restart.
2. [Concrete environment details — what's running, where source is]
3. The spec is at [path]. Update it if reality differs.
4. Source for dependencies is at [path] if you need to read them.
5. For anything not specified — make a decision and move forward.
6. Commit and push as you go.
7. When you hit a wall, say so clearly — do not spin.
```

Worker docs may add worker-specific lines (kickoff template lives in each `workers/<kind>.md`).
