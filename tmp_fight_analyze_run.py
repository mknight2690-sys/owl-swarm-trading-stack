import json
import os
import subprocess
import tempfile

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
CWD = r"C:\Users\mknig\owl-swarm"
INST = "FIGHT-USDT"
PRE_SHORT = 0.854
PRE_LONG = 0.404


def bridge(method, args):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    f.write(json.dumps(args))
    f.close()
    out = subprocess.check_output([PY, "blofin_bridge.py", method, "@" + f.name], cwd=CWD)
    os.unlink(f.name)
    return json.loads(out)


ticker = bridge("get_ticker", {"inst_id": INST})[0]
fund = bridge("get_funding_rate", {"inst_id": INST})
ob = bridge("get_order_book", {"inst_id": INST})
c15 = bridge("get_candles", {"inst_id": INST, "bar": "15m", "limit": "100"})


def parse(raw):
    return [
        {"ts": int(x[0]), "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])}
        for x in reversed(raw)
    ]


d15 = parse(c15)
closes = [x["c"] for x in d15]
price = float(ticker["last"])
gains, losses = [], []
for i in range(1, len(closes)):
    ch = closes[i] - closes[i - 1]
    gains.append(max(ch, 0))
    losses.append(max(-ch, 0))
avg_gain = sum(gains[-14:]) / 14
avg_loss = sum(losses[-14:]) / 14
rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss else 100


def ema(vals, n):
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for v in vals[n:]:
        e = v * k + e * (1 - k)
    return e


ema9 = ema(closes, 9)
ema21 = ema(closes, 21)
mom_1h = (closes[-1] - closes[-5]) / closes[-5] * 100
mom_4h = (closes[-1] - closes[-17]) / closes[-17] * 100

low24 = float(ticker["low24h"])
high24 = float(ticker["high24h"])
support = min(x["l"] for x in d15[-20:])
resistance = max(x["h"] for x in d15[-20:])
pivot = (high24 + low24 + price) / 3

fr = float(fund["fundingRate"])
open24 = float(ticker["open24h"])
chg24 = float(ticker.get("chg_pct") or (price - open24) / open24 * 100)
vol24 = int(float(ticker["volCurrency24h"]))

if ema9 < ema21 and price < ema21:
    trend = "bearish"
elif ema9 > ema21 and price > ema21:
    trend = "bullish"
else:
    trend = "neutral"

momentum = 0.35 if rsi < 45 else (0.65 if rsi > 55 else 0.5)

if fr > 0.0001:
    fb = "mild_long_crowding"
elif fr < -0.0001:
    fb = "mild_short_crowding"
else:
    fb = "neutral"

factors = [
    PRE_SHORT,
    0.70 if ema9 < ema21 else 0.35,
    0.70 if chg24 < -5 else 0.45,
    0.65 if price < pivot else 0.45,
    0.45 if abs(price - support) / price < 0.008 else 0.55,
    0.50 if rsi < 35 else (0.55 if rsi < 45 else 0.5),
    0.60 if mom_4h < 0 else 0.45,
    0.45 if mom_1h > 0 else 0.60,
]
confidence = round(sum(factors) / len(factors), 3)
suggested = "short" if confidence >= 0.5 and PRE_SHORT > PRE_LONG else "long"

bid_sz = sum(float(b[1]) for b in ob.get("bids", [])[:10])
ask_sz = sum(float(a[1]) for a in ob.get("asks", [])[:10])
ob_imb = (bid_sz - ask_sz) / (bid_sz + ask_sz) if bid_sz + ask_sz else 0
ob_desc = "bid-side skew" if ob_imb > 0.05 else ("ask-side skew" if ob_imb < -0.05 else "balanced")
near_sup = abs(price - support) / price < 0.008
sup_word = "at" if near_sup else "above"
ema_dir = ">" if ema9 > ema21 else "<"

technical_summary = (
    f"{INST} {chg24:.1f}% in 24h from {low24:.4f} low to {high24:.4f} high; "
    f"price {price:.4f} {sup_word} session support {support:.4f} "
    f"with RSI {rsi:.1f}, EMA9 {ema_dir} EMA21. "
    f"Funding positive ({fr * 100:.4f}%) slightly favors shorts; order book {ob_desc} "
    f"(imbalance {ob_imb:+.2f}). 1h momentum {mom_1h:+.2f}%, 4h {mom_4h:+.2f}%; "
    f"resistance {resistance:.4f}, pivot {pivot:.4f}. "
    f"Pre-rank short_score {PRE_SHORT} vs long_score {PRE_LONG}."
)

report = {
    "instId": INST,
    "price": round(price, 6),
    "change24h": round(chg24, 3),
    "volume24h": vol24,
    "trend": trend,
    "momentumScore": round(momentum, 3),
    "keyLevels": [
        {"type": "support", "price": round(support, 6)},
        {"type": "resistance", "price": round(resistance, 6)},
        {"type": "pivot", "price": round(pivot, 6)},
        {"type": "24h_low", "price": round(low24, 6)},
        {"type": "24h_high", "price": round(high24, 6)},
    ],
    "fundingRate": round(fr, 6),
    "fundingBias": fb,
    "technicalSummary": technical_summary,
    "suggestedSide": suggested,
    "confidence": confidence,
}
print(json.dumps(report))
