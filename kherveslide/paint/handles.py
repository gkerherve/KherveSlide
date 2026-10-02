"""Selection handles: resize a shape, or double-click to rotate it.

Selecting a single item (pointer tool) shows **resize** handles:

* line / arrow → a handle at each endpoint,
* polygon → a handle at each vertex,
* rect / ellipse / rounded-rect → eight bounding-box handles,
* everything else (path / image / text / group) → four corner handles
  that scale the item uniformly.

Double-clicking an item switches it to **rotate** mode: a knob above
the centre that spins the item about its own centre.  The scene owns a
single `SelectionHandles` instance for the active item; handles are
parented to that item (so they follow it) and are never serialised.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import math

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem,
                             QGraphicsLineItem, QGraphicsRectItem)

from .canvas import (ArcShapeItem, DimensionItem, EllipseItem, GroupItem,
                     ImageItem, LineItem, PolygonItem, RectItem,
                     RoundedRectItem, center_origin)

HANDLE_SIZE = 9
RESIZE, ROTATE = "resize", "rotate"

_BLUE = QColor("#2176c7")
_GREEN = QColor("#2e9e5b")
_WHITE = QColor("#ffffff")

_BOX_CURSORS = {
    "nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
    "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
    "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
    "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
}


class Handle:
    """Marker base so handles can be filtered out everywhere."""


class _GuideLine(Handle, QGraphicsLineItem):
    """Non-interactive dashed line from centre to the rotate knob."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.NoButton)


class _DragMixin:
    """Shared init + press/move/release plumbing for drag handles."""

    def _init(self, controller, role, color, cursor):
        self.controller = controller
        self.role = role
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(1000)
        self.setPen(QPen(color, 0))
        self.setBrush(QBrush(_WHITE))
        self.setCursor(cursor)

    def mousePressEvent(self, event):
        self.controller.begin(self.role, event.scenePos())
        event.accept()

    def mouseMoveEvent(self, event):
        self.controller.drag(self.role, event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self.controller.end()
        event.accept()


class _RectHandle(Handle, _DragMixin, QGraphicsRectItem):
    def __init__(self, controller, role, parent, color, cursor):
        super().__init__(parent)
        s = HANDLE_SIZE
        self.setRect(-s / 2, -s / 2, s, s)
        self._init(controller, role, color, cursor)


class _BendHandle(Handle, _DragMixin, QGraphicsEllipseItem):
    """Round handle at a line's midpoint: drag it off the line to bend
    the line into a curve; drag it back onto the line to straighten."""

    def __init__(self, controller, parent):
        super().__init__(parent)
        s = HANDLE_SIZE
        self.setRect(-s / 2, -s / 2, s, s)
        self._init(controller, "mid", _BLUE, Qt.SizeAllCursor)


class _RotateHandle(Handle, QGraphicsEllipseItem):
    def __init__(self, controller, parent):
        super().__init__(parent)
        s = HANDLE_SIZE + 2
        self.setRect(-s / 2, -s / 2, s, s)
        self.controller = controller
        self.role = "rotate"
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(1000)
        self.setPen(QPen(_GREEN, 0))
        self.setBrush(QBrush(_GREEN))
        self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, event):
        self.controller.begin(self.role, event.scenePos())
        event.accept()

    def mouseMoveEvent(self, event):
        self.controller.drag(self.role, event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self.controller.end()
        event.accept()


def _kind_of(item, mode: str) -> str:
    if mode == ROTATE:
        return "rotate"
    if isinstance(item, GroupItem):
        return "gbox"           # 8 handles: corners + sides (X/Y-only resize)
    if isinstance(item, LineItem):
        return "line"
    if isinstance(item, PolygonItem):
        return "polygon"
    if isinstance(item, (RectItem, EllipseItem, RoundedRectItem,
                         ArcShapeItem)):
        return "box"
    if isinstance(item, ImageItem):
        return "image"
    return "scale"


class SelectionHandles:
    """The set of handles around one item, in resize or rotate mode."""

    def __init__(self, scene, item, mode):
        self.scene = scene
        self.item = item
        self.mode = mode
        self.kind = _kind_of(item, mode)
        self.handles = []
        self._guide = None
        self._scale_base = 1.0
        self._scale_dist = 1.0
        # A QGraphicsItemGroup intercepts its children's mouse events
        # (and PyQt can't disable that), which would make a group's
        # handles dead. So a group's handles live at scene level instead
        # of as children; every other item parents them to itself so they
        # follow it for free. _place() maps anchors accordingly.
        self._scene_level = isinstance(item, GroupItem)
        self._build()
        self.reposition()

    # ------------------------------------------------------------ build
    def _parent(self):
        return None if self._scene_level else self.item

    def _attach(self, handle):
        if self._scene_level:
            self.scene.addItem(handle)
        return handle

    def _build(self):
        if self.kind == "rotate":
            self._guide = self._attach(_GuideLine(self._parent()))
            self._guide.setPen(QPen(_GREEN, 0, Qt.DashLine))
            self._guide.setZValue(999)
            self.handles = [self._attach(_RotateHandle(self, self._parent()))]
        elif self.kind == "line":
            self.handles = [self._rect_handle(r) for r in ("p1", "p2")]
            # Dimensions measure a straight span; only plain lines and
            # arrows get the round mid-handle that bends them.
            if not isinstance(self.item, DimensionItem):
                self.handles.append(
                    self._attach(_BendHandle(self, self._parent())))
        elif self.kind == "polygon":
            count = self.item.polygon().count()
            self.handles = [self._rect_handle(i) for i in range(count)]
        elif self.kind in ("box", "image", "gbox"):
            self.handles = [self._rect_handle(r, _BOX_CURSORS[r])
                            for r in _BOX_CURSORS]
        else:                       # scale
            self.handles = [self._rect_handle(r, _BOX_CURSORS[r])
                            for r in ("nw", "ne", "se", "sw")]

    def _rect_handle(self, role, cursor=Qt.SizeAllCursor):
        return self._attach(
            _RectHandle(self, role, self._parent(), _BLUE, cursor))

    # ------------------------------------------------------------ layout
    def _place(self, handle, local):
        """Position a handle at item-local point *local*, mapping to scene
        coords when the handles live at scene level (groups)."""
        handle.setPos(self.item.mapToScene(local) if self._scene_level
                      else local)

    def reposition(self):
        if self.kind == "rotate":
            br = self.item.boundingRect()
            center, knob = br.center(), QPointF(br.center().x(), br.top() - 22)
            self._place(self.handles[0], knob)
            if self._scene_level:
                self._guide.setPos(0, 0)
                self._guide.setLine(QLineF(self.item.mapToScene(center),
                                           self.item.mapToScene(knob)))
            else:
                self._guide.setLine(QLineF(center, knob))
            return
        for handle in self.handles:
            self._place(handle, self._anchor(handle.role))

    def _anchor(self, role) -> QPointF:
        if self.kind == "line":
            ln = self.item.line()
            if role == "mid":
                mid = (ln.p1() + ln.p2()) / 2
                bend = getattr(self.item, "bend", lambda: None)()
                if bend is None:
                    return mid
                # the point the quadratic curve passes through at t=0.5
                return (mid + bend) / 2
            return ln.p1() if role == "p1" else ln.p2()
        if self.kind == "polygon":
            return self.item.polygon().at(role)
        rect = self.item.rect() if self.kind == "box" \
            else self.item.boundingRect()
        table = {
            "nw": rect.topLeft(), "ne": rect.topRight(),
            "se": rect.bottomRight(), "sw": rect.bottomLeft(),
            "n": QPointF(rect.center().x(), rect.top()),
            "s": QPointF(rect.center().x(), rect.bottom()),
            "e": QPointF(rect.right(), rect.center().y()),
            "w": QPointF(rect.left(), rect.center().y()),
        }
        return table[role]

    # ------------------------------------------------------------ drag
    def begin(self, role, scene_pos):
        self.item.setSelected(True)
        if self.kind == "rotate":
            center_origin(self.item)
            self._center = self.item.mapToScene(
                self.item.transformOriginPoint())
        elif self.kind == "scale":
            # Anchor the corner opposite the one being dragged, so the
            # item grows/shrinks from that fixed point (a proper box
            # resize) rather than ballooning about its centre.
            center_origin(self.item)
            self._origin = self.item.transformOriginPoint()
            br = self.item.boundingRect()
            corners = {"nw": br.topLeft(), "ne": br.topRight(),
                       "se": br.bottomRight(), "sw": br.bottomLeft()}
            opposite = {"nw": "se", "ne": "sw", "se": "nw", "sw": "ne"}
            self._anchor_local = corners[opposite.get(role, "nw")]
            self._anchor_scene = self.item.mapToScene(self._anchor_local)
            self._scale_base = self.item.scale() or 1.0
            self._scale_dist = max(_dist(scene_pos, self._anchor_scene), 1.0)
        elif self.kind == "gbox":
            # Group resize: capture the base local->scene map and the
            # group's own transform; _resize_gbox folds a non-uniform
            # scale (X-only / Y-only / both) into that transform.
            self._g_inv0 = self.item.sceneTransform().inverted()[0]
            self._tf0 = self.item.transform()
            self._br = self.item.boundingRect()

    def drag(self, role, scene_pos):
        snapped = self.scene.snap(scene_pos) \
            if getattr(self.scene, "snap_enabled", False) else scene_pos
        local = self.item.mapFromScene(snapped)
        if self.kind == "rotate":
            self._rotate(scene_pos)
        elif self.kind == "scale":
            self._scale(snapped)            # snap the dragged corner too
        elif self.kind == "line":
            self._drag_line(role, local)
        elif self.kind == "polygon":
            self._drag_vertex(role, local)
        elif self.kind == "box":
            self._drag_box(role, local)
        elif self.kind == "image":
            self._drag_image(role, snapped)
        elif self.kind == "gbox":
            self._resize_gbox(role, snapped)
        self.reposition()

    def end(self):
        self.scene.changed_by_user.emit()

    def remove(self):
        for handle in self.handles:
            if handle.scene() is not None:
                handle.scene().removeItem(handle)
        if self._guide is not None and self._guide.scene() is not None:
            self._guide.scene().removeItem(self._guide)
        self.handles = []
        self._guide = None

    # ------------------------------------------------------------ edits
    def _rotate(self, scene_pos):
        v = scene_pos - self._center
        angle = math.degrees(math.atan2(v.y(), v.x())) + 90
        if getattr(self.scene, "snap_enabled", False):
            angle = round(angle / 15) * 15
        self.item.setRotation(angle)

    def _scale(self, scene_pos):
        factor = _dist(scene_pos, self._anchor_scene) / self._scale_dist
        s_new = max(self._scale_base * factor, 0.05)
        self.item.setScale(s_new)
        # Reposition so the anchored corner keeps its scene position:
        # scene(p) = pos + origin + R·S·(p - origin)  (Qt's item transform).
        lin = QTransform()
        lin.rotate(self.item.rotation())
        lin.scale(s_new, s_new)
        vec = lin.map(self._anchor_local - self._origin)
        was_snap = self.scene.snap_enabled
        self.scene.snap_enabled = False        # setPos must not re-snap here
        self.item.setPos(self._anchor_scene - self._origin - vec)
        self.scene.snap_enabled = was_snap

    def _resize_gbox(self, role, scene_pos):
        """Resize a group by folding a non-uniform scale into its
        transform, about the side/corner opposite the dragged handle —
        side handles scale X-only or Y-only, corners scale both."""
        br = self._br
        corners = {
            "nw": br.topLeft(), "ne": br.topRight(),
            "se": br.bottomRight(), "sw": br.bottomLeft(),
            "n": QPointF(br.center().x(), br.top()),
            "s": QPointF(br.center().x(), br.bottom()),
            "e": QPointF(br.right(), br.center().y()),
            "w": QPointF(br.left(), br.center().y()),
        }
        opposite = {"nw": "se", "ne": "sw", "se": "nw", "sw": "ne",
                    "n": "s", "s": "n", "e": "w", "w": "e"}
        anchor, moving = corners[opposite[role]], corners[role]
        cur = self._g_inv0.map(scene_pos)          # cursor in group-local
        sx = sy = 1.0
        if "e" in role or "w" in role:
            d = moving.x() - anchor.x()
            if abs(d) > 1e-6:
                sx = (cur.x() - anchor.x()) / d
        if "n" in role or "s" in role:
            d = moving.y() - anchor.y()
            if abs(d) > 1e-6:
                sy = (cur.y() - anchor.y()) / d
        sx = max(sx, 0.05) if sx >= 0 else min(sx, -0.05)
        sy = max(sy, 0.05) if sy >= 0 else min(sy, -0.05)
        scale = QTransform()
        scale.translate(anchor.x(), anchor.y())
        scale.scale(sx, sy)
        scale.translate(-anchor.x(), -anchor.y())
        self.item.setTransform(scale * self._tf0)  # scale in local frame

    def _drag_line(self, role, local):
        ln = self.item.line()
        if role == "mid":
            # Bend so the curve passes through the cursor: for a
            # quadratic, control = 2·M − midpoint. Dropping the handle
            # back onto the straight line straightens the line again.
            mid = (ln.p1() + ln.p2()) / 2
            if ln.length() > 1e-6:
                off = abs(ln.dx() * (local.y() - ln.y1())
                          - ln.dy() * (local.x() - ln.x1())) / ln.length()
            else:
                off = _dist(local, mid)
            self.item.set_bend(None if off < 2.0 else local * 2 - mid)
            return
        if role == "p1":
            ln.setP1(local)
        else:
            ln.setP2(local)
        self.item.setLine(ln)

    def _drag_vertex(self, index, local):
        poly = QPolygonF(self.item.polygon())
        poly.replace(index, local)
        self.item.setPolygon(poly)
        if self.item.rotation() == 0:
            center_origin(self.item)

    def _drag_box(self, role, local):
        r = QRectF(self.item.rect())
        if "n" in role:
            r.setTop(local.y())
        if "s" in role:
            r.setBottom(local.y())
        if "w" in role:
            r.setLeft(local.x())
        if "e" in role:
            r.setRight(local.x())
        r = r.normalized()
        if r.width() < 1:
            r.setWidth(1)
        if r.height() < 1:
            r.setHeight(1)
        if hasattr(self.item, "set_rect"):      # rounded-rect, arc shapes
            self.item.set_rect(r)
        else:                                   # rect, ellipse
            self.item.setRect(r)
        if self.item.rotation() == 0:
            center_origin(self.item)

    def _drag_image(self, role, scene_pos):
        """Resize an image like a box, snapping the dragged corner to the
        grid. The pixmap is stretched to fill the new rect via a scale
        transform (the opposite corner stays fixed)."""
        cur = self.item.sceneBoundingRect()
        r = QRectF(cur)
        if "n" in role:
            r.setTop(scene_pos.y())
        if "s" in role:
            r.setBottom(scene_pos.y())
        if "w" in role:
            r.setLeft(scene_pos.x())
        if "e" in role:
            r.setRight(scene_pos.x())
        r = r.normalized()
        if r.width() < 1:
            r.setWidth(1)
        if r.height() < 1:
            r.setHeight(1)
        br = self.item.boundingRect()           # may include a half-px edge
        if br.width() < 1 or br.height() < 1:
            return
        sx, sy = r.width() / br.width(), r.height() / br.height()
        was_snap = self.scene.snap_enabled
        self.scene.snap_enabled = False         # corner already snapped
        self.item.setTransformOriginPoint(0, 0)
        self.item.setTransform(QTransform(sx, 0, 0, sy, 0, 0))
        # map the boundingRect's top-left exactly onto the target rect
        self.item.setPos(r.left() - sx * br.left(), r.top() - sy * br.top())
        self.scene.snap_enabled = was_snap


def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())
