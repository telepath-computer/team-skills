#!/usr/bin/env python3
"""Claude Code statusLine sidecar for supervisr.

Claude Code runs the configured statusLine command on every status refresh and
pipes a JSON blob to stdin (session_id, model, context_window, ...). This script
records that blob per session id under supervisr's state dir — giving `shep`
Claude's own context-window figure, which the transcript does not contain —
then hands the same input to whatever statusline command was configured before
(stored as `statusline_chain` in supervisr's statusline-sidecar.json), so the visible status
bar is unchanged. With no chained command — or if the chained command fails or prints
nothing — it prints a compact default line (model | ctx:<window>k | used:<tok>tok/<pct>%).

Installed by `supervisr setup statusline`; removed by `supervisr setup statusline --uninstall`.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def state_root() -> Path:
    for var in ("SUPERVISR_STATE_ROOT", "HERDR_PLUGIN_STATE_DIR"):
        if os.environ.get(var):
            return Path(os.environ[var])
    xdg = os.environ.get("XDG_STATE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "state") / "supervisr"


def main() -> int:
    raw = sys.stdin.read()
    root = state_root()
    chain = None
    try:
        cfg = json.loads((root / "statusline-sidecar.json").read_text())
        chain = cfg.get("statusline_chain")
    except Exception:
        pass
    try:
        data = json.loads(raw) if raw.strip() else {}
        sid = str(data.get("session_id") or "")
        if sid:
            out = {
                "session_id": sid,
                "model": data.get("model"),
                "context_window": data.get("context_window"),
                "cwd": data.get("cwd") or (data.get("workspace") or {}).get("current_dir"),
                "updated_at": time.time(),
            }
            d = root / "claude-ctx"
            d.mkdir(parents=True, exist_ok=True)
            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in sid)[:200]
            tmp = d / f"{safe}.json.tmp"
            tmp.write_text(json.dumps(out))
            os.replace(tmp, d / f"{safe}.json")
    except Exception:
        pass  # never let bookkeeping break the status bar
    if chain:
        # If the chained command is broken (deleted script, non-zero exit, empty
        # output), fall through to the default line rather than showing nothing.
        try:
            r = subprocess.run(chain, shell=True, input=raw, capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                sys.stdout.write(r.stdout)
                return 0
        except Exception:
            pass
    try:
        data = json.loads(raw)
        model = (data.get("model") or {}).get("display_name") or "claude"
        cw = data.get("context_window") or {}
        parts = [model]
        if cw.get("context_window_size"):
            parts.append(f"ctx:{int(cw['context_window_size']) // 1000}k")
        if cw.get("total_input_tokens") is not None and cw.get("used_percentage") is not None:
            parts.append(f"used:{int(cw['total_input_tokens'])}tok/{round(float(cw['used_percentage']))}%")
        print(" | ".join(parts))
    except Exception:
        print("claude")
    return 0


if __name__ == "__main__":
    sys.exit(main())
