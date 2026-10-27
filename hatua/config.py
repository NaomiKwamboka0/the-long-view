"""Paths and CBC constants shared across Hatua."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("HATUA_HOME", Path(__file__).resolve().parent.parent))
DATA = ROOT / "data"
RAW = DATA / "raw"
INBOX = DATA / "inbox"
STORE = ROOT / "store"
PROFILES = ROOT / "profiles"
LOGS = ROOT / "logs"
UI = ROOT / "ui"

AUDIT_LOG = LOGS / "audit.jsonl"
APPROVALS_LOG = LOGS / "approvals.jsonl"
PRIVATE = DATA / "private"  # real-to-pseudonymous ID maps; git-ignored


def require_auth() -> bool:
    """Sign-in for the approval gate is OFF by default. HATUA_REQUIRE_AUTH=1 switches it on."""
    return os.environ.get("HATUA_REQUIRE_AUTH", "").strip().lower() in {"1", "true", "yes", "on"}


def today() -> date:
    """Override with HATUA_TODAY=YYYY-MM-DD for reproducible runs and evals."""
    v = os.environ.get("HATUA_TODAY")
    return date.fromisoformat(v) if v else date.today()


# CBC rubric levels. Points follow the 4-level classroom rubric (BE=1 ... EE=4).
LEVELS = ["BE", "AE", "ME", "EE"]
LEVEL_POINTS = {lvl: i + 1 for i, lvl in enumerate(LEVELS)}
LEVEL_NAMES = {
    "EE": "Exceeding Expectations", "ME": "Meeting Expectations",
    "AE": "Approaching Expectations", "BE": "Below Expectations",
}
LEVEL_NAMES_SW = {
    "EE": "Kuzidi Matarajio", "ME": "Kufikia Matarajio",
    "AE": "Kukaribia Matarajio", "BE": "Chini ya Matarajio",
}
# Assumed score bands for converting a percentage to a rubric level when the level
# is missing. Documented as an assumption in ARCHITECTURE.md.
SCORE_BANDS = [(75, "EE"), (50, "ME"), (25, "AE"), (0, "BE")]

# Learning areas change name between upper primary and junior school, so Hatua
# follows a learner through a "family" of related areas.
AREA_ALIASES = {
    "english": "English", "kiswahili": "Kiswahili", "kisw.": "Kiswahili", "kisw": "Kiswahili",
    "mathematics": "Mathematics", "maths": "Mathematics", "math": "Mathematics",
    "science and technology": "Science and Technology",
    "integrated science": "Integrated Science", "int. science": "Integrated Science",
    "integrated sci": "Integrated Science",
    "social studies": "Social Studies", "sst": "Social Studies",
    "pre-technical studies": "Pre-Technical Studies", "pre tech": "Pre-Technical Studies",
    "pre-technical": "Pre-Technical Studies",
    "agriculture": "Agriculture",
    "creative arts": "Creative Arts",
    "creative arts and sports": "Creative Arts and Sports",
    "creative arts & sports": "Creative Arts and Sports", "cas": "Creative Arts and Sports",
}
AREA_FAMILY = {
    "Science and Technology": "Science", "Integrated Science": "Science",
    "Creative Arts": "Creative Arts", "Creative Arts and Sports": "Creative Arts",
}
FAMILY_SW = {
    "Mathematics": "Hisabati", "English": "Kiingereza", "Kiswahili": "Kiswahili",
    "Science": "Sayansi", "Social Studies": "Masomo ya Kijamii",
    "Pre-Technical Studies": "Masomo ya Awali ya Ufundi", "Agriculture": "Kilimo",
    "Creative Arts": "Sanaa Bunifu na Michezo",
}

LATE_LOGGING_DAYS = 42  # six weeks between task and upload


def family_of(area: str) -> str:
    return AREA_FAMILY.get(area, area)


def term_ordinal(grade: int, term: int) -> int:
    """Grade 4 Term 1 -> 0. Lets Hatua compare terms across years."""
    return (int(grade) - 4) * 3 + (int(term) - 1)


def term_label(grade: int, term: int) -> str:
    return f"Grade {grade} Term {term}"
