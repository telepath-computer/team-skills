"""Claude Code transcript adapter.

Transcript: ~/.claude/projects/<cwd-key>/<session-id>.jsonl (cwd-key = absolute
cwd with '/' → '-', leading '-'). Entries keyed by `uuid`.

Context window: Claude's JSONL carries prompt token usage per assistant turn but
not the window size. The statusline sidecar (see scripts/claude-statusline-sidecar.sh)
writes Claude Code's own `context_window` block per session id; when present it
is authoritative (it is what the TUI shows). Otherwise the window is unknown
and status prints an explicit `?` denominator.
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

CLAUDE_CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
PROJECTS_ROOT = CLAUDE_CONFIG_DIR / "projects"
PID_META_DIR = CLAUDE_CONFIG_DIR / "sessions"

PREFERRED_ARGS = ["command", "file_path", "path", "pattern", "query", "url", "prompt", "content", "description"]


def path_key_for_cwd(cwd: str) -> str:
    return "-" + cwd.strip("/").replace("/", "-")


def session_path_for(sid: str, cwd: Optional[str]) -> Optional[Path]:
    """Transcript for a session id. Exact by id; cwd only narrows the search."""
    if cwd:
        direct = PROJECTS_ROOT / path_key_for_cwd(cwd) / f"{sid}.jsonl"
        if direct.exists():
            return direct
    if PROJECTS_ROOT.exists():
        matches = [p for p in PROJECTS_ROOT.glob(f"*/{sid}.jsonl")]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return matches[0]
    return None


def session_from_pid(pid: int) -> Optional[Dict[str, Any]]:
    """Claude Code writes ~/.claude/sessions/<pid>.json with sessionId + cwd."""
    p = PID_META_DIR / f"{pid}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
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


def visible(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for e in entries:
        t = e.get("type")
        if t in {"user", "assistant"}:
            out.append(e)
        elif t == "system" and e.get("subtype") == "compact_boundary":
            out.append(e)
    return out


def content_text(content: Any) -> str:
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
        elif bt == "thinking":
            continue
        elif bt == "tool_use":
            parts.append(f"[tool_use:{block.get('name', '?')}]")
        elif bt == "tool_result":
            v = block.get("content", "")
            parts.append(v if isinstance(v, str) else str(v))
        else:
            parts.append(f"[{bt}]")
    return "\n".join(p for p in parts if p)


def locator_context(entries: List[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, str]]:
    ids = [str(e.get("uuid")) for e in entries if e.get("uuid")]
    prefixes = unique_prefixes(ids)
    call_locators: Dict[str, str] = {}
    for e in entries:
        uuid = str(e.get("uuid", "?"))
        loc = prefixes.get(uuid, uuid)
        content = (e.get("message") or {}).get("content", [])
        calls = [b for b in (content if isinstance(content, list) else [])
                 if isinstance(b, dict) and b.get("type") == "tool_use"]
        for number, block in enumerate(calls, 1):
            if block.get("id"):
                call_locators[str(block["id"])] = f"{loc}/tool/{number}"
    return prefixes, call_locators


def format_entry(entry: Dict[str, Any], locator: Optional[str] = None,
                 call_locators: Optional[Dict[str, str]] = None) -> Entry:
    etype = entry.get("type")
    uuid = str(entry.get("uuid", "?"))
    loc = locator or uuid
    call_locators = call_locators or {}
    ts = fmt_ts(entry.get("timestamp"))
    if etype == "assistant":
        msg = entry.get("message", {})
        text_parts: List[str] = []
        tool_lines: List[str] = []
        overview: List[OverviewLine] = []
        thinking_number = 0
        tool_number = 0
        for block in msg.get("content", []) or []:
            if not isinstance(block, dict):
                continue
            bt = block.get("type")
            if bt == "text":
                text_parts.append(block.get("text", ""))
            elif bt == "thinking":
                for label in reasoning_labels(block.get("thinking")):
                    thinking_number += 1
                    tool_lines.append(f"  intent: {label}")
                    overview.append(OverviewLine(f"{loc}/thinking/{thinking_number}", ts, "intent", label,
                                                 limit=OVERVIEW_INTENT_TRUNC, preserve_tail=True))
            elif bt == "tool_use":
                tool_number += 1
                preview = preview_args(block.get("input", {}), ARGS_TRUNC, PREFERRED_ARGS)
                child_loc = f"{loc}/tool/{tool_number}"
                tool_lines.append(f"  tool: {block.get('name', '?')}{(' ' + preview) if preview else ''} [{child_loc}]")
                overview.append(OverviewLine(child_loc, ts, "tool",
                                             f"{block.get('name', '?')} {preview_args(block.get('input', {}), OVERVIEW_TOOL_TRUNC, PREFERRED_ARGS)}",
                                             limit=OVERVIEW_TOOL_TRUNC))
        text = "\n".join(p for p in text_parts if p).strip()
        body_lines = []
        if text:
            for line in trunc(text, TEXT_TRUNC).splitlines() or [""]:
                body_lines.append("  " + line)
            overview.insert(0, OverviewLine(loc, ts, "assistant", text, preserve_tail=True))
        body_lines.extend(tool_lines)
        sr = meaningful_stop_reason(msg.get("stop_reason"), has_tool_call=tool_number > 0)
        if sr:
            body_lines.append(f"  stop: {sr}")
        if not overview:
            overview.append(OverviewLine(loc, ts, "assistant", f"stop={sr}" if sr else "(no visible content)",
                                         limit=OVERVIEW_TOOL_TRUNC))
        return Entry(uuid, ts, "assistant", f"[assistant] {ts} id={loc}", "\n".join(body_lines), overview=overview)
    if etype == "user":
        msg = entry.get("message", {})
        content = msg.get("content", "")
        if isinstance(content, list):
            tool_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
            if tool_blocks:
                lines = []
                overview = []
                for number, block in enumerate(tool_blocks, 1):
                    tool_id = str(block.get("tool_use_id", "?"))
                    text = block.get("content", "")
                    if not isinstance(text, str):
                        text = content_text(text)
                    is_error = bool(block.get("is_error"))
                    result_loc = f"{loc}/result/{number}"
                    call_ref = call_locators.get(tool_id)
                    association = f" for={call_ref}" if call_ref else ""
                    lines.append(f"[result{' ERROR' if is_error else ''}] {ts} id={result_loc}{association}")
                    lines.append(f"  {single_line(text, RESULT_TRUNC)}")
                    overview.append(OverviewLine(result_loc, ts, "result",
                                                 f"{association.strip()} {'ERROR ' if is_error else ''}{text}".strip(),
                                                 limit=OVERVIEW_RESULT_TRUNC, preserve_tail=True))
                return Entry(uuid, ts, "tool_result", "\n".join(lines), overview=overview)
        text = content_text(content)
        body = "\n".join("  " + l for l in trunc(text, TEXT_TRUNC).splitlines() or [""])
        return Entry(uuid, ts, "user", f"[user] {ts} id={loc}", body,
                     overview=[OverviewLine(loc, ts, "user", text, preserve_tail=True)])
    if etype == "system" and entry.get("subtype") == "compact_boundary":
        meta = entry.get("compactMetadata") or {}
        before, after = meta.get("preTokens"), meta.get("postTokens")
        text = "conversation compacted"
        if isinstance(before, (int, float)):
            text = f"from={before / 1000:.0f}k tokens"
            if isinstance(after, (int, float)):
                text += f" to={after / 1000:.0f}k"
        return Entry(uuid, ts, "compaction", f"[compaction] {ts} id={loc} {text}",
                     overview=[OverviewLine(loc, ts, "compaction", text, limit=OVERVIEW_TOOL_TRUNC)])
    return Entry(uuid, ts, etype or "other", f"[{etype}] {ts} id={loc}",
                 overview=[OverviewLine(loc, ts, etype or "other", "", limit=OVERVIEW_TOOL_TRUNC)])


def turn_state(entries: List[Dict[str, Any]]) -> str:
    for last in reversed(entries):
        etype = last.get("type")
        if etype == "system" and last.get("subtype") == "compact_boundary":
            continue
        msg = last.get("message", {})
        break
    else:
        return "unknown"
    if etype == "assistant":
        content = msg.get("content", [])
        has_tool_use = any(isinstance(b, dict) and b.get("type") == "tool_use"
                           for b in (content if isinstance(content, list) else []))
        stop = str(msg.get("stop_reason") or msg.get("stopReason") or "").lower()
        return "busy" if has_tool_use or stop in {"tool_use", "tooluse", "tool-use"} else "idle"
    if etype == "user":
        return "busy"
    return "unknown"


def last_context_tokens(entries: List[Dict[str, Any]]) -> Optional[int]:
    """Prompt tokens = input + cache-read + cache-creation (additive in Claude's schema)."""
    for obj in reversed(entries):
        if obj.get("type") == "system" and obj.get("subtype") == "compact_boundary":
            return None
        usage = (obj.get("message") or {}).get("usage")
        if not isinstance(usage, dict):
            continue
        try:
            total = (int(usage.get("input_tokens") or 0) + int(usage.get("cache_read_input_tokens") or 0)
                     + int(usage.get("cache_creation_input_tokens") or 0))
        except (TypeError, ValueError):
            continue
        if total > 0:
            return total
    return None


def last_model(entries: List[Dict[str, Any]]) -> Optional[str]:
    for obj in reversed(entries):
        model = (obj.get("message") or {}).get("model")
        if model:
            return str(model)
    return None


def context_window(sid: str, model: Optional[str]) -> Tuple[Optional[int], Optional[int], str]:
    """(window, used_tokens_from_sidecar, source). Sidecar is authoritative when fresh."""
    side = state.load_claude_ctx(sid)
    if side:
        cw = side.get("context_window") or {}
        window = cw.get("context_window_size")
        used = cw.get("total_input_tokens")
        if isinstance(window, (int, float)) and window > 0:
            return int(window), (int(used) if isinstance(used, (int, float)) else None), "statusline"
    if model and re.search(r"\[1m\]", model):
        return 1_000_000, None, "model-id"
    return None, None, "unknown"


# -- adapter surface ----------------------------------------------------------

def read_persisted(src: Source, count: Optional[int] = None, use_cursor: bool = True):
    path = src.path
    entries = visible(load_entries(path))
    cursor = state.load_cursor(src.sid) if use_cursor else None
    if cursor and cursor.get("session_path") == str(path):
        ids = [e.get("uuid") for e in entries]
        try:
            idx = ids.index(cursor.get("last_entry_id"))
        except ValueError:
            raise ValueError("cursor entry no longer in transcript — use 'watch --reset' to rebootstrap")
        unread = entries[idx + 1:]
        window = unread[:count] if count is not None else unread
    else:
        if cursor is None and len(entries) > ESTABLISHED_THRESHOLD and count is None:
            raise ValueError(f"established session ({len(entries)} entries) requires a cursor — "
                             "use 'watch --reset' or 'watch --count N' to bootstrap, or 'adopt' the agent")
        window = entries[-(count or RECENT_COUNT_DEFAULT):]
    prefix_by_id, call_locators = locator_context(entries)
    rendered = [format_entry(e, prefix_by_id.get(str(e.get("uuid")), str(e.get("uuid", "?"))), call_locators)
                for e in window]
    for formatted, raw in zip(rendered, window):
        formatted.cursor_after = {"session_path": str(path), "last_entry_id": raw.get("uuid")}
    new_cursor = {"session_path": str(path),
                  "last_entry_id": window[-1].get("uuid") if window else (entries[-1].get("uuid") if entries else None)}
    return rendered, new_cursor


def tail_cursor(src: Source) -> Dict[str, Any]:
    entries = visible(load_entries(src.path))
    return {"session_path": str(src.path), "last_entry_id": entries[-1].get("uuid") if entries else None}


def snapshot_ids(src: Source) -> set:
    try:
        return {str(e.get("uuid")) for e in visible(load_entries(src.path))[-30:]}
    except Exception:
        return set()


def _find(entries, target):
    ids = [str(e.get("uuid")) for e in entries if e.get("uuid")]
    parent_target = target.split("/", 1)[0]
    parent_id = None
    if "/" in target or any(v.startswith(parent_target) for v in ids):
        parent_id = resolve_unique_prefix(ids, parent_target, "claude entry id")
    return parent_id, parent_target


def detail(src: Source, target: str) -> str:
    entries = visible(load_entries(src.path))
    parent_id, parent_target = _find(entries, target)
    prefix_by_id, call_locators = locator_context(entries)
    for entry in entries:
        uuid = str(entry.get("uuid", "?"))
        content = (entry.get("message") or {}).get("content")
        blocks = content if isinstance(content, list) else []
        if parent_id == uuid and "/" in target:
            suffix = target[len(parent_target):]
            match = re.fullmatch(r"/(tool|thinking|result)/(\d+)", suffix)
            if not match:
                raise ValueError(f"invalid claude child locator: {target}")
            kind, number_text = match.groups()
            block_type = {"tool": "tool_use", "thinking": "thinking", "result": "tool_result"}[kind]
            selected = [b for b in blocks if isinstance(b, dict) and b.get("type") == block_type]
            number = int(number_text)
            if number < 1 or number > len(selected):
                raise ValueError(f"claude child locator not found: {target}")
            block = selected[number - 1]
            if kind == "thinking":
                return f"[intent] id={target}\n  " + "\n  ".join(reasoning_labels(block.get("thinking")))
            value = block.get("input", {}) if kind == "tool" else block.get("content", "")
            text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
            shown, cut = clip_overview(text, DETAIL_COMPONENT_TRUNC, preserve_tail=True)
            return f"[{kind}] id={target}\n  {shown}" + (f"\n  ({kind} content shortened)" if cut else "")
        if uuid == parent_id and "/" not in target:
            return format_entry(entry, prefix_by_id.get(uuid, uuid), call_locators).render()
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("id") == target:
                shown, cut = clip_overview(json.dumps(block.get("input", {}), ensure_ascii=False),
                                           DETAIL_COMPONENT_TRUNC, preserve_tail=True)
                return f"[tool] id={target} name={block.get('name', '?')}\n  input: {shown}" + ("\n  (input shortened)" if cut else "")
            if block.get("type") == "tool_result" and block.get("tool_use_id") == target:
                value = block.get("content", "")
                shown, cut = clip_overview(value if isinstance(value, str) else content_text(value),
                                           DETAIL_COMPONENT_TRUNC, preserve_tail=True)
                return f"[result] call={target}\n  {shown}" + ("\n  (result shortened)" if cut else "")
    raise ValueError(f"id not found: {target}")


def raw_detail(src: Source, target: str) -> Any:
    entries = visible(load_entries(src.path))
    parent_id, parent_target = _find(entries, target)
    for entry in entries:
        uuid = str(entry.get("uuid", "?"))
        content = (entry.get("message") or {}).get("content")
        blocks = content if isinstance(content, list) else []
        if parent_id == uuid and "/" in target:
            suffix = target[len(parent_target):]
            match = re.fullmatch(r"/(tool|thinking|result)/(\d+)", suffix)
            if not match:
                raise ValueError(f"invalid claude child locator: {target}")
            kind, number_text = match.groups()
            block_type = {"tool": "tool_use", "thinking": "thinking", "result": "tool_result"}[kind]
            selected = [b for b in blocks if isinstance(b, dict) and b.get("type") == block_type]
            number = int(number_text)
            if number < 1 or number > len(selected):
                raise ValueError(f"claude child locator not found: {target}")
            return selected[number - 1]
        if uuid == parent_id and "/" not in target:
            return entry
        for block in blocks:
            if isinstance(block, dict) and (
                (block.get("type") == "tool_use" and block.get("id") == target)
                or (block.get("type") == "tool_result" and block.get("tool_use_id") == target)
            ):
                return block
    raise ValueError(f"id not found: {target}")


def status_signals(src: Source) -> Dict[str, Any]:
    sig = empty_signals()
    try:
        path = src.path
        sig["persisted_age_s"] = time.time() - path.stat().st_mtime
        vis = visible(load_entries(path))
    except Exception:
        return sig
    ids = [e.get("uuid") for e in vis]
    sig["unread_count"] = unread_after_id(state.load_cursor(src.sid), identity_key="session_path",
                                          identity_value=str(path), last_key="last_entry_id", ids=ids)
    sig["turn"] = turn_state(vis)
    tokens = last_context_tokens(vis)
    model = last_model(vis)
    window, side_used, source = context_window(src.sid, model)
    if source == "statusline" and side_used:
        # Claude's own figure (what the TUI shows); the JSONL one can lag a turn.
        tokens = side_used
    sig["context_input_tokens"] = tokens
    sig["context_window_tokens"] = window
    sig["context_source"] = source
    sig["model"] = model
    sig["latest_marker"] = latest_supervisory_marker([format_entry(e) for e in vis[-50:]])
    return sig
