# Heartbeat, scheduling, and cycle reporting

The supervisor's one global self-nudging loop keeps it alive across workers,
reviews, tasks, slices, phases, and handoffs. This file covers how to schedule
it, how fast, how `supervisr events` fits in, and how to write each cycle's
report. The *lifecycle* rules (when to keep it, when to tear it down) are in
`core.md`; this file is the mechanics and the reporting discipline.

## Scheduling primitive by supervisor kind

You have a native non-blocking scheduler — use it. Do **not** use `sleep N && cat file` heartbeats.

| Capability | Claude Code | Pi |
|---|---|---|
| Recurring background tick (**default**) | `CronCreate(cron, prompt)` | `LoopCreate` `triggerType: "cron"` |
| Delete the tick (teardown) | `CronDelete(id)` | `LoopDelete(id)` |
| List active ticks | (none) | `LoopList` |
| One-shot end-of-turn re-arm | `ScheduleWakeup` | `schedule_loop_wakeup` |

Pi requires the `pi-loop` plugin for these (`pi install npm:@koltmcbride/pi-loop`); if `LoopCreate` isn't available, the plugin isn't installed. Claude's scheduling is built in.

### CRITICAL (Pi): never set `maxFires` on the supervisor heartbeat

The `pi-loop` extension's tool guidance says to always set `maxFires` on polling loops. **For the global supervisor heartbeat, ignore that guidance and omit `maxFires` entirely.** A fire count silently stops supervision based on elapsed ticks rather than actual completion; a larger number only postpones the same failure. This skill is authoritative for supervisor behavior; its lifecycle rule (tear down on a `core.md` teardown condition, via `LoopDelete`) overrides the generic recommendation. Unmetered means "no numeric expiry," not "never terminate."

## Why the cron-style tick is the default (not end-of-turn re-arm)

`ScheduleWakeup` / `schedule_loop_wakeup` require the supervisor to *re-arm itself* every turn. In practice agents forget to re-arm ~half the time, and when they do, supervision silently dies with no fallback. The cron-style tick fires on its own cadence regardless. Use the one-shot re-arm only for a genuinely one-shot dynamic cadence (e.g. "the build said ~8 min; check back then") — and if you do, state the re-arm explicitly in your end-of-turn reply, same discipline as any re-arm.

## Cadence: pick once and stay there

**Pick one cadence at kickoff and leave it for the duration.** For active supervision that is **every 2 minutes** (`*/2 * * * *`):

```
# Claude
CronCreate(cron: "*/2 * * * *", prompt: <canonical heartbeat prompt>)
# Pi — deliberately omit maxFires
LoopCreate(triggerType: "cron", trigger: "*/2 * * * *", prompt: <canonical heartbeat prompt>)
```

Use the canonical heartbeat prompt from `core.md` verbatim; do not specialize or bloat it (it is re-injected every fire). There is one loop for the supervisor's overall assignment, not one per worker/phase.

- **Keep fires under the ~5-min prompt-cache TTL; cap at 4 min in practice** (5 min lands on the boundary and misses). Inside the window the cache stays warm and each fire is cheap; past it every wakeup re-reads the full prompt for nothing.
- **Do not ramp the cadence based on worker state.** The scheduled equivalent of adaptive backoff — delete the tick, create a new one with a new cadence + the same prompt, capture the new id — is a multi-step ritual agents skip ~half the time (same family as forgetting to re-arm). Don't go there.
- **Do not extend beyond 4 min on your own.** You usually don't know how long a task will really take; a 4-min cap catches finishes, hangs, and derailments within 4 minutes. Longer intervals are under-supervising to save yourself work. Only go longer on explicit user request, or with a concrete timing signal (use the one-shot re-arm for that, not a slow cron).

To change cadence (only on user request or a very-long-phase span): `CronDelete`/`LoopDelete` the current tick, then create a new one with the new cadence + the canonical prompt, and remember the new id for teardown.

## `supervisr events` — the event-hub accelerator

herdr has an authoritative event hub, and `supervisr events` streams one line per status transition of the agents in scope (`EVENT alice blocked`, `EVENT bob done`, `EVENT carol gone`). Unlike the forbidden "Monitor polls for a guessed text pattern" anti-pattern (`core.md`), this fires on herdr's real state, not a prediction, so it is not a wrong-premise trap. Run it under a host background-command facility (a Monitor) as an **accelerator** that wakes you between heartbeats — but keep the recurring cron/loop as the **backstop** for hangs, missed events, and premises the hub can't see (e.g. a worker busy-but-stalled with no transition). Park `events` on **already-running** workers; starting it against an empty scope and relying on rescope during a fast dispatch can miss the first transitions. It never permits a foreground wait that holds your turn open.

## Heartbeat workflow per fire

1. Reassess the overall goal and current state; identify what needs attention now.
2. Observe each relevant worker via `supervisr sweep`, then `supervisr watch` only what `sweep` flags. Use `supervisr detail` for one entry when needed.
3. Interpret signals; distinguish worker completion from supervisor completion.
4. Decide the next action: wait, nudge established work, correct, dispatch, review, transition, escalate, or conclude.
5. If sending, `supervisr send` and confirm it landed (herdr's `--wait` effect-gate, or the next `sweep`). Use `supervisr note` for significant decisions/blockers/completions — not routine per-fire status.
6. End with a short cycle narrative (below).
7. Tear the tick down only on a `core.md` steady-state teardown condition (`CronDelete`/`LoopDelete`). A worker completing changes step 4, not step 7.

There is no "re-arm" step — the cron fires on its own.

## Heartbeat reply: narrate the cycle

End each fire's turn with a short reply that **narrates what the worker did over the cycle** (the `watch` delta since last fire). This is the user's primary view of progress and your own continuity record. Two readers: the **user** (following like a game — wants what just happened, not a state snapshot) and **you next fire** (your prior replies survive in context and tell you whether the worker has been idle one cycle or three, and what you've already nudged).

### Three principles (also apply to notes and any observation log)

**1. The worker is the subject. Your stance is punctuation.** Frame every sentence around what the worker did, not what you observed or decided. The supervisor's stance ("Holding.", "Nudged.", "Escalating.") is a one-word ending, not the framing. Avoid "I checked / status was / decided to."

**2. No ritual fields.** `status: running, age: 0.5m, decision: wait` is invisible noise — the reader has to translate labels back into "what's going on?". Write narrative prose; status/age/decision show up implicitly or don't matter that cycle.

**3. Lede first, detail second.** Inverted pyramid: the first sentence carries the news, framed so the reader cares. A reader who stops after sentence one still knows what happened.

### Style

- **Action verbs with concrete objects.** "Closed `repo-orientation-docs` clean (commit 24a196c)" beats "made progress." File names, commit hashes, defect slugs, sizes.
- **Chain causally.** "Read X, found Y, therefore filed Z" reads as a story; lists of operations don't.
- **One or two anchoring details** dropped in as texture make the reader feel present.
- **Soft forward inference** where the last action obviously sets up the next ("likely about to file or close"). Past tense for what happened, soft prediction for trajectory; don't overcommit.
- **Length tuned to the cycle** — 3–4 sentences if a lot happened, half a sentence if nothing did. Don't pad an empty cycle.

### Examples

**Good (cycle narrative, lede first):**

> The errors leaf produced the first behavioral signal of the lap — a p2 + p3 that go past the prior reviewer's same-area finding. The p2 (commit 6836276) isn't just "add the missing code"; the slug suggests the error-code classification itself needs rework. Worker then opened `logging`, read spec + first two test files, mid-investigation. Holding.

> Worker has been idle 3 fires since closing the auth slice. No new commits, no nudges yet. Likely waiting on direction — sending "Continue with the migration slice next." Nudged.

> Worker reported "all done" and the tree is clean with 12/12 tests passing. Tearing down.

**Bad:**

> Worker is mid-test-run on slice 1.4; turn-state busy, recent commits look correct. Waiting.
> *(Snapshot, not narrative — what did the worker DO this cycle?)*

> status: running, age: 0.5m, decision: wait
> *(Field dump; forces the reader to translate.)*

> I checked the worker and saw it was reading specs. I decided to wait.
> *(Subject is the supervisor; trivial detail dressed as decision.)*

For cycle-spanning observations (decisions, interventions, blockers, milestones), also `supervisr note <name> "…" --tag supervisor` — same three principles, and it survives compaction.

## Compaction recovery

When your own context compacts: the `supervisr` cursors under `~/.local/state/supervisr/` are unaffected (outside your context). On the first fire post-compaction, `supervisr sweep` re-derives who your workers are from herdr (no memory needed), then `supervisr watch` each relevant one — it returns only entries past each cursor, typically 0–20. **Do not** re-read history to "get oriented"; that is the loop that destroys context. On Pi, `LoopList` confirms your tick is still running without reading any worker state; Claude has no equivalent, so remember the cron id.
