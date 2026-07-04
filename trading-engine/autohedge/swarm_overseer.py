"""
Swarm Overseer — 1-minute perpetual monitor, notes, optimize, verify self-healing.

Runs forever alongside the trading loop. Takes notes, checks all subsystems,
verifies playbook auto-heals, and optimizes when patterns emerge.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from loguru import logger

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
OVERSEER_LOG = OUTPUT_DIR / "overseer_notes.jsonl"
OVERSEER_STATE = OUTPUT_DIR / "overseer_state.json"

_started = False
_lock = threading.Lock()


def _append_note(note: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    row = {"ts": time.time(), "ts_iso": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), **note}
    with OVERSEER_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def run_overseer_tick(*, tick: int | None = None) -> dict[str, Any]:
    """One minute oversight pass — check everything, heal, note, optimize hints."""
    report: dict[str, Any] = {
        "tick": tick,
        "ts": time.time(),
        "status": "ok",
        "checks": {},
        "actions": [],
        "notes": [],
    }
    heal: dict[str, Any] = {}

    # 1. Self-heal playbook (fix once, teach forever)
    try:
        from autohedge.self_heal_playbook import run_autonomous_heal

        heal = run_autonomous_heal(source="overseer")
        report["checks"]["self_heal"] = heal
        if heal.get("auto_healed"):
            report["actions"].append(f"playbook_auto_healed:{heal['auto_healed']}")
        if heal.get("newly_taught"):
            report["actions"].append(f"newly_taught:{heal['newly_taught']}")
        if heal.get("failed"):
            report["status"] = "degraded"
            report["notes"].append(f"heal failures: {heal['failed']}")
    except Exception as exc:
        report["checks"]["self_heal"] = {"error": str(exc)}
        report["status"] = "degraded"

    # 1b. TPSL Guard — critical protection audit every minute (never skip)
    try:
        from autohedge.self_heal_playbook import api_cooldown_active
        from autohedge.tpsl_guard import run_tpsl_guard

        if api_cooldown_active():
            report["checks"]["tpsl_guard"] = {"status": "deferred", "reason": "api_cooldown"}
        else:
            tg = run_tpsl_guard(source="overseer")
            report["checks"]["tpsl_guard"] = {
                "status": tg.get("status"),
                "missing": (tg.get("audit") or {}).get("missing"),
                "protected": (tg.get("audit") or {}).get("protected"),
            }
            if tg.get("status") != "ok":
                report["status"] = "degraded"
                report["notes"].append(f"TPSL guard: {tg.get('audit', {}).get('missing')}")
            for act in tg.get("actions") or []:
                report["actions"].append(act)
    except Exception as exc:
        report["checks"]["tpsl_guard"] = {"error": str(exc)}
        report["status"] = "degraded"
        report["notes"].append(f"tpsl_guard error: {exc}")

    # 1c–2c. Heavy checks moved to swarm_periodic_audit (every 15 min by default)
    try:
        from autohedge.swarm_periodic_audit import deep_audit_due, run_deep_audit

        if deep_audit_due():
            deep = run_deep_audit(source="overseer")
            report["checks"]["deep_audit"] = {
                "ok": deep.get("ok"),
                "notes": (deep.get("notes") or [])[:5],
                "optimization": deep.get("optimization"),
            }
            report["actions"].append("deep_audit:ran")
            if not deep.get("ok") and not deep.get("skipped"):
                report["status"] = "degraded"
                report["notes"].extend((deep.get("notes") or [])[:3])
        else:
            report["checks"]["deep_audit"] = {"due": False}
    except Exception as exc:
        report["checks"]["deep_audit"] = {"error": str(exc)}

    # 2b2. Dashboard / graph surface sync (light — disk only)
    try:
        from autohedge.swarm_surface_sync import verify_surface_sync

        sync = verify_surface_sync()
        report["checks"]["surface_sync"] = {"ok": sync.get("ok"), "issues": sync.get("issues")}
        if not sync.get("ok"):
            report["status"] = "degraded"
            report["notes"].append(f"surface sync: {sync.get('issues')}")
    except Exception as exc:
        report["checks"]["surface_sync"] = {"error": str(exc)}

    # 3. Task board + topology + completion audit (light every minute)
    try:
        from autohedge.swarm_tasks import get_task_board
        from autohedge.swarm_topology import get_swarm_graph
        from autohedge.task_completion_audit import audit_cycle_tasks

        tb = get_task_board()
        graph = get_swarm_graph()
        task_audit = audit_cycle_tasks(cycle=int(tb.get("cycle") or 0), source="overseer", auto_repair=True)
        report["checks"]["task_completion"] = {
            "ok": task_audit.get("ok"),
            "incomplete": task_audit.get("incomplete"),
            "phantom_done": task_audit.get("phantom_done"),
            "issues": (task_audit.get("issues") or [])[:5],
        }
        report["checks"]["tasks"] = tb.get("summary")
        report["checks"]["graph"] = {
            "active_agent": graph.get("active_agent"),
            "verify_status": graph.get("verify_status"),
            "convergence_streak": graph.get("convergence_streak"),
        }
        if not task_audit.get("ok"):
            report["status"] = "degraded"
            report["notes"].append(f"task audit: {task_audit.get('issues', [])[:3]}")
        if tb.get("summary", {}).get("failed", 0) > 0:
            report["notes"].append(f"failed tasks: {tb['summary']['failed']}")
    except Exception as exc:
        report["checks"]["tasks"] = {"error": str(exc)}

    # 4. Trading trajectory + equity (disk/journal — no heavy API when cooling down)
    try:
        from autohedge.collective_audit import audit_trading_trajectory
        from autohedge.self_heal_playbook import api_cooldown_active
        from autohedge.swarm_tasks import record_equity

        traj = audit_trading_trajectory()
        report["checks"]["trading"] = {
            "equity_pnl": traj.get("total_pnl"),
            "avg_win": traj.get("avg_win"),
            "improving": traj.get("improving"),
        }
        if not api_cooldown_active():
            try:
                from autohedge.tools.blofin_tools import blofin_get_equity_summary

                eq = json.loads(blofin_get_equity_summary())
                record_equity(int(tick or 0), float(eq.get("equity") or 0), float(eq.get("available") or 0))
            except Exception:
                pass
    except Exception as exc:
        report["checks"]["trading"] = {"error": str(exc)}

    # 5. Playbook stats — are we fixing twice?
    try:
        from autohedge.self_heal_playbook import playbook_summary

        pb = playbook_summary()
        report["checks"]["playbook"] = {
            "taught": pb.get("total_fixes_taught"),
            "auto_heals": pb.get("auto_heals_total"),
        }
        repeat_risk = [f for f in pb.get("fixes", []) if int(f.get("teach_count") or 0) > 3 and int(f.get("auto_apply_count") or 0) == 0]
        if repeat_risk:
            report["notes"].append(f"fixes taught but never auto-applied: {[f.get('issue_id') for f in repeat_risk]}")
    except Exception as exc:
        report["checks"]["playbook"] = {"error": str(exc)}

    # 6. Code/config drift — self-restart when deploy or env changes on disk
    try:
        from autohedge.swarm_restart import check_overseer_restart, restart_pending

        check_overseer_restart()
        pending = restart_pending()
        if pending:
            report["actions"].append(f"restart_pending:{pending.get('reason', '')[:80]}")
            report["notes"].append("graceful restart queued for next cycle")
    except Exception as exc:
        report["checks"]["restart"] = {"error": str(exc)}

    # 7. Optimization hints (deterministic, no LLM cost per minute)
    try:
        state: dict[str, Any] = {}
        if OVERSEER_STATE.is_file():
            state = json.loads(OVERSEER_STATE.read_text(encoding="utf-8"))
        hints: list[str] = list(state.get("optimization_hints") or [])
        if report["checks"].get("trading", {}).get("improving"):
            hints.append("trajectory_improving: maintain asymmetric TP doctrine")
        if heal.get("auto_healed"):
            hints.append(f"playbook_working: {heal['auto_healed']}")
        state["last_tick"] = tick
        state["last_status"] = report["status"]
        state["optimization_hints"] = hints[-30:]
        state["updated_at"] = time.time()
        OVERSEER_STATE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        report["optimization_hints"] = hints[-5:]
    except Exception:
        pass

    # 8. Cursor gap-fill — last resort after swarm self-heal (fix once, teach forever)
    try:
        from autohedge.cursor_gap_fill import run_gap_fill_pass

        gap = run_gap_fill_pass(source="overseer")
        report["checks"]["cursor_gap"] = {
            "gaps": gap.get("gaps_found"),
            "actions": gap.get("actions"),
            "taught": gap.get("taught"),
        }
        if gap.get("gaps_found"):
            report["actions"].extend([f"cursor_gap:{g}" for g in gap["gaps_found"]])
    except Exception as exc:
        report["checks"]["cursor_gap"] = {"error": str(exc)}

    # 9. Stuck guard — equity stream + pipeline freeze
    try:
        from autohedge.swarm_stuck_guard import run_stuck_guard

        stuck = run_stuck_guard(source="overseer")
        report["checks"]["stuck_guard"] = stuck
        if not stuck.get("equity_stream", {}).get("ok"):
            report["notes"].append(f"equity stream stale: {stuck.get('equity_stream')}")
        if stuck.get("pipeline", {}).get("actions"):
            report["actions"].extend(stuck["pipeline"]["actions"])
    except Exception as exc:
        report["checks"]["stuck_guard"] = {"error": str(exc)}

    _append_note(
        {
            "kind": "overseer_tick",
            "status": report["status"],
            "actions": report["actions"],
            "notes": report["notes"],
            "checks_summary": {
                k: v if not isinstance(v, dict) or len(str(v)) < 200 else {**v, "_truncated": True}
                for k, v in report["checks"].items()
            },
        }
    )

    # Deep audit kind logged separately by swarm_periodic_audit
    if report["checks"].get("deep_audit", {}).get("ok") is False:
        _append_note(
            {
                "kind": "deep_audit",
                "status": "degraded",
                "notes": report["checks"]["deep_audit"].get("notes"),
                "optimization": report["checks"]["deep_audit"].get("optimization"),
            }
        )

    if report["status"] != "ok":
        logger.warning("Overseer tick {}: {}", tick, report["notes"])
        try:
            from autohedge.cursor_wake import request_cursor_wake

            request_cursor_wake(
                "overseer_degraded",
                detail="; ".join(report.get("notes") or [])[:400],
                source="overseer",
                priority="high" if report.get("actions") else "normal",
                proof={"actions": report.get("actions"), "checks": list((report.get("checks") or {}).keys())},
            )
        except Exception:
            pass

    return report


def _overseer_loop() -> None:
    interval = int(os.environ.get("OWL_OVERSEER_INTERVAL_SEC", "60"))
    tick = 0
    while True:
        try:
            time.sleep(interval)
            tick += 1
            run_overseer_tick(tick=tick)
        except Exception as exc:
            logger.warning("Overseer loop error: {}", exc)
            _append_note({"kind": "overseer_error", "error": str(exc)})


def ensure_overseer_background() -> None:
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_overseer_loop, name="owl-overseer", daemon=True)
    t.start()
    logger.info("Swarm overseer active (every {}s)", os.environ.get("OWL_OVERSEER_INTERVAL_SEC", "60"))


def overseer_report_json() -> str:
    notes: list[dict[str, Any]] = []
    if OVERSEER_LOG.is_file():
        for line in OVERSEER_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]:
            try:
                notes.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    state: dict[str, Any] = {}
    if OVERSEER_STATE.is_file():
        try:
            state = json.loads(OVERSEER_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return json.dumps({"state": state, "recent_notes": notes}, indent=2, default=str)
