# Worker — Pi (herdr)

Pi as a supervised herdr agent.

## 1. Launch and identity

Launch with `supervisr dispatch <name> --kind pi`. supervisr defaults the model to `openai-codex/gpt-5.6-sol:xhigh` and seeds an explicit `--session-id <name>-<uuid>` automatically (pi needs it, and registration binds on it). **Always launch pi with an explicit model** — a bare `pi` inherits whatever model/level were last used interactively, which makes launches non-reproducible. The model string encodes model **and** reasoning level (`:xhigh`); an explicit `--model x:level` wins over `--effort`.

Known pi models (default GPT-5.6 Sol):

| Ask | `--model` value |
|---|---|
| GPT-5.6 Sol (default) | `openai-codex/gpt-5.6-sol:xhigh` |
| GPT-5.5 | `openai-codex/gpt-5.5:xhigh` |
| GLM 5.2 | `fireworks/accounts/fireworks/models/glm-5p2:xhigh` |
| GLM 5.2 Fast | `fireworks/accounts/fireworks/routers/glm-5p2-fast:medium` |

**Reasoning level on Fast models:** prefer `:medium` over `:xhigh` — a fast router model's value is speed, which `xhigh` defeats. So for a Fast worker pass `--model …glm-5p2-fast:medium` explicitly (the `xhigh` default is for the non-fast GPT/GLM models).

**Session id / transcript.** herdr's pi integration reports the session **path** (install once: `herdr integration install pi`); sessions live at `~/.pi/agent/sessions/--<cwd-with-dashes>--/<ts>_<session-id>.jsonl`. Pi writes the JSONL on its **first assistant reply**, not at boot. Pi has no permission-bypass flag; its permission model is governed elsewhere.

**Startup banner.** A pi "Update Available" banner can swallow the first prompt's keystrokes; dispatch's interactive-ready gate and `supervisr send`'s brief `agent_not_ready` retry ride over it.

## 2. Send a message

`supervisr send <name> "<message>"` via herdr `agent.prompt`; `--wait` uses the effect-gate + settle. When pi is mid-task, an incoming message may route to its **steering buffer** (which can split a paste on blank lines into separate steering events) — for long directives during active work, prefer an idle moment.

## 3. Read state

- **Persisted:** `supervisr watch <name>` reads the **active branch** of the pi session JSONL (the JSONL is a tree keyed by `id`/`parentId`; the adapter walks back from the latest entry to the root). Displayed types: `message` (roles `user`/`assistant`/`toolResult`/`bashExecution`), `model_change`, `thinking_level_change`, `compaction`, `branch_summary`. If the active branch changes (rare), the cursor entry may no longer be on it — `watch` tells you to `--reset` rather than silently jumping branches.
- **Live:** `supervisr screen <name>` for anomaly/liveness only.

## 4. Measure context fill

`supervisr status`/`sweep` report `ctx=<used>/<window>(<pct>%)` for pi with **no sidecar** — the window resolves through pi's local model registry on every read (so a model change or compaction is reflected without re-registering). Used = `input + cacheRead` of the most recent assistant turn (additive). If no denominator resolves, status shows `ctx=<used>/?`.

### Which regime applies to which model — this changes WHEN you compact

- **GPT models on the OpenAI codex sub** (gpt-5.6-sol, gpt-5.5, gpt-5.4) are capped by OpenAI at **272k–376k** actual context, even though the same models can reach ~1M via direct API and even if a local model-metadata override claims 1M. So on the codex sub, **GPT workers are the small-window regime below.**
- The **1M-window rollback heuristic** applies only to models that actually get a 1M window at runtime — currently **GLM 5.2 and GLM 5.2 Fast via Fireworks** (both report 1.0M).

**1M-window models (GLM 5.2): rollback risk.** Pi tends to develop "rollback glitches" (regenerating earlier behavior as if state rolled back) once context gets deep — empirically past roughly **30–40%** on a 1M window with many tool turns. Use the percentage as one signal among several (have you actually seen rollback symptoms, how many tool calls deep, is the work coherent).

**Small-window models (272k GPT on codex sub): forced-compaction risk, not rollback.** The failure mode flips:
- Rollback is not the concern — the model hits exhaustion before it accumulates rollback-triggering cruft.
- **Forced compaction at the wrong time is.** The runtime force-compacts near the limit (~≥90%, ~244k on a 272k window); a forced mid-task compact truncates whatever state the worker was holding, and it resumes a half-finished operation lossily.
- **Policy: compact opportunistically at a breakpoint** the supervisor recognizes (a slice committed, a phase wrapped, next assignment queued) rather than waiting for the forced compact. On small-window workers, if ctx is ≥60–70% and the worker is between assignments, prefer to compact now. This is the exception to "don't compact on a percentage" — that guidance is for 1M-window workers where the failure mode is different.

**Overflow / hard failure.** Pi may run **past 100%** of its nominal window (a 272k worker observed at 113%) before the runtime declares `Context overflow` and auto-compacts, so >100% is not itself a fault. Auto-compaction can fail outright (`Compaction failed: …`); a worker in that state is unrecoverable by supervision — retire it and launch a replacement. The real defence is arranging that a worker's memory is never load-bearing (durable state on disk, commits pushed as made, briefs re-seeded from files), so replacement costs a relaunch and nothing else.

## 5. `/compact`

Same `core.md` rule: the model cannot self-compact; the supervisor submits the isolated `supervisr send <name> "/compact"` when idle. Verify pi shows `⠴ Compacting context...` via `supervisr screen`; the operation takes 30s–2min on a deep context; when done the percentage drops sharply. Do not compact pre-emptively on a percentage for 1M-window workers; small-window between-assignments is the exception above. Document any compact you trigger with `supervisr note --tag supervisor`.

### NEVER send Escape while a compaction is running — Escape is its cancel key

The indicator says `(escape to cancel)` and means it. A supervisor reaching for Escape as a generic "unstick" gesture **cancels the compaction**, silently as far as status is concerned (the worker keeps reading idle, context stays deep). Two situations look identical from outside — a worker that is compacting, and the post-compaction phantom state where sends stack unsubmitted — and the phantom-state recovery (Escape then Enter) is exactly wrong for the first. **Distinguish before touching the pane**, reading scrollback not just the last lines:

```bash
supervisr screen <name> --lines 30    # look for compaction text
```
- `⠴ Compacting context...` / `Context overflow detected, Auto-compacting...` → hands off entirely; wait it out (minutes on deep contexts).
- `Queued message for after compaction` → your send is parked behind an in-flight compaction; it delivers when that finishes. Sending again just queues more.
- `Error: Compaction cancelled` → something cancelled it (most likely a supervisor keystroke); stop touching it, the runtime generally retries.
- No compaction text, worker idle, sends not landing → *now* the phantom state applies and `supervisr interrupt <name>` (Escape) then a resend is the right recovery.

## 6. Quirks

- **Post-compaction phantom state** — after a compaction pi can read idle/busy with a still pane while everything you send stacks unsubmitted. Recovery: `supervisr interrupt <name>` (Escape) to flush the queue into the composer, then resend — **only after confirming no compaction is running** (above).
- **Long server-side thinking pauses (gpt-5.5-class)** — a single reasoning step can take **20+ minutes** with a still pane, frozen ctx/cost, and no new JSONL entries. This is normal deep reasoning, not a stall — allow up to **~40 minutes** before treating it as hung, then `supervisr interrupt <name>` (Escape) to break the stuck generation and nudge a retry. To reduce opaque thinking, instruct pi workers to prefer several shorter tool calls over one massive reasoning burst — visible incremental progress is easier to supervise.
- **`/name` doesn't fully persist alone** — to make a named session show in `/resume`, send at least one real message after naming.
- **Branch switches** — rare in normal supervision; the adapter detects a cursor off the active branch and asks for `--reset`.

## 7. Done signals

- Final `[assistant]` entry with no trailing tool call; `supervisr status` `turn=idle` and herdr `done`/`idle`; working tree clean (verify read-only).

## 8. Stepping away / resume

herdr persists; a restart relaunches with `pi --session <id>` from the reported session. No pause/resume CLI. Resuming restores the model/level the session was launched with (pi persists `model_change`), so no `--model` at resume. End with `supervisr stop <name> --close-pane`.

## 9. Kickoff additions (Pi)

Append to the core kickoff:

```
9. You were launched with an explicit model (e.g. openai-codex/gpt-5.6-sol:xhigh), which sets your
   reasoning level; use pi --thinking only to raise effort beyond the launch setting.
10. The supervisor reads your active-branch JSONL (via supervisr) and can read your pane.
11. When you complete a phase, summarize in a final assistant turn so the done signal is clear.
12. Prefer several shorter tool calls over one long silent reasoning burst.
```
