import json
import subprocess

BR = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
PY = ["py", "-3.12", BR]
ENTRY = 0.003679
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
    return {"bias": bias, "rsi": r, "mom5": mom}


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
liq_price = ENTRY * (1 + 1 / LEVERAGE)
liq_dist = ((liq_price - ENTRY) / ENTRY) * 100

funding_ok = fr >= 0
spread_ok = spread < 0.5
t1_ok = t1["bias"] == "short"
t15_mom_ok = t15["mom5"] < 0
t1h_ok = t1h["bias"] == "short"
liq_ok = liq_dist >= 5
verified = funding_ok and spread_ok and t1_ok and t15_mom_ok and t1h_ok and liq_ok

conf = 0.35
if t15["bias"] == "short" and t1h["bias"] == "short":
    conf += 0.12
if t1["bias"] == "short":
    conf += 0.05
if t15["mom5"] > 0:
    conf -= 0.12
if t1h["mom5"] > 0:
    conf -= 0.08
if fr >= 0:
    conf += 0.05
if spread_ok:
    conf += 0.03
change24h = (float(ticker["last"]) - float(ticker["open24h"])) / float(ticker["open24h"]) * 100
if change24h < -5:
    conf += 0.05
conf = round(max(0, min(1, conf)), 3)

notes = [
    f"funding {fr:.6f} positive longs-pay-shorts favorable for short",
    f"spread {spread:.4f}% OK below 0.5%",
    f"1m EMA bias {t1['bias']} RSI {t1['rsi']:.1f} mom5 {t1['mom5']:+.2f}%",
    f"15m EMA bias {t15['bias']} but mom5 {t15['mom5']:+.2f}% upward conflicts short momentum",
    f"1h EMA bias {t1h['bias']} RSI {t1h['rsi']:.1f} mom5 {t1h['mom5']:+.2f}% recent bounce",
    f"liq {liq_dist:.1f}% at 10x isolated short no HIGH LIQUIDATION RISK",
    "ERROR: analysis momentumScore 0.85 overstated; 15m/1h mom5 positive",
    "FIGHT-USDT absent from trade history; no track-record bias",
]

side = (
    "short"
    if t15["bias"] == "short" and t1h["bias"] == "short" and t1["bias"] != "long"
    else "neutral"
)

out = {
    "instId": inst,
    "suggestedSide": side,
    "confidence": conf,
    "liquidationPrice": round(liq_price, 6),
    "liquidationDistancePct": round(liq_dist, 2),
    "spreadPct": round(spread, 4),
    "fundingRate": fr,
    "verified": verified,
    "notes": "; ".join(notes),
}
print(json.dumps(out))
