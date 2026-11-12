"""Entry point for the Hatua download (PyInstaller). See hatua/app.py."""
import sys

from hatua.app import main

if __name__ == "__main__":
    sys.exit(main())
