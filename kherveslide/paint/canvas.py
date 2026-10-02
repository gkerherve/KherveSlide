"""Canvas: raster layer + vector items in one QGraphicsScene.

The raster layer is a QGraphicsPixmapItem pinned at z=-10 — "Open
PNG" loads into it and the pencil tool paints into its pixmap.
Vector tools (line, rect, circle, ellipse, text) create snap-aware
QGraphicsItem subclasses on top, edited with the pointer tool.
The grid is drawn in the view's foreground so it never ends up in
exported PNGs.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import math

from PySide6.QtCore import QLineF, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath,
                         QPainterPathStroker, QPen, QPixmap, QPolygonF,
                         QTextCursor, QTransform)
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem,
                             QGraphicsItemGroup, QGraphicsLineItem,
                             QGraphicsPathItem, QGraphicsPixmapItem,
                             QGraphicsPolygonItem, QGraphicsRectItem,
                             QGraphicsScene, QGraphicsTextItem,
                             QGraphicsView, QStyle, QWidget)

from . import chemistry

# Tool identifiers.
POINTER, PENCIL, LINE, RECT, CIRCLE, ELLIPSE, TEXT = (
    "pointer", "pencil", "line", "rect", "circle", "ellipse", "text")
BUCKET = "bucket"
ERASER, PICKER = "eraser", "picker"
PROTRACTOR = "protractor"     # three-click angle measurement
ROOM = "room"                 # drag-to-size room (the empty space / walls)
ARROW, ROUNDRECT = "arrow", "roundrect"
DIMENSION = "dimension"
HALFCIRCLE, QUARTERCIRCLE = "halfcircle", "quartercircle"
TRIANGLE, DIAMOND, PENTAGON, HEXAGON, STAR = (
    "triangle", "diamond", "pentagon", "hexagon", "star")
RIGHT_TRIANGLE, PARALLELOGRAM, TRAPEZOID = (
    "right_triangle", "parallelogram", "trapezoid")
HEPTAGON, OCTAGON, STAR6 = "heptagon", "octagon", "star6"
PLUS, CHEVRON, ARROW_RIGHT, LIGHTNING, HOUSE = (
    "plus", "chevron", "arrow_right", "lightning", "house")
# Chemistry tools.
CHEM_SINGLE, CHEM_DOUBLE, CHEM_TRIPLE, CHEM_WEDGE, CHEM_HASH = (
    "chem_single", "chem_double", "chem_triple", "chem_wedge", "chem_hash")
CHEM_HBOND = "chem_hbond"
CHEM_CHAIN = "chem_chain"
CHEM_BENZENE, CHEM_CYCLOHEXANE, CHEM_CYCLOPENTANE = (
    "chem_benzene", "chem_cyclohexane", "chem_cyclopentane")
CHEM_ATOM = "chem_atom"
_CHEM_BOND_TOOLS = (CHEM_SINGLE, CHEM_DOUBLE, CHEM_TRIPLE, CHEM_WEDGE,
                    CHEM_HASH, CHEM_HBOND)
_CHEM_RING_TOOLS = (CHEM_BENZENE, CHEM_CYCLOHEXANE, CHEM_CYCLOPENTANE)
_CHEM_PLACE_TOOLS = _CHEM_RING_TOOLS + (CHEM_ATOM,)   # placed on a click
_CHEM_TOOLS = _CHEM_BOND_TOOLS + _CHEM_PLACE_TOOLS + (CHEM_CHAIN,)
#: Room-layout / electrical / science element placement tools.
PLAN_PLACE = "plan_place"
ELEC_PLACE = "elec_place"
OPTICS_PLACE = "optics_place"
VACUUM_PLACE = "vacuum_place"
LABWARE_PLACE = "labware_place"
FLOW_PLACE = "flow_place"
NET_PLACE = "net_place"
PID_PLACE = "pid_place"
ARROW_PLACE = "arrow_place"
BIO_PLACE = "bio_place"
MATH_PLACE = "math_place"
MOL_PLACE = "mol_place"
S3D_PLACE = "s3d_place"
SOLID_PLACE = "solid_place"
#: All spec-library placement tools (drop a symbol on click).
_PLACE_TOOLS = (PLAN_PLACE, ELEC_PLACE, OPTICS_PLACE, VACUUM_PLACE,
                LABWARE_PLACE, FLOW_PLACE, NET_PLACE, PID_PLACE,
                ARROW_PLACE, BIO_PLACE, MATH_PLACE, MOL_PLACE, S3D_PLACE,
                SOLID_PLACE)

#: Parametric polygons created by dragging a bounding rect — all of
#: these are vertex polygons, so they explode into their edge lines.
POLYGON_KINDS = (TRIANGLE, RIGHT_TRIANGLE, DIAMOND, PARALLELOGRAM,
                 TRAPEZOID, PENTAGON, HEXAGON, HEPTAGON, OCTAGON, STAR,
                 STAR6, PLUS, CHEVRON, ARROW_RIGHT, LIGHTNING, HOUSE)

#: Custom polygons given as fractional (x, y) vertices within the rect.
_POLY_FRACTIONS = {
    TRIANGLE: [(0.5, 0), (1, 1), (0, 1)],
    RIGHT_TRIANGLE: [(0, 0), (0, 1), (1, 1)],
    DIAMOND: [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)],
    PARALLELOGRAM: [(0.25, 0), (1, 0), (0.75, 1), (0, 1)],
    TRAPEZOID: [(0.25, 0), (0.75, 0), (1, 1), (0, 1)],
    PLUS: [(0.34, 0), (0.66, 0), (0.66, 0.34), (1, 0.34), (1, 0.66),
           (0.66, 0.66), (0.66, 1), (0.34, 1), (0.34, 0.66), (0, 0.66),
           (0, 0.34), (0.34, 0.34)],
    CHEVRON: [(0, 0), (0.6, 0), (1, 0.5), (0.6, 1), (0, 1), (0.4, 0.5)],
    ARROW_RIGHT: [(0, 0.3), (0.6, 0.3), (0.6, 0), (1, 0.5), (0.6, 1),
                  (0.6, 0.7), (0, 0.7)],
    LIGHTNING: [(0.6, 0), (0, 0.6), (0.35, 0.6), (0.15, 1), (1, 0.35),
                (0.55, 0.35), (0.75, 0)],
    HOUSE: [(0.5, 0), (1, 0.45), (1, 1), (0, 1), (0, 0.45)],
}
#: Regular polygons by number of sides.
_POLY_SIDES = {PENTAGON: 5, HEXAGON: 6, HEPTAGON: 7, OCTAGON: 8}
#: Parametric arc shapes created by dragging a bounding rect.
ARC_KINDS = (HALFCIRCLE, QUARTERCIRCLE)
#: Tools defined by two points (drag start -> end).
_TWO_POINT_TOOLS = (LINE, ARROW, DIMENSION)
#: Tools defined by a dragged bounding rect.
_RECT_TOOLS = (RECT, ROOM, CIRCLE, ELLIPSE, ROUNDRECT) + POLYGON_KINDS \
    + ARC_KINDS
#: Tools that rubber-band a new vector item between press and release.
_SHAPE_TOOLS = _TWO_POINT_TOOLS + _RECT_TOOLS

#: Qt picks the platform sans-serif when the family is missing; naming one
#: keeps documents consistent across machines that do have it.
DEFAULT_FONT_FAMILY = "Helvetica"

_ITEM_FLAGS = (QGraphicsItem.ItemIsSelectable
               | QGraphicsItem.ItemIsMovable
               | QGraphicsItem.ItemSendsGeometryChanges)


class NoSelMixin:
    """Suppress Qt's built-in dashed selection rectangle. Selection is
    shown by our own handles, and the default dashes were lingering on
    screen after deselect (especially for grouped items)."""

    def paint(self, painter, option, widget=None):
        option.state = option.state & ~QStyle.State_Selected
        super().paint(painter, option, widget)


class SnapMixin:
    """Snaps the item's position to the scene grid while it is moved."""

    def itemChange(self, change, value):
        if (change == QGraphicsItem.ItemPositionChange
                and self.scene() is not None
                and getattr(self.scene(), "snap_enabled", False)):
            value = self.scene().snap(value)
        return super().itemChange(change, value)


def center_origin(item):
    """Make the item rotate/scale about its own centre rather than the
    scene origin (otherwise a shape whose geometry sits far from (0,0)
    swings off-screen when rotated)."""
    item.setTransformOriginPoint(item.boundingRect().center())


def _tilts_in_range(tilts, cells):
    """Keep only the cell tilts that fall inside the *cells* supercell (and
    actually rotate something); None when there is no supercell at all."""
    if not tilts or not cells:
        return None
    kept = {}
    for key, angles in tilts.items():
        try:
            i, j, k = (int(v) for v in str(key).split(","))
        except ValueError:
            continue
        if any(angles) and 0 <= i < cells[0] and 0 <= j < cells[1] \
                and 0 <= k < cells[2]:
            kept[key] = angles
    return kept or None


class LabelMixin:
    """An optional text label drawn centred inside a shape. Defaults
    live at class level (immutable), so an unlabelled shape carries no
    per-instance state until set_label() is called."""

    _label = ""
    _label_family = DEFAULT_FONT_FAMILY
    _label_size = 14
    _label_bold = False
    _label_italic = False
    _label_color_name = "#1a1a1a"

    def label(self) -> str:
        return self._label

    def set_label(self, text: str):
        self._label = text or ""
        self.update()

    def label_font(self) -> QFont:
        font = QFont(self._label_family, self._label_size)
        font.setBold(self._label_bold)
        font.setItalic(self._label_italic)
        return font

    def set_label_font(self, font: QFont):
        self._label_family = font.family()
        self._label_size = font.pointSize()
        self._label_bold = font.bold()
        self._label_italic = font.italic()
        self.update()

    def label_color(self) -> QColor:
        return QColor(self._label_color_name)

    def set_label_color(self, color):
        self._label_color_name = QColor(color).name()
        self.update()

    def _paint_label(self, painter):
        if not self._label:
            return
        painter.save()
        painter.setFont(self.label_font())
        painter.setPen(self.label_color())
        painter.drawText(self.boundingRect(),
                         Qt.AlignCenter | Qt.TextWordWrap, self._label)
        painter.restore()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        self._paint_label(painter)


#: Minimum comfortable width of a click target, in scene px.
_PICK_WIDTH = 8.0


def _stroke_only_shape(path: QPainterPath, pen: QPen,
                       pick: bool = False) -> QPainterPath:
    """Hit area of *path* drawn as a stroke: just the pen's ribbon, NOT
    the path's implicit fill region. Qt's default shape() unions in the
    fill area even for an unfilled item, so a big unfilled curve or arc
    silently swallowed every click 'inside' it — stealing selection from
    whatever actually shows there (e.g. a bucket-fill path stacked
    behind it). With *pick* the ribbon is fattened to a comfortable
    click width — use that ONLY where boundingRect() does not derive
    from shape() (Qt's rect/ellipse/path items compute boundingRect
    from shape() when the pen is wide, so a fat ribbon there would
    silently inflate geometry, group bounds and exports)."""
    stroker = QPainterPathStroker()
    width = max(pen.widthF(), 1e-6)
    if pick:
        width = max(width, _PICK_WIDTH)
    stroker.setWidth(width)
    stroker.setCapStyle(pen.capStyle())
    stroker.setJoinStyle(pen.joinStyle())
    stroker.setMiterLimit(pen.miterLimit())
    return stroker.createStroke(path)


class LineItem(NoSelMixin, SnapMixin, QGraphicsLineItem):
    """A straight segment, optionally **bent** into a quadratic curve:
    the bend is a control point in item coordinates (None = straight),
    dragged via the round mid-handle when the line is selected."""

    def __init__(self, *a):
        super().__init__(*a)
        self.setFlags(_ITEM_FLAGS)
        self._bend = None               # QPointF control point, or None

    def bend(self):
        return QPointF(self._bend) if self._bend is not None else None

    def set_bend(self, point):
        self.prepareGeometryChange()
        self._bend = QPointF(point) if point is not None else None
        self.update()

    def curve_path(self) -> QPainterPath:
        """The drawn geometry: a straight segment, or the quadratic
        curve through the bend control point."""
        ln = self.line()
        path = QPainterPath(ln.p1())
        if self._bend is not None:
            path.quadTo(self._bend, ln.p2())
        else:
            path.lineTo(ln.p2())
        return path

    def end_angle(self) -> float:
        """Direction (radians) the line arrives at p2 — the curve's end
        tangent when bent, so arrowheads follow the curve."""
        ln = self.line()
        if self._bend is not None:
            v = ln.p2() - self._bend
            if abs(v.x()) > 1e-9 or abs(v.y()) > 1e-9:
                return math.atan2(v.y(), v.x())
        return math.atan2(ln.dy(), ln.dx())

    def boundingRect(self):
        # Independent of shape(): the fat pick ribbon below must not
        # inflate the geometry.
        w = self.pen().widthF() / 2 + 1
        return self.curve_path().boundingRect().adjusted(-w, -w, w, w)

    def shape(self):
        # A comfortable click target even for a hairline stroke.
        return _stroke_only_shape(self.curve_path(), self.pen(), pick=True)

    def paint(self, painter, option, widget=None):
        if self._bend is None:
            super().paint(painter, option, widget)
            return
        option.state = option.state & ~QStyle.State_Selected
        painter.setPen(self.pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.curve_path())


class OutlinePickMixin:
    """Unfilled (and unlabelled) shapes are picked by their outline
    only, like in other vector editors: Qt's default shape() would let
    an empty rectangle/ellipse/curve swallow every click inside it,
    stealing selection from whatever is actually visible there — most
    painfully a bucket-fill path stacked behind the shapes that bound
    it. A filled or labelled shape keeps its clickable interior.

    Because Qt's rect/ellipse/polygon/path items derive boundingRect()
    from shape() when the pen is wide, the fattened pick ribbon must
    NOT leak into geometry: boundingRect() is overridden to the
    exact-pen-width value Qt would have computed (cached — it is called
    on every repaint)."""

    _pick_cache = None          # (fingerprint, QRectF)

    def _outline_pick(self) -> QPainterPath:
        raise NotImplementedError

    def _hollow(self) -> bool:
        return (self.brush().style() == Qt.NoBrush
                and not getattr(self, "_label", ""))

    def shape(self):
        if self._hollow():
            return _stroke_only_shape(self._outline_pick(), self.pen(),
                                      pick=True)
        return super().shape()

    def boundingRect(self):
        if not self._hollow():
            return super().boundingRect()
        path = self._outline_pick()
        key = (self.pen().widthF(), path.elementCount(),
               path.controlPointRect().getRect())
        if self._pick_cache is None or self._pick_cache[0] != key:
            rect = _stroke_only_shape(path, self.pen()).controlPointRect()
            self._pick_cache = (key, rect)
        return QRectF(self._pick_cache[1])


class RectItem(NoSelMixin, LabelMixin, OutlinePickMixin, SnapMixin,
               QGraphicsRectItem):
    def __init__(self, *a):
        super().__init__(*a)
        self.setFlags(_ITEM_FLAGS)

    def _outline_pick(self):
        path = QPainterPath()
        path.addRect(self.rect())
        return path


class EllipseItem(NoSelMixin, LabelMixin, OutlinePickMixin, SnapMixin,
                  QGraphicsEllipseItem):
    def __init__(self, *a):
        super().__init__(*a)
        self.setFlags(_ITEM_FLAGS)

    def _outline_pick(self):
        path = QPainterPath()
        path.addEllipse(self.rect())
        return path


#: Arrowhead styles: filled triangle, open "V", slim stealth, filled at
#: both ends.
ARROW_HEADS = ("filled", "open", "stealth", "double")


class ArrowItem(LineItem):
    """A line with an arrowhead at the second endpoint (and, for the
    "double" style, at the first one too)."""

    HEAD = 14

    def __init__(self, *a):
        super().__init__(*a)
        self.head = "filled"

    def set_head(self, head: str):
        self.head = head if head in ARROW_HEADS else "filled"
        self.update()

    def boundingRect(self):
        h = self.HEAD + self.pen().widthF()
        return super().boundingRect().adjusted(-h, -h, h, h)

    def start_angle(self) -> float:
        """Direction the line leaves p1, pointing backwards (for a tail
        head)."""
        ln = self.line()
        ref = self._bend if self._bend is not None else ln.p2()
        v = ln.p1() - ref
        return math.atan2(v.y(), v.x())

    def _head_polygon(self, tip=None, angle=None) -> QPolygonF:
        if tip is None:
            tip, angle = self.line().p2(), self.end_angle()
        size = self.HEAD + max(0.0, self.pen().widthF() - 2) * 1.5
        spread = math.pi / 7 if self.head != "stealth" else math.pi / 10
        left = tip - QPointF(math.cos(angle - spread) * size,
                             math.sin(angle - spread) * size)
        right = tip - QPointF(math.cos(angle + spread) * size,
                              math.sin(angle + spread) * size)
        if self.head == "stealth":
            notch = tip - QPointF(math.cos(angle) * size * 0.65,
                                  math.sin(angle) * size * 0.65)
            return QPolygonF([tip, left, notch, right])
        return QPolygonF([tip, left, right])

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.line().length() < 1:
            return
        pen = QPen(self.pen().color(), self.pen().widthF())
        pen.setJoinStyle(Qt.MiterJoin if self.head != "open"
                         else Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        heads = [self._head_polygon()]
        if self.head == "double":
            heads.append(self._head_polygon(self.line().p1(),
                                            self.start_angle()))
        for poly in heads:
            if self.head == "open":
                painter.setBrush(Qt.NoBrush)
                painter.drawPolyline(QPolygonF([poly[1], poly[0], poly[2]]))
            else:
                painter.setBrush(QBrush(self.pen().color()))
                painter.drawPolygon(poly)


#: Conversion from millimetres to each supported display unit.
_UNIT_PER_MM = {"mm": 1.0, "cm": 0.1, "in": 1.0 / 25.4}
#: Selectable end-cap styles for a dimension line.
DIM_CAPS = ("arrows", "ticks", "dots", "none")


class DimensionItem(LineItem):
    """A measured line with configurable style: end caps (arrows / ticks /
    dots / none), optional perpendicular extension lines, a solid or
    dashed line, and a length label whose unit, decimals and prefix/suffix
    are all adjustable (length derived from the scene dpi). Edited like a
    line via its endpoints; the label updates live as the endpoints move."""

    HEAD = 10
    TICK = 7               # half-length of a tick slash
    DOT_R = 4              # dot-cap radius
    EXT = 14              # half-length of an extension (witness) line
    _LABEL_PAD = 60        # boundingRect slack for caps + label text

    # Style defaults live at class level (immutable), so an unstyled
    # dimension carries no per-instance state until something is set.
    cap_style = "arrows"   # one of DIM_CAPS
    extension = False      # draw perpendicular witness lines at the ends
    dash = False           # dashed dimension + extension lines
    unit = "mm"            # mm | cm | in
    decimals = 1
    prefix = ""
    suffix = ""

    def boundingRect(self):
        extra = self.HEAD + self.pen().widthF() + self._LABEL_PAD
        return super().boundingRect().adjusted(-extra, -extra, extra, extra)

    def length_mm(self) -> float:
        scene = self.scene()
        dpi = getattr(scene, "dpi", 96) if scene is not None else 96
        return self.line().length() / max(dpi, 1) * 25.4

    def length_in_unit(self) -> float:
        return self.length_mm() * _UNIT_PER_MM.get(self.unit, 1.0)

    def _label_text(self) -> str:
        value = f"{self.length_in_unit():.{self.decimals}f}"
        return f"{self.prefix}{value} {self.unit}{self.suffix}"

    def _line_pen(self) -> QPen:
        pen = QPen(self.pen())
        pen.setStyle(Qt.DashLine if self.dash else Qt.SolidLine)
        return pen

    def _head(self, tip: QPointF, other: QPointF) -> QPolygonF:
        angle = math.atan2(tip.y() - other.y(), tip.x() - other.x())
        left = tip - QPointF(math.cos(angle - math.pi / 7) * self.HEAD,
                             math.sin(angle - math.pi / 7) * self.HEAD)
        right = tip - QPointF(math.cos(angle + math.pi / 7) * self.HEAD,
                              math.sin(angle + math.pi / 7) * self.HEAD)
        return QPolygonF([tip, left, right])

    def _draw_caps(self, painter, ln, angle, color):
        width = self.pen().widthF()
        if self.cap_style == "arrows":
            painter.setPen(QPen(color, width))
            painter.setBrush(QBrush(color))
            painter.drawPolygon(self._head(ln.p2(), ln.p1()))
            painter.drawPolygon(self._head(ln.p1(), ln.p2()))
        elif self.cap_style == "ticks":
            painter.setPen(QPen(color, max(width, 1)))
            d = QPointF(math.cos(angle + math.pi / 4),
                        math.sin(angle + math.pi / 4)) * self.TICK
            for p in (ln.p1(), ln.p2()):
                painter.drawLine(p - d, p + d)
        elif self.cap_style == "dots":
            painter.setPen(QPen(color, width))
            painter.setBrush(QBrush(color))
            for p in (ln.p1(), ln.p2()):
                painter.drawEllipse(p, self.DOT_R, self.DOT_R)

    def paint(self, painter, option, widget=None):
        ln = self.line()
        if ln.length() < 1:
            return
        color = self.pen().color()
        angle = math.atan2(ln.dy(), ln.dx())
        perp = QPointF(math.sin(angle), -math.cos(angle))

        painter.setBrush(Qt.NoBrush)
        painter.setPen(self._line_pen())
        painter.drawLine(ln)                           # the measured line
        if self.extension:
            for p in (ln.p1(), ln.p2()):
                painter.drawLine(p - perp * self.EXT, p + perp * self.EXT)
        self._draw_caps(painter, ln, angle, color)

        # length label, offset just off the line at its midpoint
        mid = QPointF((ln.x1() + ln.x2()) / 2, (ln.y1() + ln.y2()) / 2)
        tp = mid + perp * 14
        painter.save()
        painter.setFont(QFont(DEFAULT_FONT_FAMILY, 10))
        painter.setPen(QPen(color))
        painter.setBrush(Qt.NoBrush)
        text = self._label_text()
        fm = painter.fontMetrics()
        painter.drawText(
            QPointF(tp.x() - fm.horizontalAdvance(text) / 2,
                    tp.y() + fm.ascent() / 2 - 1), text)
        painter.restore()


def polygon_for_kind(kind: str, rect: QRectF) -> QPolygonF:
    """Vertices of a parametric polygon *kind* inscribed in *rect*."""
    left, top = rect.left(), rect.top()
    w, h = rect.width(), rect.height()
    cx, cy = rect.center().x(), rect.center().y()
    rx, ry = w / 2, h / 2

    if kind in _POLY_FRACTIONS:
        pts = [(left + fx * w, top + fy * h)
               for fx, fy in _POLY_FRACTIONS[kind]]
    elif kind in (STAR, STAR6):
        points = 5 if kind == STAR else 6
        pts = []
        for i in range(points * 2):
            ang = -math.pi / 2 + i * math.pi / points
            scale = 1.0 if i % 2 == 0 else 0.4
            pts.append((cx + rx * scale * math.cos(ang),
                        cy + ry * scale * math.sin(ang)))
    else:                                   # regular polygon
        sides = _POLY_SIDES.get(kind, 6)
        pts = []
        for i in range(sides):
            ang = -math.pi / 2 + i * 2 * math.pi / sides
            pts.append((cx + rx * math.cos(ang), cy + ry * math.sin(ang)))
    return QPolygonF([QPointF(x, y) for x, y in pts])


class PolygonItem(NoSelMixin, LabelMixin, OutlinePickMixin, SnapMixin,
                  QGraphicsPolygonItem):
    """Free or parametric polygon. *kind* is kept for display only;
    geometry is always the vertex list, so SVG-imported polygons and
    triangle/star/etc. behave identically."""

    def __init__(self, polygon=None, kind="polygon"):
        super().__init__(QPolygonF(polygon) if polygon else QPolygonF())
        self.setFlags(_ITEM_FLAGS)
        self.kind = kind

    def set_rect(self, rect: QRectF):
        self.setPolygon(polygon_for_kind(self.kind, rect))

    def _outline_pick(self):
        path = QPainterPath()
        path.addPolygon(self.polygon())
        path.closeSubpath()
        return path


class RoundedRectItem(NoSelMixin, LabelMixin, OutlinePickMixin, SnapMixin,
                      QGraphicsPathItem):
    """A rectangle with rounded corners (radius is a real property)."""

    def _outline_pick(self):
        return self.path()

    def __init__(self, rect=None, radius: float = 12.0):
        super().__init__()
        self.setFlags(_ITEM_FLAGS)
        self._rect = QRectF(rect) if rect else QRectF()
        self._radius = radius
        self._rebuild()

    def rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_rect(self, rect: QRectF):
        self._rect = QRectF(rect)
        self._rebuild()

    def radius(self) -> float:
        return self._radius

    def set_radius(self, radius: float):
        self._radius = radius
        self._rebuild()

    def _rebuild(self):
        path = QPainterPath()
        r = min(self._radius, self._rect.width() / 2, self._rect.height() / 2)
        path.addRoundedRect(self._rect, r, r)
        self.setPath(path)


def arc_path(kind: str, rect: QRectF, flip_h=False, flip_v=False
             ) -> QPainterPath:
    """A half- or quarter-disc filling *rect* (with optional flips)."""
    r = QRectF(rect)
    path = QPainterPath()
    if r.width() <= 0 or r.height() <= 0:
        return path
    if kind == HALFCIRCLE:
        # flat side on the bottom edge, arc bulging up over the top
        ell = QRectF(r.left(), r.top(), r.width(), r.height() * 2)
        path.arcMoveTo(ell, 0)
        path.arcTo(ell, 0, 180)
        path.closeSubpath()
    else:                                  # quarter: corner at bottom-left
        ell = QRectF(r.left() - r.width(), r.top(),
                     r.width() * 2, r.height() * 2)
        path.moveTo(r.left(), r.bottom())
        path.arcTo(ell, 0, 90)
        path.closeSubpath()
    if flip_h or flip_v:
        c = r.center()
        t = QTransform()
        t.translate(c.x(), c.y())
        t.scale(-1 if flip_h else 1, -1 if flip_v else 1)
        t.translate(-c.x(), -c.y())
        path = t.map(path)
    return path


class ArcShapeItem(NoSelMixin, LabelMixin, OutlinePickMixin, SnapMixin,
                   QGraphicsPathItem):
    """Half- or quarter-circle, parametric on a bounding rect plus
    horizontal/vertical flip flags (so it can be mirrored and still
    round-trip)."""

    def _outline_pick(self):
        return self.path()

    def __init__(self, rect=None, kind=HALFCIRCLE):
        super().__init__()
        self.setFlags(_ITEM_FLAGS)
        self._rect = QRectF(rect) if rect else QRectF()
        self.kind = kind
        self.flip_h = False
        self.flip_v = False
        self._rebuild()

    def rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_rect(self, rect: QRectF):
        self._rect = QRectF(rect)
        self._rebuild()

    def mirror(self, horizontal=True):
        if horizontal:
            self.flip_h = not self.flip_h
        else:
            self.flip_v = not self.flip_v
        self._rebuild()

    def _rebuild(self):
        self.setPath(arc_path(self.kind, self._rect, self.flip_h, self.flip_v))


class PathItem(NoSelMixin, OutlinePickMixin, SnapMixin, QGraphicsPathItem):
    """An arbitrary vector path — the import target for SVG <path> and
    for elements carrying a non-trivial (scaled/sheared) transform."""

    def __init__(self, path=None):
        super().__init__(path if path else QPainterPath())
        self.setFlags(_ITEM_FLAGS)

    def _outline_pick(self):
        return self.path()


class ImageItem(NoSelMixin, SnapMixin, QGraphicsPixmapItem):
    """A pasted/placed bitmap living on the vector layer (movable)."""

    def __init__(self, pixmap=None):
        super().__init__(pixmap if pixmap else QPixmap())
        self.setFlags(_ITEM_FLAGS)
        self.setTransformationMode(Qt.SmoothTransformation)


class GroupItem(NoSelMixin, SnapMixin, QGraphicsItemGroup):
    def __init__(self):
        super().__init__()
        self.setFlags(_ITEM_FLAGS)

    def addToGroup(self, item):
        super().addToGroup(item)
        scene = self.scene()
        if scene is not None and hasattr(scene, "_keep"):
            scene._keep(item)


class TextItem(NoSelMixin, SnapMixin, QGraphicsTextItem):
    """Vector text — double-click to edit inline."""

    def __init__(self, text: str = "Text"):
        super().__init__(text)
        self.setFlags(_ITEM_FLAGS)
        self.setFont(QFont(DEFAULT_FONT_FAMILY, 14))

    def start_editing(self):
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus(Qt.MouseFocusReason)
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        self.setTextCursor(cursor)

    def mouseDoubleClickEvent(self, event):
        self.start_editing()
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        was_editing = bool(self.textInteractionFlags())
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        super().focusOutEvent(event)
        scene = self.scene()
        if was_editing and scene is not None:
            # Typed text is only captured for undo once editing ends; an
            # emptied label is removed rather than left as an invisible item.
            if not self.toPlainText().strip():
                scene.removeItem(self)
            if hasattr(scene, "changed_by_user"):
                scene.changed_by_user.emit()


class PaintScene(QGraphicsScene):
    """One scene holding the raster layer plus all vector items."""

    changed_by_user = Signal()
    #: emitted after the colour-picker samples a colour: (hex name,
    #: "stroke" or "fill" — which colour it landed in).
    color_picked = Signal(str, str)

    def __init__(self, width: int = 800, height: int = 600, parent=None):
        super().__init__(parent)
        self._alive = set()
        self.tool = POINTER
        self.pen = QPen(QColor("#1a1a1a"), 2)
        self.pen.setCapStyle(Qt.RoundCap)
        self.pen.setJoinStyle(Qt.RoundJoin)
        self.fill_color = QColor("#4aa3ff")
        self.fill_color2 = QColor("#ffffff")  # gradient end colour
        self.fill_style = "solid"             # solid | linear | radial | sun
        self.fill_angle = 90.0                # linear gradient direction
        self.fill_enabled = False
        self.arrow_head = "filled"        # head style for new arrows
        self.text_font = QFont(DEFAULT_FONT_FAMILY, 14)
        self.erase_objects = True         # eraser removes whole vector items
        self.bucket_vector = True         # bucket output: vector by default
        # (raster paint can't be selected, moved or deleted afterwards)
        self.dim_cap = "arrows"           # end-cap style for new dimensions
        self.dim_orientation = "aligned"  # aligned | horizontal | vertical
        self.chem_atom = "C"              # label placed by the atom tool
        self.plan_element = "wall"        # room-layout element to place
        self.elec_element = "resistor"    # electrical element to place
        self.optics_element = "laser"     # optics symbol to place
        self.vacuum_element = "chamber"   # vacuum symbol to place
        self.labware_element = "beaker"   # glassware symbol to place
        self.flow_element = "process"     # flowchart node to place
        self.net_element = "server"       # network symbol to place
        self.pid_element = "tank"         # P&ID symbol to place
        self.arrow_element = "arrow_right"  # annotation arrow to place
        self.bio_element = "cell"         # biology symbol to place
        self.math_element = "axes_2d"     # math/graph symbol to place
        self.mol_element = "methane"      # molecule/crystal model to place
        self.s3d_element = "slab_grey"    # 3D-schematic block to place
        self.solid_element = "cube"       # 3D solid to place
        self.solid_color = "#5b8fd9"      # its body colour
        self.chem_fixed = True            # ChemDraw-style fixed length + angle
        self.bond_length_mm = 6.0         # predefined bond length (mm)
        self._chain_pts = None            # vertices of an in-progress chain
        self._chain_preview = None        # rubber-band segment to the cursor
        self._angle_pts = None            # clicked points of the protractor
        self._angle_preview = None        # preview arm items while measuring
        self._erase_last = None           # previous eraser point while dragging
        self._paint_image = None          # ImageItem being pixel-painted, if any
        self._orbit_item = None           # molecule being 3D-rotated in place
        self._orbit_last = None           # last drag point while orbiting
        self._orbiting = False            # an orbit drag is in progress
        self._orbit_dirty = False         # orbit changed the doc (commit once)

        # The grid is specified as a physical distance in millimetres
        # between adjacent lines; the pixel spacing is derived from the
        # canvas dpi (see grid_size). Smaller mm -> finer cells.
        self.grid_mm = 1.0
        self.snap_enabled = True
        self.show_grid = False
        self.infinite = True      # infinite paper by default (grid fills view)
        self.dpi = 96             # pixels per inch, for physical export size

        self.raster_item = QGraphicsPixmapItem()
        self.raster_item.setZValue(-10)
        self.addItem(self.raster_item)

        self._drawing = False
        self._start = QPointF()
        self._temp_item = None
        self._stroke_path = None        # freehand pencil path while drawing

        self._sel_handles = None        # SelectionHandles for active item
        self._rotate_target = None      # item currently in rotate mode
        self._crop = None               # active CropSession, if any
        self._press_positions = {}      # selected item positions at press
        self.selectionChanged.connect(self._on_selection_changed)

        self.new_document(width, height)

    # ------------------------------------------------------------ ownership
    # PySide6 can hand a Python-created item back to Python ownership when
    # its parentItem() (None) is queried, after which the item dies with
    # its last Python reference even though the scene still shows it. The
    # scene therefore keeps its own reference to everything it holds.
    def _keep(self, item):
        self._alive.add(item)
        for child in item.childItems():
            self._keep(child)

    def _release(self, item):
        self._alive.discard(item)
        for child in item.childItems():
            self._release(child)

    def addItem(self, item):
        super().addItem(item)
        self._keep(item)

    def removeItem(self, item):
        super().removeItem(item)
        self._release(item)

    def destroyItemGroup(self, group):
        self._alive.discard(group)
        super().destroyItemGroup(group)

    # ------------------------------------------------------------ document
    def new_document(self, width: int, height: int):
        """Reset to a blank white canvas of the given size."""
        for item in list(self.items()):
            if item is not self.raster_item:
                self.removeItem(item)
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.white)
        self.raster_item.setPixmap(pixmap)
        self.setSceneRect(0, 0, width, height)

    def set_raster_pixmap(self, pixmap: QPixmap):
        """Replace the raster layer (Open PNG) and resize the canvas."""
        self.raster_item.setPixmap(pixmap)
        self.setSceneRect(0, 0, pixmap.width(), pixmap.height())

    def resize_canvas(self, width: int, height: int):
        """Change the canvas size, keeping all content where it is
        (raster content is preserved at the top-left, padded white)."""
        width, height = max(1, int(width)), max(1, int(height))
        old = self.raster_item.pixmap()
        new = QPixmap(width, height)
        new.fill(Qt.white)
        painter = QPainter(new)
        painter.drawPixmap(0, 0, old)
        painter.end()
        self.raster_item.setPixmap(new)
        self.setSceneRect(0, 0, width, height)
        self.changed_by_user.emit()

    def fit_to_content(self, selection_only: bool = False, margin: int = 10):
        """Resize the canvas to the bounding box of the drawing (or the
        selection), shifting all content so it sits at *margin* from the
        top-left. Both layers move together, so nothing is lost."""
        chosen = [i for i in self.selectedItems() if i.parentItem() is None] \
            if selection_only else []
        items = chosen or self.vector_items()
        rect = QRectF()
        for item in items:
            rect = rect.united(item.sceneBoundingRect())
        if rect.isEmpty():
            return
        dx = int(round(margin - rect.left()))
        dy = int(round(margin - rect.top()))
        width = int(math.ceil(rect.width())) + 2 * margin
        height = int(math.ceil(rect.height())) + 2 * margin

        was_snap = self.snap_enabled
        self.snap_enabled = False
        for item in self.vector_items():
            item.moveBy(dx, dy)
        self.snap_enabled = was_snap

        old = self.raster_item.pixmap()
        new = QPixmap(width, height)
        new.fill(Qt.white)
        painter = QPainter(new)
        painter.drawPixmap(dx, dy, old)
        painter.end()
        self.raster_item.setPixmap(new)
        self.setSceneRect(0, 0, width, height)
        self.changed_by_user.emit()

    def vector_items(self):
        """Top-level vector items, bottom to top (excludes the raster and
        any scene-level selection handles). `items()` is top-first, so
        reverse before the (stable) z-sort — otherwise items sharing a z
        come back top-first, contradicting the documented order."""
        from .handles import Handle
        ordered = list(self.items())[::-1]            # bottom-to-top
        ordered.sort(key=lambda i: i.zValue())        # stable: honour z
        return [i for i in ordered
                if i is not self.raster_item and i.parentItem() is None
                and not isinstance(i, Handle)]

    # ------------------------------------------------------------ grid
    @property
    def grid_size(self) -> float:
        """Exact pixel spacing between grid lines, from the physical grid
        distance (mm) and the canvas dpi. Kept as a float (NOT rounded to
        whole pixels): a rounded spacing makes snapped points miss true
        millimetre positions, so a measured dimension drifts — e.g. a
        1 mm grid at 300 dpi is 11.81 px, and rounding to 12 px turned a
        10 mm line into 10.2 mm."""
        return max(1e-6, self.grid_mm / 25.4 * self.dpi)

    # ------------------------------------------------------------ snapping
    def snap(self, pos: QPointF) -> QPointF:
        # floor(x/g + 0.5) rounds half-up; round() would banker-round
        # half-grid points inconsistently.
        g = self.grid_size
        return QPointF(math.floor(pos.x() / g + 0.5) * g,
                       math.floor(pos.y() / g + 0.5) * g)

    def _tool_pos(self, pos: QPointF) -> QPointF:
        """Snap vector-tool positions; the pencil stays freehand."""
        if (self.snap_enabled
                and self.tool in _SHAPE_TOOLS + (TEXT,) + _PLACE_TOOLS
                + _CHEM_TOOLS):
            return self.snap(pos)
        return pos

    # ------------------------------------------------------------ brushes
    def current_brush(self) -> QBrush:
        if not self.fill_enabled:
            return QBrush(Qt.NoBrush)
        from . import gradient
        return gradient.brush_for(self.fill_style, self.fill_color,
                                  self.fill_color2, self.fill_angle)

    # ------------------------------------------------------------ grouping
    def group_selection(self):
        selected = {i for i in self.selectedItems()
                    if i.parentItem() is None}
        if len(selected) < 2:
            return
        # Add children in their CURRENT stacking order (bottom to top) and
        # give them sequential z, so the group keeps which item is in
        # front — selectedItems() order is arbitrary, which previously
        # let a later child cover earlier ones after grouping.
        ordered = [i for i in reversed(self.items()) if i in selected]
        group = GroupItem()
        self.addItem(group)
        # Reparenting must not snap: addToGroup repositions each child
        # into group coords, and snapping that would shift them.
        self.clear_handles()
        was_snap = self.snap_enabled
        self.snap_enabled = False
        for z, item in enumerate(ordered):
            item.setZValue(z)
            # Clear the child's own selection flag before it becomes a group
            # member — otherwise it stays 'selected' inside the group and,
            # once ungrouped, is stuck selected but unknown to the scene.
            item.setSelected(False)
            group.addToGroup(item)
        self.snap_enabled = was_snap
        self.clearSelection()
        group.setSelected(True)
        self.changed_by_user.emit()

    def ungroup_selection(self):
        self.clear_handles()
        was_snap = self.snap_enabled
        self.snap_enabled = False
        freed = []
        for item in list(self.selectedItems()):
            if isinstance(item, QGraphicsItemGroup):
                children = item.childItems()
                self.destroyItemGroup(item)
                for child in children:
                    child.setFlags(_ITEM_FLAGS)
                    freed.append(child)
        self.snap_enabled = was_snap
        self.clearSelection()
        for child in freed:
            # destroyItemGroup leaves children with a stale 'selected' flag
            # that the scene never registered; toggle it so setSelected(True)
            # is a real change the scene records (else selectedItems() stays
            # empty and re-grouping / deselecting break).
            child.setSelected(False)
            child.setSelected(True)
        self.changed_by_user.emit()

    def delete_selection(self):
        self.clear_handles()
        for item in self.selectedItems():
            self.removeItem(item)
        self.changed_by_user.emit()

    def explode_selection(self):
        """Break each selected shape's outline into its individual edge
        segments (straight edges -> lines, curved edges -> arc paths), so
        a single piece can be deleted or edited (then the rest regrouped
        with Ctrl+G). The new segments are left selected."""
        self.clear_handles()
        new_items = []
        originals = []
        for item in self.selectedItems():
            segments = self._explode_item(item)
            if segments:
                originals.append(item)
                new_items.extend(segments)
        if not new_items:
            return
        for item in originals:
            self.removeItem(item)
        self.clearSelection()
        for seg in new_items:
            self.addItem(seg)
            seg.setSelected(True)
        self.changed_by_user.emit()

    @staticmethod
    def _outline_path(item):
        """The shape's outline as a QPainterPath in item-local coords, or
        None if the item has no breakable outline (line/text/image/group)."""
        if isinstance(item, PolygonItem):
            path = QPainterPath()
            path.addPolygon(item.polygon())
            path.closeSubpath()
            return path
        if isinstance(item, RectItem):
            path = QPainterPath()
            path.addRect(item.rect())
            return path
        if isinstance(item, EllipseItem):
            path = QPainterPath()
            path.addEllipse(item.rect())
            return path
        if isinstance(item, (RoundedRectItem, ArcShapeItem, PathItem)):
            return QPainterPath(item.path())
        return None                          # line/arrow/text/image/group

    def _explode_item(self, item):
        local = self._outline_path(item)
        if local is None or local.elementCount() < 2:
            return None
        path = item.sceneTransform().map(local)   # to scene coordinates
        pen = QPen(item.pen())
        segments = []
        cur = None
        i, n = 0, path.elementCount()
        while i < n:
            e = path.elementAt(i)
            if e.isMoveTo():
                cur = QPointF(e.x, e.y)
                i += 1
            elif e.isLineTo():
                end = QPointF(e.x, e.y)
                if cur is not None:
                    line = LineItem(QLineF(cur, end))
                    line.setPen(pen)
                    segments.append(line)
                cur = end
                i += 1
            else:                            # cubic: control1 + 2 data points
                c2 = path.elementAt(i + 1)
                ep = path.elementAt(i + 2)
                sub = QPainterPath()
                sub.moveTo(cur)
                sub.cubicTo(QPointF(e.x, e.y), QPointF(c2.x, c2.y),
                            QPointF(ep.x, ep.y))
                arc = PathItem(sub)
                arc.setPen(pen)
                arc.setBrush(QBrush(Qt.NoBrush))
                segments.append(arc)
                cur = QPointF(ep.x, ep.y)
                i += 3
        return segments

    # ------------------------------------------------------------ selection
    def _toggle_select(self, scene_pos) -> str:
        """Shift/Ctrl+click multi-select: toggle the top-level item
        under the cursor in or out of the selection. Returns "toggled",
        "pass" (a resize handle or an active text edit should get the
        click instead) or "miss" (empty canvas). We toggle on *press*
        rather than relying on Qt's Ctrl handling, which only toggles on
        release and aborts if the cursor moved at all in between — real
        clicks jitter a pixel or two, so it both missed the toggle and
        nudged the selected items (and Qt gives Shift no role at all)."""
        from .handles import Handle
        for it in self.items(scene_pos):
            if it is self.raster_item:
                continue
            if isinstance(it, Handle):
                return "pass"           # the handle drag wins
            if isinstance(it, TextItem) and it.textInteractionFlags():
                return "pass"           # let the text edit take the click
            while it.parentItem() is not None:
                it = it.parentItem()    # groups select as a whole
            if not (it.flags() & QGraphicsItem.ItemIsSelectable):
                continue                # e.g. crop overlay decoration
            it.setSelected(not it.isSelected())
            # Keep release-time move detection in sync with this press.
            self._press_positions = {i: i.pos()
                                     for i in self.selectedItems()}
            return "toggled"
        return "miss"

    # ------------------------------------------------------------ handles
    def clear_handles(self):
        if self._sel_handles is not None:
            self._sel_handles.remove()
            self._sel_handles = None

    def _on_selection_changed(self):
        # Force a repaint so vacated selection outlines never linger.
        self.update()
        # Drop handles whenever the active single selection goes away
        # (covers clearSelection() before export/fill/save, and
        # rubber-band multi-select).
        if len(self.selectedItems()) != 1:
            self.clear_handles()
            self._rotate_target = None

    def refresh_handles(self, mode=None, item=None):
        """Rebuild handles for the active item. Without *mode*, keep
        rotate mode if this item was put in it, else show resize."""
        from .handles import RESIZE, ROTATE, SelectionHandles
        sel = self.selectedItems()
        target = item if item is not None else (
            sel[0] if len(sel) == 1 else None)
        self.clear_handles()
        if target is None or self.tool != POINTER:
            self._rotate_target = None
            return
        if mode is None:
            mode = ROTATE if target is self._rotate_target else RESIZE
        self._rotate_target = target if mode == ROTATE else None
        self._sel_handles = SelectionHandles(self, target, mode)

    def enter_rotate_mode(self, item):
        from .handles import ROTATE
        center_origin(item)
        self.clearSelection()
        item.setSelected(True)
        self.refresh_handles(mode=ROTATE, item=item)

    # ------------------------------------------------------------ cropping
    def crop_active(self) -> bool:
        return self._crop is not None

    def begin_crop(self, image):
        from .crop import CropSession
        self.cancel_crop()
        self.clear_handles()
        self.clearSelection()
        self._crop = CropSession(self, image)

    def apply_crop(self):
        if self._crop is not None:
            self._crop.apply()
            self._crop = None

    def cancel_crop(self):
        if self._crop is not None:
            self._crop.cancel()
            self._crop = None

    # --------------------------------------------------------- chain tool
    def _chain_click(self, event):
        """Click-to-click connected bonds: each click drops a vertex; the
        bond runs from the previous vertex. Clicking the last vertex again
        (or any non-left button) ends the chain."""
        if event.button() != Qt.LeftButton:
            self.end_chain()
            return
        raw = event.scenePos()
        if self._chain_pts is None:
            pos = self._tool_pos(raw)
            self._chain_pts = [pos]
            self._chain_preview = LineItem(QLineF(pos, pos))
            self._chain_preview.setPen(QPen(self.pen))
            self.addItem(self._chain_preview)
            return
        last = self._chain_pts[-1]
        if QLineF(last, raw).length() < max(self.grid_size, 6):
            self.end_chain()                 # clicked the last vertex -> finish
            return
        pos = self._chem_constrain(last, raw)   # fixed length + 30° angle
        bond = LineItem(QLineF(last, pos))
        bond.setPen(QPen(self.pen))
        self.addItem(bond)
        center_origin(bond)
        self._chain_pts.append(pos)
        self._chain_preview.setLine(QLineF(pos, pos))
        self.changed_by_user.emit()

    def end_chain(self):
        """Finish an in-progress bond chain, removing the preview segment."""
        if self._chain_preview is not None:
            self.removeItem(self._chain_preview)
        self._chain_preview = None
        self._chain_pts = None

    # ------------------------------------------------------- protractor
    def _protractor_click(self, event):
        """Three-click angle measure: click the vertex, then each arm end.
        A non-left button (or Esc) cancels the in-progress measurement."""
        if event.button() != Qt.LeftButton:
            self.end_angle()
            return
        pos = event.scenePos()
        if self._angle_pts is None:                 # 1st click: the vertex
            self._angle_pts = [pos]
            arm = LineItem(QLineF(pos, pos))
            arm.setPen(QPen(self.pen))
            self.addItem(arm)
            self._angle_preview = [arm]
            return
        if len(self._angle_pts) == 1:               # 2nd click: first arm end
            self._angle_pts.append(pos)
            self._angle_preview[0].setLine(QLineF(self._angle_pts[0], pos))
            arm = LineItem(QLineF(self._angle_pts[0], pos))
            arm.setPen(QPen(self.pen))
            self.addItem(arm)
            self._angle_preview.append(arm)
            return
        # 3rd click: second arm end -> build the measured angle
        v, a = self._angle_pts[0], self._angle_pts[1]
        b = pos
        for it in self._angle_preview:
            self.removeItem(it)
        self._angle_preview = None
        self._angle_pts = None
        self._finish_angle(v, a, b)

    def _update_angle_preview(self, pos: QPointF):
        if not self._angle_pts or self._angle_preview is None:
            return
        self._angle_preview[-1].setLine(QLineF(self._angle_pts[-1], pos))

    def end_angle(self):
        """Cancel an in-progress protractor measurement (drop previews)."""
        if self._angle_preview is not None:
            for it in self._angle_preview:
                self.removeItem(it)
        self._angle_preview = None
        self._angle_pts = None

    def _finish_angle(self, v: QPointF, a: QPointF, b: QPointF):
        """Build the measured angle at vertex *v* between arms v→a and v→b:
        the two arms, an arc through the smaller sweep, and a degree label —
        grouped, editable and undoable."""
        aa = math.atan2(a.y() - v.y(), a.x() - v.x())
        ab = math.atan2(b.y() - v.y(), b.x() - v.x())
        if QLineF(v, a).length() < 1 or QLineF(v, b).length() < 1:
            return
        delta = ab - aa
        while delta <= -math.pi:
            delta += 2 * math.pi
        while delta > math.pi:
            delta -= 2 * math.pi
        deg = abs(math.degrees(delta))
        r = min(QLineF(v, a).length(), QLineF(v, b).length()) * 0.4
        r = max(min(r, 60.0), 12.0)
        items = []
        for end in (a, b):                          # the two arms
            arm = LineItem(QLineF(v, end))
            arm.setPen(QPen(self.pen))
            items.append(arm)
        arc = QPainterPath()                        # arc through the sweep
        steps = max(int(abs(delta) / (math.pi / 36)) + 1, 2)
        for i in range(steps + 1):
            ang = aa + delta * i / steps
            p = QPointF(v.x() + r * math.cos(ang), v.y() + r * math.sin(ang))
            arc.moveTo(p) if i == 0 else arc.lineTo(p)
        arc_item = PathItem(arc)
        arc_item.setPen(QPen(self.pen))
        arc_item.setBrush(QBrush(Qt.NoBrush))
        items.append(arc_item)
        mid = aa + delta / 2.0                       # label on the bisector
        lp = QPointF(v.x() + (r + 14) * math.cos(mid),
                     v.y() + (r + 14) * math.sin(mid))
        label = TextItem(f"{deg:.1f}°")
        label.setDefaultTextColor(self.pen.color())
        lb = label.boundingRect()
        label.setPos(lp.x() - lb.width() / 2.0, lp.y() - lb.height() / 2.0)
        items.append(label)
        group = GroupItem()
        self.addItem(group)
        self.clearSelection()
        for z, it in enumerate(items):
            it.setZValue(z)
            group.addToGroup(it)
        center_origin(group)
        group.setSelected(True)
        self.changed_by_user.emit()
        return group

    # ------------------------------------------------------------ tools
    def mousePressEvent(self, event):
        if self._orbit_item is not None:
            if (self.tool == POINTER and event.button() == Qt.LeftButton
                    and self._top_level_at(event.scenePos())
                    is self._orbit_item):
                self._orbiting = True         # grab the molecule and spin it
                self._orbit_last = event.scenePos()
                event.accept()
                return
            self._exit_orbit()                # any other press ends orbiting
        if self.tool == CHEM_CHAIN:
            self._chain_click(event)
            return
        if self.tool == PROTRACTOR:
            self._protractor_click(event)
            return
        if self.tool == POINTER or event.button() != Qt.LeftButton:
            if (self.tool == POINTER and event.button() == Qt.LeftButton
                    and event.modifiers() & (Qt.ShiftModifier
                                             | Qt.ControlModifier)
                    and not self.crop_active()
                    and self._toggle_select(event.scenePos()) != "pass"):
                # "toggled" — done; "miss" — a modifier-click that landed
                # on empty canvas must NOT clear the selection the user
                # is building (Qt would), so swallow it either way.
                event.accept()
                return
            super().mousePressEvent(event)
            if self.tool == POINTER:
                self._press_positions = {it: it.pos()
                                         for it in self.selectedItems()}
            return
        # Let an in-progress text edit receive the click first.
        focus = self.focusItem()
        if isinstance(focus, TextItem) and focus.textInteractionFlags():
            super().mousePressEvent(event)
            return

        if self.tool == BUCKET:
            from . import fill
            fill.bucket_fill(self, event.scenePos(), self.fill_color,
                             vector=self.bucket_vector)
            return
        if self.tool == PICKER:                     # eyedropper: one click
            self._pick_color(event.scenePos(),
                             fill=bool(event.modifiers() & Qt.ShiftModifier))
            return

        pos = self._tool_pos(event.scenePos())
        self._drawing = True
        self._start = pos

        if self.tool == ERASER:
            # Over an image -> erase that image's pixels; else the raster layer.
            self._paint_image = self._image_at(event.scenePos())
            self._erase_last = event.scenePos()
            self._erase(event.scenePos(), event.scenePos())
        elif self.tool == PENCIL:
            # Over an image -> paint directly onto its pixels (raster, like
            # Paint); over empty canvas -> a normal freehand vector stroke.
            self._paint_image = self._image_at(event.scenePos())
            if self._paint_image is not None:
                self._erase_last = event.scenePos()
                self._paint_image_stroke(self._paint_image, event.scenePos(),
                                         event.scenePos(), erase=False)
            else:
                self.pencil_begin(event.scenePos())
        elif self.tool in _TWO_POINT_TOOLS:
            cls = {ARROW: ArrowItem, DIMENSION: DimensionItem}.get(
                self.tool, LineItem)
            self._temp_item = cls(QLineF(pos, pos))
            self._temp_item.setPen(self.pen)
            if self.tool == DIMENSION:
                self._temp_item.cap_style = self.dim_cap
            elif self.tool == ARROW:
                self._temp_item.set_head(self.arrow_head)
            self.addItem(self._temp_item)
        elif self.tool in _RECT_TOOLS:
            item = self._new_rect_item(self.tool)
            if self.tool == ROOM:                       # a room = wall outline
                wall = QPen(QColor("#333333"),
                            max(self.pen.widthF() * 2, 4))
                wall.setJoinStyle(Qt.MiterJoin)
                item.setPen(wall)
                item.setBrush(QBrush(Qt.NoBrush))       # just the space
            else:
                item.setPen(self.pen)
                item.setBrush(self.current_brush())
            self.addItem(item)
            self._temp_item = item
        elif self.tool == TEXT:
            item = TextItem()
            item.setFont(self.text_font)
            item.setDefaultTextColor(self.pen.color())
            item.setPos(pos)
            self.addItem(item)
            item.start_editing()
            self._drawing = False
            self.changed_by_user.emit()
        elif self.tool in _CHEM_BOND_TOOLS:
            self._temp_item = self._new_chem_bond(pos)
            self.addItem(self._temp_item)
        elif self.tool in _CHEM_PLACE_TOOLS:        # rings / atom: one click
            self._drawing = False
            if self.tool == CHEM_ATOM:
                self.place_chem_atom(self.chem_atom, pos)
            else:
                self.place_chem_ring(self.tool.split("_")[1], pos)
        elif self.tool == PLAN_PLACE:               # room-layout element
            self._drawing = False
            self.place_plan_element(self.plan_element, pos)
        elif self.tool == ELEC_PLACE:               # electrical symbol
            self._drawing = False
            self.place_elec_element(self.elec_element, pos)
        elif self.tool == OPTICS_PLACE:             # optics symbol
            self._drawing = False
            self.place_optics_element(self.optics_element, pos)
        elif self.tool == VACUUM_PLACE:             # vacuum symbol
            self._drawing = False
            self.place_vacuum_element(self.vacuum_element, pos)
        elif self.tool == LABWARE_PLACE:            # glassware symbol
            self._drawing = False
            self.place_labware_element(self.labware_element, pos)
        elif self.tool == FLOW_PLACE:               # flowchart node
            self._drawing = False
            self.place_flow_element(self.flow_element, pos)
        elif self.tool == NET_PLACE:                # network symbol
            self._drawing = False
            self.place_net_element(self.net_element, pos)
        elif self.tool == PID_PLACE:                # P&ID symbol
            self._drawing = False
            self.place_pid_element(self.pid_element, pos)
        elif self.tool == ARROW_PLACE:              # annotation arrow
            self._drawing = False
            self.place_arrow_element(self.arrow_element, pos)
        elif self.tool == BIO_PLACE:                # biology symbol
            self._drawing = False
            self.place_bio_element(self.bio_element, pos)
        elif self.tool == MATH_PLACE:               # math / graph symbol
            self._drawing = False
            self.place_math_element(self.math_element, pos)
        elif self.tool == MOL_PLACE:                # molecule / crystal model
            self._drawing = False
            self.place_mol_element(self.mol_element, pos)
        elif self.tool == S3D_PLACE:                # 3D-schematic block
            self._drawing = False
            self.place_s3d_element(self.s3d_element, pos)
        elif self.tool == SOLID_PLACE:              # rotatable 3D solid
            self._drawing = False
            self.place_solid_element(self.solid_element, pos)

    def mouseMoveEvent(self, event):
        if self._orbiting:
            self._orbit_drag(event.scenePos())
            event.accept()
            return
        if self.tool == CHEM_CHAIN and self._chain_pts is not None:
            last = self._chain_pts[-1]
            self._chain_preview.setLine(
                QLineF(last, self._chem_constrain(last, event.scenePos())))
            return
        if self.tool == PROTRACTOR and self._angle_pts is not None:
            self._update_angle_preview(event.scenePos())
            return
        if not self._drawing:
            super().mouseMoveEvent(event)
            return
        if self.tool == ERASER:
            self._erase(self._erase_last, event.scenePos())
            self._erase_last = event.scenePos()
            return
        if self.tool == PENCIL:
            if self._paint_image is not None:
                self._paint_image_stroke(self._paint_image, self._erase_last,
                                         event.scenePos(), erase=False)
                self._erase_last = event.scenePos()
            else:
                self.pencil_extend(event.scenePos())
            return
        if self._temp_item is None:
            return
        pos = self._tool_pos(event.scenePos())
        if self.tool in _TWO_POINT_TOOLS:
            if self.tool == DIMENSION:
                pos = self._dim_constrain(pos)
            self._temp_item.setLine(QLineF(self._start, pos))
        elif self.tool in _CHEM_BOND_TOOLS:
            end = self._chem_constrain(self._start, event.scenePos())
            self._update_chem_bond(self._temp_item, self._start, end)
        else:
            self._apply_rect(self._temp_item, self._shape_rect(pos))

    def _dim_constrain(self, pos: QPointF) -> QPointF:
        """Force a dimension to a pure horizontal/vertical line (so it
        measures Δx or Δy only) for those ruler orientations."""
        if self.dim_orientation == "horizontal":
            return QPointF(pos.x(), self._start.y())
        if self.dim_orientation == "vertical":
            return QPointF(self._start.x(), pos.y())
        return pos

    # ------------------------------------------------------------ chemistry
    def _chem_constrain(self, start: QPointF, pos: QPointF) -> QPointF:
        """ChemDraw-style: the bond endpoint sits at the predefined bond
        length from *start*, in the cursor's direction snapped to 30°. When
        fixed mode is off, fall back to plain grid snapping."""
        if not self.chem_fixed:
            return self._tool_pos(pos)
        dx, dy = pos.x() - start.x(), pos.y() - start.y()
        if dx == 0 and dy == 0:
            return QPointF(start)
        step = math.radians(30)
        ang = round(math.atan2(dy, dx) / step) * step
        length = self.bond_length_mm / 25.4 * self.dpi
        return QPointF(start.x() + length * math.cos(ang),
                       start.y() + length * math.sin(ang))

    def _chem_gap(self) -> float:
        """Spacing between the parallel lines of a multiple bond / the
        half-width of a wedge — scaled off the current stroke width."""
        return max(3.0, self.pen.widthF() * 2.0 + 2.0)

    def _new_chem_bond(self, pos: QPointF):
        if self.tool == CHEM_WEDGE:
            item = PolygonItem(chemistry.wedge_polygon(pos, pos,
                                                       self._chem_gap()))
            item.setPen(QPen(self.pen.color(), 1))
            item.setBrush(QBrush(self.pen.color()))     # solid filled wedge
        else:
            kind = self.tool.split("_")[1]              # single/double/...
            item = PathItem(chemistry.bond_path(kind, pos, pos,
                                                self._chem_gap()))
            item.setPen(QPen(self.pen))
            item.setBrush(QBrush(Qt.NoBrush))
        return item

    def _update_chem_bond(self, item, p1: QPointF, p2: QPointF):
        if self.tool == CHEM_WEDGE:
            item.setPolygon(chemistry.wedge_polygon(p1, p2, self._chem_gap()))
        else:
            item.setPath(chemistry.bond_path(self.tool.split("_")[1],
                                             p1, p2, self._chem_gap()))

    def place_chem_ring(self, kind: str, center: QPointF):
        """Drop a ready-made ring (editable) centred at *center*."""
        r = 6.0 / 25.4 * self.dpi                       # ~6 mm radius
        poly = chemistry.ring_polygon(kind, center, r)
        side = "pentagon" if kind == "cyclopentane" else "hexagon"
        ring = PolygonItem(poly, kind=side)
        ring.setPen(QPen(self.pen))
        ring.setBrush(self.current_brush())
        self.clearSelection()
        if chemistry.is_aromatic(kind):                 # benzene: inner circle
            ir = r * 0.55
            circle = EllipseItem(QRectF(center.x() - ir, center.y() - ir,
                                        2 * ir, 2 * ir))
            circle.setPen(QPen(self.pen))
            circle.setBrush(QBrush(Qt.NoBrush))
            group = GroupItem()
            self.addItem(group)
            for z, it in enumerate((ring, circle)):
                it.setZValue(z)
                group.addToGroup(it)
            center_origin(group)
            group.setSelected(True)
        else:
            self.addItem(ring)
            center_origin(ring)
            ring.setSelected(True)
        self.changed_by_user.emit()

    def _nearest_bond_end(self, scene_pos: QPointF, tol: float):
        """The nearest line/path endpoint to *scene_pos* within *tol*, so an
        atom label snaps onto the end of a bond. Returns None if none near."""
        best, best_d = None, tol
        for it in self.vector_items():
            pts = []
            if isinstance(it, LineItem):            # single/chain/arrow bonds
                ln = it.line()
                pts = [it.mapToScene(ln.p1()), it.mapToScene(ln.p2())]
            elif isinstance(it, PathItem):          # double/triple/hash bonds
                path = it.path()
                pts = [it.mapToScene(QPointF(path.elementAt(i).x,
                                             path.elementAt(i).y))
                       for i in range(path.elementCount())]
            for p in pts:
                d = QLineF(scene_pos, p).length()
                if d < best_d:
                    best, best_d = p, d
        return best

    def place_chem_atom(self, text: str, center: QPointF):
        """Place an atom/group label, snapping onto a nearby bond end so it
        sits exactly at the terminus (e.g. the O of a C=O)."""
        tol = self.bond_length_mm / 25.4 * self.dpi * 0.4
        anchor = self._nearest_bond_end(center, tol)
        if anchor is not None:
            center = anchor
        item = TextItem(text or "C")
        item.setDefaultTextColor(self.pen.color())
        self.addItem(item)
        c = item.boundingRect().center()        # exact centre incl. margins
        was_snap = self.snap_enabled
        self.snap_enabled = False               # sit exactly on the bond end
        item.setPos(center.x() - c.x(), center.y() - c.y())
        self.snap_enabled = was_snap
        center_origin(item)
        self.clearSelection()
        item.setSelected(True)
        self.changed_by_user.emit()

    # ------------------------------------------------------------ paint tools
    def _image_at(self, pos: QPointF):
        """Topmost inserted/pasted image item under *pos* (scene coords), or
        None. The raster background (a plain pixmap item, not an ImageItem)
        is intentionally excluded — it keeps the raster-layer paint path."""
        for it in self.items(pos):
            if isinstance(it, ImageItem):
                return it
        return None

    def _paint_image_stroke(self, image_item, p1: QPointF, p2: QPointF,
                            erase: bool):
        """Paint a round-capped stroke onto *image_item*'s own pixels along
        p1->p2 (scene coords). *erase* clears to transparent; otherwise the
        current stroke colour is drawn. Editing the bitmap directly, like the
        MS-Paint eraser/pencil, but on the selected image rather than the
        raster layer. The alpha round-trips through save + undo."""
        from PySide6.QtGui import QImage
        pixmap = image_item.pixmap()
        if pixmap.isNull():
            return
        image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
        # Map scene points into the image's own pixel space (honours the
        # image's position, rotation and scale).
        a = image_item.mapFromScene(p1)
        b = image_item.mapFromScene(p2)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if erase:
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            width = max(self.pen.widthF() * 4, 12)
            color = Qt.transparent            # colour ignored in Clear mode
        else:
            width = max(self.pen.widthF(), 1)
            color = self.pen.color()
        pen = QPen(color, width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        if a == b:                            # single click -> a round dot
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(a, width / 2.0, width / 2.0)
        else:
            painter.drawLine(a, b)
        painter.end()
        image_item.setPixmap(QPixmap.fromImage(image))

    def _erase(self, p1: QPointF, p2: QPointF):
        """Erase along p1->p2. Over an inserted image, clear its pixels to
        transparent; otherwise paint the raster layer white (MS-Paint)."""
        if self._paint_image is not None:
            self._paint_image_stroke(self._paint_image, p1, p2, erase=True)
            return
        if self.erase_objects:
            # In a vector drawing the eraser mostly meets shapes, not
            # pixels: remove whole top-level items the stroke touches.
            from .handles import Handle
            for it in self.items(p2):
                if it is self.raster_item or isinstance(it, Handle):
                    continue
                while it.parentItem() is not None:
                    it = it.parentItem()
                if isinstance(it, ImageItem):
                    continue
                self.clear_handles()
                self.removeItem(it)
                return
        pixmap = self.raster_item.pixmap()
        if pixmap.isNull():
            return
        painter = QPainter(pixmap)
        pen = QPen(Qt.white, max(self.pen.widthF() * 4, 12))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(p1, p2)
        painter.end()
        self.raster_item.setPixmap(pixmap)

    def _pick_color(self, pos: QPointF, fill: bool = False):
        """Colour picker / eyedropper: sample the colour under the cursor
        (raster, images and vector items, as drawn) into the stroke pen —
        or into the fill colour when *fill* (Shift+click)."""
        from PySide6.QtGui import QImage
        img = QImage(1, 1, QImage.Format_ARGB32)
        img.fill(Qt.white)
        painter = QPainter(img)
        self.render(painter, QRectF(0, 0, 1, 1),
                    QRectF(pos.x(), pos.y(), 1, 1))
        painter.end()
        color = QColor(img.pixel(0, 0))
        if fill:
            self.fill_color = color
        else:
            self.pen.setColor(color)
        self.color_picked.emit(color.name(), "fill" if fill else "stroke")

    # ------------------------------------------------ symbol libraries (plan/elec)
    def place_plan_element(self, name: str, center: QPointF):
        """Drop a top-view room-layout element (walls/furniture/fittings),
        grouped and editable, centred on *center*."""
        from . import floorplan
        return self._place_symbol(floorplan, name, center)

    def place_elec_element(self, name: str, center: QPointF):
        """Drop an electrical symbol (component or installation marker)."""
        from . import electrical
        return self._place_symbol(electrical, name, center)

    def place_optics_element(self, name: str, center: QPointF):
        """Drop an optics / photonics symbol (beam-path diagrams)."""
        from . import optics
        return self._place_symbol(optics, name, center)

    def place_vacuum_element(self, name: str, center: QPointF):
        """Drop a vacuum / surface-science symbol (UHV systems)."""
        from . import vacuum
        return self._place_symbol(vacuum, name, center)

    def place_labware_element(self, name: str, center: QPointF):
        """Drop a lab-glassware / apparatus symbol."""
        from . import labware
        return self._place_symbol(labware, name, center)

    def place_flow_element(self, name: str, center: QPointF):
        """Drop a flowchart node symbol."""
        from . import flowchart
        return self._place_symbol(flowchart, name, center)

    def place_net_element(self, name: str, center: QPointF):
        """Drop a network / IT architecture symbol."""
        from . import network
        return self._place_symbol(network, name, center)

    def place_pid_element(self, name: str, center: QPointF):
        """Drop a P&ID / process-flow symbol."""
        from . import pid
        return self._place_symbol(pid, name, center)

    def place_arrow_element(self, name: str, center: QPointF):
        """Drop an annotation arrow / callout / banner."""
        from . import arrows
        return self._place_symbol(arrows, name, center)

    def place_bio_element(self, name: str, center: QPointF):
        """Drop a biology / life-science symbol."""
        from . import biology
        return self._place_symbol(biology, name, center)

    def place_math_element(self, name: str, center: QPointF):
        """Drop a math / graph / vector symbol."""
        from . import maths
        return self._place_symbol(maths, name, center)

    def place_s3d_element(self, name: str, center: QPointF):
        """Drop a 3D-schematic block (slab, particle bed, glow, trail…)."""
        from . import scheme3d
        return self._place_symbol(scheme3d, name, center)

    def place_solid_element(self, name: str, center: QPointF):
        """Drop a shaded, rotatable 3D solid (cube, cylinder, torus…)."""
        from . import solids
        return solids.place_solid(self, name, center, self.solid_color)

    def place_mol_element(self, name: str, center: QPointF):
        """Drop a molecule / crystal ball-and-stick model."""
        from . import molecules
        top = self._place_symbol(molecules, name, center)
        if top is not None:                      # tag for the 3D viewer
            w_mm, h_mm = molecules.size_mm(name)
            ref = getattr(molecules, "REFERENCE_MM", 4800.0)
            scale = (self.sceneRect().width() or 1) / ref
            box = max(w_mm * scale, h_mm * scale)
            self._tag_model(top, name, molecules.DEFAULT_AZ,
                            molecules.DEFAULT_EL, molecules.default_bond(name),
                            box=box)
        return top

    def place_built_molecule(self, atoms, bonds, center, az=None, el=None,
                             bond=None, mode="3d", name="custom", commit=True):
        """Place a molecule (hand-built in the builder, or emitted by the AI)
        as a new tagged, 3D-rotatable, editable group centred on *center*.
        Undoable when *commit* (pass False to batch several into one step)."""
        from . import molecules, molrepr
        from .specs import _spec_to_item
        if not atoms:
            return None
        az = molecules.DEFAULT_AZ if az is None else az
        el = molecules.DEFAULT_EL if el is None else el
        bond = molecules.DEFAULT_BOND if bond is None else bond
        ref = getattr(molecules, "REFERENCE_MM", 130.0)
        box = (self.sceneRect().width() or 1) / ref * 72.0
        if mode == "3d":
            specs = molecules.specs_from_atoms(atoms, bonds, box, box, az, el,
                                               bond)
        else:
            specs = molrepr.representation_specs(mode, atoms, bonds, box, box)
        items = [it for it in (_spec_to_item(s) for s in specs)
                 if it is not None]
        if not items:
            return None
        top = self._drop_items(items, center, box, box)
        self._tag_model(top, name, az, el, bond, atoms, bonds, box=box,
                        repr=mode)
        if commit:
            self.changed_by_user.emit()
        return top

    @staticmethod
    def _tag_model(item, name, az, el, bond, atoms=None, bonds=None, box=None,
                   repr="3d", cells=None, colors=None, tilts=None,
                   poly=False):
        """Stamp a group with its model identity (name + view + bond spread +
        stable build box + representation, the raw atoms/bonds when the
        structure was hand-built, the ``(nx, ny, nz)`` supercell counts
        when unit cells have been stacked, the per-element/site colour
        override map for crystals — see `molcolor` — and the per-cell tilt
        map ``{"i,j,k": (rx, ry, rz)}`` for rotated cells in a supercell)."""
        item.mol_name = name
        item.mol_az = az
        item.mol_el = el
        item.mol_bond = bond
        item.mol_atoms = atoms
        item.mol_bonds = bonds
        item.mol_box = box
        item.mol_repr = repr
        item.mol_cells = cells
        item.mol_colors = colors
        item.mol_tilts = tilts
        item.mol_poly = bool(poly)

    def _place_symbol(self, module, name: str, center: QPointF):
        """Build items from a spec-library module's `build_specs`/`size_mm`
        and place them centred on *center* (grouped if multi-part). Returns
        the created top-level item (group or single), or None.

        Symbols are sized as a fraction of the PAGE, not in absolute mm —
        the page width represents `module.REFERENCE_MM` of real space, so a
        whole room (or circuit) fits the drawing (e.g. a 480 mm chair on a
        4.8 m reference is ~1/10 of the page)."""
        from .specs import _spec_to_item
        w_mm, h_mm = module.size_mm(name)
        ref = getattr(module, "REFERENCE_MM", 4800.0)
        page = getattr(self, "symbol_page_px", None) or self.sceneRect().width()
        scale = (page or 1) / ref
        w = w_mm * scale
        h = h_mm * scale
        # Tiny components (a 24 mm resistor on a 600 mm reference) would be
        # a few pixels wide; rebuild them larger rather than scale the item,
        # so their stroke widths stay as designed.
        min_px = getattr(self, "symbol_min_px", 0)
        if 0 < max(w, h) < min_px:
            k = min_px / max(w, h)
            w, h = w * k, h * k
        items = [it for it in (_spec_to_item(s)
                               for s in module.build_specs(name, w, h))
                 if it is not None]
        if not items:
            return None
        top = self._drop_items(items, center, w, h)
        # remember what it is ("scheme3d:slab_grey") for list_items and the
        # Items panel — persisted, so it survives undo and save
        top.symbol = f"{module.__name__.rsplit('.', 1)[-1]}:{name}"
        self.changed_by_user.emit()
        return top

    def _drop_items(self, items, center, w, h):
        """Place *items* (positioned within a (w, h) box) centred on *center*,
        grouping them if there is more than one; return the top-level item."""
        dx, dy = center.x() - w / 2, center.y() - h / 2
        was_snap = self.snap_enabled
        self.snap_enabled = False                # already grid-snapped centre
        self.clearSelection()
        if len(items) == 1:
            top = items[0]
            top.moveBy(dx, dy)
            self.addItem(top)
            center_origin(top)
        else:
            top = GroupItem()
            self.addItem(top)
            for z, item in enumerate(items):
                item.moveBy(dx, dy)
                item.setZValue(z)
                top.addToGroup(item)
            center_origin(top)
        top.setSelected(True)
        self.snap_enabled = was_snap
        return top

    def place_scale_bar(self, length_mm: float, label: str, center: QPointF):
        """Drop a labelled scale bar whose bar is *length_mm* long at the
        current dpi (a filled bar + end ticks + a centred caption), grouped
        and centred on *center*. Ordinary editable items, so it round-trips
        and is undoable. Returns the group (or None)."""
        dpi = max(getattr(self, "dpi", 96), 1)
        length = length_mm / 25.4 * dpi                  # px
        if length <= 0:
            return None
        thick = max(length * 0.04, 2.5)
        tick = thick * 2.2
        x0, y0 = -length / 2.0, 0.0
        ink = QColor("#111111")
        items = []
        bar = RectItem(QRectF(x0, y0, length, thick))
        bar.setPen(QPen(ink, 1))
        bar.setBrush(QBrush(ink))
        items.append(bar)
        for xx in (x0, x0 + length):                     # end ticks
            t = LineItem(QLineF(xx, y0 - tick + thick, xx, y0 + thick))
            t.setPen(QPen(ink, max(thick * 0.5, 1.0)))
            items.append(t)
        cap = TextItem(label)                            # caption below
        f = cap.font()
        f.setPixelSize(max(int(length * 0.2), 12))
        cap.setFont(f)
        cap.setDefaultTextColor(ink)
        cb = cap.boundingRect()
        cap.setPos(-cb.width() / 2.0, y0 + thick + tick * 0.2)
        items.append(cap)
        # Group and move so the group's centre lands on *center*.
        group = GroupItem()
        self.addItem(group)
        self.clearSelection()
        for z, it in enumerate(items):
            it.setZValue(z)
            group.addToGroup(it)
        c = group.sceneBoundingRect().center()
        was_snap = self.snap_enabled
        self.snap_enabled = False
        group.moveBy(center.x() - c.x(), center.y() - c.y())
        self.snap_enabled = was_snap
        center_origin(group)
        group.setSelected(True)
        self.changed_by_user.emit()
        return group

    def reorient_model(self, item, az, el, bond=None, atoms=None, bonds=None,
                       mode=None, cells="keep", colors="keep", tilts="keep",
                       poly="keep", commit=True):
        """Rebuild a placed molecule/crystal *item* at view angles (az, el),
        bond spread *bond* and representation *mode* (3d / structural / lewis
        / condensed), preserving its centre and footprint. When *atoms*/
        *bonds* are given the structure is replaced (hand-built in the
        builder); *cells* re-tiles a crystal supercell, *colors* recolours
        its atoms and *tilts* rotates chosen cells inside the supercell
        (``"keep"`` reuses the item's current values). Returns the new
        top-level item. Undoable when *commit*."""
        name = getattr(item, "mol_name", None)
        if name is None:
            return None
        from . import molecules, molrepr
        from .specs import _spec_to_item
        if bond is None:
            bond = getattr(item, "mol_bond", None)
            if bond is None:            # NOT `or`: a 0.0 spacing is valid
                bond = molecules.default_bond(name)
        if mode is None:
            mode = getattr(item, "mol_repr", None) or "3d"
        if cells == "keep":
            cells = getattr(item, "mol_cells", None)
        if colors == "keep":
            colors = getattr(item, "mol_colors", None)
        if tilts == "keep":
            tilts = getattr(item, "mol_tilts", None)
        tilts = _tilts_in_range(tilts, cells)
        if poly == "keep":
            poly = bool(getattr(item, "mol_poly", False))
        if atoms is None:
            atoms = getattr(item, "mol_atoms", None)
            bonds = getattr(item, "mol_bonds", None)
        rect = item.sceneBoundingRect()
        center = rect.center()
        # Use the STABLE build box stamped at placement, not the current
        # (margin-shrunk) bounding rect — deriving it from the drawn size
        # would compound smaller on every rebuild during a drag.
        box = getattr(item, "mol_box", None) or max(rect.width(),
                                                    rect.height()) or 1.0
        if mode == "3d":
            if atoms:
                specs = molecules.specs_from_atoms(atoms, bonds or [], box,
                                                   box, az, el, bond)
            else:
                specs = molecules.build_specs_oriented(name, box, box, az, el,
                                                       bond, cells=cells,
                                                       colors=colors,
                                                       tilts=tilts, poly=poly)
        else:                                     # 2D chemistry diagram
            a2, b2 = ((atoms, bonds) if atoms
                      else molecules.model_data(name, cells, tilts=tilts)[:2])
            specs = molrepr.representation_specs(mode, a2, b2, box, box)
        new_items = [it for it in (_spec_to_item(s) for s in specs)
                     if it is not None]
        if not new_items:
            return None
        self.clear_handles()
        self.removeItem(item)
        top = self._drop_items(new_items, center, box, box)
        self._tag_model(top, name, az, el, bond, atoms, bonds, box=box,
                        repr=mode, cells=cells, colors=colors, tilts=tilts,
                        poly=poly)
        if commit:
            self.changed_by_user.emit()
        return top

    def set_representation(self, item, mode):
        """Redraw a placed molecule in a different representation (3D ball-
        and-stick, structural / Lewis formula, or condensed formula)."""
        self.reorient_model(item, getattr(item, "mol_az", None),
                            getattr(item, "mol_el", None), mode=mode)

    def set_cells(self, item, nx, ny, nz):
        """Rebuild a placed crystal *item* as an ``nx×ny×nz`` supercell —
        stacking unit cells face-to-face — keeping it a tagged, rotatable
        model. (1, 1, 1) restores the single unit cell. Undoable."""
        from . import molecules
        name = getattr(item, "mol_name", None)
        if not name or not molecules.can_stack(name):
            return None
        cells = (int(nx), int(ny), int(nz))
        if cells == (1, 1, 1):
            cells = None
        # Recompute the base single-cell box from the model's footprint, then
        # magnify by the stack factor so the drawn spheres keep a constant
        # size as the cell count grows (bigger span in a proportionally
        # bigger box → same on-screen ball radius).
        w_mm, h_mm = molecules.size_mm(name)
        ref = getattr(molecules, "REFERENCE_MM", 130.0)
        scale = (self.sceneRect().width() or 1) / ref
        base = max(w_mm * scale, h_mm * scale)
        item.mol_box = base * molecules.stack_factor(cells)
        return self.reorient_model(item, getattr(item, "mol_az", None),
                                   getattr(item, "mol_el", None), cells=cells)

    # ---------------------------------------------- on-canvas 3D rotation
    def enter_orbit_mode(self, item):
        """Start rotating a placed molecule/crystal *item* in 3D directly on
        the canvas: drag anywhere on it to spin; click off it (or press Esc,
        or switch tool) to finish. Returns True if *item* is a 3D model."""
        if getattr(item, "solid", None):
            pass                                  # 3D solid: always spins
        elif not getattr(item, "mol_name", None):
            return False
        elif (getattr(item, "mol_repr", None) or "3d") != "3d":
            return False                          # 2D formulas don't rotate
        self.clear_handles()
        self.clearSelection()
        item.setSelected(True)
        self._orbit_item = item
        self._orbit_dirty = False
        for view in self.views():
            view.viewport().setCursor(Qt.OpenHandCursor)
        return True

    def _exit_orbit(self):
        if self._orbit_item is None:
            return
        self._orbit_item = None
        self._orbiting = False
        self._orbit_last = None
        for view in self.views():
            view.set_tool_cursor(self.tool)
        if self._orbit_dirty:
            self.changed_by_user.emit()   # one undoable step for the session
        self._orbit_dirty = False
        self.refresh_handles()

    def _orbit_drag(self, scene_pos):
        """Spin the orbit target by the drag delta (live, no per-move undo)."""
        import math as _math
        from . import molecules
        item = self._orbit_item
        delta = scene_pos - self._orbit_last
        self._orbit_last = scene_pos
        if getattr(item, "solid", None):          # 3D solid, not a molecule
            from . import solids
            new = solids.reorient_solid(
                self, item, item.solid["az"] + delta.x() * 0.012,
                item.solid["el"] + delta.y() * 0.012, commit=False)
            if new is not None:
                self._orbit_item = new
                self._orbit_dirty = True
            return
        az = (getattr(item, "mol_az", None) or molecules.DEFAULT_AZ) \
            + delta.x() * 0.012
        el = (getattr(item, "mol_el", None) or molecules.DEFAULT_EL) \
            - delta.y() * 0.012
        el = max(-_math.pi / 2, min(_math.pi / 2, el))
        new = self.reorient_model(item, az, el, commit=False)
        if new is not None:
            self._orbit_item = new
            self._orbit_dirty = True

    def _top_level_at(self, scene_pos):
        from .handles import Handle
        for it in self.items(scene_pos):
            if isinstance(it, Handle):
                continue
            while it.parentItem() is not None:
                it = it.parentItem()
            return it
        return None

    def mouseReleaseEvent(self, event):
        if self._orbiting:                    # finished one spin drag
            self._orbiting = False            # stay in orbit mode for more
            for view in self.views():
                view.viewport().setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        if not self._drawing:
            super().mouseReleaseEvent(event)
            if self.tool == POINTER and event.button() == Qt.LeftButton:
                moved = self._moved_since_press()
                self.refresh_handles()
                if moved:
                    self.changed_by_user.emit()
            return
        self._drawing = False
        if self.tool == ERASER:
            self._erase_last = None
            self._paint_image = None
            self.changed_by_user.emit()         # raster/image change is undoable
            return
        if self.tool == PENCIL:
            if self._paint_image is not None:   # painted onto an image's pixels
                self._paint_image = None
                self._erase_last = None
                self.changed_by_user.emit()
            else:
                self.pencil_end()
            return
        item = self._temp_item
        self._temp_item = None
        if item is None:
            return
        if self.tool == ROOM:
            self._finish_room(item)
            return
        if isinstance(item, LineItem):
            degenerate = item.line().length() < 1
        else:
            br = item.boundingRect()
            degenerate = br.width() < 1 and br.height() < 1
        if degenerate:
            self.removeItem(item)
        else:
            center_origin(item)
            self.changed_by_user.emit()

    def _finish_room(self, preview):
        """Turn the dragged rectangle into a room: four solid wall bars with
        an empty (hollow) square at each corner where the walls meet."""
        rect = QRectF(preview.rect()).normalized()
        self.removeItem(preview)
        if rect.width() < 2 or rect.height() < 2:
            return
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        t = max(min(w, h) * 0.02, 2.0)               # wall depth
        wall_pen = QPen(QColor("#222222"), 1)
        wall_pen.setJoinStyle(Qt.MiterJoin)
        corner_pen = QPen(QColor("#333333"), 2)
        corner_pen.setJoinStyle(Qt.MiterJoin)
        parts = []
        # solid wall bars, stopping short of the corners
        for r in (QRectF(x + t, y, w - 2 * t, t),            # top
                  QRectF(x + t, y + h - t, w - 2 * t, t),    # bottom
                  QRectF(x, y + t, t, h - 2 * t),            # left
                  QRectF(x + w - t, y + t, t, h - 2 * t)):   # right
            bar = RectItem(r)
            bar.setPen(QPen(wall_pen))
            bar.setBrush(QBrush(QColor("#222222")))
            parts.append(bar)
        # empty corner squares
        for r in (QRectF(x, y, t, t), QRectF(x + w - t, y, t, t),
                  QRectF(x, y + h - t, t, t),
                  QRectF(x + w - t, y + h - t, t, t)):
            sq = RectItem(r)
            sq.setPen(QPen(corner_pen))
            sq.setBrush(QBrush(Qt.NoBrush))
            parts.append(sq)
        group = GroupItem()
        self.addItem(group)
        self.clearSelection()
        for z, it in enumerate(parts):
            it.setZValue(z)
            group.addToGroup(it)
        center_origin(group)
        group.setSelected(True)
        self.changed_by_user.emit()

    # ------------------------------------------------------------ pencil
    def pencil_begin(self, point: QPointF):
        """Start a freehand vector stroke at *point* (scene coords)."""
        self._stroke_path = QPainterPath(point)
        stroke = PathItem(self._stroke_path)
        stroke.setPen(QPen(self.pen))          # copy, not shared
        stroke.setBrush(QBrush(Qt.NoBrush))
        self.addItem(stroke)
        self._temp_item = stroke

    def pencil_extend(self, point: QPointF):
        if self._stroke_path is None or self._temp_item is None:
            return
        if (point - self._stroke_path.currentPosition()
                ).manhattanLength() >= 2:
            self._stroke_path.lineTo(point)
            self._temp_item.setPath(self._stroke_path)

    def pencil_end(self):
        stroke = self._temp_item
        path = self._stroke_path
        self._temp_item = None
        self._stroke_path = None
        if stroke is None:
            return
        if path is None or path.elementCount() <= 1:
            self.removeItem(stroke)            # a click with no drag
        else:
            center_origin(stroke)
            self.changed_by_user.emit()

    def _moved_since_press(self) -> bool:
        """True if any item selected at press has since changed position
        (a pointer move gesture), so it can be recorded for undo."""
        return any(it.scene() is self and it.pos() != pos
                   for it, pos in self._press_positions.items())

    def _new_rect_item(self, tool: str):
        """A fresh, empty rect-defined item for *tool*."""
        if tool in (RECT, ROOM):
            return RectItem(QRectF())
        if tool == ROUNDRECT:
            return RoundedRectItem(QRectF())
        if tool in POLYGON_KINDS:
            return PolygonItem(kind=tool)
        if tool in ARC_KINDS:
            return ArcShapeItem(kind=tool)
        return EllipseItem(QRectF())          # RECT/CIRCLE/ELLIPSE ellipses

    @staticmethod
    def _apply_rect(item, rect: QRectF):
        """Resize a rect-defined item during the creation drag."""
        if isinstance(item, (PolygonItem, RoundedRectItem, ArcShapeItem)):
            item.set_rect(rect)
        else:
            item.setRect(rect)

    # ------------------------------------------------------------ mirror
    def mirror_selection(self, horizontal: bool = True):
        """Flip the selected items in place (about their own centres)."""
        items = [i for i in self.selectedItems() if i.parentItem() is None]
        for item in items:
            self._mirror_item(item, horizontal)
        if items:
            self.changed_by_user.emit()

    def _mirror_item(self, item, horizontal: bool):
        if isinstance(item, GroupItem):
            self._mirror_group(item, horizontal)
            return
        if isinstance(item, ArcShapeItem):
            item.mirror(horizontal)
            return
        if isinstance(item, ImageItem):
            item.setPixmap(item.pixmap().transformed(
                QTransform().scale(-1 if horizontal else 1,
                                   1 if horizontal else -1)))
            return
        c = item.boundingRect().center()
        t = QTransform()
        t.translate(c.x(), c.y())
        t.scale(-1 if horizontal else 1, 1 if horizontal else -1)
        t.translate(-c.x(), -c.y())
        if isinstance(item, PolygonItem):
            item.setPolygon(t.map(item.polygon()))
        elif isinstance(item, LineItem):       # includes arrow
            ln = item.line()
            item.setLine(QLineF(t.map(ln.p1()), t.map(ln.p2())))
            if item.bend() is not None:
                item.set_bend(t.map(item.bend()))
        elif isinstance(item, PathItem):
            item.setPath(t.map(item.path()))
        # rect/ellipse/rounded-rect/text are symmetric: nothing to do

    def _mirror_group(self, group, horizontal: bool):
        """Flip a group about its centre: flip each child in place and
        reflect its position about the group centre (the two together
        equal reflecting the whole group). Keeps every child native, so
        the flip round-trips through save."""
        from .handles import Handle
        centre = group.boundingRect().center()
        was_snap = self.snap_enabled
        self.snap_enabled = False
        for child in group.childItems():
            if isinstance(child, Handle):
                continue
            self._mirror_item(child, horizontal)
            cc = child.mapToParent(child.boundingRect().center())
            if horizontal:
                child.moveBy(2 * (centre.x() - cc.x()), 0)
            else:
                child.moveBy(0, 2 * (centre.y() - cc.y()))
        self.snap_enabled = was_snap

    def _shape_rect(self, pos: QPointF) -> QRectF:
        """Rect from drag start to *pos*; the circle tool stays square."""
        dx = pos.x() - self._start.x()
        dy = pos.y() - self._start.y()
        if self.tool == CIRCLE:
            side = max(abs(dx), abs(dy))
            dx = side if dx >= 0 else -side
            dy = side if dy >= 0 else -side
        return QRectF(self._start,
                      self._start + QPointF(dx, dy)).normalized()


class _RulerBar(QWidget):
    """A thin ruler along the top or left edge of the view, graduated in
    millimetres. Reads the view's transform + the scene dpi each paint, so
    ticks track zoom and scroll; a marker follows the cursor."""

    THICK = 22

    def __init__(self, view, horizontal: bool):
        super().__init__(view)
        self._view = view
        self._h = horizontal
        self._cursor = None                       # scene coord of the cursor
        self.setFont(QFont("Segoe UI", 7))

    def set_cursor(self, scene_val):
        self._cursor = scene_val
        self.update()

    @staticmethod
    def _nice_step_mm(px_per_mm, target=58):
        """Smallest 1/2/5·10ⁿ mm step whose labels are ≥ ~target px apart."""
        if px_per_mm <= 0:
            return 1.0
        raw = target / px_per_mm
        mag = 10.0 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
        for m in (1, 2, 5, 10):
            if m * mag >= raw:
                return m * mag
        return 10 * mag

    def paintEvent(self, _event):
        view = self._view
        scene = view.scene()
        dpi = max(getattr(scene, "dpi", 96), 1)
        zoom = view.current_zoom()
        px_per_mm = zoom * dpi / 25.4
        pal = self.palette()
        bg = pal.window().color()
        ink = pal.windowText().color()
        painter = QPainter(self)
        painter.fillRect(self.rect(), bg)
        painter.setPen(QPen(ink, 0))
        length = self.width() if self._h else self.height()
        edge = self.THICK
        # visible scene range across this ruler
        if self._h:
            s0 = view.mapToScene(QPoint(0, 0)).x()
            s1 = view.mapToScene(QPoint(length, 0)).x()
        else:
            s0 = view.mapToScene(QPoint(0, 0)).y()
            s1 = view.mapToScene(QPoint(0, length)).y()
        mm0, mm1 = s0 / dpi * 25.4, s1 / dpi * 25.4
        step = self._nice_step_mm(px_per_mm)
        minor = step / 5.0
        v = math.floor(mm0 / minor) * minor
        while v <= mm1:
            scene_v = v / 25.4 * dpi
            if self._h:
                pos = view.mapFromScene(QPointF(scene_v, 0)).x()
            else:
                pos = view.mapFromScene(QPointF(0, scene_v)).y()
            major = abs(v - round(v / step) * step) < minor * 0.5
            t = edge * (0.62 if major else 0.32)
            if self._h:
                painter.drawLine(int(pos), int(edge - t), int(pos), edge)
            else:
                painter.drawLine(int(edge - t), int(pos), edge, int(pos))
            if major:
                label = f"{round(v / step) * step:g}"
                if self._h:
                    painter.drawText(int(pos) + 2, edge - t - 1, label)
                else:
                    painter.save()
                    painter.translate(edge - t - 1, int(pos) - 2)
                    painter.rotate(-90)
                    painter.drawText(0, 0, label)
                    painter.restore()
            v += minor
        # cursor marker
        if self._cursor is not None:
            if self._h:
                cp = view.mapFromScene(QPointF(self._cursor, 0)).x()
                painter.setPen(QPen(QColor("#d23b3b"), 1))
                painter.drawLine(int(cp), 0, int(cp), edge)
            else:
                cp = view.mapFromScene(QPointF(0, self._cursor)).y()
                painter.setPen(QPen(QColor("#d23b3b"), 1))
                painter.drawLine(0, int(cp), edge, int(cp))
        painter.end()


class PaintView(QGraphicsView):
    """Canvas view: grid overlay, zoom, cursor tracking."""

    cursor_moved = Signal(QPointF)
    #: (top-level item, global QPoint) when an item is right-clicked.
    item_context = Signal(object, object)
    #: (scene QPointF, global QPoint) when empty canvas is right-clicked.
    canvas_context = Signal(object, object)
    #: emitted with the new zoom factor (1.0 == 100%) whenever it changes.
    zoom_changed = Signal(float)
    #: (list of local file paths, dropped QImage or None, scene pos) on drop.
    content_dropped = Signal(list, object, QPointF)

    MIN_ZOOM, MAX_ZOOM = 0.1, 16.0

    def __init__(self, scene: PaintScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing
                            | QPainter.SmoothPixmapTransform)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFocusPolicy(Qt.StrongFocus)   # so Enter/Esc reach the view
        self.setAcceptDrops(True)             # drop images/files onto canvas
        # Repaint the whole viewport on every change: partial updates
        # leave stale selection dashes / handles behind after deselect.
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        # Edge rulers (mm), hidden until toggled from the Measure menu.
        self._rulers_on = False
        self._ruler_h = _RulerBar(self, horizontal=True)
        self._ruler_v = _RulerBar(self, horizontal=False)
        self._ruler_corner = QWidget(self)
        for w in (self._ruler_h, self._ruler_v, self._ruler_corner):
            w.hide()

    # --------------------------------------------------------- drag & drop
    @staticmethod
    def _has_droppable(mime) -> bool:
        return mime.hasImage() or mime.hasUrls()

    def dragEnterEvent(self, event):
        if self._has_droppable(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._has_droppable(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        mime = event.mimeData()
        if not self._has_droppable(mime):
            super().dropEvent(event)
            return
        paths = [u.toLocalFile() for u in mime.urls()
                 if u.isLocalFile()] if mime.hasUrls() else []
        image = mime.imageData() if mime.hasImage() else None
        self.content_dropped.emit(paths, image, self.mapToScene(event.position().toPoint()))
        event.acceptProposedAction()

    def _pick_item(self, view_pos):
        """Top-level editable item under *view_pos*, or None.
        Skips endpoint handles and the raster layer; climbs to the
        outermost group so right-clicking inside a group targets it."""
        from .handles import Handle
        for it in self.items(view_pos):
            if isinstance(it, Handle) or it is self.scene().raster_item:
                continue
            while it.parentItem() is not None:
                it = it.parentItem()
            return it
        return None

    def contextMenuEvent(self, event):
        if self.scene().tool != POINTER:
            return
        item = self._pick_item(event.pos())
        if item is None:                       # empty canvas: tools + library
            self.canvas_context.emit(self.mapToScene(event.pos()),
                                     event.globalPos())
            return
        if not item.isSelected():
            self.scene().clearSelection()
            item.setSelected(True)
        self.item_context.emit(item, event.globalPos())

    def mouseDoubleClickEvent(self, event):
        if self.scene().crop_active():        # double-click confirms a crop
            self.scene().apply_crop()
            return
        if self.scene().tool == POINTER:
            item = self._pick_item(event.position().toPoint())
            if item is not None and getattr(item, "rxn_data", None):
                from .reactionview import open_reaction_builder
                open_reaction_builder(self, item)      # re-edit the scheme
                return
            if item is not None and getattr(item, "solid", None):
                self.scene().enter_orbit_mode(item)    # spin a 3D solid
                return
            if item is not None and getattr(item, "mol_name", None):
                # 3D model: rotate in place on the canvas (no popup).
                # 2D formula: open the builder (where you can switch back).
                if not self.scene().enter_orbit_mode(item):
                    self.open_molecule_builder(item)
                return
            if item is not None and not isinstance(item, TextItem):
                self.scene().enter_rotate_mode(item)
                return
        super().mouseDoubleClickEvent(event)

    def open_molecule_builder(self, item):
        """Open the molecule builder for a placed molecule/crystal; on OK it
        rebuilds the model at the chosen orientation, bond length and (if
        edited) structure."""
        from .molview import MoleculeViewer
        dlg = MoleculeViewer(item.mol_name, getattr(item, "mol_az", None),
                             getattr(item, "mol_el", None),
                             getattr(item, "mol_bond", None),
                             getattr(item, "mol_atoms", None),
                             getattr(item, "mol_bonds", None),
                             getattr(item, "mol_repr", None),
                             colors=getattr(item, "mol_colors", None),
                             cells=getattr(item, "mol_cells", None),
                             tilts=getattr(item, "mol_tilts", None),
                             poly=getattr(item, "mol_poly", False),
                             parent=self)
        if dlg.exec():
            atoms, bonds = dlg.result()
            kwargs = dict(bond=dlg.bond, atoms=atoms, bonds=bonds,
                          mode=dlg.representation(),
                          colors=dlg.colors or None)
            if not dlg.editable:
                # crystal: the builder also chooses the supercell + tilts;
                # regrow the build box so the spheres keep a constant size
                from . import molecules
                cells = dlg.cells if dlg.cells != (1, 1, 1) else None
                w_mm, h_mm = molecules.size_mm(item.mol_name)
                ref = getattr(molecules, "REFERENCE_MM", 130.0)
                scale = (self.scene().sceneRect().width() or 1) / ref
                item.mol_box = max(w_mm * scale, h_mm * scale) \
                    * molecules.stack_factor(cells)
                kwargs.update(cells=cells, tilts=dlg.tilts or None,
                              poly=dlg.poly)
            self.scene().reorient_model(item, dlg.az, dlg.el, **kwargs)

    def set_tool_cursor(self, tool: str):
        if tool == POINTER:
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.viewport().setCursor(Qt.ArrowCursor)
        else:
            self.setDragMode(QGraphicsView.NoDrag)
            self.viewport().setCursor(
                Qt.IBeamCursor if tool == TEXT else Qt.CrossCursor)

    # ------------------------------------------------------------ grid
    def drawForeground(self, painter: QPainter, rect: QRectF):
        super().drawForeground(painter, rect)
        scene = self.scene()
        if getattr(scene, "show_grid", False):
            self._draw_grid(painter, rect)
        self._draw_selection(painter)

    def _draw_grid(self, painter: QPainter, rect: QRectF):
        scene = self.scene()
        g = scene.grid_size
        # Infinite paper: the grid fills the whole exposed view; finite
        # paper clips it to the page and draws the page border.
        infinite = getattr(scene, "infinite", False)
        area = rect if infinite else rect.intersected(scene.sceneRect())
        if area.isEmpty():
            return
        painter.setPen(QPen(QColor(120, 144, 168, 70), 0))
        x = math.floor(area.left() / g) * g     # g is a float (exact mm)
        while x <= area.right():
            painter.drawLine(QPointF(x, area.top()),
                             QPointF(x, area.bottom()))
            x += g
        y = math.floor(area.top() / g) * g
        while y <= area.bottom():
            painter.drawLine(QPointF(area.left(), y),
                             QPointF(area.right(), y))
            y += g
        if not infinite:
            painter.setPen(QPen(QColor(120, 144, 168, 160), 0))
            painter.drawRect(scene.sceneRect())

    def _draw_selection(self, painter: QPainter):
        """A cosmetic dashed box around every selected top-level item, so
        a multi-selection is visible (handles only mark a single item).
        Drawn in the foreground, so it never lingers and never exports."""
        from .handles import Handle
        scene = self.scene()
        items = [i for i in scene.selectedItems()
                 if i.parentItem() is None and not isinstance(i, Handle)]
        if not items:
            return
        pen = QPen(QColor("#2176c7"), 0, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for item in items:
            if isinstance(item, LineItem):
                # A line reads as a line, not a box: dash along its own
                # geometry (the curve when bent) — the endpoint handles
                # already mark it, so no bounding rectangle.
                painter.drawPath(
                    item.sceneTransform().map(item.curve_path()))
            else:
                painter.drawRect(
                    item.sceneBoundingRect().adjusted(-1, -1, 1, 1))

    # ------------------------------------------------------------ zoom
    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        else:
            super().wheelEvent(event)

    def zoom(self, factor: float):
        current = self.transform().m11()
        if self.MIN_ZOOM <= current * factor <= self.MAX_ZOOM:
            self.scale(factor, factor)
            self.zoom_changed.emit(self.transform().m11())
            self._update_rulers()

    # ------------------------------------------------------------ rulers
    def set_rulers_visible(self, on: bool):
        """Show/hide the mm edge rulers (reserving viewport margin space)."""
        self._rulers_on = bool(on)
        m = _RulerBar.THICK if on else 0
        self.setViewportMargins(m, m, 0, 0)
        for w in (self._ruler_h, self._ruler_v, self._ruler_corner):
            w.setVisible(bool(on))
        if on:
            self._layout_rulers()
        self._update_rulers()

    def _layout_rulers(self):
        if not self._rulers_on:
            return
        vp = self.viewport().geometry()
        rw = _RulerBar.THICK
        self._ruler_h.setGeometry(vp.x(), vp.y() - rw, vp.width(), rw)
        self._ruler_v.setGeometry(vp.x() - rw, vp.y(), rw, vp.height())
        self._ruler_corner.setGeometry(vp.x() - rw, vp.y() - rw, rw, rw)

    def _update_rulers(self):
        if self._rulers_on:
            self._ruler_h.update()
            self._ruler_v.update()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self._update_rulers()

    def set_zoom(self, scale: float):
        """Set the absolute zoom factor (1.0 == 100%), clamped."""
        scale = max(self.MIN_ZOOM, min(self.MAX_ZOOM, scale))
        self.resetTransform()
        self.scale(scale, scale)
        self.zoom_changed.emit(scale)
        self._update_rulers()

    def current_zoom(self) -> float:
        return self.transform().m11()

    def zoom_reset(self):
        self.resetTransform()
        self.zoom_changed.emit(1.0)
        self._update_rulers()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_rulers()

    def apply_scroll_bounds(self):
        """Let the view scroll across a large empty area when the scene
        is in infinite-paper mode; otherwise follow the page rect. In
        infinite mode the whole canvas is white (no themed surround)."""
        if getattr(self.scene(), "infinite", False):
            m = 100000
            self.setSceneRect(QRectF(-m, -m, 2 * m, 2 * m))
            self.setBackgroundBrush(QBrush(Qt.white))
        else:
            self.setSceneRect(QRectF())   # follow the scene's page rect
            self.setBackgroundBrush(QBrush())   # back to the theme surround

    def mouseMoveEvent(self, event):
        # Forward first so the scene updates the shape being drawn/resized,
        # then emit — the size readout reads the just-updated geometry.
        super().mouseMoveEvent(event)
        sp = self.mapToScene(event.position().toPoint())
        self.cursor_moved.emit(sp)
        if self._rulers_on:
            self._ruler_h.set_cursor(sp.x())
            self._ruler_v.set_cursor(sp.y())

    def keyPressEvent(self, event):
        if self.scene().crop_active():
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.scene().apply_crop()
                return
            if event.key() == Qt.Key_Escape:
                self.scene().cancel_crop()
                return
        if event.key() == Qt.Key_Escape:        # finish a bond chain / orbit
            self.scene().end_chain()
            self.scene().end_angle()
            self.scene()._exit_orbit()
        super().keyPressEvent(event)
