#!/usr/bin/env python3
"""Verify Blofin credentials and live order placement (place + cancel + market round-trip)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autohedge.tools.blofin_client import BlofinClient  # noqa: E402


def _instrument_specs(client: BlofinClient, inst_id: str) -> dict:
    data = client.request(
        "GET",
        "/api/v1/market/instruments",
        params={"instType": "SWAP"},
        private=False,
    )
    for row in data.get("data") or []:
        if row.get("instId") == inst_id:
            return row
    raise RuntimeError(f"Instrument not found: {inst_id}")


def _round_to_step(value: float, step: float) -> str:
    if step <= 0:
        return str(value)
    rounded = round(round(value / step) * step, 10)
    if step >= 1:
        return str(int(rounded))
    decimals = max(0, len(str(step).split(".")[-1].rstrip("0")))
    return f"{rounded:.{decimals}f}"


def main() -> int:
    client = BlofinClient()
    inst_id = "BTC-USDT"

    print("=== 1. Auth: futures balance ===")
    balances = client.get_balances()
    print(json.dumps(balances, indent=2)[:1500])

    print("\n=== 2. Position mode ===")
    print("mode:", client.ensure_net_position_mode())

    print("\n=== 3. All live instruments (via authenticated tickers) ===")
    tickers = client.get_tickers()
    print(f"count={len(tickers)}")

    btc = next((t for t in tickers if t.get("instId") == inst_id), None)
    if not btc:
        print(f"ERROR: {inst_id} not in ticker list")
        return 1
    specs = _instrument_specs(client, inst_id)
    last = float(btc.get("last") or 0)
    tick = float(specs.get("tickSize") or "0.1")
    min_size = str(specs.get("minSize") or specs.get("lotSize") or "0.1")
    safe_price = _round_to_step(max(tick, last * 0.5), tick)

    print(f"\n=== 4. Place post_only limit buy (size={min_size}, price={safe_price}) ===")
    placed = client.place_order(
        inst_id,
        "buy",
        "post_only",
        min_size,
        price=safe_price,
    )
    print(json.dumps(placed, indent=2))
    order_id = placed.get("orderId")
    if not order_id:
        print("ERROR: place_order returned no orderId")
        return 1

    time.sleep(1)
    print(f"\n=== 5. Cancel order {order_id} ===")
    cancelled = client.cancel_order(str(order_id), inst_id)
    print(json.dumps(cancelled, indent=2))

    time.sleep(1.5)
    print("\n=== 6. Market open (min size) ===")
    opened = client.place_order(inst_id, "buy", "market", min_size)
    print(json.dumps(opened, indent=2))
    if not opened.get("orderId"):
        print("ERROR: market open failed")
        return 1

    time.sleep(1.5)
    print("\n=== 7. Market close (reduceOnly) ===")
    closed = client.place_order(
        inst_id,
        "sell",
        "market",
        min_size,
        reduce_only="true",
    )
    print(json.dumps(closed, indent=2))
    if not closed.get("orderId"):
        print("ERROR: market close failed")
        return 1

    print("\nSUCCESS: Blofin authenticated, listed all assets, placed, cancelled, and executed market trades.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
