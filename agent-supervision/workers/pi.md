# Worker — Pi

Pi as the supervised agent.

## 1. Transports used

- `transports/tmux.md` — Pi runs in a tmux pane (live signal + sending messages)
- `transports/jsonl.md` — Pi persists sessions to JSONL (authoritative content)

## 2. Launch

`superv` does not launch agents. The operator launches pi using whichever flags fit the task; `superv register` attaches the running pi to the supervision tooling afterward.

**Always launch pi with an explicit `--model`.** A bare `pi` inherits whatever model and reasoning level were last used interactively, so a worker launched without `--model` silently picks up whatever you were last experimenting with — non-reproducible and easy to miss. The model string encodes both the model and the reasoning level, e.g. `openai-codex/gpt-5.6-sol:xhigh` selects gpt-5.6-sol at xhigh reasoning. (The `triad` CLI automates this; see the `agent-triad` skill.)

Known Pi models (use the one the user asks for; default to GPT-5.6 Sol):

| Ask | `--model` value |
|---|---|
| GPT-5.6 Sol (default) | `openai-codex/gpt-5.6-sol:xhigh` |
| GPT-5.5 | `openai-codex/gpt-5.5:xhigh` |
| GLM 5.2 | `fireworks/accounts/fireworks/models/glm-5p2:xhigh` |
| GLM 5.2 Fast | `fireworks/accounts/fireworks/routers/glm-5p2-fast:medium` |

So if the user asks for a "GLM Pi worker", launch it with `pi --model fireworks/accounts/fireworks/models/glm-5p2:xhigh "<prompt>"`.

**Reasoning level on Fast models:** prefer `:medium` over `:xhigh`. The point of a fast router model is speed; `xhigh` reasoning defeats it. Use `:medium` for Fast variants unless the task genuinely needs deeper reasoning and you're willing to give up the speed advantage. The `:xhigh` default above is for the non-fast GPT/GLM models where reasoning depth is the value.

**Standard launch pattern** (tmux + seeded interactive prompt):

```bash
# 1. Create a background tmux window for the worker.
tmux new-window -t <session> -n pi-worker -d

# 2. Start pi inside that window. Pi supports "seeded interactive" mode —
#    pass the prompt as a positional arg (no -p flag) and pi boots the full
#    TUI, then immediately sends the prompt. This is the standard worker
#    launch shape. Always pass --model explicitly.
tmux send-keys -t <session>:pi-worker.0 \
  'cd /path/to/workdir && pi --model openai-codex/gpt-5.6-sol:xhigh "<initial prompt>"' Enter
```

**Common flags:**

| Flag | Purpose |
|---|---|
| `--model <model[:level]>` | Model and reasoning level, e.g. `openai-codex/gpt-5.6-sol:xhigh` (default) or `fireworks/accounts/fireworks/models/glm-5p2:xhigh` (GLM 5.2). **Always pass this** so the worker doesn't inherit the last interactive setting. The optional `:level` suffix sets reasoning effort inline. |
| `--thinking <level>` | Reasoning effort: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`. Use `xhigh` when the task needs maximum reasoning. Redundant if the reasoning level is already set via the `--model` suffix. |
| (positional prompt) | First turn the TUI runs after boot. Pi's "seeded" mode — no flag needed. |

Pi has no permission-bypass flag analogous to `--yolo` or `--dangerously-skip-permissions`; pi's permission model is governed elsewhere.

**Readiness marker:** the pi TUI shows `escape interrupt` in the status bar once it's accepting input. If you launched without a seeded prompt and want to send one programmatically, poll the pane until you see that marker before `tmux send-keys`.

**After launch**, once pi has produced its first turn (so the JSONL exists at `~/.pi/agent/sessions/--<cwd>--/<ts>_<id>.jsonl`):

```bash
superv register <id> --kind pi --tmux <session>:pi-worker.0
```

## 3. Identify

Pi sessions live under:

```
~/.pi/agent/sessions/--<cwd-with-dashes>--/<timestamp>_<session-id>.jsonl
```

Where `<cwd-with-dashes>` is the absolute cwd's `/` replaced by `-`, surrounded by `--`. The latest file in the directory is the active one for that cwd.

`superv register --kind pi --tmux <target>` does this lookup automatically: it reads the pane's cwd via `tmux display-message -p '#{pane_current_path}'` and picks the newest matching JSONL.

## 4. Send a message

Once Pi is idle (`superv status <id>` shows `turn=idle`):

```
superv send <id> "<message>"              # any text via tmux paste-buffer (single or multi-line)
superv send <id> --file path.md           # read message from a file (convenience)
```

`superv send` uses tmux's paste-buffer mechanism so newlines are preserved as soft newlines and only the trailing Enter submits. Note: when pi is mid-task, incoming messages may route to its **steering buffer**, which has its own behavior (e.g. it may split a paste on blank lines into separate steering events). For long supervisory directives during active work, send during an idle moment if possible.

## 5. Read live state

`superv watch <id> --live` captures the tmux pane for anomaly/liveness checks:

- The TUI status bar at the bottom — token counts, model name, cost.
- Permission/crash/error text or an unexpected prompt.
- The compose prompt and other visible UI context.

Busy/idle comes from transcript turn-state in the JSONL (`superv status <id>` prints `turn=busy|idle|unknown`), not from spinner glyphs in the captured pane.

## 6. Read persisted state

`superv watch <id>` reads the active branch of the Pi session JSONL. The JSONL is a tree (entries have `id`/`parentId`); the adapter walks back from the latest entry to the root via `parentId` to extract the active branch.

Entry types displayed: `message`, `model_change`, `thinking_level_change`, `compaction`, `branch_summary`, `session_info`, `custom_message`, `label`. Within a `message`, roles include `user`, `assistant`, `toolResult`, `bashExecution`, `custom`.

`superv detail <id> <entry-or-toolcall-id>` shows full content.

## 7. Context-window observation and `/compact`

`superv status <id>` prints `ctx=Nk` — the prompt token count for the most recent assistant turn (the next turn's prompt size). Use it for context-pressure decisions.

```
$ superv status dave
id=dave kind=pi status=running turn=busy persisted_age=0.5m ctx=271k
```

Internally that reads `input + cacheRead` from the most recent assistant turn's `message.usage` block in the JSONL (verified additive: `totalTokens = input + cacheRead + output`).

Pi's JSONL doesn't include the model context window, but Pi's TUI status bar does. `superv register --kind pi` parses the `46.8%/1.0M` fragment from a tmux capture and caches the window in the registry — so subsequent `superv status` calls show the percentage automatically:

```
↑11M ↓1.2M R806M $255.445 (sub) 46.8%/1.0M (auto)                                                       (openai-codex) gpt-5.4 • medium
$ superv status dave
id=dave kind=pi status=running turn=busy persisted_age=0.5m ctx=271k/1000k(27%)
```

If Pi switches model mid-session to one with a different window (`/model`), the cached value goes stale until you re-register. If the parse fails at register (status bar not yet rendered, unusual layout), superv just stores no window and falls back to printing raw tokens.

### Which regime applies to which model

The GPT models on the **OpenAI codex sub** (gpt-5.6-sol, gpt-5.5, gpt-5.4) are capped by OpenAI at **272k–376k** of actual context, even though the same models can reach ~1.05M via direct API access, and even if a local pi model-metadata override claims 1M. So on the codex sub, **GPT workers always land in the small-window regime below** — the 1M rollback heuristic in this section does not apply to them.

The 1M-window rollback heuristic applies only to models that actually receive a 1M window at runtime — currently **GLM 5.2 and GLM 5.2 Fast via Fireworks** (both report 1.0M in pi's model list). Treat those with the deep-context guidance below.

### Deep-context warning signs (1M-window models, e.g. GLM 5.2)

Pi tends to develop "rollback glitches" (regenerating earlier behavior as if state was rolled back, see core.md anti-patterns) once the context window gets deep. Empirically the rollback risk climbs noticeably past roughly 30–40% on a 1M window when the session has accumulated many tool turns. Exact thresholds vary by workload; use the percentage as one signal among several (the others being: have you actually seen rollback symptoms, how many tool calls deep is the session, is the work coherent or scattered).

### Small context windows (e.g. 272k — GPT models on codex sub)

The 30–40% rollback heuristic above is anchored to 1M-window models with deep accumulated history. On smaller windows — and **this is the normal regime for GPT models on the OpenAI codex sub** (gpt-5.6-sol at 376k, gpt-5.5 at 272k, gpt-5.4 capped similarly) — the failure mode flips:

- **Rollback risk is not the primary concern.** The model hits context exhaustion long before it accumulates the kind of cruft that triggers rollback.
- **Forced compaction at the wrong time is.** The runtime will force a compact when the worker gets near the window limit (roughly ≥90% — ~244k on a 272k window). A forced mid-task compact truncates whatever state the worker was actively holding; the worker resumes a half-finished operation with a lossy memory of where it was, and tends to redo or skip steps it had partially completed.

**Policy: compact opportunistically at break points the supervisor recognizes, rather than waiting for the forced compact.**

A "break point" is a moment when the worker just landed a self-contained unit of work and is about to start a new one — a slice just committed, a phase wrapped, the next assignment is queued. At those moments the supervisor can send `/compact` before dispatching the next task. The worker enters with a clean summary and full window headroom, and the next-task brief reseeds whatever state the new work needs.

Concretely: on small-window workers, if ctx is approaching the danger zone (≥60–70%) and the worker is between assignments, prefer to compact now rather than risk a forced compact halfway through the next assignment. This is an explicit exception to the "don't compact on a percentage threshold" guidance below — that guidance was written for 1M-window workers where the failure mode is different.

### Triggering `/compact`

#### Hard rule: `/compact` must be the entire submitted command

A supervised agent **cannot compact itself in response to natural-language instructions**. The model has no mechanism for invoking its own TUI slash commands. Telling it “run `/compact`,” “compact at the next breakpoint,” or any equivalent instruction fundamentally does not work. Including the text `/compact` inside a longer message does not turn that message into a slash command, even if `/compact` has a leading slash.

Compaction happens only when the supervisor submits the literal `/compact` slash command in isolation as the complete TUI input:

```bash
superv send <id> "/compact"
```

Do not add a prefix, suffix, explanation, or second instruction to that submission. Send any follow-up such as `Continue.` separately after compaction finishes.

Wait until the worker is idle before sending `/compact`. If Pi is busy, incoming text can enter its steering buffer as an ordinary message rather than execute as a TUI slash command. Do not ask the worker to self-compact as a workaround; wait for an idle breakpoint and submit the isolated command yourself.

After sending, verify with `superv watch <id> --live` that Pi displays `⠴ Compacting context... (escape to cancel)`. The operation typically takes 30s–2min on a deep context. When it finishes, the status-bar percentage drops substantially (often to single digits) and the prompt area returns to idle. Verify again with `superv watch <id> --live`, then send any continuation instruction as a separate message.

### When to actually do this

**Only if instructed by the user's monitoring goals.** Compaction is a destructive context operation: pi loses fine-grained recall of earlier turns and replaces it with a summary. That can break in-flight tasks if pi was holding onto state the supervisor expected it to remember. Don't compact unilaterally on a percentage threshold.

Appropriate triggers:

- The user has told you (in conversation, in the supervisor notes file, or in a heartbeat prompt) that you may compact when context gets deep.
- You have observed rollback glitches (per core.md) and the user has authorized state-restoring interventions.
- The user explicitly asks for a compact ("trigger /compact for pi", "have pi compact before next file", etc.).
- **Small-window workers between assignments:** the worker just landed a self-contained unit (slice committed, phase wrapped) and ctx is in the danger zone for that window's forced-compact threshold. See "Small context windows" above.

Do **not** compact:

- Pre-emptively as a precaution without being told to.
- Mid-task when pi is holding state the user is depending on (e.g., halfway through a multi-spec workflow with cross-file references in context).
- Just because the percentage looks high on a 1M-window worker with no symptoms. (Small-window workers are different — see above.)

Document any compact you trigger in `superv note --tag supervisor` so the user can correlate it with later behavior.

## 8. Quirks

- **`/name` doesn't fully persist alone** — to make a named session show up later in `/resume`, send at least one real message after naming it.
- **Branch switches** — if the active branch changes (rare in normal supervision), the cursor entry may no longer be on the active branch. The adapter detects this and tells you to reset via `superv watch <id> --reset` rather than silently jumping branches.
- **TUI chrome strips during live capture** — `tmux-poll` removes the bottom separator pair and status bar before snapshot anchoring; this is automatic and not normally a concern.
- **Busy/idle is transcript-derived** — `superv status` reads the active JSONL branch as a turn-state machine. Pane spinners are useful UI context only, not the authoritative busy signal.
- **Long server-side thinking pauses (gpt-5.5)** — when Pi is running gpt-5.5 (or similar reasoning models), a single thinking step can take 20 minutes or more. During this time the transcript turn-state remains `busy`, the cost counter and context percentage may be frozen, no new JSONL entries appear, and the live pane content may not change. This is normal deep-reasoning behavior, not a stall. **Allow up to 40 minutes** before treating it as hung. After 40 minutes with no progress (no new JSONL entry, no cost/ctx change), send `Escape` to the tmux pane to interrupt the stuck generation: `tmux send-keys -t <target> Escape`. The worker will recover and can be nudged to retry. Note: to reduce opaque thinking phases, instruct Pi workers to prefer multiple shorter tool calls over single massive reasoning sessions — visible incremental progress is easier to supervise than long silent thinking.

## 9. Done signals

- Final `[assistant]` entry with no trailing `toolCall`.
- `superv status` reports `turn=idle` (final assistant message with no pending tool calls).
- Working tree clean (verify with `git status` read-only).

## 9b. Pause / resume

Pi supports session resume by UUID. The supervisor wraps this via `superv pause` / `superv resume` (see `core.md`). Pausing mid-turn discards the in-flight turn, so operators typically pause at a quiet moment — the tool does not check or block.

- **Resume command shape**: `pi --session <uuid>`. The `<uuid>` is the trailing part of the JSONL filename `<timestamp>_<uuid>.jsonl`.
- **No `--model` at resume.** Resuming a session restores the model and reasoning level it was launched with (Pi persists `model_change`/`thinking_level_change` in the JSONL), so the explicit `--model` belongs at first launch, not at resume.
- **Cwd-independent for *finding*** the session — Pi searches by partial UUID across `~/.pi/agent/sessions/`.
- **But run resume in the original cwd** for cleanest behavior. The session metadata remembers the cwd it was created in; resuming elsewhere makes file paths and git context inconsistent. `superv resume` defaults to the stored cwd.
- **Pi has no permission-bypass flag** like Claude's `--dangerously-skip-permissions` — Pi's permission model is governed elsewhere; nothing extra is needed at resume time.

## 10. Kickoff template (Pi-flavored additions)

Append to the core kickoff:

```
8. You were launched with an explicit model (e.g. `pi --model openai-codex/gpt-5.6-sol:xhigh`),
   which already sets your reasoning level; use `pi --thinking xhigh` only if you need to
   raise effort beyond what the launch set.
9. The supervisor reads your active-branch JSONL and live tmux pane — both are observed.
10. When you complete a phase, summarize in a final assistant turn so the supervisor's
    persisted-history check picks up a clear done signal.
```
