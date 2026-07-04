import os, json, time, base64, hmac, hashlib, uuid, requests
from datetime import datetime

CRED_PATH = os.path.expanduser("C:/Users/mknig/Downloads/MK Blo Openclaw API compendium.txt")
text = open(CRED_PATH).read()
fields = {}
for line in text.splitlines():
    line = line.strip()
    if not line or ':' not in line:
        continue
    k, v = line.split(':', 1)
    fields[k.strip().lower().replace(' ', '_')] = v.strip()

API_KEY = fields.get('api_key') or fields.get('apikey')
SECRET = fields.get('secret_key') or fields.get('secretkey')
PASSPHRASE = fields.get('passphrase')
BROKER = '5388cb1f51cec2e3'
BASE = 'http://127.0.0.1:9876'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
    'Origin': 'https://blofin.com',
    'Referer': 'https://blofin.com/',
    'Content-Type': 'application/json',
}
COINS = ['BTC-USDT','ETH-USDT','SOL-USDT','XRP-USDT','DOGE-USDT','SUI-USDT','ARB-USDT','AVAX-USDT','LINK-USDT','UNI-USDT','ENA-USDT','WLD-USDT','ONDO-USDT','FIDA-USDT']

def sign(method, path, body=''):
    ts = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())
    prehash = f'{path}{method}{ts}{nonce}{body}'
    hex_sig = hmac.new(SECRET.encode(), prehash.encode(), hashlib.sha256).hexdigest()
    signature = base64.b64encode(hex_sig.encode()).decode()
    return {'ACCESS-KEY': API_KEY, 'ACCESS-SIGN': signature, 'ACCESS-PASSPHRASE': PASSPHRASE, 'ACCESS-TIMESTAMP': ts, 'ACCESS-NONCE': nonce}

def req(method, path, body=None, params=None, private=True):
    url = BASE + path
    if params:
        url += '?' + '&'.join(f'{k}={v}' for k, v in params.items())
    body_str = json.dumps(body, separators=(',', ':')) if body else ''
    h = dict(HEADERS)
    if private:
        h.update(sign(method, path, body_str))
    r = requests.request(method, url, headers=h, data=body_str.encode() if body_str else None, timeout=20)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {'raw': r.text[:500]}

def get_balance():
    sc, data = req('GET', '/api/v1/account/balance', params={'accountType': 'futures'})
    d = data.get('data') or data
    if isinstance(d, dict):
        for k in ['totalEquity', 'totalEq', 'adjEq', 'equityUsd']:
            if k in d and d[k]:
                return float(d[k]), d
    return 0.0, data

def get_positions():
    sc, data = req('GET', '/api/v1/account/positions', params={'marginMode': 'cross'})
    rows = data.get('data') if isinstance(data, dict) else []
    if isinstance(rows, list):
        return [r for r in rows if float(r.get('positions', 0)) != 0]
    return []

def get_candles(inst_id, limit=10):
    sc, data = req('GET', '/api/v1/market/candles', params={'instId': inst_id, 'bar': '1m', 'limit': str(limit)}, private=False)
    rows = data.get('data') if isinstance(data, dict) else []
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        try:
            out.append({'ts': int(r[0]), 'open': float(r[1]), 'high': float(r[2]), 'low': float(r[3]), 'close': float(r[4]), 'vol': float(r[5])})
        except Exception:
            pass
    return out

def get_instruments():
    try:
        sc, data = req('GET', '/api/v1/market/instruments', params={'instType': 'SWAP'}, private=False)
        rows = data.get('data') if isinstance(data, dict) else []
        if isinstance(rows, list):
            return {r['instId']: r for r in rows}
    except Exception:
        pass
    return {}

def close_position(inst_id, pos_size, side, leverage=10):
    body = {
        'instId': inst_id, 'tdMode': 'cross', 'marginMode': 'cross',
        'side': side, 'orderType': 'market', 'size': str(pos_size), 'ccy': 'USDT',
        'brokerId': BROKER, 'clOrdId': f'close{int(time.time()*1000)}',
        'positionSide': side, 'reduceOnly': 'true', 'lever': str(leverage),
    }
    return req('POST', '/api/v1/trade/order', body=body)

def place_order(inst_id, side, size, leverage=10):
    body = {
        'instId': inst_id, 'tdMode': 'cross', 'marginMode': 'cross',
        'side': side, 'orderType': 'market', 'size': str(size), 'ccy': 'USDT',
        'brokerId': BROKER, 'clOrdId': f'cron{int(time.time()*1000)}',
        'positionSide': side, 'reduceOnly': 'false', 'lever': str(leverage),
    }
    return req('POST', '/api/v1/trade/order', body=body)

def call_stepfun(equity, positions, instruments, snapshot):
    top = sorted(snapshot, key=lambda x: x['score'], reverse=True)[:5]
    if not top:
        return {'close': [], 'open': []}
    lines = []
    lines.append(f'EQUITY={equity:.4f}')
    for p in positions:
        lines.append(f"POS {p['instId']} pnl={p.get('unrealizedPnlRatio',0)} age={(time.time()*1000-int(p.get('createTime',0)))/1000:.0f}s size={p.get('positions',0)}")
    for c in top:
        lines.append(f"CAND {c['instId']} score={c['score']} price={c['price']} cv={c['contractValue']} min={c['minSize']} lot={c['lotSize']}")
    lines.append('OUTPUT FORMAT: one action per line. CLOSE:INST_ID or OPEN:INST_ID:SIZE. Max 3 opens. Only USDT linear. Only positive score.')
    prompt = '\n'.join(lines)
    url = 'https://inference-api.nousresearch.com/v1/chat/completions'
    api_key = os.environ.get('NOUS_API_KEY', '')
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': 'stepfun/step-3.7-flash:free',
        'messages': [
            {'role': 'system', 'content': 'You are a trading bot. Output one command per line.'},
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': 600,
        'temperature': 0.1,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        msg = r.json()['choices'][0]['message']
        content = msg.get('content') or msg.get('reasoning') or ''
        print(f'AI raw repr: {repr(content[:400])}', flush=True)
        closes = []
        opens = []
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('CLOSE:'):
                closes.append(line.split(':',1)[1].strip())
            elif line.startswith('OPEN:'):
                parts = line.split(':')
                if len(parts) >= 3:
                    opens.append({'instId': parts[1].strip(), 'size': float(parts[2].strip()), 'score': 0})
        return {'close': closes, 'open': opens}
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'AI error: {e}', flush=True)
        return {'close': [], 'open': []}

def run():
    print(f'[{datetime.now().isoformat()}] === AI TRADE CYCLE ===', flush=True)

    equity, acct = get_balance()
    print(f'Equity: {equity:.4f} USDT', flush=True)

    positions = get_positions()
    print(f'Positions: {len(positions)}', flush=True)
    for p in positions:
        print(f"  {p.get('instId')} pos={float(p.get('positions',0)):.2f} pnl={float(p.get('unrealizedPnlRatio',0))*100:.3f}% age={(time.time()*1000-int(p.get('createTime',0)))/1000:.0f}s", flush=True)

    # Build instruments and snapshot
    instruments = get_instruments()
    snapshot = []
    for coin in COINS:
        info = instruments.get(coin)
        if not info:
            continue
        candles = get_candles(coin, limit=10)
        if len(candles) < 5:
            continue
        close = [c['close'] for c in candles]
        vol = [c['vol'] for c in candles]
        if vol[-1] == 0:
            continue
        mom = (close[-1] - close[-4]) / close[-4]
        avg_vol = sum(vol[-5:-1]) / 4
        score = mom * (vol[-1] / avg_vol) if avg_vol > 0 else 0
        snapshot.append({
            'instId': coin, 'score': round(score, 6), 'price': close[-1],
            'contractValue': float(info.get('contractValue', 1)),
            'minSize': float(info.get('minSize', 1)),
            'lotSize': float(info.get('lotSize', 1)),
        })

    decision = call_stepfun(equity, [{'instId':p.get('instId'),'positions':float(p.get('positions',0)),'unrealizedPnlRatio':float(p.get('unrealizedPnlRatio',0)),'createTime':p.get('createTime',0)} for p in positions], {k:v for k,v in instruments.items() if k in COINS}, snapshot)
    print(f'AI decision: {json.dumps(decision)}', flush=True)

    # Close signals
    for inst_id in decision.get('close', []):
        pos = next((p for p in positions if p.get('instId') == inst_id), None)
        if pos:
            side = 'sell' if pos.get('positionSide','long') == 'long' else 'buy'
            sc, data = close_position(inst_id, float(pos.get('positions', 0)), side)
            print(f'Close {inst_id}: {sc} {json.dumps(data)[:200]}', flush=True)

    # Refresh positions after closes
    positions = get_positions()
    already = {p.get('instId') for p in positions}
    opened = 0
    for entry in decision.get('open', []):
        inst_id = entry.get('instId')
        if inst_id in already:
            continue
        if opened >= 3:
            break
        info = instruments.get(inst_id, {})
        price = entry.get('price', 0)
        if price <= 0:
            continue
        notional = max(equity * 0.08, 0.5)
        size = entry.get('size', 1)
        if float(size) < float(info.get('minSize', 1)):
            continue
        sc, data = place_order(inst_id, 'buy', size, leverage=10)
        print(f'Open {inst_id} size={size}: {sc} {json.dumps(data)[:300]}', flush=True)
        opened += 1

    print('=== CYCLE END ===', flush=True)

if __name__ == '__main__':
    run()
