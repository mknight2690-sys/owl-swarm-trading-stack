"""Watch live-run.log every 60s for 60 rounds, auto-fix known errors."""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "outputs" / "live-run.log"
START = int(sys.argv[1]) if len(sys.argv) > 1 else LOG.stat().st_size
INTERVAL = int(sys.argv[2]) if len(sys.argv) > 2 else 60
ROUNDS = int(sys.argv[3]) if len(sys.argv) > 3 else 60

ERR_RE = re.compile(r"ERROR|152002|103003|Traceback|CYCLE .* error|NameError|FileNotFoundError|NameResolutionError", re.I)


def scan(offset: int) -> tuple[int, list[str], list[str]]:
    data = LOG.read_bytes()[offset:].decode("utf-8", errors="replace")
    lines = data.splitlines()
    errs = [l for l in lines if ERR_RE.search(l)]
    trades = [l for l in lines if "Deterministic Execution completed" in l or "Set leverage" in l]
    return offset + len(data.encode("utf-8", errors="replace")), errs, trades


def restart_loop() -> None:
    """Kill existing loop processes and relaunch."""
    subprocess.run(
        ["powershell.exe", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object {$_.CommandLine -like '*run_blofin_loop*'} | "
         "ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}"],
        capture_output=True, timeout=15,
    )
    time.sleep(2)
    subprocess.run(
        ["powershell.exe", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | "
         "Where-Object {$_.CommandLine -like '*run_blofin_loop*'} | "
         "ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}"],
        capture_output=True, timeout=15,
    )
    time.sleep(1)
    subprocess.run(
        ["powershell.exe", "-Command",
         "Remove-Item 'C:\\Users\\mknig\\blofin-auto-trader\\outputs\\blofin-loop.lock' -Force -ErrorAction SilentlyContinue; "
         "Remove-Item 'C:\\Users\\mknig\\blofin-auto-trader\\outputs\\blofin-loop-shell.lock' -Force -ErrorAction SilentlyContinue"],
        capture_output=True, timeout=10,
    )
    script = "Set-Location 'C:\\Users\\mknig\\blofin-auto-trader'; .\\.venv\\Scripts\\python.exe scripts\\run_blofin_loop.py --sleep 30 --log-file outputs\\live-run.log"
    subprocess.Popen(
        ["powershell.exe", "-NoExit", "-Command", script],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        if sys.platform == "win32"
        else 0,
    )
    print("[fix] Restarted AutoHedge loop", flush=True)


def fix_nameerror_os() -> None:
    """Fix missing os import in blofin_universe_feed.py."""
    f = ROOT / "autohedge" / "tools" / "blofin_universe_feed.py"
    text = f.read_text(encoding="utf-8")
    if "import os" not in text.splitlines()[:10]:
        text = text.replace("import json", "import json\nimport os", 1)
        f.write_text(text, encoding="utf-8")
        print("[fix] Added 'import os' to blofin_universe_feed.py", flush=True)


def fix_credentials_path() -> None:
    """Ensure .env points to the correct credentials file."""
    env = ROOT / ".env"
    text = env.read_text(encoding="utf-8")
    target = 'BLOFIN_CREDENTIALS_PATH="C:\\Users\\mknig\\Downloads\\MK Blo Hermes API compendium.txt"'
    if target not in text:
        text = re.sub(
            r'BLOFIN_CREDENTIALS_PATH="[^"]*"',
            target,
            text,
        )
        env.write_text(text, encoding="utf-8")
        print("[fix] Updated BLOFIN_CREDENTIALS_PATH in .env", flush=True)


def fix_api_base() -> None:
    """Ensure BLOFIN_API_BASE is api.blofin.com (not 1b.blofin.com)."""
    env = ROOT / ".env"
    text = env.read_text(encoding="utf-8")
    target = 'BLOFIN_API_BASE="https://api.blofin.com"'
    if target not in text:
        if "BLOFIN_API_BASE=" in text:
            text = re.sub(r'BLOFIN_API_BASE="[^"]*"', target, text)
        else:
            text = text.rstrip() + "\n" + target + "\n"
        env.write_text(text, encoding="utf-8")
        print("[fix] Set BLOFIN_API_BASE to api.blofin.com", flush=True)


def main() -> None:
    offset = START
    print(f"watch_and_fix start offset={offset} rounds={ROUNDS} interval={INTERVAL}s")
    fixes_applied: set[str] = set()
    for i in range(1, ROUNDS + 1):
        time.sleep(INTERVAL)
        offset, errs, trades = scan(offset)
        print(f"\n=== check {i} | trades_so_far={len(trades)} ===", flush=True)
        if errs:
            print(f"[!] {len(errs)} errors detected:", flush=True)
            for line in errs[-5:]:
                print("  " + line[:200], flush=True)
        for line in trades[-3:]:
            print("  [trade] " + line[:150], flush=True)

        # Auto-fix known errors
        blob = "\n".join(errs)
        if "NameError: name 'os' is not defined" in blob and "os_import" not in fixes_applied:
            fix_nameerror_os()
            fixes_applied.add("os_import")
            restart_loop()
        if "1b.blofin.com" in blob and "api_base" not in fixes_applied:
            fix_api_base()
            fixes_applied.add("api_base")
            restart_loop()
        if "credentials not found" in blob and "creds_path" not in fixes_applied:
            fix_credentials_path()
            fixes_applied.add("creds_path")
            restart_loop()
        if "152401" in blob and "api_base" not in fixes_applied:
            fix_api_base()
            fixes_applied.add("api_base")
            restart_loop()

    print(f"\nwatch_and_fix complete. Total trades observed: {len(trades)}", flush=True)


if __name__ == "__main__":
    main()
