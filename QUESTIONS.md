# Open questions

Questions that arose during the freeze-and-harden plan. Each has a default
answer (what the code does now) and a note of who needs to decide.

Write the answer here when it is settled; do not change the code without
updating the entry.

---

## Q1 (H2): Does a signed-in, logged teacher view satisfy the pathway gate?

**Plan reference:** WP1.2  
**Default:** A signed-in, logged teacher view is treated as a sufficient gate.
Pathway ideas are served to the teacher in the learner payload; the `portal.view_pathways`
audit event records each serve.  
**Question to organisers:** Does a signed-in, logged teacher view satisfy the
requirement for a gate before a pathway suggestion reaches a teacher, or must it
follow an explicit teacher action (e.g. a click-to-reveal button)?  
**If organisers say "explicit action":** Switch to click-to-reveal (the payload
omits `pathways` until a second call). This is a small change.  
**Owner:** Moses to send this question. Record answer below.  
**Answer:** *(pending)*

---

## Q2 (H8): Can the entry keep one stated theme while pathway ideas are prominent?

**Plan reference:** WP0, WP-P (P6)  
**Default:** Entry is described under *Longitudinal strength tracking*. Pathway
guidance is described as how a teacher uses the longitudinal profile, not as a
second theme.  
**Question to organisers:** Can the entry keep one stated theme while pathway
ideas are a prominent feature? Can the theme be restated?  
**Owner:** Moses  
**Answer:** *(pending)*

---

## Q3 (H1): Single theme wording

**Plan reference:** WP0, `docs/FROZEN.md`  
**Default:** *Longitudinal strength tracking* with *Plain-language reporting*
as sub-theme.  
**Decision:** Moses and Naomi to confirm or change this wording.  
**Answer:** *(pending)*

---

## Q4: Deadline — do commits after the stated deadline count?

**Plan reference:** WP0  
**Question to organisers:** How do you treat commits made after the stated
challenge deadline? Is the entry judged at a specific tag or at a specific
date/time?  
**Owner:** Moses  
**Answer:** *(pending)*

---

## Q5 (Windows CI): `hashlib.scrypt` and `hashlib.pbkdf2_hmac` absent on Python 3.14 Windows

**Found during:** WP0 baseline  
**Fact:** Python 3.14.6 on Windows (this machine, Moses's laptop) ships without
OpenSSL. Both `hashlib.scrypt` and `hashlib.pbkdf2_hmac` are absent.
`hashlib.sha256` and `hmac` are always available.  
**Fix applied (chore/freeze-and-harden, WP0 commit):** `hatua/auth.py` now
detects which KDF is available and falls back through three paths:
1. `scrypt` (Linux/macOS with OpenSSL) — preferred
2. `hashlib.pbkdf2_hmac` (Windows with OpenSSL, e.g. most pre-3.14 builds)
3. Pure-Python PBKDF2-HMAC-SHA256 using `hmac` + `hashlib.sha256` (this machine)

The hash is prefixed (`scrypt:…` or `pbkdf2:…`) so the right algorithm is
used on verify. The pure-Python path uses 50k iterations (slower to brute-force
than plain SHA-256; slower to run than scrypt/pbkdf2_hmac but tolerable on a
local machine).  
**No action needed** unless Naomi's machine also runs Python 3.14 without
OpenSSL — in which case the same fallback applies automatically.
