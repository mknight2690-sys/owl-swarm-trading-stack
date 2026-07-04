"""Central registry of all Blofin tools — used for cross-agent fallback."""

from __future__ import annotations

from typing import Any, Callable

from autohedge.tools.blofin_tools import (
    blofin_assess_portfolio,
    blofin_cancel_order,
    blofin_close_position,
    blofin_compute_position_size,
    blofin_ensure_position_tpsl,
    blofin_execute_minimum_trade,
    blofin_get_account_balances,
    blofin_get_candles,
    blofin_get_equity_summary,
    blofin_get_funding_rate,
    blofin_get_instrument_specs,
    blofin_get_order_book,
    blofin_get_pending_tpsl,
    blofin_get_positions,
    blofin_get_ticker,
    blofin_get_trade_insights,
    blofin_get_universe_snapshot,
    blofin_list_all_instruments,
    blofin_place_order,
    blofin_place_tpsl,
    blofin_rank_opportunities,
    blofin_technical_analysis,
)
from autohedge.tools.crypto_sentiment import crypto_news_search

BLOFIN_TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "blofin_assess_portfolio": blofin_assess_portfolio,
    "blofin_cancel_order": blofin_cancel_order,
    "blofin_close_position": blofin_close_position,
    "blofin_compute_position_size": blofin_compute_position_size,
    "blofin_execute_minimum_trade": blofin_execute_minimum_trade,
    "blofin_ensure_position_tpsl": blofin_ensure_position_tpsl,
    "blofin_get_account_balances": blofin_get_account_balances,
    "blofin_get_candles": blofin_get_candles,
    "blofin_get_equity_summary": blofin_get_equity_summary,
    "blofin_get_funding_rate": blofin_get_funding_rate,
    "blofin_get_instrument_specs": blofin_get_instrument_specs,
    "blofin_get_order_book": blofin_get_order_book,
    "blofin_get_pending_tpsl": blofin_get_pending_tpsl,
    "blofin_get_positions": blofin_get_positions,
    "blofin_get_ticker": blofin_get_ticker,
    "blofin_get_trade_insights": blofin_get_trade_insights,
    "blofin_get_universe_snapshot": blofin_get_universe_snapshot,
    "blofin_list_all_instruments": blofin_list_all_instruments,
    "blofin_place_order": blofin_place_order,
    "blofin_place_tpsl": blofin_place_tpsl,
    "blofin_rank_opportunities": blofin_rank_opportunities,
    "blofin_technical_analysis": blofin_technical_analysis,
    "crypto_news_search": crypto_news_search,
}


def call_blofin_tool(name: str, arguments: dict[str, Any]) -> str:
    fn = BLOFIN_TOOL_REGISTRY.get(name)
    if fn is None:
        raise KeyError(name)
    return fn(**arguments)
