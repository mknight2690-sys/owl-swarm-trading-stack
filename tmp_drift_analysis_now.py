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
    out = p.stdout.strip()
    if p.returncode != 0:
        raise RuntimeError(p.stderr + p.stdout)
    return json.loads(out)


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


def trend_label(candles):
    closes = [c["close"] for c in candles]
    last = closes[-1]
    e9, e21 = ema(closes, 9), ema(closes, 21)
    r = rsi(closes)
    if e9 and e21:
        if e9 > e21 and last > e21:
            t = "bullish"
        elif e9 < e21 and last < e21:
            t = "bearish"
        elif e9 > e21:
            t = "mild_bullish"
        else:
            t = "mild_bearish"
    else:
        t = "neutral"
    return t, last, r, e9, e21


funding = fetch("get_funding_rate", {"inst_id": INST})
book = fetch("get_order_book", {"inst_id": INST})
c1m = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1m", "limit": 50}))
c15m = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "15m", "limit": 30}))
c1h = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1h", "limit": 24}))

# funding rate extraction
fr = funding
if isinstance(funding, list) and funding:
    fr = funding[0]
if isinstance(fr, dict):
    funding_rate = float(fr.get("fundingRate", fr.get("funding_rate", 0)))
else:
    funding_rate = float(fr)

# order book spread
bids = book.get("bids", [])
asks = book.get("asks", [])
best_bid = float(bids[0][0]) if bids else 0
best_ask = float(asks[0][0]) if asks else 0
mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
spread_pct = ((best_ask - best_bid) / mid * 100) if mid else 999

t1m, p1m, r1m, _, _ = trend_label(c1m)
t15m, p15m, r15m, _, _ = trend_label(c15m)
t1h, p1h, r1h, _, _ = trend_label(c1h)

# key levels from 1h and 15m
highs_1h = [c["high"] for c in c1h]
lows_1h = [c["low"] for c in c1h]
highs_15m = [c["high"] for c in c15m]
lows_15m = [c["low"] for c in c15m]
key_levels = sorted(set([
    round(max(highs_1h), 5),
    round(min(lows_1h), 5),
    round(max(highs_15m), 5),
    round(min(lows_15m), 5),
    round(p1m, 5),
]))

result = {
    "funding": funding,
    "funding_rate": funding_rate,
    "book": {"best_bid": best_bid, "best_ask": best_ask, "spread_pct": spread_pct},
    "1m": {"trend": t1m, "price": p1m, "rsi": r1m},
    "15m": {"trend": t15m, "price": p15m, "rsi": r15m},
    "1h": {"trend": t1h, "price": p1h, "rsi": r1h},
    "key_levels": key_levels,
}
print(json.dumps(result, indent=2))
