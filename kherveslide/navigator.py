"""The slide navigator — the little visual strip down the left side.

Each slide is a rendered thumbnail; dragging one reorders the deck, and
clicking one selects it. This is the "move the slides around" surface the
designer is built around.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from .canvas import render_thumbnail
from .model import Deck


THUMB_W = 168


class SlideNavigator(QListWidget):
    """Vertical strip of slide thumbnails with drag-to-reorder."""

    slideSelected = Signal(int)
    slidesReordered = Signal(list)   # emits the new index order

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ListMode)
        self.setIconSize(QSize(THUMB_W, THUMB_W * 9 // 16))
        self.setSpacing(6)
        self.setMovement(QListWidget.Snap)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setUniformItemSizes(False)
        self.setFixedWidth(THUMB_W + 36)
        self.setStyleSheet("QListWidget::item { padding: 2px; }")
        self.currentRowChanged.connect(self._on_row)
        self._suppress = False

    def _on_row(self, row: int):
        if not self._suppress and row >= 0:
            self.slideSelected.emit(row)

    def refresh(self, deck: Deck, current: int):
        """Rebuild every thumbnail from the deck and keep *current*
        selected."""
        self._suppress = True
        self.clear()
        for i, slide in enumerate(deck.slides):
            pm = render_thumbnail(slide, deck.aspect, THUMB_W)
            item = QListWidgetItem(QIcon(pm), f"  {i + 1}")
            item.setSizeHint(QSize(THUMB_W + 8, pm.height() + 8))
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item.setData(Qt.UserRole, i)   # source index, survives reorder
            self.addItem(item)
        self.setCurrentRow(current)
        self._suppress = False

    def refresh_one(self, deck: Deck, index: int):
        """Re-render just one thumbnail (after editing its slide) without
        disturbing selection or scroll position."""
        if 0 <= index < self.count():
            pm = render_thumbnail(deck.slides[index], deck.aspect, THUMB_W)
            self.item(index).setIcon(QIcon(pm))

    def dropEvent(self, event):
        super().dropEvent(event)
        # Each item still carries its original deck index in UserRole, so
        # reading them top-to-bottom gives the exact permutation to apply.
        order = [self.item(r).data(Qt.UserRole) for r in range(self.count())]
        if order != sorted(order):
            self.slidesReordered.emit(order)
