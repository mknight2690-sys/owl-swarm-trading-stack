import sys, json
sys.path.insert(0, r'C:/Users/mknig/blofin-auto-trader')
from autohedge.tools.blofin_client import BlofinClient
from autohedge.blofin_credentials import load_blofin_credentials

creds = load_blofin_credentials()
client = BlofinClient(creds)
print('Client OK')
result = client.get_balances()
print('Balances:', json.dumps(result, default=str)[:500])
positions = client.get_positions()
print('Positions:', len(positions))
