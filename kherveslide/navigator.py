"""The slide navigator — the little visual strip down the left side.

Each slide is a rendered thumbnail; dragging one up or down reorders the
deck (an orange line shows where it will land), and clicking one selects
it. Right-click for the slide menu (delete, hide / show, move…); Delete
removes the selected slide. A hidden slide is drawn faded with its number
struck through. This is the "move the slides around" surface the designer
is built around.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem

from .canvas import render_thumbnail
from .model import Deck


THUMB_W = 200


def faded(pm: QPixmap) -> QPixmap:
    """A hidden slide's thumbnail: washed out, with a slashed-eye badge."""
    out = QPixmap(pm)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    dpr = out.devicePixelRatio()
    w, h = out.width() / dpr, out.height() / dpr
    p.fillRect(0, 0, round(w), round(h), QColor(255, 255, 255, 150))
    r = 11
    cx, cy = w - r - 5, r + 5
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(55, 65, 81, 210))
    p.drawEllipse(round(cx - r), round(cy - r), 2 * r, 2 * r)
    p.setPen(QPen(QColor("white"), 1.6))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(round(cx - 6), round(cy - 3.5), 12, 7)
    p.drawLine(round(cx - 6), round(cy + 6), round(cx + 6), round(cy - 6))
    p.end()
    return out


def hidden_label_font(base: QFont) -> QFont:
    f = QFont(base)
    f.setStrikeOut(True)
    return f


class SlideNavigator(QListWidget):
    """Vertical strip of slide thumbnails with drag-to-reorder."""

    slideSelected = Signal(int)
    slidesReordered = Signal(list)   # emits the new index order
    slideMenuRequested = Signal(int, object)   # (row, global QPoint)
    deleteRequested = Signal(int)              # Delete on a slide

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ListMode)
        self.setIconSize(QSize(THUMB_W, THUMB_W * 9 // 16))
        self.setSpacing(6)
        # Dragging a slide up / down is done here, not by Qt's item drag
        # (a press, a move past the drag distance, a release): the slide
        # lands exactly where the orange line shows, with no clash with
        # dropping presentation files on the window.
        self.setDragDropMode(QListWidget.NoDragDrop)
        self._press: tuple | None = None    # (row, QPoint) of the press
        self._drop_row: int | None = None   # insertion row while dragging
        self.setUniformItemSizes(False)
        self.setFixedWidth(THUMB_W + 36)
        self.setStyleSheet("QListWidget::item { padding: 2px; }")
        self.currentRowChanged.connect(self._on_row)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self._suppress = False
        # Optional callable (index, width) -> QPixmap | None giving the
        # themed page to draw under each thumbnail (set by the window).
        self.backdrop_for = None
        # While the master is edited: the slide whose page shows under it
        # (the list then holds the master alone), else None.
        self.master_index: int | None = None

    def _backdrop(self, index: int):
        if self.backdrop_for is None:
            return None
        from .canvas import thumbnail_dpr
        return self.backdrop_for(index, int(THUMB_W * thumbnail_dpr()))

    def _on_row(self, row: int):
        if not self._suppress and row >= 0:
            self.slideSelected.emit(row)

    def _on_context_menu(self, pos):
        item = self.itemAt(pos)
        row = self.row(item) if item is not None else self.currentRow()
        if row >= 0:
            self.slideMenuRequested.emit(row, self.viewport().mapToGlobal(pos))

    def refresh(self, deck: Deck, current: int):
        """Rebuild every thumbnail from the deck and keep *current*
        selected."""
        self._suppress = True
        self.clear()
        if self.master_index is not None:
            pm = render_thumbnail(deck.master, deck, THUMB_W,
                                  self._backdrop(self.master_index))
            item = QListWidgetItem(QIcon(pm), "  Master")
            h = round(pm.height() / pm.devicePixelRatio())
            item.setSizeHint(QSize(THUMB_W + 8, h + 8))
            item.setToolTip("The master: what you put on it shows on "
                            "every slide")
            item.setFlags(item.flags() & ~Qt.ItemIsDragEnabled)
            self.addItem(item)
            self.setCurrentRow(0)
            self._suppress = False
            return
        for i, slide in enumerate(deck.slides):
            pm = render_thumbnail(slide, deck, THUMB_W, self._backdrop(i))
            if slide.hidden:
                pm = faded(pm)
            item = QListWidgetItem(QIcon(pm), f"  {i + 1}")
            if slide.hidden:
                item.setFont(hidden_label_font(item.font()))
                item.setForeground(QColor("#9ca3af"))
                item.setToolTip("Hidden — not in the PDF or the slideshow "
                                "(right-click ▸ Show slide)")
            h = round(pm.height() / pm.devicePixelRatio())
            item.setSizeHint(QSize(THUMB_W + 8, h + 8))
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item.setData(Qt.UserRole, i)   # source index, survives reorder
            self.addItem(item)
        self.setCurrentRow(current)
        self._suppress = False

    def refresh_one(self, deck: Deck, index: int):
        """Re-render just one thumbnail (after editing its slide) without
        disturbing selection or scroll position."""
        if self.master_index is not None:
            self.refresh(deck, 0)
            return
        if 0 <= index < self.count():
            pm = render_thumbnail(deck.slides[index], deck, THUMB_W,
                                  self._backdrop(index))
            if deck.slides[index].hidden:
                pm = faded(pm)
            self.item(index).setIcon(QIcon(pm))

    # ---- drag a slide up or down ----
    def _insertion_row(self, pos) -> int:
        """Where a slide dropped at *pos* goes: before the first slide whose
        middle is below the pointer, or at the end."""
        for r in range(self.count()):
            if pos.y() < self.visualItemRect(self.item(r)).center().y():
                return r
        return self.count()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        item = self.itemAt(event.position().toPoint())
        self._drop_row = None
        self._press = ((self.row(item), event.position().toPoint())
                       if item is not None and self.master_index is None
                       and event.button() == Qt.LeftButton else None)

    def mouseMoveEvent(self, event):
        if self._press is None or not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        pos = event.position().toPoint()
        if self._drop_row is None and (pos - self._press[1]).manhattanLength() \
                < QApplication.startDragDistance():
            return
        self._drop_row = self._insertion_row(pos)
        self.viewport().setCursor(Qt.ClosedHandCursor)
        bar = self.verticalScrollBar()       # scroll near the edges
        if pos.y() < 30:
            bar.setValue(bar.value() - 14)
        elif pos.y() > self.viewport().height() - 30:
            bar.setValue(bar.value() + 14)
        self.viewport().update()

    def mouseReleaseEvent(self, event):
        press, drop = self._press, self._drop_row
        self._press = self._drop_row = None
        if press is None or drop is None:
            super().mouseReleaseEvent(event)
            return
        self.viewport().unsetCursor()
        self.viewport().update()
        src = press[0]
        order = list(range(self.count()))
        order.pop(src)
        order.insert(drop - 1 if drop > src else drop, src)
        if order != sorted(order):
            self.slidesReordered.emit(order)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_row is None or not self.count():
            return
        if self._drop_row < self.count():
            y = self.visualItemRect(self.item(self._drop_row)).top() - 3
        else:
            y = self.visualItemRect(self.item(self.count() - 1)).bottom() + 3
        p = QPainter(self.viewport())
        p.setPen(QPen(QColor("#DE6A14"), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(6, y, self.viewport().width() - 6, y)
        p.end()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) \
                and self.master_index is None and self.currentRow() >= 0:
            self.deleteRequested.emit(self.currentRow())
            return
        super().keyPressEvent(event)
