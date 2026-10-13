"""The human gate.

`approve` is the ONLY way a draft becomes approved, and it is deliberately not an MCP
tool: the agent has no tool it could use to approve its own work. A named teacher
approves from the command line or the Hatua page (exported, then imported here).

`update_profile` (an MCP tool) refuses to write anything unless an approval exists
whose hash matches the exact text being saved.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import audit, config, guard, store
from .summary import GateBlocked, text_hash


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _approvals() -> list[dict]:
    if not config.APPROVALS_LOG.exists():
        return []
    return [json.loads(l) for l in config.APPROVALS_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]


@audit.audited("approve", actor="teacher")
def approve(draft_id: str, teacher: str, decision: str = "approve", edited_text: str | None = None,
            share_with_guardian: bool = False, reason: str = "", removed_pattern_ids: list[str] | None = None,
            expected_hash: str | None = None) -> dict:
    teacher = (teacher or "").strip()
    if len(teacher) < 3:
        raise GateBlocked("A named teacher must approve. Enter your full name.")
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be 'approve' or 'reject'")
    drafts: list[dict] = store.load("drafts")  # type: ignore[assignment]
    d = next((x for x in drafts if x["draft_id"] == draft_id), None)
    if not d:
        raise ValueError(f"Unknown draft {draft_id}")
    if expected_hash and expected_hash != d["hash"]:
        raise GateBlocked("The draft changed after the teacher saw it. Review the new draft.")
    if d["status"] != "pending_teacher_review":
        raise GateBlocked(f"Draft is already {d['status']}.")
    final = edited_text if edited_text is not None else d["text"]
    if decision == "approve":
        problems = guard.check(final, d["learner_id"])
        if problems:
            raise GateBlocked("Edited text failed safety checks: " + "; ".join(problems))
        if d["audience"] == "guardian" and not share_with_guardian:
            raise GateBlocked("Tick 'share with guardian' to approve a guardian message.")
    entry = {"approval_id": f"AP-{len(_approvals()) + 1:05d}", "draft_id": draft_id,
             "learner_id": d["learner_id"], "audience": d["audience"], "teacher": teacher,
             "decision": decision, "final_hash": text_hash(final), "edited": edited_text is not None,
             "share_with_guardian": share_with_guardian, "reason": reason, "ts": _now()}
    config.LOGS.mkdir(parents=True, exist_ok=True)
    with config.APPROVALS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    d.update(status="approved" if decision == "approve" else "rejected", final_text=final,
             approved_by=teacher, approval_id=entry["approval_id"],
             removed_pattern_ids=removed_pattern_ids or [])
    store.save("drafts", drafts)
    return entry


def update_profile(draft_id: str) -> dict:
    drafts: list[dict] = store.load("drafts")  # type: ignore[assignment]
    d = next((x for x in drafts if x["draft_id"] == draft_id), None)
    if not d:
        raise ValueError(f"Unknown draft {draft_id}")
    if d["status"] != "approved":
        raise GateBlocked(f"Blocked: draft {draft_id} has no teacher approval (status: {d['status']}).")
    ap = next((a for a in _approvals() if a["approval_id"] == d.get("approval_id")), None)
    if not ap or ap["decision"] != "approve" or ap["final_hash"] != text_hash(d["final_text"]):
        raise GateBlocked("Blocked: the approval record does not match this text.")
    config.PROFILES.mkdir(parents=True, exist_ok=True)
    lid = d["learner_id"]
    if d["audience"] == "guardian":
        if not ap["share_with_guardian"]:
            raise GateBlocked("Blocked: the teacher did not approve sharing with the guardian.")
        out = config.PROFILES / f"{lid}_guardian_{d['language']}.txt"
        out.write_text(d["final_text"] + "\n", encoding="utf-8")
        result = {"saved": str(out.relative_to(config.ROOT)), "note": "Ready for the teacher to send. Hatua sends nothing."}
    else:
        path = config.PROFILES / f"{lid}.json"
        profile = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"learner_id": lid, "entries": []}
        if any(e["draft_id"] == draft_id for e in profile["entries"]):
            return {"saved": str(path.relative_to(config.ROOT)), "note": "Already in the profile."}
        profile["entries"].append({"draft_id": draft_id, "approved_by": ap["teacher"], "approved_at": ap["ts"],
                                   "text": d["final_text"], "citations": guard.citations(d["final_text"])})
        path.write_text(json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")
        result = {"saved": str(path.relative_to(config.ROOT)), "entries": len(profile["entries"])}
    d["status"] = "approved"
    d["saved_at"] = _now()
    store.save("drafts", drafts)
    return result
