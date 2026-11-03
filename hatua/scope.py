"""The single scope rule for the teacher portal and the scoped agent.

Policy: a class teacher sees the full Grades 4-9 history of the learners
currently in their class, including records entered by earlier teachers. A
teacher with no assignment, or with a role other than class_teacher, sees
nothing; there is no admin or head-teacher role in this phase. This is a
data-protection decision for the school to confirm (plan H1); do not widen
it here.

This module reads only through hatua.store. It performs no I/O and keeps no
cache, so every call reflects the store as it is at that moment. It does not
check the teacher registry: assignments, not credentials, decide scope.
"""
from __future__ import annotations

from . import store


def visible_learner_ids(teacher_id: str) -> set[str]:
    """Return the learner IDs whose CURRENT stream is assigned to the teacher.

    Deny by default: an unknown teacher, a non-class_teacher role, a malformed
    assignment, or no streams all return an empty set. A learner is included
    only when the loaded class list places them in one of the teacher's
    streams; a learner who is not in the loaded class list is never included.
    """
    assignments = store.load("assignments")
    if not isinstance(assignments, dict):
        return set()
    assignment = assignments.get(teacher_id)
    if not isinstance(assignment, dict) or assignment.get("role") != "class_teacher":
        return set()

    streams = assignment.get("streams")
    if not isinstance(streams, list):
        return set()
    allowed = {token.strip() for token in streams if isinstance(token, str) and token.strip()}
    if not allowed:
        return set()

    learners = store.load("learners")
    if not isinstance(learners, list):
        return set()
    visible: set[str] = set()
    for learner in learners:
        if not isinstance(learner, dict):
            continue
        learner_id = learner.get("learner_id")
        stream = learner.get("stream")
        if (isinstance(learner_id, str) and learner_id
                and isinstance(stream, str) and stream.strip() in allowed):
            visible.add(learner_id)
    return visible


def can_view(teacher_id: str, learner_id: str) -> bool:
    """Return whether this teacher may see this learner.

    This is the one visibility decision for every portal endpoint and scoped
    MCP tool; do not add another. It is exactly membership in
    visible_learner_ids, with the same deny-by-default behaviour.
    """
    return learner_id in visible_learner_ids(teacher_id)
