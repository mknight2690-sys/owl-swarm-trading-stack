import json, subprocess
from pathlib import Path
ROOT = Path(r"C:\Users\mknig\owl-swarm")
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"

def bridge(method, args):
    args_file = ROOT / "tmp_bridge_call.json"
    args_file.write_text(json.dumps(args), encoding="utf-8")
    proc = subprocess.run([PY, str(ROOT / "blofin_bridge.py"), method, f"@{args_file}"], cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr

for method, args in [
    ("get_ticker", {"inst_id": "W-USDT"}),
    ("get_funding_rate", {"inst_id": "W-USDT"}),
    ("get_order_book", {"inst_id": "W-USDT"}),
    ("get_candles", {"inst_id": "W-USDT", "bar": "1m", "limit": 3}),
]:
    rc, out, err = bridge(method, args)
    print("===", method, "rc", rc)
    print(out[:1200])
