"""Check recent trades in the journal."""
import json
from pathlib import Path

journal = Path(r"C:\Users\mknig\blofin-auto-trader\outputs\trade_journal.jsonl")
if not journal.exists():
    print("No trade journal found")
    exit()

lines = journal.read_text().strip().splitlines()
print(f"Total entries: {len(lines)}")

# Show last 10 entries
for line in lines[-10:]:
    try:
        entry = json.loads(line)
        ts = entry.get("ts", 0)
        from datetime import datetime
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        etype = entry.get("type", "unknown")
        inst = entry.get("instId", "")
        if etype == "order_placed":
            side = entry.get("side", "")
            size = entry.get("size", "")
            print(f"  {dt} | {etype} | {inst} {side} size={size}")
        elif etype == "position_closed":
            pnl = entry.get("realizedPnl", "")
            print(f"  {dt} | {etype} | {inst} pnl={pnl}")
        else:
            print(f"  {dt} | {etype} | {inst} | {entry}")
    except json.JSONDecodeError:
        pass
