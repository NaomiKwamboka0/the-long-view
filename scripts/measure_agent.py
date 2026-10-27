"""Measure the local model over many runs, and publish the result as it came out.

    python scripts/measure_agent.py --runs 10                 # qwen2.5:7b in Ollama
    python scripts/measure_agent.py --runs 10 --rules         # baseline, no model

Each run gets a fresh temporary HATUA_HOME, the synthetic class and a fixed HATUA_TODAY.
Crashed runs are recorded as failed runs, not dropped. This never falls back to the fixed
rules silently: without Ollama it stops and says so.

Results go to evals/agent_runs.json and are summarised on the terminal. Do not re-run a
batch to improve the numbers: the first complete batch is the published batch.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TODAY = "2026-10-13"
RESULTS = REPO / "evals" / "agent_runs.json"


# ---------------------------------------------------------------- one run (child process)
def child(args) -> int:
    """Run the agent once in this process. HATUA_HOME is already set by the driver."""
    sys.path.insert(0, str(REPO))
    from hatua import agent, cli  # imported after HATUA_HOME is set

    (Path(os.environ["HATUA_HOME"]) / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / "scripts" / "make_dummy_data.py", Path(os.environ["HATUA_HOME"]) / "scripts")
    cli.main(["setup", "--fresh"])

    started = time.perf_counter()
    out = asyncio.run(agent.run(max_learners=args.max, use_model=not args.rules,
                                use_fs=True, decide=None, verbose=False))
    seconds = round(time.perf_counter() - started, 1)
    activity = out.get("activity") or {}
    payload = {"ok": True, "crashed": False, "planner": out.get("planner"),
               "drafts": len(out.get("drafts", [])), "paused": out.get("paused", False),
               "seconds": seconds,
               "nudges": activity.get("nudges", 0),
               "corrections": activity.get("corrections", []),
               "tool_calls": activity.get("tool_calls", 0),
               "blocked_calls": activity.get("blocked_calls", 0),
               "tokens": activity.get("tokens", 0)}
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return 0


# ---------------------------------------------------------------- the batch
def model_digest(name: str) -> dict:
    """Ask Ollama what it has. Returns {"name", "digest"} or raises RuntimeError."""
    sys.path.insert(0, str(REPO))
    from hatua import agent
    from hatua.local_model import local_host, open_local

    host = local_host()
    if not host:
        raise RuntimeError("HATUA_OLLAMA_HOST is not a loopback address, so no model can be used.")
    try:
        with open_local(f"{host}/api/tags", timeout=5) as response:
            models = json.loads(response.read()).get("models", [])
    except Exception as exc:  # noqa: BLE001 - any failure means "cannot measure"
        raise RuntimeError(f"Ollama is not reachable at {host} ({exc}). Start it, then run again.") from None
    for model in models:
        if model.get("name") in (name, f"{name}:latest"):
            return {"name": model["name"], "digest": model.get("digest", "")}
    available = ", ".join(sorted(m.get("name", "?") for m in models)) or "none"
    raise RuntimeError(f"Ollama has no model called {name}. Available: {available}. "
                       f"Pull it with: ollama pull {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the Hatua agent over many runs.")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--max", type=int, default=3, help="Learners to draft per run")
    parser.add_argument("--rules", action="store_true", help="Fixed-rules baseline, no model")
    parser.add_argument("--out", default=str(RESULTS))
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--home", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.child:
        return child(args)

    sys.path.insert(0, str(REPO))
    from hatua import measure

    model = {"name": "none (fixed rules)", "digest": ""}
    if not args.rules:
        try:
            model = model_digest(args.model)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    runs: list[dict] = []
    for index in range(1, args.runs + 1):
        home = tempfile.mkdtemp(prefix="hatua-measure-")
        out_file = Path(home) / "run.json"
        env = {**os.environ, "HATUA_HOME": home, "HATUA_TODAY": TODAY, "HATUA_LLM": "",
               "HATUA_MODEL": args.model}
        started = time.perf_counter()
        command = [sys.executable, str(Path(__file__).resolve()), "--child", "--home", home,
                   "--out", str(out_file), "--max", str(args.max)]
        if args.rules:
            command.append("--rules")
        try:
            subprocess.run(command, env=env, check=False, timeout=1800)
        except subprocess.SubprocessError as exc:
            print(f"  run {index}: crashed ({type(exc).__name__})")
        elapsed = round(time.perf_counter() - started, 1)
        record = {"run": index, "crashed": True, "drafts": 0, "nudges": 0, "tool_calls": 0,
                  "blocked_calls": 0, "tokens": 0, "seconds": elapsed}
        if out_file.exists():
            try:
                record = {**record, **json.loads(out_file.read_text(encoding="utf-8"))}
            except ValueError:
                pass
        record["crashed"] = not out_file.exists() or not record.get("ok", False)
        record["unaided"] = (not record["crashed"] and record.get("drafts", 0) >= args.max
                             and record.get("nudges", 0) == 0)
        runs.append(record)
        state = "crashed" if record["crashed"] else (
            f"{record['drafts']} drafts, {record['nudges']} nudge(s), {record['seconds']:g}s")
        print(f"  run {index}/{args.runs}: {state}")
        shutil.rmtree(home, ignore_errors=True)

    summary = measure.summarise(runs, target=args.max)
    payload = {"generated": date.today().isoformat(), "mode": "rules" if args.rules else "model",
               "model": model, "machine": measure.machine_info(), "target_learners": args.max,
               "today": TODAY, "summary": summary, "runs": runs}
    measure.write_results(Path(args.out), payload)
    print("\n" + measure.table(summary, args.max))
    print(f"\nWritten to {Path(args.out)}. This batch is the published batch; do not re-run it to improve it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
