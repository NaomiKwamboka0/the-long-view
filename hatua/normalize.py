"""Clean messy CBC records and raise data-quality flags.

Hatua never silently "fixes" evidence. Each repair or doubt becomes a flag that the
teacher can see, and each flag points at the record it concerns.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from . import config

LEVEL_SPELLINGS = {
    "ee": "EE", "e.e": "EE", "e.e.": "EE", "exceeding expectations": "EE", "exceeding": "EE", "4": "EE",
    "me": "ME", "m.e": "ME", "m.e.": "ME", "meeting expectations": "ME", "meeting exp": "ME", "3": "ME",
    "ae": "AE", "a.e": "AE", "a.e.": "AE", "approaching expectations": "AE", "approaching": "AE", "2": "AE",
    "be": "BE", "b.e": "BE", "b.e.": "BE", "below expectations": "BE", "below expectation": "BE", "1": "BE",
}
_ID_RE = re.compile(r"^\s*ht[\s\-_]?0*(\d{1,4})\s*$", re.IGNORECASE)


def flag(kind: str, severity: str, message: str, record_id: str = "", learner_id: str = "") -> dict:
    return {"type": kind, "severity": severity, "message": message,
            "record_id": record_id, "learner_id": learner_id}


def learner_id(raw: str) -> str | None:
    m = _ID_RE.match(raw or "")
    return f"HT-{int(m.group(1)):04d}" if m else None


def area(raw: str) -> str | None:
    return config.AREA_ALIASES.get((raw or "").strip().lower())


def level(raw: str) -> str | None:
    return LEVEL_SPELLINGS.get((raw or "").strip().lower())


def level_from_score(score: float) -> str:
    for floor, lvl in config.SCORE_BANDS:
        if score >= floor:
            return lvl
    return "BE"


def parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def clean_record(row: dict, known_learners: set[str]) -> tuple[dict | None, list[dict]]:
    """Return (clean record or None if rejected, flags)."""
    rid = (row.get("record_id") or "").strip()
    flags: list[dict] = []
    lid = learner_id(row.get("learner_id", ""))
    if lid and lid != (row.get("learner_id") or "").strip():
        flags.append(flag("id_repaired", "info",
                          f"Learner ID '{row.get('learner_id')}' read as {lid}.", rid, lid))
    if not lid or lid not in known_learners:
        return None, [flag("unknown_learner", "reject",
                           f"Learner ID '{row.get('learner_id')}' is not on the class list. Record not used.",
                           rid, lid or "")]

    ar = area(row.get("learning_area", ""))
    if not ar:
        return None, flags + [flag("unknown_area", "reject",
                                   f"Learning area '{row.get('learning_area')}' not recognised. Record not used.",
                                   rid, lid)]
    if ar != (row.get("learning_area") or ""):
        flags.append(flag("area_repaired", "info",
                          f"Learning area '{row.get('learning_area')}' read as {ar}.", rid, lid))

    lvl = level(row.get("level", ""))
    score_raw = (row.get("score") or "").strip()
    score = float(score_raw) if re.fullmatch(r"\d+(\.\d+)?", score_raw) else None
    if lvl and (row.get("level") or "") != lvl:
        flags.append(flag("level_repaired", "info",
                          f"Rubric level '{row.get('level')}' read as {lvl}.", rid, lid))
    if not lvl and score is not None:
        lvl = level_from_score(score)
        flags.append(flag("level_from_score", "warn",
                          f"No rubric level recorded; {lvl} taken from score {score_raw}%. Check the original sheet.",
                          rid, lid))
    if not lvl:
        return None, flags + [flag("no_result", "reject", "No rubric level or score. Record not used.", rid, lid)]
    if score is not None and level_from_score(score) != lvl:
        flags.append(flag("score_level_conflict", "warn",
                          f"Recorded level {lvl} does not match score {score_raw}% "
                          f"(would be {level_from_score(score)}). Teacher's level kept.", rid, lid))

    task_d = parse_date(row.get("task_date", ""))
    logged_d = parse_date(row.get("logged_date", ""))
    if not task_d:
        flags.append(flag("bad_task_date", "warn", f"Task date '{row.get('task_date')}' unreadable.", rid, lid))
    elif task_d > config.today():
        flags.append(flag("future_task_date", "warn",
                          f"Task date {task_d} is in the future. Probably a typing error.", rid, lid))
    if not logged_d:
        flags.append(flag("missing_logged_date", "info", "No upload date recorded.", rid, lid))
    elif task_d and (logged_d - task_d).days > config.LATE_LOGGING_DAYS:
        flags.append(flag("late_logging", "warn",
                          f"Logged {(logged_d - task_d).days} days after the task.", rid, lid))

    grade, term = int(row["grade"]), int(row["term"])
    rec = {
        "record_id": rid, "learner_id": lid, "grade": grade, "year": int(row["year"]), "term": term,
        "ordinal": config.term_ordinal(grade, term), "learning_area": ar,
        "family": config.family_of(ar), "task": (row.get("task") or "").strip(),
        "level": lvl, "points": config.LEVEL_POINTS[lvl], "score": score,
        "task_date": task_d.isoformat() if task_d else None,
        "logged_date": logged_d.isoformat() if logged_d else None,
        "teacher": (row.get("teacher") or "").strip(), "source": (row.get("source") or "").strip(),
        "flags": [f["type"] for f in flags],
    }
    return rec, flags
