# Architecture

## Agent loop (LangGraph, `hatua/agent.py`)

```
START ─► plan ─► tools ─► after_tools ─┐        plan: local Ollama model (qwen2.5:7b) picks the next
          ▲                             │              tool call; fixed rules if no model is running
          └─────────────────────────────┘        tools: MCP tools from hatua-mcp + filesystem server
          │ (no more tool calls)
          ▼
      self_check ──(a draft fails)──► plan        re-checks citations and wording, redrafts once
          │
          ▼
      teacher_gate  ◄── LangGraph interrupt: the graph pauses until a named teacher decides
          │
          ▼
         END
```

The planner is told the steps and the rules, and it chooses the calls itself. Tool errors are returned to it as messages so it can correct course (eval A03). It has no tool that approves anything.

## Data path

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

**Built: `hatua-mcp`.** It exposes seven tools:
- `list_learners` (read)
- `ingest_record` (writes: cleans an export and records quality flags)
- `review_queue` (read: learners with new records whose patterns are still going on, listed by ID)
- `find_patterns` (read, cited)
- `get_evidence` (read: opens any citation)
- `draft_summary` (writes a pending draft)
- `update_profile` (writes, gated)

The tool boundaries follow the teacher's own steps, so another school system could reuse them.

**Borrowed: the official filesystem MCP server** (`@modelcontextprotocol/server-filesystem`), scoped to `data/inbox` only. The agent uses `list_directory` to see which exports have arrived. It beats writing our own because it is a reviewed reference server that already enforces the folder boundary. Its write tools are not given to the planner.

## Decisions

- **Rules, not a model, find patterns.** The patterns are deterministic and explainable to a parent who asks "why?". They are:
  - Held strength: 3 or more terms in a row at EE.
  - Needs support: 4 or more terms in a row at AE or below, still going on.
  - Going up or going down: the two earliest terms in the window sit a full rubric step from the two latest, with no reversal in between.
  - Attendance: 2 or more terms in a row under 75%.
- **Learning areas are followed as families.** For example, Science and Technology (Grades 4–6) continues as Integrated Science (Grades 7–9).
- **Teacher levels win over scores.** When a score and the rubric level disagree, Hatua keeps the teacher's level and flags the record. A percentage is converted to a level only when the level is missing. The bands EE ≥75, ME ≥50, AE ≥25 are our assumption.
- **Approval is outside the agent.** `approve` is not exposed over MCP. `update_profile` checks that an approval exists for the draft and that the approved text's hash matches.
- **Local only.** There are no network calls in the core. The planner model runs in Ollama on `localhost`; any other host is refused. Learner data never leaves the laptop, which fits Kenya's rule that basic-education data is processed in Kenya. The optional wording rewrite (`hatua/llm.py`) follows the same rule and is dropped if it loses a citation or fails the guard.
- **The model plans; rules write.** The model decides which tools to call. Patterns and drafts come from deterministic code, so a claim about a learner never depends on what the model happened to generate.
- **Offline teacher page.** All data is embedded in one HTML file, so it runs on a school laptop without internet.
