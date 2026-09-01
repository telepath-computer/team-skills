"""Codex (OpenAI Codex CLI) rollout adapter.

Rollouts: ~/.codex/sessions/YYYY/MM/DD/rollout-<ISO-ts>-<session-id>.jsonl
Linear; entries addressed by raw line index (`codex-r<N>`). A session can span
midnight and produce a second file; resolution by id picks the newest file that
carries the id, so the cursor's `session_path` changes across that boundary
and `watch` asks for a `--reset` rather than silently jumping files.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import state
from ..render import (ARGS_TRUNC, ESTABLISHED_THRESHOLD, OVERVIEW_INTENT_TRUNC, OVERVIEW_RESULT_TRUNC,
                      OVERVIEW_TOOL_TRUNC, RECENT_COUNT_DEFAULT, RESULT_TRUNC, TEXT_TRUNC, Entry,
                      OverviewLine, fmt_ts, latest_supervisory_marker, reasoning_labels, single_line, trunc)
from . import Source, empty_signals

SESSIONS_ROOT = Path.home() / ".codex" / "sessions"


def session_path_for(sid: str, cwd: Optional[str]) -> Optional[Path]:
    if not SESSIONS_ROOT.exists():
        return None
    if sid:
        matches = [p for p in SESSIONS_ROOT.rglob(f"*{sid}*.jsonl")]
        if matches:
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return matches[0]
    if cwd:
        # cwd fallback: codex workers launch inside their own worktree, so cwd is
        # unique per agent in the recommended topology. Still second choice.
        candidates = sorted(SESSIONS_ROOT.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in candidates[:50]:
            try:
                with p.open("r", encoding="utf-8") as f:
                    meta = json.loads(f.readline() or "{}")
                if meta.get("type") == "session_meta":
                    if os.path.realpath((meta.get("payload") or {}).get("cwd", "")) == os.path.realpath(cwd):
                        return p
            except Exception:
                continue
    return None


def load_entries(path: Path) -> List[Dict[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def reasoning_text(payload: Dict[str, Any]) -> str:
    parts = []
    for item in payload.get("summary") if isinstance(payload.get("summary"), list) else []:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            value = item.get("text") or item.get("summary_text")
            if value:
                parts.append(str(value))
    return "\n\n".join(parts)


def is_call_type(ptype: Any) -> bool:
    value = str(ptype or "")
    return value.endswith("_call") or value in {"function_call", "web_search_call", "local_shell_call"}


def is_output_type(ptype: Any) -> bool:
    value = str(ptype or "")
    return value.endswith("_call_output") or value in {"function_call_output"}


def visible_indexed(entries: List[Dict[str, Any]]) -> List[Tuple[int, Dict[str, Any]]]:
    out: List[Tuple[int, Dict[str, Any]]] = []
    for raw_index, e in enumerate(entries):
        t = e.get("type")
        payload = e.get("payload", {})
        ptype = payload.get("type")
        if t in {"session_meta", "turn_context"}:
            continue
        if t == "event_msg":
            if ptype in {"task_started", "task_complete", "context_compacted"}:
                out.append((raw_index, e))
        elif t == "response_item":
            if ptype == "message":
                if payload.get("role") != "developer":
                    out.append((raw_index, e))
            elif is_call_type(ptype) or is_output_type(ptype):
                out.append((raw_index, e))
            elif ptype == "reasoning" and reasoning_text(payload):
                out.append((raw_index, e))
        elif t == "compacted":
            out.append((raw_index, e))
    return out


def format_entry(entry: Dict[str, Any], idx: int) -> Entry:
    ts = fmt_ts(entry.get("timestamp"))
    eid = f"codex-r{idx}"
    payload = entry.get("payload", {})
    ptype = payload.get("type", "?")
    if entry.get("type") == "event_msg":
        if ptype == "task_started":
            text = f"turn={payload.get('turn_id', '?')}"
            return Entry(eid, ts, "system", f"[task_started] {ts} id={eid} {text}",
                         overview=[OverviewLine(eid, ts, "task-started", text, limit=OVERVIEW_TOOL_TRUNC)])
        if ptype == "task_complete":
            return Entry(eid, ts, "system", f"[task_complete] {ts} id={eid}",
                         overview=[OverviewLine(eid, ts, "task-complete", "", limit=OVERVIEW_TOOL_TRUNC)])
        if ptype == "context_compacted":
            return Entry(eid, ts, "compaction", f"[compaction] {ts} id={eid}",
                         overview=[OverviewLine(eid, ts, "compaction", "conversation compacted", limit=OVERVIEW_TOOL_TRUNC)])
    if entry.get("type") == "compacted":
        return Entry(eid, ts, "compaction", f"[compaction] {ts} id={eid}",
                     overview=[OverviewLine(eid, ts, "compaction", "conversation compacted", limit=OVERVIEW_TOOL_TRUNC)])
    if entry.get("type") == "response_item":
        if ptype == "message":
            role = payload.get("role", "?")
            content = payload.get("content", [])
            text = "\n".join(b.get("text", "") for b in (content if isinstance(content, list) else [])
                             if isinstance(b, dict) and b.get("type") in ("input_text", "output_text", "text")).strip()
            body = "\n".join("    " + l for l in trunc(text, TEXT_TRUNC).splitlines() or [""])
            label = "user" if role == "user" else ("assistant" if role == "assistant" else role)
            return Entry(eid, ts, label, f"[{label}] {ts} id={eid}", "  text:\n" + body,
                         overview=[OverviewLine(eid, ts, label, text, preserve_tail=True)])
        if ptype == "reasoning":
            text = reasoning_text(payload)
            body = "\n".join(f"  intent: {label}" for label in reasoning_labels(text))
            return Entry(eid, ts, "intent", f"[intent] {ts} id={eid}", body,
                         overview=[OverviewLine(eid, ts, "intent", label, limit=OVERVIEW_INTENT_TRUNC, preserve_tail=True)
                                   for label in reasoning_labels(text)])
        if is_call_type(ptype):
            name = payload.get("name") or str(ptype).removesuffix("_call") or "?"
            value = payload.get("arguments")
            if value is None:
                value = payload.get("input")
            if value is None:
                value = payload.get("command")
            if value is None:
                value = payload.get("action", "")
            raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            call_id = payload.get("call_id", payload.get("id", "?"))
            return Entry(eid, ts, "tool_call", f"[{ptype}] {ts} id={eid} call={call_id}",
                         f"  {name}({single_line(raw, ARGS_TRUNC)})",
                         overview=[OverviewLine(eid, ts, "tool", f"{name} {raw}", limit=OVERVIEW_TOOL_TRUNC)])
        if is_output_type(ptype):
            output = payload.get("output", "")
            if isinstance(output, dict):
                output = output.get("content", "") or json.dumps(output, ensure_ascii=False)
            call_id = payload.get("call_id", payload.get("id", "?"))
            status = payload.get("status")
            return Entry(eid, ts, "tool_result", f"[{ptype}] {ts} id={eid} call={call_id}",
                         f"  output: {single_line(str(output), RESULT_TRUNC)}",
                         overview=[OverviewLine(eid, ts, "result", f"{('status=' + str(status) + ' ') if status else ''}{output}",
                                                limit=OVERVIEW_RESULT_TRUNC, preserve_tail=True)])
    return Entry(eid, ts, "other", f"[{entry.get('type', '?')}/{ptype}] {ts} id={eid}",
                 overview=[OverviewLine(eid, ts, "other", f"{entry.get('type', '?')}/{ptype}", limit=OVERVIEW_TOOL_TRUNC)])


def turn_state(entries: List[Dict[str, Any]]) -> str:
    for last in reversed(entries):
        payload = last.get("payload", {})
        ptype = payload.get("type")
        etype = last.get("type")
        if etype in {"session_meta", "turn_context"} or ptype in {"token_count", "reasoning"}:
            continue
        if etype == "event_msg":
            if ptype == "task_complete":
                return "idle"
            if ptype in {"task_started", "user_message"}:
                return "busy"
            if ptype == "agent_message":
                return "idle"
            continue
        if etype == "response_item":
            if is_call_type(ptype) or is_output_type(ptype):
                return "busy"
            if ptype == "message":
                role = payload.get("role")
                if role == "assistant":
                    return "idle"
                if role == "user":
                    return "busy"
                if role == "developer":
                    continue
            if ptype == "reasoning":
                return "busy"
            return "unknown"
    return "unknown"


def last_context_tokens(entries: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[int]]:
    """Codex input_tokens already includes cached_input_tokens."""
    for entry in reversed(entries):
        payload = entry.get("payload", {})
        if entry.get("type") == "compacted" or (entry.get("type") == "event_msg" and payload.get("type") == "context_compacted"):
            return (None, None)
        if entry.get("type") != "event_msg" or payload.get("type") != "token_count":
            continue
        info = payload.get("info", {}) or {}
        last = info.get("last_token_usage", {}) or {}
        try:
            input_t = int(last.get("input_tokens") or 0) or None
        except (TypeError, ValueError):
            input_t = None
        try:
            window = int(info.get("model_context_window") or 0) or None
        except (TypeError, ValueError):
            window = None
        if input_t is not None or window is not None:
            return (input_t, window)
    return (None, None)


def last_model(entries: List[Dict[str, Any]]) -> Optional[str]:
    for entry in reversed(entries):
        if entry.get("type") == "turn_context":
            model = (entry.get("payload") or {}).get("model")
            if model:
                return str(model)
    return None


# -- adapter surface ----------------------------------------------------------

def _cursor_last_raw_idx(cursor: Dict[str, Any]) -> int:
    try:
        return int(cursor.get("last_raw_idx", -1))
    except (TypeError, ValueError):
        return -1


def read_persisted(src: Source, count: Optional[int] = None, use_cursor: bool = True):
    path = src.path
    raw_entries = load_entries(path)
    indexed = visible_indexed(raw_entries)
    cursor = state.load_cursor(src.sid) if use_cursor else None
    if cursor and cursor.get("session_path") == str(path):
        last_raw_idx = _cursor_last_raw_idx(cursor)
        unread = [(i, e) for i, e in indexed if i > last_raw_idx]
        window = unread[:count] if count is not None else unread
    else:
        if cursor is not None and cursor.get("session_path") != str(path) and count is None:
            raise ValueError(f"cursor points at {cursor.get('session_path')} but the session now lives in {path} "
                             "(date rollover or resume) — use 'watch --reset' to rebootstrap")
        if cursor is None and len(indexed) > ESTABLISHED_THRESHOLD and count is None:
            raise ValueError(f"established session ({len(indexed)} entries) requires a cursor — "
                             "use 'watch --reset' or 'watch --count N' to bootstrap, or 'adopt' the agent")
        window = indexed[-(count or RECENT_COUNT_DEFAULT):]
    rendered = [format_entry(e, i) for i, e in window]
    for formatted, (raw_index, _) in zip(rendered, window):
        formatted.cursor_after = {"session_path": str(path), "last_raw_idx": raw_index}
    last_raw_idx = window[-1][0] if window else (indexed[-1][0] if indexed else -1)
    return rendered, {"session_path": str(path), "last_raw_idx": last_raw_idx}


def tail_cursor(src: Source) -> Dict[str, Any]:
    indexed = visible_indexed(load_entries(src.path))
    return {"session_path": str(src.path), "last_raw_idx": indexed[-1][0] if indexed else -1}


def snapshot_ids(src: Source) -> set:
    try:
        return {f"codex-r{i}" for i, _ in visible_indexed(load_entries(src.path))[-30:]}
    except Exception:
        return set()


def detail(src: Source, target: str) -> str:
    entries = load_entries(src.path)
    m = re.fullmatch(r"codex-r(\d+)", target)
    if m:
        i = int(m.group(1))
        if 0 <= i < len(entries):
            return format_entry(entries[i], i).render()
    for i, e in enumerate(entries):
        payload = e.get("payload", {})
        if payload.get("call_id") == target or payload.get("id") == target:
            return format_entry(e, i).render()
    raise ValueError(f"id not found: {target}")


def raw_detail(src: Source, target: str) -> Any:
    entries = load_entries(src.path)
    m = re.fullmatch(r"codex-r(\d+)", target)
    if m:
        i = int(m.group(1))
        if 0 <= i < len(entries):
            return entries[i]
    matches = [e for e in entries if (e.get("payload") or {}).get("call_id") == target
               or (e.get("payload") or {}).get("id") == target]
    if len(matches) == 1:
        return matches[0]
    if matches:
        return matches
    raise ValueError(f"id not found: {target}")


def status_signals(src: Source) -> Dict[str, Any]:
    sig = empty_signals()
    try:
        path = src.path
        sig["persisted_age_s"] = time.time() - path.stat().st_mtime
        raw_entries = load_entries(path)
        indexed = visible_indexed(raw_entries)
    except Exception:
        return sig
    cursor = state.load_cursor(src.sid)
    if cursor is None:
        unread = len(indexed)
    elif cursor.get("session_path") != str(path):
        unread = None
    else:
        last = _cursor_last_raw_idx(cursor)
        unread = sum(i > last for i, _ in indexed)
    sig["unread_count"] = unread
    sig["turn"] = turn_state(raw_entries)
    ctx, window = last_context_tokens(raw_entries)
    sig["context_input_tokens"] = ctx
    sig["context_window_tokens"] = window
    sig["model"] = last_model(raw_entries)
    sig["latest_marker"] = latest_supervisory_marker([format_entry(e, i) for i, e in indexed[-50:]])
    return sig
