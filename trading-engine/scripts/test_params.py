"""Test correct instId format for BloFin public endpoints."""
from curl_cffi import requests

BASE = "https://openapi.blofin.com"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Test different instId formats
tests = [
    ("/api/v1/market/tickers?instType=SWAP&instId=BTC-USDT", "BTC-USDT"),
    ("/api/v1/market/tickers?instType=SWAP&instId=BTC-USDT-SWAP", "BTC-USDT-SWAP"),
    ("/api/v1/market/tickers?instId=BTC-USDT", "BTC-USDT no type"),
    ("/api/v1/market/instruments?instType=SWAP&instId=BTC-USDT", "instruments BTC-USDT"),
    ("/api/v1/market/instruments?instType=SWAP&instId=BTC-USDT-SWAP", "instruments BTC-USDT-SWAP"),
    ("/api/v1/market/candles?instType=SWAP&instId=BTC-USDT&bar=1H&limit=5", "candles BTC-USDT"),
    ("/api/v1/market/candles?instType=SWAP&instId=BTC-USDT-SWAP&bar=1H&limit=5", "candles BTC-USDT-SWAP"),
]

for path, label in tests:
    url = BASE + path
    try:
        r = requests.get(url, headers=headers, impersonate="chrome120", timeout=10)
        status = r.status_code
        body = r.text[:120]
        print(f"{label}: status={status}")
        if status == 200:
            print(f"  {body}")
        else:
            print(f"  {body}")
        print()
    except Exception as e:
        print(f"{label}: Error: {e}")
