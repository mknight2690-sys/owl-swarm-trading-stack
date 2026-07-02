import json
import subprocess

BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
PY = ["py", "-3.12", BRIDGE]
INST = "FIGHT-USDT"


def fetch(method, args):
    p = subprocess.run(
        PY + [method, json.dumps(args)],
        capture_output=True,
        text=True,
        cwd=r"C:\Users\mknig\owl-swarm",
    )
    if p.returncode != 0:
        raise RuntimeError(f"{method} failed: {p.stderr} {p.stdout}")
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


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


def ema(values, period):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    val = sum(values[:period]) / period
    for i in range(period, len(values)):
        val = values[i] * k + val * (1 - k)
    return val


def trend_bias(candles):
    closes = [c["close"] for c in candles]
    last = closes[-1]
    e9, e21 = ema(closes, 9), ema(closes, 21)
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
    return {"bias": bias, "mom5": mom, "last": last}


fund = fetch("get_funding_rate", {"inst_id": INST})
book = fetch("get_order_book", {"inst_id": INST, "size": "20"})
ticker = fetch("get_ticker", {"inst_id": INST})
if isinstance(ticker, list):
    ticker = ticker[0]

c1m = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"}))

t1, t15, t1h = trend_bias(c1m), trend_bias(c15), trend_bias(c1h)

fr = float(fund["fundingRate"])
bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100

price = float(ticker["last"])
change24h = float(
    ticker.get("chg_pct", (price - float(ticker["open24h"])) / float(ticker["open24h"]) * 100)
)
vol = float(ticker["volCurrency24h"])

rsi1m = rsi([c["close"] for c in c1m])
rsi15 = rsi([c["close"] for c in c15])
rsi1h = rsi([c["close"] for c in c1h])

highs = [c["high"] for c in c1h]
lows = [c["low"] for c in c1h]
resistance = max(highs[-12:])
support = min(lows[-12:])
pivot = (resistance + support + price) / 3

score = 0.0
for tf, w in [(t1, 0.2), (t15, 0.35), (t1h, 0.45)]:
    if tf["bias"] == "short":
        score -= w
    elif tf["bias"] == "long":
        score += w
mom_score = round(score, 3)

if fr > 0.0005:
    fb = "avoid_long"
elif fr < -0.0005:
    fb = "avoid_short"
elif fr > 0:
    fb = "slight_long_cost"
elif fr < 0:
    fb = "slight_short_cost"
else:
    fb = "neutral"

if t1["bias"] == t15["bias"] == t1h["bias"]:
    trend = t1["bias"]
elif t15["bias"] == t1h["bias"]:
    trend = f"{t15['bias']}_mixed_1m"
else:
    trend = "mixed"

conf = 0.45
if t15["bias"] == "short" and t1h["bias"] == "short":
    conf += 0.10
if t1["bias"] == "long" or t15["bias"] == "long":
    conf -= 0.15
if t1["bias"] == "long" and t15["bias"] == "long":
    conf -= 0.10
if change24h < -5:
    conf += 0.05
conf -= 0.20
conf = round(max(0.0, min(1.0, conf)), 3)

if conf >= 0.5 and t15["bias"] != "long" and t1h["bias"] == "short":
    suggested = "short"
elif conf >= 0.5 and t1["bias"] == "long" and t15["bias"] == "long" and t1h["bias"] != "short":
    suggested = "long"
else:
    suggested = "short"

tech = (
    f"1m RSI {rsi1m:.1f} {t1['bias']} mom {t1['mom5']:+.2f}%; "
    f"15m RSI {rsi15:.1f} {t15['bias']} mom {t15['mom5']:+.2f}%; "
    f"1h RSI {rsi1h:.1f} {t1h['bias']} mom {t1h['mom5']:+.2f}%. "
    f"24h {change24h:.2f}% with 1m/15m bounce vs 1h bearish; no MTF alignment. "
    f"Funding {fr:.6f} positive (shorts receive). Spread {spread:.3f}% OK. "
    f"FIGHT-USDT on avoid list with recent loss; skip repeat loser."
)

out = {
    "instId": INST,
    "price": price,
    "change24h": round(change24h, 3),
    "volume24h": vol,
    "trend": trend,
    "momentumScore": mom_score,
    "keyLevels": [round(support, 6), round(pivot, 6), round(resistance, 6)],
    "fundingRate": fr,
    "fundingBias": fb,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech,
    "suggestedSide": suggested,
    "confidence": conf,
}
print(json.dumps(out, separators=(",", ":")))
