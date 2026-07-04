#!/usr/bin/env python3
"""Verify all AutoHedge agents work with the configured free cloud model."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Windows console: avoid charmap crashes on Rich/Unicode agent output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import autohedge.swarms_bootstrap  # noqa: F401
from autohedge.env_loader import load_env, require_llm_key  # noqa: E402
from autohedge.model_config import agent_model_name  # noqa: E402
from autohedge.workers import (  # noqa: E402
    director_agent,
    execution_agent,
    quant_agent,
    risk_agent,
    sentiment_agent,
)


def _ok(name: str, output: object) -> None:
    text = str(output)
    if not text.strip():
        raise RuntimeError(f"{name} returned empty output")
    print(f"OK {name}: {text[:400].replace(chr(10), ' ')}...")


def main() -> int:
    load_env()
    model = agent_model_name()
    if not require_llm_key():
        print("Missing OPENROUTER_API_KEY")
        return 1

    print(f"Model: {model}")

    _ok(
        "quant_agent",
        quant_agent.run(
            "Stock: BTC-USDT\nThesis: Bullish momentum on Blofin perps. "
            "Call blofin_get_ticker for BTC-USDT and produce quant scores."
        ),
    )

    _ok(
        "risk_agent",
        risk_agent.run(
            "Stock: BTC-USDT\nThesis: Bullish\nQuant Analysis: technical_score 0.7"
        ),
    )

    _ok(
        "sentiment_agent",
        sentiment_agent.run(
            "Stock: BTC-USDT\nSummarize market sentiment using blofin_get_ticker."
        ),
    )

    # Execution: dry run only — describe order, do not place unless explicitly told
    _ok(
        "execution_agent",
        execution_agent.run(
            "Stock: BTC-USDT\nThesis: Bullish\nRisk Assessment: small size only. "
            "DO NOT place any order. Only output the order JSON you would send."
        ),
    )

    _ok(
        "director_agent",
        director_agent.run(
            "Review BTC-USDT on Blofin only. Use blofin_get_ticker and blofin_get_account_balances. "
            "One paragraph thesis. Do not trade."
        ),
    )

    print("\nSUCCESS: All 5 agents responded using the free cloud model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
