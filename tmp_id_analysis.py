import json
import subprocess

BR = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
inst = "ID-USDT"


def fetch(m, a):
    p = subprocess.run(
        [PY, BR, m, json.dumps(a)],
        capture_output=True,
        text=True,
        cwd=r"C:\Users\mknig\owl-swarm",
    )
    if p.returncode:
        raise RuntimeError(p.stderr + p.stdout)
    return json.loads(p.stdout.strip())


def parse(raw):
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


def ema(v, p):
    if len(v) < p:
        return None
    k = 2 / (p + 1)
    val = sum(v[:p]) / p
    for i in range(p, len(v)):
        val = v[i] * k + val * (1 - k)
    return val


def rsi(cl, p=14):
    if len(cl) < p + 1:
        return None
    g, l = [], []
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]
        g.append(max(d, 0))
        l.append(max(-d, 0))
    ag, al = sum(g[-p:]) / p, sum(l[-p:]) / p
    return 100 if al == 0 else 100 - 100 / (1 + ag / al)


def ta(c):
    cl = [x["close"] for x in c]
    last = cl[-1]
    e9, e21 = ema(cl, 9), ema(cl, 21)
    r = rsi(cl)
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
    return {
        "rsi": round(r, 2) if r else None,
        "trend": trend,
        "mom": mom,
        "tech": tech,
        "bias": bias,
        "sup": min(x["low"] for x in c[-20:]),
        "res": max(x["high"] for x in c[-20:]),
    }


fund = fetch("get_funding_rate", {"inst_id": inst})
book = fetch("get_order_book", {"inst_id": inst})
ticker = fetch("get_ticker", {"inst_id": inst})
if isinstance(ticker, list):
    ticker = ticker[0]

fr = float(fund["fundingRate"])
bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100

c1m = parse(fetch("get_candles", {"inst_id": inst, "bar": "1m", "limit": "50"}))
c15 = parse(fetch("get_candles", {"inst_id": inst, "bar": "15m", "limit": "30"}))
c1h = parse(fetch("get_candles", {"inst_id": inst, "bar": "1H", "limit": "24"}))

ta1, ta15, ta1h = ta(c1m), ta(c15), ta(c1h)

price = float(ticker["last"])
open24 = float(ticker["open24h"])
vol = float(ticker["volCurrency24h"])
low24, high24 = float(ticker["low24h"]), float(ticker["high24h"])
change24h = (price - open24) / open24 * 100

support = min(ta15["sup"], ta1h["sup"], low24)
resistance = max(ta15["res"], ta1h["res"])
pivot = (high24 + low24 + price) / 3

if fr > 0.0005:
    fb = "avoid_long"
elif fr < -0.0005:
    fb = "avoid_short"
elif fr > 0.0001:
    fb = "mild_long_crowding"
elif fr < -0.0001:
    fb = "mild_short_crowding"
else:
    fb = "neutral"

aligned_bull = all(x["bias"] == "long" for x in [ta1, ta15, ta1h])
aligned_bear = all(x["bias"] == "short" for x in [ta1, ta15, ta1h])

if aligned_bull:
    trend = "bullish"
elif aligned_bear:
    trend = "bearish"
elif ta1h["bias"] == "long" and ta1["bias"] == "long":
    trend = "bullish_pullback"
elif ta1h["bias"] == "short":
    trend = "bearish"
else:
    trend = "mixed"

mom = round((ta1["mom"] + ta15["mom"] + ta1h["mom"]) / 3, 3)
conf = ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3
avoid_long = fr > 0.0005
avoid_short = fr < -0.0005
avoid_trade = spread > 0.5

if avoid_trade:
    conf -= 0.25
if avoid_long or avoid_short:
    conf -= 0.2
if aligned_bull or aligned_bear:
    conf += 0.08
else:
    conf -= 0.1
if change24h > 10:
    conf += 0.05
if ta1["rsi"] and ta1["rsi"] > 70:
    conf -= 0.05
if ta1h["rsi"] and ta1h["rsi"] > 75:
    conf -= 0.08
conf = max(0, min(1, round(conf, 3)))

side = None
if conf >= 0.5 and not avoid_trade:
    side = ta1["bias"] if ta1["tech"] >= ta15["tech"] else ta15["bias"]
    if side == "neutral":
        side = "long" if change24h > 0 else "short"
    if side == "long" and avoid_long:
        conf = min(conf, 0.49)
        side = None
    if side == "short" and avoid_short:
        conf = min(conf, 0.49)
        side = None

align_note = (
    "Multi-timeframe aligned."
    if aligned_bull or aligned_bear
    else "Timeframes mixed; 1h overbought limits upside."
)
summary = (
    f"1m RSI {ta1['rsi']} trend {ta1['bias']}; "
    f"15m RSI {ta15['rsi']} trend {ta15['bias']}; "
    f"1h RSI {ta1h['rsi']} trend {ta1h['bias']}. "
    f"24h {change24h:+.2f}%; funding {fr:.6f} ({fb}); spread {spread:.3f}%. {align_note}"
)

out = {
    "instId": inst,
    "price": round(price, 5),
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
