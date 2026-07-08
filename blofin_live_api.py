"""
Lightweight Blofin live account fetch for the dashboard.

Avoids importing autohedge.main (solders/Jupiter deps) while still using the
production BlofinClient signing + curl_cffi stack.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import types
from pathlib import Path
from typing import Any

AUTO_TRADER_ROOT = Path(os.environ.get("AUTO_TRADER_ROOT", os.environ.get("AUTO_TRADER_ROOT", "../blofin-auto-trader")))
POSITIONS_CACHE = AUTO_TRADER_ROOT / "outputs" / "positions-cache.json"
EQUITY_CACHE = AUTO_TRADER_ROOT / "outputs" / "equity-cache.json"

_client: Any = None
_last_fetch_ts = 0.0
_last_positions: list[dict[str, Any]] | None = None
_last_equity = 0.0
_last_available = 0.0
_last_fetch_ok = False


def _ensure_client() -> Any:
    global _client
    if _client is not None:
        return _client
    try:
        from dotenv import load_dotenv

        load_dotenv(AUTO_TRADER_ROOT / ".env", override=False)
    except Exception:
        pass
    if "autohedge.tools.blofin_client" not in sys.modules:
        # Never clobber a real autohedge package (owl_llm_loop imports AutoHedge from it).
        existing = sys.modules.get("autohedge")
        if existing is not None and getattr(existing, "__file__", None):
            from autohedge.tools.blofin_client import BlofinClient

            _client = BlofinClient()
            return _client
        try:
            import importlib

            importlib.import_module("autohedge.tools.blofin_client")
            from autohedge.tools.blofin_client import BlofinClient

            _client = BlofinClient()
            return _client
        except Exception:
            pass
        autohedge = types.ModuleType("autohedge")
        autohedge.__path__ = [str(AUTO_TRADER_ROOT / "autohedge")]
        sys.modules["autohedge"] = autohedge
        for name, rel in (
            ("autohedge.blofin_credentials", "autohedge/blofin_credentials.py"),
            ("autohedge.tools.blofin_client", "autohedge/tools/blofin_client.py"),
        ):
            path = AUTO_TRADER_ROOT / rel
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Cannot load {path}")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
    client_mod = sys.modules["autohedge.tools.blofin_client"]
    _client = client_mod.BlofinClient()
    return _client


def _parse_equity(balances: dict[str, Any]) -> tuple[float, float]:
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
            if balances.get(key) not in (None, ""):
                equity = float(balances.get(key) or 0)
                break
    if available <= 0:
        for key in ("availableEquity", "available"):
            if balances.get(key) not in (None, ""):
                available = float(balances.get(key) or 0)
                break
    return equity, available


def _open_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            size = float(row.get("positions") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if row.get("instId") and abs(size) > 0:
            out.append(row)
    return out


def _persist_positions(open_rows: list[dict[str, Any]], trust: str = "live") -> None:
    try:
        POSITIONS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        POSITIONS_CACHE.write_text(
            json.dumps(
                {"updated_at": time.time(), "trust": trust, "open_rows": open_rows},
                default=str,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def _persist_equity(equity: float, available: float) -> None:
    try:
        EQUITY_CACHE.parent.mkdir(parents=True, exist_ok=True)
        EQUITY_CACHE.write_text(
            json.dumps(
                {
                    "updated_at": time.time(),
                    "equity_usdt": equity,
                    "available_usdt": available,
                },
                default=str,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def fetch_live_account(*, force: bool = False, min_interval_sec: float = 2.0) -> dict[str, Any]:
    """
    Live positions + equity from Blofin REST.
    Throttled to avoid 429; empty list is authoritative (manual close).
    """
    global _last_fetch_ts, _last_positions, _last_equity, _last_available, _last_fetch_ok
    now = time.time()
    if (
        not force
        and _last_positions is not None
        and now - _last_fetch_ts < min_interval_sec
    ):
        return {
            "positions": list(_last_positions),
            "equity": _last_equity,
            "available": _last_available,
            "ok": _last_fetch_ok,
            "source": "live_cache",
            "fetched_at": _last_fetch_ts,
        }
    try:
        client = _ensure_client()
        rows = _open_rows(client.get_positions(retries=2))
        balances = client.get_balances()
        equity, available = _parse_equity(balances)
        _last_positions = rows
        _last_equity = equity
        _last_available = available
        _last_fetch_ok = True
        _last_fetch_ts = now
        _persist_positions(rows, "live")
        if equity > 0:
            _persist_equity(equity, available)
        return {
            "positions": rows,
            "equity": equity,
            "available": available,
            "ok": True,
            "source": "live",
            "fetched_at": now,
        }
    except Exception:
        _last_fetch_ok = False
        return {
            "positions": list(_last_positions or []),
            "equity": _last_equity,
            "available": _last_available,
            "ok": False,
            "source": "live_failed",
            "fetched_at": _last_fetch_ts,
        }
