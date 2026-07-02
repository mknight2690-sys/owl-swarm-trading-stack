import json
import subprocess
import sys

def fetch(method, args):
    p = subprocess.run(
        [sys.executable, r"C:\Users\mknig\owl-swarm\blofin_bridge.py", method, json.dumps(args)],
        capture_output=True,
        text=True,
        cwd=r"C:\Users\mknig\owl-swarm",
    )
    if p.returncode != 0:
        raise RuntimeError(f"{method} failed: {p.stderr} {p.stdout}")
    return json.loads(p.stdout.strip())

inst = "NAORIS-USDT"
data = {
    "funding": fetch("get_funding_rate", {"inst_id": inst}),
    "book": fetch("get_order_book", {"inst_id": inst}),
    "c1m": fetch("get_candles", {"inst_id": inst, "bar": "1m", "limit": "50"}),
    "c15": fetch("get_candles", {"inst_id": inst, "bar": "15m", "limit": "30"}),
    "c1h": fetch("get_candles", {"inst_id": inst, "bar": "1H", "limit": "24"}),
    "ticker": fetch("get_ticker", {"inst_id": inst}),
}
print(json.dumps(data))
