import json
import subprocess

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
INST = "DOOD-USDT"
CWD = r"C:\Users\mknig\owl-swarm"


def fetch(method, args):
    p = subprocess.run(
        [PY, BRIDGE, method, json.dumps(args)],
        capture_output=True,
        text=True,
        cwd=CWD,
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


fund = fetch("get_funding_rate", {"inst_id": INST})
book = fetch("get_order_book", {"inst_id": INST})
ticker = fetch("get_ticker", {"inst_id": INST})
if isinstance(ticker, list):
    ticker = ticker[0]

c1m = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"}))

t1, t15, t1h = trend_bias(c1m), trend_bias(c15), trend_bias(c1h)

fr = float(fund["fundingRate"])
bids, asks = book.get("bids", []), book.get("asks", [])
bid = float(bids[0][0]) if bids else float(ticker["last"])
ask = float(asks[0][0]) if asks else float(ticker["last"])
spread = (ask - bid) / ((ask + bid) / 2) * 100

price = float(ticker["last"])
open24 = float(ticker["open24h"])
change24h = (price - open24) / open24 * 100
vol24h = float(ticker.get("volCurrency24h", ticker.get("volCcy24h", ticker.get("vol24h", 0))))

highs = [c["high"] for c in c1h]
lows = [c["low"] for c in c1h]
resistance = max(highs[-12:])
support = min(lows[-12:])
pivot = (resistance + support + price) / 3
keyLevels = [round(support, 6), round(pivot, 6), round(resistance, 6)]

short_votes = sum(1 for x in [t1, t15, t1h] if x["bias"] == "short")
long_votes = sum(1 for x in [t1, t15, t1h] if x["bias"] == "long")
momentumScore = round((long_votes - short_votes) / 3, 3)

if short_votes >= 2:
    trend = "bearish"
elif long_votes >= 2:
    trend = "bullish"
else:
    trend = "mixed"

if fr > 0.0005:
    fundingBias = "avoid_long"
elif fr < -0.0005:
    fundingBias = "avoid_short"
elif fr > 0:
    fundingBias = "longs_pay"
elif fr < 0:
    fundingBias = "shorts_pay"
else:
    fundingBias = "neutral"

spread_ok = spread < 0.5
favorable_long = fr <= 0.0005
favorable_short = fr >= -0.0005
aligned_long = all(x["bias"] == "long" for x in [t1, t15, t1h])
aligned_short = all(x["bias"] == "short" for x in [t1, t15, t1h])

conf = 0.45
if aligned_long:
    conf += 0.15
elif aligned_short:
    conf += 0.15
elif long_votes >= 2:
    conf += 0.08
elif short_votes >= 2:
    conf += 0.08
else:
    conf -= 0.12
if spread_ok:
    conf += 0.05
else:
    conf -= 0.25
if favorable_long and long_votes >= 2:
    conf += 0.05
if favorable_short and short_votes >= 2:
    conf += 0.05
if fr > 0.0005 and long_votes >= 2:
    conf -= 0.25
if fr < -0.0005 and short_votes >= 2:
    conf -= 0.25
if t1["rsi"] and t1["rsi"] > 75:
    conf -= 0.08
if t1["rsi"] and t1["rsi"] < 25:
    conf -= 0.05
if change24h > 10 and long_votes >= 2:
    conf += 0.05
conf = round(max(0, min(1, conf)), 3)

suggestedSide = None
if conf >= 0.5 and spread_ok:
    if aligned_long and favorable_long:
        suggestedSide = "long"
    elif aligned_short and favorable_short:
        suggestedSide = "short"
    elif trend == "bullish" and favorable_long and t1["bias"] != "short":
        suggestedSide = "long"
    elif trend == "bearish" and favorable_short and t1["bias"] != "long":
        suggestedSide = "short"

spread_label = "OK" if spread_ok else "HIGH"
mtf_label = f"aligned {trend}" if aligned_long or aligned_short else "mixed"
rsi1 = f"{t1['rsi']:.0f}" if t1["rsi"] is not None else "NA"
rsi15 = f"{t15['rsi']:.0f}" if t15["rsi"] is not None else "NA"
rsi1h = f"{t1h['rsi']:.0f}" if t1h["rsi"] is not None else "NA"

tech = (
    f"1m {t1['bias']} RSI={rsi1} mom5={t1['mom5']:+.2f}%; "
    f"15m {t15['bias']} RSI={rsi15} mom5={t15['mom5']:+.2f}%; "
    f"1h {t1h['bias']} RSI={rsi1h} mom5={t1h['mom5']:+.2f}%. "
    f"Spread {spread:.4f}% {spread_label}. Funding {fr:.6f} ({fundingBias}). "
    f"MTF {mtf_label}. DOOD no trade history."
)

out = {
    "instId": INST,
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
