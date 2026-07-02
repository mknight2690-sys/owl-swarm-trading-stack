#!/usr/bin/env python3
import json, hmac, hashlib, base64, time, sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_KEY = "f3ba1b72597249f1b1b1c74587f37a1d"
SECRET = "0c90e12753904b94a6b0fe3a71ec7242"
PASSPHRASE = "Mookie90"
BASE = "https://openapi.blofin.com"

def sign(ts, method, path, body=""):
    msg = ts + method + path + body
    mac = hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()

def req(method, path, body=None):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
         datetime.now(timezone.utc).strftime("%f")[:3] + "Z"
    sig = sign(ts, method, path, body or "")
    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGN": sig,
        "ACCESS-TIMESTAMP": ts,
        "ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json",
    }
    url = BASE + path
    r = Request(url, method=method, headers=headers)
    if body:
        r.data = body.encode()
    try:
        resp = urlopen(r, timeout=15)
        return json.loads(resp.read())
    except HTTPError as e:
        return {"error": e.code, "body": e.read().decode()}

# Check balance
print("=== BALANCE ===")
bal = req("GET", "/api/v1/account/balance")
print(json.dumps(bal, indent=2))

# Check positions
print("\n=== POSITIONS ===")
pos = req("GET", "/api/v1/account/positions")
if pos.get("data"):
    for p in pos["data"]:
        print(json.dumps(p, indent=2))

# Check PUMP-USDT instrument
print("\n=== PUMP-USDT INSTRUMENT ===")
inst = req("GET", "/api/v1/public/instruments?instType=SWAP&instId=PUMP-USDT")
print(json.dumps(inst, indent=2))

# Check PUMP-USDT ticker
print("\n=== PUMP-USDT TICKER ===")
ticker = req("GET", "/api/v1/market/ticker?instId=PUMP-USDT")
print(json.dumps(ticker, indent=2))

# Check TRUTH-USDT ticker
print("\n=== TRUTH-USDT TICKER ===")
ticker2 = req("GET", "/api/v1/market/ticker?instId=TRUTH-USDT")
print(json.dumps(ticker2, indent=2))
