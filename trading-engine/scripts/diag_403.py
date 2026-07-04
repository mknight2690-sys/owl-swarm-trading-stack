"""Diagnose which 403s actually matter for trading."""
import sys
sys.path.insert(0, r"C:\Users\mknig\blofin-auto-trader")

from autohedge.tools.blofin_client import BlofinClient
from curl_cffi import requests

client = BlofinClient()

# Test each endpoint that was 403ing
tests = [
    ("/api/v1/account/positions?accountType=futures", "GET", None, True),
    ("/api/v1/account/balance?accountType=futures", "GET", None, True),
    ("/api/v1/trade/positions?instType=SWAP", "GET", None, True),
]

for path, method, body, private in tests:
    url = f"https://openapi.blofin.com{path}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    if private and body:
        import time, json, base64, hmac, hashlib
        from uuid import uuid4
        ts = str(int(time.time() * 1000))
        nonce = str(uuid4())
        body_str = json.dumps(body, separators=(",", ":"))
        prehash = f"{path}{method.upper()}{ts}{nonce}{body_str}"
        sig = base64.b64encode(
            hmac.new(client.credentials.secret_key.encode(), prehash.encode(), hashlib.sha256).hexdigest().encode()
        ).decode()
        headers.update({
            "ACCESS-KEY": client.credentials.api_key,
            "ACCESS-SIGN": sig,
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-NONCE": nonce,
            "ACCESS-PASSPHRASE": client.credentials.passphrase,
        })
    elif private:
        import time, json, base64, hmac, hashlib
        from uuid import uuid4
        ts = str(int(time.time() * 1000))
        nonce = str(uuid4())
        prehash = f"{path}{method.upper()}{ts}{nonce}"
        sig = base64.b64encode(
            hmac.new(client.credentials.secret_key.encode(), prehash.encode(), hashlib.sha256).hexdigest().encode()
        ).decode()
        headers.update({
            "ACCESS-KEY": client.credentials.api_key,
            "ACCESS-SIGN": sig,
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-NONCE": nonce,
            "ACCESS-PASSPHRASE": client.credentials.passphrase,
        })

    for imp in ["chrome120", "chrome110", "chrome"]:
        try:
            r = requests.request(method, url, headers=headers, data=json.dumps(body) if body else None, impersonate=imp, timeout=10)
            path_short = path.split("?")[0].split("/")[-1]
            print(f"{path_short} [{imp}]: {r.status_code}")
            if r.status_code == 200:
                print(f"  SUCCESS: {r.text[:150]}")
                break
            elif r.status_code == 403:
                print(f"  403 - Cloudflare challenge")
            else:
                print(f"  {r.text[:150]}")
        except Exception as e:
            print(f"  Error: {str(e)[:80]}")
    print()
