"""Append-only audit log: every tool call with inputs, outputs, timestamps and actor."""
from __future__ import annotations

import functools
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable

from . import config

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


def write_event(event: dict) -> None:
    config.LOGS.mkdir(parents=True, exist_ok=True)
    event.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with config.AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str, ensure_ascii=False) + "\n")


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
