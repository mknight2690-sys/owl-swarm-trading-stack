"""Test curl_cffi with proper impersonation to bypass Cloudflare."""
from curl_cffi import requests

# Test with different impersonation targets
for imp in ["chrome_120", "chrome_124", "chrome_131", "edge_120", "safari_15_6"]:
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
        print(f"{imp}: Error: {e}")
