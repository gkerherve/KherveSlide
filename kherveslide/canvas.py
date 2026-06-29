"""The slide canvas — graphics scene plus the movable / resizable boxes.

Geometry is stored in the model as ``0..1`` fractions of the slide; here
those map onto a fixed-height scene so the boxes can be dragged and
resized directly, and the same drawing code renders the little
thumbnails shown in the slide navigator.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsScene,
)

from .model import Slide, SlideText, SlidePicture, SlideTable


SCENE_H = 720.0                 # slide height in scene units (px)
# beamer's slide height is ~96 mm ≈ 272.8 pt for every aspect ratio, so
# this turns a font's pt size into canvas pixels for WYSIWYG sizing.
FONT_SCALE = SCENE_H / 272.8
HANDLE = 9.0                    # half-size of a resize handle, in px
MIN_PX = 24.0                   # smallest box dimension

_ASPECT_RATIO = {              # width : height multiplier
    "169": 16 / 9, "1610": 16 / 10, "43": 4 / 3,
    "32": 3 / 2, "54": 5 / 4, "141": 1.41,
}

# Resize-handle ids, clockwise from top-left.
TL, T, TR, R, BR, B, BL, L = range(8)
_LEFT = {TL, L, BL}
_RIGHT = {TR, R, BR}
_TOP = {TL, T, TR}
_BOTTOM = {BL, B, BR}


def scene_width(aspect: str) -> float:
    return SCENE_H * _ASPECT_RATIO.get(aspect, 16 / 9)


_CM_TO_PT = 72.27 / 2.54
_BEAMER_H_PT = 272.8        # beamer slide height (~96 mm) for the presets


def page_size_px(aspect: str, w_cm: float = 0.0, h_cm: float = 0.0):
    """Return (page_w_px, page_h_px, font_scale). Height is fixed at
    SCENE_H; width follows the aspect or custom cm size. font_scale turns
    a pt font size into canvas pixels for the page's real height."""
    if w_cm > 0 and h_cm > 0:
        ratio = w_cm / h_cm
        h_pt = h_cm * _CM_TO_PT
    else:
        ratio = _ASPECT_RATIO.get(aspect, 16 / 9)
        h_pt = _BEAMER_H_PT
    return SCENE_H * ratio, SCENE_H, SCENE_H / h_pt


class BoxItem(QGraphicsObject):
    """A movable, eight-handle-resizable rectangle bound to a model
    object. Coordinates are 0..1 within the page's content area (page
    minus the deck's gap); this maps them to scene pixels. Subclasses
    paint the content."""

    geometryChanged = Signal()
    doubleClicked = Signal()

    def __init__(self, obj, page_w: float, page_h: float, gap: float = 0.0,
                 font_scale: float = FONT_SCALE):
        super().__init__()
        self.obj = obj
        self._pw = page_w
        self._ph = page_h
        self._gap = gap
        self._font_scale = font_scale
        cw, ch, ox, oy = self._content()
        self._rect = QRectF(0, 0, max(MIN_PX, obj.w * cw),
                            max(MIN_PX, obj.h * ch))
        self.setPos(ox + obj.x * cw, oy + obj.y * ch)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self._resize_handle: int | None = None
        self._press_scene = QPointF()
        self._start_rect = QRectF()
        self._start_pos = QPointF()

    # -- geometry --------------------------------------------------
    def boundingRect(self) -> QRectF:
        m = HANDLE + 1
        return self._rect.adjusted(-m, -m, m, m)

    def _handle_rects(self) -> dict[int, QRectF]:
        r = self._rect
        cx, cy = r.center().x(), r.center().y()
        pts = {
            TL: (r.left(), r.top()), T: (cx, r.top()), TR: (r.right(), r.top()),
            R: (r.right(), cy), BR: (r.right(), r.bottom()),
            B: (cx, r.bottom()), BL: (r.left(), r.bottom()), L: (r.left(), cy),
        }
        return {h: QRectF(x - HANDLE, y - HANDLE, 2 * HANDLE, 2 * HANDLE)
                for h, (x, y) in pts.items()}

    def _handle_at(self, pos: QPointF) -> int | None:
        for h, rect in self._handle_rects().items():
            if rect.contains(pos):
                return h
        return None

    # -- mouse -----------------------------------------------------
    def hoverMoveEvent(self, event):
        h = self._handle_at(event.pos()) if self.isSelected() else None
        cursors = {
            TL: Qt.SizeFDiagCursor, BR: Qt.SizeFDiagCursor,
            TR: Qt.SizeBDiagCursor, BL: Qt.SizeBDiagCursor,
            T: Qt.SizeVerCursor, B: Qt.SizeVerCursor,
            L: Qt.SizeHorCursor, R: Qt.SizeHorCursor,
        }
        self.setCursor(cursors.get(h, Qt.SizeAllCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        h = self._handle_at(event.pos()) if self.isSelected() else None
        if h is not None:
            self._resize_handle = h
            self._press_scene = event.scenePos()
            self._start_rect = QRectF(self._rect)
            self._start_pos = self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_handle is None:
            super().mouseMoveEvent(event)
            return
        d = event.scenePos() - self._press_scene
        x, y = self._start_pos.x(), self._start_pos.y()
        w, h = self._start_rect.width(), self._start_rect.height()
        hd = self._resize_handle
        if hd in _LEFT:
            x += d.x(); w -= d.x()
        if hd in _RIGHT:
            w += d.x()
        if hd in _TOP:
            y += d.y(); h -= d.y()
        if hd in _BOTTOM:
            h += d.y()
        if w < MIN_PX:
            if hd in _LEFT:
                x = self._start_pos.x() + self._start_rect.width() - MIN_PX
            w = MIN_PX
        if h < MIN_PX:
            if hd in _TOP:
                y = self._start_pos.y() + self._start_rect.height() - MIN_PX
            h = MIN_PX
        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, w, h)
        self.setPos(x, y)
        self.update()
        self._write_geometry()
        self.geometryChanged.emit()

    def mouseReleaseEvent(self, event):
        self._resize_handle = None
        self._write_geometry()
        self.geometryChanged.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        # PowerPoint-style: double-click edits the object in place.
        self.doubleClicked.emit()
        event.accept()

    def scene_rect(self) -> QRectF:
        """The box's rectangle in scene coordinates (for placing an
        in-place editor over it)."""
        return QRectF(self.pos().x(), self.pos().y(),
                      self._rect.width(), self._rect.height())

    def _content(self):
        """Content area in scene px: (width, height, origin_x, origin_y)."""
        g = self._gap
        return ((1 - 2 * g) * self._pw, (1 - 2 * g) * self._ph,
                g * self._pw, g * self._ph)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            # Keep the box on the page (it may sit within the gap margin).
            nx = min(max(0.0, value.x()), self._pw - self._rect.width())
            ny = min(max(0.0, value.y()), self._ph - self._rect.height())
            return QPointF(nx, ny)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._write_geometry()
            self.geometryChanged.emit()
        return super().itemChange(change, value)

    def _write_geometry(self) -> None:
        cw, ch, ox, oy = self._content()
        self.obj.x = round((self.pos().x() - ox) / cw, 4)
        self.obj.y = round((self.pos().y() - oy) / ch, 4)
        self.obj.w = round(self._rect.width() / cw, 4)
        self.obj.h = round(self._rect.height() / ch, 4)

    def sync_from_model(self) -> None:
        """Re-read geometry from the model (after spinbox edits)."""
        cw, ch, ox, oy = self._content()
        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, max(MIN_PX, self.obj.w * cw),
                            max(MIN_PX, self.obj.h * ch))
        self.setPos(ox + self.obj.x * cw, oy + self.obj.y * ch)
        self.update()

    # -- painting helpers -----------------------------------------
    def _paint_selection(self, painter):
        if not self.isSelected():
            painter.setPen(QPen(QColor(150, 150, 150), 0, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._rect)
            return
        painter.setPen(QPen(QColor(40, 120, 220), 0, Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self._rect)
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(QPen(QColor(40, 120, 220), 0))
        for rect in self._handle_rects().values():
            painter.drawRect(rect)


class TextBoxItem(BoxItem):
    def paint(self, painter, option, widget=None):
        obj: SlideText = self.obj
        if obj.fill:
            painter.fillRect(self._rect, QColor(obj.fill))
        font = QFont("Helvetica")
        font.setPixelSize(max(6, int(obj.font_pt * self._font_scale)))
        font.setBold(obj.bold)
        font.setItalic(obj.italic)
        painter.setFont(font)
        painter.setPen(QPen(QColor(obj.color or "#000000")))
        flag = {"center": Qt.AlignHCenter, "right": Qt.AlignRight}.get(
            obj.align, Qt.AlignLeft)
        painter.drawText(self._rect.adjusted(4, 2, -4, -2),
                         int(flag | Qt.AlignTop | Qt.TextWordWrap),
                         obj.text or "")
        self._paint_selection(painter)


class PictureBoxItem(BoxItem):
    def __init__(self, obj, page_w, page_h, gap=0.0, font_scale=FONT_SCALE):
        super().__init__(obj, page_w, page_h, gap, font_scale)
        self._pix: QPixmap | None = None
        self._pix_path = None

    def _pixmap(self) -> QPixmap | None:
        if self.obj.path != self._pix_path:
            self._pix_path = self.obj.path
            pm = QPixmap(self.obj.path) if self.obj.path else QPixmap()
            self._pix = pm if not pm.isNull() else None
        return self._pix

    def paint(self, painter, option, widget=None):
        pm = self._pixmap()
        if pm is not None:
            mode = (Qt.KeepAspectRatio if self.obj.keep_aspect
                    else Qt.IgnoreAspectRatio)
            scaled = pm.scaled(self._rect.size().toSize(), mode,
                               Qt.SmoothTransformation)
            x = self._rect.x() + (self._rect.width() - scaled.width()) / 2
            y = self._rect.y() + (self._rect.height() - scaled.height()) / 2
            painter.drawPixmap(QPointF(x, y), scaled)
        else:
            painter.fillRect(self._rect, QColor(235, 235, 235))
            painter.setPen(QPen(QColor(150, 150, 150)))
            painter.drawText(self._rect, Qt.AlignCenter, "Image\n(set path)")
        self._paint_selection(painter)


class TableBoxItem(BoxItem):
    """A grid of cells stretched to the box. Double-clicking a cell asks
    the window to edit that cell in place."""

    cellDoubleClicked = Signal(int, int)

    def _dims(self):
        rows = self.obj.rows or [[""]]
        nrows = len(rows)
        ncols = max((len(r) for r in rows), default=1)
        return rows, nrows, ncols

    def cell_scene_rect(self, r: int, c: int) -> QRectF:
        _, nrows, ncols = self._dims()
        cw = self._rect.width() / ncols
        ch = self._rect.height() / nrows
        return QRectF(self.pos().x() + c * cw, self.pos().y() + r * ch, cw, ch)

    def _cell_at(self, pos: QPointF):
        _, nrows, ncols = self._dims()
        cw = self._rect.width() / ncols
        ch = self._rect.height() / nrows
        c = min(ncols - 1, max(0, int(pos.x() // cw)))
        r = min(nrows - 1, max(0, int(pos.y() // ch)))
        return r, c

    def mouseDoubleClickEvent(self, event):
        r, c = self._cell_at(event.pos())
        self.cellDoubleClicked.emit(r, c)
        event.accept()

    def paint(self, painter, option, widget=None):
        obj: SlideTable = self.obj
        rows, nrows, ncols = self._dims()
        cw = self._rect.width() / ncols
        ch = self._rect.height() / nrows
        painter.fillRect(self._rect, QColor("#FFFFFF"))
        if obj.border:
            painter.setPen(QPen(QColor(80, 80, 80), 0))
            for i in range(ncols + 1):
                x = self._rect.x() + i * cw
                painter.drawLine(QPointF(x, self._rect.y()),
                                 QPointF(x, self._rect.bottom()))
            for j in range(nrows + 1):
                y = self._rect.y() + j * ch
                painter.drawLine(QPointF(self._rect.x(), y),
                                 QPointF(self._rect.right(), y))
        font = QFont("Helvetica")
        font.setPixelSize(max(6, int(obj.font_pt * self._font_scale)))
        painter.setFont(font)
        painter.setPen(QPen(QColor(obj.color or "#000000")))
        for r in range(nrows):
            for c in range(ncols):
                text = rows[r][c] if c < len(rows[r]) else ""
                cell = QRectF(self._rect.x() + c * cw, self._rect.y() + r * ch,
                              cw, ch)
                painter.drawText(cell.adjusted(3, 1, -3, -1),
                                 int(Qt.AlignCenter | Qt.TextWordWrap), text)
        self._paint_selection(painter)


def make_item(obj, page_w, page_h, gap=0.0, font_scale=FONT_SCALE) -> BoxItem:
    if isinstance(obj, SlideText):
        return TextBoxItem(obj, page_w, page_h, gap, font_scale)
    if isinstance(obj, SlideTable):
        return TableBoxItem(obj, page_w, page_h, gap, font_scale)
    return PictureBoxItem(obj, page_w, page_h, gap, font_scale)


class SlideScene(QGraphicsScene):
    def __init__(self, aspect="169"):
        super().__init__()
        self.aspect = aspect
        self.page_color = "#FFFFFF"   # current slide background
        self.gap = 0.0
        self.page_w = scene_width(aspect)
        self.page_h = SCENE_H
        self._set_rect()

    def _set_rect(self):
        self.setSceneRect(0, 0, self.page_w, self.page_h)

    def set_aspect(self, aspect):
        self.aspect = aspect
        self.page_w = scene_width(aspect)
        self.page_h = SCENE_H
        self._set_rect()

    def set_page(self, page_w, page_h, gap):
        self.page_w = page_w
        self.page_h = page_h
        self.gap = gap
        self._set_rect()

    def drawBackground(self, painter, rect):
        # Fill the whole exposed area (incl. the margins beyond the page)
        # with grey "desk", then lay the white page on top with a soft
        # shadow and a thin edge. Done here — not via the view's
        # backgroundBrush — because setting that brush stops the view from
        # ever calling this, leaving the page unpainted.
        painter.fillRect(rect, QColor("#9aa0a6"))
        r = self.sceneRect()
        painter.fillRect(r.translated(7, 7), QColor(0, 0, 0, 45))
        painter.fillRect(r, QColor(self.page_color or "#FFFFFF"))
        painter.setPen(QPen(QColor(150, 150, 150), 0))
        painter.drawRect(r)
        if self.gap > 0:
            # Dashed guide showing the content "safe area".
            g = self.gap
            guide = QRectF(g * self.page_w, g * self.page_h,
                           (1 - 2 * g) * self.page_w, (1 - 2 * g) * self.page_h)
            painter.setPen(QPen(QColor(120, 160, 210), 0, Qt.DashLine))
            painter.drawRect(guide)


def render_thumbnail(slide: Slide, deck, width_px: int = 160) -> QPixmap:
    """Render *slide* to a small pixmap for the navigator — reuses the
    same item painting as the live canvas so the thumbnail matches."""
    pw, ph, fs = page_size_px(deck.aspect, deck.page_w_cm, deck.page_h_cm)
    scene = SlideScene(deck.aspect)
    scene.set_page(pw, ph, deck.gap)
    scene.page_color = slide.bg or "#FFFFFF"
    for obj in slide.objects:
        item = make_item(obj, pw, ph, deck.gap, fs)
        item.setSelected(False)
        scene.addItem(item)
    height_px = int(width_px * ph / pw)
    pm = QPixmap(width_px, height_px)
    pm.fill(QColor("#FFFFFF"))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    scene.render(painter, QRectF(0, 0, width_px, height_px), scene.sceneRect())
    painter.end()
    return pm
