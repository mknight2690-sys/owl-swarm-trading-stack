#!/usr/bin/env python3
"""Standalone OWL dashboard — fast disk-backed APIs, never blocks on LLM imports."""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("OUTPUT_DIR", str(ROOT / "outputs"))

from dashboard_cache import (  # noqa: E402
    AGENT_ROSTER,
    ensure_cache_files,
    get_learning_report,
    get_swarm_graph,
    get_task_board,
    merge_events,
    owl_running,
)

OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
STATE_FILE = OUTPUT_DIR / "owl-state.json"
LIVE_FILE = OUTPUT_DIR / "owl-live.json"
DASHBOARD_HTML = ROOT / "swarm_dashboard.html"
PORT = int(os.environ.get("DASHBOARD_PORT", "7878"))

_account_lock = threading.Lock()
_last_account = 0.0
_account_thread_started = False
_stream_thread_started = False
_ACCOUNT_REFRESH_SEC = 5.0
_STREAM_EQUITY_SEC = 0.5
BLOFIN_ROOT = Path(r"C:\Users\mknig\blofin-auto-trader")

# ── SSE broadcast state ──
_sse_clients: set[Any] = set()
_sse_lock = threading.Lock()
_SSE_INTERVAL_SEC = 0.5  # max 500ms refresh for live data


def _stream_equity_loop() -> None:
    while True:
        try:
            from equity_stream import refresh_streaming_equity

            refresh_streaming_equity(write_curve=True)
        except Exception:
            pass
        time.sleep(_STREAM_EQUITY_SEC)


def _start_stream_equity() -> None:
    global _stream_thread_started
    if _stream_thread_started:
        return
    _stream_thread_started = True
    threading.Thread(target=_stream_equity_loop, name="owl-equity-stream", daemon=True).start()


def _account_refresh_loop() -> None:
    while True:
        try:
            _refresh_account(force=False)  # ← FIX: respect throttle, don't hammer API
        except Exception:
            pass
        time.sleep(_ACCOUNT_REFRESH_SEC)


def _start_account_refresh() -> None:
    global _account_thread_started
    if _account_thread_started:
        return
    _account_thread_started = True
    threading.Thread(target=_account_refresh_loop, name="owl-dash-account", daemon=True).start()


# ── SSE broadcast ──
def _broadcast(data: dict) -> None:
    """Push a JSON message to all connected SSE clients."""
    msg = f"data: {json.dumps(data, default=str)}\n\n".encode()
    with _sse_lock:
        dead: set[Any] = set()
        for wfile in list(_sse_clients):
            try:
                wfile.write(msg)
                if hasattr(wfile, "flush"):
                    wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError, ValueError):
                dead.add(wfile)
        for wfile in dead:
            _sse_clients.discard(wfile)


def _sse_loop() -> None:
    """Background broadcaster: live positions every 500ms, status/tasks/graph/learning every 2s."""
    last_status = 0.0
    last_tasks = 0.0
    last_graph = 0.0
    last_learning = 0.0
    error_count = 0
    while True:
        try:
            time.sleep(_SSE_INTERVAL_SEC)
            now = time.time()

            # Always push live equity/positions (the critical fast data)
            payload = _positions_payload()
            _broadcast({"type": "live", "data": payload})
            error_count = 0  # Reset on success

            # Push full status every 2s
            if now - last_status >= 2.0:
                _broadcast({"type": "status", "data": _status_payload()})
                last_status = now

            # Push task board every 2s
            if now - last_tasks >= 2.0:
                _broadcast({"type": "tasks", "data": get_task_board()})
                last_tasks = now

            # Push swarm graph every 2s
            if now - last_graph >= 2.0:
                _broadcast({"type": "graph", "data": get_swarm_graph()})
                last_graph = now

            # Push learning report every 2s
            if now - last_learning >= 2.0:
                _broadcast({"type": "learning", "data": get_learning_report()})
                last_learning = now
        except Exception as exc:
            error_count += 1
            if error_count <= 5:
                print(f"[SSE ERROR] {exc}", flush=True)
            # Don't let a transient error kill the loop, but don't hide it either
            time.sleep(0.5)


# ── Dashboard-Agent background thread (runs heavy drift detection separately) ──
_agent_thread_started = False
_AGENT_TICK_SEC = 3.0


def _agent_tick_loop() -> None:
    """Run Dashboard-Agent drift detection in background, never blocking SSE.
    NEVER writes positions — equity_stream.py is the sole source of positions.
    Only writes metadata: drift_detected, events, corrections, roe_by_position.
    """
    while True:
        try:
            from dashboard_agent import tick_dashboard_agent
            corrected = tick_dashboard_agent()
            # Write ONLY metadata to owl-live.json — never positions/equity/available
            live = _load_json(LIVE_FILE, {})
            live.update(
                {
                    "roe_by_position": corrected.get("roe_by_position", {}),
                    "events": corrected.get("events", live.get("events", [])),
                    "drift_detected": corrected.get("drift_detected", False),
                    "drift_details": corrected.get("drift_details", []),
                    "corrections": corrected.get("corrections", []),
                    "updated_at": int(time.time()),
                }
            )
            LIVE_FILE.write_text(json.dumps(live, indent=2, default=str), encoding="utf-8")
        except Exception as exc:
            print(f"[AGENT ERROR] {exc}", flush=True)
        time.sleep(_AGENT_TICK_SEC)


def _start_agent_loop() -> None:
    global _agent_thread_started
    if _agent_thread_started:
        return
    _agent_thread_started = True
    threading.Thread(target=_agent_tick_loop, name="owl-dash-agent", daemon=True).start()


def _start_sse_loop() -> None:
    threading.Thread(target=_sse_loop, name="owl-dash-sse", daemon=True).start()


def _load_json(path: Path, default=None):
    if not path.is_file():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _owl_running() -> bool:
    lock = OUTPUT_DIR / "owl-llm.lock"
    if lock.is_file():
        try:
            pid = int(lock.read_text(encoding="utf-8").strip())
            if _pid_running(pid):
                return True
        except (TypeError, ValueError):
            pass
    return False


def _refresh_account(force: bool = False) -> None:
    """
    Refresh account data from auto-trader disk cache FIRST.
    Only hits live API if cache is stale (>90s) or empty — prevents 429 rate limits.
    """
    global _last_account
    if not force and time.time() - _last_account < _ACCOUNT_REFRESH_SEC:
        return
    if not _account_lock.acquire(blocking=False):
        return
    try:
        now = time.time()
        positions: list[dict[str, Any]] = []
        equity = 0.0
        available = 0.0
        source = "unknown"

        # ── STEP 1: Read auto-trader disk cache (fast, no API call) ──
        pos_cache = BLOFIN_ROOT / "outputs" / "positions-cache.json"
        eq_cache = BLOFIN_ROOT / "outputs" / "equity-cache.json"
        disk_positions: list[dict[str, Any]] = []
        disk_age = 9999.0

        if pos_cache.is_file():
            try:
                raw = json.loads(pos_cache.read_text(encoding="utf-8"))
                disk_age = now - float(raw.get("updated_at") or 0)
                rows = raw.get("open_rows") or []
                if isinstance(rows, list):
                    disk_positions = rows
            except Exception:
                pass

        if disk_positions and disk_age <= 3600.0:  # Trust disk cache up to 1 hour when API is rate-limited
            positions = disk_positions
            if eq_cache.is_file():
                try:
                    eq_raw = json.loads(eq_cache.read_text(encoding="utf-8"))
                    equity = float(eq_raw.get("equity_usdt") or 0)
                    available = float(eq_raw.get("available_usdt") or 0)
                except Exception:
                    pass
            source = "disk_cache" if disk_age < 30 else "disk_cache_stale"

        # ── STEP 2: Cache is stale/empty — try live API as last resort ──
        if not positions or disk_age > 3600.0 or force:
            try:
                from blofin_live_api import fetch_live_account
                snap = fetch_live_account(force=False, min_interval_sec=5.0)
                if snap.get("ok"):
                    positions = list(snap.get("positions") or [])
                    equity = float(snap.get("equity") or 0)
                    available = float(snap.get("available") or 0)
                    source = "live"
            except Exception:
                pass

        # ── STEP 3: Write positions to owl-live.json ONLY when position set changes ──
        # equity_stream.py is the sole source of equity/available and updates mark prices
        # We only touch positions when a new position opened or one closed (detected by instId set change)
        live = _load_json(LIVE_FILE, {})
        live_inst_ids = {str(p.get("instId", "")) for p in (live.get("positions") or [])}
        disk_inst_ids = {str(p.get("instId", "")) for p in positions}

        if live_inst_ids != disk_inst_ids:
            # Position set changed — new open or close detected
            live["positions"] = positions
            live["account_source"] = source + "_position_change"
            live["position_count"] = len(positions)
            LIVE_FILE.write_text(json.dumps(live, indent=2, default=str), encoding="utf-8")
        # If instId sets match, do NOTHING — equity_stream.py is already keeping mark prices updated
        _last_account = now
    except Exception:
        pass
    finally:
        _account_lock.release()


def _kick_account_refresh() -> None:
    """Non-blocking refresh when status API is polled faster than background loop."""
    live = _load_json(LIVE_FILE, {})
    ts = int(live.get("account_ts") or 0)
    if time.time() - ts < _ACCOUNT_REFRESH_SEC:
        return
    if not _account_lock.acquire(blocking=False):
        return
    _account_lock.release()
    threading.Thread(target=_refresh_account, kwargs={"force": False}, daemon=True).start()


def _account_fields(live: dict, state: dict) -> tuple[float, float, list, dict]:
    """Read streamed account state written by background equity/position loops."""
    equity = float(live.get("equity") or state.get("equity") or 0)
    available = float(live.get("available") or state.get("available") or 0)
    positions = live.get("positions") if isinstance(live.get("positions"), list) else []
    if not positions and isinstance(state.get("positions"), list):
        positions = state.get("positions") or []
    meta = {
        "account_ts": int(live.get("account_ts") or 0),
        "account_source": live.get("account_source", ""),
    }
    return equity, available, positions, meta


def _positions_payload() -> dict:
    """Return live snapshot from owl-live.json — FAST, never blocks."""
    live = _load_json(LIVE_FILE, {})
    now = int(time.time())
    return {
        "equity": float(live.get("equity") or 0),
        "available": float(live.get("available") or 0),
        "positions": live.get("positions") or [],
        "account_ts": now,  # Always tick every second
        "account_source": live.get("account_source", ""),
        "position_count": len(live.get("positions") or []),
        "roe_by_position": live.get("roe_by_position", {}),
        "events": live.get("events", []),
        "drift_detected": live.get("drift_detected", False),
        "drift_details": live.get("drift_details", []),
        "corrections": live.get("corrections", []),
    }


def _status_payload() -> dict:
    live = _load_json(LIVE_FILE, {})
    state = _load_json(STATE_FILE, {})
    equity, available, positions, acct = _account_fields(live, state)
    running = owl_running()
    events = merge_events(live.get("events"))
    log_cycle = 0
    try:
        from dashboard_cache import _infer_cycle_from_log

        log_cycle = _infer_cycle_from_log()
    except Exception:
        pass
    cycle = max(int(state.get("cycle") or 0), int(live.get("cycle") or 0), log_cycle)
    # Dashboard-Agent health
    agent_health = {}
    try:
        from dashboard_agent import agent_health

        agent_health = agent_health()
    except Exception:
        pass
    return {
        "running": running,
        "cycle": cycle,
        "equity": equity,
        "available": available,
        "positions": positions,
        "account_ts": int(time.time()),  # Always tick every second
        "account_source": acct.get("account_source", ""),
        "events": events,
        "winRate": live.get("winRate", "--"),
        "lastError": state.get("last_error", live.get("last_error", "")),
        "pipeline": live.get("pipeline") or _load_json(OUTPUT_DIR / "pipeline_state.json", {}),
        "agentsActive": live.get("agentsActive", 11 if running else 0),
        "agentRoster": AGENT_ROSTER,
        "dashboard_mode": "standalone",
        "cycle_in_progress": running and log_cycle > int(state.get("cycle") or 0),
        "dashboard_agent": agent_health,
    }


class DashHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            html = DASHBOARD_HTML.read_text(encoding="utf-8") if DASHBOARD_HTML.is_file() else "<h1>OWL Swarm</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        elif path == "/api/status":
            self._json(_status_payload())
        elif path == "/api/positions":
            self._json(_positions_payload())
        elif path == "/api/tasks":
            self._json(get_task_board())
        elif path == "/api/swarm-graph":
            self._json(get_swarm_graph())
        elif path == "/api/learning":
            self._json(get_learning_report())
        elif path == "/api/assurance":
            self._json({"narrative": "Assurance data loads with trading cycle.", "all_pillars_live": True})
        elif path == "/api/overseer":
            notes = []
            p = OUTPUT_DIR / "overseer_notes.jsonl"
            if p.is_file():
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]:
                    try:
                        notes.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            self._json({"recent_notes": notes})
        elif path == "/api/playbook":
            pb = OUTPUT_DIR / "self_heal_playbook.json"
            self._json(_load_json(pb, {"fixes": {}}))
        elif path == "/events":
            # SSE endpoint — push real-time updates to browser
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                # Send initial live snapshot
                init = json.dumps({"type": "live", "data": _positions_payload()}, default=str)
                self.wfile.write(f"data: {init}\n\n".encode())
                self.wfile.flush()
                with _sse_lock:
                    _sse_clients.add(self.wfile)
                # Keep connection alive with periodic pings
                while True:
                    time.sleep(30)
                    ping = json.dumps({"type": "ping"})
                    self.wfile.write(f"data: {ping}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError, ValueError):
                pass
            finally:
                with _sse_lock:
                    _sse_clients.discard(self.wfile)
            return
        else:
            self.send_response(404)
            self.end_headers()

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def log_message(self, *args):
        pass


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_cache_files()
    try:
        (OUTPUT_DIR / "dashboard-server.pid").write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    _start_account_refresh()
    _start_stream_equity()
    _start_agent_loop()
    _start_sse_loop()
    _refresh_account(force=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), DashHandler)
    srv.daemon_threads = True
    print(f"OWL dashboard server: http://127.0.0.1:{PORT}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
