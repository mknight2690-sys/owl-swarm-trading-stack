#!/usr/bin/env python3
"""Claim Zalalena Base Sepolia faucet when turnstile token supplied."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Zalalena Base Sepolia faucet claim")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--token", help="Cloudflare Turnstile token from browser")
    parser.add_argument("--address", help="Override wallet address")
    args = parser.parse_args()

    from token_factory.deploy import deployer_address, get_balance_wei
    from token_factory.zalalena import claim, claim_hint, faucet_status, is_due

    addr = args.address or deployer_address()

    if args.status:
        bal = get_balance_wei("base_sepolia", addr) / 1e18
        out = {
            "address": addr,
            "balance_eth": round(bal, 8),
            "due": is_due(),
            "faucet": faucet_status(),
            "hint": claim_hint(addr),
        }
        print(json.dumps(out, indent=2))
        return 0

    if not args.token:
        print(json.dumps(claim_hint(addr), indent=2))
        print("\nPass --token <turnstile_token> after completing captcha in browser.", file=sys.stderr)
        return 2

    result = claim(addr, args.token)
    print(json.dumps(result, indent=2))
    if result.get("ok"):
        import time

        time.sleep(8)
        bal = get_balance_wei("base_sepolia", addr) / 1e18
        print(json.dumps({"balance_eth": round(bal, 8)}, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
