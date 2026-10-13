"""Build the offline teacher page: ui/hatua.html (open by double-click, no server, no APIs).

All data is embedded in the page. Decisions made on the page are kept in that
browser and exported as an approvals file, which `python3 -m hatua import-approvals`
applies through the same gate as the command line.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import audit, config, guard, patterns, store, summary, tools

TEMPLATE = config.UI / "template.html"
OUT = config.UI / "hatua.html"
OUT_FRAGMENT = config.UI / "hatua_fragment.html"  # same page without the document wrapper


def collect() -> dict:
    learners = store.load("learners")
    records = store.load("records")
    att = store.load("attendance")
    notes = store.load("notes")
    flags = store.load("flags")
    drafts = store.load("drafts")

    rec_by = {}
    for r in records:
        rec_by.setdefault(r["learner_id"], []).append(
            [r["record_id"], r["ordinal"], r["learning_area"], r["family"], r["task"], r["level"],
             r["score"], r["task_date"], r["logged_date"], r["source"], r["teacher"], ",".join(r["flags"])])
    att_by = {}
    for a in att:
        att_by.setdefault(a["learner_id"], []).append(
            [a["attendance_id"], a["ordinal"], a["days_present"], a["days_open"]])
    notes_by = {}
    for n in notes:
        notes_by.setdefault(n["learner_id"], []).append(
            [n["note_id"], n["ordinal"], n["learning_area"] or "", n["family"] or "", n["date"] or "", n["text"]])

    out = []
    for l in learners:
        lid = l["learner_id"]
        found = tools.find_patterns(lid)
        d = tools.draft_summary(lid, "teacher", "en")
        keep = {p["pattern_id"] for p in found["patterns"]}
        guardian = {}
        for lang in ("en", "sw"):
            text = summary.guardian_text(found, l, keep, lang)
            guardian[lang] = {"text": text, "hash": summary.text_hash(text)}
        approved = next((x for x in reversed(drafts) if x["learner_id"] == lid and x["audience"] == "teacher"
                         and x["status"] in ("approved", "rejected")), None)
        out.append({
            "id": lid, "name": l["first_name"], "stream": l["stream"], "grade": l["current_grade"],
            "joined": l["joined"], "span": found["span"], "reviewed": found["records_reviewed"],
            "patterns": [{k: p[k] for k in ("pattern_id", "type", "family", "statement", "trail", "evidence",
                                             "notes", "caveats", "current", "terms")} for p in found["patterns"]],
            "record_notes": found["record_notes"],
            "draft": {"id": d["draft_id"], "hash": d["hash"], "text": d["text"], "status": d["status"]},
            "decided": ({"status": approved["status"], "by": approved.get("approved_by"),
                         "text": approved.get("final_text")} if approved else None),
            "guardian": guardian,
            "records": sorted(rec_by.get(lid, []), key=lambda r: (r[1], r[3])),
            "attendance": att_by.get(lid, []), "notes": notes_by.get(lid, []),
        })
    return {
        "meta": {"school": learners[0]["school"] if learners else "", "class": "Grade 9 (streams 9A, 9B)",
                 "built": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
                 "today": config.today().isoformat(), "records": len(records)},
        "families": sorted({r["family"] for r in records}),
        "learners": out,
        "flags": [[f.get("flag_id", ""), f["type"], f["severity"], f["learner_id"], f["record_id"], f["message"],
                   f.get("source_file", "")] for f in flags],
        "guard": {"forbidden": guard.FORBIDDEN},
        "audit": audit.read_events(400),
    }


def build() -> str:
    data = json.dumps(collect(), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8").replace("/*__HATUA_DATA__*/null", data)
    OUT_FRAGMENT.write_text(page, encoding="utf-8")
    OUT.write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                   '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                   "</head>\n<body>\n" + page + "\n</body>\n</html>\n", encoding="utf-8")
    return str(OUT.relative_to(config.ROOT))
