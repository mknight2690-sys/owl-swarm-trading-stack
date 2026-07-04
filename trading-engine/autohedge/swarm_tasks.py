"""
Live task board — every job the swarm can run, what's active now, what's done.

Each agent can execute / audit / fix / optimize / oversee any job (universal swarm).
The dashboard shows ALL tasks + CURRENT work in real time.
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


OUTPUT_DIR = _output_dir()  # legacy; prefer _output_dir() at runtime
EQUITY_PATH = _output_dir() / "equity_curve.jsonl"
TASK_BOARD_PATH = _output_dir() / "task_board.json"

# All job domains in the unstoppable pipeline
SWARM_JOBS: list[dict[str, str]] = [
    {"id": "oversight", "label": "Oversight & Planning", "layer": "meta"},
    {"id": "ops_health", "label": "Ops / Stack Health", "layer": "support"},
    {"id": "tpsl_protection", "label": "TP/SL Protection Guard", "layer": "support"},
    {"id": "infrastructure_repair", "label": "Self-Heal Repairs", "layer": "support"},
    {"id": "verification", "label": "Verify Gate", "layer": "gate"},
    {"id": "market_research", "label": "Market Research", "layer": "support"},
    {"id": "tactics_research", "label": "Internet Tactics", "layer": "support"},
    {"id": "profit_optimization", "label": "Profit Optimization", "layer": "support"},
    {"id": "trading_pipeline", "label": "Trading Pipeline", "layer": "pipeline"},
    {"id": "portfolio", "label": "Portfolio Analysis", "layer": "pipeline"},
    {"id": "sentiment", "label": "Sentiment", "layer": "pipeline"},
    {"id": "quant", "label": "Quant Analysis", "layer": "pipeline"},
    {"id": "risk", "label": "Risk Approval", "layer": "pipeline"},
    {"id": "execution", "label": "Trade Execution", "layer": "pipeline"},
    {"id": "peer_audit", "label": "Collective Peer Audit", "layer": "gate"},
    {"id": "learning_compound", "label": "Compound Learning", "layer": "compound"},
    {"id": "pentest_recon", "label": "Pentest Recon", "layer": "pentest"},
    {"id": "pentest_trade_hunt", "label": "Trade Pipeline Hunt", "layer": "pentest"},
    {"id": "pentest_integrity", "label": "Verifier/Mesh Integrity", "layer": "pentest"},
    {"id": "pentest_remediate", "label": "Pentest Kill/Fix", "layer": "pentest"},
]

JOB_MODES = ["execute", "audit", "fix", "optimize", "oversee"]

_lock = threading.RLock()
_cycle = 0
_tasks: list[dict[str, Any]] = []
_equity_history: list[dict[str, Any]] = []


def _persist_board() -> None:
    """Disk mirror so standalone dashboard server can read tasks."""
    try:
        out = _output_dir()
        out.mkdir(parents=True, exist_ok=True)
        (out / "task_board.json").write_text(task_board_json(), encoding="utf-8")
    except OSError:
        pass


def _load_board_from_disk() -> bool:
    global _cycle, _tasks, _equity_history
    board_path = _output_dir() / "task_board.json"
    if not board_path.is_file():
        return False
    try:
        data = json.loads(board_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    with _lock:
        if _tasks:
            return True
        _cycle = int(data.get("cycle") or 0)
        _tasks = list(data.get("all_tasks") or [])
        _equity_history = list(data.get("equity_curve") or [])
    return bool(_tasks)


def _task_id(job: str, agent: str, mode: str) -> str:
    return f"{job}:{agent}:{mode}"


def init_cycle_tasks(cycle: int) -> None:
    """Seed the full task board for a new cycle — all jobs visible, most pending."""
    global _cycle, _tasks
    with _lock:
        _cycle = cycle
        _tasks = []
        ts = time.time()
        seeds = [
            ("oversight", "Trading-Director", "oversee", "Assess full operation, plan cycle"),
            ("ops_health", "Ops-Monitor-Agent", "audit", "Stack health check"),
            ("tpsl_protection", "Ops-Monitor-Agent", "audit", "Verify every position has TP+SL"),
            ("infrastructure_repair", "Ops-Monitor-Agent", "fix", "Preflight self-heal"),
            ("verification", "Verifier-Agent", "audit", "Cross-check all agent outputs"),
            ("market_research", "Market-Researcher-Agent", "execute", "Deep-dive top candidate"),
            ("tactics_research", "Tactics-Researcher-Agent", "execute", "Internet + journal tactics"),
            ("profit_optimization", "Profit-Strategist-Agent", "optimize", "Tune asymmetric R:R params"),
            ("trading_pipeline", "Trading-Director", "execute", "Orchestrate handoff chain"),
            ("portfolio", "Portfolio-Manager", "execute", "Margin & position gate"),
            ("sentiment", "Sentiment-Agent", "execute", "Funding + news bias"),
            ("quant", "Quant-Analyst", "execute", "Technical probability"),
            ("risk", "Risk-Manager", "execute", "TP/SL + R:R approval"),
            ("execution", "Execution-Agent", "execute", "Place trade + verify protection"),
            ("peer_audit", "Verifier-Agent", "audit", "Collective care peer sniff"),
            ("learning_compound", "Tactics-Researcher-Agent", "optimize", "Write playbook + audit trail"),
            ("pentest_recon", "Pentest-Scout-Agent", "audit", "Sniff entire swarm — recon only"),
            ("pentest_trade_hunt", "Pentest-Trade-Hunter-Agent", "audit", "Mission 1: why no trades"),
            ("pentest_integrity", "Pentest-Integrity-Agent", "audit", "Mission 2: verifier + mesh"),
            ("pentest_remediate", "Pentest-Operator-Agent", "fix", "Kill/fix confirmed threats"),
        ]
        for job, agent, mode, detail in seeds:
            _tasks.append(
                {
                    "id": _task_id(job, agent, mode),
                    "cycle": cycle,
                    "job": job,
                    "job_label": next((j["label"] for j in SWARM_JOBS if j["id"] == job), job),
                    "layer": next((j["layer"] for j in SWARM_JOBS if j["id"] == job), "other"),
                    "agent": agent,
                    "mode": mode,
                    "status": "pending",
                    "detail": detail,
                    "started_at": None,
                    "ended_at": None,
                    "updated_at": ts,
                }
            )
        _persist_board()


def start_task(
    job: str,
    agent: str,
    mode: str = "execute",
    *,
    detail: str = "",
) -> None:
    with _lock:
        tid = _task_id(job, agent, mode)
        found = False
        for t in _tasks:
            if t["id"] == tid or (t["job"] == job and t["agent"] == agent and t["mode"] == mode):
                t["status"] = "active"
                t["started_at"] = t["started_at"] or time.time()
                t["updated_at"] = time.time()
                if detail:
                    t["detail"] = detail
                found = True
                break
        if not found:
            _tasks.append(
                {
                    "id": tid,
                    "cycle": _cycle,
                    "job": job,
                    "job_label": job,
                    "layer": "other",
                    "agent": agent,
                    "mode": mode,
                    "status": "active",
                    "detail": detail,
                    "started_at": time.time(),
                    "ended_at": None,
                    "updated_at": time.time(),
                }
            )
        _persist_board()


def finish_task(
    job: str,
    agent: str,
    mode: str = "execute",
    *,
    status: str = "done",
    detail: str = "",
) -> None:
    with _lock:
        for t in _tasks:
            if t["job"] == job and t["agent"] == agent and t["mode"] == mode:
                t["status"] = status
                t["ended_at"] = time.time()
                t["updated_at"] = time.time()
                if detail:
                    t["detail"] = detail
                _persist_board()
                return
        _persist_board()


def skip_task(job: str, reason: str = "skipped") -> None:
    with _lock:
        for t in _tasks:
            if t["job"] == job and t["status"] == "pending":
                t["status"] = "skipped"
                t["detail"] = reason
                t["updated_at"] = time.time()
        _persist_board()


def record_equity(cycle: int, equity: float, available: float) -> None:
    if equity <= 0 and available <= 0:
        return
    point = {"ts": time.time(), "cycle": cycle, "equity": round(equity, 6), "available": round(available, 6)}
    with _lock:
        _equity_history.append(point)
        if len(_equity_history) > 500:
            _equity_history[:] = _equity_history[-500:]
    try:
        out = _output_dir()
        out.mkdir(parents=True, exist_ok=True)
        with (out / "equity_curve.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(point) + "\n")
    except OSError:
        pass


def _load_equity_history() -> list[dict[str, Any]]:
    if _equity_history:
        return list(_equity_history)
    if not EQUITY_PATH.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in EQUITY_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return rows


def _owl_state() -> dict[str, Any]:
    path = _output_dir() / "owl-state.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def is_cycle_in_progress() -> bool:
    """True while owl cycle is likely still running (not idle between cycles)."""
    state = _owl_state()
    last = float(state.get("last_cycle_at") or 0)
    if last <= 0:
        return False
    max_sec = float(os.environ.get("OWL_CYCLE_MAX_SEC", "240"))
    return (time.time() - last) < max_sec


def ensure_task_board_seeded(cycle: int | None = None) -> bool:
    """Re-seed sparse/stale task board — swarm self-heal when overseer finds <15 jobs."""
    board = get_task_board()
    total = int((board.get("summary") or {}).get("total") or 0)
    if total >= 15:
        return False
    if cycle is None:
        cycle = int(board.get("cycle") or 0)
    if cycle <= 0:
        cycle = int(_owl_state().get("cycle") or 0)
    if cycle <= 0:
        cycle = 1
    init_cycle_tasks(cycle)
    return True


def get_task_board() -> dict[str, Any]:
    _load_board_from_disk()
    with _lock:
        tasks = [dict(t) for t in _tasks]
        active = [t for t in tasks if t["status"] == "active"]
        pending = [t for t in tasks if t["status"] == "pending"]
        done = [t for t in tasks if t["status"] in ("done", "pass")]
        failed = [t for t in tasks if t["status"] in ("fail", "retry")]
        skipped = [t for t in tasks if t["status"] == "skipped"]

    equity = _load_equity_history()
    return {
        "cycle": _cycle,
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
        "jobs": SWARM_JOBS,
        "modes": JOB_MODES,
        "equity_curve": equity[-120:],
        "updated_at": time.time(),
    }


def task_board_json() -> str:
    return json.dumps(get_task_board(), default=str, indent=2)
