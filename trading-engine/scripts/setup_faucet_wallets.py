#!/usr/bin/env python3
"""Generate real-mainnet collection wallets for faucet money."""

from __future__ import annotations

import argparse
import hashlib
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / "faucet_money" / "wallet_secrets.env"
sys.path.insert(0, str(ROOT))


def _ensure_bit():
    try:
        from bit import Key  # type: ignore

        return Key
    except ImportError:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "bit"])
        from bit import Key  # type: ignore

        return Key


def _ensure_eth():
    try:
        from eth_account import Account
    except ImportError:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "eth-account"])
        from eth_account import Account

    return Account


def _ltc_address(wif: str) -> str:
    """Derive LTC P2PKH from same WIF as BTC (separate network byte)."""
    try:
        import base58
        from ecdsa import SECP256k1, SigningKey
    except ImportError:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "ecdsa", "base58"])
        import base58
        from ecdsa import SECP256k1, SigningKey

    raw = base58.b58decode_check(wif)
    priv = raw[1:33]
    sk = SigningKey.from_string(priv, curve=SECP256k1)
    vk = sk.get_verifying_key()
    pub = b"\x04" + vk.to_string()
    h = hashlib.new("ripemd160", hashlib.sha256(pub).digest()).digest()
    payload = b"\x30" + h  # LTC mainnet P2PKH
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return base58.b58encode(payload + chk).decode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if SECRETS.is_file() and not args.force:
        from faucet_money.wallets import load_addresses, write_wallet_card

        w = load_addresses()
        write_wallet_card(w)
        print(f"Using existing {SECRETS}")
        for k, v in w.items():
            if v:
                print(f"  {k}: {v}")
        return 0

    Key = _ensure_bit()
    Account = _ensure_eth()

    btc_key = Key()
    btc_wif = btc_key.to_wif()
    btc_addr = btc_key.address

    # Separate DOGE key (different coin)
    doge_key = Key()
    doge_addr = doge_key.address
    doge_wif = doge_key.to_wif()

    ltc_addr = _ltc_address(btc_wif)

    acct = Account.create(secrets.token_hex(16))
    fp_user = f"mk{acct.address[-8:].lower()}"

    lines = [
        f"FAUCET_BTC_ADDRESS={btc_addr}",
        f"FAUCET_BTC_WIF={btc_wif}",
        f"FAUCET_LTC_ADDRESS={ltc_addr}",
        f"FAUCET_DOGE_ADDRESS={doge_addr}",
        f"FAUCET_DOGE_WIF={doge_wif}",
        f"FAUCET_EVM_ADDRESS={acct.address}",
        f"FAUCET_EVM_PRIVATE_KEY={acct.key.hex()}",
        f"FAUCET_PAY_USERNAME={fp_user}",
    ]
    SECRETS.parent.mkdir(parents=True, exist_ok=True)
    SECRETS.write_text("\n".join(lines) + "\n", encoding="utf-8")

    from faucet_money.wallets import load_addresses, merge_env, write_wallet_card

    merge_env(
        [
            "FAUCET_BTC_ADDRESS",
            "FAUCET_EVM_ADDRESS",
            "FAUCET_PAY_USERNAME",
        ]
    )
    w = load_addresses()
    write_wallet_card(w)
    print(wallet_card := __import__("faucet_money.wallets", fromlist=["wallet_card_text"]).wallet_card_text(w))
    print(f"\nSecrets saved: {SECRETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
