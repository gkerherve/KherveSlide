"""Write a drawing to disk for the document: editable SVG (source of
truth), vector PDF cropped to the content (what LaTeX includes) and a PNG
preview (what the visual editor shows)."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import (QColor, QImage, QPageLayout, QPageSize, QPainter,
                           QPdfWriter, QPixmap)

from . import svgio
from .canvas import PaintScene

#: Breathing room (scene px) around the content in the PDF / PNG.
MARGIN = 6.0
#: PNG preview supersampling, so the thumbnail stays sharp when zoomed.
PNG_SCALE = 2.0


def raster_is_blank(scene: PaintScene) -> bool:
    """True when nobody painted on the raster layer (it is plain white),
    so exports can drop it and stay pure vector."""
    pm = scene.raster_item.pixmap()
    if pm.isNull():
        return True
    img = pm.toImage().convertToFormat(QImage.Format_RGB32)
    white = QImage(img.size(), QImage.Format_RGB32)
    white.fill(Qt.white)
    return img == white


def content_rect(scene: PaintScene) -> QRectF:
    """Tight bounding box of what is drawn (vector items, plus the page if
    the raster layer carries paint)."""
    rect = QRectF()
    for item in scene.vector_items():
        if item.isVisible():
            rect = rect.united(item.sceneBoundingRect())
    if not raster_is_blank(scene):
        rect = rect.united(scene.sceneRect())
    return rect


@contextmanager
def _export_state(scene: PaintScene):
    """Hide editing chrome (selection, handles, blank raster) while
    rendering, then restore it."""
    selected = list(scene.selectedItems())
    scene.clearSelection()
    scene.clear_handles()
    blank = raster_is_blank(scene)
    if blank:
        scene.raster_item.setVisible(False)
    was_grid = scene.show_grid
    try:
        yield
    finally:
        scene.raster_item.setVisible(True)
        scene.show_grid = was_grid
        for it in selected:
            if it.scene() is scene:
                it.setSelected(True)


def save_svg(scene: PaintScene, path: Path) -> None:
    """Editable SVG. A blank raster layer is left out so the file stays
    small and purely vector."""
    pm = scene.raster_item.pixmap()
    blank = raster_is_blank(scene)
    if blank:
        scene.raster_item.setPixmap(QPixmap())
    try:
        svgio.save_svg(scene, str(path))
    finally:
        if blank:
            scene.raster_item.setPixmap(pm)


def load_svg(scene: PaintScene, path: Path) -> None:
    svgio.load_svg(scene, str(path))


def save_pdf(scene: PaintScene, path: Path, rect: QRectF) -> None:
    dpi = getattr(scene, "dpi", 96) or 96
    writer = QPdfWriter(str(path))
    writer.setResolution(int(round(dpi)))
    writer.setCreator("kherveDOC")
    size_pt = QSizeF(rect.width() * 72 / dpi, rect.height() * 72 / dpi)
    writer.setPageLayout(QPageLayout(QPageSize(size_pt, QPageSize.Point),
                                     QPageLayout.Portrait,
                                     QMarginsF(0, 0, 0, 0)))
    with _export_state(scene):
        painter = QPainter(writer)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        scene.render(painter,
                     QRectF(0, 0, writer.width(), writer.height()), rect,
                     Qt.IgnoreAspectRatio)
        painter.end()


def save_png(scene: PaintScene, path: Path, rect: QRectF,
             scale: float = PNG_SCALE) -> bool:
    img = QImage(max(1, int(round(rect.width() * scale))),
                 max(1, int(round(rect.height() * scale))),
                 QImage.Format_ARGB32)
    img.fill(QColor("white"))
    with _export_state(scene):
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        scene.render(painter, QRectF(img.rect()), rect, Qt.IgnoreAspectRatio)
        painter.end()
    return img.save(str(path), "PNG")


def save_drawing(scene: PaintScene, png_path: Path) -> bool:
    """Write <stem>.svg, <stem>.pdf and <stem>.png next to each other.
    Returns False when there is nothing to save."""
    png_path = Path(png_path)
    rect = content_rect(scene)
    if rect.isEmpty():
        return False
    rect = rect.adjusted(-MARGIN, -MARGIN, MARGIN, MARGIN)
    save_svg(scene, png_path.with_suffix(".svg"))
    save_pdf(scene, png_path.with_suffix(".pdf"), rect)
    return save_png(scene, png_path.with_suffix(".png"), rect)
