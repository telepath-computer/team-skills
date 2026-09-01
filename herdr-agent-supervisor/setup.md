# supervisr — setup

Everything the host needs before `supervisr` can supervise. Run `supervisr doctor`
at any point; it checks every item below and prints the exact fix for whatever
is missing.

## 0. Prerequisites

- **Read the `herdr` skill first** (`../herdr/SKILL.md`, installed alongside this skill). supervisr wraps only the supervision-loop slice of herdr; setup and topology use raw `herdr`, which that skill documents.
- **herdr** installed and a server running (`herdr` starts one; `herdr session list` shows it). supervisr talks to the herdr server over its unix socket.
- **Python 3** (stdlib only — no packages to install).
- The agent CLIs you intend to supervise on PATH: `claude`, `codex`, `pi`.

## 1. Put `supervisr` on PATH

All examples call `supervisr` as a bare command, and dispatched workers never
need it. Add the skill's `scripts/` dir to PATH persistently, for login shells
(so it reaches `bash -lc`, hooks, and spawned agents), idempotently. On a stock
bash host:

```bash
DIR="$(cd "$(dirname "$(readlink -f ~/.claude/skills/herdr-agent-supervisor 2>/dev/null || echo .)")" && pwd)"
# or just use the real path to this skill's scripts/ dir:
echo 'export PATH="$HOME/workspace/artifact-stash/skills/herdr-agent-supervisor/scripts:$PATH"' >> ~/.profile
export PATH="$HOME/workspace/artifact-stash/skills/herdr-agent-supervisor/scripts:$PATH"   # this shell
```

Verify: `command -v supervisr`.

## 2. Install herdr's agent integrations — REQUIRED

This is the load-bearing step. **herdr learns a worker's native session id from
its agent integration hook.** Without the session id, supervisr cannot find the
worker's transcript and every observation command fails with `no-session-id`.

```bash
herdr integration install claude
herdr integration install codex
herdr integration install pi
herdr integration status          # each line should read "current"
```

Install only the kinds you will actually supervise. What each writes (one-time,
per user):

| kind | writes | effect |
|---|---|---|
| claude | `~/.claude/hooks/herdr-agent-state.sh` + one `SessionStart` entry in `~/.claude/settings.json` | reports Claude's `session_id` to herdr on session start (incl. `--resume`) |
| codex | `~/.codex/herdr-agent-state.sh`, `~/.codex/hooks.json`, a `config.toml` edit | reports the Codex session id |
| pi | `~/.pi/agent/extensions/herdr-agent-state.ts` | reports the pi session path + working/blocked/idle |

The hooks are inert outside herdr (they check `HERDR_ENV=1`), so they do not
affect the same agents run in plain terminals or tmux. Uninstall with
`herdr integration uninstall <kind>`.

### One-time first-launch gates (do these once per host, right after install)

Installing an integration adds a hook the agent notices on its next launch, and
some agents gate on that the first time. Clear each once and it stays cleared:

- **Codex** shows a "trust these hooks?" screen on its first launch after
  `herdr integration install codex` (herdr reads it as *idle*, not blocked, so a
  dispatched prompt can land on it). Clear it once: launch codex yourself, press
  `t` (trust all), `esc`. After that, codex dispatches start a real session
  normally.
- **Codex / Pi directory trust.** Both prompt to trust a directory the first
  time an agent runs in it. `dispatch --trust-folder` accepts it; without the
  flag, `supervisr answer <name> enter`.
- **Pi "Update Available" banner** (and a codex first-run screen) can leave a
  just-launched agent settled-but-not-yet-accepting. `dispatch` waits on herdr's
  own `interactive_ready` flag before sending the first prompt, so it rides over
  these without a retry. A bare `supervisr send` to a still-settling worker
  surfaces herdr's `not ready` honestly — just send again a moment later.

Run `supervisr doctor`; a worker whose transcript resolves is past all of these.

**Note on the transcript format.** supervisr reads the agents' own session
files (`~/.claude/projects/**.jsonl`, `~/.codex/sessions/**.jsonl`,
`~/.pi/agent/sessions/**.jsonl`) to build the activity stream. Claude Code's
docs call this format internal and subject to change between releases; the
adapters are version-tolerant but a major format change could require an
adapter update. This is the same trade the `superv` tool makes — there is no
supported alternative that yields per-tool-call activity.

## 3. Install the Claude context-window sidecar — RECOMMENDED (Claude workers)

**Why it exists.** A Claude worker's transcript records how many tokens each
turn used, but never the context-window *size*. So without this, supervisr shows
`ctx=380k/?` — a numerator with no denominator, and no percentage. The docs
confirm the window size is exposed in exactly one place: the Claude Code
**statusLine** command's JSON input (`context_window.context_window_size`,
`used_percentage`). No hook event carries it. Screen-scraping the TUI status bar
is unreliable because the user's own statusline script controls its formatting.

**What the sidecar does.** The visible status line is toolbringer's
(`~/.claude/statusline.sh`, see the toolbringer skill); the sidecar piggybacks on
it. It installs itself as the `statusLine` command. On
every refresh Claude Code pipes it the status JSON; the sidecar records
`context_window` + `model` per session id under supervisr's state dir (giving
`supervisr` the exact window and Claude's own usage figure), then runs
**whatever statusLine command you had before** with the same input, so your
visible status bar is unchanged. If you had no statusLine — or the chained one
fails or prints nothing — it prints a compact default line
(toolbringer's line adds `effort:<level>` as well). `supervisr doctor` probes the
chained command and warns if it is broken; the fix is to re-run toolbringer's
status line step, which reinstalls the script and repairs `statusline_chain`.

```bash
supervisr setup statusline            # installs; chains any existing statusLine; backs up settings.json
supervisr setup statusline --uninstall   # restores your previous statusLine exactly
```

New Claude sessions pick it up automatically; already-running sessions get it on
their next launch. Codex and pi publish their window in-band (Codex per turn in
the rollout, pi via its model registry), so they need no sidecar. Only Claude
has this gap.

## 4. Verify

```bash
supervisr doctor
```

Green means: herdr reachable, you are inside a herdr pane (so default scope
works), the integrations you need are `current`, the sidecar is installed, and
every agent currently in scope resolves to a transcript. Anything else prints
the specific remediation.

## State supervisr keeps

Under `$SUPERVISR_STATE_ROOT` → `$HERDR_PLUGIN_STATE_DIR` → `$XDG_STATE_HOME/supervisr`
→ `~/.local/state/supervisr` (first that is set):

```
cursors/<session-id>.json      observation cursor (survives compaction & restart)
notes/<session-id>.md          supervisor's running notes
sessions/<session-id>.json     resolved transcript path + last-seen name/pane cache
claude-ctx/<session-id>.json   sidecar's per-session context-window record
statusline-sidecar.json        the previous statusLine command (so uninstall restores it)
```

All keyed by the worker's **native session id**, never by pane id or herdr name —
so a moved pane, a renamed agent, or a herdr restart that resumes the agent keeps
the same cursor. Nothing is ever written inside a supervised repo.
