"""Build the public website: a landing page, the practice school in the browser, and the guide.

    npm ci                       # brings Pyodide (Python for the browser) into node_modules
    python scripts/build_site.py # writes site_out/

site_out/
    index.html        the landing page (site_src/index.html)
    try/              the real Hatua portal, running in the visitor's browser with Pyodide
    guide/            the user guide, with its pictures
    teacher-page/     the older single-file teacher page (scripts/package_teacher_demo.py)

Only made-up data is used: the practice school from scripts/make_school_demo.py. Nothing
from a real store, inbox or log is read. Standard library only.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "site_out"
PYODIDE = REPO / "node_modules" / "pyodide"
PYODIDE_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")

# Builds the practice school with the browser's PIN hash (see site_src/bridge.py).
MAKE_HOME = """
import runpy, sys
from pathlib import Path
runpy.run_path(sys.argv[2], run_name="x")["main"](Path(sys.argv[1]))
sys.path.insert(0, sys.argv[3])
import bridge  # noqa: F401 - swaps in the browser's PIN hash before the school is set up
from hatua import school_demo
print(school_demo.setup())
"""

LOADER = """<script src="pyodide/pyodide.js"></script>
<script>
/* Practice website: the portal's requests to /api/ are answered inside this browser by
   the same Hatua code a laptop runs (site_src/bridge.py). Nothing is sent anywhere. */
window.HATUA_WEB = true;
(function () {
  const realFetch = window.fetch.bind(window);
  let jar = "";
  const ready = (async () => {
    const py = await loadPyodide({ indexURL: "pyodide/" });
    const zip = await (await realFetch("hatua-web.zip")).arrayBuffer();
    py.unpackArchive(zip, "zip", { extractDir: "/app" });
    await py.runPythonAsync("import sys; sys.path.insert(0, '/app'); import bridge");
    document.getElementById("web-loading")?.remove();
    return py.pyimport("bridge");
  })();
  ready.catch(err => { const el = document.getElementById("web-loading"); if (el) el.innerHTML = "<p>The practice school could not load in this browser. Try Chrome, Edge, Safari or Firefox, or download Hatua.</p>"; console.error(err); });
  window.fetch = async (url, opts = {}) => {
    const u = new URL(url, location.href);
    const at = u.pathname.indexOf("/api/");
    if (at < 0) return realFetch(url, opts);
    const bridge = await ready;
    const headers = { ...(opts.headers || {}), Host: "127.0.0.1:8765" };
    if (jar) headers.Cookie = jar;
    let body = opts.body;
    if (typeof body === "string") body = new TextEncoder().encode(body);
    else if (body instanceof ArrayBuffer) body = new Uint8Array(body);
    const out = bridge.handle(opts.method || "GET", u.pathname.slice(at) + u.search, JSON.stringify(headers), body || null);
    const [status, data, ctype, extra] = out.toJs({ dict_converter: Object.fromEntries });
    out.destroy();
    const cookie = extra["Set-Cookie"];
    if (cookie) jar = /Max-Age=0/.test(cookie) ? "" : cookie.split(";")[0];
    return new Response(data, { status, headers: { "Content-Type": ctype } });
  };
})();
</script>
"""

BANNER = """<div id="web-loading" style="position:fixed;inset:0;z-index:50;display:grid;place-items:center;background:var(--paper);padding:24px;text-align:center">
  <div style="display:grid;gap:10px;max-width:420px"><b style="font-size:1.3rem">Opening the practice school...</b>
  <p class="soft">Hatua is loading inside your browser. This takes a few seconds the first time.</p></div></div>
<div style="background:var(--jacaranda);color:var(--jacaranda-ink);padding:8px 16px;text-align:center;font-size:.9rem">
  Practice website. All people are made up. It runs in your browser and saves nothing.
  <a href="../" style="color:inherit;font-weight:700">Download Hatua</a> for your school, with the Qwen AI helper.</div>
"""


def practice_home(dest: Path) -> None:
    subprocess.run([sys.executable, "-c", MAKE_HOME, str(dest), str(REPO / "scripts" / "make_school_demo.py"),
                    str(REPO / "site_src")], cwd=REPO, check=True,
                   env={**os.environ, "PYTHONPATH": str(REPO), "HATUA_LLM": "off", "HATUA_HOME": str(dest)})


def web_zip(path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="hatua-site-") as tmp:
        home = Path(tmp) / "home"
        practice_home(home)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(REPO / "site_src" / "bridge.py", "bridge.py")
            for f in sorted((REPO / "hatua").glob("*.py")):
                if f.stem not in ("agent", "mcp_server", "measure"):
                    z.write(f, f"hatua/{f.name}")
            for f in sorted(home.rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts:
                    z.write(f, f"home/{f.relative_to(home).as_posix()}")


def main() -> None:
    if not (PYODIDE / "pyodide.asm.wasm").exists():
        raise SystemExit("Pyodide is missing. Run: npm ci")
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "try" / "pyodide").mkdir(parents=True)
    for name in PYODIDE_FILES:
        shutil.copy2(PYODIDE / name, OUT / "try" / "pyodide" / name)
    web_zip(OUT / "try" / "hatua-web.zip")
    page = (REPO / "ui" / "portal.html").read_text(encoding="utf-8")
    page = page.replace('href="/guide"', 'href="../guide/"').replace("<title>Hatua portal</title>",
                                                                     "<title>Hatua practice school</title>")
    page = page.replace("<script>\n\"use strict\";", LOADER + "<script>\n\"use strict\";", 1)
    page = page.replace("<body>\n", "<body>\n" + BANNER, 1)
    page = page.replace("</style>", "#ai-box { display: none !important; }\n</style>", 1)
    (OUT / "try" / "index.html").write_text(page, encoding="utf-8")
    (OUT / "guide").mkdir()
    shutil.copy2(REPO / "docs" / "USER_GUIDE.html", OUT / "guide" / "index.html")
    shutil.copytree(REPO / "docs" / "guide", OUT / "guide" / "guide")
    shutil.copy2(REPO / "site_src" / "index.html", OUT / "index.html")
    for f in (REPO / "site_src").glob("*.png"):
        shutil.copy2(f, OUT / f.name)
    subprocess.run([sys.executable, "scripts/package_teacher_demo.py"], cwd=REPO, check=True)
    shutil.copytree(REPO / "dist", OUT / "teacher-page")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print("Website ready:", OUT)


if __name__ == "__main__":
    main()
