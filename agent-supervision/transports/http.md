# Transport — HTTP (OpenCode)

Used by `workers/opencode.md` only. OpenCode runs a Hono.js server (default port 4096). Both live and persisted state come through the API. There is no separate JSONL or tmux pane to read.

## Hard rules

- **No trailing slashes** on API paths. The embedded web UI has a catch-all `/*` handler that intercepts unmatched routes and returns HTML. `/session/` returns HTML; `/session` returns JSON.
- **`x-opencode-directory` header is required** for instance routing. Wrong directory = silent breakage of the user's TUI visibility.
- **Always use `superv` (or `oc-supervise.py`)**. Never raw `curl` to send messages — getting the directory header wrong is invisible until the user notices their TUI is missing replies.

## Endpoint reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/global/health` | GET | Health check, returns `{healthy, version}` |
| `/session` | GET | List all sessions (supports `?search=`, `?limit=`) |
| `/session/:id` | GET | Session metadata (includes `directory`) |
| `/session/:id/message` | GET | All messages in session |
| `/session/status` | GET | Active run status for all sessions |
| `/session/:id/message` | POST | Send message (sync, blocks streaming response) |
| `/session/:id/prompt_async` | POST | Send message (async, returns 204 immediately) |
| `/session/:id/abort` | POST | Cancel active run |
| `/global/event` | GET | SSE event stream |

## Supervisor uses

`superv` calls these internally:

- `superv list` → `/session` (with `x-opencode-directory: /` for discovery).
- `superv register --auto-oc <ses-id>` → `/session/:id` to discover the directory; cached locally in the registry.
- `superv watch <id>` → `/session/:id/message` filtered past the cursor.
- `superv watch <id> --live` → `/session/status` for active-run state. Combines with `/session/:id` for last-update time.
- `superv send <id>` → `/session/:id/prompt_async` (preferred over `/message` to avoid blocking).
- `superv detail <id> <msg-id>` → full message rendering.

## Cursor strategy

OC cursors are message-count-based: `{"last_msg_count": N, "last_check": ts}` at `~/.agent-supervision/cursors/<id>.json`.

`superv watch` refuses to operate on established sessions (>20 messages) without an existing cursor. Use `--reset` once to deliberately bootstrap.

## Stuck detection

`/session/status` returns a dict keyed by session id. When a session is mid-turn the value is `{"type": "busy"}`; when idle the session id is absent (or the whole dict is `{}`). The adapter uses persisted `/session/:id/message` turn-state for the `turn=busy|idle|unknown` status field, and `/session/:id` `time.updated` for persisted-age thresholds.

## Message rendering

Per the supervisor cursor strategy:

- Assistant text: cap ~1200 chars (where decisions and blockers live).
- Tool invocations: one-liner with name + state + 80-char arg preview.
- Reasoning: skipped.
- Step markers: skipped.
- User text: cap ~120 chars (usually the supervisor's own nudges).

`superv detail <id> <msg-id>` shows full content for one message.

## Process management

The user typically owns the OpenCode process. Supervisor does **not** start or kill it during normal operation. **Exception**: if the user is absent and the process dies, restart with `nohup opencode --port 4096 &`, then `superv note <id> "restarted opencode" --tag supervisor`.

Before restarting, always `ps aux | grep '[o]pencode'` to avoid the duplicate-process problem.

## Multi-line messages

HTTP carries multi-line content directly — `superv send <id> "<message>"` POSTs the body as one message regardless of newlines. `superv send <id> --file path.md` reads the file and POSTs its contents the same way. (The tmux transport now also handles multi-line via paste-buffer; both transports are equivalent in this regard.)
