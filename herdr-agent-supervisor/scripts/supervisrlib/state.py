"""Supervisr's own on-disk state: cursors, notes, per-session caches.

Everything is keyed by the worker's native session id — the identity of its
transcript — never by pane id or herdr agent name. Panes get new ids when
moved; names can be renamed or reused; the session id survives all of that,
including a herdr restart that relaunches the agent with `--resume`.

Location (first match wins):
  $SUPERVISR_STATE_ROOT
  $HERDR_PLUGIN_STATE_DIR        (when running as a herdr plugin hook)
  $XDG_STATE_HOME/supervisr
  ~/.local/state/supervisr
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _root() -> Path:
    for var in ("SUPERVISR_STATE_ROOT", "HERDR_PLUGIN_STATE_DIR"):
        value = os.environ.get(var)
        if value:
            return Path(value)
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "supervisr"


STATE_ROOT = _root()
CURSORS_DIR = STATE_ROOT / "cursors"
NOTES_DIR = STATE_ROOT / "notes"
SESSIONS_DIR = STATE_ROOT / "sessions"      # resolved transcript + metadata cache per sid
CLAUDE_CTX_DIR = STATE_ROOT / "claude-ctx"  # statusline sidecar output per Claude session id
SIDECAR_CONFIG_PATH = STATE_ROOT / "statusline-sidecar.json"  # owned by claude-statusline-sidecar.py


def ensure_dirs() -> None:
    for d in (CURSORS_DIR, NOTES_DIR, SESSIONS_DIR, CLAUDE_CTX_DIR):
        d.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_key(value: str) -> str:
    """Filesystem-safe form of a session id (ids may contain / or : for some agents)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)[:200]


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# -- cursors -----------------------------------------------------------------

def cursor_path(sid: str) -> Path:
    return CURSORS_DIR / f"{safe_key(sid)}.json"


def load_cursor(sid: str) -> Optional[Dict[str, Any]]:
    p = cursor_path(sid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_cursor(sid: str, payload: Dict[str, Any]) -> None:
    payload = dict(payload)
    payload["updated_at"] = now_iso()
    _atomic_write(cursor_path(sid), json.dumps(payload, indent=2))


def reset_cursor(sid: str) -> None:
    p = cursor_path(sid)
    if p.exists():
        p.unlink()


# -- notes -------------------------------------------------------------------

def notes_path(sid: str) -> Path:
    return NOTES_DIR / f"{safe_key(sid)}.md"


def append_note(sid: str, label: str, text: str, tag: str) -> Path:
    p = notes_path(sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(f"# notes — {label} ({sid})\n\n", encoding="utf-8")
    with p.open("a", encoding="utf-8") as f:
        f.write(f"- {now_iso()} [{tag}] {text}\n")
    return p


# -- per-session cache -------------------------------------------------------

def session_cache_path(sid: str) -> Path:
    return SESSIONS_DIR / f"{safe_key(sid)}.json"


def load_session_cache(sid: str) -> Optional[Dict[str, Any]]:
    p = session_cache_path(sid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_session_cache(sid: str, payload: Dict[str, Any]) -> None:
    payload = dict(payload)
    payload["updated_at"] = now_iso()
    _atomic_write(session_cache_path(sid), json.dumps(payload, indent=2))


def forget(sid: str) -> Dict[str, bool]:
    removed = {}
    for name, p in (("cursor", cursor_path(sid)), ("notes", notes_path(sid)),
                    ("session", session_cache_path(sid)),
                    ("claude-ctx", CLAUDE_CTX_DIR / f"{safe_key(sid)}.json")):
        if p.exists():
            p.unlink()
            removed[name] = True
    return removed


# -- claude statusline sidecar ----------------------------------------------

def load_claude_ctx(sid: str) -> Optional[Dict[str, Any]]:
    p = CLAUDE_CTX_DIR / f"{safe_key(sid)}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# -- statusline sidecar config ----------------------------------------------

def load_sidecar_config() -> Dict[str, Any]:
    if not SIDECAR_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(SIDECAR_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_sidecar_config(cfg: Dict[str, Any]) -> None:
    _atomic_write(SIDECAR_CONFIG_PATH, json.dumps(cfg, indent=2))
