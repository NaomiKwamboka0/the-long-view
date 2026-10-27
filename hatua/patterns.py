"""Find cited patterns across terms for one learner.

Rules are deliberately simple and deterministic so a teacher (or a parent asking
"why?") can follow them:

* sustained_strength  - 3+ recorded terms in a row averaging Exceeding Expectations
* sustained_struggle  - 4+ recorded terms in a row averaging Approaching or below
* improvement/decline - over the most recent 3-6 terms, the level moves by a full
                        rubric step or more, without a reversal along the way
* attendance_drop     - 2+ terms in a row with attendance under 75%
* record notes        - gaps and late logging, which are about the records, not the child

A one-off result never becomes a pattern. No pattern compares a learner with anyone else.
"""
from __future__ import annotations

import hashlib
from statistics import mean

from . import config, store

MAX_GAP = 2  # ordinals: one missing term inside a run is allowed and reported


def _pid(*parts) -> str:
    return "P-" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:8]


def _lvl(points: float) -> str:
    return config.LEVELS[max(0, min(3, int(points + 0.5) - 1))]


def _label(o: int) -> str:
    return config.term_label(4 + o // 3, o % 3 + 1)


def term_series(records: list[dict]) -> dict[str, list[dict]]:
    """family -> [{ordinal, points, level, record_ids}] in term order."""
    by_fam: dict[str, dict[int, list[dict]]] = {}
    for r in records:
        by_fam.setdefault(r["family"], {}).setdefault(r["ordinal"], []).append(r)
    out = {}
    for fam, terms in by_fam.items():
        series = []
        for o in sorted(terms):
            # An unresolved score/level conflict makes the whole term unconfirmed.
            # Keep it in the series as a break so runs cannot bridge across it.
            if any("score_level_conflict" in r["flags"] for r in terms[o]):
                series.append({"ordinal": o, "points": None, "level": None,
                               "record_ids": [r["record_id"] for r in terms[o]], "flagged": []})
                continue
            pts = mean(r["points"] for r in terms[o])
            series.append({"ordinal": o, "points": round(pts, 2), "level": _lvl(pts),
                           "record_ids": [r["record_id"] for r in terms[o]],
                           "flagged": [r["record_id"] for r in terms[o] if r["flags"]
                                       and set(r["flags"]) - {"level_repaired", "area_repaired", "id_repaired"}]})
        out[fam] = series
    return out


def _runs(series: list[dict], ok) -> list[list[dict]]:
    runs, cur = [], []
    for t in series:
        if t["points"] is None:
            if cur:
                runs.append(cur)
            cur = []
            continue
        if ok(t) and (not cur or t["ordinal"] - cur[-1]["ordinal"] <= MAX_GAP):
            cur.append(t)
        else:
            if cur:
                runs.append(cur)
            cur = [t] if ok(t) else []
    if cur:
        runs.append(cur)
    return runs


def _caveats(window: list[dict]) -> list[str]:
    notes = []
    gaps = [(a["ordinal"], b["ordinal"]) for a, b in zip(window, window[1:]) if b["ordinal"] - a["ordinal"] > 1]
    for a, _gap_end in gaps:
        notes.append(f"No record for {_label(a + 1)}.")
    flagged = [rid for t in window for rid in t["flagged"]]
    if flagged:
        word = "record" if len(flagged) == 1 else "records"
        notes.append(f"Please check {word} {', '.join(flagged[:6])} before relying on this.")
    return notes


def _related_notes(notes: list[dict], fam: str | None, lo: int, hi: int) -> list[dict]:
    return [n for n in notes if lo <= n["ordinal"] <= hi and (fam is None or n["family"] == fam)]


def _pattern(lid, ptype, fam, window, text, notes, extra_caveats=()) -> dict:
    lo, hi = window[0]["ordinal"], window[-1]["ordinal"]
    evidence = [rid for t in window for rid in t["record_ids"]]
    rel = _related_notes(notes, fam, lo, hi)
    return {
        "pattern_id": _pid(lid, ptype, fam, lo, hi), "learner_id": lid, "type": ptype,
        "family": fam, "from": _label(lo), "to": _label(hi), "from_ordinal": lo, "to_ordinal": hi,
        "terms": len(window), "statement": text,
        "trail": [{"term": _label(t["ordinal"]), "level": t["level"], "record_ids": t["record_ids"]}
                  for t in window],
        "evidence": evidence, "notes": [{"note_id": n["note_id"], "text": n["text"], "term": _label(n["ordinal"])}
                                        for n in rel],
        "caveats": list(extra_caveats) + _caveats(window),
    }


def _trend(series: list[dict]) -> tuple[str, list[dict]] | None:
    """Look back from the latest term for a sustained move of at least one rubric step.

    The two earliest terms in the window must ALL sit a full step away from the two
    latest terms, so a single unusual result (a one-off spike or dip) cannot start
    or end a trend. Larger windows win, so the reported trend is the longest one.
    """
    best = None
    for n in range(4, min(6, len(series)) + 1):
        w = series[-n:]
        if any(t["points"] is None for t in w):
            continue
        if w[-1]["ordinal"] - w[0]["ordinal"] > n:  # at most one missing term
            continue
        first, last = [t["points"] for t in w[:2]], [t["points"] for t in w[-2:]]
        steps = [b["points"] - a["points"] for a, b in zip(w, w[1:])]
        if min(last) - max(first) >= 1.0 and min(steps) > -1.0:
            best = ("improvement", w)
        elif min(first) - max(last) >= 1.0 and max(steps) < 1.0:
            best = ("decline", w)
    return best


def _longest(runs: list[list[dict]], minimum: int) -> list[dict] | None:
    runs = [r for r in runs if len(r) >= minimum]
    return max(runs, key=lambda r: (len(r), r[-1]["ordinal"])) if runs else None


def find(lid: str) -> dict:
    learner = store.learner(lid)
    if not learner:
        raise ValueError(f"Unknown learner {lid}")
    recs = store.records_for(lid)
    notes = [n for n in store.load("notes") if n["learner_id"] == lid]
    att = sorted((a for a in store.load("attendance") if a["learner_id"] == lid), key=lambda a: a["ordinal"])
    patterns: list[dict] = []
    series = term_series(recs)

    latest_overall = max((r["ordinal"] for r in recs), default=0)
    for fam, s in sorted(series.items()):
        name = fam
        run = _longest(_runs(s, lambda t: t["points"] >= 3.5), 3)
        if run:
            patterns.append(_pattern(lid, "sustained_strength", fam, run,
                f"{name}: Exceeding Expectations in {len(run)} recorded terms in a row, "
                f"{_label(run[0]['ordinal'])} to {_label(run[-1]['ordinal'])}.", notes))
        # A struggle is reported only while it is still going on (ends in the last 3 terms).
        run = _longest([r for r in _runs(s, lambda t: t["points"] <= 2.0)
                        if r[-1]["ordinal"] >= latest_overall - 2], 4)
        tr = _trend(s)
        if run and not (tr and tr[0] == "decline"):  # a decline already tells this story
            patterns.append(_pattern(lid, "sustained_struggle", fam, run,
                f"{name}: Approaching Expectations or below in {len(run)} recorded terms in a row, "
                f"{_label(run[0]['ordinal'])} to {_label(run[-1]['ordinal'])}.", notes))
        if tr:
            kind, w = tr
            a, b = w[0], w[-1]
            verb = "rose" if kind == "improvement" else "fell"
            patterns.append(_pattern(lid, kind, fam, w,
                f"{name}: results {verb} from {config.LEVEL_NAMES[a['level']]} ({_label(a['ordinal'])}) "
                f"to {config.LEVEL_NAMES[b['level']]} ({_label(b['ordinal'])}) over {len(w)} recorded terms.",
                notes))

    low = [a for a in att if a["rate"] is not None and a["rate"] < 0.75]
    run: list[dict] = []
    for a in low + [None]:
        if a and (not run or a["ordinal"] - run[-1]["ordinal"] == 1):
            run.append(a)
            continue
        if len(run) >= 2:
            lo, hi = run[0]["ordinal"], run[-1]["ordinal"]
            rates = ", ".join(f"{_label(x['ordinal'])}: {x['days_present']}/{x['days_open']} days" for x in run)
            patterns.append({
                "pattern_id": _pid(lid, "attendance_drop", lo, hi), "learner_id": lid,
                "type": "attendance_drop", "family": None, "from": _label(lo), "to": _label(hi),
                "from_ordinal": lo, "to_ordinal": hi, "terms": len(run),
                "statement": f"Attendance under 75% for {len(run)} terms in a row ({rates}).",
                "trail": [{"term": _label(x["ordinal"]), "level": f"{round(x['rate'] * 100)}%",
                           "record_ids": [x["attendance_id"]]} for x in run],
                "evidence": [x["attendance_id"] for x in run],
                "notes": [{"note_id": n["note_id"], "text": n["text"], "term": _label(n["ordinal"])}
                          for n in _related_notes(notes, None, lo, hi) if not n["family"]],
                "caveats": ["Attendance registers are summaries; they do not show why a learner was absent."],
            })
        run = [a] if a else []

    # Notes about the records themselves (never about the child).
    record_notes = []
    conflicts = [r["record_id"] for r in recs if "score_level_conflict" in r["flags"]]
    if conflicts:
        record_notes.append({"type": "score_level_conflict", "evidence": conflicts,
                             "statement": f"{len(conflicts)} assessment record(s) have a score and level that disagree. "
                                          "Their learning-area terms are excluded from patterns until corrected in the source records."})
    if recs:
        first = recs[0]["ordinal"]
        if first > 0:
            record_notes.append({"type": "data_gap", "evidence": [recs[0]["record_id"]],
                                 "statement": f"Records start at {_label(first)}. Earlier years are not in Hatua "
                                              f"(for example, the learner joined from another school)."})
    flags = [f for f in store.load("flags") if f["learner_id"] == lid]
    late = [f["record_id"] for f in flags if f["type"] == "late_logging"]
    if len(late) >= 5 and len(late) >= 0.1 * len(recs):
        record_notes.append({"type": "late_logging", "evidence": late,
                             "statement": f"{len(late)} records were uploaded more than six weeks after the task. "
                                          f"Check these before relying on them."})
    latest = max((r["ordinal"] for r in recs), default=None)
    for p in patterns:
        p["current"] = latest is not None and p["to_ordinal"] >= latest - 1
    order = {"decline": 0, "attendance_drop": 1, "sustained_struggle": 2, "improvement": 3, "sustained_strength": 4}
    patterns.sort(key=lambda p: (order[p["type"]], p["family"] or ""))
    return {"learner_id": lid, "first_name": learner["first_name"], "patterns": patterns,
            "record_notes": record_notes, "records_reviewed": len(recs),
            "span": f"{_label(recs[0]['ordinal'])} to {_label(recs[-1]['ordinal'])}" if recs else "no records"}
