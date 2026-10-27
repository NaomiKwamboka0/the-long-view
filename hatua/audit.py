"""Append-only, tamper-evident audit log: every tool call with inputs, outputs and actor.

Each line carries `prev`, the SHA-256 of the previous line exactly as written, so an edit,
a deletion or a reordering shows up as a broken chain. The first line uses 64 zeros.

What the chain does and does not prove: it shows that the file changed, but a determined
editor can rewrite the whole file and recompute every hash. Editing or deleting the very
last line cannot be detected at all from the file alone. The chain only catches that if the
tip hash is recorded somewhere else, for example printed on the approval page or read out
in the demo. Treat `python -m hatua verify-log` as a check on accidents and casual edits,
not as protection against someone who controls the machine. One writer at a time is
assumed; two processes appending at once can interleave and break the chain.
"""
from __future__ import annotations

import functools
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import config

GENESIS = "0" * 64

# Arguments that must never reach the log in clear text. A PIN or a session token
# would otherwise sit in logs/audit.jsonl forever.
# Secrets MUST be passed as keyword arguments: positional arguments are logged as
# they are, so `approve("D-1", "name", "approve", "pin")` would still be stored.
SECRET_KEYS = {"pin", "session", "password", "token", "secret"}
REDACTED = "[redacted]"


def scrub(kwargs: dict) -> dict:
    """Return the keyword arguments with every secret-bearing value replaced."""
    return {key: REDACTED if str(key).lower() in SECRET_KEYS else value
            for key, value in kwargs.items()}


def _short(value: Any, limit: int = 2000) -> Any:
    text = json.dumps(value, default=str, ensure_ascii=False)
    if len(text) <= limit:
        return value
    return {"truncated": True, "preview": text[:limit]}


def _lines(path: Path) -> list[str]:
    if not Path(path).exists():
        return []
    return [line for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def previous_hash(path: Path) -> str:
    """SHA-256 of the last line as written, or 64 zeros for an empty file."""
    lines = _lines(path)
    return hashlib.sha256(lines[-1].encode("utf-8")).hexdigest() if lines else GENESIS


def append_jsonl(path: Path, event: dict) -> dict:
    """Append one event with its chain hash. Used for the audit log and the approvals log."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    event["prev"] = previous_hash(path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str, ensure_ascii=False) + "\n")
    return event


def write_event(event: dict) -> None:
    event.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    append_jsonl(config.AUDIT_LOG, event)


def verify_jsonl(path: Path) -> dict:
    """Check one chained log. Returns {ok, chained, lines, tip, line, message}.

    A file written before this feature has no `prev` anywhere: it is reported as
    "unchained" rather than broken, because nothing can be checked in it.
    """
    path = Path(path)
    lines = _lines(path)
    if not lines:
        return {"ok": True, "chained": True, "lines": 0, "tip": GENESIS,
                "message": f"{path.name}: empty"}
    events = []
    for number, line in enumerate(lines, start=1):
        try:
            events.append(json.loads(line))
        except ValueError:
            return {"ok": False, "chained": True, "lines": len(lines), "line": number,
                    "tip": None, "message": f"{path.name}: line {number} is not valid JSON."}
    if any("prev" not in event for event in events):
        return {"ok": True, "chained": False, "lines": len(lines), "tip": None,
                "message": f"{path.name}: {len(lines)} line(s), not chained (written before "
                           "tamper evidence existed). Nothing can be verified in this file."}

    expected = GENESIS
    for number, (line, event) in enumerate(zip(lines, events), start=1):
        if event.get("prev") != expected:
            return {"ok": False, "chained": True, "lines": len(lines), "line": number, "tip": None,
                    "message": f"{path.name}: line {number} does not match the line before it. "
                               "A line was edited, deleted or reordered."}
        expected = hashlib.sha256(line.encode("utf-8")).hexdigest()
    return {"ok": True, "chained": True, "lines": len(lines), "tip": expected,
            "message": f"{path.name}: {len(lines)} line(s), chain intact. Tip {expected[:16]}."}


def audited(tool: str, actor: str = "agent") -> Callable:
    """Decorator that logs one line per call, success or failure."""

    def wrap(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            start = time.perf_counter()
            event = {"tool": tool, "actor": kwargs.get("teacher") or actor,
                     "inputs": _short({"args": list(args), "kwargs": scrub(kwargs)})}
            try:
                result = fn(*args, **kwargs)
                event.update(ok=True, output=_short(result))
                return result
            except Exception as exc:  # logged, then re-raised
                event.update(ok=False, error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                event["duration_ms"] = round((time.perf_counter() - start) * 1000, 1)
                write_event(event)

        return inner

    return wrap


def read_events(limit: int | None = None) -> list[dict]:
    if not config.AUDIT_LOG.exists():
        return []
    lines = config.AUDIT_LOG.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines if line.strip()]
    return events[-limit:] if limit else events
