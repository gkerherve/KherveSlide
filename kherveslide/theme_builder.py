"""Theme builder — author a beamer theme with a live master-slide preview.

Organised like PowerPoint's slide-master view: the left side is a set of
compact tabs (Theme / Colours / Text / Lines) plus a "My themes" bar to
save, reload, export (.sty) and import themes; the right side is the
master-slide editor drawn over a live render of the theme, so the theme
and the master are built by eye in one place.
"""
from __future__ import annotations

import copy
import tempfile
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QMenu, QMessageBox, QPushButton, QTabWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from . import custom_themes
from .compiler import compile_tex, tectonic_available
from .master_editor import MasterSlideEditor
from .model import Slide, ThemeSpec, blend_over_white
from .serializer import FONT_FAMILIES, _font_family_lines, _theme_spec_lines, \
    theme_to_sty
from .theme_gallery import _bundled_preview, _render_first_page

_INNER = ["", "default", "circles", "rectangles", "rounded", "inmargin"]
_OUTER = ["", "default", "infolines", "miniframes", "smoothbars",
          "sidebar", "split", "shadow", "tree"]
_FONTS = ["", "default", "serif", "professionalfonts", "structurebold",
          "structureitalicserif", "structuresmallcapsserif"]
_BULLETS = ["", "default", "circle", "square", "ball", "triangle"]
_SIZES = ["", "small", "normal", "large", "Large", "huge"]
_ASPECT_OPT = {"169": "aspectratio=169", "1610": "aspectratio=1610",
               "43": "", "32": "aspectratio=32", "54": "aspectratio=54",
               "141": "aspectratio=141"}

_COLOURS = [
    ("structure", "Structure (accent)"),
    ("text_fg", "Text colour"),
    ("canvas_bg", "Background"),
    ("canvas_bg2", "Background gradient ↓"),
    ("title_fg", "Title text"),
    ("title_bg", "Title bar"),
    ("block_bg", "Block title bar"),
    ("rule_color", "Line colour"),
]

# Fallbacks when the caller doesn't hand in the app's theme lists.
_BASE_THEMES = [
    "default", "AnnArbor", "Antibes", "Bergen", "Berkeley", "Berlin",
    "Boadilla", "CambridgeUS", "Copenhagen", "Darmstadt", "Dresden",
    "Frankfurt", "Goettingen", "Hannover", "Ilmenau", "JuanLesPins",
    "Luebeck", "Madrid", "Malmoe", "Marburg", "Montpellier", "PaloAlto",
    "Pittsburgh", "Rochester", "Singapore", "Szeged", "Warsaw",
    "metropolis", "Auriga", "Trigon", "sintef",
]
_BASE_COLOURS = [
    "", "default", "albatross", "beaver", "beetle", "crane", "dolphin",
    "dove", "fly", "lily", "monarca", "orchid", "rose", "seagull",
    "seahorse", "spruce", "structure", "whale", "wolverine",
]

# One-click coordinated palettes, PowerPoint's Design ▸ Variants ▸ Colours.
# Every slot is listed so applying a scheme fully replaces the palette
# (an omitted slot would silently keep the previous scheme's colour).
def _scheme(structure, text_fg="#212121", canvas_bg="#FFFFFF",
            canvas_bg2="", title_fg="#FFFFFF", title_bg=None,
            block_bg="", rule_color=None):
    return {"structure": structure, "text_fg": text_fg,
            "canvas_bg": canvas_bg, "canvas_bg2": canvas_bg2,
            "title_fg": title_fg,
            "title_bg": structure if title_bg is None else title_bg,
            "block_bg": block_bg,
            "rule_color": structure if rule_color is None else rule_color}


_SCHEMES = [
    ("Office Blue", _scheme("#2E74B5", block_bg="#DEEBF7")),
    ("Imperial Navy", _scheme("#003E74", block_bg="#D4E2F0",
                              rule_color="#009CBC")),
    ("Ion Teal", _scheme("#00767B", block_bg="#D2EBEC")),
    ("Facet Green", _scheme("#548235", block_bg="#E2EFDA")),
    ("Sunrise Orange", _scheme("#C55A11", block_bg="#FBE5D6")),
    ("Berlin Red", _scheme("#A4262C", block_bg="#F5D9DA")),
    ("Wisp Violet", _scheme("#7030A0", block_bg="#E9DFF2")),
    ("Slate", _scheme("#44546A", block_bg="#E1E5EB")),
    ("Ocean Gradient", _scheme("#1F6FB2", canvas_bg="#D9E8F7",
                               canvas_bg2="#FFFFFF", block_bg="#C4DCF2")),
    ("Midnight (dark)", _scheme("#7FB2FF", text_fg="#E6EAF2",
                                canvas_bg="#1B2233", title_bg="#232C44",
                                block_bg="#232C44")),
    ("Charcoal & Gold (dark)", _scheme("#FFC000", text_fg="#F2F2F2",
                                       canvas_bg="#262626",
                                       title_fg="#FFC000",
                                       title_bg="#333333",
                                       block_bg="#3B3B3B")),
    ("Minimal Mono", _scheme("#000000", text_fg="#000000",
                             title_fg="#000000", title_bg="",
                             block_bg="#EEEEEE")),
]


def _preview_tex(spec, base_theme, color_theme, aspect,
                 sample=False) -> str:
    aspect_opt = _ASPECT_OPT.get(aspect, "aspectratio=169")
    copts = f"[{aspect_opt}]" if aspect_opt else ""
    spec_on = replace(spec, enabled=True)
    lines = [f"\\documentclass{copts}{{beamer}}",
             f"\\usetheme{{{base_theme or 'default'}}}"]
    if color_theme:
        lines.append(f"\\usecolortheme{{{color_theme}}}")
    lines += _theme_spec_lines(spec_on)
    lines += ["\\usepackage{lmodern}"]
    lines += _font_family_lines(spec_on)
    if sample:
        # Placeholder body, PowerPoint-master style: shows the bullets,
        # typeface, text colour and block styling being edited.
        body = ["\\begin{frame}{Master slide}",
                "\\begin{itemize}",
                "\\item First-level bullet point",
                "\\item Another bullet to show spacing",
                "\\end{itemize}",
                "\\begin{block}{Block title}",
                "Body text inside a block.",
                "\\end{block}",
                "\\end{frame}"]
    else:
        # An empty themed frame: background, title bar and footline only,
        # so the master is drawn over the theme furniture uncluttered.
        body = ["\\begin{frame}{Master slide}", "\\vfill", "\\end{frame}"]
    lines += ["\\begin{document}", *body, "\\end{document}"]
    return "\n".join(lines) + "\n"


def _swatch_strip(colors: list[str], w=72, h=18) -> QIcon:
    """A small horizontal strip of colour swatches (a scheme's preview)."""
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    n = max(1, len(colors))
    sw = w // n
    for i, c in enumerate(colors):
        col = QColor(c) if c else QColor("#FFFFFF")
        p.fillRect(i * sw, 0, sw, h, col)
    p.setPen(QColor(0, 0, 0, 64))
    p.drawRect(0, 0, sw * n - 1, h - 1)
    p.end()
    return QIcon(pm)


class _PaletteStrip(QWidget):
    """The current palette at a glance — one cell per colour slot;
    inherited slots show as a struck-through white cell."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colors: list[str] = ["" for _ in _COLOURS]
        self.setMinimumHeight(26)
        self.setToolTip("Current palette: " +
                        " · ".join(label for _, label in _COLOURS))

    def set_colors(self, colors: list[str]):
        self._colors = list(colors)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        n = max(1, len(self._colors))
        w = self.width() // n
        h = self.height()
        for i, c in enumerate(self._colors):
            x = i * w
            p.fillRect(x, 0, w - 2, h, QColor(c) if c else QColor("#FFFFFF"))
            p.setPen(QColor("#B0B0B0"))
            p.drawRect(x, 0, w - 2, h - 1)
            if not c:
                p.drawLine(x, h - 1, x + w - 2, 0)
        p.end()


class _PreviewWorker(QThread):
    done = Signal(str)   # pdf path ("" on failure)

    def __init__(self, tex):
        super().__init__()
        self._tex = tex

    def run(self):
        wd = Path(tempfile.gettempdir()) / "kherveslide_themeprev"
        r = compile_tex(self._tex, wd, "p")
        self.done.emit(str(r.pdf_path) if r.ok and r.pdf_path else "")


class ThemeBuilderDialog(QDialog):
    def __init__(self, spec: ThemeSpec, master: Slide | None = None,
                 base_theme="default", color_theme="",
                 aspect="169", gap=0.0, page_w_cm=0.0, page_h_cm=0.0,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theme builder")
        self.resize(1150, 700)
        self.result_spec: ThemeSpec | None = None
        self.result_master: Slide | None = None
        self.result_base_theme: str | None = None
        self.result_color_theme: str | None = None
        self._base, self._color, self._aspect = base_theme, color_theme, aspect
        # Edit a copy so Cancel discards the master edits; only Apply commits.
        self._master = copy.deepcopy(master) if master is not None else Slide()
        self._colours = {key: getattr(spec, key) for key, _ in _COLOURS}
        self._worker = None
        self._pending = False
        self._loading_theme = False   # guards the signal storm on bulk loads
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self._start_preview)

        root = QHBoxLayout(self)
        controls = QWidget()
        v = QVBoxLayout(controls)
        v.setContentsMargins(0, 0, 0, 0)
        controls.setFixedWidth(400)
        root.addWidget(controls)

        v.addLayout(self._build_my_themes_row())

        self._enabled = QCheckBox("Apply the custom overrides below "
                                  "(colours, fonts, lines)")
        has_overrides = any([
            spec.inner, spec.outer, spec.fonts, spec.bullets,
            getattr(spec, "font_family", ""),
            spec.frametitle_size, spec.title_rule, spec.footline_rule,
            *(getattr(spec, k, "") for k, _ in _COLOURS)])
        self._enabled.setChecked(spec.enabled or not has_overrides)
        self._enabled.toggled.connect(self._schedule)
        v.addWidget(self._enabled)

        tabs = QTabWidget()
        tabs.addTab(self._build_theme_tab(base_theme, color_theme, spec),
                    "Theme")
        tabs.addTab(self._build_colours_tab(), "Colours")
        tabs.addTab(self._build_text_tab(spec), "Text")
        tabs.addTab(self._build_lines_tab(spec), "Lines")
        v.addWidget(tabs, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Apply theme")
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        # --- right: the master-slide editor, drawn directly over a live
        # render of the theme, so building the master and seeing the theme
        # happen in one place (no separate preview tab). ---
        right = QVBoxLayout()
        head = QHBoxLayout()
        head.addWidget(QLabel(
            "<b>Master slide</b> — draw text, pictures, lines and shapes "
            "here; they appear behind every slide."))
        head.addStretch(1)
        self._sample = QCheckBox("Sample content")
        self._sample.setToolTip(
            "Render placeholder bullets and a block in the backdrop, so the "
            "bullet style, typeface and block colours show while you build")
        self._sample.toggled.connect(self._schedule)
        head.addWidget(self._sample)
        right.addLayout(head)
        self._master_editor = MasterSlideEditor(
            self._master, aspect=aspect, gap=gap,
            page_w_cm=page_w_cm, page_h_cm=page_h_cm,
            page_color=self._page_color())
        self._master_editor.setMinimumWidth(540)
        right.addWidget(self._master_editor, 1)
        root.addLayout(right, 1)

        self._schedule()

    # ---------------- "My themes" bar ----------------
    def _build_my_themes_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("<b>My themes</b>"))
        self._saved_combo = QComboBox()
        self._saved_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._saved_combo.activated.connect(self._load_saved_theme)
        row.addWidget(self._saved_combo, 1)
        save = QPushButton("Save…")
        save.setToolTip("Save the current theme + master under a name, to "
                        "reuse in any presentation")
        save.clicked.connect(self._save_theme)
        row.addWidget(save)
        more = QToolButton()
        more.setText("More ▾")
        more.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(more)
        menu.addAction("Delete selected theme", self._delete_saved_theme)
        menu.addSeparator()
        menu.addAction("Export as beamer theme (.sty)…", self._export_sty)
        menu.addAction("Import beamer theme (.sty)…", self._import_sty)
        menu.addSeparator()
        menu.addAction("Browse the Overleaf gallery…", lambda:
                       QDesktopServices.openUrl(QUrl(
                           "https://www.overleaf.com/gallery/tagged/presentation")))
        more.setMenu(menu)
        row.addWidget(more)
        self._refresh_saved_combo()
        return row

    def _refresh_saved_combo(self, select: str = ""):
        self._saved_combo.clear()
        self._saved_combo.addItem("(saved themes)", "")
        for name in sorted(custom_themes.load_themes()):
            self._saved_combo.addItem(name, name)
        if select:
            i = self._saved_combo.findData(select)
            self._saved_combo.setCurrentIndex(max(0, i))

    def _save_theme(self):
        current = self._saved_combo.currentData() or "My theme"
        name, ok = QInputDialog.getText(
            self, "Save theme", "Theme name:", text=current)
        if not ok or not name.strip():
            return
        name = name.strip()
        custom_themes.save_theme(
            name, self._current_spec(), self._master,
            base_theme=self._base_combo.currentData() or "default",
            color_theme=self._colortheme_combo.currentData() or "")
        self._refresh_saved_combo(select=name)

    def _load_saved_theme(self, _index=None):
        name = self._saved_combo.currentData()
        if not name:
            return
        data = custom_themes.load_themes().get(name)
        if data is None:
            return
        self._loading_theme = True
        try:
            self._apply_spec_to_controls(data["spec"])
            i = self._base_combo.findData(data["base_theme"] or "default")
            if i >= 0:
                self._base_combo.setCurrentIndex(i)
            i = self._colortheme_combo.findData(data["color_theme"] or "")
            if i >= 0:
                self._colortheme_combo.setCurrentIndex(i)
            self._base = self._base_combo.currentData() or "default"
            self._color = self._colortheme_combo.currentData() or ""
            self._master.objects[:] = copy.deepcopy(data["master"].objects)
            self._master_editor.refresh()
            self._enabled.setChecked(True)
        finally:
            self._loading_theme = False
        self._schedule()

    def _delete_saved_theme(self):
        name = self._saved_combo.currentData()
        if not name:
            return
        if QMessageBox.question(
                self, "Delete theme",
                f"Delete the saved theme “{name}”?") != QMessageBox.Yes:
            return
        custom_themes.delete_theme(name)
        self._refresh_saved_combo()

    def _export_sty(self):
        name = (self._saved_combo.currentData() or "Custom")
        safe = "".join(c for c in name if c.isalnum()) or "Custom"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export beamer theme", f"beamertheme{safe}.sty",
            "beamer theme (*.sty)")
        if not path:
            return
        stem = Path(path).stem
        theme_name = (stem[len("beamertheme"):]
                      if stem.lower().startswith("beamertheme") else stem)
        sty = theme_to_sty(self._current_spec(), theme_name,
                           base_theme=self._base_combo.currentData() or "",
                           color_theme=self._colortheme_combo.currentData() or "")
        Path(path).write_text(sty, encoding="utf-8")
        QMessageBox.information(
            self, "Theme exported",
            f"Saved {Path(path).name}.\n\nDrop it next to any .tex file and "
            f"load it with \\usetheme{{{theme_name}}} — in KherveSlide, "
            "Overleaf or any LaTeX editor. (The master-slide drawings stay "
            "in KherveSlide; only the theme styling is exported.)")

    def _import_sty(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import beamer theme(s)", "",
            "beamer theme / style files (*.sty)")
        if not paths:
            return
        names = []
        for p in paths:
            n = custom_themes.import_sty(Path(p))
            if n:
                names.append(n)
        self._reload_base_themes()
        if names:
            i = self._base_combo.findData(names[0])
            if i >= 0:
                self._base_combo.setCurrentIndex(i)
            QMessageBox.information(
                self, "Theme imported",
                "Imported: " + ", ".join(names) + ".\n\nThe theme is now in "
                "the Base theme list (and works in every presentation). "
                "Files that aren't beamertheme*.sty were copied as support "
                "files.")
        else:
            QMessageBox.information(
                self, "Files imported",
                "No beamertheme*.sty among the chosen files — they were "
                "copied as support style files.")

    # ---------------- Theme tab ----------------
    def _build_theme_tab(self, base_theme, color_theme, spec) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        head = QLabel("<b>Base theme</b> — the beamer look everything "
                      "else layers on (“default” = plain)")
        head.setWordWrap(True)
        v.addWidget(head)
        form = QFormLayout()
        self._base_combo = QComboBox()
        self._base_combo.setIconSize(QSize(96, 54))
        self._reload_base_themes()
        i = self._base_combo.findData(base_theme or "default")
        self._base_combo.setCurrentIndex(max(0, i))
        self._base_combo.currentIndexChanged.connect(self._on_base_changed)
        form.addRow("Beamer theme", self._base_combo)
        self._colortheme_combo = QComboBox()
        for name in _BASE_COLOURS:
            self._colortheme_combo.addItem(name or "(theme default)", name)
        i = self._colortheme_combo.findData(color_theme)
        self._colortheme_combo.setCurrentIndex(max(0, i))
        self._colortheme_combo.currentIndexChanged.connect(self._on_base_changed)
        form.addRow("Colour theme", self._colortheme_combo)
        v.addLayout(form)

        lay = QLabel("<b>Layout</b> — beamer's building blocks "
                     "(applied with the overrides tick)")
        lay.setWordWrap(True)
        v.addWidget(lay)
        lform = QFormLayout()
        self._inner = self._combo(_INNER, spec.inner)
        self._inner.setToolTip("Inner theme: how titles, blocks and lists "
                               "are drawn inside the slide")
        self._outer = self._combo(_OUTER, spec.outer)
        self._outer.setToolTip("Outer theme: the frame furniture — head/foot "
                               "bars, sidebars, mini frame dots")
        lform.addRow("Inner theme", self._inner)
        lform.addRow("Outer theme", self._outer)
        v.addLayout(lform)
        v.addStretch(1)
        return w

    def _reload_base_themes(self):
        """(Re)populate the base-theme combo: built-ins with their preview
        thumbnails, then any user-imported beamertheme*.sty files."""
        current = self._base_combo.currentData() if \
            self._base_combo.count() else None
        self._base_combo.blockSignals(True)
        self._base_combo.clear()
        for name in _BASE_THEMES:
            pm = _bundled_preview(name)
            if pm is not None:
                self._base_combo.addItem(QIcon(pm), name, name)
            else:
                self._base_combo.addItem(name, name)
        for name in custom_themes.installed_sty_themes():
            if self._base_combo.findData(name) < 0:
                self._base_combo.addItem(f"{name}  (imported)", name)
        if current:
            i = self._base_combo.findData(current)
            if i >= 0:
                self._base_combo.setCurrentIndex(i)
        self._base_combo.blockSignals(False)

    # ---------------- Colours tab ----------------
    def _build_colours_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self._palette_strip = _PaletteStrip()
        v.addWidget(self._palette_strip)

        v.addWidget(QLabel("<b>Colour schemes</b> — one click fills the "
                           "whole palette"))
        grid = QGridLayout()
        grid.setSpacing(4)
        for idx, (name, scheme) in enumerate(_SCHEMES):
            btn = QPushButton(name)
            btn.setIcon(_swatch_strip([scheme["structure"],
                                       scheme["title_bg"] or scheme["canvas_bg"],
                                       scheme["block_bg"] or scheme["canvas_bg"],
                                       scheme["canvas_bg"],
                                       scheme["text_fg"]]))
            btn.setStyleSheet("text-align: left; padding: 2px 6px;")
            btn.clicked.connect(lambda _=False, s=scheme: self._apply_scheme(s))
            grid.addWidget(btn, idx // 2, idx % 2)
        v.addLayout(grid)

        v.addWidget(QLabel("<b>Custom colours</b> (inherit = keep the base "
                           "theme's)"))
        self._colour_btns = {}
        cform = QFormLayout()
        cform.setVerticalSpacing(3)
        for key, label in _COLOURS:
            btn = QPushButton()
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
            clear = QToolButton()
            clear.setText("×")
            clear.setToolTip("Back to inherit")
            clear.clicked.connect(lambda _=False, k=key: self._clear_colour(k))
            self._colour_btns[key] = btn
            self._refresh_btn(key)
            row = QHBoxLayout()
            row.setSpacing(2)
            row.addWidget(btn, 1)
            row.addWidget(clear)
            cform.addRow(label, row)
        v.addLayout(cform)

        tools = QHBoxLayout()
        accent = QPushButton("Build from one accent…")
        accent.setToolTip("Pick a single accent colour; the title bar, "
                          "blocks and lines are derived from it")
        accent.clicked.connect(self._build_from_accent)
        tools.addWidget(accent)
        reset = QPushButton("Reset to inherit")
        reset.clicked.connect(self._reset_colours)
        tools.addWidget(reset)
        v.addLayout(tools)

        bgrow = QHBoxLayout()
        bgrow.addWidget(QLabel("Background:"))
        for label, style in (("White", "white"), ("Tint", "tint"),
                             ("Gradient", "gradient"), ("Dark", "dark")):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, s=style: self._bg_style(s))
            bgrow.addWidget(b)
        bgrow.addStretch(1)
        v.addLayout(bgrow)
        v.addStretch(1)
        self._sync_palette_strip()
        return w

    def _sync_palette_strip(self):
        if hasattr(self, "_palette_strip"):
            self._palette_strip.set_colors(
                [self._colours.get(k, "") for k, _ in _COLOURS])

    def _apply_scheme(self, scheme: dict):
        for key, _ in _COLOURS:
            self._colours[key] = scheme.get(key, "")
            self._refresh_btn(key)
        self._enabled.setChecked(True)
        self._schedule()

    def _build_from_accent(self):
        cur = QColor(self._colours.get("structure") or "#3366CC")
        col = QColorDialog.getColor(cur, self, "Accent colour")
        if not col.isValid():
            return
        accent = col.name()
        on_accent = "#000000" if col.lightnessF() > 0.6 else "#FFFFFF"
        self._colours.update(
            structure=accent, title_bg=accent, title_fg=on_accent,
            text_fg="#1A1A1A", canvas_bg="#FFFFFF", canvas_bg2="",
            block_bg=blend_over_white(accent, 0.15), rule_color=accent)
        for key, _ in _COLOURS:
            self._refresh_btn(key)
        self._enabled.setChecked(True)
        self._schedule()

    def _bg_style(self, style: str):
        accent = self._colours.get("structure") or "#3366CC"
        if style == "white":
            self._colours.update(canvas_bg="#FFFFFF", canvas_bg2="")
        elif style == "tint":
            self._colours.update(canvas_bg=blend_over_white(accent, 0.08),
                                 canvas_bg2="")
        elif style == "gradient":
            self._colours.update(canvas_bg=blend_over_white(accent, 0.20),
                                 canvas_bg2="#FFFFFF")
        elif style == "dark":
            self._colours.update(canvas_bg="#20242C", canvas_bg2="")
            # Inherited (or dark) text would vanish on the dark page.
            for key, light in (("text_fg", "#ECEFF4"), ("title_fg", "#FFFFFF")):
                cur = self._colours.get(key, "")
                if not cur or QColor(cur).lightnessF() < 0.5:
                    self._colours[key] = light
        for key, _ in _COLOURS:
            self._refresh_btn(key)
        self._enabled.setChecked(True)
        self._schedule()

    def _clear_colour(self, key):
        self._colours[key] = ""
        self._refresh_btn(key)
        self._schedule()

    # ---------------- Text tab ----------------
    def _build_text_tab(self, spec) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("<b>Theme fonts</b> — the presentation-wide "
                           "typeface (PowerPoint's theme fonts)"))
        form = QFormLayout()
        self._font_family = QComboBox()
        self._font_family.addItem("(theme default)", "")
        for key, (label, _lines) in FONT_FAMILIES.items():
            self._font_family.addItem(label, key)
        i = self._font_family.findData(getattr(spec, "font_family", ""))
        self._font_family.setCurrentIndex(max(0, i))
        self._font_family.setToolTip(
            "Fetched by tectonic on first use — needs the network once")
        self._font_family.currentIndexChanged.connect(self._schedule)
        form.addRow("Typeface", self._font_family)
        self._fonts = self._combo(_FONTS, spec.fonts)
        self._fonts.setToolTip("beamer's font theme: serif body, bold "
                               "structure, small caps…")
        form.addRow("Font theme", self._fonts)
        self._size = self._combo(_SIZES, spec.frametitle_size)
        form.addRow("Title font size", self._size)
        v.addLayout(form)

        v.addWidget(QLabel("<b>Lists</b>"))
        bform = QFormLayout()
        self._bullets = self._combo(_BULLETS, spec.bullets)
        bform.addRow("Bullet style", self._bullets)
        v.addLayout(bform)
        tip = QLabel("Tip: tick “Sample content” above the canvas to see "
                     "the typeface and bullets while you choose.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #666;")
        v.addWidget(tip)
        v.addStretch(1)
        return w

    # ---------------- Lines tab ----------------
    def _build_lines_tab(self, spec) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("<b>Decorative lines</b> (coloured with the Line "
                           "colour on the Colours tab)"))
        self._title_rule = QCheckBox("Rule under the frame title")
        self._title_rule.setChecked(getattr(spec, "title_rule", False))
        self._title_rule.toggled.connect(self._schedule)
        v.addWidget(self._title_rule)
        self._footline_rule = QCheckBox("Footer line along the bottom")
        self._footline_rule.setChecked(getattr(spec, "footline_rule", False))
        self._footline_rule.toggled.connect(self._schedule)
        v.addWidget(self._footline_rule)
        wform = QFormLayout()
        self._rule_w = QDoubleSpinBox()
        self._rule_w.setRange(0.2, 10.0)
        self._rule_w.setSingleStep(0.5)
        self._rule_w.setValue(getattr(spec, "rule_width", 1.5) or 1.5)
        self._rule_w.valueChanged.connect(self._schedule)
        wform.addRow("Line thickness (pt)", self._rule_w)
        v.addLayout(wform)
        v.addStretch(1)
        return w

    def _page_color(self) -> str:
        """The master canvas page colour — follow the theme background so the
        master is built against the real slide colour (white if inherited)."""
        bg = self._colours.get("canvas_bg", "")
        return blend_over_white(bg, 1.0) if bg else "#FFFFFF"

    # -- controls --
    def _combo(self, items, current):
        c = QComboBox()
        for it in items:
            c.addItem(it or "(inherit)", it)
        c.setCurrentIndex(items.index(current) if current in items else 0)
        c.currentIndexChanged.connect(self._schedule)
        return c

    def _refresh_btn(self, key):
        btn = self._colour_btns.get(key) if hasattr(self, "_colour_btns") \
            else None
        if btn is None:
            return
        col = self._colours.get(key, "")
        if col:
            btn.setText(col)
            btn.setStyleSheet(f"background:{col}; color:"
                              f"{'#000' if QColor(col).lightnessF() > 0.5 else '#fff'};")
        else:
            btn.setText("(inherit)")
            btn.setStyleSheet("")
        self._sync_palette_strip()

    def _pick(self, key):
        cur = QColor(self._colours.get(key) or "#3366CC")
        col = QColorDialog.getColor(cur, self, "Choose colour")
        if col.isValid():
            self._colours[key] = col.name()
            self._refresh_btn(key)
            self._schedule()

    def _reset_colours(self):
        for key, _ in _COLOURS:
            self._colours[key] = ""
            self._refresh_btn(key)
        self._schedule()

    def _apply_spec_to_controls(self, spec: ThemeSpec):
        """Push a loaded ThemeSpec into every control (bulk, no re-preview
        per change — the caller schedules one refresh at the end)."""
        for key, _ in _COLOURS:
            self._colours[key] = getattr(spec, key, "")
            self._refresh_btn(key)
        for combo, value in ((self._inner, spec.inner),
                             (self._outer, spec.outer),
                             (self._fonts, spec.fonts),
                             (self._bullets, spec.bullets),
                             (self._size, spec.frametitle_size)):
            i = combo.findData(value)
            combo.setCurrentIndex(max(0, i))
        i = self._font_family.findData(getattr(spec, "font_family", ""))
        self._font_family.setCurrentIndex(max(0, i))
        self._title_rule.setChecked(spec.title_rule)
        self._footline_rule.setChecked(spec.footline_rule)
        self._rule_w.setValue(spec.rule_width or 1.5)

    def _current_spec(self) -> ThemeSpec:
        return ThemeSpec(
            enabled=self._enabled.isChecked(),
            inner=self._inner.currentData(),
            outer=self._outer.currentData(),
            fonts=self._fonts.currentData(),
            font_family=self._font_family.currentData(),
            bullets=self._bullets.currentData(),
            frametitle_size=self._size.currentData(),
            title_rule=self._title_rule.isChecked(),
            footline_rule=self._footline_rule.isChecked(),
            rule_width=self._rule_w.value(),
            **self._colours,
        )

    def _on_base_changed(self, *_):
        """The base theme / colour theme combo changed — re-render the
        backdrop with the new underlying theme."""
        self._base = self._base_combo.currentData() or "default"
        self._color = self._colortheme_combo.currentData() or ""
        self._schedule()

    def _apply(self):
        self.result_spec = self._current_spec()
        self.result_master = self._master
        self.result_base_theme = self._base_combo.currentData() or "default"
        self.result_color_theme = self._colortheme_combo.currentData() or ""
        self.accept()

    # -- live preview --
    def _schedule(self, *_):
        if self._loading_theme:
            return
        # Keep the master canvas page colour in step with the theme bg.
        if hasattr(self, "_master_editor"):
            self._master_editor.set_page_color(self._page_color())
        if tectonic_available():
            self._timer.start()

    def _start_preview(self):
        if self._worker is not None:
            self._pending = True
            return
        tex = _preview_tex(self._current_spec(), self._base, self._color,
                           self._aspect, sample=self._sample.isChecked())
        self._worker = _PreviewWorker(tex)
        self._worker.done.connect(self._on_preview)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    def _on_preview(self, pdf):
        # Render the themed frame and lay it under the master objects. A
        # failed compile clears the backdrop → the flat theme background shows.
        pm = _render_first_page(pdf, 1000) if pdf else None
        self._master_editor.set_backdrop(pm)

    def _on_worker_done(self):
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if self._pending:
            self._pending = False
            self._start_preview()

    def closeEvent(self, event):
        self._timer.stop()
        if self._worker is not None:
            self._worker.wait(4000)
        super().closeEvent(event)
