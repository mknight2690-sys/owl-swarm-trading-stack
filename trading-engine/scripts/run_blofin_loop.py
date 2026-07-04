#!/usr/bin/env python3
"""Run AutoHedge in a loop with a pause between cycles."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import autohedge.swarms_bootstrap  # noqa: F401 — patch handoffs before agents load

LOCK_PATH = ROOT / "outputs" / "blofin-loop.lock"
SHELL_LOCK_PATH = ROOT / "outputs" / "blofin-loop-shell.lock"
_MUTEX_NAME = "Global\\BlofinAutoHedgeLoop_v3"  # v3: clean after v2 orphan
_mutex_handle = None
_shell_pid = 0


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_shell_lock_pid() -> int:
    if not SHELL_LOCK_PATH.is_file():
        return 0
    try:
        return int(SHELL_LOCK_PATH.read_text(encoding="utf-8").strip())
    except (TypeError, ValueError):
        return 0


def _acquire_singleton_lock() -> None:
    global _mutex_handle
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        _mutex_handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
        err = kernel32.GetLastError()
        if err == ERROR_ALREADY_EXISTS:
            # Mutex exists — try to release it (handles abandoned-mutex case).
            # If ReleaseMutex fails, another live process truly owns it.
            # We attempt ReleaseMutex + CloseHandle + re-Create to force-clean.
            released = kernel32.ReleaseMutex(_mutex_handle)
            kernel32.CloseHandle(_mutex_handle)
            _mutex_handle = None
            if released:
                # Was abandoned — safe to re-create
                _mutex_handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
                print(
                    "WARNING: Previous loop's mutex was abandoned. Taking over.",
                    file=sys.stderr,
                )
            else:
                # Try one more time: close all handles and re-create
                import time
                time.sleep(0.5)
                _mutex_handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
                err2 = kernel32.GetLastError()
                if err2 == ERROR_ALREADY_EXISTS:
                    print(
                        "Another Blofin loop is already running.\n"
                        "Close the other PowerShell window (Ctrl+C) or re-run the Desktop launcher.",
                        file=sys.stderr,
                    )
                    raise SystemExit(1)
                else:
                    print(
                        "WARNING: Force-acquired abandoned mutex. Taking over.",
                        file=sys.stderr,
                    )

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    owner_shell = _read_shell_lock_pid()
    if _shell_pid and owner_shell and owner_shell != _shell_pid:
        if _pid_running(owner_shell):
            print(
                f"This loop belongs to PowerShell PID {owner_shell}, not {_shell_pid}.\n"
                "Start Blofin AutoHedge from the owning window only.",
                file=sys.stderr,
            )
            raise SystemExit(1)
    if LOCK_PATH.is_file():
        try:
            other = int(LOCK_PATH.read_text(encoding="utf-8").strip())
        except (TypeError, ValueError):
            other = 0
        if other and other != pid and _pid_running(other):
            print(
                f"Another Blofin loop is already running (PID {other}).\n"
                f"Stop it first (Ctrl+C in that window) or re-run the Desktop launcher.",
                file=sys.stderr,
            )
            raise SystemExit(1)
    LOCK_PATH.write_text(str(pid), encoding="utf-8")
    if _shell_pid and not owner_shell:
        SHELL_LOCK_PATH.write_text(str(_shell_pid), encoding="utf-8")


def _release_singleton_lock() -> None:
    global _mutex_handle
    if not LOCK_PATH.is_file():
        pass
    else:
        try:
            if int(LOCK_PATH.read_text(encoding="utf-8").strip()) == os.getpid():
                LOCK_PATH.unlink(missing_ok=True)
        except (TypeError, ValueError, OSError):
            pass
    if sys.platform == "win32" and _mutex_handle:
        import ctypes

        ctypes.windll.kernel32.CloseHandle(_mutex_handle)
        _mutex_handle = None

if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from autohedge import AutoHedge  # noqa: E402
from autohedge.env_loader import load_env, require_llm_key  # noqa: E402
from autohedge.workers import reset_agent_memories  # noqa: E402

DEFAULT_PROMPT = (
    "Scan every tradable Blofin USDT perpetual. Call blofin_rank_opportunities to shortlist, "
    "then blofin_technical_analysis on the top candidate. "
    "Use blofin_get_trade_insights — favor winners, avoid repeat losers. "
    "Portfolio-Manager: assess portfolio, ensure all open positions have TP/SL. "
    "Do NOT add to held symbols — pick a NEW setup or skip. "
    "Sentiment: funding + news on the candidate. Quant: confirm edge. Risk: size + SL/TP prices. "
    "Execution: one minimum-size market entry with TP/SL, verify pending orders."
)


def _stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoHedge loop runner")
    parser.add_argument("-p", "--prompt", default=DEFAULT_PROMPT)
    parser.add_argument(
        "--sleep",
        type=int,
        default=30,
        help="Seconds to sleep between cycles (default: 30)",
    )
    parser.add_argument(
        "--no-all-assets",
        action="store_true",
        help="Do not inject universe scan into the task.",
    )
    parser.add_argument(
        "--log-file",
        default="outputs/live-run.log",
        help="Append cycle output to this log file",
    )
    parser.add_argument(
        "--shell-pid",
        type=int,
        default=0,
        help="Owning PowerShell PID (set by launcher)",
    )
    args = parser.parse_args()

    global _shell_pid
    _shell_pid = max(0, int(args.shell_pid or 0))

    log_path = ROOT / args.log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(
        str(log_path),
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
        encoding="utf-8",
        enqueue=True,
    )

    def _log(msg: str) -> None:
        print(msg, flush=True)
        try:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(msg + "\n")
        except OSError:
            pass

    load_env()
    if not require_llm_key():
        print("Set OPENROUTER_API_KEY or add key file in OneDrive/Documents.")
        return 1

    _acquire_singleton_lock()
    cycle = 0
    start_msg = f"[{_stamp()}] Blofin AutoHedge loop started (sleep={args.sleep}s) pid={os.getpid()}"
    print(start_msg, flush=True)
    print("Press Ctrl+C to stop.\n", flush=True)
    _log(start_msg)

    while True:
        cycle += 1
        reset_agent_memories()
        header = f"\n{'=' * 60}\n[{_stamp()}] CYCLE {cycle} starting\n{'=' * 60}\n"
        print(header, end="", flush=True)
        _log(header.strip())

        try:
            system = AutoHedge(name="blofin-autohedge")
            result = system.run(
                task=args.prompt,
                review_all_assets=not args.no_all_assets,
            )
            done = f"\n[{_stamp()}] CYCLE {cycle} finished."
            print(done, flush=True)
            _log(done)
            if result:
                text = str(result)
                snippet = text[:2000] + ("..." if len(text) > 2000 else "")
                print(snippet, flush=True)
                _log(snippet)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            err = f"\n[{_stamp()}] CYCLE {cycle} error: {exc}"
            print(err, flush=True)
            _log(err)

        sleep_msg = f"\n[{_stamp()}] Sleeping for {args.sleep} seconds..."
        print(sleep_msg, flush=True)
        _log(sleep_msg.rstrip())
        try:
            time.sleep(args.sleep)
        except KeyboardInterrupt:
            print(f"\n[{_stamp()}] Stopped by user.")
            return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
        raise SystemExit(0)
    finally:
        _release_singleton_lock()
