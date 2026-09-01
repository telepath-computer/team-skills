# Per-worker notes — index

herdr and supervisr smooth over most cross-harness differences (status, send,
wait, context% are uniform — you address a worker by its herdr name or pane id
and never think about session files). The per-kind quirks that still bite —
especially **context-window handling, which differs by model and changes when
you compact** — live in one file per kind. Read the file for each kind you will
supervise, in full:

- **`workers/claude.md`** — sidecar-based context %, the ghost-text trap, the
  1M-window deep-context heuristic (~30–40%), `/compact`, done signals.
- **`workers/codex.md`** — in-band context %, the one-time hooks-trust gate,
  cwd-bound sessions, date-bucketed rollouts.
- **`workers/pi.md`** — model-registry context %, the **small-window
  (272k GPT/codex-sub) vs 1M-window (GLM) regime split** that decides whether you
  compact opportunistically or watch for rollback, the never-Escape-a-compaction
  rule, post-compaction phantom state, long-thinking pauses.

## Uniform across all three kinds

`sweep` / `status` / `watch` / `detail` / `recent` / `screen` / `send` / `answer`
/ `wait` / `events` / `dispatch` / `adopt` / `stop` / `note` behave identically
regardless of kind — the adapter under the hood handles each format. What varies
is only what the per-kind files above document.

(OpenCode is not supported by the herdr supervisor — it has no local transcript
file; supervise OpenCode with the tmux-agent-supervisor skill instead.)
