# Hatua Developer Handoff & Continuity Guide

**Date:** 12 November 2026  
**Active Branch:** `chore/freeze-and-harden`  
**Target Branch:** `main`  
**Project:** Hatua — Longitudinal Strength Tracking & Plain-Language Reporting for Kenya CBC  
**Challenge Track:** Agentic Africa Challenge (Education Track: "Education: The Long View")  
**Challenge URL:** https://agentic-africa-challenge.lovable.app/tracks/education  
**Author / Devs:** Moses Mungai & Naomi Kwamboka Onyancha  

---

## 1. What Hatua Is & The Core Mission

Hatua ("Steps" in Kiswahili) is an AI-assisted teacher copilot for the Kenyan Competency Based Curriculum (CBC).
- **Core Theme:** Longitudinal strength tracking across Grades 4–9 (primary through junior school), helping teachers spot sustained strengths, notice early struggles before they become chronic, communicate in plain language with families (English & Kiswahili), and prepare evidence for Grade 9 senior school pathway conversations (STEM, Social Sciences, Arts and Sports Science).
- **Local & Private:** Runs 100% locally on the teacher's laptop (Ollama / Qwen 2.5 7B). Zero student data leaves the machine. No external cloud API calls.
- **Strict Boundary Controls:**
  - **Deterministic Gates:** Hard python rules block AI free-text hallucinations.
  - **Zero Labeling / Ranking:** AI never orders or labels children (e.g. "gifted", "slow", "smartest in class", "belongs in STEM").
  - **Evidence Citing:** Every claim must carry a concrete, verifiable citation `[R-xxxxx]` from the teacher's own class records.
  - **Human-in-the-Loop:** Suggestions reach a learner or parent only after explicit class teacher review and approval.
  - **Tamper-Evident Audit Chains:** SHA-256 hash-chained JSONL logs (`logs/audit.jsonl`, `logs/approvals.jsonl`) record every action and approval.

---

## 2. Freeze & Harden Plan: Current Status

The team agreed to follow `# Hatua: freeze, reconcile, harden, explain`.
**Freeze Rule:** NO new features, tabs, endpoints, or frameworks. Harden what exists.

| Work Package | Description | Status |
|---|---|---|
| **WP0** | Sync `main` (`982755c`), tag `pre-hardening`, baseline numbers, freeze inventory (`docs/FROZEN.md`), track questions (`QUESTIONS.md`). | **DONE** (commit `2b858cc`) |
| **WP1** | Hard-rule gaps (audit coverage, login rate/CSRF logging, prompt injection defense, drive filename bounding, portal XSS escaping, result citation requirements, probe phrase blocking). | **COMPLETED & VERIFIED** (commit `5619949` + fixes for assistant & portal tests) |
| **WP-P** | Pathway Pillar Protection (P1 deterministic bypass for pathway questions, P2 grade gating, P3 audit logging, P4 equal visibility of 3 pathways, P5 human gate guarantee, P6 longitudinal positioning). | **DONE** (integrated in WP1) |
| **WP2** | Evals expansion (10 new scripted evaluation scenarios in `scripts/run_evals.py` and documentation in `EVALS.md`). | **NEXT UP** |
| **WP3** | Local model measurements (10 runs of Qwen 2.5 7B at temp 0.2 across comment generation & assistant answers, recording latency, citation accuracy, guard pass rate in `docs/MODEL_MEASUREMENTS.md`). | **PENDING** |
| **WP4** | Cross-platform & packaging verification (`package_teacher_demo.py`, ZIP integrity, Linux CI verification). | **PENDING** |
| **WP5** | Documentation sync (update `README.md`, `ARCHITECTURE.md`, `THREAT_MODEL.md`, `CHANGELOG.md` to reflect whole-school portal + assistant). | **PENDING** |
| **WP6** | 3-minute demo script & walkthrough runbook (`docs/WALKTHROUGH.md`). | **PENDING** |

---

## 3. Merge & Build Errors: Root Causes & Resolution

### The Error Moses Encountered
When pushing commit `5619949` and opening a PR / merging to `main`, GitHub CI failed ("Regression checks failed"), blocking the merge.
The root causes of test failures in `5619949`:
1. `AssertionError: Expected uncited claim to be rejected: She scored 85% in Science.`
   - *Cause:* Regex `RESULT_CLAIM` in `hatua/assistant.py` had `|\b\d+%\b`. Because `%` is not a word character (`\w`), `%\b` fails to match when followed by a non-word char (like space or period).
   - *Fix:* Removed the trailing `\b`, allowing `\b\d+%` to match percentages cleanly.
2. `AssertionError: states a result without a citation from class data: '- Social Sciences...'`
   - *Cause:* In `hatua/assistant.py` `problems()`, `pathways.text()` places citations at the end of the line, but sentence splitting divided the line into multiple sentences.
   - *Fix:* Added `line_cites = [c for c in guard.citations(line) if c in allowed]` so valid line citations cover sentences on that line.
3. `NameError: name 'audit' is not defined`
   - *Cause:* `tests/test_school_portal.py` called `audit.read_events()` in two tests without importing `audit`.
   - *Fix:* Added `from hatua import audit, ...` at line 17 of `tests/test_school_portal.py`.
4. `AssertionError: assert 0 == 1 in test_drive_file_safety`
   - *Cause:* `HT-0621` was not in `store.load("learners")`, causing `clean_record` to treat it as `not_on_list` instead of `other_class`.
   - *Fix:* Changed test fixture to use `HT-0401` (Grade 4 learner present in the synthetic store).
5. `TimeoutError: timed out (20s)` in `test_pathway_views_logged_and_omitted_for_grades_4_to_6`
   - *Cause:* In Python 3.14 on Windows, pure-python PBKDF2 and un-cached file operations can take ~22s during heavy test execution, hitting the 20s test client timeout.
   - *Fix:* Increased test `call()` HTTPConnection timeout from 20s to 60s in `tests/test_school_portal.py`.

**Result:** All 23 tests in `tests/test_school_portal.py` and all 16 UI checks + XSS checks in `npm run test:ui` pass with 100% success.

---

## 4. Local Environment Constraints & Quirks

- **OS:** Windows 11.
- **Python:** Python 3.14.6 (`.\.venv\Scripts\python.exe`).
- **Python 3.14 Windows Hashlib Fallback:** `hashlib.scrypt` and `hashlib.pbkdf2_hmac` are missing from Windows Python 3.14 binary distributions. `hatua/auth.py` contains a pure-stdlib PBKDF2-HMAC-SHA256 fallback (`_pbkdf2_pure`, 50k iters). Hash prefixes are self-describing (`scrypt:`, `pbkdf2:`).
- **Ruff on Windows Python 3.14:** Running `ruff` directly on Windows Python 3.14 exits with code `-1073741502` (0xC0000005 access violation in ruff-python wrapper). Ruff runs cleanly on Linux in CI (`checks.yml` on Ubuntu 3.12).
- **Line Endings:** Git uses CRLF on checkout. Keep regexes and string replacements newline-agnostic or LF-normalized.

---

## 5. Next Steps for Continuing Developer / Agent

### Step 1: Commit the WP1 Polish
Files modified:
- `hatua/assistant.py` (fixed `RESULT_CLAIM` regex and line citation coverage)
- `tests/test_school_portal.py` (added `audit` import, used `HT-0401`, 60s timeout)
- `docs/WALKTHROUGH.md` & `CHANGELOG.md` (record WP1 completion)

### Step 2: Implement WP2 (Evaluations)
Add 10 new scripted evaluation scenarios in `scripts/run_evals.py` covering:
1. `assistant_ranking_refusal` (blocks position/comparison requests)
2. `assistant_uncited_claim_rejection` (blocks free-text claims with no record citation)
3. `assistant_class_scoping` (cannot access or mention learners from another stream)
4. `notes_are_data_not_instructions` (prompt injection attempt in teacher notes)
5. `pathway_should_blocked` (blocks directive "should take STEM")
6. `pathway_views_logged` (audits `portal.view_pathways`)
7. `probe_phrase_block` (8 probe sentences blocked, 10 legit suggestions allowed)
8. `pathway_evidence_on_request` (context omits pathways unless specifically asked)
9. `drive_approval_scoped` (cannot approve files from other grade/stream)
10. `portal_forgery_rejection` (rejects forged tokens, bad CSRF, wrong origin)

Update `EVALS.md` with descriptions and run `.\.venv\Scripts\python.exe scripts/run_evals.py`.

### Step 3: Run Full Validation Suite
```powershell
# In c:\Users\Mose\Long-view:
.\.venv\Scripts\python.exe -m pytest -q
npm run test:ui
.\.venv\Scripts\python.exe scripts/run_evals.py
.\.venv\Scripts\python.exe scripts/package_teacher_demo.py
```

### Step 4: Merge to `main`
Once CI is green on `chore/freeze-and-harden`, fast-forward or merge cleanly into `main` and push tags.
