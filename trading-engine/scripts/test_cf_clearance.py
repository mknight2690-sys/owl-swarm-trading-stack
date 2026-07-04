"""Test getting cf_clearance cookie by solving Cloudflare challenge."""
from curl_cffi import requests
import time

# First, hit the challenge with a browser-like client to get cf_clearance
session = requests.Session(impersonate="chrome120")

# Hit a public endpoint first to get the challenge cookie
print("Step 1: Hitting public endpoint to get cf_clearance cookie...")
r = session.get(
    "https://openapi.blofin.com/api/v1/market/tickers?instType=SWAP",
    timeout=30,
)
print(f"  Status: {r.status_code}")
print(f"  Cookies: {dict(session.cookies)}")

# Now try a private endpoint with the clearance cookie
print("\nStep 2: Hitting private endpoint with clearance cookie...")
r2 = session.get(
    "https://openapi.blofin.com/api/v1/account/positions?accountType=futures",
    timeout=30,
)
print(f"  Status: {r2.status_code}")
print(f"  Body: {r2.text[:200]}")

# Also try with fresh session but same impersonate
print("\nStep 3: Fresh session, private endpoint...")
session2 = requests.Session(impersonate="chrome120")
r3 = session2.get(
    "https://openapi.blofin.com/api/v1/account/positions?accountType=futures",
    timeout=30,
)
print(f"  Status: {r3.status_code}")
print(f"  Body: {r3.text[:200]}")
