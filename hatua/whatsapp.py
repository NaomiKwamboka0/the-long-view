"""A free WhatsApp message from the class teacher to a parent.

Hatua does not send anything itself and uses no paid service. It does three things:

1. Drafts a short message from the learner's records: good news (a result going up, a
   strength that held) or a concern (the notices in hatua.notify). Every draft names the
   records it stands on.
2. Checks the teacher's final words with the same guard as every other draft: no ranking,
   no comparison with classmates, no pathway or career advice.
3. Builds a normal "click to chat" link (https://wa.me/<number>?text=<message>). The
   teacher presses it, WhatsApp opens with the message ready, and the teacher presses Send
   in WhatsApp with their own account.

Sharing with a guardian cannot be undone, so it needs a signed-in class teacher who ticks
that they checked the message and the number. That approval goes into the audit log with
the teacher's name, the message and its records. The parent's number is NOT kept: only its
last three digits are logged, so a wrong number can be traced without storing a contact.

Privacy note for the school: the message travels through WhatsApp, outside this computer.
Keep it short and send it only to a parent who agreed to get WhatsApp messages.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from . import audit, guard, notify, patterns, scope, store
from .config import FAMILY_SW, LEVEL_NAMES, LEVEL_NAMES_SW

MAX_CHARS = 700
GOOD = ("improvement", "sustained_strength")


class Refused(ValueError):
    """The message may not be shared as it is. The text says why, in plain words."""


def phone_digits(raw: str) -> str:
    """A WhatsApp number as digits with the country code. Kenyan numbers may start with 0.

    0712 345 678, 712345678, +254 712 345 678 and 254712345678 all give 254712345678.
    A number from another country needs its + and country code.
    """
    text = str(raw or "").strip()
    plus = text.startswith("+")
    digits = re.sub(r"[\s\-().]", "", text.lstrip("+"))
    if not digits.isdigit():
        raise Refused("Type the parent's WhatsApp number using numbers only, for example 0712 345 678.")
    if not plus:
        if len(digits) == 10 and digits[0] == "0" and digits[1] in "17":
            digits = "254" + digits[1:]
        elif len(digits) == 9 and digits[0] in "17":
            digits = "254" + digits
        elif not (len(digits) == 12 and digits.startswith("254")):
            raise Refused("That does not look like a Kenyan mobile number. Use 07.. or 01.. with 10 digits, "
                          "or start with + and the country code.")
    if not 8 <= len(digits) <= 15:
        raise Refused("That number is too short or too long. Check it and type it again.")
    return digits


def pretty(digits: str) -> str:
    if len(digits) == 12 and digits.startswith("254"):
        return f"+254 {digits[3:6]} {digits[6:9]} {digits[9:]}"
    return "+" + digits


def _good_news(learner_id: str, name: str) -> list[dict]:
    out = []
    for p in patterns.find(learner_id)["patterns"]:
        if p["type"] not in GOOD or not p.get("current") or not p.get("family"):
            continue
        fam, n = p["family"], p["terms"]
        first, last = p["trail"][0]["level"], p["trail"][-1]["level"]
        area = FAMILY_SW.get(fam, fam)
        if p["type"] == "improvement":
            en = (f"{name}'s results in {fam} have gone up over the last {n} terms, from "
                  f"{LEVEL_NAMES.get(first, first)} to {LEVEL_NAMES.get(last, last)}")
            sw = (f"matokeo ya {name} katika {area} yamepanda kwa mihula {n} iliyopita, kutoka "
                  f"{LEVEL_NAMES_SW.get(first, first)} hadi {LEVEL_NAMES_SW.get(last, last)}")
            label = f"Good news: {fam} is going up"
        else:
            en = f"{name} has kept {LEVEL_NAMES.get(last, last)} in {fam} for {n} terms"
            sw = f"{name} amedumisha {LEVEL_NAMES_SW.get(last, last)} katika {area} kwa mihula {n}"
            label = f"Good news: {fam} is a held strength"
        out.append({
            "key": "pattern:" + p["pattern_id"], "tone": "good", "label": label, "evidence": p["evidence"][:8],
            "en": f"Hello. I have good news about {name}. {en}. Please tell {name} well done. Thank you.",
            "sw": f"Habari mzazi. Nina habari njema kuhusu {name}. Tumeona kwamba {sw}. "
                  f"Tafadhali mpongeze {name}. Asante."})
    return out


def options(teacher_id: str, learner_id: str) -> list[dict]:
    """The messages this teacher can send about this learner: concerns first, then good news."""
    if not scope.can_view(teacher_id, learner_id):
        raise Refused("This learner is not in your class.")
    who = store.learner(learner_id)
    name = who["first_name"]
    out = []
    for n in notify.for_teacher(teacher_id):
        if n.get("learner_id") != learner_id or n.get("told_parent"):
            continue
        out.append({"key": "notice:" + n["notice_id"], "tone": "concern", "evidence": n.get("evidence", [])[:8],
                    "label": f"To talk about: {n['family']} " + ("fell this term" if n["kind"] == "sharp_drop"
                                                                 else "has gone down over several terms"),
                    "en": notify.parent_message(n, "en"), "sw": notify.parent_message(n, "sw")})
    out += _good_news(learner_id, name)
    out.append({"key": "own", "tone": "own", "label": "My own words", "evidence": [],
                "en": f"Hello. I am {name}'s class teacher. ", "sw": f"Habari mzazi. Mimi ni mwalimu wa darasa wa {name}. "})
    return out


def link(digits: str, text: str) -> str:
    return f"https://wa.me/{digits}?text={quote(text, safe='')}"


def prepare(teacher_id: str, teacher_name: str, learner_id: str, *, phone: str, text: str, key: str,
            checked: bool) -> dict:
    """The named teacher's approval to share. Returns the WhatsApp link, and logs the approval."""
    choice = next((o for o in options(teacher_id, learner_id) if o["key"] == key), None)
    if choice is None:
        raise Refused("That message is no longer open. Close this and start again.")
    if checked is not True:
        raise Refused("Tick the box to say you checked the message and the number.")
    text = re.sub(r"[ \t]+\n", "\n", str(text or "")).strip()
    if len(text) < 10:
        raise Refused("The message is empty. Write a few words first.")
    if len(text) > MAX_CHARS:
        raise Refused(f"The message is too long for one WhatsApp note. Keep it under {MAX_CHARS} letters.")
    digits = phone_digits(phone)
    found = guard.labels_in(text)
    if found:
        raise Refused("Hatua cannot share this message. It must not rank or compare learners, and it must not "
                      f"give pathway or career advice. Please change: {', '.join(sorted(set(found))[:3])}.")
    audit.write_event({"tool": "parent.whatsapp", "actor": teacher_id, "ok": True,
                       "inputs": {"kwargs": {"learner_id": learner_id, "message": key, "evidence": choice["evidence"]}},
                       "output": {"approved_by": teacher_name, "to_ending": digits[-3:], "text": text,
                                  "sent_by_hatua": False}})
    return {"url": link(digits, text), "to": pretty(digits), "key": key}


def sent(teacher_id: str, teacher_name: str, learner_id: str, key: str) -> dict:
    """The teacher says they pressed Send in WhatsApp. Marks the learner's open notices as told."""
    if not scope.can_view(teacher_id, learner_id):
        raise Refused("This learner is not in your class.")
    marked = []
    if key.startswith("notice:"):
        for n in notify.for_teacher(teacher_id):
            if n.get("learner_id") == learner_id and not n.get("told_parent"):
                marked.append(notify.mark(n["notice_id"], teacher_id, told_parent="By WhatsApp")["notice_id"])
    audit.write_event({"tool": "parent.told", "actor": teacher_id, "ok": True,
                       "inputs": {"kwargs": {"learner_id": learner_id, "message": key}},
                       "output": {"how": "By WhatsApp", "recorded_by": teacher_name, "notices": marked}})
    return {"ok": True, "notices": marked}
