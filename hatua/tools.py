"""The agent's tools. Each call is written to logs/audit.jsonl.

These are the functions hatua-mcp exposes. There is deliberately no approve tool.
"""
from __future__ import annotations

from pathlib import Path

from . import audit, config, gate, patterns, store, summary


@audit.audited("list_learners")
def list_learners(search: str = "", stream: str = "") -> list[dict]:
    """Class list, filtered by name/ID search and stream. Never sorted by results."""
    q = search.strip().lower()
    return [{"learner_id": l["learner_id"], "first_name": l["first_name"], "stream": l["stream"]}
            for l in store.load("learners")
            if (not q or q in l["first_name"].lower() or q in l["learner_id"].lower())
            and (not stream or l["stream"] == stream)]


@audit.audited("ingest_record")
def ingest_record(file_name: str) -> dict:
    """Clean and add a new CSV export from data/inbox, returning data-quality flags."""
    path = (config.INBOX / Path(file_name).name).resolve()
    if path.parent != config.INBOX.resolve() or not path.exists():
        raise FileNotFoundError(f"{file_name} is not in data/inbox")
    return store.ingest_records(path)


@audit.audited("review_queue")
def review_queue(file_name: str = "", max_learners: int = 3) -> dict:
    """Learners with new records in an export (default: the latest one) who have a pattern still
    going on and no approved draft for it yet. Listed by learner ID, never by results."""
    ingested = list(store.load("ingested"))  # insertion order = ingest order
    if not ingested:
        return {"file": None, "learners": [], "message": "Nothing has been ingested yet."}
    name = Path(file_name).name if file_name else ingested[-1]
    touched = sorted({r["learner_id"] for r in store.load("records") if r.get("file") == name})
    drafts = store.load("drafts")
    queue, skipped = [], 0
    for lid in touched:
        found = patterns.find(lid)
        current = sorted(p["pattern_id"] for p in found["patterns"] if p["current"])
        if not current:
            continue
        done = [d for d in drafts if d["learner_id"] == lid and d["audience"] == "teacher"
                and d["status"] == "approved" and sorted(d["pattern_ids"]) == sorted(
                    p["pattern_id"] for p in found["patterns"])]
        if done:
            skipped += 1
            continue
        queue.append({"learner_id": lid, "first_name": found["first_name"], "current_patterns": len(current)})
    return {"file": name, "learners_with_new_records": len(touched), "already_approved": skipped,
            "waiting": len(queue), "learners": queue[:max(0, int(max_learners))]}


@audit.audited("find_patterns")
def find_patterns(learner_id: str) -> dict:
    """Cited patterns across terms for one learner. No labels, no comparisons."""
    return patterns.find(learner_id)


@audit.audited("get_evidence")
def get_evidence(evidence_id: str) -> dict:
    """Open a cited record (R-), teacher note (N-) or attendance entry (A-)."""
    rec = store.get_record(evidence_id)
    if rec is None:
        raise ValueError(f"No evidence with id {evidence_id}")
    return rec


@audit.audited("draft_summary")
def draft_summary(learner_id: str, audience: str = "teacher", language: str = "en") -> dict:
    """Create a draft for teacher review. Guardian drafts need an approved teacher draft first."""
    return summary.draft(learner_id, audience, language)


@audit.audited("update_profile")
def update_profile(draft_id: str) -> dict:
    """Save an approved draft to the learner's profile. Blocked without a matching teacher approval."""
    return gate.update_profile(draft_id)
