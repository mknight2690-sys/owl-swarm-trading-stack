"""Live Blofin universe market feed (websocket + REST fallback)."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from pathlib import Path

from loguru import logger

from autohedge.tools.blofin_client import BlofinClient

UNIVERSE_DISK_CACHE = (
    Path(__file__).resolve().parents[2] / "outputs" / "universe-cache.json"
)
UNIVERSE_DISK_MAX_AGE_SEC = 7200.0
PRICE_DISK_CACHE = (
    Path(__file__).resolve().parents[2] / "outputs" / "price-cache.json"
)
PRICE_DISK_MAX_AGE_SEC = 7200.0
WS_BRIDGE_MAX_AGE_SEC = float(os.getenv("OWL_WS_MAX_AGE_SEC", "300"))


def _ws_bridge_path() -> Path | None:
    raw = os.getenv("OWL_WS_TICKERS_PATH", "").strip()
    if raw:
        return Path(raw)
    owl = Path(r"C:\Users\mknig\owl-swarm\outputs\ws-tickers.json")
    return owl if owl.is_file() else None


def _load_ws_bridge_tickers() -> list[dict[str, Any]] | None:
    """Tickers streamed by Node/Chromium WS bridge (bypasses Cloudflare)."""
    path = _ws_bridge_path()
    if not path or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        updated = float(data.get("updated_at") or 0)
        age = time.time() - updated
        if age > WS_BRIDGE_MAX_AGE_SEC:
            return None
        tickers = data.get("tickers")
        if not isinstance(tickers, list) or len(tickers) < 50:
            return None
        logger.info(
            "Using market bridge cache ({} tickers, {}s old, source={})",
            len(tickers),
            int(age),
            data.get("source", "?"),
        )
        return tickers
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("WS bridge cache read failed: {}", exc)
        return None

WS_URL = os.getenv("BLOFIN_WS_URL", "wss://api.blofin.com/ws/public")
WS_HEADERS = [
    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Origin: https://blofin.com",
    "Referer: https://blofin.com/",
]


@dataclass
class UniverseSnapshot:
    source: str
    count: int
    updated_at: float
    tickers: list[dict[str, Any]] = field(default_factory=list)
    top_gainers: list[dict[str, Any]] = field(default_factory=list)
    top_losers: list[dict[str, Any]] = field(default_factory=list)

    def summary_text(self, max_rows: int = 8) -> str:
        lines = [
            f"Universe snapshot ({self.source}): {self.count} live instruments @ {time.strftime('%H:%M:%S', time.localtime(self.updated_at))}",
            "",
            "Top gainers (24h %):",
        ]
        for row in self.top_gainers[:max_rows]:
            lines.append(
                f"  {row.get('instId')}: last={row.get('last')} chg={row.get('chg_pct')}%"
            )
        lines.append("")
        lines.append("Top losers (24h %):")
        for row in self.top_losers[:max_rows]:
            lines.append(
                f"  {row.get('instId')}: last={row.get('last')} chg={row.get('chg_pct')}%"
            )
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(
            {
                "source": self.source,
                "count": self.count,
                "updated_at": self.updated_at,
                "top_gainers": self.top_gainers[:10],
                "top_losers": self.top_losers[:10],
                "tickers": self.tickers,
            },
            default=str,
        )


def _pct_change(row: dict[str, Any]) -> float | None:
    try:
        last = float(row.get("last") or 0)
        open24 = float(row.get("open24h") or 0)
        if open24 <= 0:
            return None
        return (last - open24) / open24 * 100.0
    except (TypeError, ValueError):
        return None


def build_snapshot(tickers: list[dict[str, Any]], source: str) -> UniverseSnapshot:
    enriched: list[dict[str, Any]] = []
    for row in tickers:
        if not row.get("instId"):
            continue
        chg = _pct_change(row)
        enriched.append({**row, "chg_pct": round(chg, 3) if chg is not None else None})

    ranked = [r for r in enriched if r.get("chg_pct") is not None]
    gainers = sorted(ranked, key=lambda r: r["chg_pct"], reverse=True)[:10]
    losers = sorted(ranked, key=lambda r: r["chg_pct"])[:10]

    return UniverseSnapshot(
        source=source,
        count=len(enriched),
        updated_at=time.time(),
        tickers=enriched,
        top_gainers=gainers,
        top_losers=losers,
    )


def save_universe_disk(snap: UniverseSnapshot) -> None:
    try:
        UNIVERSE_DISK_CACHE.parent.mkdir(parents=True, exist_ok=True)
        UNIVERSE_DISK_CACHE.write_text(snap.to_json(), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not persist universe cache: {}", exc)


def load_universe_disk() -> UniverseSnapshot | None:
    if not UNIVERSE_DISK_CACHE.is_file():
        return None
    try:
        data = json.loads(UNIVERSE_DISK_CACHE.read_text(encoding="utf-8"))
        updated = float(data.get("updated_at") or 0)
        age = time.time() - updated
        if age > UNIVERSE_DISK_MAX_AGE_SEC:
            return None
        tickers = data.get("tickers")
        if not isinstance(tickers, list) or not tickers:
            return None
        snap = build_snapshot(tickers, str(data.get("source") or "disk_cache"))
        snap.updated_at = updated
        snap.top_gainers = data.get("top_gainers") or snap.top_gainers
        snap.top_losers = data.get("top_losers") or snap.top_losers
        logger.info(
            "Loaded universe disk cache ({} instruments, {}s old)",
            snap.count,
            int(age),
        )
        return snap
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Could not load universe disk cache: {}", exc)
        return None


class BlofinUniverseFeed:
    """Background feed that keeps an all-instrument snapshot fresh."""

    def __init__(
        self,
        client: BlofinClient | None = None,
        *,
        refresh_seconds: float = 300.0,
    ) -> None:
        self.client = client or BlofinClient()
        self.refresh_seconds = refresh_seconds
        self._lock = threading.Lock()
        self._snapshot: UniverseSnapshot | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ws_ok = False
        self._ws_disabled = True  # WAF blocks WS from Python; REST only
        self._ws_logged = False

    def _try_websocket_once(self) -> list[dict[str, Any]] | None:
        if getattr(self, "_ws_disabled", False):
            return None
        try:
            import websocket  # type: ignore[import-untyped]
        except ImportError:
            self._ws_disabled = True
            return None

        box: list[dict[str, Any]] = []
        done = threading.Event()

        def on_message(_ws: object, message: str) -> None:
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                return
            data = payload.get("data")
            if isinstance(data, list):
                box.extend(data)
            elif isinstance(data, dict):
                box.append(data)
            if len(box) >= 50:
                done.set()

        def on_open(ws: object) -> None:
            sub = json.dumps(
                {"op": "subscribe", "args": [{"channel": "tickers", "instType": "SWAP"}]}
            )
            ws.send(sub)  # type: ignore[attr-defined]

        def on_error(_ws: object, _err: object) -> None:
            self._ws_disabled = True
            done.set()

        app = websocket.WebSocketApp(
            WS_URL,
            header=WS_HEADERS,
            on_message=on_message,
            on_open=on_open,
            on_error=on_error,
        )
        thread = threading.Thread(
            target=app.run_forever,
            kwargs={"ping_interval": 20, "ping_timeout": 10},
            daemon=True,
        )
        thread.start()
        done.wait(6)
        try:
            app.close()
        except Exception:
            pass
        if box:
            self._ws_ok = True
            logger.info("Blofin websocket feed connected ({} tickers)", len(box))
            return box
        if not getattr(self, "_ws_logged", False):
            logger.info(
                "Blofin websocket blocked by WAF; using parallel REST universe scan"
            )
            self._ws_logged = True
        return None

    def _load_price_disk(self) -> dict[str, dict[str, Any]]:
        """Load cached ticker prices from disk."""
        if not PRICE_DISK_CACHE.is_file():
            return {}
        try:
            data = json.loads(PRICE_DISK_CACHE.read_text(encoding="utf-8"))
            updated = float(data.get("updated_at") or 0)
            if time.time() - updated > PRICE_DISK_MAX_AGE_SEC:
                return {}
            rows = data.get("prices") or {}
            if isinstance(rows, dict) and rows:
                logger.info(
                    "Loaded price disk cache ({} symbols, {}s old)",
                    len(rows),
                    int(time.time() - updated),
                )
                return rows
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
        return {}


    def _save_price_disk(self, prices: dict[str, dict[str, Any]]) -> None:
        """Persist ticker prices to disk."""
        try:
            PRICE_DISK_CACHE.parent.mkdir(parents=True, exist_ok=True)
            PRICE_DISK_CACHE.write_text(
                json.dumps(
                    {"updated_at": time.time(), "prices": prices}, default=str
                ),
                encoding="utf-8",
            )
        except OSError:
            pass


    def _bootstrap_from_instruments(self) -> UniverseSnapshot:
        """Fallback universe when /market/tickers is WAF-blocked."""
        rows = self.client.get_instruments(inst_type="SWAP")
        cached_prices = self._load_price_disk()
        tickers: list[dict[str, Any]] = []
        for row in rows:
            inst = str(row.get("instId") or "")
            if not inst.endswith("-USDT"):
                continue
            cached = cached_prices.get(inst, {})
            last = (
                cached.get("last")
                or row.get("last")
                or row.get("markPrice")
                or "0"
            )
            open24h = cached.get("open24h") or last
            vol = (
                cached.get("volCurrency24h")
                or row.get("volCurrency24h")
                or "0"
            )
            tickers.append(
                {
                    "instId": inst,
                    "last": last,
                    "open24h": open24h,
                    "volCurrency24h": vol,
                }
            )
        if not tickers:
            raise RuntimeError("instruments fallback produced no USDT perps")
        logger.warning(
            "Using instruments-only universe fallback ({} symbols); momentum ranks are degraded",
            len(tickers),
        )
        return build_snapshot(tickers, "instruments_waf_fallback")

    def _refresh_rest(self) -> UniverseSnapshot:
        with self._lock:
            stale = (
                self._snapshot is None
                or (time.time() - self._snapshot.updated_at) > 300
            )
        if not stale and self._snapshot is not None:
            return self._snapshot
        try:
            tickers = self.client.get_tickers(force_rest=True, retries=2)
            prices: dict[str, dict[str, Any]] = {}
            for t in tickers:
                inst = str(t.get("instId") or "")
                if inst:
                    prices[inst] = {
                        "last": t.get("last") or "0",
                        "open24h": t.get("open24h") or t.get("last") or "0",
                        "volCurrency24h": t.get("volCurrency24h") or "0",
                    }
            if prices:
                self._save_price_disk(prices)
            return build_snapshot(tickers, "rest_parallel")
        except Exception as exc:
            with self._lock:
                if self._snapshot is not None:
                    logger.warning(
                        "Universe REST refresh failed, keeping cached snapshot: {}",
                        exc,
                    )
                    return self._snapshot
            try:
                return self._bootstrap_from_instruments()
            except Exception as fallback_exc:
                logger.warning("Instruments fallback failed: {}", fallback_exc)
                raise exc from fallback_exc

    def refresh(self, *, force: bool = False) -> UniverseSnapshot:
        with self._lock:
            if (
                not force
                and self._snapshot is not None
                and (time.time() - self._snapshot.updated_at) < 300
            ):
                return self._snapshot
        ws_rows = _load_ws_bridge_tickers()
        ws_source = "chromium_ws"
        if not ws_rows:
            ws_rows = self._try_websocket_once()
            ws_source = "websocket"
        if ws_rows:
            snap = build_snapshot(ws_rows, ws_source)
        else:
            snap = self._refresh_rest()
        with self._lock:
            self._snapshot = snap
        save_universe_disk(snap)
        logger.info(
            "Universe feed refreshed: {} instruments via {}",
            snap.count,
            snap.source,
        )
        return snap

    def get_snapshot(self) -> UniverseSnapshot:
        with self._lock:
            if self._snapshot is not None:
                return self._snapshot
        disk = load_universe_disk()
        if disk:
            with self._lock:
                self._snapshot = disk
            return disk
        return self.refresh()

    def ticker_for(self, inst_id: str) -> dict[str, Any] | None:
        """Lookup one instrument from the last good snapshot (WAF-safe)."""
        needle = (inst_id or "").strip().upper()
        if not needle:
            return None
        snap = self.get_snapshot()
        for row in snap.tickers:
            if row.get("instId") == needle:
                return row
        return None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                ws_rows = _load_ws_bridge_tickers()
                if ws_rows:
                    snap = build_snapshot(ws_rows, "chromium_ws")
                else:
                    snap = self._refresh_rest()
                with self._lock:
                    self._snapshot = snap
                save_universe_disk(snap)
            except Exception as exc:
                logger.warning("Universe feed refresh failed: {}", exc)
            self._stop.wait(self.refresh_seconds)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        try:
            self.refresh()
        except Exception as exc:
            logger.warning(
                "Universe feed initial refresh failed (using disk cache if any): {}",
                exc,
            )
            disk = load_universe_disk()
            if disk:
                with self._lock:
                    self._snapshot = disk
            else:
                try:
                    snap = self._bootstrap_from_instruments()
                    with self._lock:
                        self._snapshot = snap
                    save_universe_disk(snap)
                except Exception as boot_exc:
                    logger.warning("Universe bootstrap failed: {}", boot_exc)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)


_feed: BlofinUniverseFeed | None = None


def get_universe_feed() -> BlofinUniverseFeed:
    global _feed
    if _feed is None:
        refresh = float(os.getenv("UNIVERSE_REFRESH_SEC", "180"))
        _feed = BlofinUniverseFeed(refresh_seconds=refresh)
        _feed.start()
    return _feed
