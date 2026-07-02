import json
import subprocess
import sys

BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
INST = "NAORIS-USDT"
ENTRY = 0.038
LEV = 10


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
        return 100
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

fr = float(fund["fundingRate"])
bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100

c1m = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"}))

t1, t15, t1h = trend_bias(c1m), trend_bias(c15), trend_bias(c1h)

price = float(ticker["last"])
change24h = (price - float(ticker["open24h"])) / float(ticker["open24h"]) * 100
vol = float(ticker["volCurrency24h"])

liq = ENTRY * (1 - 1 / LEV)
liq_dist = (ENTRY - liq) / ENTRY * 100

favorable_long = fr <= 0.0005
spread_ok = spread < 0.5
trend_match_long = all(x["bias"] == "long" for x in [t1, t15, t1h])

issues = []
if not spread_ok:
    issues.append(f"spread {spread:.4f}% exceeds 0.5% threshold")
if not favorable_long:
    issues.append(f"funding rate {fr:.6f} unfavorable for long (longs pay)")
if t1["bias"] != "long":
    issues.append(f"1m trend {t1['bias']} conflicts with long")
if t15["bias"] != "long":
    issues.append(f"15m momentum {t15['bias']} conflicts with long")
if t1h["bias"] != "long":
    issues.append(f"1h trend {t1h['bias']} conflicts with long")
if liq_dist < 5:
    issues.append("HIGH LIQUIDATION RISK")

verified = (
    len(issues) == 0
    and trend_match_long
    and favorable_long
    and spread_ok
    and liq_dist >= 5
)

conf = 0.55
if trend_match_long:
    conf += 0.1
if fr > 0.0001:
    conf -= 0.05
if t1["rsi"] and t1["rsi"] > 75:
    conf -= 0.05
if t1h["rsi"] and t1h["rsi"] > 80:
    conf -= 0.05
conf = round(max(0, min(1, conf)), 3)

if verified and conf >= 0.5:
    side = "long"
elif trend_match_long and conf >= 0.5:
    side = "long"
else:
    side = "neutral"

note_bits = [
    f"1m {t1['bias']} RSI {t1['rsi']:.1f}" if t1["rsi"] else f"1m {t1['bias']}",
    f"15m {t15['bias']} RSI {t15['rsi']:.1f}" if t15["rsi"] else f"15m {t15['bias']}",
    f"1h {t1h['bias']} RSI {t1h['rsi']:.1f}" if t1h["rsi"] else f"1h {t1h['bias']}",
    f"live price {price:.5f} vs stated 0.038 24h {change24h:.2f}% vol {vol:.0f}",
    "NAORIS-USDT no trade history in learning log",
]
if issues:
    note_bits.extend(issues)
else:
    note_bits.append("All checks pass")

out = {
    "instId": INST,
    "suggestedSide": side,
    "confidence": conf,
    "liquidationPrice": round(liq, 6),
    "liquidationDistancePct": round(liq_dist, 2),
    "spreadPct": round(spread, 4),
    "fundingRate": fr,
    "verified": verified,
    "notes": "; ".join(note_bits),
}
print(json.dumps(out))
