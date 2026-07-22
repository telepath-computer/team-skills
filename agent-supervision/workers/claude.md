# Worker — Claude Code

Claude Code as the supervised agent.

## 1. Transports used

- `transports/jsonl.md` — persisted history (authoritative content)
- `transports/tmux.md` — only when Claude is running inside a tmux pane (live signal + sending messages)

## 2. Launch

`superv` does not launch agents. The operator launches Claude Code using whichever flags fit the task; `superv register` attaches the running Claude to the supervision tooling afterward.

**Standard launch pattern** (tmux + interactive TUI):

```bash
# 1. Create a background tmux window for the worker.
tmux new-window -t <session> -n claude-worker -d

# 2. Start Claude Code inside that window. The TUI does NOT take a positional
#    initial prompt — send the kickoff message afterward via 'superv send'.
tmux send-keys -t <session>:claude-worker.0 \
  'cd /path/to/repo && claude --dangerously-skip-permissions' Enter
```

**Common flags:**

| Flag | Purpose |
|---|---|
| `--dangerously-skip-permissions` | Disable per-tool permission prompts. **Standard for autonomous workers** — without it Claude blocks on every tool call. |
| `--effort <level>` | Reasoning effort level. Values: `low, medium, high, xhigh, max`. Use `high` or above when the task needs serious reasoning. |
| `--model <id>` | Pin a specific model. Accepts an alias (`sonnet`, `opus`) or full id (`claude-opus-4-7`, `claude-sonnet-4-6`). Default is whatever the user's config selects. |
| `--add-dir <path>` | Allow access to a directory outside the cwd (e.g. `--add-dir /home/user` when working in a subdir but needing parent-tree reads). |
| `--agent <name>` | Use a specific named agent for the session. |

**First-prompt protocol:** Claude's TUI doesn't take a seeded positional prompt. Launch the TUI, then send the kickoff via `superv send` (or directly via `tmux send-keys`) once it's running. Claude won't write a session JSONL until that first turn completes.

```bash
# After 'claude --dangerously-skip-permissions' is running:
# Easiest: register first, then send the kickoff via superv (handles multi-line via paste-buffer):
#   superv register <id> --kind claude --tmux <session>:claude-worker.0
#   superv send <id> "<kickoff message>"
#   # or: superv send <id> --file kickoff.md
# Bare tmux send-keys (single-line only) also works:
tmux send-keys -t <session>:claude-worker.0 '<initial one-line prompt>' Enter
```

**After launch**, once Claude has produced its first turn (so the JSONL exists at `~/.claude/projects/<cwd-key>/<sessionId>.jsonl`):

```bash
superv register <id> --kind claude --tmux <session>:claude-worker.0
```

`register` resolves the JSONL path automatically by reading `~/.claude/sessions/<pid>.json` for the running Claude process under the tmux pane.

**Before registering your first Claude worker on this machine**, install the agent-supervision statusLine so `superv register` can capture the model context window:

```bash
superv install-claude-statusline
```

One-time per machine. Without it, `superv status` only emits raw token counts; with it, `register` parses the window from the TUI status bar and `status` shows `ctx=Nk/Mk(P%)` with the percentage. See § 6b for details.

## 3. Identify

Map a tmux pane to the Claude session JSONL via the per-process metadata file:

1. `tmux list-panes -a -F '#{pane_pid} #{session_name}:#{window_index}.#{pane_index}'` → find the pane PID running `claude`.
2. The actual `claude` process is a child of the pane shell. Look one level deeper: `pgrep -P <pane_pid> claude` (or read `~/.claude/sessions/<claude-pid>.json`).
3. The metadata JSON has `sessionId` and `cwd`.
4. Resolve transcript: `~/.claude/projects/<cwd-key>/<sessionId>.jsonl`, where `<cwd-key>` is the absolute cwd with `/` replaced by `-` and a leading `-` (e.g., `/home/user/workspace/television` → `-home-user-workspace-television`).

`superv register --kind claude --tmux <target>` does this lookup automatically.

## 4. Send a message

Two paths:

- **Inside tmux** (most common): `superv send <id> "<message>"` — uses tmux's paste-buffer mechanism, so single-line and multi-line content both work. `superv send <id> --file path.md` reads the message from a file as a convenience.
- **Composer-Enter quirk**: Claude Code sometimes leaves a pasted prompt sitting in the composer even after the trailing Enter was sent. After sending, manually verify with `superv watch <id>` (looking for the new user-message entry) and `superv watch <id> --live` (looking at the composer state). If the prompt is still in the composer, send another bare `Enter` via `tmux send-keys -t <target> Enter`.

## 5. Read live state

`superv watch <id> --live` captures the tmux pane and looks for:

- The compose box (`❯ ` prompt) — visible when idle.
- Permission prompts ("Do you want to allow ...?") — needs user attention.
- Crash/error text, stuck composer contents, or other anomalies.

Busy/idle comes from transcript turn-state in the JSONL (`superv status <id>` prints `turn=busy|idle|unknown`), not from decorative activity lines in the captured pane.

Pane capture is **liveness only**. For content, always use the persisted JSONL.

### The ghost-text trap (CRITICAL — read before interpreting compose-box content)

Claude Code's TUI renders an **AI-suggested next prompt** inside the compose box when idle. It looks visually identical to typed input in a colorblind capture: same `❯ ` prefix, text after it. It is **not** queued input — it is a suggestion that the user can accept by pressing Tab, or dismiss by typing.

If you read this as real user input you will mis-supervise — repeatedly reporting "user has a pending message" when nobody typed anything. If you act on it ("submit it for them") you will inject a nonsense prompt the worker treats as authoritative. Both failure modes have happened in practice and burn supervision cycles for hours.

**Defaults you should change immediately:**

- `tmux capture-pane -p` strips color codes. Ghost text and real input look identical. **Never reason about compose-box content from `-p` alone.**
- `superv watch <id> --live` may also strip styling depending on its rendering path. If you need to determine whether compose-box content is real or ghost, drop to raw `tmux capture-pane` with `-e`.

**The detection rule:**

```bash
tmux capture-pane -t <pane> -p -e
```

The `-e` flag preserves SGR escape sequences. Find the line containing `❯ ` and look at what immediately precedes the suggestion text:

| What you see after `❯ ` | What it means |
|---|---|
| `\e[0;2m` or `\e[2m` (dim/faint attribute) | **Ghost text** — AI suggestion. Ignore. |
| Normal foreground (no `;2`) | **Real input** typed by user, awaiting Enter. |
| Empty / nothing after `❯ ` | Compose box is genuinely empty. |

The dim SGR (`2m`) is the reliable marker — `\e[0;2m` is "reset all attributes, then enable dim/faint." Real typed input is rendered without that attribute.

**One more cross-check:** if compose-box content is real-but-unsubmitted, it does **not** appear in the JSONL (the JSONL only records submitted user messages). If you see suspicious compose-box content, `superv watch <id>` (no `--live`) and grep for the suspect text. If it's not in the JSONL and the persisted_age keeps growing, it's almost certainly ghost text — reach for `-e` to confirm before reporting it.

## 6. Read persisted state

`superv watch <id>` (no `--live` flag) reads the JSONL via the Claude adapter. Entry types: `user`, `assistant`, `progress` (skipped), `file-history-snapshot` (skipped). Each entry is keyed by `uuid`, with `timestamp`, `message.role`, and `message.content` (an array of `text` / `tool_use` / `tool_result` blocks).

`superv detail <id> <uuid-or-tool-id>` drills into one entry — full text, full tool args, full tool result.

## 6b. Measure context fill

`superv status <id>` prints `ctx=Nk` — the prompt token count for the most recent assistant turn, which is what the next turn will read. Use it for any decision keyed on context pressure (compaction staging, reflection cadence, etc.).

```
$ superv status rover
id=rover kind=claude status=running turn=busy persisted_age=0.5m ctx=405k
```

Internally that reads `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` from the most recent assistant turn's `message.usage` block in the JSONL (those three fields are additive in the Claude schema). Equivalent to:

```bash
tail -5 ~/.claude/projects/<cwd-key>/<session-id>.jsonl \
  | jq -r 'select(.message.usage) | .message.usage | (.input_tokens + .cache_read_input_tokens + .cache_creation_input_tokens)' \
  | tail -1
```

**Claude's JSONL doesn't include the model context window**, but you can get auto-percentage by installing the agent-supervision statusLine. It writes `ctx:1000k`-style fragments into the Claude TUI status bar, which `superv register --kind claude` parses once and caches in the worker registry. After install:

```
$ superv install-claude-statusline       # one-time per machine
$ superv register rover --kind claude --tmux main:rover
   ... rec.extra.context_window_tokens = 1000000
$ superv status rover
id=rover kind=claude status=running turn=busy persisted_age=0.5m ctx=405k/1000k(41%)
```

The install command refuses to overwrite an existing statusLine entry; pass `--force` to replace, or hand-edit `~/.claude/settings.json` to merge (the script needs to emit a `ctx:<n>k` fragment somewhere in its output for the parser to pick it up).

If install isn't done, superv still works — it just prints raw tokens (`ctx=405k`) and the supervisor divides by the model's context size: 1M for 1M-context variants (Opus 4.7 1M), 200k for default Claude. Codex sessions get the percentage automatically because their JSONL includes `model_context_window` per turn; Claude's doesn't.

**Do NOT use as fill:**
- **tmux task-pane per-turn token numbers** (`↑ 32k tokens`, `↓ 19.9k tokens`). Those are per-turn input/output deltas for the active thinking burst, not cumulative session size. They are per-turn UI telemetry and consistently undershoot when read as fill.
- **JSONL file size**. Looks like a proxy but isn't — JSONL has substantial overhead (JSON keys, escape chars, ToolResult content the model sees differently from raw bytes). The byte/token ratio is unstable across sessions and across the same session as it grows. Approximations from MB will undershoot by ~10pp at moderate fills.
- **`/context` slash command**. Returns accurate fill, but issuing it interrupts the worker mid-loop. The superv readout is non-disruptive.

**Per-turn token signals** (the UI numbers) can still help interpret a visible active turn — large input means the worker just consumed a big read; large output means it just generated a big write. Read them as UI telemetry, not as fill or as the busy/idle source.

### Deep-context compaction heuristic (1M-window Claude models)

A large context window is not a reason to wait until it is nearly full. Long Claude sessions accumulate tool results, abandoned branches, and stale framing well before the hard limit. On a true 1M-context model, begin planning compaction around **30–40%**, especially after many tool turns.

- At roughly 30%, start watching for the next coherent breakpoint: a slice committed, a review completed, a phase wrapped, or an assignment about to change.
- Around 40%, prefer compaction at that breakpoint before giving the worker another substantial task.
- Above that range, urgency increases with context fill. Do not repeatedly pass safe boundaries or start large new assignments while postponing compaction. As fill climbs, compact at the first suitable idle pause unless preserving the current detailed context has a concrete, stated benefit.
- Do not interrupt a coherent in-flight task merely because a percentage was crossed. The threshold tells the supervisor to find and use the next pause, not to destroy working context mid-turn.

The percentage is one signal alongside session depth, number of tool turns, coherence, and observed stale-context or rollback behavior. Use the supervisor-issued isolated `/compact` procedure in `core.md`: wait for idle, submit only `/compact`, verify it started, verify completion and reduced context, then send the next assignment separately.

## 7. Quirks

- **Composer-Enter quirk** (above) — always verify post-send.
- **Ghost-text trap** (see section 5) — compose-box content can be an AI-rendered suggestion, not user input. Use `tmux capture-pane -e` and look for the dim SGR (`\e[2m` / `\e[0;2m`) before treating compose-box text as real.
- **Subagents** write their own JSONL under `~/.claude/projects/<cwd-key>/<parent-session-id>/subagents/*.jsonl`. The current `superv` watches the parent session only; drill into a subagent transcript by registering it as a separate worker with `--path <subagent.jsonl>`.
- **Compaction events** appear inline in the JSONL as a `summary` user/assistant exchange. The cursor handles this transparently.
- **No structured "stop" event for permission gating** — Claude just goes silent waiting for input. If status flips to IDLE while the live channel shows a permission prompt, classify as NEEDS_CORRECTION and tell the user.

## 8. Done signals

- Final assistant message with no pending tool calls.
- `superv status` reports `turn=idle`.
- Worker explicitly says "all done" / "complete" / "ready for review" *and* validations have actually run (verify with read-only `git`/`npm test`).

## 8b. Pause / resume

Claude supports session resume by UUID. The supervisor wraps this via `superv pause` / `superv resume` (see `core.md`).

- **Resume command shape**: `claude --resume <uuid> --dangerously-skip-permissions`. The `<uuid>` is the session ID, stored in the registry as `rec.extra.session_id` (and is also the JSONL filename stem).
- **Cwd-independent for *finding*** the session — Claude searches across `~/.claude/projects/*/<uuid>.jsonl`.
- **But run resume in the original cwd** for cleanest behavior. `superv resume` defaults to the stored cwd.
- **Always include `--dangerously-skip-permissions`** at resume for autonomous workers — without it, Claude blocks on every tool call once it starts running again. `superv resume` includes this flag by default.

## 9. Kickoff template (Claude-flavored additions)

Append to the core kickoff:

```
8. You are running with --dangerously-skip-permissions; permission prompts will not block you.
9. Use TaskCreate / TaskUpdate liberally to track progress; the supervisor reads them.
10. When you compact, it's fine — the supervisor's cursor survives compaction.
```
