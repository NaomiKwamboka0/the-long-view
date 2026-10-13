"""Command line for Hatua. Run `python3 -m hatua --help`."""
from __future__ import annotations

import argparse
import json
import runpy
import shutil
import sys
from pathlib import Path

from . import config, gate, store, tools
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


def cmd_approve(args) -> None:
    edited = Path(args.edited).read_text(encoding="utf-8") if args.edited else None
    entry = gate.approve(args.draft_id, teacher=args.teacher, decision="reject" if args.reject else "approve",
                         edited_text=edited, share_with_guardian=args.share, reason=args.reason or "")
    print(json.dumps(entry, indent=1))


def cmd_save(args) -> None:
    print(json.dumps(tools.update_profile(args.draft_id), indent=1))


def cmd_import(args) -> None:
    """Apply approvals exported from the Hatua page (ui/hatua.html)."""
    items = json.loads(Path(args.file).read_text(encoding="utf-8"))
    for it in items:
        if it.get("audience") == "guardian":
            label = f"{it['learner_id']} guardian ({it['language']})"
            try:
                d = tools.draft_summary(it["learner_id"], "guardian", it["language"])
                gate.approve(d["draft_id"], teacher=it["teacher"], decision="approve", share_with_guardian=True,
                             expected_hash=it.get("hash"))
                print(f"{label}: approved -> {tools.update_profile(d['draft_id'])['saved']}")
            except (GateBlocked, ValueError) as exc:
                print(f"{label}: NOT applied ({exc})")
            continue
        try:
            entry = gate.approve(it["draft_id"], teacher=it["teacher"], decision=it["decision"],
                                 edited_text=it.get("edited_text"), share_with_guardian=it.get("share", False),
                                 reason=it.get("reason", ""), removed_pattern_ids=it.get("removed_pattern_ids"),
                                 expected_hash=it.get("hash"))
            msg = entry["decision"]
            if entry["decision"] == "approve":
                msg += " -> " + tools.update_profile(it["draft_id"])["saved"]
            print(f"{it['draft_id']}: {msg}")
        except (GateBlocked, ValueError) as exc:
            print(f"{it['draft_id']}: NOT applied ({exc})")


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
    cmd_build_ui(args)
    print("Open ui/hatua.html in your browser. No internet or server needed.")


def cmd_build_ui(args) -> None:
    from .build_ui import build
    print("Wrote", build())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hatua", description="Cited, teacher-approved CBC learner profiles.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="Load the synthetic class (and generate it if missing)")
    s.add_argument("--fresh", action="store_true", help="Regenerate the dummy data")
    s.set_defaults(fn=cmd_setup)
    s = sub.add_parser("ingest", help="Add a new CSV export from data/inbox")
    s.add_argument("file")
    s.set_defaults(fn=cmd_ingest)
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
    s.add_argument("--teacher", required=True, help="Your full name")
    s.add_argument("--reject", action="store_true")
    s.add_argument("--share", action="store_true", help="Allow a guardian message to be shared")
    s.add_argument("--edited", help="File with your edited text")
    s.add_argument("--reason")
    s.set_defaults(fn=cmd_approve)
    s = sub.add_parser("save", help="Save an approved draft to the profile (gated)")
    s.add_argument("draft_id")
    s.set_defaults(fn=cmd_save)
    s = sub.add_parser("import-approvals", help="Apply approvals downloaded from the Hatua page")
    s.add_argument("file")
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
    return 0
