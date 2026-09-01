"""Pi transcript adapter.

Sessions: ~/.pi/agent/sessions/--<cwd-with-dashes>--/<timestamp>_<session-id>.jsonl
The JSONL is a tree (entries carry id/parentId); only the active branch is
displayed. herdr's pi integration reports the session *path* directly, so
resolution here is normally a file-exists check.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import state
from ..render import (ARGS_TRUNC, DETAIL_COMPONENT_TRUNC, ESTABLISHED_THRESHOLD, OVERVIEW_INTENT_TRUNC,
                      OVERVIEW_RESULT_TRUNC, OVERVIEW_TOOL_TRUNC, RECENT_COUNT_DEFAULT, RESULT_TRUNC,
                      TEXT_TRUNC, Entry, OverviewLine, clip_overview, fmt_ts, latest_supervisory_marker,
                      meaningful_stop_reason, preview_args, reasoning_labels, resolve_unique_prefix,
                      single_line, trunc, unique_prefixes, unread_after_id)
from . import Source, empty_signals

PI_ROOT = Path.home() / ".pi" / "agent"
SESSIONS_ROOT = PI_ROOT / "sessions"
MODELS_PATH = PI_ROOT / "models.json"
MODELS_STORE_PATH = PI_ROOT / "models-store.json"

PREFERRED_ARGS = ["path", "command", "pattern", "oldText", "newText", "content",
                  "file", "filePath", "description", "text", "name"]


def path_key_for_cwd(cwd: str) -> str:
    return f"--{cwd.strip('/').replace('/', '-')}--"


def filename_session_id(path: Path) -> Optional[str]:
    stem = path.stem
    return stem.split("_", 1)[1] if "_" in stem else None


def read_header(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            header = json.loads(f.readline())
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(header, dict) or header.get("type") != "session":
        return None
    return header


def find_sessions_by_id(session_id: str, session_dir: Optional[str] = None) -> List[Path]:
    if session_dir:
        base = Path(session_dir).expanduser()
        candidates = list(base.glob(f"*_{session_id}.jsonl")) if base.is_dir() else []
    elif SESSIONS_ROOT.is_dir():
        candidates = list(SESSIONS_ROOT.glob(f"*/*_{session_id}.jsonl"))
    else:
        candidates = []
    out = []
    for c in candidates:
        if filename_session_id(c) != session_id:
            continue
        header = read_header(c)
        if header is None or header.get("id") != session_id:
            continue
        out.append(c)
    return sorted(out)


def session_path_for(sid: str, cwd: Optional[str]) -> Optional[Path]:
    matches = find_sessions_by_id(sid)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1 and cwd:
        real = os.path.realpath(cwd)
        narrowed = [m for m in matches
                    if os.path.realpath(str((read_header(m) or {}).get("cwd", ""))) == real]
        if len(narrowed) == 1:
            return narrowed[0]
    return None


def load_active(path: Path) -> List[Dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    parsed = []
    nonempty = [(i, l) for i, l in enumerate(lines) if l.strip()]
    for position, (line_index, line) in enumerate(nonempty):
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            if position == len(nonempty) - 1:
                continue  # incomplete tail being appended
            raise ValueError(f"malformed pi session JSONL at line {line_index + 1}: {path}")
    if not parsed or parsed[0].get("type") != "session":
        raise ValueError(f"not a pi session file: {path}")
    entries = parsed[1:]
    id_map: Dict[str, Dict[str, Any]] = {}
    leaf = None
    for e in entries:
        eid = e.get("id")
        if eid:
            id_map[eid] = e
            leaf = e
    if leaf is None:
        return []
    chain: List[Dict[str, Any]] = []
    seen = set()
    cur: Optional[Dict[str, Any]] = leaf
    while cur is not None:
        eid = cur.get("id")
        if eid in seen:
            break
        seen.add(eid)
        chain.append(cur)
        parent_id = cur.get("parentId")
        cur = id_map.get(parent_id) if parent_id else None
    chain.reverse()
    return chain


def displayable(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    types = {"message", "model_change", "thinking_level_change", "compaction",
             "branch_summary", "session_info", "custom_message", "label"}
    return [e for e in entries if e.get("type") in types]


def stringify(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            parts.append(str(block))
            continue
        bt = block.get("type")
        if bt == "text":
            parts.append(block.get("text", ""))
        elif bt == "image":
            parts.append(f"[image:{block.get('mimeType', '?')}]")
        elif bt == "thinking":
            continue
        elif bt == "toolCall":
            parts.append(f"[toolCall:{block.get('name', '?')}]")
        else:
            parts.append(f"[{bt}]")
    return "\n".join(p for p in parts if p)


def locator_context(entries: List[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, str]]:
    ids = [str(e.get("id")) for e in entries if e.get("id")]
    prefixes = unique_prefixes(ids)
    call_locators: Dict[str, str] = {}
    for e in entries:
        eid = str(e.get("id", "?"))
        loc = prefixes.get(eid, eid)
        msg = e.get("message", {}) if e.get("type") == "message" else {}
        content = msg.get("content", []) if isinstance(msg.get("content", []), list) else []
        calls = [b for b in content if isinstance(b, dict) and b.get("type") == "toolCall"]
        for number, block in enumerate(calls, 1):
            if block.get("id"):
                call_locators[str(block["id"])] = f"{loc}/tool/{number}"
    return prefixes, call_locators


def format_entry(entry: Dict[str, Any], locator: Optional[str] = None,
                 call_locators: Optional[Dict[str, str]] = None) -> Entry:
    etype = entry.get("type")
    eid = str(entry.get("id", "?"))
    loc = locator or eid
    call_locators = call_locators or {}
    ts = fmt_ts(entry.get("timestamp"))
    if etype != "message":
        if etype == "model_change":
            model = f"{entry.get('provider', '?')}/{entry.get('modelId', '?')}"
            return Entry(eid, ts, etype, f"[model] {ts} id={loc} {model}",
                         overview=[OverviewLine(loc, ts, "model", model, limit=OVERVIEW_TOOL_TRUNC)])
        if etype == "compaction":
            before = entry.get("tokensBefore")
            text = f"from={before / 1000:.0f}k tokens" if isinstance(before, (int, float)) else "conversation compacted"
            if entry.get("fromHook"):
                text += " automatically"
            return Entry(eid, ts, etype, f"[compaction] {ts} id={loc} {text}",
                         overview=[OverviewLine(loc, ts, "compaction", text, limit=OVERVIEW_TOOL_TRUNC)])
        if etype == "branch_summary":
            return Entry(eid, ts, etype, f"[branch-summary] {ts} id={loc}",
                         overview=[OverviewLine(loc, ts, "branch-summary", limit=OVERVIEW_TOOL_TRUNC)])
        return Entry(eid, ts, etype, f"[{etype}] {ts} id={loc}",
                     overview=[OverviewLine(loc, ts, str(etype), "", limit=OVERVIEW_TOOL_TRUNC)])

    msg = entry.get("message", {})
    role = msg.get("role", "?")
    if role == "user":
        text = stringify(msg.get("content", ""))
        body = "\n".join("  " + l for l in trunc(text, TEXT_TRUNC).splitlines() or [""])
        return Entry(eid, ts, "user", f"[user] {ts} id={loc}", body,
                     overview=[OverviewLine(loc, ts, "user", text, preserve_tail=True)])
    if role == "assistant":
        content = msg.get("content", [])
        content = content if isinstance(content, list) else []
        text = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text").strip()
        lines: List[str] = []
        overview: List[OverviewLine] = []
        if text:
            lines.extend("  " + l for l in trunc(text, TEXT_TRUNC).splitlines() or [""])
            overview.append(OverviewLine(loc, ts, "assistant", text, preserve_tail=True))
        thinking_number = 0
        for block in content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                for label in reasoning_labels(block.get("thinking")):
                    thinking_number += 1
                    lines.append(f"  intent: {label}")
                    overview.append(OverviewLine(f"{loc}/thinking/{thinking_number}", ts, "intent", label,
                                                 limit=OVERVIEW_INTENT_TRUNC, preserve_tail=True))
        tool_number = 0
        for tc in [b for b in content if isinstance(b, dict) and b.get("type") == "toolCall"]:
            tool_number += 1
            preview = preview_args(tc.get("arguments", {}), ARGS_TRUNC, PREFERRED_ARGS)
            child_loc = f"{loc}/tool/{tool_number}"
            lines.append(f"  tool: {tc.get('name', '?')}{(' ' + preview) if preview else ''} [{child_loc}]")
            overview.append(OverviewLine(child_loc, ts, "tool",
                                         f"{tc.get('name', '?')} {preview_args(tc.get('arguments', {}), OVERVIEW_TOOL_TRUNC, PREFERRED_ARGS)}",
                                         limit=OVERVIEW_TOOL_TRUNC))
        sr = meaningful_stop_reason(msg.get("stopReason"), has_tool_call=tool_number > 0)
        if sr:
            lines.append(f"  stop: {sr}")
        if not overview:
            overview.append(OverviewLine(loc, ts, "assistant", f"stop={sr}" if sr else "(no visible content)",
                                         limit=OVERVIEW_TOOL_TRUNC))
        return Entry(eid, ts, "assistant", f"[assistant] {ts} id={loc}", "\n".join(lines), overview=overview)
    if role == "toolResult":
        text = stringify(msg.get("content", []))
        is_error = bool(msg.get("isError"))
        tool = msg.get("toolName", "?")
        call_ref = call_locators.get(str(msg.get("toolCallId", "")))
        association = f" for={call_ref}" if call_ref else ""
        header = f"[result{' ERROR' if is_error else ''}] {ts} id={loc} tool={tool}{association}"
        body = f"  {single_line(text, RESULT_TRUNC)}" if text else ""
        return Entry(eid, ts, "tool_result", header, body,
                     overview=[OverviewLine(loc, ts, "result", f"{tool}{association} {'ERROR ' if is_error else ''}{text}",
                                            limit=OVERVIEW_RESULT_TRUNC, preserve_tail=True)])
    if role == "bashExecution":
        out = msg.get("output", "")
        command = msg.get("command", "")
        body_lines = [f"  command: {single_line(command, ARGS_TRUNC)}"]
        if out:
            body_lines.append(f"  output: {single_line(out, RESULT_TRUNC)}")
        ec = msg.get("exitCode")
        if ec is not None:
            body_lines.append(f"  exitCode: {ec}")
        overview = [OverviewLine(f"{loc}/tool/1", ts, "tool", f"bash command={command}", limit=OVERVIEW_TOOL_TRUNC),
                    OverviewLine(loc, ts, "result", f"bash exit={ec} {out}", limit=OVERVIEW_RESULT_TRUNC, preserve_tail=True)]
        return Entry(eid, ts, "bash", f"[bashExecution] {ts} id={loc}", "\n".join(body_lines), overview=overview)
    return Entry(eid, ts, role, f"[{role}] {ts} id={loc}",
                 overview=[OverviewLine(loc, ts, str(role), "", limit=OVERVIEW_TOOL_TRUNC)])


def turn_state(entries: List[Dict[str, Any]]) -> str:
    for entry in reversed(entries):
        if entry.get("type") != "message":
            continue
        msg = entry.get("message", {})
        role = msg.get("role")
        if role == "assistant":
            content = msg.get("content", [])
            has_tool_call = any(isinstance(b, dict) and b.get("type") == "toolCall"
                                for b in (content if isinstance(content, list) else []))
            stop = str(msg.get("stopReason") or msg.get("stop_reason") or "").lower()
            return "busy" if has_tool_call or stop in {"tooluse", "tool_use", "tool-use"} else "idle"
        if role in {"user", "toolResult", "bashExecution"}:
            return "busy"
        return "unknown"
    return "unknown"


def _find_model_context_window(value: Any, provider: str, model: str,
                               inherited_provider: Optional[str] = None) -> Optional[int]:
    if isinstance(value, dict):
        current_provider = str(value.get("provider") or value.get("providerId") or inherited_provider or "")
        current_model = str(value.get("id") or value.get("model") or value.get("modelId") or "")
        if current_model == model and (not provider or not current_provider or current_provider == provider):
            candidate = value.get("contextWindow") or value.get("context_window")
            try:
                parsed = int(candidate)
                if parsed > 0:
                    return parsed
            except (TypeError, ValueError):
                pass
        for key, child in value.items():
            child_provider = current_provider
            if key == provider or (inherited_provider is None and key not in {"providers", "models", "modelOverrides"}):
                child_provider = str(key)
            found = _find_model_context_window(child, provider, model, child_provider)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_model_context_window(child, provider, model, inherited_provider)
            if found:
                return found
    return None


def context_window_tokens(entries: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[str]]:
    provider = model = ""
    for entry in reversed(entries):
        if entry.get("type") == "message":
            msg = entry.get("message", {})
            if msg.get("role") == "assistant" and (msg.get("model") or msg.get("modelId")):
                provider = str(msg.get("provider") or "")
                model = str(msg.get("model") or msg.get("modelId"))
                break
        if entry.get("type") == "model_change" and entry.get("modelId"):
            provider = str(entry.get("provider") or "")
            model = str(entry.get("modelId"))
            break
    if not model:
        return None, None
    label = f"{provider}/{model}" if provider else model
    for models_path in (MODELS_PATH, MODELS_STORE_PATH):
        try:
            data = json.loads(models_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        found = _find_model_context_window(data, provider, model)
        if found:
            return found, label
    return None, label


def last_context_tokens(entries: List[Dict[str, Any]]) -> Optional[int]:
    """Pi prompt tokens are input plus cacheRead; cacheRead is additive."""
    for entry in reversed(entries):
        if entry.get("type") == "compaction":
            return None
        if entry.get("type") != "message":
            continue
        msg = entry.get("message", {})
        if msg.get("role") != "assistant":
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        try:
            total = int(usage.get("input") or usage.get("input_tokens") or 0) + \
                int(usage.get("cacheRead") or usage.get("cache_read_input_tokens") or 0)
        except (TypeError, ValueError):
            continue
        if total > 0:
            return total
    return None


# -- adapter surface ----------------------------------------------------------

def read_persisted(src: Source, count: Optional[int] = None, use_cursor: bool = True):
    path = src.path
    active = displayable(load_active(path))
    cursor = state.load_cursor(src.sid) if use_cursor else None
    if cursor and cursor.get("session_path") == str(path):
        ids = [e.get("id") for e in active]
        try:
            idx = ids.index(cursor.get("last_entry_id"))
        except ValueError:
            raise ValueError("cursor entry not on active branch — use 'watch --reset' to rebootstrap")
        unread = active[idx + 1:]
        window = unread[:count] if count is not None else unread
    else:
        if cursor is None and len(active) > ESTABLISHED_THRESHOLD and count is None:
            raise ValueError(f"established session ({len(active)} entries) requires a cursor — "
                             "use 'watch --reset' or 'watch --count N' to bootstrap, or 'adopt' the agent")
        window = active[-(count or RECENT_COUNT_DEFAULT):]
    prefix_by_id, call_locators = locator_context(active)
    rendered = [format_entry(e, prefix_by_id.get(str(e.get("id")), str(e.get("id", "?"))), call_locators)
                for e in window]
    for formatted, raw in zip(rendered, window):
        formatted.cursor_after = {"session_path": str(path), "last_entry_id": raw.get("id")}
    new_cursor = {"session_path": str(path),
                  "last_entry_id": window[-1].get("id") if window else (active[-1].get("id") if active else None)}
    return rendered, new_cursor


def tail_cursor(src: Source) -> Dict[str, Any]:
    active = displayable(load_active(src.path))
    return {"session_path": str(src.path), "last_entry_id": active[-1].get("id") if active else None}


def snapshot_ids(src: Source) -> set:
    try:
        return {str(e.get("id")) for e in displayable(load_active(src.path))[-30:]}
    except Exception:
        return set()


def detail(src: Source, target: str) -> str:
    entries = load_active(src.path)
    parent_target = target.split("/", 1)[0]
    ids = [str(e.get("id")) for e in entries if e.get("id")]
    prefix_by_id, call_locators = locator_context(entries)
    parent_id = (resolve_unique_prefix(ids, parent_target, "pi entry id")
                 if "/" in target or any(v.startswith(parent_target) for v in ids) else None)
    for entry in entries:
        eid = str(entry.get("id", "?"))
        if entry.get("type") == "message":
            msg = entry.get("message", {})
            content = msg.get("content", []) if isinstance(msg.get("content", []), list) else []
            if parent_id == eid and "/" in target:
                suffix = target[len(parent_target):]
                if msg.get("role") == "bashExecution":
                    if suffix != "/tool/1":
                        raise ValueError(f"pi child locator not found: {target}")
                    command, cut = clip_overview(msg.get("command", ""), DETAIL_COMPONENT_TRUNC, preserve_tail=True)
                    return f"[tool] id={target} name=bash\n  command: {command}" + ("\n  (command shortened)" if cut else "")
                match = re.fullmatch(r"/(tool|thinking)/(\d+)", suffix)
                if not match:
                    raise ValueError(f"invalid pi child locator: {target}")
                kind, number_text = match.groups()
                block_type = "toolCall" if kind == "tool" else "thinking"
                blocks = [b for b in content if isinstance(b, dict) and b.get("type") == block_type]
                number = int(number_text)
                if number < 1 or number > len(blocks):
                    raise ValueError(f"pi child locator not found: {target}")
                block = blocks[number - 1]
                if kind == "thinking":
                    return f"[intent] id={target}\n  " + "\n  ".join(reasoning_labels(block.get("thinking")))
                shown, cut = clip_overview(json.dumps(block.get("arguments", {}), ensure_ascii=False),
                                           DETAIL_COMPONENT_TRUNC, preserve_tail=True)
                return f"[toolCall] id={target} name={block.get('name', '?')}\n  arguments: {shown}" + ("\n  (arguments shortened)" if cut else "")
            if msg.get("role") == "toolResult" and msg.get("toolCallId") == target:
                return format_entry(entry).render()
            for block in content:
                if isinstance(block, dict) and block.get("type") == "toolCall" and block.get("id") == target:
                    shown, cut = clip_overview(json.dumps(block.get("arguments", {}), ensure_ascii=False),
                                               DETAIL_COMPONENT_TRUNC, preserve_tail=True)
                    return f"[toolCall] id={target} name={block.get('name', '?')}\n  arguments: {shown}" + ("\n  (arguments shortened)" if cut else "")
        if eid == target or (parent_id == eid and "/" not in target):
            if entry.get("type") == "compaction":
                summary, cut = clip_overview(entry.get("summary", ""), TEXT_TRUNC, preserve_tail=True)
                rendered = format_entry(entry, prefix_by_id.get(eid, eid), call_locators).render()
                return f"{rendered}\n  summary: {summary}" + ("\n  (summary shortened)" if cut else "")
            return format_entry(entry, prefix_by_id.get(eid, eid), call_locators).render()
    raise ValueError(f"id not found on active branch: {target}")


def raw_detail(src: Source, target: str) -> Any:
    entries = load_active(src.path)
    ids = [str(e.get("id")) for e in entries if e.get("id")]
    parent_target = target.split("/", 1)[0]
    parent_id = (resolve_unique_prefix(ids, parent_target, "pi entry id")
                 if "/" in target or any(v.startswith(parent_target) for v in ids) else None)
    for entry in entries:
        eid = str(entry.get("id", "?"))
        if parent_id == eid and "/" in target:
            suffix = target[len(parent_target):]
            match = re.fullmatch(r"/(tool|thinking|result)/(\d+)", suffix)
            if not match:
                raise ValueError(f"invalid pi child locator: {target}")
            kind, number_text = match.groups()
            msg = entry.get("message", {}) if entry.get("type") == "message" else {}
            if msg.get("role") == "bashExecution":
                if kind == "tool" and number_text == "1":
                    return {"type": "toolCall", "name": "bash", "command": msg.get("command", "")}
                if kind == "result" and number_text == "1":
                    return {"type": "toolResult", "output": msg.get("output", ""), "exitCode": msg.get("exitCode")}
                raise ValueError(f"pi child locator not found: {target}")
            content = msg.get("content", []) if isinstance(msg.get("content", []), list) else []
            block_type = {"tool": "toolCall", "thinking": "thinking", "result": "toolResult"}[kind]
            blocks = [b for b in content if isinstance(b, dict) and b.get("type") == block_type]
            number = int(number_text)
            if number < 1 or number > len(blocks):
                raise ValueError(f"pi child locator not found: {target}")
            return blocks[number - 1]
        if eid == parent_id and "/" not in target:
            return entry
        if entry.get("type") == "message":
            msg = entry.get("message", {})
            content = msg.get("content", []) if isinstance(msg.get("content", []), list) else []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "toolCall" and block.get("id") == target:
                    return block
            if msg.get("role") == "toolResult" and msg.get("toolCallId") == target:
                return entry
    raise ValueError(f"id not found on active branch: {target}")


def status_signals(src: Source) -> Dict[str, Any]:
    sig = empty_signals()
    try:
        path = src.path
        sig["persisted_age_s"] = time.time() - path.stat().st_mtime
        active = load_active(path)
        vis = displayable(active)
    except Exception:
        return sig
    ids = [e.get("id") for e in vis]
    sig["unread_count"] = unread_after_id(state.load_cursor(src.sid), identity_key="session_path",
                                          identity_value=str(path), last_key="last_entry_id", ids=ids)
    sig["turn"] = turn_state(active)
    sig["context_input_tokens"] = last_context_tokens(active)
    window, model = context_window_tokens(active)
    sig["context_window_tokens"] = window
    sig["model"] = model
    sig["latest_marker"] = latest_supervisory_marker([format_entry(e) for e in vis[-50:]])
    return sig
