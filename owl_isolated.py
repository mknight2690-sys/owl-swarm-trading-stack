"""Force isolated margin + conservative leverage for OWL Swarm (prevents cross liquidation)."""

from __future__ import annotations

import os

MARGIN_MODE = os.getenv("BLOFIN_MARGIN_MODE", "isolated").strip().lower() or "isolated"
MAX_LEVERAGE = int(os.getenv("OWL_MAX_LEVERAGE", "12"))
DEFAULT_LEVERAGE = int(os.getenv("OWL_DEFAULT_LEVERAGE", "8"))


def apply_isolated_patches() -> None:
    """Patch autohedge Blofin tools to use isolated margin before agents load."""
    os.environ["BLOFIN_MARGIN_MODE"] = MARGIN_MODE

    import autohedge.tools.blofin_tools as bt

    if getattr(bt, "_owl_isolated_patched", False):
        return

    def _iso(mode: str) -> str:
        m = (mode or "").strip().lower()
        return MARGIN_MODE if m in ("", "cross") else m

    _orig_place_order = bt.blofin_place_order
    _orig_place_tpsl = bt.blofin_place_tpsl
    _orig_close = bt.blofin_close_position
    _orig_ensure_lev = bt.ensure_trade_leverage

    def blofin_place_order(*args, margin_mode: str = "cross", **kwargs):
        return _orig_place_order(*args, margin_mode=_iso(margin_mode), **kwargs)

    def blofin_place_tpsl(*args, margin_mode: str = "cross", **kwargs):
        return _orig_place_tpsl(*args, margin_mode=_iso(margin_mode), **kwargs)

    def blofin_close_position(inst_id: str = "", margin_mode: str = "cross", **_kwargs):
        return _orig_close(inst_id, margin_mode=_iso(margin_mode), **_kwargs)

    def ensure_trade_leverage(inst: str, specs, *, target: float = 50.0) -> int:
        cap = min(MAX_LEVERAGE, int(float(specs.get("maxLeverage") or MAX_LEVERAGE)))
        use = min(cap, max(2, int(target or DEFAULT_LEVERAGE)))
        if use > MAX_LEVERAGE:
            use = MAX_LEVERAGE
        try:
            bt.get_blofin_client().set_leverage(inst, use, margin_mode=MARGIN_MODE)
        except Exception as exc:
            from loguru import logger
            logger.warning("set_leverage isolated {}x {}: {}", use, inst, exc)
        return use

    bt.blofin_place_order = blofin_place_order
    bt.blofin_place_tpsl = blofin_place_tpsl
    bt.blofin_close_position = blofin_close_position
    bt.ensure_trade_leverage = ensure_trade_leverage
    bt._owl_isolated_patched = True


ISOLATED_DIRECTOR_RULES = """
CRITICAL RULES (OVERRIDE any cross-margin assumptions):
- ISOLATED MARGIN ONLY on every order, TP/SL, and close. Never use cross margin.
- Dynamic leverage: choose 3-12x based on ATR/volatility and account size. Hard cap 15x.
- Small account (<$5): max ONE open position, max 10x leverage.
- EVERY entry must have TP and SL before cycle ends.
- Liquidation buffer: at chosen leverage, stop loss must trigger well before liquidation price.
- Do not add to existing positions. One symbol per cycle unless Risk vetoes.
- Use blofin_get_trade_insights every cycle — learn from wins/losses.
"""
