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
