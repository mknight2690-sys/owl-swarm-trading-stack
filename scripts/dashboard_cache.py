"""Lightweight dashboard data — disk only, no heavy autohedge imports."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(__file__).resolve().parents[1] / "outputs"
TASK_BOARD = OUTPUT / "task_board.json"
GRAPH = OUTPUT / "swarm_graph.json"
GRAPH_LIVE = OUTPUT / "graph_live.json"
STATE = OUTPUT / "owl-state.json"
LIVE = OUTPUT / "owl-live.json"
PIPELINE = OUTPUT / "pipeline_state.json"
LOG_FILE = OUTPUT / "owl-llm.log"
LOCK_FILE = OUTPUT / "owl-llm.lock"
EQUITY = OUTPUT / "equity_curve.jsonl"
LEARNING = OUTPUT / "swarm_learning_audit.jsonl"

PIPELINE_AGENTS = [
    "Portfolio-Manager",
    "Sentiment-Agent",
    "Quant-Analyst",
    "Risk-Manager",
    "Execution-Agent",
]

MESH_AGENTS = frozenset(
    {
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
        "Pentest-Scout-Agent",
        "Pentest-Trade-Hunter-Agent",
        "Pentest-Integrity-Agent",
        "Pentest-Operator-Agent",
        "Dashboard-Agent",
    }
)

_LOG_LINE_RE = re.compile(r"^\[([^\]]+)\]\s+(\w+)\s+(.*)$")
_CYCLE_START_RE = re.compile(r"=== LLM CYCLE (\d+) START")

TASK_SEEDS = [
    ("oversight", "Oversight & Planning", "Trading-Director", "oversee", "Assess full operation, plan cycle"),
    ("ops_health", "Ops / Stack Health", "Ops-Monitor-Agent", "audit", "Stack health check"),
    ("tpsl_protection", "TP/SL Protection Guard", "Ops-Monitor-Agent", "audit", "Verify every position has TP+SL"),
    ("infrastructure_repair", "Self-Heal Repairs", "Ops-Monitor-Agent", "fix", "Preflight self-heal"),
    ("verification", "Verify Gate", "Verifier-Agent", "audit", "Cross-check all agent outputs"),
    ("market_research", "Market Research", "Market-Researcher-Agent", "execute", "Deep-dive top candidate"),
    ("tactics_research", "Internet Tactics", "Tactics-Researcher-Agent", "execute", "Internet + journal tactics"),
    ("profit_optimization", "Profit Optimization", "Profit-Strategist-Agent", "optimize", "Tune asymmetric R:R params"),
    ("trading_pipeline", "Trading Pipeline", "Trading-Director", "execute", "Orchestrate handoff chain"),
    ("portfolio", "Portfolio Analysis", "Portfolio-Manager", "execute", "Margin & position gate"),
    ("sentiment", "Sentiment", "Sentiment-Agent", "execute", "Funding + news bias"),
    ("quant", "Quant Analysis", "Quant-Analyst", "execute", "Technical probability"),
    ("risk", "Risk Approval", "Risk-Manager", "execute", "TP/SL + R:R approval"),
    ("execution", "Trade Execution", "Execution-Agent", "execute", "Place trade + verify protection"),
    ("peer_audit", "Collective Peer Audit", "Verifier-Agent", "audit", "Collective care peer sniff"),
    ("learning_compound", "Compound Learning", "Tactics-Researcher-Agent", "optimize", "Write playbook + audit trail"),
    ("pentest_recon", "Pentest Recon", "Pentest-Scout-Agent", "audit", "Sniff entire swarm"),
    ("pentest_trade_hunt", "Trade Pipeline Hunt", "Pentest-Trade-Hunter-Agent", "audit", "Mission 1: no trades"),
    ("pentest_integrity", "Verifier/Mesh Integrity", "Pentest-Integrity-Agent", "audit", "Mission 2: audit fails"),
    ("pentest_remediate", "Pentest Kill/Fix", "Pentest-Operator-Agent", "fix", "Kill confirmed threats"),
    ("dashboard_stream", "Dashboard Stream & Drift Fix", "Dashboard-Agent", "execute", "Stream live equity, positions, PnL, ROE; detect and fix drift"),
]

AGENT_ROSTER = [
    {"name": "Trading-Director", "role": "orchestrator"},
    {"name": "Portfolio-Manager", "role": "trading"},
    {"name": "Sentiment-Agent", "role": "trading"},
    {"name": "Quant-Analyst", "role": "trading"},
    {"name": "Risk-Manager", "role": "trading"},
    {"name": "Execution-Agent", "role": "trading"},
    {"name": "Verifier-Agent", "role": "support"},
    {"name": "Ops-Monitor-Agent", "role": "support"},
    {"name": "Tactics-Researcher-Agent", "role": "support"},
    {"name": "Profit-Strategist-Agent", "role": "support"},
    {"name": "Market-Researcher-Agent", "role": "support"},
    {"name": "Pentest-Scout-Agent", "role": "pentest"},
    {"name": "Pentest-Trade-Hunter-Agent", "role": "pentest"},
    {"name": "Pentest-Integrity-Agent", "role": "pentest"},
    {"name": "Pentest-Operator-Agent", "role": "pentest"},
    {"name": "Dashboard-Agent", "role": "support"},
]

DEFAULT_NODES = [
    {"id": "Dashboard-Agent", "label": "Dashboard", "role": "data", "x": 0.88, "y": 0.06, "status": "idle"},
    {"id": "blofin-api", "label": "Blofin Live API", "role": "data", "x": 0.5, "y": 0.06, "status": "idle"},
    {"id": "verify-gate", "label": "Verify Gate", "role": "gate", "x": 0.5, "y": 0.16, "status": "idle"},
    {"id": "Trading-Director", "label": "Director", "role": "orchestrator", "x": 0.5, "y": 0.28, "status": "idle"},
    {"id": "Ops-Monitor-Agent", "label": "Ops", "role": "support", "x": 0.12, "y": 0.42, "status": "idle"},
    {"id": "Verifier-Agent", "label": "Verifier", "role": "support", "x": 0.28, "y": 0.42, "status": "idle"},
    {"id": "Tactics-Researcher-Agent", "label": "Tactics", "role": "support", "x": 0.44, "y": 0.42, "status": "idle"},
    {"id": "Profit-Strategist-Agent", "label": "Profit", "role": "support", "x": 0.56, "y": 0.42, "status": "idle"},
    {"id": "Market-Researcher-Agent", "label": "Market", "role": "support", "x": 0.72, "y": 0.42, "status": "idle"},
    {"id": "Portfolio-Manager", "label": "Portfolio", "role": "pipeline", "x": 0.08, "y": 0.62, "status": "idle"},
    {"id": "Sentiment-Agent", "label": "Sentiment", "role": "pipeline", "x": 0.24, "y": 0.62, "status": "idle"},
    {"id": "Quant-Analyst", "label": "Quant", "role": "pipeline", "x": 0.40, "y": 0.62, "status": "idle"},
    {"id": "Risk-Manager", "label": "Risk", "role": "pipeline", "x": 0.56, "y": 0.62, "status": "idle"},
    {"id": "Execution-Agent", "label": "Execution", "role": "pipeline", "x": 0.72, "y": 0.62, "status": "idle"},
    {"id": "Pentest-Scout-Agent", "label": "P-Scout", "role": "pentest", "x": 0.10, "y": 0.52, "status": "idle"},
    {"id": "Pentest-Trade-Hunter-Agent", "label": "P-Trade", "role": "pentest", "x": 0.30, "y": 0.52, "status": "idle"},
    {"id": "Pentest-Integrity-Agent", "label": "P-Integrity", "role": "pentest", "x": 0.50, "y": 0.52, "status": "idle"},
    {"id": "Pentest-Operator-Agent", "label": "P-Operator", "role": "pentest", "x": 0.70, "y": 0.52, "status": "idle"},
    {"id": "skill-library", "label": "Skill Library", "role": "compound", "x": 0.30, "y": 0.88, "status": "idle"},
    {"id": "learning-audit", "label": "Learning Audit", "role": "compound", "x": 0.50, "y": 0.88, "status": "idle"},
    {"id": "collective-care", "label": "Collective Care", "role": "compound", "x": 0.70, "y": 0.88, "status": "idle"},
]


def _mesh_fulfillment(node_map: dict[str, dict]) -> dict[str, Any]:
    fulfilled: list[str] = []
    pending: list[str] = []
    weak: list[str] = []
    skipped: list[str] = []
    for aid in sorted(MESH_AGENTS):
        st = str((node_map.get(aid) or {}).get("status") or "idle")
        if st in ("pass", "done", "skipped"):
            fulfilled.append(aid)
            if st == "skipped":
                skipped.append(aid)
        elif st in ("fail", "retry", "error"):
            weak.append(aid)
        else:
            pending.append(aid)
    total = len(MESH_AGENTS)
    return {
        "fulfilled": len(fulfilled),
        "total": total,
        "complete": len(fulfilled) == total and not weak,
        "fulfilled_agents": fulfilled,
        "pending_agents": pending,
        "weak_agents": weak,
        "skipped_agents": skipped,
    }


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _cycle() -> int:
    st = _load_json(STATE, {}) or {}
    live = _load_json(LIVE, {}) or {}
    return int(live.get("cycle") or st.get("cycle") or 0)


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def owl_running() -> bool:
    if not LOCK_FILE.is_file():
        return False
    try:
        pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
        return _pid_running(pid)
    except (TypeError, ValueError, OSError):
        return False


def _infer_cycle_from_log() -> int:
    if not LOG_FILE.is_file():
        return 0
    try:
        tail = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
    except OSError:
        return 0
    for line in reversed(tail):
        m = _CYCLE_START_RE.search(line)
        if m:
            return int(m.group(1))
    return 0


def events_from_log(limit: int = 40) -> list[dict[str, Any]]:
    """Tail owl-llm.log — always fresh even when owl-live.json lacks events."""
    if not LOG_FILE.is_file():
        return []
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-max(limit, 60) :]
    except OSError:
        return []
    level_map = {"INFO": "info", "WARN": "warn", "WARNING": "warn", "ERROR": "error", "SUCCESS": "success"}
    events: list[dict[str, Any]] = []
    base_ts = int(time.time() * 1000)
    for i, line in enumerate(lines):
        m = _LOG_LINE_RE.match(line.strip())
        if not m:
            continue
        _ts_str, level_raw, message = m.groups()
        level = level_map.get(level_raw.upper(), "info")
        events.append({"ts": base_ts - (len(lines) - i) * 1000, "message": message, "level": level})
    return events[-limit:]


def merge_events(live_events: list | None = None, limit: int = 40) -> list[dict[str, Any]]:
    log_events = events_from_log(limit)
    disk_events = list(live_events or [])
    merged: dict[str, dict[str, Any]] = {}
    for ev in disk_events + log_events:
        key = str(ev.get("message") or "")
        if key:
            merged[key] = ev
    ordered = sorted(merged.values(), key=lambda e: int(e.get("ts") or 0))
    return ordered[-limit:]


_CYCLE_COMPLETE_RE = re.compile(r"=== LLM CYCLE (\d+) COMPLETE")
_CYCLE_SLEEP_RE = re.compile(r"Sleeping (\d+)s")


def _infer_cycle_phase() -> str:
    """Best-effort phase for dashboard graph motion."""
    if not LOG_FILE.is_file():
        return "unknown"
    try:
        age = time.time() - LOG_FILE.stat().st_mtime
        tail = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
    except OSError:
        return "unknown"
    text = "\n".join(tail)
    if _CYCLE_SLEEP_RE.search(text) and age < 180:
        return "sleeping"
    if _CYCLE_COMPLETE_RE.search(text) and age < 90:
        return "between_cycles"
    if "Post-cycle audit in background" in text and age < 120:
        return "post_cycle"
    if "=== LLM CYCLE" in text and "START" in text and age < 600:
        if "Director output" in text and age > 20:
            return "post_cycle"
        if "Pre-ranked top pick" in text or "Fast margin deploy" in text:
            return "trading"
        return "cycle_start"
    if age > 120 and owl_running():
        return "stalled"
    return "idle"


def _pipeline_overlay() -> dict[str, Any]:
    pipe = _load_json(PIPELINE, {}) or {}
    live = _load_json(LIVE, {}) or {}
    graph_live = _load_json(GRAPH_LIVE, {}) or {}
    if not pipe and live.get("pipeline"):
        pipe = live["pipeline"]
    if not pipe and graph_live.get("pipeline"):
        pipe = graph_live["pipeline"]
    return pipe if isinstance(pipe, dict) else {}


def _repair_pipeline_veto_disk() -> None:
    """Clear next_agent after Risk veto — keeps dashboard graph from showing Execution stuck."""
    pipe = _load_json(PIPELINE, {}) or {}
    if not pipe:
        return
    completed = set(pipe.get("completed") or [])
    if not pipe.get("terminal"):
        if (
            pipe.get("next_agent") == "Execution-Agent"
            and "Risk-Manager" in completed
            and not pipe.get("risk_approved")
        ):
            pipe["terminal"] = True
            pipe["next_agent"] = ""
            PIPELINE.write_text(json.dumps(pipe, indent=2), encoding="utf-8")
        return
    if "Risk-Manager" in completed and not pipe.get("risk_approved") and pipe.get("next_agent"):
        pipe["next_agent"] = ""
        PIPELINE.write_text(json.dumps(pipe, indent=2), encoding="utf-8")


def _apply_live_graph(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    _repair_pipeline_veto_disk()
    state_cycle = _cycle()
    log_cycle = _infer_cycle_from_log()
    live_cycle = max(state_cycle, log_cycle)
    graph_live = _load_json(GRAPH_LIVE, {}) or {}
    pipe = _pipeline_overlay()
    running = owl_running()
    phase = _infer_cycle_phase()

    data["cycle"] = max(int(data.get("cycle") or 0), live_cycle)
    cycle_in_progress = running and log_cycle > state_cycle and phase in (
        "cycle_start",
        "trading",
        "post_cycle",
    )
    data["cycle_in_progress"] = cycle_in_progress
    data["cycle_phase"] = phase

    completed = set(pipe.get("completed") or graph_live.get("completed") or [])
    risk_veto = bool(pipe.get("terminal")) and "Risk-Manager" in completed and not pipe.get(
        "risk_approved", True
    )
    pipeline_terminal = bool(pipe.get("terminal")) and (
        "Execution-Agent" in completed or risk_veto
    )
    pipeline_next = ""
    if not pipeline_terminal:
        pipeline_next = str(
            pipe.get("next_agent")
            or graph_live.get("pipeline_next")
            or data.get("pipeline_next")
            or "Portfolio-Manager"
        )
        if pipeline_next in completed:
            for agent in PIPELINE_AGENTS:
                if agent not in completed:
                    pipeline_next = agent
                    break
            else:
                pipeline_next = ""
    elif risk_veto:
        pipeline_next = ""
    data["pipeline_next"] = pipeline_next or ("done" if pipeline_terminal else "Portfolio-Manager")
    data["pipeline_veto"] = risk_veto

    active_agent = str(graph_live.get("active_agent") or data.get("active_agent") or "")
    if pipeline_terminal:
        if active_agent in PIPELINE_AGENTS or risk_veto:
            active_agent = ""
    if pipeline_terminal and phase in ("between_cycles", "sleeping", "post_cycle", "stalled"):
        active_agent = ""
    elif not active_agent and running and cycle_in_progress and not pipeline_terminal:
        active_agent = "Trading-Director"
    data["active_agent"] = active_agent

    if running and graph_live.get("verify_status"):
        data["verify_status"] = graph_live.get("verify_status")
    elif running and not data.get("verify_status"):
        data["verify_status"] = "idle"

    completed = set(pipe.get("completed") or graph_live.get("completed") or [])
    node_map = {n.get("id"): n for n in data.get("nodes") or [] if n.get("id")}
    next_idx = PIPELINE_AGENTS.index(pipeline_next) if pipeline_next in PIPELINE_AGENTS else 0
    for i, agent in enumerate(PIPELINE_AGENTS):
        node = node_map.get(agent)
        if not node:
            continue
        if risk_veto and agent == "Execution-Agent":
            node["status"] = "skipped"
            node["detail"] = "skipped (risk veto)"
        elif risk_veto and agent == "Risk-Manager":
            node["status"] = "fail"
            node["detail"] = node.get("detail") or "veto"
        elif agent in completed or (
            pipeline_terminal and agent == "Execution-Agent" and "Execution-Agent" in completed
        ):
            node["status"] = "pass"
        elif pipeline_terminal and agent not in completed:
            node["status"] = "idle"
        elif pipeline_next and agent == pipeline_next and running and not pipeline_terminal:
            node["status"] = "active"
        elif running and not pipeline_terminal and i > next_idx:
            # Future agents stay idle — never show Risk/Exec stuck ahead of pipeline
            node["status"] = "idle"
        elif node.get("status") == "active" and agent not in completed and agent != pipeline_next:
            node["status"] = "idle"
    director = node_map.get("Trading-Director")
    if director and running and cycle_in_progress and not pipeline_terminal:
        director["status"] = "active"
        director["detail"] = f"Cycle {log_cycle} orchestration"
    elif director and active_agent == "Trading-Director":
        director["status"] = "active"
    elif director and pipeline_terminal:
        director["status"] = "pass"
        director["detail"] = "pipeline done" if risk_veto else director.get("detail", "")
    api = node_map.get("blofin-api")
    if api and running and phase not in ("sleeping", "between_cycles"):
        api["status"] = "active"

    edges = list(data.get("edges") or [])
    now = time.time()
    for e in edges:
        pa = e.get("pulse_age")
        pulsing = False
        if pa is not None:
            try:
                pulsing = float(pa) < 2.5
            except (TypeError, ValueError):
                pulsing = False
        e.pop("strokeStyle", None)
        e.pop("lineWidth", None)
        e["pulsing"] = pulsing

    if running and pipeline_next in PIPELINE_AGENTS and not pipeline_terminal:
        idx = PIPELINE_AGENTS.index(pipeline_next)
        if idx > 0:
            prev_agent = PIPELINE_AGENTS[idx - 1]
            edge_id = f"handoff-{prev_agent}-{pipeline_next}"
            for e in edges:
                if e.get("id") == edge_id:
                    e["pulsing"] = True
                    e["pulse_age"] = 0
        if active_agent == "Trading-Director":
            for e in edges:
                if e.get("type") == "spawn" and e.get("from") == "Trading-Director":
                    e["pulsing"] = True
                    e["pulse_age"] = 0

    if running and phase in ("post_cycle", "between_cycles", "stalled", "sleeping"):
        tick = int(now) % 3
        compound_nodes = ("skill-library", "learning-audit", "collective-care")
        pulse_target = compound_nodes[tick]
        for e in edges:
            if e.get("type") == "compound" and e.get("to") == pulse_target:
                e["pulsing"] = True
                e["pulse_age"] = 0
        for nid in compound_nodes:
            node = node_map.get(nid)
            if node:
                node["status"] = "active" if nid == pulse_target else "pass"

    if pipeline_terminal and risk_veto:
        for e in edges:
            eid = str(e.get("id") or "")
            if eid == "handoff-Risk-Manager-Execution-Agent":
                e["pulsing"] = False
            elif eid == "reject-gate-Risk-Manager":
                e["pulsing"] = True
                e["pulse_age"] = 0

    mesh = _mesh_fulfillment(node_map)
    clique_weak = mesh.get("weak_agents") or []
    verify_st = str(data.get("verify_status") or graph_live.get("verify_status") or "idle")
    data["mesh_fulfillment"] = mesh
    data["mesh_edges"] = len(MESH_AGENTS) * (len(MESH_AGENTS) - 1)
    data["polymorphic"] = True
    data["clique_rugged"] = len(clique_weak) == 0 and verify_st in ("pass", "idle", "checking")
    data["clique_weak_links"] = clique_weak
    data["nodes"] = list(node_map.values())
    data["edges"] = edges
    data["updated_at"] = now
    return data


def _apply_live_tasks(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    tasks = [dict(t) for t in (data.get("all_tasks") or [])]
    log_cycle = _infer_cycle_from_log()
    board_cycle = int(data.get("cycle") or 0)
    running = owl_running()
    live_cycle = max(board_cycle, log_cycle, _cycle())

    if running and log_cycle and log_cycle >= live_cycle:
        if board_cycle < log_cycle:
            for t in tasks:
                t["cycle"] = log_cycle
                if t.get("status") in ("active", "done", "pass", "fail", "retry"):
                    t["status"] = "pending"
                    t["started_at"] = None
                    t["ended_at"] = None
            data["cycle"] = log_cycle
            for t in tasks:
                if t.get("id") == "oversight:Trading-Director:oversee":
                    t["status"] = "active"
                    t["started_at"] = t.get("started_at") or time.time()
                    t["detail"] = f"Cycle {log_cycle} in progress"
                if t.get("id") == "trading_pipeline:Trading-Director:execute":
                    t["status"] = "active"
                    t["started_at"] = t.get("started_at") or time.time()

        pipe = _pipeline_overlay()
        completed = set(pipe.get("completed") or [])
        risk_veto = bool(pipe.get("terminal")) and "Risk-Manager" in completed and not pipe.get(
            "risk_approved", True
        )
        pipeline_terminal = bool(pipe.get("terminal")) and (
            "Execution-Agent" in completed or risk_veto
        )
        next_agent = ""
        if not pipeline_terminal:
            next_agent = str(pipe.get("next_agent") or "")
        job_for_agent = {
            "Portfolio-Manager": "portfolio",
            "Sentiment-Agent": "sentiment",
            "Quant-Analyst": "quant",
            "Risk-Manager": "risk",
            "Execution-Agent": "execution",
        }
        for agent, job in job_for_agent.items():
            tid = f"{job}:{agent}:execute"
            for t in tasks:
                if t.get("id") == tid:
                    if risk_veto and agent == "Execution-Agent":
                        t["status"] = "skipped"
                        t["detail"] = "risk veto"
                        t["ended_at"] = t.get("ended_at") or time.time()
                    elif risk_veto and agent == "Risk-Manager" and agent in completed:
                        t["status"] = "fail"
                        t["detail"] = "veto"
                        t["ended_at"] = t.get("ended_at") or time.time()
                    elif agent in completed:
                        t["status"] = "done"
                        t["ended_at"] = t.get("ended_at") or time.time()
                    elif agent == next_agent and next_agent:
                        t["status"] = "active"
                        t["started_at"] = t.get("started_at") or time.time()

    data["all_tasks"] = tasks
    data = build_task_summary(tasks, int(data.get("cycle") or live_cycle or 1))
    return data


def seed_task_board(cycle: int | None = None) -> dict[str, Any]:
    cycle = cycle or _cycle() or 1
    ts = time.time()
    tasks = []
    for job, label, agent, mode, detail in TASK_SEEDS:
        tasks.append(
            {
                "id": f"{job}:{agent}:{mode}",
                "cycle": cycle,
                "job": job,
                "job_label": label,
                "agent": agent,
                "mode": mode,
                "status": "pending",
                "detail": detail,
                "started_at": None,
                "ended_at": None,
                "updated_at": ts,
            }
        )
    board = build_task_summary(tasks, cycle)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    TASK_BOARD.write_text(json.dumps(board, indent=2, default=str), encoding="utf-8")
    return board


def build_task_summary(tasks: list[dict[str, Any]], cycle: int) -> dict[str, Any]:
    active = [t for t in tasks if t.get("status") == "active"]
    pending = [t for t in tasks if t.get("status") == "pending"]
    done = [t for t in tasks if t.get("status") in ("done", "pass")]
    failed = [t for t in tasks if t.get("status") in ("fail", "retry")]
    skipped = [t for t in tasks if t.get("status") == "skipped"]
    equity = []
    if EQUITY.is_file():
        for line in EQUITY.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]:
            try:
                row = json.loads(line)
                if float(row.get("equity") or 0) > 0:
                    equity.append(row)
            except json.JSONDecodeError:
                continue
    return {
        "cycle": cycle,
        "summary": {
            "total": len(tasks),
            "active": len(active),
            "pending": len(pending),
            "done": len(done),
            "failed": len(failed),
            "skipped": len(skipped),
        },
        "current": active,
        "all_tasks": tasks,
        "equity_curve": equity,
        "updated_at": time.time(),
    }


def get_task_board() -> dict[str, Any]:
    data = _load_json(TASK_BOARD)
    if not data or not data.get("all_tasks"):
        data = seed_task_board(_cycle() or 1)
    return _apply_live_tasks(data)


def _default_edges() -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for agent in (
        "Ops-Monitor-Agent",
        "Verifier-Agent",
        "Tactics-Researcher-Agent",
        "Profit-Strategist-Agent",
        "Market-Researcher-Agent",
        "Portfolio-Manager",
        "Dashboard-Agent",
    ):
        edges.append({"id": f"spawn-director-{agent}", "from": "Trading-Director", "to": agent, "type": "spawn"})
    pipeline = ["Portfolio-Manager", "Sentiment-Agent", "Quant-Analyst", "Risk-Manager", "Execution-Agent"]
    for i in range(len(pipeline) - 1):
        a, b = pipeline[i], pipeline[i + 1]
        edges.append({"id": f"handoff-{a}-{b}", "from": a, "to": b, "type": "handoff"})
    for agent in (
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
        "Dashboard-Agent",
    ):
        edges.append({"id": f"verify-{agent}-gate", "from": agent, "to": "verify-gate", "type": "verify"})
        edges.append({"id": f"reject-gate-{agent}", "from": "verify-gate", "to": agent, "type": "reject"})
    edges.extend(
        [
            {"id": "data-api-gate", "from": "blofin-api", "to": "verify-gate", "type": "data"},
            {"id": "data-api-director", "from": "blofin-api", "to": "Trading-Director", "type": "data"},
            {"id": "data-api-dashboard", "from": "blofin-api", "to": "Dashboard-Agent", "type": "data"},
            {"id": "compound-gate-skills", "from": "verify-gate", "to": "skill-library", "type": "compound"},
            {"id": "compound-skills-audit", "from": "skill-library", "to": "learning-audit", "type": "compound"},
            {"id": "compound-audit-care", "from": "learning-audit", "to": "collective-care", "type": "compound"},
            {"id": "repair-ops-api", "from": "Ops-Monitor-Agent", "to": "blofin-api", "type": "repair"},
            {"id": "repair-dashboard-api", "from": "Dashboard-Agent", "to": "blofin-api", "type": "repair"},
        ]
    )
    return edges


def seed_swarm_graph(cycle: int | None = None) -> dict[str, Any]:
    cycle = cycle or _cycle() or 0
    graph = {
        "cycle": cycle,
        "active_agent": "",
        "verify_status": "idle",
        "convergence_streak": 0,
        "verify_fail_this_cycle": 0,
        "verify_fail_history": [],
        "pipeline_next": "Portfolio-Manager",
        "nodes": [dict(n) for n in DEFAULT_NODES],
        "edges": _default_edges(),
        "updated_at": time.time(),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    GRAPH.write_text(json.dumps(graph, default=str), encoding="utf-8")
    return graph


def get_swarm_graph() -> dict[str, Any]:
    data = _load_json(GRAPH)
    if not data or not data.get("nodes"):
        data = seed_swarm_graph(_cycle())
    return _apply_live_graph(data)


def get_learning_report() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if LEARNING.is_file():
        for line in LEARNING.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    by_kind: dict[str, dict] = {}
    for row in reversed(rows):
        kind = str(row.get("kind") or "")
        if kind == "learned" and "last_learned" not in by_kind:
            by_kind["last_learned"] = row
        elif kind == "improvement" and "last_improvement" not in by_kind:
            by_kind["last_improvement"] = row
        elif kind == "self_fix" and "last_self_fix" not in by_kind:
            by_kind["last_self_fix"] = row
    return by_kind


def ensure_cache_files() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if not TASK_BOARD.is_file():
        seed_task_board(_cycle() or 1)
    if not GRAPH.is_file():
        seed_swarm_graph(_cycle())
