"""Theme builder — author a beamer theme by choosing inner/outer/font
sub-themes, the bullet style, the key colours and the frametitle size.
Produces a :class:`~kherveslide.model.ThemeSpec` the serializer turns into
the matching beamer preamble, layered on top of the base \\usetheme."""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .model import ThemeSpec


_INNER = ["", "default", "circles", "rectangles", "rounded", "inmargin"]
_OUTER = ["", "default", "infolines", "miniframes", "smoothbars",
          "sidebar", "split", "shadow", "tree"]
_FONTS = ["", "default", "serif", "professionalfonts", "structurebold",
          "structureitalicserif", "structuresmallcapsserif"]
_BULLETS = ["", "default", "circle", "square", "ball", "triangle"]
_SIZES = ["", "small", "normal", "large", "Large", "huge"]

_COLOURS = [
    ("structure", "Structure (accent)"),
    ("text_fg", "Text colour"),
    ("canvas_bg", "Background"),
    ("title_fg", "Title text"),
    ("title_bg", "Title bar"),
    ("block_bg", "Block title bar"),
]


class ThemeBuilderDialog(QDialog):
    def __init__(self, spec: ThemeSpec, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theme builder")
        self.resize(420, 520)
        self.result_spec: ThemeSpec | None = None
        self._colours = {key: getattr(spec, key) for key, _ in _COLOURS}

        v = QVBoxLayout(self)
        self._enabled = QCheckBox("Apply this custom theme (uncheck to "
                                  "turn it off)")
        # Default to on: opening the builder and pressing Apply should
        # actually apply. Reflect the saved state only if it was explicitly
        # disabled with content already set.
        self._enabled.setChecked(True)
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

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Apply theme")
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _combo(self, items, current):
        c = QComboBox()
        for it in items:
            c.addItem(it or "(inherit)", it)
        idx = items.index(current) if current in items else 0
        c.setCurrentIndex(idx)
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

    def _reset_colours(self):
        for key, _ in _COLOURS:
            self._colours[key] = ""
            self._refresh_btn(key)

    def _apply(self):
        self.result_spec = ThemeSpec(
            enabled=self._enabled.isChecked(),
            inner=self._inner.currentData(),
            outer=self._outer.currentData(),
            fonts=self._fonts.currentData(),
            bullets=self._bullets.currentData(),
            frametitle_size=self._size.currentData(),
            **self._colours,
        )
        self.accept()
