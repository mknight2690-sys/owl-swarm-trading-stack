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
            trend = "bullish"
        else:
            trend = "bearish"
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
        else:
            mom = 0.5
    tech = (0.75 if trend == "bullish" else (0.25 if trend == "bearish" else 0.5)) * 0.6 + mom * 0.4
    chg = (closes[-1] - closes[0]) / closes[0] * 100 if closes else 0
    return {
        "rsi": r,
        "tech": tech,
        "trend": trend,
        "chg": chg,
        "last": last,
        "high": max(c["high"] for c in candles),
        "low": min(c["low"] for c in candles),
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

if fr > 0.0005:
    funding_bias = "avoid_long"
elif fr < -0.0005:
    funding_bias = "avoid_short"
else:
    funding_bias = "neutral"

recent_high = max(c["high"] for c in c1h[-12:])
recent_low = min(c["low"] for c in c1h[-12:])
key_levels = sorted(
    set(
        [
            round(recent_low, 5),
            round(price * 0.99, 5),
            round(price, 5),
            round(price * 1.01, 5),
            round(recent_high, 5),
        ]
    )
)

momentum = ta15["tech"] * 0.5 + ta1h["tech"] * 0.5
trends = [ta1["trend"], ta15["trend"], ta1h["trend"]]
bull = trends.count("bullish")
bear = trends.count("bearish")
if bull >= 2:
    trend = "bullish"
elif bear >= 2:
    trend = "bearish"
else:
    trend = "mixed"

conf = ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3
spread_ok = spread < 0.5
fav_long = fr <= 0.0005
fav_short = fr >= -0.0005

if not spread_ok:
    conf -= 0.25
if fr > 0.0005:
    conf -= 0.2
elif fr < -0.0005:
    conf -= 0.2
if bull == 3:
    conf += 0.1
elif bear == 3:
    conf += 0.1
elif trend == "mixed":
    conf -= 0.15
if change24h > 10:
    conf += 0.05
if ta15["rsi"] and ta15["rsi"] > 70:
    conf -= 0.08
if ta1h["rsi"] and ta1h["rsi"] > 75:
    conf -= 0.08
conf -= 0.05
conf = max(0, min(1, round(conf, 3)))

suggested = "long"
if conf >= 0.5:
    if bull >= 2 and fav_long and spread_ok:
        suggested = "long"
    elif bear >= 2 and fav_short and spread_ok:
        suggested = "short"
    elif ta1["tech"] >= 0.55 and ta15["tech"] >= 0.55 and fav_long and spread_ok:
        suggested = "long"
    elif ta1["tech"] <= 0.45 and ta15["tech"] <= 0.45 and fav_short and spread_ok:
        suggested = "short"
    else:
        suggested = "long" if bull >= bear else "short"
else:
    suggested = "long" if bull > bear else "short"

rsi1 = round(ta1["rsi"], 1) if ta1["rsi"] else "N/A"
rsi15 = round(ta15["rsi"], 1) if ta15["rsi"] else "N/A"
rsi1h = round(ta1h["rsi"], 1) if ta1h["rsi"] else "N/A"
tech_sum = (
    f"1m {ta1['trend']} RSI {rsi1} chg {round(ta1['chg'], 2)}%; "
    f"15m {ta15['trend']} RSI {rsi15} chg {round(ta15['chg'], 2)}%; "
    f"1h {ta1h['trend']} RSI {rsi1h} chg {round(ta1h['chg'], 2)}%; "
    f"spread {round(spread, 4)}%; funding {fr:.6f}"
)

out = {
    "instId": INST,
    "price": round(price, 5),
    "change24h": round(change24h, 3),
    "volume24h": round(vol, 0),
    "trend": trend,
    "momentumScore": round(momentum, 3),
    "keyLevels": key_levels,
    "fundingRate": fr,
    "fundingBias": funding_bias,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech_sum,
    "suggestedSide": suggested,
    "confidence": conf,
}

print(json.dumps(out))
