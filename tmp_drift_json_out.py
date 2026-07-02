import json
import subprocess
import sys

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
BRIDGE = r"C:\Users\mknig\owl-swarm\blofin_bridge.py"
CWD = r"C:\Users\mknig\owl-swarm"
INST = "DRIFT-USDT"


def fetch(method, args):
    p = subprocess.run(
        [PY, BRIDGE, method, json.dumps(args)],
        capture_output=True,
        text=True,
        cwd=CWD,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr + p.stdout)
    return json.loads(p.stdout.strip())


def parse_candles(raw):
    return [
        {"close": float(c[4]), "high": float(c[2]), "low": float(c[3])}
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
    chg = (closes[-1] - closes[0]) / closes[0] * 100 if closes else 0
    return {
        "rsi": round(r, 2) if r else None,
        "tech": round(tech, 3),
        "bias": bias,
        "chg": round(chg, 3),
    }


fund = fetch("get_funding_rate", {"inst_id": INST})
book = fetch("get_order_book", {"inst_id": INST})
ticker = fetch("get_ticker", {"inst_id": INST})[0]
c1m = parse_candles(
    fetch("get_candles", {"inst_id": INST, "bar": "1m", "limit": "50"})
)
c15 = parse_candles(
    fetch("get_candles", {"inst_id": INST, "bar": "15m", "limit": "30"})
)
c1h = parse_candles(
    fetch("get_candles", {"inst_id": INST, "bar": "1H", "limit": "24"})
)
ta1, ta15, ta1h = ta(c1m), ta(c15), ta(c1h)

fr = float(fund["fundingRate"])
bid = float(book["bids"][0][0])
ask = float(book["asks"][0][0])
spread = (ask - bid) / ((ask + bid) / 2) * 100
price = float(ticker["last"])
change24h = float(ticker["chg_pct"])
vol24h = float(ticker["volCurrency24h"])

biases = [ta1["bias"], ta15["bias"], ta1h["bias"]]
long_c = biases.count("long")
short_c = biases.count("short")
trend = "bullish" if long_c >= 2 else ("bearish" if short_c >= 2 else "mixed")
mom = round(ta1["tech"] * 0.35 + ta15["tech"] * 0.35 + ta1h["tech"] * 0.3, 3)

conf = mom
if spread >= 0.5:
    conf -= 0.25
if fr > 0.0005:
    conf -= 0.2
if long_c == 3 or short_c == 3:
    conf += 0.08
else:
    conf -= 0.1
conf = max(0, min(1, round(conf, 3)))

if fr > 0.0005:
    fb = "avoid_long"
elif fr < -0.0005:
    fb = "avoid_short"
elif fr > 0:
    fb = "longs_pay"
elif fr < 0:
    fb = "shorts_pay"
else:
    fb = "neutral"

levels = sorted(
    set(
        [
            round(min(c["low"] for c in c1h), 5),
            round(max(c["high"] for c in c1h), 5),
            round(min(c["low"] for c in c15), 5),
            round(max(c["high"] for c in c15), 5),
            round(price, 5),
        ]
    )
)

tech_sum = (
    f"1m {ta1['bias']} RSI {ta1['rsi']} ({ta1['chg']:+.2f}% window); "
    f"15m {ta15['bias']} RSI {ta15['rsi']}; "
    f"1h {ta1h['bias']} RSI {ta1h['rsi']}; "
    f"spread {spread:.3f}%; funding {fr:.6f}; "
    "15m+1h bullish with 1m oversold pullback, mixed alignment"
)

spread_ok = spread < 0.5
if conf >= 0.5 and spread_ok and long_c >= 2 and fr <= 0.0005:
    side = "long"
elif conf >= 0.5 and spread_ok and short_c >= 2 and fr >= -0.0005:
    side = "short"
else:
    side = "neutral"
    if conf >= 0.5 and not (
        spread_ok
        and (
            (long_c >= 2 and fr <= 0.0005)
            or (short_c >= 2 and fr >= -0.0005)
        )
    ):
        conf = min(conf, 0.49)

out = {
    "instId": INST,
    "price": price,
    "change24h": change24h,
    "volume24h": vol24h,
    "trend": trend,
    "momentumScore": mom,
    "keyLevels": levels,
    "fundingRate": fr,
    "fundingBias": fb,
    "spreadPct": round(spread, 4),
    "technicalSummary": tech_sum,
    "suggestedSide": side,
    "confidence": conf,
}

print(json.dumps(out))
