import json
import subprocess

BR = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
PY = ["py", "-3.12", BR]
inst = "FIGHT-USDT"
ENTRY = 0.00369
LEV = 10


def fetch(m, a):
    p = subprocess.run(
        PY + [m, json.dumps(a)],
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


def ema(v, p):
    if len(v) < p:
        return None
    k = 2 / (p + 1)
    val = sum(v[:p]) / p
    for i in range(p, len(v)):
        val = v[i] * k + val * (1 - k)
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
    mom = ((closes[-1] - closes[-5]) / closes[-5] * 100) if len(closes) >= 5 else 0
    return {"bias": bias, "mom5": mom, "last": last}


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

liq = ENTRY * (1 + 1 / LEV)
liq_dist = ((liq - ENTRY) / ENTRY) * 100

funding_ok_short = fr <= 0
spread_ok = spread < 0.5
trend_short_all = all(x["bias"] == "short" for x in [t1, t15, t1h])
verified = spread_ok and funding_ok_short and trend_short_all and liq_dist >= 5

price = float(ticker["last"])
chg = (price - float(ticker["open24h"])) / float(ticker["open24h"]) * 100

notes = []
if not funding_ok_short:
    notes.append(
        f"HALLUCINATION: funding {fr:.6f} positive (longs receive); prior claim 'favors shorts' is false"
    )
else:
    notes.append(f"funding {fr:.6f} favorable for short")
if not trend_short_all:
    notes.append(
        f"ERROR: MTF not aligned for short (1m={t1['bias']}, 15m={t15['bias']}, 1h={t1h['bias']}); prior claim '1m bullish' is false—1m is {t1['bias']}"
    )
else:
    notes.append("all timeframes bearish aligned")
if spread_ok:
    notes.append(f"spread {spread:.4f}% OK (<0.5%)")
else:
    notes.append(f"ERROR: spread {spread:.4f}% exceeds 0.5%")
notes.append(f"liq {liq:.6f} distance {liq_dist:.1f}% at 10x isolated short entry {ENTRY}")
if liq_dist < 5:
    notes.append("HIGH LIQUIDATION RISK")
notes.append(f"live price {price} 24h {chg:.2f}% vol {ticker.get('volCurrency24h', '?')}")
notes.append("FIGHT-USDT poor track record 0W/1L pnl=-0.0105; skip per trade learning")

conf = 0.25
if t15["bias"] == "short" and t1h["bias"] == "short":
    conf += 0.12
if t1["bias"] == "short":
    conf += 0.05
else:
    conf -= 0.15
if fr > 0:
    conf -= 0.1
if chg < -5:
    conf += 0.05
conf = round(max(0, min(1, conf)), 3)

side = "neutral"
if trend_short_all and funding_ok_short and conf >= 0.5:
    side = "short"
elif all(x["bias"] == "long" for x in [t1, t15, t1h]):
    side = "long"

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
