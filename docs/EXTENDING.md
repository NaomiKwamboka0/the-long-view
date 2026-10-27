# Adding to Hatua

One page, for a live review that adds a requirement while people watch. This recipe was
timed on a scratch branch: a read-only tool went from opening `tools.py` to green `pytest`
and `run_evals.py`, including its test and evaluation row, in **2 minutes 3 seconds**. The
timer ran from 14:22:25 to 14:24:28 on 27 October 2026, by someone who already knew the
code; allow longer for a first attempt. The branch was deleted afterwards.

## Add a read-only MCP tool

The agent can only do what a tool lets it do, so the tool is the unit of work.

1. **Write the function in `hatua/tools.py`.** Decorate it with `@audit.audited("the_name")`
   so the call is logged like every other one. Read-only: it may load from `store/`, and it
   must not write, delete, send or approve anything.
2. **Register it in `hatua/mcp_server.py`** by adding it to the `TOOLS` tuple. Nothing else
   in that file changes; the server derives its schema from the signature and docstring, so
   write the docstring for the model that will read it.
3. **Tell the planner only if you want the agent to use it.** Add a line to `SYSTEM` in
   `hatua/agent.py`. A tool the agent should not call needs no prompt change, and the fixed
   rules planner (`rules_plan`) is left alone unless the agreed plan itself changes.
4. **Add one test** in `tests/`. Assert the shape of the result and, for anything that
   filters, that it never sorts by a learner's results.
5. **Add one evaluation row** in `scripts/run_evals.py`: a new `E17` `@task(...)` that calls
   the tool through the same path the agent uses and prints a one-line detail.
6. **Update the count and the list** in `ARCHITECTURE.md` ("MCP servers"), and the tool
   table in `README.md` if a teacher would recognise it.
7. **Run the gate:** `ruff check hatua tests scripts`, `python -m pytest -q`,
   `python scripts/run_evals.py`, `npm run test:ui`. All four must pass before the change is
   worth showing anyone.

### Worked example (written during the timed trial, then deleted)

```python
# hatua/tools.py
@audit.audited("list_streams")
def list_streams() -> list[str]:
    """The streams in this class, for a picker. Read-only; no learner is ranked."""
    return sorted({learner["stream"] for learner in store.load("learners")})
```

```python
# tests/test_hatua.py
def test_list_streams_is_sorted_and_unique(local_store):
    assert tools.list_streams() == ["7A", "9A"]
```

Register with `tools.list_streams` in `TOOLS`, and the evaluation row reads
`@task("E17", "List the streams in the class, read-only")`. No prompt change was needed: the
fixed plan does not use a stream picker, and the agent was not asked to.

## Add a pattern type

A pattern is a claim about a learner, so it touches three files and one test.

1. **`hatua/patterns.py`**: detect it in `find()` and emit the English `statement`, the
   `evidence` ids it rests on, and any `caveats`. Never let it span a conflicting
   score/level term: `_caveats` and the conflict exclusion exist for that reason.
2. **`hatua/summary.py`**: if guardians may be told, add the family message to
   `GUARDIAN_EN` **and** `GUARDIAN_SW` under a new key, and add that key where the caller
   selects it.
3. **`hatua/guard.py`**: if the new pattern writes a fixed line of its own, add it to
   `TEMPLATE_LINES`; if it introduces new wording that could label or rank, extend
   `FORBIDDEN`. Then check the regression test that builds every draft for all 40 learners
   in both languages and both audiences still passes.
4. **Add an evaluation row** with a planted learner, and state what the pattern must *not*
   say. A pattern that fires when it should not is worse than one that stays quiet.

## What must never be added

- **No approve, share or send tool.** `approve` lives in `hatua/gate.py` and is deliberately
  absent from MCP; `update_profile` is blocked until an approval exists. A tool that
  approves, shares or messages would remove the human gate the whole design rests on.
- **No writes outside `data/`, `store/`, `logs/` and `profiles/`,** and no path that
  accepts `../`.
- **No model call in `patterns.py`, `summary.py` (the template path) or `guard.py`,** and no
  network call anywhere in the core. The only endpoint is loopback Ollama.
- **No tool that ranks, compares or labels a learner,** and no unlogged tool.
