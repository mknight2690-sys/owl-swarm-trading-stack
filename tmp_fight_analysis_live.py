import json
import subprocess

BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
PY = ["py", "-3.12", BRIDGE]
INST = "FIGHT-USDT"


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


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - 100 / (1 + rs), 2)


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
    return {
        "bias": bias,
        "mom5": round(mom5, 3),
        "chg": round(chg, 3),
        "last": last,
        "rsi": rsi(closes),
    }


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
price = float(ticker["last"])
open24 = float(ticker["open24h"])
chg24 = (price - open24) / open24 * 100
vol = float(ticker.get("volCurrency24h", 0))

res = max(c["high"] for c in c1h)
sup = min(c["low"] for c in c1h)

if fr > 0.0005:
    fb = "avoid_long"
elif fr < -0.0005:
    fb = "avoid_short"
elif fr > 0:
    fb = "favor_short"
elif fr < 0:
    fb = "favor_long"
else:
    fb = "neutral"

scores = {"long": 1, "short": -1, "neutral": 0}
mom = scores[t1["bias"]] * 0.2 + scores[t15["bias"]] * 0.35 + scores[t1h["bias"]] * 0.45
if t1["rsi"]:
    if t1["rsi"] > 70:
        mom -= 0.1
    elif t1["rsi"] < 30:
        mom += 0.1
mom = round(max(-1, min(1, mom)), 3)

if all(x["bias"] == "short" for x in [t1, t15, t1h]):
    trend = "bearish"
elif all(x["bias"] == "long" for x in [t1, t15, t1h]):
    trend = "bullish"
elif t15["bias"] == t1h["bias"]:
    trend = f"{t15['bias']}_biased_mixed"
else:
    trend = "mixed"

conf = 0.35
if t15["bias"] == "short" and t1h["bias"] == "short":
    conf += 0.15
if t1["bias"] == "short":
    conf += 0.1
elif t1["bias"] == "long":
    conf -= 0.15
if 0 < fr <= 0.0005:
    conf += 0.05
if fr > 0.0005:
    conf -= 0.2
if spread >= 0.5:
    conf -= 0.25
if chg24 < -5:
    conf += 0.05
conf -= 0.15
conf = round(max(0, min(1, conf)), 3)

side = None
if conf >= 0.5:
    if trend == "bearish" and fb != "avoid_short" and spread < 0.5:
        side = "short"
    elif trend == "bullish" and fb != "avoid_long" and spread < 0.5:
        side = "long"
    elif t15["bias"] == "short" and t1h["bias"] == "short" and fb != "avoid_short":
        side = "short"

tech = (
    f"1m RSI {t1['rsi']} {t1['bias']} ({t1['chg']:+.2f}%); "
    f"15m {t15['bias']} mom5 {t15['mom5']:+.2f}%; "
    f"1h {t1h['bias']} ({t1h['chg']:+.2f}%)"
)

out = {
    "instId": INST,
    "price": price,
    "change24h": round(chg24, 3),
    "volume24h": vol,
    "trend": trend,
    "momentumScore": mom,
    "keyLevels": [round(sup, 6), round(price, 6), round(res, 6)],
    "fundingRate": fr,
    "fundingBias": fb,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech,
    "confidence": conf,
}
if side:
    out["suggestedSide"] = side

print(json.dumps(out))
