import json
import subprocess

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
INST = "ALICE-USDT"


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
    return {"rsi": round(r, 2) if r else None, "bias": bias, "tech": tech, "last": last}


fund = fetch("get_funding_rate", {"inst_id": INST})
book = fetch("get_order_book", {"inst_id": INST})
ticker = fetch("get_ticker", {"inst_id": INST})
if isinstance(ticker, list):
    ticker = ticker[0]

c1m = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"}))

t1, t15, t1h = ta(c1m), ta(c15), ta(c1h)

fr = float(fund["fundingRate"])
bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100
price = float(ticker["last"])
open24 = float(ticker["open24h"])
vol24 = float(ticker.get("vol24h") or ticker.get("volCcy24h") or 0)
change24h = (price - open24) / open24 * 100

highs = [c["high"] for c in c1h]
lows = [c["low"] for c in c1h]
res = max(highs)
sup = min(lows)
pivot = (res + sup + price) / 3

mom_score = round(t1["tech"] * 0.35 + t15["tech"] * 0.35 + t1h["tech"] * 0.3, 3)

if fr > 0.0005:
    fb = "avoid_long"
elif fr < -0.0005:
    fb = "avoid_short"
elif fr > 0:
    fb = "long_pays"
elif fr < 0:
    fb = "short_pays"
else:
    fb = "neutral"

aligned_short = t1["bias"] == "short" and t15["bias"] == "short" and t1h["bias"] == "short"
aligned_long = t1["bias"] == "long" and t15["bias"] == "long" and t1h["bias"] == "long"

conf = mom_score
if spread >= 0.5:
    conf -= 0.25
if aligned_short or aligned_long:
    conf += 0.08
else:
    conf -= 0.1
if fr < -0.0005:
    conf -= 0.2
if fr > 0.0005:
    conf -= 0.2
conf = max(0, min(1, round(conf, 3)))

if t1h["bias"] == "short":
    trend = "bearish"
elif t1h["bias"] == "long":
    trend = "bullish"
else:
    trend = "neutral"

tech_sum = (
    f"1m {t1['bias']} RSI {t1['rsi']}; "
    f"15m {t15['bias']} RSI {t15['rsi']}; "
    f"1h {t1h['bias']} RSI {t1h['rsi']}; "
    f"spread {spread:.3f}%; funding {fr:.6f}; 24h {change24h:.1f}%"
)

spread_ok = spread < 0.5
funding_ok_short = fr >= -0.0005
funding_ok_long = fr <= 0.0005

if not spread_ok:
    suggested = "neutral"
    conf = min(conf, 0.45)
elif aligned_short and funding_ok_short:
    suggested = "short"
elif aligned_long and funding_ok_long:
    suggested = "long"
elif t1h["bias"] == "short" and t15["bias"] == "short" and funding_ok_short:
    suggested = "short"
elif t1h["bias"] == "long" and t15["bias"] == "long" and funding_ok_long:
    suggested = "long"
else:
    suggested = "neutral"

if conf < 0.5:
    suggested = "neutral"

out = {
    "instId": INST,
    "price": round(price, 4),
    "change24h": round(change24h, 2),
    "volume24h": round(vol24, 2),
    "trend": trend,
    "momentumScore": mom_score,
    "keyLevels": [round(sup, 4), round(pivot, 4), round(res, 4)],
    "fundingRate": fr,
    "fundingBias": fb,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech_sum,
    "suggestedSide": suggested,
    "confidence": conf,
}

print(json.dumps(out))
