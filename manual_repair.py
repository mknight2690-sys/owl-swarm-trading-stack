import sys
from unittest.mock import MagicMock
sys.modules["loguru"] = MagicMock()
sys.modules["swarms"] = MagicMock()

import os
import json
# Add trading-engine to path
sys.path.append(r"C:\Users\mknig\owl-swarm\trading-engine")

from autohedge.tpsl_guard import repair_missing_tpsl

print("Running Manual Repair for CTR-USDT...")
try:
    result = repair_missing_tpsl(inst_id="CTR-USDT")
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"Error: {e}")
