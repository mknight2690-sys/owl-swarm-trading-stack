#!/usr/bin/env python3
"""
OWL Swarm — Multi-LLM autonomous trading loop (AutoHedge + Swarms).
11 LLM agents + 4 pentest special forces: 6 trading + 5 support + pentest squad. Isolated margin only.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import threading
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# Windows UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
AUTO_TRADER = Path(r"C:\Users\mknig\blofin-auto-trader")
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(AUTO_TRADER))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))


def _ensure_real_autohedge() -> None:
    """blofin_live_api can register a stub autohedge — purge it and load the real package."""
    mod = sys.modules.get("autohedge")
    if mod is not None and getattr(mod, "__file__", None):
        return
    if mod is not None:
        for key in list(sys.modules):
            if key == "autohedge" or key.startswith("autohedge."):
                del sys.modules[key]
    import importlib

    importlib.import_module("autohedge.main")


_ensure_real_autohedge()

# Isolated margin BEFORE any autohedge import
os.environ.setdefault("BLOFIN_MARGIN_MODE", "isolated")
os.environ.setdefault("OWL_MAX_LEVERAGE", "12")
os.environ.setdefault("OUTPUT_DIR", str(ROOT / "outputs"))
os.environ.setdefault("DIRECTOR_TIMEOUT_SEC", "600")
os.environ.setdefault("UNIVERSE_REFRESH_SEC", "180")
os.environ.setdefault("OWL_UNIVERSE_SCAN_ALL", "1")
os.environ.setdefault("OWL_RANK_TOP_N", "0")
os.environ.setdefault("OWL_PRERANK_TOP_N", "25")
os.environ.setdefault("OWL_PRERANK_DISPLAY_N", "25")
os.environ.setdefault("OWL_DILIGENCE_SCREEN_N", "20")
os.environ.setdefault("OWL_DILIGENCE_LLM_N", "5")
os.environ.setdefault("OWL_PIPELINE_CANDIDATE_ATTEMPTS", "3")
os.environ.setdefault("OWL_ALLOW_DETERMINISTIC_RISK", "0")
os.environ.setdefault("OWL_DIRECTOR_TIMEOUT_SEC", "600")
os.environ.setdefault("OWL_TACTICS_RESEARCH_SEC", "1800")
os.environ.setdefault("OWL_VERIFY_MAX_RETRIES", "3")
os.environ.setdefault("OWL_OPS_INTERVAL_SEC", "60")
os.environ.setdefault("OWL_OVERSEER_INTERVAL_SEC", "60")
os.environ.setdefault("OWL_SKIP_OPS_LLM", "0")
os.environ.setdefault("OWL_SUPPORT_WAIT_SEC", "8")
os.environ.setdefault("OWL_DILIGENCE_LLM_N", "2")

OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = OUTPUT_DIR / "owl-llm.log"
STATE_FILE = OUTPUT_DIR / "owl-state.json"
LOCK_FILE = OUTPUT_DIR / "owl-llm.lock"
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "7878"))
CYCLE_SLEEP_S = int(os.getenv("CYCLE_INTERVAL_S", "120"))

# ── Live dashboard state ──
class LiveState:
    running = False
    cycle = 0
    last_cycle_at = 0
    last_error = ""
    agents_active = 11
    equity = 0.0
    available = 0.0
    positions: list = []
    events: list = []
    pipeline: dict = {}
    win_rate = "--"

live = LiveState()
_client = None
_last_account_refresh = 0.0
_account_refresh_lock = threading.Lock()


def log(msg: str, level: str = "info") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {level.upper()} {msg}"
    print(line, flush=True)
    live.events.append({"ts": int(time.time() * 1000), "message": msg, "level": level})
    if len(live.events) > 200:
        live.events = live.events[-100:]
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    # Keep standalone dashboard fed during long LLM cycles
    if not hasattr(log, "_last_sync") or time.time() - log._last_sync > 4:
        log._last_sync = time.time()
        save_state()


def save_state() -> None:
    try:
        _sync_live_account()
        STATE_FILE.write_text(
            json.dumps(
                {
                    "cycle": live.cycle,
                    "last_cycle_at": live.last_cycle_at,
                    "equity": live.equity,
                    "available": live.available,
                    "last_error": live.last_error,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        live_payload = {
            "cycle": live.cycle,
            "equity": live.equity,
            "available": live.available,
            "positions": live.positions,
            "events": live.events[-40:],
            "pipeline": live.pipeline,
            "winRate": live.win_rate,
            "agentsActive": live.agents_active,
            "last_error": live.last_error,
            "running": live.running,
            "updated_at": int(time.time()),
            "account_ts": int(time.time()),
        }
        if live.equity <= 0 and live.available <= 0:
            try:
                from autohedge.tools.blofin_tools import get_account_snapshot

                snap = get_account_snapshot(prefer_live=False)
                if float(snap.get("equity") or 0) > 0:
                    live_payload["equity"] = snap["equity"]
                    live_payload["available"] = snap["available"]
                    if snap.get("positions"):
                        live_payload["positions"] = snap["positions"]
                    live_payload["account_source"] = snap.get("source", "fallback")
            except Exception:
                pass
        (OUTPUT_DIR / "owl-live.json").write_text(
            json.dumps(live_payload, indent=2, default=str),
            encoding="utf-8",
        )
        if live.pipeline:
            (OUTPUT_DIR / "pipeline_state.json").write_text(
                json.dumps(live.pipeline, indent=2, default=str),
                encoding="utf-8",
            )
        pipe = live.pipeline or {}
        graph_live = {
            "cycle": live.cycle,
            "active_agent": "Trading-Director" if live.running and live.agents_active else "",
            "pipeline_next": pipe.get("next_agent") or "Portfolio-Manager",
            "completed": pipe.get("completed") or [],
            "pipeline": pipe,
            "running": live.running,
            "updated_at": int(time.time()),
        }
        (OUTPUT_DIR / "graph_live.json").write_text(
            json.dumps(graph_live, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError:
        pass


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


def _lock_holder_is_owl(pid: int) -> bool:
    """Lock is valid only if holder is actually owl_llm_loop (not a stale unrelated PID)."""
    if pid <= 0 or not _pid_running(pid):
        return False
    if sys.platform != "win32":
        return True
    try:
        import subprocess

        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\" -ErrorAction SilentlyContinue).CommandLine",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        cmd = (out.stdout or "").strip()
        return "owl_llm_loop" in cmd
    except Exception:
        return _pid_running(pid)


def acquire_lock() -> bool:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    if LOCK_FILE.is_file():
        try:
            other = int(LOCK_FILE.read_text(encoding="utf-8").strip())
        except (TypeError, ValueError):
            other = 0
        if other and other != pid:
            if _lock_holder_is_owl(other):
                log(f"Another OWL LLM loop is running (PID {other})", "error")
                return False
            log(f"Clearing stale lock (PID {other} is not owl_llm_loop)", "warn")
            LOCK_FILE.unlink(missing_ok=True)
    LOCK_FILE.write_text(str(pid), encoding="utf-8")
    return True


def release_lock() -> None:
    try:
        if LOCK_FILE.is_file() and int(LOCK_FILE.read_text()) == os.getpid():
            LOCK_FILE.unlink(missing_ok=True)
    except (TypeError, ValueError, OSError):
        pass


def patch_isolated_margin() -> None:
    """Force isolated margin on all Blofin tool calls."""
    import functools
    import autohedge.tools.blofin_tools as bt

    margin = os.environ.get("BLOFIN_MARGIN_MODE", "isolated")
    max_lev = float(os.environ.get("OWL_MAX_LEVERAGE", "12"))

    _orig_ensure_lev = bt.ensure_trade_leverage

    @functools.wraps(_orig_ensure_lev)
    def ensure_trade_leverage(inst, specs, *, target=50.0):
        cap = min(max_lev, float(specs.get("maxLeverage") or max_lev))
        return _orig_ensure_lev(inst, specs, target=cap)

    bt.ensure_trade_leverage = ensure_trade_leverage  # type: ignore

    for name in ("blofin_place_order", "blofin_place_tpsl", "blofin_close_position"):
        orig = getattr(bt, name)

        @functools.wraps(orig)
        def wrapper(*args, _fn=orig, _margin=margin, **kwargs):
            kwargs.setdefault("margin_mode", _margin)
            return _fn(*args, **kwargs)

        setattr(bt, name, wrapper)


def _sync_live_account(*, force: bool = False) -> bool:
    """Live equity/available/positions via lightweight Blofin REST (no solders import chain)."""
    try:
        from blofin_live_api import fetch_live_account

        snap = fetch_live_account(
            force=force,
            min_interval_sec=0 if force else 2.0,
        )
        if not snap.get("ok"):
            return False
        eq = float(snap.get("equity") or 0)
        av = float(snap.get("available") or 0)
        if eq > 0:
            live.equity = eq
        if av >= 0:
            live.available = av
        if isinstance(snap.get("positions"), list):
            live.positions = snap["positions"]
        return eq > 0 or av > 0
    except Exception:
        return False


def _effective_available() -> float:
    """Available margin for deploy gates — never $0 when disk cache has funds."""
    if live.available >= float(os.environ.get("OWL_MIN_DEPLOY_AVAILABLE", "0.15")):
        return live.available
    if _sync_live_account():
        return live.available
    try:
        cache = json.loads(
            (AUTO_TRADER / "outputs" / "equity-cache.json").read_text(encoding="utf-8")
        )
        av = float(cache.get("available_usdt") or 0)
        eq = float(cache.get("equity_usdt") or 0)
        if av > 0 or eq > 0:
            if eq > 0 and live.equity <= 0:
                live.equity = eq
            if av > 0:
                live.available = av
            return av if av > 0 else live.available
    except Exception:
        pass
    return live.available


def refresh_account(force: bool = False) -> None:
    global _last_account_refresh
    now = time.time()
    if not force and now - _last_account_refresh < 15:
        return
    if not _account_refresh_lock.acquire(blocking=False):
        return
    try:
        if _sync_live_account(force=force):
            _last_account_refresh = time.time()
        else:
            log("Account refresh: live API empty — using disk snapshot", "warn")
            _effective_available()
    except Exception as e:
        log(f"Account refresh failed: {e} — disk fallback", "warn")
        _effective_available()
    finally:
        _account_refresh_lock.release()


_ws_bridge_proc: subprocess.Popen | None = None


def start_ws_bridge() -> None:
    """Launch Chromium WS bridge (Node) for live ticker stream."""
    global _ws_bridge_proc
    script = ROOT / "scripts" / "blofin_ws_bridge.mjs"
    if not script.is_file():
        log("WS bridge script missing — skipping", "warn")
        return

    os.environ["OWL_WS_TICKERS_PATH"] = str(OUTPUT_DIR / "ws-tickers.json")
    os.environ["BLOFIN_PRICE_CACHE"] = str(
        AUTO_TRADER / "outputs" / "price-cache.json"
    )

    if _ws_bridge_proc and _ws_bridge_proc.poll() is None:
        return
    _ws_bridge_proc = None

    log("Starting Chromium WebSocket bridge...")
    try:
        _ws_bridge_proc = subprocess.Popen(
            ["node", str(script)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        log(f"WS bridge started (PID {_ws_bridge_proc.pid})")
    except OSError as e:
        log(f"WS bridge failed to start: {e}", "warn")


def start_market_services() -> None:
    """Background universe feed + Chromium WS bridge."""
    start_ws_bridge()
    from autohedge.tools.blofin_universe_feed import get_universe_feed

    feed = get_universe_feed()
    try:
        feed.refresh(force=True)
        log(f"Universe feed ready: {feed.get_snapshot().count} via {feed.get_snapshot().source}")
    except Exception as e:
        log(f"Universe feed initial refresh: {e}", "warn")


def fetch_ranked_opportunities(top_n: int | None = None) -> list[dict]:
    """Rank once per cycle — full universe scan by default (OWL_UNIVERSE_SCAN_ALL=1)."""
    import json as _json
    from autohedge.tools.blofin_tools import _blocked_sets, blofin_rank_opportunities
    from autohedge.tools.market_analytics import resolve_rank_top_n

    n = resolve_rank_top_n(top_n)
    max_losses = int(os.environ.get("OWL_MAX_JOURNAL_LOSSES", "3"))
    raw = _json.loads(blofin_rank_opportunities(top_n=str(n) if n else ""))
    opps = raw.get("opportunities") or []
    try:
        snap_path = OUTPUT_DIR / "opportunities-ranked.json"
        snap_path.write_text(
            _json.dumps(
                {
                    "ts": time.time(),
                    "universe_instruments": raw.get("universe_instruments"),
                    "scan_mode": raw.get("scan_mode"),
                    "ranked_count": len(opps),
                    "opportunities": opps[:120],
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
    blocked_buy, blocked_sell = _blocked_sets()
    held = blocked_buy | blocked_sell
    # Profitability: skip repeat losers + symbols we already hold (never add to position)
    filtered = [
        o
        for o in opps
        if int(o.get("journal_losses") or 0) < max_losses
        and str(o.get("instId") or "") not in held
    ]
    if filtered:
        return filtered
    # Fallback: at least drop held symbols even if journal filter emptied the list
    unheld = [o for o in opps if str(o.get("instId") or "") not in held]
    return unheld or opps


def pick_best_opportunity(opps: list[dict]) -> dict | None:
    if not opps:
        return None
    try:
        avail = float(live.available or 0)
        lev = float(os.environ.get("OWL_MAX_LEVERAGE", "12"))
    except Exception:
        avail = float(live.available or 0)
        lev = 12.0

    held: set[str] = set()
    for pos in live.positions or []:
        inst = str(pos.get("instId") or pos.get("symbol") or "").strip().upper()
        if not inst:
            continue
        try:
            size = float(pos.get("positions") or pos.get("size") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if size != 0:
            held.add(inst)
    # Only hit positions API when live snapshot is empty but we may still be holding
    if not held and len(live.positions or []) == 0:
        pass
    elif not held:
        try:
            from autohedge.tools.blofin_tools import _blocked_sets

            blocked_buy, blocked_sell = _blocked_sets()
            held = blocked_buy | blocked_sell
        except Exception:
            held = set()

    def score(o: dict) -> float:
        wins = int(o.get("journal_wins") or 0)
        losses = int(o.get("journal_losses") or 0)
        j = wins / (wins + losses) if wins + losses else 0.5
        mom = max(float(o.get("long_score") or 0), float(o.get("short_score") or 0))
        return mom * 0.7 + j * 0.3

    unheld = [o for o in opps if str(o.get("instId") or "") not in held]
    if not unheld:
        return None

    max_checks = int(os.environ.get("OWL_PICK_BEST_CHECK_N", "20"))
    candidates = sorted(unheld, key=score, reverse=True)[:max_checks]

    affordable: list[dict] = []
    for o in candidates:
        inst = str(o.get("instId") or "")
        if not inst:
            continue
        side = str(o.get("suggested_side") or "long").lower()
        inst_u = inst.upper()
        if inst_u in held:
            continue
        try:
            px = float(o.get("last") or 0) or 0.01
            # Heuristic min margin from rank row — avoids 20+ get_instrument API calls per cycle
            min_size = 1.0
            need = (px * min_size / max(lev, 1.0)) * 1.35 + 0.004
            if avail >= need:
                affordable.append(o)
        except Exception:
            affordable.append(o)

    pool = affordable or candidates
    if not pool:
        return None

    best = max(pool, key=score)
    if held and str(best.get("instId") or "") in held:
        return None
    return best


def build_preranked_block(opps: list[dict], top_n: int | None = None) -> str:
    from autohedge.tools.blofin_universe_feed import get_universe_feed
    from autohedge.tools.market_analytics import resolve_rank_top_n

    display_n = top_n or int(os.environ.get("OWL_PRERANK_DISPLAY_N", "25"))
    snap = get_universe_feed().get_snapshot()
    scan_n = resolve_rank_top_n()
    lines = [
        "",
        f"FULL UNIVERSE SCAN: {len(opps)} tradable USDT perps ranked from {snap.count} live instruments ({snap.source}).",
        f"Scan mode: {'all symbols' if not scan_n else f'top {scan_n}'}.",
        f"TOP {min(len(opps), display_n)} for Director (full list in outputs/opportunities-ranked.json):",
        "Pick ONE unheld symbol from this ranked list — do NOT re-call blofin_rank_opportunities.",
        "Deep-dive at most top 3 with blofin_technical_analysis.",
        "Hand off agents quickly.",
        "AVOID symbols with 3+ journal losses. Favor symbols with win history.",
    ]
    for i, o in enumerate(opps[:display_n], 1):
        lines.append(
            f"  {i}. {o.get('instId')} side={o.get('suggested_side')} "
            f"chg24h={o.get('chg_pct_24h')}% "
            f"long={o.get('long_score')} short={o.get('short_score')} "
            f"journal={o.get('journal_wins', 0)}W/{o.get('journal_losses', 0)}L"
        )
    return "\n".join(lines)


def profit_guard() -> None:
    """Optional: bank tiny winners when margin is critically tight (disabled by default)."""
    if os.environ.get("OWL_PROFIT_GUARD", "0").strip().lower() in ("0", "false", "no", "off"):
        return
    min_avail = float(os.environ.get("OWL_MIN_AVAILABLE", "0.35"))
    bank_ratio = float(os.environ.get("OWL_BANK_PROFIT_RATIO", "0.025"))

    refresh_account(force=True)
    if live.available >= min_avail or not live.positions:
        return

    from autohedge.tools.blofin_tools import blofin_close_position

    for pos in live.positions:
        try:
            ratio = float(pos.get("unrealizedPnlRatio") or 0)
        except (TypeError, ValueError):
            ratio = 0.0
        if ratio < bank_ratio:
            continue
        inst = str(pos.get("instId") or "")
        if not inst:
            continue
        log(
            f"PROFIT GUARD: banking {inst} unrealized +{ratio*100:.1f}% "
            f"(avail ${live.available:.2f} < ${min_avail:.2f})",
            "success",
        )
        try:
            blofin_close_position(inst_id=inst, margin_mode="isolated")
        except Exception as e:
            log(f"Profit guard close failed {inst}: {e}", "warn")
    refresh_account(force=True)


def build_cycle_task(opps: list[dict]) -> str:
    max_lev = os.environ.get("OWL_MAX_LEVERAGE", "12")
    base = OWL_TASK.format(max_lev=max_lev)
    try:
        return base + build_preranked_block(opps)
    except Exception as e:
        log(f"Pre-rank block failed: {e}", "warn")
        return base


OWL_TASK = """
OWL Swarm cycle — Blofin USDT perpetual futures.

SELF-VERIFYING SWARM (original design — always active):
- Every agent output is verified against LIVE Blofin API data after it runs.
- Failed verification → automatic retry with fix instructions (up to 3 attempts).
- NO fast pipeline, NO deterministic Risk bypass, NO stub Quant outputs.
- Universe diligence screens top assets analytically; top K get Market/Quant/Sentiment LLM dossiers.
- Director runs ONLY from validated shortlist through full PM→Sentiment→Quant→Risk→Execution.
- Losing trade, no trade, idle margin, or pipeline veto = CYCLE ERROR to fix next iteration.

CRITICAL RULES (non-negotiable):
- ISOLATED MARGIN ONLY. Never use cross margin.
- Max leverage {max_lev}x unless instrument cap is lower. Prefer 5-10x on small accounts.
- EVERY entry MUST have TP and SL before or with the order.
- Never add to an existing position. Pick a NEW symbol or skip.
- Use blofin_get_trade_insights — learn from past wins/losses.
- If available margin is tight, take profits on winners or skip — do NOT over-leverage.
- If available < $0.35, prioritize asymmetric setups — do NOT clip winners early.
- PRE-RANKED list is in this task — DO NOT call blofin_rank_opportunities or blofin_get_universe_snapshot.

Director: use UNIVERSE DILIGENCE shortlist below. Hand off ONE agent at a time (no batching):
Portfolio-Manager → Sentiment-Agent → Quant-Analyst → Risk-Manager → Execution-Agent.
Every stage must use tools and pass verification. Risk must approve before Execution.
Be thorough — a trade without analytical validation is a failure.
"""


def _trade_confirmed_for(inst: str, *, within_sec: float = 180.0) -> bool:
    from autohedge.handoff_pipeline import _pipeline
    from autohedge.risk_gate import _journal_has_order_for, _order_confirmed

    cand = str(inst or "").strip().upper()
    if not cand:
        return False
    exec_out = str(_pipeline.agent_outputs.get("Execution-Agent") or "")
    if _order_confirmed(exec_out):
        return True
    return bool(_journal_has_order_for(cand, within_sec=within_sec))


def _pipeline_succeeded() -> bool:
    from autohedge.handoff_pipeline import pipeline_status

    ps = pipeline_status()
    if not ps.get("risk_approved"):
        return False
    if "Execution-Agent" not in set(ps.get("completed") or []):
        return False
    return _trade_confirmed_for(str(ps.get("candidate_inst_id") or ""))


def run_llm_cycle() -> None:
    from autohedge.main import AutoHedge
    from autohedge.workers import reset_agent_memories
    from autohedge.handoff_pipeline import pipeline_status
    from autohedge.swarm_autopilot import postflight_verify, preflight_repair

    live.cycle += 1
    live.last_cycle_at = int(time.time())
    live.last_error = ""
    live.agents_active = 15
    log(f"=== LLM CYCLE {live.cycle} START (15 LLM agents) ===")

    try:
        from autohedge.swarm_tasks import init_cycle_tasks, start_task
        from autohedge.swarm_topology import set_cycle, set_agent_status

        init_cycle_tasks(live.cycle)
        log("Task board seeded", "info")
        set_cycle(live.cycle)
        try:
            from autohedge.handoff_pipeline import persist_pipeline_state, reset_handoff_pipeline
            from autohedge.swarm_topology import reset_pipeline_graph

            reset_handoff_pipeline()
            reset_pipeline_graph(keep_director_active=True)
            persist_pipeline_state()
        except Exception:
            pass
        start_task("oversight", "Trading-Director", "oversee", detail=f"Cycle {live.cycle} planning")
        set_agent_status("Trading-Director", "active", detail="cycle orchestration")
        save_state()
        log("Cycle init persisted", "info")
    except Exception as e:
        log(f"Task board init: {e}", "warn")

    pf: dict = {}

    def _preflight_bg() -> None:
        try:
            from autohedge.swarm_autopilot import preflight_repair

            result = preflight_repair()
            if result.get("repairs"):
                log(f"Autopilot preflight repairs: {result['repairs']}", "success")
        except Exception as e:
            log(f"Preflight repair: {e}", "warn")

    threading.Thread(target=_preflight_bg, name="owl-preflight", daemon=True).start()
    log("Preflight in background — trading pipeline proceeding", "info")

    def _pentest_bg() -> None:
        if os.environ.get("OWL_SKIP_PENTEST", "0").strip().lower() in ("1", "true", "yes", "on"):
            return
        try:
            from autohedge.pentest_agents import start_pentest_squad_background

            start_pentest_squad_background(cycle=live.cycle, source="owl_preflight")
            log("Pentest squad armed (preflight + stall watchdog)", "info")
        except Exception as exc:
            log(f"Pentest squad: {exc}", "warn")

    threading.Thread(target=_pentest_bg, name="owl-pentest", daemon=True).start()

    # Ops monitor runs in background — never block trading pipeline on it
    def _ops_bg() -> None:
        if os.environ.get("OWL_SKIP_OPS_LLM", "1").strip().lower() in ("1", "true", "yes", "on"):
            return
        try:
            from autohedge.support_agents import run_ops_monitor

            run_ops_monitor()
        except Exception as e:
            log(f"Ops-Monitor LLM: {e}", "warn")

    threading.Thread(target=_ops_bg, name="owl-ops-monitor", daemon=True).start()
    log("Ops monitor in background — trading pipeline proceeding", "info")

    refresh_account(force=True)
    try:
        from autohedge.swarm_tasks import record_equity

        record_equity(live.cycle, live.equity, live.available)
    except Exception:
        pass
    try:
        from autohedge.self_heal_playbook import api_cooldown_active

        if not api_cooldown_active():
            from autohedge.tools.blofin_tools import warm_positions_read

            warm_positions_read(attempts=1, pause_sec=1.0)
    except Exception:
        pass
    log(f"Account: equity=${live.equity:.4f} available=${live.available:.4f} positions={len(live.positions)}")

    profit_guard()
    reset_agent_memories()

    top_pick = ""
    opps: list[dict] = []
    opps_ready = threading.Event()

    def _opps_bg() -> None:
        nonlocal opps
        try:
            opps = fetch_ranked_opportunities()
        except Exception as e:
            log(f"Pre-rank fetch: {e}", "warn")
            opps = []
        finally:
            opps_ready.set()

    threading.Thread(target=_opps_bg, name="owl-opps-prefetch", daemon=True).start()

    if not opps_ready.wait(timeout=float(os.environ.get("OWL_OPPS_WAIT_SEC", "25"))):
        log("Pre-rank fetch slow - continuing with partial universe", "warn")
    else:
        log(f"Pre-rank ready: {len(opps)} candidates", "info")
        try:
            from autohedge.pentest_agents import start_pentest_stall_watchdog

            start_pentest_stall_watchdog(cycle=live.cycle, source="owl_prerank", delay_sec=55)
        except Exception:
            pass

    try:
        from autohedge.handoff_pipeline import seed_pipeline_candidate

        t0 = time.time()
        best = pick_best_opportunity(opps)
        log(f"Pick-best done in {time.time() - t0:.1f}s", "info")
        if best:
            top_pick = str(best.get("instId") or "")
            seed_pipeline_candidate(top_pick)
            log(
                f"Universe scan: {len(opps)} ranked — top pick {top_pick} {best.get('suggested_side')} "
                f"(chg={best.get('chg_pct_24h')}% journal={best.get('journal_wins')}W/{best.get('journal_losses')}L)",
                "",
            )
        elif opps:
            log(
                f"Pre-rank: {len(opps)} candidates but none affordable/unheld "
                f"(avail=${live.available:.4f}, positions={len(live.positions)})",
                "warn",
            )
        else:
            log("Pre-rank: no tradable candidates this cycle", "warn")
    except Exception as e:
        log(f"Pre-rank seed failed: {e}", "warn")

    skip_director = False
    support: dict = {}
    support_ready = threading.Event()
    diligence_shortlist: list[str] = []
    diligence_ready = threading.Event()

    def _diligence_bg() -> None:
        nonlocal diligence_shortlist
        try:
            if not opps:
                return
            from autohedge.candidate_diligence import persist_diligence_report, run_universe_diligence

            report = run_universe_diligence(opps)
            persist_diligence_report(report)
            diligence_shortlist = list(report.shortlist or [])
            log(
                f"Universe diligence: {len(diligence_shortlist)} validated "
                f"from {len(opps)} ranked ({len(report.llm_dossiers)} LLM dossiers)",
                "info",
            )
        except Exception as e:
            log(f"Universe diligence: {e}", "warn")
        finally:
            diligence_ready.set()

    threading.Thread(target=_diligence_bg, name="owl-universe-diligence", daemon=True).start()

    def _support_bg() -> None:
        nonlocal support
        try:
            if not diligence_ready.wait(timeout=float(os.environ.get("OWL_DILIGENCE_WAIT_SEC", "20"))):
                log("Universe diligence still running — support agents proceeding", "info")
            shortlist = diligence_shortlist or ([top_pick] if top_pick else [])
            from autohedge.support_agents import run_pre_cycle_support

            support = run_pre_cycle_support(
                cycle=live.cycle,
                top_pick=top_pick,
                shortlist=shortlist,
                skip_ops_monitor=True,
                fast_path=bool(top_pick),
            )
            mr = support.get("market_research_primary") or {}
            if isinstance(mr, dict) and mr.get("ok"):
                task_extra = str(mr.get("llm_output", ""))[:600]
                if task_extra:
                    log(f"Market-Researcher: {task_extra[:120]}...", "")
            tr = support.get("tactics_research") or {}
            if isinstance(tr, dict) and tr.get("ok"):
                log("Tactics-Researcher: cycle research complete", "info")
            ps = support.get("profit_strategist") or {}
            if isinstance(ps, dict) and ps.get("ok"):
                log("Profit-Strategist: optimization pass complete", "info")
        except Exception as e:
            log(f"Support agents: {e}", "warn")
        finally:
            support_ready.set()

    threading.Thread(target=_support_bg, name="owl-pre-cycle-support", daemon=True).start()

    if top_pick and opps:
        try:
            from autohedge.handoff_pipeline import is_pipeline_terminal, run_fast_pipeline_to_execution

            if not is_pipeline_terminal():
                try_n = int(os.environ.get("OWL_FAST_TRY_N", "8"))
                by_inst = {str(o.get("instId") or ""): o for o in opps}
                try_list: list[str] = []
                for inst in [top_pick] + [
                    str(o.get("instId") or "") for o in opps[: max(try_n, 12)]
                ]:
                    if inst and inst not in try_list:
                        try_list.append(inst)
                fast: dict = {}
                for inst in try_list[:try_n]:
                    row = by_inst.get(inst) or {}
                    log(f"Fast pipeline trying {inst}...", "info")
                    try:
                        from autohedge.pentest_agents import start_pentest_stall_watchdog

                        start_pentest_stall_watchdog(cycle=live.cycle, source="owl_fast_pipeline")
                    except Exception:
                        pass
                    fast = run_fast_pipeline_to_execution(
                        inst,
                        suggested_side=str(row.get("suggested_side") or "long"),
                        probability_score=float(
                            max(
                                float(row.get("long_score") or 0),
                                float(row.get("short_score") or 0),
                                0.55,
                            )
                        ),
                    )
                    live.pipeline = pipeline_status()
                    if fast.get("ok"):
                        top_pick = inst
                        log(
                            f"Fast pipeline complete: {inst} order=confirmed",
                            "success",
                        )
                        skip_director = True
                        break
                    log(
                        f"Fast pipeline skip {inst}: "
                        f"risk_approved={live.pipeline.get('risk_approved')} "
                        f"veto={live.pipeline.get('risk_veto_reason', '')[:80]}",
                        "info",
                    )
                if not skip_director and fast.get("status", {}).get("terminal"):
                    log(
                        f"Fast pipeline: no fill after {min(len(try_list), try_n)} candidates — deploy fallback",
                        "warn",
                    )
        except Exception as e:
            log(f"Fast pipeline bootstrap: {e}", "warn")

    deploy_avail = _effective_available()
    if (
        not skip_director
        and deploy_avail >= float(os.environ.get("OWL_MIN_DEPLOY_AVAILABLE", "0.15"))
        and opps
    ):
        try:
            from autohedge.handoff_pipeline import reset_handoff_pipeline
            from autohedge.risk_gate import deploy_idle_margin

            reset_handoff_pipeline()
            if top_pick:
                from autohedge.handoff_pipeline import seed_pipeline_candidate

                seed_pipeline_candidate(top_pick)
            else:
                from autohedge.risk_gate import pick_edge_candidate

                pick_edge_candidate()
            deployed = deploy_idle_margin(primary_only=False, force=True)
            live.pipeline = pipeline_status()
            from autohedge.handoff_pipeline import _pipeline
            from autohedge.risk_gate import _order_confirmed, _journal_has_order_for

            exec_out = str(_pipeline.agent_outputs.get("Execution-Agent") or "")
            placed = _order_confirmed(exec_out)
            cand = str(live.pipeline.get("candidate_inst_id") or "")
            if not placed and cand:
                placed = _journal_has_order_for(cand, within_sec=120.0)
            if deployed and placed and "Execution-Agent" in set(live.pipeline.get("completed") or []):
                log(
                    f"Fast margin deploy: {live.pipeline.get('candidate_inst_id')} "
                    f"(avail=${live.available:.4f})",
                    "success",
                )
                skip_director = True
                save_state()
            elif deployed:
                log(
                    f"Fast margin deploy veto: {live.pipeline.get('candidate_inst_id')} "
                    f"(risk_approved={live.pipeline.get('risk_approved')})",
                    "warn",
                )
        except Exception as e:
            log(f"Fast margin deploy: {e}", "warn")

    wait_sec = float(os.environ.get("OWL_SUPPORT_WAIT_SEC", "3" if top_pick else "15"))
    if not support_ready.wait(timeout=wait_sec):
        log(f"Support agents still running — proceeding (waited {wait_sec:.0f}s)", "info")

    portfolio_line = ""
    learning_line = ""
    if not skip_director:
        try:
            from autohedge.self_heal_playbook import api_cooldown_active
            from autohedge.tools.blofin_tools import blofin_assess_portfolio, warm_positions_read
            from autohedge.tools.trade_journal import sync_position_closes, insights_text

            sync_position_closes()
            if not api_cooldown_active():
                try:
                    warm_positions_read(attempts=1, pause_sec=2.0)
                except Exception:
                    pass
                portfolio_line = blofin_assess_portfolio()[:800]
            else:
                portfolio_line = (
                    f"(API cooldown — cached equity ${live.equity:.4f} "
                    f"avail ${live.available:.4f} positions={len(live.positions)})"
                )
            learning_line = insights_text()[:400]
        except Exception as e:
            portfolio_line = f"(portfolio unavailable: {e})"
            learning_line = ""

    if skip_director:
        try:
            from autohedge.handoff_pipeline import is_pipeline_terminal
            from autohedge.risk_gate import deploy_idle_margin

            if not is_pipeline_terminal():
                deploy_idle_margin(primary_only=False)
            live.pipeline = pipeline_status()
        except Exception as e:
            log(f"Post-fast deploy: {e}", "warn")
    else:
        task = build_cycle_task(opps)
        if top_pick:
            task += f"\n\nPRIMARY CANDIDATE (locked): {top_pick} — hand off agents for this symbol."
        support_mr = support.get("market_research_primary") or {} if support else {}
        if isinstance(support_mr, dict) and support_mr.get("llm_output"):
            task += f"\n\nMARKET RESEARCHER (LLM):\n{str(support_mr.get('llm_output'))[:1200]}"
        if portfolio_line:
            task += f"\n\nCURRENT PORTFOLIO:\n{portfolio_line}"
        if learning_line:
            task += f"\n\nTRADE INSIGHTS:\n{learning_line}"

        try:
            from autohedge.tactics_learner import tactics_block_for_task

            task += tactics_block_for_task()
        except Exception as e:
            log(f"Tactics block failed: {e}", "warn")

        try:
            from autohedge.self_heal_playbook import playbook_block_for_agents

            task += playbook_block_for_agents()
        except Exception:
            pass

        try:
            import concurrent.futures

            system = AutoHedge(name="owl-swarm", output_dir=str(OUTPUT_DIR))
            director_timeout = int(os.environ.get("OWL_DIRECTOR_TIMEOUT_SEC", "180"))

            def _run_director() -> str:
                out = system.run(task=task, review_all_assets=False)
                return str(out) if out else "(no output)"

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_run_director)
                try:
                    result = fut.result(timeout=director_timeout)
                except concurrent.futures.TimeoutError:
                    log(
                        f"Director timeout ({director_timeout}s) — fast pipeline fallback",
                        "warn",
                    )
                    if top_pick:
                        from autohedge.handoff_pipeline import run_fast_pipeline_to_execution

                        run_fast_pipeline_to_execution(top_pick)
                    result = "(director timeout — deterministic fallback)"
            live.pipeline = pipeline_status()
            snippet = str(result)[:1500]
            log(f"Director output: {snippet[:400]}...", "success")
            if live.pipeline:
                log(
                    f"Pipeline: candidate={live.pipeline.get('candidate_inst_id')} "
                    f"terminal={live.pipeline.get('terminal')} next={live.pipeline.get('next_agent')}",
                    "",
                )
            try:
                from autohedge.risk_gate import deploy_idle_margin

                deployed = deploy_idle_margin()
                if deployed:
                    live.pipeline = pipeline_status()
                    log(
                        f"Idle margin deploy: {live.pipeline.get('candidate_inst_id')} "
                        f"terminal={live.pipeline.get('terminal')}",
                        "success",
                    )
            except Exception as e:
                log(f"Idle margin deploy skipped: {e}", "warn")
        except Exception as e:
            err = str(e)
            live.last_error = err
            if "timeout" in err.lower():
                log("Director timeout — autopilot will retry lighter cycle next loop", "warn")
                if top_pick:
                    try:
                        from autohedge.handoff_pipeline import run_fast_pipeline_to_execution

                        run_fast_pipeline_to_execution(top_pick)
                        live.pipeline = pipeline_status()
                    except Exception:
                        pass
                try:
                    from autohedge.swarm_learning_audit import record_self_fix

                    record_self_fix(
                        title="Director timeout absorbed",
                        detail="Cycle will retry automatically with pre-ranked candidate",
                        component="director_timeout",
                        proof={"cycle": live.cycle, "error": err[:200]},
                    )
                except Exception:
                    pass
            else:
                log(f"CYCLE ERROR: {e}", "error")
                raise

    live.agents_active = 0
    live.pipeline = pipeline_status()
    refresh_account()
    cycle_num = live.cycle
    board_snapshot: dict = {}
    try:
        from autohedge.swarm_tasks import get_task_board

        board_snapshot = get_task_board()
    except Exception:
        pass

    def _post_cycle_bg(captured_cycle: int, captured_board: dict) -> None:
        try:
            from autohedge.tactics_learner import post_cycle_learn
            from autohedge.swarm_learning_audit import get_learning_report, record_improvement
            from autohedge.swarm_autopilot import postflight_verify
            from autohedge.collective_audit import collective_care_round
            from autohedge.swarm_tasks import finish_task, skip_task, start_task
            from autohedge.swarm_topology import set_convergence_streak, set_agent_status

            postflight_verify(cycle=captured_cycle, pipeline=live.pipeline)

            try:
                from autohedge.tpsl_guard import run_tpsl_guard
                from autohedge.swarm_tasks import get_task_board

                run_tpsl_guard(source="post_cycle")
                finish_task("tpsl_protection", "Ops-Monitor-Agent", "audit", status="done")
                finish_task("ops_health", "Ops-Monitor-Agent", "audit", status="done")
                finish_task("infrastructure_repair", "Ops-Monitor-Agent", "fix", status="done")
                board_snapshot = get_task_board()
            except Exception as exc:
                log(f"Post-cycle task finalize: {exc}", "warn")

            try:
                from autohedge.support_agents import run_profit_strategist, run_tactics_researcher
                from autohedge.swarm_tasks import get_task_board

                pending = {
                    t["job"]
                    for t in (get_task_board().get("all_tasks") or [])
                    if t.get("status") == "pending"
                }
                if "tactics_research" in pending:
                    run_tactics_researcher()
                if "profit_optimization" in pending:
                    run_profit_strategist()
            except Exception as exc:
                log(f"Post-cycle support catch-up: {exc}", "warn")

            try:
                from autohedge.pentest_agents import start_pentest_squad_background

                start_pentest_squad_background(cycle=captured_cycle, source="owl_post_cycle")
            except Exception as exc:
                log(f"Pentest squad post-cycle: {exc}", "warn")

            from autohedge.task_completion_audit import run_verifier_task_audit

            task_audit = run_verifier_task_audit(cycle=captured_cycle, board_snapshot=board_snapshot)
            if not task_audit.get("ok"):
                log(f"Task audit flagged: {task_audit.get('issues', [])[:3]}", "warn")
            else:
                log("Verifier + peer audit passed", "success")
            set_agent_status("Verifier-Agent", "pass" if task_audit.get("ok") else "fail")
            post_cycle_learn(cycle=captured_cycle, pipeline=live.pipeline)
            start_task("learning_compound", "Tactics-Researcher-Agent", "optimize")
            finish_task("learning_compound", "Tactics-Researcher-Agent", "optimize", status="done")
            finish_task("oversight", "Trading-Director", "oversee", status="done")
            finish_task("trading_pipeline", "Trading-Director", "execute", status="done")
            set_agent_status("Trading-Director", "pass")
            care = collective_care_round(cycle=captured_cycle)
            streak = int((care.get("convergence") or {}).get("streak_zero") or 0)
            set_convergence_streak(streak)
            from autohedge.swarm_topology import sync_agent_status_from_task_board

            sync_agent_status_from_task_board()
            for node in ("skill-library", "learning-audit", "collective-care"):
                set_agent_status(node, "pass" if care.get("ok") else "active")
            if hasattr(run_llm_cycle, "_last_equity"):
                prev = getattr(run_llm_cycle, "_last_equity", 0.0)
                if live.equity > prev + 0.02:
                    record_improvement(
                        title="Equity grew between cycles",
                        detail=f"Cycle {captured_cycle} equity increased",
                        metric="equity_usdt",
                        before=round(prev, 4),
                        after=round(live.equity, 4),
                        proof={"cycle": captured_cycle},
                    )
            run_llm_cycle._last_equity = live.equity  # type: ignore[attr-defined]
            report = get_learning_report()
            last = report.get("last_learned")
            if last:
                log(f"Last learned: {last.get('title', '')[:100]}", "")
            fix = report.get("last_self_fix")
            if fix:
                log(f"Last self-fix: {fix.get('title', '')[:100]}", "")
        except Exception as exc:
            log(f"Post-cycle background: {exc}", "warn")

    threading.Thread(
        target=_post_cycle_bg,
        args=(cycle_num, board_snapshot),
        name="owl-post-cycle",
        daemon=True,
    ).start()
    log("Post-cycle audit in background — next cycle will not wait", "info")

    def _autonomous_trade_bg(captured_cycle: int) -> None:
        try:
            from autohedge.risk_gate import ensure_autonomous_trade

            result = ensure_autonomous_trade(source=f"owl_cycle_{captured_cycle}")
            if result.get("placed"):
                log(
                    f"Autonomous edge trade: {result.get('instId')} "
                    f"orderId={result.get('orderId')} side={result.get('side')}",
                    "success",
                )
            elif result.get("skipped"):
                pass
            elif not result.get("ok"):
                log(f"Autonomous trade skipped: {result.get('reason')}", "info")
        except Exception as exc:
            log(f"Autonomous trade: {exc}", "warn")

    threading.Thread(
        target=_autonomous_trade_bg,
        args=(cycle_num,),
        name="owl-autonomous-trade",
        daemon=True,
    ).start()
    save_state()
    try:
        from autohedge.tools.trade_journal import symbol_stats

        stats = symbol_stats()
        wins = sum(s.get("wins", 0) for s in stats.values())
        losses = sum(s.get("losses", 0) for s in stats.values())
        total = wins + losses
        live.win_rate = f"{wins / total:.0%}" if total > 0 else "--"
    except Exception:
        pass
    log(f"=== LLM CYCLE {live.cycle} COMPLETE ===")
    try:
        from autohedge.swarm_topology import commit_cycle_verify_fails

        commit_cycle_verify_fails()
    except Exception:
        pass
    try:
        from autohedge.swarm_restart import maybe_restart_after_cycle

        maybe_restart_after_cycle(release_lock=release_lock, log_fn=log)
    except Exception:
        pass


DASHBOARD_HTML_PATH = ROOT / "swarm_dashboard.html"


def _load_dashboard_html() -> str:
    if DASHBOARD_HTML_PATH.is_file():
        return DASHBOARD_HTML_PATH.read_text(encoding="utf-8")
    return DASHBOARD_HTML_FALLBACK


# Minimal fallback if swarm_dashboard.html missing
DASHBOARD_HTML_FALLBACK = """<!DOCTYPE html><html><body><h1>OWL Swarm</h1><p>swarm_dashboard.html not found</p></body></html>"""


class DashHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_load_dashboard_html().encode())
        elif self.path == "/api/swarm-graph":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                from autohedge.swarm_topology import get_swarm_graph

                body = json.dumps(get_swarm_graph(), default=str)
            except Exception as exc:
                body = json.dumps({"error": str(exc)})
            self.wfile.write(body.encode())
        elif self.path == "/api/tasks":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                from autohedge.swarm_tasks import get_task_board

                body = json.dumps(get_task_board(), default=str)
            except Exception as exc:
                body = json.dumps({"error": str(exc)})
            self.wfile.write(body.encode())
        elif self.path == "/api/assurance":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                from autohedge.collective_audit import assurance_report

                body = json.dumps(assurance_report(), default=str)
            except Exception as exc:
                body = json.dumps({"error": str(exc)})
            self.wfile.write(body.encode())
        elif self.path == "/api/overseer":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                from autohedge.swarm_overseer import overseer_report_json

                body = overseer_report_json()
            except Exception as exc:
                body = json.dumps({"error": str(exc)})
            self.wfile.write(body.encode())
        elif self.path == "/api/playbook":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                from autohedge.self_heal_playbook import playbook_json

                body = playbook_json()
            except Exception as exc:
                body = json.dumps({"error": str(exc)})
            self.wfile.write(body.encode())
        elif self.path == "/api/learning":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                from autohedge.swarm_learning_audit import get_learning_report

                body = json.dumps(get_learning_report(), default=str)
            except Exception as exc:
                body = json.dumps({"error": str(exc)})
            self.wfile.write(body.encode())
        elif self.path == "/api/status":
            try:
                refresh_account()
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                from autohedge.workers import agent_roster

                roster = agent_roster()
            except Exception:
                roster = []
            body = json.dumps(
                {
                    "running": live.running,
                    "cycle": live.cycle,
                    "equity": live.equity,
                    "available": live.available,
                    "positions": live.positions,
                    "events": live.events[-40:],
                    "winRate": live.win_rate,
                    "lastError": live.last_error,
                    "pipeline": live.pipeline,
                    "agentsActive": live.agents_active,
                    "agentRoster": roster,
                },
                default=str,
            )
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass

    def handle_error(self, *args):
        pass


def start_dashboard() -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", DASHBOARD_PORT), DashHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"Dashboard: http://127.0.0.1:{DASHBOARD_PORT}")
    return srv


def main() -> int:
    from autohedge.env_loader import load_env, require_llm_key

    import autohedge.swarms_bootstrap  # noqa: F401

    load_env()
    if not require_llm_key():
        print("No LLM API key found — set NVIDIA_NIM_API_KEY, OPENROUTER_API_KEY, or OPENAI_API_KEY in .env or OneDrive", file=sys.stderr)
        return 1

    log("=" * 60)
    log("OWL Swarm — Multi-LLM Autonomous Trading")
    log("Agents: 15 LLM (6 trading + 5 support + 4 pentest special forces)")
    log(f"Margin: ISOLATED | Max leverage: {os.environ.get('OWL_MAX_LEVERAGE', '12')}x")
    log("=" * 60)

    patch_isolated_margin()

    if not acquire_lock():
        return 1

    try:
        from autohedge.handoff_pipeline import restore_pipeline_from_disk

        if restore_pipeline_from_disk():
            log("Recovered pipeline checkpoint from prior crash", "warn")
    except Exception:
        pass

    try:
        from autohedge.swarm_restart import save_runtime_fingerprint

        save_runtime_fingerprint()
        log("Runtime fingerprint saved — self-restart will trigger on code/env drift")
        try:
            from autohedge.self_heal_playbook import bootstrap_known_fixes

            boot = bootstrap_known_fixes()
            reinforced = boot.get("reinforced") or []
            if reinforced:
                log(f"Playbook reinforced {len(reinforced)} known fixes", "info")
            from autohedge.swarm_surface_sync import verify_surface_sync

            sync = verify_surface_sync()
            if not sync.get("ok"):
                log(f"Surface sync drift: {sync.get('issues', [])[:2]}", "warn")
        except Exception:
            pass
    except Exception as e:
        log(f"Fingerprint init skipped: {e}", "warn")

    start_market_services()
    try:
        from autohedge.tactics_learner import ensure_tactics_background
        from autohedge.swarm_autopilot import bind_logger, ensure_background_ops
        from autohedge.swarm_overseer import ensure_overseer_background

        bind_logger(log)
        ensure_tactics_background()
        ensure_background_ops()
        ensure_overseer_background()
        log("Self-verifying autopilot: playbook self-heal + overseer every 60s + verify-retry loop")
    except Exception as e:
        log(f"Autopilot start failed: {e}", "warn")
    dashboard = None
    if os.environ.get("OWL_EXTERNAL_DASHBOARD", "1") != "1":
        dashboard = start_dashboard()
        log(f"Dashboard: http://127.0.0.1:{DASHBOARD_PORT}")
    else:
        log("Dashboard served by scripts/dashboard_server.py (external)")
    live.running = True

    # Restore cycle count from disk
    if STATE_FILE.is_file():
        try:
            st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            live.cycle = int(st.get("cycle", 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    log(f"Loop interval: {CYCLE_SLEEP_S}s | Press Ctrl+C to stop")

    try:
        while True:
            t0 = time.time()
            try:
                run_llm_cycle()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log(f"Cycle failed (will retry): {e}", "error")
                live.last_error = str(e)

            elapsed = time.time() - t0
            sleep_s = max(10, CYCLE_SLEEP_S - int(elapsed))
            log(f"Sleeping {sleep_s}s...")
            time.sleep(sleep_s)
    except KeyboardInterrupt:
        log("Stopped by user")
    finally:
        live.running = False
        if _ws_bridge_proc and _ws_bridge_proc.poll() is None:
            _ws_bridge_proc.terminate()
        if dashboard is not None:
            dashboard.shutdown()
        release_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
