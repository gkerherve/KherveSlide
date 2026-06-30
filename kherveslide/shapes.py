"""Vector-shape geometry shared by the canvas (QPainterPath) and the
serializer (tikz). Every shape is defined in a normalised box: coordinates
run 0..1 with (0,0) at the top-left and (1,1) at the bottom-right, so the
same outline fills whatever box the user draws — the canvas and the PDF
agree pixel-for-pixel.
"""
from __future__ import annotations

import math


def _regular(n: int, rot: float = 0.0) -> list[tuple[float, float]]:
    """A regular n-gon inscribed in the unit box, first vertex at the top."""
    pts = []
    for k in range(n):
        a = math.radians(-90 + rot + k * 360.0 / n)
        pts.append((0.5 + 0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a)))
    return pts


def _star(points: int, inner: float = 0.4) -> list[tuple[float, float]]:
    pts = []
    for k in range(points * 2):
        r = 0.5 if k % 2 == 0 else inner
        a = math.radians(-90 + k * 180.0 / points)
        pts.append((0.5 + r * math.cos(a), 0.5 + r * math.sin(a)))
    return pts


# Polygon outlines (closed) keyed by shape name. Curved shapes (ellipse,
# circle) and the plain/rounded rectangle are handled separately.
_POLY: dict[str, list[tuple[float, float]]] = {
    "triangle": [(0.5, 0.0), (1.0, 1.0), (0.0, 1.0)],
    "right_triangle": [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0)],
    "diamond": [(0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5)],
    "parallelogram": [(0.25, 0.0), (1.0, 0.0), (0.75, 1.0), (0.0, 1.0)],
    "trapezoid": [(0.2, 0.0), (0.8, 0.0), (1.0, 1.0), (0.0, 1.0)],
    "pentagon": _regular(5),
    "hexagon": _regular(6),
    "heptagon": _regular(7),
    "octagon": _regular(8),
    "star5": _star(5),
    "star6": _star(6),
    "star4": _star(4, inner=0.34),
    "arrow_right": [(0.0, 0.32), (0.6, 0.32), (0.6, 0.06), (1.0, 0.5),
                    (0.6, 0.94), (0.6, 0.68), (0.0, 0.68)],
    "arrow_left": [(1.0, 0.32), (0.4, 0.32), (0.4, 0.06), (0.0, 0.5),
                   (0.4, 0.94), (0.4, 0.68), (1.0, 0.68)],
    "arrow_up": [(0.32, 1.0), (0.32, 0.4), (0.06, 0.4), (0.5, 0.0),
                 (0.94, 0.4), (0.68, 0.4), (0.68, 1.0)],
    "arrow_down": [(0.32, 0.0), (0.32, 0.6), (0.06, 0.6), (0.5, 1.0),
                   (0.94, 0.6), (0.68, 0.6), (0.68, 0.0)],
    "double_arrow": [(0.0, 0.5), (0.22, 0.08), (0.22, 0.32), (0.78, 0.32),
                     (0.78, 0.08), (1.0, 0.5), (0.78, 0.92), (0.78, 0.68),
                     (0.22, 0.68), (0.22, 0.92)],
    "chevron": [(0.0, 0.0), (0.72, 0.0), (1.0, 0.5), (0.72, 1.0),
                (0.0, 1.0), (0.28, 0.5)],
    "pentagon_arrow": [(0.0, 0.0), (0.72, 0.0), (1.0, 0.5), (0.72, 1.0),
                       (0.0, 1.0)],
    "plus": [(0.34, 0.0), (0.66, 0.0), (0.66, 0.34), (1.0, 0.34),
             (1.0, 0.66), (0.66, 0.66), (0.66, 1.0), (0.34, 1.0),
             (0.34, 0.66), (0.0, 0.66), (0.0, 0.34), (0.34, 0.34)],
    "lightning": [(0.55, 0.0), (0.2, 0.55), (0.45, 0.55), (0.3, 1.0),
                  (0.8, 0.4), (0.5, 0.4), (0.7, 0.0)],
    "speech": [(0.0, 0.0), (1.0, 0.0), (1.0, 0.75), (0.45, 0.75),
               (0.2, 1.0), (0.25, 0.75), (0.0, 0.75)],
}

# Display name + grouping for the Shapes menu / picker.
GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Rectangles", [
        ("rect", "Rectangle"), ("rounded_rect", "Rounded rectangle")]),
    ("Basic", [
        ("ellipse", "Ellipse"), ("circle", "Circle"),
        ("triangle", "Triangle"), ("right_triangle", "Right triangle"),
        ("diamond", "Diamond"), ("parallelogram", "Parallelogram"),
        ("trapezoid", "Trapezoid"), ("plus", "Cross / plus")]),
    ("Polygons", [
        ("pentagon", "Pentagon"), ("hexagon", "Hexagon"),
        ("heptagon", "Heptagon"), ("octagon", "Octagon")]),
    ("Arrows", [
        ("arrow_right", "Arrow right"), ("arrow_left", "Arrow left"),
        ("arrow_up", "Arrow up"), ("arrow_down", "Arrow down"),
        ("double_arrow", "Double arrow"), ("chevron", "Chevron"),
        ("pentagon_arrow", "Arrow pentagon")]),
    ("Stars & symbols", [
        ("star4", "4-point star"), ("star5", "5-point star"),
        ("star6", "6-point star"), ("lightning", "Lightning"),
        ("speech", "Speech bubble")]),
]

# Flat name → label and an ordered list of all keys.
LABELS: dict[str, str] = {k: lbl for _g, items in GROUPS for k, lbl in items}
ALL: list[str] = list(LABELS)


def outline(shape: str):
    """Return a structured description of *shape*:
    ('ellipse',) | ('rect', rounded_bool) | ('poly', [(x, y), ...])."""
    if shape in ("ellipse", "circle"):
        return ("ellipse",)
    if shape == "rounded_rect":
        return ("rect", True)
    if shape == "rect":
        return ("rect", False)
    pts = _POLY.get(shape)
    if pts is not None:
        return ("poly", pts)
    return ("rect", False)


def qt_path(shape: str, rect):
    """Build a QPainterPath for *shape* filling *rect* (a QRectF)."""
    from PySide6.QtGui import QPainterPath
    kind = outline(shape)
    path = QPainterPath()
    if kind[0] == "ellipse":
        path.addEllipse(rect)
    elif kind[0] == "rect":
        if kind[1]:
            r = min(rect.width(), rect.height()) * 0.14
            path.addRoundedRect(rect, r, r)
        else:
            path.addRect(rect)
    else:
        pts = kind[1]
        path.moveTo(rect.x() + pts[0][0] * rect.width(),
                    rect.y() + pts[0][1] * rect.height())
        for nx, ny in pts[1:]:
            path.lineTo(rect.x() + nx * rect.width(),
                        rect.y() + ny * rect.height())
        path.closeSubpath()
    return path
