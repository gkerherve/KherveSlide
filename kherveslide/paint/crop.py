"""Interactive cropping of an image item.

Starting a crop overlays the image with a dimmed mask, a dashed crop
frame and eight drag handles (reused from `handles.py`).  Dragging the
handles sets the crop rectangle; pressing Enter applies it (the
pixmap is replaced by the cropped copy and the item shifts so the kept
region stays put), Escape cancels.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPathItem,
                             QGraphicsRectItem)

from .handles import _BLUE, _BOX_CURSORS, Handle, _RectHandle


class _CropMask(Handle, QGraphicsPathItem):
    """Dimming overlay outside the crop rect (a Handle so it is never
    serialised or picked)."""


class _CropFrame(Handle, QGraphicsRectItem):
    pass


class CropSession:
    """Drives the crop overlay on one image item."""

    def __init__(self, scene, image):
        self.scene = scene
        self.image = image
        pm = image.pixmap()
        self.bounds = QRectF(0, 0, pm.width(), pm.height())
        self.rect = QRectF(self.bounds)
        # Freeze the image while cropping so it can't be moved or show
        # its own selection handles over the crop overlay.
        self._old_flags = image.flags()
        image.setFlag(QGraphicsItem.ItemIsMovable, False)
        image.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self._build()

    def _build(self):
        self.mask = _CropMask(self.image)
        self.mask.setBrush(QBrush(QColor(0, 0, 0, 110)))
        self.mask.setPen(QPen(Qt.NoPen))
        self.mask.setZValue(1000)

        self.frame = _CropFrame(self.image)
        self.frame.setPen(QPen(_BLUE, 0, Qt.DashLine))
        self.frame.setBrush(QBrush(Qt.NoBrush))
        self.frame.setZValue(1001)

        self.handles = [_RectHandle(self, role, self.image, _BLUE, cursor)
                        for role, cursor in _BOX_CURSORS.items()]
        self.reposition()

    def reposition(self):
        path = QPainterPath()
        path.addRect(self.bounds)
        path.addRect(self.rect)          # odd-even -> hole over the crop
        path.setFillRule(Qt.OddEvenFill)
        self.mask.setPath(path)
        self.frame.setRect(self.rect)
        r = self.rect
        table = {
            "nw": r.topLeft(), "ne": r.topRight(),
            "se": r.bottomRight(), "sw": r.bottomLeft(),
            "n": QPointF(r.center().x(), r.top()),
            "s": QPointF(r.center().x(), r.bottom()),
            "e": QPointF(r.right(), r.center().y()),
            "w": QPointF(r.left(), r.center().y()),
        }
        for handle in self.handles:
            handle.setPos(table[handle.role])

    # --------------------------------------------- handle controller API
    def begin(self, role, scene_pos):
        pass

    def drag(self, role, scene_pos):
        local = self.image.mapFromScene(scene_pos)
        r = QRectF(self.rect)
        if "n" in role:
            r.setTop(local.y())
        if "s" in role:
            r.setBottom(local.y())
        if "w" in role:
            r.setLeft(local.x())
        if "e" in role:
            r.setRight(local.x())
        r = r.normalized().intersected(self.bounds)
        if r.width() < 1:
            r.setWidth(1)
        if r.height() < 1:
            r.setHeight(1)
        self.rect = r
        self.reposition()

    def end(self):
        pass

    # --------------------------------------------- finish
    def apply(self):
        ir = self.rect.intersected(self.bounds).toRect()
        if ir.width() < 1 or ir.height() < 1:
            self.cancel()
            return
        old_rect = self.image.sceneBoundingRect()
        cropped = self.image.pixmap().copy(ir)
        self.remove()
        # Shift the item so the kept region stays where it was (assumes
        # the image is unrotated / unscaled). Bypass grid snap so the
        # offset is exact.
        prev_snap = self.scene.snap_enabled
        self.scene.snap_enabled = False
        self.image.setPos(self.image.x() + ir.x(), self.image.y() + ir.y())
        self.scene.snap_enabled = prev_snap
        self.image.setPixmap(cropped)
        # The pixmap shrank: repaint the old (larger) area too, or the
        # cropped-off strip leaves stale pixels on screen.
        self.scene.update(old_rect.united(self.image.sceneBoundingRect()))
        self.scene.changed_by_user.emit()

    def cancel(self):
        self.remove()

    def remove(self):
        for item in [self.mask, self.frame, *self.handles]:
            if item is not None and item.scene() is not None:
                item.scene().removeItem(item)
        self.handles = []
        self.mask = None
        self.frame = None
        self.image.setFlags(self._old_flags)      # restore move/select
