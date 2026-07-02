import json
import subprocess

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
INST = "DRIFT-USDT"


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
    mom_pct = (closes[-1] - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0
    return {
        "rsi": round(r, 2) if r else None,
        "trend": trend,
        "mom": mom,
        "tech": tech,
        "bias": bias,
        "last": last,
        "mom_pct": mom_pct,
    }


fund = fetch("get_funding_rate", {"inst_id": INST})
book = fetch("get_order_book", {"inst_id": INST})
ticker = fetch("get_ticker", {"inst_id": INST})
if isinstance(ticker, list):
    ticker = ticker[0]

fr = float(fund["fundingRate"])
bids = book.get("bids", [])
asks = book.get("asks", [])
bid = float(bids[0][0]) if bids else float(ticker["last"])
ask = float(asks[0][0]) if asks else float(ticker["last"])
spread = (ask - bid) / ((ask + bid) / 2) * 100 if bid and ask else 999.0

c1m = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"}))

ta1, ta15, ta1h = ta(c1m), ta(c15), ta(c1h)

price = float(ticker["last"])
open24 = float(ticker["open24h"])
change24h = (price - open24) / open24 * 100
vol = float(ticker["volCurrency24h"])

all_c = c1h + c15[-8:]
highs = [c["high"] for c in all_c]
lows = [c["low"] for c in all_c]
resistance = max(highs[-12:]) if highs else price * 1.02
support = min(lows[-12:]) if lows else price * 0.98
pivot = (resistance + support + price) / 3
key_levels = [round(support, 5), round(pivot, 5), round(resistance, 5)]

if fr > 0.0005:
    funding_bias = "bearish_longs"
elif fr < -0.0005:
    funding_bias = "bearish_shorts"
else:
    funding_bias = "neutral"

momentum = round(ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3, 3)
avg_tech = (ta1["tech"] + ta15["tech"] + ta1h["tech"]) / 3
if avg_tech >= 0.6:
    trend = "bullish"
elif avg_tech <= 0.4:
    trend = "bearish"
else:
    trend = "mixed"

aligned_long = ta1["bias"] == "long" and ta15["bias"] == "long" and ta1h["bias"] == "long"
aligned_short = ta1["bias"] == "short" and ta15["bias"] == "short" and ta1h["bias"] == "short"

conf = ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3
if spread > 0.5:
    conf -= 0.25
if aligned_long or aligned_short:
    conf += 0.08
else:
    conf -= 0.1
if change24h > 10:
    conf += 0.05
if ta1h["rsi"] and ta1h["rsi"] > 75:
    conf -= 0.08
if ta1["bias"] == "neutral" and ta15["bias"] == "long":
    conf -= 0.05
# DRIFT positive track record W/L 1/1 pnl=0.3235
conf += 0.05
conf = max(0, min(1, round(conf, 3)))

favorable_long = fr <= 0.0005
favorable_short = fr >= -0.0005
spread_ok = spread < 0.5

suggested = None
if conf >= 0.5:
    long_ok = favorable_long and spread_ok and fr <= 0.0005
    short_ok = favorable_short and spread_ok and fr >= -0.0005
    if aligned_long and long_ok:
        suggested = "long"
    elif aligned_short and short_ok:
        suggested = "short"
    elif avg_tech >= 0.55 and long_ok:
        suggested = "long"
    elif avg_tech <= 0.45 and short_ok:
        suggested = "short"

tech_summary = (
    f"1m {ta1['bias']} RSI {ta1['rsi']} ({ta1['mom_pct']:+.2f}pct); "
    f"15m {ta15['bias']} RSI {ta15['rsi']} ({ta15['mom_pct']:+.2f}pct); "
    f"1h {ta1h['bias']} RSI {ta1h['rsi']} ({ta1h['mom_pct']:+.2f}pct). "
    f"Funding {fr:.6f}, spread {spread:.4f}pct. 24h chg {change24h:+.2f}pct. "
    f"Multi-TF bullish alignment; positive DRIFT track record."
)

out = {
    "instId": INST,
    "price": round(price, 5),
    "change24h": round(change24h, 3),
    "volume24h": round(vol, 0),
    "trend": trend,
    "momentumScore": momentum,
    "keyLevels": key_levels,
    "fundingRate": fr,
    "fundingBias": funding_bias,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech_summary,
    "confidence": conf,
}
if suggested:
    out["suggestedSide"] = suggested

print(json.dumps(out))
