# Transport — JSONL session readers

Used by `workers/pi.md`, `workers/codex.md`, and `workers/claude.md`. Authoritative-content channel — what was actually persisted, not what's currently on screen.

## When to prefer JSONL over tmux

- Content retrieval, citations, compare/contrast — anything fidelity-sensitive.
- Anything that may be longer than the pane buffer.
- Anything truncated by terminal width.
- Retrospective review across many turns.
- Scriptable / deterministic output.

Use tmux pane capture only for liveness/anomaly context (current screen, permission prompts, crash text). Busy/idle is derived from persisted transcript turn-state, not from pane spinners.

## Unified access via superv

```bash
superv watch <id>                       # incremental — entries past cursor
superv watch <id> --reset               # discard cursor, re-bootstrap
superv watch <id> --full                # one-shot full snapshot, also resets
superv watch <id> --count N             # for fresh bootstrap, show last N
superv detail <id> <entry-or-tool-id>   # full content for one entry
```

The same flags work regardless of worker kind — the adapter under the hood handles each format's specifics.

## Cursor discipline (mandatory)

- `superv watch <id>` requires an existing cursor on established sessions (>20 entries). It will refuse otherwise. This is intentional protection against context destruction.
- To bootstrap an established session, use `--reset` (or `--count N` for a tail) once. Subsequent calls work normally.
- Cursor files: `~/.agent-supervision/cursors/<id>.json`. Survives compaction and reboots.

## Per-worker session file locations

| Worker | Path pattern |
|---|---|
| Pi | `~/.pi/agent/sessions/--<cwd-with-dashes>--/<ts>_<id>.jsonl` |
| Claude | `~/.claude/projects/-<cwd-with-dashes>/<sessionId>.jsonl` |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-<ISO-ts>-<id>.jsonl` |

The cwd-with-dashes encoding differs slightly per worker (Pi has surrounding `--`, Claude has a single leading `-`). The adapters handle this; you address the worker by its registered id, not by file path.

## Truncation defaults

The adapters render with these caps:

- **Assistant text**: 4000 chars (this is where decisions and explanations live — be generous).
- **User text**: 4000 chars.
- **Tool args**: 140 chars (you care *what* tool, not the full args).
- **Tool results**: 220 chars (file contents are not for the supervisor).

Override with `--text-trunc / --args-trunc / --result-trunc` if needed. For full content of one entry, use `superv detail`.

## Refusal limit on `watch`

- Refuses to print more than 12000 chars rendered at once (`MAX_RENDERED_CHARS`). Entry **count** is not capped — individual entries are short (args/results are truncated when rendered), so only the total rendered size matters. In practice ~30+ short entries fit under the cap; a large new-entry count is fine as long as the rendered text stays under it.

Override with `--force` only when you've genuinely decided the cost is worth it. The normal path: scope down with `--count N` or use `superv detail` for one entry at a time.

## Active-branch handling (Pi only)

Pi sessions are trees — entries have `parentId`. The adapter walks back from the latest entry via `parentId` to extract the active branch and only displays entries on that branch. If the active branch changes (rare), the cursor entry may no longer be on it; the adapter detects this and asks you to `--reset` deliberately rather than silently jumping branches.

Claude and Codex sessions are linear — no branch handling needed.

## What entry types are surfaced

- **User and assistant turns** — always.
- **Tool calls / tool results** — yes, but with truncated args/results.
- **Reasoning / thinking blocks** — skipped by default (internal chain-of-thought, not actionable for supervision). `superv detail` shows them when needed.
- **Hook progress, file-history snapshots** (Claude) — skipped.
- **Compaction / branch_summary / model_change** (Pi) — surfaced with brief metadata.
- **session_meta, turn_context, token_count** (Codex) — skipped or summarized.

## What `detail` returns

Full original content for one entry. Use for:

- Reading full assistant explanations that were truncated.
- Inspecting tool arguments (e.g., the exact patch a worker applied).
- Inspecting tool results when verifying a worker claim.
- Reading reasoning blocks when diagnosing why a worker chose an approach.
