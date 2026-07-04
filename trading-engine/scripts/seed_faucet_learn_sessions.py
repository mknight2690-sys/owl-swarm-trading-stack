#!/usr/bin/env python3
"""Seed watched manual sessions from known FaucetPay registration flow (bootstrap learning)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAUCETPAY_REGISTER_STEPS = [
    {"action": "navigate", "url": "https://faucetpay.io/account/register", "note": "open signup"},
    {"action": "fill", "target": "USERNAME", "value": "mk554af435"},
    {"action": "click", "target": "Continue"},
    {"action": "fill", "target": "EMAIL ADDRESS", "value": "mk554af435@maildrop.cc"},
    {"action": "click", "target": "Continue"},
    {"action": "fill", "target": "PASSWORD", "value": "<account_password>"},
    {"action": "fill", "target": "PASSWORD (REPEAT)", "value": "<account_password>"},
    {"action": "click", "target": "Continue"},
    {"action": "click", "target": "Terms checkbox", "note": "accept terms"},
    {"action": "captcha_manual", "note": "Google reCAPTCHA I'm not a robot — must be solved manually"},
    {"action": "click", "target": "Sign up"},
    {"action": "confirm", "note": "land on dashboard or verification prompt"},
]

FAUCETPAY_USDT_CLAIM_STEPS = [
    {"action": "navigate", "url": "https://faucetpay.io/account/login"},
    {"action": "fill", "target": "email", "value": "mk554af435@maildrop.cc"},
    {"action": "click", "target": "Continue"},
    {"action": "fill", "target": "PASSWORD", "value": "<account_password>"},
    {"action": "click", "target": "Log in"},
    {"action": "navigate", "url": "https://faucetpay.io/bitcoin-faucet", "note": "or USDT faucet page"},
    {"action": "click", "target": "Claim", "note": "claim button on faucet page"},
    {"action": "captcha_manual", "note": "if captcha shown"},
    {"action": "confirm", "note": "balance increases in FaucetPay wallet"},
]


def _seed(faucet_id: str, steps: list[dict], *, tag: str) -> str:
    from faucet_money.learner import end_session, record_step, start_session

    s = start_session(faucet_id, operator=f"seed_{tag}")
    sid = s["id"]
    for st in steps:
        record_step(
            sid,
            action=st.get("action", "note"),
            target=st.get("target", ""),
            value=st.get("value", ""),
            url=st.get("url", ""),
            note=st.get("note", ""),
        )
    end_session(sid, success=True, notes=f"seeded from observed manual flow ({tag})")
    return sid


def main() -> int:
    a = _seed("faucetpay", FAUCETPAY_REGISTER_STEPS, tag="register_v1")
    b = _seed("faucetpay", FAUCETPAY_USDT_CLAIM_STEPS, tag="claim_v1")
    from faucet_money.learner import learn_playbook, load_playbook

    pb = learn_playbook("faucetpay")
    print(f"seed sessions: {a}, {b}")
    if pb:
        print(f"playbook faucetpay steps={len(pb['steps'])} captcha={pb['captcha_required']} trust={pb['trust_score']}")
    else:
        print("playbook not ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
