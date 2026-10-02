"""Hand a drawing to the KhervePaint app and pick up its saves.

KhervePaint is a separate (PyQt5) application, so it runs as its own
detached process with the drawing's SVG on the command line. kherveDOC
watches that SVG: whenever KhervePaint saves it, the PDF (what LaTeX
includes) and the PNG (what the page shows) are regenerated from it and
the figure is redrawn.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import (QFileSystemWatcher, QObject, QProcess, QSettings,
                            QTimer, Signal)

SETTINGS_KEY = "khervepaint/path"

NOT_FOUND_MESSAGE = (
    "KhervePaint could not be found. Install it, or point kherveDOC at "
    "it with \"Locate KhervePaint…\" (an installed KhervePaint app / "
    "executable, or KhervePaint.py from a source checkout).")


def _source_checkout() -> Path:
    # kherveDOC and KhervePaint are checked out side by side.
    return Path(__file__).resolve().parents[2] / "KhervePaint" / "KhervePaint.py"


def _python_for(script: Path) -> str | None:
    """A Python able to run the KhervePaint source: its own venv first,
    else this interpreter if it happens to have PyQt5."""
    root = script.parent
    for venv in (".venv", "venv"):
        for rel in ("bin/python", "Scripts/python.exe"):
            cand = root / venv / rel
            if cand.exists():
                return str(cand)
    if importlib.util.find_spec("PyQt5") is not None:
        return sys.executable
    return None


def _command_for(path: Path) -> list[str] | None:
    """The argv prefix that runs KhervePaint at *path*, or None."""
    if not path.exists():
        return None
    if path.suffix == ".app":
        exe = path / "Contents" / "MacOS" / "KhervePaint"
        return [str(exe)] if exe.exists() else None
    if path.suffix == ".py":
        py = _python_for(path)
        return [py, str(path)] if py else None
    return [str(path)]


def candidate_paths() -> list[Path]:
    paths: list[Path] = []
    custom = QSettings().value(SETTINGS_KEY, "", type=str)
    if custom:
        paths.append(Path(custom))
    if sys.platform == "darwin":
        paths += [Path("/Applications/KhervePaint.app"),
                  Path.home() / "Applications" / "KhervePaint.app"]
    elif os.name == "nt":
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            if os.environ.get(env):
                paths.append(Path(os.environ[env]) / "KhervePaint"
                             / "KhervePaint.exe")
        if os.environ.get("LOCALAPPDATA"):
            paths.append(Path(os.environ["LOCALAPPDATA"]) / "Programs"
                         / "KhervePaint" / "KhervePaint.exe")
    else:
        import shutil
        found = shutil.which("khervepaint") or shutil.which("KhervePaint")
        if found:
            paths.append(Path(found))
    paths.append(_source_checkout())
    return paths


def find_khervepaint() -> list[str] | None:
    for path in candidate_paths():
        cmd = _command_for(path)
        if cmd:
            return cmd
    return None


def set_custom_path(path: str) -> bool:
    """Remember a user-chosen KhervePaint; False if it cannot be run."""
    if _command_for(Path(path)) is None:
        return False
    QSettings().setValue(SETTINGS_KEY, str(path))
    return True


def _start_detached(cmd: list[str]) -> bool:
    ok, _pid = QProcess.startDetached(cmd[0], cmd[1:])
    return bool(ok)


def regenerate_from_svg(svg: Path) -> Path | None:
    """Rewrite the .pdf and .png beside *svg* from its content. The SVG
    itself is left untouched (it is KhervePaint's file). Returns the PNG,
    or None when the SVG cannot be read or is empty."""
    from .paint import export
    from .paint.authoring import new_scene
    svg = Path(svg)
    scene = new_scene()
    try:
        export.load_svg(scene, svg)
    except Exception:
        return None     # half-written by the other app; the next change retries
    rect = export.content_rect(scene)
    if rect.isEmpty():
        return None
    m = export.MARGIN
    rect = rect.adjusted(-m, -m, m, m)
    png = svg.with_suffix(".png")
    export.save_pdf(scene, svg.with_suffix(".pdf"), rect)
    export.save_png(scene, png, rect)
    return png


class KhervePaintLink(QObject):
    """Launches KhervePaint on drawings and keeps their PDF/PNG in step
    with the SVG it saves. `drawingUpdated(png_path)` fires after each
    regeneration."""

    drawingUpdated = Signal(str)

    #: Saving writes the file in several steps (or replaces it); wait for
    #: it to settle before reading.
    DEBOUNCE_MS = 400

    def __init__(self, parent=None,
                 launcher: Callable[[list[str]], bool] | None = None):
        super().__init__(parent)
        self._launch = launcher or _start_detached
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_changed)
        self._pending: set[str] = set()
        self._mtimes: dict[str, float] = {}
        self._missing: dict[str, int] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DEBOUNCE_MS)
        self._timer.timeout.connect(self._flush)

    def open(self, png_path: str | Path) -> tuple[bool, str]:
        """Open the drawing whose preview is *png_path* in KhervePaint."""
        svg = Path(png_path).with_suffix(".svg")
        if not svg.exists():
            return False, ("This figure has no editable drawing source "
                           "(.svg) to open in KhervePaint.")
        cmd = find_khervepaint()
        if cmd is None:
            return False, NOT_FOUND_MESSAGE
        self.watch(svg)
        if not self._launch(cmd + [str(svg)]):
            return False, f"KhervePaint could not be started ({cmd[0]})."
        return True, f"Opened {svg.name} in KhervePaint."

    def watch(self, svg: str | Path) -> None:
        svg = str(Path(svg).resolve())
        self._mtimes[svg] = _mtime(svg)
        if svg not in self._watcher.files():
            self._watcher.addPath(svg)

    def watched(self) -> list[str]:
        return list(self._mtimes)

    def _on_changed(self, path: str) -> None:
        self._pending.add(path)
        self._timer.start()

    def _flush(self) -> None:
        pending, self._pending = self._pending, set()
        retry = False
        for svg in pending:
            # Editors often save by replacing the file, which drops it from
            # the watcher; re-arm it (once it exists again).
            if not os.path.exists(svg):
                tries = self._missing.get(svg, 0) + 1
                self._missing[svg] = tries
                if tries < 25:          # ~10 s, then it was really deleted
                    self._pending.add(svg)
                    retry = True
                continue
            self._missing.pop(svg, None)
            if svg not in self._watcher.files():
                self._watcher.addPath(svg)
            mt = _mtime(svg)
            if mt == self._mtimes.get(svg):
                continue
            self._mtimes[svg] = mt
            png = regenerate_from_svg(Path(svg))
            if png is not None:
                self.drawingUpdated.emit(str(png))
        if retry:
            self._timer.start()


def _mtime(path: str) -> float:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return -1
