"""Checks every draft must pass before a teacher can approve it.

1. No labels, pathway or career placement, ranking, or comparison with classmates.
2. Every claim line carries at least one citation, and every citation exists and
   belongs to this learner.
"""
from __future__ import annotations

import re

from . import store

CITATION = re.compile(r"\b([RNA]-[A-Z0-9-]+?)(?=[\],;\s)]|$)")

# Phrases that would turn a profile into a verdict on a child. Kept short and explicit
# so that a reviewer can read the whole rule.
FORBIDDEN = [
    r"\bstem pathway\b", r"\bsocial sciences? pathway\b", r"\barts and sports science pathway\b",
    r"\b(should|must|ought to) (take|choose|join|pursue|study|go into)\b",
    r"\bbest suited\b", r"\bsuited for\b", r"\bcareer\b", r"\bfuture (doctor|engineer|lawyer|teacher|nurse)\b",
    r"\b(gifted|genius|talented|slow learner|weak (learner|student|pupil)|lazy|clever|bright)\b",
    r"\brank(ed|ing|s)?\b", r"\btop (of|in) (the )?class\b", r"\bbottom of\b", r"\bposition \d+\b",
    r"\b(better|worse|smarter|weaker|stronger) than\b", r"\bclassmates?\b", r"\babove average\b",
    r"\bbelow average\b", r"\bpercentile\b",
    # Kiswahili equivalents
    r"\bmwerevu\b", r"\bmzembe\b", r"\bnafasi ya\b", r"\bkuliko wenzake\b", r"\bwanafunzi wengine\b",
    r"\bmkondo wa\b",
]
_FORBIDDEN = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN]


def labels_in(text: str) -> list[str]:
    return [m.group(0) for rx in _FORBIDDEN if (m := rx.search(text))]


def citations(text: str) -> list[str]:
    return CITATION.findall(text)


def check(text: str, learner_id: str) -> list[str]:
    """Return a list of human-readable problems. Empty list means the draft passes."""
    problems: list[str] = []
    if not text.strip():
        return ["The draft is empty. Keep the evidence-based summary before approving."]
    for rx in _FORBIDDEN:
        m = rx.search(text)
        if m:
            problems.append(f"Uses '{m.group(0)}', which labels, places or compares the learner.")
    for line in text.splitlines():
        if line.lstrip().startswith(("-", "•", "*")) and not citations(line):
            problems.append(f"Claim has no citation: '{line.strip()[:80]}'")
    for cid in sorted(set(citations(text))):
        rec = store.get_record(cid)
        if rec is None:
            problems.append(f"Citation {cid} does not exist.")
        elif rec.get("learner_id") != learner_id:
            problems.append(f"Citation {cid} belongs to a different learner.")
    return problems
