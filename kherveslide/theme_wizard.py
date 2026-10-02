"""Theme wizard — make a presentation theme in five easy steps.

The advanced builder (theme_builder.py) exposes beamer's machinery; this
wizard asks only what a person thinks about when copying a university
template: start from a preset or import one (PowerPoint, beamer theme,
picture of a slide), then Colours → Logo → Title & footer → Typeface. A
real compiled preview on the right updates as you go. Everything goes
through theme_kit.ThemeKit, like the importers and the MCP server.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QRadioButton,
    QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

from .compiler import compile_tex, tectonic_available
from .model import Deck, Slide, SlideText
from .serializer import FONT_FAMILIES, serialize_deck
from .theme_kit import (
    BULLET_STYLES, FOOTER_STYLES, LOGO_CORNERS, TITLE_STYLES, ThemeKit,
    contrast_text, presets,
)

STEPS = ("Start", "Colours", "Logo", "Title & footer", "Typeface")
_QUICK = ["#003E74", "#002147", "#500778", "#0E7D7D", "#2E6B30",
          "#9E1B32", "#C55A11", "#1F4E79", "#44546A", "#000000"]


# ---------------------------------------------------------------- preview
def sample_deck(kit: ThemeKit | None, aspect: str, title: str, author: str,
                base_theme: str = "default") -> Deck:
    """A two-slide deck — title page and a content slide with a frame
    title, bullets and a block — dressed in *kit* (or in *base_theme*
    alone when kit is None, e.g. an imported beamer theme)."""
    content = (
        "\\begin{itemize}\n\\item Main finding of the study\n"
        "\\item A second, supporting point\n\\begin{itemize}\n"
        "\\item with a detail underneath\n\\end{itemize}\n"
        "\\end{itemize}")
    deck = Deck(
        title=title or "Presentation title", author=author or "Author",
        aspect=aspect, theme=base_theme or "default", page_number="none",
        slides=[
            Slide(objects=[
                SlideText(x=0.1, y=0.28, w=0.8, h=0.26,
                          text=title or "Presentation title", font_pt=30,
                          bold=True, align="center", locked=False),
                SlideText(x=0.1, y=0.64, w=0.8, h=0.08,
                          text=author or "Author", font_pt=18,
                          align="center", locked=False)]),
            Slide(title="Slide title", objects=[
                SlideText(x=0.06, y=0.27, w=0.88, h=0.4, text=content,
                          font_pt=18, locked=False),
                SlideText(x=0.06, y=0.66, w=0.5, h=0.16,
                          text="Body text inside a block.", font_pt=14,
                          block="block", block_title="Block title",
                          locked=False)]),
        ])
    if kit is not None:
        t = kit.to_theme()
        deck.theme, deck.color_theme = t["base_theme"], t["color_theme"]
        deck.theme_spec = t["spec"]
    return deck


class _PreviewWorker(QThread):
    done = Signal(object)          # pdf bytes or None

    def __init__(self, tex: str):
        super().__init__()
        self._tex = tex

    def run(self):
        data = None
        try:
            wd = Path(tempfile.gettempdir()) / "kherveslide_wizardprev"
            r = compile_tex(self._tex, wd, "w")
            if r.ok and r.pdf_path:
                data = Path(r.pdf_path).read_bytes()
        except Exception:
            data = None
        self.done.emit(data)


def _pdf_pages(data: bytes, width: int) -> list[QPixmap]:
    try:
        import pymupdf
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return []
    out = []
    for page in doc:
        z = width / page.rect.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                     QImage.Format_RGB888).copy()
        out.append(QPixmap.fromImage(img))
    return out


def kit_card(kit: ThemeKit, w: int = 176, h: int = 99) -> QPixmap:
    """A quick painted thumbnail of a kit (no compile): background, title
    bar or title, bullets, footer and a logo spot."""
    pm = QPixmap(w, h)
    pm.fill(QColor(kit.background or "#FFFFFF"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    prim = QColor(kit.primary)
    acc = QColor(kit.accent or kit.primary)
    bar_h = int(h * 0.2)
    if kit.title_style == "bar":
        p.fillRect(0, 0, w, bar_h, prim)
        p.fillRect(8, bar_h // 2 - 2, 60, 5, QColor(kit.title_text))
    else:
        p.fillRect(8, bar_h // 2 - 2, 60, 6, prim)
        if kit.title_style == "underline":
            p.fillRect(8, bar_h - 2, w - 16, 2, acc)
    p.setPen(Qt.NoPen)
    for i in range(3):
        y = bar_h + 12 + i * 13
        p.setBrush(prim)
        p.drawEllipse(12, y, 5, 5)
        p.fillRect(22, y + 1, int(w * (0.55 if i < 2 else 0.35)), 3,
                   QColor(kit.text))
    if kit.footer_style == "bar":
        p.fillRect(0, h - 9, w, 9, prim)
    elif kit.footer_style == "line":
        p.fillRect(0, h - 3, w, 3, acc)
    if kit.logo:
        lx = w - 30 if kit.logo_corner.endswith("r") else 6
        ly = 3 if kit.logo_corner.startswith("t") else h - 22
        p.setBrush(QColor(255, 255, 255, 200))
        p.setPen(QColor(kit.primary))
        p.drawRoundedRect(lx, ly, 24, 12, 2, 2)
    p.setPen(QColor(0, 0, 0, 60))
    p.setBrush(Qt.NoBrush)
    p.drawRect(0, 0, w - 1, h - 1)
    p.end()
    return pm


# ------------------------------------------------------------------ dialog
class ThemeWizard(QDialog):
    """On accept: ``result_kit`` (a ThemeKit) or, for an imported beamer
    theme used as-is, ``result_base_theme`` with result_kit None;
    ``save_to_library`` says whether to keep it in My themes."""

    def __init__(self, kit: ThemeKit | None = None, *, aspect: str = "169",
                 title: str = "", author: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theme wizard")
        self.setMinimumSize(QSize(1060, 640))
        self._kit = ThemeKit(**(kit.to_dict() if kit else {}))
        self._current = kit
        self._aspect = aspect
        self._title = title
        self._author = author
        self._base_theme = ""          # set by a beamer-theme import
        self.result_kit: ThemeKit | None = None
        self.result_base_theme: str | None = None
        self.save_to_library = True
        self._worker: _PreviewWorker | None = None
        self._pending = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self._start_preview)

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self._step_label = QLabel()
        f = self._step_label.font()
        f.setPointSizeF(f.pointSizeF() + 4)
        f.setBold(True)
        self._step_label.setFont(f)
        left.addWidget(self._step_label)
        self._hint = QLabel()
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color:#555;")
        left.addWidget(self._hint)
        self._pages = QStackedWidget()
        for build in (self._page_start, self._page_colours, self._page_logo,
                      self._page_title_footer, self._page_typeface):
            self._pages.addWidget(build())
        left.addWidget(self._pages, 1)

        nav = QHBoxLayout()
        self._back = QPushButton("← Back")
        self._back.clicked.connect(lambda: self._go(self._pages.currentIndex() - 1))
        self._next = QPushButton("Next →")
        self._next.setDefault(True)
        self._next.clicked.connect(self._on_next)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        nav.addWidget(cancel)
        nav.addStretch(1)
        nav.addWidget(self._back)
        nav.addWidget(self._next)
        left.addLayout(nav)
        holder = QWidget()
        holder.setLayout(left)
        holder.setFixedWidth(470)
        root.addWidget(holder)

        right = QVBoxLayout()
        right.addWidget(QLabel("<b>Preview</b> — compiled with LaTeX, "
                               "exactly as your slides will look"))
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumWidth(540)
        self._preview.setStyleSheet("background:#9aa0a6;")
        right.addWidget(self._preview, 1)
        self._status = QLabel()
        self._status.setStyleSheet("color:#555;")
        right.addWidget(self._status)
        root.addLayout(right, 1)

        self._sync_controls()
        self._go(0)
        self._schedule()

    # ------------------------------------------------------- navigation
    _HINTS = (
        "Pick a starting point — a ready-made style or your university's "
        "own template — then adjust it in the next steps.",
        "Choose the main colour (title bar, bullets, footer) and the "
        "others. Most university templates use one strong colour.",
        "Add your logo (PNG, JPG or PDF). It is drawn on every slide, on "
        "top of the title bar.",
        "How the slide title looks, and what runs along the bottom.",
        "The typeface and bullet shape, then a name for your theme.",
    )

    def _go(self, index: int) -> None:
        index = max(0, min(len(STEPS) - 1, index))
        self._pages.setCurrentIndex(index)
        self._step_label.setText(
            f"Step {index + 1} of {len(STEPS)} — {STEPS[index]}")
        self._hint.setText(self._HINTS[index])
        self._back.setEnabled(index > 0)
        last = index == len(STEPS) - 1 or self._base_theme
        self._next.setText("Use this theme ✓" if last else "Next →")

    def _on_next(self) -> None:
        i = self._pages.currentIndex()
        if i == len(STEPS) - 1 or self._base_theme:
            self._finish()
        else:
            self._go(i + 1)

    def _finish(self) -> None:
        if self._base_theme:
            self.result_base_theme = self._base_theme
            self.result_kit = None
        else:
            self._kit.name = self._name.text().strip() or "My theme"
            self.result_kit = ThemeKit(**self._kit.to_dict())
        self.save_to_library = self._save_box.isChecked()
        self.accept()

    # ------------------------------------------------------------ pages
    def _page_start(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("<b>Import your template</b>"))
        for text, tip, slot in (
                ("📊  From a PowerPoint template (.potx / .pptx)…",
                 "Reads the template's colours, fonts and logo",
                 self._import_pptx),
                ("📦  From a beamer theme (.sty or Overleaf .zip)…",
                 "Installs a LaTeX beamer theme and uses it as it is",
                 self._import_beamer),
                ("🖼  From a picture or PDF of a slide…",
                 "Picks the colours off a screenshot or exported slide",
                 self._import_picture)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setMinimumHeight(32)
            b.setStyleSheet("text-align:left; padding-left:10px;")
            b.clicked.connect(slot)
            lay.addWidget(b)
        lay.addSpacing(8)
        lay.addWidget(QLabel("<b>…or start from a style</b>"))
        self._gallery = QListWidget()
        self._gallery.setViewMode(QListWidget.IconMode)
        self._gallery.setIconSize(QSize(176, 99))
        self._gallery.setResizeMode(QListWidget.Adjust)
        self._gallery.setMovement(QListWidget.Static)
        self._gallery.setSpacing(6)
        self._gallery.setWordWrap(True)
        kits = presets()
        if self._current is not None:
            cur = ThemeKit(**self._current.to_dict())
            cur.name = "Current theme"
            kits.insert(0, cur)
        for kit in kits:
            it = QListWidgetItem(QIcon(kit_card(kit)), kit.name)
            it.setData(Qt.UserRole, kit.to_dict())
            self._gallery.addItem(it)
        self._gallery.currentItemChanged.connect(self._on_preset)
        self._gallery.itemDoubleClicked.connect(lambda _it: self._go(1))
        lay.addWidget(self._gallery, 1)
        return w

    def _colour_row(self, key: str, label: str, form: QFormLayout,
                    allow_auto: bool = False):
        btn = QPushButton()
        btn.setFixedSize(120, 28)
        btn.clicked.connect(lambda: self._pick_colour(key))
        row = QHBoxLayout()
        row.addWidget(btn)
        if allow_auto:
            auto = QPushButton("Same as main")
            auto.clicked.connect(lambda: self._set(key, ""))
            row.addWidget(auto)
        row.addStretch(1)
        form.addRow(label, row)
        self._swatches[key] = btn

    def _page_colours(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self._swatches: dict[str, QPushButton] = {}
        form = QFormLayout()
        self._colour_row("primary", "Main colour", form)
        quick = QHBoxLayout()
        quick.setSpacing(3)
        for c in _QUICK:
            b = QPushButton()
            b.setFixedSize(26, 22)
            b.setToolTip(c)
            b.setStyleSheet(f"background:{c}; border:1px solid #888;")
            b.clicked.connect(lambda _=False, col=c: self._set_primary(col))
            quick.addWidget(b)
        quick.addStretch(1)
        form.addRow("", quick)
        self._colour_row("accent", "Accent (lines)", form, allow_auto=True)
        self._colour_row("title_text", "Text on the bars", form)
        self._colour_row("text", "Body text", form)
        self._colour_row("background", "Slide background", form)
        lay.addLayout(form)
        lay.addStretch(1)
        return w

    def _page_logo(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        choose = QPushButton("Choose logo image…")
        choose.clicked.connect(self._choose_logo)
        row.addWidget(choose)
        remove = QPushButton("No logo")
        remove.clicked.connect(lambda: self._set("logo", ""))
        row.addWidget(remove)
        row.addStretch(1)
        lay.addLayout(row)
        self._logo_view = QLabel("No logo")
        self._logo_view.setAlignment(Qt.AlignCenter)
        self._logo_view.setFixedHeight(90)
        self._logo_view.setFrameShape(QFrame.StyledPanel)
        lay.addWidget(self._logo_view)
        lay.addWidget(QLabel("Corner"))
        grid = QGridLayout()
        self._corner_group = QButtonGroup(self)
        for i, key in enumerate(("tl", "tr", "bl", "br")):
            rb = QRadioButton(LOGO_CORNERS[key])
            rb.toggled.connect(
                lambda on, k=key: on and self._set("logo_corner", k))
            self._corner_group.addButton(rb)
            grid.addWidget(rb, i // 2, i % 2)
            setattr(self, f"_corner_{key}", rb)
        lay.addLayout(grid)
        lay.addWidget(QLabel("Size"))
        self._size = QSlider(Qt.Horizontal)
        self._size.setRange(5, 30)
        self._size.valueChanged.connect(
            lambda v: self._set("logo_size", v / 100.0))
        lay.addWidget(self._size)
        lay.addStretch(1)
        return w

    def _radio_group(self, lay, title, options: dict, key: str):
        lay.addWidget(QLabel(f"<b>{title}</b>"))
        group = QButtonGroup(self)
        buttons = {}
        for value, text in options.items():
            rb = QRadioButton(text)
            rb.toggled.connect(lambda on, v=value: on and self._set(key, v))
            group.addButton(rb)
            lay.addWidget(rb)
            buttons[value] = rb
        return buttons

    def _page_title_footer(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self._title_buttons = self._radio_group(
            lay, "Slide title", TITLE_STYLES, "title_style")
        lay.addSpacing(12)
        self._footer_buttons = self._radio_group(
            lay, "Along the bottom", FOOTER_STYLES, "footer_style")
        lay.addStretch(1)
        return w

    def _page_typeface(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self._font = QComboBox()
        self._font.addItem("Latin Modern Sans (LaTeX default)", "")
        for key, (label, _lines) in FONT_FAMILIES.items():
            self._font.addItem(label, key)
        self._font.currentIndexChanged.connect(
            lambda _i: self._set("font", self._font.currentData()))
        form.addRow("Typeface", self._font)
        self._bullets = QComboBox()
        for key, label in BULLET_STYLES.items():
            self._bullets.addItem(label, key)
        self._bullets.currentIndexChanged.connect(
            lambda _i: self._set("bullets", self._bullets.currentData()))
        form.addRow("Bullets", self._bullets)
        self._name = QLineEdit(self._kit.name)
        form.addRow("Theme name", self._name)
        lay.addLayout(form)
        self._save_box = QCheckBox("Also keep it in My themes, to reuse in "
                                   "other presentations")
        self._save_box.setChecked(True)
        lay.addWidget(self._save_box)
        lay.addStretch(1)
        return w

    # ------------------------------------------------------- behaviour
    def _set(self, key: str, value) -> None:
        if getattr(self._kit, key) == value:
            return
        setattr(self._kit, key, value)
        self._base_theme = ""
        self._sync_controls()
        self._go(self._pages.currentIndex())
        self._schedule()

    def _set_primary(self, colour: str) -> None:
        # Keep the bar text readable when the main colour changes.
        self._kit.title_text = contrast_text(colour)
        self._set("primary", colour)

    def _pick_colour(self, key: str) -> None:
        start = getattr(self._kit, key) or self._kit.primary
        c = QColorDialog.getColor(QColor(start), self, "Choose a colour")
        if c.isValid():
            if key == "primary":
                self._set_primary(c.name().upper())
            else:
                self._set(key, c.name().upper())

    def _on_preset(self, item, _prev=None) -> None:
        if item is None or not hasattr(self, "_name"):
            return
        kit = ThemeKit.from_dict(item.data(Qt.UserRole))
        logo = self._kit.logo          # keep a logo already chosen
        self._kit = kit
        if not kit.logo:
            self._kit.logo = logo
        self._base_theme = ""
        self._name.setText(kit.name if kit.name != "Current theme"
                           else self._name.text())
        self._sync_controls()
        self._go(self._pages.currentIndex())
        self._schedule()

    def _choose_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose your logo", "",
            "Images (*.png *.jpg *.jpeg *.pdf)")
        if path:
            self._set("logo", path)

    def _sync_controls(self) -> None:
        """Push the kit's values into every control without re-firing."""
        k = self._kit
        for key, btn in self._swatches.items():
            val = getattr(k, key)
            shown = val or k.primary
            btn.setText(val.upper() if val else "same as main")
            btn.setStyleSheet(
                f"background:{shown}; color:{contrast_text(shown)};"
                " border:1px solid #888;")
        if k.logo and Path(k.logo).exists():
            pm = QPixmap(k.logo)
            if pm.isNull() and k.logo.lower().endswith(".pdf"):
                pages = _pdf_pages(Path(k.logo).read_bytes(), 300)
                pm = pages[0] if pages else QPixmap()
            if not pm.isNull():
                self._logo_view.setPixmap(pm.scaled(
                    300, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self._logo_view.setText(Path(k.logo).name)
        else:
            self._logo_view.setPixmap(QPixmap())
            self._logo_view.setText("No logo")
        for w in (self._size, self._font, self._bullets):
            w.blockSignals(True)
        self._size.setValue(int(round(k.logo_size * 100)))
        self._font.setCurrentIndex(max(0, self._font.findData(k.font)))
        self._bullets.setCurrentIndex(max(0, self._bullets.findData(k.bullets)))
        for w in (self._size, self._font, self._bullets):
            w.blockSignals(False)
        for buttons, value in ((self._title_buttons, k.title_style),
                               (self._footer_buttons, k.footer_style)):
            if value in buttons:
                buttons[value].blockSignals(True)
                buttons[value].setChecked(True)
                buttons[value].blockSignals(False)
        rb = getattr(self, f"_corner_{k.logo_corner}", None)
        if rb is not None:
            rb.blockSignals(True)
            rb.setChecked(True)
            rb.blockSignals(False)

    # -------------------------------------------------------- importers
    def _import_pptx(self) -> None:
        from . import theme_import
        path, _ = QFileDialog.getOpenFileName(
            self, "PowerPoint template", "",
            "PowerPoint (*.potx *.pptx *.potm *.pptm)")
        if not path:
            return
        try:
            kit = theme_import.kit_from_pptx(path, theme_import.assets_dir())
        except Exception as exc:
            QMessageBox.warning(self, "Import failed",
                                f"Could not read that template:\n{exc}")
            return
        self._adopt(kit, f"Imported from {Path(path).name}")

    def _import_picture(self) -> None:
        from . import theme_import
        path, _ = QFileDialog.getOpenFileName(
            self, "Picture of a slide", "",
            "Slides (*.png *.jpg *.jpeg *.pdf)")
        if not path:
            return
        try:
            kit = theme_import.kit_from_picture(path)
        except Exception as exc:
            QMessageBox.warning(self, "Import failed",
                                f"Could not read that picture:\n{exc}")
            return
        self._adopt(kit, f"Colours picked from {Path(path).name} — add "
                         "the logo in step 3")

    def _import_beamer(self) -> None:
        from . import theme_import
        path, _ = QFileDialog.getOpenFileName(
            self, "Beamer theme", "",
            "Beamer theme (*.sty *.zip)")
        if not path:
            return
        try:
            name = theme_import.install_beamer_theme(path)
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        self._base_theme = name
        self._name.setText(name)
        self._status.setText(
            f"Installed the beamer theme “{name}”. It is used as it is — "
            "press “Use this theme”.")
        self._go(self._pages.currentIndex())
        self._schedule()

    def _adopt(self, kit: ThemeKit, message: str) -> None:
        self._kit = kit
        self._base_theme = ""
        self._name.setText(kit.name)
        self._sync_controls()
        self._go(1)
        self._schedule()
        self._status.setText(message)

    # ---------------------------------------------------------- preview
    def _schedule(self) -> None:
        if tectonic_available():
            self._timer.start()
        else:
            self._preview.setPixmap(kit_card(self._kit, 520, 292))
            self._status.setText("LaTeX is not available — showing a "
                                 "sketch instead of the real slides.")

    def _start_preview(self) -> None:
        if self._worker is not None:
            self._pending = True
            return
        kit = None if self._base_theme else self._kit
        deck = sample_deck(kit, self._aspect, self._title, self._author,
                           self._base_theme or "default")
        self._status.setText("Updating the preview…")
        self._worker = _PreviewWorker(serialize_deck(deck))
        self._worker.done.connect(self._on_preview)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_preview(self, data) -> None:
        if not data:
            self._status.setText("The preview could not be compiled "
                                 "(a package may be missing offline).")
            return
        width = max(400, self._preview.width() - 20)
        pages = _pdf_pages(data, width)
        if not pages:
            return
        gap = 12
        h = sum(p.height() for p in pages) + gap * (len(pages) + 1)
        sheet = QPixmap(width + 2 * gap, h)
        sheet.fill(QColor("#9aa0a6"))
        p = QPainter(sheet)
        y = gap
        for page in pages:
            p.drawPixmap(gap, y, page)
            y += page.height() + gap
        p.end()
        self._preview.setPixmap(sheet.scaled(
            self._preview.size(), Qt.KeepAspectRatio,
            Qt.SmoothTransformation))
        if self._status.text().startswith("Updating"):
            self._status.setText("")

    def _on_worker_finished(self) -> None:
        w, self._worker = self._worker, None
        if w is not None:
            w.deleteLater()
        if self._pending:
            self._pending = False
            self._start_preview()

    def closeEvent(self, event):
        self._timer.stop()
        if self._worker is not None:
            self._worker.wait(4000)
        super().closeEvent(event)

    def done(self, r):
        self._timer.stop()
        if self._worker is not None:
            self._worker.wait(4000)
        super().done(r)


def keep_logo(kit: ThemeKit, assets: Path) -> ThemeKit:
    """Copy the kit's logo into the app's theme assets folder so the theme
    keeps working if the original file moves. Returns the updated kit."""
    if not kit.logo:
        return kit
    src = Path(kit.logo)
    try:
        if src.exists() and assets not in src.parents:
            assets.mkdir(parents=True, exist_ok=True)
            dest = assets / src.name
            if dest.exists() and dest.read_bytes() != src.read_bytes():
                dest = assets / f"{src.stem}_{abs(hash(str(src))) % 10000}{src.suffix}"
            shutil.copy2(src, dest)
            kit.logo = str(dest)
    except OSError:
        pass
    return kit
