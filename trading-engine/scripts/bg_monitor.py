"""Background monitor: watches live-run.log and prints trades/errors immediately."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "outputs" / "live-run.log"
START = int(sys.argv[1]) if len(sys.argv) > 1 else LOG.stat().st_size

ERR_RE = re.compile(r"ERROR|103003|Traceback|NameError|FileNotFoundError|NameResolutionError", re.I)
TRADE_RE = re.compile(r"Deterministic Execution completed")
APPROVED_RE = re.compile(r"Deterministic Risk approved")
VETO_RE = re.compile(r"Deterministic Risk veto")


def scan(offset: int) -> tuple[int, list[str], list[str], list[str], list[str]]:
    data = LOG.read_bytes()[offset:].decode("utf-8", errors="replace")
    lines = data.splitlines()
    errs = [l for l in lines if ERR_RE.search(l)]
    trades = [l for l in lines if TRADE_RE.search(l)]
    approved = [l for l in lines if APPROVED_RE.search(l)]
    vetos = [l for l in lines if VETO_RE.search(l)]
    return offset + len(data.encode("utf-8", errors="replace")), errs, trades, approved, vetos


def main() -> None:
    offset = START
    trade_count = 0
    print(f"[monitor] start offset={offset}", flush=True)
    while True:
        time.sleep(10)
        try:
            offset, errs, trades, approved, vetos = scan(offset)
        except Exception as exc:
            print(f"[monitor] scan error: {exc}", flush=True)
            continue
        for l in errs:
            print(f"[ERROR] {l[:200]}", flush=True)
        for l in approved:
            print(f"[APPROVED] {l[:200]}", flush=True)
        for l in vetos:
            print(f"[VETO] {l[:200]}", flush=True)
        for l in trades:
            trade_count += 1
            print(f"[TRADE #{trade_count}] {l[:200]}", flush=True)
        if trade_count >= 3:
            print(f"[monitor] SUCCESS: {trade_count} trades completed!", flush=True)
            break
    print("[monitor] exiting.", flush=True)


if __name__ == "__main__":
    main()
