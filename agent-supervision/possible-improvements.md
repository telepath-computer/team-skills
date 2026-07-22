# Possible improvements — agent-supervision

Proposed modifications to the skill instructions. Each entry names the anti-pattern, the correct pattern, and the reasoning. Not yet applied to the canonical docs; collect here until a batch is ready to land.

---

## Cron loop = nudge, not a manual

### Anti-pattern 1: long self-directed instruction prompt in the cron

Putting the full supervision procedure — stage actions, decision trees, gotchas, file references — into the cron's `prompt`. The prompt is re-injected verbatim on every fire. A 100-line prompt fired every 2 minutes for a 10-hour supervision burns ~30,000 lines of context re-reading the same instructions the supervisor already holds.

### Anti-pattern 2: cron requires reading a file every fire

Shrinking the cron prompt but instructing the supervisor to `read` a state/actions file at the start of every fire. This routes the same waste through the read tool: the file content is already in the supervisor's context from the prior fire's reply, so re-reading it spends tokens to load identical knowledge. It is anti-pattern 1 with the manual moved to disk.

### Correct pattern: cron is a nudge; context lives where context lives

The cron's `prompt` is a trigger, not a manual. It should be a short nudge — "check on the agent(s), take the next supervision action, reply" — that relies on the supervisor's existing context for the actual procedure. The supervisor carries the worker's goal, the current stance, and the recent cycle history in its context from prior fires' replies and the conversation transcript. That is where context lives; it does not need to be re-injected or re-read on every tick.

Disk files (state, action tables, notes) are a **recovery anchor for compaction**, not a routine read. Read them only when the supervisor has actually lost context — e.g., on the first fire after a context compaction, when the prior cycle's replies are gone. Keep recovery locations in conversation context and the skill's standard durable-state conventions; do not name them in or otherwise specialize the canonical loop prompt. "Read `<file>` first every fire" is anti-pattern 2.

### When a task is complex enough to warrant a recovery file

Simple ongoing supervision may not need a recovery file at all — the canonical heartbeat, conversation context, and worker cursors can be enough, and a compacted supervisor reorients from recent persisted deltas and its own surviving context.

Complex multi-stage workflows (a pipeline with stage-dependent actions: plan → review → consensus → implement → impl-review) may warrant durable recovery state because the *action at the next fire genuinely depends on which stage the workflow is in*. Keep that state in the standard session or supervision notes, not in the global loop prompt, and read it only when orientation is actually lost. The test for whether recovery state is warranted: after compaction, could a supervisor with the canonical heartbeat, surviving conversation context, and recent `superv watch` output plausibly take the correct next action? If yes, do not create more state. If no, write a recovery note without changing the loop.

### What this implies for the canonical docs

The canonical docs now define one generic global supervisor-heartbeat prompt and prohibit specializing it by worker, task, phase, current state, or recovery path. Durable files remain available for actual recovery, but the loop never instructs a routine read and never becomes a workflow controller.

### Observed failure mode that motivated this

An overnight pipeline-driving cron was armed with a ~120-line prompt containing the full pipeline state machine (stage actions, gotchas, file references). Re-injected every 4 minutes for 10 hours. Revised once to a ~4-line prompt that instead instructed a per-fire `read` of two state files — same waste, routed through `read`. Both shapes spent context re-loading knowledge the supervisor already held. The correct shape is the fixed canonical global heartbeat, with any necessary state machine kept in durable supervision state and consulted only when context is genuinely lost.
