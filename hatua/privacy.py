"""The privacy notice everyone reads and ticks before Hatua opens for them the first time.

Each teacher and parent sees a short notice in plain English, written for their role, and
ticks that they agree. Hatua keeps who agreed, to which version, and when, in
store/consents.json, and writes it to the activity log. When the notice changes, VERSION
changes, and everyone is asked again at their next sign-in.

The portal refuses every page except this notice (and signing out) until the person agrees.
The full policy is PRIVACY.md.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import audit, store

VERSION = "2026-11-16"

_COMMON_END = [
    ("Your choices",
     "You can remove your WhatsApp number in My account at any time. To correct or delete anything else, "
     "talk to the school's Hatua admin. Kenya's Data Protection Act 2019 applies to all of this."),
]

NOTICE = {
    "teacher": {
        "title": "Before you start: how Hatua looks after your class's information",
        "sections": [
            ("What Hatua keeps",
             "Your class's results, days in school and your notes. They stay on this computer, in the school's "
             "Hatua folder. Hatua does not put them on the internet."),
            ("Who sees what",
             "You see only your own class. A parent sees only their own child, and only what you approve. "
             "Your private notes are never shown to parents."),
            ("You decide",
             "Results go into Hatua only when you approve the file. A report comment, a message to a parent, and "
             "senior school pathway ideas reach a family only when you choose."),
            ("WhatsApp",
             "Hatua never sends anything by itself. When you send a parent a WhatsApp message, it goes through "
             "WhatsApp with your own account. Hatua keeps a parent's number only if you tick that they agreed, and "
             "your own number only if you save it."),
            ("The AI helper",
             "Qwen runs on this computer. Your questions do not leave it, and the chat is not saved."),
            ("The activity log",
             "Hatua writes down sign-ins, approvals and messages with your name and the time, so the school can "
             "check what happened. It never writes down your PIN."),
        ] + _COMMON_END,
        "agree": "I have read this, and I agree to use Hatua this way.",
    },
    "parent": {
        "title": "Before you start: how Hatua looks after your child's information",
        "sections": [
            ("What you see",
             "Only your own child: results the class teacher approved, days in school, the teacher's comment and "
             "messages. You never see other children, and Hatua never ranks children."),
            ("Where it is kept",
             "On the school's computer, in the school's Hatua folder. Hatua does not put it on the internet."),
            ("WhatsApp",
             "If you message the class teacher, it goes through WhatsApp with your own account. Hatua does not keep "
             "your words, only that a message went. Hatua keeps your number only if you save it in My account, or "
             "if you agreed that the teacher saves it."),
            ("The AI helper",
             "It answers only about your own child, from the school's records. Your questions do not leave this "
             "computer, and the chat is not saved."),
            ("The activity log",
             "Hatua writes down when you sign in, so the school can check what happened. It never writes down "
             "your PIN."),
        ] + _COMMON_END,
        "agree": "I have read this, and I agree to use Hatua this way.",
    },
}


def _consents() -> dict:
    c = store.load("consents")
    return c if isinstance(c, dict) else {}


def accepted(person_id: str) -> bool:
    return (_consents().get(person_id) or {}).get("version") == VERSION


def notice(role: str) -> dict:
    n = NOTICE["parent" if role == "parent" else "teacher"]
    return {"version": VERSION, "title": n["title"], "agree": n["agree"],
            "sections": [{"heading": h, "text": t} for h, t in n["sections"]]}


def accept(person_id: str, role: str) -> dict:
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    c = _consents()
    c[person_id] = {"version": VERSION, "at": when, "role": role}
    store.save("consents", c)
    audit.write_event({"tool": "privacy.accept", "actor": person_id, "ok": True, "output": {"version": VERSION}})
    return {"ok": True, "version": VERSION, "at": when}
