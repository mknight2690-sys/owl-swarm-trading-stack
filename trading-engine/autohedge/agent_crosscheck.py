"""Cross-agent verification — each agent output checked against live Blofin data."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from loguru import logger

_INST_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,20}-USDT)\b")
_PRICE_RE = re.compile(
    r"(?:stop|sl|take.?profit|tp)[_ ]?(?:price|trigger)?[\"']?\s*[:=]\s*[\"']?([0-9.]+)",
    re.I,
)
_APPROVED_RE = re.compile(r"approved[\"']?\s*[:=]\s*(true|false)", re.I)
_SCORE_RE = re.compile(r"probability_score[\"']?\s*[:=]\s*([0-9.]+)", re.I)
_MIN_RR = float(os.environ.get("OWL_MIN_RR", "3.0"))


def _parse_json_blob(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _extract_prices(text: str) -> tuple[float | None, float | None]:
    sl = tp = None
    for label, var in (("sl", "sl"), ("stop", "sl"), ("tp", "tp"), ("take_profit", "tp")):
        m = re.search(rf'{label}[_ ]?(?:price|trigger)?["\']?\s*[:=]\s*["\']?([0-9.]+)', text, re.I)
        if m:
            val = float(m.group(1))
            if var == "sl":
                sl = val
            else:
                tp = val
    return sl, tp


def crosscheck_agent_output(
    agent_name: str,
    response: str,
    *,
    candidate_inst: str = "",
    pipeline_outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Verify an agent's claims against live exchange data and peer consistency."""
    issues: list[str] = []
    warnings: list[str] = []
    fixes: list[str] = []
    inst = candidate_inst.strip().upper()
    text = response or ""
    data = _parse_json_blob(text)

    if not inst:
        for sym in _INST_RE.findall(text):
            if sym.endswith("-USDT"):
                inst = sym
                break

    if agent_name == "Portfolio-Manager":
        try:
            from autohedge.tools.blofin_tools import blofin_assess_portfolio

            pf = json.loads(blofin_assess_portfolio())
            blocked = set(pf.get("blocked_inst_ids_for_new_buy") or []) | set(
                pf.get("blocked_inst_ids_for_new_sell") or []
            )
            rec = ""
            if data:
                rec = str(data.get("recommended_inst_id") or data.get("recommended_instId") or "")
            if rec and rec.upper() in blocked:
                issues.append(f"Portfolio recommended blocked symbol {rec}")
            trade_allowed = data.get("trade_allowed") if data else None
            if trade_allowed is False and not blocked:
                warnings.append("Portfolio vetoed trade_allowed=false — verify margin is truly insufficient")
        except Exception as exc:
            warnings.append(f"Portfolio cross-check skipped: {exc}")

    elif agent_name == "Sentiment-Agent" and inst:
        try:
            from autohedge.tools.blofin_client import BlofinClient

            live = BlofinClient().get_funding_rate(inst)
            live_rate = float(live.get("fundingRate") or 0)
            if "funding" in text.lower() or "crowding" in text.lower():
                if abs(live_rate) > 0.0005 and str(live_rate) not in text:
                    warnings.append(
                        f"Sentiment may not reflect live funding {live_rate:.6f} for {inst}"
                    )
        except Exception as exc:
            warnings.append(f"Sentiment funding cross-check skipped: {exc}")

    elif agent_name == "Quant-Analyst" and inst:
        try:
            from autohedge.tools.blofin_tools import blofin_technical_analysis

            live_ta = json.loads(blofin_technical_analysis(inst_id=inst))
            if live_ta.get("error"):
                warnings.append(f"Quant TA live verify failed: {live_ta.get('error')}")
            else:
                live_score = float(live_ta.get("technical_score") or 0.5)
                claimed = None
                if data and data.get("probability_score") is not None:
                    claimed = float(data["probability_score"])
                else:
                    m = _SCORE_RE.search(text)
                    if m:
                        claimed = float(m.group(1))
                if claimed is not None and abs(claimed - live_score) > 0.25:
                    issues.append(
                        f"Quant probability_score {claimed:.2f} diverges from live TA {live_score:.2f}"
                    )
                    fixes.append("Re-run blofin_technical_analysis and align scores to live data")
                if claimed is not None and claimed < 0.45:
                    warnings.append(f"Quant low probability_score {claimed:.2f} — weak asymmetric setup")
        except Exception as exc:
            warnings.append(f"Quant cross-check skipped: {exc}")

    elif agent_name == "Risk-Manager" and inst:
        try:
            from autohedge.tools.blofin_tools import resolve_mark_price

            entry = float(resolve_mark_price(inst))
            sl, tp = _extract_prices(text)
            if data:
                if data.get("stop_price"):
                    sl = float(data["stop_price"])
                if data.get("take_profit_price"):
                    tp = float(data["take_profit_price"])
            side = str((data or {}).get("side") or "").lower()
            if "short" in text.lower() and not side:
                side = "short"
            elif "long" in text.lower() and not side:
                side = "long"

            if sl and tp and entry > 0:
                if side == "short" or "sell" in side:
                    risk = abs(sl - entry)
                    reward = abs(entry - tp)
                else:
                    risk = abs(entry - sl)
                    reward = abs(tp - entry)
                if risk > 0:
                    rr = reward / risk
                    if rr < _MIN_RR:
                        issues.append(
                            f"Risk R:R {rr:.1f}:1 below minimum {_MIN_RR}:1 (SL={sl} TP={tp} entry~{entry})"
                        )
                        fixes.append(f"Widen TP or tighten SL to achieve >= {_MIN_RR}:1 reward:risk")
            approved = None
            if data and "approved" in data:
                approved = bool(data["approved"])
            else:
                m = _APPROVED_RE.search(text)
                if m:
                    approved = m.group(1).lower() == "true"
            if approved and (not sl or not tp):
                issues.append("Risk approved trade without explicit stop_price and take_profit_price")
        except Exception as exc:
            warnings.append(f"Risk cross-check skipped: {exc}")

    elif agent_name == "Execution-Agent":
        prior = (pipeline_outputs or {}).get("Risk-Manager", "")
        if prior and not _APPROVED_RE.search(prior):
            if "NO TRADE" not in text.upper():
                issues.append("Execution ran without clear Risk approval in pipeline")

    ok = len(issues) == 0
    result = {
        "agent": agent_name,
        "instId": inst or None,
        "ok": ok,
        "issues": issues,
        "warnings": warnings,
        "fixes": fixes,
    }
    if issues:
        logger.warning("Cross-check FAIL {}: {}", agent_name, "; ".join(issues))
    elif warnings:
        logger.info("Cross-check warn {}: {}", agent_name, "; ".join(warnings[:2]))
    return result


def format_crosscheck_note(result: dict[str, Any]) -> str:
    if result.get("ok") and not result.get("warnings"):
        return ""
    lines = ["[PEER CROSS-CHECK]"]
    for issue in result.get("issues") or []:
        lines.append(f"  ISSUE: {issue}")
    for warn in result.get("warnings") or []:
        lines.append(f"  WARN: {warn}")
    for fix in result.get("fixes") or []:
        lines.append(f"  FIX: {fix}")
    lines.append("Next agent: reconcile against live Blofin tools before proceeding.")
    return "\n".join(lines)
