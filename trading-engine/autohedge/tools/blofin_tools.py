"""Blofin tools for AutoHedge agents — replaces Jupiter/Solana execution."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from loguru import logger

from autohedge.tools.blofin_client import BlofinClient
from autohedge.tools.blofin_universe_feed import get_universe_feed
from autohedge.tools.tool_utils import normalize_usdt_inst_id, pick_inst_id, pick_str
from autohedge.tools.tpsl_utils import default_tpsl_for_side

_blofin_client: BlofinClient | None = None
_portfolio_cache: tuple[float, str] | None = None
_PORTFOLIO_CACHE_SEC = 12.0
_positions_cache: tuple[float, list[dict]] | None = None
_POSITIONS_CACHE_SEC = 300.0
_positions_trust: str = "unknown"  # live | stale | unknown
_positions_last_fail_ts: float = 0.0
_POSITIONS_FAIL_COOLDOWN_SEC = 30.0
_POSITIONS_CONSECUTIVE_FAIL_LIMIT = 3
_positions_consecutive_fails: int = 0
_POSITIONS_DISK_CACHE = Path(__file__).resolve().parents[2] / "outputs" / "positions-cache.json"
_POSITIONS_DISK_MAX_AGE_SEC = 3600.0
_EQUITY_DISK_CACHE = Path(__file__).resolve().parents[2] / "outputs" / "equity-cache.json"
_EQUITY_DISK_MAX_AGE_SEC = 3600.0


def get_blofin_client() -> BlofinClient:
    global _blofin_client
    if _blofin_client is None:
        _blofin_client = BlofinClient()
    return _blofin_client


def _out(data: object) -> str:
    return json.dumps(data, default=str)


def _tick_for_inst(inst_id: str) -> float:
    for row in get_blofin_client().list_live_instruments():
        if row.get("instId") == inst_id:
            try:
                return float(row.get("tickSize") or 0.1)
            except (TypeError, ValueError):
                break
    return 0.1


def positions_trust_level() -> str:
    """Whether open-position data is trustworthy for new-entry guards."""
    return _positions_trust


def resolve_positions_trust(*, allow_disk: bool = True) -> str:
    """Resolve live/stale trust; load disk cache when API is WAF-blocked."""
    global _positions_cache, _positions_trust
    if _positions_trust in {"live", "stale"}:
        return _positions_trust
    if allow_disk:
        disk = _load_positions_disk()
        if disk:
            open_rows, disk_trust = disk
            _positions_cache = (time.time(), open_rows)
            _positions_trust = (
                disk_trust if disk_trust in {"live", "stale"} else "stale"
            )
            logger.info(
                "resolve_positions_trust: disk cache ({} open, trust={})",
                len(open_rows),
                _positions_trust,
            )
            return _positions_trust
    return _positions_trust


def resolve_mark_price(inst_id: str) -> float:
    """Mark/last price with universe-feed fallback when REST tickers are WAF-blocked."""
    inst = inst_id.strip().upper()
    try:
        tickers = get_blofin_client().get_tickers(inst)
        if tickers:
            row = tickers[0]
            for key in ("last", "markPrice", "askPrice", "bidPrice"):
                raw = row.get(key)
                if raw is not None and str(raw).strip():
                    return float(raw)
    except Exception as exc:
        logger.warning("resolve_mark_price REST failed for {}: {}", inst, exc)
    cached = get_universe_feed().ticker_for(inst)
    if cached:
        for key in ("last", "markPrice", "askPrice", "bidPrice"):
            raw = cached.get(key)
            if raw is not None and str(raw).strip():
                return float(raw)
    raise ValueError(f"No price for {inst_id} (REST and cache)")


def _mark_price(inst_id: str) -> float:
    return resolve_mark_price(inst_id)


def _resolve_tpsl_prices(
    inst_id: str,
    side: str,
    *,
    entry_price: float | None = None,
    tp_trigger_price: str = "",
    sl_trigger_price: str = "",
) -> dict[str, str]:
    tick = _tick_for_inst(inst_id)
    if tp_trigger_price.strip() and sl_trigger_price.strip():
        return {
            "tpTriggerPrice": tp_trigger_price.strip(),
            "tpOrderPrice": "-1",
            "tpTriggerPriceType": "last",
            "slTriggerPrice": sl_trigger_price.strip(),
            "slOrderPrice": "-1",
            "slTriggerPriceType": "last",
            "close_side": "sell" if side.lower() == "buy" else "buy",
        }
    entry = entry_price if entry_price and entry_price > 0 else _mark_price(inst_id)
    defaults = default_tpsl_for_side(entry, side, tick=tick)
    if tp_trigger_price.strip():
        defaults["tpTriggerPrice"] = tp_trigger_price.strip()
    if sl_trigger_price.strip():
        defaults["slTriggerPrice"] = sl_trigger_price.strip()
    return defaults


def _pending_tpsl_for(inst_id: str) -> list[dict]:
    return get_blofin_client().get_pending_tpsl(inst_id)


def _position_margin_mode(row: dict[str, Any]) -> str:
    return str(row.get("marginMode") or os.environ.get("BLOFIN_MARGIN_MODE", "isolated")).lower()


def _position_fully_protected(row: dict[str, Any]) -> bool:
    from autohedge.tpsl_guard import position_has_full_tpsl

    inst = str(row.get("instId") or "")
    if not inst:
        return True
    return position_has_full_tpsl(inst, margin_mode=_position_margin_mode(row))


def blofin_get_pending_tpsl(inst_id: str = "", **_kwargs: object) -> str:
    """List live TP/SL orders. Optional inst_id filter (e.g. BTC-USDT)."""
    inst = inst_id.strip() or None
    rows = get_blofin_client().get_pending_tpsl(inst)
    return _out({"count": len(rows), "orders": rows})


def blofin_place_tpsl(
    inst_id: str,
    side: str = "",
    size: str = "-1",
    tp_trigger_price: str = "",
    sl_trigger_price: str = "",
    margin_mode: str = "",
    position_side: str = "net",
    reduce_only: str = "true",
    **_kwargs: object,
) -> str:
    """
    Attach TP/SL to an open position. side is the closing side (sell for long, buy for short).
    size -1 = entire position. Omit prices to use defaults from average entry (1.5% SL / 2.5% TP).
    """
    inst = pick_inst_id(inst_id, **_kwargs)
    if not inst:
        return _out({"code": "error", "msg": f"No open position on {inst_id}"})

    positions = get_blofin_client().get_positions(inst)
    if not positions:
        return _out({"code": "error", "msg": f"No open position on {inst}"})

    pos = positions[0]
    try:
        pos_size = float(pos.get("positions") or 0)
    except (TypeError, ValueError):
        pos_size = 0.0
    if abs(pos_size) < 1e-12:
        return _out({"code": "error", "msg": f"No open position on {inst}"})

    eff_margin = (
        margin_mode.strip().lower()
        or str(pos.get("marginMode") or os.environ.get("BLOFIN_MARGIN_MODE", "isolated")).lower()
    )

    entry_side = "buy" if pos_size > 0 else "sell"
    close_side = side.strip().lower() or ("sell" if pos_size > 0 else "buy")
    try:
        entry = float(pos.get("averagePrice") or 0)
    except (TypeError, ValueError):
        entry = _mark_price(inst)

    levels = _resolve_tpsl_prices(
        inst,
        entry_side,
        entry_price=entry,
        tp_trigger_price=tp_trigger_price,
        sl_trigger_price=sl_trigger_price,
    )
    if _position_fully_protected(pos):
        return _out(
            {
                "code": "skipped",
                "msg": f"TP/SL already live for {inst}",
                "pending": _pending_tpsl_for(inst),
            }
        )

    result = get_blofin_client().place_tpsl(
        inst,
        close_side,
        size.strip() or "-1",
        margin_mode=eff_margin,
        position_side=position_side.strip().lower(),
        reduce_only=reduce_only.strip().lower(),
        tp_trigger_price=levels["tpTriggerPrice"],
        tp_order_price=levels["tpOrderPrice"],
        tp_trigger_price_type=levels["tpTriggerPriceType"],
        sl_trigger_price=levels["slTriggerPrice"],
        sl_order_price=levels["slOrderPrice"],
        sl_trigger_price_type=levels["slTriggerPriceType"],
    )
    logger.info("blofin_place_tpsl result: {}", result)
    return _out(result)


def blofin_ensure_position_tpsl(inst_id: str = "", **_kwargs: object) -> str:
    """Place default TP/SL on any open position missing full protection (repair / safety net)."""
    from autohedge.tpsl_guard import repair_missing_tpsl

    return _out(repair_missing_tpsl(inst_id=inst_id))


def _save_positions_disk(open_rows: list[dict], trust: str) -> None:
    try:
        _POSITIONS_DISK_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _POSITIONS_DISK_CACHE.write_text(
            json.dumps(
                {
                    "updated_at": time.time(),
                    "trust": trust,
                    "open_rows": open_rows,
                },
                default=str,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not persist positions cache: {}", exc)


def _load_positions_disk() -> tuple[list[dict], str] | None:
    if not _POSITIONS_DISK_CACHE.is_file():
        return None
    try:
        data = json.loads(_POSITIONS_DISK_CACHE.read_text(encoding="utf-8"))
        updated = float(data.get("updated_at") or 0)
        age = time.time() - updated
        if age > _POSITIONS_DISK_MAX_AGE_SEC:
            return None
        rows = data.get("open_rows")
        if not isinstance(rows, list):
            return None
        trust = str(data.get("trust") or "stale")
        logger.info(
            "Loaded disk positions cache ({}s old, {} open, trust={})",
            int(age),
            len(rows),
            trust,
        )
        return rows, trust if trust in {"live", "stale"} else "stale"
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Could not load positions disk cache: {}", exc)
        return None


def _open_position_rows(*, retries: int = 6) -> list[dict]:
    global _positions_cache, _positions_trust, _positions_last_fail_ts, _positions_consecutive_fails
    now = time.time()
    disk = _load_positions_disk()
    if disk:
        open_rows, trust = disk
        if not open_rows:
            _positions_cache = (now, [])
            _positions_trust = trust if trust in {"live", "stale"} else "stale"
            return []
    try:
        from autohedge.self_heal_playbook import api_cooldown_active

        if api_cooldown_active():
            disk = _load_positions_disk()
            if disk:
                open_rows, trust = disk
                _positions_cache = (now, open_rows)
                _positions_trust = trust if trust in {"live", "stale"} else "stale"
                return open_rows
            return list(_positions_cache[1]) if _positions_cache else []
    except Exception:
        pass
    if (
        _positions_trust == "unknown"
        and not _positions_cache
        and _positions_last_fail_ts
        and (now - _positions_last_fail_ts) < _POSITIONS_FAIL_COOLDOWN_SEC
    ):
        logger.info(
            "Skipping positions API (WAF cooldown {:.0f}s remaining)",
            _POSITIONS_FAIL_COOLDOWN_SEC - (now - _positions_last_fail_ts),
        )
        disk = _load_positions_disk()
        if disk:
            open_rows, trust = disk
            _positions_cache = (now, open_rows)
            _positions_trust = trust if trust in {"live", "stale"} else "stale"
            return open_rows
        return []
    if _positions_consecutive_fails >= _POSITIONS_CONSECUTIVE_FAIL_LIMIT:
        logger.warning(
            "Positions API blocked {} consecutive times — skipping, using disk cache",
            _positions_consecutive_fails,
        )
        disk = _load_positions_disk()
        if disk:
            open_rows, trust = disk
            _positions_cache = (now, open_rows)
            _positions_trust = trust if trust in {"live", "stale"} else "stale"
            return open_rows
        return []
    try:
        rows = get_blofin_client().get_positions(retries=min(retries, 3))
        _positions_consecutive_fails = 0
        open_rows: list[dict] = []
        for row in rows:
            try:
                size = float(row.get("positions") or 0)
            except (TypeError, ValueError):
                size = 0.0
            if row.get("instId") and abs(size) > 0:
                open_rows.append(row)
        _positions_cache = (now, open_rows)
        _positions_trust = "live"
        _save_positions_disk(open_rows, "live")
        return open_rows
    except Exception as exc:
        logger.warning("get_positions failed: {}", exc)
        _positions_last_fail_ts = now
        _positions_consecutive_fails += 1
        if _positions_cache and (now - _positions_cache[0]) < _POSITIONS_CACHE_SEC:
            age = int(now - _positions_cache[0])
            logger.warning("Using stale positions cache ({}s old)", age)
            _positions_trust = "stale"
            return _positions_cache[1]
        disk = _load_positions_disk()
        if disk:
            open_rows, trust = disk
            _positions_cache = (now, open_rows)
            _positions_trust = trust
            return open_rows
        _positions_trust = "unknown"
        return []


def warm_positions_read(*, attempts: int = 1, pause_sec: float = 3.0) -> str:
    """
    Best-effort positions fetch after universe refresh.
    If WAF blocks positions, returns 'unknown' immediately without retrying.
    """
    trust = positions_trust_level()
    if trust in {"live", "stale"}:
        return trust
    try:
        _open_position_rows(retries=1)
    except Exception:
        pass
    trust = positions_trust_level()
    if trust in {"live", "stale"}:
        return trust
    logger.warning("Positions warm-up: WAF blocked — using trust=unknown (disk cache fallback)")
    return "unknown"


def _blocked_sets() -> tuple[set[str], set[str]]:
    """Lightweight blocked-symbol lookup without full portfolio JSON."""
    blocked_buy: set[str] = set()
    blocked_sell: set[str] = set()
    for row in _open_position_rows():
        inst = str(row.get("instId") or "")
        try:
            size = float(row.get("positions") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if size > 0:
            blocked_buy.add(inst)
        elif size < 0:
            blocked_sell.add(inst)
    return blocked_buy, blocked_sell


def blofin_assess_portfolio(**_kwargs: object) -> str:
    """Assess open positions and which symbols are blocked for new entries."""
    global _portfolio_cache
    now = time.time()
    if _portfolio_cache and (now - _portfolio_cache[0]) < _PORTFOLIO_CACHE_SEC:
        return _portfolio_cache[1]

    from autohedge.tools.trade_journal import sync_position_closes

    sync_position_closes()
    open_rows = _open_position_rows(retries=0)
    blocked_buy: list[str] = []
    blocked_sell: list[str] = []
    summary: list[dict] = []

    for row in open_rows:
        inst = str(row.get("instId"))
        try:
            size = float(row.get("positions") or 0)
        except (TypeError, ValueError):
            size = 0.0
        side = "long" if size > 0 else "short"
        summary.append(
            {
                "instId": inst,
                "positions": row.get("positions"),
                "side": side,
                "averagePrice": row.get("averagePrice"),
                "markPrice": row.get("markPrice"),
                "unrealizedPnl": row.get("unrealizedPnl"),
            }
        )
        if size > 0:
            blocked_buy.append(inst)
        elif size < 0:
            blocked_sell.append(inst)

    missing_tpsl = [
        str(r.get("instId"))
        for r in open_rows
        if r.get("instId") and not _position_fully_protected(r)
    ]

    payload = _out(
        {
            "open_count": len(summary),
            "open_positions": summary,
            "blocked_inst_ids_for_new_buy": blocked_buy,
            "blocked_inst_ids_for_new_sell": blocked_sell,
            "positions_missing_tpsl": missing_tpsl,
            "positions_trust": _positions_trust,
            "rules": [
                "Do NOT place new buy orders on blocked_inst_ids_for_new_buy.",
                "Do NOT place new sell orders (short add) on blocked_inst_ids_for_new_sell.",
                "If the only candidate is blocked, skip the trade this cycle.",
                "Scan the full universe and pick a different symbol or no trade.",
                "Every open position must have TP/SL. Use blofin_place_tpsl or blofin_ensure_position_tpsl if positions_missing_tpsl is non-empty.",
            ],
        }
    )
    _portfolio_cache = (now, payload)
    return payload


def blofin_get_universe_snapshot(
    inst_id: str = "", compact: str = "true", **_kwargs: object
) -> str:
    """All-asset scan. Default compact=true returns top movers only (not all 515 tickers)."""
    needle = pick_inst_id(inst_id, **_kwargs)
    snap = get_universe_feed().get_snapshot()
    if needle:
        filtered = [t for t in snap.tickers if t.get("instId") == needle]
        return json.dumps(
            {
                "source": snap.source,
                "count": len(filtered),
                "tickers": filtered,
            },
            default=str,
        )
    use_compact = str(compact).strip().lower() not in {"false", "0", "no"}
    if use_compact:
        by_vol = sorted(
            snap.tickers,
            key=lambda t: float(t.get("volCurrency24h") or 0),
            reverse=True,
        )[:12]
        return json.dumps(
            {
                "source": snap.source,
                "count": snap.count,
                "compact": True,
                "top_gainers": snap.top_gainers[:10],
                "top_losers": snap.top_losers[:10],
                "top_volume": [
                    {
                        "instId": t.get("instId"),
                        "last": t.get("last"),
                        "volCurrency24h": t.get("volCurrency24h"),
                        "chg_pct": t.get("chg_pct"),
                    }
                    for t in by_vol
                ],
                "hint": "Call with inst_id=SYMBOL-USDT for one ticker, or blofin_rank_opportunities to shortlist.",
            },
            default=str,
        )
    return snap.to_json()


def blofin_get_trade_insights(**_kwargs: object) -> str:
    """Historical trade performance from past loop cycles — use to pick better symbols."""
    from autohedge.tools.trade_journal import insights_json

    return insights_json()


def blofin_research_trading_tactics(query: str = "", **_kwargs: object) -> str:
    """Search the internet for perpetual-futures trading tactics; results persist in playbook."""
    from autohedge.tactics_learner import research_tactics_online

    q = query.strip() or None
    return json.dumps(research_tactics_online(q), default=str)


def blofin_get_learned_tactics(**_kwargs: object) -> str:
    """Return the persistent tactics playbook (internet + journal + cross-check lessons)."""
    from autohedge.tactics_learner import tactics_playbook_json

    return tactics_playbook_json()


def blofin_get_swarm_learning_report(**_kwargs: object) -> str:
    """What did the swarm last learn, improve, and fix autonomously? Includes proof."""
    from autohedge.swarm_learning_audit import learning_report_json

    return learning_report_json()


def blofin_get_self_heal_playbook(**_kwargs: object) -> str:
    """Fix-once-teach-forever playbook — what the swarm auto-heals without rediscovery."""
    from autohedge.self_heal_playbook import playbook_json

    return playbook_json()


def blofin_get_stack_health(**_kwargs: object) -> str:
    """Operational health snapshot for Ops-Monitor agent: caches, feeds, errors, equity."""
    import time as _time
    from pathlib import Path

    out_dir = Path(os.environ.get("OUTPUT_DIR", "outputs"))
    ws = out_dir / "ws-tickers.json"
    state = out_dir / "owl-state.json"
    logf = out_dir / "owl-llm.log"
    health: dict[str, Any] = {"ts": _time.time()}

    if ws.is_file():
        health["ws_cache_age_sec"] = round(_time.time() - ws.stat().st_mtime, 1)
    if state.is_file():
        try:
            health["state"] = json.loads(state.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            health["state_error"] = "parse_failed"
    if logf.is_file():
        try:
            lines = logf.read_text(encoding="utf-8", errors="replace").splitlines()
            health["last_log_lines"] = lines[-8:]
        except OSError:
            pass

    try:
        from autohedge.tools.blofin_universe_feed import get_universe_feed

        snap = get_universe_feed().get_snapshot()
        health["universe"] = {"count": snap.count, "source": snap.source, "age_sec": round(_time.time() - snap.updated_at, 1)}
    except Exception as exc:
        health["universe_error"] = str(exc)

    try:
        health["portfolio"] = json.loads(blofin_assess_portfolio())
    except Exception as exc:
        health["portfolio_error"] = str(exc)

    try:
        health["equity"] = json.loads(blofin_get_equity_summary())
    except Exception as exc:
        health["equity_error"] = str(exc)

    try:
        from autohedge.swarm_learning_audit import get_learning_report

        health["learning"] = {
            "last_learned": (get_learning_report().get("last_learned") or {}).get("title"),
            "last_self_fix": (get_learning_report().get("last_self_fix") or {}).get("title"),
        }
    except Exception:
        pass

    return _out(health)


def blofin_list_all_instruments(**_kwargs: object) -> str:
    """List every live Blofin perpetual instrument (instId, minSize, tickSize)."""
    instruments = get_blofin_client().list_live_instruments()
    summary = [
        {
            "instId": i.get("instId"),
            "minSize": i.get("minSize"),
            "tickSize": i.get("tickSize"),
            "maxLeverage": i.get("maxLeverage"),
        }
        for i in instruments
    ]
    return _out({"count": len(summary), "instruments": summary})


def blofin_get_account_balances(**_kwargs: object) -> str:
    """Futures account balances on Blofin."""
    return _out(get_blofin_client().get_balances())


def blofin_get_positions(inst_id: str = "", **_kwargs: object) -> str:
    """Open positions. Pass inst_id like BTC-USDT or leave empty for all."""
    inst = pick_inst_id(inst_id, **_kwargs) or None
    return _out(get_blofin_client().get_positions(inst))


def blofin_get_ticker(inst_id: str = "", **_kwargs: object) -> str:
    """Latest ticker for a Blofin instrument (e.g. BTC-USDT)."""
    inst = pick_inst_id(inst_id, **_kwargs)
    if not inst:
        raise ValueError("inst_id is required, e.g. BTC-USDT")
    try:
        tickers = get_blofin_client().get_tickers(inst)
        return _out({"source": "rest", "tickers": tickers})
    except Exception as exc:
        cached = get_universe_feed().ticker_for(inst)
        if cached:
            return _out(
                {
                    "source": "universe_cache",
                    "tickers": [cached],
                    "note": f"REST ticker failed ({exc}); using cached snapshot.",
                }
            )
        raise


def blofin_place_order(
    inst_id: str,
    side: str,
    order_type: str,
    size: str,
    price: str = "",
    margin_mode: str = "",
    position_side: str = "net",
    reduce_only: str = "false",
    tp_trigger_price: str = "",
    sl_trigger_price: str = "",
    **_kwargs: object,
) -> str:
    """
    Place an order on Blofin.

    inst_id: e.g. BTC-USDT
    side: buy or sell
    order_type: market, limit, post_only, ioc, fok
    size: contracts (see minSize on instrument)
    price: required for limit/post_only (use -1 or omit for market)
    tp_trigger_price / sl_trigger_price: optional; auto-set to 2.5% TP / 1.5% SL from entry if omitted on new entries
    """
    inst = inst_id.strip()
    side_l = side.strip().lower()
    reduce = reduce_only.strip().lower() in {"true", "1", "yes"}
    tpsl: dict[str, str] | None = None

    if not reduce:
        blocked_buy, blocked_sell = _blocked_sets()
        if side_l == "buy" and inst in blocked_buy:
            msg = (
                f"REJECTED: {inst} already has an open long position. "
                "Do not add size. Pick another symbol from the universe scan or skip this cycle."
            )
            logger.warning(msg)
            from autohedge.tools.trade_journal import record_event

            record_event(
                {"type": "order_blocked", "instId": inst, "side": side_l, "msg": msg}
            )
            return _out({"code": "blocked", "msg": msg, "instId": inst})
        if side_l == "sell" and inst in blocked_sell:
            msg = (
                f"REJECTED: {inst} already has an open short position. "
                "Do not add size. Pick another symbol or skip this cycle."
            )
            logger.warning(msg)
            from autohedge.tools.trade_journal import record_event

            record_event(
                {"type": "order_blocked", "instId": inst, "side": side_l, "msg": msg}
            )
            return _out({"code": "blocked", "msg": msg, "instId": inst})

        entry_est = float(price) if price.strip() and price.strip() != "-1" else _mark_price(inst)
        tpsl = _resolve_tpsl_prices(
            inst,
            side_l,
            entry_price=entry_est,
            tp_trigger_price=tp_trigger_price,
            sl_trigger_price=sl_trigger_price,
        )

    mm = margin_mode.strip().lower() or os.environ.get(
        "BLOFIN_MARGIN_MODE", "isolated"
    ).strip().lower() or "isolated"

    result = get_blofin_client().place_order(
        inst,
        side_l,
        order_type.strip().lower(),
        size.strip(),
        price=price.strip(),
        margin_mode=mm,
        position_side=position_side.strip().lower(),
        reduce_only=reduce_only.strip().lower(),
        tp_trigger_price=tpsl["tpTriggerPrice"] if tpsl else "",
        tp_order_price=tpsl["tpOrderPrice"] if tpsl else "",
        tp_trigger_price_type=tpsl["tpTriggerPriceType"] if tpsl else "last",
        sl_trigger_price=tpsl["slTriggerPrice"] if tpsl else "",
        sl_order_price=tpsl["slOrderPrice"] if tpsl else "",
        sl_trigger_price_type=tpsl["slTriggerPriceType"] if tpsl else "last",
    )
    logger.info("blofin_place_order result: {}", result)
    if str(result.get("code", "0")) in {"0", ""} and result.get("orderId"):
        from autohedge.tools.trade_journal import record_event

        record_event(
            {
                "type": "order_placed",
                "instId": inst,
                "side": side_l,
                "size": size,
                "orderType": order_type,
                "orderId": result.get("orderId"),
                "reduceOnly": reduce,
                "tpTriggerPrice": tpsl["tpTriggerPrice"] if tpsl else None,
                "slTriggerPrice": tpsl["slTriggerPrice"] if tpsl else None,
            }
        )
        if tpsl and not reduce:
            if not _pending_tpsl_for(inst):
                fallback = json.loads(
                    blofin_place_tpsl(
                        inst_id=inst,
                        tp_trigger_price=tpsl["tpTriggerPrice"],
                        sl_trigger_price=tpsl["slTriggerPrice"],
                    )
                )
                result = {**result, "tpsl_fallback": fallback}
    return _out(result)


def blofin_get_candles(
    inst_id: str = "",
    bar: str = "1H",
    limit: str = "50",
    **_kwargs: object,
) -> str:
    """OHLCV candlesticks for technical analysis. bar: 1m, 15m, 1H, 4H, 1D."""
    inst = pick_inst_id(inst_id, **_kwargs)
    if not inst:
        raise ValueError("inst_id is required")
    cap = str(min(100, max(20, int(limit or 50))))
    try:
        rows = get_blofin_client().get_candles(inst, bar=bar, limit=cap)
    except Exception as exc:
        if "403" not in str(exc):
            raise
        logger.warning("get_candles WAF for {} — returning empty candles (proxy fallback)", inst)
        return _out(
            {
                "instId": inst,
                "bar": bar,
                "count": 0,
                "candles": [],
                "error": "waf_blocked",
                "msg": "Candle API WAF-blocked; Risk gate will use rank-momentum fallback",
            }
        )
    # Return tail only — keeps LLM context small
    tail = rows[-30:] if len(rows) > 30 else rows
    return _out({"instId": inst, "bar": bar, "count": len(tail), "candles": tail})


def blofin_get_funding_rate(inst_id: str = "", **_kwargs: object) -> str:
    """Current funding rate + crowding bias (contrarian signal). Requires inst_id (e.g. BLESS-USDT)."""
    inst = pick_inst_id(inst_id, **_kwargs)
    if not inst:
        return _out(
            {
                "error": "inst_id is required",
                "hint": "Call with inst_id='SYMBOL-USDT' (aliases: instId, symbol, instrument).",
            }
        )
    from autohedge.tools.market_analytics import funding_bias

    try:
        row = get_blofin_client().get_funding_rate(inst)
        rate = float(row.get("fundingRate") or 0)
    except Exception as exc:
        logger.warning("funding rate WAF for {}: {}", inst, exc)
        row = {"instId": inst, "fundingRate": "0", "source": "waf_fallback"}
        rate = 0.0
    return _out({"instId": inst, **row, "analysis": funding_bias(rate)})


def blofin_get_order_book(inst_id: str = "", size: str = "20", **_kwargs: object) -> str:
    """Order book snapshot + bid/ask imbalance."""
    inst = pick_inst_id(inst_id, **_kwargs)
    if not inst:
        raise ValueError("inst_id is required")
    from autohedge.tools.market_analytics import order_book_imbalance

    book = get_blofin_client().get_order_book(inst, size=size)
    return _out({"instId": inst, "book": book, "imbalance": order_book_imbalance(book)})


def blofin_get_instrument_specs(inst_id: str = "", **_kwargs: object) -> str:
    """minSize, lotSize, tickSize, maxLeverage for sizing orders."""
    inst = pick_inst_id(inst_id, **_kwargs)
    if not inst:
        raise ValueError("inst_id is required")
    row = get_blofin_client().get_instrument(inst)
    if not row:
        return _out({"code": "error", "msg": f"Unknown instrument {inst_id}"})
    return _out(
        {
            "instId": row.get("instId"),
            "minSize": row.get("minSize"),
            "lotSize": row.get("lotSize"),
            "tickSize": row.get("tickSize"),
            "maxLeverage": row.get("maxLeverage"),
            "contractValue": row.get("contractValue"),
        }
    )


def blofin_technical_analysis(
    inst_id: str = "",
    bar: str = "1H",
    limit: str = "100",
    **_kwargs: object,
) -> str:
    """RSI, EMA trend, ATR volatility, Bollinger, support/resistance, long/short scores."""
    inst = pick_inst_id(inst_id, **_kwargs)
    if not inst:
        raise ValueError("inst_id is required")
    from autohedge.tools.market_analytics import technical_analysis, ticker_proxy_analysis

    client = get_blofin_client()
    funding_rate: float | None = None
    try:
        fr = client.get_funding_rate(inst)
        funding_rate = float(fr.get("fundingRate") or 0)
    except Exception:
        funding_rate = None
    try:
        candles = client.get_candles(inst, bar=bar, limit=limit)
        analysis = technical_analysis(candles, funding_rate=funding_rate)
    except Exception as exc:
        if "403" not in str(exc):
            raise
        logger.warning("candles WAF for {} — using 24h ticker proxy", inst)
        ticker_row = get_universe_feed().ticker_for(inst)
        if not ticker_row:
            try:
                rows = client.get_tickers(inst)
                ticker_row = rows[0] if rows else None
            except Exception:
                ticker_row = None
        if not ticker_row:
            return _out(
                {
                    "instId": inst,
                    "bar": bar,
                    "error": "waf_no_candle_or_ticker",
                    "msg": str(exc),
                }
            )
        analysis = ticker_proxy_analysis(ticker_row, funding_rate=funding_rate)
    return _out({"instId": inst, "bar": bar, **analysis})


def blofin_rank_opportunities(
    top_n: str = "",
    side: str = "",
    **_kwargs: object,
) -> str:
    """
    Rank tradable USDT perps by momentum, volume, and journal history.
    Scans the full universe feed by default (OWL_UNIVERSE_SCAN_ALL=1).
    Excludes symbols with open positions. Use before picking a trade.
    """
    from autohedge.tools.market_analytics import rank_from_tickers, resolve_rank_top_n
    from autohedge.tools.trade_journal import symbol_stats

    blocked_buy, blocked_sell = _blocked_sets()
    blocked = blocked_buy | blocked_sell
    snap = get_universe_feed().get_snapshot()
    if str(top_n or "").strip():
        n = max(0, int(top_n))
    else:
        n = resolve_rank_top_n()
    ranked = rank_from_tickers(
        snap.tickers,
        blocked=blocked,
        journal_stats=symbol_stats(),
        top_n=n,
    )
    if side.strip().lower() == "long":
        ranked.sort(key=lambda r: r["long_score"], reverse=True)
    elif side.strip().lower() == "short":
        ranked.sort(key=lambda r: r["short_score"], reverse=True)
    return _out(
        {
            "count": len(ranked),
            "universe_instruments": snap.count,
            "scan_mode": "full_universe" if not n else f"top_{n}",
            "blocked_count": len(blocked),
            "opportunities": ranked,
            "hint": "Full-universe rank from live feed; pick best unheld symbol and confirm with blofin_technical_analysis.",
        }
    )


def blofin_compute_position_size(
    inst_id: str,
    entry_price: str = "",
    stop_price: str = "",
    risk_pct: str = "1.0",
    **_kwargs: object,
) -> str:
    """Risk-based contract size from account equity and stop distance."""
    from autohedge.tools.market_analytics import compute_position_size

    inst = inst_id.strip()
    specs = get_blofin_client().get_instrument(inst) or {}
    min_size = float(specs.get("minSize") or 0.1)
    lot_size = float(specs.get("lotSize") or min_size)
    balances = get_blofin_client().get_balances()
    equity, _ = _parse_equity(balances)

    entry = float(entry_price) if entry_price.strip() else _mark_price(inst)
    stop = float(stop_price) if stop_price.strip() else entry * 0.985
    risk = float(risk_pct or 1.0) / 100.0
    result = compute_position_size(
        equity_usdt=equity,
        risk_pct=risk,
        entry=entry,
        stop=stop,
        min_size=min_size,
        lot_size=lot_size,
        contract_value=float(specs.get("contractValue") or 1),
    )
    return _out({"instId": inst, "equity_usdt": equity, **result})


def _save_equity_disk(equity: float, available: float) -> None:
    try:
        _EQUITY_DISK_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _EQUITY_DISK_CACHE.write_text(
            json.dumps(
                {
                    "updated_at": time.time(),
                    "equity_usdt": equity,
                    "available_usdt": available,
                }
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not persist equity cache: {}", exc)


def _load_equity_disk() -> tuple[float, float] | None:
    if not _EQUITY_DISK_CACHE.is_file():
        return None
    try:
        data = json.loads(_EQUITY_DISK_CACHE.read_text(encoding="utf-8"))
        updated = float(data.get("updated_at") or 0)
        if time.time() - updated > _EQUITY_DISK_MAX_AGE_SEC:
            return None
        equity = float(data.get("equity_usdt") or 0)
        available = float(data.get("available_usdt") or equity)
        if equity <= 0:
            return None
        logger.info(
            "Using equity disk cache (equity={:.4f} available={:.4f}, {}s old)",
            equity,
            available,
            int(time.time() - updated),
        )
        return equity, available
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Could not load equity disk cache: {}", exc)
        return None


def _parse_equity(balances: dict) -> tuple[float, float]:
    """USDT futures wallet: equityUsd + availableEquity from details row."""
    equity = 0.0
    available = 0.0
    details = balances.get("details")
    if isinstance(details, list) and details:
        row = details[0]
        equity = float(row.get("equityUsd") or row.get("equity") or 0)
        available = float(row.get("availableEquity") or row.get("available") or 0)
    if equity <= 0:
        for key in ("totalEquity", "equity"):
            if key in balances and balances.get(key) not in (None, ""):
                equity = float(balances.get(key) or 0)
                break
    if available <= 0:
        for key in ("availableEquity", "available"):
            if key in balances and balances.get(key) not in (None, ""):
                available = float(balances.get(key) or 0)
                break
    return equity, available


def order_notional_usdt(
    specs: dict[str, Any], *, size: float, entry: float
) -> float:
    """USDT notional for linear perps: size × contractValue × price."""
    contract_value = float(specs.get("contractValue") or 1)
    return size * contract_value * entry


def estimate_initial_margin(
    specs: dict[str, Any],
    *,
    size: float,
    entry: float,
    leverage: float = 50.0,
) -> float:
    """Initial margin using instrument contractValue and maxLeverage cap."""
    notional = order_notional_usdt(specs, size=size, entry=entry)
    max_lev = float(specs.get("maxLeverage") or leverage or 50)
    eff_lev = min(float(leverage), max_lev) if max_lev > 0 else float(leverage)
    if eff_lev <= 0:
        eff_lev = 50.0
    return notional / eff_lev


def resolve_equity(*, prefer_live: bool = True) -> tuple[float, float]:
    """Live balance with disk fallback when WAF blocks /account/balance."""
    if prefer_live:
        try:
            balances = get_blofin_client().get_balances()
            equity, available = _parse_equity(balances)
            if equity > 0:
                _save_equity_disk(equity, available)
            return equity, available
        except Exception as exc:
            logger.warning("get_balances failed: {}", exc)
    cached = _load_equity_disk()
    if cached:
        return cached
    raise RuntimeError("No live or cached equity available")


def get_account_snapshot(*, prefer_live: bool = True) -> dict[str, Any]:
    """
    Equity, available margin, and open positions for dashboards.
    Never returns zeros when disk cache has valid data (survives Blofin 429).
    """
    equity = 0.0
    available = 0.0
    positions: list[dict[str, Any]] = []
    source = "unknown"

    try:
        equity, available = resolve_equity(prefer_live=prefer_live)
        source = "live"
    except Exception as exc:
        logger.debug("resolve_equity failed: {}", exc)
        cached = _load_equity_disk()
        if cached:
            equity, available = cached
            source = "equity_disk"

    if equity <= 0:
        curve_path = Path(__file__).resolve().parents[2] / "outputs" / "equity_curve.jsonl"
        owl_curve = Path(os.environ.get("OWL_SWARM_ROOT", r"C:\Users\mknig\owl-swarm")) / "outputs" / "equity_curve.jsonl"
        for path in (owl_curve, curve_path):
            if not path.is_file():
                continue
            try:
                for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]):
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    eq = float(row.get("equity") or 0)
                    av = float(row.get("available") or 0)
                    if eq > 0:
                        equity, available = eq, av if av > 0 else eq
                        source = "equity_curve"
                        break
            except OSError:
                continue
            if equity > 0:
                break

    try:
        positions = _open_position_rows(retries=2) or []
        if positions:
            source = f"{source}+positions" if source != "unknown" else "positions"
    except Exception as exc:
        logger.debug("positions live failed: {}", exc)

    if not positions:
        disk = _load_positions_disk()
        if disk:
            positions, _trust = disk
            source = f"{source}+pos_disk" if source != "unknown" else "pos_disk"

    return {
        "equity": equity,
        "available": available,
        "positions": positions,
        "source": source,
        "account_ts": int(time.time()),
    }


def ensure_trade_leverage(inst: str, specs: dict[str, Any], *, target: float | None = None) -> int:
    """Set leverage before entry so margin matches gate assumptions."""
    import os

    margin_mode = os.environ.get("BLOFIN_MARGIN_MODE", "isolated").strip().lower() or "isolated"
    if target is None:
        try:
            target = float(os.environ.get("OWL_MAX_LEVERAGE", "12"))
        except (TypeError, ValueError):
            target = 12.0
    max_lev = int(float(specs.get("maxLeverage") or target or 12))
    lev = max(1, min(int(target), max_lev))
    try:
        get_blofin_client().set_leverage(inst, lev, margin_mode=margin_mode)
        logger.info("Set leverage {}x {} for {}", lev, margin_mode, inst)
    except Exception as exc:
        logger.warning("set_leverage failed for {} ({}x {}): {}", inst, lev, margin_mode, exc)
    return lev


def blofin_get_equity_summary(**_kwargs: object) -> str:
    """Account equity, available margin, and min-size affordability at 50x."""
    balances = get_blofin_client().get_balances()
    equity, available = _parse_equity(balances)
    leverage = 50.0
    sample_margin = None
    try:
        specs = get_blofin_client().get_instrument("XPL-USDT") or {}
        min_size = float(specs.get("minSize") or 1)
        price = _mark_price("XPL-USDT")
        sample_margin = round(
            estimate_initial_margin(specs, size=min_size, entry=price, leverage=leverage),
            6,
        )
    except Exception:
        pass
    return _out(
        {
            "equity_usdt": equity,
            "available_usdt": available,
            "assumed_leverage": leverage,
            "example_min_margin_xpl_usdt": sample_margin,
            "raw": balances,
            "guidance": (
                f"At {int(leverage)}x cross margin, initial margin is roughly notional/{int(leverage)}. "
                "Small accounts can open minimum-size alt perps when available_usdt covers that margin. "
                "Do NOT veto trades solely because equity < $10; use blofin_execute_minimum_trade."
            ),
        }
    )


def blofin_execute_minimum_trade(
    inst_id: str,
    side: str = "buy",
    tp_trigger_price: str = "",
    sl_trigger_price: str = "",
    size: str = "",
    **_kwargs: object,
) -> str:
    """
    Place market entry with TP/SL in one call.
    If `size` is provided, use it; otherwise fall back to instrument minSize.
    Execution agent: call this once with inst_id/side from Risk — do not loop on get_ticker.
    """
    inst = pick_inst_id(inst_id, **_kwargs)
    side_l = side.strip().lower()
    if side_l not in {"buy", "sell"}:
        return _out({"code": "error", "msg": f"invalid side: {side}"})

    specs = get_blofin_client().get_instrument(inst) or {}
    min_size = str(specs.get("minSize") or "0.1")
    tick = float(specs.get("tickSize") or 0.0001)
    entry = _mark_price(inst)

    ensure_trade_leverage(inst, specs)

    tp = tp_trigger_price.strip()
    sl = sl_trigger_price.strip()
    if not tp or not sl:
        defaults = default_tpsl_for_side(entry, side_l, tick=tick)
        tp = tp or defaults["tpTriggerPrice"]
        sl = sl or defaults["slTriggerPrice"]

    order_size = size.strip() if size and size.strip() else min_size

    order_raw = blofin_place_order(
        inst_id=inst,
        side=side_l,
        order_type="market",
        size=order_size,
        tp_trigger_price=tp,
        sl_trigger_price=sl,
    )
    order = json.loads(order_raw)
    pending = json.loads(blofin_get_pending_tpsl(inst_id=inst))
    return _out(
        {
            "instId": inst,
            "side": side_l,
            "size": min_size,
            "entry_ref": entry,
            "tp_trigger_price": tp,
            "sl_trigger_price": sl,
            "order": order,
            "pending_tpsl": pending,
        }
    )


def blofin_close_position(inst_id: str = "", margin_mode: str = "cross", **_kwargs: object) -> str:
    """Market-close an entire open position."""
    if not inst_id or not inst_id.strip():
        raise ValueError("inst_id is required")
    result = get_blofin_client().close_position(inst_id.strip(), margin_mode=margin_mode)
    return _out(result)


def blofin_cancel_order(order_id: str = "", inst_id: str = "", **_kwargs: object) -> str:
    """Cancel an open Blofin order by orderId."""
    if not order_id or not order_id.strip():
        raise ValueError("order_id is required")
    inst = inst_id.strip() or None
    return _out(get_blofin_client().cancel_order(order_id.strip(), inst))
