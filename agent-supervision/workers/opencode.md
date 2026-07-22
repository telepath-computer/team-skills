# Worker — OpenCode

OpenCode as the supervised agent.

## 1. Transports used

- `transports/http.md` — OpenCode runs an HTTP server (default :4096); live + persisted both come through the API
- `transports/tmux.md` — only if you also want to observe the human user's TUI pane (optional, supervisor usually doesn't need it)

## 2. Launch

OpenCode is structurally different from the tmux-backed workers. It is **not** a TUI in a tmux pane that the supervisor observes; it's an HTTP server, and supervision happens entirely through that server's API. **Tmux is irrelevant to the supervisor's relationship with OpenCode** — even if the user is running OpenCode's TUI inside a tmux pane, the supervisor doesn't read it. The API is the authoritative channel for both observation and sending.

Launch has three concepts to keep separate:

| Command | What it does |
|---|---|
| `opencode [project]` | The default. Starts the **TUI** with a bundled server. Typical user-facing way to run opencode. |
| `opencode serve` | **Headless server** — no TUI. Useful when the supervisor wants to run opencode without a terminal frontend. |
| `opencode attach <url>` | Connect a TUI to an already-running server (started elsewhere). |

OpenCode has no `--yolo`-style permission-bypass flag; its permissions model is governed via configuration and per-call API behavior.

**Standard supervisor expectation: the user is running OpenCode somewhere.** Either as `opencode` (TUI) or `opencode serve` (headless). The supervisor doesn't need to know which — it only needs the server's URL. `superv` defaults to `http://localhost:4096` and can be overridden via the `OPENCODE_BASE` env var.

**Confirming the server is up:**

```bash
curl -s http://localhost:4096/global/health
# {"healthy":true,"version":"1.2.18"}
```

If the user is running the TUI on a different port (whatever they configured), point superv at it: `OPENCODE_BASE=http://localhost:PORT superv list`.

**Creating a session** (operator, via API or via the TUI's UI):

```bash
curl -s -X POST 'http://localhost:4096/session' \
  -H 'x-opencode-directory: /path/to/your/project' \
  -H 'content-type: application/json' \
  -d '{"title":"my-task"}'
# returns {"id":"ses_...","directory":"/path/to/your/project",...}
```

Or the user can create a session interactively in their TUI.

**Register the session for supervision:**

```bash
superv register <id> --kind opencode --oc-session ses_29ab1c5e...
```

`register` calls `/session/<id>` to discover the session's `directory` and caches it for the `x-opencode-directory` header on subsequent requests.

**Supervisor-side restart** (exception — only if the user is absent and the process actually died):

```bash
ps aux | grep '[o]pencode'                # confirm none running
nohup opencode serve --port 4096 > /tmp/opencode.log 2>&1 &
# verify it came up:
curl -s http://localhost:4096/global/health
superv note <id> "restarted opencode :4096" --tag supervisor
```

Use `opencode serve` (headless) for supervisor-side restarts — no TUI is needed for the supervisor's purposes, and `nohup`-ing a TUI is awkward. If the user later wants a frontend they can `opencode attach http://localhost:4096`.

## 3. Identify

OpenCode sessions are addressed by id (`ses_...`). Discover with:

```bash
curl -s 'http://localhost:4096/session' \
  -H 'x-opencode-directory: /home/user/workspace/<project>'
```

The session metadata includes its `directory`, which `superv` caches and uses on every subsequent request via the `x-opencode-directory` header.

`superv register <id> --kind opencode --oc-session ses_...` is enough — the directory is auto-resolved.

## 4. Send a message

```
superv send <id> "<message>"             # any text via HTTP POST /session/:id/prompt_async
superv send <id> --file path.md          # read message from a file (convenience)
```

Note: HTTP transport carries multi-line content directly — no special handling needed. `--file` simply reads the file and sends it as a single message.

The OC adapter uses `prompt_async` (returns 204 immediately) by default rather than `prompt` (which blocks waiting for the full streaming response).

**CRITICAL**: All requests go through `superv` so the `x-opencode-directory` header is correct. Do not use raw `curl` to send messages — wrong header silently breaks the user's TUI visibility.

## 5. Read live state

`superv watch <id> --live` calls `/session/status`. When a turn is active you'll see `{"<sid>": {"type": "busy"}}`. When the session is idle the sid is absent from the response. There's no separate "screen capture" — the API is the live channel.

## 6. Read persisted state

`superv watch <id>` calls `/session/:id/message` and renders only messages past the cursor. Cursor strategy is message-count-based.

The script refuses `superv watch` on established sessions (>20 messages) without an existing cursor — this is intentional protection against context destruction. Use `superv watch <id> --reset` to deliberately bootstrap a fresh cursor on an existing session.

`superv detail <id> <message-id>` fetches the full message, including full tool-call args and full tool results.

## 6b. Measure context fill

`superv status <id>` prints `ctx=Nk` — the prompt token count for the most recent assistant message (the next turn's prompt size). Use it for context-pressure decisions.

```
$ superv status oc-worker
id=oc-worker kind=opencode status=running turn=busy persisted_age=0.5m ctx=12k
```

Internally that calls `/session/<id>/message` and reads `info.tokens.input + info.tokens.cache.read` from the most recent assistant message. OpenCode's message info.tokens shape:

```json
"tokens": {
  "total": 12137,
  "input": 8542,
  "output": 11,
  "reasoning": 0,
  "cache": {"read": 3584, "write": 0}
}
```

OpenCode treats `input` and `cache.read` as **additive** (verified: `total = input + cache.read + output`). Total prompt = `input + cache.read`.

OpenCode's message API doesn't include the model context window, but `/provider` does. `superv register --kind opencode` calls `/provider` once, looks up the session's current `(providerID, modelID)`, and caches `limit.context` in the worker registry — so subsequent `superv status` calls show the percentage automatically:

```
$ superv status oc-worker
id=oc-worker kind=opencode status=running turn=busy persisted_age=0.5m ctx=12k/400k(3%)
```

If the session switches model mid-conversation (different `limit.context`), the cached value goes stale until re-register. The `/provider` response is large (~3MB) and slow (~200ms), so superv doesn't re-fetch it on every status check.

If `/provider` is unreachable at register time, the cache stays empty and status prints raw tokens. Look up the window manually if needed:

```bash
curl -s 'http://127.0.0.1:<port>/provider?directory=<dir>' \
  | jq '.all[] | select(.id=="openai") | .models["gpt-5.5"].limit.context'
# 400000
```

## 7. Quirks

- **No trailing slashes on API paths.** `/session/` returns the embedded web UI HTML; `/session` returns JSON. The adapter handles this.
- **`x-opencode-directory` header is required** for instance routing. Wrong directory = silent breakage.
- **Conversational continuity bug**: OpenCode occasionally responds to an earlier message instead of the most recent one. Telltale: response is out of context, brings up resolved topics, doesn't reference your latest message. Canned correction:

  ```
  You've made a conversational continuity error — your last message responded
  to an earlier message instead of the most recent one. Please read the most
  recent message in the conversation and proceed from there.
  ```

- **Test duration anti-pattern**: OC is especially prone to increasing timeouts when tests hang. Watch for it; correct early.

## 8. Done signals

- `/session/status` no longer shows the session id (or shows `{}` overall) — the busy state has cleared.
- Last assistant message reads as a clean summary, no pending tool calls.
- `/session/:id` `time.updated` is recent (so it's not just abandoned).

## 9. Kickoff template (OpenCode-flavored additions)

Append to the core kickoff:

```
8. You're talking to me through OpenCode's HTTP API; my messages come through
   the user's TUI session. The user can also message you directly.
9. If you observe inconsistencies between my guidance and the user's, surface
   them — don't silently pick one.
10. Long-running tests need detailed progress logging — a 30s black box with
    pass/fail at the end is unacceptable.
```
