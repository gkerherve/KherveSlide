'''Schematic lab glassware / apparatus symbols (front-elevation diagrams).

Each `build_<name>(w, h)` returns a list of shape-spec dicts (the AI/
example format) drawing a symbol inside the box (0,0)-(w,h). Same
`build_specs`/`size_mm`/`REFERENCE_MM` interface as floorplan/electrical.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
'''
import math   # if you need it

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
OUTLINE = "#333333"
GLASS = "#eef4f8"
LIQUID = "#cfe3f2"
FLAME = "#f0a500"
METAL = "#cfd6de"
NONE = "none"

W_OUT = 2.0     # outline width
W_DET = 1.2     # detail width

REFERENCE_MM = 1000.0


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _line(x1, y1, x2, y2, stroke=OUTLINE, width=W_DET):
    return {"shape": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "stroke": stroke, "width": width}


def _rect(x, y, w, h, stroke=OUTLINE, fill=GLASS, width=W_OUT):
    return {"shape": "rect", "x": x, "y": y, "w": w, "h": h,
            "stroke": stroke, "fill": fill, "width": width}


def _rrect(x, y, w, h, radius, stroke=OUTLINE, fill=GLASS, width=W_OUT):
    return {"shape": "rounded_rect", "x": x, "y": y, "w": w, "h": h,
            "radius": radius, "stroke": stroke, "fill": fill, "width": width}


def _circle(x, y, w, h, stroke=OUTLINE, fill=GLASS, width=W_OUT):
    return {"shape": "circle", "x": x, "y": y, "w": w, "h": h,
            "stroke": stroke, "fill": fill, "width": width}


def _ellipse(x, y, w, h, stroke=OUTLINE, fill=GLASS, width=W_OUT):
    return {"shape": "ellipse", "x": x, "y": y, "w": w, "h": h,
            "stroke": stroke, "fill": fill, "width": width}


def _half(x, y, w, h, rotation=0.0, stroke=OUTLINE, fill=GLASS, width=W_OUT):
    return {"shape": "halfcircle", "x": x, "y": y, "w": w, "h": h,
            "rotation": rotation, "stroke": stroke, "fill": fill,
            "width": width}


def _quarter(x, y, w, h, rotation=0.0, stroke=OUTLINE, fill=GLASS,
             width=W_OUT):
    return {"shape": "quartercircle", "x": x, "y": y, "w": w, "h": h,
            "rotation": rotation, "stroke": stroke, "fill": fill,
            "width": width}


def _poly(shape, x, y, w, h, rotation=0.0, stroke=OUTLINE, fill=GLASS,
          width=W_OUT):
    return {"shape": shape, "x": x, "y": y, "w": w, "h": h,
            "rotation": rotation, "stroke": stroke, "fill": fill,
            "width": width}


def _bulb_liquid(cx, top, d, frac=0.55, fill=LIQUID):
    """Liquid segment filling the lower *frac* of a round bulb.

    The bulb is the circle of diameter *d* whose top is at *top* (centre
    at ``top + d/2``). The liquid is a squashed half-circle whose flat
    side sits on the surface chord and whose curve tucks *inside* the
    bulb outline (so it never spills past the glass). Returns
    ``(fill_spec, surface_line)``."""
    r = d / 2.0
    cyc = top + r                      # circle centre y
    surf = top + d * (1.0 - frac)      # liquid surface height
    dy = surf - cyc
    half = math.sqrt(max(r * r - dy * dy, 0.0))   # chord half-width
    # dome bulging DOWN (flat side on the surface): rotate the half-disc
    fill_spec = _half(cx - half, surf, 2 * half, (top + d) - surf,
                      180.0, NONE, fill, W_DET)
    line = _line(cx - half, surf, cx + half, surf, OUTLINE, W_DET)
    return fill_spec, line


# ===========================================================================
# Glassware
# ===========================================================================
def build_beaker(w, h):
    """Straight-walled cup: flared lip + pour spout, graduation ticks on
    the right, liquid filling the lower ~55%."""
    specs = []
    left, right = 0.24 * w, 0.76 * w       # vertical walls
    top, bot = 0.16 * h, 0.90 * h
    body_h = bot - top
    # glass body + liquid
    specs.append(_rect(left, top, right - left, body_h, NONE, GLASS, W_DET))
    liq_top = top + body_h * 0.45          # liquid surface (lower 55%)
    specs.append(_rect(left, liq_top, right - left, bot - liq_top,
                       NONE, LIQUID, W_DET))
    specs.append(_line(left, liq_top, right, liq_top, OUTLINE, W_DET))
    # body outline: walls + flat bottom (open top)
    specs.append(_line(left, top, left, bot, OUTLINE, W_OUT))
    specs.append(_line(right, top, right, bot, OUTLINE, W_OUT))
    specs.append(_line(left, bot, right, bot, OUTLINE, W_OUT))
    # flared lip: a short bar slightly wider than the walls
    lipL, lipR = left - 0.05 * w, right + 0.05 * w
    specs.append(_line(lipL, top, right, top, OUTLINE, W_OUT))
    specs.append(_line(lipL, top, left, top + 0.03 * h, OUTLINE, W_OUT))
    specs.append(_line(right, top, lipR, top + 0.02 * h, OUTLINE, W_OUT))
    specs.append(_line(lipR, top + 0.02 * h, right, top + 0.05 * h,
                       OUTLINE, W_OUT))
    # pour spout beak on the left of the lip
    specs.append(_line(lipL, top, lipL - 0.05 * w, top - 0.03 * h,
                       OUTLINE, W_OUT))
    specs.append(_line(lipL - 0.05 * w, top - 0.03 * h, left, top + 0.03 * h,
                       OUTLINE, W_OUT))
    # graduation ticks (right, upper portion)
    for fr in (0.20, 0.32, 0.44):
        yy = top + body_h * fr
        specs.append(_line(right - 0.12 * w, yy, right, yy, OUTLINE, W_DET))
    return specs


def build_erlenmeyer(w, h):
    """Conical flask: trapezoid cone + short neck, liquid in cone."""
    specs = []
    neck_top = 0.10 * h
    neck_bot = 0.30 * h
    cone_bot = 0.94 * h
    nl, nr = 0.42 * w, 0.58 * w
    bl, br = 0.16 * w, 0.84 * w
    # liquid in lower cone
    liq_top = neck_bot + (cone_bot - neck_bot) * 0.45
    f = (liq_top - neck_bot) / (cone_bot - neck_bot)
    ll = nl + (bl - nl) * f
    rl = nr + (br - nr) * f
    specs.append({"shape": "trapezoid", "x": bl, "y": liq_top,
                  "w": br - bl, "h": cone_bot - liq_top, "rotation": 0.0,
                  "stroke": NONE, "fill": LIQUID, "width": W_DET})
    # neck
    specs.append(_rect(nl, neck_top, nr - nl, neck_bot - neck_top,
                       OUTLINE, GLASS, W_OUT))
    # cone walls
    specs.append(_line(nl, neck_bot, bl, cone_bot, OUTLINE, W_OUT))
    specs.append(_line(nr, neck_bot, br, cone_bot, OUTLINE, W_OUT))
    specs.append(_line(bl, cone_bot, br, cone_bot, OUTLINE, W_OUT))
    # liquid surface
    specs.append(_line(ll, liq_top, rl, liq_top, OUTLINE, W_DET))
    # flared rim on the neck
    specs.append(_line(nl - 0.04 * w, neck_top, nr + 0.04 * w, neck_top,
                       OUTLINE, W_OUT))
    specs.append(_line(nl - 0.04 * w, neck_top, nl, neck_top + 0.03 * h,
                       OUTLINE, W_OUT))
    specs.append(_line(nr + 0.04 * w, neck_top, nr, neck_top + 0.03 * h,
                       OUTLINE, W_OUT))
    # graduation ticks on the right of the cone
    for fr in (0.55, 0.70):
        yy = neck_bot + (cone_bot - neck_bot) * fr
        xr = nr + (br - nr) * fr
        specs.append(_line(xr - 0.11 * w, yy, xr - 0.02 * w, yy,
                           OUTLINE, W_DET))
    return specs


def build_round_bottom_flask(w, h):
    """Round bottom (circle) with tall thin neck rect."""
    specs = []
    d = 0.56 * w
    cx = 0.5 * w
    bulb_y = 0.94 * h - d
    neck_w = 0.18 * w
    neck_top = 0.08 * h
    neck_bot = bulb_y + 0.16 * d
    # neck (behind the bulb) + glass bulb
    specs.append(_rect(cx - neck_w / 2, neck_top, neck_w,
                       neck_bot - neck_top, OUTLINE, GLASS, W_OUT))
    specs.append(_circle(cx - d / 2, bulb_y, d, d, OUTLINE, GLASS, W_OUT))
    # liquid contained inside the bulb
    fill, surf = _bulb_liquid(cx, bulb_y, d, 0.52)
    specs.append(fill)
    specs.append(surf)
    # flared rim
    specs.append(_line(cx - neck_w / 2 - 0.04 * w, neck_top,
                       cx + neck_w / 2 + 0.04 * w, neck_top, OUTLINE, W_OUT))
    specs.append(_line(cx - neck_w / 2 - 0.04 * w, neck_top,
                       cx - neck_w / 2, neck_top + 0.03 * h, OUTLINE, W_OUT))
    specs.append(_line(cx + neck_w / 2 + 0.04 * w, neck_top,
                       cx + neck_w / 2, neck_top + 0.03 * h, OUTLINE, W_OUT))
    return specs


def build_volumetric_flask(w, h):
    """Small bulb + very long thin neck + calibration ring line."""
    specs = []
    d = 0.46 * w
    cx = 0.5 * w
    bulb_y = 0.94 * h - d
    neck_w = 0.14 * w
    neck_top = 0.05 * h
    neck_bot = bulb_y + 0.10 * d
    specs.append(_rect(cx - neck_w / 2, neck_top, neck_w,
                       neck_bot - neck_top, OUTLINE, GLASS, W_OUT))
    specs.append(_circle(cx - d / 2, bulb_y, d, d, OUTLINE, GLASS, W_OUT))
    fill, surf = _bulb_liquid(cx, bulb_y, d, 0.48)
    specs.append(fill)
    specs.append(surf)
    # calibration ring on the visible neck (above the bulb)
    ring_y = neck_top + (bulb_y - neck_top) * 0.55
    specs.append(_line(cx - neck_w / 2, ring_y, cx + neck_w / 2, ring_y,
                       OUTLINE, W_DET))
    # rim
    specs.append(_line(cx - neck_w / 2 - 0.02 * w, neck_top,
                       cx + neck_w / 2 + 0.02 * w, neck_top, OUTLINE, W_OUT))
    return specs


def build_test_tube(w, h):
    """Straight tube with a U-shaped (round) bottom, liquid lower part."""
    specs = []
    tw = 0.36 * w
    x = 0.5 * w - tw / 2
    r = tw / 2.0
    top = 0.06 * h
    straight_bot = 0.94 * h - r        # where the round bottom starts
    liq_top = 0.50 * h
    # liquid: straight column + filled round bottom (dome bulging down)
    specs.append(_rect(x, liq_top, tw, straight_bot - liq_top,
                       NONE, LIQUID, W_DET))
    specs.append(_half(x, straight_bot, tw, r, 180.0, NONE, LIQUID, W_DET))
    # walls + round bottom outline
    specs.append(_line(x, top, x, straight_bot, OUTLINE, W_OUT))
    specs.append(_line(x + tw, top, x + tw, straight_bot, OUTLINE, W_OUT))
    specs.append(_half(x, straight_bot, tw, r, 180.0, OUTLINE, NONE, W_OUT))
    # liquid surface
    specs.append(_line(x, liq_top, x + tw, liq_top, OUTLINE, W_DET))
    # flared rim
    specs.append(_line(x - 0.04 * w, top, x + tw + 0.04 * w, top,
                       OUTLINE, W_OUT))
    specs.append(_line(x - 0.04 * w, top, x, top + 0.03 * h, OUTLINE, W_OUT))
    specs.append(_line(x + tw + 0.04 * w, top, x + tw, top + 0.03 * h,
                       OUTLINE, W_OUT))
    return specs


def build_graduated_cylinder(w, h):
    """Tall narrow tube on small base, graduation ticks, liquid."""
    specs = []
    tw = 0.34 * w
    x = 0.5 * w - tw / 2
    top = 0.08 * h
    bot = 0.86 * h
    # base
    base_w = 0.60 * w
    specs.append(_trap_or_rect_base(specs, w, h, base_w, bot))
    # liquid
    liq_top = 0.40 * h
    specs.append(_rect(x, liq_top, tw, bot - liq_top, NONE, LIQUID, W_DET))
    # walls + bottom
    specs.append(_rect(x, top, tw, bot - top, OUTLINE, NONE, W_OUT))
    # liquid surface
    specs.append(_line(x, liq_top, x + tw, liq_top, OUTLINE, W_DET))
    # spout at top-left
    specs.append(_line(x, top, x - 0.05 * w, top - 0.04 * h, OUTLINE, W_OUT))
    # graduation ticks
    for fr in (0.30, 0.45, 0.60, 0.75):
        yy = top + (bot - top) * fr
        specs.append(_line(x + tw - 0.10 * w, yy, x + tw, yy, OUTLINE, W_DET))
    return [s for s in specs if s is not None]


def _trap_or_rect_base(specs, w, h, base_w, bot):
    """Append a splayed foot (flared pedestal) under a tube; helper."""
    base_h = 0.10 * h
    # flared stem: trapezoid widening downward
    specs.append({"shape": "trapezoid",
                  "x": 0.5 * w - base_w / 2, "y": bot,
                  "w": base_w, "h": base_h, "rotation": 180.0,
                  "stroke": OUTLINE, "fill": GLASS, "width": W_OUT})
    # solid base pad
    specs.append(_rrect(0.5 * w - base_w / 2, bot + base_h,
                        base_w, 0.04 * h, 0.02 * h, OUTLINE, GLASS, W_OUT))
    return None


def build_funnel(w, h):
    """Wide inverted trapezoid cone narrowing into a thin stem tube."""
    specs = []
    top = 0.12 * h
    cone_bot = 0.50 * h
    stem_bot = 0.92 * h
    tl, tr = 0.10 * w, 0.90 * w
    sw = 0.14 * w
    sl, sr = 0.5 * w - sw / 2, 0.5 * w + sw / 2
    # cone walls
    specs.append(_line(tl, top, sl, cone_bot, OUTLINE, W_OUT))
    specs.append(_line(tr, top, sr, cone_bot, OUTLINE, W_OUT))
    # top rim
    specs.append(_line(tl, top, tr, top, OUTLINE, W_OUT))
    # stem
    specs.append(_rect(sl, cone_bot, sw, stem_bot - cone_bot,
                       OUTLINE, GLASS, W_OUT))
    return specs


def build_separating_funnel(w, h):
    """Pear shape + stopcock valve at bottom + stopper on top."""
    specs = []
    cx = 0.5 * w
    # stopper (top)
    sp_w = 0.20 * w
    specs.append({"shape": "trapezoid", "x": cx - sp_w / 2, "y": 0.04 * h,
                  "w": sp_w, "h": 0.10 * h, "rotation": 180.0,
                  "stroke": OUTLINE, "fill": METAL, "width": W_OUT})
    # neck
    nw = 0.14 * w
    specs.append(_rect(cx - nw / 2, 0.14 * h, nw, 0.10 * h,
                       OUTLINE, GLASS, W_OUT))
    # pear bulb: circle bottom + tapered shoulders to neck
    d = 0.56 * w
    bulb_top = 0.30 * h
    bulb_bot = 0.74 * h
    specs.append(_circle(cx - d / 2, bulb_bot - d, d, d, OUTLINE, GLASS,
                         W_OUT))
    # shoulders (taper from neck width to bulb)
    specs.append(_line(cx - nw / 2, 0.24 * h, cx - d / 2 + 0.06 * d,
                       bulb_bot - d + 0.18 * d, OUTLINE, W_OUT))
    specs.append(_line(cx + nw / 2, 0.24 * h, cx + d / 2 - 0.06 * d,
                       bulb_bot - d + 0.18 * d, OUTLINE, W_OUT))
    # liquid contained in the lower bulb
    fill, surf = _bulb_liquid(cx, bulb_bot - d, d, 0.46)
    specs.append(fill)
    specs.append(surf)
    # stopcock stem
    specs.append(_rect(cx - 0.05 * w, bulb_bot, 0.10 * w, 0.06 * h,
                       OUTLINE, GLASS, W_OUT))
    # valve (small cross / diamond)
    vy = bulb_bot + 0.08 * h
    specs.append(_poly("diamond", cx - 0.10 * w, vy - 0.05 * h,
                       0.20 * w, 0.10 * h, 0.0, OUTLINE, METAL, W_DET))
    specs.append(_line(cx - 0.14 * w, vy, cx + 0.14 * w, vy, OUTLINE, W_DET))
    # tip
    specs.append(_rect(cx - 0.04 * w, vy + 0.05 * h, 0.08 * w, 0.10 * h,
                       OUTLINE, GLASS, W_OUT))
    return specs


def build_condenser(w, h):
    """Liebig condenser: vertical double-tube + side water stubs."""
    specs = []
    top = 0.08 * h
    bot = 0.92 * h
    cx = 0.5 * w
    inner_w = 0.16 * w
    outer_w = 0.40 * w
    # outer jacket
    specs.append(_rect(cx - outer_w / 2, top + 0.06 * h, outer_w,
                       bot - top - 0.12 * h, OUTLINE, GLASS, W_OUT))
    # inner tube (full length)
    specs.append(_rect(cx - inner_w / 2, top, inner_w, bot - top,
                       OUTLINE, GLASS, W_OUT))
    # liquid in inner tube
    specs.append(_rect(cx - inner_w / 2 + 0.01 * w, 0.45 * h,
                       inner_w - 0.02 * w, bot - 0.45 * h, NONE, LIQUID,
                       W_DET))
    # water stubs
    sl = cx - outer_w / 2
    sr = cx + outer_w / 2
    specs.append(_rect(sl - 0.12 * w, 0.22 * h, 0.12 * w, 0.08 * h,
                       OUTLINE, GLASS, W_OUT))
    specs.append(_rect(sr, 0.70 * h, 0.12 * w, 0.08 * h, OUTLINE, GLASS,
                       W_OUT))
    return specs


# ===========================================================================
# Dishes & tubes
# ===========================================================================
def build_petri_dish(w, h):
    """Shallow wide dish (side view) with lid line."""
    specs = []
    dy = 0.55 * h
    dh = 0.28 * h
    dx = 0.08 * w
    dw = 0.84 * w
    # base dish
    specs.append(_rrect(dx, dy, dw, dh, dh * 0.45, OUTLINE, GLASS, W_OUT))
    # lid (slightly wider, on top)
    ly = 0.40 * h
    lh = 0.20 * h
    specs.append(_rrect(dx - 0.03 * w, ly, dw + 0.06 * w, lh, lh * 0.45,
                        OUTLINE, GLASS, W_OUT))
    return specs


def build_watch_glass(w, h):
    """Very shallow concave arc (flat watch glass)."""
    specs = []
    cx = 0.5 * w
    gw = 0.84 * w
    # shallow concave: halfcircle, flat, thin
    specs.append(_half(cx - gw / 2, 0.42 * h, gw, 0.36 * h, 0.0,
                       OUTLINE, GLASS, W_OUT))
    # top rim line (the open mouth)
    specs.append(_line(cx - gw / 2, 0.42 * h + 0.18 * h,
                       cx + gw / 2, 0.42 * h + 0.18 * h, OUTLINE, W_OUT))
    return specs


def build_burette(w, h):
    """Very long thin graduated tube + stopcock near bottom + fine tip."""
    specs = []
    tw = 0.30 * w
    x = 0.5 * w - tw / 2
    top = 0.04 * h
    stop_y = 0.82 * h
    # liquid
    specs.append(_rect(x, 0.30 * h, tw, stop_y - 0.30 * h, NONE, LIQUID,
                       W_DET))
    # tube
    specs.append(_rect(x, top, tw, stop_y - top, OUTLINE, NONE, W_OUT))
    # liquid surface
    specs.append(_line(x, 0.30 * h, x + tw, 0.30 * h, OUTLINE, W_DET))
    # graduations
    for i in range(1, 8):
        yy = top + (stop_y - top) * i / 8.0
        specs.append(_line(x + tw - 0.08 * w, yy, x + tw, yy, OUTLINE, W_DET))
    # stopcock
    cx = 0.5 * w
    specs.append(_poly("diamond", cx - 0.12 * w, stop_y, 0.24 * w, 0.08 * h,
                       0.0, OUTLINE, METAL, W_DET))
    specs.append(_line(cx - 0.16 * w, stop_y + 0.04 * h,
                       cx + 0.16 * w, stop_y + 0.04 * h, OUTLINE, W_DET))
    # short stem below the stopcock, then the fine tapered tip
    specs.append(_rect(cx - 0.04 * w, stop_y + 0.08 * h, 0.08 * w, 0.04 * h,
                       OUTLINE, GLASS, W_OUT))
    specs.append({"shape": "triangle", "x": cx - 0.04 * w,
                  "y": stop_y + 0.12 * h, "w": 0.08 * w, "h": 0.06 * h,
                  "rotation": 180.0, "stroke": OUTLINE, "fill": GLASS,
                  "width": W_OUT})
    return specs


def build_pipette(w, h):
    """Long thin tube with a central bulb and tapered tip."""
    specs = []
    cx = 0.5 * w
    tw = 0.16 * w
    top = 0.04 * h
    bot = 0.90 * h
    # tube top half
    specs.append(_rect(cx - tw / 2, top, tw, 0.34 * h, OUTLINE, GLASS, W_OUT))
    # central bulb
    bw = 0.46 * w
    specs.append(_ellipse(cx - bw / 2, 0.34 * h, bw, 0.24 * h, OUTLINE,
                          GLASS, W_OUT))
    # liquid: lower half of the bulb (dome bulging down)
    specs.append(_half(cx - bw / 2, 0.46 * h, bw, 0.12 * h,
                       180.0, NONE, LIQUID, W_DET))
    specs.append(_line(cx - bw / 2, 0.46 * h, cx + bw / 2, 0.46 * h,
                       OUTLINE, W_DET))
    # tube lower half
    specs.append(_rect(cx - tw / 2, 0.58 * h, tw, 0.20 * h, OUTLINE, GLASS,
                       W_OUT))
    # tapered tip
    specs.append({"shape": "triangle", "x": cx - tw / 2, "y": 0.78 * h,
                  "w": tw, "h": bot - 0.78 * h, "rotation": 180.0,
                  "stroke": OUTLINE, "fill": GLASS, "width": W_OUT})
    return specs


def build_dropper(w, h):
    """Small tube with a rubber bulb on top."""
    specs = []
    cx = 0.5 * w
    tw = 0.18 * w
    # rubber bulb (ellipse)
    bw = 0.40 * w
    specs.append(_ellipse(cx - bw / 2, 0.06 * h, bw, 0.28 * h, OUTLINE,
                          METAL, W_OUT))
    # tube
    specs.append(_rect(cx - tw / 2, 0.34 * h, tw, 0.44 * h, OUTLINE, GLASS,
                       W_OUT))
    # liquid
    specs.append(_rect(cx - tw / 2 + 0.01 * w, 0.55 * h, tw - 0.02 * w,
                       0.23 * h, NONE, LIQUID, W_DET))
    # tapered tip
    specs.append({"shape": "triangle", "x": cx - tw / 2, "y": 0.78 * h,
                  "w": tw, "h": 0.16 * h, "rotation": 180.0,
                  "stroke": OUTLINE, "fill": GLASS, "width": W_OUT})
    return specs


# ===========================================================================
# Heat & support
# ===========================================================================
def build_bunsen_burner(w, h):
    """Base + vertical barrel + orange flame triangle on top."""
    specs = []
    cx = 0.5 * w
    # base
    base_w = 0.60 * w
    specs.append({"shape": "trapezoid", "x": cx - base_w / 2, "y": 0.84 * h,
                  "w": base_w, "h": 0.10 * h, "rotation": 180.0,
                  "stroke": OUTLINE, "fill": METAL, "width": W_OUT})
    # barrel
    bw = 0.18 * w
    specs.append(_rect(cx - bw / 2, 0.40 * h, bw, 0.44 * h, OUTLINE, METAL,
                       W_OUT))
    # air-hole collar
    specs.append(_rect(cx - bw / 2 - 0.03 * w, 0.66 * h, bw + 0.06 * w,
                       0.06 * h, OUTLINE, METAL, W_DET))
    # flame (orange triangle)
    fw = 0.30 * w
    specs.append({"shape": "triangle", "x": cx - fw / 2, "y": 0.10 * h,
                  "w": fw, "h": 0.30 * h, "rotation": 0.0,
                  "stroke": FLAME, "fill": FLAME, "width": W_DET})
    # inner blue cone
    specs.append({"shape": "triangle", "x": cx - fw * 0.25, "y": 0.26 * h,
                  "w": fw * 0.5, "h": 0.14 * h, "rotation": 0.0,
                  "stroke": LIQUID, "fill": LIQUID, "width": W_DET})
    return specs


def build_hotplate(w, h):
    """Appliance box + round heating plate on top + control knob."""
    specs = []
    # body
    by = 0.45 * h
    specs.append(_rrect(0.08 * w, by, 0.84 * w, 0.45 * h, 0.04 * w,
                        OUTLINE, METAL, W_OUT))
    # heating plate on top
    pd = 0.46 * w
    cx = 0.5 * w
    specs.append(_circle(cx - pd / 2, by - 0.14 * h, pd, 0.20 * h,
                         OUTLINE, "#bcc4cc", W_OUT))
    # plate as ellipse top surface
    specs.append(_ellipse(cx - pd / 2, by - 0.18 * h, pd, 0.14 * h,
                          OUTLINE, "#d8dee5", W_OUT))
    # control knob
    specs.append(_circle(0.74 * w, by + 0.14 * h, 0.10 * w, 0.10 * w,
                         OUTLINE, "#9aa3ad", W_DET))
    # display
    specs.append(_rect(0.16 * w, by + 0.12 * h, 0.22 * w, 0.10 * h,
                       OUTLINE, "#1d2a36", W_DET))
    # feet
    specs.append(_rect(0.14 * w, 0.90 * h, 0.06 * w, 0.05 * h, OUTLINE,
                       METAL, W_DET))
    specs.append(_rect(0.80 * w, 0.90 * h, 0.06 * w, 0.05 * h, OUTLINE,
                       METAL, W_DET))
    return specs


def build_retort_stand(w, h):
    """Heavy base + tall vertical rod + one horizontal clamp arm."""
    specs = []
    # base
    specs.append(_rect(0.10 * w, 0.88 * h, 0.70 * w, 0.08 * h, OUTLINE,
                       METAL, W_OUT))
    # rod
    rod_x = 0.20 * w
    specs.append(_rect(rod_x, 0.06 * h, 0.06 * w, 0.82 * h, OUTLINE, METAL,
                       W_OUT))
    # boss head (clamp mount)
    specs.append(_rect(rod_x - 0.02 * w, 0.30 * h, 0.12 * w, 0.10 * h,
                       OUTLINE, "#9aa3ad", W_DET))
    # clamp arm
    specs.append(_rect(rod_x + 0.08 * w, 0.33 * h, 0.50 * w, 0.04 * h,
                       OUTLINE, METAL, W_OUT))
    # clamp jaws at arm end
    specs.append(_poly("triangle", 0.70 * w, 0.28 * h, 0.14 * w, 0.07 * h,
                       180.0, OUTLINE, METAL, W_DET))
    specs.append(_poly("triangle", 0.70 * w, 0.36 * h, 0.14 * w, 0.07 * h,
                       0.0, OUTLINE, METAL, W_DET))
    return specs


def build_tripod(w, h):
    """Flat top ring/line on three splayed legs."""
    specs = []
    cx = 0.5 * w
    top_y = 0.30 * h
    # top ring (ellipse seen edge-on) + line
    specs.append(_ellipse(0.16 * w, top_y - 0.03 * h, 0.68 * w, 0.08 * h,
                          OUTLINE, NONE, W_OUT))
    specs.append(_line(0.16 * w, top_y, 0.84 * w, top_y, OUTLINE, W_OUT))
    # three legs
    specs.append(_line(0.24 * w, top_y, 0.16 * w, 0.92 * h, OUTLINE, W_OUT))
    specs.append(_line(cx, top_y, cx, 0.92 * h, OUTLINE, W_OUT))
    specs.append(_line(0.76 * w, top_y, 0.84 * w, 0.92 * h, OUTLINE, W_OUT))
    return specs


def build_gauze(w, h):
    """Small square of wire gauze with cross-hatch grid."""
    specs = []
    x, y = 0.14 * w, 0.30 * h
    gw, gh = 0.72 * w, 0.40 * h
    specs.append(_rect(x, y, gw, gh, OUTLINE, "#e7ebef", W_OUT))
    # grid
    n = 5
    for i in range(1, n):
        vx = x + gw * i / n
        specs.append(_line(vx, y, vx, y + gh, OUTLINE, W_DET))
        hy = y + gh * i / n
        specs.append(_line(x, hy, x + gw, hy, OUTLINE, W_DET))
    # support frame legs
    specs.append(_line(x + 0.06 * w, y + gh, x + 0.06 * w, 0.90 * h,
                       OUTLINE, W_DET))
    specs.append(_line(x + gw - 0.06 * w, y + gh, x + gw - 0.06 * w,
                       0.90 * h, OUTLINE, W_DET))
    return specs


# ===========================================================================
# Other
# ===========================================================================
def build_gas_cylinder(w, h):
    """Tall rounded-top cylinder + valve/regulator on top."""
    specs = []
    cx = 0.5 * w
    bw = 0.56 * w
    bx = cx - bw / 2
    body_top = 0.20 * h
    body_bot = 0.94 * h
    # rounded-top body
    specs.append(_rrect(bx, body_top, bw, body_bot - body_top, bw * 0.35,
                        OUTLINE, "#b04a3a", W_OUT))
    # shoulder highlight band
    specs.append(_rect(bx, 0.30 * h, bw, 0.04 * h, NONE, "#c95b4a", W_DET))
    # valve neck
    vw = 0.16 * w
    specs.append(_rect(cx - vw / 2, 0.10 * h, vw, 0.12 * h, OUTLINE, METAL,
                       W_OUT))
    # regulator / handwheel
    specs.append(_circle(cx - 0.12 * w, 0.02 * h, 0.18 * w, 0.10 * h,
                         OUTLINE, METAL, W_DET))
    specs.append(_line(cx - 0.12 * w, 0.07 * h, cx + 0.06 * w, 0.07 * h,
                       OUTLINE, W_DET))
    return specs


def build_balance(w, h):
    """Benchtop balance: base box + flat pan on top + small display."""
    specs = []
    # base
    by = 0.55 * h
    specs.append(_rrect(0.10 * w, by, 0.80 * w, 0.38 * h, 0.04 * w,
                        OUTLINE, METAL, W_OUT))
    # display
    specs.append(_rect(0.18 * w, by + 0.10 * h, 0.30 * w, 0.14 * h,
                       OUTLINE, "#1d2a36", W_DET))
    # buttons
    specs.append(_circle(0.62 * w, by + 0.12 * h, 0.06 * w, 0.06 * w,
                         OUTLINE, "#9aa3ad", W_DET))
    specs.append(_circle(0.74 * w, by + 0.12 * h, 0.06 * w, 0.06 * w,
                         OUTLINE, "#9aa3ad", W_DET))
    # pan support
    cx = 0.5 * w
    specs.append(_rect(cx - 0.03 * w, 0.42 * h, 0.06 * w, 0.14 * h,
                       OUTLINE, METAL, W_DET))
    # flat pan (ellipse)
    specs.append(_ellipse(0.24 * w, 0.34 * h, 0.52 * w, 0.12 * h,
                          OUTLINE, "#d8dee5", W_OUT))
    return specs


def build_wash_bottle(w, h):
    """Squeeze bottle body + angled delivery tube from the cap."""
    specs = []
    cx = 0.5 * w
    bw = 0.50 * w
    bx = cx - bw / 2
    body_top = 0.34 * h
    specs.append(_rrect(bx, body_top, bw, 0.94 * h - body_top, bw * 0.18,
                        OUTLINE, "#dfeaf2", W_OUT))
    # liquid
    specs.append(_rect(bx + 0.02 * w, 0.60 * h, bw - 0.04 * w,
                       0.34 * h - 0.06 * h, NONE, LIQUID, W_DET))
    specs.append(_line(bx + 0.02 * w, 0.60 * h, bx + bw - 0.02 * w, 0.60 * h,
                       OUTLINE, W_DET))
    # neck + cap
    nw = 0.22 * w
    specs.append(_rect(cx - nw / 2, 0.22 * h, nw, 0.12 * h, OUTLINE, METAL,
                       W_OUT))
    # angled delivery tube
    specs.append(_line(cx, 0.22 * h, cx - 0.02 * w, 0.10 * h, OUTLINE, W_OUT))
    specs.append(_line(cx - 0.02 * w, 0.10 * h, 0.78 * w, 0.16 * h,
                       OUTLINE, W_OUT))
    return specs


# ===========================================================================
# Sizes (mm), labels, categories
# ===========================================================================
SIZES = {
    # Glassware
    "beaker": (100.0, 120.0),
    "erlenmeyer": (120.0, 160.0),
    "round_bottom_flask": (120.0, 180.0),
    "volumetric_flask": (90.0, 220.0),
    "test_tube": (40.0, 160.0),
    "graduated_cylinder": (70.0, 240.0),
    "funnel": (120.0, 150.0),
    "separating_funnel": (120.0, 280.0),
    "condenser": (110.0, 320.0),
    # Dishes & tubes
    "petri_dish": (120.0, 40.0),
    "watch_glass": (100.0, 30.0),
    "burette": (50.0, 400.0),
    "pipette": (60.0, 320.0),
    "dropper": (40.0, 120.0),
    # Heat & support
    "bunsen_burner": (120.0, 200.0),
    "hotplate": (220.0, 160.0),
    "retort_stand": (300.0, 600.0),
    "tripod": (180.0, 160.0),
    "gauze": (140.0, 120.0),
    # Other
    "gas_cylinder": (180.0, 520.0),
    "balance": (220.0, 180.0),
    "wash_bottle": (110.0, 220.0),
}

LABELS = {
    "beaker": "Beaker",
    "erlenmeyer": "Erlenmeyer flask",
    "round_bottom_flask": "Round-bottom flask",
    "volumetric_flask": "Volumetric flask",
    "test_tube": "Test tube",
    "graduated_cylinder": "Graduated cylinder",
    "funnel": "Funnel",
    "separating_funnel": "Separating funnel",
    "condenser": "Condenser",
    "petri_dish": "Petri dish",
    "watch_glass": "Watch glass",
    "burette": "Burette",
    "pipette": "Pipette",
    "dropper": "Dropper",
    "bunsen_burner": "Bunsen burner",
    "hotplate": "Hotplate",
    "retort_stand": "Retort stand",
    "tripod": "Tripod",
    "gauze": "Wire gauze",
    "gas_cylinder": "Gas cylinder",
    "balance": "Balance",
    "wash_bottle": "Wash bottle",
}

CATEGORIES = [
    ("Glassware", ["beaker", "erlenmeyer", "round_bottom_flask",
                   "volumetric_flask", "test_tube", "graduated_cylinder",
                   "funnel", "separating_funnel", "condenser"]),
    ("Dishes & tubes", ["petri_dish", "watch_glass", "burette", "pipette",
                        "dropper"]),
    ("Heat & support", ["bunsen_burner", "hotplate", "retort_stand",
                        "tripod", "gauze"]),
    ("Other", ["gas_cylinder", "balance", "wash_bottle"]),
]


_BUILDERS = {name: globals()["build_" + name] for name in SIZES}


def build_specs(name, w, h):
    return _BUILDERS[name](w, h)


def size_mm(name):
    return SIZES[name]
