#!/usr/bin/env python3
"""Autonomous live token launch cycle — fund, deploy, outreach. Never wait on user."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

JOURNAL = ROOT / "state" / "token_factory" / "business_journal.jsonl"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        secrets = ROOT / "token_factory" / "wallet_secrets.env"
        if secrets.is_file():
            load_dotenv(secrets)
    except Exception:
        pass


def _log(action: str, detail: dict) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": time.time(), "action": action, **detail}
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def run_cycle() -> dict:
    _load_dotenv()
    from token_factory.chains import get_chain
    from token_factory.deploy import deploy_erc20, deployer_address, get_balance_wei
    from token_factory.faucet import ensure_gas
    from token_factory.outreach import (
        bridge_status,
        build_launch_email,
        send_gmail,
        write_notes,
    )
    from token_factory.portfolio import LaunchedToken, load_portfolio
    from token_factory.promote import promote_token
    from token_factory.tokenomics import generate_project

    dry_run = os.getenv("TOKEN_FACTORY_DRY_RUN", "false").lower() in {"1", "true", "yes"}
    live = os.getenv("TOKEN_FACTORY_LIVE", "true").lower() in {"1", "true", "yes"}
    max_live = int(os.getenv("TOKEN_FACTORY_MAX_LIVE", "5"))
    chain_id = os.getenv("TOKEN_FACTORY_LAUNCH_CHAIN", "base_sepolia")

    report: dict = {
        "ts": time.time(),
        "live_mode": live and not dry_run,
        "dry_run": dry_run,
        "steps": [],
    }

    # Ensure wallet exists
    secrets = ROOT / "token_factory" / "wallet_secrets.env"
    if not secrets.is_file():
        import subprocess

        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "setup_token_wallets.py")])
        _load_dotenv()

    from token_factory.zalalena import claim_hint, is_due

    addr = deployer_address()
    report["deployer"] = addr
    report["zalalena"] = claim_hint(addr)
    if is_due():
        report["steps"].append({"zalalena_due": report["zalalena"]})
    write_notes()
    report["gmail"] = bridge_status()

    portfolio = load_portfolio()
    report["portfolio"] = portfolio.summary()

    # Promote eligible testnet tokens to Base mainnet when gas allows
    for t in portfolio.candidates_for_promotion():
        if dry_run:
            report["steps"].append({"promote": t.id, "dry_run": True})
            continue
        base_bal = get_balance_wei("base", addr)
        if base_bal >= 50_000_000_000_000:
            try:
                pr = promote_token(portfolio, t.id, dry_run=False)
                report["steps"].append({"promote": pr})
                _log("promote", pr)
            except Exception as exc:
                report["steps"].append({"promote_error": str(exc)[:200]})
        else:
            report["steps"].append({"promote_skipped": t.id, "reason": "no_base_gas"})

    portfolio = load_portfolio()
    if portfolio.live_count() >= max_live:
        report["steps"].append({"action": "portfolio_full", "max": max_live})
        return report

    # Fund testnet gas autonomously
    if not dry_run and live:
        gas = ensure_gas(addr, chain_id)
        report["steps"].append({"fund_gas": gas})
        _log("fund_gas", gas)
        if not gas.get("funded"):
            report["blocked"] = "awaiting_faucet_confirmation"
            return report

    # Deploy new token
    plan = generate_project(seed=f"live-{int(time.time())}")
    if dry_run or not live:
        deploy_result = deploy_erc20(plan.name, plan.symbol, plan.total_supply, chain_id, dry_run=True)
    else:
        deploy_result = deploy_erc20(plan.name, plan.symbol, plan.total_supply, chain_id, dry_run=False)
        chain = get_chain(chain_id)
        token = LaunchedToken(
            id=str(uuid.uuid4())[:12],
            name=plan.name,
            symbol=plan.symbol,
            chain=chain_id,
            contract_address=deploy_result["contract_address"],
            deployer=deploy_result["deployer"],
            tx_hash=deploy_result["tx_hash"],
            total_supply=plan.total_supply,
            tier=chain.tier,
            status="testnet" if chain.tier == "testnet" else "live",
            tokenomics=plan.to_dict(),
            launched_ts=deploy_result["launched_ts"],
            explorer_url=deploy_result["explorer_url"],
            promote_to=chain.promote_to,
        )
        portfolio.add(token)
        _log("deploy", deploy_result)

    report["steps"].append({"deploy": deploy_result})

    # Live outreach — notify owner inbox (proof of live pipeline)
    if not dry_run and live and deploy_result.get("contract_address"):
        to = os.getenv("TOKEN_FACTORY_OUTREACH_TO", "mknight2690@gmail.com")
        subj, body = build_launch_email(
            plan.name,
            plan.symbol,
            plan.tagline,
            deploy_result.get("explorer_url", ""),
            plan.narrative,
        )
        mail = send_gmail(to, subj, body)
        report["steps"].append({"outreach": mail})
        _log("outreach", mail)

    report["portfolio"] = load_portfolio().summary()
    return report


def main() -> int:
    report = run_cycle()
    print(json.dumps(report, indent=2))
    return 0 if not report.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
