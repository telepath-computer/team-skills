#!/usr/bin/env bash
# Claude Code statusLine emitter for agent-supervision.
#
# Wired into ~/.claude/settings.json -> "statusLine" { "type": "command", "command": "..." }.
# Claude Code spawns this on every status refresh, pipes a JSON state blob to stdin,
# reads one line of stdout for the TUI status bar.
#
# Format emitted (designed to be machine-parseable by superv):
#   <display_name> | ctx:<window>k | used:<input>tok/<pct>%
# Example:
#   Opus 4.7 (1M context) | ctx:1000k | used:127500tok/13%
#
# superv register --kind claude parses this from a tmux capture-pane to acquire
# the model context window once, then caches it in the worker registry.

input=$(cat)

model=$(printf '%s' "$input" | jq -r '.model.display_name // "claude"')
window=$(printf '%s' "$input" | jq -r '.context_window.context_window_size // empty')
input_tokens=$(printf '%s' "$input" | jq -r '.context_window.total_input_tokens // empty')
used_pct=$(printf '%s' "$input" | jq -r '.context_window.used_percentage // empty')

parts=("$model")
if [[ -n "$window" ]]; then
  parts+=("ctx:$((window / 1000))k")
fi
if [[ -n "$input_tokens" && -n "$used_pct" ]]; then
  pct_int=$(printf '%.0f' "$used_pct")
  parts+=("used:${input_tokens}tok/${pct_int}%")
fi

# Join with " | "
out="${parts[0]}"
for ((i=1; i<${#parts[@]}; i++)); do
  out="$out | ${parts[$i]}"
done
printf '%s\n' "$out"
