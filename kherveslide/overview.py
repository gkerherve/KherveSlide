"""The overview of all the slides — PowerPoint's slide sorter.

Every slide as a mini page in a grid that wraps to the panel's width
(shown in the right frame beside the Visual editor, or in place of the
slide when the PDF panel is hidden). Click a slide to go to it,
double-click to edit it, drag to reorder, right-click for the slide menu;
the slider sets the size of the mini pages.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem, QSlider,
    QVBoxLayout, QWidget,
)

from .canvas import render_thumbnail, thumbnail_dpr
from .navigator import faded

_NUMBER_H = 18           # room under each mini page for its number


class _Grid(QListWidget):
    reordered = Signal(list)

    def dropEvent(self, event):
        super().dropEvent(event)
        order = [self.item(r).data(Qt.UserRole) for r in range(self.count())]
        if order != sorted(order):
            self.reordered.emit(order)


class SlideOverview(QWidget):
    slideChosen = Signal(int)          # click: go to that slide
    slideOpened = Signal(int)          # double-click: edit it
    slidesReordered = Signal(list)     # the new index order
    slideMenuRequested = Signal(int, object)   # (row, global QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        head = QHBoxLayout()
        title = QLabel("All slides")
        f = title.font()
        f.setBold(True)
        title.setFont(f)
        head.addWidget(title)
        hint = QLabel("click to go · double-click to edit · drag to reorder")
        hint.setStyleSheet("color:#6b7280;")
        head.addWidget(hint, 1)
        head.addWidget(QLabel("Size"))
        self.size = QSlider(Qt.Horizontal)
        self.size.setRange(110, 420)
        self.size.setValue(200)
        self.size.setFixedWidth(110)
        self.size.setToolTip("Size of the mini pages")
        self.size.valueChanged.connect(lambda _v: self._rebuild())
        head.addWidget(self.size)
        lay.addLayout(head)

        self.grid = _Grid()
        g = self.grid
        g.setViewMode(QListView.ListMode)     # keeps drag-to-reorder exact
        g.setFlow(QListView.LeftToRight)
        g.setWrapping(True)
        g.setResizeMode(QListView.Adjust)
        g.setSpacing(10)
        g.setMovement(QListView.Snap)
        g.setDragDropMode(QListWidget.InternalMove)
        g.setDefaultDropAction(Qt.MoveAction)
        g.setStyleSheet(
            "QListWidget { background: #e9ebee; border: none; }"
            "QListWidget::item { border: 2px solid transparent;"
            " border-radius: 3px; padding: 2px; }"
            "QListWidget::item:selected { border-color: #DE6A14;"
            " background: rgba(222, 106, 20, 30); }")
        g.itemClicked.connect(lambda it: self.slideChosen.emit(g.row(it)))
        g.itemDoubleClicked.connect(
            lambda it: self.slideOpened.emit(g.row(it)))
        g.reordered.connect(self.slidesReordered)
        g.setContextMenuPolicy(Qt.CustomContextMenu)
        g.customContextMenuRequested.connect(self._on_context_menu)
        lay.addWidget(g, 1)

        # Optional callable (index, width_px) -> QPixmap | None giving the
        # themed page under each slide (the window's backdrop).
        self.backdrop_for = None
        self._deck = None
        self._current = 0
        self._dirty = False

    def _on_context_menu(self, pos):
        item = self.grid.itemAt(pos)
        if item is not None:
            self.slideMenuRequested.emit(
                self.grid.row(item), self.grid.viewport().mapToGlobal(pos))

    def refresh(self, deck, current: int) -> None:
        """Show *deck*'s slides with *current* selected — at once when
        visible, else the next time the overview is shown."""
        self._deck, self._current = deck, current
        if self.isVisible():
            self._rebuild()
        else:
            self._dirty = True

    def select(self, current: int) -> None:
        self._current = current
        if 0 <= current < self.grid.count():
            self.grid.setCurrentRow(current)

    def showEvent(self, event):
        super().showEvent(event)
        if self._dirty:
            self._rebuild()

    def _page(self, index: int, slide, width: int) -> QPixmap:
        bd = None
        if self.backdrop_for is not None:
            bd = self.backdrop_for(index, int(width * thumbnail_dpr()))
        pm = render_thumbnail(slide, self._deck, width, bd)
        if slide.hidden:
            pm = faded(pm)
        dpr = pm.devicePixelRatio()
        h = round(pm.height() / dpr)
        out = QPixmap(round(width * dpr), round((h + _NUMBER_H) * dpr))
        out.setDevicePixelRatio(dpr)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, pm)
        p.setPen(QColor(0, 0, 0, 60))
        p.drawRect(0, 0, width - 1, h - 1)
        f = QFont()
        f.setPixelSize(12)
        f.setStrikeOut(slide.hidden)
        p.setFont(f)
        p.setPen(QColor("#9ca3af" if slide.hidden else "#374151"))
        p.drawText(0, h, width, _NUMBER_H, Qt.AlignCenter, str(index + 1))
        p.end()
        return out

    def _rebuild(self) -> None:
        self._dirty = False
        g = self.grid
        g.clear()
        if self._deck is None:
            return
        w = self.size.value()
        size = None
        for i, slide in enumerate(self._deck.slides):
            pm = self._page(i, slide, w)
            size = QSize(w, round(pm.height() / pm.devicePixelRatio()))
            item = QListWidgetItem(QIcon(pm), "")
            item.setData(Qt.UserRole, i)     # source index, survives drags
            item.setToolTip((slide.title or f"Slide {i + 1}")
                            + (" — hidden" if slide.hidden else ""))
            item.setSizeHint(size + QSize(8, 8))
            g.addItem(item)
        if size is not None:
            g.setIconSize(size)
        self.select(self._current)
