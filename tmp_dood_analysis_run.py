import json
import subprocess

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
INST = "DOOD-USDT"


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
high24 = float(ticker.get("high24h", price))
low24 = float(ticker.get("low24h", price))

if fr > 0.0005:
    funding_bias = "avoid_long"
elif fr < -0.0005:
    funding_bias = "avoid_short"
elif fr > 0:
    funding_bias = "long_pays"
elif fr < 0:
    funding_bias = "short_pays"
else:
    funding_bias = "neutral"

long_votes = sum(1 for t in (ta1, ta15, ta1h) if t["bias"] == "long")
short_votes = sum(1 for t in (ta1, ta15, ta1h) if t["bias"] == "short")
if long_votes >= 2:
    trend = "bullish"
elif short_votes >= 2:
    trend = "bearish"
elif long_votes == 1 and short_votes == 0:
    trend = "mixed_bullish"
elif short_votes == 1 and long_votes == 0:
    trend = "mixed_bearish"
else:
    trend = "neutral"

momentum = round((ta1["tech"] + ta15["tech"] + ta1h["tech"]) / 3, 3)
key_levels = sorted(
    set(
        [
            round(low24, 6),
            round(min(c["low"] for c in c15[-10:]), 6),
            round(price * 0.995, 6),
            round(price, 6),
            round(price * 1.005, 6),
            round(high24, 6),
        ]
    )
)

conf = ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3
spread_ok = spread < 0.5
favorable_long = fr <= 0.0005
favorable_short = fr >= -0.0005

if not spread_ok:
    conf -= 0.25
if fr > 0.0005:
    conf -= 0.2
elif fr < -0.0005:
    conf -= 0.15
if ta1["bias"] == ta15["bias"] == ta1h["bias"] == "long":
    conf += 0.08
elif ta1["bias"] == ta15["bias"] == ta1h["bias"] == "short":
    conf += 0.08
else:
    conf -= 0.05
if change24h > 8:
    conf += 0.04
if ta15["rsi"] and ta15["rsi"] > 70:
    conf -= 0.05
if ta1h["rsi"] and ta1h["rsi"] > 75:
    conf -= 0.08
conf = max(0, min(1, round(conf, 3)))

if not spread_ok:
    suggested = "long" if momentum >= 0.55 else "short"
elif ta1["bias"] == ta15["bias"] == ta1h["bias"] == "long" and favorable_long:
    suggested = "long"
elif ta1["bias"] == ta15["bias"] == ta1h["bias"] == "short" and favorable_short:
    suggested = "short"
elif momentum >= 0.58 and favorable_long and ta1["bias"] != "short":
    suggested = "long"
elif momentum <= 0.42 and favorable_short and ta1["bias"] != "long":
    suggested = "short"
elif fr > 0.0005:
    suggested = "short" if short_votes >= long_votes else "long"
    conf = min(conf, 0.48)
elif fr < -0.0005:
    suggested = "long" if long_votes >= short_votes else "short"
    conf = min(conf, 0.48)
elif momentum >= 0.55:
    suggested = "long"
elif momentum <= 0.45:
    suggested = "short"
else:
    suggested = "long" if change24h > 0 else "short"

if conf < 0.5:
    suggested = "long" if suggested == "long" and conf >= 0.45 else ("short" if suggested == "short" and conf >= 0.45 else suggested)

tech_summary = (
    f"1m {ta1['bias']} RSI {ta1['rsi']} ({ta1['chg']:+.2f}%); "
    f"15m {ta15['bias']} RSI {ta15['rsi']} ({ta15['chg']:+.2f}%); "
    f"1h {ta1h['bias']} RSI {ta1h['rsi']} ({ta1h['chg']:+.2f}%). "
    f"Funding {fr:.6f}, spread {spread:.4f}%. 24h {change24h:+.2f}%. DOOD 2W/0L."
)

out = {
    "instId": INST,
    "price": round(price, 6),
    "change24h": round(change24h, 3),
    "volume24h": round(vol, 0),
    "trend": trend,
    "momentumScore": momentum,
    "keyLevels": key_levels,
    "fundingRate": fr,
    "fundingBias": funding_bias,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech_summary,
    "suggestedSide": suggested,
    "confidence": conf,
}

print(json.dumps(out))
