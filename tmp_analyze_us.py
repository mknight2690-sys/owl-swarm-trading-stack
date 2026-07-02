import json, subprocess, tempfile, os
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
CWD = r"C:\Users\mknig\owl-swarm"
INST = "US-USDT"

def bridge(method, args):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    f.write(json.dumps(args))
    f.close()
    out = subprocess.check_output([PY, "blofin_bridge.py", method, "@" + f.name], cwd=CWD, timeout=60)
    os.unlink(f.name)
    return json.loads(out)

ticker = bridge("get_ticker", {"inst_id": INST})[0]
fund = bridge("get_funding_rate", {"inst_id": INST})
ob = bridge("get_order_book", {"inst_id": INST})
c15 = bridge("get_candles", {"inst_id": INST, "bar": "15m", "limit": "100"})

def parse(raw):
    rows = list(reversed(raw))
    return [{"ts": int(x[0]), "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])} for x in rows]

d15 = parse(c15)
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

provided_long = 0.401
provided_short = 0.851

factors = [
    0.35 if ema9 < ema21 else 0.65,
    0.35 if rsi < 45 else (0.4 if rsi >= 70 else 0.5),
    0.7 if chg24 < -10 else 0.5,
    0.55 if fb in ("mild_short_crowding", "crowded_short") else (0.45 if fb == "mild_long_crowding" else 0.5),
    0.55 if abs(price - support) / price < 0.01 else 0.5,
    0.35 if mom_1h < 0 else 0.6,
    provided_short,
]
confidence = round(sum(factors) / len(factors), 3)

trend_label = "bearish" if trend <= 0.4 or chg24 < -8 else ("bullish" if trend >= 0.6 else "neutral")
suggested = "short" if provided_short > provided_long else "long"

ema_dir = ">" if ema9 > ema21 else "<"
near_sup = abs(price - support) / price < 0.01
sup_word = "at" if near_sup else "above"
ob_desc = "bid-side skew" if ob_imb > 0.05 else ("ask-side skew" if ob_imb < -0.05 else "balanced")

technical_summary = (
    f"{INST} {chg24:+.1f}% in 24h from {low24:.5f} low to {high24:.5f} high; "
    f"price {price:.5f} {sup_word} session support {support:.5f} "
    f"with RSI {rsi:.1f}, EMA9 {ema_dir} EMA21. "
    f"Funding {fb} ({fr*100:.4f}%); order book {ob_desc} "
    f"(imbalance {ob_imb:+.2f}). 1h momentum {mom_1h:+.2f}%, 4h {mom_4h:+.2f}%; "
    f"resistance near {resistance:.5f}, pivot {pivot:.5f}. "
    f"Short score {provided_short:.3f} vs long {provided_long:.3f}."
)

report = {
    "instId": INST,
    "price": round(price, 6),
    "change24h": round(chg24, 3),
    "volume24h": int(vol24),
    "trend": trend_label,
    "momentumScore": round(momentum, 3),
    "keyLevels": [round(support, 6), round(pivot, 6), round(resistance, 6), round(low24, 6), round(high24, 6)],
    "fundingRate": round(fr, 6),
    "fundingBias": fb,
    "technicalSummary": technical_summary,
    "suggestedSide": suggested,
    "confidence": confidence,
}
print(json.dumps(report))
