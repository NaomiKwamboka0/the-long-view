"""Build a shareable demo only from freshly generated synthetic data.

Never reads the user's store, profiles, inbox or logs. Standard library only.
    python scripts/package_teacher_demo.py
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = Path(__file__).resolve().parent.parent


def main():
    dest = REPO / "dist"
    dest.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hatua-teacher-demo-") as temp:
        home = Path(temp)
        (home / "scripts").mkdir()
        shutil.copy2(REPO / "scripts" / "make_dummy_data.py", home / "scripts")
        env = {**os.environ, "HATUA_HOME": temp, "HATUA_TODAY": "2026-10-20",
               "PYTHONPATH": str(REPO), "HATUA_LLM": "", "LANGSMITH_TRACING": "false",
               "LANGCHAIN_TRACING_V2": "false"}
        subprocess.run([sys.executable, "-m", "hatua", "demo"], cwd=REPO, env=env, check=True)
        shutil.copy2(home / "ui" / "hatua.html", dest / "index.html")
    shutil.copy2(REPO / "TEACHER_TEST.md", dest / "START_HERE.txt")
    shutil.copy2(REPO / "PRIVACY.md", dest / "PRIVACY.txt")
    with zipfile.ZipFile(dest / "Hatua-Teacher-Test.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in ("index.html", "START_HERE.txt", "PRIVACY.txt"):
            bundle.write(dest / name, f"Hatua-Teacher-Test/{name}")
    print("Ready to share:", dest / "Hatua-Teacher-Test.zip")
    print("Standalone page:", dest / "index.html")


if __name__ == "__main__":
    main()
