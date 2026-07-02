#!/usr/bin/env python3
"""1-minute overseer tick — called by monitor_health.ps1."""
import os
import sys

ROOT = r"C:\Users\mknig\owl-swarm"
sys.path.insert(0, r"C:\Users\mknig\blofin-auto-trader")
os.environ.setdefault("OUTPUT_DIR", os.path.join(ROOT, "outputs"))
os.environ.setdefault("OWL_SWARM_ROOT", ROOT)
os.environ.setdefault("BLOFIN_MARGIN_MODE", "isolated")
os.environ.setdefault("OWL_PRERANK_TOP_N", "18")
os.environ.setdefault("OWL_MAX_LEVERAGE", "12")

from autohedge.env_loader import load_env

load_env()

# Isolated margin on all repair paths (overseer runs outside owl_llm_loop)
import functools
import autohedge.tools.blofin_tools as _bt

_margin = os.environ.get("BLOFIN_MARGIN_MODE", "isolated")
for _name in ("blofin_place_order", "blofin_place_tpsl", "blofin_close_position"):
    _orig = getattr(_bt, _name)

    @functools.wraps(_orig)
    def _iso_wrapper(*args, _fn=_orig, _m=_margin, **kwargs):
        kwargs.setdefault("margin_mode", _m)
        return _fn(*args, **kwargs)

    setattr(_bt, _name, _iso_wrapper)

from autohedge.swarm_overseer import run_overseer_tick

if __name__ == "__main__":
    r = run_overseer_tick()
    print(
        f"overseer status={r.get('status')} actions={r.get('actions')} "
        f"notes={r.get('notes')}"
    )
