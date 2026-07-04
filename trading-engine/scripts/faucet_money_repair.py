#!/usr/bin/env python3
"""Self-heal faucet-money automations — fix anything broken before claims."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "state" / "faucet_money" / "repair.json"


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out.strip()[:500]
    except Exception as exc:
        return 1, str(exc)[:200]


def main() -> int:
    checks: list[dict] = []
    broken: list[str] = []

    # 1) Wallets
    code, out = _run([sys.executable, str(ROOT / "scripts" / "setup_faucet_wallets.py")])
    ok = code == 0
    checks.append({"id": "setup_wallets", "ok": ok, "detail": out.splitlines()[-1] if out else ""})
    if not ok:
        broken.append("setup_wallets")

    # 2b) FaucetPay registry (1000+ repeat claims)
    try:
        from faucet_money.faucetpay_import import ensure_registry

        reg = ensure_registry(max_age_hours=24.0)
        ok = int(reg.get("count") or 0) >= 100
        checks.append(
            {
                "id": "faucetpay_registry",
                "ok": ok,
                "detail": f"count={reg.get('count')} assets={len(reg.get('assets') or [])}",
            }
        )
        if not ok:
            broken.append("faucetpay_registry")
    except Exception as exc:
        checks.append({"id": "faucetpay_registry", "ok": False, "detail": str(exc)[:160]})
        broken.append("faucetpay_registry")

    # 3) Imports
    try:
        from faucet_money.registry import enabled_real_faucets  # noqa: F401
        from faucet_money.verify import verify_all_wallets  # noqa: F401
        from faucet_money.wallets import load_addresses

        load_addresses()
        checks.append({"id": "python_imports", "ok": True})
    except Exception as exc:
        checks.append({"id": "python_imports", "ok": False, "detail": str(exc)[:200]})
        broken.append("python_imports")

    # 3) Tick script
    code, out = _run([sys.executable, str(ROOT / "scripts" / "faucet_money_tick.py")])
    ok = code == 0
    checks.append({"id": "faucet_money_tick", "ok": ok, "detail": out.splitlines()[0] if out else ""})
    if not ok:
        broken.append("faucet_money_tick")

    # 4) Loop process
    code, out = _run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "start_faucet_money_loop.ps1"),
            "-Status",
        ]
    )
    loop_ok = "RUNNING" in out
    checks.append({"id": "notify_loop", "ok": loop_ok, "detail": out.splitlines()[0] if out else ""})
    if not loop_ok:
        broken.append("notify_loop")
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts" / "start_faucet_money_loop.ps1"),
                "-Foreground",
            ],
            cwd=ROOT,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )

    # 5) Tick json readable
    tick_path = ROOT / "state" / "faucet_money" / "tick.json"
    tick_ok = False
    if tick_path.is_file():
        try:
            tick_ok = bool(json.loads(tick_path.read_text(encoding="utf-8")).get("ok"))
        except Exception:
            pass
    checks.append({"id": "tick_json", "ok": tick_ok})
    if not tick_ok:
        broken.append("tick_json")

    # 6) Collection agent
    code, out = _run([sys.executable, str(ROOT / "scripts" / "faucet_collection_agent.py"), "tick"])
    ok = code == 0
    checks.append({"id": "collection_agent", "ok": ok, "detail": out.splitlines()[0] if out else ""})
    if not ok:
        broken.append("collection_agent")

    report = {
        "ok": len(broken) == 0,
        "broken": broken,
        "checks": checks,
        "actions": [],
    }
    if broken:
        report["actions"] = [f"fix_{b}" for b in broken]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"repair ok={report['ok']} broken={broken or 'none'}")
    for c in checks:
        mark = "OK" if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['id']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
