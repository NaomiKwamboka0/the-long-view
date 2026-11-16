"""A new school starts empty: the head teacher sets it up, then creates every class teacher's login.

No practice people, no demo data. Everything stays on this computer (hatua.store, hatua.auth).

* The FIRST account on a computer is the head teacher's. It names the school. The head teacher may also
  teach a class (optional).
* Nobody else can create an account for themselves. The head teacher adds each class teacher: name, TSC
  number and class (a stream such as 6A). Hatua makes a ONE-TIME PIN, shown once to print or write down; the
  class teacher chooses their own PIN at the first sign-in (hatua.auth). The head teacher can give a new
  one-time PIN to a teacher who forgot theirs, and remove a teacher (the class is then free to give to
  someone else; its learners stay).
* The head teacher manages ACCOUNTS. Seeing a class's learners is still decided only by hatua.scope: the
  class teacher of that class sees it, and a head teacher sees a class only if they teach it too.
* `add_learners` lets a class teacher type their learners: first names, and an admission number if they
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
    """True until the first account (the head teacher's) exists on this computer."""
    return not is_practice() and not auth.teachers() and not settings().get("school")


def is_head(teacher_id: str) -> bool:
    return bool(teacher_id) and settings().get("head") == teacher_id


def _assignments() -> dict:
    a = store.load("assignments")
    return a if isinstance(a, dict) else {}


def _check_account(name: str, member_no: str, stream: str, *, stream_required: bool) -> tuple[str, str, str]:
    """The same rules for every new account. Returns the cleaned (name, member number, stream)."""
    name = re.sub(r"\s+", " ", (name or "").strip())
    if len(name) < auth.MIN_NAME or len(name) > 60:
        raise ValueError("Type the full name.")
    member_no = (member_no or "").strip().upper()
    if not config.TEACHER_ID.match(member_no):
        raise ValueError("The member number (TSC number) must be 3 to 24 letters, numbers, '-' or '_'.")
    if auth.role_of(member_no):
        raise ValueError("That member number already has an account here.")
    stream = (stream or "").strip().upper()
    if not stream and not stream_required:
        return name, member_no, ""
    if not STREAM.match(stream):
        raise ValueError("Type the class like 6A, or just 6: a grade from 4 to 9, then the stream letter if there is one.")
    if any(stream in (a.get("streams") or []) for a in _assignments().values() if isinstance(a, dict)):
        raise ValueError(f"Class {stream} already has a class teacher on this computer.")
    return name, member_no, stream


def create_account(school: str, name: str, member_no: str, stream: str, pin: str, pin_again: str) -> dict:
    """Set the school up: the FIRST account, the head teacher's, with a PIN of their own.
    `stream` is optional: the class the head teacher also teaches. Raises ValueError with a sentence to act on."""
    if is_practice():
        raise ValueError("This is the practice school: its accounts are made up and new ones cannot be created.")
    if not first_run():
        raise ValueError("Hatua is already set up on this computer. Ask your head teacher for an account.")
    school = re.sub(r"\s+", " ", (school or "").strip())
    if not 3 <= len(school) <= 80:
        raise ValueError("Type your school's name (3 to 80 letters).")
    name, member_no, stream = _check_account(name, member_no, stream, stream_required=False)
    if pin != pin_again:
        raise ValueError("The two PINs are not the same. Type them again.")
    problem = auth.pin_problem(pin, member_no)
    if problem:
        raise ValueError(problem)
    auth.register(member_no, name, pin)          # the head teacher's own PIN: nothing is "one-time" here
    if stream:
        store.save("assignments", {**_assignments(), member_no: {"role": "class_teacher", "streams": [stream], "subjects": []}})
    store.save("settings", {**settings(), "school": school, "head": member_no})
    audit.write_event({"tool": "account.create", "actor": member_no, "ok": True,
                       "inputs": {"kwargs": {"class": stream or None}}, "output": {"head_teacher": True}})
    return {"teacher_id": member_no, "name": name, "class": stream, "school": school_name()}


# ---------------------------------------------------------------- the head teacher's accounts
def _head(session: str | None, action: str) -> dict:
    who = auth.resolve(session, kind="human", action=action)
    if who.get("role", "teacher") != "teacher" or not is_head(who["teacher_id"]):
        raise GateBlocked("Only the head teacher can do this.")
    return who


def teachers(head_id: str) -> list[dict]:
    """Every teacher account, for the head teacher: who, which class, and whether they have signed in. No PIN material."""
    if not is_head(head_id):
        raise GateBlocked("Only the head teacher can do this.")
    registry = auth._read(auth._path("teachers"), {})
    out = []
    for t in auth.teachers():
        acc = registry.get(t["teacher_id"], {})
        streams = school.streams_of(t["teacher_id"])
        out.append({"teacher_id": t["teacher_id"], "name": t["name"], "head": is_head(t["teacher_id"]), "classes": streams,
                    "learners": len(school.learners_of(t["teacher_id"])),
                    "waiting_first_sign_in": bool(acc.get("must_change")), "last_login": acc.get("last_login")})
    # classes that have learners but no class teacher (a teacher was removed): shown so the head teacher can assign one
    learners = [l for l in store.load("learners") if isinstance(l, dict)]
    taken = {c for t in out for c in t["classes"]}
    for c in sorted({l.get("stream") for l in learners} - taken - {None}):
        out.append({"teacher_id": None, "name": None, "head": False, "classes": [c], "waiting_first_sign_in": False,
                    "last_login": None, "learners": sum(1 for l in learners if l.get("stream") == c)})
    return out


def add_teacher(session: str | None, name: str, member_no: str, stream: str) -> dict:
    """The head teacher makes a class teacher's login for one class. Returns the ONE-TIME PIN, shown once."""
    from . import family
    who = _head(session, "create a teacher account")
    if len(auth.teachers()) >= MAX_TEACHERS:
        raise ValueError(f"A school can have at most {MAX_TEACHERS} teacher accounts here.")
    name, member_no, stream = _check_account(name, member_no, stream, stream_required=True)
    pin = family._one_time_pin()
    auth.register(member_no, name, pin, must_change=True)
    store.save("assignments", {**_assignments(), member_no: {"role": "class_teacher", "streams": [stream], "subjects": []}})
    audit.write_event({"tool": "teacher.add", "actor": who["teacher_id"], "ok": True,
                       "inputs": {"kwargs": {"teacher_id": member_no, "class": stream}}, "output": {"added_by": who["name"]}})
    return {"teacher_id": member_no, "name": name, "class": stream, "one_time_pin": pin, "school": school_name(), "by": who["name"]}


def new_pin(session: str | None, teacher_id: str) -> dict:
    """A teacher forgot their PIN: the head teacher gives a new ONE-TIME PIN and ends their sign-ins."""
    from . import family
    who = _head(session, "give a teacher a new PIN")
    if auth.role_of(teacher_id) != "teacher":
        raise ValueError("That teacher is not on this computer.")
    if is_head(teacher_id):
        raise ValueError("Change your own PIN from My account. Nobody can reset the head teacher's PIN from here.")
    registry = auth._read(auth._path("teachers"), {})
    pin = family._one_time_pin()
    auth.register(teacher_id, registry.get(teacher_id, {}).get("name", ""), pin, must_change=True)
    auth.remove_sessions(teacher_id)
    audit.write_event({"tool": "teacher.new_pin", "actor": who["teacher_id"], "ok": True,
                       "inputs": {"kwargs": {"teacher_id": teacher_id}}, "output": {"by": who["name"]}})
    classes = school.streams_of(teacher_id)
    return {"teacher_id": teacher_id, "name": registry.get(teacher_id, {}).get("name", ""), "class": ", ".join(classes),
            "one_time_pin": pin, "school": school_name(), "by": who["name"]}


def remove_teacher(session: str | None, teacher_id: str) -> dict:
    """The head teacher removes a teacher's login. The class is free for someone else; its learners stay."""
    from . import whatsapp
    who = _head(session, "remove a teacher account")
    if auth.role_of(teacher_id) != "teacher":
        raise ValueError("That teacher is not on this computer.")
    if is_head(teacher_id):
        raise ValueError("The head teacher's account cannot be removed.")
    classes = school.streams_of(teacher_id)
    auth.remove(teacher_id)
    assignments = _assignments()
    assignments.pop(teacher_id, None)
    store.save("assignments", assignments)
    whatsapp.forget_number("teachers", teacher_id)
    audit.write_event({"tool": "teacher.remove", "actor": who["teacher_id"], "ok": True,
                       "inputs": {"kwargs": {"teacher_id": teacher_id, "class": classes}}, "output": {"removed_by": who["name"]}})
    return {"ok": True, "classes_now_without_teacher": classes}


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
