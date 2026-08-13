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
superv watch <id> --reset               # discard cursor, re-bootstrap from recent tail
superv watch <id> --full                # read from the start; cursor advances only through shown entries
superv watch <id> --count N             # bootstrap tail, or oldest N unread with a cursor
superv recent <id> --kind messages      # historical query; does not move cursor
superv detail <id> <entry-or-tool-id>   # bounded content for one entry or child
```

The same flags work regardless of worker kind — the adapter under the hood handles each format's specifics.

## Cursor discipline (mandatory)

- `superv watch <id>` requires an existing cursor on established sessions (>20 entries). It will refuse otherwise. This is intentional protection against context destruction.
- To bootstrap an established session, use `--reset` (or `--count N` for a tail) once. Subsequent calls work normally.
- With an established cursor, `--count N` returns the oldest N unread entries. Repeating it drains a backlog without skipping the middle.
- `--reset --count N` deliberately discards unread history and starts from the latest N entries.
- Cursor files: `~/.agent-supervision/cursors/<id>.json`. Survives compaction and reboots.

## Per-worker session file locations

| Worker | Path pattern |
|---|---|
| Pi | `~/.pi/agent/sessions/--<cwd-with-dashes>--/<ts>_<id>.jsonl` |
| Claude | `~/.claude/projects/-<cwd-with-dashes>/<sessionId>.jsonl` |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-<ISO-ts>-<id>.jsonl` |

The cwd-with-dashes encoding differs slightly per worker (Pi has surrounding `--`, Claude has a single leading `-`). The adapters handle this; you address the worker by its registered id, not by file path.

For pi and claude workers launched the standard way, the cwd in these paths is the **worktrees' parent folder** (e.g. `~/workspace/wt/<repo>/`), not a worktree — workers are homed there because worktrees are often shorter-lived than the agent sessions that operate over them. That makes the cwd-keyed session dir **shared per repo**: every agent on that repo writes into the same directory, so a file's location says nothing about which agent owns it. Binding relies on session ids (pi: mandatory launch-seeded `--session-id`; claude: `extra.session_id` captured at registration), never on "newest file in the dir". Codex is the exception — its rollouts are date-keyed anyway, and codex workers still launch inside their worktree.

## Truncation defaults

The adapters render with these caps:

- **Assistant text**: 4000 chars (this is where decisions and explanations live — be generous).
- **User text**: 4000 chars.
- **Tool args**: 140 chars (you care *what* tool, not the full args).
- **Tool results**: 220 chars (file contents are not for the supervisor).

For more content from one entry, use `superv detail` with the locator shown by `watch`.

## Overflow behavior on `watch`

`watch` prints the detailed rendering when it fits under 12,000 characters. When it does not fit, it prints a compact chronological overview:

- Every tool call remains present on its own bounded line. Calls are never replaced with a count.
- Source whitespace is normalized before character-wise truncation; source line breaks do not decide what survives.
- A final `…` marks shortened content. One footer explains how to use `detail` for a locator.
- If all unread entries fit in compact form, `watch` reports `OBSERVATION COMPLETE` and advances through all of them.
- If only an oldest prefix fits, `watch` reports `INCOMPLETE OBSERVATION`, advances only through represented entries, and explicitly directs the supervisor to run `watch` again before judging worker status.

Repeat `watch` until it reports completion. Use `--reset --count N` only to deliberately discard the unread remainder and inspect a recent tail. `--force` remains an explicit bypass for the detailed-output cap.

## Active-branch handling (Pi only)

Pi sessions are trees — entries have `parentId`. The adapter walks back from the latest entry via `parentId` to extract the active branch and only displays entries on that branch. If the active branch changes (rare), the cursor entry may no longer be on it; the adapter detects this and asks you to `--reset` deliberately rather than silently jumping branches.

Claude and Codex sessions are linear — no branch handling needed.

## What entry types are surfaced

- **User and assistant turns** — always.
- **Tool calls / tool results** — yes, but with truncated args/results.
- **Reasoning / thinking blocks** — readable plaintext intent summaries are shown; empty, signed, or encrypted reasoning payloads are omitted.
- **Hook progress, file-history snapshots** (Claude) — skipped.
- **Compaction / branch_summary / model_change** (Pi) — surfaced with brief metadata.
- **session_meta, turn_context, token_count** (Codex) — skipped or summarized.

## What `detail` returns

Bounded supervisor-oriented content for one entry or child locator. It omits opaque signatures and encrypted reasoning payloads, bounds large text and results, and says when content was shortened. Use it for:

- Reading more of an assistant explanation marked with `…`.
- Inspecting one tool call through a locator such as `<entry>/tool/1`.
- Inspecting a tool result when verifying a worker claim.
- Reading a persisted plaintext intent summary.
