"""Test curl_cffi with basic impersonation."""
from curl_cffi import requests

# Try basic impersonation
for imp in ["chrome", "chrome110", "chrome116", "chrome120", "edge", "safari", "firefox"]:
    try:
        s = requests.Session(impersonate=imp, timeout=15)
        r = s.get(
            "https://api.blofin.com/api/v1/market/instruments?instType=SWAP&instId=BTC-USDT-SWAP",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Origin": "https://blofin.com",
                "Referer": "https://blofin.com/",
            },
        )
        print(f"{imp}: status={r.status_code}, len={len(r.text)}")
        if r.status_code == 200:
            print(f"  SUCCESS! Body: {r.text[:200]}")
            break
        else:
            print(f"  Body: {r.text[:100]}")
    except Exception as e:
        err = str(e)[:100]
        print(f"{imp}: Error: {err}")
