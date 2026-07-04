"""Technical analysis and opportunity ranking for Blofin perps."""

from __future__ import annotations

import math
import os
from typing import Any


def resolve_rank_top_n(override: int | None = None) -> int:
    """
    How many symbols to return from rank_from_tickers.
    0 = full universe (every tradable USDT perp with 24h volume in the feed).
    """
    if override is not None:
        return max(0, int(override))
    if os.environ.get("OWL_UNIVERSE_SCAN_ALL", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return 0
    for key in ("OWL_RANK_TOP_N", "OWL_PRERANK_TOP_N"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return max(0, int(raw))
    return 0

def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_candles(raw: list[list[Any]]) -> list[dict[str, float]]:
    """Blofin candle: [ts, open, high, low, close, vol, volCcy, ...]."""
    out: list[dict[str, float]] = []
    for row in raw:
        if not row or len(row) < 5:
            continue
        out.append(
            {
                "ts": _f(row[0]),
                "open": _f(row[1]),
                "high": _f(row[2]),
                "low": _f(row[3]),
                "close": _f(row[4]),
                "volume": _f(row[5]) if len(row) > 5 else 0.0,
            }
        )
    return list(reversed(out))


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period or period < 1:
        return None
    k = 2 / (period + 1)
    val = sum(values[:period]) / period
    for price in values[period:]:
        val = price * k + val * (1 - k)
    return val


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr(candles: list[dict[str, float]], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def bollinger(closes: list[float], period: int = 20, mult: float = 2.0) -> dict[str, float] | None:
    if len(closes) < period:
        return None
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    std = math.sqrt(variance)
    return {"middle": mid, "upper": mid + mult * std, "lower": mid - mult * std}


def ticker_change_pct(row: dict[str, Any]) -> float | None:
    last = _f(row.get("last"))
    open24 = _f(row.get("open24h"))
    if open24 <= 0:
        return None
    return (last - open24) / open24 * 100.0


def funding_bias(funding_rate: float) -> dict[str, Any]:
    """Crowding signal: high positive funding = crowded longs (bearish contrarian)."""
    if funding_rate > 0.0003:
        bias = "crowded_long"
        sentiment = 0.35
        note = "High positive funding — longs pay shorts; fade risk on longs."
    elif funding_rate > 0.0001:
        bias = "mild_long_crowding"
        sentiment = 0.45
        note = "Mild long crowding."
    elif funding_rate < -0.0003:
        bias = "crowded_short"
        sentiment = 0.65
        note = "High negative funding — shorts pay longs; squeeze risk on shorts."
    elif funding_rate < -0.0001:
        bias = "mild_short_crowding"
        sentiment = 0.55
        note = "Mild short crowding."
    else:
        bias = "neutral"
        sentiment = 0.5
        note = "Funding near neutral."
    return {
        "funding_rate": funding_rate,
        "bias": bias,
        "sentiment_score": round(sentiment, 3),
        "note": note,
    }


def order_book_imbalance(book: dict[str, Any]) -> dict[str, float]:
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    bid_vol = sum(_f(b[1]) for b in bids[:10] if len(b) > 1)
    ask_vol = sum(_f(a[1]) for a in asks[:10] if len(a) > 1)
    total = bid_vol + ask_vol
    if total <= 0:
        return {"bid_pct": 0.5, "ask_pct": 0.5, "imbalance": 0.0}
    bid_pct = bid_vol / total
    return {
        "bid_pct": round(bid_pct, 4),
        "ask_pct": round(1 - bid_pct, 4),
        "imbalance": round(bid_pct - 0.5, 4),
    }


def technical_analysis(
    candles_raw: list[list[Any]],
    *,
    funding_rate: float | None = None,
) -> dict[str, Any]:
    candles = parse_candles(candles_raw)
    closes = [c["close"] for c in candles]
    if len(closes) < 20:
        return {"error": "insufficient_candles", "count": len(closes)}

    last = closes[-1]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50) if len(closes) >= 50 else None
    rsi14 = rsi(closes, 14)
    atr14 = atr(candles, 14)
    bb = bollinger(closes, 20)

    trend = 0.5
    if ema9 is not None and ema21 is not None:
        if ema9 > ema21 and last > ema21:
            trend = 0.75
        elif ema9 < ema21 and last < ema21:
            trend = 0.25
        elif ema9 > ema21:
            trend = 0.6
        elif ema9 < ema21:
            trend = 0.4

    momentum = 0.5
    if rsi14 is not None:
        if rsi14 > 70:
            momentum = 0.3
        elif rsi14 > 55:
            momentum = 0.65
        elif rsi14 < 30:
            momentum = 0.7
        elif rsi14 < 45:
            momentum = 0.35
        else:
            momentum = 0.5

    vol_pct = (atr14 / last * 100) if atr14 and last > 0 else 0.0
    support = min(c["low"] for c in candles[-20:])
    resistance = max(c["high"] for c in candles[-20:])
    pivot = (support + resistance + last) / 3

    long_score = trend * 0.4 + momentum * 0.35
    if funding_rate is not None:
        fb = funding_bias(funding_rate)
        long_score = long_score * 0.85 + fb["sentiment_score"] * 0.15

    return {
        "last": last,
        "ema9": ema9,
        "ema21": ema21,
        "ema50": ema50,
        "rsi14": round(rsi14, 2) if rsi14 is not None else None,
        "atr14": round(atr14, 6) if atr14 is not None else None,
        "volatility_pct": round(vol_pct, 3),
        "bollinger": bb,
        "trend_strength": round(trend, 3),
        "momentum_score": round(momentum, 3),
        "technical_score": round(long_score, 3),
        "short_score": round(1 - long_score, 3),
        "key_levels": {
            "support": round(support, 8),
            "resistance": round(resistance, 8),
            "pivot": round(pivot, 8),
        },
        "suggested_bias": "long" if long_score >= 0.55 else "short" if long_score <= 0.45 else "neutral",
    }


def rank_from_tickers(
    tickers: list[dict[str, Any]],
    *,
    blocked: set[str] | None = None,
    journal_stats: dict[str, dict[str, Any]] | None = None,
    top_n: int = 15,
) -> list[dict[str, Any]]:
    """Fast universe rank using 24h momentum + volume (no per-symbol candle calls)."""
    blocked = blocked or set()
    journal_stats = journal_stats or {}
    ranked: list[dict[str, Any]] = []

    for row in tickers:
        inst = str(row.get("instId") or "")
        if not inst or inst in blocked or not inst.endswith("-USDT"):
            continue
        chg = ticker_change_pct(row)
        if chg is None:
            continue
        vol = _f(row.get("volCurrency24h"))
        if vol <= 0:
            continue

        momentum_score = max(0.0, min(1.0, 0.5 + chg / 20.0))
        volume_score = max(0.0, min(1.0, math.log10(vol + 1) / 8.0))
        journal = journal_stats.get(inst, {})
        wins = int(journal.get("wins") or 0)
        losses = int(journal.get("losses") or 0)
        journal_score = 0.5
        if wins + losses > 0:
            journal_score = wins / (wins + losses)
        elif int(journal.get("blocked") or 0) > 2:
            journal_score = 0.2

        long_score = momentum_score * 0.45 + volume_score * 0.35 + journal_score * 0.2
        short_score = (1 - momentum_score) * 0.45 + volume_score * 0.35 + (1 - journal_score) * 0.2

        ranked.append(
            {
                "instId": inst,
                "last": row.get("last"),
                "chg_pct_24h": round(chg, 3),
                "vol_currency_24h": vol,
                "long_score": round(long_score, 3),
                "short_score": round(short_score, 3),
                "journal_wins": wins,
                "journal_losses": losses,
                "suggested_side": "long" if long_score >= short_score else "short",
            }
        )

    ranked.sort(key=lambda r: max(r["long_score"], r["short_score"]), reverse=True)
    if top_n and top_n > 0:
        return ranked[:top_n]
    return ranked


def ticker_proxy_analysis(
    ticker_row: dict[str, Any],
    *,
    funding_rate: float | None = None,
) -> dict[str, Any]:
    """
    Degraded technical view from 24h ticker when candle REST is WAF-blocked.
    Conservative: neutral bias when 24h move is flat.
    """
    last = _f(ticker_row.get("last"))
    if last <= 0:
        return {"error": "no_price", "source": "ticker_proxy_waf_fallback"}
    chg = ticker_change_pct(ticker_row) or 0.0
    momentum = max(0.0, min(1.0, 0.5 + chg / 20.0))
    if chg > 1.5:
        trend = 0.65
    elif chg > 0.5:
        trend = 0.58
    elif chg < -1.5:
        trend = 0.35
    elif chg < -0.5:
        trend = 0.42
    else:
        trend = 0.5
    long_score = trend * 0.5 + momentum * 0.5
    if funding_rate is not None:
        fb = funding_bias(funding_rate)
        long_score = long_score * 0.85 + fb["sentiment_score"] * 0.15
    short_score = 1.0 - long_score
    band = max(0.01, abs(chg) / 100.0 * 2.0)
    return {
        "last": last,
        "source": "ticker_proxy_waf_fallback",
        "technical_score": round(long_score, 3),
        "short_score": round(short_score, 3),
        "trend_strength": round(trend, 3),
        "momentum_score": round(momentum, 3),
        "volatility_pct": round(min(8.0, abs(chg) / 2.0), 3),
        "suggested_bias": (
            "long" if long_score >= 0.55 else "short" if long_score <= 0.45 else "neutral"
        ),
        "key_levels": {
            "support": round(last * (1 - band), 8),
            "resistance": round(last * (1 + band), 8),
            "pivot": round(last, 8),
        },
        "warning": "Candle data unavailable (WAF); 24h ticker proxy only.",
    }


def compute_position_size(
    *,
    equity_usdt: float,
    risk_pct: float,
    entry: float,
    stop: float,
    min_size: float,
    lot_size: float,
    contract_value: float = 1.0,
    leverage: float = 50.0,
) -> dict[str, Any]:
    """Kelly-lite sizing: risk fixed % of equity to stop distance."""
    if equity_usdt <= 0 or entry <= 0 or min_size <= 0:
        return {"size": str(min_size), "reason": "fallback_minimum"}
    risk_amount = equity_usdt * max(0.005, min(risk_pct, 0.05))
    stop_dist = abs(entry - stop)
    if stop_dist <= 0:
        return {"size": str(min_size), "reason": "zero_stop_distance"}

    raw_size = risk_amount / stop_dist
    if lot_size > 0:
        raw_size = math.floor(raw_size / lot_size) * lot_size
    size = max(min_size, raw_size)
    notional = size * contract_value * entry
    margin_at_50x = notional / leverage
    return {
        "size": str(size),
        "risk_usdt": round(risk_amount, 4),
        "notional_usdt": round(notional, 2),
        "margin_at_50x_usdt": round(margin_at_50x, 6),
        "equity_usdt": round(equity_usdt, 4),
        "risk_pct": risk_pct,
        "reason": "risk_based",
    }
