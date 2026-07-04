"""Take-profit / stop-loss price helpers for Blofin orders."""

from __future__ import annotations

import os


def round_to_tick(value: float, tick: float) -> str:
    if tick <= 0:
        return f"{value:.4f}".rstrip("0").rstrip(".")
    rounded = round(round(value / tick) * tick, 10)
    decimals = max(0, len(str(tick).split(".")[-1].rstrip("0")))
    return f"{rounded:.{decimals}f}"


def _sl_pct() -> float:
    return float(os.environ.get("OWL_SL_PCT", "0.012"))


def _tp_pct() -> float:
    return float(os.environ.get("OWL_TP_PCT", "0.036"))


def clamp_tpsl_to_book(
    tpsl: dict[str, str],
    side: str,
    *,
    best_bid: float,
    best_ask: float,
    tick: float,
) -> dict[str, str]:
    """Blofin rejects SL/TP that violate best bid/ask (e.g. 102048 on shorts)."""
    side_l = side.lower()
    out = dict(tpsl)
    try:
        sl = float(out.get("slTriggerPrice") or 0)
        tp = float(out.get("tpTriggerPrice") or 0)
    except (TypeError, ValueError):
        return out
    if side_l == "sell":
        if best_bid > 0 and sl <= best_bid:
            sl = best_bid * 1.003
            out["slTriggerPrice"] = round_to_tick(sl, tick)
        if best_bid > 0 and tp >= best_bid:
            tp = best_bid * 0.97
            out["tpTriggerPrice"] = round_to_tick(tp, tick)
    else:
        if best_ask > 0 and sl >= best_ask:
            sl = best_ask * 0.997
            out["slTriggerPrice"] = round_to_tick(sl, tick)
        if best_ask > 0 and tp <= best_ask:
            tp = best_ask * 1.03
            out["tpTriggerPrice"] = round_to_tick(tp, tick)
    return out


def default_tpsl_for_side(
    entry_price: float,
    side: str,
    *,
    tick: float = 0.1,
    sl_pct: float | None = None,
    tp_pct: float | None = None,
) -> dict[str, str]:
    """Asymmetric TP/SL: tight stop (~1.2%), target (~3.6%) for 3:1 R:R."""
    sl_pct = sl_pct if sl_pct is not None else _sl_pct()
    tp_pct = tp_pct if tp_pct is not None else _tp_pct()
    side_l = side.lower()
    if side_l == "buy":
        sl = entry_price * (1 - sl_pct)
        tp = entry_price * (1 + tp_pct)
        close_side = "sell"
    else:
        sl = entry_price * (1 + sl_pct)
        tp = entry_price * (1 - tp_pct)
        close_side = "buy"

    return {
        "close_side": close_side,
        "slTriggerPrice": round_to_tick(sl, tick),
        "slOrderPrice": "-1",
        "slTriggerPriceType": "last",
        "tpTriggerPrice": round_to_tick(tp, tick),
        "tpOrderPrice": "-1",
        "tpTriggerPriceType": "last",
    }
