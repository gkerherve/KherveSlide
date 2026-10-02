"""Bucket flood-fill of an enclosed region.

Clicking with the bucket tool renders the scene to an image and
scanline-floods the connected area of similar colour from the click,
stopping at any shape outline.  The result is applied either:

* **raster** — the filled pixels are painted into the raster layer, or
* **vector** — the filled area is traced into an editable `PathItem`
  placed behind the shapes that bound it.

Because the fill works on the rendered appearance, an area "between
two shapes" fills correctly whenever those shapes' outlines enclose
it — and leaks out (ordinary paint-bucket behaviour) when they don't.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen

from .canvas import PathItem

#: Per-channel tolerance: pixels this close to the clicked colour flood.
DEFAULT_TOLERANCE = 40


def render_scene_image(scene) -> QImage:
    """The scene (raster + vectors, no grid/selection) as an ARGB image."""
    scene.clearSelection()
    rect = scene.sceneRect()
    image = QImage(int(rect.width()), int(rect.height()),
                   QImage.Format_ARGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    scene.render(painter, target=QRectF(image.rect()), source=rect)
    painter.end()
    return image


def _image_bytes(image: QImage) -> bytes:
    return bytes(image.constBits())[:image.sizeInBytes()]


def flood_runs(image: QImage, sx: int, sy: int, tolerance: int):
    """Scanline flood from (sx, sy). Returns (runs, touched_edge) where
    *runs* is a list of (y, x_left, x_right) inclusive spans."""
    w, h = image.width(), image.height()
    data = _image_bytes(image)
    bpl = image.bytesPerLine()

    base = sy * bpl + sx * 4
    tb, tg, tr = data[base], data[base + 1], data[base + 2]

    def match(x, y):
        i = y * bpl + x * 4
        return (abs(data[i] - tb) <= tolerance
                and abs(data[i + 1] - tg) <= tolerance
                and abs(data[i + 2] - tr) <= tolerance)

    visited = bytearray(w * h)
    runs = []
    touched_edge = False
    stack = [(sx, sy)]
    while stack:
        x, y = stack.pop()
        row = y * w
        if visited[row + x] or not match(x, y):
            continue
        xl = x
        while xl > 0 and not visited[row + xl - 1] and match(xl - 1, y):
            xl -= 1
        xr = x
        while xr < w - 1 and not visited[row + xr + 1] and match(xr + 1, y):
            xr += 1
        for xx in range(xl, xr + 1):
            visited[row + xx] = 1
        runs.append((y, xl, xr))
        if xl == 0 or xr == w - 1 or y == 0 or y == h - 1:
            touched_edge = True
        for xx in range(xl, xr + 1):
            if y > 0 and not visited[row - w + xx] and match(xx, y - 1):
                stack.append((xx, y - 1))
            if y < h - 1 and not visited[row + w + xx] and match(xx, y + 1):
                stack.append((xx, y + 1))
    return runs, touched_edge


def _runs_to_path(runs) -> QPainterPath:
    path = QPainterPath()
    for y, xl, xr in runs:
        path.addRect(xl, y, xr - xl + 1, 1)
    return path.simplified()


def _apply_raster(scene, runs, color: QColor):
    pixmap = scene.raster_item.pixmap()
    painter = QPainter(pixmap)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(color))
    for y, xl, xr in runs:
        painter.drawRect(xl, y, xr - xl + 1, 1)
    painter.end()
    scene.raster_item.setPixmap(pixmap)


def _apply_vector(scene, runs, color: QColor) -> PathItem:
    item = PathItem(_runs_to_path(runs))
    item.setBrush(QBrush(color))
    item.setPen(QPen(Qt.NoPen))
    zs = [i.zValue() for i in scene.vector_items()]
    item.setZValue(min(zs) - 1 if zs else 0)   # behind the bounding shapes
    scene.addItem(item)
    return item


def bucket_fill(scene, scene_pos, color, vector=False,
                tolerance=DEFAULT_TOLERANCE):
    """Flood-fill the region at *scene_pos*. Returns the created
    PathItem (vector mode), or None (raster mode / nothing filled)."""
    image = render_scene_image(scene)
    x, y = int(scene_pos.x()), int(scene_pos.y())
    if not (0 <= x < image.width() and 0 <= y < image.height()):
        return None
    runs, _ = flood_runs(image, x, y, tolerance)
    if not runs:
        return None
    color = QColor(color)
    if vector:
        item = _apply_vector(scene, runs, color)
    else:
        _apply_raster(scene, runs, color)
        item = None
    scene.changed_by_user.emit()
    return item
