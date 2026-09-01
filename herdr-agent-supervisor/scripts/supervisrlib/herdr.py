"""herdr socket client, caller context, and scope resolution.

The herdr control API is newline-delimited JSON over a unix socket: one
request line in, one response line out, connection closed (except
`events.subscribe`, which keeps streaming). No handshake. We speak it directly
rather than shelling out to `herdr` so a sweep over N agents is N cheap
round-trips, and so `events.subscribe` (which the CLI does not expose) works.

Socket resolution (first match wins): --session NAME → HERDR_SOCKET_PATH →
HERDR_SESSION → default session.
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


class HerdrError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "herdr"


def socket_path_for(session: Optional[str]) -> Path:
    if session:
        return config_dir() / "sessions" / session / "herdr.sock"
    env_path = os.environ.get("HERDR_SOCKET_PATH")
    if env_path:
        return Path(env_path)
    env_session = os.environ.get("HERDR_SESSION")
    if env_session and env_session != "default":
        return config_dir() / "sessions" / env_session / "herdr.sock"
    return config_dir() / "herdr.sock"


class Context:
    """Where the caller lives inside herdr, from the env herdr injects into panes."""

    def __init__(self) -> None:
        self.pane_id = os.environ.get("HERDR_PANE_ID")
        self.workspace_id = os.environ.get("HERDR_WORKSPACE_ID")
        self.tab_id = os.environ.get("HERDR_TAB_ID")
        self.session = os.environ.get("HERDR_SESSION")

    def inside_herdr(self) -> bool:
        return bool(self.pane_id and self.workspace_id)


class Client:
    def __init__(self, session: Optional[str] = None, *, verbose: bool = False,
                 timeout: float = 30.0):
        self.path = socket_path_for(session)
        self.verbose = verbose
        self.timeout = timeout
        self._seq = 0

    def _connect(self) -> socket.socket:
        if not self.path.exists():
            raise HerdrError("no_server", f"herdr socket not found at {self.path} — is the herdr server running?")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(str(self.path))
        return s

    def _next_id(self) -> str:
        self._seq += 1
        return f"supervisr:{os.getpid()}:{self._seq}"

    def call(self, method: str, params: Optional[Dict[str, Any]] = None,
             *, timeout: Optional[float] = None) -> Dict[str, Any]:
        params = params or {}
        req = {"id": self._next_id(), "method": method, "params": params}
        if self.verbose:
            import sys
            print(f"herdr> {method} {json.dumps(params, ensure_ascii=False)}", file=sys.stderr)
        s = self._connect()
        if timeout is not None:
            s.settimeout(timeout)
        try:
            s.sendall((json.dumps(req) + "\n").encode("utf-8"))
            line = _read_line(s)
        finally:
            s.close()
        if not line:
            raise HerdrError("empty_response", f"herdr returned no response for {method}")
        resp = json.loads(line)
        if "error" in resp:
            err = resp["error"] or {}
            raise HerdrError(str(err.get("code", "error")), str(err.get("message", "")))
        return resp.get("result", {})

    def subscribe(self, subscriptions: List[Dict[str, Any]], *,
                  idle_timeout: Optional[float] = None) -> Iterator[Dict[str, Any]]:
        """Yield subscription events until the server closes or idle_timeout passes."""
        req = {"id": self._next_id(), "method": "events.subscribe",
               "params": {"subscriptions": subscriptions}}
        s = self._connect()
        s.settimeout(idle_timeout)
        try:
            s.sendall((json.dumps(req) + "\n").encode("utf-8"))
            buf = b""
            while True:
                try:
                    chunk = s.recv(65536)
                except socket.timeout:
                    yield {"type": "timeout"}
                    continue
                if not chunk:
                    return
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        finally:
            s.close()

    # -- convenience wrappers -------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        return self.call("session.snapshot").get("snapshot", {})

    def agents(self) -> List[Dict[str, Any]]:
        return self.call("agent.list").get("agents", [])

    def agent_get(self, target: str) -> Dict[str, Any]:
        return self.call("agent.get", {"target": target}).get("agent", {})

    def agent_read(self, target: str, lines: int, source: str = "recent_unwrapped") -> Dict[str, Any]:
        return self.call("agent.read", {"target": target, "source": source, "lines": lines,
                                        "format": "text", "strip_ansi": True}).get("read", {})

    def agent_explain(self, target: str) -> Dict[str, Any]:
        return self.call("agent.explain", {"target": target}).get("explain", {})

    def agent_prompt(self, target: str, text: str, wait: Optional[Dict[str, Any]] = None,
                     *, timeout: Optional[float] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"target": target, "text": text}
        if wait is not None:
            params["wait"] = wait
        return self.call("agent.prompt", params, timeout=timeout).get("agent", {})

    def agent_send_keys(self, target: str, keys: List[str]) -> None:
        self.call("agent.send_keys", {"target": target, "keys": keys})

    def agent_wait(self, target: str, until: List[str], timeout_ms: Optional[int]) -> Dict[str, Any]:
        params: Dict[str, Any] = {"target": target, "until": until}
        if timeout_ms is not None:
            params["timeout_ms"] = timeout_ms
        sock_timeout = (timeout_ms / 1000 + 5) if timeout_ms else None
        return self.call("agent.wait", params, timeout=sock_timeout).get("agent", {})

    def agent_start(self, name: str, kind: str, pane_id: str, args: List[str],
                    timeout_ms: int = 30000) -> Dict[str, Any]:
        return self.call("agent.start", {"name": name, "kind": kind, "pane_id": pane_id,
                                         "args": args, "timeout_ms": timeout_ms},
                         timeout=timeout_ms / 1000 + 5)

    def pane_get(self, pane_id: str) -> Dict[str, Any]:
        return self.call("pane.get", {"pane_id": pane_id}).get("pane", {})

    def pane_process_info(self, pane_id: str) -> Dict[str, Any]:
        return self.call("pane.process_info", {"pane_id": pane_id}).get("process_info", {})

    def pane_send_text(self, pane_id: str, text: str) -> None:
        self.call("pane.send_text", {"pane_id": pane_id, "text": text})

    def pane_send_keys(self, pane_id: str, keys: List[str]) -> None:
        self.call("pane.send_keys", {"pane_id": pane_id, "keys": keys})

    def pane_split(self, target_pane_id: Optional[str], direction: str, cwd: Optional[str],
                   workspace_id: Optional[str] = None, focus: bool = False) -> Dict[str, Any]:
        params: Dict[str, Any] = {"direction": direction, "focus": focus}
        if target_pane_id:
            params["target_pane_id"] = target_pane_id
        if workspace_id:
            params["workspace_id"] = workspace_id
        if cwd:
            params["cwd"] = cwd
        result = self.call("pane.split", params)
        return result.get("pane") or result

    def tab_create(self, workspace_id: str, label: Optional[str], cwd: Optional[str],
                   focus: bool = False) -> Dict[str, Any]:
        params: Dict[str, Any] = {"workspace_id": workspace_id, "focus": focus}
        if label:
            params["label"] = label
        if cwd:
            params["cwd"] = cwd
        return self.call("tab.create", params)

    def pane_close(self, pane_id: str) -> None:
        self.call("pane.close", {"pane_id": pane_id})

    def report_tokens(self, pane_id: str, source: str, tokens: Dict[str, Optional[str]],
                      ttl_ms: Optional[int] = None) -> None:
        params: Dict[str, Any] = {"pane_id": pane_id, "source": source, "tokens": tokens}
        if ttl_ms:
            params["ttl_ms"] = ttl_ms
        self.call("pane.report_metadata", params)


def _read_line(s: socket.socket) -> str:
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    return buf.decode("utf-8", errors="replace").strip()


# -- scope -------------------------------------------------------------------

OWNER_TOKEN = "supervisr_owner"
METADATA_SOURCE = "supervisr"


class Scope:
    """Which agents a command sees. A filter over herdr's agent list, never a registry."""

    def __init__(self, ctx: Context, *, workspace: Optional[str] = None, tab: Optional[str] = None,
                 owned: bool = False, all_agents: bool = False, repo: bool = False,
                 include_self: bool = False):
        self.ctx = ctx
        self.workspace = workspace
        self.tab = tab
        self.owned = owned
        self.all = all_agents
        self.repo = repo
        self.include_self = include_self

    def describe(self) -> str:
        if self.all:
            base = "all workspaces"
        elif self.tab:
            base = f"tab {self.tab}"
        elif self.repo:
            base = "workspaces sharing my repo"
        else:
            base = f"workspace {self.workspace or self.ctx.workspace_id or '?'}"
        if self.owned:
            base += " (owned only)"
        return base

    def select(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        agents = snapshot.get("agents", [])
        workspaces = {w["workspace_id"]: w for w in snapshot.get("workspaces", [])}
        me = self.ctx.pane_id
        out = []
        if self.repo:
            my_ws = workspaces.get(self.workspace or self.ctx.workspace_id or "")
            my_key = ((my_ws or {}).get("worktree") or {}).get("repo_key")
            allowed = {wid for wid, w in workspaces.items()
                       if my_key and ((w.get("worktree") or {}).get("repo_key") == my_key)}
            if not allowed and my_ws:
                allowed = {my_ws["workspace_id"]}
        for a in agents:
            if not self.include_self and me and a.get("pane_id") == me:
                continue
            if self.all:
                pass
            elif self.tab:
                if a.get("tab_id") != self.tab:
                    continue
            elif self.repo:
                if a.get("workspace_id") not in allowed:
                    continue
            else:
                ws = self.workspace or self.ctx.workspace_id
                if ws is None:
                    raise ValueError(
                        "no workspace scope: HERDR_WORKSPACE_ID is not set (not running inside a herdr pane).\n"
                        "  pass --workspace <id>, --all, or run from inside herdr.")
                if a.get("workspace_id") != ws:
                    continue
            if self.owned:
                owner = (a.get("tokens") or {}).get(OWNER_TOKEN)
                if not owner or (me and owner != me):
                    continue
            out.append(a)
        return out


def agent_label(a: Dict[str, Any]) -> str:
    return a.get("name") or a.get("pane_id") or "?"


def wait_for(predicate, timeout_s: float, interval: float = 0.5):
    deadline = time.time() + timeout_s
    while True:
        value = predicate()
        if value:
            return value
        if time.time() >= deadline:
            return None
        time.sleep(interval)
