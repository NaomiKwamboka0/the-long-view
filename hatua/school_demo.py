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
from pathlib import Path

from . import auth, config, drive, notify, store

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
    approved = []
    for item in info.get("already_approved", []):
        session = auth.login(item["teacher_id"], info["pin"])["session"]
        result = drive.decide(item["file"], session, "approve")
        auth.logout(session)
        approved.append({"file": item["file"], "added": result["added"], "notices": len(result["notices"])})
    counts["approved_at_setup"] = approved
    counts["missing_or_waiting_notices"] = len(notify.check_missing())
    return counts


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
    subprocess.run([sys.executable, "-m", "hatua", "school-setup"], cwd=REPO, env=env, check=True)
    print("\nPractice accounts (PIN for all: " + info["pin"] + "):")
    for t in info["teachers"]:
        print(f"  {t['teacher_id']}  Grade {t['stream']:<3}  {t['name']}")
    if args.no_serve:
        print(f"\nStart the portal later with:  HATUA_HOME={home} HATUA_TODAY={env['HATUA_TODAY']} "
              f"python -m hatua portal")
        return
    os.execvpe(sys.executable, [sys.executable, "-m", "hatua", "portal", "--port", str(args.port)], env)
