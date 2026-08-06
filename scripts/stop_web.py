# -*- coding: utf-8 -*-
"""Stop the Themis web server started by launch_web.py / 启动网站.bat.

Finds whatever holds the listening socket on 127.0.0.1:8000, confirms it is
this project's server before touching it, and asks it to exit. A port number
is not proof of identity, so a listener that is not ours is reported and left
alone rather than killed. English-only stdout so it renders correctly in a
legacy cmd.exe code page, matching launch_web.py.

Run directly: ``python scripts/stop_web.py`` (optionally with a port).
"""
from __future__ import annotations

import subprocess
import sys
import time

PORT = 8000
# What the command line of our own server looks like, whichever way it was
# started: `python -m themis.web`, `python scripts/launch_web.py`, or uvicorn
# pointed at the app.
OURS = ("themis.web", "launch_web", "themis/web", "themis\\web")


def _listener_pids(port: int) -> list[int]:
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                         capture_output=True, text=True).stdout
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0] != "TCP" or parts[3] != "LISTENING":
            continue
        if parts[1].rsplit(":", 1)[-1] != str(port):
            continue
        pids.add(int(parts[4]))
    return sorted(pids)


def _command_line(pid: int) -> str:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
        capture_output=True, text=True)
    return (r.stdout or "").strip()


def _stop(pid: int) -> bool:
    """Ask, then insist. Returns True once the process is gone."""
    subprocess.run(["taskkill", "/PID", str(pid), "/T"],
                   capture_output=True, text=True)
    for _ in range(6):
        time.sleep(0.5)
        if pid not in _listener_pids(PORT):
            return True
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                   capture_output=True, text=True)
    time.sleep(0.5)
    return pid not in _listener_pids(PORT)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    globals()["PORT"] = port

    pids = _listener_pids(port)
    if not pids:
        print(f"[stop] nothing is listening on 127.0.0.1:{port} — "
              f"the server is already down.")
        return 0

    stopped: list[int] = []
    survived: list[int] = []
    foreign: list[tuple[int, str]] = []

    for pid in pids:
        cmd = _command_line(pid)
        if not any(mark in cmd for mark in OURS):
            foreign.append((pid, cmd))
            continue
        print(f"[stop] pid {pid}: {cmd[:110]}")
        (stopped if _stop(pid) else survived).append(pid)

    for pid, cmd in foreign:
        print(f"[stop] pid {pid} holds port {port} but is NOT the Themis "
              f"server, so it was left alone:\n         {cmd[:160] or '<no command line>'}")

    if survived:
        print(f"[stop] could not stop {survived} — try again from an "
              f"administrator shell.")
        return 1
    if stopped:
        print(f"[stop] stopped {len(stopped)} process(es); port {port} is free.")
        return 0
    print(f"[stop] port {port} is in use, but not by this project. "
          f"Nothing was killed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
