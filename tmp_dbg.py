import json, subprocess, tempfile, os
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
CWD = r"C:\Users\mknig\owl-swarm"
INST = "DRIFT-USDT"
def bridge(method, args):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    f.write(json.dumps(args)); f.close()
    out = subprocess.check_output([PY, "blofin_bridge.py", method, "@" + f.name], cwd=CWD)
    os.unlink(f.name); return json.loads(out)
def parse(raw):
    rows = list(reversed(raw))
    return [float(x[4]) for x in rows]
def ema(vals, n):
    if len(vals) < n: return vals[-1]
    k = 2/(n+1); e = sum(vals[:n])/n
    for v in vals[n:]: e = v*k + e*(1-k)
    return e
def trend_score(closes):
    e9, e21, price = ema(closes,9), ema(closes,21), closes[-1]
    if e9>e21 and price>e21: return 0.75, "bullish"
    if e9<e21 and price<e21: return 0.25, "bearish"
    if e9>e21: return 0.6, "bullish"
    if e9<e21: return 0.4, "bearish"
    return 0.5, "neutral"
c1m=parse(bridge("get_candles", {"inst_id":INST,"bar":"1m","limit":"50"}))
c15=parse(bridge("get_candles", {"inst_id":INST,"bar":"15m","limit":"30"}))
c1h=parse(bridge("get_candles", {"inst_id":INST,"bar":"1H","limit":"24"}))
for name,c in [("1m",c1m),("15m",c15),("1h",c1h)]:
    t,l=trend_score(c); print(name, l, t, "mom5", (c[-1]-c[-5])/c[-5]*100)
