#!/usr/bin/env python3
"""Close ONLY localhost:7878 tabs. Never exit the main Chrome browser."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request

OWL_MARKERS = ("127.0.0.1:7878", "localhost:7878", ":7878/")
CDP_PORTS = list(range(9222, 9236))
OWL_PROFILE_MARKER = "owl-chrome-profile"


def _close_via_cdp(port: int) -> int:
    closed = 0
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2) as resp:
            tabs = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return 0

    for tab in tabs:
        url = str(tab.get("url") or "")
        if not any(m in url for m in OWL_MARKERS):
            continue
        tid = tab.get("id")
        if not tid:
            continue
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{tid}", timeout=2)
            closed += 1
            print(f"CDP :{port} closed tab: {url[:90]}")
        except urllib.error.URLError:
            pass
    return closed


def _close_via_renderer_kill() -> int:
    """Kill only Chrome tab/renderer processes tied to :7878 — not the browser process."""
    ps = r"""
$closed = 0
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
  Where-Object {
    $c = $_.CommandLine
    if (-not $c) { return $false }
    if ($c -notmatch '7878|127\.0\.0\.1') { return $false }
    if ($c -match '--type=browser' -or $c -match '--type=gpu-process' -or $c -match '--type=utility') { return $false }
    $true
  } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    $closed++
    Write-Output "renderer $($_.ProcessId)"
  }
Write-Output "COUNT=$closed"
"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = (out.stdout or "") + (out.stderr or "")
        m = re.search(r"COUNT=(\d+)", text)
        count = int(m.group(1)) if m else 0
        for line in text.splitlines():
            if line.startswith("renderer "):
                print(f"Closed tab renderer PID {line.split()[1]}")
        return count
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"renderer kill skipped: {exc}")
        return 0


def _close_owl_profile_app() -> int:
    """Close isolated OWL app window via CDP on 9223 only — never Stop-Process chrome.exe."""
    return _close_via_cdp(9223)


def main() -> int:
    total = 0
    for port in CDP_PORTS:
        total += _close_via_cdp(port)
    total += _close_via_renderer_kill()
    total += _close_owl_profile_app()
    print(f"Closed {total} dashboard tab(s). Main Chrome browser left running.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
