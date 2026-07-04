"""Blofin REST client (openapi.blofin.com).

Uses curl_cffi with browser TLS fingerprint impersonation to bypass
Cloudflare WAF. Different endpoints require different TLS fingerprints
because Cloudflare scores per-endpoint; we rotate through them.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from curl_cffi import requests as cf_requests
from loguru import logger

from autohedge.blofin_credentials import BlofinCredentials, load_blofin_credentials

BASE_URL = os.getenv("BLOFIN_API_BASE", "https://openapi.blofin.com")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://blofin.com",
    "Referer": "https://blofin.com/",
    "Content-Type": "application/json",
}

# Cloudflare scores TLS fingerprints per-endpoint.
# We rotate through these to find one that works.
# Only include profiles supported by curl_cffi (chrome126/131/133 raise errors).
# chrome110 is tested working through ProtonVPN interface.
_IMPERSONATION_POOL = [
    "chrome110", "chrome120", "chrome116", "chrome124",
    "chrome", "edge101", "edge112",
]


def _public_inst_id(inst_id: str | None) -> str | None:
    """Strip -SWAP suffix for public endpoints (BloFin uses BTC-USDT not BTC-USDT-SWAP)."""
    if not inst_id:
        return None
    inst = inst_id.strip().upper()
    if inst.endswith("-SWAP"):
        return inst[:-5]
    return inst

_waf_backoff_until: float = 0.0
_WAF_BACKOFF_SEC = 15.0
_consecutive_403s: int = 0
_last_403_reset_ts: float = 0.0

# Per-endpoint circuit breaker: tracks consecutive 403s per sign_path
# After 3 consecutive 403s, skip further attempts for _CIRCUIT_RESET_SEC
_circuit_breaker: dict[str, dict] = {}  # sign_path -> {"count": int, "blocked_until": float}
_CIRCUIT_THRESHOLD = 8
_CIRCUIT_RESET_SEC = 120.0
_CIRCUIT_BREAKER_THRESHOLD: int = 10
_CIRCUIT_BREAKER_SEC: float = 30.0
_INSTRUMENTS_DISK = (
    Path(__file__).resolve().parents[2] / "outputs" / "instruments-cache.json"
)
_INSTRUMENTS_DISK_MAX_AGE_SEC = 86400.0


class BlofinClient:
    def __init__(self, credentials: BlofinCredentials | None = None) -> None:
        self.credentials = credentials or load_blofin_credentials()
        self.broker_id = os.getenv(
            "BLOFIN_BROKER_ID", "5388cb1f51cec2e3"
        ).strip()
        self._position_mode: str | None = None
        self._instruments_cache: list[dict[str, Any]] | None = None
        self._instruments_cache_ts: float = 0.0

    def _sign(self, method: str, path_with_query: str, body_str: str) -> tuple[str, str, str]:
        timestamp = str(int(time.time() * 1000))
        nonce = str(uuid4())
        prehash = f"{path_with_query}{method.upper()}{timestamp}{nonce}{body_str}"
        hex_sig = hmac.new(
            self.credentials.secret_key.encode(),
            prehash.encode(),
            hashlib.sha256,
        ).hexdigest()
        signature = base64.b64encode(hex_sig.encode()).decode()
        return timestamp, nonce, signature

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        private: bool = False,
        retries: int = 6,
    ) -> dict[str, Any]:
        params = params or {}
        query = "?" + urlencode(params) if params else ""
        sign_path = path + query
        body_str = json.dumps(body, separators=(",", ":")) if body else ""
        url = f"{BASE_URL}{sign_path}"
        last_error: Exception | None = None

        global _waf_backoff_until, _consecutive_403s, _last_403_reset_ts
        now = time.time()
        if now - _last_403_reset_ts > 60.0:
            _consecutive_403s = 0
            _last_403_reset_ts = now
        if now < _waf_backoff_until:
            wait = _waf_backoff_until - now
            logger.info("WAF global backoff: waiting {:.0f}s before {}", wait, sign_path)
            time.sleep(wait)

        # Check per-endpoint circuit breaker
        cb = _circuit_breaker.get(sign_path)
        if cb and now < cb.get("blocked_until", 0):
            logger.warning("Circuit breaker OPEN for {} — skipping ({}s remaining)",
                sign_path, cb["blocked_until"] - now)
            raise RuntimeError(f"Circuit breaker open for {sign_path} (Cloudflare rate limit)")

        for attempt in range(retries):
            headers = dict(DEFAULT_HEADERS)
            if private:
                timestamp, nonce, signature = self._sign(method, sign_path, body_str)
                headers.update(
                    {
                        "ACCESS-KEY": self.credentials.api_key,
                        "ACCESS-SIGN": signature,
                        "ACCESS-TIMESTAMP": timestamp,
                        "ACCESS-NONCE": nonce,
                        "ACCESS-PASSPHRASE": self.credentials.passphrase,
                    }
                )
            # Rotate TLS fingerprint per attempt to bypass Cloudflare
            impersonate = _IMPERSONATION_POOL[attempt % len(_IMPERSONATION_POOL)]
            headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
            try:
                # Bind to ProtonVPN interface to route through VPN's clean IP
                resp = cf_requests.request(
                    method.upper(),
                    url,
                    headers=headers,
                    data=body_str if body else None,
                    timeout=30,
                    impersonate=impersonate,
                    interface="10.2.0.2",
                )
            except Exception as exc:
                logger.warning("curl_cffi error on {} ({}): {}", sign_path, impersonate, exc)
                last_error = exc
                time.sleep(1.0 * (attempt + 1))
                continue

            if resp.status_code == 403:
                _consecutive_403s += 1
                # Track per-endpoint circuit breaker
                cb = _circuit_breaker.setdefault(sign_path, {"count": 0, "blocked_until": 0})
                cb["count"] += 1
                if cb["count"] >= _CIRCUIT_THRESHOLD:
                    cb["blocked_until"] = time.time() + _CIRCUIT_RESET_SEC
                    logger.warning("Circuit breaker TRIPPED for {} ({} consecutive 403s)",
                        sign_path, cb["count"])
                # Global backoff: if too many total 403s, IP is flagged — wait longer
                if _consecutive_403s >= 5:  # ← FIX: was 9999 (never triggered); now 5 triggers 30s backoff
                    _waf_backoff_until = time.time() + 30.0
                    logger.warning("WAF IP backoff: 30s global pause ({} consecutive 403s)",
                        _consecutive_403s)
                logger.warning(
                    "403 on {} (impersonate={}) — rotating TLS fingerprint",
                    sign_path, impersonate,
                )
                last_error = RuntimeError(f"HTTP 403 {sign_path} (Cloudflare)")
                # Cloudflare rate-limits per-endpoint; short backoff (circuit breaker handles sustained blocks)
                time.sleep(0.5 * (attempt + 1))
                continue
            # Reset circuit breaker on success
            if sign_path in _circuit_breaker:
                _circuit_breaker[sign_path] = {"count": 0, "blocked_until": 0}
            _consecutive_403s = 0
            if resp.status_code == 429:
                wait = 2.5 * (attempt + 1)
                logger.warning(
                    "429 rate limit on {} — retry in {:.1f}s (attempt {})",
                    sign_path,
                    wait,
                    attempt + 1,
                )
                time.sleep(wait)
                last_error = RuntimeError(f"HTTP 429 {sign_path}: {resp.text[:200]}")
                continue
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"HTTP {resp.status_code} {sign_path}: {resp.text[:500]}"
                )
            try:
                payload = resp.json()
            except Exception as exc:
                raise RuntimeError(
                    f"Non-JSON response {sign_path}: {resp.text[:200]}"
                ) from exc
            code = str(payload.get("code", ""))
            if code not in {"0", "200"}:
                raise RuntimeError(
                    f"Blofin API error {code}: {payload.get('msg')} ({sign_path}) "
                    f"data={payload.get('data')}"
                )
            return payload

        raise last_error or RuntimeError(f"Failed after {retries} retries: {sign_path}")

    def set_leverage(
        self,
        inst_id: str,
        leverage: int | str,
        *,
        margin_mode: str = "cross",
        position_side: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "instId": inst_id,
            "leverage": str(leverage),
            "marginMode": margin_mode,
        }
        if position_side:
            body["positionSide"] = position_side
        data = self.request(
            "POST",
            "/api/v1/account/set-leverage",
            body=body,
            private=True,
        )
        row = data.get("data")
        return row if isinstance(row, dict) else {"data": row}

    def get_position_mode(self) -> str:
        data = self.request("GET", "/api/v1/account/position-mode", private=True)
        mode = (data.get("data") or {}).get("positionMode", "net_mode")
        self._position_mode = mode
        return mode

    def ensure_net_position_mode(self) -> str:
        if self._position_mode in ("net_mode", "net"):
            return self._position_mode
        try:
            mode = self.get_position_mode()
        except RuntimeError as exc:
            if "429" in str(exc) or "403" in str(exc):
                logger.warning(
                    "position-mode check blocked — assuming net_mode: {}",
                    exc,
                )
                self._position_mode = "net_mode"
                return "net_mode"
            raise
        if mode != "net_mode":
            data = self.request(
                "POST",
                "/api/v1/account/set-position-mode",
                body={"positionMode": "net_mode"},
                private=True,
            )
            mode = (data.get("data") or {}).get("positionMode", "net_mode")
        self._position_mode = mode
        return mode

    def _position_side_for_order(self, side: str) -> str:
        mode = self._position_mode or self.get_position_mode()
        if mode == "long_short_mode":
            return "long" if side.lower() == "buy" else "short"
        return "net"

    def _save_instruments_disk(self, rows: list[dict[str, Any]]) -> None:
        try:
            _INSTRUMENTS_DISK.parent.mkdir(parents=True, exist_ok=True)
            _INSTRUMENTS_DISK.write_text(
                json.dumps({"updated_at": time.time(), "instruments": rows}, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Could not persist instruments cache: {}", exc)

    def _load_instruments_disk(self) -> list[dict[str, Any]]:
        if not _INSTRUMENTS_DISK.is_file():
            return []
        try:
            data = json.loads(_INSTRUMENTS_DISK.read_text(encoding="utf-8"))
            updated = float(data.get("updated_at") or 0)
            if time.time() - updated > _INSTRUMENTS_DISK_MAX_AGE_SEC:
                return []
            rows = data.get("instruments")
            return rows if isinstance(rows, list) else []
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Could not load instruments disk cache: {}", exc)
            return []

    def _instruments_cached(
        self, *, inst_id: str | None = None, inst_type: str = "SWAP"
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self._instruments_cache:
            rows = list(self._instruments_cache)
        if not rows:
            rows = self._load_instruments_disk()
            if rows:
                self._instruments_cache = rows
                self._instruments_cache_ts = time.time()
                logger.info("Using instruments disk cache ({} symbols)", len(rows))
        if not rows:
            raise RuntimeError(
                f"No cached instruments for {inst_id or 'SWAP'} (WAF blocked REST)"
            )
        if inst_id:
            rows = [r for r in rows if r.get("instId") == inst_id]
        if inst_type:
            rows = [r for r in rows if str(r.get("instType") or "") == inst_type]
        if inst_id and not rows:
            raise RuntimeError(
                f"No cached instrument spec for {inst_id} (WAF blocked REST)"
            )
        return rows

    def get_instruments(
        self,
        inst_id: str | None = None,
        inst_type: str = "SWAP",
        *,
        retries: int = 3,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"instType": inst_type}
        if inst_id:
            params["instId"] = _public_inst_id(inst_id) or inst_id
        try:
            data = self.request(
                "GET",
                "/api/v1/market/instruments",
                params=params,
                private=False,
                retries=retries,
            )
            rows = data.get("data") or []
            rows = rows if isinstance(rows, list) else []
            if rows:
                if inst_id:
                    merged = {
                        str(r.get("instId")): r for r in (self._instruments_cache or [])
                    }
                    for row in rows:
                        merged[str(row.get("instId"))] = row
                    self._instruments_cache = list(merged.values())
                else:
                    self._instruments_cache = rows
                self._instruments_cache_ts = time.time()
                if not inst_id:
                    self._save_instruments_disk(self._instruments_cache)
            return rows
        except RuntimeError as exc:
            if "403" not in str(exc) and "429" not in str(exc):
                raise
            logger.warning(
                "get_instruments WAF/rate-limit for inst_id={} — using cache",
                inst_id or "ALL",
            )
            return self._instruments_cached(inst_id=inst_id, inst_type=inst_type)

    def list_live_instruments(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if (
            not refresh
            and self._instruments_cache
            and (time.time() - self._instruments_cache_ts) < 300
        ):
            return self._instruments_cache
        try:
            rows = self.get_instruments(inst_type="SWAP")
            return rows
        except RuntimeError as exc:
            if "403" not in str(exc):
                raise
            return self._instruments_cached(inst_type="SWAP")

    def get_instrument(self, inst_id: str) -> dict[str, Any] | None:
        try:
            rows = self.get_instruments(inst_id=inst_id)
            if rows:
                return rows[0]
        except RuntimeError as exc:
            logger.warning("get_instrument failed for {}: {}", inst_id, exc)
        try:
            rows = self._instruments_cached(inst_id=inst_id)
            if rows:
                return rows[0]
        except RuntimeError:
            pass
        logger.warning(
            "get_instrument: degraded default specs for {} (WAF, no cache)",
            inst_id,
        )
        return {
            "instId": inst_id,
            "instType": "SWAP",
            "minSize": "1",
            "lotSize": "1",
            "tickSize": "0.00001",
        }

    def get_candles(
        self,
        inst_id: str,
        *,
        bar: str = "1H",
        limit: str = "100",
    ) -> list[list[Any]]:
        clean_id = _public_inst_id(inst_id)
        data = self.request(
            "GET",
            "/api/v1/market/candles",
            params={"instId": clean_id, "bar": bar, "limit": limit},
            private=False,
        )
        rows = data.get("data") or []
        return rows if isinstance(rows, list) else []

    def get_funding_rate(self, inst_id: str) -> dict[str, Any]:
        clean_id = _public_inst_id(inst_id)
        data = self.request(
            "GET",
            "/api/v1/market/funding-rate",
            params={"instId": clean_id},
            private=False,
        )
        rows = data.get("data") or []
        if isinstance(rows, list) and rows:
            return rows[0]
        return rows if isinstance(rows, dict) else {}

    def get_all_funding_rates(self) -> list[dict[str, Any]]:
        """Fetch current funding rates for all SWAP instruments at once."""
        data = self.request(
            "GET",
            "/api/v1/market/funding-rate",
            params={"instType": "SWAP"},
            private=False,
        )
        rows = data.get("data") or []
        return rows if isinstance(rows, list) else []

    def get_funding_rate_history(
        self, inst_id: str, *, limit: str = "20"
    ) -> list[dict[str, Any]]:
        clean_id = _public_inst_id(inst_id)
        data = self.request(
            "GET",
            "/api/v1/market/funding-rate-history",
            params={"instId": clean_id, "limit": limit},
            private=False,
        )
        rows = data.get("data") or []
        return rows if isinstance(rows, list) else []

    def get_order_book(self, inst_id: str, *, size: str = "20") -> dict[str, Any]:
        clean_id = _public_inst_id(inst_id)
        data = self.request(
            "GET",
            "/api/v1/market/books",
            params={"instId": clean_id, "sz": size},
            private=False,
        )
        rows = data.get("data") or []
        if isinstance(rows, list) and rows:
            return rows[0]
        return rows if isinstance(rows, dict) else {}

    def get_tickers(
        self,
        inst_id: str | None = None,
        *,
        force_rest: bool = False,
        retries: int = 2,
    ) -> list[dict[str, Any]]:
        """Public market tickers; prefers universe cache unless force_rest=True."""
        if not force_rest:
            cached = self._tickers_from_universe_cache(inst_id, required=False)
            if cached:
                return cached
        clean_id = _public_inst_id(inst_id)
        params = {"instId": clean_id} if clean_id else None
        try:
            data = self.request(
                "GET",
                "/api/v1/market/tickers",
                params=params,
                private=False,
                retries=retries,
            )
            return data.get("data") or []
        except RuntimeError as exc:
            if "403" not in str(exc):
                raise
            logger.warning(
                "get_tickers WAF 403 for inst_id={} — using universe cache",
                inst_id or "ALL",
            )
            rows = self._tickers_from_universe_cache(inst_id, required=True)
            return rows

    def _tickers_from_universe_cache(
        self, inst_id: str | None, *, required: bool = True
    ) -> list[dict[str, Any]]:
        from autohedge.tools.blofin_universe_feed import get_universe_feed, load_universe_disk

        feed = get_universe_feed()
        with feed._lock:
            snap = feed._snapshot
        if snap is None:
            snap = load_universe_disk()
        if snap is None or not snap.tickers:
            if required:
                raise RuntimeError(
                    f"No cached ticker data for {inst_id or 'universe'} (WAF blocked REST)"
                )
            return []
        rows = snap.tickers
        if inst_id:
            rows = [t for t in rows if t.get("instId") == inst_id]
        if not rows and required:
            raise RuntimeError(
                f"No cached ticker data for {inst_id or 'universe'} (WAF blocked REST)"
            )
        return rows

    def get_balances(self) -> dict[str, Any]:
        data = self.request(
            "GET",
            "/api/v1/account/balance",
            params={"accountType": "futures"},
            private=True,
        )
        row = data.get("data")
        return row if isinstance(row, dict) else {"data": row}

    def get_positions(
        self, inst_id: str | None = None, *, retries: int = 6
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"accountType": "futures"}
        if inst_id:
            params["instId"] = inst_id
        data = self.request(
            "GET",
            "/api/v1/account/positions",
            params=params,
            private=True,
            retries=retries,
        )
        rows = data.get("data") or []
        return rows if isinstance(rows, list) else []

    def get_pending_tpsl(self, inst_id: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if inst_id:
            params["instId"] = inst_id
        data = self.request(
            "GET", "/api/v1/trade/orders-tpsl-pending", params=params or None, private=True
        )
        rows = data.get("data") or []
        return rows if isinstance(rows, list) else []

    def place_order(
        self,
        inst_id: str,
        side: str,
        order_type: str,
        size: str,
        *,
        price: str = "",
        margin_mode: str = "cross",
        position_side: str = "",
        reduce_only: str = "false",
        tp_trigger_price: str = "",
        tp_order_price: str = "",
        tp_trigger_price_type: str = "last",
        sl_trigger_price: str = "",
        sl_order_price: str = "",
        sl_trigger_price_type: str = "last",
    ) -> dict[str, Any]:
        self.ensure_net_position_mode()
        pos_side = position_side or self._position_side_for_order(side)
        body: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": margin_mode,
            "marginMode": margin_mode,
            "positionSide": pos_side,
            "side": side,
            "orderType": order_type,
            "size": size,
            "reduceOnly": reduce_only,
        }
        if self.broker_id:
            body["brokerId"] = self.broker_id
        if order_type != "market" and price:
            body["price"] = price
        if tp_trigger_price and tp_order_price:
            body["tpTriggerPrice"] = tp_trigger_price
            body["tpOrderPrice"] = tp_order_price
            body["tpTriggerPriceType"] = tp_trigger_price_type
        if sl_trigger_price and sl_order_price:
            body["slTriggerPrice"] = sl_trigger_price
            body["slOrderPrice"] = sl_order_price
            body["slTriggerPriceType"] = sl_trigger_price_type
        logger.info(
            "Placing Blofin order inst={} side={} type={} size={} positionSide={} tp={} sl={}",
            inst_id,
            side,
            order_type,
            size,
            pos_side,
            tp_trigger_price or "-",
            sl_trigger_price or "-",
        )
        data = self.request(
            "POST", "/api/v1/trade/order", body=body, private=True, retries=5
        )
        rows = data.get("data") or []
        row = rows[0] if rows else data
        if str(row.get("code", "0")) not in {"0", ""}:
            raise RuntimeError(
                f"Order rejected: {row.get('msg')} (code={row.get('code')})"
            )
        return row

    def place_tpsl(
        self,
        inst_id: str,
        side: str,
        size: str,
        *,
        margin_mode: str = "cross",
        position_side: str = "net",
        reduce_only: str = "true",
        tp_trigger_price: str = "",
        tp_order_price: str = "",
        tp_trigger_price_type: str = "last",
        sl_trigger_price: str = "",
        sl_order_price: str = "",
        sl_trigger_price_type: str = "last",
    ) -> dict[str, Any]:
        """Attach TP/SL to an open position (size -1 = entire position)."""
        body: dict[str, Any] = {
            "instId": inst_id,
            "marginMode": margin_mode,
            "positionSide": position_side,
            "side": side,
            "size": size,
            "reduceOnly": reduce_only,
        }
        if self.broker_id:
            body["brokerId"] = self.broker_id
        if tp_trigger_price:
            body["tpTriggerPrice"] = tp_trigger_price
            body["tpOrderPrice"] = tp_order_price or "-1"
            body["tpTriggerPriceType"] = tp_trigger_price_type
        if sl_trigger_price:
            body["slTriggerPrice"] = sl_trigger_price
            body["slOrderPrice"] = sl_order_price or "-1"
            body["slTriggerPriceType"] = sl_trigger_price_type
        if not tp_trigger_price and not sl_trigger_price:
            raise ValueError("At least one of tp_trigger_price or sl_trigger_price is required")
        logger.info(
            "Placing Blofin TP/SL inst={} side={} size={} tp={} sl={}",
            inst_id,
            side,
            size,
            tp_trigger_price or "-",
            sl_trigger_price or "-",
        )
        data = self.request(
            "POST", "/api/v1/trade/order-tpsl", body=body, private=True
        )
        row = data.get("data")
        if isinstance(row, dict) and str(row.get("code", "0")) not in {"0", ""}:
            raise RuntimeError(
                f"TP/SL rejected: {row.get('msg')} (code={row.get('code')})"
            )
        return row if isinstance(row, dict) else data

    def cancel_order(self, order_id: str, inst_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"orderId": order_id}
        if inst_id:
            body["instId"] = inst_id
        data = self.request(
            "POST", "/api/v1/trade/cancel-order", body=body, private=True
        )
        row = data.get("data")
        return row if isinstance(row, dict) else data

    def close_position(self, inst_id: str, margin_mode: str = "cross") -> dict[str, Any]:
        body: dict[str, Any] = {
            "instId": inst_id,
            "marginMode": margin_mode,
            "positionSide": "net",
        }
        if self.broker_id:
            body["brokerId"] = self.broker_id
        data = self.request(
            "POST",
            "/api/v1/trade/close-position",
            body=body,
            private=True,
        )
        return data.get("data") or data
