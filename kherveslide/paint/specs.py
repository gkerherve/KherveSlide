"""Shape-spec dict -> canvas item, used by the symbol libraries.

Ported from KhervePaint's ai_assistant (the drawing half only).
"""

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF

from .canvas import (ARC_KINDS, POLYGON_KINDS, ArcShapeItem, ArrowItem,
                     EllipseItem, LineItem, PolygonItem, RectItem,
                     RoundedRectItem, TextItem, center_origin)

_ALIASES = {"rectangle": "rect", "rounded_rectangle": "rounded_rect",
            "block_arrow": "arrow_right", "half_circle": "halfcircle",
            "quarter_circle": "quartercircle"}


def _pen(spec):
    color = spec.get("stroke", "#1a1a1a")
    if not color or str(color).lower() == "none":
        return QPen(Qt.NoPen)
    pen = QPen(QColor(color), float(spec.get("width", 2)))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _brush(spec):
    fill = spec.get("fill")
    grad = spec.get("gradient")
    if grad is None and isinstance(fill, dict):
        grad = fill
    if isinstance(grad, dict):
        from . import gradient
        return gradient.brush_from_spec(grad)
    if not fill or str(fill).lower() == "none":
        return QBrush(Qt.NoBrush)
    return QBrush(QColor(fill))


def _spec_to_item(spec):
    shape = str(spec.get("shape", "")).lower().replace("-", "_")
    shape = _ALIASES.get(shape, shape)
    x = float(spec.get("x", 0))
    y = float(spec.get("y", 0))
    w = float(spec.get("w", spec.get("width_px", 80)))
    h = float(spec.get("h", spec.get("height_px", 60)))
    rect = QRectF(x, y, w, h)

    if shape in ("line", "arrow"):
        line = QLineF(float(spec.get("x1", x)), float(spec.get("y1", y)),
                      float(spec.get("x2", x + w)), float(spec.get("y2", y)))
        item = ArrowItem(line) if shape == "arrow" else LineItem(line)
        item.setPen(_pen(spec))
    elif shape == "text":
        item = TextItem(str(spec.get("text", "Text")))
        item.setDefaultTextColor(QColor(spec.get("color",
                                                 spec.get("stroke", "#1a1a1a"))))
        font = QFont()
        font.setPointSizeF(max(1.0, float(spec.get("size", 14))))
        item.setFont(font)
        if str(spec.get("anchor", "")).lower() == "center":
            br = item.boundingRect()
            item.setPos(x - br.width() / 2.0, y - br.height() / 2.0)
        else:
            item.setPos(x, y)
        center_origin(item)
        if spec.get("rotation"):
            item.setRotation(float(spec["rotation"]))
        return item
    elif shape in ("rect", "circle", "ellipse"):
        item = RectItem(rect) if shape == "rect" else EllipseItem(rect)
        item.setPen(_pen(spec))
        item.setBrush(_brush(spec))
    elif shape == "rounded_rect":
        item = RoundedRectItem(rect, float(spec.get("radius", 12)))
        item.setPen(_pen(spec))
        item.setBrush(_brush(spec))
    elif shape in ARC_KINDS:
        item = ArcShapeItem(rect, kind=shape)
        item.setPen(_pen(spec))
        item.setBrush(_brush(spec))
    elif shape == "polygon" and spec.get("points"):
        poly = QPolygonF([QPointF(float(px), float(py))
                          for px, py in spec["points"]])
        item = PolygonItem(poly)
        item.setPen(_pen(spec))
        item.setBrush(_brush(spec))
    elif shape in POLYGON_KINDS:
        item = PolygonItem(kind=shape)
        item.set_rect(rect)
        item.setPen(_pen(spec))
        item.setBrush(_brush(spec))
    else:
        return None

    label = spec.get("label")
    if label and hasattr(item, "set_label"):
        item.set_label(str(label))
    center_origin(item)
    if spec.get("rotation"):
        item.setRotation(float(spec["rotation"]))
    if spec.get("opacity") is not None:
        item.setOpacity(max(0.0, min(1.0, float(spec["opacity"]))))
    return item
