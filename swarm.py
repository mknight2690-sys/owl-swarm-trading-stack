#!/usr/bin/env python3
"""
OWL Swarm - Autonomous Self-Learning Trading System
No hardcoded AI variables. The swarm researches, learns, adapts, and evolves.
Uses real internet data, multi-agent collaboration, and experience-based learning.
"""

import json
import os
import sys
import io
import time
import threading
import random
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.request
import urllib.parse

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add blofin-auto-trader to path
AUTO_TRADER_DIR = Path(r"C:\Users\mknig\blofin-auto-trader")
sys.path.insert(0, str(AUTO_TRADER_DIR))

from autohedge.tools.blofin_client import BlofinClient  # noqa: E402
from autohedge.blofin_credentials import load_blofin_credentials  # noqa: E402

# ===============================================================
# CONFIG - Only operational params, no AI variables
# ===============================================================
CYCLE_INTERVAL_S = int(os.getenv("CYCLE_INTERVAL_S", "120"))
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "7878"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "outputs"))
JOURNAL_FILE = OUTPUT_DIR / "journal.jsonl"
EXPERIENCE_FILE = OUTPUT_DIR / "experience.json"
STRATEGY_FILE = OUTPUT_DIR / "strategies.json"

# ===============================================================
# STATE
# ===============================================================
class SwarmState:
    def __init__(self):
        self.cycle_count = 0
        self.total_trades = 0
        self.running = False
        self.last_equity = 0.0
        self.last_available = 0.0
        self.last_error = ""
        self.last_cycle_at = 0
        self.agents_active = 0
        self.position_open_times = {}
        self.recent_events = []
        self.open_positions = []
        self.trade_history = []
        self.strategies = []  # Learned strategies
        self.experience = []  # What worked and what didn't

state = SwarmState()
client: BlofinClient = None

# ===============================================================
# LOGGING
# ===============================================================
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def log(msg, level="info"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {level.upper()} {msg}"
    print(line, flush=True)
    state.recent_events.append({"type": "log", "message": msg, "level": level, "ts": int(time.time() * 1000)})
    if len(state.recent_events) > 200:
        state.recent_events = state.recent_events[-100:]

def save_journal(event):
    try:
        with open(JOURNAL_FILE, "a") as f:
            f.write(json.dumps({"ts": int(time.time()), **event}) + "\n")
    except: pass

def save_experience(data):
    try:
        with open(EXPERIENCE_FILE, "a") as f:
            f.write(json.dumps({"ts": int(time.time()), **data}) + "\n")
    except: pass

# ===============================================================
# BLOFIN API WRAPPERS
# ===============================================================
def get_balance():
    return client.get_balances()

def get_positions(inst_id=None):
    return client.get_positions(inst_id)

def get_tickers(inst_id=None):
    return client.get_tickers(inst_id)

def get_instruments(inst_type="SWAP"):
    return client.get_instruments(inst_type)

def get_funding_rate(inst_id):
    return client.get_funding_rate(inst_id)

def get_candles(inst_id, bar="1m", limit=50):
    return client.get_candles(inst_id, bar=bar, limit=str(limit))

def set_leverage(inst_id, leverage, margin_mode="isolated"):
    return client.set_leverage(inst_id, int(leverage), margin_mode=margin_mode)

def place_order(inst_id, side, size, tp_trigger_price="", sl_trigger_price="", margin_mode="isolated"):
    return client.place_order(
        inst_id=inst_id, side=side, order_type="market",
        size=str(size), tp_trigger_price=tp_trigger_price,
        sl_trigger_price=sl_trigger_price, margin_mode=margin_mode,
    )

def place_tpsl(inst_id, side, size="-1", tp_trigger_price="", sl_trigger_price=""):
    return client.place_tpsl(
        inst_id=inst_id, side=side, size=str(size),
        tp_trigger_price=tp_trigger_price, sl_trigger_price=sl_trigger_price,
    )

def close_position(inst_id):
    return client.close_position(inst_id, margin_mode="isolated")

def parse_balance(balance):
    details = balance.get("details", [{}])
    equity = float(balance.get("totalEquity", 0) or (details[0].get("equityUsd", 0) if details else 0))
    available = float(balance.get("availableEquity", 0) or ((details[0].get("availableEquity", 0) or details[0].get("available", 0)) if details else 0))
    return equity, available

# ===============================================================
# INTERNET RESEARCH - Fetch real market intelligence
# ===============================================================
def fetch_json(url, timeout=10):
    """Fetch JSON from any URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return None

def fetch_text(url, timeout=10):
    """Fetch text from any URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")[:5000]
    except:
        return None

# Cache internet research to avoid rate limits / hangs
_intel_cache = {}
_INTEL_TTL_S = 300

def _cache_get(key):
    entry = _intel_cache.get(key)
    if entry and time.time() - entry["ts"] < _INTEL_TTL_S:
        return entry["data"]
    return None

def _cache_set(key, data):
    _intel_cache[key] = {"ts": time.time(), "data": data}

def _safe_float(val, default=0.0):
    try:
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default

def research_market_sentiment():
    """Research overall market sentiment from multiple sources."""
    cached = _cache_get("market_sentiment")
    if cached:
        return cached

    intelligence = {"sources": [], "sentiment": "neutral", "fear_greed": 50, "trending": []}

    # Fear & Greed Index
    fg = fetch_json("https://api.alternative.me/fng/?limit=3")
    if fg and "data" in fg:
        try:
            latest = fg["data"][0]
            intelligence["fear_greed"] = int(latest["value"])
            intelligence["sentiment"] = "fear" if int(latest["value"]) < 30 else "greed" if int(latest["value"]) > 70 else "neutral"
            intelligence["sources"].append(f"Fear&Greed: {latest['value']} ({latest['value_classification']})")
        except: pass

    # CoinGecko global market data
    cg = fetch_json("https://api.coingecko.com/api/v3/global")
    if cg and "data" in cg:
        d = cg["data"]
        intelligence["btc_dominance"] = d.get("market_cap_percentage", {}).get("btc", 0)
        intelligence["total_market_cap"] = d.get("total_market_cap", {}).get("usd", 0)
        intelligence["market_cap_change_24h"] = d.get("market_cap_change_percentage_24h_usd", 0)
        intelligence["sources"].append(f"BTC Dom: {intelligence['btc_dominance']:.1f}% | 24h: {intelligence['market_cap_change_24h']:.2f}%")

    # Trending coins from CoinGecko
    trending = fetch_json("https://api.coingecko.com/api/v3/search/trending")
    if trending and "coins" in trending:
        trend_names = [c["item"]["name"] for c in trending["coins"][:5]]
        intelligence["trending"] = trend_names
        intelligence["sources"].append(f"Trending: {', '.join(trend_names)}")

    _cache_set("market_sentiment", intelligence)
    return intelligence

def _ticker_change_pct(ticker):
    """Extract 24h change from Blofin ticker fields."""
    for key in ticker.keys():
        kl = key.lower()
        if "change" in kl or "chg" in kl:
            try:
                return float(ticker.get(key, 0) or 0)
            except (TypeError, ValueError):
                pass
    return 0.0

def analyze_candles(inst_id):
    """Local momentum from Blofin candles - no external API."""
    intel = {"score_adjustments": [], "change_24h": 0, "trend": "flat"}
    try:
        candles = get_candles(inst_id, bar="15m", limit=20)
        if not candles or len(candles) < 5:
            return intel
        # Blofin returns newest first typically
        closes = []
        for c in candles:
            if isinstance(c, (list, tuple)) and len(c) > 4:
                closes.append(float(c[4]))
            elif isinstance(c, dict):
                closes.append(float(c.get("close", c.get("c", 0)) or 0))
        closes = [x for x in closes if x > 0]
        if len(closes) < 5:
            return intel
        recent = closes[0]
        older = closes[-1]
        if older > 0:
            chg = ((recent - older) / older) * 100
            intel["change_24h"] = chg
            if chg > 1.5:
                intel["trend"] = "up"
                intel["score_adjustments"].append(0.4)
            elif chg < -1.5:
                intel["trend"] = "down"
                intel["score_adjustments"].append(0.4)
    except Exception:
        pass
    return intel

def research_coin_intel(inst_id, ticker=None):
    """Deep research on a single coin - only call for top candidates."""
    cache_key = f"coin:{inst_id}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    intelligence = {"inst_id": inst_id, "score_adjustments": [], "bullish_signals": [], "bearish_signals": [], "change_24h": 0}

    if ticker:
        chg = _ticker_change_pct(ticker)
        intelligence["change_24h"] = chg
        if chg > 3:
            intelligence["bullish_signals"].append(f"Blofin 24h: +{chg:.1f}%")
            intelligence["score_adjustments"].append(0.3)
        elif chg < -3:
            intelligence["bearish_signals"].append(f"Blofin 24h: {chg:.1f}%")
            intelligence["score_adjustments"].append(0.3)

    candle_intel = analyze_candles(inst_id)
    intelligence["change_24h"] = _safe_float(candle_intel.get("change_24h"), intelligence["change_24h"])
    intelligence["score_adjustments"].extend(candle_intel.get("score_adjustments", []))

    # Optional CoinGecko (best-effort, short timeout)
    coin_symbol = inst_id.split("-")[0].lower()
    cg_data = fetch_json(
        f"https://api.coingecko.com/api/v3/coins/{coin_symbol}?localization=false&tickers=false&community_data=false&developer_data=false",
        timeout=4,
    )
    if cg_data:
        # Market cap rank
        rank = cg_data.get("market_cap_rank")
        if rank and rank < 50:
            intelligence["bullish_signals"].append(f"Top {rank} coin by market cap")
            intelligence["score_adjustments"].append(0.5)
        elif rank and rank > 200:
            intelligence["bearish_signals"].append(f"Low rank #{rank} - speculative")
            intelligence["score_adjustments"].append(-0.3)

        # Price change data
        market = cg_data.get("market_data", {})
        change_24h = _safe_float(market.get("price_change_percentage_24h"))
        change_7d = _safe_float(market.get("price_change_percentage_7d"))
        change_30d = _safe_float(market.get("price_change_percentage_30d"))
        if change_24h != 0:
            intelligence["change_24h"] = change_24h
        intelligence["change_7d"] = change_7d
        intelligence["change_30d"] = change_30d

        # Volume
        vol = market.get("total_volume", {}).get("usd", 0)
        intelligence["volume_usd"] = vol

        if change_24h > 5:
            intelligence["bullish_signals"].append(f"Strong 24h: +{change_24h:.1f}%")
            intelligence["score_adjustments"].append(0.3)
        elif change_24h < -5:
            intelligence["bearish_signals"].append(f"Weak 24h: {change_24h:.1f}%")
            intelligence["score_adjustments"].append(-0.3)

        if change_7d > 0 and change_24h > 0:
            intelligence["bullish_signals"].append("Positive momentum (7d + 24h)")
            intelligence["score_adjustments"].append(0.2)

    _cache_set(cache_key, intelligence)
    return intelligence

def _funding_rate_from_raw(fund_raw):
    if not fund_raw:
        return 0.0
    if isinstance(fund_raw, dict):
        rate = float(fund_raw.get("fundingRate", 0) or 0)
        if not rate and "data" in fund_raw:
            d = fund_raw["data"]
            if isinstance(d, list) and d:
                rate = float(d[0].get("fundingRate", 0) or 0)
            elif isinstance(d, dict):
                rate = float(d.get("fundingRate", 0) or 0)
        return rate
    if isinstance(fund_raw, list) and fund_raw:
        return float(fund_raw[0].get("fundingRate", 0) or 0)
    return 0.0

def research_onchain_signals():
    """Research on-chain and macro signals."""
    signals = []

    # Bitcoin dominance trend (via CoinGecko)
    btc_data = fetch_json("https://api.coingecko.com/api/v3/coins/bitcoin?localization=false&tickers=false&community_data=false&developer_data=false")
    if btc_data:
        btc_change = btc_data.get("market_data", {}).get("price_change_percentage_24h", 0)
        signals.append({"type": "btc_24h", "value": btc_change, "signal": "risk_on" if btc_change > 3 else "risk_off" if btc_change < -3 else "neutral"})

    return signals

# ===============================================================
# LEARNING SYSTEM - Experience-based strategy evolution
# ===============================================================
def load_experience():
    """Load past trading experience."""
    exp = []
    if EXPERIENCE_FILE.exists():
        try:
            with open(EXPERIENCE_FILE) as f:
                for line in f:
                    if line.strip():
                        exp.append(json.loads(line))
        except: pass
    return exp

def analyze_experience():
    """Analyze past trades to learn what works."""
    exp = load_experience()
    if len(exp) < 3:
        return {"confidence": 0, "patterns": [], "recommendation": "Need more data. Explore freely."}

    wins = [e for e in exp if e.get("pnl", 0) > 0]
    losses = [e for e in exp if e.get("pnl", 0) < 0]
    total = len(exp)
    win_rate = len(wins) / total if total > 0 else 0

    patterns = []

    # Learn from winning trades
    if wins:
        avg_win = sum(e.get("pnl", 0) for e in wins) / len(wins)
        avg_win_leverage = sum(e.get("leverage", 10) for e in wins) / len(wins)
        patterns.append(f"Win rate: {win_rate:.0%} ({len(wins)}W/{len(losses)}L)")
        patterns.append(f"Avg win: ${avg_win:.4f} at {avg_win_leverage:.1f}x leverage")

        # What coins won?
        win_coins = {}
        for e in wins:
            c = e.get("instId", "?")
            win_coins[c] = win_coins.get(c, 0) + 1
        best_coins = sorted(win_coins.items(), key=lambda x: x[1], reverse=True)[:3]
        if best_coins:
            patterns.append(f"Best coins: {', '.join(f'{c}({n})' for c, n in best_coins)}")

    # Learn from losing trades
    if losses:
        avg_loss = sum(e.get("pnl", 0) for e in losses) / len(losses)
        patterns.append(f"Avg loss: ${avg_loss:.4f}")

        # What caused losses?
        stop_outs = [e for e in losses if "stop" in e.get("reason", "").lower()]
        if stop_outs:
            patterns.append(f"Stop-outs: {len(stop_outs)} - consider wider stops or lower leverage")

    # Generate recommendation
    recommendation = ""
    if win_rate < 0.4 and total > 5:
        recommendation = "Low win rate. Reduce leverage, widen stops, or trade less frequently."
    elif win_rate > 0.6 and total > 5:
        recommendation = "Good win rate. Can slightly increase position size."
    elif total < 5:
        recommendation = "Learning phase. Keep exploring with small positions."
    else:
        recommendation = "Balanced approach. Follow learned patterns."

    return {
        "confidence": min(1.0, total / 20),
        "patterns": patterns,
        "recommendation": recommendation,
        "win_rate": win_rate,
        "total_trades": total,
    }

def record_trade_experience(inst_id, side, size, entry, exit_price, pnl, leverage, reason):
    """Record what happened with a trade for future learning."""
    save_experience({
        "instId": inst_id,
        "side": side,
        "size": size,
        "entry": entry,
        "exit": exit_price,
        "pnl": pnl,
        "leverage": leverage,
        "reason": reason,
    })

# ===============================================================
# MULTI-AGENT SWARM - Autonomous agents that collaborate
# ===============================================================
class Agent:
    """Base agent that can research, analyze, and make decisions."""
    def __init__(self, name):
        self.name = name

    def think(self, context):
        """Agent thinks and returns a decision. Override in subclasses."""
        return {}

class ResearcherAgent(Agent):
    """Researches market conditions and finds opportunities."""
    def __init__(self):
        super().__init__("Researcher")

    def think(self, context):
        tickers = context.get("tickers", [])
        equity = context.get("equity", 0)
        market = context.get("market", {})
        blocked = context.get("blocked", set())
        trending = {n.lower() for n in market.get("trending", [])}

        try:
            instruments = get_instruments()
            inst_map = {i.get("instId"): i for i in instruments if i.get("instId")}
        except Exception:
            inst_map = {}

        # PASS 1: cheap local scoring (no per-coin internet calls)
        prelim = []
        for t in tickers:
            inst_id = t.get("instId", "")
            if not inst_id.endswith("-USDT") or inst_id in blocked:
                continue
            last = float(t.get("last", 0) or 0)
            vol = float(t.get("volCurrency24h", 0) or 0)
            if last <= 0 or vol <= 0:
                continue

            inst = inst_map.get(inst_id, {})
            min_size = float(inst.get("minSize", "1") or "1")
            cv = float(inst.get("contractValue", "1") or "1")
            notional = min_size * cv * last
            if equity > 0 and notional > equity * 0.5:
                continue

            score = 0
            reasons = []
            if vol > 1_000_000:
                score += 3
                reasons.append("high_vol")
            elif vol > 100_000:
                score += 2
                reasons.append("med_vol")
            elif vol > 10_000:
                score += 1
                reasons.append("low_vol")

            if notional < 0.01:
                score += 3
                reasons.append("cheap")
            elif notional < 0.1:
                score += 2
                reasons.append("affordable")
            elif notional < 0.5:
                score += 1
                reasons.append("ok")

            sym = inst_id.split("-")[0].lower()
            if sym in trending or any(sym in tname.lower() for tname in trending):
                score += 1.5
                reasons.append("trending")

            chg = _ticker_change_pct(t)
            if market.get("sentiment") == "fear" and chg < -2:
                score += 0.5
                reasons.append("fear_bounce")
            elif market.get("sentiment") == "greed" and chg > 2:
                score += 0.5
                reasons.append("greed_momo")

            prelim.append({
                "instId": inst_id,
                "last": str(last),
                "score": score,
                "reasons": reasons,
                "vol": vol,
                "notional": notional,
                "ticker": t,
                "chg": chg,
            })

        prelim.sort(key=lambda x: x["score"], reverse=True)
        shortlist = prelim[:12]
        log(f"Researcher: {len(prelim)} affordable | deep-research top {len(shortlist)}", "")

        # PASS 2: deep research only on shortlist
        candidates = []
        for item in shortlist:
            inst_id = item["instId"]
            coin_intel = research_coin_intel(inst_id, ticker=item["ticker"])
            score = item["score"] + sum(coin_intel.get("score_adjustments", []))

            side = "long" if _safe_float(coin_intel.get("change_24h", item["chg"])) >= 0 else "short"
            try:
                rate = _funding_rate_from_raw(get_funding_rate(inst_id))
                if side == "long" and rate > 0.0005:
                    score -= 2
                    item["reasons"].append("bad_funding_long")
                elif side == "short" and rate < -0.0005:
                    score -= 2
                    item["reasons"].append("bad_funding_short")
            except Exception:
                pass

            candidates.append({
                "instId": inst_id,
                "last": item["last"],
                "score": score,
                "reasons": item["reasons"],
                "vol": item["vol"],
                "notional": item["notional"],
                "suggestedSide": side,
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        if len(candidates) > 1 and random.random() < 0.25:
            candidates[0], candidates[1] = candidates[1], candidates[0]
        return {"candidates": candidates[:10]}

class RiskAgent(Agent):
    """Evaluates risk and decides position sizing, leverage, TP/SL."""
    def __init__(self):
        super().__init__("RiskManager")

    def think(self, context):
        equity = context.get("equity", 0)
        available = context.get("available", 0)
        experience = context.get("experience", {})

        # Learn from experience
        win_rate = experience.get("win_rate", 0)
        confidence = experience.get("confidence", 0)

        # Dynamic leverage based on equity and experience
        # Small accounts: lower leverage to survive
        if equity < 1:
            max_lev = 8
        elif equity < 5:
            max_lev = 10
        elif equity < 20:
            max_lev = 12
        else:
            max_lev = 15

        # If we have a good track record, can be slightly more aggressive
        if confidence > 0.5 and win_rate > 0.5:
            max_lev = min(max_lev + 2, 15)

        # Dynamic TP/SL based on experience
        if win_rate < 0.4 and confidence > 0.3:
            # Losing streak - wider stops, take profit faster
            tp_pct = 0.02
            sl_pct = 0.025
        elif win_rate > 0.6 and confidence > 0.3:
            # Winning - can hold longer for bigger gains
            tp_pct = 0.04
            sl_pct = 0.02
        else:
            # Default balanced
            tp_pct = 0.03
            sl_pct = 0.02

        # Position size: risk 2-5% of equity per trade
        risk_pct = 0.05 if equity < 2 else 0.02

        return {
            "max_leverage": max_lev,
            "tp_pct": tp_pct,
            "sl_pct": sl_pct,
            "risk_pct": risk_pct,
        }

class ExecutionAgent(Agent):
    """Decides when and how to execute trades."""
    def __init__(self):
        super().__init__("Executor")

    def think(self, context):
        positions = context.get("positions", [])
        equity = context.get("equity", 0)
        available = context.get("available", 0)

        # Position limits based on equity
        if equity < 2:
            max_positions = 1
        elif equity < 10:
            max_positions = 2
        else:
            max_positions = 3

        can_trade = len(positions) < max_positions and available > 0.2

        return {
            "can_trade": can_trade,
            "max_positions": max_positions,
        }

# ===============================================================
# MAIN TRADING CYCLE
# ===============================================================
def run_cycle():
    global state
    state.cycle_count += 1
    cycle_start = time.time()
    state.last_error = ""
    state.agents_active = 0

    log(f"=== CYCLE {state.cycle_count} START ===")

    try:
        # 1. Get fresh account state
        positions = get_positions() or []
        balance = get_balance()
        equity, available = parse_balance(balance)

        # 2. Auto-protect: close worst if equity dropped >15%
        if state.last_equity > 0 and equity < state.last_equity * 0.85 and positions:
            worst = min(positions, key=lambda p: float(p.get("unrealizedPnl", 0) or 0))
            pnl = float(worst.get("unrealizedPnl", 0) or 0)
            if pnl < 0:
                log(f"EQUITY DROP: {state.last_equity:.2f} -> {equity:.2f} - closing {worst.get('instId')}", "warn")
                close_position(worst.get("instId"))
                state.position_open_times.pop(worst.get("instId"), None)
                positions = get_positions() or []
                balance = get_balance()
                equity, available = parse_balance(balance)

        state.last_equity = equity
        state.last_available = available
        state.open_positions = positions
        log(f"Account: equity={equity:.4f} available={available:.4f} positions={len(positions)}")

        # 3. Close stale/losing positions
        closed = []
        for pos in positions:
            inst_id = pos.get("instId", "")
            sz = float(pos.get("positions", 0) or 0)
            if abs(sz) < 1e-12:
                continue

            pnl_ratio = float(pos.get("unrealizedPnlRatio", 0) or 0)
            pnl_pct = pnl_ratio * 100

            open_time = state.position_open_times.get(inst_id, time.time())
            age_min = (time.time() - open_time) / 60

            should_close = False
            reason = ""

            if pnl_pct > 1.0 and available < 0.3:
                should_close = True
                reason = f"profit take (+{pnl_pct:.1f}%)"
            elif age_min > 15 and pnl_pct < 0.5:
                should_close = True
                reason = f"stale ({age_min:.0f}min, pnl={pnl_pct:.1f}%)"
            elif pnl_pct < -3:
                should_close = True
                reason = f"stop loss ({pnl_pct:.1f}%)"

            if should_close:
                try:
                    close_position(inst_id)
                    log(f"Closed {inst_id}: {reason}", "success")
                    state.position_open_times.pop(inst_id, None)
                    closed.append(inst_id)
                    pnl_usd = float(pos.get("unrealizedPnl", 0) or 0)
                    lev = float(pos.get("leverage", 0) or 0)
                    save_journal({"type": "position_closed", "instId": inst_id, "reason": reason, "pnl_pct": pnl_pct, "pnl": pnl_usd})
                    record_trade_experience(inst_id, "close", abs(sz), float(pos.get("averagePrice", 0) or 0), float(pos.get("markPrice", 0) or 0), pnl_usd, lev, reason)
                except Exception as e:
                    log(f"Failed to close {inst_id}: {e}", "error")

        if closed:
            positions = get_positions() or []
            balance = get_balance()
            equity, available = parse_balance(balance)
            state.open_positions = positions

        # 4. Ensure TP/SL on all positions
        for pos in positions:
            inst_id = pos.get("instId", "")
            sz = float(pos.get("positions", 0) or 0)
            if abs(sz) < 1e-12:
                continue
            try:
                pending = client.get_pending_tpsl(inst_id)
                if len(pending) == 0:
                    mark = float(pos.get("markPrice", 0) or float(pos.get("averagePrice", 0)) or 0)
                    if mark <= 0:
                        continue
                    side = "sell" if sz > 0 else "buy"
                    pos_side = "buy" if sz > 0 else "sell"
                    tick_res = client.get_instrument(inst_id)
                    tick = float(tick_res.get("tickSize", 0.1) or 0.1) if tick_res else 0.1
                    # Use learned TP/SL or default
                    tp_pct = 0.03
                    sl_pct = 0.02
                    if pos_side == "buy":
                        tp = mark * (1 + tp_pct)
                        sl = mark * (1 - sl_pct)
                    else:
                        tp = mark * (1 - tp_pct)
                        sl = mark * (1 + sl_pct)
                    if tick > 0:
                        tp = round(round(tp / tick) * tick, 10)
                        sl = round(round(sl / tick) * tick, 10)
                    place_tpsl(inst_id, side, "-1", f"{tp:.6f}", f"{sl:.6f}")
                    log(f"TP/SL placed on {inst_id}", "success")
            except Exception as e:
                log(f"TP/SL failed for {inst_id}: {e}", "warn")

        # 5. Check if we can trade
        if available < 0.2:
            log(f"MARGIN LOCK: available=${available:.4f}", "warn")
            return int(time.time() - cycle_start)

        # 6. INTERNET RESEARCH
        log("Researching market conditions...", "")
        market_intel = research_market_sentiment()
        for src in market_intel.get("sources", []):
            log(f"  [Research] {src}", "")

        onchain = research_onchain_signals()
        for sig in onchain:
            log(f"  [OnChain] {sig['type']}: {sig['value']:.2f}% ({sig['signal']})", "")

        # 7. LEARNING - Analyze experience
        experience = analyze_experience()
        if experience["patterns"]:
            log(f"Learning: {experience['recommendation']}", "")
            for p in experience["patterns"]:
                log(f"  [Learn] {p}", "")

        # 8. MULTI-AGENT DECISION
        state.agents_active = 3
        tickers = get_tickers() or []

        blocked = {p.get("instId") for p in positions if p.get("instId")}

        context = {
            "tickers": tickers,
            "equity": equity,
            "available": available,
            "positions": positions,
            "experience": experience,
            "market": market_intel,
            "blocked": blocked,
        }

        # Agent 1: Researcher finds opportunities
        researcher = ResearcherAgent()
        research_result = researcher.think(context)
        candidates = research_result.get("candidates", [])

        # Agent 2: Risk Manager decides parameters
        risk_mgr = RiskAgent()
        risk_result = risk_mgr.think(context)

        # Agent 3: Executor decides if we should trade
        executor = ExecutionAgent()
        exec_result = executor.think(context)

        state.agents_active = 0

        log(f"Agents: Researcher found {len(candidates)} candidates | Risk: max_lev={risk_result['max_leverage']}x tp={risk_result['tp_pct']*100:.1f}% sl={risk_result['sl_pct']*100:.1f}% | Executor: can_trade={exec_result['can_trade']}", "")

        if not exec_result["can_trade"]:
            log("Executor says NO TRADE this cycle", "")
            return int(time.time() - cycle_start)

        if not candidates:
            log("No opportunities found", "warn")
            return int(time.time() - cycle_start)

        # 9. Pick best candidate (with some randomness for exploration)
        if len(candidates) > 1 and random.random() < 0.3:
            # 30% chance to try 2nd best (exploration)
            best = candidates[1]
            log(f"EXPLORING: trying #{2} pick", "")
        else:
            best = candidates[0]

        inst_id = best["instId"]
        side = best["suggestedSide"]
        entry_price = float(best["last"])

        log(f"BEST: {inst_id} {side} price={entry_price} score={best['score']:.1f} reasons={', '.join(best['reasons'])}")

        # 10. Get instrument info
        instrument = client.get_instrument(inst_id)
        min_size = float(instrument.get("minSize", 1)) if instrument else 1
        lot_size = float(instrument.get("lotSize", 0)) if instrument else 0
        contract_value = float(instrument.get("contractValue", 1) or 1) if instrument else 1
        tick_size = float(instrument.get("tickSize", 0.1)) if instrument else 0.1
        max_leverage_inst = float(instrument.get("maxLeverage", 50)) if instrument else 50

        # 11. Dynamic leverage from Risk Agent
        leverage = min(risk_result["max_leverage"], max_leverage_inst)
        log(f"LEVERAGE: {inst_id} max={max_leverage_inst} -> FINAL={leverage}x")

        # 12. Compute TP/SL and size from Risk Agent
        tp_pct = risk_result["tp_pct"]
        sl_pct = risk_result["sl_pct"]

        if side == "long":
            tp = entry_price * (1 + tp_pct)
            sl = entry_price * (1 - sl_pct)
        else:
            tp = entry_price * (1 - tp_pct)
            sl = entry_price * (1 + sl_pct)

        if tick_size > 0:
            tp = round(round(tp / tick_size) * tick_size, 10)
            sl = round(round(sl / tick_size) * tick_size, 10)

        stop_price = sl

        # NaN guard
        if not (entry_price > 0 and min_size > 0 and contract_value > 0):
            log(f"Skipping {inst_id}: invalid data", "error")
            return int(time.time() - cycle_start)

        # Max notional cap
        max_notional = equity * 1.5
        min_notional = min_size * contract_value * entry_price
        if min_notional > max_notional:
            log(f"Skipping {inst_id}: minSize too expensive (${min_notional:.2f} > ${max_notional:.2f})", "warn")
            return int(time.time() - cycle_start)

        # Size based on risk
        risk_amount = equity * risk_result["risk_pct"]
        stop_dist = abs(entry_price - stop_price)
        if stop_dist <= 0:
            position_size = min_size
        else:
            raw_size = risk_amount / stop_dist
            if lot_size > 0:
                raw_size = (raw_size // lot_size) * lot_size
            position_size = max(min_size, int(raw_size))

        notional = position_size * contract_value * entry_price
        margin_needed = (notional / leverage) * 1.5 + 0.05

        # Cap to available margin
        if available < margin_needed:
            max_margin = max(0, available - 0.05)
            max_notional = (max_margin / 1.5) * leverage
            max_contracts = int(max_notional / (contract_value * entry_price))
            if lot_size > 0:
                max_contracts = (max_contracts // int(lot_size)) * int(lot_size)
            if max_contracts >= min_size:
                position_size = max_contracts
                notional = position_size * contract_value * entry_price
                margin_needed = (notional / leverage) * 1.5 + 0.05
                log(f"Resized {inst_id}: {position_size} contracts (margin={margin_needed:.4f})", "warn")
            else:
                log(f"Skipping {inst_id}: can't afford minSize", "warn")
                return int(time.time() - cycle_start)

        # 13. Re-fetch fresh balance before execution
        fresh_balance = get_balance()
        fresh_equity, fresh_available = parse_balance(fresh_balance)
        if fresh_available < available:
            available = fresh_available

        if available < margin_needed:
            log(f"Insufficient margin: need {margin_needed:.4f} have {available:.4f}", "warn")
            return int(time.time() - cycle_start)

        # 14. EXECUTE
        log(f"EXECUTING: {inst_id} {side} size={position_size} entry={entry_price} SL={sl:.6f} TP={tp:.6f} lev={leverage}x", "success")
        save_journal({"type": "trade_attempt", "instId": inst_id, "side": side, "size": position_size, "entry": entry_price, "leverage": leverage})

        try:
            set_leverage(inst_id, leverage)
            order_result = place_order(
                inst_id, "buy" if side == "long" else "sell",
                str(position_size), f"{tp:.6f}", f"{sl:.6f}",
            )
            order_id = order_result.get("ordId", "unknown") if isinstance(order_result, dict) else "unknown"
            log(f"Order placed: {order_id}", "success")
            state.total_trades += 1
            state.position_open_times[inst_id] = time.time()

            # Confirm and refresh state
            new_pos = get_positions(inst_id)
            if new_pos:
                log(f"Position confirmed: {inst_id} size={new_pos[0].get('positions')} avgPrice={new_pos[0].get('averagePrice')}", "success")
                state.open_positions = get_positions() or []
                state.last_equity, state.last_available = parse_balance(get_balance())

            save_journal({"type": "order_filled", "instId": inst_id, "side": side, "orderId": order_id, "size": position_size})
            state.trade_history.append({"ts": int(time.time() * 1000), "instId": inst_id, "side": side, "size": position_size, "entry": entry_price, "reason": "opened"})

        except Exception as e:
            log(f"Execution failed for {inst_id}: {e}", "error")
            state.last_error = str(e)
            save_journal({"type": "order_failed", "instId": inst_id, "error": str(e)})

        elapsed = int(time.time() - cycle_start)
        log(f"=== CYCLE {state.cycle_count} COMPLETE ({elapsed}s) ===")
        return elapsed

    except Exception as e:
        log(f"CYCLE ERROR: {e}", "error")
        state.last_error = str(e)
        return int(time.time() - cycle_start)

# ===============================================================
# DASHBOARD SERVER
# ===============================================================
DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>OWL Swarm Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0f1117;color:#e1e4e8;min-height:100vh;padding:24px}
.header{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;flex-wrap:wrap;gap:12px}
.header h1{font-size:1.6em;font-weight:700}
.header h1 span{color:#ff6b35}
.badge{padding:6px 14px;border-radius:20px;font-size:0.85em;font-weight:600;text-transform:uppercase}
.badge.run{background:#1a3a2a;color:#3fb950;border:1px solid #3fb950}
.badge.stop{background:#3a1a1a;color:#f85149;border:1px solid #f85149}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px}
.card .label{color:#8b949e;font-size:0.7em;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.metric{font-size:1.6em;font-weight:700}
.positive{color:#3fb950}.negative{color:#f85149}.neutral{color:#8b949e}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #21262d;font-size:0.85em}
th{color:#8b949e;font-weight:600;font-size:0.7em;text-transform:uppercase}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:0.75em;font-weight:600}
.pill.long{background:#1a3a2a;color:#3fb950}
.pill.short{background:#3a1a1a;color:#f85149}
.log-box{max-height:250px;overflow-y:auto;background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:10px;font-family:Consolas,monospace;font-size:0.78em;line-height:1.5}
.l-line{white-space:pre-wrap;word-break:break-all}
.l-info{color:#58a6ff}.l-success{color:#3fb950}.l-warn{color:#d29922}.l-error{color:#f85149}
.wide{grid-column:1/-1}
.half{grid-column:span 2}
.subtitle{color:#8b949e;font-size:0.85em}
</style></head><body>
<div class="header">
<h1><span>OWL</span> Swarm</h1>
<div><span class="badge stop" id="badge">STOPPED</span> <span class="subtitle" id="lastUpdate">connecting...</span></div>
</div>
<div class="grid">
<div class="card"><div class="label">Equity</div><div class="metric neutral" id="equity">$0.00</div></div>
<div class="card"><div class="label">Available</div><div class="metric neutral" id="available">$0.00</div></div>
<div class="card"><div class="label">Positions</div><div class="metric neutral" id="posCount">0</div></div>
<div class="card"><div class="label">Trades</div><div class="metric neutral" id="trades">0</div></div>
<div class="card"><div class="label">Cycle</div><div class="metric neutral" id="cycle">0</div></div>
<div class="card"><div class="label">Win Rate</div><div class="metric neutral" id="winRate">--</div></div>
</div>
<div class="card wide">
<div class="label">Open Positions</div>
<table><thead><tr><th>Instrument</th><th>Side</th><th>Size</th><th>Entry</th><th>Mark</th><th>PnL</th><th>Leverage</th></tr></thead><tbody id="posTable"><tr><td colspan="7" style="text-align:center;color:#8b949e">No positions</td></tr></tbody></table>
</div>
<div class="card half">
<div class="label">Research & Learning</div>
<div class="log-box" id="intelBox"><div class="l-info l-line">Waiting for research...</div></div>
</div>
<div class="card half">
<div class="label">Event Log</div>
<div class="log-box" id="logBox"><div class="l-info l-line">Waiting for swarm...</div></div>
</div>
<script>
function fmt(n){return '$'+Number(n).toFixed(4)}
function ts(ms){return new Date(ms).toLocaleTimeString()}
function upd(){
  fetch('/api/status').then(r=>r.json()).then(s=>{
    document.getElementById('lastUpdate').textContent='Updated '+new Date().toLocaleTimeString();
    var badge=document.getElementById('badge');
    if(s.running){badge.className='badge run';badge.textContent='RUNNING'}
    else{badge.className='badge stop';badge.textContent='STOPPED'}
    document.getElementById('equity').textContent=fmt(s.equity);
    document.getElementById('available').textContent=fmt(s.available);
    document.getElementById('posCount').textContent=s.openPositions.length;
    document.getElementById('trades').textContent=s.totalTrades;
    document.getElementById('cycle').textContent=s.cycleCount;
    document.getElementById('winRate').textContent=s.winRate||'--';
    var pt=document.getElementById('posTable');
    if(!s.openPositions||s.openPositions.length===0){pt.innerHTML='<tr><td colspan="7" style="text-align:center;color:#8b949e">No positions</td></tr>'}
    else{pt.innerHTML='';s.openPositions.forEach(function(p){
      var pnl=parseFloat(p.unrealizedPnl||0);
      var side=parseFloat(p.positions||0)>0?'long':'short';
      pt.innerHTML+='<tr><td>'+p.instId+'</td><td><span class="pill '+side+'">'+side+'</span></td><td>'+p.positions+'</td><td>'+parseFloat(p.averagePrice||0).toFixed(6)+'</td><td>'+parseFloat(p.markPrice||0).toFixed(6)+'</td><td class="'+(pnl>=0?'positive':'negative')+'">'+pnl.toFixed(4)+'</td><td>'+(p.leverage||'?')+'x</td></tr>';
    })}
    var lb=document.getElementById('logBox');
    lb.innerHTML='';
    (s.recentEvents||[]).slice(-30).forEach(function(e){
      lb.innerHTML+='<div class="l-'+e.level+' l-line">['+e.level.toUpperCase()+'] '+e.message+'</div>';
    });
    lb.scrollTop=lb.scrollHeight;
    var ib=document.getElementById('intelBox');
    ib.innerHTML='';
    (s.intel||[]).slice(-15).forEach(function(e){
      ib.innerHTML+='<div class="l-info l-line">'+e+'</div>';
    });
    ib.scrollTop=ib.scrollHeight;
  }).catch(function(e){
    document.getElementById('lastUpdate').textContent='Error: '+e.message;
  });
}
setInterval(upd,500);upd();
</script></body></html>"""

class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
        elif self.path == "/api/status":
            try:
                bal = get_balance()
                eq, avail = parse_balance(bal)
                pos = get_positions() or []
                state.last_equity = eq
                state.last_available = avail
                state.open_positions = pos
            except: pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            exp = analyze_experience()
            resp = {
                "running": state.running,
                "cycleCount": state.cycle_count,
                "totalTrades": state.total_trades,
                "equity": state.last_equity,
                "available": state.last_available,
                "openPositions": state.open_positions,
                "recentEvents": state.recent_events[-30:],
                "tradeHistory": state.trade_history[-20:],
                "intel": [e.get("message", "") for e in state.recent_events if "[Research]" in e.get("message", "") or "[Learn]" in e.get("message", "")][-15:],
                "winRate": f"{exp.get('win_rate', 0):.0%}" if exp.get('total_trades', 0) > 0 else "--",
                "lastError": state.last_error,
            }
            self.wfile.write(json.dumps(resp).encode())
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, format, *args):
        pass
    def handle_error(self, request, client_address):
        pass

def start_dashboard():
    server = HTTPServer(("127.0.0.1", DASHBOARD_PORT), DashboardHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log(f"Dashboard running at http://127.0.0.1:{DASHBOARD_PORT}")
    return server

# ===============================================================
# MAIN
# ===============================================================
def main():
    global state, client

    log("=" * 60)
    log("OWL Swarm - Autonomous Self-Learning Trading System")
    log("No hardcoded AI. Real research. Real learning. Real adaptation.")
    log("=" * 60)

    creds = load_blofin_credentials()
    client = BlofinClient(creds)
    log("Blofin client initialized")

    # Load past experience
    exp = load_experience()
    log(f"Loaded {len(exp)} past trade experiences")

    server = start_dashboard()

    state.running = True
    log(f"Starting autonomous trading loop (interval: {CYCLE_INTERVAL_S}s)")

    try:
        while state.running:
            elapsed = run_cycle()
            sleep_time = max(5, CYCLE_INTERVAL_S - elapsed)
            log(f"Sleeping {sleep_time}s until next cycle...")
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        log("Shutting down...")
    except Exception as e:
        log(f"FATAL: {e}", "error")
    finally:
        state.running = False
        server.shutdown()

if __name__ == "__main__":
    main()
