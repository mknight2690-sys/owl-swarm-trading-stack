"""Poll live-run.log for new errors and trade events."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "outputs" / "live-run.log"
START = int(sys.argv[1]) if len(sys.argv) > 1 else LOG.stat().st_size
INTERVAL = int(sys.argv[2]) if len(sys.argv) > 2 else 120
ROUNDS = int(sys.argv[3]) if len(sys.argv) > 3 else 6

ERR_RE = re.compile(r"ERROR|152002|103003|Traceback|CYCLE .* error", re.I)
HIT_KEYS = (
    "Set leverage",
    "Deterministic Risk approved",
    "103003",
    "evaluating candidates",
    "trying next candidate",
    "Execution completed",
    "CYCLE",
    "skip ",
)


def scan(offset: int) -> tuple[int, list[str], list[str]]:
    data = LOG.read_bytes()[offset:].decode("utf-8", errors="replace")
    lines = data.splitlines()
    errs = [l for l in lines if ERR_RE.search(l)]
    hits = [l for l in lines if any(k in l for k in HIT_KEYS)]
    return offset + len(data.encode("utf-8", errors="replace")), errs, hits


def main() -> None:
    offset = START
    print(f"watch_log_slice start offset={offset} rounds={ROUNDS} interval={INTERVAL}s")
    for i in range(1, ROUNDS + 1):
        time.sleep(INTERVAL)
        offset, errs, hits = scan(offset)
        print(f"\n=== check {i} === issues={len(errs)}")
        for line in errs[-8:]:
            print(line[:240])
        for line in hits[-12:]:
            print(line[:240])
    print("\nwatch complete")


if __name__ == "__main__":
    main()
