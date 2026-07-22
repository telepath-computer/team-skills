# Transport — tmux

Used by `workers/pi.md`, `workers/codex.md`, and `workers/claude.md` (when running in a pane). Pure tooling reference.

## Hard rule: liveness only

The tmux pane is **liveness/anomaly context only** — current screen text, permission prompts, crash text, transient TUI state. It is **not** authoritative content and it is not the busy/idle source. For anything content-bearing (citations, compare/contrast, fidelity-sensitive review), and for busy/idle turn-state, read the persisted transcript via `transports/jsonl.md` instead.

## Identifying a pane

Target syntax: `<session>:<window>.<pane>`. Window can be name or index.

```bash
tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index} #{window_name} pid=#{pane_pid} cmd=#{pane_current_command} path=#{pane_current_path}'
```

To label your own session (do this once per supervisor):

```bash
tmux rename-session 'pi-agent'
tmux rename-window 'main'
tmux display-message -p '#{session_name}:#{window_name}.#{pane_index}'
```

## Capturing pane content

```bash
tmux capture-pane -t <target> -p              # current visible
tmux capture-pane -t <target> -p -S -100      # last 100 lines of scrollback
tmux capture-pane -t <target> -p -S -         # full scrollback + visible
```

Raw `capture-pane` returns everything every time. For incremental reads (only new content since last check), use `tmux-poll`.

## tmux-poll (incremental reads)

```bash
tmux-poll <target>             # incremental — only new since last check
tmux-poll --full <target>      # full capture, resets cursor
tmux-poll --reset <target>     # clear cursor without reading
tmux-poll --dir DIR <target>   # custom cursor storage
```

Cursor files default to `/tmp/tmux-poll-cursors/`. The script:

1. Captures full scrollback + visible.
2. Strips pi/codex TUI chrome (bottom separator pair + status bar) which changes every render.
3. Filters transient elements (braille spinners `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`, "Working...") before saving snapshots — prevents stale anchors.
4. Anchors on the last stable content line from the previous snapshot.
5. Returns only lines after the anchor.

`superv watch <id> --live` uses `tmux-poll` internally for tmux-backed workers.

## Sending keystrokes

`superv send` delivers any text — single-line or multi-line — by loading it into a tmux paste buffer, pasting into the target pane, and then sending a single Enter:

```bash
# What superv send does internally:
printf '%s' "$text" | tmux load-buffer -
tmux paste-buffer -d -t <target>
tmux send-keys -t <target> Enter
```

Embedded newlines arrive as soft newlines in the worker's input field; only the trailing Enter submits. No pointer-file workaround needed.

**Use `superv send`, not raw `tmux send-keys`**, for any non-trivial text:

```bash
superv send <id> "single or multi-line message goes here
preserved exactly"

# or read from a file (convenience, no special pointer pattern):
superv send <id> --file path.md
```

If you ever do call raw `tmux send-keys` (e.g. for a one-off launch command in a setup script), keep it to a single line — bare `send-keys` is still subject to newline-as-Enter semantics. The paste-buffer mechanism only kicks in via `superv send` (or by replicating the `load-buffer + paste-buffer + Enter` pattern manually).

## Submission verification

After sending:

1. Wait 2–4 seconds.
2. Check the pane: did the prompt clear from the composer? (Visible vs. submitted matters.)
3. Check the persisted JSONL: did a new user-message entry appear?

`superv send --verify` does these checks. For Claude specifically, if the prompt is still in the composer, send one additional plain `Enter` and re-verify.

## Spawning a worker in a new window

```bash
# 1. Create a background tmux window
tmux new-window -t <session> -n <name> -d

# 2. Start the worker interactively
tmux send-keys -t <session>:<name>.0 'cd <cwd> && <agent-cmd>' Enter

# 3. Poll briefly until ready (look for the agent's compose prompt)
for i in $(seq 1 40); do
  out=$(tmux capture-pane -t <session>:<name>.0 -p -S -20 2>/dev/null || true)
  if printf '%s' "$out" | grep -q '<readiness-marker>'; then break; fi
  sleep 0.25
done

# 4. Optionally name the session inside the agent (Pi: /name <id>)
```

Each worker doc specifies its own readiness marker and naming convention.

## Tmux-poll cursor location

`/tmp/tmux-poll-cursors/<sanitized-target>.snapshot` — survives the same lifetime as `/tmp`. For long-running supervision, use `--dir ~/.agent-supervision/tmux-cursors/` to persist across reboots.
