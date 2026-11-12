"""Set up and run the whole-school portal demo.

    python -m hatua school-demo          # make demo_school/, load it, open the portal
    python -m hatua school-demo --no-serve

Everything in the demo is synthetic. The practice accounts share one PIN, which the
demo login page shows; a real school registers each teacher with their own PIN using
`python -m hatua teacher-add`.
"""
from __future__ import annotations

import json
import os
import runpy
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import auth, config, drive, notify, pathways, store

REPO = Path(__file__).resolve().parent.parent


def demo_info() -> dict | None:
    p = config.ROOT / "demo.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def setup() -> dict:
    """Load the demo found in HATUA_HOME into a fresh store. Run with HATUA_HOME set."""
    info = demo_info()
    if info is None:
        raise SystemExit("No demo.json here. Run: python -m hatua school-demo")
    store.reset()
    for p in (config.LOGS, config.PROFILES, config.INBOX):
        shutil.rmtree(p, ignore_errors=True)
    for name in ("teachers", "sessions", "auth_state"):
        (config.STORE / f"{name}.json").unlink(missing_ok=True)
    raw = config.RAW
    counts = {"learners": store.load_class_list(raw / "learners.csv"),
              "teachers": store.load_assignments(raw / "teacher_assignments.csv"),
              "attendance": store.load_attendance(raw / "attendance.csv"),
              "notes": store.load_notes(raw / "teacher_notes.csv")}
    counts["history"] = store.ingest_records(raw / "records_2021_2026.csv")["added"]
    for t in info["teachers"]:
        auth.register(t["teacher_id"], t["name"], info["pin"])
    approved = 0
    items = sorted(info.get("already_approved", []), key=lambda i: not i.get("earlier"))
    for n, item in enumerate(items):
        if n and items[n - 1].get("earlier") and not item.get("earlier"):
            _forget_old_alerts()
        session = auth.login(item["teacher_id"], info["pin"])["session"]
        approved += drive.decide(item["file"], session, "approve")["added"]
        auth.logout(session)
    if items and items[-1].get("earlier"):
        _forget_old_alerts()
    for tid, lid in info.get("open_pathways", []):  # the class teacher opens, through the real gate
        session = auth.login(tid, info["pin"])["session"]
        pathways.open_ideas(session, lid)
        auth.logout(session)
    links = {}
    for p in info.get("parents", []):
        auth.register(p["parent_id"], p["name"], info["pin"], must_change=bool(p.get("one_time")), role="parent")
        teacher = next(t["name"] for t in info["teachers"] if t["teacher_id"] == p["teacher_id"])
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        links[p["parent_id"]] = {"children": list(p["children"]), "relation": p["relation"],
                                 "added": {lid: {"by": teacher, "at": at} for lid in p["children"]}}
    store.save("guardians", links)
    counts["parents"] = len(links)
    counts["files_approved_at_setup"] = len(info.get("already_approved", []))
    counts["records_from_the_drive"] = approved
    for t in info["teachers"]:  # start clean: nobody has signed in yet, and some hold a one-time PIN
        auth.register(t["teacher_id"], t["name"], info["pin"],
                      must_change=t["teacher_id"] in info.get("first_sign_in", []))
    for name in ("sessions", "auth_state"):
        (config.STORE / f"{name}.json").unlink(missing_ok=True)
    counts["missing_or_waiting_notices"] = len(notify.check_missing())
    return counts


def _forget_old_alerts() -> None:
    """Terms approved earlier in the year raised their learner alerts back then.

    The demo opens in November, so those alerts are not shown as new. A pattern that
    reaches the newest term is raised again when that term is approved.
    """
    store.save("notices", [n for n in store.load("notices") if not n.get("learner_id")])


def main(argv: list[str]) -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m hatua school-demo")
    ap.add_argument("--home", default=str(REPO / "demo_school"), help="Folder for the demo (default ./demo_school)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-serve", action="store_true", help="Set up only; do not start the portal")
    args = ap.parse_args(argv)
    home = Path(args.home).resolve()
    runpy.run_path(str(REPO / "scripts" / "make_school_demo.py"), run_name="not_main")["main"](home)
    info = json.loads((home / "demo.json").read_text(encoding="utf-8"))
    env = {**os.environ, "HATUA_HOME": str(home), "PYTHONPATH": str(REPO),
           "HATUA_TODAY": os.environ.get("HATUA_TODAY", info["today"])}
    env.pop("HATUA_DRIVE", None)
    print("Loading the school and approving Term 1 and Term 2 through the gate. This takes about 20 seconds...")
    subprocess.run([sys.executable, "-m", "hatua", "school-setup"], cwd=REPO, env=env, check=True)
    print("\nPractice accounts (PIN for all: " + info["pin"] + "):")
    for t in info["teachers"]:
        print(f"  {t['teacher_id']}  Grade {t['stream']:<3}  {t['name']}")
    for p in info.get("parents", []):
        print(f"  {p['parent_id']}  Parent     {p['name']}")
    print(f"\nThe school drive (the Excel folders for each class and term) is here:\n  {home / 'school_drive'}")
    if args.no_serve:
        print(f"\nStart the portal later with:  HATUA_HOME={home} HATUA_TODAY={env['HATUA_TODAY']} "
              f"python -m hatua portal")
        return
    os.execvpe(sys.executable, [sys.executable, "-m", "hatua", "portal", "--port", str(args.port)], env)
