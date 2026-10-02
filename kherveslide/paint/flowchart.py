'''Standard flowchart node symbols (ANSI/ISO) for method & algorithm
workflows.

Each `build_<name>(w, h)` returns a list of shape-spec dicts (the AI/
example format) drawing a symbol inside the box (0,0)-(w,h). Same
`build_specs`/`size_mm`/`REFERENCE_MM` interface as floorplan/electrical.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
'''
import math  # noqa: F401

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
_OUTLINE = "#333333"
_LIGHT = "#eef2f6"
_DECISION = "#fdf0d5"
_DATA = "#e6f0ff"
_WHITE = "#ffffff"

_W_OUTLINE = 2.0
_W_DETAIL = 1.2


def _label(text, w, h, size=None, color=_OUTLINE):
    """A centred caption naming the node, sized to fit the box."""
    if size is None:
        size = max(8.0, min(h * 0.22, w * 0.16))
    return {
        "shape": "text",
        "text": text,
        "x": w / 2.0,
        "y": h / 2.0,
        "size": size,
        "color": color,
        "anchor": "center",
    }


def _hdisc(x, y, w, h, direction, fill=_LIGHT, width=_W_OUTLINE):
    """A half-disc whose FINAL bounding box is (x, y, w, h), bulging towards
    `direction` ('u','d','l','r').  The half-circle primitive bulges up in
    its own box, so for left/right we swap the box dims before the 90/270
    rotation — keeping the disc round instead of squashing it."""
    cx, cy = x + w / 2.0, y + h / 2.0
    if direction == "u":
        bx, by, bw, bh, rot = x, y, w, h, 0
    elif direction == "d":
        bx, by, bw, bh, rot = x, y, w, h, 180
    else:                                  # 'l' / 'r': swap dims, rotate
        bw, bh = h, w
        bx, by = cx - bw / 2.0, cy - bh / 2.0
        rot = 90 if direction == "r" else 270
    return {"shape": "halfcircle", "x": bx, "y": by, "w": bw, "h": bh,
            "stroke": _OUTLINE, "fill": fill, "width": width, "rotation": rot}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def build_process(w, h):
    return [
        {"shape": "rect", "x": 0.0, "y": 0.0, "w": w, "h": h,
         "stroke": _OUTLINE, "fill": _LIGHT, "width": _W_OUTLINE},
        _label("Process", w, h),
    ]


def build_decision(w, h):
    return [
        {"shape": "diamond", "x": 0.0, "y": 0.0, "w": w, "h": h,
         "rotation": 0.0, "stroke": _OUTLINE, "fill": _DECISION,
         "width": _W_OUTLINE},
        _label("Decision", w, h, size=max(8.0, min(h * 0.16, w * 0.13))),
    ]


def build_terminator(w, h):
    return [
        {"shape": "rounded_rect", "x": 0.0, "y": 0.0, "w": w, "h": h,
         "radius": h / 2.0, "stroke": _OUTLINE, "fill": _LIGHT,
         "width": _W_OUTLINE},
        _label("Start / End", w, h, size=max(8.0, min(h * 0.20, w * 0.11))),
    ]


def build_data(w, h):
    return [
        {"shape": "parallelogram", "x": 0.0, "y": 0.0, "w": w, "h": h,
         "rotation": 0.0, "stroke": _OUTLINE, "fill": _DATA,
         "width": _W_OUTLINE},
        _label("Data", w, h),
    ]


def build_document(w, h):
    """Rectangle with a wavy bottom edge (the classic 'document' symbol)."""
    body_h = h * 0.82
    amp = h * 0.10
    specs = [
        # filled body (no border; edges drawn separately so the bottom waves)
        {"shape": "rect", "x": 0.0, "y": 0.0, "w": w, "h": body_h,
         "stroke": "none", "fill": _LIGHT, "width": _W_OUTLINE},
        {"shape": "line", "x1": 0.0, "y1": 0.0, "x2": w, "y2": 0.0,
         "stroke": _OUTLINE, "width": _W_OUTLINE},
        {"shape": "line", "x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": body_h,
         "stroke": _OUTLINE, "width": _W_OUTLINE},
        {"shape": "line", "x1": w, "y1": 0.0, "x2": w, "y2": body_h,
         "stroke": _OUTLINE, "width": _W_OUTLINE},
    ]
    # wavy bottom edge as a sine polyline
    n = 24
    pts = [(w * (i / n), body_h + amp * math.sin((i / n) * 2 * math.pi))
           for i in range(n + 1)]
    for i in range(len(pts) - 1):
        specs.append({"shape": "line", "x1": pts[i][0], "y1": pts[i][1],
                      "x2": pts[i + 1][0], "y2": pts[i + 1][1],
                      "stroke": _OUTLINE, "width": _W_OUTLINE})
    specs.append(_label("Document", w, h, size=max(8.0, min(h * 0.18, w * 0.12))))
    return specs


def build_predefined_process(w, h):
    """Rectangle with double vertical bars near the left/right edges."""
    bar = w * 0.12
    return [
        {"shape": "rect", "x": 0.0, "y": 0.0, "w": w, "h": h,
         "stroke": _OUTLINE, "fill": _LIGHT, "width": _W_OUTLINE},
        {"shape": "line", "x1": bar, "y1": 0.0, "x2": bar, "y2": h,
         "stroke": _OUTLINE, "width": _W_DETAIL},
        {"shape": "line", "x1": w - bar, "y1": 0.0, "x2": w - bar, "y2": h,
         "stroke": _OUTLINE, "width": _W_DETAIL},
        _label("Process", w, h),
    ]


def build_preparation(w, h):
    return [
        {"shape": "hexagon", "x": 0.0, "y": 0.0, "w": w, "h": h,
         "rotation": 0.0, "stroke": _OUTLINE, "fill": _LIGHT,
         "width": _W_OUTLINE},
        _label("Prepare", w, h),
    ]


def build_manual_input(w, h):
    """Quadrilateral with a slanted top edge (trapezoid rotated 180°)."""
    return [
        {"shape": "trapezoid", "x": 0.0, "y": 0.0, "w": w, "h": h,
         "rotation": 180.0, "stroke": _OUTLINE, "fill": _DATA,
         "width": _W_OUTLINE},
        _label("Input", w, h),
    ]


def build_database(w, h):
    """Cylinder: rect body + ellipse top rim + curved (halfcircle) bottom."""
    rim = h * 0.22
    body_top = rim / 2.0
    body_bot = h - rim / 2.0
    specs = [
        # body fill (between the rims) + side lines
        {"shape": "rect", "x": 0.0, "y": body_top, "w": w, "h": body_bot - body_top,
         "stroke": "none", "fill": _LIGHT, "width": _W_OUTLINE},
        {"shape": "line", "x1": 0.0, "y1": body_top, "x2": 0.0, "y2": body_bot,
         "stroke": _OUTLINE, "width": _W_OUTLINE},
        {"shape": "line", "x1": w, "y1": body_top, "x2": w, "y2": body_bot,
         "stroke": _OUTLINE, "width": _W_OUTLINE},
        # curved bottom (front of the cylinder, bulging down)
        _hdisc(0.0, body_bot - rim / 2.0, w, rim, "d", _LIGHT),
        # top rim ellipse
        {"shape": "ellipse", "x": 0.0, "y": 0.0, "w": w, "h": rim,
         "stroke": _OUTLINE, "fill": _LIGHT, "width": _W_OUTLINE},
    ]
    specs.append(_label("Database", w, h, size=max(8.0, min(h * 0.16, w * 0.13))))
    return specs


def build_stored_data(w, h):
    """Rectangle with a curved left side (stored-data symbol)."""
    bulge = w * 0.16
    return [
        # body fill + top/bottom/right edges
        {"shape": "rect", "x": bulge, "y": 0.0, "w": w - bulge, "h": h,
         "stroke": "none", "fill": _DATA, "width": _W_OUTLINE},
        {"shape": "line", "x1": bulge, "y1": 0.0, "x2": w, "y2": 0.0,
         "stroke": _OUTLINE, "width": _W_OUTLINE},
        {"shape": "line", "x1": bulge, "y1": h, "x2": w, "y2": h,
         "stroke": _OUTLINE, "width": _W_OUTLINE},
        {"shape": "line", "x1": w, "y1": 0.0, "x2": w, "y2": h,
         "stroke": _OUTLINE, "width": _W_OUTLINE},
        # curved left side bulging left (flat edge meets the body at x=bulge)
        _hdisc(0.0, 0.0, bulge, h, "l", _DATA),
        _label("Data", w + bulge, h),     # nudge label right of the curve
    ]


def build_connector(w, h):
    return [
        {"shape": "circle", "x": 0.0, "y": 0.0, "w": w, "h": h,
         "stroke": _OUTLINE, "fill": _LIGHT, "width": _W_OUTLINE},
        _label("A", w, h, size=max(8.0, min(h * 0.42, w * 0.42))),
    ]


def build_display(w, h):
    """Display symbol: a curved (rounded) left end and a rounded right end."""
    cap = h * 0.5                  # left half-disc radius worth of width
    bump = w * 0.18                # right rounded snout
    body_x = cap
    body_w = w - cap - bump
    return [
        # straight body fill between the two curved ends
        {"shape": "rect", "x": body_x, "y": 0.0, "w": body_w, "h": h,
         "stroke": "none", "fill": _LIGHT, "width": _W_OUTLINE},
        {"shape": "line", "x1": body_x, "y1": 0.0,
         "x2": body_x + body_w, "y2": 0.0, "stroke": _OUTLINE,
         "width": _W_OUTLINE},
        {"shape": "line", "x1": body_x, "y1": h,
         "x2": body_x + body_w, "y2": h, "stroke": _OUTLINE,
         "width": _W_OUTLINE},
        # curved left end (bulging left)
        _hdisc(0.0, 0.0, cap, h, "l", _LIGHT),
        # rounded right snout (bulging right)
        _hdisc(body_x + body_w, 0.0, bump, h, "r", _LIGHT),
        _label("Display", w, h, size=max(8.0, min(h * 0.20, w * 0.13))),
    ]


# ---------------------------------------------------------------------------
# Connectors
# ---------------------------------------------------------------------------
def build_flow_arrow(w, h):
    return [
        {"shape": "arrow", "x1": 0.0, "y1": h / 2.0, "x2": w, "y2": h / 2.0,
         "stroke": _OUTLINE, "width": _W_OUTLINE},
    ]


def build_flow_line(w, h):
    return [
        {"shape": "line", "x1": 0.0, "y1": h / 2.0, "x2": w, "y2": h / 2.0,
         "stroke": _OUTLINE, "width": _W_OUTLINE},
    ]


# ---------------------------------------------------------------------------
# Sizes (mm), labels, categories
# ---------------------------------------------------------------------------
REFERENCE_MM = 1400.0

SIZES = {
    "process": (200.0, 100.0),
    "decision": (160.0, 140.0),
    "terminator": (200.0, 90.0),
    "data": (200.0, 100.0),
    "document": (200.0, 110.0),
    "predefined_process": (200.0, 100.0),
    "preparation": (200.0, 110.0),
    "manual_input": (200.0, 100.0),
    "database": (140.0, 150.0),
    "stored_data": (160.0, 110.0),
    "connector": (70.0, 70.0),
    "display": (200.0, 110.0),
    "flow_arrow": (180.0, 30.0),
    "flow_line": (180.0, 20.0),
}

LABELS = {
    "process": "Process",
    "decision": "Decision",
    "terminator": "Terminator (Start/End)",
    "data": "Data (I/O)",
    "document": "Document",
    "predefined_process": "Predefined process",
    "preparation": "Preparation",
    "manual_input": "Manual input",
    "database": "Database",
    "stored_data": "Stored data",
    "connector": "Connector",
    "display": "Display",
    "flow_arrow": "Flow arrow",
    "flow_line": "Flow line",
}

CATEGORIES = [
    ("Nodes", ["process", "decision", "terminator", "data", "document",
               "predefined_process", "preparation", "manual_input"]),
    ("Data & storage", ["database", "stored_data", "connector", "display"]),
    ("Connectors", ["flow_arrow", "flow_line"]),
]


_BUILDERS = {name: globals()["build_" + name] for name in SIZES}


def build_specs(name, w, h):
    return _BUILDERS[name](w, h)


def size_mm(name):
    return SIZES[name]
