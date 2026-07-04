"""Watch the live-run.log for trades and errors in real-time."""
import time
import sys
import io
from pathlib import Path

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

LOG_PATH = Path(r"C:\Users\mknig\blofin-auto-trader\outputs\live-run.log")
TRADE_JOURNAL = Path(r"C:\Users\mknig\blofin-auto-trader\outputs\trade_journal.jsonl")

def read_new_lines(path, last_pos=0):
    """Read new lines from a file since last position."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(last_pos)
            new_content = f.read()
            new_pos = f.tell()
            if new_content:
                return new_content.splitlines(), new_pos
            return [], last_pos
    except FileNotFoundError:
        return [], last_pos

def main():
    log_pos = 0
    journal_pos = 0
    trade_count = 0
    error_count = 0
    start_time = time.time()
    
    print("HAWK: Watching loop in real-time...")
    print("=" * 60)
    
    while True:
        # Check log file
        new_lines, log_pos = read_new_lines(LOG_PATH, log_pos)
        for line in new_lines:
            line = line.strip()
            if not line or line.startswith("---"):
                continue
            
            # Highlight important events
            if any(k in line.lower() for k in ["error", "exception", "traceback"]):
                print(f"[ERROR] {line}")
                error_count += 1
            elif "order_placed" in line.lower():
                print(f"[ORDER] {line}")
                trade_count += 1
            elif "order_blocked" in line.lower():
                print(f"[BLOCKED] {line}")
            elif "position_closed" in line.lower():
                print(f"[CLOSED] {line}")
            elif "deterministic execution" in line.lower():
                print(f"[EXEC] {line}")
            elif "403" in line and "impersonate" in line:
                # Skip 403 rotation warnings -- they're handled
                pass
            elif any(k in line.lower() for k in ["warning", "veto", "rejected"]):
                print(f"[WARN] {line}")
        
        # Check trade journal for new entries
        new_journal, journal_pos = read_new_lines(TRADE_JOURNAL, journal_pos)
        for line in new_journal:
            line = line.strip()
            if not line:
                continue
            if '"order_placed"' in line:
                import json
                try:
                    entry = json.loads(line)
                    from datetime import datetime
                    dt = datetime.fromtimestamp(entry.get("ts", 0)).strftime("%H:%M:%S")
                    print(f"[JOURNAL] {dt} | ORDER_PLACED | {entry.get('instId')} {entry.get('side')} size={entry.get('size')}")
                    trade_count += 1
                except json.JSONDecodeError:
                    pass
            elif '"position_closed"' in line:
                import json
                try:
                    entry = json.loads(line)
                    from datetime import datetime
                    dt = datetime.fromtimestamp(entry.get("ts", 0)).strftime("%H:%M:%S")
                    print(f"[JOURNAL] {dt} | POSITION_CLOSED | {entry.get('instId')} pnl={entry.get('realizedPnl')}")
                except json.JSONDecodeError:
                    pass
        
        elapsed = time.time() - start_time
        if trade_count >= 3:
            print("\n" + "=" * 60)
            print(f"SUCCESS! {trade_count} trades taken in {elapsed:.0f}s")
            print("=" * 60)
            sys.exit(0)
        
        if elapsed > 3600:  # 1 hour timeout
            print(f"Timeout after 1 hour. Trades: {trade_count}, Errors: {error_count}")
            sys.exit(1)
        
        time.sleep(0.5)

if __name__ == "__main__":
    main()
