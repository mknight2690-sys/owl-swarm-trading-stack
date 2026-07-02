#!/usr/bin/env python3
"""CLI helper for monitor_health.ps1 — avoid PowerShell inline Python parse issues."""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, r"C:\Users\mknig\blofin-auto-trader")
os.environ.setdefault("OUTPUT_DIR", r"C:\Users\mknig\owl-swarm\outputs")

from autohedge.cursor_wake import request_cursor_wake


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("reason")
    p.add_argument("--detail", default="")
    p.add_argument("--source", default="monitor_health")
    p.add_argument("--priority", default="normal")
    args = p.parse_args()
    request_cursor_wake(
        args.reason,
        detail=args.detail,
        source=args.source,
        priority=args.priority,
    )


if __name__ == "__main__":
    main()
