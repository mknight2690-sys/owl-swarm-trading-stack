import json
import os
import subprocess
import tempfile

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
CWD = r"C:\Users\mknig\owl-swarm"
INST = "CLO-USDT"


def bridge(method, args):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    f.write(json.dumps(args))
    f.close()
    raw = subprocess.check_output(
        [PY, "blofin_bridge.py", method, "@" + f.name], cwd=CWD, stderr=subprocess.STDOUT
    ).decode("utf-8", errors="replace")
    os.unlink(f.name)
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if not line or not line[0] in "[{":
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"No JSON in output for {method}: {raw[:200]!r}")


def parse(raw):
    rows = list(reversed(raw))
    return [
        {"ts": int(x[0]), "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])}
        for x in rows
    ]


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

provided_long = 0.387
provided_short = 0.837

short_score = (1 - (t1 + t15 + t1h) / 3) * 0.5 + (1 - momentum) * 0.3
if mom_1m < 0 and mom_15 < 0 and mom_1h <= 0:
    short_score += 0.1
elif mom_1m > 0 and mom_15 > 0 and mom_1h > 0:
    short_score -= 0.1
if avoid_short:
    short_score -= 0.15
if avoid_long:
    short_score += 0.05
short_score = short_score * 0.7 + provided_short * 0.3

long_score = (t1 + t15 + t1h) / 3 * 0.5 + momentum * 0.3
if mom_1m > 0 and mom_15 > 0 and mom_1h > 0:
    long_score += 0.1
elif mom_1m < 0 and mom_15 < 0 and mom_1h <= 0:
    long_score -= 0.1
if avoid_long:
    long_score -= 0.15
if avoid_short:
    long_score += 0.05
long_score = long_score * 0.7 + provided_long * 0.3

factors = []
bear_count = sum(1 for l in [label_1m, label_15, label_1h] if l == "bearish")
if aligned_bear:
    factors.append(0.78)
elif aligned_bull:
    factors.append(0.22)
else:
    factors.append(0.68 if bear_count >= 2 else 0.42)

if rsi_15 < 30:
    factors.append(0.58)
elif rsi_15 < 45:
    factors.append(0.64)
elif rsi_15 < 55:
    factors.append(0.5)
else:
    factors.append(0.38)

if mom_15 < 0 and mom_1h <= 0:
    factors.append(0.72)
elif mom_15 > 0 and mom_1h > 0:
    factors.append(0.28)
else:
    factors.append(0.5)

factors.append(0.65 if funding_bias == "neutral" else 0.5)
factors.append(0.85 if not avoid_trade else 0.15)
factors.append(0.74 if short_score >= 0.6 else 0.52)
if chg24 < -25:
    factors.append(0.66)

confidence = round(sum(factors) / len(factors), 3)
if avoid_trade:
    confidence = min(confidence, 0.45)

if aligned_bear and not avoid_short and not avoid_trade:
    suggested = "short"
elif aligned_bull and not avoid_long and not avoid_trade:
    suggested = "long"
elif short_score > long_score and not avoid_short:
    suggested = "short"
elif long_score > short_score and not avoid_long:
    suggested = "long"
else:
    suggested = "short" if short_score >= long_score else "long"

overall_trend = (
    "bearish"
    if (t1 + t15 + t1h) / 3 <= 0.4
    else ("bullish" if (t1 + t15 + t1h) / 3 >= 0.6 else "neutral")
)
mtf = (
    "MTF aligned bullish"
    if aligned_bull
    else ("MTF aligned bearish" if aligned_bear else "No MTF alignment")
)
technical_summary = (
    f"1m {label_1m} RSI {rsi_1m:.1f} mom {mom_1m:+.2f}%; "
    f"15m {label_15} RSI {rsi_15:.1f} mom {mom_15:+.2f}%; "
    f"1h {label_1h} RSI {rsi_1h:.1f} mom {mom_1h:+.2f}%. "
    f"24h {chg24:+.1f}% from {low24:.5f} low. Funding {funding_bias} ({fr*100:.4f}%/8h), spread {spread_pct:.3f}%. "
    f"Support {support:.5f}, resistance {resistance:.5f}. {mtf}; long bias {provided_long:.2f} vs short {provided_short:.2f}."
)

report = {
    "instId": INST,
    "price": round(price, 6),
    "change24h": round(chg24, 3),
    "volume24h": int(vol24),
    "trend": overall_trend,
    "momentumScore": round(1 - momentum, 3),
    "keyLevels": [round(support, 6), round(pivot, 6), round(resistance, 6), round(low24, 6), round(high24, 6)],
    "fundingRate": round(fr, 6),
    "fundingBias": funding_bias,
    "spreadPct": round(spread_pct, 4),
    "technicalSummary": technical_summary,
    "suggestedSide": suggested,
    "confidence": confidence,
}
print(json.dumps(report))
