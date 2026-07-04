#!/usr/bin/env python3
"""Faucet collection agent — watch manual claims, learn, then automate with trust."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "state" / "faucet_money" / "agent_tick.json"


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2))


def cmd_watch_start(args: argparse.Namespace) -> int:
    from faucet_money.learner import get_active_session, start_session

    active = get_active_session()
    if active and not args.force:
        print(f"Active watch session already: {active['id']} ({active['faucet_id']})")
        print("Use watch end first, or --force")
        return 1
    session = start_session(args.faucet, operator=args.operator or "manual")
    print(f"WATCH STARTED session={session['id']} faucet={args.faucet}")
    print("Record each browser action:")
    print(f"  py -3.12 scripts/faucet_collection_agent.py watch step --session {session['id']} --action navigate --url <url>")
    print(f"  py -3.12 scripts/faucet_collection_agent.py watch step --session {session['id']} --action click --target \"Button text\"")
    print(f"  py -3.12 scripts/faucet_collection_agent.py watch step --session {session['id']} --action fill --target \"Email\" --value \"...\"")
    print(f"  py -3.12 scripts/faucet_collection_agent.py watch step --session {session['id']} --action captcha_manual --note \"solved recaptcha\"")
    print(f"  py -3.12 scripts/faucet_collection_agent.py watch end --session {session['id']} --success")
    return 0


def cmd_watch_step(args: argparse.Namespace) -> int:
    from faucet_money.learner import record_step

    sid = args.session
    if not sid:
        from faucet_money.learner import get_active_session

        active = get_active_session()
        if not active:
            print("No active session. Run watch start --faucet <id>")
            return 1
        sid = active["id"]
    step = record_step(
        sid,
        action=args.action,
        target=args.target or "",
        value=args.value or "",
        url=args.url or "",
        note=args.note or "",
    )
    session_path = ROOT / "state" / "faucet_money" / "sessions" / f"{sid}.json"
    n = len(json.loads(session_path.read_text(encoding="utf-8")).get("steps") or [])
    print(f"recorded step #{n}: {step['action']} {step.get('target') or step.get('url') or step.get('note')}")
    return 0


def cmd_watch_end(args: argparse.Namespace) -> int:
    from faucet_money.claims import mark_registered, record_claim
    from faucet_money.learner import end_session, learn_playbook

    sid = args.session
    if not sid:
        from faucet_money.learner import get_active_session

        active = get_active_session()
        if not active:
            print("No active session")
            return 1
        sid = active["id"]
    session = end_session(sid, success=bool(args.success), notes=args.notes or "", detail=args.detail or "")
    fid = session["faucet_id"]
    if args.success:
        if args.register:
            mark_registered(fid, username=args.username or "", email=args.email or "")
        if args.claim:
            record_claim(fid, ok=True, detail=args.detail or "watched manual claim")
        pb = learn_playbook(fid)
        if pb:
            print(f"PLAYBOOK READY {fid} steps={len(pb['steps'])} captcha={pb['captcha_required']} trust={pb['trust_score']}")
        else:
            from faucet_money.learner import MIN_MANUAL_SUCCESS, _successful_sessions

            left = max(0, MIN_MANUAL_SUCCESS - len(_successful_sessions(fid)))
            print(f"Session saved. Need {left} more successful manual watch(es) before playbook.")
    else:
        print(f"Session ended failed: {fid}")
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    from faucet_money.learner import learn_playbook

    pb = learn_playbook(args.faucet)
    if not pb:
        print(f"Not enough successful sessions for {args.faucet} (need 2)")
        return 1
    _print_json(pb)
    return 0


def cmd_replay_result(args: argparse.Namespace) -> int:
    from faucet_money.learner import record_replay

    pb = record_replay(
        args.faucet,
        success=bool(args.success),
        matched_steps=int(args.matched),
        total_steps=int(args.total),
    )
    print(
        f"replay {args.faucet} ok={args.success} trust={pb['trust_score']} "
        f"automate_allowed={pb['automate_allowed']}"
    )
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    from faucet_money.agent import tick_report

    report = tick_report()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _print_json(report)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    from faucet_money.learner import execution_plan

    _print_json(execution_plan(args.faucet))
    return 0


def cmd_tick(_: argparse.Namespace) -> int:
    from faucet_money.agent import tick_report

    report = tick_report()
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for a in report.get("actions") or []:
        print(a)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Faucet collection learning agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("watch", help="Watch manual claim session")
    ws = p.add_subparsers(dest="watch_cmd", required=True)
    s = ws.add_parser("start")
    s.add_argument("--faucet", required=True)
    s.add_argument("--operator", default="manual")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_watch_start)

    st = ws.add_parser("step")
    st.add_argument("--session", default="")
    st.add_argument("--action", required=True)
    st.add_argument("--target", default="")
    st.add_argument("--value", default="")
    st.add_argument("--url", default="")
    st.add_argument("--note", default="")
    st.set_defaults(func=cmd_watch_step)

    e = ws.add_parser("end")
    e.add_argument("--session", default="")
    e.add_argument("--success", action="store_true")
    e.add_argument("--failed", action="store_true")
    e.add_argument("--notes", default="")
    e.add_argument("--detail", default="")
    e.add_argument("--register", action="store_true")
    e.add_argument("--claim", action="store_true")
    e.add_argument("--username", default="")
    e.add_argument("--email", default="")
    e.set_defaults(func=cmd_watch_end)

    l = sub.add_parser("learn")
    l.add_argument("--faucet", required=True)
    l.set_defaults(func=cmd_learn)

    r = sub.add_parser("replay-result")
    r.add_argument("--faucet", required=True)
    r.add_argument("--success", action="store_true")
    r.add_argument("--failed", action="store_true")
    r.add_argument("--matched", default="0")
    r.add_argument("--total", default="0")
    r.set_defaults(func=cmd_replay_result)

    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("tick").set_defaults(func=cmd_tick)

    pl = sub.add_parser("plan")
    pl.add_argument("--faucet", required=True)
    pl.set_defaults(func=cmd_plan)

    args = parser.parse_args()
    if args.cmd == "watch" and args.watch_cmd == "end":
        if args.failed:
            args.success = False
        elif not args.success:
            args.success = True
    if args.cmd == "replay-result" and args.failed:
        args.success = False
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
