#!/usr/bin/env python3
"""BaaS arcade tick — catalog, marketing, sibling health, outreach readiness."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATE_PATH = ROOT / "state" / "baas_agent_tick.json"
FLAG_PATH = ROOT / ".cursor" / "BAAS_ARCADE_DUE"
LOG_PATH = ROOT / "logs" / "baas_agent.log"


def _log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")
    print(msg)


def run_tick() -> dict:
    from baas.catalog import load_catalog, summary as catalog_summary
    from baas.cross_agent import (
        gmail_bridge_status,
        persist_sibling_health,
        scan_sibling_businesses,
        write_cross_agent_notes,
    )
    from baas.marketing import build_post_draft, due_tasks, load_queue, save_drafts

    catalog = load_catalog()
    cat_sum = catalog_summary(catalog)
    siblings = scan_sibling_businesses()
    persist_sibling_health(siblings)
    bridge = gmail_bridge_status()
    notes_path = write_cross_agent_notes()

    due = due_tasks(limit=3)
    drafts = []
    actions: list[str] = []
    for task in due:
        offering = next((o for o in catalog if o.id == task.offering_id), None)
        name = offering.name if offering else task.offering_id
        tag = offering.tagline if offering else ""
        drafts.append(build_post_draft(task, name, tag))
        actions.append(f"{task.channel}:{task.id}:{task.action}")

    drafts_path = save_drafts(drafts) if drafts else None

    config_gaps: list[str] = []
    if not bridge.get("smtp_ready") and not bridge.get("oauth_ready"):
        config_gaps.append("no Gmail — set SMTP_USER or WHOLESALING_GMAIL_ROOT")
    if cat_sum.get("draft", 0) > 0:
        config_gaps.append(f"{cat_sum['draft']} offerings draft — promote when demo-ready")

    report: dict = {
        "ts": time.time(),
        "catalog": cat_sum,
        "gmail_bridge": bridge,
        "cross_agent_notes": notes_path,
        "siblings": siblings,
        "due_marketing": [t.to_dict() for t in due],
        "drafts_path": drafts_path,
        "outreach_targets": [],
        "actions": actions,
        "config_gaps": config_gaps,
        "agent_due": bool(config_gaps or due or actions),
        "summary": "",
    }

    gmail = "smtp" if bridge.get("smtp_ready") else "oauth" if bridge.get("oauth_ready") else "none"
    report["summary"] = (
        f"offerings={cat_sum['total']} live={cat_sum.get('live', 0)} | "
        f"marketing_due={len(due)} | gmail={gmail} | actions={len(actions)}"
    )

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if report["agent_due"]:
        FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        FLAG_PATH.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")
    elif FLAG_PATH.exists():
        FLAG_PATH.unlink(missing_ok=True)

    _log(report["summary"])
    return report


def main() -> int:
    report = run_tick()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
