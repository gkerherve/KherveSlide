"""Chemistry drawing geometry: bond paths and ring polygons.

Pure geometry only (no item classes) so `canvas` can import it without a
cycle. The scene builds native items (`PathItem`, `PolygonItem`,
`EllipseItem`, `TextItem`) from these shapes — so every bond/ring/atom is
a normal, editable, SVG-round-tripping item.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import math

from PySide6.QtCore import QLineF, QPointF
from PySide6.QtGui import QPainterPath, QPolygonF

#: Common atom / group labels offered by the atom tool.
ATOMS = ["C", "H", "O", "N", "S", "P", "F", "Cl", "Br",
         "OH", "CH3", "CH2", "NH2", "COOH", "R"]

#: Ring tool kind -> number of vertices.
_RING_SIDES = {"benzene": 6, "cyclohexane": 6, "cyclopentane": 5}


def _perp(p1: QPointF, p2: QPointF) -> QPointF:
    """Unit vector perpendicular to p1->p2."""
    ang = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
    return QPointF(math.sin(ang), -math.cos(ang))


def bond_path(kind: str, p1: QPointF, p2: QPointF, gap: float) -> QPainterPath:
    """A bond as a QPainterPath: single line, double/triple parallel lines,
    or a hashed (going-back) wedge of perpendicular ticks."""
    path = QPainterPath()
    if QLineF(p1, p2).length() < 1:
        return path
    perp = _perp(p1, p2)
    if kind == "single":
        path.moveTo(p1); path.lineTo(p2)
    elif kind == "double":
        for s in (perp * (gap * 0.5), perp * (-gap * 0.5)):
            path.moveTo(p1 + s); path.lineTo(p2 + s)
    elif kind == "triple":
        for s in (perp * gap, QPointF(0, 0), perp * -gap):
            path.moveTo(p1 + s); path.lineTo(p2 + s)
    elif kind == "hash":
        length = QLineF(p1, p2).length()
        n = max(3, int(length / max(gap * 1.6, 1)))
        for i in range(1, n + 1):
            t = i / (n + 1)
            c = QPointF(p1.x() + (p2.x() - p1.x()) * t,
                        p1.y() + (p2.y() - p1.y()) * t)
            w = perp * (gap * 0.4 + gap * 1.4 * t)   # widens toward p2
            path.moveTo(c - w); path.lineTo(c + w)
    elif kind == "hbond":
        # Hydrogen bond: a dashed line built from short segments, so the
        # dashes are geometry and survive an SVG round-trip (no pen dash).
        length = QLineF(p1, p2).length()
        unit = QPointF((p2.x() - p1.x()) / length, (p2.y() - p1.y()) / length)
        dash, space = max(gap * 1.4, 4.0), max(gap, 3.0)
        d = 0.0
        while d < length:
            a = p1 + unit * d
            b = p1 + unit * min(d + dash, length)
            path.moveTo(a); path.lineTo(b)
            d += dash + space
    return path


def wedge_polygon(p1: QPointF, p2: QPointF, gap: float) -> QPolygonF:
    """A solid (coming-forward) stereo bond: a filled triangle, narrow at
    p1 and wide at p2."""
    w = _perp(p1, p2) * gap
    return QPolygonF([QPointF(p1), p2 + w, p2 - w])


def ring_polygon(kind: str, center: QPointF, r: float) -> QPolygonF:
    """Vertices of a ring (regular polygon) centred at *center*, vertex up."""
    sides = _RING_SIDES.get(kind, 6)
    pts = []
    for i in range(sides):
        ang = -math.pi / 2 + i * 2 * math.pi / sides
        pts.append(QPointF(center.x() + r * math.cos(ang),
                           center.y() + r * math.sin(ang)))
    return QPolygonF(pts)


def is_aromatic(kind: str) -> bool:
    return kind == "benzene"
