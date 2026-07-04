"""Clean test of BlofinClient with curl_cffi TLS fingerprint impersonation."""
import sys
sys.path.insert(0, r"C:\Users\mknig\blofin-auto-trader")

from autohedge.tools.blofin_client import BlofinClient

client = BlofinClient()

print("=== Test 1: get_tickers (all) ===")
try:
    tickers = client.get_tickers()
    print(f"SUCCESS: {len(tickers)} tickers")
    if tickers:
        t = tickers[0]
        print(f"  Sample: {t.get('instId')} last={t.get('last')}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 2: get_tickers (specific) ===")
try:
    tickers = client.get_tickers("BTC-USDT-SWAP")
    print(f"SUCCESS: {len(tickers)} tickers")
    if tickers:
        print(f"  Sample: {tickers[0].get('instId')} last={tickers[0].get('last')}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 3: list_live_instruments ===")
try:
    insts = client.list_live_instruments()
    print(f"SUCCESS: {len(insts)} instruments")
    if insts:
        print(f"  Sample: {insts[0].get('instId')} minSize={insts[0].get('minSize')}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 4: get_candles ===")
try:
    candles = client.get_candles("BTC-USDT-SWAP", bar="1H", limit=5)
    print(f"SUCCESS: {len(candles)} candles")
    if candles:
        print(f"  Sample: ts={candles[0].get('ts')} o={candles[0].get('o')}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 5: get_funding_rate ===")
try:
    fr = client.get_funding_rate("BTC-USDT-SWAP")
    print(f"SUCCESS: {fr}")
except Exception as e:
    print(f"FAILED: {e}")

print("\nAll tests complete.")
