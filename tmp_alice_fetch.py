import json, subprocess
from pathlib import Path
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
ROOT = Path(r"C:\Users\mknig\owl-swarm")
INST = "ALICE-USDT"
def bridge(method, args):
    args_file = ROOT / "tmp_alice_live_args.json"
    args_file.write_text(json.dumps(args), encoding="utf-8")
    proc = subprocess.run([PY, str(ROOT / "blofin_bridge.py"), method, f"@{args_file}"], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        print("ERR", method, proc.stderr or proc.stdout)
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout.strip())
ob = bridge("get_order_book", {"inst_id": INST})
fund = bridge("get_funding_rate", {"inst_id": INST})
ticker = bridge("get_ticker", {"inst_id": INST})
c1m = bridge("get_candles", {"inst_id": INST, "bar": "1m", "limit": 50})
c15 = bridge("get_candles", {"inst_id": INST, "bar": "15m", "limit": 30})
c1h = bridge("get_candles", {"inst_id": INST, "bar": "1h", "limit": 24})
print(json.dumps({"ob": ob, "fund": fund, "ticker": ticker, "c1m_len": len(c1m), "c15_len": len(c15), "c1h_len": len(c1h), "c1m_last3": c1m[:3], "c1h_last3": c1h[:3]}, indent=2))
