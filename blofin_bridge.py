"""
Blofin Python Bridge — called from TypeScript via child process.
Usage: python blofin_bridge.py <method> [json_args_or_@filepath]
If json_args starts with @, reads from that file path.
"""

import json
import sys
from pathlib import Path

AUTO_TRADER_DIR = Path(r"C:\Users\mknig\blofin-auto-trader")
sys.path.insert(0, str(AUTO_TRADER_DIR))

from autohedge.tools.blofin_client import BlofinClient  # noqa: E402
from autohedge.blofin_credentials import load_blofin_credentials  # noqa: E402


def load_args(raw: str) -> dict:
    if raw.startswith("@"):
        return json.loads(Path(raw[1:]).read_text(encoding="utf-8"))
    return json.loads(raw)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No method specified"}))
        sys.exit(1)

    method = sys.argv[1]
    args = load_args(sys.argv[2]) if len(sys.argv) > 2 else {}

    try:
        creds = load_blofin_credentials()
        client = BlofinClient(creds)
        result = None

        if method == "get_tickers":
            inst_id = args.get("inst_id")
            result = client.get_tickers(inst_id)

        elif method == "get_ticker":
            result = client.get_tickers(args["inst_id"])

        elif method == "get_instruments":
            inst_type = args.get("inst_type", "SWAP")
            result = client.get_instruments(inst_type)

        elif method == "get_instrument":
            result = client.get_instrument(args["inst_id"])

        elif method == "get_candles":
            result = client.get_candles(
                args["inst_id"],
                bar=args.get("bar", "1m"),
                limit=int(args.get("limit", 100)),
            )

        elif method == "get_balances":
            result = client.get_balances()

        elif method == "get_positions":
            inst_id = args.get("inst_id")
            result = client.get_positions(inst_id)

        elif method == "get_pending_tpsl":
            inst_id = args.get("inst_id")
            result = client.get_pending_tpsl(inst_id)

        elif method == "get_funding_rate":
            result = client.get_funding_rate(args["inst_id"])

        elif method == "get_all_funding_rates":
            result = client.get_all_funding_rates()

        elif method == "get_order_book":
            result = client.get_order_book(args["inst_id"], size=args.get("size", "20"))

        elif method == "set_leverage":
            result = client.set_leverage(
                args["inst_id"],
                int(args.get("leverage", 10)),
                margin_mode=args.get("margin_mode", "isolated"),
            )

        elif method == "place_order":
            result = client.place_order(
                inst_id=args["inst_id"],
                side=args["side"],
                order_type=args.get("order_type", "market"),
                size=args["size"],
                tp_trigger_price=args.get("tp_trigger_price", ""),
                sl_trigger_price=args.get("sl_trigger_price", ""),
                margin_mode=args.get("margin_mode", "isolated"),
            )

        elif method == "place_tpsl":
            result = client.place_tpsl(
                inst_id=args["inst_id"],
                side=args["side"],
                size=args.get("size", "-1"),
                tp_trigger_price=args.get("tp_trigger_price", ""),
                sl_trigger_price=args.get("sl_trigger_price", ""),
            )

        elif method == "close_position":
            result = client.close_position(
                inst_id=args["inst_id"],
                margin_mode=args.get("margin_mode", "isolated"),
            )

        elif method == "cancel_order":
            result = client.cancel_order(args["order_id"], args.get("inst_id"))

        else:
            print(json.dumps({"error": f"Unknown method: {method}"}))
            sys.exit(1)

        print(json.dumps(result, default=str))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
