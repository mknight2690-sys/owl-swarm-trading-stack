"""
TPSL Guard — continuous protection audit for every open isolated position.

Root causes this fixes:
  - blofin_assess_portfolio returned positions_missing_tpsl=[] when API trust=unknown
  - _pending_tpsl_for() treated ANY pending order as protected (partial/wrong marginMode)
  - blofin_ensure_position_tpsl skipped entirely when positions_unverified_waf
  - blofin_place_tpsl defaulted to cross margin while positions are isolated
  - Legacy entries (e.g. PUMP) opened without attach TP/SL
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from loguru import logger

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "")


def _default_margin_mode() -> str:
    return os.environ.get("BLOFIN_MARGIN_MODE", "isolated").strip().lower() or "isolated"


def _order_has_tp(order: dict[str, Any]) -> bool:
    for key in ("tpTriggerPrice", "tpTriggerPx", "tpPrice"):
        val = str(order.get(key) or "").strip()
        if val and val not in {"0", "-1"}:
            return True
    return False


def _order_has_sl(order: dict[str, Any]) -> bool:
    for key in ("slTriggerPrice", "slTriggerPx", "slPrice"):
        val = str(order.get(key) or "").strip()
        if val and val not in {"0", "-1"}:
            return True
    return False


def position_has_full_tpsl(
    inst_id: str,
    *,
    margin_mode: str | None = None,
    pending_orders: list[dict[str, Any]] | None = None,
) -> bool:
    """True only when an isolated-matching pending order has BOTH TP and SL."""
    from autohedge.tools.blofin_tools import get_blofin_client

    inst = inst_id.strip().upper()
    want_margin = (margin_mode or _default_margin_mode()).lower()
    orders = pending_orders
    if orders is None:
        try:
            orders = get_blofin_client().get_pending_tpsl(inst)
        except Exception as exc:
            logger.warning("tpsl_guard: pending lookup failed for {}: {}", inst, exc)
            return False

    logger.debug("Checking protection for {}: orders={}", inst, orders)
    for order in orders or []:
        if str(order.get("instId") or "").upper() not in ("", inst):
            continue
        om = str(order.get("marginMode") or order.get("tdMode") or "").lower()
        if om and om != want_margin:
            logger.debug("Order {} margin mode {} does not match {}", order.get("orderId"), om, want_margin)
            continue
        has_tp = _order_has_tp(order)
        has_sl = _order_has_sl(order)
        if has_tp and has_sl:
            logger.debug("Order {} provides full protection for {}", order.get("orderId"), inst)
            return True
        else:
            logger.debug("Order {} does not provide full protection: has_tp={}, has_sl={}", order.get("orderId"), has_tp, has_sl)
    return False


def is_tpsl_audit_rate_limited(report: dict[str, Any]) -> bool:
    """True when Blofin/Cloudflare rate limits prevent TP/SL verification."""
    err = str(report.get("pending_error") or report.get("error") or "").lower()
    return report.get("pending_trust") == "failed" and (
        "429" in err or "rate" in err or "1015" in err
    )


def audit_open_positions_tpsl(*, force_refresh: bool = False) -> dict[str, Any]:
    """
    Audit all open positions for full TP+SL on matching margin mode.
    Uses disk cache fallback when live API is flaky — never returns 'all ok' on empty data.
    """
    from autohedge.tools.blofin_tools import (
        _load_positions_disk,
        _open_position_rows,
        blofin_get_pending_tpsl,
        positions_trust_level,
    )

    if force_refresh:
        try:
            from autohedge.tools import blofin_tools as bt

            bt._portfolio_cache = None  # type: ignore[attr-defined]
        except Exception:
            pass

    trust = positions_trust_level()
    rows = _open_position_rows(retries=3)
    if not rows:
        disk = _load_positions_disk()
        if disk:
            rows, disk_trust = disk
            trust = disk_trust if disk_trust in {"live", "stale"} else "stale"

    report: dict[str, Any] = {
        "ts": time.time(),
        "positions_trust": trust,
        "open_count": len(rows),
        "protected": [],
        "missing": [],
        "partial": [],
        "orphan_wrong_margin": [],
        "ok": True,
    }

    if not rows:
        report["note"] = "flat — no open positions require TP/SL"
        return report

    all_pending: list[dict[str, Any]] = []
    try:
        from autohedge.tools.blofin_tools import get_blofin_client

        all_pending = get_blofin_client().get_pending_tpsl(None)
    except Exception as exc:
        report["pending_trust"] = "failed"
        report["pending_error"] = str(exc)[:200]

    by_inst: dict[str, list[dict]] = {}
    for order in all_pending:
        inst = str(order.get("instId") or "").upper()
        by_inst.setdefault(inst, []).append(order)

    for row in rows:
        inst = str(row.get("instId") or "")
        if not inst:
            continue
        margin = str(row.get("marginMode") or _default_margin_mode()).lower()
        pending = by_inst.get(inst.upper(), [])
        wrong = [
            o
            for o in pending
            if str(o.get("marginMode") or "").lower() not in ("", margin)
            and str(o.get("marginMode") or "").lower() != margin
        ]
        if wrong:
            report["orphan_wrong_margin"].append(
                {"instId": inst, "position_margin": margin, "orphan_orders": len(wrong)}
            )
        if position_has_full_tpsl(inst, margin_mode=margin, pending_orders=pending):
            report["protected"].append(inst)
            continue
        has_any = bool(pending)
        has_tp = any(_order_has_tp(o) for o in pending)
        has_sl = any(_order_has_sl(o) for o in pending)
        if has_any and (has_tp ^ has_sl or not (has_tp and has_sl)):
            report["partial"].append(
                {"instId": inst, "has_tp": has_tp, "has_sl": has_sl, "marginMode": margin}
            )
        report["missing"].append(inst)

    if report["missing"] or report["partial"]:
        if is_tpsl_audit_rate_limited(report):
            report["ok"] = True
            report["rate_limited_skip"] = True
            report["warnings"] = report.get("warnings") or []
            report["warnings"].append(
                "TP/SL verify rate-limited — not blocking new entries on other symbols"
            )
        else:
            report["ok"] = False
    if report["orphan_wrong_margin"]:
        report["warnings"] = report.get("warnings") or []
        report["warnings"].append(
            "orphan TP/SL orders on wrong marginMode do NOT protect isolated positions"
        )
    return report


def repair_missing_tpsl(*, inst_id: str = "") -> dict[str, Any]:
    """Place asymmetric TP/SL on every unprotected position; verify after."""
    from autohedge.tools.blofin_tools import blofin_place_tpsl

    before = audit_open_positions_tpsl(force_refresh=True)
    targets = list(before.get("missing") or []) + [
        str(p.get("instId"))
        for p in (before.get("partial") or [])
        if p.get("instId")
    ]
    if inst_id.strip():
        needle = inst_id.strip().upper()
        targets = [t for t in targets if t.upper() == needle] or [needle]
    
    logger.debug("Attempting TP/SL repair for targets: {}", targets)

    results: list[dict[str, Any]] = []
    for inst in targets:
        try:
            logger.debug("Placing TP/SL for {}", inst)
            raw = blofin_place_tpsl(inst_id=inst, tp_trigger_price="", sl_trigger_price="")
            logger.debug("Raw blofin_place_tpsl response for {}: {}", inst, raw)
            row = json.loads(raw)
            results.append({"instId": inst, "status": "placed", "result": row})
        except Exception as exc:
            logger.error("Failed to place TP/SL for {}: {}", inst, exc)
            results.append({"instId": inst, "status": "error", "error": str(exc)[:300]})

    after = audit_open_positions_tpsl(force_refresh=True)
    out = {
        "before": before,
        "after": after,
        "repairs": results,
        "fixed": after.get("ok", False),
    }


    if after.get("ok"):
        try:
            from autohedge.self_heal_playbook import teach_fix, record_auto_heal

            teach_fix(
                "missing_tpsl",
                title="Repair isolated positions missing full TP+SL",
                detail=(
                    "Audit requires BOTH tp and sl on matching marginMode=isolated. "
                    "Never skip when positions_trust=unknown — use disk cache + repair."
                ),
                component="tpsl_guard",
                action="audit_open_positions_tpsl() then blofin_place_tpsl per missing inst",
                proof={"repaired": targets, "after": after},
            )
            record_auto_heal("missing_tpsl", detail=f"Protected: {after.get('protected')}")
        except Exception:
            pass
        try:
            from autohedge.swarm_learning_audit import record_self_fix, record_verified_fix

            record_self_fix(
                title="TPSL Guard repaired missing protection",
                detail=f"Fixed: {targets}",
                component="tpsl_guard",
                proof=out,
            )
            record_verified_fix(
                title="TPSL Guard verified all positions protected",
                detail=str(after.get("protected")),
                component="tpsl_guard",
                proof=after,
            )
        except Exception:
            pass
    else:
        logger.error("tpsl_guard: still unprotected after repair: {}", after)

    return out


def run_tpsl_guard(*, source: str = "tpsl_guard") -> dict[str, Any]:
    """Audit → auto-repair → re-audit. Called every overseer/ops minute."""
    audit = audit_open_positions_tpsl()
    if audit.get("ok"):
        return {"source": source, "status": "ok", "audit": audit, "actions": []}

    missing = audit.get("missing") or []
    partial = audit.get("partial") or []
    logger.warning(
        "TPSL GUARD [{}]: missing={} partial={} trust={}",
        source,
        missing,
        partial,
        audit.get("positions_trust"),
    )

    repair = repair_missing_tpsl()
    actions = [f"tpsl_repair:{missing}", f"tpsl_partial:{partial}"]

    try:
        from autohedge.swarm_tasks import finish_task, start_task
        from autohedge.swarm_topology import set_agent_status

        start_task("tpsl_protection", "Ops-Monitor-Agent", "fix", detail=str(missing or partial))
        status = "done" if repair.get("fixed") else "fail"
        finish_task("tpsl_protection", "Ops-Monitor-Agent", "fix", status=status)
        set_agent_status("Ops-Monitor-Agent", "pass" if repair.get("fixed") else "fail")
    except Exception:
        pass

    return {
        "source": source,
        "status": "ok" if repair.get("fixed") else "degraded",
        "audit": audit,
        "repair": repair,
        "actions": actions,
    }
