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
- `superv register <id> --kind opencode --oc-session <ses-id>` → `/session/:id` to discover the directory; cached locally in the registry.
- `superv watch <id>` → `/session/:id/message` filtered past the cursor.
- `superv watch <id> --live` → `/session/status` for active-run state.
- `superv status <id>` and `superv sweep` → one `/session/:id/message` read for turn state, context use, unread count, and the latest intent, plus `/session/:id` for persisted age.
- `superv send <id>` → `/session/:id/prompt_async` (preferred over `/message` to avoid blocking).
- `superv detail <id> <msg-or-child-id>` → bounded supervisor-oriented rendering. Unbounded API JSON requires `--raw --force`.

## Cursor strategy

OC cursors are message-count-based: `{"session_id": "ses_...", "last_msg_count": N}` at `~/.agent-supervision/cursors/<id>.json`.

`superv watch` refuses to operate on established sessions (>20 messages) without an existing cursor. Use `--count N` to establish a cursor from a recent tail. With a cursor, `--count N` reads the oldest N unread messages. `--reset --count N` explicitly discards unread history and starts from a recent tail.

## Stuck detection

`/session/status` returns a dict keyed by session id. When a session is mid-turn the value is `{"type": "busy"}`; when idle the session id is absent (or the whole dict is `{}`). The adapter uses persisted `/session/:id/message` turn-state for the `turn=busy|idle|unknown` status field, and `/session/:id` `time.updated` for persisted-age thresholds.

## Message rendering

The ordinary detailed view uses the shared adapter budgets: 4,000 characters for assistant and user text, 140 for tool arguments, and 220 for tool results. Every terminal OpenCode tool part renders both its call and its result. Readable plaintext reasoning summaries render as `intent` lines; empty and opaque payloads are omitted.

When the detailed batch exceeds 12,000 characters, the compact overview preserves every call and result on separate bounded lines and pages chronologically without skipping messages. `superv detail <id> <locator>` gives bounded content for one message, tool, result, or intent. Use `--raw --force` only when the unbounded API object is necessary.

## Process management

The user typically owns the OpenCode process. Supervisor does **not** start or kill it during normal operation. **Exception**: if the user is absent and the process dies, restart with `nohup opencode serve --port 4096 > /tmp/opencode.log 2>&1 &`, then `superv note <id> "restarted opencode" --tag supervisor`.

Before restarting, always `ps aux | grep '[o]pencode'` to avoid the duplicate-process problem.

## Multi-line messages

HTTP carries multi-line content directly — `superv send <id> "<message>"` POSTs the body as one message regardless of newlines. `superv send <id> --file path.md` reads the file and POSTs its contents the same way. (The tmux transport now also handles multi-line via paste-buffer; both transports are equivalent in this regard.)
