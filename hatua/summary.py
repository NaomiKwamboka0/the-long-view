"""Draft plain-language summaries from cited patterns.

Drafts are written from templates by default, so every sentence is traceable and the
output is the same on every run. An optional local open-weights model (see llm.py)
can rewrite the wording; its output is only kept if it passes the same guard.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from . import config, guard, llm, patterns, store


class GateBlocked(Exception):
    """Raised when an action needs a named teacher's approval that does not exist yet."""


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cite(ids: list[str]) -> str:
    return "[" + ", ".join(ids) + "]"


def teacher_text(found: dict, learner: dict) -> str:
    name, lid = learner["first_name"], learner["learner_id"]
    lines = [
        f"Hatua draft for the class teacher: {name} ({lid}), Grade {learner['current_grade']} {learner['stream']}",
        f"Records reviewed: {found['records_reviewed']} assessment records, {found['span']}.",
        "",
        "What the records show:",
    ]
    if not found["patterns"]:
        lines.append("No pattern held across enough terms to report. This is not a judgement on the learner.")
    for p in found["patterns"]:
        lines.append(f"- {p['statement']} {_cite(p['evidence'])}")
        for n in p["notes"][:2]:
            if guard.labels_in(n["text"]):
                lines.append(f"- A teacher note from {n['term']} uses labelling or comparison words, "
                             f"so it is not quoted here. Open it to read it. {_cite([n['note_id']])}")
            else:
                lines.append(f"- Teacher note, {n['term']}: \"{n['text']}\" {_cite([n['note_id']])}")
    checks = [c for p in found["patterns"] for c in p["caveats"]]
    if found["record_notes"] or checks:
        lines += ["", "Check before relying on this:"]
        for rn in found["record_notes"]:
            lines.append(f"- {rn['statement']} {_cite(rn['evidence'][:8])}")
        for c in dict.fromkeys(checks):
            lines.append(f"  Note: {c}")
    lines += ["", "This is a draft for the class teacher to check. It is not a placement decision, "
                  "a label, or a comparison with any other learner."]
    return "\n".join(lines)


GUARDIAN_EN = {
    "sustained_strength": "{name} has done very well in {area} for {n} terms in a row.",
    "improvement": "{name} has improved in {area}, moving from {a} to {b}.",
    "decline": "{name}'s results in {area} have gone down, from {a} to {b}. The teacher would like to talk with you about how to support {name}.",
    "sustained_struggle": "{name} needs more support in {area}. The teacher would like to agree a plan with you.",
    "attendance_drop": "{name} has missed many school days over the last {n} terms. The teacher would like to talk with you about this.",
}
GUARDIAN_SW = {
    "sustained_strength": "{name} amefanya vizuri sana katika {area} kwa mihula {n} mfululizo.",
    "improvement": "{name} ameimarika katika {area}, kutoka {a} hadi {b}.",
    "decline": "Matokeo ya {name} katika {area} yameshuka, kutoka {a} hadi {b}. Mwalimu angependa kuzungumza nanyi kuhusu jinsi ya kumsaidia {name}.",
    "sustained_struggle": "{name} anahitaji msaada zaidi katika {area}. Mwalimu angependa kupanga pamoja nanyi jinsi ya kumsaidia.",
    "attendance_drop": "{name} amekosa siku nyingi za shule katika mihula {n} iliyopita. Mwalimu angependa kuzungumza nanyi kuhusu hili.",
}


def guardian_text(found: dict, learner: dict, keep: set[str], lang: str) -> str:
    name = learner["first_name"]
    sw = lang == "sw"
    tpl = GUARDIAN_SW if sw else GUARDIAN_EN
    names = config.LEVEL_NAMES_SW if sw else config.LEVEL_NAMES
    head = (f"Habari. Huu ni ujumbe mfupi kuhusu masomo ya {name}, ulioandaliwa na mwalimu wa darasa."
            if sw else f"Hello. This is a short update about {name}'s learning, prepared by the class teacher.")
    lines = [head, ""]
    for p in found["patterns"]:
        if p["pattern_id"] not in keep:
            continue
        area = config.FAMILY_SW.get(p["family"], p["family"]) if sw else p["family"]
        trail = p["trail"]
        line = tpl[p["type"]].format(name=name, area=area, n=p["terms"],
                                     a=names.get(trail[0]["level"], ""), b=names.get(trail[-1]["level"], ""))
        ref = "Rejea" if sw else "Ref"
        lines.append(f"- {line} ({ref}: {', '.join(p['evidence'][:4])})")
    lines += ["", ("Tafadhali wasiliana na mwalimu wa darasa ukiwa na swali lolote."
                   if sw else "Please contact the class teacher with any questions.")]
    return "\n".join(lines)


def draft(learner_id: str, audience: str = "teacher", language: str = "en") -> dict:
    learner = store.learner(learner_id)
    if not learner:
        raise ValueError(f"Unknown learner {learner_id}")
    if audience not in ("teacher", "guardian"):
        raise ValueError("audience must be 'teacher' or 'guardian'")
    found = patterns.find(learner_id)
    drafts: list[dict] = store.load("drafts")  # type: ignore[assignment]

    if audience == "teacher":
        text, keep = teacher_text(found, learner), [p["pattern_id"] for p in found["patterns"]]
    else:
        approved = [d for d in drafts if d["learner_id"] == learner_id and d["audience"] == "teacher"
                    and d["status"] == "approved"]
        if not approved:
            raise GateBlocked("A guardian summary needs the class teacher to approve the teacher draft first.")
        last = approved[-1]
        if last.get("final_text", last["text"]) != last["text"]:
            raise GateBlocked("The approved teacher draft was edited. A template family message could undo those edits; review a new teacher draft first.")
        if set(last["pattern_ids"]) != {p["pattern_id"] for p in found["patterns"]}:
            raise GateBlocked("The learner's patterns changed. Review a new teacher draft before preparing a family message.")
        keep = set(last["pattern_ids"]) - set(last.get("removed_pattern_ids", []))
        text = guardian_text(found, learner, keep, language)
        keep = sorted(keep)

    writer = "template"
    polished = llm.polish(text, language) if audience == "teacher" else None
    if polished and not guard.check(polished, learner_id) and set(guard.citations(polished)) == set(guard.citations(text)):
        text, writer = polished, llm.model_name()

    problems = guard.check(text, learner_id)
    if problems:
        raise ValueError("Draft failed safety checks: " + "; ".join(problems))
    # Re-use an identical pending draft; retire older pending drafts for the same audience.
    for old in drafts:
        if (old["learner_id"], old["audience"], old["language"]) == (learner_id, audience, language) \
                and old["status"] == "pending_teacher_review":
            if old["hash"] == text_hash(text):
                return old
            old["status"] = "superseded"
    d = {"draft_id": "D-" + uuid.uuid4().hex[:8], "learner_id": learner_id, "audience": audience,
         "language": language, "text": text, "hash": text_hash(text), "writer": writer,
         "pattern_ids": keep, "status": "pending_teacher_review",
         "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    drafts.append(d)
    store.save("drafts", drafts)
    return d
