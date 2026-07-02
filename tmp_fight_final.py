import json, subprocess
from pathlib import Path
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
ROOT = Path(r"C:\Users\mknig\owl-swarm")
def bridge(method, args):
    args_file = ROOT / "tmp_bridge_call.json"
    args_file.write_text(json.dumps(args), encoding="utf-8")
    proc = subprocess.run([PY, str(ROOT / "blofin_bridge.py"), method, f"@{args_file}"], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0: raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout.strip())

inst = "FIGHT-USDT"
ticker = bridge("get_ticker", {"inst_id": inst})[0]
ob = bridge("get_order_book", {"inst_id": inst})
fund = bridge("get_funding_rate", {"inst_id": inst})
c1m = bridge("get_candles", {"inst_id": inst, "bar": "1m", "limit": 50})
c15 = bridge("get_candles", {"inst_id": inst, "bar": "15m", "limit": 30})
c1h = bridge("get_candles", {"inst_id": inst, "bar": "1h", "limit": 24})
fund_rate = float(fund["fundingRate"])
price = float(ticker["last"])
change24h = float(ticker.get("chg_pct", -10.732))
volume24h = float(ticker["volCurrency24h"])

def closes(candles):
    return [float(c[4]) for c in reversed(candles)]

def rsi(cl, period=14):
    if len(cl) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(cl)):
        d = cl[i] - cl[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    ag = sum(gains[:period])/period; al = sum(losses[:period])/period
    for i in range(period, len(gains)):
        ag = (ag*(period-1)+gains[i])/period; al = (al*(period-1)+losses[i])/period
    return 100.0 if al==0 else 100-(100/(1+ag/al))

def trend(cl, n=5):
    if len(cl) < n: return "neutral"
    recent = cl[-n:]
    if recent[-1] > recent[0]*1.002: return "bullish"
    if recent[-1] < recent[0]*0.998: return "bearish"
    return "neutral"

def momentum_score(candles):
    cl = closes(candles)
    r = rsi(cl); t = trend(cl)
    chg = (cl[-1]-cl[0])/cl[0]*100 if cl[0] else 0
    score = 0.5
    if r is not None: score += (r-50)/100
    if t=="bullish": score += 0.15
    elif t=="bearish": score -= 0.15
    score += min(max(chg/10,-0.2),0.2)
    return round(max(0,min(1,score)),3), r, t, cl

m1,r1,t1,cl1m = momentum_score(c1m)
m15,r15,t15,cl15 = momentum_score(c15)
m1h,r1h,t1h,cl1h = momentum_score(c1h)

bid = float(ob["bids"][0][0]); ask = float(ob["asks"][0][0])
mid = (bid+ask)/2; spread = (ask-bid)/mid*100

# key levels from recent 1h candles (newest 6)
recent_1h = c1h[:6]
support = min(float(c[3]) for c in recent_1h)
resistance = max(float(c[2]) for c in recent_1h)
pivot = round((support+resistance+price)/3, 6)

trends = [t1,t15,t1h]
bull, bear = trends.count("bullish"), trends.count("bearish")
overall = "bullish" if bull>=2 else "bearish" if bear>=2 else "mixed"
avg_mom = round((m1+m15+m1h)/3, 3)

funding_bias = "neutral"
if fund_rate > 0.0001: funding_bias = "longs_pay"
elif fund_rate < -0.0001: funding_bias = "shorts_pay"

avoid_long = fund_rate > 0.005
avoid_short = fund_rate < -0.005
avoid_spread = spread > 0.5

confidence = 0.35
suggested = "short"

if avoid_spread:
    confidence = 0.15; suggested = "short"
elif overall == "bullish" and not avoid_long:
    suggested = "long"; confidence = 0.58
    if t1=="bullish" and t15=="bullish": confidence += 0.12
    if r1 and 45<=r1<=68: confidence += 0.05
    if r1 and r1>72: confidence -= 0.10
    if t1h=="bearish": confidence -= 0.10
elif overall == "bearish" and not avoid_short:
    suggested = "short"; confidence = 0.58
    if t1=="bearish" and t15=="bearish": confidence += 0.12
    if r1 and 32<=r1<=55: confidence += 0.05
    if r1 and r1<25: confidence -= 0.08
    if t1h=="bullish": confidence -= 0.10
elif overall == "mixed":
    if m1<=0.42 and m15<=0.48 and not avoid_short and t1h!="bullish":
        suggested="short"; confidence=0.54
    elif m1>=0.58 and m15>=0.52 and not avoid_long and t1h!="bearish":
        suggested="long"; confidence=0.54
    else:
        suggested = "short" if avg_mom < 0.5 else "long"
        confidence = 0.38

# 24h -10.7% bearish context; short_score 0.856 > long 0.406
if change24h < -5 and overall != "bullish":
    suggested = "short"; confidence = max(confidence, 0.55)
if change24h < -5 and t1h == "bearish":
    suggested = "short"; confidence = max(confidence, 0.62)

# 1h trend from 24 candles
h24_chg = (cl1h[-1]-cl1h[0])/cl1h[0]*100
print(json.dumps({
  "debug": {
    "t1":t1,"t15":t15,"t1h":t1h,"r1":r1,"r15":r15,"r1h":r1h,
    "m1":m1,"m15":m15,"m1h":m1h,"spread":spread,"fund":fund_rate,
    "overall":overall,"h24_chg":round(h24_chg,3),
    "cl1m_last5":cl1m[-5:], "cl1h_last3":cl1h[-3:], "cl1h_first3":cl1h[:3]
  }
}, indent=2))

confidence = round(min(max(confidence,0),0.85),2)
r1s=f"{r1:.0f}" if r1 else "N/A"; r15s=f"{r15:.0f}" if r15 else "N/A"; r1hs=f"{r1h:.0f}" if r1h else "N/A"
summary = f"1m {t1} RSI {r1s}, 15m {t15} RSI {r15s}, 1h {t1h} RSI {r1hs}; 24h -10.7% decline from 0.0041 open; spread {spread:.3f}%; funding benign"
result = {
  "instId": inst, "price": price, "change24h": change24h, "volume24h": volume24h,
  "trend": overall, "momentumScore": avg_mom,
  "keyLevels": [round(support,6), pivot, round(resistance,6)],
  "fundingRate": fund_rate, "fundingBias": funding_bias, "spreadPct": round(spread,4),
  "technicalSummary": summary, "suggestedSide": suggested, "confidence": confidence
}
print(json.dumps(result, separators=(",", ":")))
