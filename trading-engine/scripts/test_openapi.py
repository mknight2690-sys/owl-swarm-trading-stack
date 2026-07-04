"""Test the correct BloFin API endpoint (openapi.blofin.com)."""
import requests

# The correct base URL per BloFin docs: https://openapi.blofin.com
# Public endpoints don't need auth
urls = [
    "https://openapi.blofin.com/api/v1/market/instruments?instType=SWAP&instId=BTC-USDT-SWAP",
    "https://openapi.blofin.com/api/v1/market/tickers?instType=SWAP",
    "https://openapi.blofin.com/api/v1/market/candles?instType=SWAP&instId=BTC-USDT-SWAP&bar=1H&limit=10",
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

for url in urls:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"URL: {url.split('?')[0].split('/')[-1]}")
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            print(f"  SUCCESS! Body: {r.text[:200]}")
        else:
            print(f"  Body: {r.text[:200]}")
        print()
    except Exception as e:
        print(f"  Error: {e}")
