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

The planner is told the steps and the rules, and it chooses the calls itself. A small supervisor sits around the model: it skips repeated calls, keeps teacher drafts in English, removes file names that do not exist, and asks the model to continue if it stops before every queued learner has a draft. If the model stops twice, the fixed rules finish the remaining steps. Each correction is logged. The supervisor can only fix or drop calls, never approve. Tool errors are returned to it as messages so it can correct course (eval A03). It has no tool that approves anything.

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

Every tool call is appended to `logs/audit.jsonl` (tool, actor, inputs, output, time, duration). Approvals go to `logs/approvals.jsonl`. Each line carries `prev`, the SHA-256 of the line before it, so `python -m hatua verify-log` reports an edited, deleted or reordered line and exits non-zero; files written before this existed are reported as unchained rather than broken. The chain does not stop someone who can rewrite the whole file: it only proves an edit if the latest hash is kept somewhere else, such as printed on the approval page or read out during the demo.

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
- **Conflicts are unconfirmed.** When a score and the rubric level disagree, Hatua preserves the original values and flags the record. The whole learning-area term is excluded from inference and breaks consecutive runs. A percentage is converted to a level only when the level is missing. The bands EE ≥75, ME ≥50, AE ≥25 are our assumption.
- **Approval is outside the agent.** `approve` is not exposed over MCP. `update_profile` checks that an approval exists for the draft and that the approved text's hash matches.
- **Local only.** There are no network calls in the core. The planner model runs in Ollama on `localhost`; any other host is refused. The endpoint parser allows literal loopback destinations only, with proxies and redirects disabled. Downloads, manually shared files, device backups and independently enabled third-party tracing require separate handling; local execution alone does not establish legal compliance. The optional wording rewrite (`hatua/llm.py`) follows the same rule and is dropped if it loses a citation or fails the guard.
- **The model plans; rules write.** The model decides which tools to call. Patterns and drafts come from deterministic code, so a claim about a learner never depends on what the model happened to generate.
- **Offline teacher page.** All data is embedded in one HTML file, so it runs on a school laptop without internet.

## Data in, and national systems

A school's own export enters through `map-export`, which copies only the columns a mapping names and, if an ID map is given, replaces real admission numbers with `HT-xxxx` kept in `data/private/` (git-ignored). [docs/INGESTION.md](docs/INGESTION.md) shows the whole path, what stays on the device, and why Hatua sits beside NEMIS/KEMIS rather than inside them; a real deployment needs the controller to finish [docs/DPIA.md](docs/DPIA.md), which is a draft, not an approved assessment.

## Teacher testing and privacy

`package_teacher_demo.py` builds the distribution using a fresh synthetic dataset in a temporary `HATUA_HOME`. It does not copy working school records. The standalone page includes a walkthrough, feedback export and the full privacy notice. Its Content Security Policy blocks application connections and external assets. There are no external fonts.

Browser decisions are namespaced by a fingerprint of the embedded dataset, including draft identities and hashes. Storage errors produce a visible warning. The clear-data action removes Hatua local-storage keys and in-memory feedback and edits, leaving other applications' storage alone. Exports, the embedded dataset, Python records and recipient copies are separate and are explained in the notice.

A previous decision is shown as current only when its source draft hash matches the new draft. Family templates remain locked if the approved teacher text was edited. Approval imports require a source hash; guardian imports also require an explicit sharing decision. Sign-in is optional (`HATUA_REQUIRE_AUTH=1`): it checks a registered teacher's PIN and records the registered name and ID instead of a typed name. It identifies a person among the teachers registered on one computer; it is not TSC or KEMIS sign-on, and anyone with file access can still edit the logs. The prototype still has no encryption at rest, concurrent-user storage or automated retention.
