"""Transcript adapters: one per agent harness.

Each adapter turns a harness's persisted history into the uniform `Entry`
stream defined in `render.py`, and answers the status questions a sweep asks
(turn state, context use, unread count, latest intent).

A `Source` is the resolved identity of one worker's transcript. It is built
from herdr's `AgentInfo` by `resolve.py`; adapters never guess by recency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class Source:
    kind: str                 # claude | codex | pi
    sid: str                  # native session id — cursor key
    path: Optional[Path] = None       # JSONL transcript (claude/codex/pi)
    cwd: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def identity(self) -> str:
        return str(self.path)


def adapter_for(kind: str):
    from . import claude, codex, pi
    table = {"claude": claude, "codex": codex, "pi": pi}
    if kind not in table:
        raise ValueError(f"unsupported agent kind for observation: {kind}")
    return table[kind]


SUPPORTED_KINDS = ("claude", "codex", "pi")


def empty_signals() -> Dict[str, Any]:
    return {
        "turn": "unknown", "persisted_age_s": float("inf"),
        "context_input_tokens": None, "context_window_tokens": None,
        "unread_count": None, "latest_marker": None,
    }
