"""
OWL Swarm Autopilot — self-verifying operations loop (Python production path).

Mirrors the original Twitter self-verifying swarm:
  execute → verify against live sources → reject → retry with feedback →
  repair infrastructure → compound learning → repeat until healthy.

No human in the loop for fixes the swarm can make itself.
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
_ops_started = False
_log_fn: Callable[[str, str], None] | None = None


def bind_logger(log_fn: Callable[[str, str], None]) -> None:
    global _log_fn
    _log_fn = log_fn


def _log(msg: str, level: str = "info") -> None:
    if _log_fn:
        _log_fn(msg, level)
    else:
        logger.log(level.upper(), msg)


def _record_self_fix(title: str, detail: str, component: str, proof: dict | None = None) -> None:
    try:
        from autohedge.swarm_learning_audit import record_self_fix

        record_self_fix(title=title, detail=detail, component=component, proof=proof or {})
        _log(f"AUTOPILOT FIX: {title}", "success")
    except Exception as exc:
        logger.warning("audit record failed: {}", exc)


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
                if parts:
                    pid = parts[-1]
                    if pid.isdigit():
                        return int(pid)
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


def preflight_repair() -> dict[str, Any]:
    """Health check + autonomous repair — playbook first (never fix twice)."""
    try:
        from autohedge.self_heal_playbook import run_autonomous_heal

        heal = run_autonomous_heal(source="preflight")
        report: dict[str, Any] = {
            "ok": heal.get("ok", True),
            "repairs": heal.get("auto_healed", []) + heal.get("newly_taught", []),
            "warnings": [],
            "playbook": heal,
        }
        if heal.get("failed"):
            report["warnings"].extend([f"heal_failed:{f}" for f in heal["failed"]])
            report["ok"] = False
    except Exception as exc:
        report = {"ok": False, "repairs": [], "warnings": [f"playbook:{exc}"], "playbook": {}}

    if report.get("repairs"):
        try:
            from autohedge.swarm_topology import pulse_repair
            from autohedge.swarm_tasks import finish_task, start_task

            start_task("infrastructure_repair", "Ops-Monitor-Agent", "fix", detail=str(report["repairs"]))
            pulse_repair()
            finish_task("infrastructure_repair", "Ops-Monitor-Agent", "fix", status="done")
        except Exception:
            pass
    return report


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


def postflight_verify(*, cycle: int, pipeline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Verify cycle outcomes against live API; auto-repair what we can."""
    report: dict[str, Any] = {"ok": True, "repairs": [], "warnings": []}

    try:
        from autohedge.tools.trade_journal import sync_position_closes

        sync_position_closes()
    except Exception as exc:
        report["warnings"].append(f"journal_sync:{exc}")

    try:
        from autohedge.tools.blofin_tools import blofin_assess_portfolio, blofin_ensure_position_tpsl

        pf = json.loads(blofin_assess_portfolio())
        missing = pf.get("positions_missing_tpsl") or []
        if missing:
            blofin_ensure_position_tpsl()
            report["repairs"].append("post_cycle_tpsl_repair")
            _record_self_fix(
                "Post-cycle TP/SL repair",
                f"After cycle {cycle}, fixed missing protection on {missing}",
                "postflight",
                {"cycle": cycle, "missing": missing},
            )
    except Exception as exc:
        report["warnings"].append(f"post_tpsl:{exc}")

    try:
        from autohedge.tpsl_guard import run_tpsl_guard

        tg = run_tpsl_guard(source=f"postflight_cycle_{cycle}")
        if tg.get("status") != "ok":
            report["ok"] = False
            report["warnings"].append(f"tpsl_guard:{tg.get('audit', {}).get('missing')}")
        elif tg.get("actions"):
            report["repairs"].append("tpsl_guard_verified")
    except Exception as exc:
        report["warnings"].append(f"tpsl_guard:{exc}")

    if pipeline and pipeline.get("risk_approved") and not pipeline.get("terminal"):
        report["warnings"].append("pipeline_incomplete_after_cycle")
        _log(f"Cycle {cycle} pipeline incomplete — will continue next cycle", "warn")

    try:
        from autohedge.tactics_learner import post_cycle_learn

        post_cycle_learn(cycle=cycle, pipeline=pipeline)
    except Exception:
        pass

    return report


def _agent_job(agent_name: str) -> str:
    return {
        "Portfolio-Manager": "portfolio",
        "Sentiment-Agent": "sentiment",
        "Quant-Analyst": "quant",
        "Risk-Manager": "risk",
        "Execution-Agent": "execution",
        "Trading-Director": "trading_pipeline",
        "Ops-Monitor-Agent": "ops_health",
        "Verifier-Agent": "verification",
        "Tactics-Researcher-Agent": "tactics_research",
        "Profit-Strategist-Agent": "profit_optimization",
        "Market-Researcher-Agent": "market_research",
    }.get(agent_name, "trading_pipeline")


def build_retry_task(agent_name: str, base_task: str, chk: dict[str, Any], attempt: int) -> str:
    from autohedge.agent_crosscheck import format_crosscheck_note

    note = format_crosscheck_note(chk)
    fixes = chk.get("fixes") or []
    fix_lines = "\n".join(f"- {f}" for f in fixes)
    return (
        f"{base_task}\n\n"
        f"═══ VERIFICATION REJECTED (attempt {attempt}) ═══\n"
        f"Your prior output failed live cross-check against Blofin API data.\n"
        f"{note}\n"
        f"Required fixes:\n{fix_lines or '- Re-call Blofin tools and correct all numbers.'}\n"
        f"Do NOT guess. Use tools. Output must pass verification."
    )


def run_agent_verified(
    pipeline: Any,
    agent_name: str,
    task: str,
    reasoning: str,
    agent_registry: dict[str, Any],
    *,
    max_retries: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Self-verifying agent execution: run → verify → reject → retry until pass.
    """
    from autohedge.agent_crosscheck import crosscheck_agent_output
    from autohedge.risk_gate import try_deterministic_risk_execution
    from autohedge.tactics_learner import record_crosscheck_lesson

    retries = max_retries or int(os.environ.get("OWL_VERIFY_MAX_RETRIES", "3"))
    fix_task = task
    last_response = ""
    last_chk: dict[str, Any] = {"ok": False, "issues": ["no_attempt"]}

    for attempt in range(1, retries + 1):
        logger.info("Verified run {} attempt {}/{}", agent_name, attempt, retries)
        try:
            from autohedge.swarm_tasks import start_task
            from autohedge.swarm_topology import set_agent_status, set_verify_status

            job = _agent_job(agent_name)
            start_task(job, agent_name, "execute", detail=f"attempt {attempt}/{retries}")
            set_agent_status(agent_name, "active", detail=f"attempt {attempt}")
            set_verify_status("checking")
        except Exception:
            pass
        last_response = str(agent_registry[agent_name].run(task=fix_task))
        last_chk = crosscheck_agent_output(
            agent_name,
            last_response,
            candidate_inst=pipeline.effective_candidate(),
            pipeline_outputs=dict(pipeline.agent_outputs),
        )
        if last_chk.get("ok"):
            try:
                from autohedge.swarm_tasks import finish_task
                from autohedge.swarm_topology import set_agent_status, set_verify_status

                finish_task(_agent_job(agent_name), agent_name, "execute", status="done")
                set_agent_status(agent_name, "pass")
                set_verify_status("pass")
            except Exception:
                pass
            if pipeline.pending_crosscheck_issues:
                from autohedge.swarm_learning_audit import record_self_fix

                prior = pipeline.pending_crosscheck_issues[-1]
                record_self_fix(
                    title=f"{agent_name} passed verify after peer issue",
                    detail=f"Resolved after cross-check on {prior.get('agent')}",
                    component="verify_retry",
                    proof={"agent": agent_name, "attempt": attempt},
                )
                pipeline.pending_crosscheck_issues.clear()
            return last_response, last_chk

        # LLM Verifier reviews failed cross-check before retry
        try:
            from autohedge.support_agents import run_llm_verifier

            v = run_llm_verifier(agent_name, last_response, last_chk)
            if v.get("passed"):
                try:
                    from autohedge.swarm_tasks import finish_task
                    from autohedge.swarm_topology import set_agent_status, set_verify_status

                    finish_task("verification", "Verifier-Agent", "audit", status="done", detail="LLM verifier pass")
                    set_agent_status(agent_name, "pass")
                    set_verify_status("pass")
                except Exception:
                    pass
                return last_response, {"ok": True, "source": "llm_verifier"}
        except Exception as exc:
            logger.warning("LLM verifier skipped: {}", exc)

        try:
            from autohedge.swarm_topology import set_verify_status, record_verify_fail

            set_verify_status("fail")
            record_verify_fail()
        except Exception:
            pass
        record_crosscheck_lesson(last_chk)
        pipeline.pending_crosscheck_issues.append(last_chk)
        _record_self_fix(
            f"Rejected {agent_name} output (attempt {attempt})",
            "; ".join(str(i) for i in (last_chk.get("issues") or [])),
            "verify_gate",
            {"agent": agent_name, "attempt": attempt, "issues": last_chk.get("issues")},
        )
        fix_task = build_retry_task(agent_name, task, last_chk, attempt)

    # No deterministic Risk/Execution bypass — failed verification is a cycle error
    if (
        agent_name == "Risk-Manager"
        and os.environ.get("OWL_ALLOW_DETERMINISTIC_RISK", "0").strip().lower()
        in ("1", "true", "yes")
    ):
        det = try_deterministic_risk_execution(pipeline)
        if det is not None:
            _record_self_fix(
                f"Deterministic Risk/Execution after {retries} LLM failures (explicit override)",
                "OWL_ALLOW_DETERMINISTIC_RISK=1",
                "risk_gate",
                {"instId": pipeline.effective_candidate()},
            )
            return det, {"ok": True, "source": "deterministic_risk_gate"}

    return last_response, last_chk


def _background_ops_loop() -> None:
    interval = int(os.environ.get("OWL_OPS_INTERVAL_SEC", "60"))
    while True:
        try:
            time.sleep(interval)
            preflight_repair()
            try:
                from autohedge.swarm_overseer import run_overseer_tick

                run_overseer_tick()
            except Exception:
                pass
        except Exception as exc:
            logger.warning("Background ops error: {}", exc)


def ensure_background_ops() -> None:
    global _ops_started
    if _ops_started:
        return
    _ops_started = True
    t = threading.Thread(target=_background_ops_loop, name="owl-autopilot-ops", daemon=True)
    t.start()
    _log("Autopilot + overseer active (self-repair + oversight every 60s)")
