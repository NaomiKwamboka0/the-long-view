"""Hatua's agent loop (LangGraph).

    python3 -m hatua agent              # plans with a local Ollama model if one is running
    python3 -m hatua agent --rules      # plans with simple fixed rules (no model)

Graph:  plan -> tools -> plan -> ... -> self_check -> teacher_gate -> END
                                          |  (draft fails a check)
                                          +-> plan (redraft)

* plan        : a LOCAL open-weights model (Ollama, default qwen2.5:7b) chooses the next
                tool call. If Ollama is not running, a fixed rules planner makes the same
                calls, so the demo always works.
* tools       : MCP tools from two servers:
                  hatua-mcp (ours)                     ingest, review_queue, find_patterns, ...
                  @modelcontextprotocol/server-filesystem (borrowed) to see what is in the inbox
* self_check  : re-checks every draft (citations exist and belong to the learner, no labels
                or comparisons). A failed draft goes back to the planner once.
* teacher_gate: the graph PAUSES (LangGraph interrupt). Only a named teacher can approve.
                The agent has no approve tool.

Nothing here calls an outside service. The model and both MCP servers run on this machine.
"""
from __future__ import annotations

import asyncio
import getpass
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from . import audit, auth, config, gate, guard, store
from . import tools as hatua_tools
from .summary import GateBlocked
from .local_model import local_host, open_local

FS_TOOLS = {"list_directory", "get_file_info"}  # the only borrowed tools the planner needs

SYSTEM = """You are Hatua, an assistant that prepares learner profiles for a Kenyan junior school class teacher.

Do these steps, one tool call at a time:
1. Call list_directory on the inbox folder to see which CSV exports have arrived.
2. Call ingest_record for each .csv file you see (just the file name). It is safe to repeat.
3. Call review_queue with max_learners={max_learners}.
4. For EACH learner in the queue: call find_patterns, then call draft_summary (audience "teacher").
   Teacher drafts are always in English. Do not repeat a call that already worked.
5. When every learner in the queue has a draft, stop calling tools and reply with one short
   sentence saying how many drafts are waiting for the teacher.

Rules you must never break:
- Never assign a pathway, track or label. Never rank or compare learners.
- You cannot approve anything. A named teacher approves after you stop.
- Do not call update_profile; it is blocked until a teacher approves.
- If a tool returns an error, read it and try a corrected call once."""


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    drafts: list[dict]
    checked: list[dict]
    redrafts: int
    planner: str
    max_learners: int
    inbox: str
    fallback: bool


# ---------------------------------------------------------------- helpers
def _content(msg: ToolMessage) -> Any:
    """MCP tool results arrive as text (sometimes a list of text blocks). Return parsed JSON if possible."""
    c = msg.content
    if isinstance(c, list):
        c = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in c)
    try:
        return json.loads(c)
    except (TypeError, ValueError):
        return c


def ollama_model() -> str | None:
    """Return the model name if a local Ollama server has it, else None."""
    host = local_host()
    if not host:
        return None  # local only, by design
    want = os.environ.get("HATUA_MODEL", "qwen2.5:7b")
    try:
        with open_local(f"{host}/api/tags", timeout=2) as r:
            names = {m["name"] for m in json.loads(r.read()).get("models", [])}
    except Exception:
        return None
    return want if want in names or f"{want}:latest" in names else None


def servers(use_fs: bool = True) -> dict:
    code = str(Path(__file__).resolve().parent.parent)  # folder that holds the hatua package
    env = {**os.environ, "HATUA_HOME": str(config.ROOT), "PYTHONPATH": code}
    conns = {"hatua": {"command": sys.executable, "args": ["-m", "hatua.mcp_server"],
                       "transport": "stdio", "env": env, "cwd": code}}
    if use_fs and shutil.which("npx"):
        conns["filesystem"] = {"command": "npx",
                               "args": ["-y", "@modelcontextprotocol/server-filesystem", str(config.INBOX)],
                               "transport": "stdio", "env": dict(os.environ)}
    return conns


# ---------------------------------------------------------------- supervisor
# A small local model (7B) plans well most of the time, but on a real laptop run it stopped after
# one learner, repeated a call, asked for a Kiswahili teacher draft and invented a file name.
# These checks keep it on track. They never add power: they only fix or drop calls, and finish
# the agreed steps with the rules planner when the model stops too early.
MAX_NUDGES = 2
VERBOSE = True


def print_note(text: str) -> None:
    if VERBOSE:
        print(f"  [guide] {text}")


def queue_ids(messages: list) -> list[str]:
    """Learner IDs from the largest review_queue result so far (a later empty one does not wipe it)."""
    best: list[str] = []
    for m in messages:
        if isinstance(m, ToolMessage) and m.name == "review_queue":
            data = _content(m)
            ids = [l["learner_id"] for l in data.get("learners", [])] if isinstance(data, dict) else []
            if len(ids) >= len(best):
                best = ids
    return best


def _done_calls(messages: list) -> set[str]:
    """Signatures of calls that already returned without an error."""
    ok_ids = {m.tool_call_id for m in messages if isinstance(m, ToolMessage) and m.status != "error"}
    sigs = set()
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls:
                if tc["id"] in ok_ids:
                    sigs.add(_sig(tc["name"], tc["args"]))
    return sigs


def _sig(name: str, args: dict) -> str:
    return name + json.dumps(args, sort_keys=True)


def tidy_calls(msg: AIMessage, state: State) -> tuple[AIMessage, list[str]]:
    """Fix or drop model tool calls that break the plan. Returns the new message and what changed."""
    notes, kept = [], []
    done = _done_calls(state["messages"])
    redraft = isinstance(state["messages"][-1], HumanMessage) and state["messages"][-1].content.startswith("REDRAFT")
    inbox = {p.name for p in config.INBOX.glob("*.csv")}
    for tc in msg.tool_calls:
        name, args = tc["name"], dict(tc.get("args") or {})
        if name == "draft_summary" and args.get("audience", "teacher") == "teacher":
            if args.get("language", "en") != "en":
                notes.append(f"teacher draft for {args.get('learner_id')} set to English")
            args = {"learner_id": args.get("learner_id", ""), "audience": "teacher", "language": "en"}
        if name == "review_queue":
            if args.get("file_name") and Path(str(args["file_name"])).name not in inbox:
                notes.append(f"unknown file '{args['file_name']}' removed from review_queue")
                args.pop("file_name")
            args["max_learners"] = state["max_learners"]
        sig = _sig(name, args)
        if sig in done and not (redraft and name == "draft_summary") and name != "list_directory":
            notes.append(f"repeated {name} call skipped")
            continue
        if sig in {_sig(k["name"], k["args"]) for k in kept}:
            continue  # the same call twice in one step
        kept.append({**tc, "args": args})
    return AIMessage(content=msg.content, tool_calls=kept, id=msg.id), notes


def work_left(state: State, tool_names: set) -> AIMessage | None:
    """The next call the agreed plan still needs, or None when every queued learner has a draft."""
    nxt = rules_plan({**state, "_tool_names": tool_names})  # type: ignore[typeddict-item]
    return nxt if nxt.tool_calls else None


# ---------------------------------------------------------------- rules planner
def rules_plan(state: State) -> AIMessage:
    """Fixed plan with the same tool calls the model is asked to make. Used when no model runs."""
    called: dict[str, list] = {}
    results: dict[str, list] = {}
    for m in state["messages"]:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls:
                called.setdefault(tc["name"], []).append(tc["args"])
        if isinstance(m, ToolMessage):
            results.setdefault(m.name, []).append(_content(m))
    n = sum(len(v) for v in called.values())

    def call(name, **args):
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"rules-{n}"}])

    # Redraft request from self_check
    last = state["messages"][-1]
    if isinstance(last, HumanMessage) and last.content.startswith("REDRAFT"):
        return call("draft_summary", learner_id=last.content.split()[1], audience="teacher")

    if "list_directory" not in called and "list_directory" in state.get("_tool_names", ()):  # type: ignore[operator]
        return call("list_directory", path=state["inbox"])
    if "ingest_record" not in called:
        listing = results.get("list_directory", [""])[-1]
        files = [line.split("]", 1)[-1].strip() for line in str(listing).splitlines() if line.endswith(".csv")]
        if not files:
            files = sorted(p.name for p in config.INBOX.glob("*.csv"))
        if files:
            return AIMessage(content="", tool_calls=[
                {"name": "ingest_record", "args": {"file_name": f}, "id": f"rules-{n}-{i}"}
                for i, f in enumerate(files)])
    if "review_queue" not in called:
        return call("review_queue", max_learners=state["max_learners"])
    learners = queue_ids(state["messages"])
    found = {a["learner_id"] for a in called.get("find_patterns", [])}
    drafted = {d["learner_id"] for d in state.get("drafts", [])}
    for lid in learners:
        if lid not in found:
            return call("find_patterns", learner_id=lid)
        if lid not in drafted:
            return call("draft_summary", learner_id=lid, audience="teacher")
    return AIMessage(content=f"{len(learners)} draft(s) are waiting for the class teacher to review.")


# ---------------------------------------------------------------- graph
def build_graph(tools: list, model=None):
    tool_names = {t.name for t in tools}
    llm = model.bind_tools(tools) if model is not None else None

    def log_plan(actor: str, msg: AIMessage, notes: list[str] | None = None) -> None:
        audit.write_event({"tool": "agent.plan", "actor": actor, "ok": True,
                           "output": {"tool_calls": [{"name": t["name"], "args": t["args"]} for t in msg.tool_calls],
                                      "text": (msg.content or "")[:300] if isinstance(msg.content, str) else "",
                                      "corrections": notes or []}})

    def plan(state: State) -> dict:
        if llm is None or state.get("fallback"):
            msg = rules_plan({**state, "_tool_names": tool_names})  # type: ignore[typeddict-item]
            log_plan("rules-fallback" if llm is not None else "rules", msg)
            return {"messages": [msg]}

        history, added = list(state["messages"]), []
        for attempt in range(MAX_NUDGES + 1):
            raw = llm.invoke(history)
            msg, notes = tidy_calls(raw, {**state, "messages": history})
            log_plan(state["planner"], msg, notes)
            added.append(msg)
            if notes:
                print_note(f"corrected: {'; '.join(notes)}")
            if msg.tool_calls:
                return {"messages": added}
            left = work_left({**state, "messages": history + [msg]}, tool_names)
            if left is None:
                return {"messages": added}  # the agreed work is done
            if attempt < MAX_NUDGES:
                todo = [l for l in queue_ids(history) if l not in {d["learner_id"] for d in state.get("drafts", [])}]
                nudge = HumanMessage(content=(
                    "Not finished yet. " + (f"These learners still have no teacher draft: {', '.join(todo)}. "
                                            "For each one call find_patterns, then draft_summary (audience \"teacher\")."
                                            if todo else "Continue with the next step of the plan.")))
                print_note("model stopped early; asked it to continue")
                history += [msg, nudge]
                added.append(nudge)
        # The model stopped twice without finishing: the rules planner makes the remaining call.
        log_plan("rules-fallback", left)
        print_note("model stopped again; the fixed rules finish the remaining steps")
        added.append(left)
        return {"messages": added, "fallback": True}

    def after_tools(state: State) -> dict:
        """Log borrowed-server calls (ours log themselves) and collect new drafts."""
        drafts = list(state.get("drafts", []))
        for m in reversed(state["messages"]):
            if not isinstance(m, ToolMessage):
                break
            data = _content(m)
            if m.name not in {"list_learners", "ingest_record", "review_queue", "find_patterns",
                              "get_evidence", "draft_summary", "update_profile"}:
                audit.write_event({"tool": f"filesystem.{m.name}", "actor": "agent",
                                   "ok": m.status != "error", "output": str(data)[:500]})
            if m.name == "draft_summary" and isinstance(data, dict) and data.get("draft_id"):
                drafts = [d for d in drafts if d["learner_id"] != data["learner_id"]] + [
                    {"draft_id": data["draft_id"], "learner_id": data["learner_id"], "hash": data["hash"]}]
        return {"drafts": drafts}

    def route_plan(state: State) -> str:
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else "self_check"

    def self_check(state: State) -> dict:
        checked, redo = [], None
        by_id = {d["draft_id"]: d for d in store.load("drafts")}
        for d in state.get("drafts", []):
            rec = by_id.get(d["draft_id"])
            problems = ["draft not found"] if rec is None else guard.check(rec["text"], d["learner_id"])
            checked.append({**d, "problems": problems})
            if problems and redo is None:
                redo = d["learner_id"]
        audit.write_event({"tool": "agent.self_check", "actor": "agent", "ok": not redo,
                           "output": [{"draft_id": c["draft_id"], "problems": c["problems"]} for c in checked]})
        if redo and state.get("redrafts", 0) < 1:
            return {"checked": checked, "redrafts": state.get("redrafts", 0) + 1,
                    "messages": [HumanMessage(content=f"REDRAFT {redo}: the draft failed checks. Draft it again.")]}
        return {"checked": checked}

    def route_check(state: State) -> str:
        last = state["messages"][-1]
        return "plan" if isinstance(last, HumanMessage) and last.content.startswith("REDRAFT") else "teacher_gate"

    def teacher_gate(state: State) -> dict:
        ready = [c for c in state.get("checked", []) if not c["problems"]]
        if not ready:
            return {}
        decision = interrupt({"waiting_for": "named class teacher", "drafts": ready})
        teacher = (decision or {}).get("teacher", "").strip()
        session = (decision or {}).get("session")
        results = []
        for c in ready:
            choice = (decision or {}).get("decisions", {}).get(c["draft_id"], "pending")
            if choice not in ("approve", "reject") or not teacher:
                results.append({"draft_id": c["draft_id"], "result": "left pending"})
                continue
            try:
                gate.approve(c["draft_id"], teacher=teacher, decision=choice,
                             expected_hash=c["hash"], session=session)
                saved = hatua_tools.update_profile(c["draft_id"])["saved"] if choice == "approve" else None
                results.append({"draft_id": c["draft_id"], "result": choice, "saved": saved})
            except (GateBlocked, ValueError) as exc:
                results.append({"draft_id": c["draft_id"], "result": f"blocked: {exc}"})
        return {"messages": [AIMessage(content=json.dumps({"teacher": teacher or None, "results": results}))]}

    g = StateGraph(State)
    g.add_node("plan", plan)
    g.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    g.add_node("after_tools", after_tools)
    g.add_node("self_check", self_check)
    g.add_node("teacher_gate", teacher_gate)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", route_plan, {"tools": "tools", "self_check": "self_check"})
    g.add_edge("tools", "after_tools")
    g.add_edge("after_tools", "plan")
    g.add_conditional_edges("self_check", route_check, {"plan": "plan", "teacher_gate": "teacher_gate"})
    g.add_edge("teacher_gate", END)
    return g.compile(checkpointer=InMemorySaver())


def _print_step(update: dict) -> None:
    for node, data in update.items():
        if not isinstance(data, dict):
            continue
        for m in data.get("messages", []) or []:
            if isinstance(m, AIMessage) and m.tool_calls:
                for tc in m.tool_calls:
                    print(f"  [{node}] call {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})")
            elif isinstance(m, ToolMessage):
                text = str(_content(m))
                print(f"  [tool]  {m.name} -> {text[:110].replace(chr(10), ' ')}{'...' if len(text) > 110 else ''}")
            elif isinstance(m, AIMessage) and m.content and node == "plan":
                print(f"  [plan]  {m.content}")
        if node == "self_check":
            for c in data.get("checked", []):
                print(f"  [check] {c['draft_id']} {c['learner_id']}: {'OK' if not c['problems'] else c['problems']}")


async def run(max_learners: int = 3, use_model: bool = True, use_fs: bool = True,
              teacher: str | None = None, decide=None, model=None, verbose: bool = True) -> dict:
    """Run the agent once. `decide(drafts) -> {"teacher": str, "decisions": {draft_id: approve|reject}}`."""
    global VERBOSE
    VERBOSE = verbose
    name = None
    if model is None and use_model:
        name = ollama_model()
        if name:
            from langchain_ollama import ChatOllama
            model = ChatOllama(model=name, temperature=0,
                               base_url=local_host(),
                               client_kwargs={"trust_env": False, "follow_redirects": False})
    planner = f"ollama:{name}" if name else ("model:test" if model is not None else "rules")
    conns = servers(use_fs)
    client = MultiServerMCPClient(conns)
    all_tools = await client.get_tools()
    tools = [t for t in all_tools if t.name in FS_TOOLS or t.name not in
             {"read_file", "read_text_file", "read_media_file", "read_multiple_files", "write_file", "edit_file",
              "create_directory", "directory_tree", "move_file", "search_files", "list_allowed_directories",
              "list_directory_with_sizes"}]
    if verbose:
        print(f"Planner: {planner}")
        print(f"MCP servers: {', '.join(conns)}" + ("" if "filesystem" in conns else
              "  (borrowed filesystem server skipped: install Node.js to enable it)"))
        print(f"Tools: {', '.join(sorted(t.name for t in tools))}\n")
    graph = build_graph(tools, model)
    cfg = {"configurable": {"thread_id": "hatua"}, "recursion_limit": 80}
    start = {"messages": [SystemMessage(content=SYSTEM.format(max_learners=max_learners)),
                          HumanMessage(content=f"New exports may be in the inbox folder: {config.INBOX}. "
                                               f"Prepare drafts for up to {max_learners} learners.")],
             "drafts": [], "checked": [], "redrafts": 0, "planner": planner, "fallback": False,
             "max_learners": max_learners, "inbox": str(config.INBOX)}
    audit.write_event({"tool": "agent.start", "actor": planner, "ok": True,
                       "inputs": {"max_learners": max_learners, "servers": list(conns)}})
    async for update in graph.astream(start, cfg, stream_mode="updates"):
        if verbose:
            _print_step(update)
    snap = graph.get_state(cfg)
    outcome = {"planner": planner, "servers": list(conns), "drafts": snap.values.get("checked", []),
               "paused": bool(snap.interrupts)}
    if snap.interrupts:
        drafts = snap.interrupts[0].value["drafts"]
        resume = decide(drafts) if decide else {"teacher": teacher or "", "decisions": {}}
        async for update in graph.astream(Command(resume=resume), cfg, stream_mode="updates"):
            pass
        final = graph.get_state(cfg).values["messages"][-1]
        outcome["gate"] = json.loads(final.content)
    return outcome


def cli_decide(drafts: list[dict]) -> dict:
    """Ask the teacher in the terminal. When sign-in is on, the PIN is never kept."""
    by_id = {d["draft_id"]: d for d in store.load("drafts")}
    print("\n=== Paused for the class teacher. Nothing is saved until you approve. ===")
    if not sys.stdin.isatty():
        print("No terminal input available, so all drafts are left pending.")
        return {"teacher": "", "decisions": {}}
    session = None
    if config.require_auth():
        teacher_id = input("Your teacher ID: ").strip()
        try:
            identity = auth.login(teacher_id, getpass.getpass("Your PIN (input is hidden): "))
        except GateBlocked as exc:
            print(f"Sign-in failed, so every draft is left pending. {exc}")
            return {"teacher": "", "decisions": {}}
        teacher, session = identity["name"], identity["session"]
        print(f"Signed in as {teacher} ({identity['teacher_id']}).")
    else:
        teacher = input("Your full name (Enter to leave everything pending): ").strip()
        if not teacher:
            return {"teacher": "", "decisions": {}}
    decisions = {}
    for d in drafts:
        print("\n" + "-" * 70 + "\n" + by_id[d["draft_id"]]["text"] + "\n" + "-" * 70)
        a = input(f"{d['learner_id']}: [a]pprove, [r]eject, Enter to leave pending: ").strip().lower()
        decisions[d["draft_id"]] = {"a": "approve", "r": "reject"}.get(a[:1], "pending")
    return {"teacher": teacher, "decisions": decisions, "session": session}


def main(max_learners: int = 3, rules: bool = False, no_fs: bool = False) -> None:
    out = asyncio.run(run(max_learners=max_learners, use_model=not rules, use_fs=not no_fs, decide=cli_decide))
    if "gate" in out:
        for r in out["gate"]["results"]:
            print(f"  {r['draft_id']}: {r['result']}" + (f" -> {r['saved']}" if r.get("saved") else ""))
    print("\nEvery step is in logs/audit.jsonl. Rebuild the page with: python3 -m hatua build-ui")
