"""
Live equity stream — mark-to-market from WS tickers + live/cached positions.

Dashboard equity and open positions tick every 500ms; live REST reconciles
opens/closes every ~2s so manual closes show up quickly.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

OWL_ROOT = Path(os.environ.get("OWL_SWARM_ROOT", r"C:\Users\mknig\owl-swarm"))
AUTO_TRADER_ROOT = Path(os.environ.get("AUTO_TRADER_ROOT", r"C:\Users\mknig\blofin-auto-trader"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", OWL_ROOT / "outputs"))
LIVE_FILE = OUTPUT_DIR / "owl-live.json"
STATE_FILE = OUTPUT_DIR / "owl-state.json"
WS_TICKERS = OUTPUT_DIR / "ws-tickers.json"
POSITIONS_CACHE = AUTO_TRADER_ROOT / "outputs" / "positions-cache.json"
EQUITY_CURVE = OUTPUT_DIR / "equity_curve.jsonl"
STREAM_STATE = OUTPUT_DIR / "equity_stream_state.json"

POSITIONS_DISK_MAX_AGE_SEC = 90.0
LIVE_ACCOUNT_MIN_INTERVAL_SEC = 2.0


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _normalize_tickers(tickers_raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """ws-tickers.json stores tickers as a list; normalize to instId -> row."""
    tickers = tickers_raw.get("tickers")
    if isinstance(tickers, dict):
        return {str(k): v for k, v in tickers.items() if isinstance(v, dict)}
    if isinstance(tickers, list):
        out: dict[str, dict[str, Any]] = {}
        for row in tickers:
            if isinstance(row, dict) and row.get("instId"):
                out[str(row["instId"])] = row
        return out
    return {}


def _ws_mark(inst_id: str, tickers: dict[str, Any]) -> float:
    row = tickers.get(inst_id) or tickers.get(inst_id.replace("-USDT", "USDT"))
    if not isinstance(row, dict):
        return 0.0
    for key in ("markPrice", "last", "lastPrice", "price"):
        try:
            v = float(row.get(key) or 0)
            if v > 0:
                return v
        except (TypeError, ValueError):
            continue
    return 0.0


def _position_contract_value(pos: dict[str, Any]) -> float:
    """Blofin perp qty is contracts; uPnL needs contractValue (varies per inst)."""
    try:
        cv = float(pos.get("contractValue") or 0)
        if cv > 0:
            return cv
    except (TypeError, ValueError):
        pass
    try:
        rest_upnl = float(pos.get("unrealizedPnl") or 0)
        qty = float(pos.get("positions") or 0)
        avg = float(pos.get("averagePrice") or 0)
        mark = float(pos.get("markPrice") or 0)
    except (TypeError, ValueError):
        return 1.0
    diff = mark - avg
    if abs(diff) > 1e-15 and qty != 0:
        inferred = rest_upnl / (diff * qty)
        if inferred > 0:
            return inferred
    return 1.0


def _position_unrealized(pos: dict[str, Any], mark: float) -> float:
    if mark <= 0:
        try:
            return float(pos.get("unrealizedPnl") or 0)
        except (TypeError, ValueError):
            return 0.0
    try:
        qty = float(pos.get("positions") or 0)
        avg = float(pos.get("averagePrice") or 0)
    except (TypeError, ValueError):
        return float(pos.get("unrealizedPnl") or 0)
    if qty == 0 or avg <= 0:
        return float(pos.get("unrealizedPnl") or 0)
    cv = _position_contract_value(pos)
    return (mark - avg) * qty * cv


def _disk_positions() -> tuple[list[dict[str, Any]], float]:
    cache = _load_json(POSITIONS_CACHE, {}) or {}
    rows = list(cache.get("open_rows") or [])
    age = time.time() - float(cache.get("updated_at") or 0)
    return rows, age


def _load_base_balances(
    live: dict[str, Any],
    state: dict[str, Any],
    *,
    live_equity: float = 0.0,
    live_available: float = 0.0,
) -> tuple[float, float]:
    """Prefer live WS-calculated equity, then current live file, then disk cache, then state."""
    if live_equity > 0:
        return live_equity, live_available
    # Try current live file (last WS-calculated equity)
    eq = float(live.get("equity") or 0)
    av = float(live.get("available") or 0)
    if eq > 0:
        return eq, av
    # Then disk cache
    eq_disk = AUTO_TRADER_ROOT / "outputs" / "equity-cache.json"
    cache = _load_json(eq_disk, {}) or {}
    try:
        eq = float(cache.get("equity_usdt") or 0)
        av = float(cache.get("available_usdt") or 0)
        if eq > 0:
            return eq, av
    except (TypeError, ValueError):
        pass
    # Finally state
    return float(state.get("equity") or 0), float(state.get("available") or 0)


def _resolve_positions_and_balances(
    fallback: list[dict[str, Any]],
    *,
    live_equity: float = 0.0,
    live_available: float = 0.0,
    force_live: bool = False,
) -> tuple[list[dict[str, Any]], float, float, str]:
    """
    Read auto-trader disk cache FIRST to avoid API rate limits.
    Only call live REST if disk cache is stale (>30s) or explicitly forced.
    """
    disk_rows, disk_age = _disk_positions()
    if disk_rows and disk_age <= 30.0 and not force_live:
        eq, av = _load_base_balances({}, {}, live_equity=live_equity, live_available=live_available)
        return disk_rows, eq, av, "pos_disk_fresh"

    # Disk cache is stale or empty — try live API (throttled)
    from blofin_live_api import fetch_live_account
    live = fetch_live_account(force=force_live, min_interval_sec=LIVE_ACCOUNT_MIN_INTERVAL_SEC)
    if live.get("ok"):
        positions = list(live.get("positions") or [])
        equity = float(live.get("equity") or 0)
        available = float(live.get("available") or 0)
        return positions, equity, available, str(live.get("source") or "live")

    # Live failed — fall back to disk (even if stale, up to 90s)
    if disk_rows and disk_age <= POSITIONS_DISK_MAX_AGE_SEC:
        eq, av = _load_base_balances({}, {}, live_equity=live_equity, live_available=live_available)
        return disk_rows, eq, av, "pos_disk"

    if fallback:
        eq, av = _load_base_balances({}, {}, live_equity=live_equity, live_available=live_available)
        return list(fallback), eq, av, "owl_live_fallback"

    return [], 0.0, 0.0, "unknown"


def refresh_streaming_equity(*, write_curve: bool = True, force_live: bool = False) -> dict[str, Any]:
    """
    Update owl-live.json equity from WS marks + live positions.
    Returns snapshot meta.
    """
    live = _load_json(LIVE_FILE, {}) or {}
    state = _load_json(STATE_FILE, {}) or {}
    stream = _load_json(STREAM_STATE, {}) or {}

    positions, live_equity, live_available, pos_source = _resolve_positions_and_balances(
        list(live.get("positions") or []),
        live_equity=float(live.get("equity") or 0),
        live_available=float(live.get("available") or 0),
        force_live=force_live,
    )
    base_equity, available = _load_base_balances(
        live,
        state,
        live_equity=live_equity,
        live_available=live_available,
    )
    if live_available > 0:
        available = live_available

    tickers_raw = _load_json(WS_TICKERS, {}) or {}
    tickers = _normalize_tickers(tickers_raw)

    rest_unreal = sum(float(p.get("unrealizedPnl") or 0) for p in positions)
    stream_unreal = 0.0
    updated_positions: list[dict[str, Any]] = []
    for pos in positions:
        inst = str(pos.get("instId") or "")
        mark = _ws_mark(inst, tickers) or float(pos.get("markPrice") or 0)
        upnl = _position_unrealized(pos, mark)
        stream_unreal += upnl
        row = dict(pos)
        if mark > 0:
            row["markPrice"] = mark
        # Keep Blofin's actual unrealizedPnl — do NOT overwrite with WS-derived calculation.
        # The WS-derived unrealized is only used for equity curve smoothing above.
        updated_positions.append(row)

    if base_equity > 0 and positions:
        equity = base_equity - rest_unreal + stream_unreal
    elif base_equity > 0:
        equity = base_equity
    else:
        equity = 0.0

    now = time.time()
    account_source = "ws_stream" if positions else pos_source
    meta = {
        "equity": round(equity, 8),
        "available": round(available, 8),
        "positions": updated_positions,
        "account_ts": int(now),
        "account_source": account_source,
        "stream_unrealized": round(stream_unreal, 8),
        "position_count": len(updated_positions),
        "ws_age_sec": round(now - float(tickers_raw.get("updated_at") or tickers_raw.get("ts") or 0), 1),
    }

    if equity > 0 or not updated_positions:
        live.update(meta)
        live["updated_at"] = int(now)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        LIVE_FILE.write_text(json.dumps(live, indent=2, default=str), encoding="utf-8")
        if equity > 0:
            state["equity"] = equity
            state["available"] = available
            STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

    prev_eq = float(stream.get("last_equity") or 0)
    if write_curve and equity > 0 and (
        prev_eq == 0
        or abs(equity - prev_eq) > 1e-8
        or now - float(stream.get("last_curve_at") or 0) >= 5
    ):
        point = {
            "ts": now,
            "cycle": int(live.get("cycle") or state.get("cycle") or 0),
            "equity": round(equity, 6),
            "available": round(available, 6),
            "source": account_source,
        }
        with EQUITY_CURVE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(point) + "\n")
        stream["last_curve_at"] = now
        stream["last_equity"] = equity

    stream["last_tick_at"] = now
    stream["last_equity"] = equity
    stream["position_count"] = len(updated_positions)
    STREAM_STATE.write_text(json.dumps(stream, indent=2, default=str), encoding="utf-8")
    return meta


def read_live_snapshot() -> dict[str, Any]:
    """Fast read for /api/positions — no REST, no file writes."""
    live = _load_json(LIVE_FILE, {}) or {}
    return {
        "equity": float(live.get("equity") or 0),
        "available": float(live.get("available") or 0),
        "positions": live.get("positions") or [],
        "account_ts": int(live.get("account_ts") or 0),
        "account_source": live.get("account_source", ""),
        "position_count": len(live.get("positions") or []),
        "stream_unrealized": live.get("stream_unrealized"),
        "updated_at": int(live.get("updated_at") or 0),
    }


def equity_stream_healthy(*, max_age_sec: float = 15.0) -> dict[str, Any]:
    """True when streaming equity ticked recently (monitor/overseer)."""
    stream = _load_json(STREAM_STATE, {}) or {}
    last = float(stream.get("last_tick_at") or 0)
    age = time.time() - last if last else 9999.0
    return {
        "ok": age <= max_age_sec and float(stream.get("last_equity") or 0) > 0,
        "age_sec": round(age, 1),
        "last_equity": stream.get("last_equity"),
        "position_count": stream.get("position_count"),
    }
