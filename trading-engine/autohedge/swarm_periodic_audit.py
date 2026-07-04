"""
Periodic deep audit — full mesh/clique/pentest/collective care every N minutes.

Light overseer ticks run every 60s (TPSL, playbook, task board).
Deep audit runs on schedule so we stay at the top without API storms every minute.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from loguru import logger

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
AUDIT_LOG = OUTPUT_DIR / "periodic_audit.jsonl"
STATE_FILE = OUTPUT_DIR / "overseer_state.json"

DEEP_INTERVAL_SEC = int(os.environ.get("OWL_DEEP_AUDIT_INTERVAL_SEC", "900"))


def _load_state() -> dict[str, Any]:
    if not STATE_FILE.is_file():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = time.time()
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def deep_audit_due() -> bool:
    state = _load_state()
    last = float(state.get("last_deep_audit_at") or 0)
    return (time.time() - last) >= DEEP_INTERVAL_SEC


def _append_audit(row: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def run_deep_audit(*, source: str = "periodic") -> dict[str, Any]:
    """Full-stack audit: mesh, clique, pentest, collective care, trajectory, optimize."""
    report: dict[str, Any] = {
        "kind": "deep_audit",
        "source": source,
        "ts": time.time(),
        "ok": True,
        "checks": {},
        "actions": [],
        "notes": [],
        "optimization": [],
    }

    try:
        from autohedge.self_heal_playbook import api_cooldown_active

        if api_cooldown_active():
            report["skipped"] = "api_cooldown"
            report["notes"].append("deferred heavy audit during API cooldown")
            _append_audit(report)
            return report
    except Exception:
        pass

    # Pentest squad
    try:
        from autohedge.pentest_agents import run_pentest_squad

        pt = run_pentest_squad(cycle=0, source=source)
        report["checks"]["pentest"] = {
            "ok": pt.get("ok"),
            "critical": (pt.get("mission_queue") or {}).get("critical_count"),
            "kills": len((pt.get("instant_kill") or {}).get("actions") or []),
        }
        if not pt.get("ok") and not pt.get("skipped"):
            report["ok"] = False
    except Exception as exc:
        report["checks"]["pentest"] = {"error": str(exc)}

    # Clique + mesh
    try:
        from autohedge.collective_audit import audit_clique_rugged, run_polymorphic_mesh_audit

        cr = audit_clique_rugged()
        mesh = run_polymorphic_mesh_audit()
        report["checks"]["clique"] = {"rugged": cr.get("rugged"), "weak_links": cr.get("weak_links")}
        report["checks"]["mesh"] = {
            "ok": mesh.get("ok"),
            "fulfillment": mesh.get("fulfillment"),
            "mesh_edges": mesh.get("mesh_edges"),
        }
        if not cr.get("rugged"):
            report["ok"] = False
            report["notes"].append(f"clique weak: {len(cr.get('weak_links') or [])}")
        ful = mesh.get("fulfillment") or {}
        if not mesh.get("ok"):
            report["notes"].append(f"mesh {ful.get('fulfilled')}/{ful.get('total')}")
    except Exception as exc:
        report["checks"]["mesh"] = {"error": str(exc)}

    # Collective care + repair verify
    try:
        from autohedge.collective_audit import collective_care_round, verify_repairs
        from autohedge.swarm_autopilot import preflight_repair

        pf = preflight_repair()
        vr = verify_repairs(pf)
        care = collective_care_round()
        report["checks"]["collective_care"] = care
        report["checks"]["repair_verify"] = vr
        if not vr.get("ok"):
            report["ok"] = False
            report["notes"].append(f"repair verify: {(vr.get('issues') or [])[:2]}")
    except Exception as exc:
        report["checks"]["collective_care"] = {"error": str(exc)}

    # Trading trajectory + optimization hints
    try:
        from autohedge.collective_audit import audit_trading_trajectory

        traj = audit_trading_trajectory()
        report["checks"]["trajectory"] = traj
        if traj.get("improving"):
            report["optimization"].append("maintain_asymmetric_tp: trajectory improving")
        if float(traj.get("total_pnl") or 0) < -0.5:
            report["optimization"].append("tighten_edge_filter: equity drawdown")
        if float(traj.get("avg_win") or 0) == 0 and int(traj.get("trade_count") or 0) > 3:
            report["optimization"].append("review_tp_sl_ratios: wins not banking")
    except Exception as exc:
        report["checks"]["trajectory"] = {"error": str(exc)}

    # Autonomous trade proof (deep only — not every minute)
    try:
        from autohedge.risk_gate import ensure_autonomous_trade

        trade = ensure_autonomous_trade(source=source)
        report["checks"]["autonomous_trade"] = trade
        if trade.get("placed"):
            report["actions"].append(f"trade:{trade.get('instId')}")
    except Exception as exc:
        report["checks"]["autonomous_trade"] = {"error": str(exc)}

    # Teach optimization patterns into playbook when new
    try:
        from autohedge.self_heal_playbook import teach_fix

        for hint in report["optimization"]:
            issue_id = f"optimize_{hint.split(':')[0]}"
            teach_fix(
                issue_id,
                title=f"Optimization hint: {hint.split(':')[0]}",
                detail=hint,
                component="swarm_periodic_audit",
                action=hint,
                proof={"deep_audit_ts": report["ts"]},
            )
    except Exception:
        pass

    state = _load_state()
    state["last_deep_audit_at"] = time.time()
    state["last_deep_audit_ok"] = report["ok"]
    hints = list(state.get("optimization_hints") or [])
    hints.extend(report["optimization"])
    state["optimization_hints"] = hints[-40:]
    _save_state(state)

    _append_audit(report)
    logger.info(
        "DEEP AUDIT ok={} notes={}",
        report["ok"],
        report["notes"][:3],
    )
    return report
