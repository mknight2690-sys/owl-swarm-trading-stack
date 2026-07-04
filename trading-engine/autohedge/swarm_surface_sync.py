"""
Surface sync — when swarm behavior/architecture changes, update ALL user-visible surfaces.

Taught to every agent and enforced in playbook so dashboard, graph API, doctrines, and
launcher/monitor never drift from production logic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
OWL_ROOT = Path(os.environ.get("OWL_SWARM_ROOT", r"C:\Users\mknig\owl-swarm"))
AUTO_ROOT = Path(os.environ.get("AUTO_TRADER_ROOT", r"C:\Users\mknig\blofin-auto-trader"))

# Surfaces that MUST stay aligned when swarm architecture changes
SYNC_SURFACES: list[dict[str, str]] = [
    {"id": "dashboard", "path": str(OWL_ROOT / "swarm_dashboard.html"), "owner": "Ops-Monitor-Agent"},
    {"id": "swarm_topology", "path": str(AUTO_ROOT / "autohedge" / "swarm_topology.py"), "owner": "Verifier-Agent"},
    {"id": "collective_audit", "path": str(AUTO_ROOT / "autohedge" / "collective_audit.py"), "owner": "Verifier-Agent"},
    {"id": "prompts", "path": str(AUTO_ROOT / "autohedge" / "prompts.py"), "owner": "Trading-Director"},
    {"id": "workers", "path": str(AUTO_ROOT / "autohedge" / "workers.py"), "owner": "Trading-Director"},
    {"id": "pentest_agents", "path": str(AUTO_ROOT / "autohedge" / "pentest_agents.py"), "owner": "Pentest-Operator-Agent"},
    {"id": "swarm_tasks", "path": str(AUTO_ROOT / "autohedge" / "swarm_tasks.py"), "owner": "Ops-Monitor-Agent"},
    {"id": "launch", "path": str(OWL_ROOT / "launch.ps1"), "owner": "Ops-Monitor-Agent"},
    {"id": "monitor", "path": str(OWL_ROOT / "scripts" / "monitor_health.ps1"), "owner": "Ops-Monitor-Agent"},
]

# Graph API fields the dashboard must render (add here when extending /api/swarm-graph)
REQUIRED_GRAPH_FIELDS = (
    "clique_rugged",
    "clique_weak_links",
    "mesh_fulfillment",
    "mesh_edges",
    "polymorphic",
    "nodes",
    "edges",
    "verify_status",
    "convergence_streak",
)

DASHBOARD_MARKERS = (
    "mesh_fulfillment",
    "meshFulfillment",
    "clique_rugged",
    "cliqueRugged",
    "peer_audit",
    "polymorphic",
)


def verify_surface_sync() -> dict[str, Any]:
    """Check dashboard + graph API alignment; teach playbook if drift detected."""
    report: dict[str, Any] = {"ok": True, "issues": [], "surfaces": {}, "ts": __import__("time").time()}

    dash = OWL_ROOT / "swarm_dashboard.html"
    report["surfaces"]["dashboard_exists"] = dash.is_file()
    if dash.is_file():
        text = dash.read_text(encoding="utf-8", errors="replace")
        missing_markers = [m for m in DASHBOARD_MARKERS if m not in text]
        if missing_markers:
            report["ok"] = False
            report["issues"].append(f"dashboard missing markers: {missing_markers}")
    else:
        report["ok"] = False
        report["issues"].append("swarm_dashboard.html missing")

    try:
        from autohedge.swarm_topology import get_swarm_graph

        graph = get_swarm_graph()
        missing_fields = [f for f in REQUIRED_GRAPH_FIELDS if f not in graph]
        if missing_fields:
            report["ok"] = False
            report["issues"].append(f"swarm-graph missing fields: {missing_fields}")
        report["graph_sample"] = {
            "mesh_edges": graph.get("mesh_edges"),
            "polymorphic": graph.get("polymorphic"),
            "mesh_fulfillment": graph.get("mesh_fulfillment"),
        }
    except Exception as exc:
        report["ok"] = False
        report["issues"].append(f"graph check failed: {exc}")

    if not report["ok"]:
        try:
            from autohedge.self_heal_playbook import teach_fix

            teach_fix(
                "surface_sync_drift",
                title="User-visible surfaces drifted from swarm logic",
                detail="; ".join(report["issues"][:5]),
                component="swarm_surface_sync",
                action="Update swarm_dashboard.html + graph API + prompts/playbook together",
                proof=report,
            )
        except Exception:
            pass

    return report


def surface_sync_checklist_text() -> str:
    lines = ["SURFACE SYNC CHECKLIST (required on every architecture change):"]
    for row in SYNC_SURFACES:
        lines.append(f"  - {row['id']}: {row['path']} ({row['owner']})")
    lines.append("  - Extend REQUIRED_GRAPH_FIELDS in swarm_surface_sync.py when adding graph keys")
    lines.append("  - Extend swarm_dashboard.html to render new graph/status fields")
    lines.append("  - teach_fix in self_heal_playbook if new auto-heal path")
    lines.append("  - request_restart / save_runtime_fingerprint after deploy")
    return "\n".join(lines)
