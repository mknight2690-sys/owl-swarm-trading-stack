import json, subprocess, tempfile, os
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
CWD = r"C:\Users\mknig\owl-swarm"
INST = "ID-USDT"

def bridge(method, args):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    f.write(json.dumps(args))
    f.close()
    out = subprocess.check_output([PY, "blofin_bridge.py", method, "@" + f.name], cwd=CWD)
    os.unlink(f.name)
    return json.loads(out)

ticker = bridge("get_ticker", {"inst_id": INST})[0]
fund = bridge("get_funding_rate", {"inst_id": INST})
ob = bridge("get_order_book", {"inst_id": INST})
c15 = bridge("get_candles", {"inst_id": INST, "bar": "15m", "limit": "100"})
c1h = bridge("get_candles", {"inst_id": INST, "bar": "1H", "limit": "48"})

def parse(raw):
    rows = list(reversed(raw))
    return [{"ts": int(x[0]), "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])} for x in rows]

d15 = parse(c15)
d1h = parse(c1h)
closes = [x["c"] for x in d15]
price = float(ticker["last"])

period = 14
gains, losses = [], []
for i in range(1, len(closes)):
    ch = closes[i] - closes[i - 1]
    gains.append(max(ch, 0))
    losses.append(max(-ch, 0))
avg_gain = sum(gains[-period:]) / period
avg_loss = sum(losses[-period:]) / period
rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss else 100

def ema(vals, n):
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for v in vals[n:]:
        e = v * k + e * (1 - k)
    return e

ema9 = ema(closes, 9)
ema21 = ema(closes, 21)
mom_1h = (closes[-1] - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0
mom_4h = (closes[-1] - closes[-17]) / closes[-17] * 100 if len(closes) >= 17 else 0

low24 = float(ticker["low24h"])
high24 = float(ticker["high24h"])
recent_low = min(x["l"] for x in d15[-32:])
recent_high = max(x["h"] for x in d15[-32:])
pivot = (high24 + low24 + price) / 3
support = min(x["l"] for x in d15[-20:])
resistance = max(x["h"] for x in d15[-20:])

bid_sz = sum(float(b[1]) for b in ob.get("bids", [])[:10])
ask_sz = sum(float(a[1]) for a in ob.get("asks", [])[:10])
ob_imb = (bid_sz - ask_sz) / (bid_sz + ask_sz) if bid_sz + ask_sz else 0

fr = float(fund["fundingRate"])
open24 = float(ticker["open24h"])
chg24 = float(ticker.get("chg_pct") or (price - open24) / open24 * 100)
vol24 = float(ticker["volCurrency24h"])

trend = 0.5
if ema9 > ema21 and price > ema21:
    trend = 0.75
elif ema9 < ema21 and price < ema21:
    trend = 0.25
elif ema9 > ema21:
    trend = 0.6
else:
    trend = 0.4

momentum = 0.5
if rsi > 70:
    momentum = 0.3
elif rsi > 55:
    momentum = 0.65
elif rsi < 30:
    momentum = 0.7
elif rsi < 45:
    momentum = 0.35

if fr > 0.0003:
    fb, fs = "crowded_long", 0.35
elif fr > 0.0001:
    fb, fs = "mild_long_crowding", 0.45
elif fr < -0.0003:
    fb, fs = "crowded_short", 0.65
elif fr < -0.0001:
    fb, fs = "mild_short_crowding", 0.55
else:
    fb, fs = "neutral", 0.5

long_score = trend * 0.4 + momentum * 0.35
long_score = long_score * 0.85 + fs * 0.15
if ob_imb > 0.05:
    long_score += 0.03
elif ob_imb < -0.05:
    long_score -= 0.03
if chg24 > 40:
    long_score -= 0.08
if price < recent_high * 0.97:
    long_score -= 0.05

factors = [
    0.7 if ema9 > ema21 else 0.35,
    0.55 if 55 < rsi < 70 else (0.4 if rsi >= 70 else 0.5),
    0.45 if chg24 > 40 else 0.6,
    0.55 if fb in ("mild_short_crowding", "crowded_short") else (0.45 if fb == "mild_long_crowding" else 0.5),
    0.5 if abs(price - resistance) / price < 0.01 else 0.55,
    0.6 if mom_1h > 0 else 0.4,
]
confidence = round(sum(factors) / len(factors), 3)

trend_label = "bullish" if trend >= 0.6 else ("bearish" if trend <= 0.4 else "neutral")
suggested = "long" if long_score >= 0.55 else ("short" if long_score <= 0.45 else "long")
if confidence < 0.5:
    suggested = "long" if long_score >= 0.55 else "short"

ema_dir = ">" if ema9 > ema21 else "<"
near_res = abs(price - resistance) / price < 0.01
ob_desc = "bid-side skew" if ob_imb > 0.05 else ("ask-side skew" if ob_imb < -0.05 else "balanced")

technical_summary = (
    f"{INST} +{chg24:.1f}% in 24h from {low24:.5f} low to {high24:.5f} high; "
    f"price {price:.5f} {'at' if near_res else 'below'} session resistance {resistance:.5f} "
    f"with RSI {rsi:.1f}, EMA9 {ema_dir} EMA21. "
    f"Funding {fb.replace('_',' ')} ({fr*100:.4f}%); order book {ob_desc} "
    f"(imbalance {ob_imb:+.2f}). 1h momentum {mom_1h:+.2f}%, 4h {mom_4h:+.2f}%; "
    f"support near {support:.5f}, pivot {pivot:.5f}."
)

report = {
    "instId": INST,
    "price": round(price, 5),
    "change24h": round(chg24, 3),
    "volume24h": int(vol24),
    "trend": trend_label,
    "momentumScore": round(momentum, 3),
    "keyLevels": [round(support, 5), round(pivot, 5), round(resistance, 5), round(low24, 5), round(high24, 5)],
    "fundingRate": round(fr, 6),
    "fundingBias": fb,
    "technicalSummary": technical_summary,
    "suggestedSide": suggested if confidence >= 0.5 else suggested,
    "confidence": confidence,
}
print(json.dumps(report))
