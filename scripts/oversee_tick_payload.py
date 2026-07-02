#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, r"C:\Users\mknig\blofin-auto-trader")
os.environ.setdefault("OUTPUT_DIR", r"C:\Users\mknig\owl-swarm\outputs")
os.environ.setdefault("OWL_SWARM_ROOT", r"C:\Users\mknig\owl-swarm")

from autohedge.cursor_wake import oversee_tick_payload

print(oversee_tick_payload())
