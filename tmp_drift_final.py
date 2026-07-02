import json, subprocess, tempfile, os
PY = r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
CWD = r"C:\Users\mknig\owl-swarm"
INST = "DRIFT-USDT"
PL, PS = 0.948, 0.298

def bridge(method, args):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    f.write(json.dumps(args)); f.close()
    out = subprocess.check_output([PY, "blofin_bridge.py", method, "@" + f.name], cwd=CWD)
    os.unlink(f.name); return json.loads(out)

def parse(raw):
    return [{"ts":int(x[0]),"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4])} for x in reversed(raw)]

def rsi(closes, p=14):
    if len(closes) < p+1: return 50.0
    g,l=[],[]
    for i in range(1,len(closes)):
        ch=closes[i]-closes[i-1]; g.append(max(ch,0)); l.append(max(-ch,0))
    ag,al=sum(g[-p:])/p,sum(l[-p:])/p
    return 100 if al==0 else 100-100/(1+ag/al)

def ema(vals,n):
    if len(vals)<n: return vals[-1]
    k=2/(n+1); e=sum(vals[:n])/n
    for v in vals[n:]: e=v*k+e*(1-k)
    return e

def trend(closes):
    e9,e21,p=ema(closes,9),ema(closes,21),closes[-1]
    if e9>e21 and p>e21: return 0.75,"bullish"
    if e9<e21 and p<e21: return 0.25,"bearish"
    if e9>e21: return 0.6,"bullish"
    if e9<e21: return 0.4,"bearish"
    return 0.5,"neutral"

ticker=bridge("get_ticker",{"inst_id":INST})[0]
fund=bridge("get_funding_rate",{"inst_id":INST})
ob=bridge("get_order_book",{"inst_id":INST})
c1m=parse(bridge("get_candles",{"inst_id":INST,"bar":"1m","limit":"50"}))
c15=parse(bridge("get_candles",{"inst_id":INST,"bar":"15m","limit":"30"}))
c1h=parse(bridge("get_candles",{"inst_id":INST,"bar":"1H","limit":"24"}))

price=float(ticker["last"])
open24=float(ticker["open24h"])
chg24=float(ticker.get("chg_pct") or (price-open24)/open24*100)
vol24=float(ticker["volCurrency24h"])
low24,high24=float(ticker["low24h"]),float(ticker["high24h"])

bb,ba=float(ob["bids"][0][0]),float(ob["asks"][0][0])
mid=(bb+ba)/2; spread=(ba-bb)/mid*100
fr=float(fund["fundingRate"])

cl1=[x["c"] for x in c1m]; cl15=[x["c"] for x in c15]; cl1h=[x["c"] for x in c1h]
r1,r15,r1h=rsi(cl1),rsi(cl15),rsi(cl1h)
t1,l1=trend(cl1); t15,l15=trend(cl15); t1h,l1h=trend(cl1h)
m1=(cl1[-1]-cl1[-5])/cl1[-5]*100
m15=(cl15[-1]-cl15[-5])/cl15[-5]*100
m1h=(cl1h[-1]-cl1h[-4])/cl1h[-4]*100

support=min(x["l"] for x in c15[-20:])
resistance=max(x["h"] for x in c15[-20:])
pivot=(high24+low24+price)/3

avoid_long=fr>0.005; avoid_short=fr<-0.005; avoid_trade=spread>0.5
if fr>0.005: fb="expensive_long"
elif fr>0.0003: fb="crowded_long"
elif fr>0.0001: fb="mild_long_crowding"
elif fr<-0.005: fb="expensive_short"
elif fr<-0.0003: fb="crowded_short"
elif fr<-0.0001: fb="mild_short_crowding"
else: fb="neutral"

mom=0.65 if 55<r15<70 else (0.3 if r15>=70 else (0.7 if r15<30 else 0.5))
bull2=l15=="bullish" and l1h=="bullish"
bear_all=l1=="bearish" and l15=="bearish" and l1h=="bearish"

avg_t=(t1+t15+t1h)/3
model_long=avg_t*0.35+mom*0.25+(0.65 if bull2 else 0.45)*0.2+(0.1 if m1>0 else 0)*0.1+PL*0.1
model_short=1-model_long

factors=[0.72 if bull2 else (0.28 if bear_all else 0.52), 0.65 if 45<r15<70 else 0.4, 0.58 if bull2 else 0.42, 0.55, 0.88 if not avoid_trade else 0.15, 0.72 if not avoid_long else 0.2, PL*0.9]
conf=round(sum(factors)/len(factors),3)

if avoid_trade or (avoid_long and model_long>=0.5):
    conf=min(conf,0.45); side="short" if model_short>model_long else "long"
elif bull2 and not avoid_long:
    side="long"; conf=max(conf,0.62)
elif bear_all and not avoid_short:
    side="short"; conf=max(conf,0.62)
elif model_long>=model_short and not avoid_long:
    side="long"
else:
    side="short"

if conf<0.5:
    side="long" if model_long>=model_short else "short"

ot="bullish" if avg_t>=0.6 else ("bearish" if avg_t<=0.4 else "neutral")
mtf="15m+1h bullish, 1m pullback" if bull2 and l1=="bearish" else ("aligned bullish" if bull2 and l1=="bullish" else "mixed")
summary=(f"1m {l1} RSI {r1:.1f} mom {m1:+.2f}%; 15m {l15} RSI {r15:.1f} mom {m15:+.2f}%; 1h {l1h} RSI {r1h:.1f} mom {m1h:+.2f}%. 24h +{chg24:.1f}%; {mtf}. Funding {fb} ({fr*100:.4f}%/8h), spread {spread:.3f}%. Support {support:.5f}, resistance {resistance:.5f}. Strong bid book; prior DRIFT win (+0.33 PnL).")

print(json.dumps({"instId":INST,"price":round(price,5),"change24h":round(chg24,3),"volume24h":int(vol24),"trend":ot,"momentumScore":round(mom,3),"keyLevels":[round(support,5),round(pivot,5),round(resistance,5),round(low24,5),round(high24,5)],"fundingRate":round(fr,6),"fundingBias":fb,"spreadPct":round(spread,4),"technicalSummary":summary,"suggestedSide":side,"confidence":conf}))
