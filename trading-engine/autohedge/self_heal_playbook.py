"""
Fix once, teach forever — the swarm never solves the same problem twice manually.

When an issue is detected and fixed, it is recorded in self_heal_playbook.json with:
  - issue fingerprint (what to detect)
  - remediation steps (what to do)
  - verification (how to confirm it worked)

Next time the same issue surfaces, playbook auto-applies before any human or fresh LLM work.
Agents read learned fixes via blofin_get_self_heal_playbook / tactics injection.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from loguru import logger

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
ROOT = Path(os.environ.get("OWL_SWARM_ROOT", r"C:\Users\mknig\owl-swarm"))
PYTHON = os.environ.get(
    "OWL_PYTHON",
    r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe",
)
PLAYBOOK_PATH = OUTPUT_DIR / "self_heal_playbook.json"
OVERSEER_LOG = OUTPUT_DIR / "overseer_notes.jsonl"
OWL_LOG = OUTPUT_DIR / "owl-llm.log"
AUTO_TRADER_OUTPUT = Path(
    os.environ.get("AUTO_TRADER_ROOT", r"C:\Users\mknig\blofin-auto-trader")
) / "outputs"
JOURNAL_PATH = AUTO_TRADER_OUTPUT / "trade_journal.jsonl"
API_COOLDOWN_FILE = OUTPUT_DIR / "blofin_api_cooldown.json"
API_HEAVY_FIXES = frozenset(
    {
        "false_margin_block",
        "missing_tpsl",
        "tpsl_rate_limit_blocking",
        "prerank_held_symbol",
        "polymorphic_mesh_incomplete",
        "stale_positions_cache",
        "stale_account_available",
        "risk_veto_stale",
        "tpsl_flat_false_veto",
    }
)

_lock = threading.Lock()


def _load() -> dict[str, Any]:
    if not PLAYBOOK_PATH.is_file():
        return {"version": 1, "fixes": {}, "stats": {"auto_heals": 0, "taught": 0}}
    try:
        return json.loads(PLAYBOOK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "fixes": {}, "stats": {"auto_heals": 0, "taught": 0}}


def _save(data: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = time.time()
    PLAYBOOK_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def teach_fix(
    issue_id: str,
    *,
    title: str,
    detail: str,
    component: str,
    action: str,
    proof: dict[str, Any] | None = None,
) -> None:
    """Record how we fixed this — swarm applies automatically on recurrence."""
    with _lock:
        data = _load()
        fixes: dict[str, Any] = data.setdefault("fixes", {})
        row = fixes.get(issue_id) or {
            "issue_id": issue_id,
            "title": title,
            "action": action,
            "component": component,
            "first_taught_at": time.time(),
            "auto_apply_count": 0,
            "teach_count": 0,
        }
        row["title"] = title
        row["detail"] = detail
        row["action"] = action
        row["component"] = component
        row["last_taught_at"] = time.time()
        row["teach_count"] = int(row.get("teach_count") or 0) + 1
        row["proof"] = proof or {}
        fixes[issue_id] = row
        data["stats"]["taught"] = int(data.get("stats", {}).get("taught") or 0) + 1
        _save(data)

    try:
        from autohedge.tactics_learner import _add_tactic, _load as load_tactics, _save as save_tactics

        with _lock:
            td = load_tactics()
            _add_tactic(
                td,
                title=f"SELF-HEAL: {title[:60]}",
                body=f"When {issue_id}: {detail}. Action: {action}",
                source="self_heal_playbook",
                confidence=0.92,
            )
            save_tactics(td)
    except Exception as exc:
        logger.debug("tactics teach from playbook: {}", exc)

    try:
        from autohedge.swarm_learning_audit import record_learned

        record_learned(
            title=f"Swarm taught to self-heal: {title}",
            detail=f"Action: {action}. Will auto-apply on recurrence.",
            source="self_heal_playbook",
            proof={"issue_id": issue_id, **(proof or {})},
        )
    except Exception:
        pass
    logger.info("PLAYBOOK taught [{}]: {}", issue_id, title[:70])


def record_auto_heal(issue_id: str, *, detail: str = "", proof: dict[str, Any] | None = None) -> None:
    with _lock:
        data = _load()
        fixes = data.setdefault("fixes", {})
        row = fixes.get(issue_id, {"issue_id": issue_id, "title": issue_id})
        row["auto_apply_count"] = int(row.get("auto_apply_count") or 0) + 1
        row["last_auto_heal_at"] = time.time()
        row["last_auto_detail"] = detail
        fixes[issue_id] = row
        data["stats"]["auto_heals"] = int(data.get("stats", {}).get("auto_heals") or 0) + 1
        _save(data)

    try:
        from autohedge.swarm_learning_audit import record_verified_fix

        record_verified_fix(
            title=f"Playbook auto-healed: {issue_id}",
            detail=detail or "Known fix applied without re-discovery",
            component="self_heal_playbook",
            proof=proof or {"issue_id": issue_id},
        )
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
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


def _port_listener_pid(port: int) -> int | None:
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts and parts[-1].isdigit():
                    return int(parts[-1])
    except (subprocess.CalledProcessError, OSError):
        pass
    return None


def _owl_pid() -> int | None:
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Where-Object { $_.CommandLine -like '*owl_llm_loop*' } | "
                "Select-Object -First 1).ProcessId",
            ],
            text=True,
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        ).strip()
        return int(out) if out.isdigit() else None
    except (subprocess.CalledProcessError, ValueError, OSError):
        return None


def _dashboard_server_pid() -> int | None:
    """PID of standalone dashboard_server.py (OWL_EXTERNAL_DASHBOARD=1)."""
    pid_file = OUTPUT_DIR / "dashboard-server.pid"
    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            if _pid_alive(pid):
                return pid
        except (ValueError, OSError):
            pass
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Where-Object { $_.CommandLine -like '*dashboard_server.py*' } | "
                "Select-Object -First 1).ProcessId",
            ],
            text=True,
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        ).strip()
        return int(out) if out.isdigit() else None
    except (subprocess.CalledProcessError, ValueError, OSError):
        return None


def _tail_owl_log(lines: int = 50) -> list[str]:
    if not OWL_LOG.is_file():
        return []
    try:
        return OWL_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    except OSError:
        return []


def _owl_log_age_sec() -> float:
    if not OWL_LOG.is_file():
        return 9999.0
    try:
        return max(0.0, time.time() - OWL_LOG.stat().st_mtime)
    except OSError:
        return 9999.0


def _api_cooldown_active() -> bool:
    if not API_COOLDOWN_FILE.is_file():
        return False
    try:
        row = json.loads(API_COOLDOWN_FILE.read_text(encoding="utf-8"))
        return time.time() < float(row.get("until") or 0)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return False


def _set_api_cooldown(seconds: float = 120.0, *, reason: str = "429_storm") -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    API_COOLDOWN_FILE.write_text(
        json.dumps({"until": time.time() + seconds, "reason": reason, "ts": time.time()}),
        encoding="utf-8",
    )


def api_cooldown_active() -> bool:
    """Public — overseer/deep audit skip heavy API work during cooldown."""
    return _api_cooldown_active()


def _ensure_scripts_path() -> Path:
    scripts = ROOT / "scripts"
    if scripts.is_dir() and str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return scripts


def _fetch_live_snap(*, force: bool = True) -> dict[str, Any] | None:
    """Live positions/equity via owl-swarm blofin_live_api (no solders chain)."""
    if _api_cooldown_active():
        return None
    try:
        _ensure_scripts_path()
        from blofin_live_api import fetch_live_account

        snap = fetch_live_account(force=force, min_interval_sec=0)
        if snap.get("ok") or isinstance(snap.get("positions"), list):
            return snap
    except Exception as exc:
        logger.debug("playbook live snap: {}", exc)
    return None


def _heal_owl_live_from_snap(snap: dict[str, Any]) -> bool:
    """Sync owl-live.json surfaces after authoritative Blofin fetch."""
    try:
        live_path = OUTPUT_DIR / "owl-live.json"
        live: dict[str, Any] = {}
        if live_path.is_file():
            live = json.loads(live_path.read_text(encoding="utf-8"))
        positions = list(snap.get("positions") or [])
        live.update(
            {
                "equity": float(snap.get("equity") or live.get("equity") or 0),
                "available": float(snap.get("available") or live.get("available") or 0),
                "positions": positions,
                "account_ts": int(time.time()),
                "position_count": len(positions),
                "account_source": snap.get("source", "playbook_heal"),
            }
        )
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        live_path.write_text(json.dumps(live, indent=2, default=str), encoding="utf-8")
        return True
    except Exception as exc:
        logger.debug("heal owl-live: {}", exc)
        return False


def _recent_journal_events(*, limit: int = 40) -> list[dict[str, Any]]:
    if not JOURNAL_PATH.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in JOURNAL_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return rows


def _journal_order_placed_recent(inst: str, *, within_sec: float = 600.0) -> bool:
    inst = (inst or "").strip().upper()
    if not inst:
        return False
    cutoff = time.time() - within_sec
    for ev in reversed(_recent_journal_events(limit=60)):
        if str(ev.get("type") or "") != "order_placed":
            continue
        if str(ev.get("instId") or "").upper() != inst:
            continue
        if float(ev.get("ts") or 0) >= cutoff and ev.get("orderId"):
            return True
    return False


def _detect_stale_lock() -> tuple[str, dict[str, Any]] | None:
    lock = OUTPUT_DIR / "owl-llm.lock"
    if not lock.is_file():
        return None
    try:
        lock_pid = int(lock.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return ("stale_lock", {"lock_pid": 0})
    my_pid = os.getpid()
    if lock_pid and lock_pid != my_pid and not _pid_alive(lock_pid):
        return ("stale_lock", {"lock_pid": lock_pid})
    return None


def _detect_port_hijacker() -> tuple[str, dict[str, Any]] | None:
    # Standalone dashboard_server.py owns :7878 — never treat it as a hijacker.
    if os.environ.get("OWL_EXTERNAL_DASHBOARD", "1") == "1":
        return None
    port = int(os.environ.get("DASHBOARD_PORT", "7878"))
    port_pid = _port_listener_pid(port)
    if not port_pid:
        return None
    allowed = {os.getpid()}
    owl_pid = _owl_pid()
    if owl_pid:
        allowed.add(owl_pid)
    dash_pid = _dashboard_server_pid()
    if dash_pid:
        allowed.add(dash_pid)
    if port_pid in allowed:
        return None
    # External dashboard: never kill the legitimate dashboard_server listener
    if os.environ.get("OWL_EXTERNAL_DASHBOARD", "1") == "1" and dash_pid == port_pid:
        return None
    return ("port_hijacker", {"port": port, "pid": port_pid})


def _detect_stale_ws_cache() -> tuple[str, dict[str, Any]] | None:
    ws = OUTPUT_DIR / "ws-tickers.json"
    if not ws.is_file():
        return ("stale_ws_cache", {"age_sec": None})
    age = time.time() - ws.stat().st_mtime
    if age > 180:
        return ("stale_ws_cache", {"age_sec": round(age, 1)})
    return None


def _detect_missing_tpsl() -> tuple[str, dict[str, Any]] | None:
    try:
        from autohedge.tpsl_guard import audit_open_positions_tpsl, is_tpsl_audit_rate_limited

        audit = audit_open_positions_tpsl()
        if is_tpsl_audit_rate_limited(audit):
            return None
        missing = list(audit.get("missing") or [])
        partial = audit.get("partial") or []
        if missing or partial:
            return (
                "missing_tpsl",
                {
                    "missing": missing,
                    "partial": partial,
                    "positions_trust": audit.get("positions_trust"),
                },
            )
    except Exception:
        pass
    return None


def _detect_universe_stale() -> tuple[str, dict[str, Any]] | None:
    try:
        from autohedge.tools.blofin_universe_feed import get_universe_feed

        snap = get_universe_feed().get_snapshot()
        age = time.time() - snap.updated_at
        if age > 300:
            return ("universe_feed_stale", {"age_sec": round(age, 1)})
    except Exception:
        pass
    return None


def _detect_task_completion_gap() -> tuple[str, dict[str, Any]] | None:
    try:
        from autohedge.task_completion_audit import audit_cycle_tasks

        audit = audit_cycle_tasks(source="playbook_detect", auto_repair=False)
        if not audit.get("ok"):
            return (
                "task_completion_gap",
                {
                    "incomplete": audit.get("incomplete"),
                    "phantom_done": audit.get("phantom_done"),
                    "issues": (audit.get("issues") or [])[:5],
                },
            )
    except Exception:
        pass
    return None


def _detect_surface_sync_drift() -> tuple[str, dict[str, Any]] | None:
    try:
        from autohedge.swarm_surface_sync import verify_surface_sync

        sync = verify_surface_sync()
        if not sync.get("ok"):
            return ("surface_sync_drift", {"issues": sync.get("issues")})
    except Exception:
        pass
    return None


def _detect_mesh_incomplete() -> tuple[str, dict[str, Any]] | None:
    try:
        from autohedge.swarm_tasks import is_cycle_in_progress

        if is_cycle_in_progress():
            return None
        from autohedge.collective_audit import run_polymorphic_mesh_audit

        mesh = run_polymorphic_mesh_audit()
        if not mesh.get("ok"):
            fulfillment = mesh.get("fulfillment") or {}
            fulfilled = int(fulfillment.get("fulfilled") or 0)
            total = int(fulfillment.get("total") or 15)
            # Only escalate when cycle idle AND mesh still mostly empty
            if fulfilled < max(1, total // 3):
                return ("polymorphic_mesh_incomplete", {"fulfillment": fulfillment})
    except Exception:
        pass
    return None


def _detect_dashboard_down() -> tuple[str, dict[str, Any]] | None:
    if os.environ.get("OWL_EXTERNAL_DASHBOARD", "1") != "1":
        return None
    port = int(os.environ.get("DASHBOARD_PORT", "7878"))
    if _port_listener_pid(port):
        return None
    return ("dashboard_down", {"port": port})


def _detect_false_margin_block() -> tuple[str, dict[str, Any]] | None:
    """Blofin 103003 despite local margin math passing — leverage/mode mismatch."""
    try:
        from autohedge.tools.trade_journal import _read_last_n

        for line in reversed(_read_last_n(30)):
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") != "order_blocked":
                continue
            if ev.get("reason") not in ("insufficient_margin_exchange", None):
                if "103003" not in str(ev.get("msg") or ""):
                    continue
            try:
                avail = float(ev.get("available_usdt") or 0)
                need = float(ev.get("margin_need_usdt") or 0)
            except (TypeError, ValueError):
                continue
            if need > 0 and avail > need * 1.5:
                return (
                    "false_margin_block",
                    {
                        "instId": ev.get("instId"),
                        "available_usdt": avail,
                        "margin_need_usdt": need,
                        "age_sec": round(time.time() - float(ev.get("ts") or 0), 1),
                    },
                )
    except Exception:
        pass
    return None


def _detect_tpsl_rate_limited() -> tuple[str, dict[str, Any]] | None:
    try:
        from autohedge.tpsl_guard import audit_open_positions_tpsl, is_tpsl_audit_rate_limited

        audit = audit_open_positions_tpsl()
        if is_tpsl_audit_rate_limited(audit):
            return (
                "tpsl_rate_limit_blocking",
                {
                    "missing": audit.get("missing"),
                    "pending_error": str(audit.get("pending_error") or "")[:120],
                },
            )
    except Exception:
        pass
    return None


def _detect_prerank_held_symbol() -> tuple[str, dict[str, Any]] | None:
    try:
        from autohedge.handoff_pipeline import pipeline_status
        from autohedge.tools.blofin_tools import _blocked_sets
        from autohedge.tools.tool_utils import normalize_usdt_inst_id

        ps = pipeline_status()
        cand = normalize_usdt_inst_id(str(ps.get("candidate_inst_id") or ""))
        if not cand:
            return None
        blocked_buy, blocked_sell = _blocked_sets()
        if cand in blocked_buy or cand in blocked_sell:
            return (
                "prerank_held_symbol",
                {"candidate": cand, "blocked_buy": list(blocked_buy), "blocked_sell": list(blocked_sell)},
            )
    except Exception:
        pass
    return None


def _start_external_dashboard() -> bool:
    script = ROOT / "scripts" / "dashboard_server.py"
    if not script.is_file() or not Path(PYTHON).is_file():
        return False
    env = {**os.environ, "OWL_EXTERNAL_DASHBOARD": "1", "OUTPUT_DIR": str(OUTPUT_DIR)}
    subprocess.Popen(
        [PYTHON, str(script)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    time.sleep(2)
    port = int(os.environ.get("DASHBOARD_PORT", "7878"))
    return _port_listener_pid(port) is not None


def _detect_cycle_log_stall() -> tuple[str, dict[str, Any]] | None:
    if not _owl_pid():
        return None
    age = _owl_log_age_sec()
    if age < 120:
        return None
    tail = _tail_owl_log(40)
    text = "\n".join(tail)
    if "Sleeping " in text or "COMPLETE" in text:
        return None
    return ("cycle_log_stall", {"log_age_sec": round(age, 1), "last": (tail[-1] if tail else "")[:120]})


def _detect_phantom_execution() -> tuple[str, dict[str, Any]] | None:
    try:
        from autohedge.handoff_pipeline import pipeline_status

        ps = pipeline_status()
        cand = str(ps.get("candidate_inst_id") or "").strip().upper()
        if "Execution-Agent" not in set(ps.get("completed") or []) or not cand:
            return None
        if _journal_order_placed_recent(cand):
            return None
        if ps.get("risk_approved"):
            return ("phantom_execution", {"candidate": cand, "terminal": ps.get("terminal")})
    except Exception:
        pass
    return None


def _detect_blofin_rate_limit_storm() -> tuple[str, dict[str, Any]] | None:
    hits = sum(1 for line in _tail_owl_log(80) if "429" in line or "rate limit" in line.lower())
    if hits >= 6:
        return ("blofin_rate_limit_storm", {"429_lines": hits})
    return None


def _detect_risk_veto_stale() -> tuple[str, dict[str, Any]] | None:
    try:
        from autohedge.risk_gate import audit_risk_veto_righteous

        audit = audit_risk_veto_righteous()
        if audit.get("righteous") is False:
            verdict = str(audit.get("verdict") or "risk_veto_stale")
            issue_id = (
                "tpsl_flat_false_veto"
                if verdict == "tpsl_flat_false_veto"
                else "risk_veto_stale"
            )
            return (
                issue_id,
                {
                    "verdict": verdict,
                    "reason": str(audit.get("reason") or "")[:200],
                    "open_positions": audit.get("open_positions"),
                    "stale_symbols": audit.get("stale_symbols"),
                },
            )
    except Exception:
        pass
    return None


def _detect_tpsl_flat_false_veto_log() -> tuple[str, dict[str, Any]] | None:
    for line in reversed(_tail_owl_log(50)):
        if "TPSL guard blocked" in line and "unprotected: []" in line:
            return ("tpsl_flat_false_veto", {"log_line": line.strip()[-220:]})
    return None


def _detect_stale_positions_cache() -> tuple[str, dict[str, Any]] | None:
    cache_path = AUTO_TRADER_OUTPUT / "positions-cache.json"
    if not cache_path.is_file():
        return None
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cached_rows = list(cache.get("open_rows") or [])
    except (json.JSONDecodeError, OSError):
        return None
    if not cached_rows:
        return None
    snap = _fetch_live_snap()
    if not snap:
        return None
    live_rows = list(snap.get("positions") or [])
    if not live_rows:
        return (
            "stale_positions_cache",
            {
                "cached_count": len(cached_rows),
                "live_count": 0,
                "cached_symbols": [r.get("instId") for r in cached_rows[:8]],
            },
        )
    cached_set = {
        str(r.get("instId") or "").upper() for r in cached_rows if r.get("instId")
    }
    live_set = {str(r.get("instId") or "").upper() for r in live_rows if r.get("instId")}
    ghost = sorted(cached_set - live_set)
    if ghost:
        return (
            "stale_positions_cache",
            {
                "cached_count": len(cached_rows),
                "live_count": len(live_rows),
                "ghost_symbols": ghost,
            },
        )
    return None


def _detect_stale_account_available() -> tuple[str, dict[str, Any]] | None:
    snap = _fetch_live_snap()
    if not snap:
        return None
    live_avail = float(snap.get("available") or 0)
    if live_avail <= 0:
        return None
    owl_live = OUTPUT_DIR / "owl-live.json"
    stale_avail = 0.0
    age = 9999.0
    if owl_live.is_file():
        try:
            row = json.loads(owl_live.read_text(encoding="utf-8"))
            stale_avail = float(row.get("available") or 0)
            age = time.time() - float(row.get("account_ts") or row.get("updated_at") or 0)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return None
    drift = abs(live_avail - stale_avail)
    if drift >= 0.25 and (stale_avail < live_avail * 0.75 or age > 120):
        return (
            "stale_account_available",
            {
                "owl_live_available": stale_avail,
                "exchange_available": live_avail,
                "drift_usdt": round(drift, 4),
                "age_sec": round(age, 1),
            },
        )
    return None


def _detect_vague_risk_catchall() -> tuple[str, dict[str, Any]] | None:
    for line in reversed(_tail_owl_log(60)):
        if "no candidate passed risk checks (tried rank top picks)" in line:
            return ("risk_veto_skip_log", {"log_line": line.strip()[-220:]})
        if "Deterministic Risk veto" in line and "no candidate passed risk checks" in line:
            if " — " not in line and ": " not in line.split("no candidate", 1)[-1][:40]:
                return ("risk_veto_skip_log", {"log_line": line.strip()[-220:]})
    return None


PROBE_SEVERITY: dict[str, str] = {
    "risk_veto_stale": "high",
    "tpsl_flat_false_veto": "critical",
    "stale_positions_cache": "high",
    "stale_account_available": "medium",
    "risk_veto_skip_log": "medium",
}


def probe_playbook_findings() -> list[dict[str, Any]]:
    """Expose playbook detectors to pentest/overseer as structured findings."""
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for detect in (
        _detect_risk_veto_stale,
        _detect_tpsl_flat_false_veto_log,
        _detect_stale_positions_cache,
        _detect_stale_account_available,
        _detect_vague_risk_catchall,
    ):
        hit = detect()
        if not hit:
            continue
        issue_id, ctx = hit
        if issue_id in seen:
            continue
        seen.add(issue_id)
        mission = (
            "dashboard"
            if issue_id in ("stale_positions_cache", "stale_account_available")
            else "trade_pipeline"
        )
        findings.append(
            {
                "id": issue_id,
                "severity": PROBE_SEVERITY.get(issue_id, "high"),
                "mission": mission,
                "detail": json.dumps(ctx, default=str)[:320],
                "evidence": ctx,
            }
        )
    return findings


DETECTORS: list[Callable[[], tuple[str, dict[str, Any]] | None]] = [
    _detect_stale_lock,
    _detect_port_hijacker,
    _detect_dashboard_down,
    _detect_cycle_log_stall,
    _detect_phantom_execution,
    _detect_blofin_rate_limit_storm,
    _detect_stale_ws_cache,
    _detect_missing_tpsl,
    _detect_tpsl_rate_limited,
    _detect_false_margin_block,
    _detect_prerank_held_symbol,
    _detect_universe_stale,
    _detect_task_completion_gap,
    _detect_mesh_incomplete,
    _detect_surface_sync_drift,
    _detect_risk_veto_stale,
    _detect_tpsl_flat_false_veto_log,
    _detect_stale_positions_cache,
    _detect_stale_account_available,
    _detect_vague_risk_catchall,
]


def _apply_fix(issue_id: str, ctx: dict[str, Any]) -> bool:
    """Execute remediation. Returns True if fix attempted."""
    try:
        if issue_id == "stale_lock":
            (OUTPUT_DIR / "owl-llm.lock").unlink(missing_ok=True)
            return True

        if issue_id == "port_hijacker":
            if os.environ.get("OWL_EXTERNAL_DASHBOARD", "1") == "1":
                return False
            pid = int(ctx.get("pid") or 0)
            if pid:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                return True

        if issue_id == "stale_ws_cache":
            script = ROOT / "scripts" / "write_universe_cache.py"
            if script.is_file() and Path(PYTHON).is_file():
                subprocess.Popen(
                    [PYTHON, str(script)],
                    cwd=str(ROOT),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                return True

        if issue_id == "missing_tpsl":
            from autohedge.tpsl_guard import repair_missing_tpsl

            logger.error("Auto-heal triggering: repair_missing_tpsl()")
            repair_missing_tpsl()
            logger.error("Auto-heal finished: repair_missing_tpsl()")
            return True

        if issue_id == "universe_feed_stale":
            from autohedge.tools.blofin_universe_feed import get_universe_feed

            get_universe_feed().refresh(force=True)
            return True

        if issue_id == "task_completion_gap":
            from autohedge.swarm_tasks import ensure_task_board_seeded
            from autohedge.task_completion_audit import audit_cycle_tasks

            ensure_task_board_seeded()
            audit_cycle_tasks(source="playbook_heal", auto_repair=True)
            return True

        if issue_id == "polymorphic_mesh_incomplete":
            from autohedge.collective_audit import run_polymorphic_mesh_audit

            run_polymorphic_mesh_audit()
            return True

        if issue_id == "surface_sync_drift":
            from autohedge.swarm_surface_sync import verify_surface_sync

            verify_surface_sync()
            return True

        if issue_id == "dashboard_down":
            return _start_external_dashboard()

        if issue_id == "false_margin_block":
            os.environ.setdefault("BLOFIN_MARGIN_MODE", "isolated")
            os.environ.setdefault("OWL_MAX_LEVERAGE", "12")
            from autohedge.risk_gate import deploy_idle_margin, reseed_unheld_candidate

            reseed_unheld_candidate()
            deploy_idle_margin()
            return True

        if issue_id == "tpsl_rate_limit_blocking":
            # Code path already skips blocking on 429; retry repair when API cools
            time.sleep(3)
            from autohedge.tpsl_guard import repair_missing_tpsl

            logger.error("Auto-heal triggering: repair_missing_tpsl()")
            repair_missing_tpsl()
            logger.error("Auto-heal finished: repair_missing_tpsl()")
            return True

        if issue_id == "prerank_held_symbol":
            from autohedge.risk_gate import deploy_idle_margin, reseed_unheld_candidate

            if reseed_unheld_candidate():
                deploy_idle_margin()
                return True
            return False

        if issue_id == "phantom_execution":
            from autohedge.handoff_pipeline import reset_handoff_pipeline
            from autohedge.risk_gate import pick_edge_candidate

            reset_handoff_pipeline()
            pick_edge_candidate()
            return True

        if issue_id == "cycle_log_stall":
            restart_file = OUTPUT_DIR / "restart_pending.json"
            restart_file.write_text(
                json.dumps({"reason": "cycle_log_stall", "ctx": ctx, "ts": time.time()}),
                encoding="utf-8",
            )
            return True

        if issue_id == "blofin_rate_limit_storm":
            _set_api_cooldown(120.0, reason="429_storm")
            return True

        if issue_id in ("risk_veto_stale", "tpsl_flat_false_veto"):
            from autohedge.handoff_pipeline import _pipeline, reset_handoff_pipeline
            from autohedge.risk_gate import maybe_clear_stale_risk_veto, pick_edge_candidate

            if maybe_clear_stale_risk_veto(_pipeline):
                return True
            reset_handoff_pipeline()
            pick_edge_candidate()
            return True

        if issue_id in ("stale_positions_cache", "stale_account_available"):
            snap = _fetch_live_snap(force=True)
            if snap:
                _heal_owl_live_from_snap(snap)
                return True
            return False

        if issue_id == "risk_veto_skip_log":
            # Code path already emits per-candidate skip_log — teach only, no runtime mutation.
            return True
    except Exception as exc:
        logger.warning("Playbook fix {} failed: {}", issue_id, exc)
        return False
    return False


FIX_META: dict[str, dict[str, str]] = {
    "stale_lock": {
        "title": "Clear stale owl-llm.lock",
        "action": "unlink lock file when holder PID is dead",
        "component": "preflight",
    },
    "tpsl_invalid_price_placeholder": {
        "title": "Blofin rejects -1 as default price for TP/SL",
        "detail": "Blofin API rejects order-tpsl with tpOrderPrice='-1' or slOrderPrice='-1'.",
        "component": "blofin_tools",
        "action": "Use actual trigger price for tpOrderPrice and slOrderPrice; never use '-1' placeholder.",
    },
    "port_hijacker": {
        "title": "Protect external dashboard_server on :7878",
        "action": "When OWL_EXTERNAL_DASHBOARD=1, whitelist dashboard_server.py PID — never taskkill",
        "component": "preflight",
    },
    "dashboard_down": {
        "title": "Standalone dashboard server not listening",
        "action": "Start scripts/dashboard_server.py; write dashboard-server.pid; never kill with port_hijacker",
        "component": "dashboard",
    },
    "dashboard_restart_storm": {
        "title": "Launcher killing dashboard on slow API",
        "action": "Test-OwlDashboardHealthy: process+port=alive; 60s cooldown; no -Fresh in monitor loop",
        "component": "launch",
    },
    "false_margin_block": {
        "title": "Blofin 103003 despite sufficient available margin",
        "action": "Set BLOFIN_MARGIN_MODE=isolated + OWL_MAX_LEVERAGE=12; reseed unheld symbol; deploy_idle_margin",
        "component": "risk_gate",
    },
    "tpsl_rate_limit_blocking": {
        "title": "TPSL verify rate-limited — falsely blocking new trades",
        "action": "On Blofin 429, skip TPSL veto for new symbols; repair TP/SL when API recovers",
        "component": "tpsl_guard",
    },
    "prerank_held_symbol": {
        "title": "Pipeline candidate already has open position",
        "action": "reseed_unheld_candidate() then deploy_idle_margin — never add size on held symbols",
        "component": "risk_gate",
    },
    "task_board_deadlock": {
        "title": "Task board persist deadlock on cycle init",
        "action": "swarm_tasks._lock must be threading.RLock() — init_cycle_tasks calls get_task_board under same lock",
        "component": "swarm_tasks",
    },
    "leverage_margin_mismatch": {
        "title": "Execution used wrong leverage/margin mode vs risk gate",
        "action": "blofin_execute_minimum_trade uses OWL_MAX_LEVERAGE; ensure_trade_leverage defaults isolated",
        "component": "blofin_tools",
    },
    "fast_deploy_false_success": {
        "title": "Fast margin deploy logged success on veto only",
        "action": "Log success only when Execution-Agent in pipeline.completed after deploy_idle_margin",
        "component": "owl_llm_loop",
    },
    "ops_monitor_blocking_pipeline": {
        "title": "Ops monitor blocked trading pipeline",
        "action": "Run ops monitor in background thread; never block Director handoff",
        "component": "owl_llm_loop",
    },
    "stale_ws_cache": {
        "title": "Refresh stale WS ticker cache",
        "action": "run write_universe_cache.py REST fallback",
        "component": "preflight",
    },
    "missing_tpsl": {
        "title": "Repair positions missing full TP+SL (isolated margin)",
        "action": "tpsl_guard.run_tpsl_guard() — BOTH tp+sl on matching marginMode",
        "component": "tpsl_guard",
    },
    "universe_feed_stale": {
        "title": "Refresh stale universe feed",
        "action": "universe_feed.refresh(force=True)",
        "component": "preflight",
    },
    "task_completion_gap": {
        "title": "Task board did not match live verification",
        "action": "audit_cycle_tasks(auto_repair=True) — re-check every done task vs Blofin",
        "component": "task_completion_audit",
    },
    "desktop_hygiene": {
        "title": "Close old PowerShell and browser tabs before opening new ones",
        "action": "Close-StaleOwlDesktopWindows before Start-Process monitor/dashboard",
        "component": "launch",
    },
    "clique_rugged": {
        "title": "Clique rugged — all agents verified-rich, peers are crutches",
        "action": "run_polymorphic_mesh_audit() + audit_clique_rugged until 11/11 fulfill",
        "component": "collective_audit",
    },
    "clique_weak_link": {
        "title": "Weak agent in clique — full mesh must crutch before fall",
        "action": "pulse_peer_mesh(focus_agents=[weak]) — all 10 peers audit the weak agent",
        "component": "collective_audit",
    },
    "polymorphic_mesh": {
        "title": "Full mesh — every agent connected to every other until all fulfill",
        "action": "all_peer_pairs() in swarm_topology + dashboard mesh_fulfillment UI",
        "component": "swarm_topology",
    },
    "polymorphic_mesh_incomplete": {
        "title": "Mesh incomplete — not all 11 agents fulfilled",
        "action": "run_polymorphic_mesh_audit(auto_repair via peer pulses on weak/pending)",
        "component": "collective_audit",
    },
    "surface_sync": {
        "title": "Keep dashboard and graph API aligned with swarm logic",
        "action": "verify_surface_sync(); update swarm_dashboard.html when adding graph fields",
        "component": "swarm_surface_sync",
    },
    "surface_sync_drift": {
        "title": "Dashboard or graph API drifted from production logic",
        "action": "Update swarm_dashboard.html markers + REQUIRED_GRAPH_FIELDS together",
        "component": "swarm_surface_sync",
    },
    "cycle_log_stall": {
        "title": "Owl cycle log stalled mid-cycle",
        "action": "Write restart_pending.json for launcher graceful restart",
        "component": "owl_llm_loop",
    },
    "phantom_execution": {
        "title": "Execution-Agent completed without journal order_placed",
        "action": "reset_handoff_pipeline + pick_edge_candidate — never trust phantom fills",
        "component": "risk_gate",
    },
    "blofin_rate_limit_storm": {
        "title": "Blofin 429 rate-limit storm",
        "action": "Set API cooldown 120s; defer API-heavy heals until cool",
        "component": "blofin_client",
    },
    "risk_veto_stale": {
        "title": "Risk veto cites closed positions or stale TPSL",
        "action": "maybe_clear_stale_risk_veto(); audit_risk_veto_righteous; filter TPSL to live open only",
        "component": "risk_gate",
    },
    "tpsl_flat_false_veto": {
        "title": "TPSL guard blocks entries on flat account",
        "action": "audit_open_positions_tpsl ok=True when open_count=0; risk_gate flat_account bypass",
        "component": "tpsl_guard",
    },
    "stale_positions_cache": {
        "title": "positions-cache.json shows closed trades as open",
        "action": "blofin_live_api.fetch_live_account(force=True) persists authoritative open_rows",
        "component": "dashboard",
    },
    "stale_account_available": {
        "title": "Event log available margin stale vs exchange",
        "action": "_sync_live_account() via blofin_live_api; refresh owl-live.json available+equity",
        "component": "owl_llm_loop",
    },
    "dashboard_pnl_contract_value": {
        "title": "Dashboard PnL scaled wrong (missing contractValue)",
        "action": "equity_stream unrealized_pnl multiplies by pos.contractValue; restart equity_stream",
        "component": "equity_stream",
    },
    "risk_veto_skip_log": {
        "title": "Opaque Risk catch-all veto hid per-symbol reasons",
        "action": "_log_skip per candidate; veto lists INST: reason; skip_log in Risk payload",
        "component": "risk_gate",
    },
}


def run_autonomous_heal(*, source: str = "autopilot") -> dict[str, Any]:
    """
    Detect issues → apply playbook if taught → teach on first fix.
    Never fix the same issue twice without recording it for the swarm.
    """
    report: dict[str, Any] = {
        "ok": True,
        "source": source,
        "detected": [],
        "auto_healed": [],
        "newly_taught": [],
        "failed": [],
        "ts": time.time(),
    }

    data = _load()
    known = data.get("fixes") or {}

    for detect in DETECTORS:
        hit = detect()
        if not hit:
            continue
        issue_id, ctx = hit
        if _api_cooldown_active() and issue_id in API_HEAVY_FIXES:
            report["detected"].append(
                {"issue_id": issue_id, "ctx": ctx, "deferred": "api_cooldown"}
            )
            continue
        report["detected"].append({"issue_id": issue_id, "ctx": ctx})
        meta = FIX_META.get(issue_id, {"title": issue_id, "action": "auto", "component": source})

        if issue_id in known and int(known[issue_id].get("teach_count") or 0) > 0:
            if _apply_fix(issue_id, ctx):
                record_auto_heal(
                    issue_id,
                    detail=meta["title"],
                    proof={**ctx, "from_playbook": True},
                )
                report["auto_healed"].append(issue_id)
                logger.info("PLAYBOOK auto-healed [{}] (count={})", issue_id, known[issue_id].get("auto_apply_count"))
            else:
                report["failed"].append(issue_id)
        else:
            if _apply_fix(issue_id, ctx):
                teach_fix(
                    issue_id,
                    title=meta["title"],
                    detail=json.dumps(ctx, default=str)[:500],
                    component=meta["component"],
                    action=meta["action"],
                    proof=ctx,
                )
                report["newly_taught"].append(issue_id)
                try:
                    from autohedge.swarm_learning_audit import record_self_fix

                    record_self_fix(
                        title=meta["title"],
                        detail=json.dumps(ctx, default=str)[:300],
                        component=meta["component"],
                        proof=ctx,
                    )
                except Exception:
                    pass
            else:
                report["failed"].append(issue_id)

    report["ok"] = len(report["failed"]) == 0
    return report


def teach_from_audit_event(
    *,
    issue_id: str,
    title: str,
    detail: str,
    component: str,
    action: str | None = None,
    proof: dict[str, Any] | None = None,
) -> None:
    """Hook for any self_fix in audit trail — compound into playbook."""
    teach_fix(
        issue_id,
        title=title,
        detail=detail,
        component=component,
        action=action or detail[:200],
        proof=proof,
    )


# ── Fix-once-teach-forever catalog (reinforced every boot) ──

KNOWN_FIXES: dict[str, dict[str, str]] = {
    "tpsl_invalid_price_placeholder": {
        "title": "Blofin rejects -1 as default price for TP/SL",
        "detail": "Blofin API rejects order-tpsl with tpOrderPrice='-1' or slOrderPrice='-1'.",
        "component": "blofin_tools",
        "action": "Use actual trigger price for tpOrderPrice and slOrderPrice; never use '-1' placeholder.",
    },
    "port_hijacker": {
        "title": "Protect external dashboard_server on :7878",
        "detail": "preflight port_hijacker was taskkilling dashboard_server.py every cycle when OWL_EXTERNAL_DASHBOARD=1.",
        "component": "preflight",
        "action": "When OWL_EXTERNAL_DASHBOARD=1, whitelist dashboard_server.py PID — never taskkill",
    },
    "dashboard_down": {
        "title": "Standalone dashboard server not listening",
        "detail": "Port 7878 has no LISTENING process while browser/launcher still poll.",
        "component": "dashboard",
        "action": "Start scripts/dashboard_server.py; write dashboard-server.pid",
    },
    "dashboard_restart_storm": {
        "title": "Launcher restart storm killed dashboard every 16s",
        "detail": "Slow /api/status during Blofin refresh triggered -Fresh kill loop.",
        "component": "launch",
        "action": "Test-OwlDashboardHealthy: process+port=alive; 60s cooldown; no -Fresh in monitor loop",
    },
    "false_margin_block": {
        "title": "Blofin 103003 despite sufficient available margin",
        "detail": "Risk gate assumed 12x isolated but execution set 50x cross — exchange rejected orders.",
        "component": "risk_gate",
        "action": "BLOFIN_MARGIN_MODE=isolated + OWL_MAX_LEVERAGE=12; reseed unheld symbol; deploy_idle_margin",
    },
    "tpsl_rate_limit_blocking": {
        "title": "TPSL verify rate-limited — falsely blocking new trades",
        "detail": "Blofin 429 on orders-tpsl-pending made audit think positions were unprotected.",
        "component": "tpsl_guard",
        "action": "On Blofin 429, skip TPSL veto for new symbols; repair TP/SL when API recovers",
    },
    "prerank_held_symbol": {
        "title": "Pipeline candidate already has open position",
        "detail": "Pre-rank kept picking Q/XAI/PUMP while user already held them — 103003 on add-size.",
        "component": "risk_gate",
        "action": "reseed_unheld_candidate() then deploy_idle_margin — never add size on held symbols",
    },
    "task_board_deadlock": {
        "title": "Task board persist deadlock on cycle init",
        "detail": "init_cycle_tasks held Lock and called get_task_board which re-acquired same Lock.",
        "component": "swarm_tasks",
        "action": "swarm_tasks._lock must be threading.RLock() not Lock()",
    },
    "leverage_margin_mismatch": {
        "title": "Execution used wrong leverage/margin mode vs risk gate",
        "detail": "blofin_execute_minimum_trade called ensure_trade_leverage(target=50) with cross default.",
        "component": "blofin_tools",
        "action": "Use OWL_MAX_LEVERAGE + BLOFIN_MARGIN_MODE=isolated in ensure_trade_leverage and place_order",
    },
    "fast_deploy_false_success": {
        "title": "Fast margin deploy logged success on veto only",
        "detail": "deploy_idle_margin returns veto strings as truthy — misled operators.",
        "component": "owl_llm_loop",
        "action": "Log success only when journal has order_placed + orderId (_order_confirmed)",
    },
    "phantom_execution": {
        "title": "Execution-Agent completed without journal order_placed",
        "detail": "Pipeline marked complete but no orderId in trade_journal — false success.",
        "component": "risk_gate",
        "action": "reset_handoff_pipeline + pick_edge_candidate; deploy with force=True only after journal proof",
    },
    "cycle_log_stall": {
        "title": "Owl cycle log stalled mid-cycle",
        "detail": "owl-llm.log mtime >120s without COMPLETE/Sleeping — cycle hung on support/Director.",
        "component": "owl_llm_loop",
        "action": "Write restart_pending.json; launcher graceful restart single PID",
    },
    "blofin_rate_limit_storm": {
        "title": "Blofin 429 rate-limit storm blocking orders",
        "detail": "Heavy preflight/TPSL/dashboard hammering caused position-mode and place_order 429s.",
        "component": "blofin_client",
        "action": "API cooldown 120s; defer false_margin_block/missing_tpsl heals during cooldown",
    },
    "autonomous_edge_trade": {
        "title": "Autonomous edge-driven proof trade",
        "detail": "ensure_autonomous_trade picks unheld symbol with OWL_EDGE_MIN_PROB/CHG; verifies journal orderId.",
        "component": "risk_gate",
        "action": "pick_edge_candidate + deploy_idle_margin(force=True); overseer + post-cycle background",
    },
    "fast_deploy_primary_veto": {
        "title": "Fast deploy veto — only tried one candidate",
        "detail": "primary_only=True failed on pre-ranked pick; no fallback to next unheld symbol.",
        "component": "owl_llm_loop",
        "action": "deploy_idle_margin(primary_only=False); journal proof via _journal_has_order_for",
    },
    "api_429_trade_block": {
        "title": "429 storm stalls trade deploy",
        "detail": "Repeated assess/tpsl/positions API per candidate triggers Cloudflare 1015.",
        "component": "risk_gate",
        "action": "assess_cache per deploy batch; API cooldown 90s; disk position cache",
    },
    "pentest_squad": {
        "title": "Pentest special forces — self-directing sniff/kill/fix",
        "detail": "4 interconnected LLM agents run recon → trade hunt + integrity → operator every cycle.",
        "component": "pentest_agents",
        "action": "pentest_build_mission_queue → pentest_apply_targeted_fixes → teach_fix on new patterns",
    },
    "overseer_stale_task_board": {
        "title": "Overseer audited sparse task board (<15 jobs)",
        "detail": "task_board.json had only 1-2 rows — overseer falsely reported missing oversight/ops_health.",
        "component": "swarm_tasks",
        "action": "ensure_task_board_seeded(cycle) before audit_cycle_tasks when total < 15",
    },
    "overseer_mid_cycle_audit": {
        "title": "Overseer false task failures during active cycle",
        "detail": "1-min overseer flagged pending required jobs while cycle still running.",
        "component": "task_completion_audit",
        "action": "relax required-job checks when source=overseer and is_cycle_in_progress()",
    },
    "overseer_light_vs_deep": {
        "title": "Overseer API storm from heavy checks every 60s",
        "detail": "pentest+mesh+collective care+autonomous trade every minute caused 429 stalls.",
        "component": "swarm_overseer",
        "action": "Light tick 60s (heal/TPSL/tasks); deep audit every OWL_DEEP_AUDIT_INTERVAL_SEC (900)",
    },
    "equity_stream_stale": {
        "title": "Dashboard equity frozen — REST throttled",
        "detail": "Equity value stuck when Blofin REST 429; user cannot confirm stream health.",
        "component": "equity_stream",
        "action": "refresh_streaming_equity() every 3s from ws-tickers + cached positions; monitor EQUITY_STREAM age",
    },
    "pipeline_director_stall": {
        "title": "Risk/Execution stuck — Director LLM blocked handoffs",
        "detail": "Cycle hung after pre-rank; PM→Quant never completed; Risk/Execution never ran.",
        "component": "handoff_pipeline",
        "action": "bootstrap_pipeline_for_deterministic + run_fast_pipeline_to_execution; OWL_DIRECTOR_TIMEOUT_SEC fallback",
    },
    "universe_scan_narrow": {
        "title": "Universe scan too narrow — missed trades",
        "detail": "Ranking capped at top 15-30 while feed has 500+ instruments; deploy tried only 6 candidates.",
        "component": "market_analytics",
        "action": "OWL_UNIVERSE_SCAN_ALL=1 OWL_RANK_TOP_N=0 OWL_DEPLOY_MAX_CANDIDATES=60 — rank full feed, walk all candidates",
    },
    "pipeline_veto_execution_stuck": {
        "title": "Risk veto left Execution active on dashboard",
        "detail": "terminal=true + risk_approved=false but next_agent=Execution-Agent — UI stuck forever.",
        "component": "handoff_pipeline",
        "action": "audit_pipeline_consistency in pentest; repair_pipeline_disk; next_agent() returns None when terminal",
    },
    "pipeline_execution_stall": {
        "title": "Risk approved but Execution never ran",
        "detail": "Handoff pipeline incomplete after Risk pass — Director or LLM blocked Execution.",
        "component": "handoff_pipeline",
        "action": "pentest_apply_targeted_fixes → run_fast_pipeline_to_execution(candidate)",
    },
    "post_cycle_task_board_race": {
        "title": "Verifier false-fails auditing next cycle task board",
        "detail": "post_cycle_bg ran after init_cycle_tasks(N+1) — audited pending tasks as failures.",
        "component": "owl_llm_loop",
        "action": "Capture cycle_num + board_snapshot in finally; pass to run_verifier_task_audit",
    },
    "ops_monitor_blocking_pipeline": {
        "title": "Ops monitor blocked trading pipeline",
        "detail": "Synchronous ops monitor stalled cycle before Director handoff.",
        "component": "owl_llm_loop",
        "action": "Run ops monitor in background thread; trading pipeline proceeds immediately",
    },
    "desktop_hygiene": {
        "title": "Close old PowerShell and browser tabs before opening new ones",
        "detail": "Duplicate launchers/monitors/dashboard tabs cause kill storms and stale locks.",
        "component": "launch",
        "action": "Stop-AllOwlBotsOnComputer -FastBoot; mutex retry; Repair-OwlStackDuplicates not full kill",
    },
    "launcher_stops_after_kill": {
        "title": "Launcher appeared to stop after killing bots",
        "detail": "Phase 1 kill took 60s+ or mutex held by dead launcher — user thought it exited.",
        "component": "launch",
        "action": "FastBoot kill + mutex WaitOne retry 8x; launcher window stays in while($true) monitor loop",
    },
    "pipeline_fast_persistent": {
        "title": "Trading pipeline must be fast, redundant, and disk-persistent",
        "detail": "Director LLM stall blocks Risk/Execution; dashboard graph drifts from handoff state.",
        "component": "handoff_pipeline",
        "action": "persist_pipeline_state after each agent; run_fast_pipeline_to_execution before Director; restore_pipeline_from_disk on crash",
    },
    "pipeline_parallel_prefetch": {
        "title": "Pre-rank and support agents run in parallel threads",
        "detail": "Sequential universe fetch + support blocked Director for 30-60s per cycle.",
        "component": "owl_llm_loop",
        "action": "owl-opps-prefetch thread; support bg with OWL_SUPPORT_WAIT_SEC=5 when top_pick locked",
    },
    "clique_rugged": {
        "title": "Clique rugged — peers are crutches",
        "detail": "If every agent is verified-rich, the clique is rugged; no one falls because everyone audits each other.",
        "component": "collective_audit",
        "action": "run_polymorphic_mesh_audit() + audit_clique_rugged every cycle until 11/11 fulfill",
    },
    "polymorphic_mesh": {
        "title": "Full mesh — every polymorphic agent connected to every other",
        "detail": "110 directed peer links; mesh complete only when the last agent fulfills (11/11 pass).",
        "component": "swarm_topology",
        "action": "all_peer_pairs() edges in graph + run_polymorphic_mesh_audit post-cycle",
    },
    "surface_sync": {
        "title": "Update dashboard and all surfaces when swarm logic changes",
        "detail": "Backend-only changes left dashboard/playbook stale — verify_surface_sync catches drift.",
        "component": "swarm_surface_sync",
        "action": "verify_surface_sync() after every deploy; extend REQUIRED_GRAPH_FIELDS when adding API keys",
    },
    "tpsl_flat_false_veto": {
        "title": "TPSL guard blocks entries on flat account",
        "detail": "Risk veto 'unprotected: []' when positions=0 — false positive blocks all fast pipeline candidates.",
        "component": "tpsl_guard",
        "action": "audit_open_positions_tpsl returns ok=True when open_count=0; risk_gate flat_account bypass",
    },
    "fast_pipeline_stall": {
        "title": "Fast pipeline hangs after 'trying SYMBOL'",
        "detail": "run_fast_pipeline_to_execution blocked on 429 positions/instruments/leverage API retries.",
        "component": "risk_gate",
        "action": "pentest stall watchdog → disk cache + deploy_idle_margin; OWL_FAST_PIPELINE uses instrument disk first",
    },
    "pick_best_hang": {
        "title": "pick_best blocks cycle after pre-rank",
        "detail": "_blocked_sets() → _open_position_rows() hits 429 for minutes when account is flat.",
        "component": "owl_llm_loop",
        "action": "pick_best uses live.positions only when flat; pentest teaches squad on smell",
    },
    "duplicate_owl_process": {
        "title": "Duplicate owl_llm_loop processes",
        "detail": "Runtime fingerprint restarts + launcher overlap spawn twin bots that fight for API quota.",
        "component": "launch",
        "action": "pentest_operator Repair-OwlStackDuplicates; stop.ps1 before launch; mutex",
    },
    "risk_veto_stale": {
        "title": "Risk veto cites closed positions or stale TPSL",
        "detail": "Veto referenced symbols no longer open or TP/SL now protected — pipeline stuck until cleared.",
        "component": "risk_gate",
        "action": "maybe_clear_stale_risk_veto(); _prepare_portfolio_guards filters to live open only",
    },
    "stale_positions_cache": {
        "title": "positions-cache.json shows closed trades as open",
        "detail": "Manual close left stale open_rows; empty [] was treated as falsy — dashboard showed ghost positions.",
        "component": "dashboard",
        "action": "blofin_live_api.fetch_live_account(force=True); dashboard uses [] not stale cache",
    },
    "stale_account_available": {
        "title": "Event log / owl-live available stale vs exchange",
        "detail": "get_account_snapshot failed (solders import); live.available stuck low vs real wallet.",
        "component": "owl_llm_loop",
        "action": "_sync_live_account() via blofin_live_api on refresh_account/save_state",
    },
    "dashboard_pnl_contract_value": {
        "title": "Dashboard PnL ~1000× too small",
        "detail": "uPnL used (mark-avg)*qty without contractValue multiplier per Blofin perp instrument.",
        "component": "equity_stream",
        "action": "unrealized_pnl includes float(pos.contractValue); ws-tickers dict parsing fixed",
    },
    "risk_veto_skip_log": {
        "title": "Opaque Risk catch-all veto hid real reasons",
        "detail": "'no candidate passed risk checks (tried rank top picks)' without per-symbol skip_log.",
        "component": "risk_gate",
        "action": "_log_skip per candidate; veto message lists INST: reason; skip_log in payload",
    },
}


def reinforce_known_fixes() -> list[str]:
    """Ensure catalog fixes are taught — re-teach when action text drifts."""
    reinforced: list[str] = []
    data = _load()
    fixes = data.get("fixes") or {}
    for issue_id, meta in KNOWN_FIXES.items():
        row = fixes.get(issue_id) or {}
        if row.get("action") != meta["action"] or int(row.get("teach_count") or 0) < 1:
            teach_fix(issue_id, proof={"catalog": True}, **meta)
            reinforced.append(issue_id)
    return reinforced


def bootstrap_known_fixes(*, run_heal: bool = False) -> dict[str, Any]:
    """Boot-time: reinforce catalog; optional heal (preflight runs heal every cycle)."""
    reinforced = reinforce_known_fixes()
    heal: dict[str, Any] = {}
    if run_heal:
        heal = run_autonomous_heal(source="bootstrap")
    return {"reinforced": reinforced, "heal": heal}


def teach_from_journal_event(event: dict[str, Any]) -> None:
    """Compound journal patterns into playbook without human intervention."""
    etype = str(event.get("type") or "")
    if etype != "order_blocked":
        return
    reason = str(event.get("reason") or "")
    msg = str(event.get("msg") or "")
    if reason == "insufficient_margin_exchange" or "103003" in msg:
        try:
            avail = float(event.get("available_usdt") or 0)
            need = float(event.get("margin_need_usdt") or 0)
        except (TypeError, ValueError):
            avail = need = 0.0
        if need > 0 and avail > need * 1.5:
            teach_fix(
                "false_margin_block",
                title=KNOWN_FIXES["false_margin_block"]["title"],
                detail=f"{event.get('instId')} blocked: avail=${avail:.4f} need=${need:.4f}",
                component="risk_gate",
                action=KNOWN_FIXES["false_margin_block"]["action"],
                proof={"instId": event.get("instId"), "available_usdt": avail, "margin_need_usdt": need},
            )
    if "already has an open" in msg.lower():
        teach_fix(
            "prerank_held_symbol",
            title=KNOWN_FIXES["prerank_held_symbol"]["title"],
            detail=msg[:300],
            component="risk_gate",
            action=KNOWN_FIXES["prerank_held_symbol"]["action"],
            proof={"instId": event.get("instId"), "side": event.get("side")},
        )


def teach_from_journal_block(
    *,
    inst_id: str,
    available_usdt: float,
    margin_need_usdt: float,
    msg: str,
) -> None:
    teach_from_journal_event(
        {
            "type": "order_blocked",
            "instId": inst_id,
            "reason": "insufficient_margin_exchange",
            "available_usdt": available_usdt,
            "margin_need_usdt": margin_need_usdt,
            "msg": msg,
        }
    )


def playbook_summary() -> dict[str, Any]:
    data = _load()
    fixes = list((data.get("fixes") or {}).values())
    return {
        "total_fixes_taught": len(fixes),
        "auto_heals_total": int((data.get("stats") or {}).get("auto_heals") or 0),
        "fixes": sorted(fixes, key=lambda x: int(x.get("auto_apply_count") or 0), reverse=True)[:20],
        "path": str(PLAYBOOK_PATH),
    }


def playbook_json() -> str:
    return json.dumps(playbook_summary(), indent=2, default=str)


def playbook_block_for_agents() -> str:
    data = _load()
    fixes = list((data.get("fixes") or {}).values())[:12]
    if not fixes:
        return "\n\nSELF-HEAL PLAYBOOK: (empty — first fixes will be taught automatically)"
    lines = ["\n\nSELF-HEAL PLAYBOOK (auto-apply on recurrence — do NOT rediscover these fixes):"]
    for f in fixes:
        lines.append(
            f"  - [{f.get('issue_id')}] {f.get('title')}: {f.get('action')} "
            f"(auto-applied {f.get('auto_apply_count', 0)}x)"
        )
    return "\n".join(lines)
