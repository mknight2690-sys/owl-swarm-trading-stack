import sys
import os

# Add trading-engine to path so 'import autohedge' works
sys.path.append(r"C:\Users\mknig\owl-swarm\trading-engine")

from autohedge.tpsl_guard import run_tpsl_guard

print("Running TPSL Guard...")
try:
    result = run_tpsl_guard()
    print(result)
except Exception as e:
    print(f"Error: {e}")
