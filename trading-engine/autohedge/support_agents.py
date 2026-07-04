"""Support LLM agents — ops, verify, research, profit (not in trading handoff chain)."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from loguru import logger


def run_ops_monitor() -> dict[str, Any]:
    from autohedge.workers import ops_monitor_agent
    from autohedge.swarm_autopilot import preflight_repair

    try:
        from autohedge.swarm_tasks import finish_task, start_task
        from autohedge.swarm_topology import set_agent_status

        start_task("ops_health", "Ops-Monitor-Agent", "audit")
        set_agent_status("Ops-Monitor-Agent", "active")
    except Exception:
        pass
    task = (
        "Run a full operational health check of the OWL swarm stack. "
        "Use blofin_get_stack_health and blofin_get_swarm_learning_report. "
        "Output strict JSON with status, issues, repair_actions, confidence, narrative."
    )
    try:
        raw = str(ops_monitor_agent.run(task=task))
        pf = preflight_repair()
        try:
            from autohedge.swarm_tasks import finish_task
            from autohedge.swarm_topology import set_agent_status

            finish_task("ops_health", "Ops-Monitor-Agent", "audit", status="done")
            set_agent_status("Ops-Monitor-Agent", "pass")
        except Exception:
            pass
        return {"llm_output": raw[:3000], "autopilot_repairs": pf.get("repairs", []), "ok": True}
    except Exception as exc:
        logger.warning("Ops monitor LLM failed: {}", exc)
        pf = preflight_repair()
        return {"error": str(exc), "autopilot_repairs": pf.get("repairs", []), "ok": False}


def run_tactics_researcher(query: str = "") -> dict[str, Any]:
    from autohedge.workers import tactics_researcher_agent

    try:
        from autohedge.swarm_tasks import finish_task, start_task
        from autohedge.swarm_topology import set_agent_status

        start_task("tactics_research", "Tactics-Researcher-Agent", "execute")
        set_agent_status("Tactics-Researcher-Agent", "active")
    except Exception:
        pass
    q = query or "asymmetric risk reward momentum perpetual futures small account"
    task = (
        f"Research trading tactics for: {q}. "
        "Use blofin_research_trading_tactics and blofin_get_trade_insights. "
        "Output JSON with tactics_learned, queries_used, apply_next_cycle."
    )
    try:
        raw = str(tactics_researcher_agent.run(task=task))
        try:
            from autohedge.swarm_tasks import finish_task
            from autohedge.swarm_topology import set_agent_status

            finish_task("tactics_research", "Tactics-Researcher-Agent", "execute", status="done")
            set_agent_status("Tactics-Researcher-Agent", "pass")
        except Exception:
            pass
        return {"llm_output": raw[:4000], "query": q, "ok": True}
    except Exception as exc:
        logger.warning("Tactics researcher LLM failed: {}", exc)
        from autohedge.tactics_learner import research_tactics_online

        fallback = research_tactics_online(q)
        return {"error": str(exc), "script_fallback": fallback, "ok": False}


def run_profit_strategist() -> dict[str, Any]:
    from autohedge.workers import profit_strategist_agent

    try:
        from autohedge.swarm_tasks import finish_task, start_task
        from autohedge.swarm_topology import set_agent_status

        start_task("profit_optimization", "Profit-Strategist-Agent", "optimize")
        set_agent_status("Profit-Strategist-Agent", "active")
    except Exception:
        pass
    task = (
        "Review our trading performance and propose profit-maximizing changes. "
        "Use blofin_get_trade_insights, blofin_get_learned_tactics, blofin_get_equity_summary. "
        "Output JSON: recommendations, already_implemented, rejected (with reasons)."
    )
    try:
        raw = str(profit_strategist_agent.run(task=task))
        _apply_profit_recommendations(raw)
        try:
            from autohedge.swarm_tasks import finish_task
            from autohedge.swarm_topology import set_agent_status

            finish_task("profit_optimization", "Profit-Strategist-Agent", "optimize", status="done")
            set_agent_status("Profit-Strategist-Agent", "pass")
        except Exception:
            pass
        return {"llm_output": raw[:4000], "ok": True}
    except Exception as exc:
        logger.warning("Profit strategist LLM failed: {}", exc)
        return {"error": str(exc), "ok": False}


def run_market_researcher(inst_id: str) -> dict[str, Any]:
    from autohedge.workers import market_researcher_agent
    from autohedge.candidate_diligence import parse_agent_json

    if not inst_id:
        try:
            from autohedge.swarm_tasks import skip_task

            skip_task("market_research", "no top pick")
        except Exception:
            pass
        return {"skipped": True}
    try:
        from autohedge.swarm_tasks import start_task
        from autohedge.swarm_topology import set_agent_status

        start_task("market_research", "Market-Researcher-Agent", "execute", detail=inst_id)
        set_agent_status("Market-Researcher-Agent", "active")
    except Exception:
        pass
    task = (
        f"Deep-dive market research on {inst_id}. "
        "Use all analysis tools. Output JSON with suggested_side, move_potential_pct, "
        "confidence, veto, thesis. Focus on asymmetric upside."
    )
    try:
        raw = str(market_researcher_agent.run(task=task))
        try:
            from autohedge.swarm_tasks import finish_task
            from autohedge.swarm_topology import set_agent_status

            finish_task("market_research", "Market-Researcher-Agent", "execute", status="done")
            set_agent_status("Market-Researcher-Agent", "pass")
        except Exception:
            pass
        return {"instId": inst_id, "llm_output": raw[:4000], "parsed": parse_agent_json(raw), "ok": True}
    except Exception as exc:
        logger.warning("Market researcher LLM failed for {}: {}", inst_id, exc)
        return {"instId": inst_id, "error": str(exc), "ok": False}


def run_quant_diligence(inst_id: str) -> dict[str, Any]:
    """Quant deep-dive on one symbol — required before any trade."""
    from autohedge.workers import quant_agent
    from autohedge.candidate_diligence import parse_agent_json

    inst = (inst_id or "").strip().upper()
    if not inst:
        return {"skipped": True, "ok": False}
    try:
        from autohedge.swarm_tasks import finish_task, start_task
        from autohedge.swarm_topology import set_agent_status

        start_task("quant", "Quant-Analyst", "execute", detail=f"diligence:{inst}")
        set_agent_status("Quant-Analyst", "active", detail="universe diligence")
    except Exception:
        pass
    task = (
        f"QUANT DILIGENCE on {inst} — this trade will NOT execute without your validated analysis.\n"
        "Use blofin_technical_analysis, blofin_get_candles, blofin_get_funding_rate, blofin_get_order_book.\n"
        "Output JSON: instId, probability_score, technical_score, suggested_side, suggested_tp_pct, "
        "suggested_sl_pct, key_levels, confidence, veto (true if chop or R:R < 3:1)."
    )
    try:
        raw = str(quant_agent.run(task=task))
        try:
            from autohedge.swarm_tasks import finish_task
            from autohedge.swarm_topology import set_agent_status

            finish_task("quant", "Quant-Analyst", "execute", status="done")
            set_agent_status("Quant-Analyst", "pass")
        except Exception:
            pass
        parsed = parse_agent_json(raw)
        veto = bool(parsed.get("veto"))
        prob = float(parsed.get("probability_score") or parsed.get("technical_score") or 0)
        ok = prob >= float(os.environ.get("OWL_MIN_PROBABILITY", "0.45")) and not veto
        return {
            "instId": inst,
            "llm_output": raw[:4000],
            "parsed": parsed,
            "ok": ok,
            "veto": veto,
        }
    except Exception as exc:
        logger.warning("Quant diligence failed for {}: {}", inst, exc)
        return {"instId": inst, "error": str(exc), "ok": False}


def run_sentiment_diligence(inst_id: str) -> dict[str, Any]:
    """Sentiment deep-dive on one symbol."""
    from autohedge.workers import sentiment_agent
    from autohedge.candidate_diligence import parse_agent_json

    inst = (inst_id or "").strip().upper()
    if not inst:
        return {"skipped": True, "ok": False}
    try:
        from autohedge.swarm_tasks import finish_task, start_task
        from autohedge.swarm_topology import set_agent_status

        start_task("sentiment", "Sentiment-Agent", "execute", detail=f"diligence:{inst}")
        set_agent_status("Sentiment-Agent", "active", detail="universe diligence")
    except Exception:
        pass
    task = (
        f"SENTIMENT DILIGENCE on {inst}.\n"
        "Use crypto_news_search, blofin_get_funding_rate, blofin_get_ticker.\n"
        "Output JSON: instId, overall_sentiment_score, move_potential, funding_crowding_bias, "
        "confidence, veto (true if no catalyst / flat chop)."
    )
    try:
        raw = str(sentiment_agent.run(task=task))
        try:
            from autohedge.swarm_tasks import finish_task
            from autohedge.swarm_topology import set_agent_status

            finish_task("sentiment", "Sentiment-Agent", "execute", status="done")
            set_agent_status("Sentiment-Agent", "pass")
        except Exception:
            pass
        parsed = parse_agent_json(raw)
        veto = bool(parsed.get("veto"))
        score = float(parsed.get("overall_sentiment_score") or parsed.get("confidence") or 0)
        ok = score >= 0.4 and not veto
        return {
            "instId": inst,
            "llm_output": raw[:4000],
            "parsed": parsed,
            "ok": ok,
            "veto": veto,
        }
    except Exception as exc:
        logger.warning("Sentiment diligence failed for {}: {}", inst, exc)
        return {"instId": inst, "error": str(exc), "ok": False}


def run_llm_verifier(agent_name: str, agent_output: str, crosscheck: dict[str, Any]) -> dict[str, Any]:
    from autohedge.workers import verifier_agent

    task = (
        f"Verify output from agent '{agent_name}'.\n"
        f"Deterministic cross-check result: {json.dumps(crosscheck, default=str)[:1500]}\n"
        f"Agent output excerpt:\n{agent_output[:2500]}\n"
        "Use live Blofin tools to confirm or reject. Output JSON: status, discrepancies, required_fixes, retryable."
    )
    try:
        raw = str(verifier_agent.run(task=task))
        passed = "pass" in raw.lower() and "fail" not in raw.lower()[:80]
        return {"llm_output": raw[:3000], "passed": passed, "ok": True}
    except Exception as exc:
        logger.warning("Verifier LLM failed: {}", exc)
        return {"error": str(exc), "passed": crosscheck.get("ok", False), "ok": False}


def run_pre_cycle_support(
    *,
    cycle: int,
    top_pick: str = "",
    shortlist: list[str] | None = None,
    skip_ops_monitor: bool = False,
    fast_path: bool = False,
) -> dict[str, Any]:
    """All non-trading LLM agents that run before each trading cycle (parallel with pipeline)."""
    report: dict[str, Any] = {"cycle": cycle, "ts": time.time()}
    if skip_ops_monitor:
        report["ops_monitor"] = {"ok": True, "skipped": "background_ops"}
    else:
        report["ops_monitor"] = run_ops_monitor()

    targets = [s for s in (shortlist or []) if s]
    if not targets and top_pick:
        targets = [top_pick]

    diligence_n = int(os.environ.get("OWL_DILIGENCE_LLM_N", "3"))
    report["diligence_targets"] = targets
    report["market_research"] = []
    if targets:
        primary = targets[0]
        report["market_research_primary"] = run_market_researcher(primary)
        report["market_research"].append(report["market_research_primary"])
        for inst in targets[1:diligence_n]:
            if inst != primary:
                report["market_research"].append(run_market_researcher(inst))
    else:
        try:
            from autohedge.swarm_tasks import skip_task

            skip_task("market_research", "no candidates this cycle")
        except Exception:
            pass
        report["market_research_primary"] = {"ok": True, "skipped": "no_top_pick"}

    if cycle % 2 == 1:
        report["tactics_research"] = run_tactics_researcher()
    else:
        try:
            from autohedge.swarm_tasks import skip_task

            skip_task("tactics_research", "runs odd cycles only")
        except Exception:
            pass

    if cycle % 2 == 0:
        report["profit_strategist"] = run_profit_strategist()
    else:
        try:
            from autohedge.swarm_tasks import skip_task

            skip_task("profit_optimization", "runs even cycles only")
        except Exception:
            pass

    if fast_path:
        report["fast_path"] = True
    try:
        from autohedge.swarm_learning_audit import record_learned

        record_learned(
            title=f"Pre-cycle support agents cycle {cycle}",
            detail=f"ops={'ok' if report['ops_monitor'].get('ok') else 'fail'} "
            f"research={bool(top_pick)} tactics={cycle % 2 == 1}",
            source="support_agents",
            proof={"agents": list(report.keys())},
        )
    except Exception:
        pass
    return report


def _apply_profit_recommendations(raw: str) -> None:
    """Apply safe env tunings the profit strategist recommends."""
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return

    allowed = {
        "OWL_TP_PCT": (0.03, 0.15),
        "OWL_SL_PCT": (0.008, 0.02),
        "OWL_MIN_RR": (3.0, 8.0),
        "OWL_PRERANK_TOP_N": (12, 30),
        "OWL_DEPLOY_MAX_CANDIDATES": (30, 80),
        "OWL_TRADE_CANDIDATE_MAX": (30, 80),
    }
    applied: list[str] = []
    for rec in data.get("recommendations") or []:
        if not rec.get("implement"):
            continue
        change = str(rec.get("change") or "")
        for key, (lo, hi) in allowed.items():
            if key in change:
                import re

                m = re.search(r"([0-9.]+)", change)
                if m:
                    val = float(m.group(1))
                    if key.endswith("_N"):
                        os.environ[key] = str(int(max(lo, min(hi, val))))
                    else:
                        os.environ[key] = str(max(lo, min(hi, val)))
                    applied.append(key)
                    try:
                        from autohedge.swarm_learning_audit import record_improvement

                        record_improvement(
                            title=f"Profit strategist applied {key}",
                            detail=str(rec.get("reason") or ""),
                            metric=key,
                            before="default",
                            after=os.environ[key],
                            proof={"recommendation": rec},
                        )
                    except Exception:
                        pass
    if applied:
        try:
            from autohedge.swarm_restart import request_restart

            request_restart(
                reason=f"Profit strategist tuned env: {', '.join(applied)}",
                source="profit_strategist",
                component="env_tuning",
                proof={"keys": applied},
            )
        except Exception:
            pass
