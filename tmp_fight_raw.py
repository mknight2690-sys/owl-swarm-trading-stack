import json, subprocess
from pathlib import Path
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
ROOT = Path(r"C:\Users\mknig\owl-swarm")
def bridge(method, args):
    args_file = ROOT / "tmp_bridge_call.json"
    args_file.write_text(json.dumps(args), encoding="utf-8")
    proc = subprocess.run([PY, str(ROOT / "blofin_bridge.py"), method, f"@{args_file}"], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0: raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout.strip())

inst = "FIGHT-USDT"
for m,a in [("get_ticker",{"inst_id":inst}),("get_funding_rate",{"inst_id":inst}),("get_order_book",{"inst_id":inst})]:
    print("===", m, "===")
    print(json.dumps(bridge(m,a), indent=2)[:2000])
for bar, lim in [("1m",50),("15m",30),("1h",24)]:
    c = bridge("get_candles", {"inst_id": inst, "bar": bar, "limit": lim})
    print(f"=== candles {bar} count={len(c)} first3={c[:3]} last3={c[-3:]} ===")
