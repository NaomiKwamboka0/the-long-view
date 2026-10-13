# Hatua

*Hatua kwa hatua* — step by step. Hatua helps a Kenyan junior school class teacher see each learner's strengths and struggles across Grades 4 to 9, with every statement linked to the record it came from. Nothing is saved to a profile or shared with a guardian until a named teacher approves it.

Built for the **Education: The Long View** track of the African Agentic AI Design Challenge. Sub-theme: *Longitudinal strength tracking*, with *Plain-language reporting* (English and Kiswahili).

> All data in this repository is **synthetic**. No real learner is represented.

## Run it (one command)

```bash
python3 -m hatua demo
```

Then open `ui/hatua.html` in any browser (`open ui/hatua.html` on a Mac). It needs only Python 3.9+, with nothing to install. It works offline: no server, no internet, no outside APIs.

The MCP server needs Python 3.10+ and `pip install -r requirements.txt`.

## What the teacher sees

- **Learners**: search by name or ID (Search button or Enter), and filter by stream, learning area, what the records show (going up, going down, held strength, needs support, attendance), review status, data issues, and "still going on". Learners are listed by ID and never sorted by results.
- **One learner**: cited patterns, related teacher notes, a Grade 4–9 "long view" grid of CBC rubric levels (EE, ME, AE, BE) and attendance, and a draft to edit, approve or reject. Tap any cell or citation to open the record behind it.
- **Data checks**: every repair or doubt Hatua found in the records (late uploads, score and level disagreeing, duplicates, unknown learners), searchable and filterable.
- **Activity log**: every tool call, with inputs, results, time and who did it.

Decisions made on the page stay in that browser until the teacher applies them:

```bash
python3 -m hatua import-approvals approvals.json
```

## Command line

| Command | What it does |
|---|---|
| `python3 -m hatua demo` | Load the synthetic class, take in this term's export, build the page |
| `python3 -m hatua ingest 2026_T3_new_records.csv` | Clean a new export from `data/inbox` and report data-quality flags |
| `python3 -m hatua patterns HT-0003` | Show cited patterns for one learner |
| `python3 -m hatua draft HT-0003` | Draft a summary for the class teacher |
| `python3 -m hatua approve D-xxxx --teacher "Full Name"` | Teacher approves (add `--reject`, `--edited file.txt`, `--share`) |
| `python3 -m hatua save D-xxxx` | Save an approved draft to the profile (blocked without approval) |
| `python3 -m hatua draft HT-0003 --audience guardian --lang sw` | Guardian message in Kiswahili (only after teacher approval) |

## MCP server

`python3 -m hatua.mcp_server` starts **hatua-mcp** over stdio with six tools: `list_learners`, `ingest_record`, `find_patterns`, `get_evidence`, `draft_summary`, `update_profile`. There is no approve tool, so the agent cannot approve its own work. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Rules Hatua enforces

- Never assigns a pathway, track or label, and never ranks or compares a learner with classmates. A guard blocks such wording, including in teacher edits.
- Every claim cites `R-` (assessment), `N-` (teacher note) or `A-` (attendance) evidence that exists and belongs to that learner.
- A single result never becomes a pattern.
- Saving to a profile and sharing with a guardian both need a named teacher's approval, recorded with a hash of the exact text.
- Everything runs on the teacher's machine. Kenya's data rules require basic-education data to be processed in Kenya.

## Evaluation

```bash
python3 scripts/run_evals.py
```

16 fixed tasks, including one known failure we have not fixed. See [EVALS.md](EVALS.md).

## Status (honest)

Done: synthetic messy cohort, cleaning and quality flags, cited pattern finder, drafts in English and Kiswahili, approval gate, audit log, MCP server, offline teacher page, evals.

Not done yet:
- LangGraph orchestration loop.
- The borrowed MCP server (the official filesystem server for the inbox folder).
- A full task on a local open-weights model. The hook exists in `hatua/llm.py`, off by default, local only.
- Talking to a practising junior school teacher.

## Licence

MIT. See [LICENSE](LICENSE).
