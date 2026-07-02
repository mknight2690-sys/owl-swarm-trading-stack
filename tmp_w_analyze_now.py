import json
from pathlib import Path

ROOT = Path(r"C:\Users\mknig\owl-swarm")

def load(name):
    return json.loads(ROOT.joinpath(name).read_text(encoding="utf-8-sig"))

def closes(candles):
    return [float(c[4]) for c in reversed(candles)]

def rsi(cl, period=14):
    if len(cl) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return 100 - (100 / (1 + ag / al))

def trend(cl, n=5):
    if len(cl) < n:
        return "neutral"
    recent = cl[-n:]
    if recent[-1] > recent[0] * 1.002:
        return "bullish"
    if recent[-1] < recent[0] * 0.998:
        return "bearish"
    return "neutral"

def momentum_score(candles):
    cl = closes(candles)
    r = rsi(cl)
    t = trend(cl)
    chg = (cl[-1] - cl[0]) / cl[0] * 100 if cl[0] else 0
    score = 0.5
    if r is not None:
        score += (r - 50) / 100
    if t == "bullish":
        score += 0.15
    elif t == "bearish":
        score -= 0.15
    score += min(max(chg / 10, -0.2), 0.2)
    return round(max(0, min(1, score)), 3), r, t

fund = json.loads('{"instId": "W-USDT", "fundingRate": "0.00006754465453742726", "fundingTime": "1782100800000"}')
ob = {"asks": [["0.01157", "52437"]], "bids": [["0.01156", "148538"]], "ts": "1782089529590"}
ticker = {"instId": "W-USDT", "last": "0.01157", "vol24h": "28809332", "chg_pct": 12.221, "high24h": "0.01174", "low24h": "0.01026", "open24h": "0.01031"}

c1m = load("tmp_w_1m_out.json")
c15 = load("tmp_w_15m_out.json")
c1h = load("tmp_w_1h_out.json")

fund_rate = float(fund["fundingRate"])
bid = float(ob["bids"][0][0])
ask = float(ob["asks"][0][0])
mid = (bid + ask) / 2
spread = (ask - bid) / mid * 100

m1, r1, t1 = momentum_score(c1m)
m15, r15, t15 = momentum_score(c15)
m1h, r1h, t1h = momentum_score(c1h)

cl1h = closes(c1h)
recent_1h = c1h[:6]
support = min(float(c[3]) for c in recent_1h)
resistance = max(float(c[2]) for c in recent_1h)
pivot = round((support + resistance + float(c1h[0][4])) / 3, 5)

trends = [t1, t15, t1h]
bull = trends.count("bullish")
bear = trends.count("bearish")
overall = "bullish" if bull >= 2 else ("bearish" if bear >= 2 else "mixed")
avg_mom = round((m1 + m15 + m1h) / 3, 3)

funding_bias = "neutral"
if fund_rate > 0.0001:
    funding_bias = "longs_pay"
elif fund_rate < -0.0001:
    funding_bias = "shorts_pay"

avoid_long = fund_rate > 0.005
avoid_short = fund_rate < -0.005
avoid_spread = spread > 0.5

confidence = 0.35
suggested = "long"
if avoid_spread:
    confidence = 0.15
elif overall == "bullish" and not avoid_long:
    suggested = "long"
    confidence = 0.58
    if t1 == "bullish" and t15 == "bullish":
        confidence += 0.12
    if r1 and 45 <= r1 <= 68:
        confidence += 0.05
    if r1 and r1 > 72:
        confidence -= 0.08
    if t1h == "bearish":
        confidence -= 0.1
elif overall == "bearish" and not avoid_short:
    suggested = "short"
    confidence = 0.58
    if t1 == "bearish" and t15 == "bearish":
        confidence += 0.12
elif overall == "mixed":
    if m1 >= 0.58 and m15 >= 0.52 and not avoid_long and t1h != "bearish":
        suggested = "long"
        confidence = 0.54
    elif m1 <= 0.42 and m15 <= 0.48 and not avoid_short and t1h != "bullish":
        suggested = "short"
        confidence = 0.54
    else:
        suggested = "long" if avg_mom >= 0.5 else "short"
        confidence = 0.38

confidence = round(min(max(confidence, 0.0), 0.85), 2)
price = round(float(ticker["last"]), 5)
change24h = round(float(ticker["chg_pct"]), 3)
volume24h = float(ticker["vol24h"])

summary = (
    f"1m {t1} RSI {int(r1) if r1 else 'NA'}, 15m {t15} RSI {int(r15) if r15 else 'NA'}, "
    f"1h {t1h} RSI {int(r1h) if r1h else 'NA'}; 24h +{change24h:.1f}%; "
    f"spread {spread:.3f}%; funding {fund_rate*100:.4f}%/8h benign; MTF {overall}"
)

print(json.dumps({
    "instId": "W-USDT",
    "price": price,
    "change24h": change24h,
    "volume24h": volume24h,
    "trend": overall,
    "momentumScore": avg_mom,
    "keyLevels": [round(support, 5), pivot, round(resistance, 5)],
    "fundingRate": fund_rate,
    "fundingBias": funding_bias,
    "spreadPct": round(spread, 4),
    "technicalSummary": summary,
    "suggestedSide": suggested,
    "confidence": confidence,
}, separators=(",", ":")))
