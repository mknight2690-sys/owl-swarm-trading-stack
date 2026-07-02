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
    chg = (closes[-1] - closes[0]) / closes[0] * 100 if closes else 0
    mom_pct = (closes[-1] - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0
    hi = max(c["high"] for c in candles)
    lo = min(c["low"] for c in candles)
    return {
        "rsi": round(r, 2) if r else None,
        "tech": tech,
        "bias": bias,
        "chg": round(chg, 3),
        "last": last,
        "mom_pct": round(mom_pct, 3),
        "high": hi,
        "low": lo,
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
vol24h = float(
    ticker.get("volCurrency24h", ticker.get("volCcy24h", ticker.get("vol24h", 0)))
)

biases = [ta1["bias"], ta15["bias"], ta1h["bias"]]
if all(b == "long" for b in biases):
    trend = "bullish"
elif all(b == "short" for b in biases):
    trend = "bearish"
elif biases.count("long") >= 2:
    trend = "mostly_bullish"
elif biases.count("short") >= 2:
    trend = "mostly_bearish"
else:
    trend = "mixed"

momentumScore = round(ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3, 3)

support = round(min(ta1h["low"], ta15["low"], ta1["low"]), 5)
resistance = round(max(ta1h["high"], ta15["high"], ta1["high"]), 5)
pivot = round((support + resistance + price) / 3, 5)
keyLevels = [support, round(price * 0.995, 5), pivot, round(price * 1.005, 5), resistance]

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
aligned_long = all(b == "long" for b in biases)
aligned_short = all(b == "short" for b in biases)

conf = momentumScore
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
conf = max(0, min(1, round(conf, 3)))

technicalSummary = (
    f"1m {ta1['bias']} RSI {ta1['rsi']} chg {ta1['chg']}% mom {ta1['mom_pct']:+.2f}%; "
    f"15m {ta15['bias']} RSI {ta15['rsi']} chg {ta15['chg']}% mom {ta15['mom_pct']:+.2f}%; "
    f"1h {ta1h['bias']} RSI {ta1h['rsi']} chg {ta1h['chg']}% mom {ta1h['mom_pct']:+.2f}%; "
    f"spread {spread:.4f}% funding {fr:.6f}; DRIFT track 1W/1L +0.32 PnL"
)

suggestedSide = "long" if momentumScore >= 0.5 else "short"
if conf >= 0.5 and spread_ok:
    if favorable_long and aligned_long:
        suggestedSide = "long"
    elif favorable_short and aligned_short:
        suggestedSide = "short"
    elif favorable_long and biases.count("long") >= 2 and ta1["bias"] != "short":
        suggestedSide = "long"
    elif favorable_short and biases.count("short") >= 2 and ta1["bias"] != "long":
        suggestedSide = "short"
    elif favorable_long and momentumScore >= 0.55 and ta15["bias"] != "short":
        suggestedSide = "long"
    elif favorable_short and momentumScore <= 0.45 and ta15["bias"] != "long":
        suggestedSide = "short"
    else:
        suggestedSide = "long" if momentumScore >= 0.5 else "short"
        if suggestedSide == "long" and not favorable_long:
            conf = min(conf, 0.49)
        if suggestedSide == "short" and not favorable_short:
            conf = min(conf, 0.49)

if not spread_ok:
    conf = min(conf, 0.49)
if suggestedSide == "long" and fr > 0.0005:
    conf = min(conf, 0.49)
if suggestedSide == "short" and fr < -0.0005:
    conf = min(conf, 0.49)

out = {
    "instId": INST,
    "price": round(price, 5),
    "change24h": round(change24h, 3),
    "volume24h": round(vol24h, 0),
    "trend": trend,
    "momentumScore": momentumScore,
    "keyLevels": keyLevels,
    "fundingRate": fr,
    "fundingBias": fundingBias,
    "spreadPct": round(spread, 4),
    "technicalSummary": technicalSummary,
    "suggestedSide": suggestedSide,
    "confidence": conf,
}

print(json.dumps(out))
