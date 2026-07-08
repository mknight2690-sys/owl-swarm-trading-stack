"""Deterministic Risk → Execution gate after Quant completes (no LLM stall)."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from collections import deque
from datetime import datetime, timedelta

from loguru import logger

from autohedge.tools.blofin_tools import (
    _blocked_sets,
    blofin_assess_portfolio,
    blofin_execute_minimum_trade,
    blofin_technical_analysis,
    estimate_initial_margin,
    get_blofin_client,
    order_notional_usdt,
    resolve_equity,
    resolve_mark_price,
    resolve_positions_trust,
)
from autohedge.tools.market_analytics import compute_position_size
from autohedge.tools.tpsl_utils import clamp_tpsl_to_book, default_tpsl_for_side
from autohedge.tools.tool_utils import normalize_usdt_inst_id

MIN_PROBABILITY = 0.45
MAX_RISK_SCORE = 0.70
MARGIN_BUFFER = 1.25
FEE_BUFFER_USDT = 0.004
MIN_SENTIMENT = 0.35

# Rejection tracking - avoid retrying recently vetoed symbols
_REJECTION_TRACKER: deque = deque(maxlen=50)  # Store last 50 rejections
_REJECTION_TIMEOUT_SEC = 3600  # 1 hour timeout before retrying symbol


def _assumed_leverage() -> float:
    import os

    try:
        return float(os.environ.get("OWL_MAX_LEVERAGE", "12"))
    except (TypeError, ValueError):
        return 12.0

_SCORE_RE = re.compile(
    r"(?P<key>probability_score|overall_sentiment_score|risk_score)"
    r"\s*[:=]\s*(?P<val>0?\.\d+|1\.0|1|0)",
    re.IGNORECASE,
)


def _parse_score(text: str, key: str) -> float | None:
    for match in _SCORE_RE.finditer(text or ""):
        if match.group("key").lower() == key.lower():
            try:
                return float(match.group("val"))
            except ValueError:
                continue
    try:
        data = json.loads(text)
        if isinstance(data, dict) and key in data:
            return float(data[key])
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _risk_score_from_volatility(volatility_pct: float) -> float:
    return min(1.0, max(0.0, volatility_pct / 8.0))


def _load_technical(inst_id: str) -> dict[str, Any] | None:
    try:
        raw = blofin_technical_analysis(inst_id=inst_id)
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("risk_gate technical_analysis failed for {}: {}", inst_id, exc)
        return None
    if data.get("error"):
        return None
    return data


def _ranked_opportunities(top_n: int = 15) -> list[dict[str, Any]]:
    """Get ranked opportunities with rejection tracking."""
    # Clear old rejections periodically
    _clear_old_rejections()
    
    try:
        from autohedge.tools.blofin_universe_feed import get_universe_feed
        from autohedge.tools.market_analytics import rank_from_tickers
        from autohedge.tools.trade_journal import symbol_stats

        snap = get_universe_feed().get_snapshot()
        if not snap or not snap.tickers:
            return []
        blocked_buy, blocked_sell = _blocked_sets()
        blocked = blocked_buy | blocked_sell
        
        # Get initial ranked list
        ranked = rank_from_tickers(
            snap.tickers,
            blocked=blocked,
            journal_stats=symbol_stats(),
            top_n=top_n * 2,  # Get more candidates to filter from
        )
        
        # Filter out recently rejected symbols
        filtered_ranked = []
        skipped_count = 0
        
        for row in ranked:
            inst = str(row.get("instId") or "")
            
            # Skip if recently rejected
            if _is_recently_rejected(inst):
                skipped_count += 1
                logger.debug("Skipping recently rejected: {}", inst)
                continue
                
            # Skip if blocked or invalid
            if not inst or inst in blocked:
                continue
                
            filtered_ranked.append(row)
            
            # Stop if we have enough candidates
            if len(filtered_ranked) >= top_n:
                break
        
        if skipped_count > 0:
            logger.info("Filtered {} recently rejected symbols from ranking", skipped_count)
            
        return filtered_ranked
        
    except Exception as exc:
        logger.warning("risk_gate rank list failed: {}", exc)
        return []


def _deploy_max_candidates() -> int:
    import os

    try:
        return max(1, int(os.environ.get("OWL_DEPLOY_MAX_CANDIDATES", "60")))
    except (TypeError, ValueError):
        return 60


def _trade_candidate_max() -> int:
    import os

    try:
        return max(1, int(os.environ.get("OWL_TRADE_CANDIDATE_MAX", "60")))
    except (TypeError, ValueError):
        return 60


def _rank_row_for(inst: str) -> dict[str, Any] | None:
    for row in _ranked_opportunities():
        if str(row.get("instId") or "").upper() == inst:
            return row
    return None


def _journal_skip(inst: str) -> bool:
    """Skip repeat losers; favor fresh momentum names."""
    from autohedge.tools.trade_journal import symbol_stats

    stats = symbol_stats().get(inst, {})
    wins = int(stats.get("wins") or 0)
    losses = int(stats.get("losses") or 0)
    if inst == "BTC-USDT" and losses >= 1 and wins == 0:
        return True
    return losses >= 2 and wins == 0


def _track_rejection(inst: str, reason: str) -> None:
    """Track symbol rejections to avoid immediate retry."""
    rejection_entry = {
        "inst": inst,
        "reason": reason,
        "timestamp": time.time()
    }
    _REJECTION_TRACKER.append(rejection_entry)
    logger.debug("Tracked rejection: {} - {}", inst, reason)


def _is_recently_rejected(inst: str) -> bool:
    """Check if symbol was recently rejected (within timeout period)."""
    current_time = time.time()
    cutoff_time = current_time - _REJECTION_TIMEOUT_SEC
    
    for rejection in _REJECTION_TRACKER:
        if (rejection["inst"] == inst and 
            rejection["timestamp"] > cutoff_time):
            return True
    return False


def _clear_old_rejections() -> None:
    """Remove expired rejection entries to prevent memory bloat."""
    current_time = time.time()
    cutoff_time = current_time - _REJECTION_TIMEOUT_SEC
    
    global _REJECTION_TRACKER
    _REJECTION_TRACKER = deque(
        (r for r in _REJECTION_TRACKER if r["timestamp"] > cutoff_time),
        maxlen=50
    )


def _estimate_margin_for(inst: str, entry: float | None = None) -> float:
    """Rough margin at min size for candidate sorting (cheapest first)."""
    inst = normalize_usdt_inst_id(inst)
    if not inst:
        return float("inf")
    try:
        specs = get_blofin_client().get_instrument(inst) or {}
        min_size = float(specs.get("minSize") or 1)
        px = entry if entry and entry > 0 else resolve_mark_price(inst)
        return estimate_initial_margin(
            specs, size=min_size, entry=px, leverage=_assumed_leverage()
        )
    except Exception:
        return float("inf")


def reseed_unheld_candidate() -> str | None:
    """Pick first ranked symbol without an open position; seed pipeline."""
    from autohedge.handoff_pipeline import reset_handoff_pipeline, seed_pipeline_candidate

    blocked_buy, blocked_sell = _blocked_sets()
    held = blocked_buy | blocked_sell
    for row in _ranked_opportunities():
        inst = normalize_usdt_inst_id(str(row.get("instId") or ""))
        if inst and inst not in held and not _journal_skip(inst):
            reset_handoff_pipeline()
            seed_pipeline_candidate(inst)
            logger.info("reseed_unheld_candidate: {}", inst)
            return inst
    return None


def _fit_size_to_available(
    specs: dict[str, Any],
    *,
    entry: float,
    available: float,
    leverage: float,
    min_size: float,
    lot_size: float,
    desired: float,
) -> float | None:
    """Shrink size until initial margin fits available (isolated wallet)."""
    lot = float(lot_size or min_size) or min_size
    size = float(desired)
    floor = float(min_size)
    budget = max(0.0, available * 0.90 - FEE_BUFFER_USDT)
    while size >= floor - 1e-12:
        margin_req = estimate_initial_margin(
            specs, size=size, entry=entry, leverage=leverage
        )
        if margin_req * MARGIN_BUFFER <= budget:
            return size
        size = max(floor, size - lot)
        if size <= floor:
            margin_req = estimate_initial_margin(
                specs, size=floor, entry=entry, leverage=leverage
            )
            if margin_req * MARGIN_BUFFER <= budget:
                return floor
            return None
    return None


def _order_confirmed(exec_raw: str) -> bool:
    try:
        data = json.loads(exec_raw) if isinstance(exec_raw, str) else exec_raw
    except json.JSONDecodeError:
        return False
    order = (data or {}).get("order") if isinstance(data, dict) else None
    if not isinstance(order, dict):
        order = data if isinstance(data, dict) else {}
    order_id = order.get("orderId") or order.get("order_id")
    code = str(order.get("code", "0"))
    return bool(order_id) and code in {"0", ""}


def _current_open_insts() -> set[str]:
    """Live open symbols — sync closes first so Risk does not veto on ghost positions."""
    from autohedge.tools.blofin_tools import _open_position_rows
    from autohedge.tools.trade_journal import sync_position_closes

    sync_position_closes()
    rows = _open_position_rows(retries=2)
    open_insts: set[str] = set()
    for row in rows or []:
        inst = str(row.get("instId") or "").upper()
        try:
            size = float(row.get("positions") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if inst and abs(size) > 0:
            open_insts.add(inst)
    return open_insts


def _log_skip(cache: dict[str, Any], inst: str, reason: str, **extra: Any) -> None:
    cache.setdefault("skip_log", []).append(
        {"instId": inst, "reason": reason, **extra}
    )


def _prepare_portfolio_guards(cache: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], set[str]]:
    """Build assess + TPSL audit filtered to positions that are actually open now."""
    from autohedge.tpsl_guard import audit_open_positions_tpsl, is_tpsl_audit_rate_limited

    open_insts = _current_open_insts()
    if "assess" in cache and "tpsl_audit" in cache:
        assess = cache["assess"]
        tpsl = cache["tpsl_audit"]
        assess["positions_missing_tpsl"] = [
            m for m in (assess.get("positions_missing_tpsl") or []) if m.upper() in open_insts
        ]
        if not open_insts:
            tpsl = {
                "ok": True,
                "open_count": 0,
                "missing": [],
                "partial": [],
                "note": "flat account",
            }
            cache["tpsl_audit"] = tpsl
        return assess, tpsl, open_insts

    try:
        from autohedge.self_heal_playbook import api_cooldown_active

        on_cooldown = api_cooldown_active()
    except Exception:
        on_cooldown = False

    if not open_insts:
        assess = {"positions_missing_tpsl": [], "ok": True, "open_count": 0}
        tpsl = {
            "ok": True,
            "open_count": 0,
            "missing": [],
            "partial": [],
            "note": "flat account",
        }
    elif on_cooldown:
        assess = {"positions_missing_tpsl": [], "ok": True, "open_count": len(open_insts)}
        tpsl = {"ok": True, "rate_limited": True, "open_count": len(open_insts)}
    else:
        try:
            assess = json.loads(blofin_assess_portfolio())
        except Exception:
            assess = {"positions_missing_tpsl": [], "ok": True}
        try:
            tpsl = audit_open_positions_tpsl()
        except Exception:
            tpsl = {"ok": True, "rate_limited": True}
        assess["positions_missing_tpsl"] = [
            m
            for m in (assess.get("positions_missing_tpsl") or [])
            if str(m).upper() in open_insts
        ]
        assess["open_count"] = len(open_insts)
        tpsl["missing"] = [
            m for m in (tpsl.get("missing") or []) if str(m).upper() in open_insts
        ]
        filtered_partial: list[Any] = []
        for item in tpsl.get("partial") or []:
            inst = (
                str(item.get("instId") or item).upper()
                if isinstance(item, dict)
                else str(item).upper()
            )
            if inst in open_insts:
                filtered_partial.append(item)
        tpsl["partial"] = filtered_partial
        if is_tpsl_audit_rate_limited(tpsl):
            tpsl["ok"] = True
        elif not tpsl.get("missing") and not tpsl.get("partial"):
            tpsl["ok"] = True

    cache["assess"] = assess
    cache["tpsl_audit"] = tpsl
    cache["open_insts"] = sorted(open_insts)
    return assess, tpsl, open_insts


def _tpsl_block_reason(
    assess: dict[str, Any],
    tpsl_audit: dict[str, Any],
    open_insts: set[str],
) -> str | None:
    """Return a veto reason only when TP/SL protection genuinely blocks a new entry."""
    from autohedge.tpsl_guard import is_tpsl_audit_rate_limited

    if not open_insts:
        return None
    if is_tpsl_audit_rate_limited(tpsl_audit):
        return None

    missing_tpsl = list(assess.get("positions_missing_tpsl") or [])
    if missing_tpsl:
        return f"open positions missing full TP/SL: {missing_tpsl}"

    missing = list(tpsl_audit.get("missing") or [])
    partial = list(tpsl_audit.get("partial") or [])
    if tpsl_audit.get("ok"):
        return None
    if not missing and not partial:
        logger.warning(
            "risk_gate: TPSL audit ok=False but nothing unprotected — treating as pass"
        )
        return None
    if partial and not missing:
        parts = [
            p.get("instId") if isinstance(p, dict) else str(p) for p in partial
        ]
        return f"open positions partial TP/SL: {parts}"
    return f"TPSL guard blocked trade — unprotected: {missing}"


def maybe_clear_stale_risk_veto(pipeline: Any) -> bool:
    """Drop Risk veto when live portfolio no longer supports the cited reason."""
    if "Risk-Manager" not in pipeline.completed or pipeline.risk_approved:
        return False
    audit = audit_risk_veto_righteous(
        pipeline_state=pipeline.status() if hasattr(pipeline, "status") else None
    )
    if audit.get("righteous") is False:
        from autohedge.handoff_pipeline import _clear_risk_execution_state

        logger.warning(
            "risk_gate: clearing stale Risk veto ({}) — {}",
            audit.get("verdict"),
            str(audit.get("reason") or "")[:120],
        )
        _clear_risk_execution_state()
        try:
            from autohedge.self_heal_playbook import record_auto_heal

            verdict = str(audit.get("verdict") or "risk_veto_stale")
            issue_id = (
                "tpsl_flat_false_veto"
                if verdict == "tpsl_flat_false_veto"
                else "risk_veto_stale"
            )
            record_auto_heal(
                issue_id,
                detail=str(audit.get("verdict") or ""),
                proof=audit,
            )
        except Exception:
            pass
        return True
    return False

def _trade_candidates(pipeline: Any) -> list[str]:
    primary = (
        pipeline.effective_candidate()
        if hasattr(pipeline, "effective_candidate")
        else normalize_usdt_inst_id(pipeline.candidate_inst_id or "")
    )
    blocked_buy, blocked_sell = _blocked_sets()
    held = blocked_buy | blocked_sell
    candidates: list[str] = []
    if primary and primary not in held and not _journal_skip(primary):
        candidates.append(primary)
    rank_prices: dict[str, float] = {}
    max_cands = _trade_candidate_max()
    for row in _ranked_opportunities():
        inst = normalize_usdt_inst_id(str(row.get("instId") or ""))
        if not inst or inst in held:
            continue
        try:
            rank_prices[inst] = float(row.get("last") or 0)
        except (TypeError, ValueError):
            pass
        if inst in candidates or _journal_skip(inst):
            continue
        side = str(row.get("suggested_side") or "long").lower()
        score = float(
            row.get("long_score") if side == "long" else row.get("short_score") or 0
        )
        if score >= MIN_PROBABILITY:
            candidates.append(inst)
        if len(candidates) >= max_cands:
            break

    def _sort_key(sym: str) -> float:
        entry = rank_prices.get(sym)
        return _estimate_margin_for(sym, entry if entry and entry > 0 else None)

    pinned = primary if primary in candidates else ""
    if pinned:
        candidates = [pinned] + sorted(
            [c for c in candidates if c != pinned], key=_sort_key
        )
    else:
        candidates.sort(key=_sort_key)
    return candidates


def _resolve_trade_signal(
    inst: str, tech: dict[str, Any]
) -> tuple[str, float, str]:
    bias = str(tech.get("suggested_bias") or "neutral").lower()
    long_score = float(tech.get("technical_score") or 0)
    short_score = float(tech.get("short_score") or 0)
    if bias == "long":
        tech_prob = long_score
    elif bias == "short":
        tech_prob = short_score
    else:
        tech_prob = max(long_score, short_score)
        bias = "long" if long_score >= short_score else "short"

    rank = _rank_row_for(inst)
    if rank:
        rank_side = str(rank.get("suggested_side") or "long").lower()
        rank_prob = float(
            rank.get("long_score") if rank_side == "long" else rank.get("short_score") or 0
        )
        from autohedge.tools.trade_journal import symbol_stats

        journal = symbol_stats().get(inst, {})
        wins = int(journal.get("wins") or 0)
        losses = int(journal.get("losses") or 0)
        if wins > losses:
            rank_prob = min(1.0, rank_prob * 1.05)
        if rank_prob >= MIN_PROBABILITY and (
            tech_prob < MIN_PROBABILITY or rank_prob > tech_prob
        ):
            logger.info(
                "risk_gate: rank momentum {} {} prob={:.3f} (tech {} {:.3f})",
                inst,
                rank_side,
                rank_prob,
                bias,
                tech_prob,
            )
            return rank_side, rank_prob, "rank_momentum"

    return bias, tech_prob, str(tech.get("source") or "technical")


def _record_veto(
    pipeline: Any,
    reason: str,
    *,
    inst_id: str,
    details: dict[str, Any] | None = None,
) -> str:
    detail = dict(details or {})
    payload = {
        "approved": False,
        "instId": inst_id,
        "reason": reason,
        "source": "deterministic_risk_gate",
        **detail,
    }
    text = json.dumps(payload, default=str)
    pipeline.agent_outputs["Risk-Manager"] = text
    pipeline.completed.add("Risk-Manager")
    pipeline.risk_approved = False
    pipeline.risk_veto_reason = reason
    pipeline.terminal_skip = True
    
    # Track this rejection to prevent immediate retry
    _track_rejection(inst_id, reason)
    
    logger.info("Deterministic Risk veto for {}: {}", inst_id, reason)
    return (
        f"\nAgent: Risk-Manager (deterministic)\n\n"
        f"Task: auto risk gate\n\nResponse:\n{text}\n"
    )


def _signal_from_rank(inst: str) -> tuple[str, float, str, float] | None:
    """Fast rank-only signal: (bias, prob, source, volatility_pct)."""
    rank = _rank_row_for(inst)
    if not rank:
        return None
    bias = str(rank.get("suggested_side") or "long").lower()
    prob = float(
        rank.get("long_score") if bias == "long" else rank.get("short_score") or 0
    )
    if prob < MIN_PROBABILITY:
        return None
    chg = abs(float(rank.get("chg_pct_24h") or 0))
    vol = min(8.0, chg / 2.0)
    return bias, prob, "rank_momentum", vol


def _try_execute_candidate(
    pipeline: Any,
    inst: str,
    *,
    trust: str,
    sent_text: str,
    assess_cache: dict[str, Any] | None = None,
) -> str | None:
    inst = normalize_usdt_inst_id(inst)
    if not inst:
        return None
    sent_score = _parse_score(sent_text, "overall_sentiment_score")
    if sent_score is not None and sent_score < MIN_SENTIMENT:
        logger.info(
            "risk_gate: skip {} — sentiment {:.3f} < {}",
            inst,
            sent_score,
            MIN_SENTIMENT,
        )
        _log_skip(
            assess_cache,
            inst,
            f"sentiment {sent_score:.3f} < {MIN_SENTIMENT}",
            sentiment=sent_score,
        )
        return None

    rank_fast = _signal_from_rank(inst)
    if rank_fast:
        bias, prob, signal_source, vol = rank_fast
        tech = None
    else:
        tech = _load_technical(inst)
        if not tech:
            _log_skip(assess_cache, inst, "technical analysis unavailable")
            return None
        bias, prob, signal_source = _resolve_trade_signal(inst, tech)
        vol = float(tech.get("volatility_pct") or 0)

    if bias not in ("long", "short") or prob < MIN_PROBABILITY:
        logger.info(
            "risk_gate: skip {} — bias={} prob={:.3f}",
            inst,
            bias,
            prob,
        )
        _log_skip(
            assess_cache,
            inst,
            f"probability {prob:.3f} < {MIN_PROBABILITY} or invalid bias",
            probability=prob,
            bias=bias,
        )
        return None

    side = "buy" if bias == "long" else "sell"
    blocked_buy, blocked_sell = _blocked_sets()
    if side == "buy" and inst in blocked_buy:
        _log_skip(assess_cache, inst, "already long — blocked for new buy")
        return None
    if side == "sell" and inst in blocked_sell:
        _log_skip(assess_cache, inst, "already short — blocked for new sell")
        return None

    try:
        assess, tpsl_audit, open_insts = _prepare_portfolio_guards(assess_cache)
        tpsl_reason = _tpsl_block_reason(assess, tpsl_audit, open_insts)
        if tpsl_reason:
            return _record_veto(
                pipeline,
                tpsl_reason,
                inst_id=inst,
                details={
                    "veto_class": "tpsl_protection",
                    "open_positions": sorted(open_insts),
                    "tpsl_audit": tpsl_audit,
                },
            )
        if tpsl_audit.get("rate_limited") or assess.get("rate_limited"):
            logger.warning(
                "risk_gate: TPSL verify rate-limited — proceeding with {} {}",
                inst,
                side,
            )
    except Exception as exc:
        logger.warning("risk_gate assess_portfolio failed: {}", exc)
        _log_skip(assess_cache, inst, f"portfolio guard error: {exc}")
        return None

    # Volatility is no longer a hard veto — position sizing and tight stops handle risk.
    # This was vetoing explosive momentum setups (|chg24h| >= 14%) that the profit
    # doctrine explicitly targets. Removed per user directive: high-momentum moves
    # are the strategy, not a bug.
    risk_score = _risk_score_from_volatility(vol)
    # if risk_score > MAX_RISK_SCORE:
    #     _log_skip(
    #         assess_cache,
    #         inst,
    #         f"volatility risk {risk_score:.3f} > {MAX_RISK_SCORE}",
    #         risk_score=risk_score,
    #     )
    #     return None

    client = get_blofin_client()
    specs = client.get_instrument(inst) or {}
    min_size = float(specs.get("minSize") or 0.1)
    tick = float(specs.get("tickSize") or 0.0001)

    try:
        entry = resolve_mark_price(inst)
    except Exception as exc:
        logger.warning("risk_gate mark price failed for {}: {}", inst, exc)
        _log_skip(assess_cache, inst, f"mark price unavailable: {exc}")
        return None

    try:
        equity, available = resolve_equity(prefer_live=False)
    except Exception as exc:
        logger.warning("risk_gate equity resolve failed: {}", exc)
        _log_skip(assess_cache, inst, f"equity unavailable: {exc}")
        return None

    max_lev = float(specs.get("maxLeverage") or _assumed_leverage() or 12)
    eff_lev = min(_assumed_leverage(), max_lev) if max_lev > 0 else _assumed_leverage()
    margin_req = estimate_initial_margin(
        specs, size=min_size, entry=entry, leverage=eff_lev
    )
    notional = order_notional_usdt(specs, size=min_size, entry=entry)
    if available < margin_req * MARGIN_BUFFER + FEE_BUFFER_USDT:
        logger.info(
            "risk_gate: skip {} — margin need {:.4f} (init {:.4f} notional {:.4f}) avail {:.4f}",
            inst,
            margin_req * MARGIN_BUFFER + FEE_BUFFER_USDT,
            margin_req,
            notional,
            available,
        )
        _log_skip(
            assess_cache,
            inst,
            f"insufficient margin need ${margin_req * MARGIN_BUFFER + FEE_BUFFER_USDT:.4f} avail ${available:.4f}",
            margin_need=round(margin_req * MARGIN_BUFFER + FEE_BUFFER_USDT, 4),
            available=round(available, 4),
        )
        return None

    contract_value = float(specs.get("contractValue") or 1)
    tpsl = None
    try:
        tpsl = default_tpsl_for_side(entry, side, tick=tick)
    except Exception as exc:
        logger.warning("risk_gate: default_tpsl_for_side failed for {}: {}", inst, exc)
    if tpsl is None:
        # Fallback: basic 2.5% TP / 1.5% SL from entry
        tp_pct = 0.025
        sl_pct = 0.015
        if side == "buy":
            tp = round((entry * (1 + tp_pct)) / tick) * tick
            sl = round((entry * (1 - sl_pct)) / tick) * tick
        else:
            tp = round((entry * (1 - tp_pct)) / tick) * tick
            sl = round((entry * (1 + sl_pct)) / tick) * tick
        tpsl = {
            "tpTriggerPrice": str(tp),
            "slTriggerPrice": str(sl),
            "tpTriggerPriceType": "last",
            "slTriggerPriceType": "last",
            "tpOrderPrice": "",
            "slOrderPrice": "",
        }
    try:
        from autohedge.self_heal_playbook import api_cooldown_active

        if not api_cooldown_active():
            book_raw = client.get_order_book(inst, size="5")
            bids = (book_raw or {}).get("bids") or []
            asks = (book_raw or {}).get("asks") or []
            best_bid = float(bids[0][0]) if bids else entry * 0.999
            best_ask = float(asks[0][0]) if asks else entry * 1.001
            tpsl = clamp_tpsl_to_book(tpsl, side, best_bid=best_bid, best_ask=best_ask, tick=tick)
    except Exception as exc:
        logger.debug("risk_gate: order book clamp skipped for {}: {}", inst, exc)
    risk_pct = 0.01
    sl_price = float(tpsl["slTriggerPrice"]) if tpsl["slTriggerPrice"] else 0.0
    stop_dist = abs(entry - sl_price) if sl_price else entry * 0.015
    sized = compute_position_size(
        equity_usdt=equity,
        risk_pct=risk_pct,
        entry=entry,
        stop=entry - stop_dist if side == "buy" else entry + stop_dist,
        min_size=min_size,
        lot_size=float(specs.get("lotSize") or min_size),
        contract_value=contract_value,
        leverage=eff_lev,
    )
    position_size = float(sized.get("size", min_size))
    if available < float(os.environ.get("OWL_SMALL_ACCOUNT_AVAILABLE", "2.5")):
        min_fit = _fit_size_to_available(
            specs,
            entry=entry,
            available=available,
            leverage=eff_lev,
            min_size=min_size,
            lot_size=float(specs.get("lotSize") or min_size),
            desired=min_size,
        )
        if min_fit is not None:
            position_size = min_fit
    fitted = _fit_size_to_available(
        specs,
        entry=entry,
        available=available,
        leverage=eff_lev,
        min_size=min_size,
        lot_size=float(specs.get("lotSize") or min_size),
        desired=position_size,
    )
    if fitted is None:
        logger.info(
            "risk_gate: skip {} — cannot fit size within avail {:.4f}",
            inst,
            available,
        )
        _log_skip(
            assess_cache,
            inst,
            f"cannot fit position size within available ${available:.4f}",
            available=round(available, 4),
        )
        return None
    position_size = fitted
    margin_req = estimate_initial_margin(
        specs, size=position_size, entry=entry, leverage=eff_lev
    )
    margin_need = margin_req * MARGIN_BUFFER + FEE_BUFFER_USDT
    pipeline.set_candidate(inst)
    risk_payload = {
        "approved": True,
        "instId": inst,
        "side": side,
        "position_size": str(position_size),
        "entry_ref": entry,
        "stop_price": tpsl["slTriggerPrice"],
        "take_profit_price": tpsl["tpTriggerPrice"],
        "risk_score": round(risk_score, 3),
        "probability_score": round(prob, 3),
        "signal_source": signal_source,
        "equity_usdt": round(equity, 4),
        "available_usdt": round(available, 4),
        "notional_usdt": round(notional, 4),
        "margin_required_usdt": round(margin_req, 6),
        "margin_need_usdt": round(margin_need, 6),
        "contract_value": specs.get("contractValue"),
        "positions_trust": trust,
        "source": "deterministic_risk_gate",
    }
    risk_text = json.dumps(risk_payload, default=str)
    pipeline.agent_outputs["Risk-Manager"] = risk_text
    pipeline.completed.add("Risk-Manager")
    pipeline.risk_approved = True
    logger.info(
        "Deterministic Risk approved {} {} size={} prob={:.3f} source={} "
        "notional={:.4f} margin={:.4f} avail={:.4f}",
        inst,
        side,
        position_size,
        prob,
        signal_source,
        notional,
        margin_req,
        available,
    )

    try:
        exec_raw = blofin_execute_minimum_trade(
            inst_id=inst,
            side=side,
            tp_trigger_price=tpsl["tpTriggerPrice"],
            sl_trigger_price=tpsl["slTriggerPrice"],
            size=str(position_size),
        )
        try:
            exec_data = json.loads(exec_raw) if isinstance(exec_raw, str) else exec_raw
            order = (exec_data or {}).get("order") or {}
            if not isinstance(order, dict):
                order = exec_data if isinstance(exec_data, dict) else {}
            order_id = order.get("orderId") or order.get("order_id")
            code = str(order.get("code", "0"))
            if not order_id or code not in {"0", ""}:
                raise RuntimeError(
                    f"Blofin order rejected: code={code} msg={order.get('msg')} "
                    f"raw={str(exec_raw)[:200]}"
                )
        except json.JSONDecodeError:
            if "103003" in str(exec_raw) or "Insufficient margin" in str(exec_raw):
                raise RuntimeError(str(exec_raw)[:300])
            raise RuntimeError(f"Invalid execution response: {str(exec_raw)[:200]}")
        if not _order_confirmed(exec_raw):
            raise RuntimeError(f"Execution missing orderId: {str(exec_raw)[:200]}")
        pipeline.agent_outputs["Execution-Agent"] = exec_raw
        pipeline.completed.add("Execution-Agent")
        logger.info("Deterministic Execution completed for {}", inst)
        try:
            from autohedge.swarm_learning_audit import record_self_fix

            record_self_fix(
                title=f"Deterministic Risk/Execution enforced {inst} {side}",
                detail=(
                    f"Auto-applied SL={tpsl['slTriggerPrice']} TP={tpsl['tpTriggerPrice']} "
                    f"size={position_size} without human intervention"
                ),
                component="risk_gate",
                proof={
                    "instId": inst,
                    "side": side,
                    "stop": tpsl["slTriggerPrice"],
                    "take_profit": tpsl["tpTriggerPrice"],
                    "risk_reward_enforced": True,
                    "source": "deterministic_risk_gate",
                },
            )
        except Exception:
            pass
        return (
            f"\nAgent: Risk-Manager (deterministic)\n\nResponse:\n{risk_text}\n\n"
            f"Agent: Execution-Agent (deterministic)\n\nResponse:\n{exec_raw}\n"
        )
    except Exception as exc:
        err = f"Deterministic execution failed: {exc}"
        logger.error(err)
        if "103003" in str(exc) or "Insufficient margin" in str(exc):
            try:
                from autohedge.tools.trade_journal import record_event

                record_event(
                    {
                        "type": "order_blocked",
                        "instId": inst,
                        "side": side,
                        "reason": "insufficient_margin_exchange",
                        "msg": str(exc),
                        "margin_need_usdt": round(margin_need, 6),
                        "available_usdt": round(available, 6),
                    }
                )
            except Exception:
                pass
            if available > margin_need * 1.5:
                try:
                    from autohedge.self_heal_playbook import teach_from_journal_block

                    teach_from_journal_block(
                        inst_id=inst,
                        available_usdt=available,
                        margin_need_usdt=margin_need,
                        msg=str(exc),
                    )
                except Exception:
                    pass
            pipeline.completed.discard("Risk-Manager")
            pipeline.completed.discard("Execution-Agent")
            pipeline.risk_approved = False
            pipeline.agent_outputs.pop("Risk-Manager", None)
            pipeline.agent_outputs.pop("Execution-Agent", None)
            logger.info(
                "risk_gate: {} rejected by exchange (103003) — trying next candidate",
                inst,
            )
            return None
        pipeline.agent_outputs["Execution-Agent"] = json.dumps(
            {"code": "error", "msg": err, "instId": inst}
        )
        pipeline.completed.add("Execution-Agent")
        return (
            f"\nAgent: Risk-Manager (deterministic)\n\nResponse:\n{risk_text}\n\n"
            f"Agent: Execution-Agent (deterministic)\n\nResponse:\n{err}\n"
        )


def audit_risk_veto_righteous(*, pipeline_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Verify the latest Risk veto still matches live portfolio reality.
    Returns righteous=False when veto reason references closed positions or stale TPSL claims.
    """
    import re

    report: dict[str, Any] = {"righteous": True, "verdict": "ok"}
    ps = pipeline_state
    if ps is None:
        try:
            from autohedge.handoff_pipeline import pipeline_status

            ps = pipeline_status()
        except Exception:
            ps = {}
    if ps.get("risk_approved"):
        report["verdict"] = "approved"
        return report
    completed = set(ps.get("completed") or [])
    if "Risk-Manager" not in completed:
        report["verdict"] = "no_veto"
        return report

    reason = str(ps.get("risk_veto_reason") or "")
    if not reason:
        try:
            from autohedge.handoff_pipeline import _pipeline

            raw = str(_pipeline.agent_outputs.get("Risk-Manager") or "")
            if raw.strip().startswith("{"):
                reason = str(json.loads(raw).get("reason") or "")
        except Exception:
            pass
    report["reason"] = reason
    report["candidate"] = str(ps.get("candidate_inst_id") or "")

    if re.search(r"unprotected:\s*\[\]", reason) or "unprotected: []" in reason:
        report["righteous"] = False
        report["verdict"] = "tpsl_flat_false_veto"
        return report

    open_insts: set[str] = set()
    try:
        from autohedge.tools.blofin_tools import _blocked_sets

        blocked_buy, blocked_sell = _blocked_sets()
        open_insts = {s.upper() for s in (blocked_buy | blocked_sell)}
    except Exception as exc:
        report["righteous"] = None
        report["verdict"] = "positions_unavailable"
        report["error"] = str(exc)
        return report

    report["open_positions"] = sorted(open_insts)

    if "missing full TP/SL" in reason.lower() or "unprotected" in reason.lower():
        cited = [m.upper() for m in re.findall(r"([A-Z][A-Z0-9]{1,20}-USDT)", reason)]
        stale = [sym for sym in cited if sym not in open_insts]
        if stale:
            report["righteous"] = False
            report["verdict"] = "stale_tpsl_veto"
            report["stale_symbols"] = stale
            return report
        if cited:
            try:
                from autohedge.tpsl_guard import audit_open_positions_tpsl, is_tpsl_audit_rate_limited

                audit = audit_open_positions_tpsl()
                if not is_tpsl_audit_rate_limited(audit) and audit.get("ok"):
                    report["righteous"] = False
                    report["verdict"] = "tpsl_now_protected"
                    report["tpsl_audit"] = audit
                    return report
                if audit.get("missing"):
                    report["righteous"] = True
                    report["verdict"] = "tpsl_still_missing"
                    report["tpsl_audit"] = audit
                    return report
            except Exception as exc:
                report["tpsl_check_error"] = str(exc)

    if "no candidate passed risk checks" in reason.lower():
        report["verdict"] = "edge_threshold_veto"
        report["righteous"] = True
        try:
            from autohedge.handoff_pipeline import _pipeline

            raw = str(_pipeline.agent_outputs.get("Risk-Manager") or "")
            if raw.strip().startswith("{"):
                payload = json.loads(raw)
                skip_log = payload.get("skip_log") or payload.get("details", {}).get(
                    "skip_log"
                )
                if skip_log:
                    report["skip_log"] = skip_log
                    margin_only = all(
                        "margin" in str(s.get("reason") or "").lower()
                        or "probability" in str(s.get("reason") or "").lower()
                        or "sentiment" in str(s.get("reason") or "").lower()
                        for s in skip_log
                    )
                    if margin_only and not open_insts:
                        report["verdict"] = "threshold_no_edge_flat"
                    report["righteous"] = True
        except Exception:
            pass

    if "no ranked candidates" in reason.lower():
        report["verdict"] = "no_candidates"
        report["righteous"] = True

    return report


def try_deterministic_risk_execution(
    pipeline: Any, *, max_candidates: int | None = None
) -> str | None:
    if "Quant-Analyst" not in pipeline.completed:
        return None
    if "Risk-Manager" in pipeline.completed:
        return None

    maybe_clear_stale_risk_veto(pipeline)

    trust = resolve_positions_trust()
    if trust == "unknown":
        logger.warning(
            "risk_gate: positions trust=unknown (WAF) — proceeding with disk-cache fallback"
        )

    sent_text = pipeline.agent_outputs.get("Sentiment-Agent", "")
    candidates = _trade_candidates(pipeline)
    try:
        from autohedge.self_heal_playbook import api_cooldown_active

        if api_cooldown_active():
            locked = normalize_usdt_inst_id(pipeline.candidate_inst_id or "")
            if locked:
                candidates = [locked]
            max_candidates = 1
    except Exception:
        pass
    if max_candidates is not None and max_candidates > 0:
        candidates = candidates[:max_candidates]
    if not candidates:
        return _record_veto(
            pipeline,
            "no ranked candidates above threshold",
            inst_id=(pipeline.candidate_inst_id or "UNKNOWN"),
        )

    logger.info("risk_gate: evaluating candidates {}", candidates)
    last_inst = candidates[-1]
    assess_cache: dict[str, Any] = {"skip_log": []}
    for inst in candidates:
        result = _try_execute_candidate(
            pipeline, inst, trust=trust, sent_text=sent_text, assess_cache=assess_cache
        )
        if result is not None:
            return result
        if "Risk-Manager" in pipeline.completed:
            return result

    skip_log = assess_cache.get("skip_log") or []
    if skip_log:
        brief = "; ".join(
            f"{row['instId']}: {row['reason']}" for row in skip_log[:6]
        )
        veto_reason = f"no candidate passed risk checks — {brief}"
    else:
        veto_reason = "no candidate passed risk checks (tried rank top picks)"

    return _record_veto(
        pipeline,
        veto_reason,
        inst_id=last_inst,
        details={"candidates_tried": candidates, "skip_log": skip_log},
    )


def deploy_idle_margin(
    *, min_available: float | None = None, primary_only: bool = False, force: bool = False
) -> str | None:
    """
    When available margin sits unused after a cycle, try a NEW symbol via deterministic gate.
    Skips symbols that already have open positions.
    """
    import os

    floor = min_available
    if floor is None:
        try:
            floor = float(os.environ.get("OWL_MIN_DEPLOY_AVAILABLE", "0.15"))
        except (TypeError, ValueError):
            floor = 0.15
    try:
        _, available = resolve_equity(prefer_live=False)
    except Exception as exc:
        logger.warning("deploy_idle_margin: equity unavailable: {}", exc)
        return None
    if available < floor:
        return None

    from autohedge.handoff_pipeline import pipeline_status

    ps = pipeline_status()
    completed = set(ps.get("completed") or [])
    from autohedge.handoff_pipeline import reset_handoff_pipeline, seed_pipeline_candidate

    blocked_buy, blocked_sell = _blocked_sets()
    held = blocked_buy | blocked_sell

    if "Execution-Agent" in completed:
        cand = normalize_usdt_inst_id(str(ps.get("candidate_inst_id") or ""))
        if force or (cand and not _journal_has_order_for(cand)):
            reset_handoff_pipeline()
            if cand and cand not in held:
                seed_pipeline_candidate(cand)
            elif force:
                pick_edge_candidate()
        else:
            return None

    from autohedge.handoff_pipeline import _pipeline

    cand = normalize_usdt_inst_id(
        _pipeline.effective_candidate()
        if hasattr(_pipeline, "effective_candidate")
        else (_pipeline.candidate_inst_id or "")
    )
    if cand in held:
        _pipeline.candidate_inst_id = ""
        for row in _ranked_opportunities():
            inst = normalize_usdt_inst_id(str(row.get("instId") or ""))
            if inst and inst not in held:
                _pipeline.set_candidate(inst)
                logger.info("deploy_idle_margin: reseeded candidate {} (was held {})", inst, cand)
                break

    for agent in ("Portfolio-Manager", "Sentiment-Agent", "Quant-Analyst"):
        _pipeline.completed.add(agent)

    trust = resolve_positions_trust()
    logger.info(
        "deploy_idle_margin: avail=${:.4f} — running deterministic deploy",
        available,
    )
    return try_deterministic_risk_execution(
        _pipeline,
        max_candidates=(1 if primary_only else _deploy_max_candidates()),
    )


def _journal_path() -> Path:
    import os
    from pathlib import Path

    root = Path(os.environ.get("AUTO_TRADER_ROOT", r"C:\Users\mknig\blofin-auto-trader"))
    return root / "outputs" / "trade_journal.jsonl"


def _journal_has_order_for(inst: str, *, within_sec: float = 900.0) -> bool:
    inst = normalize_usdt_inst_id(inst)
    if not inst:
        return False
    path = _journal_path()
    if not path.is_file():
        return False
    cutoff = time.time() - within_sec
    try:
        for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]):
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(ev.get("type") or "") != "order_placed":
                continue
            if str(ev.get("instId") or "").upper() != inst:
                continue
            if float(ev.get("ts") or 0) >= cutoff and ev.get("orderId"):
                return True
    except OSError:
        pass
    return False


def _journal_has_recent_order(*, within_sec: float = 2700.0) -> bool:
    path = _journal_path()
    if not path.is_file():
        return False
    cutoff = time.time() - within_sec
    try:
        for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]):
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(ev.get("type") or "") == "order_placed" and float(ev.get("ts") or 0) >= cutoff:
                if ev.get("orderId"):
                    return True
    except OSError:
        pass
    return False


def _last_order_for(inst: str) -> dict[str, Any] | None:
    inst = normalize_usdt_inst_id(inst)
    path = _journal_path()
    if not path.is_file() or not inst:
        return None
    try:
        for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]):
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(ev.get("type") or "") == "order_placed" and str(ev.get("instId") or "").upper() == inst:
                return ev
    except OSError:
        pass
    return None


def pick_edge_candidate() -> str | None:
    """
    Highest-conviction UNHELD symbol: momentum + rank score + journal hygiene.
    Used for autonomous proof trades — not spray-and-pray.
    """
    try:
        edge_min_prob = float(os.environ.get("OWL_EDGE_MIN_PROB", "0.58"))
        edge_min_chg = float(os.environ.get("OWL_EDGE_MIN_CHG", "5.0"))
    except (TypeError, ValueError):
        edge_min_prob, edge_min_chg = 0.58, 5.0

    blocked_buy, blocked_sell = _blocked_sets()
    held = blocked_buy | blocked_sell
    best_inst = ""
    best_score = 0.0
    relax = os.environ.get("OWL_EDGE_RELAX", "1").strip().lower() in ("1", "true", "yes", "on")
    for row in _ranked_opportunities():
        inst = normalize_usdt_inst_id(str(row.get("instId") or ""))
        if not inst or inst in held or _journal_skip(inst):
            continue
        side = str(row.get("suggested_side") or "long").lower()
        prob = float(
            row.get("long_score") if side == "long" else row.get("short_score") or 0
        )
        chg = abs(float(row.get("chg_pct_24h") or 0))
        if not relax and (prob < edge_min_prob or chg < edge_min_chg):
            continue
        if relax and prob < MIN_PROBABILITY:
            continue
        if not relax and not _signal_from_rank(inst):
            continue
        score = prob + (0.02 if chg >= edge_min_chg else 0.0)
        if score > best_score:
            best_score = score
            best_inst = inst
    if not best_inst:
        return None
    from autohedge.handoff_pipeline import reset_handoff_pipeline, seed_pipeline_candidate

    reset_handoff_pipeline()
    seed_pipeline_candidate(best_inst)
    logger.info("pick_edge_candidate: {} score={:.3f}", best_inst, best_score)
    return best_inst


def ensure_autonomous_trade(*, source: str = "swarm") -> dict[str, Any]:
    """
    Autonomous proof trade — only when no recent fill and edge candidate passes gate.
    Verifies order_placed + orderId in journal before reporting success.
    """
    import time as _time

    report: dict[str, Any] = {"ok": False, "source": source, "ts": _time.time()}
    if _journal_has_recent_order():
        report.update({"ok": True, "skipped": True, "reason": "recent_order_placed"})
        return report
    try:
        _, available = resolve_equity(prefer_live=False)
    except Exception as exc:
        report["reason"] = f"equity_unavailable:{exc}"
        return report
    floor = float(os.environ.get("OWL_MIN_DEPLOY_AVAILABLE", "0.15"))
    if available < floor:
        report["reason"] = "insufficient_available"
        report["available"] = round(available, 4)
        return report
    inst = pick_edge_candidate()
    if not inst:
        report["reason"] = "no_edge_candidate"
        return report
    report["instId"] = inst
    retries = int(os.environ.get("OWL_AUTONOMOUS_TRADE_RETRIES", "4"))
    for attempt in range(max(1, retries)):
        if attempt:
            _time.sleep(20)
        logger.info(
            "ensure_autonomous_trade [{}] attempt {} inst={} avail={:.4f}",
            source,
            attempt + 1,
            inst,
            available,
        )
        deploy_idle_margin(primary_only=True, force=True)
        if _journal_has_order_for(inst, within_sec=180.0):
            placed = _last_order_for(inst) or {}
            report.update(
                {
                    "ok": True,
                    "placed": True,
                    "orderId": placed.get("orderId"),
                    "side": placed.get("side"),
                    "size": placed.get("size"),
                }
            )
            try:
                from autohedge.swarm_learning_audit import record_self_fix

                record_self_fix(
                    title=f"Autonomous edge trade {inst}",
                    detail=f"source={source} orderId={placed.get('orderId')} side={placed.get('side')}",
                    component="risk_gate",
                    proof=report,
                )
            except Exception:
                pass
            return report
    report["reason"] = "deploy_failed_after_retries"
    return report
