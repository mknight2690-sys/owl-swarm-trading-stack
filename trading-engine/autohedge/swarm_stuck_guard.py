"""
Detect stuck cycles, stale equity stream, and frozen pipeline agents — auto-unstick.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from loguru import logger

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
OWL_LOG = OUTPUT_DIR / "owl-llm.log"
PIPELINE_STATE = OUTPUT_DIR / "pipeline_state.json"
GRAPH_LIVE = OUTPUT_DIR / "graph_live.json"


def _log_age_sec() -> float:
    if not OWL_LOG.is_file():
        return 9999.0
    try:
        return time.time() - OWL_LOG.stat().st_mtime
    except OSError:
        return 9999.0


def check_equity_stream(*, max_age_sec: float = 20.0) -> dict[str, Any]:
    try:
        import sys

        root = Path(os.environ.get("OWL_SWARM_ROOT", r"C:\Users\mknig\owl-swarm"))
        scripts = root / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from equity_stream import equity_stream_healthy, refresh_streaming_equity

        health = equity_stream_healthy(max_age_sec=max_age_sec)
        if not health.get("ok"):
            refresh_streaming_equity(write_curve=True)
            health = equity_stream_healthy(max_age_sec=max_age_sec)
        return health
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def check_pipeline_stuck(*, max_log_age_sec: float = 480.0) -> dict[str, Any]:
    """Risk/Execution appear stuck when Director LLM blocks or veto leaves bad next_agent."""
    report: dict[str, Any] = {"ok": True, "actions": []}
    try:
        from autohedge.handoff_pipeline import audit_pipeline_consistency, repair_pipeline_disk

        audit = audit_pipeline_consistency()
        stuck_ids = {
            "pipeline_veto_execution_stuck",
            "pipeline_dashboard_stuck",
            "pipeline_terminal_next_mismatch",
        }
        if any(f.get("id") in stuck_ids for f in audit.get("findings") or []):
            repair = repair_pipeline_disk()
            if repair.get("fixed"):
                report["actions"].append("repair_pipeline_veto_state")
                report["pipeline"] = repair.get("status")
                return report
    except Exception as exc:
        report["audit_error"] = str(exc)

    age = _log_age_sec()
    if age < max_log_age_sec:
        return report

    try:
        pipe = {}
        if PIPELINE_STATE.is_file():
            pipe = json.loads(PIPELINE_STATE.read_text(encoding="utf-8"))
        completed = set(pipe.get("completed") or [])
        risk_veto = bool(pipe.get("terminal")) and "Risk-Manager" in completed and not pipe.get(
            "risk_approved", True
        )
        if risk_veto or ("Risk-Manager" in completed and "Execution-Agent" in completed):
            return report
        if pipe.get("terminal") and not pipe.get("next_agent"):
            return report

        from autohedge.handoff_pipeline import pipeline_status, run_fast_pipeline_to_execution

        cand = str(pipe.get("candidate_inst_id") or "")
        if not cand:
            live = OUTPUT_DIR / "owl-live.json"
            if live.is_file():
                cand = str(json.loads(live.read_text(encoding="utf-8")).get("pipeline", {}).get("candidate_inst_id") or "")
        if cand:
            fast = run_fast_pipeline_to_execution(cand)
            report["actions"].append(f"unstick_fast_pipeline:{cand}")
            report["pipeline"] = fast.get("status")
            PIPELINE_STATE.write_text(json.dumps(fast.get("status") or pipeline_status(), indent=2), encoding="utf-8")
            report["ok"] = bool(fast.get("ok"))
        else:
            report["ok"] = False
            report["reason"] = "cycle_log_stall_no_candidate"
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
    return report


def run_stuck_guard(*, source: str = "overseer") -> dict[str, Any]:
    report: dict[str, Any] = {
        "source": source,
        "ts": time.time(),
        "equity_stream": check_equity_stream(),
        "pipeline": check_pipeline_stuck(),
        "log_age_sec": round(_log_age_sec(), 1),
    }
    if not report["equity_stream"].get("ok"):
        try:
            from autohedge.self_heal_playbook import teach_fix

            teach_fix(
                "equity_stream_stale",
                title="Dashboard equity frozen — REST throttled",
                detail="Equity must tick every few seconds via WS mark-to-market.",
                component="equity_stream",
                action="refresh_streaming_equity() every 3s from ws-tickers.json + cached positions",
            )
        except Exception:
            pass
    if report["pipeline"].get("actions"):
        try:
            from autohedge.self_heal_playbook import teach_fix

            teach_fix(
                "pipeline_veto_execution_stuck",
                title="Risk veto left Execution active on dashboard",
                detail="terminal=true but next_agent=Execution-Agent after Risk veto",
                component="handoff_pipeline",
                action="next_agent() returns None when terminal; dashboard treats veto as done",
            )
            teach_fix(
                "pipeline_director_stall",
                title="Risk/Execution stuck — Director LLM blocked handoffs",
                detail=f"log_age={report['log_age_sec']}s pipeline incomplete",
                component="handoff_pipeline",
                action="bootstrap_pipeline_for_deterministic + run_fast_pipeline_to_execution before Director",
            )
        except Exception:
            pass
        logger.warning("STUCK GUARD actions: {}", report["pipeline"].get("actions"))
    return report
