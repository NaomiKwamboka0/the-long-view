"""Kenya's basic-education school calendar, read from data/calendar/kenya_<year>.json.

The dates are the Ministry of Education's, kept in a plain file so a school can correct
them without touching code. Nothing here makes a network call.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from . import config


def _file(year: int) -> Path:
    return config.DATA / "calendar" / f"kenya_{year}.json"


def load(year: int) -> dict | None:
    """The calendar for a year, or None if the school has no file for it."""
    p = _file(year)
    if not p.exists():
        return None
    cal = json.loads(p.read_text(encoding="utf-8"))
    grace = int(cal.get("results_due_days_after_close", 7))
    for t in cal["terms"]:
        t["opens"] = date.fromisoformat(t["opens"])
        t["closes"] = date.fromisoformat(t["closes"])
        t["results_due"] = t["closes"] + timedelta(days=grace)
    return cal


def term_on(day: date) -> dict:
    """Where a day falls: {"year", "term", "state": "in_term"|"half_term"|"holiday", ...}."""
    cal = load(day.year)
    if cal is None:
        return {"year": day.year, "term": None, "state": "unknown",
                "text": f"No school calendar file for {day.year}."}
    for t in cal["terms"]:
        if t["opens"] <= day <= t["closes"]:
            ht = t.get("half_term")
            if ht and date.fromisoformat(ht["from"]) <= day <= date.fromisoformat(ht["to"]):
                return {"year": day.year, "term": t["term"], "state": "half_term",
                        "text": f"Term {t['term']} half-term break"}
            week = (day - t["opens"]).days // 7 + 1
            return {"year": day.year, "term": t["term"], "state": "in_term", "week": week,
                    "text": f"Term {t['term']}, week {week}"}
    nxt = next((t for t in cal["terms"] if t["opens"] > day), None)
    last = max((t for t in cal["terms"] if t["closes"] < day), key=lambda t: t["closes"], default=None)
    text = "School holiday"
    if last:
        text += f" after Term {last['term']}"
    if nxt:
        text += f". Term {nxt['term']} opens {nxt['opens'].strftime('%d %b %Y')}"
    return {"year": day.year, "term": last["term"] if last else None, "state": "holiday", "text": text + "."}


def due_terms(day: date) -> list[dict]:
    """Terms of this year whose results are due on or before `day` (closing date + grace)."""
    cal = load(day.year)
    if cal is None:
        return []
    return [{"year": cal["year"], "term": t["term"], "closes": t["closes"], "due": t["results_due"]}
            for t in cal["terms"] if t["results_due"] <= day]


def summary(day: date) -> dict:
    cal = load(day.year)
    now = term_on(day)
    if cal is None:
        return {"today": day.isoformat(), "now": now["text"], "terms": [], "source": ""}
    return {"today": day.isoformat(), "now": now["text"], "source": cal.get("source", ""),
            "source_urls": cal.get("source_urls", []),
            "terms": [{"term": t["term"], "opens": t["opens"].isoformat(), "closes": t["closes"].isoformat(),
                       "results_due": t["results_due"].isoformat()} for t in cal["terms"]],
            "national_assessments": cal.get("national_assessments", [])}
