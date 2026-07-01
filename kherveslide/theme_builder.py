"""Theme builder — author a beamer theme with a live master-slide preview.

The left side has the controls (inner/outer/font sub-themes, bullet style,
key colours, frametitle size); the right side renders a sample "master"
slide with the current settings so you can build the theme by eye.
"""
from __future__ import annotations

import copy
import tempfile
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from .compiler import compile_tex, tectonic_available
from .master_editor import MasterSlideEditor
from .model import Slide, ThemeSpec, blend_over_white
from .serializer import _theme_spec_lines
from .theme_gallery import _render_first_page


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
    ("title_fg", "Title text"),
    ("title_bg", "Title bar"),
    ("block_bg", "Block title bar"),
    ("rule_color", "Line colour"),
]


def _preview_tex(spec, base_theme, color_theme, aspect) -> str:
    aspect_opt = _ASPECT_OPT.get(aspect, "aspectratio=169")
    copts = f"[{aspect_opt}]" if aspect_opt else ""
    lines = [f"\\documentclass{copts}{{beamer}}",
             f"\\usetheme{{{base_theme or 'default'}}}"]
    if color_theme:
        lines.append(f"\\usecolortheme{{{color_theme}}}")
    lines += _theme_spec_lines(replace(spec, enabled=True))
    lines += [
        "\\usepackage{lmodern}",
        "\\begin{document}",
        # An empty themed frame: shows the background, title bar and footline
        # so the master is drawn over the real theme furniture, without any
        # sample body text cluttering the canvas.
        "\\begin{frame}{Master slide}",
        "\\vfill",
        "\\end{frame}",
        "\\end{document}",
    ]
    return "\n".join(lines) + "\n"


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
        self.resize(960, 620)
        self.result_spec: ThemeSpec | None = None
        self.result_master: Slide | None = None
        self._base, self._color, self._aspect = base_theme, color_theme, aspect
        # Edit a copy so Cancel discards the master edits; only Apply commits.
        self._master = copy.deepcopy(master) if master is not None else Slide()
        self._colours = {key: getattr(spec, key) for key, _ in _COLOURS}
        self._worker = None
        self._pending = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self._start_preview)

        root = QHBoxLayout(self)
        controls = QWidget()
        v = QVBoxLayout(controls)
        controls.setMaximumWidth(380)
        root.addWidget(controls)

        self._enabled = QCheckBox("Apply this custom theme (uncheck to "
                                  "turn it off)")
        self._enabled.setChecked(True)
        self._enabled.toggled.connect(self._schedule)
        v.addWidget(self._enabled)

        form = QFormLayout()
        self._inner = self._combo(_INNER, spec.inner)
        self._outer = self._combo(_OUTER, spec.outer)
        self._fonts = self._combo(_FONTS, spec.fonts)
        self._bullets = self._combo(_BULLETS, spec.bullets)
        self._size = self._combo(_SIZES, spec.frametitle_size)
        form.addRow("Inner theme", self._inner)
        form.addRow("Outer theme", self._outer)
        form.addRow("Fonts", self._fonts)
        form.addRow("Bullets", self._bullets)
        form.addRow("Title font size", self._size)
        v.addLayout(form)

        v.addWidget(QLabel("<b>Colours</b> (leave as inherit to keep the "
                           "base theme's)"))
        self._colour_btns = {}
        cform = QFormLayout()
        for key, label in _COLOURS:
            btn = QPushButton()
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
            self._colour_btns[key] = btn
            self._refresh_btn(key)
            cform.addRow(label, btn)
        v.addLayout(cform)
        reset = QPushButton("Reset colours to inherit")
        reset.clicked.connect(self._reset_colours)
        v.addWidget(reset)

        v.addWidget(QLabel("<b>Lines</b> (use the Line colour above)"))
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

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Apply theme")
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        # --- right: the master-slide editor, drawn directly over a live
        # render of the theme, so building the master and seeing the theme
        # happen in one place (no separate preview tab). ---
        right = QVBoxLayout()
        right.addWidget(QLabel(
            "<b>Master slide</b> — draw text, pictures, lines and shapes here; "
            "they appear behind every slide. The backdrop is a live preview "
            "of the theme."))
        self._master_editor = MasterSlideEditor(
            self._master, aspect=aspect, gap=gap,
            page_w_cm=page_w_cm, page_h_cm=page_h_cm,
            page_color=self._page_color())
        self._master_editor.setMinimumWidth(540)
        right.addWidget(self._master_editor, 1)
        root.addLayout(right, 1)

        self._schedule()

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
        btn = self._colour_btns[key]
        col = self._colours.get(key, "")
        if col:
            btn.setText(col)
            btn.setStyleSheet(f"background:{col}; color:"
                              f"{'#000' if QColor(col).lightnessF() > 0.5 else '#fff'};")
        else:
            btn.setText("(inherit)")
            btn.setStyleSheet("")

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

    def _current_spec(self) -> ThemeSpec:
        return ThemeSpec(
            enabled=self._enabled.isChecked(),
            inner=self._inner.currentData(),
            outer=self._outer.currentData(),
            fonts=self._fonts.currentData(),
            bullets=self._bullets.currentData(),
            frametitle_size=self._size.currentData(),
            title_rule=self._title_rule.isChecked(),
            footline_rule=self._footline_rule.isChecked(),
            rule_width=self._rule_w.value(),
            **self._colours,
        )

    def _apply(self):
        self.result_spec = self._current_spec()
        self.result_master = self._master
        self.accept()

    # -- live preview --
    def _schedule(self, *_):
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
                           self._aspect)
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
