import json
import subprocess
import sys

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
CWD = r"C:\Users\mknig\owl-swarm"

def fetch(method, args):
    p = subprocess.run([PY, BRIDGE, method, json.dumps(args)], cwd=CWD, capture_output=True, text=True)
    return json.loads(p.stdout.strip())

def rsi(closes, period=14):
    closes = list(reversed(closes))
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))

def trend_score(closes):
    if len(closes) < 5:
        return 0
    recent = list(reversed(closes))[-10:]
    up = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i-1])
    return up / (len(recent) - 1)

funding = fetch("get_funding_rate", {"inst_id": "UB-USDT"})
book = fetch("get_order_book", {"inst_id": "UB-USDT"})
c1m = fetch("get_candles", {"inst_id": "UB-USDT", "bar": "1m", "limit": "50"})
c15 = fetch("get_candles", {"inst_id": "UB-USDT", "bar": "15m", "limit": "30"})
c1h = fetch("get_candles", {"inst_id": "UB-USDT", "bar": "1H", "limit": "24"})

def parse(candles):
    return {
        "closes": [float(c[4]) for c in candles],
        "highs": [float(c[2]) for c in candles],
        "lows": [float(c[3]) for c in candles],
    }

d1m, d15, d1h = parse(c1m), parse(c15), parse(c1h)
ask = float(book["asks"][0][0])
bid = float(book["bids"][0][0])
mid = (ask + bid) / 2
spread_pct = (ask - bid) / mid * 100
fr = float(funding["fundingRate"])

rsi1m = rsi(d1m["closes"])
rsi15 = rsi(d15["closes"])
t1m = trend_score(d1m["closes"])
t15 = trend_score(d15["closes"])
t1h = trend_score(d1h["closes"])

support = min(d1h["lows"][:6] + d15["lows"][:4])
resistance = max(d1h["highs"][:3] + d15["highs"][:2])
pivot = (support + resistance + d1m["closes"][0]) / 3

print(json.dumps({
    "price": d1m["closes"][0],
    "fundingRate": fr,
    "spreadPct": spread_pct,
    "rsi1m": rsi1m,
    "rsi15": rsi15,
    "t1m": t1m,
    "t15": t15,
    "t1h": t1h,
    "support": support,
    "resistance": resistance,
    "pivot": pivot,
    "change1h": (d1h["closes"][0] - d1h["closes"][1]) / d1h["closes"][1] * 100,
    "change15m_last": (d15["closes"][0] - d15["closes"][1]) / d15["closes"][1] * 100,
}, indent=2))
