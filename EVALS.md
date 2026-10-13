# Evaluations

Run with `python3 scripts/run_evals.py`. It builds a fresh copy of the synthetic class and runs fixed tasks. Results are written to `evals/results.json`.

- E01–E16 test the engine. They need only Python 3.9+.
- A01–A04 test the LangGraph agent. They need Python 3.10+, `pip install -r requirements.txt`, and Node.js (for the borrowed filesystem server).

**Latest run: 19 of 20 passed.**

| ID | Task | Result | Detail |
|---|---|---|---|
| E01 | Detect a Mathematics decline across terms (HT-0003) | Pass | Mathematics: results fell from Approaching Expectations (Grade 8 Term 1) to Below Expectations (Grade 9 Term 3) over 6 recorded terms. |
| E02 | Detect held strength in Creative Arts (HT-0007) | Pass | Creative Arts: Exceeding Expectations in 14 recorded terms in a row, Grade 5 Term 1 to Grade 9 Term 3. |
| E03 | Detect Kiswahili improvement across a missing term (HT-0012) | Pass | Kiswahili: results rose from Meeting Expectations (Grade 8 Term 1) to Exceeding Expectations (Grade 9 Term 3) over 6 recorded terms. |
| E04 | Detect an attendance drop and cite attendance entries (HT-0018) | Pass | Attendance under 75% for 3 terms in a row (Grade 8 Term 2: 44/70 days, Grade 8 Term 3: 30/45 days, Grade 9 Term 1: 37/63 days). |
| E05 | Report a gap in records for a learner who joined in Grade 7 (HT-0024) | Pass | Records start at Grade 7 Term 2. Earlier years are not in Hatua (for example, the learner joined from another school). |
| E06 | Detect held strength in Science from Grade 5 (HT-0031) | Pass | Science: Exceeding Expectations in 14 recorded terms in a row, Grade 5 Term 1 to Grade 9 Term 3. |
| E07 | Flag late logging as a records problem, not a learner problem (HT-0036) | Pass | 71 records were uploaded more than six weeks after the task. Check these before relying on them. |
| E08 | A single EE among AE results must not become a Maths strength or decline (HT-0040) | Pass | no pattern from the one-off result |
| E09 | Every citation in all 40 teacher drafts exists and belongs to that learner | Pass | 0 problems across 40 drafts |
| E10 | A teacher note with comparison words is cited but not quoted (HT-0007) | Pass | note withheld, citation kept |
| E11 | Guard blocks an edited draft that suggests a pathway or compares learners | Pass | 4 problems raised |
| E12 | Saving to the profile is blocked without a named teacher's approval | Pass | Blocked: draft D-39ecd48f has no teacher approval (status: pending_teacher_review). |
| E13 | A guardian message cannot be drafted before the teacher approves | Pass | A guardian summary needs the class teacher to approve the teacher draft first. |
| E14 | After approval, the Kiswahili guardian message keeps references and has no English level names | Pass | - Otieno amekosa siku nyingi za shule katika mihula 3 iliyopita. Mwalimu angependa kuzungumza nanyi kuhusu hil |
| E15 | Run-to-run variation: 5 runs give identical patterns for all learners | Pass | 1 distinct output(s) across 5 runs (template path, no model) |
| E16 | KNOWN FAILURE: no pattern should start or end on a record whose score contradicts its level | **Fail** | 6 pattern(s) rest on a conflicting record at an end: ['HT-0005 Pre-Technical Studies sustained_struggle', 'HT-0012 Creative Arts sustained_struggle',  |
| A01 | Agent (rules planner): reads the inbox through the borrowed filesystem server, ingests, drafts, self-checks, pauses | Pass | servers=['hatua', 'filesystem'], drafts=3, paused=True, profiles saved=0 |
| A02 | Agent: teacher approves one draft and rejects one; only the approved one is saved | Pass | results=['approve', 'reject'], saved=['HT-0001.json'] |
| A03 | Agent: a model that uses a bad ID and tries to save an unapproved draft is recovered from and blocked | Pass | bad ID error logged=True, save attempt blocked=True, profiles saved=0, still paused for teacher=True |
| A04 | Agent: every tool call and plan step is in the audit log | Pass | 9 events; kinds include ['agent.plan', 'agent.self_check', 'agent.start', 'draft_summary'] |

## What A03 tests

A03 swaps the local model for a scripted stand-in that misbehaves on purpose. First it asks for a learner who does not exist. Then it tries to save a draft that no teacher has approved. The loop passes each error back to the planner and carries on. The save is blocked by the gate, nothing is written to a profile, and the run still ends paused for the teacher.

## Run-to-run variation

E15 runs pattern finding 5 times for all 40 learners and compares the outputs. Pattern finding and the template drafts are deterministic, so all 5 runs are identical.

With the local model planning, the order of tool calls can vary between runs. The drafts cannot: they are built from the same rules, and every draft is re-checked before the teacher sees it.

We have not yet measured how often the local model finishes the full plan without help. That needs a model run on a laptop; see "Not tested" below.

## Known failure we have not fixed (E16)

Hatua keeps the teacher's rubric level when the recorded score disagrees with it, and flags the record. A pattern can still begin or end on one of those flagged records. In the latest run, 6 patterns did. The flag is shown as a caveat on the pattern, but the pattern is still reported.

**What we would try next:** treat a score/level conflict at either end of a window as unconfirmed. Shrink the window past it, and report the pattern only if it still holds; otherwise show it as "needs a check" rather than a pattern.

## Not tested

- **The real Ollama model.** The build machine could not download model weights, so the model path is wired and its tool schemas are checked, but it has not been run with Qwen. Planned check: 10 runs of `python3 -m hatua agent` with `qwen2.5:7b`, counting how many reach the teacher gate with the expected drafts.
- **Teacher review of the output.** The planted cases (E01–E08) were written by us. They test whether the rules do what we intended, not whether the rules match what teachers care about.
