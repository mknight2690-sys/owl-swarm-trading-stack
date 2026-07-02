import json, subprocess

def fetch(method, args):
    p = subprocess.run([
        r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe",
        r"C:\Users\mknig\owl-swarm\blofin_bridge.py", method, json.dumps(args)
    ], capture_output=True, text=True, cwd=r"C:\Users\mknig\owl-swarm")
    return json.loads(p.stdout.strip())

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain*(period-1)+gains[i])/period
        avg_loss = (avg_loss*(period-1)+losses[i])/period
    if avg_loss == 0: return 100
    rs = avg_gain/avg_loss
    return 100 - 100/(1+rs)

def trend_score(closes):
    if len(closes) < 5: return 0
    first = sum(closes[:5])/5
    last = sum(closes[-5:])/5
    pct = (last-first)/first*100
    if pct > 0.3: return 1
    if pct < -0.3: return -1
    return 0

def key_levels(candles):
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]
    return {
        'support': min(lows),
        'resistance': max(highs),
        'pivot': (max(highs)+min(lows)+closes[0])/3
    }

for bar, limit in [('1m',50),('15m',30),('1H',24)]:
    c = fetch('get_candles', {'inst_id':'SAGA-USDT','bar':bar,'limit':str(limit)})
    closes = [float(x[4]) for x in reversed(c)]
    print(bar, 'last', closes[-1], 'rsi14', round(rsi(closes),2), 'trend', trend_score(closes), 'chg5', round((closes[-1]-closes[-6])/closes[-6]*100,3) if len(closes)>5 else None)

book = fetch('get_order_book', {'inst_id':'SAGA-USDT'})
bid, ask = float(book['bids'][0][0]), float(ask:=float(book['asks'][0][0]))
mid = (bid+ask)/2
print('spread_pct', round((ask-bid)/mid*100,4))

fund = fetch('get_funding_rate', {'inst_id':'SAGA-USDT'})
print('funding', fund['fundingRate'])

c1h = fetch('get_candles', {'inst_id':'SAGA-USDT','bar':'1H','limit':'24'})
closes1h = [float(x[4]) for x in reversed(c1h)]
print('1h range', min(float(x[3]) for x in c1h), max(float(x[2]) for x in c1h))
print('1h 6h chg', round((closes1h[-1]-closes1h[-7])/closes1h[-7]*100,3))
print('1h 24h chg', round((closes1h[-1]-closes1h[0])/closes1h[0]*100,3))
