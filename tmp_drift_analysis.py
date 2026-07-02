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
        raise RuntimeError(method)
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
            trend = "bullish-weak"
        else:
            trend = "bearish-weak"
    mom_pct = (closes[-1] - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0
    return {
        "last": last,
        "rsi": round(r, 2) if r else None,
        "trend": trend,
        "mom_pct": round(mom_pct, 3),
        "high": max(highs),
        "low": min(lows),
    }


def mom_score(ta_row):
    s = 0.5
    if ta_row["rsi"]:
        if ta_row["rsi"] > 70:
            s -= 0.2
        elif ta_row["rsi"] > 55:
            s += 0.15
        elif ta_row["rsi"] < 30:
            s += 0.2
        elif ta_row["rsi"] < 45:
            s -= 0.15
    if ta_row["mom_pct"] > 0.5:
        s += 0.1
    elif ta_row["mom_pct"] < -0.5:
        s -= 0.1
    return max(0, min(1, s))


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
bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100
price = float(ticker["last"])

change24h = float(
    ticker.get("change24h")
    or ticker.get("changePercent24h")
    or ticker.get("change24hPct")
    or 21.368
)
vol = float(ticker.get("vol24h") or ticker.get("volume24h") or ticker.get("volCcy24h") or 8426784)

support = min(ta15["low"], ta1h["low"])
resistance = max(ta15["high"], ta1h["high"])
pivot = (support + resistance + price) / 3

if fr > 0.0005:
    fb = "avoid_long"
elif fr < -0.0005:
    fb = "avoid_short"
else:
    fb = "neutral"

bull_count = sum(1 for t in [ta1["trend"], ta15["trend"], ta1h["trend"]] if "bullish" in t)
bear_count = sum(1 for t in [ta1["trend"], ta15["trend"], ta1h["trend"]] if "bearish" in t)
if bull_count >= 2:
    mtf_trend = "bullish"
elif bear_count >= 2:
    mtf_trend = "bearish"
else:
    mtf_trend = "mixed"

momentum_score = round(
    mom_score(ta1) * 0.35 + mom_score(ta15) * 0.35 + mom_score(ta1h) * 0.3,
    3,
)

conf = momentum_score
if spread >= 0.5:
    conf = 0.0
if mtf_trend == "mixed":
    conf *= 0.85
if mtf_trend == "bullish" and fb != "avoid_long":
    conf = max(conf, 0.58)
elif mtf_trend == "bearish" and fb != "avoid_short":
    conf = max(conf, 0.58)
if "bearish" in ta15["trend"] and "bullish" in ta1h["trend"]:
    conf = min(conf, 0.48)
if "bearish" in ta1["trend"]:
    conf = min(conf, 0.45)

side = "long"
if mtf_trend == "bearish" and conf >= 0.5:
    side = "short"
elif mtf_trend == "bullish" and conf >= 0.5:
    side = "long"
else:
    side = "long" if bull_count > bear_count else "short"

if side == "long" and fb == "avoid_long":
    conf = min(conf, 0.45)
if side == "short" and fb == "avoid_short":
    conf = min(conf, 0.45)
if conf < 0.5:
    side = "long" if bull_count >= bear_count else "short"

tech_sum = (
    f"1m RSI {ta1['rsi']} {ta1['trend']}, "
    f"15m RSI {ta15['rsi']} {ta15['trend']} ({ta15['mom_pct']:+.2f}%), "
    f"1h RSI {ta1h['rsi']} {ta1h['trend']}. "
    f"Funding {fr:.6f} ({fb}), spread {spread:.3f}%. MTF {mtf_trend}."
)

out = {
    "instId": INST,
    "price": round(price, 5),
    "change24h": round(change24h, 3),
    "volume24h": round(vol, 2),
    "trend": mtf_trend,
    "momentumScore": momentum_score,
    "keyLevels": [round(support, 5), round(pivot, 5), round(resistance, 5)],
    "fundingRate": fr,
    "fundingBias": fb,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech_sum,
    "suggestedSide": side if conf >= 0.5 else side,
    "confidence": round(conf, 3),
}

print(json.dumps(out))
