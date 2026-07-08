import sys
from unittest.mock import MagicMock
sys.modules["loguru"] = MagicMock()
sys.modules["swarms"] = MagicMock()
sys.modules["litellm"] = MagicMock()
sys.modules["litellm.utils"] = MagicMock()

import os
import json
# Add trading-engine to path
sys.path.append(r"C:\Users\mknig\owl-swarm\trading-engine")

from autohedge.tpsl_guard import repair_missing_tpsl

# Mock blofin_place_tpsl to see what happens
import autohedge.tools.blofin_tools as blofin_tools
blofin_tools.blofin_place_tpsl = MagicMock(return_value='{"code":"0", "msg":"success"}')

print("Running Manual Repair for CTR-USDT...")
try:
    result = repair_missing_tpsl(inst_id="CTR-USDT")
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"Error: {e}")
