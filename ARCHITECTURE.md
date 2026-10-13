# Architecture

## Shape

```
data/inbox/*.csv ──► ingest_record ──► store/ (clean records + quality flags)
                                           │
                       find_patterns ◄─────┘   cited: R- assessment, N- note, A- attendance
                            │
                       draft_summary ──► guard (no labels, no comparisons, every claim cited)
                            │
                  ┌─────────┴──────────┐
                  │  TEACHER GATE      │  approve: CLI or ui/hatua.html → import-approvals
                  │  (not an MCP tool) │  named teacher + hash of the exact approved text
                  └─────────┬──────────┘
                       update_profile ──► profiles/HT-xxxx.json
                            │
             guardian draft (EN / Kiswahili) ──► teacher ticks "share" ──► text file the teacher sends
```

Every tool call is appended to `logs/audit.jsonl` (tool, actor, inputs, output, time, duration). Approvals go to `logs/approvals.jsonl`.

## MCP servers

**Built: `hatua-mcp`.** It exposes six tools:
- `list_learners` (read)
- `ingest_record` (writes: cleans an export and records quality flags)
- `find_patterns` (read, cited)
- `get_evidence` (read: opens any citation)
- `draft_summary` (writes a pending draft)
- `update_profile` (writes, gated)

The tool boundaries follow the teacher's own steps, so another school system could reuse them.

**Borrowed (planned): the official filesystem MCP server**, scoped to `data/inbox`. It lets the agent see which exports have arrived without us writing file-handling code. It is a reference implementation that others already review.

## Decisions

- **Rules, not a model, find patterns.** The patterns are deterministic and explainable to a parent who asks "why?". They are:
  - Held strength: 3 or more terms in a row at EE.
  - Needs support: 4 or more terms in a row at AE or below, still going on.
  - Going up or going down: the two earliest terms in the window sit a full rubric step from the two latest, with no reversal in between.
  - Attendance: 2 or more terms in a row under 75%.
- **Learning areas are followed as families.** For example, Science and Technology (Grades 4–6) continues as Integrated Science (Grades 7–9).
- **Teacher levels win over scores.** When a score and the rubric level disagree, Hatua keeps the teacher's level and flags the record. A percentage is converted to a level only when the level is missing. The bands EE ≥75, ME ≥50, AE ≥25 are our assumption.
- **Approval is outside the agent.** `approve` is not exposed over MCP. `update_profile` checks that an approval exists for the draft and that the approved text's hash matches.
- **Local only.** There are no network calls in the core. The optional model rewrite (`hatua/llm.py`) talks only to Ollama on `localhost`, is off by default, and its output is dropped if it loses a citation or fails the guard.
- **Offline teacher page.** All data is embedded in one HTML file, so it runs on a school laptop without internet.
