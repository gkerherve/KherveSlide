#!/usr/bin/env python
"""Run-me launcher for KherveSlide.

Right-click → Run (or double-click) this file to start the app. It lives
at the project root so importing the ``kherveslide`` package works
without any module/run configuration; the real entry point is
``kherveslide/__main__.py``.
"""
import sys
from pathlib import Path

# Make sure the project root is importable even if launched from a
# different working directory (e.g. a desktop shortcut).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from kherveslide.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
