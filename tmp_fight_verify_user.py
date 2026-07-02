import json
import subprocess

BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
PY = r"py"
PY_ARGS = ["-3.12", BRIDGE]
ENTRY = 0.003675
LEVERAGE = 10


def fetch(method, args):
    p = subprocess.run(
        [PY, *PY_ARGS, method, json.dumps(args)],
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
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
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
    mom = ((closes[-1] - closes[-5]) / closes[-5] * 100) if len(closes) >= 5 else 0
    return {"bias": bias, "rsi": r, "mom5": mom, "last": last}


inst = "FIGHT-USDT"
fund = fetch("get_funding_rate", {"inst_id": inst})
book = fetch("get_order_book", {"inst_id": inst, "size": "20"})
ticker = fetch("get_ticker", {"inst_id": inst})
if isinstance(ticker, list):
    ticker = ticker[0]

fr = float(fund["fundingRate"])
bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100

c1m = parse_candles(fetch("get_candles", {"inst_id": inst, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": inst, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": inst, "bar": "1H", "limit": "24"}))

t1, t15, t1h = trend_bias(c1m), trend_bias(c15), trend_bias(c1h)

liq_price = ENTRY * (1 + 1 / LEVERAGE)
liq_dist = ((liq_price - ENTRY) / ENTRY) * 100

funding_favorable_short = fr <= 0
spread_ok = spread < 0.5
trend_match_short = all(x["bias"] == "short" for x in [t1, t15, t1h])
verified = spread_ok and funding_favorable_short and trend_match_short and liq_dist >= 5

price = float(ticker["last"])
change24h = (price - float(ticker["open24h"])) / float(ticker["open24h"]) * 100

# confidence from verified signals only
conf = 0.35
if t15["bias"] == "short" and t1h["bias"] == "short":
    conf += 0.12
if t1["bias"] != "short":
    conf -= 0.15
if not funding_favorable_short:
    conf -= 0.1
if change24h < -5:
    conf += 0.05
conf = round(max(0, min(1, conf)), 3)

side = "neutral"
if trend_match_short and conf >= 0.5 and funding_favorable_short:
    side = "short"
elif all(x["bias"] == "long" for x in [t1, t15, t1h]):
    side = "long"
elif t15["bias"] == "short" and t1h["bias"] == "short" and t1["bias"] != "long":
    side = "short"
elif t1["bias"] == "long":
    side = "neutral"

notes_parts = []
if not funding_favorable_short:
    notes_parts.append("ERROR: funding positive (shorts pay); not favorable for short")
if not trend_match_short:
    notes_parts.append(f"ERROR: 1m trend {t1['bias']} conflicts with short (15m={t15['bias']}, 1h={t1h['bias']})")
if spread_ok:
    notes_parts.append(f"spread {spread:.4f}% OK (<0.5%)")
else:
    notes_parts.append(f"spread {spread:.4f}% FAIL")
notes_parts.append(f"liq {liq_dist:.1f}% at 10x isolated short entry {ENTRY}")
if liq_dist < 5:
    notes_parts.append("HIGH LIQUIDATION RISK")
notes_parts.append(f"live price {price} 24h {change24h:.2f}% vol {ticker['volCurrency24h']}")
notes_parts.append("FIGHT-USDT not in trade history; no track-record bias")

out = {
    "instId": inst,
    "suggestedSide": side,
    "confidence": conf,
    "liquidationPrice": round(liq_price, 6),
    "liquidationDistancePct": round(liq_dist, 2),
    "spreadPct": round(spread, 4),
    "fundingRate": fr,
    "verified": verified,
    "notes": "; ".join(notes_parts),
}
print(json.dumps(out))
