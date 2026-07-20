# -*- coding: utf-8 -*-
"""One-click launcher for the Themis web product.

Rebuilds the frontend (so a stale ``frontend/dist`` can never be served),
starts the FastAPI backend on 127.0.0.1:8000, and opens the browser once the
server answers. Close the window (Ctrl-C) to stop. English-only stdout so it
renders correctly in a legacy cmd.exe code page.

Run directly (``python scripts/launch_web.py``) or via ``启动网站.bat``.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FRONTEND = REPO / "themis" / "web" / "frontend"
URL = "http://127.0.0.1:8000"


def _build_frontend() -> None:
    """Best-effort rebuild. If pnpm/node is missing or the build fails, fall
    back to whatever is already in dist/ rather than blocking the demo."""
    if not (FRONTEND / "node_modules").exists():
        print("[build] installing frontend deps (first run, ~1 min)...", flush=True)
        subprocess.run("pnpm install", cwd=str(FRONTEND), shell=True)
    print("[build] rebuilding frontend...", flush=True)
    r = subprocess.run("pnpm build", cwd=str(FRONTEND), shell=True)
    if r.returncode != 0:
        dist_ok = (FRONTEND / "dist" / "index.html").exists()
        if dist_ok:
            print("[build] SKIPPED (pnpm unavailable or build failed) — "
                  "serving the existing dist/ build.", flush=True)
        else:
            print("[build] FAILED and no existing dist/ — the page will fall back "
                  "to the legacy static UI. Install Node + pnpm to build the React app.",
                  flush=True)


def _open_when_ready() -> None:
    for _ in range(120):  # up to ~60s
        try:
            urllib.request.urlopen(URL, timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    webbrowser.open(URL)


def main() -> None:
    os.chdir(REPO)
    _build_frontend()
    threading.Thread(target=_open_when_ready, daemon=True).start()
    print(f"[serve] Themis web at {URL}  (close this window to stop)", flush=True)
    try:
        import uvicorn
    except ImportError:
        print("[serve] uvicorn not installed. Run: pip install uvicorn fastapi", flush=True)
        sys.exit(1)
    uvicorn.run("themis.web.app:app", host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
