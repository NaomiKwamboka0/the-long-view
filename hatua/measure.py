"""Summarise batches of agent runs, and describe the machine they ran on.

Kept out of the script so the arithmetic can be tested with fabricated records. The
numbers here are the ones EVALS.md is allowed to quote, so nothing may be rounded up
or dropped: a crashed run is a failed run.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def _p90(values: list[float]) -> float:
    """Nearest-rank 90th percentile: never less than the ninth of ten sorted runs."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * 9 // 10))  # ceil(0.9n)
    return float(ordered[min(rank, len(ordered)) - 1])


def summarise(runs: list[dict], target: int = 3) -> dict:
    """Count unaided completions and the spread of nudges and wall time.

    A run is unaided when it produced a draft for every target learner and the supervisor
    never had to step in. Crashes count as failures, never as missing data.
    """
    total = len(runs)
    unaided = [r for r in runs if not r.get("crashed") and r.get("drafts", 0) >= target
               and r.get("nudges", 0) == 0]
    nudges = [int(r.get("nudges", 0)) for r in runs]
    seconds = [float(r.get("seconds", 0.0)) for r in runs]
    return {
        "runs": total,
        "unaided": len(unaided),
        "unaided_rate": round(len(unaided) / total, 3) if total else 0.0,
        "crashed": sum(1 for r in runs if r.get("crashed")),
        "nudges": {"median": _median(nudges), "worst": max(nudges, default=0),
                   "total": sum(nudges)},
        "seconds": {"median": round(_median(seconds), 1), "p90": round(_p90(seconds), 1),
                    "worst": round(max(seconds, default=0.0), 1)},
        "tool_calls": sum(int(r.get("tool_calls", 0)) for r in runs),
        "blocked_calls": sum(int(r.get("blocked_calls", 0)) for r in runs),
    }


def table(summary: dict, target: int) -> str:
    """A short table for the terminal, and the same numbers go into EVALS.md."""
    return "\n".join([
        f"Unaided completions : {summary['unaided']}/{summary['runs']} "
        f"(finished all {target} learners with no supervisor help)",
        f"Crashed runs        : {summary['crashed']}",
        f"Nudges              : median {summary['nudges']['median']:g}, "
        f"worst {summary['nudges']['worst']}, total {summary['nudges']['total']}",
        f"Wall seconds        : median {summary['seconds']['median']:g}, "
        f"p90 {summary['seconds']['p90']:g}, worst {summary['seconds']['worst']:g}",
        f"Tool calls          : {summary['tool_calls']} "
        f"({summary['blocked_calls']} returned an error)",
    ])


def _total_ram_gb() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024 / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    try:  # Windows
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.ullTotalPhys / 1024 ** 3, 1)
    except (OSError, AttributeError, ValueError):
        pass
    return None


def _gpu() -> str | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    name = out.stdout.strip().splitlines()[0].strip() if out.stdout.strip() else ""
    return name or None


def machine_info() -> dict:
    return {"platform": platform.platform(), "processor": platform.processor() or platform.machine(),
            "cpus": os.cpu_count(), "ram_gb": _total_ram_gb(), "gpu": _gpu()}


def write_results(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
