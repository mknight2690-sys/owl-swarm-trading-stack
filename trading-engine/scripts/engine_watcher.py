#!/usr/bin/env python3
"""AutoHedge Engine Watcher — monitors, auto-fixes, reports. No alerts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = ROOT / "outputs" / "live-run.log"
WATCH_LOG = ROOT / "outputs" / "engine_watcher.log"
LOCK_FILE = ROOT / "outputs" / "blofin-loop.lock"
SHELL_LOCK = ROOT / "outputs" / "blofin-loop-shell.lock"
RESTART_LOG = ROOT / "outputs" / "engine_watcher_restarts.jsonl"

MAX_STALL_SEC = 300  # 5 minutes without cycle start = stalled
CYCLE_START_RE = re.compile(r"CYCLE\s+(\d+)\s+starting")
CYCLE_ERROR_RE = re.compile(r"CYCLE\s+(\d+)\s+error:")
TPSL_ERROR_RE = re.compile(r"cannot access local variable 'tpsl'")
PYTHON_EXE = os.environ.get("PYTHON_EXE", r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe")
LOOP_SCRIPT = ROOT / "scripts" / "run_blofin_loop.py"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str) -> None:
    line = f"[{_now()}] {msg}"
    print(line)
    try:
        with WATCH_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _record_restart(reason: str, details: dict) -> None:
    entry = {"ts": time.time(), "ts_iso": _now(), "reason": reason, **details}
    try:
        with RESTART_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def _find_engine_pid() -> int | None:
    """Find the blofin loop python process."""
    try:
        if sys.platform == "win32":
            # Read lock file first
            if LOCK_FILE.is_file():
                try:
                    pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
                    if pid > 0:
                        # Verify it's alive
                        import ctypes
                        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                        if handle:
                            ctypes.windll.kernel32.CloseHandle(handle)
                            return pid
                except (ValueError, OSError):
                    pass
            # Fallback: tasklist
            result = subprocess.run(
                ["tasklist", "/fi", "imagename eq python.exe", "/fo", "csv"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines()[1:]:
                parts = line.strip().strip('"').split('","')
                if len(parts) >= 2:
                    try:
                        pid = int(parts[1])
                        return pid
                    except ValueError:
                        pass
    except Exception as exc:
        _log(f"WARN: PID lookup failed: {exc}")
    return None


def _kill_process(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=15)
        else:
            os.kill(pid, 9)
        time.sleep(2)
        return True
    except Exception as exc:
        _log(f"WARN: Failed to kill PID {pid}: {exc}")
        return False


def _start_engine() -> int | None:
    try:
        # Clean up old lock files
        for lf in (LOCK_FILE, SHELL_LOCK):
            if lf.is_file():
                try:
                    lf.unlink()
                except OSError:
                    pass
        # Start the loop in background
        proc = subprocess.Popen(
            [PYTHON_EXE, str(LOOP_SCRIPT), "--sleep", "30", "--log-file", "outputs/live-run.log"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        time.sleep(5)  # Give it time to start
        return proc.pid
    except Exception as exc:
        _log(f"ERROR: Failed to start engine: {exc}")
        return None


def _check_log_tail(n: int = 100) -> list[str]:
    if not LOG_FILE.is_file():
        return []
    try:
        text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-n:] if len(lines) > n else lines
    except OSError:
        return []


def _last_cycle_start_time(lines: list[str]) -> float | None:
    """Return timestamp of last 'CYCLE X starting' line."""
    for line in reversed(lines):
        match = CYCLE_START_RE.search(line)
        if match:
            # Try to extract timestamp from the line prefix
            ts_match = re.search(r"\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]", line)
            if ts_match:
                try:
                    dt = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
                    return dt.timestamp()
                except ValueError:
                    pass
            return time.time()  # fallback: assume recent
    return None


def _check_for_tpsl_error(lines: list[str]) -> bool:
    return any(TPSL_ERROR_RE.search(line) for line in lines[-50:])


def _check_for_cycle_error(lines: list[str]) -> tuple[bool, str]:
    for line in reversed(lines[-50:]):
        match = CYCLE_ERROR_RE.search(line)
        if match:
            return True, line.strip()
    return False, ""


def main() -> int:
    _log("=" * 60)
    _log("Engine watcher check starting")
    _log("=" * 60)

    pid = _find_engine_pid()
    lines = _check_log_tail(200)

    issues: list[str] = []
    actions: list[str] = []

    # 1. Check if engine is running
    if pid is None:
        issues.append("Engine process not found")
        _log("ISSUE: Engine process not found")
    else:
        _log(f"OK: Engine running at PID {pid}")

    # 2. Check for tpsl error (regression)
    if _check_for_tpsl_error(lines):
        issues.append("tpsl UnboundLocalError detected (regression)")
        _log("ISSUE: tpsl UnboundLocalError detected in recent log")

    # 3. Check for any cycle error
    has_error, error_line = _check_for_cycle_error(lines)
    if has_error:
        issues.append(f"Cycle error: {error_line[:120]}")
        _log(f"ISSUE: Cycle error — {error_line[:120]}")

    # 4. Check for stall (no new cycle start for > 5 min)
    last_start = _last_cycle_start_time(lines)
    if last_start is None:
        if pid is not None:
            issues.append("No cycle start found in recent log — possible stall")
            _log("ISSUE: No cycle start found in recent log")
    else:
        elapsed = time.time() - last_start
        _log(f"OK: Last cycle start was {elapsed:.0f}s ago")
        if elapsed > MAX_STALL_SEC:
            issues.append(f"Engine stalled — no cycle start for {elapsed:.0f}s")
            _log(f"ISSUE: Engine stalled — no cycle start for {elapsed:.0f}s")

    # 5. Check log file age
    if LOG_FILE.is_file():
        log_age = time.time() - LOG_FILE.stat().st_mtime
        _log(f"OK: Log file age = {log_age:.0f}s")
        if log_age > MAX_STALL_SEC:
            issues.append(f"Log file stale ({log_age:.0f}s old)")
            _log(f"ISSUE: Log file stale ({log_age:.0f}s old)")
    else:
        issues.append("Log file missing")
        _log("ISSUE: Log file missing")

    # Auto-fix: if any issue detected, restart the engine
    if issues:
        _log(f"ACTION: {len(issues)} issue(s) detected — restarting engine")
        if pid is not None:
            _log(f"ACTION: Killing PID {pid}")
            _kill_process(pid)
            time.sleep(3)

        new_pid = _start_engine()
        if new_pid:
            actions.append(f"Restarted engine at PID {new_pid}")
            _log(f"OK: Engine restarted at PID {new_pid}")
            _record_restart(
                "auto_restart",
                {"issues": issues, "new_pid": new_pid, "old_pid": pid}
            )
        else:
            actions.append("FAILED to restart engine")
            _log("ERROR: Failed to restart engine")
            _record_restart(
                "restart_failed",
                {"issues": issues, "old_pid": pid}
            )
    else:
        _log("OK: No issues detected — engine healthy")
        actions.append("No action needed — engine healthy")

    _log("=" * 60)
    _log(f"Watcher check complete. Issues: {len(issues)}, Actions: {len(actions)}")
    _log("=" * 60)

    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
