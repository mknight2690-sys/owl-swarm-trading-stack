import json
import subprocess

BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
PY = [r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe", BRIDGE]
INST = "SAGA-USDT"
ENTRY = 0.01518
LEVERAGE = 10
CLAIMED_PRICE = 0.01518
CLAIMED_CHANGE = 10.803
CLAIMED_VOLUME = 10426292


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
    chg = (closes[-1] - closes[0]) / closes[0] * 100 if closes else 0
    mom5 = ((closes[-1] - closes[-5]) / closes[-5] * 100) if len(closes) >= 5 else 0
    return {"bias": bias, "rsi": r, "chg": chg, "mom5": mom5, "last": last}


fund = fetch("get_funding_rate", {"inst_id": INST})
book = fetch("get_order_book", {"inst_id": INST})
ticker = fetch("get_ticker", {"inst_id": INST})
if isinstance(ticker, list):
    ticker = ticker[0]

c1m = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"}))
c15 = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"}))
c1h = parse_candles(fetch("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"}))

t1, t15, t1h = trend_bias(c1m), trend_bias(c15), trend_bias(c1h)

fr = float(fund["fundingRate"])
bid = float(book["bids"][0][0])
ask = float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100

price = float(ticker["last"])
change24h = (price - float(ticker["open24h"])) / float(ticker["open24h"]) * 100
volume24h = float(ticker.get("vol24h", ticker.get("volCcy24h", 0)))

liq_price = ENTRY * (1 - 1 / LEVERAGE)
liq_dist = ((ENTRY - liq_price) / ENTRY) * 100

funding_favorable_long = fr <= 0.0005
spread_ok = spread < 0.5
trend_match_long = all(x["bias"] == "long" for x in [t1, t15, t1h])
track_record_good = True  # SAGA 2W/0L +0.2432

verified = (
    spread_ok
    and funding_favorable_long
    and trend_match_long
    and liq_dist >= 5
    and track_record_good
)

conf = 0.55
if trend_match_long:
    conf += 0.15
elif t15["bias"] == "long" and t1h["bias"] == "long":
    conf += 0.08
else:
    conf -= 0.15
if t1["bias"] != "long":
    conf -= 0.12
if not funding_favorable_long:
    conf -= 0.1
if not spread_ok:
    conf -= 0.15
if liq_dist < 5:
    conf -= 0.2
if track_record_good:
    conf += 0.05
conf = round(max(0, min(1, conf)), 3)

side = "neutral"
if trend_match_long and conf >= 0.5 and funding_favorable_long and spread_ok:
    side = "long"
elif all(x["bias"] == "short" for x in [t1, t15, t1h]):
    side = "short"
elif t15["bias"] == "long" and t1h["bias"] == "long" and t1["bias"] != "short":
    side = "long"
elif t1["bias"] == "short":
    side = "neutral"

notes_parts = []
if abs(price - CLAIMED_PRICE) / CLAIMED_PRICE > 0.005:
    notes_parts.append(f"ERROR: live price {price:.5f} differs from claimed {CLAIMED_PRICE}")
if abs(change24h - CLAIMED_CHANGE) > 1.0:
    notes_parts.append(f"ERROR: live 24h change {change24h:.2f}% vs claimed {CLAIMED_CHANGE}%")
if abs(volume24h - CLAIMED_VOLUME) / CLAIMED_VOLUME > 0.05:
    notes_parts.append(f"WARN: live volume {volume24h:.0f} vs claimed {CLAIMED_VOLUME}")
if fr > 0:
    notes_parts.append(f"funding positive {fr:.6f} (longs pay shorts); weakly favorable not free carry")
elif fr <= 0:
    notes_parts.append(f"funding {fr:.6f} favorable for long (shorts pay or neutral)")
else:
    notes_parts.append(f"funding {fr:.6f}")
if not trend_match_long:
    notes_parts.append(
        f"ERROR: trend mismatch for long (1m={t1['bias']} chg={t1['chg']:.2f}%, "
        f"15m={t15['bias']} chg={t15['chg']:.2f}%, 1h={t1h['bias']} chg={t1h['chg']:.2f}%)"
    )
else:
    notes_parts.append("all timeframes bullish/long aligned")
if spread_ok:
    notes_parts.append(f"spread {spread:.4f}% OK")
else:
    notes_parts.append(f"ERROR: spread {spread:.4f}% >= 0.5%")
if liq_dist < 5:
    notes_parts.append(f"HIGH LIQUIDATION RISK: liq distance {liq_dist:.2f}%")
else:
    notes_parts.append(f"liq distance {liq_dist:.2f}% at 10x")
if track_record_good:
    notes_parts.append("SAGA track record 2W/0L +0.2432 pnl favorable")

out = {
    "instId": INST,
    "suggestedSide": side,
    "confidence": conf,
    "liquidationPrice": round(liq_price, 6),
    "liquidationDistancePct": round(liq_dist, 2),
    "spreadPct": round(spread, 4),
    "fundingRate": fr,
    "verified": verified,
    "notes": "; ".join(notes_parts),
    "_debug": {
        "livePrice": price,
        "change24h": round(change24h, 2),
        "volume24h": volume24h,
        "t1m": t1,
        "t15m": t15,
        "t1h": t1h,
        "bid": bid,
        "ask": ask,
    },
}

print(json.dumps(out))
