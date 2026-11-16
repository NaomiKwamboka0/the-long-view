"""A new school starts empty: someone creates an account, then adds their own learners.

No practice people, no demo data. Everything stays on this computer (hatua.store, hatua.auth).

* `create_account` registers a class teacher for ONE class (a stream such as 6A). The first account on
  a computer also names the school. After that, each further teacher creates their own account for a
  class that has no class teacher yet, so nobody can claim a class that someone already teaches: what a
  teacher sees is decided only by hatua.scope, from the class they were assigned here.
* `add_learners` lets the class teacher type their learners: first names, and an admission number if they
  like. Hatua gives each learner its own HT-number, which is what results files use.
* `results_template` makes the Excel sheet to fill in for a term, with one row per learner and learning area.

A practice school (it has a demo.json) never opens accounts: those are made-up people.
"""
from __future__ import annotations

import re

from . import audit, auth, config, school, store, xlsx
from .summary import GateBlocked

STREAM = re.compile(r"^[4-9][A-Za-z0-9]{0,3}$")
NAME = re.compile(r"^[^\W\d_][\w'’. -]{0,39}$")
ADMISSION = re.compile(r"^[A-Za-z0-9/_-]{1,20}$")
MAX_TEACHERS = 60
MAX_CLASS = 200
MAX_PER_ADD = 100

AREAS = {
    "lower": ["Mathematics", "English", "Kiswahili", "Science and Technology", "Social Studies", "Agriculture", "Creative Arts"],
    "upper": ["Mathematics", "English", "Kiswahili", "Integrated Science", "Social Studies", "Pre-Technical Studies",
              "Agriculture", "Creative Arts and Sports"],
}


def settings() -> dict:
    s = store.load("settings")
    return s if isinstance(s, dict) else {}


def school_name() -> str:
    name = settings().get("school", "")
    if name:
        return name
    learners = store.load("learners")
    return learners[0].get("school", "") if learners and isinstance(learners[0], dict) else ""


def is_practice() -> bool:
    return (config.ROOT / "demo.json").exists()


def first_run() -> bool:
    """True until the first account exists on this computer."""
    return not is_practice() and not auth.teachers() and not settings().get("school")


def signup_open() -> bool:
    return not is_practice() and len(auth.teachers()) < MAX_TEACHERS


def create_account(school: str, name: str, member_no: str, stream: str, pin: str, pin_again: str) -> dict:
    """Make a class teacher's account for their class. Raises ValueError with a sentence the person can act on."""
    if not signup_open():
        raise ValueError("New accounts are not opened on this computer.")
    first = first_run()
    school = re.sub(r"\s+", " ", (school or "").strip())
    if first:
        if not 3 <= len(school) <= 80:
            raise ValueError("Type your school's name (3 to 80 letters).")
    else:
        school = school_name()
    name = re.sub(r"\s+", " ", (name or "").strip())
    if len(name) < auth.MIN_NAME or len(name) > 60:
        raise ValueError("Type your full name.")
    member_no = (member_no or "").strip().upper()
    if not config.TEACHER_ID.match(member_no):
        raise ValueError("Your member number (TSC number) must be 3 to 24 letters, numbers, '-' or '_'.")
    if auth.role_of(member_no):
        raise ValueError("That member number already has an account here. Sign in instead.")
    stream = (stream or "").strip().upper()
    if not STREAM.match(stream):
        raise ValueError("Type your class like 6A, or just 6: a grade from 4 to 9, then your stream letter if you have one.")
    assignments = store.load("assignments")
    assignments = assignments if isinstance(assignments, dict) else {}
    if any(stream in (a.get("streams") or []) for a in assignments.values() if isinstance(a, dict)):
        raise ValueError(f"Class {stream} already has a class teacher on this computer.")
    if pin != pin_again:
        raise ValueError("The two PINs are not the same. Type them again.")
    problem = auth.pin_problem(pin, member_no)
    if problem:
        raise ValueError(problem)
    auth.register(member_no, name, pin)          # the person's own PIN: nothing is "one-time" here
    assignments[member_no] = {"role": "class_teacher", "streams": [stream], "subjects": []}
    store.save("assignments", assignments)
    if first:
        store.save("settings", {**settings(), "school": school})
    audit.write_event({"tool": "account.create", "actor": member_no, "ok": True,
                       "inputs": {"kwargs": {"class": stream}}, "output": {"first_account": first}})
    return {"teacher_id": member_no, "name": name, "class": stream, "school": school_name()}


def _own_stream(teacher_id: str) -> str:
    streams = school.streams_of(teacher_id)
    if not streams:
        raise GateBlocked("You have no class on this computer.")
    return streams[0]


def parse_learners(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Lines like 'Wanjiku' or 'Wanjiku, 1042' → (name, admission number) pairs, and the lines that were refused."""
    rows, bad = [], []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in re.split(r"[,\t;]", line, maxsplit=1)]
        name, adm = parts[0], (parts[1] if len(parts) > 1 else "")
        if not NAME.match(name) or (adm and not ADMISSION.match(adm)):
            bad.append(line[:40])
            continue
        rows.append((name, adm))
    return rows, bad


def add_learners(teacher_id: str, text: str) -> dict:
    """Add the class teacher's learners. Returns {added: [{learner_id, name}], skipped: [...], total}."""
    stream = _own_stream(teacher_id)
    rows, bad = parse_learners(text)
    if not rows and not bad:
        raise ValueError("Type at least one name. Put each learner on a new line.")
    if len(rows) > MAX_PER_ADD:
        raise ValueError(f"Add at most {MAX_PER_ADD} learners at a time.")
    learners = store.load("learners")
    learners = learners if isinstance(learners, list) else []
    mine = [l for l in learners if isinstance(l, dict) and l.get("stream") == stream]
    if len(mine) + len(rows) > MAX_CLASS:
        raise ValueError(f"A class can have at most {MAX_CLASS} learners here.")
    taken = {(l.get("first_name", "").lower(), l.get("admission_no", "")) for l in mine}
    nums = [int(m.group(1)) for l in learners if isinstance(l, dict) and (m := re.match(r"HT-(\d{4})$", l.get("learner_id", "")))]
    nxt = max(nums, default=0) + 1
    added, skipped = [], []
    for name, adm in rows:
        if (name.lower(), adm) in taken:
            skipped.append(name)
            continue
        if nxt > 9999:
            raise ValueError("This computer has reached its limit of learners.")
        lid = f"HT-{nxt:04d}"
        nxt += 1
        learners.append({"learner_id": lid, "first_name": name, "sex": "", "current_grade": stream[0], "stream": stream,
                         "joined": "", "school": school_name(), "admission_no": adm})
        taken.add((name.lower(), adm))
        added.append({"learner_id": lid, "name": name})
    store.save("learners", learners)
    audit.write_event({"tool": "learners.add", "actor": teacher_id, "ok": True,
                       "inputs": {"kwargs": {"class": stream}}, "output": {"added": len(added), "skipped": len(skipped), "refused": len(bad)}})
    return {"added": added, "skipped": skipped, "refused": bad, "total": len(mine) + len(added)}


def results_template(teacher_id: str, year: int, term: int) -> bytes:
    """An Excel sheet for one term: a row per learner and learning area, with the level (EE ME AE BE) left to fill in."""
    stream = _own_stream(teacher_id)
    grade = int(stream[0])
    areas = AREAS["lower" if grade <= 6 else "upper"]
    rows = [{"learner_id": l["learner_id"], "name": l["first_name"], "grade": grade, "year": year, "term": term,
             "learning_area": a, "level": "", "score": "", "task": ""}
            for l in school.learners_of(teacher_id) for a in areas]
    if not rows:
        raise ValueError("Add your learners first.")
    return xlsx.to_bytes(rows, "Results", ["learner_id", "name", "grade", "year", "term", "learning_area", "level", "score", "task"])
