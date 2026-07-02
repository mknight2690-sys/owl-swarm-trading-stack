import json, subprocess, tempfile, os, sys
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
    return [{"ts": int(x[0]), "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4]), "v": float(x[5]) if len(x) > 5 else 0} for x in rows]

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
        return 0.5, e9, e21
    if e9 > e21 and price > e21:
        return 0.75, e9, e21
    if e9 < e21 and price < e21:
        return 0.25, e9, e21
    if e9 > e21:
        return 0.6, e9, e21
    return 0.4, e9, e21

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

def funding_bias(fr):
    if fr > 0.0003:
        return "crowded_long", 0.35
    if fr > 0.0001:
        return "mild_long_crowding", 0.45
    if fr < -0.0003:
        return "crowded_short", 0.65
    if fr < -0.0001:
        return "mild_short_crowding", 0.55
    return "neutral", 0.5

ticker = bridge("get_ticker", {"inst_id": INST})
if isinstance(ticker, list):
    ticker = ticker[0]
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
mid = (best_bid + best_ask) / 2 if best_bid and best_ask else price
spread_pct = ((best_ask - best_bid) / mid * 100) if mid > 0 else 999

fr = float(fund["fundingRate"])
fb, fs = funding_bias(fr)

closes1m = [x["c"] for x in c1m]
closes15 = [x["c"] for x in c15]
closes1h = [x["c"] for x in c1h]

rsi1m = rsi(closes1m)
rsi15 = rsi(closes15)
rsi1h_val = rsi(closes1h)
t1m, _, _ = trend_score(closes1m, price)
t15, _, _ = trend_score(closes15, price)
t1h, _, _ = trend_score(closes1h, price)

m1m = mom_score(rsi1m)
m15 = mom_score(rsi15)
m1h = mom_score(rsi1h_val)

h1_dir = "up" if closes1h[-1] > closes1h[0] else ("down" if closes1h[-1] < closes1h[0] else "flat")
mom_15 = (closes15[-1] - closes15[-5]) / closes15[-5] * 100 if len(closes15) >= 5 else 0
mom_1h = (closes1h[-1] - closes1h[-4]) / closes1h[-4] * 100 if len(closes1h) >= 4 else 0

support = min(x["l"] for x in c15[-20:]) if c15 else low24
resistance = max(x["h"] for x in c15[-20:]) if c15 else high24
pivot = (high24 + low24 + price) / 3

avg_trend = (t1m + t15 + t1h) / 3
if avg_trend >= 0.6:
    trend_label = "bullish"
elif avg_trend <= 0.4:
    trend_label = "bearish"
else:
    trend_label = "neutral"

momentum = round((m1m + m15 + m1h) / 3, 3)

long_score = avg_trend * 0.4 + momentum * 0.35
long_score = long_score * 0.85 + fs * 0.15

avoid_long = fr > 0.005
avoid_short = fr < -0.005
avoid_trade = spread_pct > 0.5

if avoid_long:
    long_score -= 0.15
if avoid_short:
    long_score += 0.15
if avoid_trade:
    long_score = 0.5

bull_count = sum(1 for t in [t1m, t15, t1h] if t >= 0.6)
bear_count = sum(1 for t in [t1m, t15, t1h] if t <= 0.4)
if bull_count == 3:
    long_score += 0.08
elif bear_count == 3:
    long_score -= 0.08
elif bull_count >= 2 and bear_count == 0:
    long_score += 0.04
elif bear_count >= 2 and bull_count == 0:
    long_score -= 0.04

if long_score >= 0.55 and not avoid_long and not avoid_trade:
    suggested = "long"
elif long_score <= 0.45 and not avoid_short and not avoid_trade:
    suggested = "short"
else:
    suggested = "neutral"

factors = []
factors.append(0.75 if bull_count >= 2 else (0.35 if bear_count >= 2 else 0.5))
factors.append(0.65 if rsi15 and 45 < rsi15 < 70 else (0.4 if rsi15 and rsi15 >= 70 else 0.5))
factors.append(0.7 if not avoid_trade else 0.2)
factors.append(0.65 if not (avoid_long and suggested == "long") and not (avoid_short and suggested == "short") else 0.35)
factors.append(0.6 if abs(mom_15) > 0.5 or abs(mom_1h) > 0.5 else 0.45)
factors.append(0.55 if bull_count == 3 or bear_count == 3 else 0.45)
confidence = round(sum(factors) / len(factors), 3)

if avoid_trade or (suggested == "long" and avoid_long) or (suggested == "short" and avoid_short):
    confidence = min(confidence, 0.45)
    suggested = "neutral"

if confidence < 0.5:
    suggested = "neutral"

rsi1m_str = f"{rsi1m:.1f}" if rsi1m is not None else "n/a"
rsi15_str = f"{rsi15:.1f}" if rsi15 is not None else "n/a"
technical_summary = (
    f"TRUTH-USDT at {price:.5f} ({chg24:+.2f}% 24h). Spread {spread_pct:.3f}%. "
    f"Funding {fr * 100:.4f}% ({fb}). 1m RSI {rsi1m_str}, 15m RSI {rsi15_str}. "
    f"MTF: 1m={t1m:.2f}, 15m={t15:.2f}, 1h={t1h:.2f} ({h1_dir} 1h). "
    f"15m mom {mom_15:+.2f}%, 1h mom {mom_1h:+.2f}%. Support {support:.5f}, resistance {resistance:.5f}."
)

report = {
    "instId": INST,
    "price": round(price, 5),
    "change24h": round(chg24, 3),
    "volume24h": int(vol24),
    "trend": trend_label,
    "momentumScore": momentum,
    "keyLevels": [round(support, 5), round(pivot, 5), round(resistance, 5), round(low24, 5), round(high24, 5)],
    "fundingRate": round(fr, 6),
    "fundingBias": fb,
    "spreadPct": round(spread_pct, 4),
    "technicalSummary": technical_summary,
    "suggestedSide": suggested,
    "confidence": confidence,
}

print(json.dumps(report))
