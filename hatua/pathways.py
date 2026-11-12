"""Senior school pathway ideas, from the evidence, for the teacher to discuss.

Kenya's senior school has three pathways (Ministry of Education and KICD):

    STEM                     Pure Sciences, Applied Sciences, Technical and Engineering,
                             Career and Technical Studies
    Social Sciences          Languages and Literature, Humanities, Business Science
    Arts and Sports Science  Visual Arts, Performing Arts, Sports

The challenge brief allows "plain-language subject or career-direction suggestions" that
are "age-appropriate, never prescriptive", for "a teacher to raise with the learner and
their guardian". It disqualifies "an agent that assigns a track or label". So Hatua:

* shows, for EACH pathway in a fixed order, the cited strengths that relate to it - it
  never picks one, never orders pathways by fit, and never calls a child "a STEM learner";
* gives full ideas in Grade 9 (when learners choose), early "strengths to explore" in
  Grades 7 and 8, and nothing in Grades 4 to 6;
* keeps pathway ideas out of parent messages and report comments: the teacher raises
  them with the learner and family first.

The gate. The brief asks for a named human to approve "pathway suggestions before they
reach a teacher". So pathway ideas are CLOSED for every learner until the signed-in
class teacher opens them for that learner (`open_ideas`). Opening is a promise, shown
on the button: "I will raise these with the learner and guardian myself." The name and
time go in the audit log. Until then the portal sends no pathway ideas for that
learner and the assistant is not given them. An agent token cannot open them.

The mapping from junior school learning areas to pathways is Hatua's own assumption,
documented in docs/PORTAL.md, and a school can change PATHWAYS below.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import audit, auth, notify, patterns, scope, store
from .config import LEVEL_NAMES, LEVELS
from .summary import GateBlocked

PATHWAYS = [
    {"name": "STEM", "full": "Science, Technology, Engineering and Mathematics (STEM)",
     "tracks": "Pure Sciences, Applied Sciences, Technical and Engineering, Career and Technical Studies",
     "families": ["Mathematics", "Science", "Pre-Technical Studies", "Agriculture"]},
    {"name": "Social Sciences", "full": "Social Sciences",
     "tracks": "Languages and Literature, Humanities, Business Science",
     "families": ["English", "Kiswahili", "Social Studies"]},
    {"name": "Arts and Sports Science", "full": "Arts and Sports Science",
     "tracks": "Visual Arts, Performing Arts, Sports",
     "families": ["Creative Arts"]},
]
STRONG = {"sustained_strength", "improvement"}
TO_BUILD = {"decline", "sustained_struggle"}
CHOICE_NOTE = ("The learner chooses, with their family, using their interests, the KJSEA results, the school's "
               "career guidance and KNEC's aptitude tests. Hatua only shows what the records say.")


def stage(grade: int) -> str:
    return "suggest" if grade >= 9 else "explore" if grade >= 7 else "too_early"


def _latest(learner_id: str) -> dict[str, dict]:
    out = {}
    for fam, terms in notify._term_levels(learner_id).items():
        t = terms[max(terms)]
        out[fam] = {"level": LEVELS[max(0, min(3, int(t["points"] + 0.5) - 1))], "id": t["ids"][0],
                    "grade": t["grade"], "term": t["term"]}
    return out


def _short(p: dict) -> str:
    last = p["trail"][-1]["level"] if p.get("trail") else ""
    now = LEVEL_NAMES.get(last, last)
    return {"sustained_strength": f"{p['family']} held at {now} for {p['terms']} terms",
            "improvement": f"{p['family']} has gone up to {now}",
            "decline": f"{p['family']} has gone down to {now}",
            "sustained_struggle": f"{p['family']} at Approaching Expectations or below for {p['terms']} terms"}[p["type"]]


def for_learner(learner_id: str) -> dict:
    """Pathway ideas for one learner. Every statement carries its record numbers."""
    l = store.learner(learner_id)
    if not l:
        return {"stage": "unknown", "pathways": []}
    grade = int(l["current_grade"])
    st = stage(grade)
    if st == "too_early":
        return {"stage": st, "grade": grade, "pathways": [],
                "intro": (f"Senior school pathways are chosen in Grade 9. In Grade {grade}, Hatua shows "
                          f"{l['first_name']}'s strengths but does not suggest pathways.")}
    current = [p for p in patterns.find(learner_id)["patterns"] if p["current"]]
    latest = _latest(learner_id)
    out = []
    for pw in PATHWAYS:
        fams = pw["families"]
        strong = [p for p in current if p["family"] in fams and p["type"] in STRONG]
        build = [p for p in current if p["family"] in fams and p["type"] in TO_BUILD]
        named = {p["family"] for p in strong + build}
        steady = [(f, latest[f]) for f in fams if f in latest and f not in named and latest[f]["level"] in ("ME", "EE")]
        lines, evidence = [], []
        for p in strong:
            ids = p["evidence"][:4]
            lines.append({"kind": "strength", "text": _short(p), "evidence": ids})
            evidence += ids
        for f, x in steady:
            lines.append({"kind": "steady", "text": f"{f} at {LEVEL_NAMES[x['level']]} in the latest term",
                          "evidence": [x["id"]]})
            evidence.append(x["id"])
        for p in build:
            ids = p["evidence"][:4]
            lines.append({"kind": "to_build", "text": _short(p), "evidence": ids})
            evidence += ids
        if strong:
            summary = "The records show strengths in learning areas that lead to this pathway."
        elif steady:
            summary = "Results in some of this pathway's learning areas are at Meeting Expectations or above."
        else:
            summary = "The records do not show strengths in this pathway's learning areas yet."
        out.append({"name": pw["name"], "full": pw["full"], "tracks": pw["tracks"], "areas": fams,
                    "summary": summary, "lines": lines, "evidence": evidence,
                    "strengths": len(strong), "steady": len(steady)})
    if st == "suggest":
        intro = (f"Ideas for {l['first_name']}'s pathway conversation, from the records. Talk about all three with "
                 f"{l['first_name']} and the family, and ask what {l['first_name']} enjoys. " + CHOICE_NOTE)
    else:
        intro = (f"Early ideas only. {l['first_name']} chooses a pathway in Grade 9. These are strengths to explore "
                 "and keep building, not a choice. " + CHOICE_NOTE)
    return {"stage": st, "grade": grade, "intro": intro, "pathways": out}


def text(learner_id: str) -> str:
    """The same ideas as plain text with citations, for the assistant's context and answers."""
    info = for_learner(learner_id)
    if info["stage"] in ("too_early", "unknown"):
        return info.get("intro", "")
    parts = [info["intro"]]
    for pw in info["pathways"]:
        bits = [f"{x['text']} [{', '.join(x['evidence'])}]" + (" (to keep building)" if x["kind"] == "to_build" else "")
                for x in pw["lines"]]
        parts.append(f"- {pw['name']} ({pw['tracks']}): {pw['summary']}" + (" " + "; ".join(bits) + "." if bits else ""))
    return "\n".join(parts)


# ---------------------------------------------------------------- the named-teacher gate
def opened(teacher_id: str, learner_id: str) -> dict | None:
    """{"by": name, "at": time} if this teacher has opened this learner's pathway ideas."""
    gate = store.load("pathway_gate")
    return (gate.get(teacher_id) or {}).get(learner_id) if isinstance(gate, dict) else None


def opened_ids(teacher_id: str) -> set[str]:
    gate = store.load("pathway_gate")
    return set(gate.get(teacher_id) or {}) if isinstance(gate, dict) else set()


def open_ideas(session: str | None, learner_id: str) -> dict:
    """The signed-in class teacher opens one learner's pathway ideas. Logged with their name."""
    who = auth.resolve(session, kind="human", action="open pathway ideas")
    if not scope.can_view(who["teacher_id"], learner_id):
        raise GateBlocked("This learner is not in your class.")
    l = store.learner(learner_id)
    if stage(int(l["current_grade"])) == "too_early":
        raise GateBlocked("Pathway ideas start in Grade 7. There is nothing to open for this learner.")
    gate = store.load("pathway_gate")
    gate = gate if isinstance(gate, dict) else {}
    mine = gate.setdefault(who["teacher_id"], {})
    if learner_id not in mine:
        mine[learner_id] = {"by": who["name"], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        store.save("pathway_gate", gate)
        audit.write_event({"tool": "pathways.open", "actor": who["teacher_id"], "ok": True,
                           "inputs": {"kwargs": {"learner_id": learner_id}},
                           "output": {"approved_by": who["name"],
                                      "promise": "will raise these with the learner and guardian first"}})
    return mine[learner_id]


def for_teacher(teacher_id: str, learner_id: str) -> dict:
    """What the portal may show this teacher: the ideas if opened, else only that they are closed."""
    info = for_learner(learner_id)
    if info["stage"] in ("too_early", "unknown"):
        return info
    seen = opened(teacher_id, learner_id)
    if seen:
        return {**info, "opened": seen}
    return {"stage": info["stage"], "grade": info["grade"], "locked": True, "pathways": []}
