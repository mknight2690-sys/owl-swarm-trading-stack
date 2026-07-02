import json
import subprocess
import sys

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
CWD = r"C:\Users\mknig\owl-swarm"
INST = "DRIFT-USDT"
ENTRY = 0.02144
LEV = 10


def fetch(method, args):
    p = subprocess.run(
        [PY, BRIDGE, method, json.dumps(args)],
        capture_output=True,
        text=True,
        cwd=CWD,
    )
    if p.returncode != 0:
        print(p.stderr, file=sys.stderr)
        print(p.stdout, file=sys.stderr)
        raise RuntimeError(method)
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
        "last": last,
        "rsi": round(r, 2) if r else None,
        "trend": trend,
        "mom": mom,
        "tech": tech,
        "bias": bias,
        "mom_pct": round(mom_pct, 3),
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
bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100
price = float(ticker["last"])

liq = ENTRY * (1 - 1 / LEV)
liq_dist = (ENTRY - liq) / ENTRY * 100

candidate_side = "long"
checks = {
    "funding_favorable_long": fr <= 0.0005,
    "spread_under_half_pct": spread < 0.5,
    "1m_trend_matches_long": ta1["bias"] == "long",
    "15m_momentum_bullish": ta15["bias"] == "long"
    or (ta15["mom_pct"] > 0 and (ta15["rsi"] or 50) > 50),
    "1h_trend_bullish": ta1h["bias"] == "long",
}
all_pass = all(checks.values())

notes = []
if not checks["1m_trend_matches_long"]:
    notes.append(f"1m bearish RSI {ta1['rsi']} bias {ta1['bias']} conflicts with long")
if not checks["15m_momentum_bullish"]:
    notes.append(
        f"15m weak RSI {ta15['rsi']} mom {ta15['mom_pct']:+.2f}% bias {ta15['bias']}"
    )
if checks["1h_trend_bullish"]:
    notes.append(f"1h bullish RSI {ta1h['rsi']} supports long")
else:
    notes.append(f"1h not bullish RSI {ta1h['rsi']} bias {ta1h['bias']}")
if fr <= 0.0005:
    notes.append(f"funding {fr:.6f} neutral OK for long")
else:
    notes.append(f"funding {fr:.6f} expensive for long")
if spread < 0.5:
    notes.append(f"spread {spread:.3f}% OK")
else:
    notes.append(f"spread {spread:.3f}% too wide")
notes.append("DRIFT track record 1W/0L +0.3262 PnL")
if liq_dist < 5:
    notes.append("HIGH LIQUIDATION RISK")
else:
    notes.append(f"liq distance {liq_dist:.1f}% at 10x")

conf = ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3
if not all_pass:
    conf = min(conf, 0.45)

if all_pass:
    side = candidate_side
elif ta1h["bias"] == "long" and ta1["bias"] != "long":
    side = "neutral"
else:
    side = ta1["bias"] if ta1["bias"] != "neutral" else "neutral"

out = {
    "instId": INST,
    "suggestedSide": side,
    "confidence": round(max(0, min(1, conf)), 3),
    "liquidationPrice": round(liq, 5),
    "liquidationDistancePct": round(liq_dist, 2),
    "spreadPct": round(spread, 4),
    "fundingRate": fr,
    "verified": all_pass,
    "notes": "; ".join(notes),
}
print(json.dumps(out))
