# Worker — Codex (OpenAI Codex CLI)

Codex CLI as the supervised agent.

## 1. Transports used

- `transports/tmux.md` — Codex TUI runs in a tmux pane (live + send for the interactive form)
- `transports/jsonl.md` — Codex persists "rollouts" to JSONL (authoritative content)

## 2. Launch

`superv` does not launch agents. The operator launches codex using whichever flags fit the task; `superv register` attaches the running codex to the supervision tooling afterward.

**Standard launch pattern** (tmux + interactive TUI):

```bash
# 1. Create a background tmux window for the worker.
tmux new-window -t <session> -n codex-worker -d

# 2. Start codex inside that window. Codex accepts an optional positional
#    initial prompt — pass it after the flags, like pi's seeded mode:
tmux send-keys -t <session>:codex-worker.0 \
  'cd /path/to/repo && codex --yolo "<initial prompt>"' Enter
# Or launch without a seeded prompt and send the kickoff afterward via
# 'superv send' (or another 'tmux send-keys'):
#   tmux send-keys -t <session>:codex-worker.0 'cd /path && codex --yolo' Enter
```

**Common flags:**

| Flag | Purpose |
|---|---|
| `--yolo` | Alias for `--dangerously-bypass-approvals-and-sandbox`. Disables sandbox + approval prompts. **Standard for autonomous workers** — without it, codex will block on every tool call. |
| `-m, --model <id>` | Pick a specific model (e.g. `gpt-5.4`). Default comes from `~/.codex/config.toml`. |
| `-C, --cd <DIR>` | Set the working directory explicitly (alternative to `cd` in the shell). |
| `--full-auto` | Convenience: `-a on-request --sandbox workspace-write`. Less aggressive than `--yolo`. |
| `-s, --sandbox <mode>` | Sandbox policy: `read-only`, `workspace-write`, `danger-full-access`. |
| `-a, --ask-for-approval <policy>` | Approval policy: `untrusted`, `on-request`, `never`. `--yolo` implies `never`. |
| `-c <key>=<value>` | Override any config key from `~/.codex/config.toml`. See "Reasoning effort" below. |
| `[PROMPT]` | Optional positional prompt — codex DOES accept a positional first prompt at TUI launch. |

**Reasoning effort:** codex has no dedicated CLI flag. It's a config value, settable three ways:

1. Per-invocation via `-c`:
   ```bash
   codex --yolo -c model_reasoning_effort=high
   ```
2. Persistently in `~/.codex/config.toml` under the model section.
3. Some model names accept an effort suffix in `--model` (form depends on model; check current Codex docs).

The exact accepted values for `model_reasoning_effort` depend on the model and may evolve — `low`, `medium`, `high` are commonly available. Run `codex --help` and check `~/.codex/config.toml` examples for current options.

**One-shot exec mode** (not for long-running workers — useful as a supervisor's own verification query):

```bash
echo "<prompt>" | codex exec --json -o output.txt
# First JSONL event is type=thread.started with the thread_id.
# Resume that thread:
echo "<follow-up>" | codex exec resume <thread-id>
```

**First-prompt protocol:** codex won't write a rollout JSONL until it has produced its first turn, so `superv register` will fail until then. Two paths:

```bash
# A) Seeded launch — pass the prompt positionally (preferred when you have
#    the kickoff ready):
tmux send-keys -t <session>:codex-worker.0 \
  'cd /path && codex --yolo "<initial prompt>"' Enter

# B) Bare launch, then send-keys the prompt afterward:
tmux send-keys -t <session>:codex-worker.0 'cd /path && codex --yolo' Enter
# (briefly capture-pane to confirm the composer is ready)
tmux send-keys -t <session>:codex-worker.0 '<initial prompt>' Enter
```

After the first turn has streamed back (rollout JSONL now exists at `~/.codex/sessions/YYYY/MM/DD/rollout-...jsonl`):

```bash
superv register <id> --kind codex --tmux <session>:codex-worker.0
```

**Submission verification (codex-specific quirk):** in practice we've observed codex sometimes leaves the prompt in the composer after `Enter` rather than submitting — most often when there's a startup banner (e.g. an "update available" prompt) that consumes the keystrokes. After sending, `tmux capture-pane` to verify the prompt cleared from the composer; if it didn't, send a bare `Enter` and re-check.

## 3. Identify

Codex rollouts live at:

```
~/.codex/sessions/YYYY/MM/DD/rollout-<ISO-ts>-<session-id>.jsonl
```

The first JSONL line is `type=session_meta` with `payload.id`, `payload.cwd`, `payload.originator` (e.g. `codex-tui`), and `payload.git`. The latest rollout under today's date with matching `cwd` is the active one.

`superv register --kind codex --tmux <target>` does this lookup automatically: it reads the pane's cwd and scans recent rollouts for a match by `payload.cwd`.

## 4. Send a message

Same as Pi — Codex TUI listens to keystrokes:

```
superv send <id> "<message>"       # any text via tmux paste-buffer (single or multi-line)
superv send <id> --file path.md    # read message from a file (convenience)
```

## 5. Read live state

`superv watch <id> --live` captures the tmux pane for anomaly/liveness checks. Codex shows:

- A token-count footer line (similar to Pi).
- Tool / shell call previews inline.
- Permission/crash/error text or unexpected prompts.

Busy/idle comes from rollout turn-state (`superv status <id>` prints `turn=busy|idle|unknown`), not from live-pane activity indicators.

## 6. Read persisted state

`superv watch <id>` reads the rollout JSONL. Entry shapes:

- `type=session_meta` — header (skipped from display after parsing).
- `type=event_msg` with `payload.type` ∈ {`task_started`, `user_message`, `token_count`, `task_complete`, ...}.
- `type=response_item` with `payload.type` ∈ {`message`, `reasoning`, `function_call`, `function_call_output`}.
- `type=turn_context` — turn metadata (cwd, approval policy).

Display surface: user messages (`event_msg.user_message` and `response_item.message` with role=user), assistant messages (`response_item.message` role=assistant, content array of `output_text`), tool calls (`response_item.function_call`), tool outputs (`response_item.function_call_output`). Reasoning is skipped by default (analogous to Claude's `thinking`).

## 6b. Measure context fill

`superv status <id>` prints `ctx=Nk/Mk(P%)` for Codex — both the prompt token count and the percentage of the model's context window consumed. Codex's JSONL conveniently includes both numbers, so you get the percentage automatically (Claude and Pi only get raw tokens because their JSONLs don't include the model window).

```
$ superv status codex-worker
id=codex-worker kind=codex status=running turn=busy persisted_age=0.4m ctx=25k/258k(10%)
```

Internally that reads the most recent `event_msg` of `payload.type=token_count`:
- `info.last_token_usage.input_tokens` — most recent prompt size (input_tokens already includes cached_input_tokens as a subset; do NOT add them)
- `info.model_context_window` — the window size

If you only want the cumulative-across-turns count, use `info.total_token_usage.input_tokens` instead — but for staging decisions you want the per-turn prompt size, which is what superv reports.

## 7. Quirks

- **Rollouts are date-bucketed** — a single Codex session can span midnight and produce two files. Adapter follows the active session by `payload.id` from the meta line, not by file mtime alone.
- **No tree/branch model** — Codex rollouts are linear, simpler than Pi's branch tree.
- **Cwd lock-in** — the cwd from `session_meta` is the canonical project; verifications should use that path.
- **`codex exec resume`** can resume a thread by id outside the TUI for one-shot follow-ups. Useful for the supervisor's own verification queries.

## 8. Done signals

- `event_msg.task_complete` for the active turn.
- Final assistant message in `response_item`.
- `superv status` reports `turn=idle` (usually after `event_msg.task_complete` or a final assistant message).

## 8b. Pause / resume

Codex supports session resume by UUID. The supervisor wraps this via `superv pause` / `superv resume` (see `core.md`).

- **Resume command shape**: `codex resume <uuid> --dangerously-bypass-approvals-and-sandbox`. Note this is a subcommand (`codex resume`), not a flag (`codex --resume`).
- The `<uuid>` is the UUID portion of the rollout filename: `rollout-<ISO-ts>-<uuid>.jsonl` — the last 5 dash-separated tokens of the stem (UUIDs have 4 dashes).
- **`codex resume --last`** picks the most recent session in the current cwd interactively; not used by `superv resume` because we want explicit ID-based resume.
- **`codex exec resume <thread-id>`** is the *non-interactive* form — useful for the supervisor's own one-shot verification queries, not for re-launching a long-running TUI worker.
- Run resume in the original cwd for cleanest behavior; `superv resume` defaults to the stored cwd.

## 9. Kickoff template (Codex-flavored additions)

Append to the core kickoff:

```
8. You are running with --yolo; sandboxing and approvals are off, you have full access.
9. The supervisor reads your rollout JSONL and live tmux pane.
10. When done, end your final turn with a clear summary — the supervisor uses
    task_complete + assistant text as a done signal.
```
