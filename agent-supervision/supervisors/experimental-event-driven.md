# Supervisor — Experimental Event-Driven Mode

This is an opt-in overlay for a scheduled supervisor. Use it only when the user explicitly selects experimental event-driven supervision. Read it after `core.md`, `supervisors/scheduled.md`, the worker docs, and their transport docs.

The ordinary scheduled-supervision rules continue to apply except for the narrow overrides stated here.

## Lifecycle

Event-driven supervision uses two mechanisms:

- `superv await <id>` is a one-shot background attention notifier for one active worker.
- The global recurring heartbeat is a monitoring backstop for hangs, dead waiter processes, missed events, permission prompts absent from persisted history, and mistaken premises.

The background waiter is the primary alert for an ordinary worker turn ending. The heartbeat remains active until a supervisor-level teardown condition applies. Use a four-minute heartbeat unless the user requests another cadence; four minutes remains inside the prompt-cache window described in `scheduled.md`.

## Await override

This mode narrowly overrides `core.md`'s prohibition on waiting for a supervised worker. The allowed mechanism must satisfy all of these conditions:

- `superv await` runs through the supervisor host's background-command facility.
- The supervisor's active turn is free to end and respond to other events.
- A recurring global heartbeat remains active as a monitoring backstop.
- The waiter is treated only as an attention signal; worker content is read through `superv watch`.

A foreground command that holds the supervisor's active turn open remains prohibited.

## Dispatch and arm

For each worker assignment:

1. Send the assignment and verify that it landed.
2. Start `superv await <id>` through the host's background-command facility.
3. End the supervisor turn normally.
4. When the background command exits, run `superv watch <id>` until it reports `OBSERVATION COMPLETE`, then interpret the worker's state.
5. Rearm only after dispatching more work to that worker.

An idle worker already needs attention. If `await` starts after a fast worker has completed, it exits immediately with `IDLE`. Do not rearm an idle worker merely to keep a waiter present.

## Attention events

The waiter exits for these structural events:

- `IDLE` — the worker reached a terminal turn or was idle when the waiter started.
- `COMPACTION` — the persisted stream recorded a compaction boundary. The worker may stop or continue; inspect the stream.
- `STREAM RESYNC REQUIRED` — the transcript changed identity, shrank, left Pi's armed branch, or could not provide a reliable turn state.

Compaction interrupts the wait immediately because post-compaction continuation is not predictable. The supervisor determines what happened next through `watch`.

`await` does not classify worker completion, blockers, questions, or corrections. It does not print worker message text, summaries, excerpts, or locators, and it never advances the watch cursor. Its output deliberately directs the supervisor to the authoritative stream:

```text
ATTENTION bob: IDLE
Run: superv watch bob
```

## Supported workers

The experimental command supports Pi, Claude Code, and Codex through their persisted JSONL formats. OpenCode is rejected until its compaction behavior has an established event contract.

## Backstop heartbeat

On each heartbeat, reassess the overall assignment as usual. In addition, check for active work that has no functioning waiter or has remained busy without a structural event. The heartbeat is responsible for conditions an append-driven waiter cannot observe reliably, including a hung generation and a live-channel permission prompt.

An await process exiting does not affect heartbeat teardown. Apply the supervisor-level steady-state test from `core.md` independently.
