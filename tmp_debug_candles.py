import json, subprocess
from pathlib import Path
ROOT = Path(r"C:\Users\mknig\owl-swarm")
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"

def bridge(method, args):
    args_file = ROOT / "tmp_bridge_call.json"
    args_file.write_text(json.dumps(args), encoding="utf-8")
    proc = subprocess.run([PY, str(ROOT / "blofin_bridge.py"), method, f"@{args_file}"], cwd=ROOT, capture_output=True, text=True)
    return json.loads(proc.stdout.strip())

for bar, limit in [("1m", 50), ("15m", 30), ("1h", 24)]:
    c = bridge("get_candles", {"inst_id": "W-USDT", "bar": bar, "limit": limit})
    closes = [float(x[4]) for x in c]
    rev = [float(x[4]) for x in reversed(c)]
    print(bar, "first3", closes[:3], "last3", closes[-3:])
    print(bar, "rev first3", rev[:3], "rev last3", rev[-3:], "rev[-1]", rev[-1])
