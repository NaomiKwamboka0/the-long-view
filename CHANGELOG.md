# Hardening and honesty — 27 October 2026

## T6: a three-minute runbook with real output in it

- New `docs/DEMO.md`: a storyboard with per-step timings, the exact commands, the output each one prints, a pre-recording checklist, and a closing note not to edit out the pause, the block or the crash.
- The demo run, the two-learner agent run, the blocked save and the guard-blocked edit were run and their output pasted in. The sign-in block was captured through the CLI test with the hidden prompt stubbed, and the document says so, because a scripted shell cannot answer `getpass`.
- **Not done:** no video has been recorded. That is H4, and it needs a human in front of a terminal.

## T5: the recipe for a requirement added live

- New `docs/EXTENDING.md`: adding a read-only MCP tool (function with `@audit.audited`, registration in `mcp_server.py`, planner prompt only when the agent should use it, one test, one evaluation row, tool count in ARCHITECTURE.md), adding a pattern type (rules, both family-message languages, guard allowlist), and the list of things that must never be added (approve/share/send tools, unlogged tools, model calls in the rules path).
- **Verified by doing it:** on a scratch branch I added `list_streams`, its test and an `E17` evaluation row. `ruff`, `pytest` (95 tests) and `run_evals.py` (E17 PASS, 17/22 with the agent tasks failing for the environment reason below) went green in 2 minutes 3 seconds. The branch was deleted and nothing was merged.

## T4: CI now runs what we claim

- The workflow installs from `requirements.lock.txt` (69 pinned packages) instead of bare `pytest`, lints with `ruff`, runs the 21 evaluations, prints coverage, and still builds and tests the teacher demo. A failed evaluation task now fails the build; `run_evals.py` already exited non-zero, and that is now exercised.
- `pyproject.toml` adds the ruff configuration (target Python 3.9, so no 3.10+ only suggestions) and the pytest settings. 26 pre-existing findings were fixed; `BLE001` and `E741` are ignored with the reasons written in the file.
- **Verified:** changing one assertion in E01 made that task FAIL and the run exit 1 (15/21 passed). The change was reverted.
- **Not done:** the workflow has not run on GitHub from this machine (no push credentials available here). Every step was run locally, but the five agent evaluations need Node's filesystem server and were not part of that local proof.

## T3: EVALS.md now separates what is measured from what is claimed

- New section **"A failure we did not fix"**: in the one real run the model drafted for 1 of 3 learners and stopped, repeated a call, asked for a Kiswahili teacher draft and invented a file name. The supervisor works around all four; the model is not fixed. The next step is named: run the 10-run batch, then compare a larger local model and a stricter tool-schema prompt.
- E15 is now stated plainly as covering the template path only, with a pointer to `scripts/measure_agent.py` for the model path.
- The "Not tested" entry for many Qwen runs points at the harness and says the batch does not exist yet.
- The README limitation was rewritten to match: one real run, no completion rate claimed.
- **Not done:** no rate is published anywhere, because no batch has been run. No number was moved or rounded to look better; the existing single-run account is left as recorded.

## T2: measuring the local model instead of guessing

- New `scripts/measure_agent.py` runs the agent N times, each in a fresh temporary home with a fixed `HATUA_TODAY`, and records for every run: whether it finished all target learners without the supervisor, the nudge count, drafts, tool calls, blocked calls, token counts when Ollama reports them, and wall time. Crashed runs are recorded as failed runs.
- Results go to `evals/agent_runs.json` with the model name and digest and a description of the machine. Without Ollama the script stops with exit code 2 and never falls back to the rules planner silently.
- `agent.run()` now returns an `activity` block (nudges, corrections, tool calls, blocked calls, tokens) so the numbers come from the run itself rather than from a log scrape.
- The arithmetic (median, nearest-rank p90, unaided counting) lives in `hatua/measure.py` and is tested with fabricated records.

**Not done:** the batch itself. This machine has no Ollama model pulled, so `evals/agent_runs.json` does not exist yet and no model-run number is published. Run `python scripts/measure_agent.py --runs 10` once with `qwen2.5:7b` and commit the first complete batch.

## T1: the guard now checks every sentence

- Text is normalised before matching (Unicode NFKC, lowercase, runs of whitespace, hyphens and underscores collapsed), so `stem  pathway` and `STEM_pathway` no longer slip through.
- Every sentence must be covered by a citation, except the lines the templates write themselves (`TEMPLATE_LINES`, derived from what `summary.py` emits). Previously only bullet lines were checked, so an uncited prose sentence passed.
- The forbidden list now covers pathway/track/career suggestions, ranking and comparison (`outperforms`, `among the top`, `top 5 in the class`, `best/worse than`), trait labels (`natural leader`, `gifted`, `slow learner`) and four Kiswahili equivalents. Bare "track" is deliberately not blocked. The Kiswahili list is marked for native-speaker review.
- The optional wording rewrite is kept only when it has the same number of lines and the same citation set on each line; otherwise the template text stands.
- A teacher's edited text is checked the same way, so adding an uncited sentence is now refused. That is a deliberate change: one existing test was updated to put a citation on its review note.
- `guard.check` now reads the evidence tables once per call instead of once per citation, which cut the full-class regression from five minutes to thirty seconds.

Tests: 88 pass, including 31 blocked phrases, 11 legitimate sentences, a check of every draft for all 40 learners in English and Kiswahili for both audiences, and the rewrite cases. E09, E10 and E11 are unchanged.

## Not done

- No semantic check of a claim. The guard is a phrase list plus citation coverage; a teacher's reading is still the real control.

# Data intake, sign-in and data protection — 27 October 2026

This update answers the two questions a panel asks first: how real school data reaches the agent lawfully, and whether "a named teacher approved this" means anything.

## Changes

- **Secrets stay out of the audit log.** A keyword argument named `pin`, `session`, `password`, `token` or `secret` is written to `logs/audit.jsonl` as `[redacted]`. Positional arguments are not scrubbed, and the module says so (A1).
- **Optional teacher sign-in, off by default** (`HATUA_REQUIRE_AUTH=1`). A teacher registers an ID, a name and a PIN on one computer; the PIN is stored as a salted scrypt hash. Sessions are random tokens kept only as SHA-256 with a 15-minute life, and an ID locks for 15 minutes after 5 failed attempts. A signed-in approval records the registered name and teacher ID, ignores the typed name, and marks the entry as authenticated. A draft approved while sign-in was off cannot be saved once it is on (A2).
- **New commands:** `teacher-add`, `teacher-list`, `approve --teacher-id`, `import-approvals --teacher-id`, and `map-export`. `GateBlocked` still exits 2; a bad value or missing file now exits 1 with a message instead of a traceback (A2).
- **`map-export` maps a school's own CSV onto Hatua's columns** from an explicit JSON mapping. It copies only the mapped columns, reports every dropped heading, names the ones that look personal, tidies "Grade 7" to 7, and gives unmapped rows a stable content-hash `record_id`. With an `id_map`, real admission numbers become `HT-xxxx`, and a real ID missing from the map is skipped rather than passed through. `data/private/` is git-ignored (A3).
- **New documents:** `docs/INGESTION.md` (the data path, what stays on the device, and how NEMIS/KEMIS relate) and `docs/DPIA.md` (a draft for the school to complete, not an approved assessment). `ARCHITECTURE.md`, `README.md`, `PRIVACY.md` and the privacy notice inside the teacher page now describe sign-in and export mapping accurately (A4).

## Verification

- 48 Python regression tests pass (28 existing + 20 new).
- The 16 engine evaluations pass unchanged, and existing commands behave as before with sign-in off.
- No real school export has been tried, so `map-export` is proven against the shipped template only.

## Not done

- No real, anonymised school export has been run through `map-export`, and no `.xlsx` support exists; teachers save as CSV.
- Sign-in is per computer. It is not TSC or KEMIS single sign-on, it does not prove who a person is, and anyone with file access can edit the logs. The offline teacher page still records a typed name.
- The DPIA is unfinished by design: the lawful basis, retention, notice and sign-off are the school's to complete.

# Teacher testing and privacy update — 20 October 2026

Hatua is an offline, evidence-linked learner review prototype. This update makes its synthetic-data demonstration easier for a teacher to try and makes its data handling more explicit.

## Changes

- A guided 10–15 minute teacher test, example scenarios, progress checklist and downloadable feedback. The standalone HTML needs no account, Python or network after download.
- An embedded privacy notice and PRIVACY.md covering local storage, typed teacher names, exports, audit logs, plain-text files, deletion, hosting and prerequisites for a real-school pilot.
- Synthetic-only packaging from a fresh temporary workspace, plus an optional manually triggered GitHub Pages workflow. Existing working data and audit logs are not copied into the package.
- No external fonts; the standalone page's Content Security Policy blocks external assets and application connections.
- Browser storage scoped to the embedded dataset, visible storage-failure notices, malformed-storage handling and a clear-data control. In-progress edits survive navigation within the page.
- Separate family-message approval and download, with prepared messages locked after teacher edits so they cannot silently undo a teacher's changes. Changed patterns require fresh teacher review.
- Conflicting assessment terms are excluded from pattern calculations, break consecutive runs, and remain inspectable. The former E16 failure is resolved.
- Literal loopback-only Ollama endpoints, no proxy use or redirects; approval imports require source hashes and explicit family-sharing approval.
- Live class search, keyboard navigation between tabs, source-record access for every record contributing to a term, and browser decisions visible in History.
- Regression checks and a GitHub Actions check workflow.

## Verification

- 21/21 existing evaluations passed, using the rules planner and scripted stand-in models.
- 28/28 Python regression tests passed.
- 16/16 UI DOM integration checks passed against the generated standalone page.
- Python compilation and Git whitespace checks passed.
- No new live Ollama/Qwen run and no real-browser visual, screen-reader or device testing were performed. No real teacher or school validation has been claimed.

## Remaining limits

This remains a synthetic-data prototype. Typed names are not authentication; local files and browser storage are unencrypted; there is no automatic retention schedule. Phrase/citation checks cannot establish semantic correctness. A real-school pilot needs identified responsibility, appropriate privacy and security arrangements, and review with teachers and guardians. The browser demo cannot send messages or import school records.

Source changes are on the local branch improve/teacher-testing-privacy. GitHub publication and a public Pages link depend on account authorization and repository settings; this update does not itself establish a deployed URL.
