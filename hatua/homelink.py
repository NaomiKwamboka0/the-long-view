"""Parents at home, on their own phone: printed slips and a sealed phone link.

The portal runs on the school laptop and listens only on 127.0.0.1, so a parent at home
cannot reach it. This module lets the class teacher hand the child's page to the parent
without a server and without the records leaving the laptop in readable form:

1. Slips. The teacher prints parent slips for the whole class, or ticks the parents they
   want. A slip shows the parent number, a one-time PIN (only for a parent who has not
   signed in yet: PINs are never stored, so printing makes a new one), and the parent's
   HOME CODE: 8 letters and numbers, kept on this laptop so the teacher can send a new
   link next term without printing again.

2. The phone link. `link_data` returns the page a parent may see (only what the teacher
   approved, as in hatua.family) and the home code. The TEACHER'S BROWSER then seals it:
   AES-256-GCM with a key made from the home code (PBKDF2-SHA256, 310,000 rounds). The
   sealed page goes after the "#" of a link to the Hatua phone page
   (https://naomikwamboka0.github.io/the-long-view/home/). Browsers never send the part
   after "#" to the website, so the website never receives the child's page. The parent
   opens the link, types the home code from the slip, and the phone opens the page.

3. Sending. The teacher types the parent's phone number (or uses the saved one), ticks
   that they checked it, and WhatsApp opens with the link ready. The home code stays on
   the paper slip unless the teacher ticks "put the home code in the message too".

Every slip print and every link is written to the audit log with the teacher's name: a
link shares a child's page with a guardian, which cannot be undone.

What a phone link is not: it is a copy made on one day. It does not change when new
results are approved; the teacher sends a new link. Anyone who has both the link AND the
home code can open it, so the code should travel on paper, apart from the link.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

from . import audit, auth, family, school, school_calendar, scope, store, whatsapp
from .config import today
from .summary import GateBlocked

# Letters and numbers that cannot be mixed up when read from paper: no 0/O, 1/I/L.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 8  # 31^8 is about 8.5e11 codes; with 310,000 PBKDF2 rounds each guess is slow
ROUNDS = 310_000
HOME_URL = os.environ.get("HATUA_HOME_URL", "https://naomikwamboka0.github.io/the-long-view/home/")
MAX_SLIPS = 80


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _codes() -> dict:
    c = store.load("homecodes")
    return c if isinstance(c, dict) else {}


def _new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def pretty_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def code_for(parent_id: str, made_by: str, *, fresh: bool = False) -> str:
    """The parent's home code, made the first time it is needed. `fresh` replaces it."""
    codes = _codes()
    entry = codes.get(parent_id)
    if fresh or not isinstance(entry, dict) or not entry.get("code"):
        entry = {"code": _new_code(), "by": made_by, "at": _now()}
        codes[parent_id] = entry
        store.save("homecodes", codes)
    return entry["code"]


def forget(parent_id: str) -> None:
    """Called when a parent's account is deleted."""
    codes = _codes()
    if codes.pop(parent_id, None) is not None:
        store.save("homecodes", codes)


def _teacher(session: str | None, action: str) -> dict:
    who = auth.resolve(session, kind="human", action=action)
    if who.get("role", "teacher") != "teacher":
        raise GateBlocked("Only the class teacher can do this.")
    return who


# ---------------------------------------------------------------- the class's parents
def class_parents(teacher_id: str) -> list[dict]:
    """Every parent of every learner in this teacher's class, listed by admission number."""
    rows = []
    for l in sorted(school.learners_of(teacher_id), key=lambda x: x["learner_id"]):
        lid = l["learner_id"]
        parents = family.parents_of(lid)
        if not parents:
            rows.append({"learner_id": lid, "child": l["first_name"], "parent_id": None})
        for p in parents:
            digits = whatsapp.number_of("parents", p["parent_id"])
            rows.append({"learner_id": lid, "child": l["first_name"], "parent_id": p["parent_id"],
                         "name": p["name"], "relation": p["relation"],
                         "waiting_first_sign_in": p["waiting_first_sign_in"],
                         "whatsapp": whatsapp.pretty(digits) if digits else None,
                         "has_code": p["parent_id"] in _codes()})
    return rows


def _pairs_in_class(teacher_id: str, pairs: list) -> list[tuple[str, str]]:
    """Checks every (learner, parent) pair the page sent against this teacher's class."""
    allowed = {(r["learner_id"], r["parent_id"]) for r in class_parents(teacher_id) if r["parent_id"]}
    out = []
    for p in pairs:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError("That list of parents was not readable. Reload and try again.")
        pair = (str(p[0]), str(p[1]))
        if pair not in allowed:
            raise GateBlocked("One of those parents is not a parent in your class.")
        if pair not in out:
            out.append(pair)
    if not out:
        raise ValueError("Tick at least one parent first.")
    if len(out) > MAX_SLIPS:
        raise ValueError(f"Print at most {MAX_SLIPS} slips at a time.")
    return out


def slips(session: str | None, pairs: list) -> dict:
    """Slips for the ticked parents. A parent waiting for a first sign-in gets a new one-time PIN."""
    who = _teacher(session, "print parent slips")
    tid = who["teacher_id"]
    chosen = _pairs_in_class(tid, pairs)
    registry = auth._read(auth._path("teachers"), {})
    tname = who["name"]
    out, new_pins = [], []
    for lid, pid in chosen:
        acc = registry.get(pid, {})
        pin = None
        if acc.get("must_change"):
            pin = family._one_time_pin()
            auth.register(pid, acc.get("name", ""), pin, must_change=True, role="parent")
            auth.remove_sessions(pid)
            new_pins.append(pid)
        l = store.learner(lid) or {}
        out.append({"learner_id": lid, "child": l.get("first_name", ""), "grade": l.get("stream", ""),
                    "school": l.get("school", ""), "teacher": tname, "parent_id": pid, "name": acc.get("name", ""),
                    "relation": (family._links().get(pid) or {}).get("relation", ""), "one_time_pin": pin,
                    "home_code": pretty_code(code_for(pid, tname))})
    audit.write_event({"tool": "parent.slips", "actor": tid, "ok": True,
                       "inputs": {"kwargs": {"pairs": [list(p) for p in chosen]}},
                       "output": {"printed_by": tname, "slips": len(out), "new_one_time_pins": new_pins}})
    return {"slips": out, "home_url": HOME_URL}


# ---------------------------------------------------------------- the phone page
def page(learner_id: str) -> dict:
    """What the phone page shows: the same teacher-approved parts as the parent's own page,
    smaller. Every result keeps its record number, so every line on the phone is cited."""
    l = store.learner(learner_id)
    tid, tname = family._teacher_name(learner_id)
    view_latest = family._latest_levels(learner_id)
    approved = [c for c in (family.comments.for_learner(learner_id, tid) if tid else []) if c.get("rating") == "up"]
    told = [n for n in family.notify._all() if n.get("learner_id") == learner_id and n.get("told_parent")]
    att = sorted((a for a in store.load("attendance") if a["learner_id"] == learner_id), key=lambda a: a["ordinal"])
    pw = family._pathways_for_parent(learner_id, tid, tname)
    cal = school_calendar.summary(today())
    teacher_digits = whatsapp.number_of("teachers", tid) if tid else None
    return {
        "v": 1, "made": today().isoformat(), "child": l["first_name"], "grade": l["stream"],
        "school": l.get("school", ""), "teacher": tname, "teacher_whatsapp": teacher_digits,
        "latest": [{"area": r["family"], "level": r["level"], "when": f"Grade {r['grade']} Term {r['term']}",
                    "id": r["id"], "before": r["before"], "change": r["change"]} for r in view_latest],
        "days": [{"id": a["attendance_id"], "when": f"Grade {4 + a['ordinal'] // 3} Term {a['ordinal'] % 3 + 1}",
                  "present": a["days_present"], "open": a["days_open"]} for a in att[-3:]],
        "comment": ({"text": approved[-1].get("teacher_edit") or approved[-1]["text"],
                     "by": approved[-1].get("rated_by", ""), "at": approved[-1].get("rated_at", "")[:10]}
                    if approved else None),
        "messages": [{"at": n["told_parent"]["at"][:10], "en": family.notify.parent_message(n, "en"),
                      "sw": family.notify.parent_message(n, "sw")} for n in told][-5:],
        "pathways": ({"intro": pw.get("intro", ""), "by": (pw.get("opened") or {}).get("by", ""),
                      "ideas": [{"name": x["name"], "tracks": x["tracks"], "summary": x["summary"],
                                 "lines": [{"text": y["text"], "ids": y["evidence"][:2], "build": y["kind"] == "to_build"}
                                           for y in x["lines"]][:4]} for x in pw.get("pathways", [])]}
                     if pw.get("pathways") else {"intro": pw.get("intro", "")}),
        "now": cal.get("now", ""),
        "terms": cal.get("terms", []),
    }


def link_data(session: str | None, learner_id: str, parent_id: str) -> dict:
    """The named teacher approves sharing this child's page with this parent's phone."""
    who = _teacher(session, "send a parent a phone link")
    if not scope.can_view(who["teacher_id"], learner_id):
        raise GateBlocked("This learner is not in your class.")
    if not family.can_view(parent_id, learner_id):
        raise ValueError("That parent cannot see this learner.")
    data = page(learner_id)
    cited = [r["id"] for r in data["latest"]] + [d["id"] for d in data["days"]]
    code = code_for(parent_id, who["name"])
    audit.write_event({"tool": "parent.home_link", "actor": who["teacher_id"], "ok": True,
                       "inputs": {"kwargs": {"learner_id": learner_id, "parent_id": parent_id, "evidence": cited}},
                       "output": {"approved_by": who["name"], "made": data["made"],
                                  "comment_shared": data["comment"] is not None,
                                  "pathways_shared": "ideas" in data["pathways"]}})
    parent = (auth._read(auth._path("teachers"), {}).get(parent_id) or {}).get("name", "")
    saved = whatsapp.number_of("parents", parent_id)
    return {"page": data, "code": code, "pretty_code": pretty_code(code), "rounds": ROUNDS, "home_url": HOME_URL,
            "parent": parent, "whatsapp": whatsapp.pretty(saved) if saved else None}


def send(session: str | None, learner_id: str, parent_id: str, *, phone: str, checked, with_code: bool,
         save: bool) -> dict:
    """The teacher's last check before WhatsApp opens with the link. Returns the number to use."""
    who = _teacher(session, "send a parent a phone link")
    if not scope.can_view(who["teacher_id"], learner_id) or not family.can_view(parent_id, learner_id):
        raise GateBlocked("That parent is not a parent in your class.")
    if checked is not True:
        raise whatsapp.Refused("Tick the box to say you checked this number with the parent.")
    typed = str(phone or "").strip()
    digits = whatsapp.phone_digits(typed) if typed else whatsapp.number_of("parents", parent_id)
    if not digits:
        raise whatsapp.Refused("Type the parent's WhatsApp number.")
    saved = bool(save and typed)
    if saved:
        whatsapp.save_number("parents", parent_id, digits, who["teacher_id"])
    audit.write_event({"tool": "parent.home_link_sent", "actor": who["teacher_id"], "ok": True,
                       "inputs": {"kwargs": {"learner_id": learner_id, "parent_id": parent_id}},
                       "output": {"approved_by": who["name"], "to_ending": digits[-3:], "code_in_message": bool(with_code),
                                  "number_saved": saved, "sent_by_hatua": False}})
    return {"digits": digits, "to": whatsapp.pretty(digits)}
