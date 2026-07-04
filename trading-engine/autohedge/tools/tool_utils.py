"""Shared helpers for Blofin agent tools."""

from __future__ import annotations

from typing import Any


def pick_inst_id(inst_id: str = "", **kwargs: Any) -> str:
    """Normalize inst_id / instId / instrument from tool kwargs."""
    raw = ""
    if inst_id and str(inst_id).strip():
        raw = str(inst_id).strip()
    else:
        for key in ("inst_id", "instId", "instrument", "symbol", "ticker"):
            val = kwargs.get(key)
            if val is not None and str(val).strip():
                raw = str(val).strip()
                break
    return normalize_usdt_inst_id(raw)


_INVALID_INST = frozenset(
    {"", "NULL", "NONE", "UNKNOWN", "N/A", "NA", "UNSET", "BTC", "ETH"}
)


def normalize_usdt_inst_id(inst_id: str) -> str:
    """Ensure Blofin linear USDT perp id (e.g. BTW -> BTW-USDT)."""
    inst = (inst_id or "").strip().upper()
    if not inst or inst in _INVALID_INST:
        return ""
    if inst.endswith("-USDT"):
        return inst
    if "-" in inst:
        return inst
    return f"{inst}-USDT"


def pick_str(*values: Any, default: str = "") -> str:
    for val in values:
        if val is not None and str(val).strip():
            return str(val).strip()
    return default
