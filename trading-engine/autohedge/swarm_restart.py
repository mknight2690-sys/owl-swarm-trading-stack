"""
Graceful self-restart — apply code/config/playbook changes without human intervention.

When the swarm changes itself (env tuning, code deploy, playbook update), it can
request a restart between cycles. The running process spawns a fresh copy and exits;
the desktop launcher also watches restart_pending.json as a backup.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from loguru import logger

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parents[1] / "outputs"))
ROOT = Path(os.environ.get("OWL_SWARM_ROOT", r"C:\Users\mknig\owl-swarm"))
AUTO_TRADER = Path(os.environ.get("AUTO_TRADER_ROOT", r"C:\Users\mknig\blofin-auto-trader"))
PYTHON = os.environ.get(
    "OWL_PYTHON",
    r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe",
)
MAIN_SCRIPT = ROOT / "owl_llm_loop.py"

RESTART_PENDING = OUTPUT_DIR / "restart_pending.json"
FINGERPRINT_FILE = OUTPUT_DIR / "runtime_fingerprint.json"

# Files whose change requires a reload to take effect
_TRACKED = [
    ROOT / "owl_llm_loop.py",
    ROOT / "swarm_dashboard.html",
    AUTO_TRADER / "autohedge" / "swarm_autopilot.py",
    AUTO_TRADER / "autohedge" / "self_heal_playbook.py",
    AUTO_TRADER / "autohedge" / "swarm_overseer.py",
    AUTO_TRADER / "autohedge" / "swarm_restart.py",
    AUTO_TRADER / "autohedge" / "workers.py",
    AUTO_TRADER / "autohedge" / "support_agents.py",
    AUTO_TRADER / "autohedge" / "collective_audit.py",
    AUTO_TRADER / "autohedge" / "swarm_surface_sync.py",
    AUTO_TRADER / "autohedge" / "task_completion_audit.py",
    AUTO_TRADER / "autohedge" / "tpsl_guard.py",
]


def _file_sig(path: Path) -> str:
    if not path.is_file():
        return "missing"
    st = path.stat()
    return f"{st.st_mtime_ns}:{st.st_size}"


_ENV_DEFAULTS: dict[str, str] = {
    "OWL_TP_PCT": "",
    "OWL_SL_PCT": "",
    "OWL_MIN_RR": "",
    "OWL_PRERANK_TOP_N": "25",
    "OWL_UNIVERSE_SCAN_ALL": "1",
    "OWL_RANK_TOP_N": "0",
    "OWL_DEPLOY_MAX_CANDIDATES": "60",
    "OWL_TRADE_CANDIDATE_MAX": "60",
    "OWL_MAX_LEVERAGE": "12",
}


def _env_snapshot() -> dict[str, str]:
    return {k: os.environ.get(k) or _ENV_DEFAULTS.get(k, "") for k in _ENV_DEFAULTS}


def compute_fingerprint() -> dict[str, Any]:
    files: dict[str, str] = {}
    for p in _TRACKED:
        files[str(p)] = _file_sig(p)
    env_snap = _env_snapshot()
    blob = json.dumps({"files": files, "env": env_snap}, sort_keys=True)
    return {
        "digest": hashlib.sha256(blob.encode()).hexdigest()[:16],
        "files": files,
        "env": env_snap,
        "ts": time.time(),
    }


def save_runtime_fingerprint() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FINGERPRINT_FILE.write_text(json.dumps(compute_fingerprint(), indent=2), encoding="utf-8")


def fingerprint_drifted() -> tuple[bool, str]:
    if not FINGERPRINT_FILE.is_file():
        return False, ""
    try:
        saved = json.loads(FINGERPRINT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, ""
    current = compute_fingerprint()
    if current["digest"] != saved.get("digest"):
        for path, sig in current["files"].items():
            if saved.get("files", {}).get(path) != sig:
                return True, f"file changed: {Path(path).name}"
        for k, v in current["env"].items():
            if saved.get("env", {}).get(k) != v:
                return True, f"env changed: {k}={v}"
        return True, "runtime fingerprint drift"
    return False, ""


def request_restart(
    *,
    reason: str,
    source: str,
    component: str = "swarm_restart",
    proof: dict[str, Any] | None = None,
    after_cycle: bool = True,
) -> None:
    """Queue a graceful restart — picked up between cycles or by launcher."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "reason": reason,
        "source": source,
        "component": component,
        "proof": proof or {},
        "after_cycle": after_cycle,
        "requested_at": time.time(),
        "requested_pid": os.getpid(),
    }
    RESTART_PENDING.write_text(json.dumps(row, indent=2, default=str), encoding="utf-8")
    try:
        from autohedge.self_heal_playbook import teach_fix

        teach_fix(
            "graceful_restart",
            title="Graceful self-restart when changes need reload",
            detail=reason,
            component=component,
            action="spawn fresh owl_llm_loop.py between cycles",
            proof=row,
        )
    except Exception:
        pass
    try:
        from autohedge.swarm_learning_audit import record_self_fix

        record_self_fix(
            title=f"Restart requested: {reason[:80]}",
            detail=f"Source={source} — will restart between cycles for changes to take effect",
            component=component,
            proof=row,
        )
    except Exception:
        pass
    logger.info("RESTART requested [{}]: {}", source, reason[:100])


def restart_pending() -> dict[str, Any] | None:
    if not RESTART_PENDING.is_file():
        return None
    try:
        return json.loads(RESTART_PENDING.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def clear_restart_request() -> None:
    RESTART_PENDING.unlink(missing_ok=True)


def execute_self_restart(
    release_lock: Callable[[], None] | None = None,
    log_fn: Callable[[str, str], None] | None = None,
) -> None:
    """Spawn fresh owl_llm_loop and exit current process."""
    pending = restart_pending()
    reason = (pending or {}).get("reason", "scheduled")
    if log_fn:
        log_fn(f"SELF-RESTART: {reason}", "success")
    else:
        logger.info("SELF-RESTART: {}", reason)

    clear_restart_request()
    if release_lock:
        try:
            release_lock()
        except Exception:
            pass

    if not Path(PYTHON).is_file() or not MAIN_SCRIPT.is_file():
        logger.error("Cannot self-restart — python or main script missing")
        return

    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if sys.platform == "win32":
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)

    subprocess.Popen(
        [PYTHON, str(MAIN_SCRIPT)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=False,
    )
    os._exit(0)


def maybe_restart_after_cycle(
    *,
    release_lock: Callable[[], None] | None = None,
    log_fn: Callable[[str, str], None] | None = None,
) -> bool:
    """Between cycles: restart if pending or code/env drifted."""
    drifted, detail = fingerprint_drifted()
    if drifted and not restart_pending():
        request_restart(
            reason=f"Runtime drift detected: {detail}",
            source="fingerprint_watch",
            proof={"detail": detail},
        )

    if restart_pending():
        execute_self_restart(release_lock=release_lock, log_fn=log_fn)
        return True
    return False


def check_overseer_restart() -> None:
    """Called from overseer — request restart once if deployed code changed."""
    if restart_pending():
        return
    drifted, detail = fingerprint_drifted()
    if drifted:
        request_restart(
            reason=f"Code/config updated on disk: {detail}",
            source="overseer",
            proof={"detail": detail},
        )
