"""
Swarm topology — visual connection structure from the X self-verifying loop video.

Functional layers (matches Kimi Agent Swarm / 0xRicker demo):
  1. ORCHESTRATOR hub spawns and coordinates all agents
  2. PARALLEL support agents fan out from hub (ops, verify, research, profit, market)
  3. SEQUENTIAL trading pipeline (Portfolio → Execution)
  4. VERIFY GATE — every output cross-checked against Blofin live API
  5. REJECT → RETRY loops back to failing agent until zero errors
  6. COMPOUND — verified outputs flow into skill library + learning audit
  7. COLLECTIVE CARE — full polymorphic mesh: every agent peer-linked to every other until all fulfill

The dashboard renders this graph live with pulsing connections as work flows.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

def _output_dir() -> Path:
    return Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))


GRAPH_PATH = _output_dir() / "swarm_graph.json"

# Node roles for styling in the UI
ROLE_ORCHESTRATOR = "orchestrator"
ROLE_SUPPORT = "support"
ROLE_PIPELINE = "pipeline"
ROLE_GATE = "gate"
ROLE_DATA = "data"
ROLE_COMPOUND = "compound"
ROLE_PENTEST = "pentest"

# Connection types — each has distinct visual behaviour in the dashboard
EDGE_SPAWN = "spawn"           # orchestrator → agent
EDGE_HANDOFF = "handoff"         # sequential pipeline step
EDGE_VERIFY = "verify"           # agent → verify gate
EDGE_REJECT = "reject"           # verify gate → agent (retry loop)
EDGE_DATA = "data"               # live API ↔ verify / agents
EDGE_COMPOUND = "compound"       # verify → skill library
EDGE_PEER = "peer_audit"         # collective care sniff
EDGE_REPAIR = "repair"           # ops → infrastructure
EDGE_OVERSIGHT = "oversight"     # director oversees all

_lock = threading.Lock()
_node_state: dict[str, dict[str, Any]] = {}
_edge_pulse: dict[str, float] = {}  # edge_id → last_pulse_ts
_cycle = 0
_active_agent = ""
_verify_status = "idle"  # idle | checking | pass | fail
_convergence_streak = 0
_cycle_verify_fails = 0
_verify_fail_history: list[int] = []


def _default_nodes() -> list[dict[str, Any]]:
    """Static graph layout — positions are normalized 0-1 for responsive canvas."""
    return [
        {"id": "blofin-api", "label": "Blofin Live API", "role": ROLE_DATA, "x": 0.5, "y": 0.06, "group": "data"},
        {"id": "verify-gate", "label": "Verify Gate", "role": ROLE_GATE, "x": 0.5, "y": 0.16, "group": "gate"},
        {
            "id": "Trading-Director",
            "label": "Director",
            "role": ROLE_ORCHESTRATOR,
            "x": 0.5,
            "y": 0.28,
            "group": "orchestrator",
        },
        {"id": "Ops-Monitor-Agent", "label": "Ops", "role": ROLE_SUPPORT, "x": 0.12, "y": 0.42, "group": "support"},
        {"id": "Verifier-Agent", "label": "Verifier", "role": ROLE_SUPPORT, "x": 0.28, "y": 0.42, "group": "support"},
        {
            "id": "Tactics-Researcher-Agent",
            "label": "Tactics",
            "role": ROLE_SUPPORT,
            "x": 0.44,
            "y": 0.42,
            "group": "support",
        },
        {
            "id": "Profit-Strategist-Agent",
            "label": "Profit",
            "role": ROLE_SUPPORT,
            "x": 0.56,
            "y": 0.42,
            "group": "support",
        },
        {
            "id": "Market-Researcher-Agent",
            "label": "Market",
            "role": ROLE_SUPPORT,
            "x": 0.72,
            "y": 0.42,
            "group": "support",
        },
        {"id": "Portfolio-Manager", "label": "Portfolio", "role": ROLE_PIPELINE, "x": 0.08, "y": 0.62, "group": "pipeline"},
        {"id": "Sentiment-Agent", "label": "Sentiment", "role": ROLE_PIPELINE, "x": 0.24, "y": 0.62, "group": "pipeline"},
        {"id": "Quant-Analyst", "label": "Quant", "role": ROLE_PIPELINE, "x": 0.40, "y": 0.62, "group": "pipeline"},
        {"id": "Risk-Manager", "label": "Risk", "role": ROLE_PIPELINE, "x": 0.56, "y": 0.62, "group": "pipeline"},
        {"id": "Execution-Agent", "label": "Execution", "role": ROLE_PIPELINE, "x": 0.72, "y": 0.62, "group": "pipeline"},
        {"id": "Pentest-Scout-Agent", "label": "P-Scout", "role": ROLE_PENTEST, "x": 0.10, "y": 0.52, "group": "pentest"},
        {"id": "Pentest-Trade-Hunter-Agent", "label": "P-Trade", "role": ROLE_PENTEST, "x": 0.30, "y": 0.52, "group": "pentest"},
        {"id": "Pentest-Integrity-Agent", "label": "P-Integrity", "role": ROLE_PENTEST, "x": 0.50, "y": 0.52, "group": "pentest"},
        {"id": "Pentest-Operator-Agent", "label": "P-Operator", "role": ROLE_PENTEST, "x": 0.70, "y": 0.52, "group": "pentest"},
        {"id": "skill-library", "label": "Skill Library", "role": ROLE_COMPOUND, "x": 0.30, "y": 0.88, "group": "compound"},
        {"id": "learning-audit", "label": "Learning Audit", "role": ROLE_COMPOUND, "x": 0.50, "y": 0.88, "group": "compound"},
        {"id": "collective-care", "label": "Collective Care", "role": ROLE_COMPOUND, "x": 0.70, "y": 0.88, "group": "compound"},
    ]


def _default_edges() -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []

    # Orchestrator spawns all agents (hub-and-spoke from video)
    for agent in (
        "Ops-Monitor-Agent",
        "Verifier-Agent",
        "Tactics-Researcher-Agent",
        "Profit-Strategist-Agent",
        "Market-Researcher-Agent",
        "Pentest-Scout-Agent",
        "Pentest-Trade-Hunter-Agent",
        "Pentest-Integrity-Agent",
        "Pentest-Operator-Agent",
        "Portfolio-Manager",
    ):
        edges.append({"id": f"spawn-director-{agent}", "from": "Trading-Director", "to": agent, "type": EDGE_SPAWN})

    # Sequential trading pipeline
    pipeline = [
        "Portfolio-Manager",
        "Sentiment-Agent",
        "Quant-Analyst",
        "Risk-Manager",
        "Execution-Agent",
    ]
    for i in range(len(pipeline) - 1):
        a, b = pipeline[i], pipeline[i + 1]
        edges.append({"id": f"handoff-{a}-{b}", "from": a, "to": b, "type": EDGE_HANDOFF})

    # Every agent verifies against gate (core self-verifying loop)
    all_agents = [
        "Trading-Director",
        "Portfolio-Manager",
        "Sentiment-Agent",
        "Quant-Analyst",
        "Risk-Manager",
        "Execution-Agent",
        "Ops-Monitor-Agent",
        "Verifier-Agent",
        "Tactics-Researcher-Agent",
        "Profit-Strategist-Agent",
        "Market-Researcher-Agent",
        "Pentest-Scout-Agent",
        "Pentest-Trade-Hunter-Agent",
        "Pentest-Integrity-Agent",
        "Pentest-Operator-Agent",
    ]
    for agent in all_agents:
        edges.append({"id": f"verify-{agent}-gate", "from": agent, "to": "verify-gate", "type": EDGE_VERIFY})
        edges.append({"id": f"reject-gate-{agent}", "from": "verify-gate", "to": agent, "type": EDGE_REJECT})

    # Live data feeds verify gate and orchestrator
    edges.append({"id": "data-api-gate", "from": "blofin-api", "to": "verify-gate", "type": EDGE_DATA})
    edges.append({"id": "data-api-director", "from": "blofin-api", "to": "Trading-Director", "type": EDGE_DATA})

    # Verified outputs compound into skill library
    edges.append({"id": "compound-gate-skills", "from": "verify-gate", "to": "skill-library", "type": EDGE_COMPOUND})
    edges.append({"id": "compound-skills-audit", "from": "skill-library", "to": "learning-audit", "type": EDGE_COMPOUND})
    edges.append({"id": "compound-audit-care", "from": "learning-audit", "to": "collective-care", "type": EDGE_COMPOUND})

    # Ops repairs infrastructure
    edges.append({"id": "repair-ops-api", "from": "Ops-Monitor-Agent", "to": "blofin-api", "type": EDGE_REPAIR})

    # Director oversees entire operation
    for target in ("verify-gate", "skill-library", "collective-care"):
        edges.append(
            {"id": f"oversight-director-{target}", "from": "Trading-Director", "to": target, "type": EDGE_OVERSIGHT}
        )

    # Pentest squad chain — scout → hunters → operator
    pentest_chain = [
        "Pentest-Scout-Agent",
        "Pentest-Trade-Hunter-Agent",
        "Pentest-Integrity-Agent",
        "Pentest-Operator-Agent",
    ]
    for i in range(len(pentest_chain) - 1):
        a, b = pentest_chain[i], pentest_chain[i + 1]
        edges.append({"id": f"pentest-{a}-{b}", "from": a, "to": b, "type": "pentest_chain"})

    # Full polymorphic peer mesh — every agent connected to every other (15×14 directed links)
    try:
        from autohedge.collective_audit import all_peer_pairs, peer_edge_id

        for reviewer, reviewed in all_peer_pairs():
            edges.append(
                {
                    "id": peer_edge_id(reviewer, reviewed),
                    "from": reviewer,
                    "to": reviewed,
                    "type": EDGE_PEER,
                }
            )
    except Exception:
        pass

    return edges


def _persist_graph_snapshot() -> None:
    """Fast disk write — no peer mesh / collective_audit (avoids cycle-init deadlock)."""
    now = time.time()
    with _lock:
        nodes = _default_nodes()
        for n in nodes:
            st = _node_state.get(n["id"], {})
            n["status"] = st.get("status", "idle")
            n["detail"] = st.get("detail", "")
            n["updated_at"] = st.get("ts", 0)
        edges = _default_edges()
        for e in edges:
            pulse_ts = _edge_pulse.get(e["id"], 0)
            e["pulsing"] = (now - pulse_ts) < 2.5
            e["pulse_age"] = round(now - pulse_ts, 2) if pulse_ts else None
        pipeline_next = ""
        completed: list[str] = []
        try:
            from autohedge.handoff_pipeline import pipeline_status

            ps = pipeline_status()
            pipeline_next = str(ps.get("next_agent") or "")
            completed = list(ps.get("completed") or [])
            for agent in completed:
                for n in nodes:
                    if n["id"] == agent:
                        n["status"] = "pass"
        except Exception:
            pass
        payload = {
            "cycle": _cycle,
            "active_agent": _active_agent,
            "verify_status": _verify_status,
            "convergence_streak": _convergence_streak,
            "verify_fail_this_cycle": int(globals().get("_cycle_verify_fails") or 0),
            "verify_fail_history": list(globals().get("_verify_fail_history") or []),
            "pipeline_next": pipeline_next,
            "completed": completed,
            "nodes": nodes,
            "edges": edges,
            "updated_at": now,
        }
    _persist_swarm_graph(payload)
    try:
        out = _output_dir()
        out.mkdir(parents=True, exist_ok=True)
        (out / "graph_live.json").write_text(
            json.dumps(
                {
                    "cycle": payload["cycle"],
                    "active_agent": payload["active_agent"],
                    "pipeline_next": pipeline_next,
                    "completed": completed,
                    "verify_status": payload["verify_status"],
                    "updated_at": int(now),
                },
                default=str,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def _persist_graph_async() -> None:
    def _run() -> None:
        try:
            _persist_graph_snapshot()
        except Exception:
            pass

    threading.Thread(target=_run, name="owl-graph-persist", daemon=True).start()


def set_agent_status(agent_id: str, status: str, *, detail: str = "") -> None:
    """status: idle | active | pass | fail | repair | skipped"""
    with _lock:
        _node_state[agent_id] = {
            "status": status,
            "detail": detail,
            "ts": time.time(),
        }
        if status == "active":
            globals()["_active_agent"] = agent_id
            _pulse_edge(f"verify-{agent_id}-gate")
            if agent_id == "Trading-Director":
                for e in _default_edges():
                    if e["type"] == EDGE_SPAWN and e["from"] == "Trading-Director":
                        _pulse_edge(e["id"])
        if status in ("pass", "fail"):
            _pulse_edge(f"verify-{agent_id}-gate")
        if status == "fail":
            _pulse_edge(f"reject-gate-{agent_id}")
    _persist_graph_async()


def sync_agent_status_from_task_board() -> None:
    """Reflect real task board state on the swarm graph (no blanket pass)."""
    try:
        from autohedge.swarm_tasks import get_task_board

        priority = {
            "active": 6,
            "fail": 5,
            "retry": 5,
            "done": 4,
            "pass": 4,
            "skipped": 3,
            "pending": 1,
        }
        status_map = {
            "done": "pass",
            "pass": "pass",
            "skipped": "skipped",
            "fail": "fail",
            "retry": "fail",
            "active": "active",
            "pending": "idle",
        }
        best: dict[str, dict[str, Any]] = {}
        for task in get_task_board().get("all_tasks") or []:
            agent = str(task.get("agent") or "")
            if not agent:
                continue
            st = str(task.get("status") or "pending")
            if agent not in best or priority.get(st, 0) > priority.get(
                str(best[agent].get("status") or ""), 0
            ):
                best[agent] = task
        for agent, task in best.items():
            st = str(task.get("status") or "pending")
            set_agent_status(
                agent,
                status_map.get(st, "idle"),
                detail=str(task.get("detail") or "")[:120],
            )
    except Exception as exc:
        logger.debug("sync_agent_status_from_task_board: {}", exc)


def set_verify_status(status: str) -> None:
    """idle | checking | pass | fail"""
    with _lock:
        globals()["_verify_status"] = status
        _node_state["verify-gate"] = {"status": status, "ts": time.time()}
        if status == "checking":
            _pulse_edge("data-api-gate")
        elif status == "pass":
            _pulse_edge("compound-gate-skills")
            _pulse_edge("compound-skills-audit")
        elif status == "fail" and globals().get("_active_agent"):
            _pulse_edge(f"reject-gate-{globals()['_active_agent']}")
    _persist_graph_async()


def pulse_handoff(from_agent: str, to_agent: str) -> None:
    with _lock:
        _pulse_edge(f"handoff-{from_agent}-{to_agent}")


def pulse_repair() -> None:
    with _lock:
        _pulse_edge("repair-ops-api")
        _node_state["Ops-Monitor-Agent"] = {"status": "repair", "ts": time.time()}


def pulse_peer_audit(reviewer: str, reviewed: str) -> None:
    with _lock:
        try:
            from autohedge.collective_audit import peer_edge_id

            _pulse_edge(peer_edge_id(reviewer, reviewed))
        except Exception:
            rid = reviewer.replace(" ", "-").lower()
            rvid = reviewed.replace(" ", "-").lower()
            _pulse_edge(f"peer-{rid}-{rvid}")


def set_cycle(cycle: int) -> None:
    with _lock:
        globals()["_cycle"] = cycle
    _persist_graph_async()


def reset_pipeline_graph(*, keep_director_active: bool = True) -> None:
    """Idle all trading-pipeline nodes at cycle start — prevents Risk/Exec stuck display."""
    from autohedge.handoff_pipeline import PIPELINE_ORDER

    with _lock:
        globals()["_active_agent"] = "Trading-Director" if keep_director_active else ""
        for agent in PIPELINE_ORDER:
            _node_state[agent] = {"status": "idle", "detail": "", "ts": time.time()}
        if keep_director_active:
            _node_state["Trading-Director"] = {
                "status": "active",
                "detail": "cycle orchestration",
                "ts": time.time(),
            }
    _persist_graph_async()


def set_convergence_streak(streak: int) -> None:
    with _lock:
        globals()["_convergence_streak"] = streak


def record_verify_fail() -> None:
    with _lock:
        globals()["_cycle_verify_fails"] = int(globals().get("_cycle_verify_fails") or 0) + 1


def commit_cycle_verify_fails() -> None:
    """Push this cycle's verify-fail count into history (12→3→0 convergence view)."""
    with _lock:
        hist = list(globals().get("_verify_fail_history") or [])
        hist.append(int(globals().get("_cycle_verify_fails") or 0))
        globals()["_verify_fail_history"] = hist[-12:]
        globals()["_cycle_verify_fails"] = 0


def _pulse_edge(edge_id: str) -> None:
    _edge_pulse[edge_id] = time.time()


def get_swarm_graph() -> dict[str, Any]:
    """Full graph for /api/swarm-graph — nodes, edges, live states, pulses."""
    now = time.time()
    with _lock:
        nodes = _default_nodes()
        for n in nodes:
            st = _node_state.get(n["id"], {})
            n["status"] = st.get("status", "idle")
            n["detail"] = st.get("detail", "")
            n["updated_at"] = st.get("ts", 0)

        edges = _default_edges()
        for e in edges:
            pulse_ts = _edge_pulse.get(e["id"], 0)
            e["pulsing"] = (now - pulse_ts) < 2.5
            e["pulse_age"] = round(now - pulse_ts, 2) if pulse_ts else None

        pipeline_next = ""
        try:
            from autohedge.handoff_pipeline import pipeline_status

            ps = pipeline_status()
            pipeline_next = str(ps.get("next_agent") or "")
            completed = ps.get("completed") or []
            for agent in completed:
                for n in nodes:
                    if n["id"] == agent:
                        n["status"] = "pass"
        except Exception:
            pass

        clique_weak = [
            n["id"]
            for n in nodes
            if n["id"] in (
                "Trading-Director",
                "Ops-Monitor-Agent",
                "Verifier-Agent",
                "Tactics-Researcher-Agent",
                "Profit-Strategist-Agent",
                "Market-Researcher-Agent",
                "Portfolio-Manager",
                "Sentiment-Agent",
                "Quant-Analyst",
                "Risk-Manager",
                "Execution-Agent",
            )
            and n.get("status") in ("fail", "retry", "error")
        ]
        clique_rugged = (
            len(clique_weak) == 0
            and _verify_status in ("pass", "idle", "checking")
        )

        mesh: dict[str, Any] = {}
        mesh_edges = 0
        try:
            from autohedge.collective_audit import all_peer_pairs, mesh_fulfillment

            mesh = mesh_fulfillment(nodes)
            mesh_edges = len(all_peer_pairs())
        except Exception:
            mesh = {"fulfilled": 0, "total": 11, "complete": False}

        payload = {
            "cycle": _cycle,
            "active_agent": _active_agent,
            "verify_status": _verify_status,
            "convergence_streak": _convergence_streak,
            "clique_rugged": clique_rugged,
            "clique_weak_links": clique_weak,
            "mesh_fulfillment": mesh,
            "mesh_edges": mesh_edges,
            "polymorphic": True,
            "verify_fail_this_cycle": int(globals().get("_cycle_verify_fails") or 0),
            "verify_fail_history": list(globals().get("_verify_fail_history") or []),
            "pipeline_next": pipeline_next,
            "nodes": nodes,
            "edges": edges,
            "edge_types": {
                EDGE_SPAWN: "Orchestrator spawns agent",
                EDGE_HANDOFF: "Sequential handoff",
                EDGE_VERIFY: "Output → verify gate",
                EDGE_REJECT: "Reject → retry loop",
                EDGE_DATA: "Live API data feed",
                EDGE_COMPOUND: "Verified → skill library",
                EDGE_PEER: "Polymorphic peer mesh (every agent → every other)",
                EDGE_REPAIR: "Ops self-repair",
                EDGE_OVERSIGHT: "Director oversees",
            },
            "updated_at": now,
        }
        _persist_swarm_graph(payload)
        return payload


def _persist_swarm_graph(data: dict[str, Any]) -> None:
    try:
        out = _output_dir()
        out.mkdir(parents=True, exist_ok=True)
        (out / "swarm_graph.json").write_text(json.dumps(data, default=str), encoding="utf-8")
    except OSError:
        pass


def load_swarm_graph_from_disk() -> dict[str, Any] | None:
    path = _output_dir() / "swarm_graph.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def swarm_graph_json() -> str:
    return json.dumps(get_swarm_graph(), default=str)
