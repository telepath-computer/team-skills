"""AgentInfo (from herdr) → Source (a worker's transcript identity).

Identity comes from the native session id herdr learned through its agent
integrations (`herdr integration install claude|codex|pi`). For Claude
there is a second, hook-free path: Claude Code writes
~/.claude/sessions/<pid>.json, and herdr can tell us the pane's foreground pid.
Nothing here ever picks "the newest file in the directory".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from . import state
from .adapters import SUPPORTED_KINDS, Source
from .adapters import claude as claude_ad
from .adapters import codex as codex_ad
from .adapters import pi as pi_ad
from .herdr import Client


class ResolveError(ValueError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason  # unsupported-kind | no-session-id | no-transcript


def _claude_session_from_pane(client: Client, pane_id: str):
    try:
        info = client.pane_process_info(pane_id)
    except Exception:
        return None, None
    for proc in info.get("foreground_processes") or []:
        name = str(proc.get("name") or "")
        if name == "claude" or name.endswith("/claude"):
            try:
                pid = int(proc.get("pid"))
            except (TypeError, ValueError):
                continue
            meta = claude_ad.session_from_pid(pid)
            if meta and meta.get("sessionId"):
                return str(meta["sessionId"]), meta.get("cwd")
    return None, None


def resolve(client: Client, agent: Dict[str, Any]) -> Source:
    kind = str(agent.get("agent") or "")
    if kind not in SUPPORTED_KINDS:
        raise ResolveError("unsupported-kind", f"agent kind '{kind or '?'}' has no transcript adapter")
    sess = agent.get("agent_session") or {}
    sid = sess.get("value") if sess.get("kind") == "id" else None
    sess_path = Path(sess["value"]) if sess.get("kind") == "path" and sess.get("value") else None
    cwd = agent.get("cwd")
    pane_id = agent.get("pane_id") or ""

    if kind == "claude":
        if not sid:
            sid, meta_cwd = _claude_session_from_pane(client, pane_id)
            cwd = cwd or meta_cwd
        if not sid:
            raise ResolveError("no-session-id",
                               "herdr has no session id for this Claude pane and ~/.claude/sessions/<pid>.json "
                               "was not found — is `herdr integration install claude` done, and has the agent started?")
        cached = state.load_session_cache(sid) or {}
        path = Path(cached["path"]) if cached.get("path") and Path(cached["path"]).exists() else None
        path = path or claude_ad.session_path_for(sid, cwd)
        if not path:
            raise ResolveError("no-transcript",
                               f"no transcript yet for Claude session {sid} (Claude writes it after the first turn)")
        _remember(sid, kind, path, agent)
        return Source(kind, sid, path=path, cwd=cwd)

    if kind == "codex":
        if not sid:
            raise ResolveError("no-session-id",
                               "herdr has no session id for this Codex pane — is `herdr integration install codex` done?")
        cached = state.load_session_cache(sid) or {}
        path = Path(cached["path"]) if cached.get("path") and Path(cached["path"]).exists() else None
        fresh = codex_ad.session_path_for(sid, cwd)
        if fresh and (path is None or fresh.stat().st_mtime > path.stat().st_mtime):
            path = fresh  # date rollover produces a newer file for the same session
        if not path:
            raise ResolveError("no-transcript",
                               f"no rollout yet for Codex session {sid} (written after the first turn)")
        _remember(sid, kind, path, agent)
        return Source(kind, sid, path=path, cwd=cwd)

    if kind == "pi":
        if sess_path and sess_path.exists():
            sid = pi_ad.filename_session_id(sess_path) or sess_path.stem
            _remember(sid, kind, sess_path, agent)
            return Source(kind, sid, path=sess_path, cwd=cwd)
        if not sid and sess_path:
            sid = pi_ad.filename_session_id(sess_path) or sess_path.stem
        if not sid:
            raise ResolveError("no-session-id",
                               "herdr has no session reference for this pi pane — is `herdr integration install pi` done?")
        cached = state.load_session_cache(sid) or {}
        path = Path(cached["path"]) if cached.get("path") and Path(cached["path"]).exists() else None
        path = path or pi_ad.session_path_for(sid, cwd)
        if not path:
            raise ResolveError("no-transcript",
                               f"no session file yet for pi session {sid} (pi writes it on the first assistant reply)")
        _remember(sid, kind, path, agent)
        return Source(kind, sid, path=path, cwd=cwd)

def _remember(sid: str, kind: str, path: Optional[Path], agent: Dict[str, Any], **extra: Any) -> None:
    cache = state.load_session_cache(sid) or {}
    cache.update({"sid": sid, "kind": kind, "path": str(path) if path else None,
                  "last_name": agent.get("name"), "last_pane_id": agent.get("pane_id"),
                  "last_workspace_id": agent.get("workspace_id"), "cwd": agent.get("cwd")})
    cache.update(extra)
    state.save_session_cache(sid, cache)
