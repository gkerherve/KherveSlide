'''Math, graph-axes, vector and symbol glyphs.

Each `build_<name>(w, h)` returns a list of shape-spec dicts (the AI/
example format) drawing a symbol inside the box (0,0)-(w,h). Same
`build_specs`/`size_mm`/`REFERENCE_MM` interface as floorplan/electrical.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
'''
import math

_OUTLINE = "#333333"
_CURVE = "#2b6cb0"
_VECTOR = "#d9534f"
_GRID = "#c8ced6"


def build_axes_2d(w, h):
    ox, oy = w * 0.15, h * 0.85
    specs = [
        {"shape": "arrow", "x1": ox, "y1": oy, "x2": w * 0.95, "y2": oy,
         "stroke": _OUTLINE, "width": 2},
        {"shape": "arrow", "x1": ox, "y1": oy, "x2": ox, "y2": h * 0.08,
         "stroke": _OUTLINE, "width": 2},
        {"shape": "text", "text": "x", "x": w * 0.97, "y": oy - h * 0.08,
         "size": min(w, h) * 0.12, "color": _OUTLINE},
        {"shape": "text", "text": "y", "x": ox + w * 0.07, "y": h * 0.08,
         "size": min(w, h) * 0.12, "color": _OUTLINE},
    ]
    return specs


def build_axes_3d(w, h):
    ox, oy = w * 0.4, h * 0.5
    specs = [
        {"shape": "arrow", "x1": ox, "y1": oy, "x2": w * 0.95, "y2": oy,
         "stroke": _OUTLINE, "width": 2},
        {"shape": "arrow", "x1": ox, "y1": oy, "x2": ox, "y2": h * 0.08,
         "stroke": _OUTLINE, "width": 2},
        {"shape": "arrow", "x1": ox, "y1": oy, "x2": w * 0.08, "y2": h * 0.92,
         "stroke": _OUTLINE, "width": 2},
        {"shape": "text", "text": "x", "x": w * 0.97, "y": oy - h * 0.07,
         "size": min(w, h) * 0.11, "color": _OUTLINE},
        {"shape": "text", "text": "y", "x": ox + w * 0.07, "y": h * 0.08,
         "size": min(w, h) * 0.11, "color": _OUTLINE},
        {"shape": "text", "text": "z", "x": w * 0.05, "y": h * 0.97,
         "size": min(w, h) * 0.11, "color": _OUTLINE},
    ]
    return specs


def build_number_line(w, h):
    cy = h * 0.5
    ox = w * 0.08
    specs = [
        {"shape": "arrow", "x1": ox, "y1": cy, "x2": w * 0.95, "y2": cy,
         "stroke": _OUTLINE, "width": 2},
    ]
    labels = ["-1", "0", "1", "2"]
    n = len(labels)
    span = w * 0.78
    start = w * 0.12
    for i, lab in enumerate(labels):
        tx = start + span * (i / (n - 1))
        specs.append({"shape": "line", "x1": tx, "y1": cy - h * 0.08,
                      "x2": tx, "y2": cy + h * 0.08,
                      "stroke": _OUTLINE, "width": 1.5})
        specs.append({"shape": "text", "text": lab, "x": tx,
                      "y": cy + h * 0.25, "size": min(w, h) * 0.16,
                      "color": _OUTLINE, "anchor": "center"})
    return specs


def build_grid_graph(w, h):
    ox, oy = w * 0.15, h * 0.85
    specs = []
    n = 4
    gx0, gx1 = ox, w * 0.92
    gy0, gy1 = h * 0.1, oy
    for i in range(1, n + 1):
        x = gx0 + (gx1 - gx0) * (i / n)
        specs.append({"shape": "line", "x1": x, "y1": gy0, "x2": x, "y2": gy1,
                      "stroke": _GRID, "width": 1.5})
    for i in range(0, n):
        y = gy0 + (gy1 - gy0) * (i / n)
        specs.append({"shape": "line", "x1": gx0, "y1": y, "x2": gx1, "y2": y,
                      "stroke": _GRID, "width": 1.5})
    specs.append({"shape": "arrow", "x1": ox, "y1": oy, "x2": w * 0.95,
                  "y2": oy, "stroke": _OUTLINE, "width": 2})
    specs.append({"shape": "arrow", "x1": ox, "y1": oy, "x2": ox,
                  "y2": h * 0.08, "stroke": _OUTLINE, "width": 2})
    return specs


def build_curve(w, h):
    ox, oy = w * 0.15, h * 0.85
    specs = [
        {"shape": "arrow", "x1": ox, "y1": oy, "x2": w * 0.95, "y2": oy,
         "stroke": _OUTLINE, "width": 2},
        {"shape": "arrow", "x1": ox, "y1": oy, "x2": ox, "y2": h * 0.08,
         "stroke": _OUTLINE, "width": 2},
    ]
    x0, x1 = w * 0.18, w * 0.92
    ytop, ybot = h * 0.12, h * 0.82
    samples = 24
    pts = []
    for i in range(samples + 1):
        t = i / samples
        px = x0 + (x1 - x0) * t
        s = 0.5 * (1.0 + math.sin(math.pi * (2.0 * t - 0.5)))
        py = ybot - (ybot - ytop) * s
        pts.append((px, py))
    for i in range(len(pts) - 1):
        x1p, y1p = pts[i]
        x2p, y2p = pts[i + 1]
        specs.append({"shape": "line", "x1": x1p, "y1": y1p,
                      "x2": x2p, "y2": y2p, "stroke": _CURVE, "width": 2})
    return specs


def build_vector(w, h):
    specs = [
        {"shape": "arrow", "x1": w * 0.15, "y1": h * 0.85,
         "x2": w * 0.85, "y2": h * 0.18, "stroke": _VECTOR, "width": 2},
        {"shape": "text", "text": "v", "x": w * 0.78, "y": h * 0.32,
         "size": min(w, h) * 0.14, "color": _VECTOR},
    ]
    return specs


def build_angle_arc(w, h):
    vx, vy = w * 0.15, h * 0.85
    specs = [
        {"shape": "line", "x1": vx, "y1": vy, "x2": w * 0.92, "y2": vy,
         "stroke": _OUTLINE, "width": 2},
        {"shape": "line", "x1": vx, "y1": vy, "x2": w * 0.85, "y2": h * 0.2,
         "stroke": _OUTLINE, "width": 2},
    ]
    r = min(w, h) * 0.32
    a0 = 0.0
    a1 = math.atan2(vy - h * 0.2, w * 0.85 - vx)
    samples = 12
    arc = []
    for i in range(samples + 1):
        a = a0 + (a1 - a0) * (i / samples)
        arc.append((vx + r * math.cos(a), vy - r * math.sin(a)))
    for i in range(len(arc) - 1):
        x1p, y1p = arc[i]
        x2p, y2p = arc[i + 1]
        specs.append({"shape": "line", "x1": x1p, "y1": y1p,
                      "x2": x2p, "y2": y2p, "stroke": _OUTLINE, "width": 1.5})
    mid = (a0 + a1) * 0.5
    tr = r * 1.4
    specs.append({"shape": "text", "text": "θ",
                  "x": vx + tr * math.cos(mid),
                  "y": vy - tr * math.sin(mid),
                  "size": min(w, h) * 0.16, "color": _OUTLINE})
    return specs


def build_right_angle(w, h):
    vx, vy = w * 0.18, h * 0.82
    specs = [
        {"shape": "line", "x1": vx, "y1": vy, "x2": w * 0.92, "y2": vy,
         "stroke": _OUTLINE, "width": 2},
        {"shape": "line", "x1": vx, "y1": vy, "x2": vx, "y2": h * 0.1,
         "stroke": _OUTLINE, "width": 2},
    ]
    s = min(w, h) * 0.18
    specs.append({"shape": "line", "x1": vx + s, "y1": vy,
                  "x2": vx + s, "y2": vy - s, "stroke": _OUTLINE,
                  "width": 1.5})
    specs.append({"shape": "line", "x1": vx, "y1": vy - s,
                  "x2": vx + s, "y2": vy - s, "stroke": _OUTLINE,
                  "width": 1.5})
    return specs


def build_brace(w, h):
    specs = [
        {"shape": "text", "text": "{", "x": w * 0.5, "y": h * 0.5,
         "size": h * 0.95, "color": _OUTLINE, "anchor": "center"},
    ]
    return specs


def _glyph(w, h, glyph, color=_OUTLINE):
    return [
        {"shape": "text", "text": glyph, "x": w * 0.5, "y": h * 0.5,
         "size": min(w, h) * 0.7, "color": color, "anchor": "center"},
    ]


def build_sum(w, h):
    return _glyph(w, h, "Σ")


def build_integral(w, h):
    return _glyph(w, h, "∫")


def build_pi(w, h):
    return _glyph(w, h, "π")


def build_infinity(w, h):
    return _glyph(w, h, "∞")


def build_delta(w, h):
    return _glyph(w, h, "Δ")


def build_theta(w, h):
    return _glyph(w, h, "θ")


REFERENCE_MM = 1000.0

SIZES = {
    "axes_2d": (220.0, 200.0),
    "axes_3d": (220.0, 200.0),
    "number_line": (220.0, 200.0),
    "grid_graph": (220.0, 200.0),
    "curve": (220.0, 200.0),
    "vector": (200.0, 200.0),
    "angle_arc": (200.0, 200.0),
    "right_angle": (200.0, 200.0),
    "brace": (120.0, 120.0),
    "sum": (120.0, 120.0),
    "integral": (120.0, 120.0),
    "pi": (120.0, 120.0),
    "infinity": (120.0, 120.0),
    "delta": (120.0, 120.0),
    "theta": (120.0, 120.0),
}

LABELS = {
    "axes_2d": "2D axes",
    "axes_3d": "3D axes",
    "number_line": "Number line",
    "grid_graph": "Grid graph",
    "curve": "Curve plot",
    "vector": "Vector",
    "angle_arc": "Angle",
    "right_angle": "Right angle",
    "brace": "Brace {",
    "sum": "Sum Σ",
    "integral": "Integral ∫",
    "pi": "Pi π",
    "infinity": "Infinity ∞",
    "delta": "Delta Δ",
    "theta": "Theta θ",
}

CATEGORIES = [
    ("Axes & graphs", ["axes_2d", "axes_3d", "number_line", "grid_graph",
                       "curve"]),
    ("Vectors & angles", ["vector", "angle_arc", "right_angle", "brace"]),
    ("Symbols", ["sum", "integral", "pi", "infinity", "delta", "theta"]),
]

_BUILDERS = {name: globals()["build_" + name] for name in SIZES}


def build_specs(name, w, h):
    return _BUILDERS[name](w, h)


def size_mm(name):
    return SIZES[name]
