# Supervisor — Scheduled (Claude Code or Pi)

You are a scheduled supervisor — Claude Code or Pi. You have native non-blocking schedule primitives. Use them. Do **not** use `sleep N && cat file` for heartbeats — that's a category error here.

The scheduled loop is the supervisor's one global self-nudging heartbeat. It keeps the supervisor alive across workers, reviews, tasks, slices, phases, and handoffs. It is not a monitor scoped to one worker or assignment, and firing does not imply that a worker needs a nudge.

## Primitive mapping

The two supervisors have near-identical scheduling capability under different tool names. The strategy in this file is shared; only the tool calls differ. Find your column and use it throughout.

| Capability | Claude Code | Pi | Notes |
|---|---|---|---|
| Recurring background tick (**default**) | `CronCreate(cron, prompt)` | `LoopCreate` with `triggerType: "cron"` | Set once, fires on its own cadence until deleted. |
| Delete the tick | `CronDelete(id)` | `LoopDelete(id)` | Stops the loop. The critical teardown step. |
| List active ticks | (none) | `LoopList` | Pi-only convenience. |
| One-shot end-of-turn re-arm | `ScheduleWakeup` | `schedule_loop_wakeup` (self-paced `/loop`) | Same re-arm failure mode in both — see below. **Not for ongoing supervision.** |

Pi extras with no Claude equivalent (use carefully — see "Event/hybrid triggers" below):

- `LoopCreate` accepts `triggerType: "event"` (fires on a pi event-bus channel such as `tool_execution_end` or `turn_end`) and `"hybrid"` (cron + event with debounce).
- `LoopCreate` accepts `maxFires` (auto-stop after N fires) and `readOnly` (restrict the agent to read-only tools on each fire).

## Prerequisite (Pi): install the `pi-loop` plugin

Pi does not ship with scheduling built in — the `LoopCreate` / `LoopDelete` / `LoopList` / `schedule_loop_wakeup` primitives come from the `pi-loop` extension. Claude Code's scheduling is built in; Pi's is not. Install the plugin once per machine before acting as a scheduled supervisor:

```bash
pi install npm:@koltmcbride/pi-loop
```

Source: https://github.com/kolt-mcb/pi-loop

If `LoopCreate` is not available in your current Pi session, the plugin is not installed (or not enabled) — install it and restart Pi. A Pi without the plugin has no scheduling primitive and must supervise as a **polled** supervisor (`supervisors/polled.md`), falling back to `superv heartbeat` + `sleep N && cat file`. The bootstrap routing in `SKILL.md` keys on whether the primitive is actually available, so an uninstalled plugin routes you to polled automatically.

## Schedule primitives

| Primitive | When to use |
|---|---|
| `CronCreate` (Claude) / `LoopCreate` cron (Pi) | **Default.** Recurring background tick that fires regardless of what the supervisor is doing. Set once, runs reliably until you delete it. |
| `ScheduleWakeup` (Claude) / `schedule_loop_wakeup` (Pi) | One-shot dynamic re-entry. Use only for genuine one-offs ("check back in 20 minutes for build result") — see warning below. |

## Why the cron-style tick is the default (and end-of-turn re-arm is not)

`ScheduleWakeup` (Claude) and `schedule_loop_wakeup` (Pi) both require the supervisor to *actively re-arm itself* at the end of every turn. In practice, agents forget to re-arm roughly half the time — no matter how strongly the prompt insists on it. When that happens, supervision silently dies. There is no fallback. The Pi tool description states this directly: *"If you do not call it, the self-paced loop ends."*

`CronCreate` (Claude) and `LoopCreate` with a cron trigger (Pi) do not have this failure mode. The scheduler fires on its own cadence whether you remember anything or not. If you want supervision to keep running, set the cron once. If you want it to stop, run `CronDelete` / `LoopDelete`.

Use the one-shot re-arm only when the cadence is genuinely one-shot and dynamic (e.g., "the build said it'd be done in 8 minutes; check back then"). For ongoing supervision, always use the recurring cron-style tick.

If you do use the one-shot re-arm path, you must state the re-arm explicitly in your end-of-turn reply (same discipline as the polled supervisor's re-arm clause) — "re-arming with schedule_loop_wakeup / ScheduleWakeup for +N" or "not re-arming because Y." The omission is otherwise silent.

## Canonical loop prompt

Use the canonical supervisor-heartbeat prompt from `core.md` **verbatim**. It is intentionally generic and already tells future fires to preserve it in that form. Do not rewrite, replace, or enrich it with a worker ID, task goal, phase name, current constraint, notes path, teardown rule, or status snapshot. The loop prompt is only a self-nudge to resume dynamic supervisor duties; conversation context and durable supervision state carry the work.

There is one scheduled loop for the supervisor's overall assignment, not one loop per worker, task, review, slice, or phase. Recreating it at ordinary workflow boundaries introduces a handoff where supervision can silently stop.

Default cadence (see "Cadence default: pick once and stay there" below):

```
# Claude
CronCreate(cron: "*/2 * * * *", prompt: <heartbeat-prompt>)   # every 2 min — the standard

# Pi
LoopCreate(triggerType: "cron", trigger: "*/2 * * * *", prompt: <heartbeat-prompt>)
```

Pick this and leave it alone. Only change it on explicit user request — see the cadence section below for the why.

**Anti-pattern: do not specialize or bloat the prompt.** The cron prompt is re-injected verbatim on every fire, so every byte is paid for repeatedly and stale details can silently narrow the supervisor's duties. The nudge taxonomy, idle taxonomy, verification ladder, cursor discipline, context-budget thresholds, reporting discipline, workers, task constraints, and current phase all live in conversation context and durable supervision state. If you feel tempted to rewrite the loop for a new worker or phase, leave the canonical prompt untouched and update the appropriate session or note state instead.

## Cache-window-aware cadences

**Keep fires under the ~5-min prompt cache TTL; in practice cap at 4 min (5 min lands right on the TTL boundary and reliably misses).** Past ~5 min the cache has expired and every wakeup re-reads the full prompt, which costs more and gives nothing back. Inside the window the cache stays warm and each fire is cheap.

### Cadence default: pick once and stay there

**Pick a single cadence at supervision kickoff and leave it alone for the duration.** For a typical active-supervision loop, that means **every 2 minutes** (`*/2 * * * *`). It stays inside the cache window, gives you 30 fires/hour of visibility, and requires zero further bookkeeping.

Do not try to ramp the cadence based on the worker's state. The polled supervisor uses adaptive backoff because its sleep+cat heartbeat is in-band and adjusting `next_sleep` is one tool call. The scheduled equivalent — deleting the tick followed by a fresh create with the new cadence + same prompt + capturing the new id back into your context — is a multi-step ritual agents skip ~half the time. Same family of failure mode as forgetting to re-arm. **Don't go there.**

### When to actually change the cadence

Only on explicit user request, or if the user has set up the supervision to span very different phases (e.g., "watch this 12-hour soak"). To change:

```
# Claude
CronDelete <current-cron-id>
CronCreate(cron: "<new-cron>", prompt: <heartbeat-prompt>)
# remember the new cron id; it's what you'll CronDelete on teardown

# Pi
LoopDelete <current-loop-id>
LoopCreate(triggerType: "cron", trigger: "<new-cron>", prompt: <heartbeat-prompt>)
# remember the new loop id; it's what you'll LoopDelete on teardown
```

### Do not extend beyond 4 min on your own

It is tempting to think "the worker is mid-build / mid-test / mid-long-task; I should back off to every 20 min to save cache." **Do not.** Reasons:

- You usually do not know how long the worker's task will actually take. "Long-running" is rarely a reliable estimate; tasks finish, hang, or go off the rails on their own schedules. A 4-min cap means you catch any of those within 4 minutes.
- Backing off feels like optimization but is mostly the supervisor under-supervising to save itself work. The point of supervision is to catch things early. Long intervals defeat the point.
- The user values knowing the worker is being watched at a regular cadence more than they value the saved cache cost.

Long intervals (>4 min) are only appropriate when:

1. The user explicitly asks for them ("just check it once an hour"), or
2. You have a concrete, verifiable timing signal — e.g., a build script reported "ETA 8 minutes" and you have nothing else to do until then. In that case, use the one-shot re-arm (`ScheduleWakeup` / `schedule_loop_wakeup`) for the one-shot, not a slow cron.

If you're not sure which case you're in, you're not in either. Stay at the 4-min cap.

## Event/hybrid triggers (Pi only — use carefully)

Pi's `LoopCreate` accepts `triggerType: "event"` and `"hybrid"`, which fire on pi event-bus channels (e.g. `tool_execution_end`, `turn_end`) instead of a fixed cadence. This looks attractive for supervision ("wake me whenever the worker finishes a turn") but has the **same premise-trap as the disallowed `Monitor` use** described in `core.md`: an event trigger only fires when the worker does what you assumed. If the worker stalls, hangs, or goes silent, the event never fires and the supervisor sits silent indefinitely — no re-examination of premises, no audit trail of the supervisor still reasoning.

For ongoing worker supervision, **use the cron trigger, not event/hybrid.** A recurring cron fires on its own schedule regardless of the worker's state, which is exactly the property that makes supervision robust to wrong assumptions about what the worker is doing.

Event/hybrid triggers are appropriate for genuine reactive work — not supervision of an external worker — where the event itself is the truth ("wake me when *my own* tool execution ends") rather than a premise about another agent's behavior.

## Heartbeat workflow per cron fire

1. Reassess the supervisor's overall goal and current conversation/durable state. Identify what, if anything, needs attention now.
2. Observe each relevant worker through `superv watch <id>` and `superv status <id>`. Use `superv detail <id> <entry-id>` only when one full entry is needed.
3. Interpret worker signals and project state. Distinguish worker completion from supervisor completion.
4. Decide the next supervisory action: wait, nudge established work, correct, dispatch new work, review, transition phases, escalate, or conclude.
5. If sending, use `superv send`; verify submission. Use `superv note` for significant decisions, blockers, corrections, approvals, completions/handoffs, transitions, context-management events, and interventions—not routine per-fire status.
6. End with a brief cycle narrative centered on what progressed and what supervisory action follows.
7. Delete the tick only when the supervisor's overall assignment is definitively complete, progress definitively requires user input, or the user explicitly says to stop.

There is no step 8 "re-arm" in this list — that's the whole point of using a cron-style tick. The next fire happens on its own. A worker becoming complete changes step 4; it does not trigger step 7.

## Heartbeat reply: narrate the cycle

End each fire's turn with a short reply that **narrates what the worker did over the cycle** (the watch delta since last fire). This is the user's primary view of progress and your own continuity record across fires. Two readers:

- **The user** — follows along like watching a game. Wants to know what just happened, not what state things are in right now.
- **You on the next fire** — your prior replies survive in context better than long prose; reading them tells you whether the worker has been idle for one cycle or three, and what you've already nudged about.

### The three principles

These also apply to log entries when an observational log is configured (see below), and to durable supervisor notes.

**1. The worker is the subject. Your stance is punctuation.**

Frame every sentence around what the worker did, not what you observed or decided. The supervisor's stance ("Holding.", "Nudged.", "Escalating.") shows up as one short word or phrase at the end — not as the framing of the message. Avoid "I checked" / "status was" / "decided to" framings; they reverse the subject.

**2. No ritual fields.**

Don't render the reply (or log bullet) as labeled fields. `status: running, age: 0.5m, decision: wait` is invisible noise — the user has to translate it back into the question they actually have ("what's going on?"). Write narrative prose. The status, age, and decision either show up implicitly through what you say, or they don't matter that cycle.

**3. Lede first, detail second.**

Inverted pyramid. The first sentence (or first clause of a one-line bullet) carries the news — the most important thing that happened in the cycle, framed in a way the reader cares about. Subsequent sentences add supporting detail. A reader who stops after sentence one should still know what happened. A reader who reads the whole thing gets the texture.

If the cycle's news is "leaf closed clean and rover moved on," lead with that. If the cycle's news is "first behavioral defect of the lap, here's what makes it interesting," lead with that. The headline frames the rest.

### Style notes

- **Use action verbs with concrete objects.** "Closed `repo-orientation-docs` clean (commit 24a196c)" beats "made progress on a leaf." File names, commit hashes, defect slugs, sizes. Specific enough that the reader can picture it.
- **Chain causally.** "Read X, found Y, therefore filed Z" — actions that produce consequences read as a story; lists of operations don't.
- **Anchoring details.** One or two real moments from the cycle dropped in as texture. ("The 10-byte `@AGENTS.md` redirect" or "`src/search-query-translator.ts:225`.") Makes the reader feel like they were watching.
- **Forward inference where it helps.** If the worker's last action obviously sets up something next, name it briefly. ("Likely about to file or close.") Past tense for what happened, soft prediction for trajectory. Don't overcommit.
- **Length tuned to the cycle.** If a lot happened, 3–4 sentences. If nothing happened, half a sentence is fine. Don't pad an empty cycle into prose.

### Examples

**Good (cycle narrative, lede first):**

> The errors leaf produced the first behavioral signal of the lap — a p2 + p3 that go past the prior reviewer's same-area finding. The p2 (commit 6836276) isn't just "add the missing code"; the slug suggests the error-code classification itself needs rework. The companion p3 surfaces that the test that should catch spec/code drift doesn't actually enforce parity, so this whole drift class can recur. Worker then opened `logging`, read spec + src + first two test files, mid-investigation. Holding.

> Worker has been idle 3 fires since closing the auth slice. No new commits, no nudges yet. Likely waiting on direction or budget-pausing — sending "Continue with the migration slice next." Nudged.

> Worker reported "all done" and the tree is clean with 12/12 tests passing. Tearing down.

**Bad (snapshot framing, supervisor as subject, ritual fields):**

> Worker is mid-test-run on slice 1.4; transcript turn-state is busy, recent commits look correct. Waiting another cycle.
>
> *(Snapshot, not narrative — what did the worker DO in this cycle? Reader can't tell.)*

> status: running, age: 0.5m, decision: wait
>
> *(Field dump. Forces the reader to translate.)*

> I checked the worker and saw it was reading specs. I decided to wait.
>
> *(Subject is the supervisor; trivial detail dressed up as decision.)*

> d2/l3 spc, ttl 4m, +reads, no nudge
>
> *(Cryptic compression. Compactness is not the goal.)*

### Log entries (when configured)

If the cron prompt configures a per-fire log (e.g. an observation log file), the same three principles apply. The log bullet is one line, but uses multiple clauses (semicolon-separated) to narrate the cycle:

> `- HH:MMZ — first behavioral signal of the lap: filed p2 + p3 in errors that go past prior reviewer's parity finding (p2: spec drift AND classification needs work; p3: test doesn't enforce spec union, so drift class can recur); commit 6836276; opened logging leaf, read spec + src + 2 test files`

First clause = headline. Subsequent clauses = detail.

### Durable observations

For cycle-spanning observations (significant decisions, interventions, blockers, milestones), also use `superv note <id> "..." --tag supervisor` — that writes to disk and survives context drops. Same three principles apply.

## Verification: subagent mechanism

The general verification ladder lives in `core.md` (Rung 1: ask the worker; Rung 2: spawn an isolated subagent; Rung 3: ask the worker to checkpoint then subagent). This section covers the Rung-2 mechanism for each scheduled supervisor.

### Claude Code — `Agent` tool with `isolation: "worktree"`

For Rung 2, use the `Agent` tool with `isolation: "worktree"`:

```
Agent({
  description: "Verify worker claim about X",
  subagent_type: "Explore",
  prompt: "...",
  isolation: "worktree"
})
```

`isolation: "worktree"` creates a temporary git worktree from `HEAD` and gives the subagent its own checkout. Cleanup behavior: the worktree is automatically cleaned up *if the subagent makes no changes*; if it did write, the worktree path and branch are returned in the result so you can inspect or salvage the work. **Never** spawn a research agent without `isolation: "worktree"` while a worker is active in the same repo — without it, the subagent can clobber uncommitted changes.

Note: `subagent_type: "Explore"` is the right default for read-only research. `general-purpose` works too if you need broader tools, but make sure the prompt doesn't ask it to write or commit anything in the worktree (the worktree mutations get discarded on cleanup, but they can still race against the worker's environment as described in core's "Side-effect risk").

### Pi — worker-as-subagent (no built-in isolation flag)

Pi has no special subagent tool and no `isolation: "worktree"` flag. The "subagent" *is* a worker session — you launch a fresh pi instance in its own tmux window with a focused verification prompt, treat it as a short-lived worker (this same skill applies recursively), read its result, then tear it down. Isolation comes from the worktree cwd: the new pi sees that worktree as its repo and cannot touch the worker's working tree.

Mechanism — the normal pi-launch flow plus a worktree:

```bash
git worktree add <isolated-worktree-path>          # from the worker's repo HEAD
tmux new-window -t <session> -n verify -d
tmux send-keys -t <session>:verify.0 \
  'cd <isolated-worktree-path> && pi --model <model> "<verification prompt>"' Enter
# wait for first turn, then:
superv register <verify-id> --kind pi --tmux <session>:verify.0
```

Because this subagent is itself a pi worker, register it and let the existing global supervisor heartbeat observe it alongside any other relevant worker. Do not create a verification-specific loop. When verification is done, tear down or unregister the verify worker as appropriate and clean up the worktree (`git worktree remove <path>`); keep the global supervisor heartbeat alive unless a supervisor-level teardown condition applies.

Class A/B/C isolation rules from `core.md` still apply: a read-only verification subagent doesn't strictly need the worktree, but use it as the default safety net since there's no cheap built-in flag. Class B (runs commands) and Class C (shared external state) verifications need the worktree at minimum, and Class C may require falling back to Rung 1 or Rung 3.

If assembling a worktree is too heavy for the task, **prefer Rung 1 (ask the worker)** for verification. Rung 3 (worker checkpoints, then subagent against the new HEAD) is a strong fallback when Rung 1 isn't appropriate.

## Compaction recovery

When your context compacts:

1. Cursor files in `~/.agent-supervision/cursors/` are unaffected — they're outside your context entirely.
2. On the first wakeup post-compaction, run `superv watch <id>` for whichever workers are currently relevant. It returns only entries past each cursor — typically 0–20.
3. **Do not** re-read history "to get oriented." That's the loop that destroys context permanently. Conversation context, durable notes, worker docs, cursors, and recent persisted deltas are enough to reorient.

One Pi-specific note: `LoopList` shows your active scheduled loops with fire counts and next-fire times. If you come out of compaction unsure whether your supervision tick is still running, `LoopList` answers that without re-reading any worker state. Claude has no equivalent — you'd have to remember the cron id.

## Supervisor-heartbeat teardown

Do not delete the tick because a worker, task, review, slice, or phase completed, or because all current workers are idle. Those are reasons to reassess and possibly transition or dispatch—not reasons to stop supervising.

Delete the tick only when:

1. The supervisor's overall assignment is definitively complete.
2. Further progress definitively requires user input, and you have stated the exact question or blocker.
3. The user explicitly told you to stop.

Then delete it with `CronDelete <cron-id>` on Claude or `LoopDelete <loop-id>` on Pi and record the outcome when useful. If the user later resumes work after a user-input stop, create the same canonical global heartbeat again. Do not rewrite it for the resumed phase.
