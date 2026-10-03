"""Visual theme picker — see each beamer theme rendered before applying.

Compiling a theme just to look at it is slow, so for the default (no
colour theme) the gallery shows pre-rendered images shipped with the
app. Pick a colour theme from the dropdown and the previews are compiled
live with that colour applied, so what you see is the real combination.
Both the theme and the colour theme are returned on Apply.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QVBoxLayout,
)

from .compiler import compile_tex, tectonic_available
from .model import Deck, Slide, SlideText
from .serializer import serialize_deck


def _sample_deck(theme: str, color: str, aspect: str) -> Deck:
    """A representative slide so the theme's title bar / colours show."""
    return Deck(
        theme=theme, color_theme=color, aspect=aspect, plain_frames=False,
        title="Sample Title", author="Author",
        slides=[Slide(objects=[
            SlideText(x=0.07, y=0.10, w=0.86, h=0.16, text="Sample Title",
                      font_pt=30, bold=True),
            SlideText(x=0.07, y=0.36, w=0.86, h=0.5,
                      text="\\begin{itemize}\n\\item First point\n"
                           "\\item Second point\n\\end{itemize}",
                      font_pt=20),
        ])])


def _render_first_page(pdf_path: str, width: int) -> QPixmap | None:
    """Render page 1 of a PDF to a pixmap on the calling (main) thread."""
    try:
        from PySide6.QtPdf import QPdfDocument
    except ImportError:
        return None
    doc = QPdfDocument()
    if doc.load(pdf_path) != QPdfDocument.Error.None_:
        return None
    if doc.pageCount() < 1:
        return None
    size = doc.pagePointSize(0)
    if size.width() <= 0:
        return None
    h = int(width * size.height() / size.width())
    img: QImage = doc.render(0, QSize(width, h))
    return QPixmap.fromImage(img) if not img.isNull() else None


def _key(theme: str, color: str) -> str:
    return f"{theme}|{color}"


class _PreviewWorker(QThread):
    """Compiles each (theme, colour) sample deck; emits the resulting PDF
    path so the main thread can render it (Qt PDF rendering wants the GUI
    thread)."""

    compiled = Signal(str, str, str)   # theme, colour, pdf_path ("" on fail)

    def __init__(self, themes, color, aspect, workdir):
        super().__init__()
        self._themes = themes
        self._color = color
        self._aspect = aspect
        self._workdir = workdir

    def run(self):
        for theme in self._themes:
            try:
                tex = serialize_deck(_sample_deck(theme, self._color,
                                                  self._aspect))
                tag = f"thm_{theme}_{self._color or 'default'}"
                r = compile_tex(tex, self._workdir / tag, "p")
                self.compiled.emit(
                    theme, self._color,
                    str(r.pdf_path) if r.ok and r.pdf_path else "")
            except Exception:
                self.compiled.emit(theme, self._color, "")


_PREVIEW_W = 300
_PREVIEW_DIR = Path(__file__).resolve().parent / "theme_previews"
_SHIPPED_GENERATED = Path(__file__).resolve().parent / "theme_previews_generated"


def _bundled_preview(theme: str) -> QPixmap | None:
    """Pre-rendered preview shipped with the app (instant, no compile).
    Only available for the default colour theme."""
    path = _PREVIEW_DIR / f"{theme}.png"
    if path.exists():
        pm = QPixmap(str(path))
        if not pm.isNull():
            return pm
    return None


def _disk_cache_dir() -> Path:
    """Persistent store for compiled theme×colour previews, kept in the app's
    own ``theme_previews_generated`` folder so each combination is only ever
    rendered once (then loads instantly) and the previews live with the
    project rather than in a hidden OS cache. A frozen build cannot write
    inside itself (it would break the macOS signature), so it renders new
    ones into the user's cache and reads the shipped ones from the bundle."""
    d = _SHIPPED_GENERATED
    if getattr(sys, "frozen", False):
        from PySide6.QtCore import QStandardPaths
        d = Path(QStandardPaths.writableLocation(
            QStandardPaths.CacheLocation)) / "theme_previews_generated"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _disk_cache_path(theme: str, color: str, aspect: str) -> Path:
    safe = f"{theme}__{color or 'default'}__{aspect}.png".replace("/", "-")
    return _disk_cache_dir() / safe


def _load_disk_preview(theme: str, color: str, aspect: str) -> QPixmap | None:
    p = _disk_cache_path(theme, color, aspect)
    if not p.exists():
        p = _SHIPPED_GENERATED / p.name
    if p.exists():
        pm = QPixmap(str(p))
        if not pm.isNull():
            return pm
    return None


def _save_disk_preview(pm: QPixmap, theme: str, color: str, aspect: str) -> None:
    try:
        pm.save(str(_disk_cache_path(theme, color, aspect)), "PNG")
    except Exception:
        pass


def uncached_combos(themes, colors, aspect) -> list[tuple[str, str]]:
    """Every (theme, colour) pair that doesn't yet have a saved preview on
    disk — the work list for pre-generating the whole gallery once."""
    return [(t, c) for c in colors for t in themes
            if not _disk_cache_path(t, c, aspect).exists()]


class GenerateAllWorker(QThread):
    """Compiles every requested (theme, colour) sample so the main thread can
    render each to a pixmap and save it in the on-disk preview cache. Emits
    per-item progress; rendering stays on the GUI thread (Qt PDF wants it)."""

    compiled = Signal(int, int, str, str, str)   # done, total, theme, colour, pdf

    def __init__(self, combos, aspect, workdir):
        super().__init__()
        self._combos = combos
        self._aspect = aspect
        self._workdir = workdir

    def run(self):
        n = len(self._combos)
        for i, (theme, color) in enumerate(self._combos, 1):
            pdf = ""
            try:
                tex = serialize_deck(_sample_deck(theme, color, self._aspect))
                tag = f"gen_{theme}_{color or 'default'}".replace("/", "-")
                r = compile_tex(tex, self._workdir / tag, "p")
                if r.ok and r.pdf_path:
                    pdf = str(r.pdf_path)
            except Exception:
                pdf = ""
            self.compiled.emit(i, n, theme, color, pdf)


class ThemeGallery(QDialog):
    """Modal gallery. After exec(), ``chosen`` holds the picked theme and
    ``chosen_color`` the picked colour theme."""

    def __init__(self, themes, color_themes, aspect, current,
                 current_color="", parent=None, cache: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Choose a theme")
        self.resize(740, 600)
        self.chosen = None
        self.chosen_color = current_color
        self._themes = list(themes)
        self._aspect = aspect
        self._cache = cache if cache is not None else {}
        self._items: dict[str, QListWidgetItem] = {}
        self._current_color = current_color
        self._workers: list = []   # kept referenced; all waited on close

        v = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Colour theme:"))
        self._color_combo = QComboBox()
        for c in color_themes:
            self._color_combo.addItem(c or "(theme default)", c)
        idx = max(0, self._color_combo.findData(current_color))
        self._color_combo.setCurrentIndex(idx)
        self._color_combo.currentIndexChanged.connect(self._on_color_changed)
        top.addWidget(self._color_combo)
        top.addStretch(1)
        v.addLayout(top)

        self._status = QLabel("")
        v.addWidget(self._status)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(_PREVIEW_W, _PREVIEW_W * 9 // 16))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSpacing(10)
        self.list.itemDoubleClicked.connect(lambda _it: self._apply())
        v.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Apply")
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

        for theme in self._themes:
            item = QListWidgetItem(theme)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            item.setSizeHint(QSize(_PREVIEW_W + 20, _PREVIEW_W * 9 // 16 + 36))
            self.list.addItem(item)
            self._items[theme] = item
            if theme == current:
                self.list.setCurrentItem(item)
        self._refresh_icons()

    # -- preview management --
    def _refresh_icons(self):
        """Show cached previews for the current colour; compile the rest."""
        color = self._current_color
        pending = []
        for theme in self._themes:
            k = _key(theme, color)
            if k not in self._cache:
                # persistent disk cache first, then bundled defaults
                pm = _load_disk_preview(theme, color, self._aspect)
                if pm is None and not color:
                    pm = _bundled_preview(theme)   # instant default previews
                if pm is not None:
                    self._cache[k] = pm
            if k in self._cache:
                self._items[theme].setIcon(QIcon(self._cache[k]))
            else:
                self._items[theme].setIcon(QIcon())
                pending.append(theme)
        if not pending:
            self._status.setText("Double-click a theme to apply it.")
        elif not tectonic_available():
            self._status.setText("tectonic unavailable — names only.")
        else:
            self._status.setText(
                f"Rendering {len(pending)} preview(s) with "
                f"{color or 'the default'} colours…")
            workdir = Path(tempfile.gettempdir()) / "kherveslide_thumbs"
            worker = _PreviewWorker(pending, color, self._aspect, workdir)
            worker.compiled.connect(self._on_compiled)
            worker.finished.connect(self._on_worker_finished)
            self._workers.append(worker)   # hold ref so it isn't GC'd mid-run
            worker.start()

    def _on_color_changed(self):
        self._current_color = self._color_combo.currentData()
        self.chosen_color = self._current_color
        self._refresh_icons()

    def _on_compiled(self, theme, color, pdf_path):
        if pdf_path:
            pm = _render_first_page(pdf_path, _PREVIEW_W)
            if pm is not None:
                self._cache[_key(theme, color)] = pm
                _save_disk_preview(pm, theme, color, self._aspect)  # persist
                # Only update the visible grid if it's still this colour.
                if color == self._current_color and theme in self._items:
                    self._items[theme].setIcon(QIcon(pm))

    def _on_worker_finished(self):
        self._status.setText("Double-click a theme to apply it.")

    def _apply(self):
        item = self.list.currentItem()
        if item is not None:
            self.chosen = item.text()
        self.chosen_color = self._current_color
        self.accept()

    def closeEvent(self, event):
        for worker in self._workers:
            if worker.isRunning():
                worker.wait(5000)
        super().closeEvent(event)
