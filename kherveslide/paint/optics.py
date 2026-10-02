'''Schematic optics / photonics symbols for beam-path diagrams.

Each `build_<name>(w, h)` returns a list of shape-spec dicts (the AI/
example format) drawing a symbol inside the box (0,0)-(w,h). Same
`build_specs`/`size_mm`/`REFERENCE_MM` interface as floorplan/electrical.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
'''
import math  # noqa: F401  (available for geometry if needed)

# --- palette ---------------------------------------------------------
_OUTLINE = "#333333"
_METAL = "#dfe7ee"
_GLASS = "#e8f0f5"
_BEAM = "#d9534f"
_DETECTOR = "#cfd6de"
_LIGHT = "#fde7b0"   # soft light-cone / glow fill
_RAY = "#e8a317"     # warm light ray

_W2 = 2.0    # outline width
_W1 = 1.2    # detail width

REFERENCE_MM = 600.0


# --- Sources & detectors --------------------------------------------
def build_laser(w, h):
    bx, by = 0.04 * w, 0.22 * h
    bw, bh = 0.62 * w, 0.56 * h
    cy = by + bh / 2.0
    return [
        {"shape": "rect", "x": bx, "y": by, "w": bw, "h": bh,
         "stroke": _OUTLINE, "fill": _METAL, "width": _W2},
        {"shape": "rect", "x": bx + bw, "y": cy - 0.06 * h,
         "w": 0.04 * w, "h": 0.12 * h,
         "stroke": _OUTLINE, "fill": _METAL, "width": _W1},
        {"shape": "arrow", "x1": bx + bw + 0.04 * w, "y1": cy,
         "x2": 0.98 * w, "y2": cy, "stroke": _BEAM, "width": _W2},
    ]


def build_lamp(w, h):
    cx, cy = 0.5 * w, 0.5 * h
    r = 0.26 * min(w, h)
    specs = [
        {"shape": "circle", "x": cx - r, "y": cy - r, "w": 2 * r, "h": 2 * r,
         "stroke": _OUTLINE, "fill": _GLASS, "width": _W2},
    ]
    for i in range(8):
        a = i * math.pi / 4.0
        x1 = cx + math.cos(a) * r * 1.25
        y1 = cy + math.sin(a) * r * 1.25
        x2 = cx + math.cos(a) * r * 1.75
        y2 = cy + math.sin(a) * r * 1.75
        specs.append({"shape": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                      "stroke": _BEAM, "width": _W1})
    return specs


def build_detector(w, h):
    bx, by = 0.18 * w, 0.12 * h
    bw, bh = 0.7 * w, 0.76 * h
    cy = by + bh / 2.0
    notch = 0.3 * h
    return [
        {"shape": "rect", "x": bx, "y": by, "w": bw, "h": bh,
         "stroke": _OUTLINE, "fill": _DETECTOR, "width": _W2},
        # concave face (shallow halfcircle notch) facing left
        {"shape": "halfcircle", "x": bx - notch / 2.0, "y": cy - notch / 2.0,
         "w": notch, "h": notch, "stroke": _OUTLINE, "fill": _GLASS,
         "width": _W1, "rotation": 90.0},
    ]


def build_photodiode(w, h):
    bx, by = 0.2 * w, 0.18 * h
    s = 0.6 * min(w, h)
    cx, cy = bx + s / 2.0, by + s / 2.0
    return [
        {"shape": "rect", "x": bx, "y": by, "w": s, "h": s,
         "stroke": _OUTLINE, "fill": _GLASS, "width": _W2},
        # diagonal interface line
        {"shape": "line", "x1": bx, "y1": by + s, "x2": bx + s, "y2": by,
         "stroke": _OUTLINE, "width": _W1},
        # two small in-pointing arrows (incident light)
        {"shape": "arrow", "x1": bx - 0.18 * s, "y1": by - 0.12 * s,
         "x2": cx - 0.12 * s, "y2": cy - 0.06 * s,
         "stroke": _BEAM, "width": _W1},
        {"shape": "arrow", "x1": bx - 0.06 * s, "y1": by - 0.24 * s,
         "x2": cx, "y2": cy - 0.18 * s, "stroke": _BEAM, "width": _W1},
    ]


def build_camera(w, h):
    bx, by = 0.06 * w, 0.18 * h
    bw, bh = 0.7 * w, 0.64 * h
    cy = by + bh / 2.0
    lr = 0.16 * h
    lcx = bx + bw
    return [
        {"shape": "rounded_rect", "x": bx, "y": by, "w": bw, "h": bh,
         "radius": 0.08 * bw, "stroke": _OUTLINE, "fill": _METAL,
         "width": _W2},
        {"shape": "circle", "x": lcx - lr, "y": cy - lr,
         "w": 2 * lr, "h": 2 * lr,
         "stroke": _OUTLINE, "fill": _GLASS, "width": _W2},
        {"shape": "circle", "x": lcx - lr * 0.5, "y": cy - lr * 0.5,
         "w": lr, "h": lr, "stroke": _OUTLINE, "fill": "none", "width": _W1},
    ]


# --- Mirrors & beams -------------------------------------------------
def build_mirror_flat(w, h):
    bx = 0.34 * w
    bw = 0.32 * w
    by, bh = 0.06 * h, 0.88 * h
    specs = [
        {"shape": "rect", "x": bx, "y": by, "w": bw, "h": bh,
         "stroke": _OUTLINE, "fill": _METAL, "width": _W2},
    ]
    # hatch ticks down the back (right) side
    n = 9
    for i in range(n):
        y = by + bh * (i + 0.5) / n
        specs.append({"shape": "line",
                      "x1": bx + bw, "y1": y,
                      "x2": bx + bw + 0.22 * w, "y2": y + 0.05 * h,
                      "stroke": _OUTLINE, "width": _W1})
    return specs


def build_mirror_curved(w, h):
    ax, ay = 0.1 * w, 0.06 * h
    aw, ah = 0.5 * w, 0.88 * h
    specs = [
        {"shape": "halfcircle", "x": ax, "y": ay, "w": aw, "h": ah,
         "stroke": _OUTLINE, "fill": "none", "width": _W2, "rotation": 0.0},
    ]
    # hatch ticks on the convex back (right) side
    n = 8
    cx = ax + aw / 2.0
    cy = ay + ah / 2.0
    rx = aw / 2.0
    ry = ah / 2.0
    for i in range(n):
        t = -math.pi / 2.0 + math.pi * (i + 0.5) / n
        ex = cx + math.cos(t) * rx
        ey = cy + math.sin(t) * ry
        specs.append({"shape": "line",
                      "x1": ex, "y1": ey,
                      "x2": ex + 0.2 * w, "y2": ey + 0.04 * h,
                      "stroke": _OUTLINE, "width": _W1})
    return specs


def build_beam_splitter(w, h):
    bx, by = 0.18 * w, 0.12 * h
    s = 0.64 * min(w, h)
    return [
        {"shape": "rect", "x": bx, "y": by, "w": s, "h": s,
         "stroke": _OUTLINE, "fill": _GLASS, "width": _W2},
        {"shape": "line", "x1": bx, "y1": by + s, "x2": bx + s, "y2": by,
         "stroke": _OUTLINE, "width": _W2},
    ]


def build_beam(w, h):
    cy = 0.5 * h
    return [
        {"shape": "arrow", "x1": 0.02 * w, "y1": cy, "x2": 0.98 * w, "y2": cy,
         "stroke": _BEAM, "width": _W2},
    ]


# --- Lenses & elements ----------------------------------------------
def build_lens_convex(w, h):
    cx = 0.5 * w
    ew = 0.5 * w
    ey, eh = 0.06 * h, 0.88 * h
    return [
        {"shape": "ellipse", "x": cx - ew / 2.0, "y": ey, "w": ew, "h": eh,
         "stroke": _OUTLINE, "fill": _GLASS, "width": _W2},
        {"shape": "line", "x1": cx, "y1": ey, "x2": cx, "y2": ey + eh,
         "stroke": _OUTLINE, "width": _W1},
        {"shape": "arrow", "x1": cx, "y1": ey + eh * 0.2,
         "x2": cx, "y2": ey - 0.04 * h, "stroke": _OUTLINE, "width": _W1},
        {"shape": "arrow", "x1": cx, "y1": ey + eh * 0.8,
         "x2": cx, "y2": ey + eh + 0.04 * h, "stroke": _OUTLINE,
         "width": _W1},
    ]


def build_lens_concave(w, h):
    cx = 0.5 * w
    bw = 0.34 * w
    bx = cx - bw / 2.0
    by, bh = 0.08 * h, 0.84 * h
    bite = 0.26 * w
    return [
        {"shape": "rect", "x": bx, "y": by, "w": bw, "h": bh,
         "stroke": _OUTLINE, "fill": _GLASS, "width": _W2},
        # left bite (concave side) — halfcircle facing right
        {"shape": "halfcircle", "x": bx - bite / 2.0, "y": by + bh / 2.0 - bite,
         "w": bite, "h": 2 * bite, "stroke": _OUTLINE, "fill": "#ffffff",
         "width": _W1, "rotation": 90.0},
        # right bite — halfcircle facing left
        {"shape": "halfcircle", "x": bx + bw - bite / 2.0,
         "y": by + bh / 2.0 - bite,
         "w": bite, "h": 2 * bite, "stroke": _OUTLINE, "fill": "#ffffff",
         "width": _W1, "rotation": 270.0},
        # in-pointing tips top and bottom
        {"shape": "arrow", "x1": cx, "y1": by - 0.06 * h,
         "x2": cx, "y2": by + 0.14 * h, "stroke": _OUTLINE, "width": _W1},
        {"shape": "arrow", "x1": cx, "y1": by + bh + 0.06 * h,
         "x2": cx, "y2": by + bh - 0.14 * h, "stroke": _OUTLINE,
         "width": _W1},
    ]


def build_prism(w, h):
    return [
        {"shape": "triangle", "x": 0.08 * w, "y": 0.1 * h,
         "w": 0.84 * w, "h": 0.8 * h, "rotation": 0.0,
         "stroke": _OUTLINE, "fill": _GLASS, "width": _W2},
    ]


def build_grating(w, h):
    bx, by = 0.22 * w, 0.06 * h
    bw, bh = 0.56 * w, 0.88 * h
    specs = [
        {"shape": "rect", "x": bx, "y": by, "w": bw, "h": bh,
         "stroke": _OUTLINE, "fill": _GLASS, "width": _W2},
    ]
    n = 12
    for i in range(1, n):
        x = bx + bw * i / n
        specs.append({"shape": "line", "x1": x, "y1": by, "x2": x,
                      "y2": by + bh, "stroke": _OUTLINE, "width": _W1})
    return specs


def build_polarizer(w, h):
    cx, cy = 0.5 * w, 0.5 * h
    r = 0.38 * min(w, h)
    d = r / math.sqrt(2.0)
    specs = [
        {"shape": "circle", "x": cx - r, "y": cy - r, "w": 2 * r, "h": 2 * r,
         "stroke": _OUTLINE, "fill": _GLASS, "width": _W2},
        # transmission axis (main diagonal)
        {"shape": "line", "x1": cx - d, "y1": cy + d, "x2": cx + d,
         "y2": cy - d, "stroke": _OUTLINE, "width": _W2},
    ]
    # a couple of short parallel lines
    for off in (-0.5 * r, 0.5 * r):
        ox = off / math.sqrt(2.0)
        oy = off / math.sqrt(2.0)
        specs.append({"shape": "line",
                      "x1": cx - 0.4 * d + ox, "y1": cy + 0.4 * d + oy,
                      "x2": cx + 0.4 * d + ox, "y2": cy - 0.4 * d + oy,
                      "stroke": _OUTLINE, "width": _W1})
    return specs


def build_aperture(w, h):
    cx, cy = 0.5 * w, 0.5 * h
    r = 0.42 * min(w, h)
    rin = 0.16 * min(w, h)
    return [
        {"shape": "circle", "x": cx - r, "y": cy - r, "w": 2 * r, "h": 2 * r,
         "stroke": _OUTLINE, "fill": _METAL, "width": _W2},
        {"shape": "circle", "x": cx - rin, "y": cy - rin,
         "w": 2 * rin, "h": 2 * rin,
         "stroke": _OUTLINE, "fill": "#ffffff", "width": _W1},
    ]


def build_filter(w, h):
    bx, by = 0.1 * w, 0.14 * h
    bw, bh = 0.8 * w, 0.72 * h
    tab = 0.16 * w
    return [
        {"shape": "rounded_rect", "x": bx, "y": by, "w": bw, "h": bh,
         "radius": 0.06 * bw, "stroke": _OUTLINE, "fill": _GLASS,
         "width": _W2},
        # small corner label tab
        {"shape": "rect", "x": bx + bw - tab, "y": by, "w": tab,
         "h": 0.18 * h, "stroke": _OUTLINE, "fill": _METAL, "width": _W1},
    ]


# --- Components ------------------------------------------------------
def build_sample(w, h):
    fx, fy = 0.16 * w, 0.16 * h
    fw, fh = 0.68 * w, 0.68 * h
    s = 0.3 * min(w, h)
    cx, cy = 0.5 * w, 0.5 * h
    return [
        # thin holder frame
        {"shape": "rect", "x": fx, "y": fy, "w": fw, "h": fh,
         "stroke": _OUTLINE, "fill": "none", "width": _W1},
        # sample square centred
        {"shape": "rect", "x": cx - s / 2.0, "y": cy - s / 2.0,
         "w": s, "h": s, "stroke": _OUTLINE, "fill": _GLASS, "width": _W2},
    ]


def build_monochromator(w, h):
    bx, by = 0.06 * w, 0.1 * h
    bw, bh = 0.88 * w, 0.8 * h
    cy = by + bh / 2.0
    specs = [
        {"shape": "rect", "x": bx, "y": by, "w": bw, "h": bh,
         "stroke": _OUTLINE, "fill": _METAL, "width": _W2},
    ]
    # slit ticks on opposite sides
    slit = 0.18 * h
    specs.append({"shape": "rect", "x": bx - 0.02 * w, "y": cy - slit / 2.0,
                  "w": 0.04 * w, "h": slit,
                  "stroke": _OUTLINE, "fill": "#ffffff", "width": _W1})
    specs.append({"shape": "rect", "x": bx + bw - 0.02 * w,
                  "y": cy - slit / 2.0,
                  "w": 0.04 * w, "h": slit,
                  "stroke": _OUTLINE, "fill": "#ffffff", "width": _W1})
    # internal grating line
    gx = bx + bw * 0.6
    specs.append({"shape": "line", "x1": gx, "y1": by + bh * 0.25,
                  "x2": gx, "y2": by + bh * 0.75,
                  "stroke": _OUTLINE, "width": _W2})
    return specs


# --- Lighting / illumination ----------------------------------------
def build_light_cone(w, h):
    """A cone of light to shine down onto an object: a source dot at the
    top widening into a pale beam with edge rays."""
    cx = 0.5 * w
    return [
        {"shape": "triangle", "x": 0.12 * w, "y": 0.14 * h, "w": 0.76 * w,
         "h": 0.80 * h, "rotation": 0, "stroke": _RAY, "fill": _LIGHT,
         "width": _W1},
        {"shape": "line", "x1": cx, "y1": 0.16 * h, "x2": 0.33 * w,
         "y2": 0.9 * h, "stroke": _RAY, "width": _W1},
        {"shape": "line", "x1": cx, "y1": 0.16 * h, "x2": 0.67 * w,
         "y2": 0.9 * h, "stroke": _RAY, "width": _W1},
        {"shape": "circle", "x": cx - 0.06 * w, "y": 0.04 * h, "w": 0.12 * w,
         "h": 0.12 * w, "stroke": _OUTLINE, "fill": _RAY, "width": _W1},
    ]


def build_spotlight(w, h):
    """A focused spotlight: lamp head casting a narrow cone onto a hotspot."""
    cx = 0.5 * w
    return [
        {"shape": "trapezoid", "x": 0.10 * w, "y": 0.28 * h, "w": 0.80 * w,
         "h": 0.52 * h, "rotation": 0, "stroke": _RAY, "fill": _LIGHT,
         "width": _W1},
        {"shape": "trapezoid", "x": 0.30 * w, "y": 0.04 * h, "w": 0.40 * w,
         "h": 0.24 * h, "rotation": 0, "stroke": _OUTLINE, "fill": _METAL,
         "width": _W2},
        {"shape": "circle", "x": cx - 0.06 * w, "y": 0.15 * h, "w": 0.12 * w,
         "h": 0.12 * w, "stroke": _OUTLINE, "fill": _RAY, "width": _W1},
        {"shape": "ellipse", "x": 0.20 * w, "y": 0.82 * h, "w": 0.60 * w,
         "h": 0.13 * h, "stroke": _RAY, "fill": _LIGHT, "width": _W1},
    ]


def build_floodlight(w, h):
    """A broad floodlight: rectangular fixture with a wide light spread."""
    return [
        {"shape": "trapezoid", "x": 0.02 * w, "y": 0.32 * h, "w": 0.96 * w,
         "h": 0.60 * h, "rotation": 0, "stroke": _RAY, "fill": _LIGHT,
         "width": _W1},
        {"shape": "rect", "x": 0.24 * w, "y": 0.06 * h, "w": 0.52 * w,
         "h": 0.24 * h, "stroke": _OUTLINE, "fill": _METAL, "width": _W2},
        {"shape": "line", "x1": 0.42 * w, "y1": 0.06 * h, "x2": 0.42 * w,
         "y2": 0.30 * h, "stroke": _OUTLINE, "width": _W1},
        {"shape": "line", "x1": 0.58 * w, "y1": 0.06 * h, "x2": 0.58 * w,
         "y2": 0.30 * h, "stroke": _OUTLINE, "width": _W1},
        {"shape": "line", "x1": 0.24 * w, "y1": 0.18 * h, "x2": 0.12 * w,
         "y2": 0.18 * h, "stroke": _OUTLINE, "width": _W2},
        {"shape": "line", "x1": 0.76 * w, "y1": 0.18 * h, "x2": 0.88 * w,
         "y2": 0.18 * h, "stroke": _OUTLINE, "width": _W2},
    ]


def build_desk_lamp(w, h):
    """An adjustable desk lamp shining a cone of light onto the bench."""
    return [
        {"shape": "ellipse", "x": 0.08 * w, "y": 0.90 * h, "w": 0.44 * w,
         "h": 0.08 * h, "stroke": _OUTLINE, "fill": _METAL, "width": _W2},
        {"shape": "line", "x1": 0.30 * w, "y1": 0.90 * h, "x2": 0.34 * w,
         "y2": 0.40 * h, "stroke": _OUTLINE, "width": _W2},
        {"shape": "line", "x1": 0.34 * w, "y1": 0.40 * h, "x2": 0.60 * w,
         "y2": 0.22 * h, "stroke": _OUTLINE, "width": _W2},
        {"shape": "trapezoid", "x": 0.48 * w, "y": 0.12 * h, "w": 0.34 * w,
         "h": 0.20 * h, "rotation": 0, "stroke": _OUTLINE, "fill": _METAL,
         "width": _W2},
        {"shape": "triangle", "x": 0.44 * w, "y": 0.30 * h, "w": 0.50 * w,
         "h": 0.52 * h, "rotation": 0, "stroke": _RAY, "fill": _LIGHT,
         "width": _W1},
    ]


def build_bulb(w, h):
    """An incandescent light bulb (glass + filament + screw base) with
    emitted rays."""
    cx = 0.5 * w
    d = 0.52 * w
    gx, gy = cx - d / 2.0, 0.10 * h
    ccy = gy + d / 2.0
    specs = [
        {"shape": "circle", "x": gx, "y": gy, "w": d, "h": d,
         "stroke": _OUTLINE, "fill": _LIGHT, "width": _W2},
        {"shape": "line", "x1": cx - 0.09 * w, "y1": gy + d * 0.72,
         "x2": cx - 0.03 * w, "y2": gy + d * 0.45, "stroke": _RAY,
         "width": _W1},
        {"shape": "line", "x1": cx - 0.03 * w, "y1": gy + d * 0.45,
         "x2": cx + 0.03 * w, "y2": gy + d * 0.55, "stroke": _RAY,
         "width": _W1},
        {"shape": "line", "x1": cx + 0.03 * w, "y1": gy + d * 0.55,
         "x2": cx + 0.09 * w, "y2": gy + d * 0.30, "stroke": _RAY,
         "width": _W1},
        {"shape": "rect", "x": cx - 0.12 * w, "y": gy + d - 0.005 * h,
         "w": 0.24 * w, "h": 0.16 * h, "stroke": _OUTLINE, "fill": _METAL,
         "width": _W1},
    ]
    for i in (1, 2):
        y = gy + d + 0.05 * h * i
        specs.append({"shape": "line", "x1": cx - 0.12 * w, "y1": y,
                      "x2": cx + 0.12 * w, "y2": y, "stroke": _OUTLINE,
                      "width": _W1})
    for a in (-70, -35, 0, 35, 70):
        ang = math.radians(a - 90)
        r0, r1 = d * 0.60, d * 0.85
        specs.append({"shape": "line",
                      "x1": cx + r0 * math.cos(ang), "y1": ccy + r0 * math.sin(ang),
                      "x2": cx + r1 * math.cos(ang), "y2": ccy + r1 * math.sin(ang),
                      "stroke": _RAY, "width": _W1})
    return specs


def build_led(w, h):
    """An LED (domed emitter on two leads) with the two emitted-light arrows."""
    cx = 0.5 * w
    dw, dh = 0.5 * w, 0.42 * h
    dx, dy = cx - dw / 2.0, 0.28 * h
    return [
        {"shape": "halfcircle", "x": dx, "y": dy, "w": dw, "h": dh,
         "rotation": 0, "stroke": _OUTLINE, "fill": _LIGHT, "width": _W2},
        {"shape": "line", "x1": dx, "y1": dy + dh, "x2": dx + dw, "y2": dy + dh,
         "stroke": _OUTLINE, "width": _W2},
        {"shape": "line", "x1": cx - 0.1 * w, "y1": dy + dh, "x2": cx - 0.1 * w,
         "y2": 0.94 * h, "stroke": _OUTLINE, "width": _W2},
        {"shape": "line", "x1": cx + 0.1 * w, "y1": dy + dh, "x2": cx + 0.1 * w,
         "y2": 0.94 * h, "stroke": _OUTLINE, "width": _W2},
        {"shape": "arrow", "x1": dx + 0.20 * dw, "y1": dy + 0.05 * dh,
         "x2": dx - 0.10 * dw, "y2": dy - 0.28 * dh, "stroke": _RAY,
         "width": _W1},
        {"shape": "arrow", "x1": dx + 0.42 * dw, "y1": dy - 0.05 * dh,
         "x2": dx + 0.14 * dw, "y2": dy - 0.36 * dh, "stroke": _RAY,
         "width": _W1},
    ]


def build_ring_light(w, h):
    """A ring illuminator: an annulus of LEDs shining inward on a sample."""
    cx, cy = 0.5 * w, 0.5 * h
    m = min(w, h)
    r, ri = 0.44 * m, 0.24 * m
    specs = [
        {"shape": "circle", "x": cx - r, "y": cy - r, "w": 2 * r, "h": 2 * r,
         "stroke": _OUTLINE, "fill": _LIGHT, "width": _W2},
        {"shape": "circle", "x": cx - ri, "y": cy - ri, "w": 2 * ri,
         "h": 2 * ri, "stroke": _OUTLINE, "fill": "#ffffff", "width": _W1},
    ]
    rm, dd = (r + ri) / 2.0, 0.035 * m
    for i in range(12):
        a = math.radians(i * 30)
        dx, dy = cx + rm * math.cos(a), cy + rm * math.sin(a)
        specs.append({"shape": "circle", "x": dx - dd, "y": dy - dd,
                      "w": 2 * dd, "h": 2 * dd, "stroke": _OUTLINE,
                      "fill": _RAY, "width": _W1})
    for i in range(4):
        a = math.radians(i * 90 + 45)
        specs.append({"shape": "line",
                      "x1": cx + ri * 0.95 * math.cos(a),
                      "y1": cy + ri * 0.95 * math.sin(a),
                      "x2": cx + ri * 0.30 * math.cos(a),
                      "y2": cy + ri * 0.30 * math.sin(a),
                      "stroke": _RAY, "width": _W1})
    return specs


def build_shine(w, h):
    """A sparkle / glint to drop on an object to show it is lit or shiny."""
    cx, cy = 0.5 * w, 0.5 * h
    m = min(w, h)
    specs = []
    for a in (0, 90, 180, 270):
        ang = math.radians(a)
        specs.append({"shape": "line", "x1": cx, "y1": cy,
                      "x2": cx + 0.46 * m * math.cos(ang),
                      "y2": cy + 0.46 * m * math.sin(ang),
                      "stroke": _RAY, "width": _W2})
    for a in (45, 135, 225, 315):
        ang = math.radians(a)
        specs.append({"shape": "line", "x1": cx, "y1": cy,
                      "x2": cx + 0.26 * m * math.cos(ang),
                      "y2": cy + 0.26 * m * math.sin(ang),
                      "stroke": _RAY, "width": _W1})
    dd = 0.12 * m
    specs.append({"shape": "circle", "x": cx - dd, "y": cy - dd, "w": 2 * dd,
                  "h": 2 * dd, "stroke": _RAY, "fill": _LIGHT, "width": _W1})
    return specs


# --- registry / metadata --------------------------------------------
SIZES = {
    "laser": (140.0, 60.0),
    "lamp": (80.0, 80.0),
    "detector": (90.0, 90.0),
    "photodiode": (80.0, 80.0),
    "camera": (110.0, 80.0),
    "mirror_flat": (40.0, 120.0),
    "mirror_curved": (50.0, 120.0),
    "beam_splitter": (80.0, 80.0),
    "beam": (160.0, 20.0),
    "lens_convex": (40.0, 120.0),
    "lens_concave": (40.0, 120.0),
    "prism": (90.0, 80.0),
    "grating": (40.0, 110.0),
    "polarizer": (80.0, 80.0),
    "aperture": (80.0, 80.0),
    "filter": (90.0, 70.0),
    "sample": (70.0, 70.0),
    "monochromator": (160.0, 120.0),
    "light_cone": (120.0, 140.0),
    "spotlight": (120.0, 140.0),
    "floodlight": (140.0, 120.0),
    "desk_lamp": (130.0, 150.0),
    "bulb": (90.0, 130.0),
    "led": (80.0, 120.0),
    "ring_light": (110.0, 110.0),
    "shine": (90.0, 90.0),
}

LABELS = {
    "laser": "Laser",
    "lamp": "Lamp / source",
    "detector": "Detector",
    "photodiode": "Photodiode",
    "camera": "Camera",
    "mirror_flat": "Flat mirror",
    "mirror_curved": "Curved mirror",
    "beam_splitter": "Beam splitter",
    "beam": "Beam path",
    "lens_convex": "Convex lens",
    "lens_concave": "Concave lens",
    "prism": "Prism",
    "grating": "Grating",
    "polarizer": "Polarizer",
    "aperture": "Aperture / iris",
    "filter": "Filter",
    "sample": "Sample",
    "monochromator": "Monochromator",
    "light_cone": "Light cone",
    "spotlight": "Spotlight",
    "floodlight": "Floodlight",
    "desk_lamp": "Desk lamp",
    "bulb": "Light bulb",
    "led": "LED",
    "ring_light": "Ring light",
    "shine": "Shine / glint",
}

CATEGORIES = [
    ("Sources & detectors",
     ["laser", "lamp", "detector", "photodiode", "camera"]),
    ("Mirrors & beams",
     ["mirror_flat", "mirror_curved", "beam_splitter", "beam"]),
    ("Lenses & elements",
     ["lens_convex", "lens_concave", "prism", "grating", "polarizer",
      "aperture", "filter"]),
    ("Components",
     ["sample", "monochromator"]),
    ("Lighting",
     ["light_cone", "spotlight", "floodlight", "desk_lamp", "bulb", "led",
      "ring_light", "shine"]),
]


_BUILDERS = {name: globals()["build_" + name] for name in SIZES}


def build_specs(name, w, h):
    return _BUILDERS[name](w, h)


def size_mm(name):
    return SIZES[name]
