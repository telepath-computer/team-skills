# Worker — Claude Code (herdr)

Claude Code as a supervised herdr agent. Read this before supervising a Claude worker.

## 1. Launch and identity

Launch with `supervisr dispatch <name> --kind claude` (see herdr-agent-supervisor / herdr-agent-triad). Default launch flags: `--dangerously-skip-permissions --model claude-fable-5 --effort xhigh` (override with `--model`/`--effort`). Claude's TUI does not take a seeded positional prompt; `dispatch` waits for herdr to mark the pane interactive-ready and then sends the first prompt.

**Session id / transcript.** herdr's Claude integration reports the session id on `SessionStart` (install once: `herdr integration install claude`). `supervisr` resolves the transcript at `~/.claude/projects/<cwd-key>/<session-id>.jsonl`. If the session id is missing (e.g. a Claude that started before the integration was installed), supervisr falls back to `~/.claude/sessions/<pid>.json` via the pane's foreground pid — so a pre-existing Claude in your workspace can still be `supervisr adopt`ed and observed. Claude does not write the JSONL until its first turn completes.

**Folder-trust dialog.** A fresh Claude in a new cwd blocks on "Is this a project you trust?" before it is interactive. herdr reports this correctly as `blocked`. `dispatch --trust-folder` accepts it; otherwise `supervisr answer <name> enter`.

## 2. Send a message

`supervisr send <name> "<message>"` routes through herdr's `agent.prompt` (bracketed-paste aware, Enter after a short delay, refuses a blocked agent). With `--wait` herdr's effect-gate confirms the turn took and waits for the settled state. There is no composer-Enter workaround to run by hand — herdr's effect-gate catches an unsubmitted composer (it reports `agent_prompt_stalled`); if you see that, inspect `supervisr screen <name>`.

## 3. Read state

- **Persisted (authoritative):** `supervisr watch <name>` — the cursor-based transcript delta. Entry types: `user`, `assistant`, `system/compact_boundary`; assistant turns carry `text`, `thinking` (rendered as intent), and `tool_use` blocks; user turns carry `tool_result` blocks. `supervisr detail <name> <locator>` for one entry/child.
- **Live (liveness/anomaly only):** `supervisr screen <name>` reads the pane. Use it to read the *content* of a blocked dialog or a crash — not for routine observation. herdr's `sweep` already surfaces `blocked` without a screen read.
- **Busy/idle** is herdr's semantic status plus transcript turn-state; `sweep` merges them and flags disagreements with `?` (e.g. `idle?` when the transcript has a pending tool call herdr's screen can't see).

### The ghost-text trap (read before interpreting compose-box content)

Claude Code's TUI renders an **AI-suggested next prompt** in the compose box when idle. In a colorless screen read it looks identical to typed input: same `❯ ` prefix. It is **not** queued input — it is a suggestion (Tab accepts, typing dismisses). If you read it as a real pending user message you will mis-supervise; if you act on it you inject a nonsense prompt the worker treats as authoritative. Both have burned real supervision hours.

- Never reason about compose-box content from a plain (colorless) screen read.
- Cross-check the transcript: real-but-unsubmitted compose-box content does **not** appear in the JSONL (only submitted user messages do). If suspicious text is on screen but `supervisr watch`/`recent` doesn't show it and `persisted_age` keeps growing, it is almost certainly ghost text. herdr's status will also read `idle`/`done`, not `blocked`, for ghost text — a genuine pending user action would not sit as idle.

## 4. Measure context fill

`supervisr status <name>` / `sweep` report `ctx=<used>/<window>(<pct>%)`. The used figure is the prompt tokens of the most recent assistant turn (`input + cache_read + cache_creation`, additive in Claude's schema). **The window size is not in the transcript** — it comes from the statusline sidecar (`supervisr setup statusline`), which records Claude's own `context_window` per session; that figure matches the TUI exactly and leads the transcript by up to one turn. Without the sidecar, status shows `ctx=<used>/?`. 1M-context models print `[1m]` in the model id and supervisr reads a 1,000,000 window from that even without the sidecar.

**Do NOT use as fill:**
- **Per-turn token numbers** from the pane (`↑ 32k tokens`, `↓ 19.9k`). Those are per-turn input/output deltas for the active burst, not cumulative session size; they consistently undershoot when read as fill.
- **JSONL file size.** JSON overhead makes the byte/token ratio unstable; MB-based estimates undershoot by ~10pp at moderate fills.
- **`/context`.** Accurate but issuing it interrupts the worker mid-loop; the supervisr readout is non-disruptive.

Per-turn UI numbers can still *interpret* a visible active turn (large input = just consumed a big read; large output = just generated a big write) — read them as telemetry, not fill.

### Deep-context compaction heuristic (1M-window Claude)

A large window is not a reason to wait until nearly full. Long sessions accumulate tool results, abandoned branches, and stale framing well before the hard limit. On a true 1M-context model, begin planning compaction around **30–40%**, especially after many tool turns:

- At ~30%, start watching for the next coherent breakpoint (a slice committed, a review completed, a phase wrapped, an assignment about to change).
- Around 40%, prefer compaction at that breakpoint before giving another substantial task.
- Above that, urgency rises with fill; do not keep starting large new assignments while postponing.
- Do not interrupt a coherent in-flight task merely because a percentage was crossed — the threshold says "find the next pause," not "destroy working context now."

The percentage is one signal alongside session depth, tool-turn count, coherence, and any observed stale-context behavior.

## 5. `/compact`

`/compact` is a TUI command the model cannot invoke on itself — telling Claude to "compact yourself" does nothing. Compaction happens only when the supervisor submits the literal command as the whole input: `supervisr send <name> "/compact"` (no prefix/suffix), and only when the worker is idle. `supervisr send` detects `/compact` and prints the caveat that its completion is **not** observable from the transcript (compaction writes no persisted entry). Do not re-send `/compact` to check — a second compaction can discard the context the first rebuilt. Send the post-compaction orientation message in the same turn (it queues safely), then on a later heartbeat verify via `supervisr screen`/`status` that the context figure dropped. Full procedure and the orientation-message contents are in `core.md`.

## 6. Quirks

- **Subagents** write their own JSONL under `~/.claude/projects/<cwd-key>/<parent-session-id>/subagents/*.jsonl`. supervisr watches the parent session; to observe a subagent, adopt it as a separate worker by its own session file.
- **Compaction boundaries** appear inline in the JSONL as a `compact_boundary` system entry; the cursor handles this transparently, and `watch` shows a `[compaction]` line.
- **No structured "stop" event for permission gating** — but under herdr this is a *strength*: a permission/approval dialog shows as `blocked` in `sweep`, which the tmux/superv setup could not see. If `sweep` shows `idle`/`done` while a dialog is visible, that is the ghost-text case, not a real block.

## 7. Done signals

- Final assistant message with no pending tool calls; `supervisr status` shows `turn=idle` and herdr `done`/`idle`.
- Worker says "all done" / "ready for review" **and** validations actually ran (verify read-only with `git`/tests, or ask the worker to run them per the verification ladder in `core.md`).

## 8. Stepping away / resume

herdr persists the pane; there is no pause/resume CLI. Detaching herdr keeps Claude running, and a herdr server restart relaunches it with `claude --resume <id>` from the reported session id — the observation cursor (keyed by that session id) survives untouched. To end it, `supervisr stop <name> --close-pane`.

## 9. Kickoff additions (Claude)

Append to the core kickoff:

```
9. You are running with --dangerously-skip-permissions; permission prompts will not block you.
10. Use TaskCreate / TaskUpdate liberally to track progress; the supervisor reads them.
11. When you compact, it's fine — the supervisor's cursor survives compaction.
```
