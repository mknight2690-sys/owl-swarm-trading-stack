import json
import subprocess

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
INST = "UB-USDT"
ENTRY = 0.12051
LEV = 10
CLAIMED_PRICE = 0.12051
CLAIMED_CHANGE = 49.017
CLAIMED_VOL = 27503000
CLAIMED_SIDE = "long"


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
    return {
        "rsi": round(r, 2) if r else None,
        "trend": trend,
        "mom": mom,
        "tech": tech,
        "bias": bias,
        "last": last,
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

liq = ENTRY * (1 - 1 / LEV)
liq_dist = (ENTRY - liq) / ENTRY * 100

favorable_long = fr <= 0.0005
spread_ok = spread < 0.5

conf = ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3
if spread > 0.5:
    conf -= 0.25
if fr > 0.0005:
    conf -= 0.2
if ta1["bias"] == "long" and ta15["bias"] == "long" and ta1h["bias"] == "long":
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

issues = []
if not spread_ok:
    issues.append(f"spread {spread:.4f}% exceeds 0.5% threshold")
if CLAIMED_SIDE == "long" and not favorable_long:
    issues.append(f"funding rate {fr:.6f} ({fr * 100:.4f}%) unfavorable for long (longs pay)")
if CLAIMED_SIDE == "long" and ta1["bias"] != "long":
    issues.append(f"1m trend {ta1['bias']} conflicts with long")
if CLAIMED_SIDE == "long" and ta15["bias"] == "short":
    issues.append(f"15m momentum bearish ({ta15['bias']})")
if CLAIMED_SIDE == "long" and ta1h["bias"] == "short":
    issues.append(f"1h trend bearish ({ta1h['bias']})")
if liq_dist < 5:
    issues.append("HIGH LIQUIDATION RISK")
if abs(price - CLAIMED_PRICE) / CLAIMED_PRICE > 0.01:
    issues.append(f"claimed price {CLAIMED_PRICE} vs live {price:.5f}")
if abs(change24h - CLAIMED_CHANGE) > 2.0:
    issues.append(f"claimed 24h change {CLAIMED_CHANGE}% vs live {change24h:.2f}%")
if abs(vol - CLAIMED_VOL) / CLAIMED_VOL > 0.05:
    issues.append(f"claimed volume {CLAIMED_VOL} vs live {vol:.0f}")

verified = len(issues) == 0

if not favorable_long or not spread_ok:
    suggested = "neutral"
elif conf >= 0.5:
    suggested = ta1["bias"] if ta1["tech"] >= ta15["tech"] else ta15["bias"]
    if suggested == "neutral":
        suggested = "long" if change24h > 0 else "short"
    if suggested == "long" and not favorable_long:
        suggested = "neutral"
else:
    suggested = "neutral"

note_bits = [
    f"1m {ta1['bias']} RSI {ta1['rsi']}",
    f"15m {ta15['bias']} RSI {ta15['rsi']}",
    f"1h {ta1h['bias']} RSI {ta1h['rsi']}",
    f"live price {price:.5f} 24h {change24h:.2f}% vol {vol:.0f}",
]
if issues:
    note_bits.extend(issues)
else:
    note_bits.append("All checks pass")

out = {
    "instId": INST,
    "suggestedSide": suggested,
    "confidence": conf,
    "liquidationPrice": round(liq, 6),
    "liquidationDistancePct": round(liq_dist, 2),
    "spreadPct": round(spread, 4),
    "fundingRate": fr,
    "verified": verified,
    "notes": "; ".join(note_bits),
}
print(json.dumps(out))
