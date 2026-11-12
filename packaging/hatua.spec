# PyInstaller recipe for the Hatua download. Build from the repository root:
#     pyinstaller packaging/hatua.spec --noconfirm
# The app is the teacher and parent portal only: standard library, no LangGraph.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
datas = [
    (str(ROOT / "ui" / "portal.html"), "ui"),
    (str(ROOT / "docs" / "USER_GUIDE.html"), "docs"),
    (str(ROOT / "docs" / "guide"), "docs/guide"),
    (str(ROOT / "scripts" / "make_school_demo.py"), "scripts"),
    (str(ROOT / "data" / "raw"), "data/raw"),
    (str(ROOT / "data" / "inbox" / "2026_T3_new_records.csv"), "data/inbox"),
    (str(ROOT / "data" / "calendar"), "data/calendar"),
    (str(ROOT / "docs" / "templates"), "docs/templates"),
]
hidden = [f"hatua.{m.stem}" for m in (ROOT / "hatua").glob("*.py")
          if m.stem not in ("agent", "mcp_server", "measure", "__main__")]

a = Analysis([str(ROOT / "packaging" / "hatua_app.py")], pathex=[str(ROOT)], datas=datas, hiddenimports=hidden,
             excludes=["langgraph", "langchain_core", "langchain_ollama", "langchain_mcp_adapters", "mcp", "pytest",
                        "numpy", "pandas"], noarchive=False)
pyz = PYZ(a.pure)
icon = str(ROOT / "packaging" / ("hatua.icns" if sys.platform == "darwin" else "hatua.ico"))
icon = icon if Path(icon).exists() else None
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Hatua", console=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name="Hatua")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="Hatua.app", icon=icon, bundle_identifier="org.hatua.app",
                 info_plist={"CFBundleShortVersionString": "1.0.0", "NSHighResolutionCapable": True})
