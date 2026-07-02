#!/usr/bin/env python3
"""Check which instruments are tradeable with small balance."""
import sys, json
sys.path.insert(0, r'C:\Users\mknig\blofin-auto-trader')
from autohedge.tools.blofin_client import BlofinClient
from autohedge.blofin_credentials import load_blofin_credentials

creds = load_blofin_credentials()
c = BlofinClient(creds)

# Get all tickers for price data (one batch call)
all_tickers = c.get_tickers()
ticker_map = {}
for t in all_tickers:
    inst_id = t.get('instId', '')
    if inst_id:
        ticker_map[inst_id] = t

# Get instruments
instruments = c.get_instruments()
print(f"Total instruments: {len(instruments)}")

available = 1.27

tradeable = []
for inst in instruments:
    inst_id = inst.get('instId', '')
    if not inst_id.endswith('-USDT'):
        continue
    min_size = float(inst.get('minSize', '999') or '999')
    cv = float(inst.get('contractValue', '1') or '1')
    max_lev = float(inst.get('maxLeverage', '1') or '1')
    
    # Get price from ticker map
    t = ticker_map.get(inst_id)
    price = float(t.get('last', 0) or 0) if t else 0
    
    if price <= 0 or min_size <= 0:
        continue
    
    notional = min_size * cv * price
    min_margin = notional / max_lev
    
    if min_margin < available * 0.8:
        vol = float(t.get('volCurrency24h', 0) or 0) if t else 0
        tradeable.append({
            'instId': inst_id,
            'minSize': min_size,
            'cv': cv,
            'price': price,
            'notional': notional,
            'minMargin': min_margin,
            'maxLev': max_lev,
            'vol24h': vol,
        })

# Sort by min margin needed
tradeable.sort(key=lambda x: x['minMargin'])

print(f"\n=== TRADEABLE WITH ${available:.2f} (margin < ${available*0.8:.2f}) ===")
print(f"{'InstId':<20} {'minSz':>8} {'cv':>10} {'Price':>12} {'Notional':>10} {'MinMargin':>10} {'MaxLev':>8} {'Vol24h':>12}")
print("-" * 110)
for t in tradeable[:30]:
    print(f"{t['instId']:<20} {t['minSize']:>8.2f} {t['cv']:>10.6f} {t['price']:>12.6f} {t['notional']:>10.4f} {t['minMargin']:>10.4f} {t['maxLev']:>8.0f}x {t['vol24h']:>12.0f}")

print(f"\nTotal tradeable: {len(tradeable)} out of {len(instruments)}")
