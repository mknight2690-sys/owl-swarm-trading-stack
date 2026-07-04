"""Sequential trading handoffs: Portfolio → Sentiment → Quant → Risk → Execution."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from loguru import logger

from autohedge.risk_gate import try_deterministic_risk_execution
from autohedge.tools.tool_utils import normalize_usdt_inst_id

PIPELINE_ORDER = [
    "Portfolio-Manager",
    "Sentiment-Agent",
    "Quant-Analyst",
    "Risk-Manager",
    "Execution-Agent",
]

_SYMBOL_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,20}-USDT)\b")
_INST_JSON_RE = re.compile(
    r'recommended_inst_id["\']?\s*[:=]\s*["\']?([A-Z0-9-]+)',
    re.IGNORECASE,
)


class HandoffPipeline:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.completed: set[str] = set()
        self.risk_approved = False
        self.risk_veto_reason = ""
        self.candidate_inst_id = ""
        self.agent_outputs: dict[str, str] = {}
        self.terminal_skip = False
        self.pending_crosscheck_issues: list[dict[str, Any]] = []

    def next_agent(self) -> str | None:
        if self.is_terminal():
            return None
        for name in PIPELINE_ORDER:
            if name not in self.completed:
                return name
        return None

    def _stage(self, agent_name: str) -> int:
        try:
            return PIPELINE_ORDER.index(agent_name)
        except ValueError:
            return len(PIPELINE_ORDER)

    def _missing_prereq(self, agent_name: str) -> str | None:
        stage = self._stage(agent_name)
        if stage <= 0:
            return None
        for prereq in PIPELINE_ORDER[:stage]:
            if prereq not in self.completed:
                return prereq
        return None

    @staticmethod
    def _risk_approved(response: str) -> bool:
        text = (response or "").lower()
        if any(
            token in text
            for token in (
                "approved: false",
                "approved=false",
                '"approved": false',
                "approved false",
                "trade_allowed=false",
                "trade_allowed: false",
                "veto",
                "no trade",
            )
        ):
            return False
        if any(
            token in text
            for token in (
                "approved: true",
                "approved=true",
                '"approved": true',
                "approved true",
                "trade_allowed=true",
                "trade_allowed: true",
            )
        ):
            return True
        return False

    def effective_candidate(self) -> str:
        inst = normalize_usdt_inst_id(self.candidate_inst_id or "")
        if inst != self.candidate_inst_id:
            self.candidate_inst_id = inst
        return inst

    def note_symbols(self, *texts: str) -> None:
        if self.effective_candidate():
            return
        for text in texts:
            if not text:
                continue
            match = _INST_JSON_RE.search(text)
            if match:
                inst = normalize_usdt_inst_id(match.group(1))
                if inst:
                    self.candidate_inst_id = inst
                    return
                continue
            for sym in _SYMBOL_RE.findall(text):
                if sym.endswith("-USDT"):
                    self.candidate_inst_id = sym.upper()
                    return

    def set_candidate(self, inst_id: str) -> None:
        inst = normalize_usdt_inst_id(inst_id)
        if inst:
            self.candidate_inst_id = inst

    def is_terminal(self) -> bool:
        if "Execution-Agent" in self.completed:
            return True
        if "Risk-Manager" in self.completed and not self.risk_approved:
            return True
        if self.terminal_skip:
            return True
        return False

    def status(self) -> dict[str, Any]:
        return {
            "candidate_inst_id": self.candidate_inst_id,
            "completed": list(PIPELINE_ORDER) if len(self.completed) == len(PIPELINE_ORDER) else sorted(
                self.completed, key=lambda n: self._stage(n)
            ),
            "next_agent": self.next_agent(),
            "risk_approved": self.risk_approved,
            "risk_veto_reason": self.risk_veto_reason,
            "terminal": self.is_terminal(),
        }

    def _task_for(self, agent_name: str) -> str:
        inst = self.effective_candidate()
        if inst:
            inst_hint = f"Locked cycle candidate: {inst}."
            funding_arg = f"inst_id='{inst}'"
        else:
            inst = "the top ranked non-blocked symbol from blofin_rank_opportunities"
            inst_hint = "Pick ONE instId from blofin_rank_opportunities and lock it for remaining agents."
            funding_arg = "inst_id from your chosen symbol"
        tasks = {
            "Portfolio-Manager": (
                "Call blofin_assess_portfolio and blofin_get_equity_summary. "
                "At 50x cross margin, minimum-size alt perps often need under $1 initial margin. "
                "Do NOT set trade_allowed=false only because equity is small. "
                "Output recommended_inst_id for ONE new symbol (not blocked). "
                f"{inst_hint}"
            ),
            "Sentiment-Agent": (
                f"Analyze {inst}: blofin_get_funding_rate({funding_arg}) and crypto_news_search. "
                "Output sentiment score and 4-24h trading implication."
            ),
            "Quant-Analyst": (
                f"Run blofin_technical_analysis on {inst}. "
                "Output probability_score, suggested_side (long/short), key levels, and veto if score < 0.45."
            ),
            "Risk-Manager": (
                f"For {inst}: review Quant output (below). "
                "Use minimum contract size when risk-based size is below minSize. "
                "Approve at 50x if available margin covers min_notional/50. "
                "Output approved (true/false), position_size, stop_price, take_profit_price, risk_score.\n"
                f"Quant output excerpt:\n{(self.agent_outputs.get('Quant-Analyst') or '')[:1200]}"
            ),
            "Execution-Agent": (
                f"If Risk approved: call blofin_execute_minimum_trade once for {inst} "
                "with side and TP/SL from Risk. Otherwise output NO TRADE with reason."
            ),
        }
        return tasks[agent_name]

    def run(
        self,
        handoffs: list[dict[str, str]],
        agent_registry: dict[str, Any] | None,
    ) -> str:
        if not agent_registry:
            return "Error: No agent registry provided. Handoffs are not configured."
        if not handoffs:
            return "Error: No handoffs specified."

        valid: list[dict[str, str]] = []
        errors: list[str] = []
        seen: set[str] = set()

        for handoff in handoffs:
            if not isinstance(handoff, dict):
                errors.append(
                    "Each handoff must be a dictionary with agent_name, task, and reasoning"
                )
                continue
            agent_name = handoff.get("agent_name") or ""
            task = handoff.get("task") or ""
            if not agent_name:
                errors.append("One or more handoffs missing 'agent_name'")
                continue
            if not task:
                errors.append(f"Handoff to {agent_name} missing 'task'")
                continue
            if agent_name not in agent_registry:
                errors.append(
                    f"Agent '{agent_name}' not found. Available: {list(agent_registry.keys())}"
                )
                continue
            if agent_name in seen:
                continue
            seen.add(agent_name)
            self.note_symbols(task)
            valid.append(handoff)

        if errors and not valid:
            return "Validation errors:\n" + "\n".join(f"- {e}" for e in errors)

        valid.sort(key=lambda h: self._stage(h["agent_name"]))

        results: list[str] = []
        for handoff in valid:
            agent_name = handoff["agent_name"]
            task = handoff["task"]
            reasoning = handoff.get("reasoning", "")

            if agent_name in self.completed:
                nxt = self.next_agent()
                msg = (
                    f"Skipped duplicate handoff to {agent_name}: already completed this cycle. "
                    f"Hand off to {nxt} next."
                )
                logger.warning(msg)
                results.append(msg)
                continue

            prereq = self._missing_prereq(agent_name)
            if prereq:
                msg = (
                    f"Blocked handoff to {agent_name}: complete {prereq} first "
                    f"(pipeline: {' → '.join(PIPELINE_ORDER)})."
                )
                logger.warning(msg)
                results.append(msg)
                continue

            if agent_name == "Execution-Agent":
                if "Risk-Manager" not in self.completed:
                    msg = "Blocked Execution-Agent: Risk-Manager must finish before execution."
                    logger.warning(msg)
                    results.append(msg)
                    continue
                if not self.risk_approved:
                    msg = "Blocked Execution-Agent: Risk vetoed or did not approve the trade."
                    logger.warning(msg)
                    results.append(msg)
                    continue

            if agent_name == "Risk-Manager":
                pass  # Risk must run through verified LLM — no deterministic hijack

            try:
                logger.info(f"Delegating task to {agent_name}: {task[:100]}...")
                from autohedge.swarm_autopilot import run_agent_verified

                response_text, chk = run_agent_verified(
                    self,
                    agent_name,
                    task,
                    reasoning,
                    agent_registry,
                )
                if not chk.get("ok") and agent_name != "Risk-Manager":
                    err = (
                        f"Agent {agent_name} failed verification after retries: "
                        f"{chk.get('issues')}"
                    )
                    logger.error(err)
                    errors.append(err)
                    # Do not mark complete — pipeline stops for Director to recover
                    continue

                self.agent_outputs[agent_name] = response_text
                self.completed.add(agent_name)
                try:
                    persist_pipeline_state()
                except Exception:
                    pass
                nxt = self.next_agent()
                if nxt:
                    try:
                        from autohedge.swarm_topology import pulse_handoff

                        pulse_handoff(agent_name, nxt)
                    except Exception:
                        pass
                self.note_symbols(task, response_text)

                if agent_name == "Portfolio-Manager":
                    try:
                        data = json.loads(response_text)
                        rec = data.get("recommended_inst_id") or data.get("recommended_instId")
                        if rec:
                            self.set_candidate(str(rec))
                    except (json.JSONDecodeError, TypeError):
                        pass

                if agent_name == "Risk-Manager":
                    self.risk_approved = self._risk_approved(response_text)
                    logger.info(f"Risk approval for execution: {self.risk_approved}")

                results.append(
                    f"\nAgent: {agent_name}\n\nReasoning: {reasoning}\n\n"
                    f"Task: {task}\n\nResponse:\n{response_text}\n"
                )
                logger.info(f"Completed handoff to {agent_name}")
            except Exception as exc:
                err = f"Error executing handoff to {agent_name}: {exc}"
                logger.error(err)
                errors.append(err)

        if not results:
            body = "No handoffs executed."
            if errors:
                body += "\n" + "\n".join(errors)
            return body

        text = "=" * 80 + "\nHANDOFF RESULTS (sequential pipeline)\n" + "=" * 80 + "\n\n"
        text += "\n".join(results)
        if errors:
            text += "\n\n" + "=" * 80 + "\nERRORS\n" + "=" * 80 + "\n"
            text += "\n".join(f"- {e}" for e in errors)
        return text

    def advance_once(self, agent_registry: dict[str, Any]) -> str | None:
        if self.is_terminal():
            return None
        next_agent = self.next_agent()
        if not next_agent:
            self.terminal_skip = True
            return None
        expected = self._missing_prereq(next_agent)
        if expected:
            logger.warning(
                "Pipeline advance blocked: {} waiting on {}", next_agent, expected
            )
            return None
        if next_agent == "Risk-Manager":
            pass  # Full LLM Risk + Execution — analytical validation required

        handoff = {
            "agent_name": next_agent,
            "task": self._task_for(next_agent),
            "reasoning": "Auto pipeline advance to complete the cycle.",
        }
        return self.run([handoff], agent_registry)


_pipeline = HandoffPipeline()


def seed_pipeline_candidate(inst_id: str) -> None:
    """Set top pick before Director runs (skips universe discovery)."""
    if inst_id:
        _pipeline.set_candidate(inst_id.strip().upper())


def reset_handoff_pipeline() -> None:
    _pipeline.reset()


def ordered_handoff_task(
    handoffs: list[dict[str, str]],
    agent_registry: dict[str, Any] | None = None,
) -> str:
    return _pipeline.run(handoffs, agent_registry)


def pipeline_status() -> dict[str, Any]:
    return _pipeline.status()


def is_pipeline_terminal() -> bool:
    return _pipeline.is_terminal()


def advance_pipeline_once(agent_registry: dict[str, Any]) -> str | None:
    return _pipeline.advance_once(agent_registry)


def try_deterministic_completion() -> str | None:
    """Programmatic Risk→Execution when Quant is done (bypasses LLM stall)."""
    return try_deterministic_risk_execution(_pipeline)


def _clear_risk_execution_state() -> None:
    for agent in ("Risk-Manager", "Execution-Agent"):
        _pipeline.completed.discard(agent)
        _pipeline.agent_outputs.pop(agent, None)
    _pipeline.risk_approved = False
    _pipeline.risk_veto_reason = ""
    _pipeline.terminal_skip = False


def bootstrap_pipeline_for_deterministic(
    inst_id: str,
    *,
    suggested_side: str = "long",
    probability_score: float = 0.58,
) -> bool:
    """
    Mark PM→Sentiment→Quant complete so Risk/Execution can run without Director LLM.
    Used when pre-ranked candidate exists but Director stalls or API is throttled.
    """
    inst = normalize_usdt_inst_id(inst_id)
    if not inst:
        return False
    side = str(suggested_side or "long").lower()
    if side not in ("long", "short"):
        side = "long"
    prob = max(0.5, min(0.85, float(probability_score or 0.58)))
    if normalize_usdt_inst_id(_pipeline.candidate_inst_id or "") != inst:
        _clear_risk_execution_state()
    _pipeline.set_candidate(inst)
    stubs = {
        "Portfolio-Manager": json.dumps(
            {"recommended_inst_id": inst, "trade_allowed": True, "source": "fast_bootstrap"}
        ),
        "Sentiment-Agent": json.dumps(
            {
                "instId": inst,
                "overall_sentiment_score": 0.55,
                "sentiment": "bullish" if side == "long" else "bearish",
                "source": "fast_bootstrap",
            }
        ),
        "Quant-Analyst": json.dumps(
            {
                "instId": inst,
                "probability_score": prob,
                "suggested_side": side,
                "source": "fast_bootstrap",
            }
        ),
    }
    for agent, out in stubs.items():
        if agent not in _pipeline.completed:
            _pipeline.completed.add(agent)
            _pipeline.agent_outputs[agent] = out
    return True


def run_fast_pipeline_to_execution(
    inst_id: str,
    *,
    suggested_side: str = "long",
    probability_score: float = 0.58,
) -> dict[str, Any]:
    """Bootstrap + deterministic Risk→Execution. Returns pipeline status + detail."""
    from autohedge.risk_gate import _journal_has_order_for, _order_confirmed, maybe_clear_stale_risk_veto

    maybe_clear_stale_risk_veto(_pipeline)
    _clear_risk_execution_state()
    bootstrap_pipeline_for_deterministic(
        inst_id,
        suggested_side=suggested_side,
        probability_score=probability_score,
    )
    detail = try_deterministic_completion()
    st = _pipeline.status()
    persist_pipeline_state()
    cand = str(st.get("candidate_inst_id") or inst_id or "").strip().upper()
    exec_done = "Execution-Agent" in _pipeline.completed
    placed = False
    if exec_done:
        placed = _order_confirmed(str(_pipeline.agent_outputs.get("Execution-Agent") or ""))
    if not placed and cand:
        placed = _journal_has_order_for(cand, within_sec=180.0)
    ok = bool(exec_done and st.get("risk_approved") and placed)
    return {"ok": ok, "placed": placed, "detail": detail, "status": st}


def audit_pipeline_consistency() -> dict[str, Any]:
    """
    Deterministic handoff state-machine audit — catches Risk veto / Execution stuck UI,
    graph drift, and incomplete prereq chains. Used by pentest + stuck guard.
    """
    findings: list[dict[str, Any]] = []
    out = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
    pipe_path = out / "pipeline_state.json"
    graph_path = out / "graph_live.json"

    ps: dict[str, Any] = {}
    if pipe_path.is_file():
        try:
            ps = json.loads(pipe_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            findings.append(
                {
                    "id": "pipeline_state_unreadable",
                    "severity": "high",
                    "mission": "pipeline_handoff",
                    "detail": "pipeline_state.json unreadable",
                }
            )
    else:
        return {"findings": findings, "pipeline": ps, "graph": {}, "ts": time.time()}

    gl: dict[str, Any] = {}
    if graph_path.is_file():
        try:
            gl = json.loads(graph_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    completed = set(ps.get("completed") or [])
    next_agent = ps.get("next_agent")
    terminal = bool(ps.get("terminal"))
    risk_approved = bool(ps.get("risk_approved"))
    cand = str(ps.get("candidate_inst_id") or "").strip().upper()

    risk_veto = "Risk-Manager" in completed and not risk_approved
    if risk_veto and next_agent == "Execution-Agent":
        findings.append(
            {
                "id": "pipeline_veto_execution_stuck",
                "severity": "critical",
                "mission": "pipeline_handoff",
                "detail": (
                    f"Risk veto on {cand or '?'} but next_agent=Execution-Agent — "
                    "dashboard shows Execution active forever"
                ),
                "candidate": cand,
                "root_cause_hint": "terminal veto must clear next_agent; dashboard must treat veto as done",
                "evidence": {"terminal": terminal, "completed": list(completed), "next_agent": next_agent},
            }
        )
    elif risk_veto and terminal and next_agent:
        findings.append(
            {
                "id": "pipeline_veto_execution_stuck",
                "severity": "critical",
                "mission": "pipeline_handoff",
                "detail": f"Terminal Risk veto but next_agent={next_agent!r} still set",
                "candidate": cand,
                "evidence": {"terminal": terminal, "next_agent": next_agent},
            }
        )

    if terminal and next_agent and next_agent not in completed and not risk_veto:
        findings.append(
            {
                "id": "pipeline_terminal_next_mismatch",
                "severity": "high",
                "mission": "pipeline_handoff",
                "detail": f"terminal=true but next_agent={next_agent!r} not in completed",
                "candidate": cand,
            }
        )

    if (
        "Risk-Manager" in completed
        and "Execution-Agent" not in completed
        and risk_approved
        and not terminal
    ):
        log_path = out / "owl-llm.log"
        log_age = 9999.0
        if log_path.is_file():
            try:
                log_age = time.time() - log_path.stat().st_mtime
            except OSError:
                pass
        if log_age > 180:
            findings.append(
                {
                    "id": "pipeline_execution_stall",
                    "severity": "critical",
                    "mission": "pipeline_handoff",
                    "detail": (
                        f"Risk approved {cand or '?'} but Execution never ran "
                        f"(log silent {round(log_age, 0)}s)"
                    ),
                    "candidate": cand,
                    "root_cause_hint": "run_fast_pipeline_to_execution or Director timeout fallback",
                    "log_age_sec": round(log_age, 1),
                }
            )
        else:
            findings.append(
                {
                    "id": "pipeline_execution_pending",
                    "severity": "medium",
                    "mission": "pipeline_handoff",
                    "detail": f"Risk approved — awaiting Execution for {cand or '?'}",
                    "candidate": cand,
                }
            )

    for i, agent in enumerate(PIPELINE_ORDER):
        if agent not in completed:
            continue
        for prereq in PIPELINE_ORDER[:i]:
            if prereq not in completed:
                findings.append(
                    {
                        "id": "pipeline_prereq_violation",
                        "severity": "high",
                        "mission": "pipeline_handoff",
                        "detail": f"{agent} marked complete but prereq {prereq} missing",
                        "candidate": cand,
                    }
                )
                break

    gl_completed = set(gl.get("completed") or [])
    gl_next = str(gl.get("pipeline_next") or gl.get("active_agent") or "")
    if gl_completed and gl_completed != completed:
        findings.append(
            {
                "id": "pipeline_graph_drift",
                "severity": "medium",
                "mission": "pipeline_handoff",
                "detail": "graph_live.completed disagrees with pipeline_state.json",
                "evidence": {"graph": list(gl_completed), "pipeline": list(completed)},
            }
        )
    if gl_next == "Execution-Agent" and risk_veto:
        findings.append(
            {
                "id": "pipeline_dashboard_stuck",
                "severity": "critical",
                "mission": "pipeline_handoff",
                "detail": "graph_live still points Execution active after Risk veto",
                "candidate": cand,
            }
        )

    try:
        from autohedge.risk_gate import audit_risk_veto_righteous

        veto_audit = audit_risk_veto_righteous(pipeline_state=ps)
        report["risk_veto_audit"] = veto_audit
        if veto_audit.get("righteous") is False:
            findings.append(
                {
                    "id": "risk_veto_stale",
                    "severity": "high",
                    "mission": "pipeline_handoff",
                    "detail": (
                        f"Risk veto no longer valid: {veto_audit.get('verdict')} "
                        f"({veto_audit.get('reason', '')[:120]})"
                    ),
                    "candidate": cand,
                    "evidence": veto_audit,
                }
            )
    except Exception as exc:
        report["risk_veto_audit_error"] = str(exc)

    return {
        "findings": findings,
        "pipeline": ps,
        "graph": gl,
        "candidate": cand,
        "completed": list(completed),
        "ts": time.time(),
    }


def repair_pipeline_disk() -> dict[str, Any]:
    """Fix veto terminal state where Execution looked stuck (next_agent set but terminal)."""
    out = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
    path = out / "pipeline_state.json"
    if not path.is_file():
        return {"ok": True, "action": "no_file"}
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"ok": False, "error": "parse_fail"}
    fixed = False
    completed = set(st.get("completed") or [])
    if st.get("terminal"):
        if "Risk-Manager" in completed and not st.get("risk_approved"):
            if st.get("next_agent"):
                st["next_agent"] = ""
                fixed = True
        elif "Execution-Agent" in completed and st.get("next_agent"):
            st["next_agent"] = ""
            fixed = True
    elif st.get("next_agent") == "Execution-Agent" and "Risk-Manager" in completed:
        if not st.get("risk_approved"):
            st["terminal"] = True
            st["next_agent"] = ""
            fixed = True
    if fixed:
        path.write_text(json.dumps(st, indent=2), encoding="utf-8")
        # Sync in-memory pipeline for same process
        _pipeline.reset()
        _pipeline.candidate_inst_id = str(st.get("candidate_inst_id") or "")
        _pipeline.risk_approved = bool(st.get("risk_approved"))
        for agent in completed:
            _pipeline.completed.add(agent)
        persist_pipeline_state()
    return {"ok": True, "fixed": fixed, "status": st}


def restore_pipeline_from_disk() -> bool:
    """Resume in-memory pipeline from pipeline_state.json after crash (incomplete cycles only)."""
    out = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
    path = out / "pipeline_state.json"
    if not path.is_file():
        return False
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not st.get("candidate_inst_id"):
        return False
    if st.get("terminal"):
        return False
    completed = set(st.get("completed") or [])
    if "Execution-Agent" in completed:
        return False
    age = 9999.0
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        pass
    if age > 1800:
        return False
    _pipeline.reset()
    _pipeline.candidate_inst_id = str(st.get("candidate_inst_id") or "")
    _pipeline.risk_approved = bool(st.get("risk_approved"))
    for agent in completed:
        if agent in PIPELINE_ORDER:
            _pipeline.completed.add(agent)
    persist_pipeline_state()
    return True


def persist_pipeline_state() -> None:
    """Disk mirror for dashboard + stuck guard."""
    try:
        out = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
        out.mkdir(parents=True, exist_ok=True)
        st = _pipeline.status()
        (out / "pipeline_state.json").write_text(json.dumps(st, indent=2), encoding="utf-8")
        completed = set(st.get("completed") or [])
        next_agent = str(st.get("next_agent") or "")
        try:
            from autohedge.swarm_topology import pulse_handoff, set_agent_status

            risk_veto = "Risk-Manager" in completed and not st.get("risk_approved")
            prev = None
            for agent in PIPELINE_ORDER:
                if agent in completed:
                    if agent == "Risk-Manager" and risk_veto:
                        set_agent_status(agent, "fail", detail="veto")
                    else:
                        set_agent_status(agent, "pass")
                    if prev:
                        pulse_handoff(prev, agent)
                    prev = agent
                elif risk_veto and agent == "Execution-Agent":
                    set_agent_status(agent, "skipped", detail="risk veto")
                elif agent == next_agent and not st.get("terminal"):
                    set_agent_status(agent, "active", detail="pipeline handoff")
                else:
                    set_agent_status(agent, "idle")
        except Exception:
            pass
        graph_live = out / "graph_live.json"
        gl: dict[str, Any] = {}
        if graph_live.is_file():
            try:
                gl = json.loads(graph_live.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                gl = {}
        gl.update(
            {
                "pipeline_next": next_agent or ("done" if st.get("terminal") else ""),
                "completed": list(completed),
                "pipeline": st,
                "updated_at": time.time(),
            }
        )
        if st.get("terminal"):
            gl["active_agent"] = ""
        elif next_agent:
            gl["active_agent"] = next_agent
        graph_live.write_text(json.dumps(gl, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass


def continuation_prompt() -> str:
    st = _pipeline.status()
    nxt = st.get("next_agent") or "none"
    cand = st.get("candidate_inst_id") or "unset — pick one from rank_opportunities"
    completed = ", ".join(st.get("completed") or []) or "none"
    return (
        "PIPELINE INCOMPLETE — continue this cycle only.\n"
        f"Locked candidate: {cand}\n"
        f"Completed agents: {completed}\n"
        f"REQUIRED NEXT (one handoff_task only): {nxt}\n"
        "SELF-VERIFYING LOOP: if prior agent failed cross-check, re-handoff with corrected "
        "live Blofin tool data — do not proceed with bad numbers.\n"
        "Do NOT re-handoff any completed agent. "
        "If Risk already approved, hand off to Execution-Agent with blofin_execute_minimum_trade."
    )
