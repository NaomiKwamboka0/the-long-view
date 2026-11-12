"""The school drive: shared folders where results arrive BEFORE they enter Hatua.

    school_drive/Grade 6/2026 Term 3/grade6_2026_term3_results.xlsx

Files may be Excel (.xlsx, first sheet) or CSV. Excel is read with hatua.xlsx, which
needs no extra package and never runs a formula.

A file on the drive is not in Hatua. Only the class teacher, signed in, can approve it,
and an approval covers only the rows for that teacher's own learners. Rows for another
stream wait for that stream's teacher; rows for a learner who is not on the class list
are never used. On approval the teacher's rows are copied into data/inbox and ingested
through the same audited tool the agent uses, and the alerts are worked out at once.

This is a human step on purpose. There is no MCP tool for it: the agent can read the
inbox, but it cannot let a file into Hatua.

Point HATUA_DRIVE at a real synced folder (for example a school's shared drive on the
laptop) to use it instead of the demo folder.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import audit, auth, config, school, store, tools, xlsx
from .normalize import clean_record
from .summary import GateBlocked

FOLDER = re.compile(r"^Grade (\d)$")
TERM_FOLDER = re.compile(r"^(\d{4}) Term ([123])$")
NEEDED = {"learner_id", "grade", "year", "term", "learning_area", "level"}
MAX_BYTES = 5 * 1024 * 1024
SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")
KINDS = {".xlsx": "Excel", ".csv": "CSV"}


def root() -> Path:
    return Path(os.environ.get("HATUA_DRIVE") or (config.ROOT / "school_drive")).resolve()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(rel: str) -> Path:
    """A drive path given by the page, refused if it points outside the drive."""
    path = (root() / rel).resolve()
    if root() not in path.parents or path.suffix.lower() not in KINDS or not path.is_file():
        raise ValueError("That file is not on the school drive. It may have been moved or deleted.")
    return path


def _table(path: Path) -> tuple[list[str], list[dict]]:
    """(column headings, rows) of a results file, Excel or CSV."""
    if path.suffix.lower() == ".xlsx":
        return xlsx.read(path)
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
    rows = list(reader)
    return [h.strip() for h in (reader.fieldnames or [])], rows


def _results_files(folder: Path) -> list[Path]:
    """Results files in a term folder. Excel's own lock files (~$name.xlsx) are skipped."""
    if not folder.is_dir():
        return []
    return sorted(f for f in folder.iterdir()
                  if f.is_file() and f.suffix.lower() in KINDS and not f.name.startswith(("~$", ".")))


def _where(path: Path) -> tuple[int, int, int] | None:
    """(grade, year, term) from the folder names, or None for a file outside the layout."""
    try:
        term_dir, grade_dir = path.parent.name, path.parent.parent.name
    except IndexError:
        return None
    g, t = FOLDER.match(grade_dir), TERM_FOLDER.match(term_dir)
    if not g or not t:
        return None
    return int(g.group(1)), int(t.group(1)), int(t.group(2))


def _state() -> dict:
    s = store.load("drive")
    return s if isinstance(s, dict) else {}


def _decision(rel: str, sha: str, teacher_id: str) -> dict | None:
    entry = _state().get(rel)
    if not entry or entry.get("sha") != sha:
        return None  # never decided, or the file changed after the decision
    return entry.get("decisions", {}).get(teacher_id)


def folders(teacher_id: str, year: int | None = None) -> list[dict]:
    """The teacher's own grade folders, with every term sub-folder and its files.

    The three term folders of `year` are always listed, even when someone has deleted
    the folder itself, so a missing term is seen and not silently skipped.
    """
    year = year or config.today().year
    out = []
    for grade in sorted(school.grades_of(teacher_id)):
        gdir = root() / f"Grade {grade}"
        names = {f"{year} Term {t}" for t in (1, 2, 3)}
        if gdir.is_dir():
            names |= {p.name for p in gdir.iterdir() if p.is_dir() and TERM_FOLDER.match(p.name)}
        terms = []
        for name in sorted(names, reverse=True):
            tdir = gdir / name
            m = TERM_FOLDER.match(name)
            files = []
            for f in _results_files(tdir):
                rel = f.relative_to(root()).as_posix()
                d = _decision(rel, _sha(f), teacher_id)
                files.append({"path": rel, "name": f.name, "size": f.stat().st_size, "kind": KINDS[f.suffix.lower()],
                              "modified": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(timespec="minutes"),
                              "status": d["decision"] if d else "waiting",
                              "decided_by": d.get("name") if d else None, "decided_at": d.get("at") if d else None,
                              "rows_added": d.get("added") if d else None})
            terms.append({"folder": f"Grade {grade}/{name}", "label": name, "year": int(m.group(1)),
                          "term": int(m.group(2)), "exists": tdir.is_dir(), "files": files})
        out.append({"grade": grade, "folder": f"Grade {grade}", "terms": terms})
    return out


def approved_before(teacher_id: str, grade: int, label: str) -> dict | None:
    """The last approval this teacher gave for a file in a term folder, even if the file is gone now."""
    prefix = f"Grade {grade}/{label}/"
    found = [d["decisions"][teacher_id] | {"file": rel.rsplit("/", 1)[-1]}
             for rel, d in _state().items()
             if rel.startswith(prefix) and d.get("decisions", {}).get(teacher_id, {}).get("decision") == "approve"]
    return max(found, key=lambda d: d.get("at", "")) if found else None


def preview(rel: str, teacher_id: str) -> dict:
    """What approving would do, without changing anything."""
    path = _resolve(rel)
    where = _where(path)
    if where is None or where[0] not in school.grades_of(teacher_id):
        raise GateBlocked("This file is not in your class's grade folder.")
    mine = {l["learner_id"] for l in school.learners_of(teacher_id)}
    known = {l["learner_id"] for l in store.load("learners")}
    header, rows = _table(path)
    missing = sorted(NEEDED - set(header))
    counts = {"rows": len(rows), "yours": 0, "other_class": 0, "not_on_list": 0, "not_usable": 0,
              "wrong_term": 0}
    learners, areas, issues = set(), set(), {}
    for row in rows if not missing else []:
        rec, flags = clean_record(row, known)
        if rec is None:
            counts["not_on_list" if any(f["type"] == "unknown_learner" for f in flags) else "not_usable"] += 1
            continue
        if rec["learner_id"] not in mine:
            counts["other_class"] += 1
            continue
        counts["yours"] += 1
        learners.add(rec["learner_id"])
        areas.add(rec["family"])
        if (rec["grade"], rec["year"], rec["term"]) != where:
            counts["wrong_term"] += 1
        for f in flags:
            if f["severity"] == "warn":
                issues[f["type"]] = issues.get(f["type"], 0) + 1
    grade, year, term = where
    return {"path": rel, "name": path.name, "kind": KINDS[path.suffix.lower()], "grade": grade, "year": year, "term": term,
            "missing_columns": missing, "counts": counts, "learners": len(learners),
            "class_size": len(mine), "learning_areas": sorted(areas), "issues": issues,
            "decision": _decision(rel, _sha(path), teacher_id)}


def decide(rel: str, session: str, decision: str, reason: str = "") -> dict:
    """A signed-in class teacher approves or rejects a drive file for their own class."""
    who = auth.resolve(session, kind="human", action="approve")
    if decision not in ("approve", "reject"):
        raise ValueError("Choose approve or reject.")
    info = preview(rel, who["teacher_id"])
    if info["missing_columns"]:
        raise ValueError("The file is missing columns: " + ", ".join(info["missing_columns"]))
    path = _resolve(rel)
    sha = _sha(path)
    if _decision(rel, sha, who["teacher_id"]):
        raise GateBlocked("You have already decided on this version of the file.")
    result = {"decision": decision, "added": 0, "notices": []}
    if decision == "approve":
        if not info["counts"]["yours"]:
            raise GateBlocked("No rows in this file are for your class, so there is nothing to approve.")
        mine = {l["learner_id"] for l in school.learners_of(who["teacher_id"])}
        header, rows = _table(path)
        keep = [r for r in rows if (clean_record(r, mine)[0] or {}).get("learner_id") in mine]
        streams = "_".join(school.streams_of(who["teacher_id"]))
        inbox_name = f"{path.stem}.{streams}.{sha[:8]}.csv"
        config.INBOX.mkdir(parents=True, exist_ok=True)
        with (config.INBOX / inbox_name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
            w.writeheader()
            w.writerows(keep)
        report = tools.ingest_record(inbox_name)
        from . import notify  # here, so the drive module stays importable on its own
        result.update(added=report["added"], message=report["message"], inbox_file=inbox_name,
                      notices=notify.after_ingest(inbox_name))
    entry = _state()
    item = entry.setdefault(rel, {"sha": sha, "decisions": {}})
    if item.get("sha") != sha:
        item.update(sha=sha, decisions={})
    item["decisions"][who["teacher_id"]] = {"decision": decision, "name": who["name"], "at": _now(),
                                            "reason": reason.strip()[:300], "added": result["added"]}
    store.save("drive", entry)
    audit.write_event({"tool": f"drive.{decision}", "actor": who["teacher_id"], "ok": True,
                       "inputs": {"kwargs": {"file": rel}},
                       "output": {"added": result["added"], "notices": len(result["notices"])}})
    if decision == "approve":
        from . import notify
        notify.check_missing()
    return result


def upload(session: str, filename: str, content: bytes, year: int, term: int) -> dict:
    """Save an Excel or CSV results file into the teacher's own grade folder. It waits there for approval."""
    who = auth.resolve(session, kind="human", action="continue")
    grades = sorted(school.grades_of(who["teacher_id"]))
    if not grades:
        raise GateBlocked("You have no class assigned, so there is no folder to upload to.")
    if len(content) > MAX_BYTES:
        raise ValueError("That file is larger than 5 MB.")
    if term not in (1, 2, 3):
        raise ValueError("Choose Term 1, 2 or 3.")
    excel = content[:2] == b"PK"
    if excel:
        header, _ = xlsx.read_bytes(content)
    else:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("Hatua reads Excel (.xlsx) and CSV files. Save the file as .xlsx and try again.") from None
        header = [h.strip() for h in next(csv.reader(io.StringIO(text)), [])]
    missing = sorted(NEEDED - set(header))
    if missing:
        raise ValueError("The file is missing columns: " + ", ".join(missing) +
                         ". Row 1 must hold the column names. Use docs/templates/results_template.xlsx.")
    ext = ".xlsx" if excel else ".csv"
    name = SAFE_NAME.sub("", Path(filename or "results").name).strip()
    stem = Path(name).stem[:60].strip(" .") or "results"
    folder = root() / f"Grade {grades[0]}" / f"{year} Term {term}"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{stem}{ext}"
    n = 2
    while dest.exists():
        if dest.read_bytes() == content:
            break  # the very same file again (for example, put back after it was deleted)
        dest = folder / f"{stem} ({n}){ext}"
        n += 1
    dest.write_bytes(content)
    rel = dest.relative_to(root()).as_posix()
    audit.write_event({"tool": "drive.upload", "actor": who["teacher_id"], "ok": True,
                       "inputs": {"kwargs": {"file": rel}}, "output": {"bytes": len(content)}})
    d = _decision(rel, _sha(dest), who["teacher_id"])
    return {"path": rel, "status": d["decision"] if d else "waiting"}
