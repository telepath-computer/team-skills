"""Bounded rendering primitives shared by every transcript adapter.

Everything a supervisor reads passes through here. The budgets are tuned so an
idle worker costs a few bytes to observe and a busy one costs a bounded page.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# -- truncation defaults ------------------------------------------------------

ARGS_TRUNC = 140
RESULT_TRUNC = 220
TEXT_TRUNC = 4000
RECENT_COUNT_DEFAULT = 6
MAX_RENDERED_CHARS = 12000
ESTABLISHED_THRESHOLD = 20  # entries; cursor required beyond this on bootstrap

# Compact-overview budgets apply after whitespace normalization.
OVERVIEW_TEXT_TRUNC = 420
OVERVIEW_INTENT_TRUNC = 220
OVERVIEW_TOOL_TRUNC = 160
OVERVIEW_RESULT_TRUNC = 180
DETAIL_COMPONENT_TRUNC = 8000
LOCATOR_PREFIX_MIN = 8


def trunc(text: Any, limit: int) -> str:
    s = "" if text is None else str(text)
    if len(s) <= limit:
        return s
    return f"{s[:limit]}... ({len(s)} chars)"


def single_line(text: Any, limit: int) -> str:
    return trunc(str(text).replace("\n", "\\n"), limit)


def normalize_whitespace(text: Any) -> str:
    return re.sub(r"\s+", " ", "" if text is None else str(text)).strip()


def clip_overview(text: Any, limit: int, *, preserve_tail: bool = False) -> Tuple[str, bool]:
    """Character-wise clipping for compact overview lines.

    Prose and tool results keep a small tail (conclusions and errors live
    there). Tool-call arguments favor the leading text, which identifies the
    command, path, pattern, query, or URL.
    """
    value = normalize_whitespace(text)
    if len(value) <= limit:
        return value, False
    if limit <= 1:
        return "…", True
    if preserve_tail and limit >= 24:
        tail = max(12, limit // 4)
        head = limit - tail - 1
        return f"{value[:head].rstrip()}…{value[-tail:].lstrip()}", True
    return f"{value[:limit - 1].rstrip()}…", True


def reasoning_labels(text: Any) -> List[str]:
    """Readable plaintext intent labels from a persisted reasoning summary."""
    raw = "" if text is None else str(text)
    labels = []
    for part in re.split(r"\n\s*\n", raw):
        value = normalize_whitespace(part)
        if value.startswith("**") and value.endswith("**") and len(value) >= 4:
            value = value[2:-2].strip()
        if value:
            labels.append(value)
    return labels


def meaningful_stop_reason(reason: Any, *, has_tool_call: bool = False) -> Optional[str]:
    value = "" if reason is None else str(reason).strip()
    normalized = re.sub(r"[-_]", "", value).lower()
    if normalized in {"stop", "endturn"}:
        return None
    if normalized == "tooluse" and has_tool_call:
        return None
    return value or None


def common_prefix_length(left: str, right: str) -> int:
    size = 0
    for a, b in zip(left, right):
        if a != b:
            break
        size += 1
    return size


def unique_prefixes(values: List[str], minimum: int = LOCATOR_PREFIX_MIN) -> Dict[str, str]:
    strings = sorted(str(v) for v in values if v)
    out: Dict[str, str] = {}
    for index, value in enumerate(strings):
        previous = common_prefix_length(value, strings[index - 1]) if index else 0
        following = common_prefix_length(value, strings[index + 1]) if index + 1 < len(strings) else 0
        needed = max(previous, following) + 1
        size = min(len(value), max(minimum, needed))
        out[value] = value[:size]
    return out


def resolve_unique_prefix(values: List[str], target: str, label: str = "id") -> str:
    if target in values:
        return target
    matches = [v for v in values if v.startswith(target)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"{label} not found: {target}")
    prefixes = unique_prefixes(matches)
    choices = ", ".join(prefixes[v] for v in matches[:12])
    suffix = " …" if len(matches) > 12 else ""
    raise ValueError(f"ambiguous {label} prefix '{target}'; use one of: {choices}{suffix}")


def fmt_ts(ts: Any) -> str:
    if not ts:
        return "?"
    try:
        if isinstance(ts, (int, float)):
            seconds = ts / 1000 if ts > 1e12 else ts
            return datetime.fromtimestamp(seconds).strftime("%H:%M:%S")
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).strftime("%H:%M:%S")
    except Exception:
        return str(ts)[:19]


def preview_args(args: Any, limit: int, preferred: List[str]) -> str:
    if not isinstance(args, dict):
        return single_line(str(args), limit)
    for k in preferred:
        if k in args:
            return f"{k}={single_line(json.dumps(args[k], ensure_ascii=False), limit)}"
    if not args:
        return ""
    k = next(iter(args))
    return f"{k}={single_line(json.dumps(args[k], ensure_ascii=False), limit)}"


# -- entry model --------------------------------------------------------------

class OverviewLine:
    """One bounded line in an overflow overview."""

    def __init__(self, locator: str, ts: str, kind: str, text: Any = "", *,
                 limit: int = OVERVIEW_TEXT_TRUNC, preserve_tail: bool = False):
        self.locator = locator
        self.ts = ts
        self.kind = kind
        self.text, self.truncated = clip_overview(text, limit, preserve_tail=preserve_tail)

    def render(self) -> str:
        suffix = f" {self.text}" if self.text else ""
        return f"{self.ts} {self.locator} {self.kind}{suffix}"


class Entry:
    """Uniform rendered entry returned by adapters.

    One persisted entry may contain several overview lines; every tool call
    stays individually visible rather than collapsing into a count.
    """

    def __init__(self, eid: str, ts: str, kind: str, header: str, body: str = "",
                 overview: Optional[List[OverviewLine]] = None,
                 cursor_after: Optional[Dict[str, Any]] = None):
        self.id = eid
        self.ts = ts
        self.kind = kind
        self.header = header
        self.body = body
        self.overview = overview or [OverviewLine(eid, ts, kind, body or header)]
        self.cursor_after = cursor_after

    def render(self) -> str:
        return f"{self.header}\n{self.body}" if self.body else self.header

    def render_overview(self) -> str:
        return "\n".join(line.render() for line in self.overview)

    def overview_was_truncated(self) -> bool:
        return any(line.truncated for line in self.overview)


def render_entries(entries: List[Entry]) -> str:
    return "\n\n".join(e.render() for e in entries)


def render_overview(entries: List[Entry]) -> str:
    return "\n".join(e.render_overview() for e in entries)


def latest_supervisory_marker(entries: List[Entry]) -> Optional[Tuple[str, str]]:
    """Most recent readable intent or conversation text, excluding tool traffic."""
    for entry in reversed(entries):
        intents = [l for l in entry.overview if l.kind == "intent" and l.text]
        if intents:
            return "intent", intents[-1].text
        messages = [l for l in entry.overview if l.kind in {"assistant", "user"} and l.text]
        if messages:
            return messages[-1].kind, messages[-1].text
    return None


def unread_after_id(cursor: Optional[Dict[str, Any]], *, identity_key: str,
                    identity_value: str, last_key: str, ids: List[Any]) -> Optional[int]:
    """Exact unread count for an id-addressed cursor, or None if it is stale."""
    if cursor is None:
        return len(ids)
    if cursor.get(identity_key) != identity_value:
        return None
    try:
        index = ids.index(cursor.get(last_key))
    except ValueError:
        return None
    return len(ids) - index - 1


def overview_page(entries: List[Entry]) -> List[Entry]:
    """Largest oldest contiguous entry page whose compact overview fits."""
    page: List[Entry] = []
    for entry in entries:
        candidate = page + [entry]
        if page and len(render_overview(candidate)) > MAX_RENDERED_CHARS:
            break
        page.append(entry)
        if len(render_overview(page)) > MAX_RENDERED_CHARS:
            break
    return page


def fmt_tokens(n: Optional[int]) -> str:
    if not n:
        return "?"
    return f"{n / 1000:.0f}k"
