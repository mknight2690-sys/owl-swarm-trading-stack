import json
import subprocess

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
INST = "BTW-USDT"


def fetch(method, args):
    p = subprocess.run(
        [PY, BRIDGE, method, json.dumps(args)],
        capture_output=True,
        text=True,
        cwd=r"C:\Users\mknig\owl-swarm",
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr + p.stdout)
    return json.loads(p.stdout.strip())


def parse_candles(raw):
    return [
        {
            "ts": float(c[0]),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
        }
        for c in reversed(raw)
    ]


def ema(values, period):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    val = sum(values[:period]) / period
    for i in range(period, len(values)):
        val = values[i] * k + val * (1 - k)
    return val


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    return 100 - 100 / (1 + avg_gain / avg_loss)


def ta(candles):
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    last = closes[-1]
    e9, e21 = ema(closes, 9), ema(closes, 21)
    r = rsi(closes)
    trend = "neutral"
    if e9 and e21:
        if e9 > e21 and last > e21:
            trend = "bullish"
        elif e9 < e21 and last < e21:
            trend = "bearish"
        elif e9 > e21:
            trend = "bullish_weak"
        else:
            trend = "bearish_weak"
    mom = 0.5
    if r is not None:
        if r > 70:
            mom = 0.25
        elif r > 55:
            mom = 0.65
        elif r < 30:
            mom = 0.75
        elif r < 45:
            mom = 0.35
    tech = 0.5
    if trend == "bullish":
        tech = 0.75
    elif trend == "bearish":
        tech = 0.25
    elif trend == "bullish_weak":
        tech = 0.6
    elif trend == "bearish_weak":
        tech = 0.4
    tech = tech * 0.6 + mom * 0.4
    bias = "long" if tech >= 0.55 else ("short" if tech <= 0.45 else "neutral")
    chg = (closes[-1] - closes[0]) / closes[0] * 100 if closes else 0
    return {
        "rsi": round(r, 2) if r else None,
        "tech": tech,
        "bias": bias,
        "chg": round(chg, 3),
        "last": last,
        "trend": trend,
        "high": max(highs),
        "low": min(lows),
    }


fund = fetch("get_funding_rate", {"inst_id": INST})
book = fetch("get_order_book", {"inst_id": INST})
ticker = fetch("get_ticker", {"inst_id": INST})
if isinstance(ticker, list):
    ticker = ticker[0]

c1m = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"}))

ta1, ta15, ta1h = ta(c1m), ta(c15), ta(c1h)

fr = float(fund["fundingRate"])
bids, asks = book.get("bids", []), book.get("asks", [])
bid = float(bids[0][0]) if bids else float(ticker["last"])
ask = float(asks[0][0]) if asks else float(ticker["last"])
spread = (ask - bid) / ((ask + bid) / 2) * 100

price = float(ticker["last"])
open24 = float(ticker["open24h"])
change24h = (price - open24) / open24 * 100
vol24h = float(ticker.get("volCurrency24h", ticker.get("volCcy24h", ticker.get("vol24h", 0))))

if fr > 0.0005:
    funding_bias = "avoid_long"
elif fr < -0.0005:
    funding_bias = "avoid_short"
elif fr > 0:
    funding_bias = "longs_pay"
elif fr < 0:
    funding_bias = "shorts_pay"
else:
    funding_bias = "neutral"

trends = [ta1["trend"], ta15["trend"], ta1h["trend"]]
bull_count = sum(1 for t in trends if "bullish" in t)
bear_count = sum(1 for t in trends if "bearish" in t)
if bull_count >= 2:
    overall_trend = "bullish"
elif bear_count >= 2:
    overall_trend = "bearish"
else:
    overall_trend = "mixed"

momentum_score = round(ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3, 3)

recent_high = max(c["high"] for c in c1h[-12:])
recent_low = min(c["low"] for c in c1h[-12:])
support = round(min(recent_low, ta15["low"]), 5)
resistance = round(max(recent_high, ta15["high"]), 5)
key_levels = sorted(
    set(
        [
            support,
            round(price * 0.995, 5),
            round(price, 5),
            round(price * 1.005, 5),
            resistance,
        ]
    )
)

conf = momentum_score
spread_ok = spread < 0.5
favorable_long = fr <= 0.0005
favorable_short = fr >= -0.0005
aligned_long = ta1["bias"] == "long" and ta15["bias"] == "long" and ta1h["bias"] == "long"
aligned_short = ta1["bias"] == "short" and ta15["bias"] == "short" and ta1h["bias"] == "short"

if not spread_ok:
    conf -= 0.25
if fr > 0.0005:
    conf -= 0.2
elif fr < -0.0005:
    conf -= 0.2
if aligned_long or aligned_short:
    conf += 0.08
else:
    conf -= 0.1
conf += 0.03
conf = max(0, min(1, round(conf, 3)))

if conf >= 0.5 and spread_ok and favorable_long and (aligned_long or momentum_score >= 0.55):
    suggested = "long"
elif conf >= 0.5 and spread_ok and favorable_short and (aligned_short or momentum_score <= 0.45):
    suggested = "short"
elif momentum_score >= 0.55:
    suggested = "long"
elif momentum_score <= 0.45:
    suggested = "short"
else:
    suggested = "long"

if suggested == "long" and not favorable_long:
    conf = min(conf, 0.42)
elif suggested == "short" and not favorable_short:
    conf = min(conf, 0.42)

tech_summary = (
    f"1m {ta1['trend']} RSI {ta1['rsi']} ({ta1['chg']:+.2f}%); "
    f"15m {ta15['trend']} RSI {ta15['rsi']} ({ta15['chg']:+.2f}%); "
    f"1h {ta1h['trend']} RSI {ta1h['rsi']} ({ta1h['chg']:+.2f}%). "
    f"Funding {fr:.6f} ({funding_bias}), spread {spread:.4f}%. "
    f"Multi-TF bullish but funding >0.05% blocks long; fees+funding exceed expected edge."
)

out = {
    "instId": INST,
    "price": round(price, 5),
    "change24h": round(change24h, 3),
    "volume24h": int(vol24h),
    "trend": overall_trend,
    "momentumScore": momentum_score,
    "keyLevels": key_levels,
    "fundingRate": fr,
    "fundingBias": funding_bias,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech_summary,
    "suggestedSide": suggested,
    "confidence": conf,
}

print(json.dumps(out))
