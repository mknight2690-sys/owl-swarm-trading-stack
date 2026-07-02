import json
import subprocess

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
INST = "RESOLV-USDT"


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
    return {
        "rsi": round(r, 2) if r else None,
        "tech": tech,
        "bias": bias,
        "chg": round(chg, 3),
        "last": last,
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
vol = float(ticker.get("volCurrency24h", ticker.get("volCcy24h", ticker.get("vol24h", 0))))

favorable_long = fr <= 0.0005
favorable_short = fr >= -0.0005
spread_ok = spread < 0.5

mom_score = ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3

biases = [ta1["bias"], ta15["bias"], ta1h["bias"]]
if all(b == "long" for b in biases):
    trend = "bullish"
elif all(b == "short" for b in biases):
    trend = "bearish"
elif ta1h["bias"] == "long":
    trend = "bullish"
elif ta1h["bias"] == "short":
    trend = "bearish"
else:
    trend = "mixed"

if fr > 0.0005:
    funding_bias = "long_expensive"
elif fr < -0.0005:
    funding_bias = "short_expensive"
else:
    funding_bias = "neutral"

key_levels = sorted(
    set(
        [
            round(ta1h["low"], 6),
            round(ta15["low"], 6),
            round(ta1["low"], 6),
            round(price, 6),
            round(ta1["high"], 6),
            round(ta15["high"], 6),
            round(ta1h["high"], 6),
        ]
    )
)

conf = mom_score
if not spread_ok:
    conf -= 0.25
if fr > 0.0005:
    conf -= 0.2
elif fr < -0.0005:
    conf -= 0.2
if ta1["bias"] == "long" and ta15["bias"] == "long" and ta1h["bias"] == "long":
    conf += 0.08
elif ta1["bias"] == "short" and ta15["bias"] == "short" and ta1h["bias"] == "short":
    conf += 0.08
else:
    conf -= 0.1
if change24h > 10:
    conf += 0.05
if ta15["rsi"] and ta15["rsi"] > 70:
    conf -= 0.05
if ta1h["rsi"] and ta1h["rsi"] > 75:
    conf -= 0.08
conf = max(0, min(1, round(conf, 3)))

if spread_ok:
    if favorable_long and ta1["bias"] == "long" and ta15["bias"] == "long" and ta1h["bias"] == "long":
        suggested = "long"
    elif favorable_short and ta1["bias"] == "short" and ta15["bias"] == "short" and ta1h["bias"] == "short":
        suggested = "short"
    elif mom_score >= 0.55 and favorable_long and trend != "bearish":
        suggested = "long"
    elif mom_score <= 0.45 and favorable_short and trend != "bullish":
        suggested = "short"
    else:
        suggested = "neutral"
else:
    suggested = "neutral"

if conf < 0.5:
    suggested = "neutral"

tech_summary = (
    f"1m {ta1['bias']} RSI {ta1['rsi']} ({ta1['chg']}%); "
    f"15m {ta15['bias']} RSI {ta15['rsi']} ({ta15['chg']}%); "
    f"1h {ta1h['bias']} RSI {ta1h['rsi']} ({ta1h['chg']}%); "
    f"spread {spread:.4f}%; funding {fr:.6f}"
)

out = {
    "instId": INST,
    "price": price,
    "change24h": round(change24h, 3),
    "volume24h": vol,
    "trend": trend,
    "momentumScore": round(mom_score, 3),
    "keyLevels": key_levels,
    "fundingRate": fr,
    "fundingBias": funding_bias,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech_summary,
    "suggestedSide": suggested,
    "confidence": conf,
}
print(json.dumps(out))
