# Worker — Pi

Pi as the supervised agent.

## 1. Transports used

- `transports/tmux.md` — Pi runs in a tmux pane (live signal + sending messages)
- `transports/jsonl.md` — Pi persists sessions to JSONL (authoritative content)

## 2. Launch

`superv` does not launch agents. The operator launches pi using whichever flags fit the task; `superv register` attaches the running pi to the supervision tooling afterward.

**Always launch pi with an explicit `--model`.** A bare `pi` inherits whatever model and reasoning level were last used interactively, so a worker launched without `--model` silently picks up whatever you were last experimenting with — non-reproducible and easy to miss. The model string encodes both the model and the reasoning level, e.g. `openai-codex/gpt-5.6-sol:xhigh` selects gpt-5.6-sol at xhigh reasoning. (The `triad` CLI automates this; see the `tmux-agent-triad` skill.)

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
#    launch shape. Always pass --model explicitly, and ALWAYS seed an explicit
#    --session-id — it is the only thing that lets registration bind this pane
#    to exactly this worker's transcript (see "Identify" below).
#
#    Launch cwd: the WORKTREES' PARENT folder (e.g. ~/workspace/wt/<repo>/),
#    not the task worktree itself. Worktrees are often shorter-lived than the
#    agent sessions that operate over them; a worker homed inside one is
#    stranded (shell and cwd-keyed session files) when the worktree is deleted.
#    The trade: the worker cannot infer its worktree from its cwd, so the
#    initial prompt / task brief MUST state the worktree's absolute path.
SID="pi-worker-$(uuidgen)"
tmux send-keys -t <session>:pi-worker.0 \
  'cd /path/to/wt-parent && pi --model openai-codex/gpt-5.6-sol:xhigh --session-id '"$SID"' "<initial prompt naming the worktree path>"' Enter
```

**Common flags:**

| Flag | Purpose |
|---|---|
| `--model <model[:level]>` | Model and reasoning level, e.g. `openai-codex/gpt-5.6-sol:xhigh` (default) or `fireworks/accounts/fireworks/models/glm-5p2:xhigh` (GLM 5.2). **Always pass this** so the worker doesn't inherit the last interactive setting. The optional `:level` suffix sets reasoning effort inline. |
| `--session-id <id>` | Exact session id for the new session (pi creates it if missing). **Always pass this for supervised workers** — it is the identity handshake that `superv register --session-id` binds on. Ids are alphanumeric plus `-`/`_`/`.`; a good shape is `<worker-name>-<uuid>`. |
| `--thinking <level>` | Reasoning effort: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`. Use `xhigh` when the task needs maximum reasoning. Redundant if the reasoning level is already set via the `--model` suffix. |
| (positional prompt) | First turn the TUI runs after boot. Pi's "seeded" mode — no flag needed. |

Pi has no permission-bypass flag analogous to `--yolo` or `--dangerously-skip-permissions`; pi's permission model is governed elsewhere.

**Readiness marker:** the pi TUI shows `escape interrupt` in the status bar once it's accepting input. If you launched without a seeded prompt and want to send one programmatically, poll the pane until you see that marker before `tmux send-keys`.

**After launch**, once pi has produced its first turn (pi writes the JSONL on its **first assistant reply**, not at boot — so the file exists only after that reply lands):

```bash
superv register <name> --kind pi --tmux <session>:pi-worker.0 --session-id "$SID"
```

## 3. Identify

Pi sessions live under:

```
~/.pi/agent/sessions/--<cwd-with-dashes>--/<timestamp>_<session-id>.jsonl
```

Where `<cwd-with-dashes>` is the absolute cwd's `/` replaced by `-`, surrounded by `--`. The `<session-id>` in the filename (also in the file's header line) is the session's identity.

**Identity is established at launch, never inferred afterwards.** `superv register --kind pi` requires an exact identity — `--session-id <id>` (the id the worker was launched with) or `--path <file>` — and resolves it by matching the id in both the filename and the session header, cross-checked against the pane's cwd. Without an identity, registration **fails closed**: it lists the candidate files it can see but never picks one.

Why no auto-resolution exists: several pi agents may share one cwd (parallel workers in one worktree is a normal setup), pi doesn't flush a fresh session's JSONL until the first assistant reply (so a stale transcript can be the only file on disk during launch), and a running pi process can't be interrogated after the fact — pi rewrites its process title at startup, erasing launch flags from the process table, holds no open handle to its transcript, and exports no session id. "Newest file in the cwd's directory" therefore misbinds exactly when it matters, and superv no longer does it — at registration or any later point (if a bound transcript disappears, watch/status fail loudly instead of re-resolving by recency).

For an already-running pi launched **without** `--session-id`: the operator can run `/session` inside its TUI to see the session file, then register with `--path <file>`. A worker launched with a custom `pi --session-dir <dir>` registers with the same `--session-dir` value.

Registration also refuses to bind a transcript that is already bound to another registered worker — two supervision handles on one transcript is the misbinding this design exists to prevent.

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

`superv detail <id> <entry-or-toolcall-id>` shows bounded supervisor-oriented content. Use the explicit `--raw --force` double override only when the persisted JSON itself is necessary.

## 7. Context-window observation and `/compact`

`superv status <id>` reports the exact unread-entry count and the most recent prompt size against the active model's context window. Use the percentage for context-pressure decisions and `unread` to decide which workers need `watch` during a sweep.

```
$ superv status dave
id=dave kind=pi status=running turn=busy persisted_age=0.5m unread=14 ctx=143k/272k(52%)
```

The prompt size is `input + cacheRead` from the most recent assistant turn's `message.usage` block in the JSONL (verified additive: `totalTokens = input + cacheRead + output`). The same persisted history identifies the current provider and model. `superv` resolves that model's `contextWindow` from Pi's local model registry on every status read, so a model change or compaction is reflected without capturing the pane or re-registering the worker.

The tmux status bar remains a registration-time fallback for context-window metadata. If no denominator can be resolved, status says so explicitly, for example `ctx=143k/?`.

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

#### NEVER send Escape while a compaction is running — Escape is its cancel key

The compaction indicator says `(escape to cancel)` and it means it. A supervisor who reaches for Escape as a generic "unstick the pane" gesture **cancels the compaction**, and does so silently as far as `superv status` is concerned — the worker keeps reading `idle`, the pane stays quiet, and the context stays deep. Repeat the gesture and you get a cancel loop that keeps a worker pinned over its limit indefinitely.

This bites because two different situations look identical from outside: a worker that is compacting, and a worker sitting in the post-compaction phantom state where sends stack unsubmitted (see § 8 Quirks). Both read `busy` or `idle` with a still pane and no new JSONL entries. The flush-and-submit recovery for the phantom state — `Escape` then `Enter` — is exactly the wrong move for the first.

**Always distinguish before touching the pane.** Read the scrollback, not just the last few lines:

```bash
tmux capture-pane -t <target> -p -S -20 | grep -iE 'compacting|compaction|context overflow'
```

- `⠴ Compacting context...` or `Context overflow detected, Auto-compacting...` → **hands off entirely.** No keystrokes, no sends. Wait it out; deep contexts can take minutes.
- `Queued message for after compaction` → your `/compact` (or any other send) is parked behind a compaction already in flight. It will deliver when that finishes. Sending again just queues more.
- `Error: Compaction cancelled` → something cancelled it, and the most likely something is a supervisor keystroke. Stop touching it; the runtime generally retries on its own.
- No compaction text at all, worker idle, sends not landing → *now* the phantom state applies and `Escape` then `Enter` is the right recovery.

#### Auto-compaction, overflow, and hard failure

Pi may run **past 100% of its nominal window** (a 272k worker observed working normally at 113%) before the runtime declares `Context overflow detected` and auto-compacts. So a percentage over 100 is not itself a fault, and interrupting a productive turn to force a compaction usually costs more than it saves.

Auto-compaction can fail outright — observed: `Error: Compaction failed: Cannot read properties of undefined (reading 'signal')`. A worker in that state is **unrecoverable by supervision**: it sits far over its window, ignores sends including direct status probes, and cannot compact its way down. Do not spend cycles nudging it. Retire it and launch a replacement.

The real defence is arranging beforehand that a worker's memory is never load-bearing, so replacement is cheap: durable task state on disk (see the context-file practice in `core.md`), commits pushed as they are made rather than batched, and briefs re-seeded from files rather than from conversation. When those hold, losing a worker costs a relaunch and nothing else.

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

- **Post-compaction phantom state** — after a compaction, Pi can land in a state where it reads `idle` (or `busy`) with a still pane while everything you send stacks in its steering buffer unsubmitted. Nothing lands; the worker looks like it is thinking and is not. Recovery is `tmux send-keys -t <target> Escape` to flush the queue into the composer, then `Enter` to submit. **Confirm no compaction is running first** — Escape cancels a compaction (see § 7).
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

- **Resume command shape**: `pi --session <uuid>`. The `<uuid>` is the trailing part of the JSONL filename `<timestamp>_<uuid>.jsonl`. (For a worker launched with a custom `--session-dir`, `superv resume` addresses the session file by path and re-supplies `--session-dir` automatically.)
- **Re-registering a resumed worker**: the resume id IS the session identity — register with `superv register <name> --kind pi --tmux <target> --session-id <uuid>`.
- **No `--model` at resume.** Resuming a session restores the model and reasoning level it was launched with (Pi persists `model_change`/`thinking_level_change` in the JSONL), so the explicit `--model` belongs at first launch, not at resume.
- **Cwd-independent for *finding*** the session — Pi searches by partial UUID across `~/.pi/agent/sessions/`.
- **But run resume in the stored cwd** for cleanest behavior; `superv resume` defaults to it. For workers launched the standard way, the stored cwd is the worktrees' parent folder — stable even after the task worktree rotates or is deleted, which is exactly why workers are homed there. Passing `--cwd` to relocate also re-resolves and rewrites the stored transcript path by session id (or refuses if it can't).
- **Pi has no permission-bypass flag** like Claude's `--dangerously-skip-permissions` — Pi's permission model is governed elsewhere; nothing extra is needed at resume time.

## 10. Kickoff template (Pi-flavored additions)

Append to the core kickoff:

```
9. You were launched with an explicit model (e.g. `pi --model openai-codex/gpt-5.6-sol:xhigh`),
   which already sets your reasoning level; use `pi --thinking xhigh` only if you need to
   raise effort beyond what the launch set.
10. The supervisor reads your active-branch JSONL and live tmux pane — both are observed.
11. When you complete a phase, summarize in a final assistant turn so the supervisor's
    persisted-history check picks up a clear done signal.
```
