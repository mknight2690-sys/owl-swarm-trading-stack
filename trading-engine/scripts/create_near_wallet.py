#!/usr/bin/env python3
"""
Generate a fresh Near Protocol wallet (ed25519 keypair) and store it securely.
The public address is printed for you to add to invoices.
The private key is saved to state/baas/near_wallet.json (keep this file secret!).
"""

import json
import time
from pathlib import Path
from nacl import signing, encoding

ROOT = Path(r"C:\Users\mknig\blofin-auto-trader")
WALLET_PATH = ROOT / "state" / "baas" / "near_wallet.json"

def main() -> None:
    # Generate an ed25519 signing key (private) and its verify key (public)
    signing_key = signing.SigningKey.generate()
    verify_key = signing_key.verify_key

    private_hex = signing_key.encode(encoder=encoding.HexEncoder).decode()
    public_hex = verify_key.encode(encoder=encoding.HexEncoder).decode()

    # Near address format: "ed25519:<public_key>"
    near_address = f"ed25519:{public_hex}"

    wallet = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "address": near_address,
        "private_key": private_hex
    }

    WALLET_PATH.parent.mkdir(parents=True, exist_ok=True)
    WALLET_PATH.write_text(json.dumps(wallet, indent=2), encoding="utf-8")

    print(f"\n✅ Near wallet created.")
    print(f"📦 Public address (share this on invoices):\n{near_address}\n")
    print(f"🔐 Private key stored securely at:\n{WALLET_PATH}\n")

if __name__ == "__main__":
    main()