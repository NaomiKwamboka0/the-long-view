"""Command line for Hatua. Run `python3 -m hatua --help`."""
from __future__ import annotations

import argparse
import getpass
import json
import runpy
import shutil
import sys
from pathlib import Path

from . import auth, config, gate, importer, store, tools
from .summary import GateBlocked


def cmd_setup(args) -> None:
    if args.fresh or not (config.RAW / "learners.csv").exists():
        runpy.run_path(str(config.ROOT / "scripts" / "make_dummy_data.py"), run_name="__main__")
    store.reset()
    for p in (config.LOGS, config.PROFILES):
        shutil.rmtree(p, ignore_errors=True)
    print("class list:", store.load_class_list(config.RAW / "learners.csv"))
    print("attendance rows:", store.load_attendance(config.RAW / "attendance.csv"))
    print("teacher notes:", store.load_notes(config.RAW / "teacher_notes.csv"))
    print(store.ingest_records(config.RAW / "records_2021_2026.csv")["message"])
    print("Next: python3 -m hatua build-ui   (then open ui/hatua.html)")


def cmd_ingest(args) -> None:
    print(json.dumps(tools.ingest_record(args.file), indent=1, ensure_ascii=False))


def cmd_map_export(args) -> None:
    """Turn a school's own CSV into Hatua's columns, keeping only what the mapping names."""
    report = importer.map_export(Path(args.file), Path(args.mapping), args.out)
    print(json.dumps(report, indent=1, ensure_ascii=False))


def cmd_patterns(args) -> None:
    found = tools.find_patterns(args.learner_id)
    print(f"{found['first_name']} ({found['learner_id']}): {found['records_reviewed']} records, {found['span']}")
    for p in found["patterns"]:
        print(f"- [{p['type']}] {p['statement']}\n    evidence: {', '.join(p['evidence'][:10])}")
    for n in found["record_notes"]:
        print(f"- [record note] {n['statement']}")


def cmd_draft(args) -> None:
    d = tools.draft_summary(args.learner_id, args.audience, args.lang)
    print(d["text"])
    print(f"\n{d['draft_id']}  status={d['status']}  writer={d['writer']}")


def _sign_in(teacher_id: str) -> str:
    """Ask for the PIN once and return a session token. The PIN is never stored or logged."""
    pin = getpass.getpass(f"PIN for {teacher_id} (input is hidden): ")
    return auth.login(teacher_id, pin)["session"]


def cmd_teacher_add(args) -> None:
    pin = getpass.getpass("Choose a PIN (at least 6 characters, input is hidden): ")
    if pin != getpass.getpass("Type the PIN again: "):
        raise ValueError("The two PINs do not match.")
    entry = auth.register(args.id, args.name, pin)
    print(f"Registered {entry['name']} ({entry['teacher_id']}) on this computer.")
    print("Sign-in is asked for only when HATUA_REQUIRE_AUTH=1.")


def cmd_teacher_list(args) -> None:
    people = auth.teachers()
    if not people:
        print('No teachers registered here. Add one: python -m hatua teacher-add --id you --name "Your Name"')
        return
    for person in people:
        print(f"{person['teacher_id']}  {person['name']}")


def cmd_approve(args) -> None:
    edited = Path(args.edited).read_text(encoding="utf-8") if args.edited else None
    teacher_id = getattr(args, "teacher_id", None)
    entry = gate.approve(args.draft_id, teacher=getattr(args, "teacher", "") or "",
                         decision="reject" if args.reject else "approve",
                         edited_text=edited, share_with_guardian=args.share, reason=args.reason or "",
                         session=_sign_in(teacher_id) if teacher_id else None)
    print(json.dumps(entry, indent=1))


def cmd_save(args) -> None:
    print(json.dumps(tools.update_profile(args.draft_id), indent=1))


def cmd_import(args) -> None:
    """Apply approvals exported from the Hatua page (ui/hatua.html).

    With --teacher-id the person at this terminal signs in once and vouches for every
    decision in the file.
    """
    items = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("Approvals file must contain a JSON list.")
    teacher_id = getattr(args, "teacher_id", None)
    session = _sign_in(teacher_id) if teacher_id else None
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get("hash"), str) or len(it["hash"]) != 64:
            print("Decision: NOT applied (missing draft hash; export the reviewed decision again)")
            continue
        if not isinstance(it.get("teacher"), str) or it.get("decision") not in ("approve", "reject"):
            print("Decision: NOT applied (invalid teacher or decision)")
            continue
        if it.get("audience") == "guardian" and (it.get("share") is not True or it.get("decision") != "approve"):
            print("Guardian: NOT applied (explicit sharing approval is required)")
            continue
        if it.get("audience") == "guardian":
            label = f"{it.get('learner_id', 'unknown')} guardian ({it.get('language', 'unknown')})"
            try:
                d = tools.draft_summary(it["learner_id"], "guardian", it["language"])
                gate.approve(d["draft_id"], teacher=it["teacher"], decision="approve", share_with_guardian=True,
                             expected_hash=it.get("hash"), session=session)
                print(f"{label}: approved -> {tools.update_profile(d['draft_id'])['saved']}")
            except (GateBlocked, ValueError, KeyError, TypeError) as exc:
                print(f"{label}: NOT applied ({exc})")
            continue
        try:
            entry = gate.approve(it["draft_id"], teacher=it["teacher"], decision=it["decision"],
                                 edited_text=it.get("edited_text"), share_with_guardian=it.get("share", False),
                                 reason=it.get("reason", ""), removed_pattern_ids=it.get("removed_pattern_ids"),
                                 expected_hash=it.get("hash"), session=session)
            msg = entry["decision"]
            if entry["decision"] == "approve":
                msg += " -> " + tools.update_profile(it["draft_id"])["saved"]
            print(f"{it['draft_id']}: {msg}")
        except (GateBlocked, ValueError, KeyError, TypeError) as exc:
            print(f"{it.get('draft_id', 'unknown')}: NOT applied ({exc})")


def cmd_agent(args) -> None:
    try:
        from . import agent
    except ImportError as exc:
        print(f"The agent needs Python 3.10+ and: pip install -r requirements.txt  ({exc})", file=sys.stderr)
        raise SystemExit(1)
    agent.main(max_learners=args.max, rules=args.rules, no_fs=args.no_fs)


def cmd_demo(args) -> None:
    """One command: load the synthetic class, take in this term's export, build the page."""
    cmd_setup(argparse.Namespace(fresh=False))
    print(tools.ingest_record("2026_T3_new_records.csv")["message"])
    args.demo = True
    cmd_build_ui(args)
    print("Open ui/hatua.html in your browser. No internet or server needed.")


def cmd_build_ui(args) -> None:
    from .build_ui import build
    print("Wrote", build(demo=getattr(args, "demo", False)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hatua", description="Cited, teacher-approved CBC learner profiles.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="Load the synthetic class (and generate it if missing)")
    s.add_argument("--fresh", action="store_true", help="Regenerate the dummy data")
    s.set_defaults(fn=cmd_setup)
    s = sub.add_parser("ingest", help="Add a new CSV export from data/inbox")
    s.add_argument("file")
    s.set_defaults(fn=cmd_ingest)
    s = sub.add_parser("map-export", help="Convert a school's own CSV into Hatua's columns")
    s.add_argument("file")
    s.add_argument("--mapping", required=True, help="JSON mapping file, see data/mappings/")
    s.add_argument("--out", help="Output file name inside data/inbox (default: <name>_hatua.csv)")
    s.set_defaults(fn=cmd_map_export)
    s = sub.add_parser("patterns", help="Show cited patterns for a learner")
    s.add_argument("learner_id")
    s.set_defaults(fn=cmd_patterns)
    s = sub.add_parser("draft", help="Draft a summary for teacher review")
    s.add_argument("learner_id")
    s.add_argument("--audience", choices=["teacher", "guardian"], default="teacher")
    s.add_argument("--lang", choices=["en", "sw"], default="en")
    s.set_defaults(fn=cmd_draft)
    s = sub.add_parser("approve", help="(Teacher) approve or reject a draft")
    s.add_argument("draft_id")
    s.add_argument("--teacher", help="Your full name (not used when you sign in)")
    s.add_argument("--teacher-id", help="Sign in with this teacher ID and PIN")
    s.add_argument("--reject", action="store_true")
    s.add_argument("--share", action="store_true", help="Allow a guardian message to be shared")
    s.add_argument("--edited", help="File with your edited text")
    s.add_argument("--reason")
    s.set_defaults(fn=cmd_approve)
    s = sub.add_parser("save", help="Save an approved draft to the profile (gated)")
    s.add_argument("draft_id")
    s.set_defaults(fn=cmd_save)
    s = sub.add_parser("teacher-add", help="Register a teacher (ID, name, PIN) on this computer")
    s.add_argument("--id", required=True, help="3 to 24 letters, digits, '-' or '_'")
    s.add_argument("--name", required=True, help="The teacher's full name")
    s.set_defaults(fn=cmd_teacher_add)
    s = sub.add_parser("teacher-list", help="List the teachers registered on this computer")
    s.set_defaults(fn=cmd_teacher_list)
    s = sub.add_parser("import-approvals", help="Apply approvals downloaded from the Hatua page")
    s.add_argument("file")
    s.add_argument("--teacher-id", help="Sign in and vouch for every decision in the file")
    s.set_defaults(fn=cmd_import)
    s = sub.add_parser("agent", help="Run the agent: inbox -> patterns -> drafts -> pause for the teacher")
    s.add_argument("--max", type=int, default=3, help="Most learners to draft for in one run (default 3)")
    s.add_argument("--rules", action="store_true", help="Plan with fixed rules instead of the local model")
    s.add_argument("--no-fs", action="store_true", help="Skip the borrowed filesystem MCP server")
    s.set_defaults(fn=cmd_agent)
    s = sub.add_parser("demo", help="Set up the synthetic class, ingest this term, build the page")
    s.set_defaults(fn=cmd_demo)
    s = sub.add_parser("build-ui", help="Build the offline teacher page ui/hatua.html")
    s.set_defaults(fn=cmd_build_ui)
    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except GateBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0
