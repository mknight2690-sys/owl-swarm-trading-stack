"""Test curl_cffi with BloFin - different impersonation strategies."""
from curl_cffi import requests

url = "https://openapi.blofin.com/api/v1/market/instruments?instType=SWAP&instId=BTC-USDT-SWAP"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Try different impersonation targets
for impersonate in ["chrome", "chrome120", "chrome124", "chrome131", "edge101", "safari15_5"]:
    try:
        r = requests.get(url, headers=headers, impersonate=impersonate, timeout=10)
        status = r.status_code
        body_preview = r.text[:100]
        print(f"impersonate={impersonate}: status={status}")
        if status == 200:
            print(f"  SUCCESS! {body_preview}")
            break
        else:
            print(f"  {body_preview}")
    except Exception as e:
        print(f"impersonate={impersonate}: Error: {e}")

# Also try the demo endpoint
print("\n--- Demo endpoint ---")
demo_url = "https://demo-trading-openapi.blofin.com/api/v1/market/instruments?instType=SWAP&instId=BTC-USDT-SWAP"
for impersonate in ["chrome120", "chrome124"]:
    try:
        r = requests.get(demo_url, headers=headers, impersonate=impersonate, timeout=10)
        status = r.status_code
        print(f"impersonate={impersonate}: status={status}")
        if status == 200:
            print(f"  SUCCESS! {r.text[:100]}")
            break
        else:
            print(f"  {r.text[:100]}")
    except Exception as e:
        print(f"impersonate={impersonate}: Error: {e}")
