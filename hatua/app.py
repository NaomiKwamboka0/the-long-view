"""The Hatua app: double-click to start. Used by the Mac and Windows downloads.

    Hatua                         start your own school: empty, you create your account and add your learners
    Hatua --practice              open the practice school (made-up people, for trying Hatua out)
    Hatua --school "D:/Our School" open a school's Hatua folder someone else prepared
    Hatua cli teacher-list        run any `python -m hatua` command (for the school's Hatua admin)

What it does:

1. Picks the Hatua folder: <home>/Hatua/My school, empty at first (the sign-in page asks the person to
   create their account). With --practice it is <home>/Hatua/Practice school, made the first time
   (about 20 seconds); nothing in that one is real.
2. Starts Ollama if it is installed, so Qwen can answer. Downloading Qwen is a button
   on the sign-in page (hatua.ai_setup).
3. Starts the portal on 127.0.0.1 and opens it in the web browser.
4. Shows a small window with "Open Hatua", "User guide" and "Stop Hatua". If the
   computer has no window toolkit, it runs in the terminal instead.

EXPERIMENTAL: `Hatua --native` (needs `pip install pywebview`) shows Hatua in its own window with the
computer's built-in web view instead of a browser. The page loads there, but the links that open a new
tab (the user guide, WhatsApp) are not verified yet, so it is not the default.

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


def _prepare(argv: list[str]) -> tuple[Path, str]:
    """Set HATUA_HOME (and the practice school's date) before Hatua is imported.
    Returns the folder and the mode: "mine" (a new, empty school), "practice" or "school"."""
    if "--school" in argv:
        i = argv.index("--school")
        if i + 1 >= len(argv):
            raise SystemExit("Give the school's Hatua folder after --school.")
        home = Path(argv[i + 1]).expanduser().resolve()
        os.environ["HATUA_HOME"] = str(home)
        return home, "school"
    base = Path(os.environ.get("HATUA_APP_HOME", Path.home() / "Hatua"))
    if "--practice" in argv:
        home = base / "Practice school"
        os.environ["HATUA_HOME"] = str(home)
        os.environ.setdefault("HATUA_TODAY", PRACTICE_TODAY)
        return home, "practice"
    home = base / "My school"
    os.environ["HATUA_HOME"] = str(home)
    return home, "mine"


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


def _start(home: Path, mode: str, open_browser: bool = True):
    """Make the practice school or an empty school if needed, start Ollama and the portal. Returns (url, guide, stop)."""
    if mode == "practice" and not (home / "store" / "learners.json").exists():
        _make_practice(home)
    if mode == "mine":
        (home / "store").mkdir(parents=True, exist_ok=True)   # empty: the sign-in page creates the first account
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
    if open_browser:
        webbrowser.open(url)
    return url, url + "/guide", httpd.shutdown


LOADING = """<!doctype html><meta charset="utf-8"><title>Hatua</title>
<body style="margin:0;display:grid;place-items:center;height:100vh;background:#eef2ee;color:#213029;font:17px -apple-system,system-ui,sans-serif;text-align:center">
<div><b style="font-size:1.4rem">Getting Hatua ready...</b><p style="color:#5b6a63">The first time, this takes about 20 seconds.</p></div>"""


class _NativeApi:
    """What the page may ask the app to do. Pages inside Hatua open in Hatua's own windows;
    only outside links (WhatsApp) go to the computer's own browser or WhatsApp app."""

    def __init__(self, base: str):
        self.base = base

    def open_external(self, url: str) -> bool:
        import webview
        url = str(url or "")
        if url.startswith(self.base + "/"):                      # the user guide, the video guide
            webview.create_window("Hatua", url, width=1000, height=760)
            return True
        if url.startswith(("https://wa.me/", "https://api.whatsapp.com/")):   # a WhatsApp chat, never anything else
            webbrowser.open(url)
            return True
        return False


def _run_native(home: Path, mode: str, check=None) -> int | None:
    """Show Hatua in its own window. Returns None when this computer has no built-in web view."""
    try:
        import webview
    except Exception:
        return None
    window = webview.create_window("Hatua", html=LOADING, width=1240, height=860, min_size=(420, 600))
    state: dict = {}

    def work():
        try:
            url, _guide, stop = _start(home, mode, open_browser=False)
            state["stop"] = stop
            window.expose(_NativeApi(url.rstrip("/")).open_external)
            window.load_url(url)
            if check:
                check(window, url)
        except BaseException as exc:
            window.load_html(f"<body style='font:17px system-ui;padding:40px'><h2>Hatua could not start</h2><p>{exc or exc.__class__.__name__}</p>")

    try:
        webview.start(work)
    except Exception:
        return None
    if state.get("stop"):
        state["stop"]()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["cli"]:
        os.environ.setdefault("HATUA_HOME", str(Path.home() / "Hatua" / "School"))
        from .cli import main as cli_main
        return cli_main(argv[1:])
    home, mode = _prepare(argv)
    if "--native" in argv:
        code = _run_native(home, mode)
        if code is not None:
            return code
    try:
        win = None if "--no-window" in argv else _Window()
    except Exception:
        win = None  # no window toolkit on this computer: run in the terminal
    if win is None:
        _url, _guide, stop = _start(home, mode)
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
            result["ok"] = _start(home, mode)
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
