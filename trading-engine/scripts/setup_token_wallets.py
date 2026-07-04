#!/usr/bin/env python3
"""Generate token factory EVM wallet."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / "token_factory" / "wallet_secrets.env"
ENV = ROOT / ".env"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if SECRETS.is_file() and not args.force:
        print(f"Using existing {SECRETS}")
        return 0

    try:
        from eth_account import Account
    except ImportError:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "eth-account"])
        from eth_account import Account

    acct = Account.create(secrets.token_hex(16))
    lines = [
        f"TOKEN_FACTORY_EVM_PRIVATE_KEY={acct.key.hex()}",
        f"TOKEN_FACTORY_EVM_ADDRESS={acct.address}",
    ]
    SECRETS.parent.mkdir(parents=True, exist_ok=True)
    SECRETS.write_text("\n".join(lines) + "\n", encoding="utf-8")

    env_lines: list[str] = []
    if ENV.is_file():
        env_lines = ENV.read_text(encoding="utf-8").splitlines()
    keys = {l.split("=", 1)[0] for l in env_lines if "=" in l and not l.strip().startswith("#")}
    for line in lines:
        k = line.split("=", 1)[0]
        if k not in keys:
            env_lines.append(line)
    if "TOKEN_FACTORY_DRY_RUN=false" not in "\n".join(env_lines):
        env_lines.append("TOKEN_FACTORY_DRY_RUN=false")
    if "TOKEN_FACTORY_LIVE=true" not in "\n".join(env_lines):
        env_lines.append("TOKEN_FACTORY_LIVE=true")
    if "WHOLESALING_GMAIL_ROOT=" not in "\n".join(env_lines):
        guess = Path.home() / "matthew-knight-wholesaling"
        if guess.is_dir():
            env_lines.append(f"WHOLESALING_GMAIL_ROOT={guess}")
    ENV.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    print(f"Wallet: {acct.address}")
    print(f"Secrets: {SECRETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
