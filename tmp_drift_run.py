import json
import subprocess
import sys

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
CWD = r"C:\Users\mknig\owl-swarm"
INST = "DRIFT-USDT"


def fetch(method, args):
    p = subprocess.run(
        [PY, BRIDGE, method, json.dumps(args)],
        capture_output=True,
        text=True,
        cwd=CWD,
    )
    if p.returncode != 0:
        print(p.stderr, file=sys.stderr)
        print(p.stdout, file=sys.stderr)
        raise RuntimeError(f"fetch failed: {method}")
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
    last = closes[-1]
    e9, e21 = ema(closes, 9), ema(closes, 21)
    r = rsi(closes)
    trend = 0.5
    if e9 and e21:
        if e9 > e21 and last > e21:
            trend = 0.75
        elif e9 < e21 and last < e21:
            trend = 0.25
        elif e9 > e21:
            trend = 0.6
        else:
            trend = 0.4
    mom = 0.5
    if r is not None:
        if r > 70:
            mom = 0.3
        elif r > 55:
            mom = 0.65
        elif r < 30:
            mom = 0.7
        elif r < 45:
            mom = 0.35
    tech = trend * 0.6 + mom * 0.4
    bias = "long" if tech >= 0.55 else ("short" if tech <= 0.45 else "neutral")
    sup = min(c["low"] for c in candles[-20:])
    res = max(c["high"] for c in candles[-20:])
    return {
        "last": last,
        "rsi14": round(r, 2) if r else None,
        "trend": trend,
        "momentumScore": mom,
        "technicalScore": tech,
        "suggestedBias": bias,
        "keyLevels": {"support": sup, "resistance": res},
    }


fund = fetch("get_funding_rate", {"inst_id": INST})
book = fetch("get_order_book", {"inst_id": INST})
ticker = fetch("get_ticker", {"inst_id": INST})
if isinstance(ticker, list):
    ticker = ticker[0]

fr = float(fund["fundingRate"])
bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100

c1m = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"}))

ta1m, ta15, ta1h = ta(c1m), ta(c15), ta(c1h)

price = float(ticker["last"])
open24 = float(ticker["open24h"])
change24h = (price - open24) / open24 * 100
vol = float(ticker["volCurrency24h"])
low24, high24 = float(ticker["low24h"]), float(ticker["high24h"])

support = min(ta15["keyLevels"]["support"], ta1h["keyLevels"]["support"], low24)
resistance = max(ta15["keyLevels"]["resistance"], ta1h["keyLevels"]["resistance"])
pivot = (high24 + low24 + price) / 3

if fr > 0.0003:
    fb = "crowded_long"
elif fr > 0.0001:
    fb = "mild_long_crowding"
elif fr < -0.0003:
    fb = "crowded_short"
elif fr < -0.0001:
    fb = "mild_short_crowding"
else:
    fb = "neutral"

aligned_bull = all(x["suggestedBias"] == "long" for x in [ta1m, ta15, ta1h])
aligned_bear = all(x["suggestedBias"] == "short" for x in [ta1m, ta15, ta1h])

if aligned_bull:
    trend = "bullish"
elif aligned_bear:
    trend = "bearish"
elif ta1h["suggestedBias"] == "long" and ta1m["suggestedBias"] == "long":
    trend = "bullish_pullback"
elif ta1h["suggestedBias"] == "short":
    trend = "bearish"
else:
    trend = "mixed"

mom = round((ta1m["momentumScore"] + ta15["momentumScore"] + ta1h["momentumScore"]) / 3, 3)

conf = ta1m["technicalScore"] * 0.35 + ta15["technicalScore"] * 0.35 + ta1h["technicalScore"] * 0.3
avoid_long = fr > 0.0001
avoid_short = fr < -0.0001
if spread > 0.5:
    conf -= 0.25
if avoid_long or avoid_short:
    conf -= 0.15
if aligned_bull or aligned_bear:
    conf += 0.08
else:
    conf -= 0.1
if change24h > 10:
    conf += 0.05
if ta1m["rsi14"] and ta1m["rsi14"] > 70:
    conf -= 0.05
conf = max(0, min(1, round(conf, 3)))

side = None
if conf >= 0.5:
    side = ta1m["suggestedBias"] if ta1m["technicalScore"] >= ta15["technicalScore"] else ta15["suggestedBias"]
    if side == "neutral":
        side = "long" if change24h > 0 else "short"
    if avoid_long and side == "long":
        conf = min(conf, 0.45)
        side = None
    if avoid_short and side == "short":
        conf = min(conf, 0.45)
        side = None
    if spread > 0.5:
        conf = min(conf, 0.45)
        side = None

align_note = (
    "Multi-timeframe aligned."
    if aligned_bull or aligned_bear
    else "Timeframes mixed."
)
summary = (
    f"1m RSI {ta1m['rsi14']} trend {ta1m['suggestedBias']}; "
    f"15m RSI {ta15['rsi14']} trend {ta15['suggestedBias']}; "
    f"1h RSI {ta1h['rsi14']} trend {ta1h['suggestedBias']}. "
    f"24h {change24h:+.2f}%; funding {fr:.6f} ({fb}); spread {spread:.3f}%. {align_note}"
)

out = {
    "instId": INST,
    "price": price,
    "change24h": round(change24h, 3),
    "volume24h": vol,
    "trend": trend,
    "momentumScore": mom,
    "keyLevels": [round(support, 5), round(pivot, 5), round(resistance, 5)],
    "fundingRate": fr,
    "fundingBias": fb,
    "spreadPct": round(spread, 4),
    "technicalSummary": summary,
    "confidence": conf,
}
if side and conf >= 0.5:
    out["suggestedSide"] = side
print(json.dumps(out))
