import json
import subprocess

BR = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
PY = ["py", "-3.12", BR]
inst = "FIGHT-USDT"


def fetch(method, args):
    p = subprocess.run(
        PY + [method, json.dumps(args)],
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
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    return 100 - 100 / (1 + avg_gain / avg_loss)


def trend_bias(candles):
    closes = [c["close"] for c in candles]
    last = closes[-1]
    e9, e21 = ema(closes, 9), ema(closes, 21)
    r = rsi(closes)
    if e9 and e21:
        if e9 > e21 and last > e21:
            bias = "long"
        elif e9 < e21 and last < e21:
            bias = "short"
        elif e9 > e21:
            bias = "long"
        else:
            bias = "short"
    else:
        bias = "neutral"
    mom = ((closes[-1] - closes[-5]) / closes[-5] * 100) if len(closes) >= 5 else 0
    return {"bias": bias, "rsi": r, "mom5": mom, "last": last}


fund = fetch("get_funding_rate", {"inst_id": inst})
book = fetch("get_order_book", {"inst_id": inst, "size": "20"})
ticker = fetch("get_ticker", {"inst_id": inst})
if isinstance(ticker, list):
    ticker = ticker[0]
c1m = parse_candles(fetch("get_candles", {"inst_id": inst, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": inst, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": inst, "bar": "1H", "limit": "24"}))

price = float(ticker["last"])
change24h = (price - float(ticker["open24h"])) / float(ticker["open24h"]) * 100
vol24h = float(
    ticker.get("volCurrency24h", ticker.get("volCcy24h", ticker.get("vol24h", 11713800)))
)
fr = float(fund["fundingRate"])
bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100

t1, t15, t1h = trend_bias(c1m), trend_bias(c15), trend_bias(c1h)

highs = [c["high"] for c in c1h]
lows = [c["low"] for c in c1h]
resistance = max(highs[-12:])
support = min(lows[-12:])
pivot = (resistance + support + price) / 3
keyLevels = [round(support, 6), round(pivot, 6), round(resistance, 6)]

short_votes = sum(1 for x in [t1, t15, t1h] if x["bias"] == "short")
long_votes = sum(1 for x in [t1, t15, t1h] if x["bias"] == "long")
momentumScore = round((short_votes - long_votes) / 3, 3)

if short_votes >= 2:
    trend = "bearish"
elif long_votes >= 2:
    trend = "bullish"
else:
    trend = "mixed"

if fr > 0.0005:
    fundingBias = "long_expensive"
elif fr < -0.0005:
    fundingBias = "short_expensive"
elif fr > 0:
    fundingBias = "slightly_long_pays"
elif fr < 0:
    fundingBias = "slightly_short_pays"
else:
    fundingBias = "neutral"

mtf_aligned = all(x["bias"] == "short" for x in [t1, t15, t1h])

conf = 0.35
if mtf_aligned:
    conf += 0.20
if t15["bias"] == "short" and t1h["bias"] == "short":
    conf += 0.10
if t1["bias"] == "short":
    conf += 0.05
if t1["rsi"] and t1["rsi"] < 30:
    conf -= 0.10
if t15["mom5"] > 0:
    conf -= 0.10
if t1h["mom5"] > 0:
    conf -= 0.05
if fr > 0:
    conf += 0.05
if spread < 0.5:
    conf += 0.03
if change24h < -5:
    conf += 0.05
conf -= 0.15
conf = round(max(0, min(1, conf)), 3)

suggestedSide = None
if conf >= 0.5:
    if short_votes >= 2:
        suggestedSide = "short"
    elif long_votes >= 2:
        suggestedSide = "long"

align_str = "MTF aligned bearish" if mtf_aligned else "No MTF alignment"
tech = (
    f"1m {t1['bias']} RSI={t1['rsi']:.0f} mom5={t1['mom5']:+.2f}%; "
    f"15m {t15['bias']} RSI={t15['rsi']:.0f} mom5={t15['mom5']:+.2f}%; "
    f"1h {t1h['bias']} RSI={t1h['rsi']:.0f} mom5={t1h['mom5']:+.2f}%. "
    f"{align_str}. Spread {spread:.3f}% OK. Funding {fr:.6f} favors shorts. "
    f"1m oversold bounce risk. Poor FIGHT track record; skip repeat loser."
)

out = {
    "instId": inst,
    "price": price,
    "change24h": round(change24h, 3),
    "volume24h": vol24h,
    "trend": trend,
    "momentumScore": momentumScore,
    "keyLevels": keyLevels,
    "fundingRate": fr,
    "fundingBias": fundingBias,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech,
    "confidence": conf,
}
if suggestedSide:
    out["suggestedSide"] = suggestedSide

print(json.dumps(out))
