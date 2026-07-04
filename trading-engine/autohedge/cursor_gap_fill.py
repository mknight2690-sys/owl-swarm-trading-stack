"""
Cursor Agent gap-fill layer — fix once, teach forever.

Doctrine:
  - Cursor intervenes ONLY when swarm + overseer + pentest miss something.
  - Every manual fix MUST call teach_gap() so playbook auto-heals next time.
  - Cursor does NOT babysit: no duplicate owls, no closing XAI/PUMP, no redoing
    work the playbook already handles.

Run via overseer (1/min) or manually:
  python -c "from autohedge.cursor_gap_fill import run_gap_fill_pass; print(run_gap_fill_pass())"
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from loguru import logger

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
GAP_LOG = OUTPUT_DIR / "cursor_gap_fill.jsonl"

CURSOR_DOCTRINE = """
Cursor Agent = gap filler + teacher, NOT primary operator.
1. Let swarm self-heal, overseer tick (60s light), deep audit (15m) run first.
2. Only patch what they still miss after one full detection pass.
3. teach_gap() every new pattern — swarm must never need Cursor twice for same issue.
4. Never duplicate owl PIDs, kill external dashboard, or close profitable XAI/PUMP.
"""


def _append_log(row: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with GAP_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def teach_gap(
    issue_id: str,
    *,
    title: str,
    detail: str,
    component: str,
    action: str,
    proof: dict[str, Any] | None = None,
) -> None:
    """Record a Cursor-taught fix — compounds into self_heal_playbook + tactics."""
    from autohedge.self_heal_playbook import teach_fix

    teach_fix(
        issue_id,
        title=title,
        detail=detail,
        component=component,
        action=action,
        proof={"taught_by": "cursor_agent", **(proof or {})},
    )
    _append_log(
        {
            "ts": time.time(),
            "kind": "teach",
            "issue_id": issue_id,
            "title": title,
            "component": component,
        }
    )
    logger.info("CURSOR taught [{}]: {}", issue_id, title[:70])


def _gap_sparse_task_board() -> dict[str, Any] | None:
    try:
        from autohedge.swarm_tasks import ensure_task_board_seeded, get_task_board

        board = get_task_board()
        total = int((board.get("summary") or {}).get("total") or 0)
        if total >= 15:
            return None
        cycle = int(board.get("cycle") or 0)
        reseeded = ensure_task_board_seeded(cycle=cycle)
        if reseeded:
            teach_gap(
                "overseer_stale_task_board",
                title="Overseer audited sparse task board (<15 jobs)",
                detail=f"Board had {total} tasks; re-seeded cycle {cycle}",
                component="swarm_tasks",
                action="ensure_task_board_seeded(cycle) when total < 15",
                proof={"before_total": total, "cycle": cycle},
            )
        return {"fixed": reseeded, "before_total": total, "cycle": cycle}
    except Exception as exc:
        return {"error": str(exc)}


def _gap_playbook_never_auto_applied() -> list[str]:
    """Fixes taught many times but never auto-applied — swarm isn't learning them."""
    try:
        from autohedge.self_heal_playbook import playbook_summary

        pb = playbook_summary()
        gaps: list[str] = []
        for row in pb.get("fixes") or []:
            taught = int(row.get("teach_count") or 0)
            applied = int(row.get("auto_apply_count") or 0)
            if taught >= 2 and applied == 0:
                gaps.append(str(row.get("issue_id") or ""))
        return [g for g in gaps if g]
    except Exception:
        return []


def run_gap_fill_pass(*, source: str = "cursor_gap") -> dict[str, Any]:
    """
    One pass: detect gaps swarm missed, apply minimal fix, teach playbook.
    Called from overseer after autonomous heal — Cursor layer is last resort.
    """
    report: dict[str, Any] = {
        "ts": time.time(),
        "source": source,
        "doctrine": "gap_fill_only",
        "gaps_found": [],
        "actions": [],
        "taught": [],
        "ok": True,
    }

    # Reinforce catalog fixes (idempotent)
    try:
        from autohedge.self_heal_playbook import reinforce_known_fixes

        reinforced = reinforce_known_fixes()
        if reinforced:
            report["actions"].append(f"reinforced:{reinforced}")
    except Exception as exc:
        report["actions"].append(f"reinforce_error:{exc}")

    sparse = _gap_sparse_task_board()
    if sparse and sparse.get("fixed"):
        report["gaps_found"].append("overseer_stale_task_board")
        report["actions"].append(f"task_board_reseeded:{sparse}")
        report["taught"].append("overseer_stale_task_board")

    never_applied = _gap_playbook_never_auto_applied()
    if never_applied:
        report["gaps_found"].append("playbook_not_auto_applying")
        report["notes"] = f"taught but never auto-applied: {never_applied[:5]}"
        teach_gap(
            "playbook_auto_apply_gap",
            title="Playbook fixes taught but never auto-applied",
            detail=f"issue_ids: {never_applied[:8]}",
            component="self_heal_playbook",
            action="Verify _apply_fix() handles each issue_id; reinforce KNOWN_FIXES on boot",
            proof={"issue_ids": never_applied[:10]},
        )
        report["taught"].append("playbook_auto_apply_gap")

    # Teach mid-cycle audit doctrine once (code path now in task_completion_audit)
    try:
        from autohedge.self_heal_playbook import _load

        data = _load()
        if "overseer_mid_cycle_audit" not in (data.get("fixes") or {}):
            teach_gap(
                "overseer_mid_cycle_audit",
                title="Overseer false task failures during active cycle",
                detail="1-min overseer flagged pending required jobs while cycle still running.",
                component="task_completion_audit",
                action="relax required-job checks when source=overseer and is_cycle_in_progress()",
            )
            report["taught"].append("overseer_mid_cycle_audit")
    except Exception:
        pass

    _append_log({"kind": "pass", **report})
    return report


def gap_fill_summary_json() -> str:
    rows: list[dict[str, Any]] = []
    if GAP_LOG.is_file():
        for line in GAP_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return json.dumps({"doctrine": CURSOR_DOCTRINE.strip(), "recent": rows}, indent=2, default=str)
