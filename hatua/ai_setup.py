"""Get Qwen ready on this computer, from the Hatua page, without a terminal.

Hatua itself still talks only to this computer. The pieces:

* Ollama is the free program that runs Qwen. If it is not installed, the page shows a
  link to https://ollama.com/download: the person installs it once, the normal way.
* If Ollama is installed but not running, Hatua starts it (`open -a Ollama` on a Mac,
  "ollama app.exe" on Windows, `ollama serve` elsewhere).
* If Qwen is missing, Hatua asks Ollama on 127.0.0.1 to download it (POST /api/pull).
  Ollama does the download; Hatua only reads the progress. About 4.7 GB, once.

Standard library only.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

from .local_model import local_host, open_local

DOWNLOAD_PAGE = "https://ollama.com/download"
SIZE = "about 4.7 GB"
_STATE = {"state": "idle", "percent": 0, "message": ""}
_LOCK = threading.Lock()


def model() -> str:
    return os.environ.get("HATUA_MODEL", "qwen2.5:7b")


def _ollama_path() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    system = platform.system()
    candidates = []
    if system == "Darwin":
        candidates = ["/Applications/Ollama.app", str(Path.home() / "Applications" / "Ollama.app"),
                      "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama"]
    elif system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Programs" / "Ollama"
        candidates = [str(base / "ollama app.exe"), str(base / "ollama.exe")]
    return next((c for c in candidates if Path(c).exists()), None)


def _tags() -> set[str] | None:
    """Model names Ollama has, or None when Ollama is not answering."""
    host = local_host()
    if not host:
        return None
    try:
        with open_local(f"{host}/api/tags", timeout=2) as r:
            return {m["name"] for m in json.loads(r.read()).get("models", [])}
    except Exception:
        return None


def status() -> dict:
    tags = _tags()
    want = model()
    if tags is None:
        ollama = "not_running" if _ollama_path() else "not_installed"
        ready = False
    else:
        ollama = "running"
        ready = want in tags or f"{want}:latest" in tags
    with _LOCK:
        pull = dict(_STATE)
    if ready and pull["state"] == "pulling":
        pull = {"state": "done", "percent": 100, "message": ""}
    return {"ollama": ollama, "model": want, "ready": ready, "pull": pull, "download_page": DOWNLOAD_PAGE,
            "size": SIZE, "system": {"Darwin": "mac", "Windows": "windows"}.get(platform.system(), "other")}


def start_ollama() -> bool:
    """Start Ollama if it is installed. Returns whether a start was tried."""
    path = _ollama_path()
    if not path:
        return False
    flags = {}
    if platform.system() == "Windows":
        flags["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        if platform.system() == "Darwin" and path.endswith(".app"):
            subprocess.Popen(["open", "-a", path], **flags)
        elif platform.system() == "Darwin" and Path("/Applications/Ollama.app").exists():
            subprocess.Popen(["open", "-a", "Ollama"], **flags)
        elif path.endswith("ollama app.exe"):
            subprocess.Popen([path], **flags)
        else:
            subprocess.Popen([path, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
    except OSError:
        return False
    return True


def _pull() -> None:
    host = local_host()
    body = json.dumps({"model": model(), "stream": True}).encode()
    try:
        req = urllib.request.Request(f"{host}/api/pull", data=body, headers={"Content-Type": "application/json"})
        with open_local(req, timeout=60) as resp:
            for line in resp:
                if not line.strip():
                    continue
                msg = json.loads(line)
                if msg.get("error"):
                    raise RuntimeError(msg["error"])
                total, done = msg.get("total") or 0, msg.get("completed") or 0
                with _LOCK:
                    if total:
                        _STATE["percent"] = max(_STATE["percent"], int(100 * done / total))
                    _STATE["message"] = str(msg.get("status", ""))[:80]
        with _LOCK:
            _STATE.update(state="done", percent=100, message="Qwen is ready.")
    except Exception as exc:
        with _LOCK:
            _STATE.update(state="error", message=f"The download stopped: {str(exc)[:120]}. Check the internet "
                                                 "connection and press the button again. It continues where it stopped.")


def get_qwen() -> dict:
    """Ask Ollama to download Qwen in the background. Safe to press twice."""
    if _tags() is None:
        raise RuntimeError("Ollama is not running yet. Start it first.")
    with _LOCK:
        if _STATE["state"] == "pulling":
            return dict(_STATE)
        _STATE.update(state="pulling", percent=0, message="Starting the download...")
    threading.Thread(target=_pull, daemon=True, name="hatua-qwen-download").start()
    return status()["pull"]
