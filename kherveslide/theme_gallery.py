"""Visual theme picker — see each beamer theme rendered before applying.

Compiling a theme just to look at it is slow, so the gallery renders a
small sample slide for every theme once (in the background, using the
warm tectonic cache) and shows them side by side. Pick one and it's
applied to the deck — no apply-compile-look-repeat loop.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem,
    QVBoxLayout,
)

from .compiler import compile_tex, tectonic_available
from .model import Deck, Slide, SlideText
from .serializer import serialize_deck


def _sample_deck(theme: str, aspect: str) -> Deck:
    """A representative slide so the theme's title bar / colours show."""
    return Deck(
        theme=theme, color_theme="", aspect=aspect, plain_frames=False,
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


class _PreviewWorker(QThread):
    """Compiles each theme's sample deck; emits the resulting PDF path so
    the main thread can render it (Qt PDF rendering wants the GUI thread)."""

    compiled = Signal(str, str)   # theme, pdf_path ("" on failure)

    def __init__(self, themes, aspect, workdir):
        super().__init__()
        self._themes = themes
        self._aspect = aspect
        self._workdir = workdir

    def run(self):
        for theme in self._themes:
            try:
                tex = serialize_deck(_sample_deck(theme, self._aspect))
                r = compile_tex(tex, self._workdir / f"thm_{theme}", "p")
                self.compiled.emit(
                    theme, str(r.pdf_path) if r.ok and r.pdf_path else "")
            except Exception:
                self.compiled.emit(theme, "")


_PREVIEW_W = 300


class ThemeGallery(QDialog):
    """Modal gallery; ``chosen`` holds the picked theme after exec()."""

    def __init__(self, themes, aspect, current, parent=None,
                 cache: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Choose a theme")
        self.resize(720, 560)
        self.chosen = None
        self._aspect = aspect
        self._cache = cache if cache is not None else {}
        self._items: dict[str, QListWidgetItem] = {}

        v = QVBoxLayout(self)
        self._status = QLabel("Rendering theme previews…")
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

        for theme in themes:
            item = QListWidgetItem(theme)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            item.setSizeHint(QSize(_PREVIEW_W + 20, _PREVIEW_W * 9 // 16 + 36))
            if theme in self._cache:
                item.setIcon(QIcon(self._cache[theme]))
            self.list.addItem(item)
            self._items[theme] = item
            if theme == current:
                self.list.setCurrentItem(item)

        pending = [t for t in themes if t not in self._cache]
        if not pending:
            self._status.setText("Double-click a theme to apply it.")
            self._worker = None
        elif not tectonic_available():
            self._status.setText("tectonic unavailable — names only.")
            self._worker = None
        else:
            workdir = Path(tempfile.gettempdir()) / "kherveslide_thumbs"
            self._worker = _PreviewWorker(pending, aspect, workdir)
            self._worker.compiled.connect(self._on_compiled)
            self._worker.finished.connect(
                lambda: self._status.setText("Double-click a theme to apply it."))
            self._worker.start()

    def _on_compiled(self, theme, pdf_path):
        if pdf_path:
            pm = _render_first_page(pdf_path, _PREVIEW_W)
            if pm is not None:
                self._cache[theme] = pm
                self._items[theme].setIcon(QIcon(pm))

    def _apply(self):
        item = self.list.currentItem()
        if item is not None:
            self.chosen = item.text()
        self.accept()

    def closeEvent(self, event):
        if self._worker is not None:
            self._worker.wait(3000)
        super().closeEvent(event)
