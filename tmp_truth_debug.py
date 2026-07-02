import json, subprocess, tempfile, os
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
CWD = r"C:\Users\mknig\owl-swarm"
INST = "TRUTH-USDT"

def bridge(method, args):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(args, f)
    f.close()
    out = subprocess.check_output([PY, "blofin_bridge.py", method, "@" + f.name], cwd=CWD)
    os.unlink(f.name)
    return json.loads(out)

def parse(raw):
    rows = list(reversed(raw))
    return [{"c": float(x[4])} for x in rows]

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0))
        losses.append(max(-ch, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    return 100 - 100 / (1 + avg_gain / avg_loss)

def ema(vals, n):
    if len(vals) < n:
        return None
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for v in vals[n:]:
        e = v * k + e * (1 - k)
    return e

def trend_score(closes, price):
    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    if e9 is None or e21 is None:
        return 0.5
    if e9 > e21 and price > e21:
        return 0.75
    if e9 < e21 and price < e21:
        return 0.25
    if e9 > e21:
        return 0.6
    return 0.4

def mom_score(r):
    if r is None:
        return 0.5
    if r > 70:
        return 0.3
    if r > 55:
        return 0.65
    if r < 30:
        return 0.7
    if r < 45:
        return 0.35
    return 0.5

ticker = bridge("get_ticker", {"inst_id": INST})
if isinstance(ticker, list):
    ticker = ticker[0]
price = float(ticker["last"])
c1m = parse(bridge("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"}))
c15 = parse(bridge("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"}))
c1h = parse(bridge("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"}))
closes1m = [x["c"] for x in c1m]
closes15 = [x["c"] for x in c15]
closes1h = [x["c"] for x in c1h]
t1m = trend_score(closes1m, price)
t15 = trend_score(closes15, price)
t1h = trend_score(closes1h, price)
rsi1m = rsi(closes1m)
rsi15 = rsi(closes15)
rsi1h = rsi(closes1h)
m1m = mom_score(rsi1m)
m15 = mom_score(rsi15)
m1h = mom_score(rsi1h)
momentum = (m1m + m15 + m1h) / 3
avg_trend = (t1m + t15 + t1h) / 3
long_score = avg_trend * 0.4 + momentum * 0.35
long_score = long_score * 0.85 + 0.5 * 0.15
bull_count = sum(1 for t in [t1m, t15, t1h] if t >= 0.6)
bear_count = sum(1 for t in [t1m, t15, t1h] if t <= 0.4)
if bull_count >= 2 and bear_count == 0:
    long_score += 0.04
print(json.dumps({"t1m": t1m, "t15": t15, "t1h": t1h, "rsi1m": rsi1m, "rsi15": rsi15, "rsi1h": rsi1h, "momentum": momentum, "avg_trend": avg_trend, "long_score": long_score, "bull": bull_count, "bear": bear_count}))
