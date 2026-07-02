import json
import subprocess

BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
PY = ["py", "-3.12", BRIDGE]
INST = "FIGHT-USDT"
ENTRY = 0.003713
LEVERAGE = 10


def fetch(method, args):
    p = subprocess.run(
        PY + [method, json.dumps(args)],
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
    chg = (closes[-1] - closes[0]) / closes[0] * 100 if closes else 0
    mom5 = ((closes[-1] - closes[-5]) / closes[-5] * 100) if len(closes) >= 5 else 0
    return {"bias": bias, "mom5": round(mom5, 3), "chg": round(chg, 3), "last": last}


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

liq = ENTRY * (1 + 1 / LEVERAGE)
liq_dist = (liq - ENTRY) / ENTRY * 100

price = float(ticker["last"])
open24 = float(ticker["open24h"])
chg24 = (price - open24) / open24 * 100
vol = float(ticker.get("volCurrency24h", 0))

fund_ok_short = fr > 0
spread_ok = spread < 0.5
trend_short = all(x["bias"] == "short" for x in [t1, t15, t1h])
liq_ok = liq_dist >= 5
avoid_penalty = True

verified = spread_ok and fund_ok_short and trend_short and liq_ok and not avoid_penalty

conf = 0.35
if t15["bias"] == "short" and t1h["bias"] == "short":
    conf += 0.12
if t1["bias"] != "short":
    conf -= 0.15
if not fund_ok_short:
    conf -= 0.1
if chg24 < -5:
    conf += 0.05
if avoid_penalty:
    conf -= 0.15
conf = round(max(0, min(1, conf)), 3)

side = "neutral"
if trend_short and conf >= 0.5 and fund_ok_short:
    side = "short"
elif all(x["bias"] == "long" for x in [t1, t15, t1h]):
    side = "long"
elif t15["bias"] == "short" and t1h["bias"] == "short" and t1["bias"] != "long":
    side = "short"
elif t1["bias"] == "long" and t15["bias"] == "long":
    side = "long"

notes_parts = []
if fund_ok_short:
    notes_parts.append(f"funding {fr:.8f} favorable for short (longs pay)")
else:
    notes_parts.append(f"ERROR: funding {fr:.8f} unfavorable for short")

if trend_short:
    notes_parts.append("1m/15m/1h all bearish aligned for short")
else:
    notes_parts.append(
        f"ERROR: timeframe mismatch 1m={t1['bias']}({t1['chg']:+.2f}%) "
        f"15m={t15['bias']}({t15['chg']:+.2f}%) 1h={t1h['bias']}({t1h['chg']:+.2f}%)"
    )

if spread_ok:
    notes_parts.append(f"spread {spread:.4f}% OK (<0.5%)")
else:
    notes_parts.append(f"ERROR: spread {spread:.4f}% exceeds 0.5%")

notes_parts.append(f"liq {liq:.6f} distance {liq_dist:.1f}% at 10x isolated short")
if liq_dist < 5:
    notes_parts.append("HIGH LIQUIDATION RISK")

notes_parts.append(f"live price {price} 24h {chg24:.3f}% vol {vol:.0f}")
notes_parts.append("ERROR: FIGHT-USDT on avoid list; 2 losing shorts; skip repeat loser")

out = {
    "instId": INST,
    "suggestedSide": side,
    "confidence": conf,
    "liquidationPrice": round(liq, 6),
    "liquidationDistancePct": round(liq_dist, 2),
    "spreadPct": round(spread, 4),
    "fundingRate": fr,
    "verified": verified,
    "notes": "; ".join(notes_parts),
}
print(json.dumps(out))
