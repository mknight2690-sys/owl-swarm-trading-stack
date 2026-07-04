import json, subprocess, sys
from datetime import datetime, timezone

BASE = os.getenv("BLOFIN_API_BASE", "https://1b.blofin.com")
KEY = "1dc6839f3993477fab9f06a283cced08"
SECRET = "b5d4a931d5d846638ce00f6da5b12dd0"
PASSPHRASE = "Carterjaxon15"
BROKER = "5388cb1f51cec2e3"

def auth_headers(body="", timestamp=None):
    import hashlib, hmac, base64
    if timestamp is None:
        timestamp = str(int(datetime.now().astimezone(timezone.utc).timestamp()*1000))
    signature = base64.b64encode(hmac.new(SECRET.encode(), (timestamp + "GET" + "/api/v1/account/info" + body).encode(), hashlib.sha256).digest()).decode()
    return {
        "ACCESS-KEY": KEY, "ACCESS-SIGN": signature, "ACCESS-PASSPHRASE": PASSPHRASE,
        "ACCESS-TIMESTAMP": timestamp, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "Origin": "https://blofin.com", "Referer": "https://blofin.com/"
    }

def curl_req(url, method="GET", headers=None, body=""):
    hfile = "h.txt"
    with open(hfile, "w") as f:
        for k, v in (headers or {}).items():
            f.write(f"{k.replace(': ','-').upper()}: {v}\n")
    cmd = ["curl", "-s", "-X", method, "-H", f"@C:/Users/mknig/blofin-auto-trader/{hfile}",
           "-H", "Content-Type: application/json"]
    if body:
        cmd += ["-d", body]
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True, text=True).stdout

def ts():
    return str(int(datetime.now().astimezone(timezone.utc).timestamp()*1000))

def get_account():
    t = ts()
    headers = auth_headers(timestamp=t)
    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    headers["Origin"] = "https://blofin.com"
    headers["Referer"] = "https://blofin.com/"
    return json.loads(curl_req(BASE + "/api/v1/account/info", headers=headers))

def get_positions():
    t = ts()
    headers = auth_headers(timestamp=t)
    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    headers["Origin"] = "https://blofin.com"
    headers["Referer"] = "https://blofin.com/"
    return json.loads(curl_req(BASE + "/api/v1/position/allPositions?marginMode=cross&positionSide=long", headers=headers))

def place_order(inst_id, side, ord_type, sz, pos_side="long", td_mode="cross", reduce_only="false", tgt_ccy="USDT", trigger_px=None, sl=None, lever="125"):
    body_dict = {
        "instId": inst_id, "tdMode": td_mode, "side": side, "ordType": ord_type,
        "sz": str(sz), "ccy": tgt_ccy, "brokerId": BROKER, "clOrdId": "cron"+ts()[-6:],
        "positionSide": pos_side, "reduceOnly": reduce_only, "lever": lever
    }
    if trigger_px:
        body_dict["triggerPx"] = str(trigger_px)
    if sl:
        body_dict["slOrdPx"] = str(sl)
    t = ts()
    h = auth_headers(body=json.dumps(body_dict), timestamp=t)
    h.update({"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
              "Origin":"https://blofin.com","Referer":"https://blofin.com/"})
    return json.loads(curl_req(BASE + "/api/v1/trade/order", method="POST", headers=h, body=json.dumps(body_dict)))

def get_candles(inst_id, bar="1m", limit=30):
    t = ts()
    h = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
         "Origin":"https://blofin.com","Referer":"https://blofin.com/"}
    r = curl_req(BASE + f"/api/v1/market/history-candles?instId={inst_id}&bar={bar}&limit={limit}", headers=h)
    return json.loads(r)

print(f"[{datetime.now().isoformat()}] Trade cycle starting")
print("=== ACCOUNT ===")
acct = get_account()
print(json.dumps(acct, indent=2))
