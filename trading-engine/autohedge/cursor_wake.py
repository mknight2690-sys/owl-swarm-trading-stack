"""
Escalate to Cursor Agent — disk wake file + prompt payload for loop ticks.

Local monitor/overseer/pentest run first. When degraded or swarm misses a gap,
write cursor_wake.json so the 1-minute AGENT_LOOP tick knows to pull Cursor in.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
WAKE_FILE = OUTPUT_DIR / "cursor_wake.json"
WAKE_LOG = OUTPUT_DIR / "cursor_wake.jsonl"

DEFAULT_PROMPT = (
    "OWL oversee tick — you are the human's Cursor overseer, NOT delegated to scripts alone. "
    "Read outputs/cursor_wake.json, monitor.log tail, pipeline_state.json, equity stream age. "
    "Fix only what swarm+overseer+pentest missed; teach_gap() once per new pattern. "
    "Never duplicate owl PIDs, kill external dashboard, or close profitable XAI/PUMP."
)


def request_cursor_wake(
    reason: str,
    *,
    detail: str = "",
    source: str = "overseer",
    priority: str = "normal",
    proof: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Queue a Cursor wake — idempotent merge if same reason within 5 min."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    row: dict[str, Any] = {
        "ts": now,
        "reason": reason,
        "detail": detail[:500],
        "source": source,
        "priority": priority,
        "prompt": DEFAULT_PROMPT,
        "proof": proof or {},
        "acked": False,
    }
    if WAKE_FILE.is_file():
        try:
            prev = json.loads(WAKE_FILE.read_text(encoding="utf-8"))
            if (
                prev.get("reason") == reason
                and now - float(prev.get("ts") or 0) < 300
                and not prev.get("acked")
            ):
                prev["detail"] = detail[:500] or prev.get("detail")
                prev["ts"] = now
                prev["proof"] = {**(prev.get("proof") or {}), **(proof or {})}
                WAKE_FILE.write_text(json.dumps(prev, indent=2), encoding="utf-8")
                return prev
        except (json.JSONDecodeError, OSError):
            pass
    WAKE_FILE.write_text(json.dumps(row, indent=2), encoding="utf-8")
    with WAKE_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


def ack_cursor_wake(*, note: str = "") -> bool:
    if not WAKE_FILE.is_file():
        return False
    try:
        row = json.loads(WAKE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    row["acked"] = True
    row["acked_at"] = time.time()
    if note:
        row["ack_note"] = note[:200]
    WAKE_FILE.write_text(json.dumps(row, indent=2), encoding="utf-8")
    return True


def wake_status() -> dict[str, Any]:
    if not WAKE_FILE.is_file():
        return {"pending": False}
    try:
        row = json.loads(WAKE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"pending": False, "error": "parse_fail"}
    age = time.time() - float(row.get("ts") or 0)
    return {
        "pending": not row.get("acked"),
        "age_sec": round(age, 1),
        "reason": row.get("reason"),
        "priority": row.get("priority"),
        "source": row.get("source"),
        "prompt": row.get("prompt") or DEFAULT_PROMPT,
    }


def oversee_tick_payload() -> str:
    """JSON prompt for AGENT_LOOP_TICK sentinel."""
    st = wake_status()
    prompt = st.get("prompt") or DEFAULT_PROMPT
    if st.get("pending"):
        prompt += f" PRIORITY wake: {st.get('reason')} (age={st.get('age_sec')}s)."
    return json.dumps({"prompt": prompt, "wake": st}, separators=(",", ":"))
