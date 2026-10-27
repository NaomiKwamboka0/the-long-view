"""Optional teacher sign-in for the approval gate. Off by default.

    HATUA_REQUIRE_AUTH=1 python -m hatua agent

A typed name proves nothing: anyone can type any name. When sign-in is on, a teacher
registers once on this computer with an ID, a name and a PIN, and the approval entry
then carries the registered name and the teacher ID instead of whatever was typed.

What this does and does not do:
* It identifies a person among the teachers registered on this one computer.
* It is not TSC or KEMIS single sign-on, and it is not a claim about who someone is.
* Anyone who can edit the files under store/ and logs/ can still forge an entry.

Standard library only. Nothing here makes a network call.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .summary import GateBlocked

TEACHER_ID = re.compile(r"^[A-Za-z0-9_-]{3,24}$")
MIN_NAME = 3
MIN_PIN = 6
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
SESSION_MINUTES = 15
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
    token = secrets.token_urlsafe(24)
    expires = _now() + timedelta(minutes=SESSION_MINUTES)
    sessions[_digest(token)] = {"teacher_id": teacher_id, "name": entry.get("name", ""),
                                "expires": expires.isoformat(timespec="seconds")}
    _write(_path("sessions"), sessions)
    return {"session": token, "teacher_id": teacher_id, "name": entry.get("name", "")}


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _pruned_sessions() -> dict:
    """Sessions that have not expired. Only the SHA-256 of a token is ever stored."""
    now = _now()
    kept = {}
    for digest, s in _read(_path("sessions"), {}).items():
        try:
            if datetime.fromisoformat(s["expires"]) > now:
                kept[digest] = s
        except (KeyError, TypeError, ValueError):
            continue
    return kept


def resolve(session: str | None) -> dict:
    """Return {teacher_id, name} for a valid session, or raise GateBlocked."""
    if not session:
        raise GateBlocked("Sign-in required. Approve with --teacher-id and your PIN.")
    stored = _read(_path("sessions"), {}).get(_digest(session))
    if stored is None:
        raise GateBlocked("Sign-in required. That session is not valid on this computer.")
    try:
        expired = datetime.fromisoformat(stored["expires"]) <= _now()
    except (KeyError, TypeError, ValueError):
        expired = True
    if expired:
        raise GateBlocked("Your sign-in expired. Sign in again.")
    name = (_read(_path("teachers"), {}).get(stored.get("teacher_id", "")) or {}).get("name")
    if not name:
        raise GateBlocked("Sign-in required. That teacher is no longer registered on this computer.")
    return {"teacher_id": stored["teacher_id"], "name": name}
