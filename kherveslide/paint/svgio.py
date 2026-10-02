"""SVG import/export — the editable, default document format.

Two directions:

* **Write** (`save_svg`) emits clean, standard SVG: one element per
  native item, geometry in local coordinates with a `translate`/
  `rotate` transform, the raster layer as an embedded `<image>`, and
  KhervePaint-specific bits (grid settings, polygon kind, arrow flag)
  under a private ``kp:`` namespace so our own files round-trip
  losslessly while staying readable by any SVG tool.

* **Read** (`load_svg`) parses an arbitrary SVG into *editable* native
  items.  `<g>` becomes a `GroupItem` (so it can be ungrouped), the
  common primitives become their native items, and anything carrying a
  non-trivial (scaled/sheared) transform — or a `<path>` — becomes a
  `PathItem`.  This is what lets an imported SVG be broken apart and
  edited entity by entity.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import base64
import math
import re
import xml.etree.ElementTree as ET

from PySide6.QtCore import QBuffer, QByteArray, QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QPainterPath, QPen, QPixmap,
                         QPolygonF, QTransform)

from .canvas import (ARC_KINDS, ArcShapeItem, ArrowItem, DimensionItem,
                     EllipseItem, GroupItem, ImageItem, LabelMixin, LineItem,
                     PaintScene, PathItem, PolygonItem, RectItem,
                     RoundedRectItem, TextItem, center_origin)
from . import gradient
from .document import (DASH_STYLES, cmds_to_painterpath, dash_name,
                       painterpath_to_cmds)

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
# Internal SVG namespace for our private attributes (grid, dim style,
# polygon kind, raster role…). Kept at the original URI — not the renamed
# one — so SVGs saved before the rename still round-trip. It is never
# shown to users (only the "kp:" prefix appears in the file).
KP_NS = "https://kerherve.app/khervepaint"

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)
ET.register_namespace("kp", KP_NS)

_EPS = 1e-4


def _svg(tag):
    return f"{{{SVG_NS}}}{tag}"


def _kp(tag):
    return f"{{{KP_NS}}}{tag}"


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _float_or_none(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _json_or_none(text):
    if not text:
        return None
    try:
        import json
        return json.loads(text)
    except (TypeError, ValueError):
        return None


# ================================================================ writing
def _pixmap_data_uri(pixmap: QPixmap) -> str:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QBuffer.WriteOnly)
    pixmap.save(buf, "PNG")
    buf.close()
    b64 = base64.b64encode(bytes(data)).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _transform_attr(item) -> str:
    # Scaled items (incl. resized groups) are emitted as the exact
    # transform matrix, which encodes the centre transform-origin. A bare
    # scale(s) ignores that origin, so the loader — which bakes scaled
    # geometry — would shift the item by origin·(1−s). Rotation-only and
    # translation stay human-readable: the loader rebuilds those about the
    # centre itself, so the simple form round-trips exactly.
    if abs(item.scale() - 1) > _EPS or not item.transform().isIdentity():
        m = (item.sceneTransform() if item.parentItem() is None
             else item.itemTransform(item.parentItem()))
        return _matrix_attr(m)
    parts = []
    pos = item.pos()
    if abs(pos.x()) > _EPS or abs(pos.y()) > _EPS:
        parts.append(f"translate({pos.x():g},{pos.y():g})")
    if abs(item.rotation()) > _EPS:
        parts.append(f"rotate({item.rotation():g})")
    return " ".join(parts)


def _set_common(el, item):
    tf = _transform_attr(item)
    if tf:
        el.set("transform", tf)
    if item.opacity() < 1 - _EPS:
        el.set("opacity", f"{item.opacity():g}")


def _set_stroke(el, pen: QPen):
    if pen.style() == Qt.NoPen:
        el.set("stroke", "none")
        return
    color = pen.color()
    el.set("stroke", color.name())
    el.set("stroke-width", f"{pen.widthF():g}")
    if color.alpha() < 255:
        el.set("stroke-opacity", f"{color.alphaF():g}")
    el.set("stroke-linecap", "round")
    el.set("stroke-linejoin", "round")
    dash = dash_name(pen)
    if dash != "solid":
        w = max(pen.widthF(), 1.0)
        el.set("stroke-dasharray",
               ",".join(f"{v * w:g}" for v in pen.dashPattern()))
        el.set(_kp("dash"), dash)


def _set_fill(el, brush: QBrush, ctx=None):
    if brush is None or brush.style() == Qt.NoBrush:
        el.set("fill", "none")
        return
    spec = gradient.brush_spec(brush)
    if spec is not None and ctx is not None:
        el.set("fill", f"url(#{_gradient_def(ctx, spec)})")
        return
    color = brush.color()
    el.set("fill", color.name())
    if color.alpha() < 255:
        el.set("fill-opacity", f"{color.alphaF():g}")


def _gradient_def(ctx, spec) -> str:
    """Write *spec* as a <linearGradient>/<radialGradient> in the file's
    <defs> (created on first use) and return its id. *ctx* is the save
    context: {"root": svg element, "defs": element|None, "n": counter}."""
    if ctx["defs"] is None:
        ctx["defs"] = ET.Element(_svg("defs"))
        ctx["root"].insert(0, ctx["defs"])
    ctx["n"] += 1
    gid = f"kpgrad{ctx['n']}"
    stops = ((0, "c1"), (1, "c2"))
    if spec["kind"] == "radial":
        el = ET.SubElement(ctx["defs"], _svg("radialGradient"))
        el.set("cx", "0.5"); el.set("cy", "0.5"); el.set("r", "0.7071")
    elif spec["kind"] == "sun":       # off-centre highlight, light first
        el = ET.SubElement(ctx["defs"], _svg("radialGradient"))
        cx, cy = gradient.SUN_CENTER
        fx, fy = gradient.SUN_FOCAL
        el.set("cx", f"{cx:g}"); el.set("cy", f"{cy:g}")
        el.set("r", f"{gradient.SUN_RADIUS:g}")
        el.set("fx", f"{fx:g}"); el.set("fy", f"{fy:g}")
        stops = ((0, "c2"), (1, "c1"))
    else:
        el = ET.SubElement(ctx["defs"], _svg("linearGradient"))
        x1, y1, x2, y2 = gradient.angle_points(spec.get("angle", 90.0))
        el.set("x1", f"{x1:g}"); el.set("y1", f"{y1:g}")
        el.set("x2", f"{x2:g}"); el.set("y2", f"{y2:g}")
    el.set("id", gid)
    el.set("gradientUnits", "objectBoundingBox")
    for offset, name in stops:
        color = QColor(spec[name])
        stop = ET.SubElement(el, _svg("stop"))
        stop.set("offset", str(offset))
        stop.set("stop-color", color.name())
        if color.alpha() < 255:
            stop.set("stop-opacity", f"{color.alphaF():g}")
    return gid


def _line_element(parent, item):
    """A line/arrow as SVG: `<line>` when straight, or — when bent — a
    quadratic `<path>` (so any viewer draws the curve) whose endpoints
    and control point ride along in kp: attributes for round-trip."""
    ln = item.line()
    bend = item.bend()
    if bend is None:
        el = ET.SubElement(parent, _svg("line"))
        el.set("x1", f"{ln.x1():g}"); el.set("y1", f"{ln.y1():g}")
        el.set("x2", f"{ln.x2():g}"); el.set("y2", f"{ln.y2():g}")
        return el
    el = ET.SubElement(parent, _svg("path"))
    el.set("d", f"M{ln.x1():g},{ln.y1():g} Q{bend.x():g},{bend.y():g} "
                f"{ln.x2():g},{ln.y2():g}")
    el.set("fill", "none")
    el.set(_kp("x1"), f"{ln.x1():g}"); el.set(_kp("y1"), f"{ln.y1():g}")
    el.set(_kp("x2"), f"{ln.x2():g}"); el.set(_kp("y2"), f"{ln.y2():g}")
    el.set(_kp("bend"), f"{bend.x():g} {bend.y():g}")
    return el


def painterpath_to_d(path: QPainterPath) -> str:
    out = []
    for c in painterpath_to_cmds(path):
        if c[0] == "M":
            out.append(f"M{c[1]:g},{c[2]:g}")
        elif c[0] == "L":
            out.append(f"L{c[1]:g},{c[2]:g}")
        elif c[0] == "C":
            out.append(f"C{c[1]:g},{c[2]:g} {c[3]:g},{c[4]:g} "
                       f"{c[5]:g},{c[6]:g}")
    return " ".join(out)


def _item_to_element(parent, item, ctx=None):
    if isinstance(item, GroupItem):
        from .handles import Handle
        g = ET.SubElement(parent, _svg("g"))
        _set_common(g, item)
        if getattr(item, "mol_name", None):      # 3D molecule/crystal model
            g.set(_kp("model"), item.mol_name)
            if getattr(item, "mol_az", None) is not None:
                g.set(_kp("model-az"), f"{item.mol_az:g}")
            if getattr(item, "mol_el", None) is not None:
                g.set(_kp("model-el"), f"{item.mol_el:g}")
            if getattr(item, "mol_bond", None) is not None:
                g.set(_kp("model-bond"), f"{item.mol_bond:g}")
            if getattr(item, "mol_box", None) is not None:
                g.set(_kp("model-box"), f"{item.mol_box:g}")
            if getattr(item, "mol_repr", None):
                g.set(_kp("model-repr"), item.mol_repr)
            if getattr(item, "mol_colors", None):  # colour override map
                import json as _json
                g.set(_kp("model-colors"), _json.dumps(item.mol_colors))
            if getattr(item, "mol_tilts", None):   # per-cell tilt map
                import json as _json
                g.set(_kp("model-tilts"), _json.dumps(item.mol_tilts))
            if getattr(item, "mol_poly", False):   # coordination polyhedra
                g.set(_kp("model-poly"), "1")
            if getattr(item, "mol_cells", None):   # stacked supercell counts
                import json as _json
                g.set(_kp("model-cells"), _json.dumps(list(item.mol_cells)))
            if getattr(item, "mol_atoms", None):   # hand-built structure
                import json as _json
                g.set(_kp("model-atoms"), _json.dumps(item.mol_atoms))
                g.set(_kp("model-bonds"), _json.dumps(item.mol_bonds or []))
        if getattr(item, "symbol", None):          # palette symbol identity
            g.set(_kp("symbol"), item.symbol)
        if getattr(item, "solid", None):           # rotatable 3D solid
            import json as _json
            g.set(_kp("solid"), _json.dumps(item.solid))
        if getattr(item, "rxn_data", None):        # re-editable reaction
            import json as _json
            g.set(_kp("reaction"), _json.dumps(item.rxn_data,
                                               ensure_ascii=False))
        for child in item.childItems():
            if not isinstance(child, Handle):
                _item_to_element(g, child, ctx)
        return g

    if isinstance(item, DimensionItem):
        ln = item.line()
        el = ET.SubElement(parent, _svg("line"))
        el.set("x1", f"{ln.x1():g}"); el.set("y1", f"{ln.y1():g}")
        el.set("x2", f"{ln.x2():g}"); el.set("y2", f"{ln.y2():g}")
        el.set(_kp("kind"), "dimension")
        el.set(_kp("dim-cap"), item.cap_style)
        el.set(_kp("dim-ext"), "1" if item.extension else "0")
        el.set(_kp("dim-dash"), "1" if item.dash else "0")
        el.set(_kp("dim-unit"), item.unit)
        el.set(_kp("dim-decimals"), str(item.decimals))
        if item.prefix:
            el.set(_kp("dim-prefix"), item.prefix)
        if item.suffix:
            el.set(_kp("dim-suffix"), item.suffix)
        _set_stroke(el, item.pen())
    elif isinstance(item, ArrowItem):
        el = _line_element(parent, item)
        el.set(_kp("kind"), "arrow")
        if item.head != "filled":
            el.set(_kp("head"), item.head)
        _set_stroke(el, item.pen())
    elif isinstance(item, LineItem):
        el = _line_element(parent, item)
        _set_stroke(el, item.pen())
    elif isinstance(item, RoundedRectItem):
        r = item.rect()
        el = ET.SubElement(parent, _svg("rect"))
        el.set("x", f"{r.x():g}"); el.set("y", f"{r.y():g}")
        el.set("width", f"{r.width():g}"); el.set("height", f"{r.height():g}")
        el.set("rx", f"{item.radius():g}"); el.set("ry", f"{item.radius():g}")
        _set_stroke(el, item.pen()); _set_fill(el, item.brush(), ctx)
    elif isinstance(item, RectItem):
        r = item.rect()
        el = ET.SubElement(parent, _svg("rect"))
        el.set("x", f"{r.x():g}"); el.set("y", f"{r.y():g}")
        el.set("width", f"{r.width():g}"); el.set("height", f"{r.height():g}")
        _set_stroke(el, item.pen()); _set_fill(el, item.brush(), ctx)
    elif isinstance(item, EllipseItem):
        r = item.rect()
        el = ET.SubElement(parent, _svg("ellipse"))
        el.set("cx", f"{r.center().x():g}"); el.set("cy", f"{r.center().y():g}")
        el.set("rx", f"{r.width() / 2:g}"); el.set("ry", f"{r.height() / 2:g}")
        _set_stroke(el, item.pen()); _set_fill(el, item.brush(), ctx)
    elif isinstance(item, PolygonItem):
        el = ET.SubElement(parent, _svg("polygon"))
        pts = " ".join(f"{p.x():g},{p.y():g}" for p in item.polygon())
        el.set("points", pts)
        if item.kind and item.kind != "polygon":
            el.set(_kp("kind"), item.kind)
        _set_stroke(el, item.pen()); _set_fill(el, item.brush(), ctx)
    elif isinstance(item, ArcShapeItem):
        el = ET.SubElement(parent, _svg("path"))
        el.set("d", painterpath_to_d(item.path()))
        r = item.rect()
        el.set(_kp("kind"), item.kind)
        el.set(_kp("ax"), f"{r.x():g}"); el.set(_kp("ay"), f"{r.y():g}")
        el.set(_kp("aw"), f"{r.width():g}"); el.set(_kp("ah"), f"{r.height():g}")
        if item.flip_h:
            el.set(_kp("flip-h"), "1")
        if item.flip_v:
            el.set(_kp("flip-v"), "1")
        _set_stroke(el, item.pen()); _set_fill(el, item.brush(), ctx)
    elif isinstance(item, PathItem):
        el = ET.SubElement(parent, _svg("path"))
        el.set("d", painterpath_to_d(item.path()))
        _set_stroke(el, item.pen()); _set_fill(el, item.brush(), ctx)
    elif isinstance(item, TextItem):
        el = ET.SubElement(parent, _svg("text"))
        el.set("x", "0"); el.set("y", "0")
        el.set("dominant-baseline", "text-before-edge")
        font = item.font()
        el.set("font-family", font.family())
        el.set("font-size", f"{font.pointSize()}")
        if font.bold():
            el.set("font-weight", "bold")
        if font.italic():
            el.set("font-style", "italic")
        el.set("fill", item.defaultTextColor().name())
        el.text = item.toPlainText()
    elif isinstance(item, ImageItem):
        pm = item.pixmap()
        el = ET.SubElement(parent, _svg("image"))
        el.set("x", "0"); el.set("y", "0")
        el.set("width", f"{pm.width()}"); el.set("height", f"{pm.height()}")
        el.set(f"{{{XLINK_NS}}}href", _pixmap_data_uri(pm))
        # The image's full transform (translate + rotate + scale) goes
        # out as a matrix so resizing and rotation are saved exactly.
        m = (item.sceneTransform() if item.parentItem() is None
             else item.itemTransform(item.parentItem()))
        el.set("transform", _matrix_attr(m))
        if item.opacity() < 1 - _EPS:
            el.set("opacity", f"{item.opacity():g}")
        return el
    else:
        return None
    _set_common(el, item)
    if isinstance(item, LabelMixin) and item.label():
        _emit_label(parent, el, item)
    return el


def _matrix_attr(m) -> str:
    return (f"matrix({m.m11():g},{m.m12():g},{m.m21():g},"
            f"{m.m22():g},{m.dx():g},{m.dy():g})")


def _emit_label(parent, el, item):
    """Store the shape's label under kp: attributes (lossless) and also
    emit a visible <text> sibling so other SVG viewers show it."""
    el.set(_kp("label"), item.label())
    el.set(_kp("label-color"), item.label_color().name())
    el.set(_kp("label-family"), item._label_family)
    el.set(_kp("label-size"), str(item._label_size))
    if item._label_bold:
        el.set(_kp("label-bold"), "1")
    if item._label_italic:
        el.set(_kp("label-italic"), "1")

    c = item.boundingRect().center()
    t = ET.SubElement(parent, _svg("text"))
    t.set("x", f"{c.x():g}"); t.set("y", f"{c.y():g}")
    t.set("text-anchor", "middle")
    t.set("dominant-baseline", "central")
    tf = _transform_attr(item)
    if tf:
        t.set("transform", tf)
    t.set("font-family", item._label_family)
    t.set("font-size", str(item._label_size))
    if item._label_bold:
        t.set("font-weight", "bold")
    if item._label_italic:
        t.set("font-style", "italic")
    t.set("fill", item.label_color().name())
    t.set(_kp("role"), "label")
    t.text = item.label()


def save_svg(scene: PaintScene, path: str):
    rect = scene.sceneRect()
    dpi = getattr(scene, "dpi", 96)
    w, h = int(rect.width()), int(rect.height())
    root = ET.Element(_svg("svg"))
    # Physical size (in) for publication, with a pixel viewBox so the
    # coordinate system stays in px and our loader reads it back exactly.
    root.set("width", f"{w / dpi:g}in")
    root.set("height", f"{h / dpi:g}in")
    root.set("viewBox", f"0 0 {w} {h}")
    root.set(_kp("dpi"), str(dpi))
    root.set(_kp("grid-mm"), f"{scene.grid_mm:g}")
    root.set(_kp("grid-show"), "1" if scene.show_grid else "0")
    root.set(_kp("grid-snap"), "1" if scene.snap_enabled else "0")
    root.set(_kp("infinite"), "1" if scene.infinite else "0")

    raster = scene.raster_item.pixmap()
    if not raster.isNull():
        img = ET.SubElement(root, _svg("image"))
        img.set("x", "0"); img.set("y", "0")
        img.set("width", f"{raster.width()}")
        img.set("height", f"{raster.height()}")
        img.set(_kp("role"), "raster")
        img.set(f"{{{XLINK_NS}}}href", _pixmap_data_uri(raster))

    ctx = {"root": root, "defs": None, "n": 0}
    for item in scene.vector_items():
        _item_to_element(root, item, ctx)

    ET.ElementTree(root).write(path, xml_declaration=True, encoding="utf-8")


# ================================================================ reading
def _color(value: str, fallback="#000000") -> QColor:
    if value is None:
        return QColor(fallback)
    value = value.strip()
    if value in ("none", "transparent"):
        return QColor(Qt.transparent)
    m = re.match(r"rgba?\(([^)]+)\)", value)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        nums = [int(round(float(p[:-1]) * 2.55)) if p.endswith("%")
                else int(round(float(p))) for p in parts[:3]]
        c = QColor(*nums)
        if len(parts) == 4:
            c.setAlphaF(float(parts[3]))
        return c
    c = QColor(value)
    return c if c.isValid() else QColor(fallback)


def _resolve_style(el, inherited: dict) -> dict:
    s = dict(inherited)
    style = el.get("style")
    if style:
        for decl in style.split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                s[k.strip()] = v.strip()
    for key in ("fill", "stroke", "stroke-width", "fill-opacity",
                "stroke-opacity", "font-size", "font-family", "font-weight",
                "font-style"):
        if el.get(key) is not None:
            s[key] = el.get(key)
    if el.get("stroke-dasharray") is not None:
        s["stroke-dasharray"] = el.get("stroke-dasharray")
        s["_dash"] = el.get(_kp("dash"), "dash")
    if el.get("opacity") is not None:           # opacity composes
        s["_opacity"] = s.get("_opacity", 1.0) * float(el.get("opacity"))
    return s


def _pen_from_style(s: dict) -> QPen:
    stroke = s.get("stroke", "none")
    if stroke in (None, "none"):
        return QPen(Qt.NoPen)
    color = _color(stroke)
    if "stroke-opacity" in s:
        color.setAlphaF(float(s["stroke-opacity"]))
    pen = QPen(color, float(s.get("stroke-width", 1)))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    dash = s.get("stroke-dasharray")
    if dash and dash.strip() != "none":
        pen.setStyle(DASH_STYLES.get(s.get("_dash", "dash"), Qt.DashLine))
    return pen


def _brush_from_style(s: dict) -> QBrush:
    fill = s.get("fill", "#000000")        # SVG default fill is black
    if fill in (None, "none"):
        return QBrush(Qt.NoBrush)
    m = re.match(r"url\(\s*['\"]?#([^)'\"]+)['\"]?\s*\)", fill)
    if m:                                  # paint server: gradient by id
        spec = s.get("_gradients", {}).get(m.group(1))
        return (gradient.brush_from_spec(spec) if spec
                else QBrush(Qt.NoBrush))
    color = _color(fill)
    if "fill-opacity" in s:
        color.setAlphaF(float(s["fill-opacity"]))
    return QBrush(color)


def _scan_gradients(root) -> dict:
    """id -> gradient spec for every two(+)-stop gradient in the tree.
    Stops may live on a referenced base gradient (xlink:href chains, as
    Inkscape writes them); only the first and last stop are kept."""
    els = {e.get("id"): e for e in root.iter()
           if _localname(e.tag) in ("linearGradient", "radialGradient")
           and e.get("id")}

    def stops_of(el, depth=0):
        stops = [c for c in el if _localname(c.tag) == "stop"]
        if stops or depth > 4:
            return stops
        href = _href(el)
        if href and href.startswith("#") and href[1:] in els:
            return stops_of(els[href[1:]], depth + 1)
        return []

    def stop_color(stop):
        style = {}
        for decl in (stop.get("style") or "").split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                style[k.strip()] = v.strip()
        color = _color(stop.get("stop-color")
                       or style.get("stop-color"), "#000000")
        opacity = stop.get("stop-opacity") or style.get("stop-opacity")
        if opacity is not None:
            color.setAlphaF(float(opacity))
        return color

    def frac(el, key, default):
        v = el.get(key)
        if v is None:
            return default
        v = v.strip()
        return float(v[:-1]) / 100 if v.endswith("%") else float(v)

    specs = {}
    for gid, el in els.items():
        stops = stops_of(el)
        if not stops:
            continue
        c1, c2 = stop_color(stops[0]), stop_color(stops[-1])
        spec = {"c1": c1.name(QColor.HexArgb), "c2": c2.name(QColor.HexArgb),
                "angle": 90.0}
        if _localname(el.tag) == "radialGradient":
            cx, cy = frac(el, "cx", 0.5), frac(el, "cy", 0.5)
            if abs(cx - 0.5) > 0.01 or abs(cy - 0.5) > 0.01:
                # off-centre highlight = our "sun" kind (light stop first)
                spec["kind"] = "sun"
                spec["c1"], spec["c2"] = spec["c2"], spec["c1"]
            else:
                spec["kind"] = "radial"
        else:
            spec["kind"] = "linear"
            dx = frac(el, "x2", 1.0) - frac(el, "x1", 0.0)
            dy = frac(el, "y2", 0.0) - frac(el, "y1", 0.0)
            if dx or dy:
                spec["angle"] = math.degrees(math.atan2(dy, dx)) % 360
            else:
                spec["angle"] = 0.0
        specs[gid] = spec
    return specs


def _parse_transform(text: str) -> QTransform:
    t = QTransform()
    if not text:
        return t
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text):
        n = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        op = QTransform()
        if name == "translate":
            op.translate(n[0], n[1] if len(n) > 1 else 0)
        elif name == "scale":
            op.scale(n[0], n[1] if len(n) > 1 else n[0])
        elif name == "rotate":
            if len(n) == 3:
                op.translate(n[1], n[2]); op.rotate(n[0])
                op.translate(-n[1], -n[2])
            else:
                op.rotate(n[0])
        elif name == "matrix" and len(n) == 6:
            op = QTransform(n[0], n[1], n[2], n[3], n[4], n[5])
        elif name == "skewX":
            op.shear(math.tan(math.radians(n[0])), 0)
        elif name == "skewY":
            op.shear(0, math.tan(math.radians(n[0])))
        t = op * t          # right-to-left: leftmost op applied last
    return t


def _decompose(tf: QTransform):
    """Return (dx, dy, degrees, simple) where *simple* means the matrix
    is a pure translation + rotation (uniform scale 1, no shear)."""
    m11, m12, m21, m22 = tf.m11(), tf.m12(), tf.m21(), tf.m22()
    dx, dy = tf.dx(), tf.dy()
    simple = (abs(m11 * m11 + m12 * m12 - 1) < 1e-3
              and abs(m11 - m22) < 1e-3 and abs(m12 + m21) < 1e-3
              and (m11 * m22 - m12 * m21) > 0)
    degrees = math.degrees(math.atan2(m12, m11))
    return dx, dy, degrees, simple


def _finalise(item, total: QTransform, style: dict):
    """Apply transform + opacity to a freshly built native item."""
    dx, dy, deg, _ = _decompose(total)
    item.setPos(dx, dy)
    if abs(deg) > _EPS:
        center_origin(item)
        item.setRotation(deg)
    if "_opacity" in style:
        item.setOpacity(style["_opacity"])
    return item


def _styled(item, style: dict, fill=True):
    item.setPen(_pen_from_style(style))
    if fill and hasattr(item, "setBrush"):
        item.setBrush(_brush_from_style(style))
    return item


def _rect_of(el) -> QRectF:
    return QRectF(float(el.get("x", 0)), float(el.get("y", 0)),
                  float(el.get("width", 0)), float(el.get("height", 0)))


def _baked_path(local_path: QPainterPath, total: QTransform, style: dict):
    item = PathItem(total.map(local_path))
    _styled(item, style)
    if "_opacity" in style:
        item.setOpacity(style["_opacity"])
    return item


def _read_dim_style(item, el):
    """Restore a DimensionItem's style from its kp: attributes."""
    item.cap_style = el.get(_kp("dim-cap"), "arrows")
    item.extension = el.get(_kp("dim-ext"), "0") == "1"
    item.dash = el.get(_kp("dim-dash"), "0") == "1"
    item.unit = el.get(_kp("dim-unit"), "mm")
    item.decimals = int(float(el.get(_kp("dim-decimals"), "1")))
    item.prefix = el.get(_kp("dim-prefix"), "")
    item.suffix = el.get(_kp("dim-suffix"), "")


def _build_leaf(el, total: QTransform, style: dict):
    tag = _localname(el.tag)
    dx, dy, deg, simple = _decompose(total)

    if tag == "line":
        line = QLineF(float(el.get("x1", 0)), float(el.get("y1", 0)),
                      float(el.get("x2", 0)), float(el.get("y2", 0)))
        cls = {"arrow": ArrowItem, "dimension": DimensionItem}.get(
            el.get(_kp("kind")), LineItem)
        if simple:
            item = cls(line)
            if cls is DimensionItem:
                _read_dim_style(item, el)
            if isinstance(item, ArrowItem):
                item.set_head(el.get(_kp("head"), "filled"))
            return _finalise(_styled(item, style, fill=False), total, style)
        path = QPainterPath(line.p1()); path.lineTo(line.p2())
        return _baked_path(path, total, style)

    if tag == "rect":
        rect = _rect_of(el)
        rx = float(el.get("rx", 0) or 0)
        if simple and rx > 0:
            item = RoundedRectItem(rect, rx)
            return _finalise(_styled(item, style), total, style)
        if simple:
            item = RectItem(rect)
            return _finalise(_styled(item, style), total, style)
        path = QPainterPath()
        path.addRoundedRect(rect, rx, rx) if rx else path.addRect(rect)
        return _baked_path(path, total, style)

    if tag in ("circle", "ellipse"):
        if tag == "circle":
            r = float(el.get("r", 0))
            rx = ry = r
        else:
            rx = float(el.get("rx", 0)); ry = float(el.get("ry", 0))
        cx = float(el.get("cx", 0)); cy = float(el.get("cy", 0))
        rect = QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry)
        if simple:
            item = EllipseItem(rect)
            return _finalise(_styled(item, style), total, style)
        path = QPainterPath(); path.addEllipse(rect)
        return _baked_path(path, total, style)

    if tag in ("polygon", "polyline"):
        poly = _parse_points(el.get("points", ""))
        if simple:
            item = PolygonItem(poly, kind=el.get(_kp("kind"), "polygon"))
            return _finalise(_styled(item, style), total, style)
        path = QPainterPath(); path.addPolygon(poly)
        if tag == "polygon":
            path.closeSubpath()
        return _baked_path(path, total, style)

    if tag == "path":
        kind = el.get(_kp("kind"))
        if el.get(_kp("bend")) is not None and simple:  # bent line/arrow
            line = QLineF(float(el.get(_kp("x1"), 0)),
                          float(el.get(_kp("y1"), 0)),
                          float(el.get(_kp("x2"), 0)),
                          float(el.get(_kp("y2"), 0)))
            item = (ArrowItem if kind == "arrow" else LineItem)(line)
            bx, by = [float(v) for v in
                      re.split(r"[\s,]+", el.get(_kp("bend")).strip())]
            item.set_bend(QPointF(bx, by))
            if isinstance(item, ArrowItem):
                item.set_head(el.get(_kp("head"), "filled"))
            return _finalise(_styled(item, style, fill=False), total, style)
        if kind in ARC_KINDS and simple:
            r = QRectF(float(el.get(_kp("ax"), 0)), float(el.get(_kp("ay"), 0)),
                       float(el.get(_kp("aw"), 0)), float(el.get(_kp("ah"), 0)))
            item = ArcShapeItem(r, kind=kind)
            item.flip_h = el.get(_kp("flip-h")) == "1"
            item.flip_v = el.get(_kp("flip-v")) == "1"
            item._rebuild()
            return _finalise(_styled(item, style), total, style)
        local = _path_from_d(el.get("d", ""))
        if simple:
            item = PathItem(local)
            return _finalise(_styled(item, style), total, style)
        return _baked_path(local, total, style)

    if tag == "text":
        return _build_text(el, total, style)

    if tag == "image":
        return _build_image(el, total, style)

    return None


def _build_text(el, total: QTransform, style: dict):
    text = "".join(el.itertext())
    item = TextItem(text.strip())
    size = int(float(re.sub(r"[^\d.]", "", style.get("font-size", "14")) or 14))
    font = QFont(style.get("font-family", "Segoe UI"), size)
    font.setBold("bold" in str(style.get("font-weight", "")))
    font.setItalic(style.get("font-style") == "italic")
    item.setFont(font)
    item.setDefaultTextColor(_color(style.get("fill", "#000000")))
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    if el.get("dominant-baseline") != "text-before-edge":
        y -= size * 0.8                       # baseline -> top-left approx
    pt = total.map(QPointF(x, y))
    item.setPos(pt)
    _, _, deg, _ = _decompose(total)
    if abs(deg) > _EPS:
        center_origin(item)
        item.setRotation(deg)
    if "_opacity" in style:
        item.setOpacity(style["_opacity"])
    return item


def _href(el):
    return el.get(f"{{{XLINK_NS}}}href") or el.get("href")


def _pixmap_from_href(href: str) -> QPixmap:
    pm = QPixmap()
    if href and href.startswith("data:"):
        b64 = href.split(",", 1)[1]
        pm.loadFromData(base64.b64decode(b64))
    return pm


def _build_image(el, total: QTransform, style: dict):
    pm = _pixmap_from_href(_href(el))
    item = ImageItem(pm)
    natw, nath = pm.width() or 1, pm.height() or 1
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    w = float(el.get("width", natw))
    h = float(el.get("height", nath))
    # native pixels -> element box (scale then translate) -> parent
    content = QTransform(w / natw, 0, 0, h / nath, 0, 0) * \
        QTransform(1, 0, 0, 1, x, y)
    full = content * total
    item.setTransformOriginPoint(0, 0)
    item.setTransform(QTransform(full.m11(), full.m12(),
                                 full.m21(), full.m22(), 0, 0))
    item.setPos(full.dx(), full.dy())
    if "_opacity" in style:
        item.setOpacity(style["_opacity"])
    return item


def _parse_points(text: str) -> QPolygonF:
    nums = [float(x) for x in re.split(r"[\s,]+", text.strip()) if x]
    return QPolygonF([QPointF(nums[i], nums[i + 1])
                      for i in range(0, len(nums) - 1, 2)])


def _parse_element(el, parent_tf: QTransform, inherited: dict, scene,
                   defs, depth: int = 0):
    """Return a native item (or None). Raster images set the layer
    directly and return None."""
    if depth > 50:                       # guard against <use> reference loops
        return None
    tag = _localname(el.tag)
    style = _resolve_style(el, inherited)
    total = _parse_transform(el.get("transform")) * parent_tf

    if tag == "use":
        return _parse_use(el, total, style, scene, defs, depth)

    if tag in ("g", "symbol", "a", "svg"):
        group = GroupItem()
        for child in el:
            sub = _parse_element(child, total, style, scene, defs, depth + 1)
            if sub is not None:
                # addToGroup (not setParentItem) so the group's cached
                # bounding rect is correct — otherwise its scale/rotate
                # origin and sceneBoundingRect are empty after load.
                group.addToGroup(sub)
        model = el.get(_kp("model"))
        if model:                            # 3D molecule/crystal model tag
            group.mol_name = model
            group.mol_az = _float_or_none(el.get(_kp("model-az")))
            group.mol_el = _float_or_none(el.get(_kp("model-el")))
            group.mol_bond = _float_or_none(el.get(_kp("model-bond")))
            group.mol_box = _float_or_none(el.get(_kp("model-box")))
            group.mol_repr = el.get(_kp("model-repr")) or "3d"
            cells = _json_or_none(el.get(_kp("model-cells")))
            group.mol_cells = tuple(cells) if cells else None
            group.mol_colors = _json_or_none(el.get(_kp("model-colors")))
            group.mol_tilts = _json_or_none(el.get(_kp("model-tilts")))
            group.mol_poly = el.get(_kp("model-poly")) == "1"
            group.mol_atoms = _json_or_none(el.get(_kp("model-atoms")))
            group.mol_bonds = _json_or_none(el.get(_kp("model-bonds")))
        if el.get(_kp("symbol")):
            group.symbol = el.get(_kp("symbol"))
        solid = _json_or_none(el.get(_kp("solid")))
        if isinstance(solid, dict):              # rotatable 3D solid tag
            group.solid = solid
        rxn = _json_or_none(el.get(_kp("reaction")))
        if isinstance(rxn, dict):                # reaction scheme tag
            group.rxn_data = rxn
        return group if group.childItems() else None

    if tag == "image" and el.get(_kp("role")) == "raster":
        pm = _pixmap_from_href(_href(el))
        if not pm.isNull():
            scene.set_raster_pixmap(pm)
        return None

    if tag == "text" and el.get(_kp("role")) == "label":
        return None          # the shape carries its own label via kp attrs

    if tag in ("defs", "title", "desc", "metadata", "style"):
        return None

    item = _build_leaf(el, total, style)
    if isinstance(item, LabelMixin):
        _read_label(el, item)
    return item


def _parse_use(el, total: QTransform, style: dict, scene, defs, depth: int):
    """Resolve a <use xlink:href="#id"> by cloning the referenced element
    (from <defs> or anywhere by id) with the use's x/y offset applied.
    Inkscape/matplotlib exports lean on <use> for tick marks, markers and
    text rendered as glyph paths — without this they vanish on import."""
    href = _href(el)
    if not href or not href.startswith("#"):
        return None
    target = defs.get(href[1:])
    if target is None:
        return None
    x = float(el.get("x", 0) or 0)
    y = float(el.get("y", 0) or 0)
    base = QTransform.fromTranslate(x, y) * total if (x or y) else total
    return _parse_element(target, base, style, scene, defs, depth + 1)


def _read_label(el, item):
    label = el.get(_kp("label"))
    if not label:
        return
    item.set_label(label)
    size = int(float(el.get(_kp("label-size"), "14")))
    font = QFont(el.get(_kp("label-family"), "Segoe UI"), size)
    font.setBold(el.get(_kp("label-bold")) == "1")
    font.setItalic(el.get(_kp("label-italic")) == "1")
    item.set_label_font(font)
    item.set_label_color(_color(el.get(_kp("label-color"), "#1a1a1a")))


def load_svg(scene: PaintScene, path: str):
    root = ET.parse(path).getroot()
    width, height = _root_size(root)
    scene.new_document(width, height)

    dpi = root.get(_kp("dpi"))
    if dpi is not None:
        scene.dpi = int(float(dpi))

    grid_mm = root.get(_kp("grid-mm"))
    divisions = root.get(_kp("grid-divisions"))   # legacy: divisions/width
    legacy = root.get(_kp("grid-size"))           # legacy: pixel spacing
    if grid_mm is not None:
        scene.grid_mm = float(grid_mm)
    elif divisions is not None:
        px = width / max(int(float(divisions)), 1)
        scene.grid_mm = px / scene.dpi * 25.4
    elif legacy is not None:
        scene.grid_mm = float(legacy) / scene.dpi * 25.4
    if grid_mm is not None or divisions is not None or legacy is not None:
        scene.show_grid = root.get(_kp("grid-show"), "1") == "1"
        scene.snap_enabled = root.get(_kp("grid-snap"), "1") == "1"
        scene.infinite = root.get(_kp("infinite"), "0") == "1"

    # Map every element that carries an id, so <use href="#id"> can find
    # its referent (glyphs/markers/ticks defined once in <defs>).
    defs = {e.get("id"): e for e in root.iter() if e.get("id")}

    # Gradient defs ride along in the inherited style dict (it is copied
    # down the tree), so fill="url(#id)" resolves anywhere.
    base = {"fill": "#000000", "stroke": "none",
            "_gradients": _scan_gradients(root)}
    z = 0
    for child in root:
        item = _parse_element(child, QTransform(), base, scene, defs)
        if item is not None:
            item.setZValue(z)
            z += 1
            scene.addItem(item)


def _root_size(root):
    vb = root.get("viewBox")
    if vb:
        nums = [float(x) for x in re.split(r"[\s,]+", vb.strip())]
        if len(nums) == 4:
            return int(nums[2]), int(nums[3])
    w = re.sub(r"[^\d.]", "", root.get("width", "800") or "800") or "800"
    h = re.sub(r"[^\d.]", "", root.get("height", "600") or "600") or "600"
    return int(float(w)), int(float(h))


# ---------------------------------------------------------------- path data
def _path_from_d(d: str) -> QPainterPath:
    path = QPainterPath()
    tokens = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?",
                        d)
    i, n = 0, len(tokens)
    cur = QPointF(0, 0)
    start = QPointF(0, 0)
    prev_cmd = ""
    prev_ctrl = None

    def num():
        nonlocal i
        v = float(tokens[i]); i += 1
        return v

    while i < n:
        tok = tokens[i]
        if re.match(r"[A-Za-z]", tok):
            cmd = tok; i += 1
        else:
            cmd = prev_cmd if prev_cmd not in ("Z", "z") else "L"
        rel = cmd.islower()
        C = cmd.upper()

        if C == "M":
            x, y = num(), num()
            cur = QPointF(cur.x() + x, cur.y() + y) if rel else QPointF(x, y)
            path.moveTo(cur); start = QPointF(cur)
            prev_cmd = "l" if rel else "L"
        elif C == "L":
            x, y = num(), num()
            cur = QPointF(cur.x() + x, cur.y() + y) if rel else QPointF(x, y)
            path.lineTo(cur); prev_cmd = cmd
        elif C == "H":
            x = num()
            cur = QPointF(cur.x() + x if rel else x, cur.y())
            path.lineTo(cur); prev_cmd = cmd
        elif C == "V":
            y = num()
            cur = QPointF(cur.x(), cur.y() + y if rel else y)
            path.lineTo(cur); prev_cmd = cmd
        elif C == "C":
            c1 = _pt(num(), num(), cur, rel)
            c2 = _pt(num(), num(), cur, rel)
            end = _pt(num(), num(), cur, rel)
            path.cubicTo(c1, c2, end)
            prev_ctrl = c2; cur = end; prev_cmd = cmd
        elif C == "S":
            c1 = _reflect(prev_ctrl, cur) if prev_cmd.upper() in ("C", "S") \
                else QPointF(cur)
            c2 = _pt(num(), num(), cur, rel)
            end = _pt(num(), num(), cur, rel)
            path.cubicTo(c1, c2, end)
            prev_ctrl = c2; cur = end; prev_cmd = cmd
        elif C == "Q":
            c = _pt(num(), num(), cur, rel)
            end = _pt(num(), num(), cur, rel)
            path.quadTo(c, end)
            prev_ctrl = c; cur = end; prev_cmd = cmd
        elif C == "T":
            c = _reflect(prev_ctrl, cur) if prev_cmd.upper() in ("Q", "T") \
                else QPointF(cur)
            end = _pt(num(), num(), cur, rel)
            path.quadTo(c, end)
            prev_ctrl = c; cur = end; prev_cmd = cmd
        elif C == "A":
            rx, ry = num(), num()
            rot = num(); large = num(); sweep = num()
            end = _pt(num(), num(), cur, rel)
            _arc_to(path, cur, rx, ry, rot, large, sweep, end)
            cur = end; prev_cmd = cmd
        elif C == "Z":
            path.closeSubpath(); cur = QPointF(start); prev_cmd = cmd
        else:
            break
    return path


def _pt(x, y, cur, rel):
    return QPointF(cur.x() + x, cur.y() + y) if rel else QPointF(x, y)


def _reflect(ctrl, cur):
    if ctrl is None:
        return QPointF(cur)
    return QPointF(2 * cur.x() - ctrl.x(), 2 * cur.y() - ctrl.y())


def _arc_to(path, p0, rx, ry, phi_deg, large, sweep, p1):
    """Append an SVG elliptical arc to *path* as cubic segments."""
    if rx == 0 or ry == 0 or (p0 == p1):
        path.lineTo(p1)
        return
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi_deg)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx, dy = (p0.x() - p1.x()) / 2, (p0.y() - p1.y()) / 2
    x1p = cos_p * dx + sin_p * dy
    y1p = -sin_p * dx + cos_p * dy
    denom = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    if denom == 0:
        path.lineTo(p1)
        return
    lam = (rx * rx * ry * ry) / denom
    if lam < 1:
        scale = math.sqrt(lam)
        rx, ry = rx / scale, ry / scale
    sign = -1 if large == sweep else 1
    num_ = max(rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p, 0)
    co = sign * math.sqrt(num_ / (rx * rx * y1p * y1p + ry * ry * x1p * x1p)) \
        if denom else 0
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (p0.x() + p1.x()) / 2
    cy = sin_p * cxp + cos_p * cyp + (p0.y() + p1.y()) / 2

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        det = ux * vy - uy * vx
        return math.atan2(det, dot)

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                   (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi

    segments = max(1, int(math.ceil(abs(dtheta) / (math.pi / 2))))
    delta = dtheta / segments
    t = (4 / 3) * math.tan(delta / 4)
    theta = theta1
    for _ in range(segments):
        cos1, sin1 = math.cos(theta), math.sin(theta)
        cos2, sin2 = math.cos(theta + delta), math.sin(theta + delta)
        e1 = _elpt(cx, cy, rx, ry, cos_p, sin_p, cos1, sin1)
        e2 = _elpt(cx, cy, rx, ry, cos_p, sin_p, cos2, sin2)
        d1 = _elpt(0, 0, rx, ry, cos_p, sin_p, -sin1, cos1)
        d2 = _elpt(0, 0, rx, ry, cos_p, sin_p, -sin2, cos2)
        c1 = QPointF(e1.x() + t * d1.x(), e1.y() + t * d1.y())
        c2 = QPointF(e2.x() - t * d2.x(), e2.y() - t * d2.y())
        path.cubicTo(c1, c2, e2)
        theta += delta


def _elpt(cx, cy, rx, ry, cos_p, sin_p, cos_t, sin_t):
    x = rx * cos_t
    y = ry * sin_t
    return QPointF(cx + cos_p * x - sin_p * y, cy + sin_p * x + cos_p * y)
