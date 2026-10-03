"""What KherveSlide.spec (Windows) and KherveSlideMAC.spec (macOS) share.

Both specs import this, so the module list, the data files, the bundled
tectonic and the excludes cannot drift apart between the two platforms.

Copyright (C) 2026 Gwilherm Kerherve
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "KherveSlide"
ENTRY = str(ROOT / "KherveSlide.py")
VERSION_FILE = ROOT / "kherveslide" / "VERSION"

#: Other Qt bindings / toolkits and dev-only packages. KherveSlide is
#: PySide6-only; two Qt bindings in one bundle break at start-up.
#: unittest must NOT be excluded — pyparsing (matplotlib) imports it.
EXCLUDES = [
    "PyQt5", "PyQt6", "PySide2", "tkinter", "_tkinter",
    "IPython", "jedi", "notebook", "jupyter_client",
    "pytest", "_pytest", "setuptools", "pip",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
    "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSql",
]


def git_version():
    """(full, short): '0.158.N+sha7' and '0.158.N' — the same number the
    window title shows, from ``__version__`` plus the commit count."""
    sys.path.insert(0, str(ROOT))
    from kherveslide import __version__
    git = lambda *a: subprocess.run(  # noqa: E731
        ["git", *a], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()
    try:
        count, sha = git("rev-list", "--count", "HEAD"), git("rev-parse", "--short=7", "HEAD")
    except (OSError, subprocess.CalledProcessError):
        raise SystemExit("could not read the commit count from git")
    if int(count) < 50:
        raise SystemExit(f"git reports only {count} commits — shallow clone? "
                         "(use fetch-depth: 0)")
    short = f"{__version__}.{count}"
    return f"{short}+{sha}", short


def stamp_version():
    """Write kherveslide/VERSION (a frozen build has no .git) and return
    (full, short)."""
    full, short = git_version()
    VERSION_FILE.write_text(full, encoding="ascii")
    return full, short


def icons():
    """(ico, icns) under build/, rendered from the app's own mark."""
    ico = ROOT / "build" / f"{APP_NAME}.ico"
    icns = ROOT / "build" / f"{APP_NAME}.icns"
    if not (ico.is_file() and icns.is_file()):
        sys.path.insert(0, str(ROOT / "packaging"))
        from make_icons import build_icons
        build_icons(ROOT / "build")
    return str(ico), str(icns)


def find_tectonic() -> str:
    """The tectonic binary to bundle: KHERVESLIDE_TECTONIC if set, else the
    official self-contained release binary (downloaded by fetch_tectonic).
    Without it the app cannot compile a single slide, so a build that
    cannot get it fails rather than shipping a dead app."""
    path = os.environ.get("KHERVESLIDE_TECTONIC")
    if not path:
        sys.path.insert(0, str(ROOT / "packaging"))
        from fetch_tectonic import fetch
        path = str(fetch())
    if not Path(path).is_file():
        raise SystemExit(f"tectonic not found at {path}")
    return str(Path(path).resolve())


def analysis_inputs():
    """(datas, binaries, hiddenimports) for Analysis()."""
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules

    datas = [
        # help.py reads <bundle>/docs/USER_GUIDE.md
        (str(ROOT / "docs" / "USER_GUIDE.md"), "docs"),
        (str(VERSION_FILE), "kherveslide"),
    ]
    # example_media, theme_previews, theme_previews_generated, ...
    datas += collect_data_files("kherveslide")
    datas += collect_data_files("pptx")            # python-pptx's default.pptx
    datas += collect_data_files("spellchecker")    # en.json.gz dictionaries
    # compiler.py looks for it at the bundle root (sys._MEIPASS)
    binaries = [(find_tectonic(), ".")]
    # Dialogs, the paint symbol libraries, the MCP stack and the updater
    # are imported lazily, so static analysis alone would leave them out.
    hiddenimports = collect_submodules("kherveslide") + [
        "PySide6.QtNetwork", "PySide6.QtPrintSupport", "PySide6.QtSvg",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets",
        "matplotlib.backends.backend_agg",
        "matplotlib.backends.backend_qtagg",
        "matplotlib.mathtext",
        "pymupdf", "fitz", "pygit2", "pptx", "spellchecker",
    ]
    return datas, binaries, hiddenimports
