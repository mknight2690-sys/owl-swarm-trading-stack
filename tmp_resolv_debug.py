import json
import subprocess
from pathlib import Path

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
ROOT = Path(r"C:\Users\mknig\owl-swarm")
INST = "RESOLV-USDT"

def bridge(method, args):
    args_file = ROOT / "tmp_bridge_call.json"
    args_file.write_text(json.dumps(args), encoding="utf-8")
    proc = subprocess.run(
        [PY, str(ROOT / "blofin_bridge.py"), method, f"@{args_file}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout.strip())

for name, method, args in [
    ("ticker", "get_ticker", {"inst_id": INST}),
    ("fund", "get_funding_rate", {"inst_id": INST}),
    ("ob", "get_order_book", {"inst_id": INST}),
    ("c1m", "get_candles", {"inst_id": INST, "bar": "1m", "limit": 50}),
    ("c15", "get_candles", {"inst_id": INST, "bar": "15m", "limit": 30}),
    ("c1h", "get_candles", {"inst_id": INST, "bar": "1h", "limit": 24}),
]:
    data = bridge(method, args)
    print(f"\n=== {name} ===")
    if name == "ob":
        print(json.dumps({"bid": data["bids"][0], "ask": data["asks"][0]}, indent=2))
    elif name.startswith("c"):
        print("first:", data[0])
        print("last:", data[-1])
        print("count:", len(data))
    else:
        print(json.dumps(data, indent=2)[:2000])
