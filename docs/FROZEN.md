# Frozen — inventory of everything in the project at `pre-hardening`

Written as part of WP0 of the freeze-and-harden plan. Every file or module is
marked **core** (the agent loop, MCP tools, gate, guard, evals, pathway pillar)
or **supporting** (whole-school teacher portal, drive, alerts, calendar, comments, assistant).

Pathway ideas (`hatua/pathways.py` and the learner-page pathway section)
are **core**: a protected pillar (see WP-P in the freeze-and-harden plan).
Nothing may be added to this list after the `pre-hardening` tag without an
explicit decision by Moses in `QUESTIONS.md`.

## Single theme entered under

**Longitudinal strength tracking** — with *Plain-language reporting* in English
and Kiswahili as a sub-theme, and senior-school pathway guidance as a feature of
the longitudinal profile (not a second theme).

> **Decision required (H1 / H8):** Moses and Naomi to confirm this wording and
> decide whether to ask the organisers whether pathway ideas may be described as
> a prominent feature under one theme. Record the answer in `QUESTIONS.md`.

---

## Core — the minimum set that must work for the entry to be valid

| Item | Path | What it does |
|---|---|---|
| Agent loop | `hatua/agent.py` | LangGraph: plan → tools → self_check → teacher_gate |
| MCP server (hatua-mcp) | `hatua/mcp_server.py` | Exposes 7 tools to the planner |
| Tool: list_learners | `hatua/tools.py` | Read — class list for the signed-in teacher |
| Tool: ingest_record | `hatua/tools.py` | Write — cleans a CSV export, records quality flags |
| Tool: review_queue | `hatua/tools.py` | Read — learners with new unprocessed records |
| Tool: find_patterns | `hatua/tools.py` | Read — cited multi-term patterns per learner |
| Tool: get_evidence | `hatua/tools.py` | Read — opens any citation by ID |
| Tool: draft_summary | `hatua/tools.py` | Write — produces a pending draft |
| Tool: update_profile | `hatua/tools.py` | Write, gated — saves a draft only after approval |
| Borrowed filesystem server | `node_modules/@modelcontextprotocol/server-filesystem` | Lists inbox; write tools not given to planner |
| Teacher gate | `hatua/gate.py` | LangGraph interrupt; `approve` not exposed over MCP |
| Guard | `hatua/guard.py` | Rejects labels, comparisons, pathway language, uncited claims |
| Pattern engine | `hatua/patterns.py` | Deterministic: decline, growth, held strength, attendance |
| Pathway pillar | `hatua/pathways.py` | Grade-staged ideas for teacher only; never picks one, side-by-side |
| Approval hash | `hatua/gate.py`, `hatua/summary.py` | SHA-256 of the approved text; mismatch blocks save |
| Audit log | `hatua/audit.py` | Append-only, hash-chained JSONL (`audit.jsonl`, `approvals.jsonl`) |
| Scope | `hatua/scope.py` | One rule: class teacher sees only their current streams |
| Auth / sign-in | `hatua/auth.py` | Optional PIN; two token kinds (human / agent) |
| Evaluations (21 tasks) | `scripts/run_evals.py`, `evals/` | E01–E16 engine; A01–A05 agent |
| Eval: measure_agent | `scripts/measure_agent.py` | Batch run → `evals/agent_runs.json` (to be run in WP3) |

## Supporting — features that extend the entry but are not the core claim

| Item | Path | What it does |
|---|---|---|
| Whole-school portal server | `hatua/portal.py` | ThreadingHTTPServer on loopback only, origin/host/CSRF checks |
| Whole-school portal UI | `ui/portal.html` | Whole-school UI: class list, learner view, drive, calendar, chat |
| Assistant | `hatua/assistant.py` | In-portal chat helper (Qwen or deterministic built-in fallback) |
| School drive & approvals | `hatua/drive.py` | Staged CSV uploads, stream filtering, approval into school store |
| Alerts & notices | `hatua/notify.py` | Term attendance, missing records, upcoming deadlines |
| School calendar | `hatua/school_calendar.py`, `data/calendar/kenya_2026.json` | Term dates, exam windows, half-term breaks |
| Report comments | `hatua/comments.py` | Formatted end-of-term comments citing verified records |
| School context | `hatua/school.py` | School metadata, teacher registry, active terms |
| Standalone teacher demo | `ui/hatua.html`, `ui/hatua_fragment.html` | Self-contained offline single-file demo |
| Demo packager | `scripts/package_teacher_demo.py` | Builds the synthetic-only ZIP for teachers |
| School demo generator | `scripts/make_school_demo.py`, `hatua/school_demo.py` | Builds full multi-stream school demo data |
| Synthetic data generator | `scripts/make_dummy_data.py` | Produces `store/*.json` and `teacher_assignments.csv` |
| Importer / map-export | `hatua/importer.py` | Maps a school's own CSV headings |
| Normalise | `hatua/normalize.py` | Cleans raw records before ingest |
| Store | `hatua/store.py` | Reads/writes local JSON files |
| Summary / draft writer | `hatua/summary.py` | Templates for teacher and guardian drafts |
| LLM rewrite (optional) | `hatua/llm.py` | Optional wording rewrite; dropped if it loses a citation |
| Local model client | `hatua/local_model.py` | Qwen 2.5 7B via Ollama |
| Config | `hatua/config.py` | Paths, env vars, constants |
| CLI | `hatua/cli.py` | `python -m hatua` commands |
| Build UI | `hatua/build_ui.py` | Assembles the standalone HTML |
| Measure | `hatua/measure.py` | Helpers for `measure_agent.py` |
| UI tests | `tests/test_ui.cjs` | jsdom checks for the portal HTML |
| Test suite | `tests/` | Python pytest: unit & regression test files |
| CI workflow | `.github/workflows/checks.yml` | Ubuntu: pytest, ruff, evals, demo build |
| Demo CI workflow | `.github/workflows/teacher-demo.yml` | Publishes synthetic demo to GitHub Pages |
| Docs | `docs/` | ARCHITECTURE.md, DEMO.md, DPIA.md, EXTENDING.md, INGESTION.md, PORTAL.md |
| Privacy policy | `PRIVACY.md`, `ui/privacy.html` | Full data handling notice |
| Teacher test guide | `TEACHER_TEST.md` | Instructions for a teacher running the demo |

---

## What may not be added after `pre-hardening`

The plan (section 5) is explicit:

- A second portal or web framework
- A standalone history module
- MCP over HTTP
- Extra cohorts
- New tabs, endpoints, notification channels or storage backends
- Any new model path
- Real data
- Changing the guard to permit pathway or label language in drafts and messages

If a work package needs something not on this list, write it to `QUESTIONS.md`
and use the smallest alternative that keeps existing tests passing.
