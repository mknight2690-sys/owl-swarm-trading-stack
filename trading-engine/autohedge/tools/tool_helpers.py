"""Shared helpers for Blofin agent tools."""

from __future__ import annotations

import json
import time
from typing import Any

_KWARG_ALIASES: dict[str, tuple[str, ...]] = {
    "inst_id": ("instId", "instid", "instrument", "instrument_id", "symbol", "ticker"),
    "order_id": ("orderId", "orderid"),
    "top_n": ("topN", "limit", "n"),
    "bar": ("timeframe", "interval"),
    "risk_pct": ("risk_percent", "risk"),
    "entry_price": ("entry", "price"),
    "stop_price": ("stop", "sl", "stop_loss"),
    "tp_trigger_price": ("tp", "take_profit", "tp_price"),
    "sl_trigger_price": ("sl_trigger", "stop_loss_price"),
}


def normalize_tool_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Map common LLM argument spellings to our tool parameter names."""
    out = dict(kwargs)
    for canonical, aliases in _KWARG_ALIASES.items():
        if canonical in out and out[canonical] not in (None, ""):
            continue
        for alias in aliases:
            val = out.pop(alias, None)
            if val is not None and str(val).strip() != "":
                out[canonical] = val
                break
    return out


def pick_inst_id(inst_id: str = "", **kwargs: Any) -> str:
    normalized = normalize_tool_kwargs({"inst_id": inst_id, **kwargs})
    return str(normalized.get("inst_id") or "").strip()


_portfolio_cache: tuple[float, str] | None = None
PORTFOLIO_CACHE_TTL = 20.0


def invalidate_portfolio_cache() -> None:
    global _portfolio_cache
    _portfolio_cache = None


def get_portfolio_json(force: bool = False) -> str:
    """Cached portfolio assessment to cut duplicate API work per cycle."""
    global _portfolio_cache
    from autohedge.tools.trade_journal import sync_position_closes

    now = time.time()
    if (
        not force
        and _portfolio_cache
        and (now - _portfolio_cache[0]) < PORTFOLIO_CACHE_TTL
    ):
        return _portfolio_cache[1]

    sync_position_closes()
    from autohedge.tools.blofin_client import BlofinClient

    client = BlofinClient()
    open_rows: list[dict] = []
    for row in client.get_positions():
        try:
            size = float(row.get("positions") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if row.get("instId") and abs(size) > 0:
            open_rows.append(row)

    blocked_buy: list[str] = []
    blocked_sell: list[str] = []
    summary: list[dict] = []
    missing_tpsl: list[str] = []

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
        try:
            pending = client.get_pending_tpsl(inst)
            if not pending:
                missing_tpsl.append(inst)
        except Exception:
            missing_tpsl.append(inst)

    payload = {
        "open_count": len(summary),
        "open_positions": summary,
        "blocked_inst_ids_for_new_buy": blocked_buy,
        "blocked_inst_ids_for_new_sell": blocked_sell,
        "positions_missing_tpsl": missing_tpsl,
        "rules": [
            "Do NOT place new buy orders on blocked_inst_ids_for_new_buy.",
            "Do NOT place new sell orders (short add) on blocked_inst_ids_for_new_sell.",
            "If the only candidate is blocked, skip the trade this cycle.",
            "Scan the full universe and pick a different symbol or no trade.",
            "Every open position must have TP/SL.",
        ],
    }
    text = json.dumps(payload, default=str)
    _portfolio_cache = (now, text)
    return text


def portfolio_summary_text(portfolio_json: str) -> str:
    """Compact one-line-per-position summary for cycle prompts."""
    try:
        data = json.loads(portfolio_json)
    except json.JSONDecodeError:
        return portfolio_json[:500]
    lines = [
        f"open={data.get('open_count', 0)} blocked_buy={data.get('blocked_inst_ids_for_new_buy', [])} "
        f"missing_tpsl={data.get('positions_missing_tpsl', [])}"
    ]
    for pos in data.get("open_positions") or []:
        lines.append(
            f"  {pos.get('instId')} {pos.get('side')} size={pos.get('positions')} "
            f"upnl={pos.get('unrealizedPnl')}"
        )
    return "\n".join(lines)
