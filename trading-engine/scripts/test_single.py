"""Test single endpoint with different impersonation."""
from curl_cffi import requests
import time

BASE = "https://openapi.blofin.com"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Test tickers with different impersonations
impersonations = ["chrome120", "chrome110", "chrome116", "chrome124", "chrome126", "chrome131", "chrome133", "chrome", "edge101", "edge112", "safari15_5", "firefox115", "firefox120"]

for imp in impersonations:
    url = BASE + "/api/v1/market/tickers?instType=SWAP"
    try:
        r = requests.get(url, headers=headers, impersonate=imp, timeout=10)
        status = r.status_code
        body = r.text[:100]
        print(f"{imp}: status={status} {body}")
        if status == 200:
            print(f"\n=== SUCCESS with {imp} ===")
            break
    except Exception as e:
        print(f"{imp}: Error: {str(e)[:60]}")
    time.sleep(0.5)
