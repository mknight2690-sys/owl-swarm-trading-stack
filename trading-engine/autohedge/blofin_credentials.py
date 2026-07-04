"""Load Blofin API credentials from the user's Documents file only."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CREDENTIALS_PATH = Path(
    os.environ.get(
        "BLOFIN_CREDENTIALS_PATH",
        Path.home() / "OneDrive" / "Documents" / "1B Blofin API.txt",
    )
)


@dataclass(frozen=True)
class BlofinCredentials:
    api_key: str
    secret_key: str
    passphrase: str


def _parse_credentials_text(text: str) -> BlofinCredentials:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().lower().replace(" ", "_")] = value.strip()

    api_key = fields.get("api_key") or fields.get("apikey")
    secret_key = fields.get("secret_key") or fields.get("secretkey")
    passphrase = fields.get("passphrase")
    if not api_key or not secret_key or not passphrase:
        raise ValueError(
            "Credentials file must contain Passphrase, API Key, and Secret Key"
        )
    return BlofinCredentials(
        api_key=api_key, secret_key=secret_key, passphrase=passphrase
    )


def load_blofin_credentials(path: Path | None = None) -> BlofinCredentials:
    cred_path = Path(path) if path else DEFAULT_CREDENTIALS_PATH
    if not cred_path.is_file():
        raise FileNotFoundError(f"Blofin credentials not found: {cred_path}")
    return _parse_credentials_text(cred_path.read_text(encoding="utf-8"))
