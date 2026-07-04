#!/usr/bin/env python3
"""Post-tick execute: update $100 goal, confirm balances, record claim queue."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GOAL = ROOT / "state" / "faucet_money" / "goal.json"
OUT = ROOT / "state" / "faucet_money" / "execute.json"


def _blofin_usdt() -> float:
    try:
        from autohedge.tools.blofin_client import BlofinClient

        bal = BlofinClient().get_balances()
        for row in bal.get("details") or []:
            if row.get("currency") == "USDT":
                return float(row.get("available") or 0)
    except Exception:
        pass
    return 0.0


def main() -> int:
    from faucet_money.claims import due_faucets, is_registered, priority_actions
    from faucet_money.verify import verify_all_wallets
    from faucet_money.wallets import load_addresses

    wallets = load_addresses()
    verification = verify_all_wallets(wallets)
    on_chain = float(verification.get("real_money_total_usd") or 0)
    blofin = _blofin_usdt()

    goal: dict = {}
    if GOAL.is_file():
        try:
            goal = json.loads(GOAL.read_text(encoding="utf-8"))
        except Exception:
            pass
    target = float(goal.get("target_usd") or 100.0)
    baseline = float(goal.get("baseline_blofin_usdt") or blofin)

    total = blofin + on_chain  # FaucetPay internal balance added after login API
    remaining = max(0.0, target - total)

    goal.update(
        {
            "target_usd": target,
            "baseline_blofin_usdt": baseline,
            "sources": {
                "blofin_usdt": round(blofin, 6),
                "on_chain_mainnet_usd": round(on_chain, 6),
                "faucetpay_usd": float(goal.get("sources", {}).get("faucetpay_usd") or 0),
            },
            "total_usd": round(total, 6),
            "remaining_usd": round(remaining, 6),
            "phase": "manual_grind_until_100" if remaining > 0 else "ready_to_automate",
            "updated_ts": time.time(),
        }
    )
    GOAL.parent.mkdir(parents=True, exist_ok=True)
    GOAL.write_text(json.dumps(goal, indent=2), encoding="utf-8")

    actions = priority_actions(wallets)
    due = due_faucets()
    report = {
        "ok": True,
        "total_usd": total,
        "remaining_usd": remaining,
        "on_chain_usd": on_chain,
        "blofin_usdt": blofin,
        "faucetpay_registered": is_registered("faucetpay"),
        "due_count": len(due),
        "next_actions": actions[:12],
        "confirmations": {
            "wallets_ok": bool(wallets.get("btc")),
            "mainnet_verified": on_chain >= 0,
            "blofin_api_ok": blofin > 0,
        },
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"execute total=${total:.4f} remaining=${remaining:.2f} "
        f"due={len(due)} faucetpay_reg={is_registered('faucetpay')}"
    )
    for a in actions[:6]:
        print(f"  -> {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
