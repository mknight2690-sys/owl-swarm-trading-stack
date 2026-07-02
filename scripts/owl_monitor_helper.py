#!/usr/bin/env python3
"""Monitor/launcher helper — teach playbook events without PowerShell quoting pain."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = r"C:\Users\mknig\owl-swarm"
sys.path.insert(0, r"C:\Users\mknig\blofin-auto-trader")
os.environ.setdefault("OUTPUT_DIR", os.path.join(ROOT, "outputs"))
os.environ.setdefault("OWL_PRERANK_TOP_N", "18")

from autohedge.env_loader import load_env

load_env()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("event", choices=("graceful_restart", "stack_down", "save_fingerprint"))
    p.add_argument("--detail", default="")
    p.add_argument("--pid", type=int, default=0)
    args = p.parse_args()

    if args.event == "save_fingerprint":
        from autohedge.swarm_restart import save_runtime_fingerprint

        save_runtime_fingerprint()
        return 0

    from autohedge.self_heal_playbook import teach_fix

    if args.event == "graceful_restart":
        teach_fix(
            "graceful_restart",
            title="Monitor applied graceful restart",
            detail=args.detail or "graceful reload",
            component="monitor_health",
            action="restart owl_llm_loop on restart_pending",
            proof={"pid": args.pid},
        )
    elif args.event == "stack_down":
        teach_fix(
            "stack_down",
            title="Monitor auto-restarted OWL stack",
            detail=args.detail or "Stack was DOWN",
            component="monitor_health",
            action="restart owl_llm_loop.py",
            proof={"pid": args.pid},
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
