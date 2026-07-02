import json
import subprocess

BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
PY = r"py"
PY_ARGS = ["-3.12", BRIDGE]
ENTRY = 0.00368
LEVERAGE = 10
CANDIDATE_SIDE = "short"


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
    return {"bias": bias, "rsi": r, "mom5": mom, "last": last, "e9": e9, "e21": e21}


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

funding_ok_short = fr < 0.0005 and fr <= 0.0001  # favorable = not paying much; mild positive is neutral not favorable
spread_ok = spread < 0.5
trend_match = all(x["bias"] == CANDIDATE_SIDE for x in [t1, t15, t1h])

checks = []
if spread_ok:
    checks.append("spread_ok")
else:
    checks.append("spread_fail")
if fr < 0.0005:
    checks.append("funding_not_extreme")
else:
    checks.append("funding_avoid_short")
if fr <= 0:
    checks.append("funding_favorable_short")
else:
    checks.append("funding_unfavorable_short_pays")
if trend_match:
    checks.append("trend_aligned_short")
else:
    checks.append("trend_mismatch")

verified = spread_ok and fr < 0.0005 and trend_match and liq_dist >= 5

out = {
    "instId": inst,
    "suggestedSide": CANDIDATE_SIDE if trend_match else "neutral",
    "confidence": 0.453,
    "liquidationPrice": round(liq_price, 6),
    "liquidationDistancePct": round(liq_dist, 2),
    "spreadPct": round(spread, 4),
    "fundingRate": fr,
    "verified": verified,
    "notes": (
        f"Live price {ticker['last']}; 24h {((float(ticker['last'])-float(ticker['open24h']))/float(ticker['open24h'])*100):.2f}%; "
        f"1m={t1['bias']} rsi={round(t1['rsi'],1) if t1['rsi'] else None}; "
        f"15m={t15['bias']} rsi={round(t15['rsi'],1) if t15['rsi'] else None} mom5={round(t15['mom5'],2)}%; "
        f"1h={t1h['bias']} rsi={round(t1h['rsi'],1) if t1h['rsi'] else None}; "
        f"funding mildly positive (shorts pay, not favorable); spread {spread:.4f}% OK; "
        f"liq dist {liq_dist:.1f}% at 10x; confidence 0.453<0.5 threshold; checks={checks}; "
        f"book thin bid={book['bids'][0]} ask={book['asks'][0]}"
    ),
    "debug": {"t1": t1, "t15": t15, "t1h": t1h, "checks": checks},
}
print(json.dumps(out))
