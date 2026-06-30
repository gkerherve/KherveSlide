"""Predefined table designs (PowerPoint-style gallery) plus a grid picker
for choosing table dimensions. A style is a plain dict of the SlideTable
appearance fields; applying one just copies those fields across.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QLabel, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)


def _style(name, header_bg, header_fg, grid, striped, stripe, rule,
           color="#000000", header=True):
    return dict(name=name, header_bg=header_bg, header_fg=header_fg,
                grid=grid, striped=striped, stripe_color=stripe,
                rule_color=rule, color=color, header=header)


# Accent palette: (name, strong header colour, light banded tint).
_ACCENTS = [
    ("Blue", "#2E75B6", "#DEEBF7"),
    ("Orange", "#ED7D31", "#FCE4D6"),
    ("Green", "#548235", "#E2EFDA"),
    ("Red", "#C00000", "#F8D7D2"),
    ("Purple", "#7030A0", "#E6DBF2"),
    ("Teal", "#2A9D8F", "#D7F0EC"),
    ("Grey", "#595959", "#EDEDED"),
]

TABLE_STYLES: list[dict] = [
    _style("Plain", "#FFFFFF", "#000000", "all", False, "#F5F5F5", "#BFBFBF"),
    _style("Grid only", "#FFFFFF", "#000000", "all", False, "#F5F5F5",
           "#808080"),
    _style("No grid", "#FFFFFF", "#000000", "none", False, "#F5F5F5",
           "#BFBFBF", header=False),
    _style("Lines", "#FFFFFF", "#000000", "horizontal", False, "#F5F5F5",
           "#808080"),
]
for _nm, _hd, _lt in _ACCENTS:
    TABLE_STYLES.append(
        _style(f"{_nm} header", _hd, "#FFFFFF", "horizontal", False,
               _lt, _hd))
    TABLE_STYLES.append(
        _style(f"{_nm} banded", _hd, "#FFFFFF", "horizontal", True,
               _lt, _hd))
    TABLE_STYLES.append(
        _style(f"{_nm} grid", _hd, "#FFFFFF", "all", False, _lt, _hd))


def apply_table_style(obj, st: dict) -> None:
    obj.header = st.get("header", True)
    obj.header_bg = st["header_bg"]
    obj.header_fg = st["header_fg"]
    obj.grid = st["grid"]
    obj.border = st["grid"] != "none"
    obj.striped = st["striped"]
    obj.stripe_color = st["stripe_color"]
    obj.rule_color = st["rule_color"]
    obj.color = st.get("color", "#000000")


def swatch(st: dict, w: int = 116, h: int = 70) -> QPixmap:
    """A small preview thumbnail of a table style."""
    pm = QPixmap(w, h)
    pm.fill(QColor("#FFFFFF"))
    p = QPainter(pm)
    rows = 4
    rh = h / rows
    if st.get("header", True):
        p.fillRect(QRectF(0, 0, w, rh), QColor(st["header_bg"]))
    for r in range(1, rows):
        if st["striped"] and (r - 1) % 2 == 1:
            p.fillRect(QRectF(0, r * rh, w, rh), QColor(st["stripe_color"]))
    if st["grid"] != "none":
        p.setPen(QPen(QColor(st["rule_color"]), 1))
        if st["grid"] in ("all", "horizontal"):
            for r in range(rows + 1):
                y = min(h - 1, int(r * rh))
                p.drawLine(0, y, w, y)
        if st["grid"] == "all":
            for c in range(1, 3):
                x = int(c * w / 3)
                p.drawLine(x, 0, x, h)
        if st["grid"] == "outer":
            p.drawLine(0, 0, w, 0)
            p.drawLine(0, h - 1, w, h - 1)
    # Text hint: short bars per cell.
    for r in range(rows):
        fg = st["header_fg"] if (r == 0 and st.get("header", True)) else "#7a7a7a"
        p.setPen(QPen(QColor(fg), 2))
        for c in range(3):
            x = int(c * w / 3) + 6
            y = int(r * rh + rh / 2)
            p.drawLine(x, y, x + int(w / 3) - 14, y)
    p.setPen(QPen(QColor("#cccccc"), 1))
    p.drawRect(0, 0, w - 1, h - 1)
    p.end()
    return pm


class TableGridPicker(QWidget):
    """A hover-to-choose rows x columns grid, like PowerPoint's Insert Table."""

    picked = Signal(int, int)        # (rows, cols)

    def __init__(self, max_r=8, max_c=8, parent=None):
        super().__init__(parent)
        self._mr, self._mc = max_r, max_c
        self._cell, self._gap, self._pad, self._labelh = 18, 3, 8, 22
        self._hr = self._hc = 0
        self.setMouseTracking(True)
        self.setFixedSize(
            self._pad * 2 + max_c * (self._cell + self._gap),
            self._pad * 2 + max_r * (self._cell + self._gap) + self._labelh)

    def _cell_at(self, pos):
        step = self._cell + self._gap
        c = int((pos.x() - self._pad) // step) + 1
        r = int((pos.y() - self._pad) // step) + 1
        return max(0, min(self._mr, r)), max(0, min(self._mc, c))

    def mouseMoveEvent(self, e):
        self._hr, self._hc = self._cell_at(e.position().toPoint())
        self.update()

    def mousePressEvent(self, e):
        r, c = self._cell_at(e.position().toPoint())
        if r >= 1 and c >= 1:
            self.picked.emit(r, c)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#ffffff"))
        step = self._cell + self._gap
        for r in range(self._mr):
            for c in range(self._mc):
                x = self._pad + c * step
                y = self._pad + r * step
                on = r < self._hr and c < self._hc
                p.setBrush(QColor("#cfe2ff") if on else QColor("#f3f3f3"))
                p.setPen(QPen(QColor("#3b82f6") if on else QColor("#cccccc")))
                p.drawRect(x, y, self._cell, self._cell)
        p.setPen(QColor("#333333"))
        label = (f"{self._hr} × {self._hc} table"
                 if self._hr and self._hc else "Insert table")
        p.drawText(QRect(0, self.height() - self._labelh, self.width(),
                         self._labelh), Qt.AlignCenter, label)
        p.end()


class TableStyleGallery(QDialog):
    """A scrollable gallery of table designs; sets ``chosen`` on accept."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Table design")
        self.chosen: dict | None = None
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        grid = QGridLayout(host)
        cols = 5
        for i, st in enumerate(TABLE_STYLES):
            btn = QToolButton()
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setIcon(swatch(st))
            from PySide6.QtCore import QSize
            btn.setIconSize(QSize(116, 70))
            btn.setText(st["name"])
            btn.setAutoRaise(True)
            btn.clicked.connect(lambda _=False, s=st: self._pick(s))
            grid.addWidget(btn, i // cols, i % cols)
        scroll.setWidget(host)
        outer.addWidget(scroll)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)
        self.resize(660, 520)

    def _pick(self, st):
        self.chosen = st
        self.accept()
