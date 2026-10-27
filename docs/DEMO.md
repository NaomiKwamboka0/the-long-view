# Demo runbook: three minutes, unedited

A recording, not a rehearsal: run these commands once, on camera, and let what happens
happen. The last step deliberately shows a failure.

Provenance, so nobody has to guess: the `demo`, `agent`, `save` and `approve --edited` blocks
below were captured from real runs on 27 October 2026 (Windows, Python 3.14, no model). The
sign-in block was captured through the CLI test with the hidden prompt stubbed, because a
scripted shell cannot answer `getpass`; record that one in a real terminal.

## Before recording

- [ ] `git status` is clean and you are on one branch you can name.
- [ ] `store/`, `logs/`, `profiles/` are empty: `rm -rf store logs profiles` (PowerShell: `Remove-Item -Recurse -Force store,logs,profiles -ErrorAction SilentlyContinue`).
- [ ] `python -m venv .venv` done and `pip install -r requirements.txt` already run.
- [ ] Node.js installed. Without it the borrowed filesystem server is skipped and the agent has no inbox to list.
- [ ] Ollama running with the model: `ollama list` shows `qwen2.5:7b`. (Not needed if you record with `--rules`.)
- [ ] `export HATUA_TODAY=2026-10-13` (PowerShell: `$env:HATUA_TODAY="2026-10-13"`) so dates match this document.
- [ ] A teacher registered if you will show sign-in: `python -m hatua teacher-add --id mary --name "Mary Wambui"`.
- [ ] Terminal 100x30, font 16pt or larger, no other windows in shot.

## Storyboard

| Time | Step | Command | What the viewer sees |
|---|---|---|---|
| 0:00 | The class and the page | `python -m hatua demo` | 40 synthetic learners, 4449 records, the teacher page written |
| 0:20 | The agent works | `python -m hatua agent --rules --max 2` | One plan line and one tool line per call, then the pause |
| 1:10 | The pause | (the agent is waiting) | "Paused for the class teacher. Nothing is saved until you approve." |
| 1:30 | Sign in and approve | `HATUA_REQUIRE_AUTH=1 python -m hatua approve D-xxxxxxxx --teacher-id mary` | A hidden PIN prompt, then `"authenticated": true` |
| 2:00 | The gate holds | `python -m hatua save D-xxxxxxxx` | `BLOCKED: ... has no teacher approval`, exit code 2 |
| 2:20 | The guard holds | `python -m hatua approve D-xxxxxxxx --teacher "Mary Wambui" --edited bad.txt` | `BLOCKED: Edited text failed safety checks: Uses 'stem'...` |
| 2:40 | The honest failure | `python scripts/measure_agent.py --rules --runs 1` | A crashed run reported as a crash, not hidden |

### 0:00 `python -m hatua demo`

```
learners=40 records=4494 inbox=308 attendance=646 notes=259
class list: 40
attendance rows: 646
teacher notes: 259
Added 4449 records, rejected 19, skipped 26 duplicates.
Next: python3 -m hatua build-ui   (then open ui/hatua.html)
Added 308 records, rejected 0, skipped 0 duplicates.
Wrote ui\hatua.html
Open ui/hatua.html in your browser. No internet or server needed.
```

Say: every record is invented. The rejected 19 are bad learner IDs and unknown learning
areas, counted rather than quietly dropped.

### 0:20 `python -m hatua agent --rules --max 2`

`--rules` plans with fixed rules, so the recording does not depend on model speed. Drop the
flag to show Ollama planning instead; the tool lines look the same.

```
Planner: rules
MCP servers: hatua, filesystem
Tools: draft_summary, find_patterns, get_evidence, get_file_info, ingest_record, list_directory, list_learners, review_queue, update_profile

  [plan] call list_directory({"path": "...\\data\\inbox"})
  [tool]  list_directory -> [FILE] 2026_T3_new_records.csv
  [plan] call ingest_record({"file_name": "2026_T3_new_records.csv"})
  [tool]  ingest_record -> {'file': '2026_T3_new_records.csv', 'added': 0, 'rejected': 0, 'skipped_duplicates': 0, 'message': 'This exact...
  [plan] call review_queue({"max_learners": 2})
  [tool]  review_queue -> {'file': '2026_T3_new_records.csv', 'learners_with_new_records': 40, 'already_approved': 0, 'waiting': 40, 'le...
  [plan] call find_patterns({"learner_id": "HT-0001"})
  [tool]  find_patterns -> {'learner_id': 'HT-0001', 'first_name': 'Achieng', 'patterns': [{'pattern_id': 'P-...
  [plan] call draft_summary({"learner_id": "HT-0001", "audience": "teacher"})
  [tool]  draft_summary -> {'draft_id': 'D-...', 'learner_id': 'HT-0001', ...
  [plan] call find_patterns({"learner_id": "HT-0002"})
  ...
  [check] D-... HT-0001: OK
  [check] D-... HT-0002: OK
  [plan]  2 draft(s) are waiting for the class teacher to review.
```

Say: `added: 0` is correct — `demo` already took this export in, and re-ingesting the same
file changes nothing. The model chooses the calls; the drafts come from fixed rules; the
self-check runs before a teacher sees anything.

### 1:10 the pause

The graph stops at `teacher_gate` and asks for a name. Nothing is saved while it waits. If
you press Enter, every draft stays pending, which is worth showing because it is the default.

### 1:30 approve with sign-in

```
PIN for mary (input is hidden):
{
 "approval_id": "AP-00001",
 "draft_id": "D-...",
 "learner_id": "HT-0001",
 "teacher": "Mary Wambui",
 "teacher_id": "mary",
 "authenticated": true,
 ...
}
```

Say: the typed name is ignored; the registered name and ID are recorded. The PIN never
reaches `logs/audit.jsonl`, and the session token is stored there as `[redacted]`.

### 2:00 the gate holds

```
BLOCKED: Blocked: draft D-86d64a6f has no teacher approval (status: pending_teacher_review).
```

Exit code 2, and the draft is still `pending_teacher_review` afterwards. Say: the agent has
no tool that can approve, so this is the only path to a profile.

### 2:20 the guard holds

```
echo "- Cynthia should take the STEM pathway; she is weaker than classmates. [R-02937]" > bad.txt
python -m hatua approve D-xxxxxxxx --teacher "Mary Wambui" --edited bad.txt
```

```
BLOCKED: Edited text failed safety checks: Uses 'pathway', which labels, places or compares the learner.; Uses 'stem', which labels, places or compares the learner.; Uses 'should take', which labels, places or compares the learner.; Uses 'classmates', which labels, places or compares the learner.; Uses 'weaker than', which labels, places or compares the learner.
```

Exit code 2, draft unchanged. Say: the guard checks the teacher's own edits, not just the
agent's draft.

### 2:40 one visible failure

```
  run 1/1: crashed

Unaided completions : 0/1 (finished all 3 learners with no supervisor help)
Crashed runs        : 1
Nudges              : median 0, worst 0, total 0
Wall seconds        : median 5.9, p90 5.9, worst 5.9
```

Say: this is the honest number today, and here it is a crash because the borrowed filesystem
server could not start. With Ollama running the same table reports real completions. The
harness exists so the number stops being a guess; without it, one lucky run would be all we
could show.

## After recording

Rebuild the page with `python -m hatua build-ui` if you approved anything, then stop. Do not
edit the recording to hide the pause, the block or the crash: those three are the demo.
