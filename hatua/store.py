"""Local JSON store. Nothing leaves the machine: no network calls anywhere in Hatua's core."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from . import config
from .normalize import area as clean_area, clean_record, flag, learner_id as clean_id, parse_date

FILES = ("learners", "records", "attendance", "notes", "flags", "drafts", "ingested")


def _path(name: str) -> Path:
    return config.STORE / f"{name}.json"


def load(name: str) -> list | dict:
    p = _path(name)
    if not p.exists():
        return {} if name == "ingested" else []
    return json.loads(p.read_text(encoding="utf-8"))


def save(name: str, data) -> None:
    config.STORE.mkdir(parents=True, exist_ok=True)
    tmp = _path(name).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_path(name))


def read_csv(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def reset() -> None:
    for name in FILES:
        if _path(name).exists():
            _path(name).unlink()


def load_class_list(path: Path) -> int:
    rows = read_csv(path)
    save("learners", rows)
    return len(rows)


def load_attendance(path: Path) -> int:
    rows = []
    for r in read_csv(path):
        lid = clean_id(r["learner_id"])
        g, t = int(r["grade"]), int(r["term"])
        opened = int(r["days_open"])
        present = int(r["days_present"])
        rows.append({"attendance_id": f"A-{lid}-G{g}T{t}", "learner_id": lid, "grade": g, "term": t,
                     "year": int(r["year"]), "ordinal": config.term_ordinal(g, t),
                     "days_present": present, "days_open": opened,
                     "rate": round(present / opened, 3) if opened else None})
    save("attendance", rows)
    return len(rows)


def load_notes(path: Path) -> int:
    rows = []
    for r in read_csv(path):
        ar = clean_area(r.get("learning_area", ""))
        d = parse_date(r.get("date", ""))
        g, t = int(r["grade"]), int(r["term"])
        rows.append({"note_id": r["note_id"], "learner_id": clean_id(r["learner_id"]),
                     "grade": g, "term": t, "year": int(r["year"]), "ordinal": config.term_ordinal(g, t),
                     "learning_area": ar, "family": config.family_of(ar) if ar else None,
                     "date": d.isoformat() if d else None, "teacher": r.get("teacher", ""),
                     "text": r["text"].strip()})
    save("notes", rows)
    return len(rows)


def ingest_records(path: Path) -> dict:
    """Validate, clean and add a CSV of assessment records. Returns a quality report."""
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    ingested: dict = load("ingested")  # type: ignore[assignment]
    if digest in ingested.values():
        return {"file": path.name, "added": 0, "rejected": 0, "skipped_duplicates": 0,
                "message": "This exact file was already ingested. Nothing added.", "flags": []}

    known = {l["learner_id"] for l in load("learners")}
    records: list[dict] = load("records")  # type: ignore[assignment]
    by_id = {r["record_id"] for r in records}
    by_key = {(r["learner_id"], r["ordinal"], r["learning_area"], r["task"], r["level"], r["task_date"])
              for r in records}
    all_flags: list[dict] = load("flags")  # type: ignore[assignment]
    new_flags: list[dict] = []
    added = rejected = dup = 0
    for row in read_csv(path):
        rec, flags = clean_record(row, known)
        if rec is None:
            rejected += 1
            new_flags.extend(flags)
            continue
        key = (rec["learner_id"], rec["ordinal"], rec["learning_area"], rec["task"], rec["level"], rec["task_date"])
        if rec["record_id"] in by_id or key in by_key:
            dup += 1
            new_flags.append(flag("duplicate_row", "info",
                                  "Same record appears twice in the export; the copy was skipped.",
                                  rec["record_id"], rec["learner_id"]))
            continue
        rec["file"] = path.name
        records.append(rec)
        by_id.add(rec["record_id"])
        by_key.add(key)
        new_flags.extend(flags)
        added += 1
    for i, f in enumerate(new_flags, start=len(all_flags) + 1):
        f["flag_id"] = f"Q-{i:05d}"
        f["source_file"] = path.name
    all_flags.extend(new_flags)
    ingested[path.name] = digest
    save("records", records)
    save("flags", all_flags)
    save("ingested", ingested)
    counts: dict[str, int] = {}
    for f in new_flags:
        counts[f["type"]] = counts.get(f["type"], 0) + 1
    return {"file": path.name, "added": added, "rejected": rejected, "skipped_duplicates": dup,
            "flag_counts": counts, "flags": new_flags[:25],
            "message": f"Added {added} records, rejected {rejected}, skipped {dup} duplicates."}


def learner(lid: str) -> dict | None:
    return next((l for l in load("learners") if l["learner_id"] == lid), None)


def records_for(lid: str) -> list[dict]:
    return sorted((r for r in load("records") if r["learner_id"] == lid),
                  key=lambda r: (r["ordinal"], r["family"], r["record_id"]))


def get_record(evidence_id: str) -> dict | None:
    """Look up any cited evidence: R- (assessment), N- (teacher note) or A- (attendance)."""
    table = {"R": ("records", "record_id"), "N": ("notes", "note_id"), "A": ("attendance", "attendance_id")}
    kind = evidence_id.split("-", 1)[0]
    if kind not in table:
        return None
    name, key = table[kind]
    return next((r for r in load(name) if r[key] == evidence_id), None)
