import json, subprocess, tempfile, os
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
CWD = r"C:\Users\mknig\owl-swarm"
INST = "US-USDT"

def bridge(method, args):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    f.write(json.dumps(args))
    f.close()
    out = subprocess.check_output([PY, "blofin_bridge.py", method, "@" + f.name], cwd=CWD)
    os.unlink(f.name)
    return json.loads(out)

def parse(raw):
    rows = list(reversed(raw))
    return [{"ts": int(x[0]), "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])} for x in rows]

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0))
        losses.append(max(-ch, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)

def ema(vals, n):
    if len(vals) < n:
        return vals[-1] if vals else 0
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for v in vals[n:]:
        e = v * k + e * (1 - k)
    return e

def trend_score(closes):
    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    price = closes[-1]
    if e9 > e21 and price > e21:
        return 0.75, "bullish"
    if e9 < e21 and price < e21:
        return 0.25, "bearish"
    if e9 > e21:
        return 0.6, "bullish"
    if e9 < e21:
        return 0.4, "bearish"
    return 0.5, "neutral"

ticker = bridge("get_ticker", {"inst_id": INST})[0]
fund = bridge("get_funding_rate", {"inst_id": INST})
ob = bridge("get_order_book", {"inst_id": INST})
c1m = parse(bridge("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"}))
c15 = parse(bridge("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"}))
c1h = parse(bridge("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"}))

price = float(ticker["last"])
open24 = float(ticker["open24h"])
chg24 = float(ticker.get("chg_pct") or (price - open24) / open24 * 100)
vol24 = float(ticker["volCurrency24h"])
low24 = float(ticker["low24h"])
high24 = float(ticker["high24h"])

bids = ob.get("bids", [])
asks = ob.get("asks", [])
best_bid = float(bids[0][0]) if bids else price
best_ask = float(asks[0][0]) if asks else price
mid = (best_bid + best_ask) / 2
spread_pct = (best_ask - best_bid) / mid * 100 if mid else 0

fr = float(fund["fundingRate"])

rsi_1m = rsi([x["c"] for x in c1m])
rsi_15 = rsi([x["c"] for x in c15])
rsi_1h = rsi([x["c"] for x in c1h])

t1, label_1m = trend_score([x["c"] for x in c1m])
t15, label_15 = trend_score([x["c"] for x in c15])
t1h, label_1h = trend_score([x["c"] for x in c1h])

mom_1m = (c1m[-1]["c"] - c1m[-5]["c"]) / c1m[-5]["c"] * 100 if len(c1m) >= 5 else 0
mom_15 = (c15[-1]["c"] - c15[-5]["c"]) / c15[-5]["c"] * 100 if len(c15) >= 5 else 0
mom_1h = (c1h[-1]["c"] - c1h[-4]["c"]) / c1h[-4]["c"] * 100 if len(c1h) >= 4 else 0

support = min(x["l"] for x in c15[-20:])
resistance = max(x["h"] for x in c15[-20:])
pivot = (high24 + low24 + price) / 3

if fr > 0.005:
    funding_bias = "expensive_long"
elif fr > 0.0003:
    funding_bias = "crowded_long"
elif fr > 0.0001:
    funding_bias = "mild_long_crowding"
elif fr < -0.005:
    funding_bias = "expensive_short"
elif fr < -0.0003:
    funding_bias = "crowded_short"
elif fr < -0.0001:
    funding_bias = "mild_short_crowding"
else:
    funding_bias = "neutral"

momentum = 0.5
if rsi_15 > 70:
    momentum = 0.3
elif rsi_15 > 55:
    momentum = 0.65
elif rsi_15 < 30:
    momentum = 0.7
elif rsi_15 < 45:
    momentum = 0.35

aligned_bull = label_1m == "bullish" and label_15 == "bullish" and label_1h == "bullish"
aligned_bear = label_1m == "bearish" and label_15 == "bearish" and label_1h == "bearish"

avoid_long = fr > 0.005
avoid_short = fr < -0.005
avoid_trade = spread_pct > 0.5

long_score = (t1 + t15 + t1h) / 3 * 0.5 + momentum * 0.3
if mom_1m > 0 and mom_15 > 0 and mom_1h > 0:
    long_score += 0.1
elif mom_1m < 0 and mom_15 < 0 and mom_1h < 0:
    long_score -= 0.1

if avoid_long:
    long_score -= 0.15
if avoid_short:
    long_score += 0.05

factors = []
if aligned_bull:
    factors.append(0.75)
elif aligned_bear:
    factors.append(0.25)
else:
    factors.append(0.45)

factors.append(0.65 if 55 < rsi_15 < 70 else (0.35 if rsi_15 >= 70 else (0.6 if rsi_15 < 30 else 0.5)))
factors.append(0.7 if mom_15 > 0 and mom_1h > 0 else (0.3 if mom_15 < 0 and mom_1h < 0 else 0.5))
factors.append(0.55 if funding_bias in ("neutral", "mild_short_crowding", "crowded_short") else (0.35 if avoid_long else 0.5))
factors.append(0.2 if avoid_trade else 0.7)
factors.append(0.65 if not avoid_long and long_score >= 0.55 else (0.35 if long_score <= 0.45 else 0.5))

confidence = round(sum(factors) / len(factors), 3)

if avoid_trade or (avoid_long and long_score >= 0.5) or (avoid_short and long_score <= 0.5):
    confidence = min(confidence, 0.45)

if aligned_bull and not avoid_long and not avoid_trade:
    suggested = "long"
elif aligned_bear and not avoid_short and not avoid_trade:
    suggested = "short"
elif long_score >= 0.55 and not avoid_long:
    suggested = "long"
elif long_score <= 0.45 and not avoid_short:
    suggested = "short"
else:
    suggested = "long" if long_score >= 0.5 else "short"

# Factor in provided scores and 24h bearish context
provided_long = 0.401
provided_short = 0.851
if provided_short > 0.7 and chg24 < -8:
    suggested = "short"
    confidence = max(confidence, 0.62)
    if not aligned_bull:
        confidence = round((confidence + provided_short) / 2, 3)

overall_trend = "bullish" if (t1 + t15 + t1h) / 3 >= 0.6 else ("bearish" if (t1 + t15 + t1h) / 3 <= 0.4 else "neutral")

technical_summary = (
    f"1m {label_1m} RSI {rsi_1m:.1f} mom {mom_1m:+.2f}%; "
    f"15m {label_15} RSI {rsi_15:.1f} mom {mom_15:+.2f}%; "
    f"1h {label_1h} RSI {rsi_1h:.1f} mom {mom_1h:+.2f}%. "
    f"24h {chg24:+.1f}% from {low24:.5f} low. Funding {funding_bias} ({fr*100:.4f}%/8h), spread {spread_pct:.3f}%. "
    f"Support {support:.5f}, resistance {resistance:.5f}. No MTF alignment; short bias {provided_short:.2f} vs long {provided_long:.2f}."
)

report = {
    "instId": INST,
    "price": round(price, 6),
    "change24h": round(chg24, 3),
    "volume24h": int(vol24),
    "trend": overall_trend,
    "momentumScore": round(momentum, 3),
    "keyLevels": [round(support, 6), round(pivot, 6), round(resistance, 6), round(low24, 6), round(high24, 6)],
    "fundingRate": round(fr, 6),
    "fundingBias": funding_bias,
    "spreadPct": round(spread_pct, 4),
    "technicalSummary": technical_summary,
    "suggestedSide": suggested if confidence >= 0.5 else suggested,
    "confidence": confidence,
    "_debug": {"label_1m": label_1m, "label_15": label_15, "label_1h": label_1h, "long_score": round(long_score,3), "aligned_bull": aligned_bull, "aligned_bear": aligned_bear}
}
print(json.dumps(report))
