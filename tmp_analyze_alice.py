import json
import subprocess
from pathlib import Path

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
ROOT = Path(r"C:\Users\mknig\owl-swarm")


def bridge(method, args):
    args_file = ROOT / "tmp_alice_bridge_args.json"
    args_file.write_text(json.dumps(args), encoding="utf-8")
    proc = subprocess.run(
        [PY, str(ROOT / "blofin_bridge.py"), method, f"@{args_file}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout.strip())


ob = bridge("get_order_book", {"inst_id": "ALICE-USDT"})
fund = bridge("get_funding_rate", {"inst_id": "ALICE-USDT"})
c1m = bridge("get_candles", {"inst_id": "ALICE-USDT", "bar": "1m", "limit": 50})
c15 = bridge("get_candles", {"inst_id": "ALICE-USDT", "bar": "15m", "limit": 30})
c1h = bridge("get_candles", {"inst_id": "ALICE-USDT", "bar": "1h", "limit": 24})
fund_rate = float(fund["fundingRate"])


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


cl1m = closes(c1m)
cl1h = closes(c1h)
m1, r1, t1 = momentum_score(c1m)
m15, r15, t15 = momentum_score(c15)
m1h, r1h, t1h = momentum_score(c1h)

bid = float(ob["bids"][0][0])
ask = float(ob["asks"][0][0])
mid = (bid + ask) / 2
spread = (ask - bid) / mid * 100

recent_1h = c1h[:6]
support = min(float(c[3]) for c in recent_1h)
resistance = max(float(c[2]) for c in recent_1h)
pivot = round((support + resistance + cl1h[-1]) / 3, 5)
price = round(cl1m[-1], 4)

trends = [t1, t15, t1h]
bull = trends.count("bullish")
bear = trends.count("bearish")
if bull >= 2:
    overall = "bullish"
elif bear >= 2:
    overall = "bearish"
else:
    overall = "mixed"

avg_mom = round((m1 + m15 + m1h) / 3, 3)

funding_bias = "neutral"
if fund_rate > 0.0001:
    funding_bias = "longs_pay"
elif fund_rate < -0.0001:
    funding_bias = "shorts_pay"

confidence = 0.35
suggested = "short"

avoid_long = fund_rate > 0.005
avoid_short = fund_rate < -0.005
avoid_spread = spread > 0.5

if avoid_spread:
    confidence = 0.15
    suggested = "short"
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
    if r1 and 32 <= r1 <= 55:
        confidence += 0.05
    if r1 and r1 < 25:
        confidence -= 0.08
    if t1h == "bullish":
        confidence -= 0.1
elif overall == "mixed":
    if m1 <= 0.42 and m15 <= 0.48 and not avoid_short and t1h != "bullish":
        suggested = "short"
        confidence = 0.54
    elif m1 >= 0.58 and m15 >= 0.52 and not avoid_long and t1h != "bearish":
        suggested = "long"
        confidence = 0.54
    else:
        suggested = "short" if avg_mom < 0.5 else "long"
        confidence = 0.38

# 24h dump + short_score 0.852 favors short when aligned
if overall == "bearish" or (overall == "mixed" and avg_mom < 0.45):
    if not avoid_short and not avoid_spread:
        suggested = "short"
        if confidence < 0.5:
            confidence = 0.52

confidence = round(min(max(confidence, 0.0), 0.85), 2)

r1s = f"{r1:.0f}" if r1 is not None else "n/a"
r15s = f"{r15:.0f}" if r15 is not None else "n/a"
r1hs = f"{r1h:.0f}" if r1h is not None else "n/a"

summary = (
    f"1m {t1} RSI {r1s}, 15m {t15} RSI {r15s}, 1h {t1h} RSI {r1hs}; "
    f"24h -22.4% heavy selloff; spread {spread:.2f}%; "
    f"funding {fund_rate:.6f} ({funding_bias})"
)

result = {
    "instId": "ALICE-USDT",
    "price": price,
    "change24h": -22.373,
    "volume24h": 8027450.1,
    "trend": overall,
    "momentumScore": avg_mom,
    "keyLevels": [round(support, 5), pivot, round(resistance, 5)],
    "fundingRate": fund_rate,
    "fundingBias": funding_bias,
    "spreadPct": round(spread, 4),
    "technicalSummary": summary,
    "suggestedSide": suggested if confidence >= 0.5 else "none",
    "confidence": confidence,
}

print(json.dumps(result, separators=(",", ":")))
