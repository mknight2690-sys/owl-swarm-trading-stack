#!/usr/bin/env python3
"""Record a confirmed manual claim or registration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--register", help="faucet id to mark registered")
    parser.add_argument("--claim", help="faucet id to mark claimed")
    parser.add_argument("--username", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--detail", default="")
    parser.add_argument("--failed", action="store_true")
    args = parser.parse_args()

    from faucet_money.claims import mark_registered, record_claim

    if args.register:
        mark_registered(args.register, username=args.username, email=args.email)
        print(f"registered {args.register}")
    if args.claim:
        record_claim(args.claim, ok=not args.failed, detail=args.detail or None)
        print(f"claim {args.claim} ok={not args.failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
