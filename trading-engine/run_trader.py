import base64, hashlib, hmac, json, os, time, uuid, requests

CRED_PATH = os.path.expanduser("C:/Users/mknig/Downloads/MK Blo Openclaw API compendium.txt")
text = open(CRED_PATH).read()
fields = {}
for line in text.splitlines():
    line = line.strip()
    if not line or ":" not in line:
        continue
    key, value = line.split(":", 1)
    fields[key.strip().lower().replace(" ", "_")] = value.strip()

API_KEY = fields.get("api_key") or fields.get("apikey")
SECRET = fields.get("secret_key") or fields.get("secretkey")
PASSPHRASE = fields.get("passphrase")
BASE = "https://openapi.blofin.com"
BROKER = "5388cb1f51cec2e3"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Origin": "https://blofin.com",
    "Referer": "https://blofin.com/",
    "Content-Type": "application/json",
}
COINS = ["SOL","ETH","XRP","BTC","DOGE","SUI","ARB","AVAX","LINK","UNI","ENA","WLD","ONDO","FIDA"]

def sign(method, path, body="", timestamp=None, nonce=None):
    if timestamp is None:
        timestamp = str(int(time.time() * 1000))
    if nonce is None:
        nonce = str(uuid.uuid4())
    prehash = f"{path}{method}{timestamp}{nonce}{body}"
    hex_sig = hmac.new(SECRET.encode(), prehash.encode(), hashlib.sha256).hexdigest()
    signature = base64.b64encode(hex_sig.encode()).decode()
    return {
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGN": signature,
        "ACCESS-PASSPHRASE": PASSPHRASE,
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-NONCE": nonce,
    }

def signed_request(method, path, body_obj=None):
    body = json.dumps(body_obj, separators=(",", ":")) if body_obj else ""
    h = dict(HEADERS)
    h.update(sign(method, path, body))
    url = BASE + path
    r = requests.request(method, url, headers=h, data=body.encode() if body else None, timeout=20)
    return r.status_code, r.json() if r.text else {}

def public_request(path):
    url = BASE + path
    r = requests.get(url, headers=HEADERS, timeout=20)
    return r.status_code, r.json() if r.text else {}

def get_equity():
    sc, data = signed_request("GET", "/api/v1/account/balance?accountType=futures")
    d = data.get("data")
    if isinstance(d, dict):
        for k in ["totalEquity", "totalEq", "adjEq", "equityUsd"]:
            if k in d and d[k]:
                return float(d[k])
    return 0.0

def get_positions():
    sc, data = signed_request("GET", "/api/v1/account/positions?accountType=futures")
    rows = data.get("data")
    if isinstance(rows, list):
        out = [r for r in rows if float(r.get("positions", 0) or r.get("pos", 0)) != 0]
        print("DEBUG_POSITIONS:", json.dumps(out, indent=2))
        return out
    elif isinstance(rows, dict):
        out = [rows] if float(rows.get("positions", 0) or rows.get("pos", 0)) != 0 else []
        print("DEBUG_POSITIONS:", json.dumps(out, indent=2))
        return out
    print("DEBUG_POSITIONS: []")
    return []

def get_candles(inst_id, limit=20):
    sc, data = public_request(f"/api/v1/market/candles?instId={inst_id}&bar=1m&limit={limit}")
    rows = data.get("data") if isinstance(data, dict) else []
    if not isinstance(rows, list):
        return []
    return [{"ts": int(r[0]), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "vol": float(r[5])} for r in rows]

def close_position(inst_id):
    positions = get_positions()
    pos = next((p for p in positions if p["instId"] == inst_id), None)
    if not pos:
        return {"status": "no_position"}
    pos_size = float(pos["positions"] if "positions" in pos else pos.get("pos", 0))
    side = "sell" if pos_size > 0 else "buy"
    sz = abs(pos_size)
    position_side = pos.get("positionSide") or pos.get("position_side") or ("long" if pos_size > 0 else "short")
    body = {
        "instId": inst_id,
        "tdMode": "cross",
        "marginMode": "cross",
        "side": side,
        "orderType": "market",
        "size": str(sz),
        "positionSide": position_side,
        "ccy": "USDT",
        "brokerId": BROKER,
        "clOrdId": f"close_{int(time.time()*1000)}",
        "reduceOnly": "true",
    }
    return signed_request("POST", "/api/v1/trade/order", body)

def place_order(inst_id, side, sz, tp=None, sl=None, leverage=10):
    body = {
        "instId": inst_id,
        "tdMode": "cross",
        "marginMode": "cross",
        "side": side,
        "orderType": "market",
        "size": str(sz),
        "positionSide": "long" if side == "buy" else "short",
        "ccy": "USDT",
        "brokerId": BROKER,
        "clOrdId": f"enter_{int(time.time()*1000)}",
        "lever": str(leverage),
    }
    if tp:
        body["tpTriggerPx"] = str(tp)
        body["tpOrdPx"] = str(tp)
        body["tpOrdPxType"] = "last"
    if sl:
        body["slTriggerPx"] = str(sl)
        body["slOrdPx"] = str(sl)
        body["slOrdPxType"] = "last"
    return signed_request("POST", "/api/v1/trade/order", body)

def main():
    print("=" * 60)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"AUTO TRADER TICK - {now}")
    print("=" * 60)

    equity = get_equity()
    positions = get_positions()

    print(f"EQUITY={equity:.6f}")
    pos_desc = []
    for p in positions:
        side = "LONG" if float(p.get("positions", 0) or p.get("pos", 0)) > 0 else "SHORT"
        upl = float(p.get("upl", 0))
        pos_desc.append(f"{p.get('instId','?')}({side},PnL={upl:.4f})")
    print(f"OPEN_POSITIONS={pos_desc}")
    print(f"POSITION_COUNT={len(positions)}")

    ts_now = int(time.time() * 1000)
    actions = []
    for p in positions[:]:
        inst = p["instId"]
        upl = float(p.get("upl", 0))
        ctime = int(p.get("cTime", p.get("openTime", 0)))
        age_min = (ts_now - ctime) / 60000 if ctime else 0

        if upl >= 0.8 or upl <= -0.6:
            actions.append(("CLOSE", "TP_SL_HIT", inst))
            close_position(inst)
        elif age_min > 5:
            actions.append(("CLOSE", "STALE", inst))
            close_position(inst)

    if actions:
        print("ACTIONS_TAKEN:")
        for a in actions:
            print(f"  ACTION={a[0]}, SIGNAL={a[1]}, INST={a[2]}")
        equity = get_equity()
        positions = get_positions()
        print(f"EQUITY_AFTER={equity:.6f}")

    MAX_POS = 3
    if len(positions) >= MAX_POS:
        print("ACTION=HOLD, SIGNAL=MAX_POSITIONS_REACHED")
        return

    best = None
    best_score = 0
    for coin in COINS:
        inst_id = f"{coin}-USDT"
        candles = get_candles(inst_id, limit=20)
        if len(candles) < 5:
            continue
        closes = [c["close"] for c in candles[-5:]]
        pct = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0
        recent = candles[-3:]
        streak = sum(1 if c["close"] > c["open"] else -1 for c in recent) / len(recent)

        if abs(pct) < 0.4 or abs(streak) < 0.5:
            continue

        score = abs(pct) * 0.5 + abs(streak) * 0.5
        if score > best_score:
            best_score = score
            best = {
                "coin": coin,
                "inst_id": inst_id,
                "side": "buy" if pct > 0 else "sell",
                "pct": pct,
                "streak": streak,
                "price": closes[-1],
                "score": score
            }

    if not best:
        print("ACTION=FLAT, SIGNAL=NO_EDGE, PNL=N/A")
        return

    size_pct = 0.10 if equity > 0.05 else 0.05
    notional = equity * size_pct * 10
    contracts = notional / best["price"] if best["price"] > 0 else 0
    contracts = max(1, int(contracts))

    tp = best["price"] * (1.008 if best["side"] == "buy" else 0.992)
    sl = best["price"] * (0.995 if best["side"] == "buy" else 1.005)

    print(f"ACTION=TRADE, SIGNAL=MOMENTUM_{best['side'].upper()}, INST={best['inst_id']}, PCT={best['pct']:.2f}%")
    print(f"Contracts={contracts}, TP={tp:.6f}, SL={sl:.6f}")

    result = place_order(best["inst_id"], best["side"], contracts, tp=tp, sl=sl, leverage=10)
    print(f"Order result: {json.dumps(result)}")

    positions = get_positions()
    pos_desc = []
    for p in positions:
        side = "LONG" if float(p.get("positions", 0) or p.get("pos", 0)) > 0 else "SHORT"
        upl = float(p.get("upl", 0))
        pos_desc.append(f"{p.get('instId','?')}({side},PnL={upl:.4f})")
    print(f"FINAL_OPEN_POSITIONS={pos_desc}")
    print(f"FINAL_EQUITY={get_equity():.6f}")

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print(f"FATAL_LOOP_ERROR: {e}")
        time.sleep(60)
