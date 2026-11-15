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
that this is the right person and that they checked the message. That approval goes into the
audit log with the teacher's name, the message and its records, and the last three digits of
the number.

Saved numbers (store/contacts.json), so the teacher picks a person by name, not by number:

* A parent's number is saved only when the class teacher ticks that the parent agreed, or when
  the parent saves it in My account. A one-off number typed for one message is not kept.
* A teacher saves their own number in My account. Then the parents who can see one of that
  teacher's learners can press "Message the teacher". No one else sees it.
* Removing a parent's access deletes their saved number with their account.

Hatua cannot ask Safaricom or WhatsApp whose number it is: there is no free service for that.
The name comes from Hatua's own records, and WhatsApp itself shows the chat's name before Send.

Privacy note for the school: the message travels through WhatsApp, outside this computer.
Keep it short and send it only to a person who agreed to get WhatsApp messages.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote

from . import audit, family, guard, notify, patterns, scope, store
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


# ---------------------------------------------------------------- saved numbers
def _contacts() -> dict:
    c = store.load("contacts")
    return c if isinstance(c, dict) else {}


def number_of(kind: str, person_id: str) -> str | None:
    """The saved WhatsApp number (digits) of a parent ("parents") or teacher ("teachers"), or None."""
    return ((_contacts().get(kind) or {}).get(person_id) or {}).get("whatsapp")


def save_number(kind: str, person_id: str, digits: str, by: str) -> None:
    c = _contacts()
    c.setdefault(kind, {})[person_id] = {"whatsapp": digits, "by": by,
                                         "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    store.save("contacts", c)


def forget_number(kind: str, person_id: str) -> None:
    c = _contacts()
    if (c.get(kind) or {}).pop(person_id, None) is not None:
        store.save("contacts", c)


def my_number(person_id: str, role: str) -> dict:
    digits = number_of("parents" if role == "parent" else "teachers", person_id)
    return {"whatsapp": pretty(digits) if digits else None}


def set_my_number(person_id: str, role: str, phone: str, agreed: bool) -> dict:
    """A teacher or parent saves (or, with an empty number, removes) their own WhatsApp number."""
    kind = "parents" if role == "parent" else "teachers"
    if not str(phone or "").strip():
        forget_number(kind, person_id)
        audit.write_event({"tool": "whatsapp.number", "actor": person_id, "ok": True, "output": {"removed": True}})
        return my_number(person_id, role)
    if agreed is not True:
        raise Refused("Tick the box to agree that Hatua keeps your number on this computer.")
    digits = phone_digits(phone)
    save_number(kind, person_id, digits, person_id)
    audit.write_event({"tool": "whatsapp.number", "actor": person_id, "ok": True, "output": {"to_ending": digits[-3:]}})
    return my_number(person_id, role)


def recipients(learner_id: str) -> list[dict]:
    """The parents who can see this learner, by name, with their saved number if there is one."""
    out = []
    for p in family.parents_of(learner_id):
        digits = number_of("parents", p["parent_id"])
        out.append({"parent_id": p["parent_id"], "name": p["name"], "relation": p["relation"],
                    "whatsapp": pretty(digits) if digits else None})
    return out


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
            checked: bool, to: str = "", save: bool = False) -> dict:
    """The named teacher's approval to share. Returns the WhatsApp link, and logs the approval.

    `to` is a parent number (P-123456) from recipients(): their saved WhatsApp number is used
    unless the teacher typed another one. `save` keeps the typed number for that parent.
    Without `to`, the typed number is used once and not kept.
    """
    choice = next((o for o in options(teacher_id, learner_id) if o["key"] == key), None)
    if choice is None:
        raise Refused("That message is no longer open. Close this and start again.")
    if checked is not True:
        raise Refused("Tick the box to say this is the right person and you checked the message.")
    text = re.sub(r"[ \t]+\n", "\n", str(text or "")).strip()
    if len(text) < 10:
        raise Refused("The message is empty. Write a few words first.")
    if len(text) > MAX_CHARS:
        raise Refused(f"The message is too long for one WhatsApp note. Keep it under {MAX_CHARS} letters.")
    person = None
    if to:
        person = next((r for r in recipients(learner_id) if r["parent_id"] == to), None)
        if person is None:
            raise Refused("That parent cannot see this learner. Choose another person.")
        typed = str(phone or "").strip()
        digits = phone_digits(typed) if typed else number_of("parents", to)
        if not digits:
            raise Refused(f"Type {person['name']}'s WhatsApp number.")
    else:
        digits = phone_digits(phone)
    found = guard.labels_in(text)
    if found:
        raise Refused("Hatua cannot share this message. It must not rank or compare learners, and it must not "
                      f"give pathway or career advice. Please change: {', '.join(sorted(set(found))[:3])}.")
    saved = bool(person and save and str(phone or "").strip())
    if saved:
        save_number("parents", to, digits, teacher_id)
    audit.write_event({"tool": "parent.whatsapp", "actor": teacher_id, "ok": True,
                       "inputs": {"kwargs": {"learner_id": learner_id, "message": key, "evidence": choice["evidence"],
                                             "to_parent": to or None}},
                       "output": {"approved_by": teacher_name, "to_ending": digits[-3:], "text": text,
                                  "number_saved": saved, "sent_by_hatua": False}})
    return {"url": link(digits, text), "to": pretty(digits), "key": key,
            "name": person["name"] if person else None, "relation": person["relation"] if person else None}


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


# ---------------------------------------------------------------- a parent writes to the class teacher
def teacher_contact(parent_id: str, learner_id: str) -> dict:
    """Who the parent can message about this child, and whether that teacher shared a number."""
    if not family.can_view(parent_id, learner_id):
        raise Refused("You can only message the teacher of your own child.")
    tid, tname = family._teacher_name(learner_id)
    digits = number_of("teachers", tid) if tid else None
    return {"name": tname, "whatsapp": pretty(digits) if digits else None}


def to_teacher(parent_id: str, parent_name: str, learner_id: str, *, text: str, checked: bool) -> dict:
    """A parent's message to their child's class teacher. Returns the WhatsApp link."""
    contact = teacher_contact(parent_id, learner_id)
    tid, _ = family._teacher_name(learner_id)
    digits = number_of("teachers", tid) if tid else None
    if not digits:
        raise Refused(f"{contact['name']} has not added a WhatsApp number in Hatua yet. Talk to the school.")
    if checked is not True:
        raise Refused("Tick the box to say this is the right person and you checked the message.")
    text = re.sub(r"[ \t]+\n", "\n", str(text or "")).strip()
    if len(text) < 10:
        raise Refused("The message is empty. Write a few words first.")
    if len(text) > MAX_CHARS:
        raise Refused(f"The message is too long for one WhatsApp note. Keep it under {MAX_CHARS} letters.")
    # The parent's own words are theirs: Hatua logs that a message went, not what it said.
    audit.write_event({"tool": "teacher.whatsapp", "actor": parent_id, "ok": True,
                       "inputs": {"kwargs": {"learner_id": learner_id, "teacher_id": tid}},
                       "output": {"by": parent_name, "to_ending": digits[-3:], "chars": len(text), "sent_by_hatua": False}})
    return {"url": link(digits, text), "to": pretty(digits), "name": contact["name"]}


# ---------------------------------------------------------------- Qwen writes or changes the message
STYLES = {
    "write": "Write the message from the notes below. Keep every fact. Make it clear and kind.",
    "shorter": "Make it shorter: two or three short sentences. Keep the facts and the names.",
    "casual": "Make it more casual and friendly, like a WhatsApp message to someone you know. Keep the facts.",
    "formal": "Make it more formal and professional, like a note from a school. Keep the facts.",
    "warmer": "Make it warmer and more encouraging. Keep the facts.",
}
PROMPT = """You help {sender} write a WhatsApp message to {recipient} about {child}.
{style}
Rules: write only the message, nothing else. {language} Do not add any fact, number, score or
date that is not in the message. Keep the names. Never rank the child or compare them with other
children. Never suggest a career, pathway or school track. Under {limit} letters.

The message now:
{text}
"""
_CASUAL = [("Hello.", "Hi!"), ("Hello", "Hi"), ("I would like to", "I'd like to"), ("We would like to", "We'd like to"),
           ("We have noticed", "We've noticed"), ("Please let me know", "Let me know"), ("Thank you.", "Thanks!"),
           ("I am ", "I'm ")]
_FORMAL = [("Hi!", "Good day."), ("Hi ", "Good day "), ("Hello.", "Good day."), ("I'd", "I would"), ("We'd", "We would"),
           ("We've", "We have"), ("I'm", "I am"), ("Let me know", "Please let me know"), ("Thanks!", "Thank you."),
           ("Thanks", "Thank you")]


_FILLER = re.compile(r"^(I would like to talk|I'd like to talk|We would like to support|We'd like to support|"
                     r"I hope you|Please tell .* well done|Nimefurahi|Ningependa tuzungumze|Tumsaidie)", re.I)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def _by_rule(text: str, style: str, sender: str) -> str:
    """When Qwen is not running: simple, safe word rules that never add a fact."""
    if style == "shorter":  # drop the polite filler, keep the greeting, the facts and the thanks
        s = _sentences(text)
        kept = [x for i, x in enumerate(s) if i in (0, len(s) - 1) or not _FILLER.search(x)]
        return " ".join(kept)
    if style == "casual":
        for a, b in _CASUAL:
            text = text.replace(a, b)
        return text
    if style == "formal":
        for a, b in _FORMAL:
            text = text.replace(a, b)
        return text if sender.split()[0] in text[-60:] else f"{text}\n\nKind regards,\n{sender}"
    if style == "warmer":
        s = _sentences(text)
        if s and "hope you are well" not in text.lower():
            s.insert(1, "I hope you and the family are well.")
        return " ".join(s)
    return text


def rewrite(text: str, style: str, *, sender: str, recipient: str, child: str, check: bool) -> dict:
    """Qwen writes or changes the message in the chosen style. Returns {"text", "writer"}.

    The person still reads it, can change any word, and presses Send in WhatsApp themselves.
    `check` runs the no-ranking, no-pathway guard on the new words (always on for teachers).
    """
    from . import comments  # the same local Qwen the report comments use
    if style not in STYLES:
        raise Refused("Choose how to change the message.")
    text = str(text or "").strip()[:MAX_CHARS]
    if len(text) < 3:
        raise Refused("Write a few words first, then I can help.")
    swahili = sum(w in text.lower().split() for w in ("habari", "mzazi", "asante", "tafadhali", "na", "ya", "wa"))
    language = "Write in Kiswahili." if swahili >= 3 else "Write in simple English."
    model = comments.model_name()
    if model:
        out = comments._ask_model(model, PROMPT.format(sender=sender, recipient=recipient, child=child,
                                                      style=STYLES[style], language=language, limit=MAX_CHARS - 100,
                                                      text=text))
        if out and len(out) <= MAX_CHARS and not (check and guard.labels_in(out)):
            return {"text": out.strip(), "writer": model}
    if style == "write":
        return {"text": text, "writer": "none",
                "note": "Qwen is not running on this computer, so your words are kept as they are."}
    return {"text": _by_rule(text, style, sender), "writer": "rules"}
