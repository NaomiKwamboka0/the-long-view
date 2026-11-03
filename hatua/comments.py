"""Report comments written by the local model (Qwen via Ollama), judged by the teacher.

The model only words the comment. The facts come from Hatua's pattern rules, so a
comment never says something the records do not show. Every comment is checked by the
guard (no labels, rankings, comparisons with classmates, or pathway advice) and kept
short. If Ollama is not running, or the model's text fails a check, a fixed template
writes the comment instead, and the page says which one wrote it.

The teacher gives each comment a thumbs up (use it) or a thumbs down with a reason
(too harsh, too vague, not accurate, too long). A thumbs down writes a new version that
takes the reason into account. Comments a teacher liked become style examples for
that teacher's next comments, so the wording moves towards how they write.

Nothing is sent outside this computer.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from . import auth, guard, patterns, scope, store
from .config import LEVEL_NAMES
from .local_model import local_host, open_local
from .summary import GateBlocked

REASONS = {
    "harsh": "It sounded too harsh. Be warmer and more encouraging, without hiding the facts.",
    "vague": "It was too vague. Name the learning areas and what the records show.",
    "inaccurate": "It did not match the records. Use only the facts given.",
    "long": "It was too long. Use at most two short sentences.",
    "formal": "It was too formal. Use simple, everyday English a parent will understand.",
}
MAX_CHARS = 480

PROMPT = """You write end-of-term report comments for learners in a Kenyan CBC school.
Write ONE comment of two or three short sentences, in plain, warm English that a parent
will understand. Mention one thing that is going well and one thing to work on, with a
small practical suggestion. Use the learner's first name.

Rules you must never break:
- Use only the facts below. Do not invent marks, events or reasons.
- No labels such as gifted, lazy, weak, bright or slow.
- Never compare the learner with classmates or the class. No ranks or positions.
- Never suggest a pathway, subject choice, track or career.
- Do not use record numbers.

Learner: {name}
Facts from the records:
{facts}
{style}{feedback}
Write only the comment, nothing else."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _all() -> list[dict]:
    c = store.load("comments")
    return c if isinstance(c, list) else []


def facts(learner_id: str) -> tuple[list[dict], list[str]]:
    """Facts for the comment as {kind, family, text}, and the record IDs behind them."""
    from . import notify  # the same one-term drop rule the teacher's notices use
    found = patterns.find(learner_id)
    out, evidence = [], []
    for p in found["patterns"]:
        if not p["current"]:
            continue
        last = p["trail"][-1]["level"] if p.get("trail") else ""
        level = LEVEL_NAMES.get(last, last)
        fam = p["family"] or "Attendance"
        text = {
            "sustained_strength": f"{fam}: has held {level} for {p['terms']} terms in a row.",
            "improvement": f"{fam}: results have gone up, now {level}.",
            "decline": f"{fam}: results have gone down over several terms, now {level}.",
            "sustained_struggle": f"{fam}: has been at Approaching Expectations or below for {p['terms']} terms.",
            "attendance_drop": "Attendance: has missed many school days in recent terms.",
        }.get(p["type"])
        if text:
            out.append({"kind": p["type"], "family": fam, "level": level, "terms": p.get("terms"), "text": text})
            evidence += p["evidence"][:4]
    latest = max((r["ordinal"] for r in store.records_for(learner_id)), default=None)
    for a in notify.learner_alerts(learner_id, {latest} if latest is not None else set()):
        if a["kind"] == "sharp_drop":
            was, now = LEVEL_NAMES[a["parent"]["was"]], LEVEL_NAMES[a["parent"]["is"]]
            out.insert(0, {"kind": "sharp_drop", "family": a["family"], "level": now, "terms": 1,
                           "text": f"{a['family']}: fell from {was} to {now} in the latest term (one term only)."})
            evidence = a["evidence"] + evidence
    order = {"sustained_strength": 0, "improvement": 1, "sharp_drop": 2, "decline": 3,
             "sustained_struggle": 4, "attendance_drop": 5}
    out.sort(key=lambda f: order.get(f["kind"], 9))
    if not out:
        out.append({"kind": "steady", "family": "", "level": "", "terms": 0,
                    "text": "No strong pattern yet: results have been steady."})
    return out[:5], evidence[:16]


def model_name() -> str | None:
    """The local model, if Ollama is running on this computer and has it. Else None."""
    if os.environ.get("HATUA_LLM", "").lower() in {"off", "0", "none"}:
        return None
    host = local_host()
    if not host:
        return None
    want = os.environ.get("HATUA_MODEL", "qwen2.5:7b")
    try:
        with open_local(f"{host}/api/tags", timeout=2) as r:
            names = {m["name"] for m in json.loads(r.read()).get("models", [])}
    except Exception:
        return None
    return want if (want in names or f"{want}:latest" in names) else None


def _ask_model(model: str, prompt: str) -> str | None:
    host = local_host()
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.5, "num_predict": 160}}).encode()
    try:
        import urllib.request
        req = urllib.request.Request(f"{host}/api/generate", data=body, headers={"Content-Type": "application/json"})
        with open_local(req, timeout=90) as resp:
            return json.loads(resp.read())["response"].strip().strip('"')
    except Exception:
        return None


def problems(text: str, name: str) -> list[str]:
    out = [f'uses "{w}"' for w in guard.labels_in(text)]
    if len(text) > MAX_CHARS:
        out.append("too long")
    if name.lower() not in text.lower():
        out.append("does not name the learner")
    if guard.citations(text) or re.search(r"\b[RNA]-\d", text):
        out.append("contains record numbers")
    return out


def _template(name: str, fact_list: list[dict], feedback: list[str]) -> str:
    """The comment Hatua writes when the model is off. Plain, warm and short."""
    good = [f for f in fact_list if f["kind"] in ("sustained_strength", "improvement")]
    work = [f for f in fact_list if f["kind"] in ("sharp_drop", "decline", "sustained_struggle", "attendance_drop")]
    short, soft = "long" in feedback, "harsh" in feedback
    parts = []
    if good:
        g = good[0]
        if g["kind"] == "sustained_strength" and not short:
            parts.append(f"{name} is doing very well in {g['family']}, at {g['level']} for {g['terms']} terms in a row.")
        elif g["kind"] == "improvement" and not short:
            parts.append(f"{name} has improved in {g['family']} and is now at {g['level']}.")
        else:
            parts.append(f"{name} is doing well in {g['family']}.")
    else:
        parts.append(f"{name} has kept working steadily this term.")
    if work:
        w = work[0]
        if w["kind"] == "attendance_drop":
            parts.append(f"Coming to school every day will help {name} keep up.")
        elif soft:
            parts.append(f"With a little practice at home each day, {name} can grow in {w['family']}.")
        elif w["kind"] == "sharp_drop":
            parts.append(f"{w['family']} was harder this term, so {name} will benefit from extra practice and support.")
        else:
            parts.append(f"{name} needs more support in {w['family']}; short daily practice at home will help.")
    if not short:
        parts.append(f"Let us keep encouraging {name} together.")
    return " ".join(parts)


def write(learner_id: str, teacher_id: str, feedback: list[str] | None = None, replaces: str | None = None) -> dict:
    """Write a new comment for a learner the teacher can see."""
    if not scope.can_view(teacher_id, learner_id):
        raise GateBlocked("You can only write comments for learners in your class.")
    who = store.learner(learner_id)
    name = who["first_name"]
    feedback = [f for f in (feedback or []) if f in REASONS]
    fact_lines, evidence = facts(learner_id)
    mine = [c for c in _all() if c["teacher_id"] == teacher_id]
    liked = [c["text"] for c in reversed(mine) if c.get("rating") == "up"][:3]
    style = ("\nComments this teacher liked before (copy the tone, not the facts):\n" +
             "\n".join(f"- {t}" for t in liked) + "\n") if liked else ""
    recent_down = [c for c in mine if c.get("rating") == "down"][-5:]  # the teacher's last five thumbs-downs
    past = {r for c in recent_down for r in c.get("reasons", [])}
    wanted = list(dict.fromkeys(feedback + sorted(past)))
    fb = ("\nThe teacher's feedback on earlier comments:\n" + "\n".join(f"- {REASONS[r]}" for r in wanted) + "\n"
          ) if wanted else ""
    model, text, writer = model_name(), None, "template"
    if model:
        prompt = PROMPT.format(name=name, facts="\n".join(f"- {f['text']}" for f in fact_lines),
                               style=style, feedback=fb)
        for _ in range(2):
            draft = _ask_model(model, prompt)
            if draft and not problems(draft, name):
                text, writer = draft, model
                break
    if text is None:
        text = _template(name, fact_lines, wanted)
    items = _all()
    comment = {"comment_id": f"C-{len(items) + 1:05d}", "learner_id": learner_id, "teacher_id": teacher_id,
               "text": text, "writer": writer, "facts": [f["text"] for f in fact_lines], "evidence": evidence,
               "feedback_used": wanted, "created": _now(), "rating": None, "reasons": [],
               "replaces": replaces}
    items.append(comment)
    store.save("comments", items)
    return comment


def rate(comment_id: str, session: str, rating: str, reasons: list[str] | None = None,
         note: str = "", edited_text: str | None = None) -> dict:
    """Thumbs up (use this comment) or thumbs down (write another, with these reasons)."""
    who = auth.resolve(session, kind="human", action="approve")
    if rating not in ("up", "down"):
        raise ValueError("Choose thumbs up or thumbs down.")
    items = _all()
    c = next((x for x in items if x["comment_id"] == comment_id), None)
    if c is None or c["teacher_id"] != who["teacher_id"] or not scope.can_view(who["teacher_id"], c["learner_id"]):
        raise GateBlocked("That comment is not one of yours.")
    if c["rating"] is not None:
        raise GateBlocked("This comment already has your rating.")
    reasons = [r for r in (reasons or []) if r in REASONS]
    if rating == "up" and edited_text is not None and edited_text.strip() != c["text"]:
        name = store.learner(c["learner_id"])["first_name"]
        issues = [p for p in problems(edited_text.strip(), name) if p != "does not name the learner"]
        if issues:
            raise ValueError("Your edit " + ", ".join(issues) + ". Please reword it.")
        c["teacher_edit"] = edited_text.strip()
    c.update(rating=rating, reasons=reasons, note=note.strip()[:200], rated_by=who["name"], rated_at=_now())
    store.save("comments", items)
    out = {"comment": c}
    if rating == "down":
        out["next"] = write(c["learner_id"], who["teacher_id"], feedback=reasons, replaces=comment_id)
    return out


def for_learner(learner_id: str, teacher_id: str) -> list[dict]:
    return [c for c in _all() if c["learner_id"] == learner_id and c["teacher_id"] == teacher_id]
