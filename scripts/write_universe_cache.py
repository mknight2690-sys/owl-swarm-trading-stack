#!/usr/bin/env python3
"""Refresh universe via curl_cffi REST and write ws-tickers.json for feed consumers."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTO = Path(r"C:\Users\mknig\blofin-auto-trader")
sys.path.insert(0, str(AUTO))

OUT = Path(
    os.environ.get(
        "OWL_WS_TICKERS_PATH",
        str(ROOT / "outputs" / "ws-tickers.json"),
    )
)


def main() -> int:
    from autohedge.tools.blofin_universe_feed import get_universe_feed

    feed = get_universe_feed()
    snap = feed.refresh(force=True)
    payload = {
        "updated_at": snap.updated_at,
        "source": snap.source,
        "count": snap.count,
        "tickers": snap.tickers,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, default=str), encoding="utf-8")
    print(f"OK {snap.count} {snap.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
