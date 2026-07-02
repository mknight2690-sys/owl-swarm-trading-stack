import json
import subprocess
from pathlib import Path

PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
ROOT = Path(r"C:\Users\mknig\owl-swarm")
INST = "RESOLV-USDT"

def bridge(method, args):
    args_file = ROOT / "tmp_bridge_call.json"
    args_file.write_text(json.dumps(args), encoding="utf-8")
    proc = subprocess.run([PY, str(ROOT / "blofin_bridge.py"), method, f"@{args_file}"], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout.strip())

ob = bridge("get_order_book", {"inst_id": INST})
fund = bridge("get_funding_rate", {"inst_id": INST})
ticker = bridge("get_ticker", {"inst_id": INST})[0]
c1m = bridge("get_candles", {"inst_id": INST, "bar": "1m", "limit": 50})
c15 = bridge("get_candles", {"inst_id": INST, "bar": "15m", "limit": 30})
c1h = bridge("get_candles", {"inst_id": INST, "bar": "1h", "limit": 24})

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

def mom(candles):
    cl = closes(candles)
    return rsi(cl), trend(cl), cl

r1, t1, _ = mom(c1m)
r15, t15, _ = mom(c15)
r1h, t1h, cl1h = mom(c1h)

bid, ask = float(ob["bids"][0][0]), float(ob["asks"][0][0])
spread = (ask - bid) / ((bid + ask) / 2) * 100
fund_rate = float(fund["fundingRate"])
price = float(ticker["last"])
change24h = float(ticker.get("chg_pct", 0))
vol24h = int(float(ticker.get("volCurrency24h", ticker.get("vol24h", 0))))

recent_1h = c1h[:6]
support = min(float(c[3]) for c in recent_1h)
resistance = max(float(c[2]) for c in recent_1h)
pivot = round((support + resistance + price) / 3, 5)

trends = [t1, t15, t1h]
bull, bear = trends.count("bullish"), trends.count("bearish")
overall = "bullish" if bull >= 2 else "bearish" if bear >= 2 else "mixed"

m1 = 0.5 + ((r1 or 50) - 50) / 100 + (0.15 if t1 == "bullish" else -0.15 if t1 == "bearish" else 0)
m15 = 0.5 + ((r15 or 50) - 50) / 100 + (0.15 if t15 == "bullish" else -0.15 if t15 == "bearish" else 0)
m1h = 0.5 + ((r1h or 50) - 50) / 100 + (0.15 if t1h == "bullish" else -0.15 if t1h == "bearish" else 0)
avg_mom = round(max(0, min(1, (m1 + m15 + m1h) / 3)), 3)

funding_bias = "longs_pay" if fund_rate > 0.0001 else "shorts_pay" if fund_rate < -0.0001 else "neutral"

avoid_long = fund_rate > 0.005
avoid_short = fund_rate < -0.005
avoid_spread = spread > 0.5

suggested = "long"
confidence = 0.5

if avoid_spread:
    suggested, confidence = "long", 0.15
elif overall == "bullish" and not avoid_long:
    suggested, confidence = "long", 0.62
elif overall == "bearish" and not avoid_short:
    suggested, confidence = "short", 0.58
else:
    # mixed MTF: weigh funding + 15m bounce vs 1m/1h weakness
    if not avoid_long and fund_rate < 0 and t15 == "bullish":
        suggested, confidence = "long", 0.57
    elif not avoid_short and t1 == "bearish" and t1h == "bearish" and (r1 or 0) < 45:
        suggested, confidence = "short", 0.55
    else:
        suggested = "long" if avg_mom >= 0.5 else "short"
        confidence = 0.48

if r1 and r1 > 70 and suggested == "long":
    confidence -= 0.05
if r15 and r15 < 30 and t15 == "bullish" and suggested == "long":
    confidence += 0.03
if fund_rate < 0 and suggested == "long":
    confidence += 0.03
if fund_rate < 0 and suggested == "short":
    confidence -= 0.05
confidence += 0.03  # RESOLV positive track record
if suggested == "long":
    confidence -= 0.03  # recent long loss
confidence = round(min(max(confidence, 0.0), 0.85), 2)

r1s = f"{r1:.0f}" if r1 is not None else "N/A"
r15s = f"{r15:.0f}" if r15 is not None else "N/A"
r1hs = f"{r1h:.0f}" if r1h is not None else "N/A"
summary = (
    f"1m {t1} RSI {r1s}, 15m {t15} RSI {r15s}, 1h {t1h} RSI {r1hs}; "
    f"24h +{change24h:.1f}%; spread {spread:.2f}%; funding {fund_rate:.6f}; MTF {overall}"
)

print(json.dumps({
    "instId": INST,
    "price": round(price, 5),
    "change24h": round(change24h, 3),
    "volume24h": vol24h,
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
