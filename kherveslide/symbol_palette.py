"""A compact symbol picker — grouped LaTeX symbols, click to insert."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from .symbols import SYMBOL_GROUPS


class SymbolPalette(QDialog):
    """Modal palette; ``chosen`` holds the picked LaTeX after exec()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Insert symbol")
        self.resize(420, 360)
        self.chosen: str | None = None

        v = QVBoxLayout(self)
        tabs = QTabWidget()
        v.addWidget(tabs)
        for group, items in SYMBOL_GROUPS:
            page = QWidget()
            grid = QGridLayout(page)
            grid.setSpacing(2)
            for i, (latex, glyph) in enumerate(items):
                btn = QPushButton(glyph or latex)
                btn.setToolTip(latex)
                btn.setFixedSize(40, 34)
                btn.clicked.connect(lambda _=False, l=latex: self._pick(l))
                grid.addWidget(btn, i // 8, i % 8)
            tabs.addTab(page, group)

    def _pick(self, latex: str):
        self.chosen = latex
        self.accept()
