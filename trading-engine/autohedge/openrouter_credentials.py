"""Load OpenRouter API key from the user's Documents file."""

from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_OPENROUTER_KEY_PATH = Path(
    os.environ.get(
        "OPENROUTER_CREDENTIALS_PATH",
        Path.home()
        / "OneDrive"
        / "Documents"
        / "1BananaOnTheWall Openrouter API Key.txt",
    )
)


def load_openrouter_api_key(path: Path | None = None) -> str:
    key_path = Path(path) if path else DEFAULT_OPENROUTER_KEY_PATH
    if not key_path.is_file():
        raise FileNotFoundError(f"OpenRouter key file not found: {key_path}")
    for line in reversed(key_path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if line.startswith("sk-or-"):
            return line
    match = re.search(r"sk-or-[A-Za-z0-9_-]+", key_path.read_text(encoding="utf-8"))
    if match:
        return match.group(0)
    raise ValueError(f"No OpenRouter API key found in {key_path}")
