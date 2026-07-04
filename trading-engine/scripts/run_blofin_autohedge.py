#!/usr/bin/env python3
"""Run AutoHedge Director → Quant → Risk → Execution on all Blofin instruments."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autohedge import AutoHedge  # noqa: E402
from autohedge.env_loader import load_env, require_llm_key  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoHedge on Blofin")
    parser.add_argument(
        "-p",
        "--prompt",
        default=(
            "Review every live Blofin perpetual. For each instrument, produce a thesis, "
            "quant scores, risk sizing, and execute only high-conviction setups via Blofin."
        ),
    )
    parser.add_argument(
        "--no-all-assets",
        action="store_true",
        help="Do not inject the full instrument list (director picks symbols only).",
    )
    args = parser.parse_args()

    if not require_llm_key():
        print("Set OPENROUTER_API_KEY or add key file in OneDrive/Documents.")
        return 1

    system = AutoHedge(name="blofin-autohedge")
    result = system.run(task=args.prompt, review_all_assets=not args.no_all_assets)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
