"""Checks every draft must pass before a teacher can approve it.

1. No labels, pathway, track, career or course suggestions, no ranking, and no
   comparison with classmates.
2. Every sentence carries at least one citation, and every citation exists and
   belongs to this learner. Only lines that the templates write themselves are exempt.

Text is normalised before matching, so punctuation, doubled spaces and hyphens do not
help a draft slip past a rule. This is a safety net, not a proof: a phrase list can
always be phrased around, and the teacher's own reading is the real control.
"""
from __future__ import annotations

import re
import unicodedata

from . import store

CITATION = re.compile(r"\b([RNA]-[A-Z0-9-]+?)(?=[\],;\s)]|$)")

# Patterns are matched against normalised text: NFKC, lowercase, and runs of whitespace,
# hyphens and underscores collapsed to one space. Bare words that appear in legitimate
# sentences (for example the standalone word "track") are deliberately not blocked.
FORBIDDEN = [
    # pathway, track, career and course suggestions
    r"\bpathways?\b", r"\bsciences? track\b", r"\barts? track\b", r"\btechnical track\b",
    r"\bstem\b", r"\bsteam (pathway|track)\b", r"\btrack (of study|choice)\b",
    r"\b(fit|suited|right|ideal) for (the )?(field|career|job|profession|engineering"
    r"|medicine|law|science|arts|business|teaching)\b",
    r"\bsuited to\b",
    r"\bshould consider (a |the )?(career|path|pathway|track|course|field|subject|studying"
    r"|taking|pursuing|engineering|medicine|law|science|arts|business|teaching)\b",
    r"\b(should|must|ought to) (take|choose|join|pursue|study|go into)\b",
    r"\bcareers?\b", r"\bcourse (choice|selection)\b",
    # ranking and comparison
    r"\btop (\d+|ten|five|performers?|of the class|in the class)\b", r"\boutperform(s|ed|ing)?\b",
    r"\brest of the class\b", r"\bamong the (best|top)\b", r"\brank(ed|ing|s)?\b",
    r"\bbottom of\b", r"\bposition \d+\b", r"\bclassmates?\b", r"\babove average\b",
    r"\bbelow average\b", r"\bpercentile\b",
    r"\b(better|worse|smarter|weaker|stronger) than\b",
    # trait labels
    r"\bnatural (leader|talent|genius|mathematician|scientist|artist|writer|athlete|speaker)\b",
    r"\b(gifted|talented|genius|slow learner|weak (learner|student|pupil)|lazy|clever|bright)\b",
    r"\bbest suited\b",
    # Kiswahili equivalents  # NEEDS NATIVE-SPEAKER REVIEW
    r"\bkuliko wenzake\b", r"\bkuliko wanafunzi wengine\b", r"\bkipanga\b", r"\bmwerevu\b",
    r"\bmzembe\b", r"\bnafasi ya\b", r"\bmkondo wa\b", r"\bwanafunzi wengine\b",
]
_FORBIDDEN = [re.compile(p) for p in FORBIDDEN]

# Lines the templates write by themselves, with no claim about the learner in them.
# Derived from what hatua/summary.py actually emits: if a template line changes, change
# it here too, or the draft will fail its own check (the regression test says so loudly).
TEMPLATE_LINES = [
    r"hatua draft for the class teacher:.+",
    r"records reviewed: \d+ assessment records,.+",
    r"what the records show:",
    r"no pattern held across enough terms to report\. this is not a judgement on the learner\.",
    r"a teacher note from .+ uses labelling or comparison words, so it is not quoted here\. "
    r"open it to read it\..*",
    r"check before relying on this:",
    r"note: .+",
    r"this is a draft for the class teacher to check\. .+",
    r"hello\. this is a short update about .+",
    r"habari\. huu ni ujumbe mfupi kuhusu masomo ya .+",
    r"please contact the class teacher with any questions\.",
    r"tafadhali wasiliana na mwalimu wa darasa ukiwa na swali lolote\.",
]
_TEMPLATE = [re.compile(f"^{p}$") for p in TEMPLATE_LINES]

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
# A trailing citation that the templates put on its own, e.g. " [R-00012, R-00013]" or
# " (Ref: R-00012)". It belongs to the sentence before it, so it is merged back rather
# than counted as a sentence of its own.
_TRAILING_CITATION = re.compile(r"^[(\[]\s*[^)\]]*[)\]]$")


def normalise(text: str) -> str:
    """Lowercase and flatten the text, so spacing and punctuation cannot dodge a rule."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[_\-–—]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def labels_in(text: str) -> list[str]:
    flat = normalise(text)
    return [m.group(0) for rx in _FORBIDDEN if (m := rx.search(flat))]


def citations(text: str) -> list[str]:
    return CITATION.findall(text)


def is_template_line(line: str) -> bool:
    flat = normalise(line)
    return any(rx.match(flat) for rx in _TEMPLATE)


def sentences(line: str) -> list[str]:
    """Split a line into sentences, keeping a trailing citation group with its claim."""
    parts = _SENTENCE.split(line.strip())
    merged: list[str] = []
    for part in parts:
        if merged and _TRAILING_CITATION.match(part) and CITATION.search(part):
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return [p for p in merged if p]


def uncited(line: str) -> str | None:
    """The first sentence of the run at the end of a line that no citation covers.

    The templates write a claim that runs over two sentences and cite it once at the end
    ("2 records disagree. Their terms are excluded until corrected. [R-…]"). So a citation
    covers the sentences before it on the same line, and what fails is a line that ends on
    a sentence with no citation behind it. That is the hole this closes: prose that carries
    no evidence anywhere.
    """
    pending: str | None = None
    for sentence in sentences(line):
        if CITATION.search(sentence):
            pending = None
        elif pending is None:
            pending = sentence
    return pending


def _evidence_index() -> dict[str, dict]:
    """Every citable record, note and attendance entry, read once per check.

    Calling store.get_record() for each citation re-read the whole records file each time,
    which made a full-class regression test take minutes. The data is the same either way.
    """
    index: dict[str, dict] = {}
    for name, key in (("records", "record_id"), ("notes", "note_id"), ("attendance", "attendance_id")):
        for row in store.load(name):
            index[row[key]] = row
    return index


def check(text: str, learner_id: str) -> list[str]:
    """Return a list of human-readable problems. Empty list means the draft passes."""
    problems: list[str] = []
    if not text.strip():
        return ["The draft is empty. Keep the evidence-based summary before approving."]
    flat = normalise(text)
    for rx in _FORBIDDEN:
        m = rx.search(flat)
        if m:
            problems.append(f"Uses '{m.group(0)}', which labels, places or compares the learner.")
    for line in text.splitlines():
        if not line.strip() or is_template_line(line):
            continue
        if (first := uncited(line)) is not None:
            problems.append(f"Claim has no citation: '{first.strip()[:80]}'")
    index = _evidence_index()
    for cid in sorted(set(citations(text))):
        rec = index.get(cid)
        if rec is None:
            problems.append(f"Citation {cid} does not exist.")
        elif rec.get("learner_id") != learner_id:
            problems.append(f"Citation {cid} belongs to a different learner.")
    return problems
