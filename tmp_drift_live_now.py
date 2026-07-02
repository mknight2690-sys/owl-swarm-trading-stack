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
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
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
vol24h = float(
    ticker.get("volCurrency24h", ticker.get("volCcy24h", ticker.get("vol24h", 0)))
)

support = round(min(ta1h["low"], ta15["low"], min(c["low"] for c in c1m[-20:])), 5)
resistance = round(max(ta1h["high"], ta15["high"], max(c["high"] for c in c1m[-20:])), 5)
pivot = round((support + resistance + price) / 3, 5)

biases = [ta1["bias"], ta15["bias"], ta1h["bias"]]
long_count = biases.count("long")
short_count = biases.count("short")
if long_count >= 2:
    trend = "bullish"
elif short_count >= 2:
    trend = "bearish"
else:
    trend = "mixed"

momentumScore = round((ta1["tech"] + ta15["tech"] + ta1h["tech"]) / 3, 3)

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

conf = ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3
spread_ok = spread < 0.5
fav_long = fr <= 0.0005
fav_short = fr >= -0.0005
aligned_long = long_count == 3
aligned_short = short_count == 3

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

if conf >= 0.5 and spread_ok and fav_long and aligned_long:
    suggested = "long"
elif conf >= 0.5 and spread_ok and fav_short and aligned_short:
    suggested = "short"
elif conf >= 0.5 and spread_ok and fav_long and long_count >= 2:
    suggested = "long"
elif conf >= 0.5 and spread_ok and fav_short and short_count >= 2:
    suggested = "short"
else:
    suggested = "long" if momentumScore >= 0.5 else "short"

tech_sum = (
    f"1m {ta1['bias']} RSI {ta1['rsi']} ({ta1['chg']:+.2f}pct); "
    f"15m {ta15['bias']} RSI {ta15['rsi']} ({ta15['chg']:+.2f}pct); "
    f"1h {ta1h['bias']} RSI {ta1h['rsi']} ({ta1h['chg']:+.2f}pct). "
    f"Spread {spread:.3f}pct. Funding {fr:.6f}. 24h {change24h:+.2f}pct. "
    f"Positive track record 1W/1L +0.32 PnL."
)

out = {
    "instId": INST,
    "price": round(price, 5),
    "change24h": round(change24h, 3),
    "volume24h": round(vol24h, 0),
    "trend": trend,
    "momentumScore": momentumScore,
    "keyLevels": [support, pivot, resistance],
    "fundingRate": fr,
    "fundingBias": fundingBias,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech_sum,
    "suggestedSide": suggested,
    "confidence": conf,
}

print(json.dumps(out))
