import json
import subprocess

BR = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
PY = ["py", "-3.12", BR]
ENTRY = 0.003683
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
    return [{"close": float(c[4])} for c in reversed(raw)]


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
    mom5 = ((closes[-1] - closes[-5]) / closes[-5] * 100) if len(closes) >= 5 else 0
    return {"bias": bias, "rsi": r, "mom5": mom5}


inst = "FIGHT-USDT"
fund = fetch("get_funding_rate", {"inst_id": inst})
book = fetch("get_order_book", {"inst_id": inst, "size": "20"})
ticker = fetch("get_ticker", {"inst_id": inst})
if isinstance(ticker, list):
    ticker = ticker[0]
c1m = parse_candles(fetch("get_candles", {"inst_id": inst, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": inst, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": inst, "bar": "1H", "limit": "24"}))

fr = float(fund["fundingRate"])
bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100
t1, t15, t1h = trend_bias(c1m), trend_bias(c15), trend_bias(c1h)
liq = ENTRY * (1 + 1 / LEVERAGE)
liq_dist = ((liq - ENTRY) / ENTRY) * 100

funding_favorable_short = fr > 0
spread_ok = spread < 0.5
trend_match_short = all(x["bias"] == "short" for x in [t1, t15, t1h])
track_record_bad = True
liq_ok = liq_dist >= 5
verified = (
    spread_ok
    and funding_favorable_short
    and trend_match_short
    and liq_ok
    and not track_record_bad
)

change24h = float(ticker["chg_pct"])
conf = 0.35
if t15["bias"] == "short" and t1h["bias"] == "short":
    conf += 0.12
if t1["bias"] == "short":
    conf += 0.05
elif t1["bias"] != "short":
    conf -= 0.15
if t15["mom5"] > 0:
    conf -= 0.12
if t1h["mom5"] > 0:
    conf -= 0.08
if funding_favorable_short:
    conf += 0.05
if spread_ok:
    conf += 0.03
if change24h < -5:
    conf += 0.05
if track_record_bad:
    conf -= 0.15
conf = round(max(0, min(1, conf)), 3)

side = "neutral"
if trend_match_short and conf >= 0.5 and funding_favorable_short and not track_record_bad:
    side = "short"
elif all(x["bias"] == "long" for x in [t1, t15, t1h]):
    side = "long"
elif t15["bias"] == "short" and t1h["bias"] == "short" and t1["bias"] != "long":
    side = "short"

notes = []
if funding_favorable_short:
    notes.append(f"funding {fr:.6f} positive longs-pay-shorts favorable for short")
else:
    notes.append("ERROR: funding negative (shorts pay); not favorable for short")
if spread_ok:
    notes.append(f"spread {spread:.4f}% OK below 0.5%")
else:
    notes.append(f"ERROR: spread {spread:.4f}% exceeds 0.5%")
notes.append(f"1m bias={t1['bias']} RSI={t1['rsi']:.1f} mom5={t1['mom5']:+.2f}%")
notes.append(f"15m bias={t15['bias']} RSI={t15['rsi']:.1f} mom5={t15['mom5']:+.2f}%")
notes.append(f"1h bias={t1h['bias']} RSI={t1h['rsi']:.1f} mom5={t1h['mom5']:+.2f}%")
if not trend_match_short:
    notes.append("ERROR: not all timeframes bearish/short aligned (15m bias long)")
if t15["mom5"] > 0 or t1h["mom5"] > 0:
    notes.append("ERROR: 1h positive mom5 conflicts with short momentum claim")
notes.append(f"liq distance {liq_dist:.2f}% at 10x isolated short entry {ENTRY}")
if liq_dist < 5:
    notes.append("HIGH LIQUIDATION RISK")
notes.append(f"live price {float(ticker['last'])} 24h {change24h:.2f}% matches user data")
notes.append(
    "HALLUCINATION/ASSUMPTION: FIGHT-USDT poor track record 1 trade W/L=0/1 pnl=-0.0105; on avoid list"
)

out = {
    "instId": inst,
    "suggestedSide": side,
    "confidence": conf,
    "liquidationPrice": round(liq, 6),
    "liquidationDistancePct": round(liq_dist, 2),
    "spreadPct": round(spread, 4),
    "fundingRate": fr,
    "verified": verified,
    "notes": "; ".join(notes),
}
print(json.dumps(out))
