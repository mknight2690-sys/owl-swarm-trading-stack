"""Diagnose why we're getting 403s - test each endpoint with each fingerprint."""
import sys, time, json
sys.path.insert(0, r"C:\Users\mknig\blofin-auto-trader")
from autohedge.tools.blofin_client import BlofinClient
from curl_cffi import requests

client = BlofinClient()

# Test each endpoint with each fingerprint, one at a time with 2s delays
tests = [
    ("/api/v1/market/tickers?instType=SWAP", "GET", None, False),
    ("/api/v1/account/positions?accountType=futures", "GET", None, True),
    ("/api/v1/account/balance?accountType=futures", "GET", None, True),
    ("/api/v1/market/instruments?instType=SWAP", "GET", None, False),
    ("/api/v1/market/funding-rate?instId=BTC-USDT", "GET", None, False),
    ("/api/v1/market/candles?instId=BTC-USDT&bar=1H&limit=10", "GET", None, False),
]

impersonates = ["chrome120", "chrome110", "chrome116", "chrome124", "chrome", "edge101", "edge112"]

results = {}
for path, method, body, private in tests:
    short = path.split("?")[0].split("/")[-1]
    results[short] = []
    for imp in impersonates:
        url = f"https://openapi.blofin.com{path}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        if private:
            import base64, hmac, hashlib
            from uuid import uuid4
            ts = str(int(time.time() * 1000))
            nonce = str(uuid4())
            body_str = json.dumps(body, separators=(",", ":")) if body else ""
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
        try:
            r = requests.request(method, url, headers=headers, data=json.dumps(body) if body else None, impersonate=imp, timeout=10)
            status = r.status_code
            body_preview = r.text[:80] if status != 200 else "OK"
        except Exception as e:
            status = f"ERR:{str(e)[:40]}"
            body_preview = ""
        results[short].append((imp, status))
        print(f"{short:20s} | {imp:12s} | {status}")
        time.sleep(2)  # 2s between requests to avoid rate limiting

print("\n=== SUMMARY ===")
for endpoint, rlist in results.items():
    working = [imp for imp, s in rlist if s == 200]
    print(f"{endpoint}: {len(working)}/{len(rlist)} fingerprints work: {working}")
