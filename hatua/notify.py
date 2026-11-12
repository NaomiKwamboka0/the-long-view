"""Notices for the class teacher: results files that are missing, and learners to watch.

Each kind goes only to the teacher who can act on it:

* missing_upload - a term's results are past due (Kenya's calendar: closing date plus
  the grace days in data/calendar) and no file for this class is in the term folder.
* waiting_approval - the file is in the folder but the class teacher has not approved it.
* file_removed - the results are in Hatua, but the file the teacher approved is no
  longer in the term folder (deleted or moved). The school has lost its copy.
* sharp_drop - in the newest term a learner fell two rubric levels or more in a learning
  area compared with the term before. ONE term is an early sign, not a pattern, and the
  notice says so. Sent at once, when the teacher approves the file.
* decline - the steady fall that Hatua's pattern rules report, now reaching this term.

Notices are deterministic rules, not model output. Nothing is sent outside this computer:
the teacher sees them when they sign in, and decides what to tell the parent.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import audit, config, drive, patterns, school, school_calendar, store
from .config import FAMILY_SW, LEVEL_NAMES, LEVEL_NAMES_SW

KIND_ORDER = {"sharp_drop": 0, "decline": 1, "missing_upload": 2, "file_removed": 3, "waiting_approval": 4}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _all() -> list[dict]:
    n = store.load("notices")
    return n if isinstance(n, list) else []


def _add(items: list[dict], notice: dict) -> dict | None:
    """Add a notice unless one with the same key exists. Returns the new notice or None."""
    if any(n["key"] == notice["key"] for n in items):
        return None
    last = max((int(n["notice_id"][3:]) for n in items), default=0)
    notice.update(notice_id=f"NT-{last + 1:05d}", created=_now(), read=False,
                  resolved=False, told_parent=None)
    items.append(notice)
    return notice


def _level(points: float) -> str:
    return config.LEVELS[max(0, min(3, int(points + 0.5) - 1))]


def _term_levels(learner_id: str) -> dict[str, dict[int, dict]]:
    """family -> ordinal -> {"points": mean points, "ids": record ids, "year", "term"}."""
    out: dict[str, dict[int, dict]] = {}
    for r in store.records_for(learner_id):
        slot = out.setdefault(r["family"], {}).setdefault(
            r["ordinal"], {"sum": 0, "n": 0, "ids": [], "grade": r["grade"], "year": r["year"], "term": r["term"]})
        slot["sum"] += r["points"]
        slot["n"] += 1
        slot["ids"].append(r["record_id"])
    for fam in out.values():
        for slot in fam.values():
            slot["points"] = slot["sum"] / slot["n"]
    return out


def learner_alerts(learner_id: str, ordinals: set[int]) -> list[dict]:
    """Sharp drops and declines that end in one of the given (newly added) terms."""
    who = store.learner(learner_id)
    teacher = school.teacher_for(learner_id)
    if not who or not teacher:
        return []
    found = []
    for fam, terms in _term_levels(learner_id).items():
        for o in sorted(set(terms) & ordinals):
            earlier = [p for p in terms if p < o]
            if not earlier:
                continue
            prev = terms[max(earlier)]
            now = terms[o]
            if now["points"] <= prev["points"] - 2:
                was, is_ = _level(prev["points"]), _level(now["points"])
                found.append({
                    "kind": "sharp_drop", "teacher_id": teacher, "learner_id": learner_id, "name": who["first_name"],
                    "family": fam, "grade": now["grade"], "year": now["year"], "term": now["term"],
                    "key": f"sharp_drop:{learner_id}:{fam}:{o}",
                    "title": f"{who['first_name']}: {fam} fell two levels this term",
                    "text": (f"{who['first_name']}'s {fam} went from {LEVEL_NAMES[was]} in Grade {prev['grade']} "
                             f"Term {prev['term']} to {LEVEL_NAMES[is_]} in Grade {now['grade']} Term {now['term']}. "
                             "This is one term, so it is an early sign, not a pattern yet. Check the records, "
                             "talk with the learner, and let the parent know."),
                    "evidence": prev["ids"][:4] + now["ids"][:4],
                    "parent": {"was": was, "is": is_}})
    for p in patterns.find(learner_id)["patterns"]:
        if p["type"] != "decline" or not p["current"]:
            continue
        last = [store.get_record(r) for r in (p.get("trail") or [{}])[-1].get("record_ids", [])]
        if not any(r and r["ordinal"] in ordinals for r in last):
            continue  # an older decline: it was reported when its own term arrived
        found.append({
            "kind": "decline", "teacher_id": teacher, "learner_id": learner_id, "name": who["first_name"],
            "family": p["family"],
            "key": f"decline:{learner_id}:{p['pattern_id']}",
            "title": f"{who['first_name']}: {p['family']} has gone down over several terms",
            "text": p["statement"] + " This is a pattern across terms. A good time to talk with the parent.",
            "evidence": p["evidence"][:8], "parent": None})
    return found


def after_ingest(inbox_file: str) -> list[dict]:
    """Alerts for the learners in a file that was just added. Called at approval time."""
    rows = [r for r in store.load("records") if r.get("file") == inbox_file]
    by_learner: dict[str, set[int]] = {}
    for r in rows:
        by_learner.setdefault(r["learner_id"], set()).add(r["ordinal"])
    items, new = _all(), []
    for lid, ords in sorted(by_learner.items()):
        for alert in learner_alerts(lid, ords):
            added = _add(items, alert)
            if added:
                new.append(added)
    store.save("notices", items)
    return new


def term_states(teacher_id: str, today=None, records: list | None = None) -> list[dict]:
    """Where each term of this year stands for one class teacher.

    state is one of:
      in_hatua      the results are in Hatua and the file is in the term folder
      file_removed  the results are in Hatua, but the file is no longer in the folder
      waiting       a file is in the folder and waits for this teacher's approval
      missing       results are due and no file is in the folder
      not_due       the term's results are not due yet
    """
    today = today or config.today()
    cal = school_calendar.load(today.year)
    learners = school.learners_of(teacher_id)
    if cal is None or not learners:
        return []
    mine = {l["learner_id"] for l in learners}
    records = store.load("records") if records is None else records
    have = {(r["year"], r["term"]) for r in records if r["learner_id"] in mine}
    by_label = {t["label"]: (f["grade"], t) for f in drive.folders(teacher_id, today.year) for t in f["terms"]}
    out = []
    for t in cal["terms"]:
        label = f"{cal['year']} Term {t['term']}"
        grade, folder = by_label.get(label, (None, {"files": [], "folder": label}))
        files = folder["files"]
        waiting = [f for f in files if f["status"] == "waiting"]
        usable = [f for f in files if f["status"] != "reject"]
        if (cal["year"], t["term"]) in have:
            state = "in_hatua" if usable else "file_removed"
        elif waiting:
            state = "waiting"
        else:
            state = "missing" if t["results_due"] <= today else "not_due"
        out.append({"year": cal["year"], "term": t["term"], "label": label, "state": state, "grade": grade,
                    "folder": folder["folder"], "closes": t["closes"], "due": t["results_due"],
                    "waiting": waiting, "files": len(files),
                    "approved": drive.approved_before(teacher_id, grade, label) if grade else None})
    return out


def _file_notice(teacher_id: str, st: dict) -> dict | None:
    """The notice a term's state calls for, or None when nothing is wrong."""
    stream = ", ".join(school.streams_of(teacher_id))
    term, label = st["term"], st["label"]
    when, closed = st["due"].strftime("%d %b %Y"), st["closes"].strftime("%d %b")
    base = {"teacher_id": teacher_id, "year": st["year"], "term": term, "evidence": [], "parent": None,
            "folder": st["folder"]}
    # In Kenya, school-based results from Grade 7 and Grade 8 go towards the Grade 9 result.
    counts = (" Grade 7 and Grade 8 school results count towards the Grade 9 result, so this file matters."
              if st.get("grade") in (7, 8) else "")
    if st["state"] == "waiting":
        return {**base, "kind": "waiting_approval", "key": f"waiting_approval:{teacher_id}:{label}",
                "title": f"Term {term} results are waiting for you to approve",
                "text": ((f"A results file for {stream} is in the folder '{st['folder']}'. It is not in Hatua until "
                          "you approve it." if len(st["waiting"]) == 1 else
                          f"{len(st['waiting'])} results files for {stream} are in the folder '{st['folder']}'. "
                          "They are not in Hatua until you approve them.")
                         + (f" Results were due on {when}." if st["due"] <= config.today() else "")),
                "path": st["waiting"][0]["path"]}
    if st["state"] == "missing":
        return {**base, "kind": "missing_upload", "key": f"missing_upload:{teacher_id}:{label}",
                "title": f"Term {term} results file for {stream} is missing",
                "text": (f"There is no results file for {stream} in the folder '{st['folder']}'. "
                         f"Term {term} closed on {closed} and results were due on {when}. "
                         "Upload the Excel file on the School drive tab, then approve it." + counts)}
    if st["state"] == "file_removed":
        was = st.get("approved")
        seen = (f" You approved '{was['file']}' on {datetime.fromisoformat(was['at']).strftime('%d %b %Y')}." if was else "")
        return {**base, "kind": "file_removed", "key": f"file_removed:{teacher_id}:{label}",
                "title": f"Term {term} results file for {stream} is gone from the school drive",
                "text": (f"The folder '{st['folder']}' has no results file now.{seen} "
                         f"The Term {term} results are still safe in Hatua, but the school has lost its copy. "
                         "Put the file back in the folder, or upload it again on the School drive tab.")}
    return None


FILE_KINDS = ("missing_upload", "waiting_approval", "file_removed")


def check_missing(today=None) -> list[dict]:
    """Tell each class teacher about a term whose results file is missing, waiting or gone.

    Runs when a teacher signs in, opens Today or the School drive, and after every
    approval, so a file deleted from the drive is noticed the next time the teacher
    looks. A notice closes by itself once its problem is fixed, and opens again if the
    problem comes back. Returns the notices that are new or re-opened.
    """
    today = today or config.today()
    items, new = _all(), []
    records = store.load("records")
    assignments = store.load("assignments")
    changed = False
    for teacher_id in sorted(assignments if isinstance(assignments, dict) else {}):
        for st in term_states(teacher_id, today, records):
            want = _file_notice(teacher_id, st)
            keys = {f"{k}:{teacher_id}:{st['label']}" for k in FILE_KINDS}
            for n in items:
                if n["key"] in keys and not n["resolved"] and (want is None or n["key"] != want["key"]):
                    n["resolved"] = True
                    changed = True
            if want is None:
                continue
            old = next((n for n in items if n["key"] == want["key"]), None)
            if old is None:
                added = _add(items, want)
                new.append(added)
            elif old["resolved"]:  # the same problem came back
                old.update(resolved=False, read=False, created=_now(), title=want["title"], text=want["text"])
                new.append(old)
            else:
                if old["text"] != want["text"]:
                    old.update(title=want["title"], text=want["text"])
                    changed = True
                continue
            changed = True
            audit.write_event({"tool": "notice.raise", "actor": "hatua", "ok": True,
                               "inputs": {"kwargs": {"teacher": teacher_id, "folder": st["folder"]}},
                               "output": {"kind": want["kind"], "term": st["term"]}})
    if changed:
        store.save("notices", items)
    return new


def for_teacher(teacher_id: str, include_resolved: bool = False) -> list[dict]:
    out = [n for n in _all() if n["teacher_id"] == teacher_id and (include_resolved or not n["resolved"])]
    return sorted(out, key=lambda n: (KIND_ORDER.get(n["kind"], 9), n["created"]), reverse=False)


def mark(notice_id: str, teacher_id: str, *, read: bool | None = None, told_parent: str | None = None) -> dict:
    items = _all()
    n = next((x for x in items if x["notice_id"] == notice_id and x["teacher_id"] == teacher_id), None)
    if n is None:
        raise ValueError("Notice not found.")
    if read is not None:
        n["read"] = read
    if told_parent is not None:
        n["told_parent"] = {"by": teacher_id, "at": _now(), "how": told_parent[:60]}
        n["read"] = True
    store.save("notices", items)
    return n


def parent_message(notice: dict, language: str = "en") -> str:
    """A short message the teacher can copy, edit and send. Hatua sends nothing."""
    who = store.learner(notice["learner_id"]) if notice.get("learner_id") else None
    if not who:
        return ""
    name, fam = who["first_name"], notice["family"]
    if language == "sw":
        area = FAMILY_SW.get(fam, fam)
        if notice["kind"] == "sharp_drop":
            was, is_ = LEVEL_NAMES_SW[notice["parent"]["was"]], LEVEL_NAMES_SW[notice["parent"]["is"]]
            change = f"matokeo ya {name} katika {area} yameshuka kutoka {was} hadi {is_} muhula huu"
        else:
            change = f"matokeo ya {name} katika {area} yamekuwa yakishuka kwa mihula kadhaa"
        return (f"Habari mzazi. Ningependa tuzungumze kuhusu {name}. Tumeona kwamba {change}. "
                f"Tumsaidie {name} pamoja. Tafadhali niambie wakati unaofaa tuongee. Asante.")
    if notice["kind"] == "sharp_drop":
        was, is_ = LEVEL_NAMES[notice["parent"]["was"]], LEVEL_NAMES[notice["parent"]["is"]]
        change = f"{name}'s results in {fam} went from {was} to {is_} this term"
    else:
        change = f"{name}'s results in {fam} have been going down over several terms"
    return (f"Hello. I would like to talk with you about {name}. We have noticed that {change}. "
            f"We would like to support {name} together. Please let me know a good time to talk. Thank you.")
