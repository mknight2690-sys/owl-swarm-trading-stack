#!/usr/bin/env python3
"""Token launch tick — status + due flag for 1m Cursor loop."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATE_PATH = ROOT / "state" / "token_launch_tick.json"
FLAG_PATH = ROOT / ".cursor" / "TOKEN_LAUNCH_DUE"
LOG_PATH = ROOT / "logs" / "token_launch_agent.log"


def _log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")
    print(msg)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        secrets = ROOT / "token_factory" / "wallet_secrets.env"
        if secrets.is_file():
            load_dotenv(secrets)
    except Exception:
        pass


def main() -> int:
    _load_dotenv()
    now = time.time()
    row: dict = {"ts": now, "ok": True, "agent_due": True}

    try:
        from token_factory.deploy import deployer_address, get_balance_wei
        from token_factory.outreach import bridge_status, write_notes
        from token_factory.portfolio import load_portfolio
        from token_factory.tokenomics import generate_project

        portfolio = load_portfolio()
        dry_run = os.getenv("TOKEN_FACTORY_DRY_RUN", "false").lower() in {"1", "true", "yes"}
        live = os.getenv("TOKEN_FACTORY_LIVE", "true").lower() in {"1", "true", "yes"}
        chain = os.getenv("TOKEN_FACTORY_LAUNCH_CHAIN", "base_sepolia")

        actions = ["python scripts/token_launch_execute.py"]
        if not addr:
            actions.insert(0, "python scripts/setup_token_wallets.py")
        if balances.get("base_sepolia", 0) < 0.00005 and live and not dry_run:
            actions.append("auto_fund_base_sepolia")
        if portfolio.live_count() == 0:
            actions.append("deploy_first_token_live")
        if portfolio.candidates_for_promotion():
            actions.append("promote_testnet_to_base")

        addr = None
        balances: dict[str, float] = {}
        try:
            addr = deployer_address()
            for c in ("base_sepolia", "base"):
                balances[c] = round(get_balance_wei(c, addr) / 1e18, 8)
        except Exception as exc:
            balances["error"] = str(exc)[:120]

        gmail = bridge_status()
        notes = write_notes()
        sample = generate_project(seed=f"tick-{int(now)}")

        zal = {}
        if addr:
            from token_factory.zalalena import claim_hint, is_due

            zal = claim_hint(addr)
            if is_due():
                actions.insert(0, "claim_zalalena_faucet_browser")
        row["zalalena"] = zal

        row.update(
            {
                "live_mode": live and not dry_run,
                "dry_run": dry_run,
                "launch_chain": chain,
                "deployer": addr,
                "balances_eth": balances,
                "portfolio": portfolio.summary(),
                "promotion_queue": [t.id for t in portfolio.candidates_for_promotion()],
                "gmail_bridge": gmail,
                "outreach_notes": notes,
                "next_project": {"name": sample.name, "symbol": sample.symbol},
                "actions": actions,
            }
        )
        row["summary"] = (
            f"live={row['live_mode']} tokens={portfolio.summary()['total']} "
            f"gmail={'oauth' if gmail.get('oauth_ready') else 'none'} "
            f"bal_sepolia={balances.get('base_sepolia', 0)} "
            f"zalalena_due={zal.get('due') if addr else 'n/a'}"
        )
    except Exception as exc:
        row["ok"] = False
        row["error"] = str(exc)[:400]
        row["actions"] = ["python scripts/setup_token_wallets.py", "python scripts/token_launch_execute.py"]

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(row, indent=2), encoding="utf-8")

    if row.get("agent_due"):
        FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        FLAG_PATH.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")

    _log(row.get("summary", str(row.get("error", "tick"))))
    print(json.dumps(row, indent=2))
    return 0 if row.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
