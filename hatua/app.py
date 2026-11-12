"""The Hatua app: double-click to start. Used by the Mac and Windows downloads.

    Hatua                         open the practice school (made-up people)
    Hatua --school "D:/Our School" open a real school's Hatua folder
    Hatua cli teacher-list        run any `python -m hatua` command (for the school's Hatua admin)

What it does:

1. Picks the Hatua folder. The practice school lives in <home>/Hatua/Practice school
   and is made the first time (about 20 seconds). Nothing in it is real.
2. Starts Ollama if it is installed, so Qwen can answer. Downloading Qwen is a button
   on the sign-in page (hatua.ai_setup).
3. Starts the portal on 127.0.0.1 and opens it in the web browser.
4. Shows a small window with "Open Hatua", "User guide" and "Stop Hatua". If the
   computer has no window toolkit, it runs in the terminal instead.

The HATUA_* settings must be in place before hatua.config is imported, so this module
imports the rest of Hatua only inside main().
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

PRACTICE_TODAY = "2026-11-04"  # the practice school is set just after Term 3 2026, when results are due


def _free_port(preferred: int = 8765) -> int:
    for port in [preferred] + list(range(8766, 8800)):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("No free port for Hatua between 8765 and 8799.")


def _bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def _prepare(argv: list[str]) -> tuple[Path, bool]:
    """Set HATUA_HOME (and the practice school's date) before Hatua is imported."""
    if "--school" in argv:
        i = argv.index("--school")
        if i + 1 >= len(argv):
            raise SystemExit("Give the school's Hatua folder after --school.")
        home = Path(argv[i + 1]).expanduser().resolve()
        os.environ["HATUA_HOME"] = str(home)
        return home, False
    home = Path(os.environ.get("HATUA_APP_HOME", Path.home() / "Hatua")) / "Practice school"
    os.environ["HATUA_HOME"] = str(home)
    os.environ.setdefault("HATUA_TODAY", PRACTICE_TODAY)
    return home, True


def _make_practice(home: Path) -> None:
    import json
    import runpy

    from . import school_demo
    print("Making the practice school the first time. This takes about 20 seconds...")
    runpy.run_path(str(_bundle_root() / "scripts" / "make_school_demo.py"), run_name="not_main")["main"](home)
    school_demo.setup()
    (home / "app.json").write_text(json.dumps({"made_by": "Hatua app"}), encoding="utf-8")


class _Window:
    """A small control window: what Hatua is doing, and Open / User guide / Stop."""

    def __init__(self):
        import tkinter as tk
        self.tk = tk
        self.root = tk.Tk()
        self.root.title("Hatua")
        self.root.geometry("440x260")
        self.root.configure(bg="#eef2ee")
        self.title = tk.Label(self.root, text="Getting Hatua ready...", font=("Helvetica", 15, "bold"),
                              bg="#eef2ee", fg="#213029")
        self.title.pack(pady=(22, 6))
        self.text = tk.Label(self.root, text="The first time, this takes about 20 seconds.", bg="#eef2ee",
                             fg="#5b6a63", justify="center", wraplength=400)
        self.text.pack(pady=(0, 14))
        self.row = tk.Frame(self.root, bg="#eef2ee")
        self.row.pack()
        self.stop_btn = tk.Button(self.root, text="Stop Hatua", width=12, command=self.quit)
        self.stop_btn.pack(pady=14)
        tk.Label(self.root, text="Closing this window stops Hatua.", bg="#eef2ee", fg="#5b6a63").pack()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.stop = None

    def ready(self, url: str, guide: str, stop) -> None:
        def show():
            self.title.config(text="Hatua is running on this computer")
            self.text.config(text=f"It opened in your web browser.\nIf it did not, press Open Hatua, or go to {url}")
            self.tk.Button(self.row, text="Open Hatua", width=12, command=lambda: webbrowser.open(url)).pack(side="left", padx=6)
            self.tk.Button(self.row, text="User guide", width=12, command=lambda: webbrowser.open(guide)).pack(side="left", padx=6)
        self.stop = stop
        self.root.after(0, show)

    def failed(self, message: str) -> None:
        self.root.after(0, lambda: (self.title.config(text="Hatua could not start"), self.text.config(text=message)))

    def quit(self) -> None:
        if self.stop:
            self.stop()
        self.root.destroy()


def _start(home: Path, practice: bool):
    """Make the practice school if needed, start Ollama and the portal. Returns (url, guide, stop)."""
    if practice and not (home / "store" / "learners.json").exists():
        _make_practice(home)
    if not (home / "store").exists():
        raise SystemExit(f"There is no Hatua school in {home}. Ask the school's Hatua admin.")
    from . import ai_setup, portal
    if ai_setup.status()["ollama"] == "not_running":
        ai_setup.start_ollama()  # Qwen answers when Ollama is running; Hatua works without it
    port = _free_port()
    httpd = portal.make_server(port)
    threading.Thread(target=httpd.serve_forever, daemon=True, name="hatua-portal").start()
    url = f"http://127.0.0.1:{port}"
    print(f"Hatua is running: {url}\nSchool folder: {home}\nThe school drive (Excel folders): {home / 'school_drive'}")
    webbrowser.open(url)
    return url, url + "/guide", httpd.shutdown


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["cli"]:
        os.environ.setdefault("HATUA_HOME", str(Path.home() / "Hatua" / "School"))
        from .cli import main as cli_main
        return cli_main(argv[1:])
    home, practice = _prepare(argv)
    try:
        win = None if "--no-window" in argv else _Window()
    except Exception:
        win = None  # no window toolkit on this computer: run in the terminal
    if win is None:
        _url, _guide, stop = _start(home, practice)
        print("Press Ctrl+C to stop Hatua.")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        stop()
        return 0

    result: dict = {}

    def work():
        try:
            result["ok"] = _start(home, practice)
        except BaseException as exc:  # show it in the window instead of vanishing
            result["error"] = str(exc) or exc.__class__.__name__

    def poll():  # Tk is only touched from this (the main) thread
        if "ok" in result:
            win.ready(*result["ok"])
        elif "error" in result:
            win.failed(result["error"])
        else:
            win.root.after(200, poll)
    threading.Thread(target=work, daemon=True, name="hatua-start").start()
    win.root.after(200, poll)
    win.root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
