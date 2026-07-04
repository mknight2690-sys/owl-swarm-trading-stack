"""Test if routing through VPN interface bypasses Cloudflare 403s."""
import sys, time, json, hmac, hashlib, base64
from uuid import uuid4
sys.path.insert(0, r"C:\Users\mknig\blofin-auto-trader")
from autohedge.tools.blofin_client import BlofinClient
from curl_cffi import requests

client = BlofinClient()

# Test private endpoint through VPN with full signing
print("Testing private endpoint through ProtonVPN (10.2.0.2)...")

path = "/api/v1/account/positions"
params = {"accountType": "futures"}
query = "?" + "&".join(f"{k}={v}" for k, v in params.items())
sign_path = path + query
method = "GET"
body_str = ""
ts = str(int(time.time() * 1000))
nonce = str(uuid4())
prehash = f"{sign_path}{method}{ts}{nonce}{body_str}"
sig = base64.b64encode(
    hmac.new(client.credentials.secret_key.encode(), prehash.encode(), hashlib.sha256).hexdigest().encode()
).decode()

headers = {
    "ACCESS-KEY": client.credentials.api_key,
    "ACCESS-SIGN": sig,
    "ACCESS-TIMESTAMP": ts,
    "ACCESS-NONCE": nonce,
    "ACCESS-PASSPHRASE": client.credentials.passphrase,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

for imp in ["chrome120", "chrome110", "chrome"]:
    url = f"https://openapi.blofin.com{sign_path}"
    try:
        r = requests.request("GET", url, headers=headers, impersonate=imp, interface="10.2.0.2", timeout=15)
        print(f"  [{imp}] Status: {r.status_code}")
        if r.status_code != 200:
            print(f"  Body: {r.text[:200]}")
        else:
            print(f"  SUCCESS: {r.text[:150]}")
            break
    except Exception as e:
        print(f"  [{imp}] Error: {str(e)[:80]}")
    time.sleep(1)

# Also test balance
print("\nTesting /account/balance through VPN...")
path2 = "/api/v1/account/balance"
params2 = {"accountType": "futures"}
query2 = "?" + "&".join(f"{k}={v}" for k, v in params2.items())
sign_path2 = path2 + query2
prehash2 = f"{sign_path2}GET{ts}{nonce}"
sig2 = base64.b64encode(
    hmac.new(client.credentials.secret_key.encode(), prehash2.encode(), hashlib.sha256).hexdigest().encode()
).decode()
headers2 = dict(headers)
headers2["ACCESS-SIGN"] = sig2

for imp in ["chrome120", "chrome110", "chrome"]:
    url = f"https://openapi.blofin.com{sign_path2}"
    try:
        r = requests.request("GET", url, headers=headers2, impersonate=imp, interface="10.2.0.2", timeout=15)
        print(f"  [{imp}] Status: {r.status_code}")
        if r.status_code != 200:
            print(f"  Body: {r.text[:200]}")
        else:
            print(f"  SUCCESS: {r.text[:150]}")
            break
    except Exception as e:
        print(f"  [{imp}] Error: {str(e)[:80]}")
    time.sleep(1)
