"""Optional teacher sign-in for the approval gate. Off by default.

    HATUA_REQUIRE_AUTH=1 python -m hatua agent

A typed name proves nothing: anyone can type any name. When sign-in is on, a teacher
registers once on this computer with an ID, a name and a PIN, and the approval entry
then carries the registered name and the teacher ID instead of whatever was typed.

What this does and does not do:
* It identifies a person among the teachers registered on this one computer.
* It is not TSC or KEMIS single sign-on, and it is not a claim about who someone is.
* Anyone who can edit the files under store/ and logs/ can still forge an entry.

Two kinds of token share the session store, and `resolve` refuses the wrong kind for a
job rather than treating them as equal:

* `human` - created by login. It slides by 15 minutes on each authenticated request, up
  to an absolute 8 hours after sign-in, and it is the only kind that may approve or save.
* `agent` - minted from a human session for one agent run. It lasts at most 30 minutes,
  stops working as soon as the human session that minted it ends (idle expiry, the
  8-hour limit, or `logout`), and can read and draft but never approve, save or mint
  another token.

Only the SHA-256 of a token - or of a session's CSRF value - is stored, never the value
itself.

One writer at a time is assumed, exactly as in hatua/audit.py: two processes rewriting
store/sessions.json at once can lose each other's changes, and every writer uses the
same temporary file name. One local portal on one computer is the intended deployment.

Standard library only. Nothing here makes a network call.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .summary import GateBlocked

TEACHER_ID = config.TEACHER_ID  # one rule, shared with the assignment loader in store.py
MIN_NAME = 3
MIN_PIN = 6
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
SESSION_MINUTES = 15   # a human session slides by this much on each authenticated request
SESSION_MAX_HOURS = 8  # ... but never further than this after sign-in
AGENT_MINUTES = 30     # an agent token is minted for one run and does not slide
LOCK_FAILURES = 5
LOCK_MINUTES = 15

# A fixed salt used to hash a PIN for an unknown teacher ID, so a failed sign-in takes
# about the same time whether or not the ID exists.
_DUMMY_SALT = bytes(16)


def _path(name: str) -> Path:
    return config.STORE / f"{name}.json"


def _now() -> datetime:
    """Patchable clock, so tests can expire a session without waiting."""
    return datetime.now(timezone.utc)


def _read(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return dict(default)
    return data if isinstance(data, dict) else dict(default)


def _write(path: Path, data: dict) -> None:
    """Write atomically, and make the file owner-only where the platform allows it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass  # Windows has no meaningful chmod; the folder permissions are the control
    tmp.replace(path)


def _hash(pin: str, salt: bytes) -> str:
    return hashlib.scrypt(pin.encode("utf-8"), salt=salt, **SCRYPT).hex()


def _burn_time(pin: str) -> None:
    """One hash for an unknown teacher ID. The result is compared and thrown away."""
    hmac.compare_digest(_hash(pin, _DUMMY_SALT), "0" * (2 * SCRYPT["dklen"]))


def _fail_message() -> str:
    return "Sign-in failed. Check the teacher ID and the PIN."


# ---------------------------------------------------------------- registry
def register(teacher_id: str, name: str, pin: str) -> dict:
    """Add or update one teacher on this computer. Returns {teacher_id, name}."""
    teacher_id = (teacher_id or "").strip()
    name = (name or "").strip()
    if not TEACHER_ID.match(teacher_id):
        raise ValueError("Teacher ID must be 3 to 24 letters, digits, '-' or '_'.")
    if len(name) < MIN_NAME:
        raise ValueError(f"Enter the teacher's full name ({MIN_NAME} characters or more).")
    if len(pin or "") < MIN_PIN:
        raise ValueError(f"The PIN must be at least {MIN_PIN} characters.")
    salt = secrets.token_bytes(16)
    teachers = _read(_path("teachers"), {})
    teachers[teacher_id] = {"name": name, "salt": salt.hex(), "hash": _hash(pin, salt),
                            "registered": _now().isoformat(timespec="seconds")}
    _write(_path("teachers"), teachers)
    return {"teacher_id": teacher_id, "name": name}


def teachers() -> list[dict]:
    """The registry without any PIN material."""
    return [{"teacher_id": tid, "name": t.get("name", "")}
            for tid, t in sorted(_read(_path("teachers"), {}).items())]


# ---------------------------------------------------------------- sign-in
def _lock_until(state: dict, teacher_id: str) -> datetime | None:
    raw = (state.get(teacher_id) or {}).get("locked_until")
    if not raw:
        return None
    try:
        until = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return until if until > _now() else None


def _record_failure(state: dict, teacher_id: str) -> None:
    entry = state.get(teacher_id) or {"failures": 0}
    entry["failures"] = int(entry.get("failures", 0)) + 1
    if entry["failures"] >= LOCK_FAILURES:
        entry["locked_until"] = (_now() + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds")
        entry["failures"] = 0
    state[teacher_id] = entry


def login(teacher_id: str, pin: str) -> dict:
    """Check a PIN and return {session, teacher_id, name}. Raises GateBlocked on failure."""
    teacher_id = (teacher_id or "").strip()
    pin = pin or ""
    registry = _read(_path("teachers"), {})
    state = _read(_path("auth_state"), {})

    until = _lock_until(state, teacher_id)
    if until is not None:
        raise GateBlocked(
            f"These sign-ins are locked for {LOCK_MINUTES} minutes after {LOCK_FAILURES} failed "
            "attempts. Try again later.")

    entry = registry.get(teacher_id)
    if entry is None:
        # Do the same expensive work and return the same error as a wrong PIN on a real ID,
        # so a failed sign-in does not reveal which teacher IDs exist.
        _burn_time(pin)
        _record_failure(state, teacher_id)
        _write(_path("auth_state"), state)
        raise GateBlocked(_fail_message())

    try:
        salt = bytes.fromhex(entry["salt"])
        expected = entry["hash"]
    except (KeyError, TypeError, ValueError):
        _record_failure(state, teacher_id)
        _write(_path("auth_state"), state)
        raise GateBlocked(_fail_message()) from None

    if not hmac.compare_digest(_hash(pin, salt), expected):
        _record_failure(state, teacher_id)
        _write(_path("auth_state"), state)
        raise GateBlocked(_fail_message())

    state.pop(teacher_id, None)  # a good sign-in clears the failure count
    _write(_path("auth_state"), state)
    sessions = _pruned_sessions()
    token, csrf = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    now = _now()
    absolute = now + timedelta(hours=SESSION_MAX_HOURS)
    sessions[_digest(token)] = {"teacher_id": teacher_id, "name": entry.get("name", ""),
                                "kind": "human", "scope": "human",
                                "created": _iso(now),
                                "expires": _iso(_clamped(now, SESSION_MINUTES, absolute)),
                                "absolute": _iso(absolute),
                                "csrf": _digest(csrf)}
    _write(_path("sessions"), sessions)
    # The CSRF value reaches the caller once and is kept only as its digest.
    return {"session": token, "teacher_id": teacher_id, "name": entry.get("name", ""),
            "kind": "human", "csrf": csrf, "expires_in": SESSION_MINUTES * 60}


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _iso(when: datetime) -> str:
    return when.isoformat(timespec="seconds")


def _parse(value) -> datetime | None:
    """A stored timestamp, or None when it is missing or unreadable."""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _kind(stored: dict) -> str:
    """Session files written before kinds existed are human sessions."""
    return stored.get("kind") or "human"


def _live(stored: dict, now: datetime) -> bool:
    """Whether a stored session record is still usable at `now`.

    One copy of the rule, so the check that refuses a request and the cleanup that prunes
    the file cannot drift apart.
    """
    expires = _parse(stored.get("expires"))
    if expires is None or expires <= now:
        return False
    absolute = _parse(stored.get("absolute"))
    return absolute is None or absolute > now


def _clamped(now: datetime, minutes: int, absolute: datetime | None) -> datetime:
    """A new expiry, never later than the absolute limit that applies to the token."""
    expires = now + timedelta(minutes=minutes)
    return expires if absolute is None else min(expires, absolute)


def _valid(session: str | None, kind: str, action: str = "continue") -> tuple[str, dict]:
    """The stored record for a live session of the required kind, or raise GateBlocked.

    `action` only shapes the error a missing session gets, so signing in to save does not
    tell the person to approve.
    """
    if not session:
        raise GateBlocked(f"Sign-in required. Sign in with your teacher ID and PIN to {action}.")
    digest = _digest(session)
    sessions = _read(_path("sessions"), {})
    stored = sessions.get(digest)
    if stored is None:
        raise GateBlocked("Sign-in required. That session is not valid on this computer.")
    now = _now()
    if not _live(stored, now):
        raise GateBlocked("Your sign-in expired. Sign in again.")
    if _kind(stored) != kind:
        raise GateBlocked("That is an agent token. An agent token can read and draft but cannot "
                          "approve, save or mint another token; a teacher must sign in."
                          if kind == "human" else "That is a teacher session, not an agent token.")
    if kind == "agent" and not _live(sessions.get(stored.get("parent") or "") or {}, now):
        raise GateBlocked("The teacher's sign-in that started this agent run has ended. "
                          "Start the run again.")
    return digest, stored


def _pruned_sessions() -> dict:
    """Sessions that have not expired. Only the SHA-256 of a token is ever stored."""
    now = _now()
    return {digest: s for digest, s in _read(_path("sessions"), {}).items() if _live(s, now)}


def _slide(digest: str) -> None:
    """Extend a live human session by SESSION_MINUTES, never past its absolute expiry.

    Re-reads the file first, so a session signed out between the check and this write
    stays signed out instead of being put back by the caller's copy of the record.
    """
    now = _now()
    sessions = _read(_path("sessions"), {})
    stored = sessions.get(digest)
    if stored is None or not _live(stored, now):
        return
    stored["expires"] = _iso(_clamped(now, SESSION_MINUTES, _parse(stored.get("absolute"))))
    sessions[digest] = stored
    _write(_path("sessions"), sessions)


def resolve(session: str | None, kind: str = "human", action: str = "continue") -> dict:
    """Return {teacher_id, name, kind} for a valid session, or raise GateBlocked.

    `kind` says what the caller is about to do. A token of the wrong kind is refused
    rather than treated as equal: an agent token cannot stand in for a teacher at the
    approval gate, and a teacher session is not an agent token.
    """
    digest, stored = _valid(session, kind, action)
    teacher_id = stored.get("teacher_id", "")
    name = (_read(_path("teachers"), {}).get(teacher_id) or {}).get("name")
    if not name:
        raise GateBlocked("Sign-in required. That teacher is no longer registered on this computer.")
    if kind == "human":
        _slide(digest)  # each authenticated request buys 15 more minutes
    return {"teacher_id": teacher_id, "name": name, "kind": kind}


def mint_agent_token(session: str | None) -> str:
    """Create a token for one agent run acting as the signed-in teacher.

    Requires a live human session; an agent token cannot mint another token. The new
    token lasts at most 30 minutes and shares the human session's absolute expiry, and it
    dies with that session, so signing out is enough to stop a run.
    """
    digest, stored = _valid(session, "human", "start an agent run")
    now = _now()
    absolute = _parse(stored.get("absolute"))
    expires = _clamped(now, AGENT_MINUTES, absolute)
    token = secrets.token_urlsafe(24)
    sessions = _pruned_sessions()
    sessions[_digest(token)] = {"teacher_id": stored.get("teacher_id", ""),
                                "name": stored.get("name", ""),
                                "kind": "agent", "scope": "agent",
                                "created": _iso(now), "expires": _iso(expires),
                                "absolute": _iso(expires), "parent": digest}
    _write(_path("sessions"), sessions)
    return token


def logout(session: str | None) -> bool:
    """Delete a session. Signing out of a human session also kills its agent tokens."""
    if not session:
        return False
    digest = _digest(session)
    sessions = _pruned_sessions()
    if digest not in sessions:
        return False
    for key in [k for k, s in sessions.items() if s.get("parent") == digest]:
        del sessions[key]
    del sessions[digest]
    _write(_path("sessions"), sessions)
    return True


def new_csrf(session: str | None) -> str:
    """Give a signed-in browser a fresh CSRF value (for example after a page reload).

    Only its SHA-256 is stored, like the session token itself.
    """
    digest, _ = _valid(session, "human")
    sessions = _pruned_sessions()
    value = secrets.token_urlsafe(24)
    sessions[digest]["csrf"] = _digest(value)
    _write(_path("sessions"), sessions)
    return value


def csrf_ok(session: str | None, value: str | None) -> bool:
    """Whether a request's CSRF value matches the one issued to this human session."""
    if not value:
        return False
    try:
        _, stored = _valid(session, "human")
    except GateBlocked:
        return False
    return hmac.compare_digest(stored.get("csrf", ""), _digest(value))
