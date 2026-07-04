"""Test all BloFin API endpoints with curl_cffi chrome120 impersonation."""
from curl_cffi import requests
import json

BASE = "https://openapi.blofin.com"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

test_paths = [
    "/api/v1/market/instruments?instType=SWAP&instId=BTC-USDT-SWAP",
    "/api/v1/market/tickers?instType=SWAP",
    "/api/v1/market/candles?instType=SWAP&instId=BTC-USDT-SWAP&bar=1H&limit=5",
    "/api/v1/market/funding-rate?instType=SWAP&instId=BTC-USDT-SWAP",
    "/api/v1/public/info?instType=SWAP&instId=BTC-USDT-SWAP",
]

for path in test_paths:
    url = BASE + path
    try:
        r = requests.get(url, headers=headers, impersonate="chrome120", timeout=10)
        status = r.status_code
        body = r.text[:150]
        endpoint = path.split("?")[0].split("/")[-1]
        print(f"{endpoint}: status={status}")
        if status == 200:
            print(f"  {body}")
        else:
            print(f"  {body}")
        print()
    except Exception as e:
        print(f"Error: {e}")
