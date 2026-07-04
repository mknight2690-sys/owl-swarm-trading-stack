"""Blofin HTTP client using curl_cffi with browser impersonation.

Bypasses Cloudflare JS Challenge by impersonating a real Chrome browser
at the TLS/JA3 layer. Combined with strict rate limiting to stay
under 500 req/min, this avoids triggering Turnstile entirely.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from loguru import logger

# Rate limiting
_last_request_ts: float = 0.0
_MIN_INTERVAL_SEC: float = 0.15  # Max ~400 req/min to stay under 500 limit
_request_count: int = 0
_window_start: float = 0.0
_WINDOW_SEC: float = 60.0
_MAX_PER_WINDOW: int = 450  # Stay under 500/min limit


def _rate_limit() -> None:
    """Enforce rate limiting to stay under Cloudflare/Blofin limits."""
    global _last_request_ts, _request_count, _window_start
    now = time.time()
    # Per-request interval
    elapsed = now - _last_request_ts
    if elapsed < _MIN_INTERVAL_SEC:
        time.sleep(_MIN_INTERVAL_SEC - elapsed)
    _last_request_ts = time.time()
    # Window-based limit
    if now - _window_start > _WINDOW_SEC:
        _window_start = now
        _request_count = 0
    _request_count += 1
    if _request_count >= _MAX_PER_WINDOW:
        wait = _WINDOW_SEC - (now - _window_start)
        if wait > 0:
            logger.warning("Rate limit: waiting {:.1f}s ({} req in window)", wait, _request_count)
            time.sleep(wait)
        _window_start = time.time()
        _request_count = 0


class BlofinHTTPClient:
    """Drop-in replacement for requests-based BlofinClient that bypasses Cloudflare."""

    def __init__(self, credentials: Any = None) -> None:
        from autohedge.blofin_credentials import BlofinCredentials, load_blofin_credentials
        self.credentials = credentials or load_blofin_credentials()
        self.broker_id = os.getenv("BLOFIN_BROKER_ID", "5388cb1f51cec2e3").strip()
        self._position_mode: str | None = None
        self._instruments_cache: list[dict[str, Any]] | None = None
        self._instruments_cache_ts: float = 0.0
        self._session: Any = None

    def _get_session(self) -> Any:
        if self._session is None:
            from curl_cffi import requests as curl_requests
            self._session = curl_requests.Session(
                impersonate="chrome_120",
                timeout=30,
            )
        return self._session

    def _sign(self, method: str, path_with_query: str, body_str: str) -> tuple[str, str, str]:
        import base64
        import hashlib
        import hmac
        from uuid import uuid4
        timestamp = str(int(time.time() * 1000))
        nonce = str(uuid4())
        prehash = f"{path_with_query}{method.upper()}{timestamp}{nonce}{body_str}"
        hex_sig = hmac.new(
            self.credentials.secret_key.encode(),
            prehash.encode(),
            hashlib.sha256,
        ).hexdigest()
        return timestamp, nonce, hex_sig

    def _headers(self, method: str, path_with_query: str, body_str: str) -> dict[str, str]:
        timestamp, nonce, sign = self._sign(method, path_with_query, body_str)
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "ACCESS-KEY": self.credentials.api_key,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-NONCE": nonce,
            "ACCESS-PASSPHRASE": self.credentials.passphrase,
            "Origin": "https://blofin.com",
            "Referer": "https://blofin.com/",
        }

    def request(self, method: str, path: str, *, body: dict | None = None, private: bool = True) -> dict[str, Any]:
        """Make a rate-limited, Cloudflare-bypassed request."""
        _rate_limit()
        base = os.getenv("BLOFIN_API_BASE", "https://api.blofin.com")
        url = f"{base}{path}"
        body_str = json.dumps(body) if body else ""
        path_with_query = path
        headers = self._headers(method, path_with_query, body_str)
        session = self._get_session()
        try:
            if method.upper() == "GET":
                resp = session.get(url, headers=headers)
            elif method.upper() == "POST":
                resp = session.post(url, headers=headers, data=body_str)
            elif method.upper() == "DELETE":
                resp = session.delete(url, headers=headers)
            else:
                resp = session.request(method.upper(), url, headers=headers, data=body_str)
            if resp.status_code == 403:
                logger.warning("403 WAF on {} {} — backing off 30s", method, path)
                time.sleep(30)
                return self.request(method, path, body=body, private=private)
            if resp.status_code == 429:
                logger.warning("429 rate limit on {} {} — backing off 60s", method, path)
                time.sleep(60)
                return self.request(method, path, body=body, private=private)
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code} {path}: {resp.text[:500]}")
            payload = resp.json()
            code = str(payload.get("code", ""))
            if code not in {"0", "200"}:
                raise RuntimeError(
                    f"Blofin API error {code}: {payload.get('msg')} ({path})"
                )
            return payload
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Request failed {method} {path}: {exc}") from exc

    # --- Convenience methods (match BlofinClient interface) ---

    def get_tickers(self, inst_id: str | None = None, *, force_rest: bool = False, retries: int = 1) -> list[dict[str, Any]]:
        if inst_id:
            data = self.request("GET", f"/api/v1/market/ticker?instId={inst_id}")
        else:
            data = self.request("GET", "/api/v1/market/tickers?instType=SWAP")
        rows = data.get("data", [])
        return rows if isinstance(rows, list) else [rows]

    def get_candles(self, inst_id: str, *, bar: str = "1H", limit: int = 100) -> list[dict[str, Any]]:
        data = self.request("GET", f"/api/v1/market/candles?instId={inst_id}&bar={bar}&limit={limit}")
        return data.get("data", [])

    def get_instruments(self, inst_id: str | None = None) -> list[dict[str, Any]]:
        if inst_id:
            data = self.request("GET", f"/api/v1/market/instruments?instType=SWAP&instId={inst_id}")
        else:
            data = self.request("GET", "/api/v1/market/instruments?instType=SWAP")
        return data.get("data", [])

    def get_funding_rate(self, inst_id: str) -> dict[str, Any]:
        data = self.request("GET", f"/api/v1/market/funding-rate?instId={inst_id}")
        rows = data.get("data", [])
        return rows[0] if rows else {}

    def get_positions(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/api/v1/account/positions")
        return data.get("data", [])

    def get_account(self) -> dict[str, Any]:
        data = self.request("GET", "/api/v1/account/balance")
        rows = data.get("data", [])
        return rows[0] if rows else {}

    def get_equity(self) -> float:
        account = self.get_account()
        return float(account.get("totalEquity") or account.get("equity") or 0)

    def set_leverage(self, inst_id: str, leverage: int, *, margin_mode: str = "cross") -> dict[str, Any]:
        body = {
            "instId": inst_id,
            "leverage": str(leverage),
            "marginMode": margin_mode,
        }
        data = self.request("POST", "/api/v1/account/set-leverage", body=body)
        row = data.get("data")
        return row if isinstance(row, dict) else {"data": row}

    def get_position_mode(self) -> str:
        data = self.request("GET", "/api/v1/account/position-mode")
        mode = (data.get("data") or {}).get("positionMode", "net_mode")
        self._position_mode = mode
        return mode

    def ensure_net_position_mode(self) -> str:
        mode = self.get_position_mode()
        if mode != "net_mode":
            data = self.request("POST", "/api/v1/account/set-position-mode", body={"positionMode": "net_mode"})
            mode = (data.get("data") or {}).get("positionMode", "net_mode")
        self._position_mode = mode
        return mode

    def _position_side_for_order(self, side: str) -> str:
        mode = self._position_mode or self.get_position_mode()
        if mode == "long_short_mode":
            return "long" if side.lower() == "buy" else "short"
        return "net"

    def place_order(
        self,
        inst_id: str,
        side: str,
        size: str,
        *,
        order_type: str = "market",
        position_side: str = "",
        tp_trigger_price: str = "",
        sl_trigger_price: str = "",
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": "cross",
            "side": side,
            "ordType": order_type,
            "sz": size,
            "reduceOnly": str(reduce_only).lower(),
        }
        if position_side:
            body["posSide"] = position_side
        if tp_trigger_price:
            body["tpTriggerPx"] = tp_trigger_price
        if sl_trigger_price:
            body["slTriggerPx"] = sl_trigger_price
        if self.broker_id:
            body["brokerId"] = self.broker_id
        data = self.request("POST", "/api/v1/trade/order", body=body)
        row = data.get("data")
        return row if isinstance(row, dict) else {"data": row}

    def cancel_order(self, inst_id: str, order_id: str) -> dict[str, Any]:
        data = self.request("POST", "/api/v1/trade/cancel-order", body={
            "instId": inst_id,
            "ordId": order_id,
        })
        row = data.get("data")
        return row if isinstance(row, dict) else {"data": row}

    def list_live_instruments(self) -> list[dict[str, Any]]:
        return self.get_instruments()
