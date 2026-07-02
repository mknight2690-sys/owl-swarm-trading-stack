#!/usr/bin/env python3
"""Debug the balance response format."""
import sys, json
sys.path.insert(0, r'C:\Users\mknig\blofin-auto-trader')
from autohedge.tools.blofin_client import BlofinClient
from autohedge.blofin_credentials import load_blofin_credentials

creds = load_blofin_credentials()
c = BlofinClient(creds)

print("=== BALANCE ===")
bal = c.get_balances()
print(json.dumps(bal, indent=2, default=str)[:2000])

print("\n=== POSITIONS ===")
pos = c.get_positions()
print(json.dumps(pos, indent=2, default=str)[:2000])
