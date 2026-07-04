"""
Universe diligence — every top-ranked asset gets real analytical validation
before Director locks a candidate. No stubs, no fast-bootstrap shortcuts.

Tier 1: Full-universe programmatic rank (owl pre-rank).
Tier 2: Deterministic TA + funding screen on top N (live tools).
Tier 3: LLM deep-dive (Market Research, Quant, Sentiment) on top K passers.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from autohedge.tools.tool_utils import normalize_usdt_inst_id


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class CandidateScreen:
    inst_id: str
    rank_score: float
    chg_pct_24h: float
    suggested_side: str
    probability_score: float
    technical_score: float
    volatility_pct: float
    veto: bool
    veto_reason: str = ""
    journal_wins: int = 0
    journal_losses: int = 0
    source: str = "analytic_screen"


@dataclass
class CandidateLLMDossier:
    inst_id: str
    market_research: dict[str, Any] = field(default_factory=dict)
    quant: dict[str, Any] = field(default_factory=dict)
    sentiment: dict[str, Any] = field(default_factory=dict)
    composite_score: float = 0.0
    veto: bool = False
    veto_reason: str = ""


@dataclass
class DiligenceReport:
    universe_ranked: int
    screened: list[CandidateScreen] = field(default_factory=list)
    llm_dossiers: list[CandidateLLMDossier] = field(default_factory=list)
    shortlist: list[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe_ranked": self.universe_ranked,
            "screened_count": len(self.screened),
            "llm_count": len(self.llm_dossiers),
            "shortlist": self.shortlist,
            "ts": self.ts,
            "screened": [s.__dict__ for s in self.screened],
            "llm_dossiers": [
                {
                    "inst_id": d.inst_id,
                    "composite_score": d.composite_score,
                    "veto": d.veto,
                    "veto_reason": d.veto_reason,
                    "market_ok": d.market_research.get("ok"),
                    "quant_ok": d.quant.get("ok"),
                    "sentiment_ok": d.sentiment.get("ok"),
                }
                for d in self.llm_dossiers
            ],
        }


def _min_probability() -> float:
    return _env_float("OWL_MIN_PROBABILITY", 0.45)


def screen_candidate(row: dict[str, Any]) -> CandidateScreen:
    """Deterministic TA validation — real blofin_technical_analysis, not stubs."""
    from autohedge.tools.blofin_tools import blofin_get_funding_rate, blofin_technical_analysis

    inst = normalize_usdt_inst_id(str(row.get("instId") or ""))
    rank_side = str(row.get("suggested_side") or "long").lower()
    rank_score = max(float(row.get("long_score") or 0), float(row.get("short_score") or 0))
    chg = float(row.get("chg_pct_24h") or 0)
    wins = int(row.get("journal_wins") or 0)
    losses = int(row.get("journal_losses") or 0)

    veto = False
    reason = ""
    tech_score = 0.0
    prob = 0.0
    vol = 0.0
    side = rank_side

    if not inst:
        return CandidateScreen(
            inst_id="",
            rank_score=0,
            chg_pct_24h=0,
            suggested_side="neutral",
            probability_score=0,
            technical_score=0,
            volatility_pct=0,
            veto=True,
            veto_reason="invalid_inst",
        )

    try:
        tech = json.loads(blofin_technical_analysis(inst_id=inst))
    except Exception as exc:
        return CandidateScreen(
            inst_id=inst,
            rank_score=rank_score,
            chg_pct_24h=chg,
            suggested_side=rank_side,
            probability_score=0,
            technical_score=0,
            volatility_pct=0,
            veto=True,
            veto_reason=f"technical_analysis_error:{exc}",
            journal_wins=wins,
            journal_losses=losses,
        )

    if tech.get("error"):
        return CandidateScreen(
            inst_id=inst,
            rank_score=rank_score,
            chg_pct_24h=chg,
            suggested_side=rank_side,
            probability_score=0,
            technical_score=0,
            volatility_pct=0,
            veto=True,
            veto_reason=str(tech.get("error")),
            journal_wins=wins,
            journal_losses=losses,
        )

    bias = str(tech.get("suggested_bias") or "neutral").lower()
    long_s = float(tech.get("technical_score") or 0)
    short_s = float(tech.get("short_score") or 0)
    tech_score = long_s if bias == "long" else short_s if bias == "short" else max(long_s, short_s)
    prob = tech_score
    vol = float(tech.get("volatility_pct") or 0)
    side = bias if bias in ("long", "short") else rank_side

    if prob < _min_probability():
        veto = True
        reason = f"probability_{prob:.3f}_below_min"
    elif vol < 0.15 and abs(chg) < 1.0:
        veto = True
        reason = "flat_chop_low_volatility"
    elif losses >= 3 and wins == 0:
        veto = True
        reason = "journal_repeat_loser"

    try:
        funding = json.loads(blofin_get_funding_rate(inst_id=inst))
        rate = float(funding.get("funding_rate") or funding.get("fundingRate") or 0)
        if side == "long" and rate > 0.0005:
            prob *= 0.92
        elif side == "short" and rate < -0.0005:
            prob *= 0.92
    except Exception:
        pass

    return CandidateScreen(
        inst_id=inst,
        rank_score=rank_score,
        chg_pct_24h=chg,
        suggested_side=side,
        probability_score=round(prob, 4),
        technical_score=round(tech_score, 4),
        volatility_pct=round(vol, 4),
        veto=veto,
        veto_reason=reason,
        journal_wins=wins,
        journal_losses=losses,
    )


def screen_top_candidates(opps: list[dict[str, Any]], *, top_n: int | None = None) -> list[CandidateScreen]:
    n = top_n or _env_int("OWL_DILIGENCE_SCREEN_N", 20)
    screened: list[CandidateScreen] = []
    pause = _env_float("OWL_DILIGENCE_API_PAUSE_SEC", 0.35)
    for row in opps[:n]:
        screened.append(screen_candidate(row))
        if pause > 0:
            time.sleep(pause)
    screened.sort(
        key=lambda s: (s.veto, -s.probability_score, -s.rank_score),
    )
    return screened


def run_llm_dossier(inst_id: str) -> CandidateLLMDossier:
    """Full LLM diligence on one symbol — Market Research, Quant, Sentiment."""
    from autohedge.support_agents import (
        run_market_researcher,
        run_quant_diligence,
        run_sentiment_diligence,
    )

    inst = normalize_usdt_inst_id(inst_id)
    dossier = CandidateLLMDossier(inst_id=inst)
    if not inst:
        dossier.veto = True
        dossier.veto_reason = "invalid_inst"
        return dossier

    dossier.market_research = run_market_researcher(inst)
    dossier.quant = run_quant_diligence(inst)
    dossier.sentiment = run_sentiment_diligence(inst)

    scores: list[float] = []
    vetoes: list[str] = []

    for label, block in (
        ("market", dossier.market_research),
        ("quant", dossier.quant),
        ("sentiment", dossier.sentiment),
    ):
        if block.get("skipped"):
            continue
        if not block.get("ok"):
            vetoes.append(f"{label}_llm_fail")
            continue
        parsed = block.get("parsed") or {}
        if parsed.get("veto") is True:
            vetoes.append(f"{label}_veto")
        conf = float(parsed.get("confidence") or parsed.get("probability_score") or 0)
        prob = float(parsed.get("probability_score") or parsed.get("technical_score") or conf or 0)
        if prob > 0:
            scores.append(prob)
        elif conf > 0:
            scores.append(conf)

    dossier.composite_score = round(sum(scores) / len(scores), 4) if scores else 0.0
    if vetoes:
        dossier.veto = True
        dossier.veto_reason = ";".join(vetoes)
    elif dossier.composite_score < _min_probability():
        dossier.veto = True
        dossier.veto_reason = f"llm_composite_{dossier.composite_score}_below_min"

    return dossier


def run_universe_diligence(opps: list[dict[str, Any]]) -> DiligenceReport:
    """Full diligence pass — screen top N, LLM deep-dive top K passers."""
    report = DiligenceReport(universe_ranked=len(opps))
    report.screened = screen_top_candidates(opps)

    llm_n = _env_int("OWL_DILIGENCE_LLM_N", 5)
    passers = [s for s in report.screened if not s.veto and s.inst_id]
    for screen in passers[:llm_n]:
        try:
            dossier = run_llm_dossier(screen.inst_id)
            report.llm_dossiers.append(dossier)
        except Exception as exc:
            logger.warning("LLM dossier failed for {}: {}", screen.inst_id, exc)
            report.llm_dossiers.append(
                CandidateLLMDossier(
                    inst_id=screen.inst_id,
                    veto=True,
                    veto_reason=str(exc),
                )
            )

    shortlist: list[str] = []
    dossier_by_inst = {d.inst_id: d for d in report.llm_dossiers if d.inst_id}
    for d in report.llm_dossiers:
        if not d.veto and d.inst_id:
            shortlist.append(d.inst_id)
    if not shortlist:
        for s in passers:
            if s.inst_id and s.inst_id not in shortlist:
                shortlist.append(s.inst_id)
            if len(shortlist) >= _env_int("OWL_PIPELINE_CANDIDATE_ATTEMPTS", 3):
                break

    report.shortlist = shortlist[: _env_int("OWL_PIPELINE_CANDIDATE_ATTEMPTS", 3)]
    return report


def persist_diligence_report(report: DiligenceReport) -> None:
    try:
        from pathlib import Path

        out = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
        out.mkdir(parents=True, exist_ok=True)
        (out / "diligence_report.json").write_text(
            json.dumps(report.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not persist diligence report: {}", exc)


def build_diligence_block(report: DiligenceReport) -> str:
    lines = [
        "",
        "═" * 60,
        "UNIVERSE DILIGENCE (mandatory — trades ONLY from this validated shortlist)",
        f"Ranked universe: {report.universe_ranked} | Screened: {len(report.screened)} | "
        f"LLM dossiers: {len(report.llm_dossiers)}",
        f"VALIDATED SHORTLIST (pick ONE, then run full pipeline): {', '.join(report.shortlist) or 'NONE'}",
        "",
        "Analytic screen (top passers):",
    ]
    for s in report.screened:
        if s.veto:
            continue
        flag = "✓" if s.inst_id in report.shortlist else "·"
        lines.append(
            f"  {flag} {s.inst_id} side={s.suggested_side} prob={s.probability_score} "
            f"tech={s.technical_score} chg24h={s.chg_pct_24h}% "
            f"journal={s.journal_wins}W/{s.journal_losses}L"
        )
        if len([ln for ln in lines if ln.startswith("  ")]) >= 12:
            break

    if report.llm_dossiers:
        lines.append("")
        lines.append("LLM dossier summary:")
        for d in report.llm_dossiers:
            st = "VETO" if d.veto else "PASS"
            lines.append(
                f"  [{st}] {d.inst_id} composite={d.composite_score} "
                f"mr={'ok' if d.market_research.get('ok') else 'fail'} "
                f"quant={'ok' if d.quant.get('ok') else 'fail'} "
                f"sent={'ok' if d.sentiment.get('ok') else 'fail'}"
            )
            if d.veto_reason:
                lines.append(f"      reason: {d.veto_reason[:120]}")

    lines.append("")
    lines.append(
        "RULES: No trade without Quant + Sentiment + Risk LLM verification. "
        "If shortlist empty, skip cycle — idle margin is an ERROR."
    )
    lines.append("═" * 60)
    return "\n".join(lines)


def parse_agent_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
