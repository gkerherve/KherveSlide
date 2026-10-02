'''Annotation arrows, callouts and banners.

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

OUTLINE = "#333333"
FILL = "#dfe7ee"
ACCENT = "#cfe0f5"


def _tri(cx, cy, length, base, direction, fill=FILL):
    """Filled triangle, apex at (cx, cy), reaching `length` in `direction`
    ('l','r','u','d'); box dims swapped before 90/270 so it isn't squashed."""
    if direction in ("u", "d"):
        if direction == "u":
            x, y, rot = cx - base * 0.5, cy, 0
        else:
            x, y, rot = cx - base * 0.5, cy - length, 180
        return {"shape": "triangle", "x": x, "y": y, "w": base, "h": length,
                "stroke": OUTLINE, "fill": fill, "width": 2, "rotation": rot}
    if direction == "r":
        cxb, rot = cx - length * 0.5, 90
    else:
        cxb, rot = cx + length * 0.5, 270
    return {"shape": "triangle", "x": cxb - base * 0.5, "y": cy - length * 0.5,
            "w": base, "h": length, "stroke": OUTLINE, "fill": fill,
            "width": 2, "rotation": rot}


def build_arrow_right(w, h):
    return [{"shape": "arrow_right", "x": 0.0, "y": 0.0, "w": w, "h": h,
             "rotation": 0.0, "stroke": OUTLINE, "fill": FILL, "width": 2}]


def build_arrow_left(w, h):
    return [{"shape": "arrow_right", "x": 0.0, "y": 0.0, "w": w, "h": h,
             "rotation": 180.0, "stroke": OUTLINE, "fill": FILL, "width": 2}]


def build_arrow_up(w, h):
    return [{"shape": "arrow_right", "x": 0.0, "y": 0.0, "w": w, "h": h,
             "rotation": 270.0, "stroke": OUTLINE, "fill": FILL, "width": 2}]


def build_arrow_down(w, h):
    return [{"shape": "arrow_right", "x": 0.0, "y": 0.0, "w": w, "h": h,
             "rotation": 90.0, "stroke": OUTLINE, "fill": FILL, "width": 2}]


def build_double_arrow(w, h):
    head = w * 0.26
    cy = h * 0.5
    shaft_h = h * 0.42
    return [
        {"shape": "rect", "x": head, "y": cy - shaft_h * 0.5,
         "w": w - 2 * head, "h": shaft_h,
         "stroke": OUTLINE, "fill": FILL, "width": 2},
        _tri(0.0, cy, head, h, "l"),        # left head, apex at far left
        _tri(w, cy, head, h, "r"),          # right head, apex at far right
    ]


def _head(tipx, tipy, ang, size, fill=FILL):
    """Filled arrowhead, apex at (tipx, tipy), pointing along `ang` (rad).
    A square box keeps it undistorted under arbitrary rotation."""
    cx = tipx - size * 0.5 * math.cos(ang)
    cy = tipy - size * 0.5 * math.sin(ang)
    return {"shape": "triangle", "x": cx - size * 0.5, "y": cy - size * 0.5,
            "w": size, "h": size, "rotation": math.degrees(ang) + 90,
            "stroke": OUTLINE, "fill": fill, "width": 2}


def build_curved_arrow(w, h):
    """A smooth ~110° arc with a filled arrowhead tangent at its tip."""
    cx, cy = w * 0.18, h * 0.82
    rx, ry = w * 0.66, h * 0.66
    a0, a1 = math.radians(-100), math.radians(8)
    n = 24
    pts = [(cx + rx * math.cos(a0 + (a1 - a0) * i / n),
            cy + ry * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    specs = [{"shape": "line", "x1": pts[i][0], "y1": pts[i][1],
              "x2": pts[i + 1][0], "y2": pts[i + 1][1],
              "stroke": OUTLINE, "width": 2} for i in range(len(pts) - 1)]
    ex, ey = pts[-1]
    px, py = pts[-2]
    specs.append(_head(ex, ey, math.atan2(ey - py, ex - px), min(w, h) * 0.28))
    return specs


def build_bent_arrow(w, h):
    sw = min(w, h) * 0.16
    head = min(w, h) * 0.3
    vx = w - sw - head * 0.5
    return [
        {"shape": "rect", "x": 0.0, "y": h - sw, "w": vx + sw, "h": sw,
         "stroke": OUTLINE, "fill": FILL, "width": 2},
        {"shape": "rect", "x": vx, "y": head, "w": sw, "h": h - head - sw,
         "stroke": OUTLINE, "fill": FILL, "width": 2},
        {"shape": "triangle", "x": vx + sw / 2 - head / 2, "y": 0.0,
         "w": head, "h": head, "rotation": 0.0,
         "stroke": OUTLINE, "fill": FILL, "width": 2},
    ]


def build_circular_arrow(w, h):
    """A cycle/refresh arrow: a ~300° ring drawn as a polyline + a V head."""
    cx, cy = w * 0.5, h * 0.52
    rx, ry = w * 0.36, h * 0.36
    a0, a1 = math.radians(70), math.radians(70 + 300)   # gap at the top
    n = 28
    pts = [(cx + rx * math.cos(a0 + (a1 - a0) * i / n),
            cy + ry * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    specs = [{"shape": "line", "x1": pts[i][0], "y1": pts[i][1],
              "x2": pts[i + 1][0], "y2": pts[i + 1][1],
              "stroke": OUTLINE, "width": 2} for i in range(len(pts) - 1)]
    # V arrowhead at the end, along the tangent
    end, prev = pts[-1], pts[-2]
    ang = math.atan2(end[1] - prev[1], end[0] - prev[0])
    hd = min(w, h) * 0.18
    for da in (math.radians(150), math.radians(-150)):
        specs.append({"shape": "line", "x1": end[0], "y1": end[1],
                      "x2": end[0] + hd * math.cos(ang + da),
                      "y2": end[1] + hd * math.sin(ang + da),
                      "stroke": OUTLINE, "width": 2})
    return specs


def build_callout_rect(w, h):
    body_h = h * 0.78
    tail_w = w * 0.18
    tail_x = w * 0.15
    return [
        {"shape": "rect", "x": 0.0, "y": 0.0, "w": w, "h": body_h,
         "stroke": OUTLINE, "fill": FILL, "width": 2},
        {"shape": "triangle", "x": tail_x, "y": body_h, "w": tail_w,
         "h": h - body_h, "rotation": 180.0,
         "stroke": OUTLINE, "fill": FILL, "width": 2},
    ]


def build_callout_round(w, h):
    body_h = h * 0.78
    tail_w = w * 0.18
    tail_x = w * 0.15
    return [
        {"shape": "rounded_rect", "x": 0.0, "y": 0.0, "w": w, "h": body_h,
         "radius": min(w, body_h) * 0.18, "stroke": OUTLINE, "fill": FILL,
         "width": 2},
        {"shape": "triangle", "x": tail_x, "y": body_h, "w": tail_w,
         "h": h - body_h, "rotation": 180.0,
         "stroke": OUTLINE, "fill": FILL, "width": 2},
    ]


def build_banner(w, h):
    """A ribbon banner: a rectangle with a fishtail (V-notch) cut into each
    short end."""
    notch = w * 0.10
    cy = h * 0.5
    specs = [
        # body fill (border drawn separately so the ends can be notched)
        {"shape": "rect", "x": 0.0, "y": 0.0, "w": w, "h": h,
         "stroke": "none", "fill": FILL, "width": 2},
        # carve the two fishtail notches with background-coloured triangles
        dict(_tri(notch, cy, notch, h, "r"), stroke="none", fill="#ffffff"),
        dict(_tri(w - notch, cy, notch, h, "l"), stroke="none", fill="#ffffff"),
    ]
    # outline of the resulting banner (6 segments)
    pts = [(0.0, 0.0), (w, 0.0), (w - notch, cy), (w, h), (0.0, h),
           (notch, cy)]
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        specs.append({"shape": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                      "stroke": OUTLINE, "width": 2})
    return specs


def build_burst(w, h):
    return [
        {"shape": "star", "x": 0.0, "y": 0.0, "w": w, "h": h,
         "rotation": 0.0, "stroke": OUTLINE, "fill": ACCENT, "width": 2},
        {"shape": "text", "text": "NEW!", "x": w * 0.5, "y": h * 0.5,
         "size": h * 0.18, "color": OUTLINE, "anchor": "center"},
    ]


# ---------------------------------------------------------------------------
# Thin line connectors (same look as the straight arrow tool, but curved /
# bent).  Drawn as a thin polyline + a small solid arrowhead at the tip.
# ---------------------------------------------------------------------------
def _seg(x1, y1, x2, y2):
    return {"shape": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "stroke": OUTLINE, "width": 2}


def _polyline_head(pts, hsize):
    """Line specs through `pts` plus a solid arrowhead on the last segment."""
    specs = [_seg(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
             for i in range(len(pts) - 1)]
    ex, ey = pts[-1]
    px, py = pts[-2]
    specs.append(_head(ex, ey, math.atan2(ey - py, ex - px), hsize,
                       fill=OUTLINE))
    return specs


def build_connector_curve(w, h):
    """A gently curved thin arrow (quadratic bezier) — tail bottom-left,
    head top-right."""
    x0, y0 = w * 0.05, h * 0.80
    x1, y1 = w * 0.93, h * 0.30
    cxp, cyp = w * 0.45, h * 0.02      # control point bows the curve up
    n = 22
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        pts.append((mt * mt * x0 + 2 * mt * t * cxp + t * t * x1,
                    mt * mt * y0 + 2 * mt * t * cyp + t * t * y1))
    return _polyline_head(pts, min(w, h) * 0.18)


def build_connector_elbow(w, h):
    """A right-angle (elbow) thin arrow: across, then down to the head."""
    x0, y0 = w * 0.06, h * 0.18
    xc = w * 0.85
    y1 = h * 0.92
    return _polyline_head([(x0, y0), (xc, y0), (xc, y1)], min(w, h) * 0.16)


def build_connector_zigzag(w, h):
    """A stepped (Z) thin arrow: across, down, across to the head."""
    x0, y0 = w * 0.06, h * 0.22
    xm = w * 0.52
    x1, y1 = w * 0.94, h * 0.78
    return _polyline_head([(x0, y0), (xm, y0), (xm, y1), (x1, y1)],
                          min(w, h) * 0.16)


def build_connector_u(w, h):
    """A U-turn thin arrow: up, across, back down to the head."""
    x0, y0 = w * 0.22, h * 0.94
    yt = h * 0.10
    x1 = w * 0.78
    return _polyline_head([(x0, y0), (x0, yt), (x1, yt), (x1, y0)],
                          min(w, h) * 0.16)


REFERENCE_MM = 1200.0

SIZES = {
    "arrow_right": (200.0, 100.0),
    "arrow_left": (200.0, 100.0),
    "arrow_up": (100.0, 200.0),
    "arrow_down": (100.0, 200.0),
    "double_arrow": (200.0, 100.0),
    "curved_arrow": (160.0, 160.0),
    "bent_arrow": (160.0, 160.0),
    "circular_arrow": (160.0, 160.0),
    "callout_rect": (220.0, 150.0),
    "callout_round": (220.0, 150.0),
    "banner": (260.0, 90.0),
    "burst": (160.0, 160.0),
    "connector_curve": (220.0, 130.0),
    "connector_elbow": (180.0, 160.0),
    "connector_zigzag": (200.0, 150.0),
    "connector_u": (160.0, 170.0),
}

LABELS = {
    "arrow_right": "Arrow right",
    "arrow_left": "Arrow left",
    "arrow_up": "Arrow up",
    "arrow_down": "Arrow down",
    "double_arrow": "Double arrow",
    "curved_arrow": "Curved arrow",
    "bent_arrow": "Bent arrow",
    "circular_arrow": "Circular arrow",
    "callout_rect": "Rectangular callout",
    "callout_round": "Rounded callout",
    "banner": "Ribbon banner",
    "burst": "Starburst badge",
    "connector_curve": "Curved connector",
    "connector_elbow": "Elbow connector",
    "connector_zigzag": "Z-bend connector",
    "connector_u": "U-turn connector",
}

CATEGORIES = [
    ("Block arrows",
     ["arrow_right", "arrow_left", "arrow_up", "arrow_down", "double_arrow"]),
    ("Special arrows",
     ["curved_arrow", "bent_arrow", "circular_arrow"]),
    ("Callouts & banners",
     ["callout_rect", "callout_round", "banner", "burst"]),
    ("Connectors",
     ["connector_curve", "connector_elbow", "connector_zigzag",
      "connector_u"]),
]


_BUILDERS = {name: globals()["build_" + name] for name in SIZES}


def build_specs(name, w, h):
    return _BUILDERS[name](w, h)


def size_mm(name):
    return SIZES[name]
