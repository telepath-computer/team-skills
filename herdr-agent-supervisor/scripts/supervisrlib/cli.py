"""supervisr — the supervisor's command set, on top of herdr.

Every command a supervisor runs while supervising lives here. Observation reads
the worker's transcript through a cursor; control goes through herdr's agent
API. Raw `herdr` is for setup-time topology only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import state
from .adapters import SUPPORTED_KINDS, Source, adapter_for
from .herdr import (METADATA_SOURCE, OWNER_TOKEN, Client, Context, HerdrError, Scope, agent_label, wait_for)
from .render import (MAX_RENDERED_CHARS, RECENT_COUNT_DEFAULT, clip_overview, fmt_tokens, overview_page,
                     render_entries, render_overview)
from .resolve import ResolveError, resolve

SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
SIDE_CAR = SKILL_ROOT / "scripts" / "claude-statusline-sidecar.py"
SETTLED = ["idle", "done", "blocked"]
KEY_NAMES = {"enter", "esc", "escape", "tab", "space", "up", "down", "left", "right", "backspace",
             "ctrl+c", "ctrl+d", "ctrl+u", "shift+tab", "y", "n"} | {str(d) for d in range(10)}
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

# Launch defaults. Deliberate choices, visible in --help; override per dispatch.
DEFAULT_EFFORT = "xhigh"
DEFAULT_MODEL = {
    "claude": "claude-fable-5",
    "codex": "gpt-5.6-sol",
    "pi": "openai-codex/gpt-5.6-sol",   # reasoning level appended as :<effort>
}
DEFAULT_TAB_PLACEMENT = True   # each dispatched agent gets its own tab unless --split/--pane


def eprint(*a: Any) -> None:
    print(*a, file=sys.stderr)


class Supervisr:
    def __init__(self, args: argparse.Namespace):
        for name, default in (("workspace", None), ("tab", None), ("owned", False), ("all", False),
                              ("repo", False), ("include_self", False), ("session", None),
                              ("json", False), ("verbose", False)):
            if not hasattr(args, name):
                setattr(args, name, default)
        self.args = args
        self.ctx = Context()
        self.client = Client(session=args.session, verbose=args.verbose)
        self.scope = Scope(self.ctx, workspace=args.workspace, tab=args.tab, owned=args.owned,
                           all_agents=args.all, repo=args.repo, include_self=args.include_self)
        self.json = bool(args.json)

    # -- targets ---------------------------------------------------------------

    def agent(self, target: str) -> Dict[str, Any]:
        try:
            return self.client.agent_get(target)
        except HerdrError as e:
            if e.code in {"agent_not_found", "target_not_found", "not_found"} or "not found" in e.message:
                raise SystemExit(f"error: no agent '{target}' in herdr (targets are agent names or pane ids; "
                                 f"try `supervisr sweep --all`)")
            raise

    def source(self, agent: Dict[str, Any]) -> Source:
        return resolve(self.client, agent)

    def target_source(self, target: str) -> Tuple[Dict[str, Any], Source]:
        agent = self.agent(target)
        try:
            return agent, self.source(agent)
        except ResolveError as e:
            raise SystemExit(f"error: {agent_label(agent)}: {e}")

    def my_id(self) -> str:
        return self.ctx.pane_id or "cli"

    # -- status line -------------------------------------------------------------

    def signals_for(self, agent: Dict[str, Any]) -> Dict[str, Any]:
        try:
            src = self.source(agent)
        except ResolveError as e:
            return {"resolve_error": e.reason, "resolve_message": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"resolve_error": "error", "resolve_message": str(e)}
        sig = adapter_for(src.kind).status_signals(src)
        sig["sid"] = src.sid
        sig["path"] = str(src.path) if src.path else None
        return sig

    @staticmethod
    def verdict(agent: Dict[str, Any], sig: Dict[str, Any]) -> str:
        h = str(agent.get("agent_status") or "unknown")
        t = sig.get("turn", "unknown")
        age = sig.get("persisted_age_s", float("inf"))
        if h == "blocked":
            return "BLOCKED"
        if h == "working":
            if t == "busy" and age > 600:
                return "stalled?"
            if t == "idle" and age > 120:
                return "working?"
            return "working"
        if h in {"idle", "done"}:
            if t == "busy" and age > 20:
                return "idle?"  # transcript expects a tool result herdr's screen does not see
            return "done" if h == "done" else "idle"
        return {"busy": "busy?", "idle": "idle?"}.get(t, "unknown")

    def status_record(self, agent: Dict[str, Any], sig: Dict[str, Any], *, with_latest: bool) -> Dict[str, Any]:
        rec = {
            "name": agent_label(agent), "kind": agent.get("agent"), "pane_id": agent.get("pane_id"),
            "workspace_id": agent.get("workspace_id"), "herdr_status": agent.get("agent_status"),
        }
        if sig.get("resolve_error"):
            rec.update({"verdict": f"{agent.get('agent_status', '?')}", "observe": sig["resolve_error"],
                        "observe_message": sig.get("resolve_message")})
            return rec
        rec.update({
            "verdict": self.verdict(agent, sig), "turn": sig.get("turn"), "unread": sig.get("unread_count"),
            "ctx_tokens": sig.get("context_input_tokens"), "ctx_window": sig.get("context_window_tokens"),
            "age_s": None if sig.get("persisted_age_s") == float("inf") else round(sig.get("persisted_age_s", 0), 1),
            "sid": sig.get("sid"), "model": sig.get("model"),
        })
        if with_latest:
            marker = sig.get("latest_marker")
            rec["latest"] = {"kind": marker[0], "text": marker[1]} if marker else None
            if rec["verdict"] == "BLOCKED":
                rec["blocked_on"] = self.blocked_evidence(agent)
        return rec

    def blocked_evidence(self, agent: Dict[str, Any], *, full: bool = False) -> Optional[str]:
        """The matched blocked rule's evidence. Truncated for display; pass
        full=True (used by dialog matching) to get the whole region + rule id,
        so a long cwd path can't push a marker phrase into the elided middle."""
        try:
            ex = self.client.agent_explain(agent.get("pane_id") or agent_label(agent))
        except Exception:
            return None
        for rule in ex.get("evaluated_rules") or []:
            if rule.get("matched") and rule.get("state") == "blocked":
                preview = (rule.get("evidence") or {}).get("region_preview") or ""
                if full:
                    return f"{rule.get('id', '')} {preview}"
                text, _ = clip_overview(preview, 140, preserve_tail=True)
                return text or rule.get("id")
        return None

    @staticmethod
    def fmt_line(rec: Dict[str, Any]) -> str:
        name = rec["name"]
        kind = rec.get("kind") or "?"
        if rec.get("observe"):
            return f"{name:<10} {kind:<8} {str(rec.get('herdr_status') or '?'):<9} no-transcript ({rec['observe']}: {rec.get('observe_message', '')})"
        ctx = rec.get("ctx_tokens")
        win = rec.get("ctx_window")
        if ctx and win:
            ctx_s = f"ctx={fmt_tokens(ctx)}/{fmt_tokens(win)}({ctx / win * 100:.0f}%)"
        elif ctx:
            ctx_s = f"ctx={fmt_tokens(ctx)}/?"
        else:
            ctx_s = "ctx=?"
        age = rec.get("age_s")
        age_s = f"age={age / 60:.1f}m" if age is not None else "age=?"
        unread = rec.get("unread")
        parts = [f"{name:<10}", f"{kind:<8}", f"{rec['verdict']:<9}",
                 f"unread={unread if unread is not None else '?':<4}", f"{ctx_s:<18}", f"{age_s:<9}"]
        tail = ""
        if rec.get("blocked_on"):
            tail = f"BLOCKED ON: {rec['blocked_on']}"
        elif rec.get("latest"):
            text, _ = clip_overview(rec["latest"]["text"], 140, preserve_tail=True)
            prefix = "intent: " if rec["latest"]["kind"] == "intent" else ("user: " if rec["latest"]["kind"] == "user" else "")
            tail = prefix + text
        return " ".join(parts) + (" " + tail if tail else "")

    # -- commands: observe -------------------------------------------------------

    def cmd_sweep(self) -> int:
        snapshot = self.client.snapshot()
        agents = self.scope.select(snapshot)
        if not agents:
            print(f"(no agents in scope: {self.scope.describe()})")
            return 0
        records = []
        for a in agents:
            sig = self.signals_for(a)
            rec = self.status_record(a, sig, with_latest=True)
            records.append(rec)
            if self.args.publish and a.get("pane_id"):
                self.publish_tokens(a["pane_id"], rec)
        if self.json:
            print(json.dumps(records, indent=1, ensure_ascii=False))
            return 0
        for rec in records:
            print(self.fmt_line(rec))
        attention = [r["name"] for r in records if r["verdict"] in {"BLOCKED", "done", "stalled?"} or
                     (r.get("unread") or 0) > 0]
        print(f"\nscope: {self.scope.describe()} · {len(records)} agents · attention: {', '.join(attention) or 'none'}")
        return 0

    def publish_tokens(self, pane_id: str, rec: Dict[str, Any]) -> None:
        tokens: Dict[str, Optional[str]] = {}
        if rec.get("unread") is not None:
            tokens["sv_unread"] = str(rec["unread"])
        if rec.get("ctx_tokens") and rec.get("ctx_window"):
            tokens["sv_ctx"] = f"{rec['ctx_tokens'] / rec['ctx_window'] * 100:.0f}%"
        if rec.get("latest"):
            text, _ = clip_overview(rec["latest"]["text"], 78)
            tokens["sv_intent"] = text
        if tokens:
            try:
                self.client.report_tokens(pane_id, METADATA_SOURCE, tokens, ttl_ms=15 * 60 * 1000)
            except HerdrError as e:
                eprint(f"warn: token publish failed for {pane_id}: {e}")

    def cmd_status(self) -> int:
        agent = self.agent(self.args.target)
        rec = self.status_record(agent, self.signals_for(agent), with_latest=True)
        print(json.dumps(rec, indent=1, ensure_ascii=False) if self.json else self.fmt_line(rec))
        return 0

    def cmd_watch(self) -> int:
        a = self.args
        agent, src = self.target_source(a.target)
        ad = adapter_for(src.kind)
        label = agent_label(agent)
        if a.count is not None and a.count <= 0:
            raise SystemExit("watch --count must be a positive integer")
        if a.reset:
            state.reset_cursor(src.sid)
        use_cursor = not a.full
        read_count = a.count if a.count is not None else (RECENT_COUNT_DEFAULT if a.reset else None)
        if a.full and a.count is None:
            read_count = sys.maxsize
        try:
            entries, new_cursor = ad.read_persisted(src, count=read_count, use_cursor=use_cursor)
        except ValueError as e:
            raise SystemExit(f"error: {label}: {e}")
        if not entries:
            print("(no new entries)")
            state.save_cursor(src.sid, new_cursor)
            return 0
        detailed = render_entries(entries)
        if len(detailed) <= MAX_RENDERED_CHARS or a.force:
            print(detailed)
            state.save_cursor(src.sid, new_cursor)
            if a.count is None and not a.reset:
                print(f"\nOBSERVATION COMPLETE — {len(entries)}/{len(entries)} unread entries shown; cursor advanced through all.")
            return 0
        page = overview_page(entries)
        complete = len(page) == len(entries)
        print(f"COMPACT OVERVIEW — detailed content shortened ({len(entries)} unread entries)\n")
        print(render_overview(page))
        if any(e.overview_was_truncated() for e in page):
            print(f"\nLines ending in … were shortened. Use `supervisr detail {label} <locator>` to inspect one entry.")
        cursor_to_save = new_cursor if complete else page[-1].cursor_after
        if cursor_to_save is None:
            raise SystemExit("internal error: overview page has no cursor boundary")
        state.save_cursor(src.sid, cursor_to_save)
        if complete:
            print(f"\nOBSERVATION COMPLETE — {len(page)}/{len(entries)} unread entries shown (compact); cursor advanced through all.")
        else:
            remaining = len(entries) - len(page)
            print(f"\n⚠ INCOMPLETE OBSERVATION — {len(page)}/{len(entries)} unread entries shown; {remaining} remain.")
            print(f"Cursor advanced through shown entries only. Run again: supervisr watch {label}")
            print("Repeat until OBSERVATION COMPLETE.")
            print(f"Intentional skip: supervisr watch {label} --reset --count <N> (discards unread remainder).")
        return 0

    def cmd_detail(self) -> int:
        a = self.args
        if a.raw != a.force:
            raise SystemExit("unbounded raw detail requires both --raw and --force")
        agent, src = self.target_source(a.target)
        ad = adapter_for(src.kind)
        try:
            if a.raw:
                print(json.dumps(ad.raw_detail(src, a.locator), indent=2, ensure_ascii=False))
                return 0
            rendered = ad.detail(src, a.locator)
        except ValueError as e:
            raise SystemExit(f"error: {e}")
        if len(rendered) <= MAX_RENDERED_CHARS:
            print(rendered)
        else:
            shown, _ = clip_overview(rendered, MAX_RENDERED_CHARS, preserve_tail=True)
            print(shown)
            print(f"\nDETAIL SHORTENED — original rendered content was {len(rendered)} characters.")
        return 0

    def cmd_recent(self) -> int:
        a = self.args
        if a.count <= 0:
            raise SystemExit("recent --count must be a positive integer")
        agent, src = self.target_source(a.target)
        ad = adapter_for(src.kind)
        entries, _ = ad.read_persisted(src, count=sys.maxsize, use_cursor=False)
        lines = [l for e in entries for l in e.overview]
        if a.kind == "messages":
            lines = [l for l in lines if l.kind in {"assistant", "user", "intent"}]
        elif a.kind == "tools":
            lines = [l for l in lines if l.kind in {"tool", "result"}]
        elif a.kind == "errors":
            pattern = re.compile(r"\b(error|failed|failure)\b|\bexit=[1-9]\d*", re.I)
            lines = [l for l in lines if pattern.search(l.text)]
        selected = lines[-a.count:]
        if not selected:
            print("(no matching recent entries)")
            return 0
        print("\n".join(l.render() for l in selected))
        if any(l.truncated for l in selected):
            print(f"\nLines ending in … were shortened. Use `supervisr detail {agent_label(agent)} <locator>` to inspect one entry.")
        print("\n(recent query did not move the watch cursor)")
        return 0

    def cmd_screen(self) -> int:
        a = self.args
        agent = self.agent(a.target)
        lines = max(1, min(a.lines, 120))
        read = self.client.agent_read(agent.get("pane_id") or a.target, lines)
        text = read.get("text", "").rstrip("\n")
        print(f"screen {agent_label(agent)} · last {lines} lines · herdr={agent.get('agent_status')} · "
              f"liveness only — routine observation is `supervisr watch`")
        print("-" * 72)
        print(text)
        return 0

    def cmd_explain(self) -> int:
        agent = self.agent(self.args.target)
        ex = self.client.agent_explain(agent.get("pane_id") or self.args.target)
        if self.json:
            print(json.dumps(ex, indent=1, ensure_ascii=False))
            return 0
        print(f"{agent_label(agent)}: agent={ex.get('agent')} status={agent.get('agent_status')} "
              f"source={ex.get('manifest_source') or ex.get('source') or '?'}")
        matched = [r for r in ex.get("evaluated_rules") or [] if r.get("matched")]
        for r in matched[:3]:
            preview, _ = clip_overview((r.get("evidence") or {}).get("region_preview") or "", 300, preserve_tail=True)
            print(f"  matched {r.get('id')} → {r.get('state')} (prio {r.get('priority')}, region {r.get('region')})")
            if preview:
                print(f"    {preview}")
        if not matched:
            print(f"  no rule matched; fallback={ex.get('fallback_reason') or ex.get('fallback') or '?'}")
        if ex.get("screen_detection_skip_reason"):
            print(f"  screen detection skipped: {ex['screen_detection_skip_reason']}")
        return 0

    # -- commands: act -------------------------------------------------------------

    def _read_message(self) -> str:
        a = self.args
        if a.message and a.file:
            raise SystemExit("send: pass either a positional message OR --file <path>, not both")
        if a.file:
            p = Path(a.file)
            if not p.exists():
                raise SystemExit(f"--file path does not exist: {p}")
            text = p.read_text(encoding="utf-8")
        else:
            text = a.message or ""
        if not text.strip():
            raise SystemExit("send: empty message")
        return text

    @staticmethod
    def is_compaction_command(text: str) -> bool:
        first = text.strip().splitlines()[0].strip() if text.strip() else ""
        return first == "/compact" or first.startswith("/compact ")

    def cmd_send(self) -> int:
        # A thin pass-through to herdr's agent.prompt. herdr types the prompt,
        # owns readiness, and — with --wait — confirms the turn took effect
        # (its effect-gate catches an unsubmitted composer via state_change_seq)
        # and waits for the settled state. supervisr adds nothing here except the
        # /compact caveat, which is knowledge herdr does not have.
        a = self.args
        text = self._read_message()
        agent = self.agent(a.target)
        label = agent_label(agent)
        target = agent.get("pane_id") or a.target
        if agent.get("agent_status") == "blocked":
            print(f"{label} is BLOCKED at a dialog; refusing to type a prompt into it.\n"
                  f"  inspect: supervisr screen {label}\n  answer:  supervisr answer {label} <enter|esc|y|n|text>")
            return 3

        wait = {"until": SETTLED, "timeout_ms": int(a.timeout * 1000)} if a.wait else None
        sock_timeout = (a.timeout + 10) if a.wait else None
        try:
            result = self.client.agent_prompt(target, text, wait=wait, timeout=sock_timeout)
        except HerdrError as e:
            if e.code == "agent_blocked":
                print(f"{label} is BLOCKED; nothing sent. `supervisr screen {label}` then `supervisr answer`.")
                return 3
            if e.code == "agent_not_ready":
                print(f"{label} is not ready for input yet (herdr). Try again in a moment, or `supervisr screen {label}`.")
                return 5
            if e.code == "agent_prompt_stalled":
                print(f"{label}: herdr saw no state change after the prompt — it may be sitting unsubmitted. "
                      f"Inspect `supervisr screen {label}`.")
                return 4
            if e.code == "timeout":
                print(f"wait: {label} still working after {a.timeout:.0f}s")
                return 2
            raise
        print(f"sent {len(text)} chars to {label} via herdr agent.prompt{' (+waited)' if a.wait else ''}.")

        if self.is_compaction_command(text):
            print("\n!! COMPACTION SENT — its completion cannot be observed from the transcript. !!\n"
                  "Compaction writes no persisted entry. Do NOT re-send /compact to find out whether it worked;\n"
                  "a second compaction can discard the context the first one just rebuilt. Send the\n"
                  "post-compaction orientation message now (it queues safely), and on the next heartbeat\n"
                  f"check `supervisr screen {label}` / `supervisr status {label}` for the reduced context figure.")
            return 0
        if a.wait and result:
            print(self.fmt_line(self.status_record(result, self.signals_for(result), with_latest=True)))
        return 0

    def cmd_answer(self) -> int:
        a = self.args
        agent = self.agent(a.target)
        label = agent_label(agent)
        target = agent.get("pane_id") or a.target
        if agent.get("agent_status") != "blocked" and not a.force:
            print(f"{label} is not BLOCKED (herdr={agent.get('agent_status')}); `answer` is for dialogs. "
                  f"Use `supervisr send` for prompts, or --force.")
            return 3
        tokens = a.keys
        if all(t.lower() in KEY_NAMES for t in tokens):
            keys = ["escape" if t.lower() == "esc" else t.lower() for t in tokens]
            self.client.agent_send_keys(target, keys)
            print(f"sent keys {keys} to {label}")
        else:
            text = " ".join(tokens)
            self.client.pane_send_text(target, text)
            if not a.no_enter:
                time.sleep(0.2)
                self.client.agent_send_keys(target, ["enter"])
            print(f"typed {len(text)} chars{'' if a.no_enter else ' + Enter'} into {label}")
        time.sleep(1.0)
        after = self.client.agent_get(target)
        print(f"{label}: herdr={after.get('agent_status')}")
        return 0

    def cmd_interrupt(self) -> int:
        agent = self.agent(self.args.target)
        target = agent.get("pane_id") or self.args.target
        keys = ["ctrl+c"] if self.args.hard else ["escape"]
        self.client.agent_send_keys(target, keys)
        print(f"sent {keys} to {agent_label(agent)} (Escape cancels a running compaction — be sure none is in flight)")
        return 0

    # -- commands: wait / events ---------------------------------------------------

    def _scope_agents(self) -> List[Dict[str, Any]]:
        return self.scope.select(self.client.snapshot())

    def cmd_wait(self) -> int:
        a = self.args
        until = a.until or SETTLED
        timeout_ms = int(a.timeout * 1000) if a.timeout else None
        if len(a.targets) == 1:
            agent = self.agent(a.targets[0])
            try:
                got = self.client.agent_wait(agent.get("pane_id") or a.targets[0], until, timeout_ms)
            except HerdrError as e:
                if e.code == "timeout":
                    print("TIMEOUT")
                    return 2
                if e.code == "agent_not_running":
                    print(f"EVENT {agent_label(agent)} gone")
                    return 0
                raise
            print(f"EVENT {agent_label(got)} {got.get('agent_status')}")
            return 0
        agents = [self.agent(t) for t in a.targets] if a.targets else self._scope_agents()
        if not agents:
            print(f"(no agents in scope: {self.scope.describe()})")
            return 1
        for ag in agents:
            if ag.get("agent_status") in until:
                print(f"EVENT {agent_label(ag)} {ag.get('agent_status')}")
                return 0
        return self._stream(agents, until, a.timeout, one_shot=True)

    def cmd_events(self) -> int:
        a = self.args
        agents = [self.agent(t) for t in a.targets] if a.targets else self._scope_agents()
        print(f"READY scope={self.scope.describe()} agents={','.join(agent_label(x) for x in agents) or '-'}", flush=True)
        return self._stream(agents, a.until or None, a.timeout, one_shot=False, rescope=not a.targets)

    def _stream(self, agents: List[Dict[str, Any]], until: Optional[List[str]], timeout_s: Optional[float],
                *, one_shot: bool, rescope: bool = False) -> int:
        names = {ag["pane_id"]: agent_label(ag) for ag in agents}
        last = {ag["pane_id"]: ag.get("agent_status") for ag in agents}
        deadline = time.time() + timeout_s if timeout_s else None
        while True:
            subs = [{"type": "pane.agent_status_changed", "pane_id": pid} for pid in names]
            subs += [{"type": "pane.closed"}, {"type": "pane.exited"}, {"type": "pane.agent_detected"}, {"type": "pane.created"}]
            needs_rescope = False
            idle = max(1.0, (deadline - time.time())) if deadline else 60.0
            for ev in self.client.subscribe(subs, idle_timeout=idle):
                if deadline and time.time() >= deadline:
                    print("TIMEOUT", flush=True)
                    return 2
                if not isinstance(ev, dict):
                    continue
                if ev.get("type") == "timeout":
                    continue
                if "error" in ev:
                    # A pane in our subscription list closed between snapshot and
                    # subscribe. Drop it and rescope rather than killing the stream.
                    if rescope:
                        needs_rescope = True
                        break
                    eprint(f"events: {ev['error']}")
                    return 1
                if "result" in ev:
                    continue  # subscription_started
                # herdr names status events "pane.agent_status_changed" but lifecycle
                # events "pane_closed"/"pane_exited"/"pane_created"; accept both spellings.
                et = str(ev.get("event") or "").replace(".", "_")
                payload = ev.get("data") if isinstance(ev.get("data"), dict) else {}
                if et == "pane_agent_status_changed":
                    pid = payload.get("pane_id")
                    if pid not in names:
                        continue
                    # A new subscription replays recent history; trust the live status,
                    # not the event's, so stale replays collapse into no-ops.
                    try:
                        status = self.client.agent_get(pid).get("agent_status")
                    except HerdrError:
                        status = payload.get("agent_status")
                    if status == last.get(pid):
                        continue
                    last[pid] = status
                    if until is None or status in until:
                        print(f"EVENT {names[pid]} {status}", flush=True)
                        if one_shot:
                            return 0
                elif et in {"pane_closed", "pane_exited"}:
                    pid = payload.get("pane_id") or (payload.get("pane") or {}).get("pane_id")
                    if pid in names:
                        print(f"EVENT {names[pid]} gone", flush=True)
                        if one_shot:
                            return 0
                        names.pop(pid, None)
                        needs_rescope = True
                        break
                elif et in {"pane_agent_detected", "pane_created"} and rescope:
                    needs_rescope = True
                    break
            if not needs_rescope:
                # Server closed the stream: re-check scope and reconnect.
                time.sleep(1.0)
            if rescope:
                try:
                    fresh = self._scope_agents()
                except Exception:
                    fresh = []
                for ag in fresh:
                    if ag["pane_id"] not in names:
                        names[ag["pane_id"]] = agent_label(ag)
                        last[ag["pane_id"]] = ag.get("agent_status")
                        print(f"EVENT {agent_label(ag)} appeared {ag.get('agent_status')}", flush=True)
            if not names and one_shot:
                print("(no agents left in scope)")
                return 1

    # -- commands: lifecycle ---------------------------------------------------------

    def _launch_args(self, kind: str) -> List[str]:
        a = self.args
        extra = list(a.agent_args or [])
        model = a.model or DEFAULT_MODEL.get(kind)
        effort = a.effort or DEFAULT_EFFORT
        if kind == "claude":
            return ["--dangerously-skip-permissions", "--model", model, "--effort", effort] + extra
        if kind == "codex":
            return ["--yolo", "-m", model, "-c", f"model_reasoning_effort={effort}"] + extra
        if kind == "pi":
            # pi encodes the reasoning level in the model string; an explicit --model with
            # its own :level wins over --effort.
            if ":" not in model:
                model = f"{model}:{effort}"
            return ["--model", model, "--session-id", f"{a.name}-{uuid.uuid4()}"] + extra
        raise SystemExit(f"unsupported kind: {kind}")

    def cmd_dispatch(self) -> int:
        a = self.args
        if not NAME_RE.match(a.name):
            raise SystemExit("name must match ^[a-z][a-z0-9_-]{0,31}$ and be unique across the herdr session")
        kind = a.kind
        if kind not in SUPPORTED_KINDS:
            raise SystemExit(f"--kind must be one of {', '.join(SUPPORTED_KINDS)}")
        prompt = None
        if a.prompt or a.file:
            prompt = a.prompt or Path(a.file).read_text(encoding="utf-8")
        cwd = os.path.abspath(a.cwd) if a.cwd else None
        if a.worktree:
            cwd = self._make_worktree(a.worktree, a.base, a.worktree_root)
        launch_args = self._launch_args(kind)
        ws = a.workspace or self.ctx.workspace_id

        if a.pane:
            pane_id = a.pane
        elif a.split:
            # Explicit split requested; otherwise each agent gets its own tab.
            anchor = a.split_from or self.ctx.pane_id
            if not anchor and not ws:
                raise SystemExit("no pane to split from: run inside herdr, or pass --split-from <pane> or --pane")
            pane = self.client.pane_split(anchor, a.split, cwd, workspace_id=None if anchor else ws, focus=False)
            pane_id = pane.get("pane_id")
        else:
            if not ws:
                raise SystemExit("a new tab needs a workspace: run inside herdr, or pass --workspace "
                                 "(or place the agent yourself with --split/--pane)")
            res = self.client.tab_create(ws, a.tab_label or a.name, cwd, focus=False)
            pane_id = (res.get("root_pane") or {}).get("pane_id")
        if not pane_id:
            raise SystemExit("could not determine the new pane id from herdr's response")
        print(f"pane {pane_id}" + (f" cwd={cwd}" if cwd else ""))

        if cwd and a.pane:
            # an existing shell pane: move it to the requested directory first
            self.client.pane_send_text(pane_id, f"cd {shlex.quote(cwd)}\n")
            time.sleep(0.3)

        print(f"starting {kind} as '{a.name}': {kind} {' '.join(shlex.quote(x) for x in launch_args)}")
        deadline = time.time() + 15.0
        while True:
            try:
                res = self.client.agent_start(a.name, kind, pane_id, launch_args, timeout_ms=int(a.start_timeout * 1000))
                break
            except HerdrError as e:
                # A freshly split pane's shell (prompt init, rc files) is briefly "not an
                # available shell"; give it a few seconds before giving up.
                if e.code in {"agent_pane_busy", "agent_pane_unavailable"} and time.time() < deadline:
                    time.sleep(0.5)
                    continue
                raise SystemExit(f"agent start failed: {e}\n  the pane {pane_id} is left as-is for inspection")
        agent = res.get("agent") or {}
        print(f"started: {agent_label(agent)} pane={agent.get('pane_id')} herdr={agent.get('agent_status')}")
        self._stamp_owner(pane_id)

        agent = self._await_ready(a.name, pane_id, a.start_timeout, trust_folder=a.trust_folder)
        if agent is None:
            return 3

        if prompt:
            self.args.target = a.name
            self.args.message = prompt
            self.args.file = None
            self.args.wait = a.wait
            self.args.timeout = a.timeout
            rc = self.cmd_send()
            if rc in (3, 5):   # blocked / not-ready: could not deliver
                return rc
        sid = wait_for(lambda: ((self.client.agent_get(a.name).get("agent_session") or {}).get("value")), 5.0, 0.5)
        print(f"session: {sid or 'not reported yet (herdr integration hook fires at session start)'}")
        print(f"next: supervisr sweep · supervisr watch {a.name}")
        return 0

    def _await_ready(self, name: str, pane_id: str, timeout_s: float, *, trust_folder: bool) -> Optional[Dict[str, Any]]:
        """Wait — via herdr — until the new agent can take input.

        The waiting is herdr's: `agent.wait` for a settled state, then herdr's
        own `interactive_ready` flag. The only thing supervisr adds is answering
        a startup trust dialog, which herdr detects (as `blocked`) but will not
        answer on its own.
        """
        for _ in range(4):
            try:
                agent = self.client.agent_wait(pane_id, SETTLED, int(timeout_s * 1000))
            except HerdrError as e:
                if e.code == "timeout":
                    print(f"{name}: not settled after {timeout_s:.0f}s; inspect with `supervisr screen {name}`")
                    return None
                raise
            if agent.get("agent_status") == "blocked":
                evidence = (self.blocked_evidence(agent, full=True) or "").lower()
                is_trust = any(m in evidence for m in (
                    "trust this folder", "quick safety check", "trust_prompt",  # claude
                    "do you trust the contents", "trust the directory",         # codex
                ))
                if is_trust and trust_folder:
                    print(f"{name}: accepting the folder/directory-trust dialog (--trust-folder)")
                    self.client.agent_send_keys(pane_id, ["enter"])
                    time.sleep(1.0)
                    continue
                if is_trust:
                    print(f"{name}: BLOCKED on a folder/directory-trust dialog for this cwd.\n"
                          f"  accept:  supervisr answer {name} enter     (or pass --trust-folder to dispatch)\n"
                          f"  inspect: supervisr screen {name}")
                    return None
                print(f"{name}: BLOCKED at startup — {evidence or 'see supervisr screen ' + name}")
                return None
            # Settled and not a dialog. Wait for herdr to mark the pane
            # interactive-ready before the first prompt (herdr's own signal;
            # a just-cleared banner can be settled-but-not-yet-accepting).
            ready = wait_for(lambda: self.client.agent_get(pane_id).get("interactive_ready"), 10.0, 0.4)
            if not ready:
                print(f"{name}: herdr has not marked the pane interactive-ready; "
                      f"the first prompt may need a retry. Inspect `supervisr screen {name}`.")
            return self.client.agent_get(pane_id)
        print(f"{name}: still blocked after handling startup dialogs; inspect with `supervisr screen {name}`")
        return None
        return None

    def _make_worktree(self, branch: str, base: Optional[str], root: Optional[str]) -> str:
        # Follows the herdr-start-worktree conventions: dir at
        # <repo_parent>/wt/<repo>/<task-slug>, branch thopter/<task-slug>, and a
        # NEW branch bases off the remote default (origin/<default>) after a
        # fetch — so the task starts from the latest published state, not stale
        # local HEAD. The dir is the task slug (a leading thopter/ is stripped),
        # not the full branch slug.
        repo = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if repo.returncode != 0:
            raise SystemExit("--worktree requires running inside the git repo the worktree should belong to")
        repo_root = repo.stdout.strip()
        root_dir = Path(root or (Path(repo_root).parent / "wt" / Path(repo_root).name))
        task_slug = re.sub(r"^thopter/", "", branch).replace("/", "-")
        path = root_dir / task_slug
        if path.exists():
            print(f"worktree exists: {path}")
            return str(path)
        root_dir.mkdir(parents=True, exist_ok=True)
        exists = subprocess.run(["git", "-C", repo_root, "rev-parse", "--verify", "--quiet", branch],
                                capture_output=True).returncode == 0
        if exists:
            cmd = ["git", "-C", repo_root, "worktree", "add", str(path), branch]
        else:
            if base is None:
                subprocess.run(["git", "-C", repo_root, "fetch", "--all", "--prune"],
                               capture_output=True, text=True)
                base = self._remote_default_ref(repo_root)
            cmd = ["git", "-C", repo_root, "worktree", "add", "-b", branch, str(path), base]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"git worktree add failed: {r.stderr.strip()}")
        print(f"worktree: {path} (branch {branch} {'reused' if exists else 'new, off ' + base})")
        return str(path)

    @staticmethod
    def _remote_default_ref(repo_root: str) -> str:
        # origin/HEAD → origin/<default>; fall back to origin/main then HEAD.
        r = subprocess.run(["git", "-C", repo_root, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().replace("refs/remotes/", "", 1)
        for cand in ("origin/main", "origin/master"):
            if subprocess.run(["git", "-C", repo_root, "rev-parse", "--verify", "--quiet", cand],
                              capture_output=True).returncode == 0:
                return cand
        return "HEAD"

    def _stamp_owner(self, pane_id: str) -> None:
        try:
            self.client.report_tokens(pane_id, METADATA_SOURCE, {OWNER_TOKEN: self.my_id()})
        except HerdrError as e:
            eprint(f"warn: could not stamp owner token: {e}")

    def cmd_adopt(self) -> int:
        a = self.args
        agent, src = self.target_source(a.target)
        ad = adapter_for(src.kind)
        if a.count:
            entries, new_cursor = ad.read_persisted(src, count=sys.maxsize, use_cursor=False)
            keep = entries[-a.count:]
            before = entries[:-a.count] if a.count < len(entries) else []
            cursor = before[-1].cursor_after if before else None
            if cursor:
                state.save_cursor(src.sid, cursor)
            else:
                state.reset_cursor(src.sid)
            print(f"adopted {agent_label(agent)} ({src.kind}, session {src.sid}); {len(keep)} entries left unread")
        else:
            state.save_cursor(src.sid, ad.tail_cursor(src))
            print(f"adopted {agent_label(agent)} ({src.kind}, session {src.sid}); cursor at current tail")
        if agent.get("pane_id"):
            self._stamp_owner(agent["pane_id"])
        return 0

    def cmd_stop(self) -> int:
        a = self.args
        agent = self.agent(a.target)
        label = agent_label(agent)
        pane_id = agent.get("pane_id")
        if a.close_pane:
            self.client.pane_close(pane_id)
            print(f"closed pane {pane_id} ({label}); cursor and notes kept — `supervisr forget {label}` to drop them")
            return 0
        self.client.agent_send_keys(pane_id, ["ctrl+c"])
        time.sleep(0.4)
        self.client.agent_send_keys(pane_id, ["ctrl+c"])
        print(f"sent ctrl+c ×2 to {label}; verify with `supervisr status {label}` (use --close-pane to end the pane)")
        return 0

    def cmd_forget(self) -> int:
        t = self.args.target
        sid = None
        try:
            agent = self.client.agent_get(t)
            try:
                sid = self.source(agent).sid
            except Exception:
                sid = (agent.get("agent_session") or {}).get("value")
        except HerdrError:
            sid = t
        if not sid:
            raise SystemExit(f"cannot determine a session id for {t}")
        removed = state.forget(sid)
        print(f"forgot {sid}: removed {', '.join(removed) or 'nothing'}")
        return 0

    # -- commands: notes ---------------------------------------------------------------

    def cmd_note(self) -> int:
        agent, src = self.target_source(self.args.target)
        p = state.append_note(src.sid, agent_label(agent), self.args.text, self.args.tag)
        print(f"noted → {p}")
        return 0

    def cmd_notes(self) -> int:
        agent, src = self.target_source(self.args.target)
        p = state.notes_path(src.sid)
        print(p.read_text(encoding="utf-8") if p.exists() else f"(no notes for {agent_label(agent)})")
        return 0

    # -- commands: setup / doctor ---------------------------------------------------------

    def cmd_doctor(self) -> int:
        ok = True

        def line(status: str, text: str) -> None:
            print(f"  [{status}] {text}")

        print("herdr")
        try:
            snap = self.client.snapshot()
            line("ok", f"server reachable at {self.client.path} (herdr {snap.get('version')}, protocol {snap.get('protocol')})")
        except Exception as e:
            line("FAIL", f"herdr not reachable: {e}")
            return 1
        if self.ctx.inside_herdr():
            line("ok", f"running inside herdr: workspace={self.ctx.workspace_id} pane={self.ctx.pane_id}")
        else:
            line("warn", "not inside a herdr pane: default scope needs --workspace/--all; dispatch needs --tab/--pane")

        print("integrations (how herdr learns session ids)")
        try:
            out = subprocess.run(["herdr", "integration", "status"], capture_output=True, text=True, timeout=15).stdout
        except Exception as e:  # noqa: BLE001
            out = ""
            line("warn", f"could not run `herdr integration status`: {e}")
        for kind in SUPPORTED_KINDS:
            m = re.search(rf"^{kind}:\s*(.+)$", out, re.M)
            status = (m.group(1) if m else "?").strip()
            good = status.startswith("current")
            line("ok" if good else "warn", f"{kind}: {status}" + ("" if good else f"  → herdr integration install {kind}"))
            ok = ok and good

        print("claude context window (statusline sidecar)")
        settings = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"
        try:
            cmd = (json.loads(settings.read_text()).get("statusLine") or {}).get("command", "")
        except Exception:
            cmd = ""
        if str(SIDE_CAR) in cmd:
            line("ok", f"sidecar installed ({settings})")
            chain = state.load_sidecar_config().get("statusline_chain")
            if chain:
                probe = json.dumps({"session_id": "", "model": {"display_name": "probe"},
                                    "context_window": {"context_window_size": 1000, "used_percentage": 0,
                                                       "total_input_tokens": 0}})
                try:
                    r = subprocess.run(chain, shell=True, input=probe, capture_output=True, text=True, timeout=5)
                    chain_ok = r.returncode == 0 and bool(r.stdout.strip())
                except Exception:
                    chain_ok = False
                if chain_ok:
                    line("ok", f"chained statusline works: {chain}")
                else:
                    line("warn", f"chained statusline is broken: {chain}\n"
                                 f"      the sidecar shows its default line instead; re-run toolbringer's status line "
                                 f"step, or fix `statusline_chain` in {state.SIDECAR_CONFIG_PATH}")
        else:
            line("warn", "sidecar not installed → `supervisr setup statusline` (Claude ctx% will show as ?)")

        print(f"state: {state.STATE_ROOT}")
        print(f"agents in scope ({self.scope.describe()})")
        agents = self.scope.select(snap)
        if not agents:
            line("info", "none")
        for a in agents:
            try:
                src = self.source(a)
                line("ok", f"{agent_label(a)} {a.get('agent')} → {src.path or src.sid}")
            except ResolveError as e:
                line("warn", f"{agent_label(a)} {a.get('agent')}: {e.reason}: {e}")
            except Exception as e:  # noqa: BLE001
                line("warn", f"{agent_label(a)}: {e}")
        return 0 if ok else 1

    def cmd_setup(self) -> int:
        a = self.args
        if a.what == "statusline":
            return self._setup_statusline(uninstall=a.uninstall, force=a.force)
        raise SystemExit("setup: unknown target (try: statusline)")

    def _setup_statusline(self, *, uninstall: bool, force: bool) -> int:
        settings = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"
        data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
        current = data.get("statusLine") or {}
        cfg = state.load_sidecar_config()
        sidecar_cmd = f"python3 {shlex.quote(str(SIDE_CAR))}"
        if uninstall:
            if str(SIDE_CAR) not in str(current.get("command", "")):
                print("sidecar is not installed; nothing to do")
                return 0
            chain = cfg.pop("statusline_chain", None)
            if chain:
                data["statusLine"] = {"type": "command", "command": chain}
            else:
                data.pop("statusLine", None)
            settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            state.save_sidecar_config(cfg)
            print(f"restored statusLine to {chain or '(none)'}")
            return 0
        if str(SIDE_CAR) in str(current.get("command", "")) and not force:
            print("sidecar already installed")
            return 0
        if current.get("command") and str(SIDE_CAR) not in current["command"]:
            cfg["statusline_chain"] = current["command"]
            print(f"chaining existing statusline: {current['command']}")
        state.ensure_dirs()
        state.save_sidecar_config(cfg)
        backup = settings.with_name(f"settings.json.pre-supervisr-{int(time.time())}")
        if settings.exists():
            backup.write_text(settings.read_text(encoding="utf-8"), encoding="utf-8")
        data["statusLine"] = {"type": "command", "command": sidecar_cmd}
        settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"installed sidecar statusline → {settings} (backup {backup.name})\n"
              f"  writes {state.CLAUDE_CTX_DIR}/<session-id>.json on every refresh; new Claude sessions pick it up")
        return 0

# -- argparse ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    # Shared flags are accepted before or after the subcommand. SUPPRESS keeps the
    # subparser copy from overwriting a value given at the top level.
    S = argparse.SUPPRESS
    common = argparse.ArgumentParser(add_help=False)
    g = common.add_argument_group("scope")
    g.add_argument("--workspace", default=S, help="scope to a workspace id (default: $HERDR_WORKSPACE_ID)")
    g.add_argument("--tab", default=S, help="scope to a tab id")
    g.add_argument("--owned", action="store_true", default=S, help="only agents this supervisor dispatched/adopted")
    g.add_argument("--all", action="store_true", default=S, help="every agent in the herdr session")
    g.add_argument("--repo", action="store_true", default=S, help="workspaces sharing my workspace's git repo (herdr worktree provenance)")
    g.add_argument("--include-self", action="store_true", default=S, help="do not exclude the calling pane")
    g.add_argument("--session", default=S, help="herdr named session (default: the one this pane runs in)")
    common.add_argument("--json", action="store_true", default=S, help="machine-readable output where supported")
    common.add_argument("--verbose", action="store_true", default=S, help="print underlying herdr calls to stderr")

    p = argparse.ArgumentParser(prog="supervisr", description="agent supervision on herdr", parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name: str, help_: str, **kw):
        return sub.add_parser(name, help=help_, parents=[common], **kw)

    s = add("sweep", "one line per agent in scope; never moves cursors")
    s.add_argument("--publish", action="store_true", help="also push $sv_unread/$sv_ctx/$sv_intent tokens to herdr's sidebar")
    s = add("status", "one line for one agent"); s.add_argument("target")
    s = add("watch", "new transcript entries since the cursor; advances it")
    s.add_argument("target"); s.add_argument("--count", type=int); s.add_argument("--reset", action="store_true")
    s.add_argument("--full", action="store_true"); s.add_argument("--force", action="store_true")
    s = add("detail", "bounded detail for one entry or child locator")
    s.add_argument("target"); s.add_argument("locator"); s.add_argument("--raw", action="store_true"); s.add_argument("--force", action="store_true")
    s = add("recent", "non-mutating tail query")
    s.add_argument("target"); s.add_argument("--kind", choices=["all", "messages", "tools", "errors"], default="all")
    s.add_argument("--count", type=int, default=RECENT_COUNT_DEFAULT)
    s = add("screen", "bounded live screen read (for blocked dialogs; not routine observation)")
    s.add_argument("target"); s.add_argument("--lines", type=int, default=40)
    s = add("explain", "why herdr classifies the agent as it does"); s.add_argument("target")

    s = add("send", "prompt an agent via herdr; refuses blocked agents; verifies the prompt landed")
    s.add_argument("target"); s.add_argument("message", nargs="?"); s.add_argument("--file")
    s.add_argument("--wait", action="store_true", help="use herdr's effect-gate + settle wait")
    s.add_argument("--timeout", type=float, default=600.0, help="seconds for --wait")
    s = add("answer", "answer a blocked dialog: keys (enter, esc, y, n, 1..9, up, down, tab) or free text")
    s.add_argument("target"); s.add_argument("keys", nargs="+"); s.add_argument("--no-enter", action="store_true")
    s.add_argument("--force", action="store_true", help="send even if herdr does not report blocked")
    s = add("interrupt", "send Escape (or --hard ctrl+c) to an agent"); s.add_argument("target"); s.add_argument("--hard", action="store_true")

    s = add("wait", "block until an agent in scope reaches a status (default: idle, done, blocked)")
    s.add_argument("targets", nargs="*"); s.add_argument("--until", action="append", choices=["idle", "done", "blocked", "working", "unknown"])
    s.add_argument("--timeout", type=float, help="seconds (default: none)")
    s = add("events", "stream one line per status transition in scope (for a background monitor)")
    s.add_argument("targets", nargs="*"); s.add_argument("--until", action="append", choices=["idle", "done", "blocked", "working", "unknown"])
    s.add_argument("--timeout", type=float)

    s = add("dispatch", "split/tab a pane, start an agent, stamp ownership, optionally send the first prompt")
    s.add_argument("name"); s.add_argument("--kind", required=True, choices=list(SUPPORTED_KINDS))
    s.add_argument("--model", help=f"default per kind: {DEFAULT_MODEL}")
    s.add_argument("--effort", help=f"default {DEFAULT_EFFORT} · claude --effort · codex model_reasoning_effort · pi :<level> model suffix")
    s.add_argument("--cwd"); s.add_argument("--worktree", metavar="BRANCH", help="git worktree add (under <repo>/../wt/<repo>/ by default)")
    s.add_argument("--base", help="base ref for a new --worktree branch"); s.add_argument("--worktree-root")
    s.add_argument("--split", choices=["right", "down"], help="split a pane instead of the default new tab"); s.add_argument("--split-from", metavar="PANE")
    s.add_argument("--new-tab", dest="tab_label", nargs="?", const="", metavar="LABEL", help="label for the agent's tab (default: the agent name)")
    s.add_argument("--pane", help="use an existing idle shell pane")
    s.add_argument("--prompt"); s.add_argument("--file"); s.add_argument("--wait", action="store_true")
    s.add_argument("--trust-folder", action="store_true", help="accept Claude's folder-trust dialog for a new cwd")
    s.add_argument("--timeout", type=float, default=600.0); s.add_argument("--start-timeout", type=float, default=45.0)
    s.add_argument("--settle", type=float, default=1.0, help="seconds between agent-ready and first prompt")
    s.add_argument("agent_args", nargs="*", help="extra native agent args after --")
    s = add("adopt", "take over an existing agent: cursor at tail (or --count N unread) + owner token")
    s.add_argument("target"); s.add_argument("--count", type=int)
    s = add("stop", "ctrl+c ×2, or --close-pane"); s.add_argument("target"); s.add_argument("--close-pane", action="store_true")
    s = add("forget", "drop cursor, notes, and cache for an agent or session id"); s.add_argument("target")

    s = add("note", "append a tagged note for an agent"); s.add_argument("target"); s.add_argument("text"); s.add_argument("--tag", default="supervisor")
    s = add("notes", "print an agent's notes"); s.add_argument("target")
    add("doctor", "check herdr, integrations, sidecar, and transcript resolution")
    s = add("setup", "install helpers"); s.add_argument("what", choices=["statusline"]); s.add_argument("--uninstall", action="store_true"); s.add_argument("--force", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # scope flags on the top-level parser shadow the subparser copies when given after the subcommand
    state.ensure_dirs()
    sv = Supervisr(args)
    handler = getattr(sv, f"cmd_{args.cmd}")
    try:
        return handler() or 0
    except HerdrError as e:
        eprint(f"herdr error: {e}")
        return 1
    except ResolveError as e:
        eprint(f"error: {e}")
        return 1
    except KeyboardInterrupt:
        return 130
