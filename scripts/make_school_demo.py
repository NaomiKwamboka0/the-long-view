"""Generate a SYNTHETIC whole-school demo for the Hatua teacher portal.

No real learner, teacher or school is represented. Everything is invented.

    python scripts/make_school_demo.py [HOME]        (default HOME: ./demo_school)

The demo is a separate Hatua home, so the Grade 9 class used by the tests and
evaluations is not changed. It holds:

* Grades 4 to 8: one class each (streams 4A to 8A), with records from the year each
  class was in Grade 4 up to 2026.
* Grade 9: the existing class (streams 9A and 9B), copied from data/raw unchanged.
* One class teacher per stream, each with a member number (M-4001 ... M-9002).
* A school drive: school_drive/Grade N/2026 Term T/*.xlsx, the way a school's shared
  drive is divided into folders, with one Excel results sheet per class per term.
  Files there are NOT in Hatua until the class teacher approves them in the portal.
  Term 1 and Term 2 are approved at setup, through the real approval gate.

Practice parents (same PIN; P-100003 has a one-time PIN): P-100001 sees Achieng
(Grade 9, pathway ideas shared), P-100002 sees two children in Grades 4 and 8.

Planted situations, so every feature has something to show:

    Any grade  Delete a Term 1 or Term 2 Excel file from the drive: that class's
             teacher is told the file is gone.
    Grade 4  Term 3 already approved. Wanjiku (HT-0405) dropped in Kiswahili in Term 3.
    Grade 5  Term 3 file waiting for the teacher's approval.
    Grade 6  Term 3 file waiting. Inside it: Kamau (HT-0603) falls two levels in
             Mathematics, and Atieno (HT-0607) completes a slow decline in English.
    Grade 7  NO Term 3 file yet: the Grade 7 teacher is told it is overdue.
             A ready file is in samples/ to try the upload.
    Grade 8  Term 3 file waiting. Inside it: Nyokabi (HT-0805) falls in Science.
    Grade 9  Term 3 file waiting (the existing 2026_T3_new_records.csv).
"""
from __future__ import annotations

import csv
import json
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from hatua import xlsx  # noqa: E402 - standard library only

SEED = 4026
SCHOOL = "Mwangaza Comprehensive School (fictional)"
YEAR = 2026
DEMO_TODAY = "2026-11-04"  # after Term 3 closed (23 Oct 2026), so Term 3 results are due
DEMO_PIN = "246810"        # practice accounts only; printed on the demo login page

PRIMARY_AREAS = ["English", "Kiswahili", "Mathematics", "Science and Technology",
                 "Social Studies", "Creative Arts"]
JUNIOR_AREAS = ["English", "Kiswahili", "Mathematics", "Integrated Science",
                "Social Studies", "Pre-Technical Studies", "Agriculture",
                "Creative Arts and Sports"]
FAMILY = {"Science and Technology": "Science", "Integrated Science": "Science",
          "Creative Arts": "Creative Arts", "Creative Arts and Sports": "Creative Arts"}
LEVELS = ["BE", "AE", "ME", "EE"]
SCORE_BANDS = {"EE": (75, 98), "ME": (50, 74), "AE": (25, 49), "BE": (5, 24)}
SPELLINGS = {"EE": ["EE", "Exceeding Expectations", "ee"], "ME": ["ME", "Meeting Expectations", "me"],
             "AE": ["AE", "Approaching Expectations", "ae"], "BE": ["BE", "Below Expectations", "be"]}
TERM_START = {1: (1, 8), 2: (4, 28), 3: (8, 26)}
TERM_DAYS_OPEN = {1: 64, 2: 68, 3: 44}
TASKS = {
    "Mathematics": ["Fractions task", "Geometry project", "Data handling quiz", "Measurement task"],
    "English": ["Composition", "Reading comprehension", "Oral presentation", "Grammar quiz"],
    "Kiswahili": ["Insha", "Ufahamu", "Mazungumzo", "Sarufi"],
    "Science": ["Practical investigation", "Model building", "Science quiz"],
    "Social Studies": ["Map work", "Community project", "Citizenship quiz"],
    "Pre-Technical Studies": ["Technical drawing", "Woodwork project", "Safety quiz"],
    "Agriculture": ["Kitchen garden project", "Soil study", "Agriculture quiz"],
    "Creative Arts": ["Drawing and painting", "Music performance", "Craft project", "PE skills"],
}
NAMES = {
    4: ["Amani", "Baraka", "Chiku", "Daudi", "Ekaru", "Furaha", "Gathoni", "Hamisi", "Imara", "Jelimo",
        "Kendi", "Lemayian"],
    5: ["Makena", "Nekesa", "Odera", "Pendo", "Rotich", "Sanaipei", "Tumaini", "Uhuru", "Wairimu",
        "Yusuf", "Zuri", "Adhiambo"],
    6: ["Biko", "Cherono", "Kamau", "Dalila", "Ewoi", "Fanaka", "Atieno", "Habiba", "Ibrahim", "Jepkosgei",
        "Kioko", "Lulu"],
    7: ["Mumbi", "Nasimiyu", "Onyango", "Penina", "Ruto", "Saida", "Tito", "Ushindi", "Wafula", "Yatich",
        "Zainabu", "Auma"],
    8: ["Barasa", "Chelangat", "Dida", "Eunice", "Nyokabi", "Githinji", "Hadija", "Jomo", "Kagwiria",
        "Langat", "Mwanaisha", "Njoroge"],
}
NAMES[4][4] = "Wanjiku"  # HT-0405, planted below
TEACHERS = [  # member number, invented name, stream
    ("M-4001", "Grace Wambui", "4A"), ("M-5001", "Peter Otieno", "5A"), ("M-6001", "Mary Njeri", "6A"),
    ("M-7001", "John Kiprop", "7A"), ("M-8001", "Ruth Mwende", "8A"),
    ("M-9001", "Daniel Mutiso", "9A"), ("M-9002", "Agnes Chepkoech", "9B"),
]
# Which grades have a Term 3 file on the drive, and which are already approved.
TERM3_ON_DRIVE = {4: "approved", 5: "waiting", 6: "waiting", 8: "waiting", 9: "waiting"}  # 7: missing
# This practice teacher signs in with a one-time PIN and must choose their own PIN first.
FIRST_SIGN_IN = ["M-5001"]
# Practice parents. Each sees only the children listed. Lucy has two children in two classes.
# Samuel has a one-time PIN, like M-5001. Achieng's teacher opens her pathway ideas at setup,
# so Rose can see them; every other learner's pathway ideas stay closed.
PARENTS = [
    {"parent_id": "P-100001", "name": "Rose Akinyi", "relation": "Mother", "children": ["HT-0001"],
     "teacher_id": "M-9001"},
    {"parent_id": "P-100002", "name": "Lucy Wanjiru", "relation": "Mother", "children": ["HT-0405", "HT-0805"],
     "teacher_id": "M-4001"},
    {"parent_id": "P-100003", "name": "Samuel Mwangi", "relation": "Father", "children": ["HT-0603"],
     "teacher_id": "M-6001", "one_time": True},
]
OPEN_PATHWAYS = [("M-9001", "HT-0001")]


def results_name(grade: int, term: int) -> str:
    return f"Grade {grade} Term {term} {YEAR} results.xlsx"


def tindex(grade: int, term: int) -> int:
    return (grade - 4) * 3 + (term - 1)


def planted(lid: str, fam: str, grade: int, term: int) -> str | None:
    """Fixed levels for the planted learners. None means: use the learner's usual level."""
    t = tindex(grade, term)
    if lid == "HT-0405" and fam == "Kiswahili":
        return {1: "ME", 2: "ME", 3: "BE"}[term]
    if lid == "HT-0603" and fam == "Mathematics":
        return "BE" if (grade, term) == (6, 3) else "ME"
    if lid == "HT-0607" and fam == "English":
        return ["EE", "EE", "EE", "EE", "ME", "ME", "ME", "AE", "AE"][t]
    if lid == "HT-0805" and fam == "Science":
        return "AE" if (grade, term) == (8, 3) else "EE"
    if lid == "HT-0704" and fam == "Mathematics":
        return "BE" if (grade, term) == (7, 3) else "ME"
    return None


def make_cohort(rng: random.Random, grade_now: int, rid: int, nid: int):
    stream = f"{grade_now}A"
    learners = [{"learner_id": f"HT-{grade_now * 100 + i:04d}", "first_name": name,
                 "sex": "F" if i % 2 else "M", "current_grade": grade_now, "stream": stream,
                 "joined": f"{YEAR - (grade_now - 4)}-T1", "school": SCHOOL}
                for i, name in enumerate(NAMES[grade_now], start=1)]
    families = sorted({FAMILY.get(a, a) for a in PRIMARY_AREAS + JUNIOR_AREAS})
    usual = {(l["learner_id"], f): rng.gauss(2.7, 0.5) for l in learners for f in families}
    history, this_year, attendance, notes = [], {1: [], 2: [], 3: []}, [], []
    for grade in range(4, grade_now + 1):
        year = YEAR - (grade_now - grade)
        areas = PRIMARY_AREAS if grade <= 6 else JUNIOR_AREAS
        for term in (1, 2, 3):
            start = date(year, *TERM_START[term])
            for l in learners:
                lid = l["learner_id"]
                for area in areas:
                    fam = FAMILY.get(area, area)
                    lvl = planted(lid, fam, grade, term)
                    if lvl is None:
                        if rng.random() < 0.03:
                            continue  # a missing record, as in real exports
                        lvl = LEVELS[int(round(max(1, min(4, usual[(lid, fam)] + rng.gauss(0, 0.17))))) - 1]
                    task_d = start + timedelta(days=rng.randint(14, 40 if term == 3 else 60))
                    logged = task_d + timedelta(days=rng.randint(45, 60) if rng.random() < 0.03
                                                else rng.randint(1, 18))
                    lo, hi = SCORE_BANDS[lvl]
                    rid += 1
                    row = {"record_id": f"R-{rid:05d}", "learner_id": lid, "grade": grade, "year": year,
                           "term": term, "learning_area": area, "task": rng.choice(TASKS[fam]),
                           "level": rng.choice(SPELLINGS[lvl]) if rng.random() < 0.2 else lvl,
                           "score": "" if (grade <= 6 and rng.random() < 0.5) else str(rng.randint(lo, hi)),
                           "task_date": task_d.isoformat(), "logged_date": logged.isoformat(),
                           "teacher": f"T-{fam[:3].upper()}{grade}",
                           "source": "rubric_sheet_transcribed" if grade <= 6 else "cba_portal_export"}
                    if year == YEAR:
                        this_year[term].append(row)  # arrives as an Excel sheet on the school drive
                    else:
                        history.append(row)
            if year == YEAR and term == 3:
                continue  # this term's register arrives with the Term 3 file
            for l in learners:
                opened = TERM_DAYS_OPEN[term] + rng.randint(-2, 2)
                rate = min(1.0, rng.betavariate(18, 1.5))
                attendance.append({"learner_id": l["learner_id"], "grade": grade, "year": year, "term": term,
                                   "days_present": int(round(opened * rate)), "days_open": opened})
    bank = {"EE": "Explains reasoning clearly to the group.", "ME": "Completes work on time.",
            "AE": "Needs support with multi-step questions.", "BE": "Needs one-to-one support."}
    noted = history + this_year[1] + this_year[2]
    for r in rng.sample(noted, k=min(len(noted), len(learners) * 3)):
        nid += 1
        notes.append({"note_id": f"N-{nid:04d}", "learner_id": r["learner_id"], "grade": r["grade"],
                      "year": r["year"], "term": r["term"], "learning_area": r["learning_area"],
                      "date": r["task_date"], "teacher": r["teacher"],
                      "text": bank[r["level"] if r["level"] in bank else "ME"]})
    return learners, history, this_year, attendance, notes, rid, nid


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main(home: Path) -> None:
    rng = random.Random(SEED)
    if home.exists():
        shutil.rmtree(home)
    raw = home / "data" / "raw"
    drive = home / "school_drive"

    # Grade 9: the existing synthetic class, unchanged.
    learners = read(REPO / "data" / "raw" / "learners.csv")
    records = read(REPO / "data" / "raw" / "records_2021_2026.csv")
    attendance = read(REPO / "data" / "raw" / "attendance.csv")
    notes = read(REPO / "data" / "raw" / "teacher_notes.csv")
    rid = max(int(r["record_id"][2:]) for r in records if r["record_id"][2:].isdigit()) + 1000
    nid = max(int(n["note_id"][2:]) for n in notes) + 100
    is_now = lambda r, term: str(r["year"]) == str(YEAR) and str(r["term"]) == str(term)  # noqa: E731
    sheets = {9: {1: [r for r in records if is_now(r, 1)], 2: [r for r in records if is_now(r, 2)],
                  3: read(REPO / "data" / "inbox" / "2026_T3_new_records.csv")}}
    records = [r for r in records if str(r["year"]) != str(YEAR)]

    for g in (4, 5, 6, 7, 8):
        l, hist, now, att, nts, rid, nid = make_cohort(rng, g, rid, nid)
        learners += l
        records += hist
        attendance += att
        notes += nts
        sheets[g] = now

    write(raw / "learners.csv", learners)
    write(raw / "records_2021_2026.csv", records)
    write(raw / "attendance.csv", attendance)
    write(raw / "teacher_notes.csv", notes)
    write(raw / "teacher_assignments.csv",
          [{"teacher_id": t, "role": "class_teacher", "streams": s, "subjects": ""} for t, _, s in TEACHERS])

    # The school drive: one folder per grade, one sub-folder per term, one Excel sheet per term.
    for g in range(4, 10):
        for term in (1, 2, 3):
            folder = drive / f"Grade {g}" / f"{YEAR} Term {term}"
            folder.mkdir(parents=True, exist_ok=True)
            if term < 3 or g in TERM3_ON_DRIVE:
                xlsx.write(folder / results_name(g, term), sheets[g][term], sheet_name=f"Grade {g} Term {term}")
    xlsx.write(home / "samples" / results_name(7, 3), sheets[7][3], sheet_name="Grade 7 Term 3")

    def teachers_of(g: int) -> list[str]:
        return [t for t, _, s in TEACHERS if s.startswith(str(g))]

    # Setup approves these through the real drive gate, signed in as each class teacher.
    # "earlier": approved earlier in the year, so its learner alerts are old news in November.
    approved = [{"teacher_id": t, "file": f"Grade {g}/{YEAR} Term {term}/{results_name(g, term)}", "earlier": True}
                for term in (1, 2) for g in range(4, 10) for t in teachers_of(g)]
    approved += [{"teacher_id": t, "file": f"Grade {g}/{YEAR} Term 3/{results_name(g, 3)}"}
                 for g, st in TERM3_ON_DRIVE.items() if st == "approved" for t in teachers_of(g)]
    demo = {"today": DEMO_TODAY, "pin": DEMO_PIN, "school": SCHOOL,
            "teachers": [{"teacher_id": t, "name": n, "stream": s} for t, n, s in TEACHERS],
            "first_sign_in": FIRST_SIGN_IN, "already_approved": approved,
            "parents": PARENTS, "open_pathways": OPEN_PATHWAYS}
    (home / "demo.json").write_text(json.dumps(demo, indent=2), encoding="utf-8")
    shutil.copytree(REPO / "data" / "calendar", home / "data" / "calendar")
    print(f"school demo: {len(learners)} learners in Grades 4-9, {len(records)} history records, "
          f"{len(TEACHERS)} class teachers -> {home}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO / "demo_school")
