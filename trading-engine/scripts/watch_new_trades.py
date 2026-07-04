"""Watch for NEW trades only (starting from now)."""
import time
import sys
import io
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

TRADE_JOURNAL = Path(r"C:\Users\mknig\blofin-auto-trader\outputs\trade_journal.jsonl")

# Get current last line count as baseline
if TRADE_JOURNAL.exists():
    baseline_lines = len(TRADE_JOURNAL.read_text().strip().splitlines())
else:
    baseline_lines = 0

print(f"HAWK: Watching for NEW trades (baseline: {baseline_lines} existing entries)")
print("=" * 60)

start_time = time.time()
trade_count = 0

while True:
    try:
        if TRADE_JOURNAL.exists():
            lines = TRADE_JOURNAL.read_text().strip().splitlines()
            new_lines = lines[baseline_lines:]
            for line in new_lines:
                line = line.strip()
                if not line:
                    continue
                if '"order_placed"' in line:
                    import json
                    try:
                        entry = json.loads(line)
                        dt = datetime.fromtimestamp(entry.get("ts", 0)).strftime("%H:%M:%S")
                        print(f"[NEW TRADE] {dt} | {entry.get('instId')} {entry.get('side')} size={entry.get('size')}")
                        trade_count += 1
                    except json.JSONDecodeError:
                        pass
                elif '"position_closed"' in line:
                    import json
                    try:
                        entry = json.loads(line)
                        dt = datetime.fromtimestamp(entry.get("ts", 0)).strftime("%H:%M:%S")
                        print(f"[CLOSED] {dt} | {entry.get('instId')} pnl={entry.get('realizedPnl')}")
                    except json.JSONDecodeError:
                        pass
                baseline_lines += 1
        
        elapsed = time.time() - start_time
        if trade_count >= 3:
            print("\n" + "=" * 60)
            print(f"SUCCESS! {trade_count} NEW trades taken in {elapsed:.0f}s")
            print("=" * 60)
            sys.exit(0)
        
        if elapsed > 3600:
            print(f"Timeout after 1 hour. New trades: {trade_count}")
            sys.exit(1)
        
        time.sleep(1)
    except KeyboardInterrupt:
        print(f"\nStopped. New trades: {trade_count}")
        sys.exit(0)
