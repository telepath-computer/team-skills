# Worker — Codex (herdr)

OpenAI Codex CLI as a supervised herdr agent.

## 1. Launch and identity

Launch with `supervisr dispatch <name> --kind codex`. Default flags: `--yolo -m gpt-5.6-sol -c model_reasoning_effort=xhigh` (`--yolo` = `--dangerously-bypass-approvals-and-sandbox`; override model with `--model`, effort with `--effort`). Codex accepts a positional first prompt, but `dispatch` handles the first prompt after readiness like the other kinds.

**Session id / transcript.** herdr's Codex integration reports the session id (install once: `herdr integration install codex`). Rollout at `~/.codex/sessions/YYYY/MM/DD/rollout-<ISO-ts>-<session-id>.jsonl`; the first line is `session_meta` with `payload.id`/`payload.cwd`. Codex does not write the rollout until its first turn.

**First-launch gates (one-time per host).** After `herdr integration install codex`, the first codex launch shows a **"trust these hooks?"** screen (herdr reads it as *idle*, not blocked, so a dispatched prompt can land on it). Clear it once: launch codex yourself, press `t` (trust all), `esc`. Codex also shows a **directory-trust** prompt the first time in a cwd — `dispatch --trust-folder` accepts it. `supervisr send` retries `agent_not_ready` briefly so a startup banner does not fail the first prompt.

## 2. Send a message

`supervisr send <name> "<message>"` via herdr `agent.prompt`; `--wait` uses herdr's effect-gate + settle. Same honest-error surfacing as the other kinds (blocked / not-ready / stalled).

## 3. Read state

- **Persisted:** `supervisr watch <name>` reads the rollout. Entry shapes: `event_msg` (`task_started`, `task_complete`, `context_compacted`), `response_item` (`message`, `reasoning` → intent, `*_call`/`*_call_output` → tool call/result), `compacted`. Addressed by raw line index (`codex-r<N>`).
- **Live:** `supervisr screen <name>` for anomaly/liveness only.
- **Busy/idle** from rollout turn-state merged with herdr status.

## 4. Measure context fill

Codex publishes context **in-band** — no sidecar needed. `supervisr status`/`sweep` read the most recent `event_msg` of type `token_count`:
- used = `info.last_token_usage.input_tokens` (this already **includes** cached input tokens — do NOT add `cached_input_tokens` on top),
- window = `info.model_context_window`.

If you only want the cumulative-across-turns count it is `info.total_token_usage.input_tokens`, but for staging decisions the per-turn prompt size is what matters and is what supervisr reports.

## 5. `/compact`

Codex compaction, like Claude's, is a runtime operation with no persisted entry — the same `core.md` procedure and the same "do not re-send to check" caution apply. Codex may also auto-compact near its window limit; prefer compacting opportunistically at a breakpoint before a forced mid-task compact truncates state.

## 6. Quirks

- **Rollouts are date-bucketed** — a session that spans midnight produces a second file. supervisr re-resolves to the newest file carrying the session id, and `watch` asks for a `--reset` rather than silently jumping files.
- **Linear, no branch model** — simpler than pi's tree.
- **cwd identity.** Codex binds sessions by cwd (its rollout carries `payload.cwd`), so the recommended topology launches a codex worker **inside its own worktree** (unlike claude/pi, which home in the parent). With herdr's session-id reporting this matters less than under superv, but keep codex workers in distinct cwds to be safe. `dispatch --worktree` (which sets the pane cwd to the worktree) satisfies this naturally.
- **Submission after a startup banner** — an "update available" banner can consume the first keystrokes; `supervisr send`'s retry and dispatch's interactive-ready gate handle it.

## 7. Done signals

- `event_msg.task_complete` for the active turn; final assistant `response_item.message`; `supervisr status` `turn=idle` and herdr `done`/`idle`.

## 8. Stepping away / resume

herdr persists; a restart relaunches with `codex resume <id>` from the reported session id. No pause/resume CLI. End with `supervisr stop <name> --close-pane`. (`codex exec resume <thread-id>` remains available for a one-shot supervisor verification query outside the TUI.)

## 9. Kickoff additions (Codex)

Append to the core kickoff:

```
9. You are running with --yolo; sandboxing and approvals are off, you have full access.
10. The supervisor reads your rollout JSONL (via supervisr) and can read your pane.
11. When done, end your final turn with a clear summary — task_complete + assistant text is the done signal.
```
