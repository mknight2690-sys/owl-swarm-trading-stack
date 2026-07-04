#!/usr/bin/env python3
"""Import 1000+ real-mainnet FaucetPay faucets into repeat-claim pool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-health", type=int, default=20)
    parser.add_argument("--require-activity", action="store_true", help="Only faucets with balance or paid_today")
    parser.add_argument("--max", type=int, default=0, help="Cap import count (0=all)")
    args = parser.parse_args()

    from faucet_money.faucetpay_import import import_registry

    report = import_registry(
        min_health=args.min_health,
        require_activity=args.require_activity,
        max_count=args.max,
    )
    print(
        f"Imported {report['count']} real-mainnet faucets "
        f"(health>={args.min_health}, assets={len(report['assets'])})"
    )
    print(json.dumps({k: report[k] for k in ("count", "assets", "min_health", "require_activity")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
