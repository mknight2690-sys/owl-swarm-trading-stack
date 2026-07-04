"""Persistent trading tactics — internet research + journal learning + cross-check memory."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from loguru import logger

from autohedge.swarm_learning_audit import record_improvement, record_learned
from autohedge.tools.web_search import web_search

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
PLAYBOOK_PATH = OUTPUT_DIR / "tactics_playbook.json"
RESEARCH_INTERVAL_SEC = int(os.environ.get("OWL_TACTICS_RESEARCH_SEC", "1800"))
_lock = threading.Lock()
_bg_started = False

_DEFAULT_QUERIES = [
    "crypto perpetual futures momentum breakout asymmetric risk reward tactics",
    "funding rate carry cost perpetual futures when to avoid holding position",
    "small account altcoin futures explosive 24h movers position sizing tactics",
    "stop loss take profit ratio 5 to 1 momentum trading crypto futures",
]


def _load() -> dict[str, Any]:
    if not PLAYBOOK_PATH.is_file():
        return {
            "version": 1,
            "updated_at": 0.0,
            "tactics": [],
            "internet_research": [],
            "crosscheck_lessons": [],
            "cycle_lessons": [],
        }
    try:
        return json.loads(PLAYBOOK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "updated_at": 0.0, "tactics": [], "internet_research": []}


def _save(data: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = time.time()
    PLAYBOOK_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _add_tactic(
    data: dict[str, Any],
    *,
    title: str,
    body: str,
    source: str,
    confidence: float = 0.6,
) -> None:
    tactics: list[dict[str, Any]] = data.setdefault("tactics", [])
    key = title.strip().lower()[:80]
    for t in tactics:
        if str(t.get("title", "")).strip().lower()[:80] == key:
            t["body"] = body
            t["confidence"] = max(float(t.get("confidence") or 0), confidence)
            t["updated_at"] = time.time()
            t["use_count"] = int(t.get("use_count") or 0) + 1
            return
    tactics.append(
        {
            "id": f"tactic_{int(time.time())}_{len(tactics)}",
            "title": title,
            "body": body,
            "source": source,
            "confidence": confidence,
            "created_at": time.time(),
            "updated_at": time.time(),
            "use_count": 0,
        }
    )
    tactics.sort(key=lambda x: float(x.get("confidence") or 0), reverse=True)
    data["tactics"] = tactics[:40]


def research_tactics_online(query: str | None = None) -> dict[str, Any]:
    """Pull trading tactics from the internet (Exa or DuckDuckGo)."""
    with _lock:
        data = _load()
        idx = int(data.get("query_index") or 0) % len(_DEFAULT_QUERIES)
        q = query or _DEFAULT_QUERIES[idx]
        data["query_index"] = idx + 1

    raw = web_search(q)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"query": q, "results": [], "error": "parse_failed"}

    summaries: list[str] = []
    for row in parsed.get("results") or []:
        title = str(row.get("title") or "")
        text = str(row.get("text") or "")
        if title or text:
            summaries.append(f"{title}: {text[:400]}".strip(": "))

    entry = {
        "ts": time.time(),
        "query": q,
        "engine": parsed.get("engine"),
        "summaries": summaries[:5],
    }

    with _lock:
        data = _load()
        research: list[dict[str, Any]] = data.setdefault("internet_research", [])
        research.append(entry)
        data["internet_research"] = research[-30:]
        data["last_research_at"] = time.time()
        if summaries:
            _add_tactic(
                data,
                title=f"Web: {q[:60]}",
                body=" | ".join(summaries[:3])[:2000],
                source="internet",
                confidence=0.55,
            )
        _save(data)

    body_text = " | ".join(summaries[:3])[:2000] if summaries else "(no results)"
    record_learned(
        title=f"Web research: {q[:70]}",
        detail=body_text,
        source=f"internet/{parsed.get('engine')}",
        proof={"query": q, "engine": parsed.get("engine"), "hit_count": len(summaries), "summaries": summaries[:3]},
    )

    logger.info("Tactics internet research: {} hits via {}", q[:50], parsed.get("engine"))
    return entry


def record_crosscheck_lesson(result: dict[str, Any]) -> None:
    from autohedge.swarm_learning_audit import record_learned

    if result.get("ok"):
        return
    with _lock:
        data = _load()
        lessons: list[dict[str, Any]] = data.setdefault("crosscheck_lessons", [])
        lessons.append(
            {
                "ts": time.time(),
                "agent": result.get("agent"),
                "instId": result.get("instId"),
                "issues": result.get("issues"),
                "fixes": result.get("fixes"),
            }
        )
        data["crosscheck_lessons"] = lessons[-50:]
        for issue in result.get("issues") or []:
            _add_tactic(
                data,
                title=f"Cross-check: {result.get('agent')}",
                body=str(issue),
                source="crosscheck",
                confidence=0.7,
            )
        _save(data)

    issues = result.get("issues") or []
    if issues:
        record_learned(
            title=f"Peer cross-check failed: {result.get('agent')}",
            detail="; ".join(str(i) for i in issues),
            source="crosscheck",
            proof={"agent": result.get("agent"), "instId": result.get("instId"), "fixes": result.get("fixes")},
        )


def learn_from_journal() -> list[str]:
    """Derive tactics from closed trades in the journal."""
    from autohedge.tools.trade_journal import load_events, symbol_stats

    notes: list[str] = []
    stats = symbol_stats()
    for inst, s in sorted(stats.items(), key=lambda kv: kv[1]["total_pnl"], reverse=True)[:5]:
        pnl = float(s.get("total_pnl") or 0)
        if pnl > 0.01:
            notes.append(
                f"{inst}: total_pnl={pnl:.4f} avg_win={s.get('avg_win', 0):.4f} "
                f"— favor similar explosive setups"
            )
        elif int(s.get("losses") or 0) >= 3:
            notes.append(f"{inst}: repeat loser ({s['losses']}L) — avoid until pattern changes")

    recent = [e for e in load_events(40) if e.get("type") == "position_closed"]
    for ev in recent[-5:]:
        try:
            pnl = float(ev.get("realizedPnl") or 0)
        except (TypeError, ValueError):
            continue
        inst = str(ev.get("instId") or "")
        if not inst:
            continue
        if pnl > 0.05:
            notes.append(f"BIG WIN {inst} +${pnl:.4f} — replicate: wide TP, momentum entry, tight SL")
        elif pnl < -0.05:
            notes.append(f"BIG LOSS {inst} ${pnl:.4f} — avoid same setup; tighten entry criteria")

    if not notes:
        return notes

    from autohedge.swarm_learning_audit import record_learned

    with _lock:
        data = _load()
        for note in notes[:8]:
            _add_tactic(
                data,
                title=note[:70],
                body=note,
                source="journal",
                confidence=0.65 if "BIG WIN" in note or "favor" in note else 0.75,
            )
        cycle_lessons: list[dict[str, Any]] = data.setdefault("cycle_lessons", [])
        cycle_lessons.append({"ts": time.time(), "notes": notes})
        data["cycle_lessons"] = cycle_lessons[-40:]
        _save(data)

    record_learned(
        title="Journal trade patterns",
        detail=notes[0],
        source="journal",
        proof={"notes": notes[:5]},
    )
    return notes


def tactics_block_for_task(max_tactics: int = 8) -> str:
    """Inject learned tactics into each cycle task."""
    with _lock:
        data = _load()
    tactics = (data.get("tactics") or [])[:max_tactics]
    if not tactics:
        return (
            "\n\nLEARNED TACTICS: (building playbook — agents should use blofin_research_trading_tactics "
            "and cross-check peers against live Blofin data each handoff)"
        )
    lines = [
        "",
        "LEARNED TACTICS (persistent playbook — apply and refine each cycle):",
        "Agents MUST cross-check each other's numbers against live Blofin tools before handoff.",
    ]
    for i, t in enumerate(tactics, 1):
        src = t.get("source", "?")
        conf = float(t.get("confidence") or 0)
        lines.append(f"  {i}. [{src} conf={conf:.2f}] {t.get('title')}: {str(t.get('body') or '')[:220]}")
    recent = (data.get("internet_research") or [])[-1:]
    if recent:
        r = recent[0]
        lines.append(f"Latest web research ({r.get('engine')}): {r.get('query')}")
        for s in (r.get("summaries") or [])[:2]:
            lines.append(f"  - {s[:180]}")
    return "\n".join(lines)


def post_cycle_learn(*, cycle: int, pipeline: dict[str, Any] | None = None) -> None:
    """After each cycle: journal lessons + optional pipeline notes."""
    notes = learn_from_journal()
    if notes:
        logger.info("Cycle {} journal tactics: {}", cycle, notes[0][:80])
    if pipeline:
        cand = pipeline.get("candidate_inst_id")
        if cand:
            with _lock:
                data = _load()
                _add_tactic(
                    data,
                    title=f"Cycle {cycle} candidate {cand}",
                    body=f"Pipeline terminal={pipeline.get('terminal')} risk={pipeline.get('risk_approved')}",
                    source="cycle",
                    confidence=0.5,
                )
                _save(data)


def _background_loop() -> None:
    while True:
        try:
            time.sleep(RESEARCH_INTERVAL_SEC)
            with _lock:
                data = _load()
                last = float(data.get("last_research_at") or 0)
            if time.time() - last < RESEARCH_INTERVAL_SEC * 0.9:
                continue
            research_tactics_online()
            learn_from_journal()
        except Exception as exc:
            logger.warning("Tactics background loop error: {}", exc)


def ensure_tactics_background() -> None:
    global _bg_started
    if _bg_started:
        return
    _bg_started = True
    # Seed playbook on startup
    try:
        with _lock:
            data = _load()
            last = float(data.get("last_research_at") or 0)
        if time.time() - last > RESEARCH_INTERVAL_SEC:
            research_tactics_online()
        learn_from_journal()
    except Exception as exc:
        logger.warning("Tactics startup seed failed: {}", exc)
    t = threading.Thread(target=_background_loop, name="owl-tactics-research", daemon=True)
    t.start()
    logger.info("Tactics research background thread started (every {}s)", RESEARCH_INTERVAL_SEC)


def tactics_playbook_json() -> str:
    with _lock:
        return json.dumps(_load(), default=str)
