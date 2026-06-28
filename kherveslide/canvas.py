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

from .model import Slide, SlideText, SlidePicture


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


class BoxItem(QGraphicsObject):
    """A movable, eight-handle-resizable rectangle bound to a model
    object. Position is the item's scene pos; size is the local rect
    ``(0, 0, w, h)``. Subclasses paint the content."""

    geometryChanged = Signal()

    def __init__(self, obj, scene_w: float):
        super().__init__()
        self.obj = obj
        self._rect = QRectF(0, 0, max(MIN_PX, obj.w * scene_w),
                            max(MIN_PX, obj.h * SCENE_H))
        self.setPos(obj.x * scene_w, obj.y * SCENE_H)
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

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            sw = scene_width(self._aspect())
            nx = min(max(0.0, value.x()), sw - self._rect.width())
            ny = min(max(0.0, value.y()), SCENE_H - self._rect.height())
            return QPointF(nx, ny)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._write_geometry()
            self.geometryChanged.emit()
        return super().itemChange(change, value)

    def _aspect(self) -> str:
        sc = self.scene()
        return getattr(sc, "aspect", "169") if sc else "169"

    def _write_geometry(self) -> None:
        sw = scene_width(self._aspect())
        self.obj.x = round(self.pos().x() / sw, 4)
        self.obj.y = round(self.pos().y() / SCENE_H, 4)
        self.obj.w = round(self._rect.width() / sw, 4)
        self.obj.h = round(self._rect.height() / SCENE_H, 4)

    def sync_from_model(self) -> None:
        """Re-read geometry from the model (after spinbox edits)."""
        sw = scene_width(self._aspect())
        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, max(MIN_PX, self.obj.w * sw),
                            max(MIN_PX, self.obj.h * SCENE_H))
        self.setPos(self.obj.x * sw, self.obj.y * SCENE_H)
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
        font.setPixelSize(max(6, int(obj.font_pt * FONT_SCALE)))
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
    def __init__(self, obj, scene_w):
        super().__init__(obj, scene_w)
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


def make_item(obj, scene_w: float) -> BoxItem:
    return (TextBoxItem(obj, scene_w) if isinstance(obj, SlideText)
            else PictureBoxItem(obj, scene_w))


class SlideScene(QGraphicsScene):
    def __init__(self, aspect="169"):
        super().__init__()
        self.aspect = aspect
        self._set_rect()

    def _set_rect(self):
        self.setSceneRect(0, 0, scene_width(self.aspect), SCENE_H)

    def set_aspect(self, aspect):
        self.aspect = aspect
        self._set_rect()

    def drawBackground(self, painter, rect):
        painter.fillRect(self.sceneRect(), QColor("#FFFFFF"))
        painter.setPen(QPen(QColor(200, 200, 200), 0))
        painter.drawRect(self.sceneRect())


def render_thumbnail(slide: Slide, aspect: str, width_px: int = 160) -> QPixmap:
    """Render *slide* to a small pixmap for the navigator — reuses the
    same item painting as the live canvas so the thumbnail matches."""
    sw = scene_width(aspect)
    scene = SlideScene(aspect)
    if slide.bg:
        scene.setBackgroundBrush(QColor(slide.bg))
    for obj in slide.objects:
        item = make_item(obj, sw)
        item.setSelected(False)
        scene.addItem(item)
    height_px = int(width_px * SCENE_H / sw)
    pm = QPixmap(width_px, height_px)
    pm.fill(QColor("#FFFFFF"))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    scene.render(painter, QRectF(0, 0, width_px, height_px), scene.sceneRect())
    painter.end()
    return pm
