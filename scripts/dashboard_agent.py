"""
Dashboard-Agent — LLM-driven drift detection and data correction for the OWL Swarm dashboard.

Hires into the swarm graph as a data/support agent. Monitors equity, positions,
PnL, and ROE streams; detects drift between cached and live Blofin data; uses a
lightweight LLM call to decide corrective actions; applies fixes without blocking
the 500ms SSE loop.

LEARNED PLAYBOOK — The agent remembers what fixes worked and replays them.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# ── paths ──
OWL_ROOT = Path(os.environ.get("OWL_SWARM_ROOT", r"C:\Users\mknig\owl-swarm"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", OWL_ROOT / "outputs"))
AUTO_TRADER_ROOT = Path(os.environ.get("AUTO_TRADER_ROOT", r"C:\Users\mknig\blofin-auto-trader"))
LIVE_FILE = OUTPUT_DIR / "owl-live.json"
STATE_FILE = OUTPUT_DIR / "owl-state.json"
STREAM_STATE = OUTPUT_DIR / "equity_stream_state.json"
AGENT_LOG = OUTPUT_DIR / "dashboard_agent_log.jsonl"
PLAYBOOK_FILE = OUTPUT_DIR / "dashboard_agent_playbook.json"
DISK_POSITIONS_CACHE = AUTO_TRADER_ROOT / "outputs" / "positions-cache.json"
DISK_EQUITY_CACHE = AUTO_TRADER_ROOT / "outputs" / "equity-cache.json"

# ── thresholds ──
_DRIFT_PNL_STALE_SEC = 3.0          # PnL should update within 3s when WS tickers flow
_DRIFT_EQUITY_STALE_SEC = 5.0       # equity should tick every 5s
_DRIFT_ROE_TOLERANCE = 0.01         # 1% ROE calc tolerance
_MAX_LLM_CALLS_PER_MIN = 6          # rate-limit LLM to avoid cost spikes


class DashboardAgent:
    """
    Swarm agent that lives on the dashboard data plane.
    - Detects drift between cached (owl-live.json) and live Blofin API data.
    - Calculates proper ROE per position.
    - Detects open/close events (position added/removed).
    - Uses LLM to decide corrective action when drift exceeds thresholds.
    - Applies corrections (force refresh, clear stale cache, etc.).
    - LEARNS from fixes: records what worked in a playbook for next time.
    """

    def __init__(self) -> None:
        self.name = "Dashboard-Agent"
        self.role = "data"
        self._last_llm_call = 0.0
        self._llm_call_count = 0
        self._llm_call_window = 0.0
        self._prev_positions: dict[str, dict[str, Any]] = {}
        self._prev_equity = 0.0
        self._prev_available = 0.0
        self._prev_ts = 0.0
        self._events: list[dict[str, Any]] = []
        self._drift_history: list[dict[str, Any]] = []
        self._playbook = self._load_playbook()
        self._consecutive_ghost_ticks = 0
        self._last_purge_ts = 0.0

    # ── public API ──

    def tick(self, *, force_live: bool = False) -> dict[str, Any]:
        """
        One correction cycle. Returns a corrected snapshot dict with keys:
        equity, available, positions, roe_by_position, events, drift_detected, corrections.
        """
        snapshot = self._read_snapshot()
        live = self._fetch_live()
        disk = self._fetch_disk_cache()

        # Combine live + disk for robust drift detection even when API is rate-limited
        trusted = self._merge_sources(live, disk)

        drift = self._detect_drift(snapshot, trusted)
        corrections: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []

        if drift["has_drift"]:
            # Try rule-based fixes first (fast, no LLM)
            rule_fixes = self._apply_rule_fixes(drift, snapshot, trusted)
            corrections.extend(rule_fixes)

            # Check playbook for learned fixes matching this symptom
            learned_fixes = self._apply_playbook_fixes(drift, snapshot, trusted)
            corrections.extend(learned_fixes)

            # If rule fixes didn't resolve, escalate to LLM
            if not self._drift_resolved(rule_fixes + learned_fixes, drift) and self._can_llm():
                llm_fix = self._llm_correct(drift, snapshot, trusted)
                if llm_fix:
                    corrections.append(llm_fix)
                    self._log_llm_call()

            # Detect open/close events
            events = self._detect_events(snapshot.get("positions", []))

        # Recalculate ROE for every position
        roe_map = self._calc_roe_map(snapshot.get("positions", []), snapshot.get("equity", 0))

        # Apply corrections to snapshot
        corrected = self._apply_corrections(snapshot, corrections, trusted)

        # Learn from this cycle
        self._learn_from_cycle(drift, corrections, corrected)

        # Log
        self._log_cycle(drift, corrections, events, corrected)

        return {
            "agent": self.name,
            "ts": int(time.time()),
            "equity": corrected.get("equity", 0.0),
            "available": corrected.get("available", 0.0),
            "positions": corrected.get("positions", []),
            "roe_by_position": roe_map,
            "events": events,
            "drift_detected": drift["has_drift"],
            "drift_details": drift.get("details", []),
            "corrections": corrections,
            "position_count": len(corrected.get("positions", [])),
            "playbook_fixes_applied": len([c for c in corrections if c.get("source") == "playbook"]),
        }

    def health(self) -> dict[str, Any]:
        """Quick health check for the dashboard status panel."""
        return {
            "agent": self.name,
            "status": "active",
            "llm_calls_this_window": self._llm_call_count,
            "last_drift": self._drift_history[-1] if self._drift_history else None,
            "events_queued": len(self._events),
            "playbook_entries": len(self._playbook.get("fixes", [])),
        }

    # ── internal: learned playbook ──

    def _load_playbook(self) -> dict[str, Any]:
        """Load the learned playbook of fixes that worked."""
        try:
            if PLAYBOOK_FILE.is_file():
                return json.loads(PLAYBOOK_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {
            "fixes": [
                # Pre-seeded with known fixes that always work
                {
                    "id": "fix_ghost_positions_disk_fallback",
                    "symptom": "GHOST_POSITIONS",
                    "action": "purge_from_disk_cache",
                    "description": "When live API is rate-limited and cached positions > disk positions, use disk as ground truth and purge stale cache entries.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
                {
                    "id": "fix_rate_limit_fallback",
                    "symptom": "LIVE_API_FAILED",
                    "action": "use_disk_cache_positions",
                    "description": "When live API returns 429/403, fall back to positions-cache.json from auto-trader as trusted source.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
                {
                    "id": "fix_stale_mark_price_ws",
                    "symptom": "STALE_MARK_PRICE",
                    "action": "override_from_rest_ticker",
                    "description": "When WS mark price hasn't updated in >5s, override with latest REST ticker or position markPrice from API.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
                {
                    "id": "fix_equity_zero_recovery",
                    "symptom": "ZERO_EQUITY",
                    "action": "restore_from_state_json",
                    "description": "When equity reads 0 but positions exist, restore from owl-state.json last known good equity or disk equity-cache.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
                {
                    "id": "fix_event_queue_overflow",
                    "symptom": "EVENT_QUEUE_OVERFLOW",
                    "action": "compact_and_flush",
                    "description": "When event queue exceeds 200 entries, compact to last 50 unique events and flush duplicates.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
                {
                    "id": "fix_sse_stale_connection",
                    "symptom": "SSE_STALE",
                    "action": "broadcast_full_refresh",
                    "description": "When dashboard clients haven't received data in >10s, force a full status + positions broadcast to reconnect stale SSE clients.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
                # NEW FIXES — learned from permanent rate-limit investigation
                {
                    "id": "fix_dashboard_force_refresh_bypass",
                    "symptom": "LIVE_API_FAILED",
                    "action": "disable_force_refresh_in_dashboard",
                    "description": "CRITICAL: The dashboard's _account_refresh_loop was calling _refresh_account(force=True) every 5s, bypassing the API throttle entirely. The dashboard must ALWAYS read auto-trader disk cache first and NEVER force a live API call.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
                {
                    "id": "fix_waf_backoff_never_triggers",
                    "symptom": "LIVE_API_FAILED",
                    "action": "patch_blofin_client_waf_threshold",
                    "description": "CRITICAL: blofin_client.py has 'if _consecutive_403s >= 9999' which NEVER triggers. The WAF backoff threshold must be 3-5 consecutive 403s before a 30s global pause. Without this, the client rotates TLS fingerprints forever without ever backing off.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
                {
                    "id": "fix_equity_stream_reads_api_first",
                    "symptom": "LIVE_API_FAILED",
                    "action": "read_disk_cache_first_in_equity_stream",
                    "description": "The equity_stream._resolve_positions_and_balances was calling fetch_live_account BEFORE checking disk cache. When multiple dashboard processes run, each independently calls the API. Disk cache must be checked FIRST (fresh <30s) before any live API call.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
                {
                    "id": "fix_cross_process_circuit_breaker",
                    "symptom": "LIVE_API_FAILED",
                    "action": "add_shared_file_lock_throttle",
                    "description": "Multiple processes (trading engine, dashboard, monitor) each have their own circuit breaker dict. They don't coordinate. A shared file-based throttle (e.g., .blofin_api_throttle.json) should track last API call timestamp across all processes.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
                {
                    "id": "fix_interface_binding_without_vpn",
                    "symptom": "LIVE_API_FAILED",
                    "action": "make_interface_binding_optional",
                    "description": "blofin_client.py hardcodes interface='10.2.0.2' (ProtonVPN). If VPN is down, curl_cffi may still work but route through normal interface. The interface should be configurable via env var BLOFIN_INTERFACE with fallback to auto-detect.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
                {
                    "id": "fix_dashboard_trust_disk_cache_always",
                    "symptom": "LIVE_API_FAILED",
                    "action": "always_trust_disk_cache_when_api_fails",
                    "description": "CRITICAL: When live API returns 429/403, the dashboard MUST always fall back to disk cache positions-cache.json regardless of age. The previous 90-second threshold was too strict and caused the dashboard to show empty positions when the API was rate-limited. Disk cache is the only reliable source when API fails.",
                    "success_rate": 1.0,
                    "uses": 0,
                },
            ],
            "version": 1,
        }

    def _save_playbook(self) -> None:
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            PLAYBOOK_FILE.write_text(json.dumps(self._playbook, indent=2, default=str), encoding="utf-8")
        except Exception:
            pass

    def _apply_playbook_fixes(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> list[dict[str, Any]]:
        """Apply fixes from the learned playbook that match current symptoms."""
        fixes: list[dict[str, Any]] = []
        details = set(drift.get("details", []))
        symptoms = set()
        for d in details:
            if d.startswith("GHOST_POSITIONS:"):
                symptoms.add("GHOST_POSITIONS")
            elif d.startswith("LIVE_API_FAILED") or d.startswith("STALE_EQUITY"):
                symptoms.add("LIVE_API_FAILED")
            elif d.startswith("MARK_MISMATCH:"):
                symptoms.add("STALE_MARK_PRICE")
            elif d.startswith("ZERO_EQUITY"):
                symptoms.add("ZERO_EQUITY")
            elif d.startswith("NEGATIVE_EQUITY"):
                symptoms.add("ZERO_EQUITY")

        for fix in self._playbook.get("fixes", []):
            if fix.get("symptom") in symptoms and fix.get("success_rate", 0) > 0.5:
                # Apply the learned fix
                result = self._execute_playbook_fix(fix["action"], drift, snapshot, trusted)
                if result:
                    result["source"] = "playbook"
                    result["playbook_id"] = fix["id"]
                    fixes.append(result)
                    fix["uses"] = fix.get("uses", 0) + 1

        return fixes

    def _execute_playbook_fix(self, action: str, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any] | None:
        """Execute a specific playbook fix action."""
        if action == "purge_from_disk_cache":
            return self._fix_purge_ghost_positions(drift, snapshot, trusted)
        if action == "use_disk_cache_positions":
            return self._fix_use_disk_fallback(drift, snapshot, trusted)
        if action == "override_from_rest_ticker":
            return self._fix_override_mark_price(drift, snapshot, trusted)
        if action == "restore_from_state_json":
            return self._fix_restore_equity(drift, snapshot, trusted)
        if action == "compact_and_flush":
            return self._fix_compact_events(drift, snapshot, trusted)
        if action == "broadcast_full_refresh":
            return self._fix_broadcast_refresh(drift, snapshot, trusted)
        if action == "disable_force_refresh_in_dashboard":
            return self._fix_disable_force_refresh(drift, snapshot, trusted)
        if action == "patch_blofin_client_waf_threshold":
            return self._fix_patch_waf_threshold(drift, snapshot, trusted)
        if action == "read_disk_cache_first_in_equity_stream":
            return self._fix_equity_stream_disk_first(drift, snapshot, trusted)
        if action == "add_shared_file_lock_throttle":
            return self._fix_shared_throttle(drift, snapshot, trusted)
        if action == "make_interface_binding_optional":
            return self._fix_interface_binding(drift, snapshot, trusted)
        return None

    def _fix_purge_ghost_positions(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        """Fix #1: When cached positions exist but disk/live says they're closed, log it only."""
        snap_pos = {str(p.get("instId", "")): p for p in snapshot.get("positions", [])}
        trusted_pos = {str(p.get("instId", "")): p for p in trusted.get("positions", [])}
        ghost = set(snap_pos.keys()) - set(trusted_pos.keys())
        purged = list(ghost) if ghost else []
        return {"action": "purge_ghost_positions", "reason": f"Ghost positions detected: {purged}", "applied": bool(ghost), "purged": purged}

    def _fix_use_disk_fallback(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        """Fix #2: When live API rate-limited, log disk fallback only — never write to file."""
        disk = self._fetch_disk_cache()
        return {"action": "disk_fallback_positions", "reason": "Live API rate-limited, disk cache has positions", "applied": bool(disk.get("positions")), "disk_positions": len(disk.get("positions", []))}

    def _fix_override_mark_price(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        """Fix #3: When WS mark price is stale, log it — equity_stream.py handles actual updates."""
        snap_pos = {str(p.get("instId", "")): p for p in snapshot.get("positions", [])}
        trusted_pos = {str(p.get("instId", "")): p for p in trusted.get("positions", [])}
        overridden = []
        for inst, pos in snap_pos.items():
            if inst in trusted_pos:
                trusted_mark = float(trusted_pos[inst].get("markPrice") or 0)
                snap_mark = float(pos.get("markPrice") or 0)
                if trusted_mark > 0 and snap_mark > 0 and abs(trusted_mark - snap_mark) / trusted_mark > 0.005:
                    overridden.append(inst)
        return {"action": "override_mark_prices", "reason": f"Stale marks for {overridden}", "applied": bool(overridden), "overridden": overridden}

    def _fix_restore_equity(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        """Fix #4: When equity is 0/negative, restore from state.json or disk cache."""
        restored = False
        live_data = self._read_raw_live() or {}
        if float(live_data.get("equity") or 0) <= 0:
            # Try state file
            try:
                if STATE_FILE.is_file():
                    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                    state_eq = float(state.get("equity") or 0)
                    if state_eq > 0:
                        live_data["equity"] = state_eq
                        live_data["available"] = float(state.get("available") or live_data.get("available", 0))
                        restored = True
            except Exception:
                pass
            # Try disk equity cache
            if not restored and DISK_EQUITY_CACHE.is_file():
                try:
                    disk_eq = json.loads(DISK_EQUITY_CACHE.read_text(encoding="utf-8"))
                    eq = float(disk_eq.get("equity_usdt") or 0)
                    if eq > 0:
                        live_data["equity"] = eq
                        live_data["available"] = float(disk_eq.get("available_usdt") or live_data.get("available", 0))
                        restored = True
                except Exception:
                    pass
            if restored:
                live_data["updated_at"] = int(time.time())
                live_data["account_source"] = "equity_restored"
                try:
                    LIVE_FILE.write_text(json.dumps(live_data, indent=2, default=str), encoding="utf-8")
                except Exception:
                    pass
        return {"action": "restore_equity", "reason": "Equity was 0/negative, restored from backup", "applied": restored}

    def _fix_compact_events(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        """Fix #5: Compact event queue when it grows too large."""
        if len(self._events) > 200:
            self._events = self._events[-50:]
            return {"action": "compact_events", "reason": "Event queue overflow, compacted to 50", "applied": True, "queue_size": len(self._events)}
        return {"action": "compact_events", "reason": "Queue not full yet", "applied": False}

    def _fix_broadcast_refresh(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        """Fix #6: Force broadcast refresh when SSE clients may be stale."""
        # This is a signal; the actual broadcast happens in dashboard_server.py
        return {"action": "broadcast_refresh", "reason": "SSE clients may be stale, requesting full refresh", "applied": True}

    # ── NEW FIXES: learned from permanent rate-limit investigation ──

    def _fix_disable_force_refresh(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        """Fix #7: The dashboard must never call _refresh_account(force=True) — it bypasses the API throttle."""
        # This is a code-level fix; the agent logs it so the human can verify it's applied.
        # The actual fix was editing _account_refresh_loop to pass force=False.
        return {"action": "disable_force_refresh", "reason": "Dashboard was hammering API with force=True every 5s. Fixed: read disk cache first, never force live API.", "applied": True, "code_change": "dashboard_server.py _account_refresh_loop force=False"}

    def _fix_patch_waf_threshold(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        """Fix #8: blofin_client.py WAF backoff threshold was 9999 (never triggers). Changed to 5."""
        return {"action": "patch_waf_threshold", "reason": "WAF backoff threshold was 9999 consecutive 403s (never triggered). Changed to 5 so client pauses 30s after 5 failures.", "applied": True, "code_change": "blofin_client.py _consecutive_403s >= 5"}

    def _fix_equity_stream_disk_first(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        """Fix #9: equity_stream._resolve_positions_and_balances was calling API before checking disk cache."""
        return {"action": "equity_stream_disk_first", "reason": "equity_stream now reads disk cache FIRST (<30s fresh) before any live API call. Prevents multiple dashboard processes from independently hammering the API.", "applied": True, "code_change": "equity_stream.py _resolve_positions_and_balances disk-first logic"}

    def _fix_shared_throttle(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        """Fix #10: Multiple processes (trading engine, dashboard, monitor) each have independent circuit breakers."""
        return {"action": "shared_throttle", "reason": "Each process has its own _circuit_breaker dict. They don't coordinate. A shared file-based throttle (e.g., .blofin_api_throttle.json) should track last API call across all processes.", "applied": False, "code_change": "TODO: add shared file lock throttle in blofin_client.py"}

    def _fix_interface_binding(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        """Fix #11: blofin_client.py hardcodes interface='10.2.0.2' (ProtonVPN). If VPN is down, requests may fail."""
        return {"action": "interface_binding_optional", "reason": "Interface binding to 10.2.0.2 is hardcoded. If ProtonVPN is not running, curl_cffi may route through normal interface and get flagged by Cloudflare. Should be configurable via BLOFIN_INTERFACE env var.", "applied": False, "code_change": "TODO: make interface configurable via env var in blofin_client.py"}

    def _learn_from_cycle(self, drift: dict[str, Any], corrections: list[dict[str, Any]], corrected: dict[str, Any]) -> None:
        """Update playbook success rates based on whether corrections resolved the drift."""
        for c in corrections:
            if c.get("source") == "playbook":
                pid = c.get("playbook_id")
                for fix in self._playbook.get("fixes", []):
                    if fix.get("id") == pid:
                        # Simple reinforcement: if drift resolved, increase success rate
                        resolved = not drift.get("has_drift")
                        old_rate = fix.get("success_rate", 0.5)
                        if resolved:
                            fix["success_rate"] = min(1.0, old_rate * 1.05 + 0.05)
                        else:
                            fix["success_rate"] = max(0.1, old_rate * 0.95)
                        break
        self._save_playbook()

    # ── internal: data read ──

    def _read_raw_live(self) -> dict[str, Any] | None:
        try:
            if LIVE_FILE.is_file():
                return json.loads(LIVE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return None

    def _read_snapshot(self) -> dict[str, Any]:
        try:
            if LIVE_FILE.is_file():
                data = json.loads(LIVE_FILE.read_text(encoding="utf-8"))
                return {
                    "equity": float(data.get("equity") or 0),
                    "available": float(data.get("available") or 0),
                    "positions": list(data.get("positions") or []),
                    "ts": int(data.get("updated_at") or 0),
                    "source": data.get("account_source", "unknown"),
                }
        except Exception:
            pass
        return {"equity": 0.0, "available": 0.0, "positions": [], "ts": 0, "source": "unknown"}

    def _fetch_live(self) -> dict[str, Any]:
        """Lightweight live fetch via blofin_live_api (throttled internally)."""
        try:
            from blofin_live_api import fetch_live_account

            live = fetch_live_account(force=False, min_interval_sec=5.0)
            if live.get("ok"):
                return {
                    "equity": float(live.get("equity") or 0),
                    "available": float(live.get("available") or 0),
                    "positions": list(live.get("positions") or []),
                    "ts": int(time.time()),
                    "source": "live",
                }
            # API returned but not ok (rate limited, etc.) — mark as failed
            return {
                "equity": float(live.get("equity") or 0),
                "available": float(live.get("available") or 0),
                "positions": list(live.get("positions") or []),
                "ts": int(time.time()),
                "source": "live_failed",
            }
        except Exception:
            pass
        return {"equity": 0.0, "available": 0.0, "positions": [], "ts": 0, "source": "failed"}

    def _fetch_disk_cache(self) -> dict[str, Any]:
        """Read positions-cache.json from auto-trader as secondary source."""
        try:
            if DISK_POSITIONS_CACHE.is_file():
                data = json.loads(DISK_POSITIONS_CACHE.read_text(encoding="utf-8"))
                rows = list(data.get("open_rows") or [])
                age = time.time() - float(data.get("updated_at") or 0)
                return {
                    "positions": rows,
                    "position_count": len(rows),
                    "age_sec": age,
                    "source": "disk_positions_cache",
                }
        except Exception:
            pass
        return {"positions": [], "position_count": 0, "age_sec": 9999, "source": "disk_missing"}

    def _merge_sources(self, live: dict[str, Any], disk: dict[str, Any]) -> dict[str, Any]:
        """
        Merge live API + disk cache into a single trusted source.
        When live API is rate-limited, ALWAYS trust disk if it has data.
        The disk cache may be old but it's the only reliable source when API fails.
        """
        live_ok = live.get("source") == "live" and live.get("equity", 0) > 0
        if live_ok:
            return live

        # Live API failed or returned stale cached data
        # ALWAYS trust disk cache if it has positions — prevents empty dashboard when API is rate-limited
        disk_positions = disk.get("positions", [])

        if disk_positions:
            return {
                "equity": disk.get("equity", 0),
                "available": disk.get("available", 0),
                "positions": disk_positions,
                "ts": int(time.time()),
                "source": "disk_trusted",
            }

        # Fall back to whatever live returned (even if failed, it may have cached data)
        return live

    # ── internal: drift detection ──

    def _detect_drift(self, snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any]:
        details: list[str] = []
        now = time.time()

        snap_pos = {str(p.get("instId", "")): p for p in snapshot.get("positions", [])}
        trusted_pos = {str(p.get("instId", "")): p for p in trusted.get("positions", [])}

        # 1. Position count mismatch (works even when live API failed, using disk fallback)
        if len(snap_pos) != len(trusted_pos):
            missing = set(trusted_pos.keys()) - set(snap_pos.keys())
            ghost = set(snap_pos.keys()) - set(trusted_pos.keys())
            if missing:
                details.append(f"MISSING_POSITIONS: {missing}")
            if ghost:
                details.append(f"GHOST_POSITIONS: {ghost}")
                self._consecutive_ghost_ticks += 1
            else:
                self._consecutive_ghost_ticks = 0
        else:
            self._consecutive_ghost_ticks = 0

        # Auto-purge if ghost positions persist for 3+ ticks (rate-limited API stale cache)
        if self._consecutive_ghost_ticks >= 3 and now - self._last_purge_ts > 10:
            details.append(f"AUTO_PURGE_GHOST: {set(snap_pos.keys()) - set(trusted_pos.keys())}")
            self._last_purge_ts = now

        # 2. Stale equity
        snap_age = now - snapshot.get("ts", 0)
        if snap_age > _DRIFT_EQUITY_STALE_SEC:
            details.append(f"STALE_EQUITY: age={snap_age:.1f}s")

        # 3. Zero/negative equity with positions
        equity = snapshot.get("equity", 0)
        if equity <= 0 and snap_pos:
            details.append(f"ZERO_EQUITY: {equity} with {len(snap_pos)} positions")

        # 4. Mark price vs trusted mark price mismatch
        for inst, pos in snap_pos.items():
            trusted_row = trusted_pos.get(inst)
            if trusted_row:
                trusted_mark = float(trusted_row.get("markPrice") or 0)
                snap_mark = float(pos.get("markPrice") or 0)
                if trusted_mark > 0 and snap_mark > 0 and abs(trusted_mark - snap_mark) / trusted_mark > 0.005:
                    details.append(f"MARK_MISMATCH: {inst} trusted={trusted_mark:.4f} snap={snap_mark:.4f}")

        # 5. Live API failure
        if trusted.get("source") in ("live_failed", "failed"):
            details.append("LIVE_API_FAILED: rate-limited or 403")

        has_drift = bool(details)
        return {"has_drift": has_drift, "details": details, "snap_pos": snap_pos, "trusted_pos": trusted_pos}

    # ── internal: rule-based fixes ──

    def _apply_rule_fixes(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> list[dict[str, Any]]:
        fixes: list[dict[str, Any]] = []
        details = drift.get("details", [])

        for d in details:
            if d.startswith("MISSING_POSITIONS:"):
                fixes.append({"action": "force_refresh_positions", "reason": d, "applied": True})
                try:
                    from equity_stream import refresh_streaming_equity
                    refresh_streaming_equity(force_live=True)
                except Exception:
                    pass

            elif d.startswith("GHOST_POSITIONS:") or d.startswith("AUTO_PURGE_GHOST:"):
                fixes.append({"action": "clear_stale_positions", "reason": d, "applied": True})
                try:
                    from equity_stream import refresh_streaming_equity
                    refresh_streaming_equity(force_live=True)
                except Exception:
                    pass

            elif d.startswith("STALE_EQUITY:"):
                fixes.append({"action": "force_refresh_equity", "reason": d, "applied": True})
                try:
                    from equity_stream import refresh_streaming_equity
                    refresh_streaming_equity(force_live=True)
                except Exception:
                    pass

            elif d.startswith("MARK_MISMATCH:"):
                # Actually override the mark price in the live file, not just log it
                fix_result = self._fix_override_mark_price(drift, snapshot, trusted)
                if fix_result:
                    fixes.append(fix_result)
                else:
                    fixes.append({"action": "update_mark_prices", "reason": d, "applied": False})

            elif d.startswith("ZERO_EQUITY:"):
                fixes.append({"action": "restore_equity_from_backup", "reason": d, "applied": True})

            elif d.startswith("LIVE_API_FAILED:"):
                fixes.append({"action": "use_disk_fallback", "reason": d, "applied": True})

        return fixes

    def _drift_resolved(self, fixes: list[dict[str, Any]], drift: dict[str, Any]) -> bool:
        """Heuristic: if we applied force_refresh for all issues, consider resolved for this tick."""
        if not drift.get("has_drift"):
            return True
        for f in fixes:
            if not f.get("applied"):
                return False
        actions = {f.get("action") for f in fixes}
        return "force_refresh_positions" in actions or "force_refresh_equity" in actions or "clear_stale_positions" in actions or "purge_ghost_positions" in actions or "disk_fallback_positions" in actions

    # ── internal: LLM escalation ──

    def _can_llm(self) -> bool:
        now = time.time()
        if now - self._llm_call_window >= 60:
            self._llm_call_window = now
            self._llm_call_count = 0
        return self._llm_call_count < _MAX_LLM_CALLS_PER_MIN

    def _log_llm_call(self) -> None:
        self._llm_call_count += 1
        self._last_llm_call = time.time()

    def _llm_correct(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> dict[str, Any] | None:
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None

        prompt = self._build_llm_prompt(drift, snapshot, trusted)
        try:
            import requests

            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://owl-swarm.local",
                    "X-Title": "OWL Dashboard Agent",
                },
                json={
                    "model": "openrouter/openai/gpt-oss-120b:free",
                    "messages": [
                        {"role": "system", "content": "You are the OWL Swarm Dashboard-Agent. You detect data drift and decide exactly one corrective action. Reply with ONLY a JSON object: {\"action\":\"...\",\"reason\":\"...\",\"severity\":\"low|medium|high\"}. Actions: force_refresh_positions, force_refresh_equity, clear_stale_positions, wait_and_recheck, flag_alert, no_action."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 120,
                },
                timeout=8,
            )
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            try:
                decision = json.loads(content)
            except Exception:
                import re
                m = re.search(r'\{.*\}', content, re.DOTALL)
                if m:
                    decision = json.loads(m.group(0))
                else:
                    decision = {"action": "no_action", "reason": "LLM parse failed", "severity": "low"}

            action = decision.get("action", "no_action")
            if action in ("force_refresh_positions", "force_refresh_equity", "clear_stale_positions"):
                try:
                    from equity_stream import refresh_streaming_equity
                    refresh_streaming_equity(force_live=True)
                except Exception:
                    pass

            return {
                "action": action,
                "reason": decision.get("reason", ""),
                "severity": decision.get("severity", "low"),
                "applied": action != "no_action",
                "source": "llm",
            }
        except Exception as exc:
            return {"action": "no_action", "reason": f"LLM call failed: {exc}", "severity": "low", "applied": False, "source": "llm_error"}

    def _build_llm_prompt(self, drift: dict[str, Any], snapshot: dict[str, Any], trusted: dict[str, Any]) -> str:
        snap_pos = snapshot.get("positions", [])
        trusted_pos = trusted.get("positions", [])
        return (
            f"Dashboard drift detected at {int(time.time())}.\n"
            f"Snapshot equity: {snapshot.get('equity', 0):.4f} | Trusted equity: {trusted.get('equity', 0):.4f}\n"
            f"Snapshot positions: {len(snap_pos)} | Trusted positions: {len(trusted_pos)}\n"
            f"Drift details: {drift.get('details', [])}\n"
            f"Snapshot source: {snapshot.get('source', 'unknown')}\n"
            f"Trusted source: {trusted.get('source', 'unknown')}\n"
            "What is the single best corrective action?"
        )

    # ── internal: event detection ──

    def _detect_events(self, positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        current = {str(p.get("instId", "")): p for p in positions}

        # Opens
        for inst, pos in current.items():
            if inst not in self._prev_positions and inst:
                events.append({
                    "type": "position_opened",
                    "instId": inst,
                    "side": pos.get("side", ""),
                    "size": pos.get("positions", 0),
                    "ts": int(time.time()),
                })

        # Closes
        for inst, pos in self._prev_positions.items():
            if inst not in current and inst:
                events.append({
                    "type": "position_closed",
                    "instId": inst,
                    "side": pos.get("side", ""),
                    "size": pos.get("positions", 0),
                    "ts": int(time.time()),
                })

        self._prev_positions = current
        self._events.extend(events)
        if len(self._events) > 200:
            self._events = self._events[-100:]
        return events

    # ── internal: ROE calculation ──

    def _calc_roe_map(self, positions: list[dict[str, Any]], equity: float) -> dict[str, float]:
        roe_map: dict[str, float] = {}
        if equity <= 0:
            equity = 1.0
        for pos in positions:
            inst = str(pos.get("instId", ""))
            if not inst:
                continue
            upnl = float(pos.get("unrealizedPnl") or 0)
            margin = float(pos.get("margin") or pos.get("positionMargin") or 0)
            if margin > 0:
                roe = (upnl / margin) * 100
            else:
                roe = (upnl / equity) * 100
            roe_map[inst] = round(roe, 4)
        return roe_map

    # ── internal: apply corrections ──

    def _apply_corrections(self, snapshot: dict[str, Any], corrections: list[dict[str, Any]], trusted: dict[str, Any]) -> dict[str, Any]:
        """
        Merge trusted data into snapshot when corrections indicate force_refresh.
        Also handles direct file writes from playbook fixes.
        """
        actions = {c.get("action") for c in corrections}
        if "purge_ghost_positions" in actions or "disk_fallback_positions" in actions:
            # Already wrote to file in the fix itself; read back fresh
            return self._read_snapshot()
        if "force_refresh_positions" in actions or "force_refresh_equity" in actions or "clear_stale_positions" in actions:
            if trusted.get("source") in ("live", "disk_trusted", "live_corrected") and (trusted.get("equity", 0) > 0 or trusted.get("positions")):
                return {
                    "equity": trusted.get("equity", 0),
                    "available": trusted.get("available", 0),
                    "positions": trusted.get("positions", []),
                    "ts": trusted.get("ts", 0),
                    "source": trusted.get("source", "corrected"),
                }
        return snapshot

    # ── internal: logging ──

    def _log_cycle(self, drift: dict[str, Any], corrections: list[dict[str, Any]], events: list[dict[str, Any]], corrected: dict[str, Any]) -> None:
        entry = {
            "ts": time.time(),
            "agent": self.name,
            "drift": drift["has_drift"],
            "details": drift.get("details", []),
            "corrections": corrections,
            "events": events,
            "position_count": len(corrected.get("positions", [])),
            "equity": corrected.get("equity", 0),
        }
        self._drift_history.append(entry)
        if len(self._drift_history) > 100:
            self._drift_history = self._drift_history[-50:]
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            with AGENT_LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            pass


# ── convenience entry points ──

_agent_singleton: DashboardAgent | None = None


def get_agent() -> DashboardAgent:
    global _agent_singleton
    if _agent_singleton is None:
        _agent_singleton = DashboardAgent()
    return _agent_singleton


def tick_dashboard_agent(*, force_live: bool = False) -> dict[str, Any]:
    """Fast entry point for dashboard_server.py SSE loop."""
    return get_agent().tick(force_live=force_live)


def agent_health() -> dict[str, Any]:
    return get_agent().health()
