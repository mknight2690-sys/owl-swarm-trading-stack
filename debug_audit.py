import sys
from unittest.mock import MagicMock
sys.modules["loguru"] = MagicMock()

import os
import json
# Add trading-engine to path
sys.path.append(r"C:\Users\mknig\owl-swarm\trading-engine")

from autohedge.tpsl_guard import audit_open_positions_tpsl

print("Running Audit...")
try:
    report = audit_open_positions_tpsl(force_refresh=True)
    print(json.dumps(report, indent=2))
except Exception as e:
    print(f"Error: {e}")
