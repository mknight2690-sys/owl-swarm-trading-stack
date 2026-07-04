"""Read last lines from log without locking."""
import sys
path = r"C:\Users\mknig\blofin-auto-trader\outputs\live-run.log"
try:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)
        size = f.tell()
        read_size = min(4096, size)
        f.seek(size - read_size)
        lines = f.read().splitlines()
        for line in lines[-20:]:
            print(line)
except Exception as e:
    print(f"Error: {e}")
