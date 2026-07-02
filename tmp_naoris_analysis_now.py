import json
import subprocess
import sys

BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
INST = "NAORIS-USDT"


def fetch(method, args):
    p = subprocess.run(
        [sys.executable, BRIDGE, method, json.dumps(args)],
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
        return 100.0
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
    return {"bias": bias, "rsi": r, "last": last}


fund = fetch("get_funding_rate", {"inst_id": INST})
book = fetch("get_order_book", {"inst_id": INST})
ticker = fetch("get_ticker", {"inst_id": INST})
if isinstance(ticker, list):
    ticker = ticker[0]

c1m = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"}))

fr = float(fund["fundingRate"])
bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100
price = float(ticker["last"])
change24h = (price - float(ticker["open24h"])) / float(ticker["open24h"]) * 100
vol = float(ticker["volCurrency24h"])

t1, t15, t1h = trend_bias(c1m), trend_bias(c15), trend_bias(c1h)

highs = [c["high"] for c in c1h]
lows = [c["low"] for c in c1h]
key_levels = sorted(
    {
        round(max(highs), 5),
        round(min(lows), 5),
        round(c1h[-1]["close"], 5),
        round(c15[-1]["close"], 5),
        round(price, 5),
    }
)

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

long_votes = sum(1 for t in (t1, t15, t1h) if t["bias"] == "long")
short_votes = sum(1 for t in (t1, t15, t1h) if t["bias"] == "short")
if long_votes >= 2:
    trend = "bullish"
elif short_votes >= 2:
    trend = "bearish"
else:
    trend = "mixed"

momentum_score = long_votes / 3 if trend == "bullish" else (short_votes / 3 if trend == "bearish" else 0.4)

conf = 0.45
if trend == "bullish" and long_votes == 3:
    conf += 0.25
elif trend == "bearish" and short_votes == 3:
    conf += 0.25
elif trend in ("bullish", "bearish"):
    conf += 0.1
if spread >= 0.5:
    conf -= 0.3
if fr > 0.0005 and trend == "bullish":
    conf -= 0.2
if fr < -0.0005 and trend == "bearish":
    conf -= 0.2
if t1["rsi"] and t1["rsi"] > 75 and trend == "bullish":
    conf -= 0.1
if t1["rsi"] and t1["rsi"] < 25 and trend == "bearish":
    conf -= 0.1
if trend == "bullish":
    conf += 0.843 * 0.15
    conf -= 0.393 * 0.1
conf = round(max(0.0, min(1.0, conf)), 3)

suggested_side = None
if conf >= 0.5 and spread < 0.5:
    if trend == "bullish" and fr <= 0.0005:
        suggested_side = "long"
    elif trend == "bearish" and fr >= -0.0005:
        suggested_side = "short"

def fmt_rsi(v):
    return f"{v:.1f}" if v is not None else "N/A"

technical_summary = (
    f"1m {t1['bias']} RSI {fmt_rsi(t1['rsi'])}; "
    f"15m {t15['bias']} RSI {fmt_rsi(t15['rsi'])}; "
    f"1h {t1h['bias']} RSI {fmt_rsi(t1h['rsi'])}; "
    f"spread {spread:.3f}%; funding {fr:.6f}"
)

out = {
    "instId": INST,
    "price": round(price, 5),
    "change24h": round(change24h, 3),
    "volume24h": round(vol, 0),
    "trend": trend,
    "momentumScore": round(momentum_score, 3),
    "keyLevels": key_levels,
    "fundingRate": fr,
    "fundingBias": funding_bias,
    "spreadPct": round(spread, 4),
    "technicalSummary": technical_summary,
    "suggestedSide": suggested_side,
    "confidence": conf,
}
print(json.dumps(out))
