"""Map a school's own spreadsheet export onto Hatua's columns.

    python -m hatua map-export my_sheet.csv --mapping data/mappings/school.json

A real school sheet will not use Hatua's headings, and it usually carries names and
phone numbers that must not enter Hatua. This module copies **only** the columns named
in a mapping file, reports everything it dropped, and can replace a real admission
number with a pseudonymous `HT-xxxx` from a private ID map.

Deterministic: no model, no fuzzy matching, no guessing what a column means. If the
mapping does not say it, the column does not travel.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from . import config

CANONICAL = ["record_id", "learner_id", "grade", "year", "term", "learning_area", "task",
             "level", "score", "task_date", "logged_date", "teacher", "source"]
REQUIRED = ["learner_id", "grade", "year", "term", "learning_area"]

# Headings that usually carry a person, not a result. They are dropped either way; the
# report names them separately so the person doing the import sees what was left behind.
PERSONAL = re.compile(
    r"\b(name|surname|phone|mobile|tel|telephone|email|parent|guardian|address|birth|dob"
    r"|nhif|sha|upi|passport|religion|tribe|disab\w*|health|medical)\b"
    r"|\bid\s*(no|number)\b", re.IGNORECASE)


class MappingError(ValueError):
    """The mapping file, the input sheet or the output path cannot be used as given."""


def _key(text: str) -> str:
    """Headings are matched ignoring stray spaces and case, but never by meaning."""
    return " ".join(str(text or "").split()).strip().lower()


def _load_mapping(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise MappingError(f"Mapping file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        raise MappingError(f"Mapping file is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise MappingError("Mapping file must contain a JSON object.")
    columns = data.get("columns")
    if not isinstance(columns, dict) or not columns:
        raise MappingError("The mapping has no 'columns': nothing would be copied.")
    unknown = sorted({str(v) for v in columns.values()} - set(CANONICAL))
    if unknown:
        raise MappingError("Unknown Hatua column(s) in 'columns': " + ", ".join(unknown))
    constants = data.get("constants") or {}
    if not isinstance(constants, dict) or sorted(set(constants) - set(CANONICAL)):
        raise MappingError("'constants' must map Hatua column names to fixed values.")
    if data.get("id_map") is not None and not isinstance(data["id_map"], str):
        raise MappingError("'id_map' must be a file path, relative to data/.")
    return data


def _read_sheet(path: Path) -> tuple[list[str], list[dict]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        headings = list(reader.fieldnames or [])
        return headings, list(reader)


def _id_map(mapping: dict) -> dict[str, str]:
    """Load real_id -> hatua_id. Kept out of the repository; see data/private/."""
    raw = mapping.get("id_map")
    if not raw:
        return {}
    path = Path(raw) if Path(raw).is_absolute() else config.DATA / raw
    if not path.exists():
        raise MappingError(f"ID map not found: {path}")
    pairs = {}
    for row in _read_sheet(path)[1]:
        real, pseudonym = (row.get("real_id") or "").strip(), (row.get("hatua_id") or "").strip()
        if real and pseudonym:
            pairs[real] = pseudonym
    return pairs


def _first_number(value: str) -> str:
    match = re.search(r"\d+", str(value or ""))
    return match.group(0) if match else str(value or "").strip()


def _row_id(values: dict) -> str:
    payload = json.dumps({k: v for k, v in values.items() if k != "record_id"},
                         sort_keys=True, ensure_ascii=False)
    return "R-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


def _out_path(name: str) -> Path:
    if not name or Path(name).name != name or name in {".", ".."} or "/" in name or "\\" in name:
        raise MappingError("Output must be a plain file name inside data/inbox.")
    path = Path(config.INBOX) / name
    if path.resolve().parent != Path(config.INBOX).resolve():
        raise MappingError("Output must stay inside data/inbox.")
    if path.exists():
        raise MappingError(f"{name} already exists in data/inbox. Choose another --out name.")
    return path


def map_export(csv_path: Path, mapping_path: Path, out_name: str | None = None) -> dict:
    """Write a Hatua-format CSV into data/inbox and return the report."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise MappingError(f"Input file not found: {csv_path}")
    mapping = _load_mapping(mapping_path)
    headings, rows = _read_sheet(csv_path)
    by_key = {_key(h): h for h in headings}

    missing = [src for src in mapping["columns"] if _key(src) not in by_key]
    if missing:
        raise MappingError("Heading(s) named in the mapping are not in the file: " + ", ".join(missing))

    target_of = {by_key[_key(src)]: canon for src, canon in mapping["columns"].items()}
    if len(set(target_of.values())) != len(target_of):
        raise MappingError("Two headings are mapped to the same Hatua column.")
    available = set(target_of.values()) | set(mapping.get("constants") or {})
    absent = [c for c in REQUIRED if c not in available]
    if absent:
        raise MappingError("The mapping must supply: " + ", ".join(absent))
    if not ({"level", "score"} & available):
        raise MappingError("The mapping must supply a rubric level or a score.")

    kept = [h for h in headings if h in target_of]
    dropped = [h for h in headings if h not in target_of]
    personal = [h for h in dropped if PERSONAL.search(h)]

    id_map = _id_map(mapping)
    constants = {k: str(v) for k, v in (mapping.get("constants") or {}).items()}
    out_rows, skipped = [], {"no_id_match": 0, "blank": 0}
    for row in rows:
        if not any((row.get(h) or "").strip() for h in kept):
            skipped["blank"] += 1
            continue
        values = {target_of[h]: (row.get(h) or "").strip() for h in kept}
        if id_map:
            real = values.get("learner_id", "")
            if real not in id_map:
                skipped["no_id_match"] += 1
                continue
            values["learner_id"] = id_map[real]
        for name, value in constants.items():
            values.setdefault(name, value)
        for name in ("grade", "term"):
            if name in values:
                values[name] = _first_number(values[name])
        if not values.get("record_id"):
            values["record_id"] = _row_id(values)
        out_rows.append(values)

    columns = [c for c in CANONICAL if c in available | {"record_id"}]
    name = out_name or f"{csv_path.stem}_hatua.csv"
    path = _out_path(name)
    if not out_rows:
        raise MappingError("No rows would be written. Check the mapping and the ID map.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)

    shown = path.relative_to(config.ROOT) if path.is_relative_to(config.ROOT) else path
    return {"written": str(shown), "rows_in": len(rows), "rows_out": len(out_rows),
            "skipped": skipped, "dropped_columns": dropped,
            "dropped_but_look_personal": personal,
            "next": f"python -m hatua ingest {path.name}"}
