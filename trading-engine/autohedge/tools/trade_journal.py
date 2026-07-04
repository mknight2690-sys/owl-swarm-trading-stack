"""Persistent trade journal for loop learning across cycles."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from loguru import logger

JOURNAL_PATH = Path(__file__).resolve().parents[2] / "outputs" / "trade_journal.jsonl"
_STATS_CACHE: tuple[float, dict[str, dict[str, Any]]] | None = None


def _ensure_parent() -> None:
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)


def _invalidate_cache() -> None:
    global _STATS_CACHE
    _STATS_CACHE = None


def record_event(event: dict[str, Any]) -> None:
    _ensure_parent()
    row = {"ts": time.time(), **event}
    with JOURNAL_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    _invalidate_cache()
    logger.info("Trade journal: {}", row.get("type", "event"))
    try:
        from autohedge.self_heal_playbook import teach_from_journal_event

        teach_from_journal_event(row)
    except Exception:
        pass


def _read_last_n(n: int) -> list[str]:
    """Read last N lines without loading entire file."""
    if not JOURNAL_PATH.is_file():
        return []
    file_size = JOURNAL_PATH.stat().st_size
    if file_size == 0:
        return []
    chunk_size = min(file_size, n * 200)
    with JOURNAL_PATH.open("rb") as fh:
        fh.seek(file_size - chunk_size)
        tail = fh.read().decode("utf-8", errors="replace")
    lines = tail.strip().splitlines()
    return lines[-n:]


def load_events(limit: int = 500) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in _read_last_n(limit):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def symbol_stats() -> dict[str, dict[str, Any]]:
    """Aggregate per-symbol outcomes from journal (cached for 5s)."""
    global _STATS_CACHE
    now = time.time()
    if _STATS_CACHE is not None and (now - _STATS_CACHE[0]) < 5.0:
        return _STATS_CACHE[1]
    stats: dict[str, dict[str, Any]] = {}
    for ev in load_events(500):
        inst = ev.get("instId")
        if not inst:
            continue
        bucket = stats.setdefault(
            inst,
            {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "blocked": 0,
                "total_pnl": 0.0,
                "last_pnl": 0.0,
                "sum_win_pnl": 0.0,
                "sum_loss_pnl": 0.0,
                "best_win": 0.0,
            },
        )
        etype = ev.get("type")
        if etype == "order_placed":
            bucket["trades"] += 1
        elif etype == "order_blocked":
            bucket["blocked"] += 1
        elif etype == "position_closed":
            try:
                pnl = float(ev.get("realizedPnl") or 0)
            except (TypeError, ValueError):
                pnl = 0.0
            bucket["total_pnl"] += pnl
            bucket["last_pnl"] = pnl
            if pnl > 0:
                bucket["wins"] += 1
                bucket["sum_win_pnl"] += pnl
                bucket["best_win"] = max(bucket["best_win"], pnl)
            elif pnl < 0:
                bucket["losses"] += 1
                bucket["sum_loss_pnl"] += abs(pnl)
    for bucket in stats.values():
        w = int(bucket.get("wins") or 0)
        l = int(bucket.get("losses") or 0)
        bucket["avg_win"] = round(bucket["sum_win_pnl"] / w, 6) if w else 0.0
        bucket["avg_loss"] = round(bucket["sum_loss_pnl"] / l, 6) if l else 0.0
    _STATS_CACHE = (now, stats)
    return stats


def sync_position_closes() -> None:
    """Detect closed positions and log realized PnL to the journal."""
    from autohedge.tools.blofin_tools import get_blofin_client

    state_path = JOURNAL_PATH.parent / "position_snapshot.json"
    try:
        current_rows = get_blofin_client().get_positions()
    except Exception:
        return

    current: dict[str, dict] = {}
    for row in current_rows:
        inst = row.get("instId")
        if not inst:
            continue
        try:
            size = float(row.get("positions") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if abs(size) > 0:
            current[str(inst)] = row

    previous: dict[str, dict] = {}
    if state_path.is_file():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}

    for inst, prev in previous.items():
        if inst not in current:
            record_event(
                {
                    "type": "position_closed",
                    "instId": inst,
                    "realizedPnl": prev.get("realizedPnl"),
                    "lastUnrealizedPnl": prev.get("unrealizedPnl"),
                    "averagePrice": prev.get("averagePrice"),
                }
            )

    _ensure_parent()
    state_path.write_text(json.dumps(current, default=str), encoding="utf-8")


def insights_text(max_symbols: int = 8) -> str:
    stats = symbol_stats()
    events = load_events(20)
    if not stats and not events:
        return "No trade history yet — first cycles are exploration."

    lines = [
        "TRADE LEARNING (from past loop cycles):",
        "Strategy: big winners pay for small losers — favor symbols with large avg_win and total_pnl.",
    ]
    ranked = sorted(
        stats.items(),
        key=lambda kv: (kv[1]["total_pnl"], kv[1].get("best_win", 0), kv[1]["wins"] - kv[1]["losses"]),
        reverse=True,
    )
    if ranked:
        lines.append("Top symbols (total PnL, best win, avg win — prioritize these):")
        for inst, s in ranked[:max_symbols]:
            lines.append(
                f"  {inst}: pnl={s['total_pnl']:.4f} best_win={s.get('best_win', 0):.4f} "
                f"avg_win={s.get('avg_win', 0):.4f} W/L={s['wins']}/{s['losses']} blocked={s['blocked']}"
            )
        losers = sorted(
            ranked,
            key=lambda kv: (kv[1]["losses"] - kv[1]["wins"], kv[1]["total_pnl"]),
        )
        if losers and losers[0][1]["losses"] > 0:
            avoid = [i for i, s in losers[:5] if s["losses"] > s["wins"]]
            if avoid:
                lines.append(f"Prefer to avoid (poor track record): {', '.join(avoid)}")

    recent = [e for e in events if e.get("type") in {"order_placed", "order_blocked", "position_closed"}]
    if recent:
        lines.append("Recent events:")
        for ev in recent[-5:]:
            lines.append(
                f"  {ev.get('type')} {ev.get('instId', '')} "
                f"{ev.get('side', '')} pnl={ev.get('realizedPnl', '')}"
            )
    lines.append(
        "Use this history: chase setups like past BIG winners (high avg_win/total_pnl); "
        "skip repeat losers (3+ losses); never clip winners early; never add to blocked positions."
    )
    return "\n".join(lines)


def insights_json() -> str:
    return json.dumps(
        {
            "insights": insights_text(),
            "symbol_stats": symbol_stats(),
            "recent": load_events(15),
        },
        default=str,
    )
