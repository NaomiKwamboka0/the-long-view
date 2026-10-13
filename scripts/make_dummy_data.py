"""Generate a SYNTHETIC, deliberately messy CBC learner cohort for Hatua.

No real learner is represented. Names are invented and carry no personal details.
The cohort is one Grade 9 class (Grade 4 in 2021 -> Grade 9 in 2026) at a fictional
public comprehensive school. Messiness is intentional, as the challenge brief asks:
mixed rubric spellings, missing terms, late logging, duplicates, ID typos,
conflicting score/level pairs and attendance gaps.

Run:  python scripts/make_dummy_data.py
Writes: data/raw/*.csv, data/inbox/2026_T3_new_records.csv, data/ground_truth.json
"""
from __future__ import annotations

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 2026
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INBOX = ROOT / "data" / "inbox"

SCHOOL = "Mwangaza Comprehensive School (fictional)"

FIRST_NAMES = [
    ("Achieng", "F"), ("Brian", "M"), ("Cynthia", "F"), ("Dennis", "M"), ("Esther", "F"),
    ("Faith", "F"), ("Kiprono", "M"), ("Halima", "F"), ("Ian", "M"), ("Joy", "F"),
    ("Kevin", "M"), ("Wanjiru", "F"), ("Linet", "F"), ("Moses", "M"), ("Nafula", "F"),
    ("Omondi", "M"), ("Purity", "F"), ("Otieno", "M"), ("Rehema", "F"), ("Samuel", "M"),
    ("Tabitha", "F"), ("Umi", "F"), ("Victor", "M"), ("Chebet", "F"), ("Wycliffe", "M"),
    ("Yvonne", "F"), ("Zawadi", "F"), ("Allan", "M"), ("Brenda", "F"), ("Collins", "M"),
    ("Mutua", "M"), ("Diana", "F"), ("Emmanuel", "M"), ("Fatuma", "F"), ("George", "M"),
    ("Akinyi", "F"), ("Hassan", "M"), ("Imani", "F"), ("Jabari", "M"), ("Baraka", "M"),
]

# Upper primary (Grades 4-6) and junior school (Grades 7-9) learning areas.
PRIMARY_AREAS = ["English", "Kiswahili", "Mathematics", "Science and Technology",
                 "Social Studies", "Creative Arts"]
JUNIOR_AREAS = ["English", "Kiswahili", "Mathematics", "Integrated Science",
                "Social Studies", "Pre-Technical Studies", "Agriculture",
                "Creative Arts and Sports"]
FAMILY = {
    "Science and Technology": "Science", "Integrated Science": "Science",
    "Creative Arts": "Creative Arts", "Creative Arts and Sports": "Creative Arts",
}

# Messy spellings a real export or transcription produces.
AREA_TYPOS = {
    "Mathematics": ["Maths", "Math", "MATHEMATICS"],
    "Kiswahili": ["Kiswahili ", "KISWAHILI", "Kisw."],
    "Integrated Science": ["Int. Science", "Integrated Sci"],
    "Creative Arts and Sports": ["Creative Arts & Sports", "CAS"],
    "Pre-Technical Studies": ["Pre Tech", "Pre-Technical"],
    "Social Studies": ["Social studies", "SST"],
}
LEVEL_SPELLINGS = {
    "EE": ["EE", "Exceeding Expectations", "ee", "E.E", "4", "Exceeding"],
    "ME": ["ME", "Meeting Expectations", "me", "M.E.", "3", "meeting exp"],
    "AE": ["AE", "Approaching Expectations", "ae", "A.E", "2", "Approaching"],
    "BE": ["BE", "Below Expectations", "be", "B.E", "1", "Below Expectation"],
}
LEVELS = ["BE", "AE", "ME", "EE"]  # index + 1 == points
SCORE_BANDS = {"EE": (75, 98), "ME": (50, 74), "AE": (25, 49), "BE": (5, 24)}

TERM_START = {1: (1, 8), 2: (4, 28), 3: (8, 26)}  # (month, day) roughly
TERM_DAYS_OPEN = {1: 64, 2: 68, 3: 44}

TASKS = {
    "Mathematics": ["Fractions task", "Geometry project", "Data handling quiz", "Algebra SBA"],
    "English": ["Composition", "Reading comprehension", "Oral presentation", "Grammar quiz"],
    "Kiswahili": ["Insha", "Ufahamu", "Mazungumzo", "Sarufi"],
    "Science": ["Practical investigation", "Model building", "Science quiz", "Lab report"],
    "Social Studies": ["Map work", "Community project", "Citizenship quiz"],
    "Pre-Technical Studies": ["Technical drawing", "Woodwork project", "Safety quiz"],
    "Agriculture": ["Kitchen garden project", "Soil study", "Agriculture quiz"],
    "Creative Arts": ["Drawing and painting", "Music performance", "Craft project", "PE skills"],
}

# ---- Planted scenarios (ground truth for EVALS) -------------------------------------
PLANTED = {
    "HT-0003": {"desc": "Mathematics declines ME -> AE -> BE from Grade 7 Term 3 onward",
                "expect": [{"type": "decline", "area": "Mathematics"}]},
    "HT-0007": {"desc": "Creative Arts held at EE for many terms; strong Pre-Technical Studies",
                "expect": [{"type": "sustained_strength", "area": "Creative Arts"}]},
    "HT-0012": {"desc": "Kiswahili improves from AE to EE across Grades 7-9",
                "expect": [{"type": "improvement", "area": "Kiswahili"}]},
    "HT-0018": {"desc": "Attendance drops below 70% in 2025 Terms 2-3",
                "expect": [{"type": "attendance_drop", "area": None}]},
    "HT-0024": {"desc": "Joined in Grade 7 Term 2 (2024); no Grade 4-6 records",
                "expect": [{"type": "data_gap", "area": None}]},
    "HT-0031": {"desc": "Science held at EE from Grade 5 onward",
                "expect": [{"type": "sustained_strength", "area": "Science"}]},
    "HT-0036": {"desc": "Many records logged 6+ weeks late",
                "expect": [{"type": "late_logging", "area": None}]},
    "HT-0040": {"desc": "One-off EE in Mathematics among AE results; must NOT become a strength",
                "expect_absent": [{"type": "sustained_strength", "area": "Mathematics"}]},
}


def clip(x: float, lo: float = 1.0, hi: float = 4.0) -> float:
    return max(lo, min(hi, x))


def term_index(grade: int, term: int) -> int:
    return (grade - 4) * 3 + (term - 1)  # 0..17


def planted_level(lid: str, family: str, grade: int, term: int) -> str | None:
    t = term_index(grade, term)
    if lid == "HT-0003" and family == "Mathematics":
        if t < term_index(7, 3):
            return "ME"
        return ["ME", "AE", "AE", "BE", "BE", "BE"][min(t - term_index(7, 3), 5)]
    if lid == "HT-0007" and family in ("Creative Arts",):
        return "EE" if t >= term_index(5, 1) else "ME"
    if lid == "HT-0007" and family == "Pre-Technical Studies":
        return "EE"
    if lid == "HT-0012" and family == "Kiswahili":
        if grade <= 6:
            return "AE"
        return ["AE", "AE", "ME", "ME", "ME", "EE", "EE", "EE"][min(t - term_index(7, 1), 7)]
    if lid == "HT-0031" and family == "Science":
        return "EE" if grade >= 5 else "ME"
    if lid == "HT-0040" and family == "Mathematics":
        return "EE" if (grade, term) == (8, 2) else "AE"
    return None


def iso(d: date) -> str:
    return d.isoformat()


def messy_date(rng: random.Random, d: date) -> str:
    r = rng.random()
    if r < 0.12:
        return d.strftime("%d/%m/%Y")
    if r < 0.15:
        return d.strftime("%d-%m-%y")
    return iso(d)


def main() -> None:
    rng = random.Random(SEED)
    RAW.mkdir(parents=True, exist_ok=True)
    INBOX.mkdir(parents=True, exist_ok=True)

    learners = []
    for i, (name, sex) in enumerate(FIRST_NAMES, start=1):
        lid = f"HT-{i:04d}"
        learners.append({
            "learner_id": lid, "first_name": name, "sex": sex,
            "current_grade": 9, "stream": "9A" if i <= 20 else "9B",
            "joined": "2024-T2" if lid == "HT-0024" else "2021-T1",
            "school": SCHOOL,
        })

    # Latent ability per learner per family, with a gentle trend.
    families = sorted({FAMILY.get(a, a) for a in PRIMARY_AREAS + JUNIOR_AREAS})
    latent = {(l["learner_id"], f): (clip(rng.gauss(2.6, 0.55)), rng.gauss(0, 0.025))
              for l in learners for f in families}

    records: list[dict] = []
    inbox: list[dict] = []
    rid = 0
    # Whole-class gap: Grade 7 Term 2 Kiswahili teacher transferred, no records.
    class_gap = {(7, 2, "Kiswahili")}

    for grade in range(4, 10):
        year = 2021 + (grade - 4)
        areas = PRIMARY_AREAS if grade <= 6 else JUNIOR_AREAS
        for term in (1, 2, 3):
            is_new_export = (grade == 9 and term == 3)
            m, dday = TERM_START[term]
            term_start = date(year, m, dday)
            for l in learners:
                lid = l["learner_id"]
                if lid == "HT-0024" and term_index(grade, term) < term_index(7, 2):
                    continue
                for area in areas:
                    fam = FAMILY.get(area, area)
                    if (grade, term, fam) in class_gap:
                        continue
                    if rng.random() < 0.03:  # random individual gaps
                        continue
                    lvl = planted_level(lid, fam, grade, term)
                    if lvl is None:
                        base, slope = latent[(lid, fam)]
                        val = clip(base + slope * term_index(grade, term) + rng.gauss(0, 0.3))
                        lvl = LEVELS[int(round(val)) - 1]
                    task_d = term_start + timedelta(days=rng.randint(14, 70 if term != 3 else 40))
                    lag = rng.randint(1, 21)
                    if lid == "HT-0036" and rng.random() < 0.6:
                        lag = rng.randint(45, 80)
                    elif rng.random() < 0.04:
                        lag = rng.randint(43, 70)
                    logged = task_d + timedelta(days=lag)
                    lo, hi = SCORE_BANDS[lvl]
                    score: str = str(rng.randint(lo, hi))
                    level_txt = rng.choice(LEVEL_SPELLINGS[lvl]) if rng.random() < 0.35 else lvl
                    if grade <= 6:
                        source = "rubric_sheet_transcribed"
                        if rng.random() < 0.55:
                            score = ""  # rubric sheets often carry the level only
                    else:
                        source = "cba_portal_export"
                    if rng.random() < 0.015:
                        level_txt = ""  # level missing, may be recoverable from score
                    if rng.random() < 0.01:
                        # conflicting score/level pair
                        score = str(rng.randint(10, 30)) if lvl in ("EE", "ME") else str(rng.randint(80, 95))
                    area_txt = area
                    if area in AREA_TYPOS and rng.random() < 0.15:
                        area_txt = rng.choice(AREA_TYPOS[area])
                    lid_txt = lid
                    if rng.random() < 0.01:
                        lid_txt = rng.choice([lid.lower().replace("-", ""), lid.replace("-", " ")])
                    rid += 1
                    rec = {
                        "record_id": f"R-{rid:05d}", "learner_id": lid_txt, "grade": grade,
                        "year": year, "term": term, "learning_area": area_txt,
                        "task": rng.choice(TASKS[fam]), "level": level_txt, "score": score,
                        "task_date": messy_date(rng, task_d),
                        "logged_date": "" if rng.random() < 0.02 else messy_date(rng, logged),
                        "teacher": f"T-{fam[:3].upper()}{1 + (year % 2)}",
                        "source": source,
                    }
                    (inbox if is_new_export else records).append(rec)
                    if not is_new_export and rng.random() < 0.006:
                        records.append(dict(rec))  # exact duplicate row

    # A few rows with an unknown learner and a future-dated task.
    rid += 1
    records.append({"record_id": f"R-{rid:05d}", "learner_id": "HT-0099", "grade": 8, "year": 2025,
                    "term": 1, "learning_area": "English", "task": "Composition", "level": "ME",
                    "score": "61", "task_date": "2025-02-10", "logged_date": "2025-02-20",
                    "teacher": "T-ENG2", "source": "cba_portal_export"})
    rid += 1
    records.append({"record_id": f"R-{rid:05d}", "learner_id": "HT-0010", "grade": 9, "year": 2026,
                    "term": 2, "learning_area": "English", "task": "Grammar quiz", "level": "ME",
                    "score": "58", "task_date": "2026-12-01", "logged_date": "2026-06-30",
                    "teacher": "T-ENG1", "source": "cba_portal_export"})

    # Attendance per learner per term.
    attendance = []
    for grade in range(4, 10):
        year = 2021 + (grade - 4)
        for term in (1, 2, 3):
            if grade == 9 and term == 3:
                continue
            for l in learners:
                lid = l["learner_id"]
                if lid == "HT-0024" and term_index(grade, term) < term_index(7, 2):
                    continue
                if rng.random() < 0.04:
                    continue  # register missing for the term
                opened = TERM_DAYS_OPEN[term] + rng.randint(-3, 3)
                rate = min(1.0, rng.betavariate(18, 1.6))
                if lid == "HT-0018" and (year, term) in {(2025, 2), (2025, 3), (2026, 1)}:
                    rate = rng.uniform(0.52, 0.68)
                attendance.append({"learner_id": lid, "grade": grade, "year": year, "term": term,
                                   "days_present": int(round(opened * rate)), "days_open": opened})

    # Teacher notes (observations). Some in Kiswahili, some without a learning area.
    note_bank = {
        "EE": ["Explains reasoning clearly to the group.", "Finished the task early and helped peers.",
               "Ana ujuzi mzuri sana katika kazi hii.", "Asks deep questions during practicals."],
        "ME": ["Completes work on time.", "Participates well in group work.",
               "Anafanya kazi yake vizuri.", "Steady effort this term."],
        "AE": ["Needs support with multi-step questions.", "Often leaves the task incomplete.",
               "Anahitaji msaada zaidi katika kusoma.", "Hesitant to answer orally."],
        "BE": ["Struggled to start the task without help.", "Did not complete most items.",
               "Anapata shida kubwa katika kazi hii.", "Needs one-to-one support."],
    }
    notes = []
    nid = 0
    by_learner: dict[str, list[dict]] = {}
    for r in records:
        by_learner.setdefault(r["learner_id"], []).append(r)
    for l in learners:
        lid = l["learner_id"]
        recs = [r for r in by_learner.get(lid, []) if r["level"] in LEVELS]
        for r in rng.sample(recs, k=min(len(recs), rng.randint(4, 9))):
            nid += 1
            area = r["learning_area"] if rng.random() > 0.2 else ""
            notes.append({"note_id": f"N-{nid:04d}", "learner_id": lid, "grade": r["grade"],
                          "year": r["year"], "term": r["term"], "learning_area": area,
                          "date": r["task_date"], "teacher": r["teacher"],
                          "text": rng.choice(note_bank[r["level"]])})
    planted_notes = [
        ("HT-0003", 8, 2025, 3, "Mathematics", "Struggles with fraction word problems; avoids the board."),
        ("HT-0003", 9, 2026, 2, "Mathematics", "Asked for extra practice sheets. Ana bidii lakini anachanganyikiwa."),
        ("HT-0007", 8, 2025, 2, "Creative Arts and Sports", "Built a detailed model of the school compound from scrap."),
        ("HT-0007", 9, 2026, 1, "Pre-Technical Studies", "Neat technical drawings; helps classmates with measuring."),
        ("HT-0012", 9, 2026, 1, "Kiswahili", "Insha yake imeboreka sana; anatumia methali vizuri."),
        ("HT-0018", 8, 2025, 2, "", "Absent often this term. Follow up with guardian."),
        ("HT-0031", 8, 2025, 3, "Integrated Science", "Designed his own experiment on plant growth."),
    ]
    for lid, g, y, t, a, text in planted_notes:
        nid += 1
        notes.append({"note_id": f"N-{nid:04d}", "learner_id": lid, "grade": g, "year": y, "term": t,
                      "learning_area": a, "date": f"{y}-{TERM_START[t][0]:02d}-28",
                      "teacher": "T-CLS1", "text": text})

    def write(path: Path, rows: list[dict]) -> None:
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    rng.shuffle(records)  # exports are rarely sorted
    write(RAW / "learners.csv", learners)
    write(RAW / "records_2021_2026.csv", records)
    write(RAW / "attendance.csv", attendance)
    write(RAW / "teacher_notes.csv", notes)
    write(INBOX / "2026_T3_new_records.csv", inbox)
    (ROOT / "data" / "ground_truth.json").write_text(json.dumps(PLANTED, indent=2), encoding="utf-8")
    print(f"learners={len(learners)} records={len(records)} inbox={len(inbox)} "
          f"attendance={len(attendance)} notes={len(notes)}")


if __name__ == "__main__":
    main()
