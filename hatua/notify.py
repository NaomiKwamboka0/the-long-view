"""Notices for the class teacher: results that are overdue, and learners to watch.

Three kinds, each sent only to the teacher who can act on it:

* missing_upload - a term's results are past due (Kenya's calendar: closing date plus
  the grace days in data/calendar) and nothing for this class is on the drive.
* waiting_approval - the file is on the drive but the class teacher has not approved it.
* sharp_drop - in the newest term a learner fell two rubric levels or more in a learning
  area compared with the term before. ONE term is an early sign, not a pattern, and the
  notice says so. Sent at once, when the teacher approves the file.
* decline - the steady fall that Hatua's pattern rules report, now reaching this term.

Notices are deterministic rules, not model output. Nothing is sent outside this computer:
the teacher sees them when they sign in, and decides what to tell the parent.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import config, drive, patterns, school, school_calendar, store
from .config import FAMILY_SW, LEVEL_NAMES, LEVEL_NAMES_SW

KIND_ORDER = {"sharp_drop": 0, "decline": 1, "missing_upload": 2, "waiting_approval": 3}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _all() -> list[dict]:
    n = store.load("notices")
    return n if isinstance(n, list) else []


def _add(items: list[dict], notice: dict) -> dict | None:
    """Add a notice unless one with the same key exists. Returns the new notice or None."""
    if any(n["key"] == notice["key"] for n in items):
        return None
    notice.update(notice_id=f"NT-{len(items) + 1:05d}", created=_now(), read=False,
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


def check_missing(today=None) -> list[dict]:
    """Tell each class teacher about term results that are due but not in Hatua.

    Also marks old missing/waiting notices resolved once the results are in.
    """
    today = today or config.today()
    items, new = _all(), []
    records = store.load("records")
    have = {(r["learner_id"], r["year"], r["term"]) for r in records}
    assignments = store.load("assignments")
    for teacher_id in sorted(assignments if isinstance(assignments, dict) else {}):
        learners = school.learners_of(teacher_id)
        if not learners:
            continue
        files = {(t["label"]): t["files"] for f in drive.folders(teacher_id) for t in f["terms"]}
        for due in school_calendar.due_terms(today):
            label = f"{due['year']} Term {due['term']}"
            done = any((l["learner_id"], due["year"], due["term"]) in have for l in learners)
            key_m = f"missing_upload:{teacher_id}:{label}"
            key_w = f"waiting_approval:{teacher_id}:{label}"
            if done:
                for n in items:
                    if n["key"] in (key_m, key_w) and not n["resolved"]:
                        n["resolved"] = True
                continue
            waiting = [f for f in files.get(label, []) if f["status"] == "waiting"]
            stream = ", ".join(school.streams_of(teacher_id))
            when = due["due"].strftime("%d %b %Y")
            closed = due["closes"].strftime("%d %b")
            if waiting:
                notice = {"kind": "waiting_approval", "teacher_id": teacher_id, "key": key_w,
                          "year": due["year"], "term": due["term"],
                          "title": f"Term {due['term']} results are waiting for your approval",
                          "text": (f"{len(waiting)} file(s) for {stream} are on the school drive in "
                                   f"'{label}'. They are not in Hatua until you approve them. "
                                   f"Results were due on {when}."),
                          "evidence": [], "parent": None, "path": waiting[0]["path"]}
            else:
                notice = {"kind": "missing_upload", "teacher_id": teacher_id, "key": key_m,
                          "year": due["year"], "term": due["term"],
                          "title": f"Term {due['term']} results for {stream} have not been uploaded",
                          "text": (f"Term {due['term']} closed on {closed}, and results were due on {when}. "
                                   f"Nothing for {stream} is in the '{label}' folder yet. Upload the CSV "
                                   "on the School drive tab, then approve it."),
                          "evidence": [], "parent": None}
            added = _add(items, notice)
            if added:
                new.append(added)
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
