"""Who teaches which class, read from the assignments and the class list.

Visibility itself is decided only by hatua.scope (one rule, deny by default). This
module answers the questions around it: which stream and grade a teacher has, and
which teacher should hear about a learner.
"""
from __future__ import annotations

from . import auth, scope, store


def streams_of(teacher_id: str) -> list[str]:
    a = store.load("assignments")
    entry = a.get(teacher_id) if isinstance(a, dict) else None
    if not isinstance(entry, dict) or entry.get("role") != "class_teacher":
        return []
    return [s for s in entry.get("streams", []) if isinstance(s, str) and s]


def learners_of(teacher_id: str) -> list[dict]:
    """The teacher's current learners, in admission-number order. Never sorted by results."""
    ids = scope.visible_learner_ids(teacher_id)
    return sorted((l for l in store.load("learners") if l["learner_id"] in ids), key=lambda l: l["learner_id"])


def grades_of(teacher_id: str) -> set[int]:
    return {int(l["current_grade"]) for l in learners_of(teacher_id)}


def teacher_for(learner_id: str) -> str | None:
    """The class teacher who should be told about this learner, or None."""
    a = store.load("assignments")
    if not isinstance(a, dict):
        return None
    for teacher_id in sorted(a):
        if scope.can_view(teacher_id, learner_id):
            return teacher_id
    return None


def profile(teacher_id: str) -> dict:
    """What the portal shows about the signed-in teacher."""
    names = {t["teacher_id"]: t["name"] for t in auth.teachers()}
    grades = sorted(grades_of(teacher_id))
    return {"teacher_id": teacher_id, "name": names.get(teacher_id, teacher_id),
            "streams": streams_of(teacher_id), "grades": grades,
            "class_label": ", ".join(f"Grade {s}" for s in streams_of(teacher_id)),
            "learners": len(learners_of(teacher_id))}
