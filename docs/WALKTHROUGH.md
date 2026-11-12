# Hatua — Walkthrough notes

Each work package in the freeze-and-harden plan adds a note here: what changed,
where, why, and how to demonstrate it. Keep each note under 15 lines. These
notes are for Moses to use in the live review.

---

## WP0 — Sync, freeze, tag `pre-hardening`

**What changed:** Three files added; one file fixed.

- `docs/FROZEN.md` — inventory of every file and module, marked **core** or
  **supporting**. Pathway ideas are core. The theme is recorded as
  *Longitudinal strength tracking*.
- `QUESTIONS.md` — open questions that need human decisions or organiser
  answers before the demo.
- `docs/WALKTHROUGH.md` — this file.
- `hatua/auth.py` — fixed `_hash()` to fall back gracefully when `hashlib.scrypt`
  and `hashlib.pbkdf2_hmac` are both absent (Python 3.14 on Windows without
  OpenSSL). Uses a pure-stdlib PBKDF2-HMAC-SHA256.

**Why this way:** Python 3.14.6 on Windows (Moses's laptop) ships without
OpenSSL. All auth tests failed with `AttributeError: module 'hashlib' has no
attribute 'scrypt'`. The fix detects capability at import time and falls back
through three paths, leaving the behaviour identical on Linux/macOS (where
Naomi runs the agent).

**How to demonstrate:** `python -m hatua teacher-add --id demo --name "Demo Teacher"`
then `python -m hatua verify-log`. On Windows the PIN is hashed with
`pbkdf2:…`; on Linux/macOS it uses `scrypt:…`. Both produce the same
sign-in experience.

---


## WP1 & WP-P — Hard-rule gaps and pathway pillar protection

**What changed:** Hard boundary defenses added across assistant, audit, drive, and portal.
- `hatua/assistant.py`: `RESULT_CLAIM` requires concrete citations for all performance claims. Prescription regex expanded with 8 probe phrases. Context only includes pathway evidence if explicitly requested. Model is bypassed for pathway questions (P1) to prevent hallucinations.
- `hatua/audit.py` & `hatua/portal.py`: Auditing wired across all portal access (`portal.login`, `portal.logout`, `portal.view_class`, `portal.view_learner`, `portal.view_evidence`, `portal.view_pathways`). Secrets (PIN, CSRF, session tokens) scrubbed.
- `ui/portal.html` & `tests/test_portal_xss.cjs`: Complete HTML escaping for learner details, calendar, and evidence dialogs.
- `hatua/drive.py`: Traversal characters stripped, uploaded filenames bounded to 60 chars.

**Why this way:** Ensures Kenya CBC senior school pathway recommendations never hallucinate directive commands ("should take STEM"), while preserving tamper-evident hash chaining.

**How to demonstrate:** Run `python -m pytest tests/test_school_portal.py` (23 tests pass) and `npm run test:ui` (includes portal XSS audit checks).
