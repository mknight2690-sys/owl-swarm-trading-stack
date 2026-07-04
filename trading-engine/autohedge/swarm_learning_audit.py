"""Append-only audit trail — what the swarm learned, improved, and fixed autonomously."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
AUDIT_PATH = OUTPUT_DIR / "swarm_learning_audit.jsonl"
SUMMARY_PATH = OUTPUT_DIR / "swarm_learning_summary.json"


def _iso(ts: float | None = None) -> str:
    t = ts if ts is not None else time.time()
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _append_event(event: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    row = {"ts": time.time(), "ts_iso": _iso(), **event}
    with AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    _update_summary(row)


def _update_summary(row: dict[str, Any]) -> None:
    kind = str(row.get("kind") or "")
    summary: dict[str, Any] = {}
    if SUMMARY_PATH.is_file():
        try:
            summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            summary = {}
    summary["updated_at"] = row.get("ts_iso")
    summary["total_events"] = int(summary.get("total_events") or 0) + 1
    if kind == "learned":
        summary["last_learned"] = row
    elif kind == "improvement":
        summary["last_improvement"] = row
    elif kind == "self_fix":
        summary["last_self_fix"] = row
    elif kind == "verified_fix":
        summary["last_verified_fix"] = row
    elif kind == "convergence":
        summary["last_convergence"] = row
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")


def record_learned(
    *,
    title: str,
    detail: str,
    source: str,
    proof: dict[str, Any] | None = None,
) -> None:
    """Something new was learned (web, journal, cross-check lesson)."""
    _append_event(
        {
            "kind": "learned",
            "title": title,
            "detail": detail,
            "source": source,
            "proof": proof or {},
        }
    )
    logger.info("AUDIT learned [{}]: {}", source, title[:80])


def record_improvement(
    *,
    title: str,
    detail: str,
    metric: str,
    before: str | float,
    after: str | float,
    proof: dict[str, Any] | None = None,
) -> None:
    """Measurable improvement (equity, win rate, R:R, fewer errors)."""
    _append_event(
        {
            "kind": "improvement",
            "title": title,
            "detail": detail,
            "metric": metric,
            "before": before,
            "after": after,
            "proof": proof or {},
        }
    )
    logger.info("AUDIT improvement {}: {} -> {}", metric, before, after)


def record_self_fix(
    *,
    title: str,
    detail: str,
    component: str,
    proof: dict[str, Any] | None = None,
) -> None:
    """Autonomous fix without human intervention."""
    proof = proof or {}
    _append_event(
        {
            "kind": "self_fix",
            "title": title,
            "detail": detail,
            "component": component,
            "proof": proof,
        }
    )
    logger.info("AUDIT self_fix [{}]: {}", component, title[:80])
    issue_id = str(proof.get("issue_id") or "").strip()
    if issue_id:
        try:
            from autohedge.self_heal_playbook import FIX_META, teach_from_audit_event

            meta = FIX_META.get(issue_id, {})
            teach_from_audit_event(
                issue_id=issue_id,
                title=meta.get("title") or title,
                detail=detail,
                component=component,
                action=meta.get("action"),
                proof=proof,
            )
        except Exception:
            pass


def record_verified_fix(
    *,
    title: str,
    detail: str,
    component: str,
    proof: dict[str, Any] | None = None,
) -> None:
    """A repair or optimization was re-audited and confirmed working."""
    _append_event(
        {
            "kind": "verified_fix",
            "title": title,
            "detail": detail,
            "component": component,
            "proof": proof or {},
        }
    )
    logger.info("AUDIT verified_fix [{}]: {}", component, title[:80])


def record_convergence(
    *,
    title: str,
    detail: str,
    streak: int,
    proof: dict[str, Any] | None = None,
) -> None:
    """Zero-error convergence milestone."""
    _append_event(
        {
            "kind": "convergence",
            "title": title,
            "detail": detail,
            "streak": streak,
            "proof": proof or {},
        }
    )
    logger.info("AUDIT convergence streak={}: {}", streak, title[:80])


def read_recent_events(limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]:
    if not AUDIT_PATH.is_file():
        return []
    lines = AUDIT_PATH.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    events: list[dict[str, Any]] = []
    for line in lines[-limit * 3 :]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if kind:
        events = [e for e in events if e.get("kind") == kind]
    return events[-limit:]


def get_learning_report() -> dict[str, Any]:
    """Answer: last learned, last improvement, last self-fix — with proof."""
    summary: dict[str, Any] = {}
    if SUMMARY_PATH.is_file():
        try:
            summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            summary = {}

    last_learned = summary.get("last_learned")
    last_improvement = summary.get("last_improvement")
    last_self_fix = summary.get("last_self_fix")

    if not last_learned:
        for e in reversed(read_recent_events(50, "learned")):
            last_learned = e
            break
    if not last_improvement:
        for e in reversed(read_recent_events(50, "improvement")):
            last_improvement = e
            break
    if not last_self_fix:
        for e in reversed(read_recent_events(50, "self_fix")):
            last_self_fix = e
            break

    def _fmt(row: dict[str, Any] | None, empty: str) -> str:
        if not row:
            return empty
        ts = row.get("ts_iso") or _iso(float(row.get("ts") or 0))
        title = row.get("title") or row.get("detail") or "(untitled)"
        detail = row.get("detail") or ""
        src = row.get("source") or row.get("component") or row.get("metric") or ""
        proof = row.get("proof") or {}
        proof_s = json.dumps(proof, default=str)[:300] if proof else "see audit log"
        return f"[{ts}] {title}. {detail} ({src}). Proof: {proof_s}"

    narrative = (
        "SWARM LEARNING REPORT\n"
        f"Last thing learned: {_fmt(last_learned, 'Nothing recorded yet.')}\n"
        f"Last improvement: {_fmt(last_improvement, 'No measured improvement logged yet.')}\n"
        f"Last autonomous fix: {_fmt(last_self_fix, 'No self-fix logged yet.')}\n"
        f"Total audit events: {summary.get('total_events', len(read_recent_events(500)))}"
    )

    return {
        "updated_at": summary.get("updated_at"),
        "total_events": summary.get("total_events", 0),
        "last_learned": last_learned,
        "last_improvement": last_improvement,
        "last_self_fix": last_self_fix,
        "recent": read_recent_events(15),
        "narrative": narrative,
        "audit_path": str(AUDIT_PATH),
        "summary_path": str(SUMMARY_PATH),
    }


def learning_report_text() -> str:
    return str(get_learning_report().get("narrative") or "")


def learning_report_json() -> str:
    return json.dumps(get_learning_report(), default=str, indent=2)
