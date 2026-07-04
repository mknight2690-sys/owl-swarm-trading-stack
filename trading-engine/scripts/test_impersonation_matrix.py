"""Test all impersonation options for blocked endpoints."""
from curl_cffi import requests
import json

BASE = "https://openapi.blofin.com"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

impersonations = [
    "chrome", "chrome110", "chrome116", "chrome120", "chrome124", 
    "chrome126", "chrome131", "chrome133",
    "edge101", "edge112", "edge116",
    "safari15_5", "safari16", "safari17_2",
    "firefox115", "firefox120", "firefox128",
]

endpoints = [
    "/api/v1/market/instruments?instType=SWAP&instId=BTC-USDT-SWAP",
    "/api/v1/market/candles?instType=SWAP&instId=BTC-USDT-SWAP&bar=1H&limit=5",
    "/api/v1/market/funding-rate?instType=SWAP&instId=BTC-USDT-SWAP",
]

for endpoint in endpoints:
    url = BASE + endpoint
    endpoint_name = endpoint.split("?")[0].split("/")[-1]
    print(f"\n=== {endpoint_name} ===")
    for imp in impersonations:
        try:
            r = requests.get(url, headers=headers, impersonate=imp, timeout=8)
            status = r.status_code
            if status == 200:
                print(f"  {imp}: 200 SUCCESS - {r.text[:80]}")
                break
            else:
                print(f"  {imp}: {status}")
        except Exception as e:
            err = str(e)[:50]
            print(f"  {imp}: Error - {err}")
