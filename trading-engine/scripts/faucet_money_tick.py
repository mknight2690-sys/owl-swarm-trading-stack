#!/usr/bin/env python3
"""Assess real-mainnet faucet money — due claims, balances, actions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "state" / "faucet_money" / "tick.json"


def main() -> int:
    from faucet_money.catalog import catalog_summary as curated_summary
    from faucet_money.claims import count_due, due_faucets, is_registered, priority_actions
    from faucet_money.faucetpay_import import ensure_registry
    from faucet_money.registry import catalog_summary
    from faucet_money.verify import verify_all_wallets
    from faucet_money.wallets import load_addresses, wallet_card_text

    ensure_registry()

    wallets = load_addresses()
    if not wallets.get("btc"):
        report = {
            "ok": False,
            "needs_wallets": True,
            "actions": ["python scripts/setup_faucet_wallets.py"],
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    verification = verify_all_wallets(wallets)
    due = due_faucets(limit=30)
    due_total = count_due()
    actions = priority_actions(wallets, batch=25)
    cat = catalog_summary()

    report = {
        "ok": True,
        "real_money": {
            "confirmed_mainnet_usd": verification["real_money_total_usd"],
            "on_chain": verification["chains"],
            "prices_usd": verification["prices_usd"],
            "note": "Only mainnet explorer balances count as real money",
        },
        "catalog": cat,
        "wallets": {k: v for k, v in wallets.items() if k != "faucetpay_user" or v},
        "faucetpay_registered": is_registered("faucetpay"),
        "due_count": due_total,
        "due_faucets_sample": due[:30],
        "enabled_faucets": cat["real_mainnet_count"],
        "repeat_claim_pool": cat["faucetpay_imported_count"],
        "actions": actions[:25],
        "wallet_card": wallet_card_text(wallets),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        f"REAL MAINNET ${verification['real_money_total_usd']:.4f} | "
        f"pool={cat['real_mainnet_count']} (imported {cat['faucetpay_imported_count']}) | "
        f"due={due_total} | actions={len(actions)}"
    )
    for a in actions[:8]:
        print(f"  -> {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
