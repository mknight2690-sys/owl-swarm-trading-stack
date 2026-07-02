import json, subprocess, tempfile, os
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
CWD = r"C:\Users\mknig\owl-swarm"
def bridge(method, args):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    f.write(json.dumps(args)); f.close()
    out = subprocess.check_output([PY, "blofin_bridge.py", method, "@" + f.name], cwd=CWD)
    os.unlink(f.name); return json.loads(out)
c15 = bridge("get_candles", {"inst_id": "W-USDT", "bar": "15m", "limit": "20"})
rows = list(reversed(c15))
for x in rows[-12:]:
    print(x[0], x[1], x[2], x[3], x[4], x[5])
