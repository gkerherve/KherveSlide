"""Drawings described as plain JSON shapes, for Claude over MCP.

A small, stable schema in millimetres (origin top-left, y down) that a
language model can author without knowing the canvas classes:

    {"type": "rect", "x": 10, "y": 10, "w": 40, "h": 15,
     "fill": "#eef2f6", "label": "Start"}

`add_shapes` turns such a list into canvas items on a `PaintScene`;
`scene_to_shapes` reads a scene back into the same schema (anything it
cannot express comes back as {"type": "other", ...}).
"""
from __future__ import annotations

import importlib

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen, QPolygonF

from .canvas import (ArrowItem, EllipseItem, GroupItem, LineItem,
                     PaintScene, PathItem, PolygonItem, RectItem,
                     RoundedRectItem, TextItem, center_origin)
from .document import DASH_STYLES, dash_name

#: Symbol libraries usable as {"type": "symbol", "symbol": "lib/name"}.
LIBRARIES = ("flowchart", "electrical", "optics", "maths", "labware",
             "arrows")

SHAPE_TYPES = ("rect", "rounded_rect", "ellipse", "circle", "line",
               "arrow", "double_arrow", "polygon", "polyline", "text",
               "symbol")

# Same symbol scale as the drawing dialog, so an MCP-made symbol matches
# one the user drops by hand.
_SYMBOL_PAGE_PX = 900
_SYMBOL_MIN_PX = 90


class ShapeError(ValueError):
    pass


def new_scene() -> PaintScene:
    scene = PaintScene(900, 600)
    scene.infinite = True
    scene.show_grid = False
    scene.snap_enabled = False
    scene.symbol_page_px = _SYMBOL_PAGE_PX
    scene.symbol_min_px = _SYMBOL_MIN_PX
    return scene


def _px_per_mm(scene) -> float:
    return (getattr(scene, "dpi", 96) or 96) / 25.4


def _library(name: str):
    if name not in LIBRARIES:
        raise ShapeError(f"Unknown symbol library {name!r}; use one of "
                         f"{', '.join(LIBRARIES)}.")
    return importlib.import_module(f"{__package__}.{name}")


def list_symbols() -> dict:
    out = {}
    for lib in LIBRARIES:
        mod = _library(lib)
        labels = getattr(mod, "LABELS", {})
        cats = getattr(mod, "CATEGORIES", None) or [("", list(mod.SIZES))]
        out[lib] = {
            "reference": f"{lib}/<name>",
            "categories": {cat or "all": [
                {"name": n, "label": labels.get(n, n.replace("_", " ")),
                 "default_size_mm": [round(v, 1) for v in
                                     _default_symbol_mm(mod, n)]}
                for n in names] for cat, names in cats},
        }
    return out


def _default_symbol_px(mod, name) -> tuple[float, float]:
    w_mm, h_mm = mod.size_mm(name)
    scale = _SYMBOL_PAGE_PX / getattr(mod, "REFERENCE_MM", 4800.0)
    w, h = w_mm * scale, h_mm * scale
    if 0 < max(w, h) < _SYMBOL_MIN_PX:
        k = _SYMBOL_MIN_PX / max(w, h)
        w, h = w * k, h * k
    return w, h


def _default_symbol_mm(mod, name) -> tuple[float, float]:
    w, h = _default_symbol_px(mod, name)
    k = 96 / 25.4
    return w / k, h / k


# ------------------------------------------------------------ building

def _color(value, default):
    if value is None:
        return None
    c = QColor(str(value))
    if not c.isValid():
        raise ShapeError(f"Not a colour: {value!r} (use #rrggbb).")
    return c


def _pen(spec, k) -> QPen:
    stroke = spec.get("stroke", "#1a1a1a")
    if stroke is None or str(stroke).lower() == "none":
        return QPen(Qt.NoPen)
    pen = QPen(_color(stroke, "#1a1a1a"),
               max(0.05, float(spec.get("width", 0.5))) * k)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    dash = str(spec.get("dash", "solid")).lower()
    if dash not in DASH_STYLES:
        raise ShapeError(f"dash must be one of {', '.join(DASH_STYLES)}.")
    pen.setStyle(DASH_STYLES[dash])
    return pen


def _brush(spec) -> QBrush:
    fill = spec.get("fill")
    if fill is None or str(fill).lower() == "none":
        return QBrush(Qt.NoBrush)
    return QBrush(_color(fill, None))


def _font(spec, default_pt=11.0) -> QFont:
    font = QFont("Helvetica")
    font.setPointSizeF(max(1.0, float(spec.get("font_size", default_pt))))
    font.setBold(bool(spec.get("bold", False)))
    font.setItalic(bool(spec.get("italic", False)))
    return font


def _num(spec, key, default=None) -> float:
    v = spec.get(key, default)
    if v is None:
        raise ShapeError(f"{spec.get('type')} needs `{key}`.")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ShapeError(f"`{key}` must be a number, got {v!r}.") from None


def _points(spec, k, minimum) -> list[QPointF]:
    pts = spec.get("points")
    if pts is None and "x1" in spec:
        pts = [[spec["x1"], spec["y1"]], [spec["x2"], spec["y2"]]]
    if not isinstance(pts, list) or len(pts) < minimum:
        raise ShapeError(f"{spec.get('type')} needs `points` with at least "
                         f"{minimum} [x, y] pairs.")
    try:
        return [QPointF(float(x) * k, float(y) * k) for x, y in pts]
    except (TypeError, ValueError):
        raise ShapeError("`points` must be [[x, y], ...] numbers.") from None


def _label(item, spec):
    text = spec.get("label")
    if not text:
        return
    item.set_label(str(text))
    item.set_label_font(_font(spec))
    color = spec.get("text_color") or "#1a1a1a"
    item.set_label_color(_color(color, "#1a1a1a"))


def _text_item(spec, k) -> TextItem:
    item = TextItem(str(spec.get("text", "")))
    item.setFont(_font(spec))
    item.setDefaultTextColor(_color(spec.get("color") or spec.get(
        "stroke") or "#1a1a1a", "#1a1a1a"))
    x, y = _num(spec, "x") * k, _num(spec, "y") * k
    br = item.boundingRect()
    anchor = str(spec.get("anchor", "center")).lower()
    if anchor == "center":
        item.setPos(x - br.width() / 2, y - br.height() / 2)
    elif anchor == "left":
        item.setPos(x, y - br.height() / 2)
    elif anchor == "topleft":
        item.setPos(x, y)
    else:
        raise ShapeError("anchor must be center, left or topleft.")
    return item


def _symbol_items(scene, spec, k):
    ref = str(spec.get("symbol", ""))
    lib, _, name = ref.replace(":", "/").partition("/")
    mod = _library(lib)
    if name not in mod.SIZES:
        raise ShapeError(f"No symbol {name!r} in {lib}; call "
                         f"list_drawing_symbols.")
    if spec.get("w") is not None or spec.get("h") is not None:
        dw, dh = _default_symbol_px(mod, name)
        w = float(spec["w"]) * k if spec.get("w") is not None else None
        h = float(spec["h"]) * k if spec.get("h") is not None else None
        if w is None:
            w = dw * h / dh
        if h is None:
            h = dh * w / dw
    else:
        w, h = _default_symbol_px(mod, name)
    from .specs import _spec_to_item
    parts = [it for it in (_spec_to_item(s)
                           for s in mod.build_specs(name, w, h)) if it]
    if not parts:
        raise ShapeError(f"Symbol {ref} produced nothing.")
    center = QPointF(_num(spec, "x") * k, _num(spec, "y") * k)
    top = scene._drop_items(parts, center, w, h)
    top.symbol = f"{lib}:{name}"
    top.setSelected(False)
    label = spec.get("label")
    if label:
        texts = [c for c in _leaves(top) if isinstance(c, TextItem)]
        if texts:        # flowchart nodes carry a placeholder caption
            t = texts[0]
            old = t.boundingRect()
            c = t.mapToScene(old.center())
            t.setPlainText(str(label))
            if spec.get("font_size"):
                t.setFont(_font(spec))
            br = t.boundingRect()
            t.setPos(t.pos() + t.mapFromScene(c) - br.center())
        else:
            # Arrowheads pad the bounding rect past the ink, and some
            # symbols draw well inside their design box: take the tighter.
            box = top.sceneBoundingRect()
            box.setBottom(min(box.bottom(), center.y() + h / 2))
            caption = _text_item({"text": label, "x": box.center().x() / k,
                                  "y": box.bottom() / k + 1,
                                  "anchor": "topleft",
                                  "font_size": spec.get("font_size", 10)}, k)
            caption.setPos(box.center().x()
                           - caption.boundingRect().width() / 2,
                           box.bottom() + 0.5 * k
                           - caption.document().documentMargin())
            scene.addItem(caption)
            return [top, caption]
    return [top]


def _leaves(item):
    for c in item.childItems():
        if isinstance(c, GroupItem):
            yield from _leaves(c)
        else:
            yield c


def _build(scene, spec, k) -> list:
    if not isinstance(spec, dict):
        raise ShapeError("Each shape must be an object.")
    kind = str(spec.get("type", "")).lower()
    if kind == "symbol":
        items = _symbol_items(scene, spec, k)
        for it in items:
            _finish(it, spec, rotate=it is items[0])
        return items
    if kind in ("rect", "rounded_rect", "ellipse"):
        rect = QRectF(_num(spec, "x") * k, _num(spec, "y") * k,
                      _num(spec, "w") * k, _num(spec, "h") * k)
        if kind == "rect":
            item = RectItem(rect)
        elif kind == "ellipse":
            item = EllipseItem(rect)
        else:
            item = RoundedRectItem(rect, float(spec.get("radius", 2.5)) * k)
        item.setPen(_pen(spec, k))
        item.setBrush(_brush(spec))
        _label(item, spec)
    elif kind == "circle":
        r = spec.get("r")
        r = float(r) if r is not None else _num(spec, "w") / 2
        cx, cy = _num(spec, "x"), _num(spec, "y")
        item = EllipseItem(QRectF((cx - r) * k, (cy - r) * k,
                                  2 * r * k, 2 * r * k))
        item.setPen(_pen(spec, k))
        item.setBrush(_brush(spec))
        _label(item, spec)
    elif kind in ("line", "arrow", "double_arrow"):
        p = _points(spec, k, 2)
        if len(p) > 2:
            raise ShapeError(f"{kind} takes exactly two points; use a "
                             f"polyline for bends.")
        cls = LineItem if kind == "line" else ArrowItem
        item = cls(QLineF(p[0], p[1]))
        item.setPen(_pen(spec, k))
        if kind == "double_arrow":
            item.set_head("double")
        elif kind == "arrow":
            item.set_head(str(spec.get("head", "filled")))
    elif kind == "polygon":
        item = PolygonItem(QPolygonF(_points(spec, k, 3)))
        item.setPen(_pen(spec, k))
        item.setBrush(_brush(spec))
        _label(item, spec)
    elif kind == "polyline":
        p = _points(spec, k, 2)
        path = QPainterPath(p[0])
        for q in p[1:]:
            path.lineTo(q)
        item = PathItem(path)
        item.setPen(_pen(spec, k))
        item.setBrush(QBrush(Qt.NoBrush))
    elif kind == "text":
        if not str(spec.get("text", "")).strip():
            raise ShapeError("text needs a non-empty `text`.")
        item = _text_item(spec, k)
    else:
        raise ShapeError(f"Unknown shape type {kind!r}; use one of "
                         f"{', '.join(SHAPE_TYPES)}.")
    scene.addItem(item)
    _finish(item, spec)
    return [item]


def _finish(item, spec, rotate=True):
    center_origin(item)
    if rotate and spec.get("rotation"):
        item.setRotation(float(spec["rotation"]))
    if spec.get("opacity") is not None:
        item.setOpacity(max(0.0, min(1.0, float(spec["opacity"]))))


def add_shapes(scene: PaintScene, shapes) -> int:
    """Add *shapes* to *scene*; returns how many top-level items were
    added. Raises ShapeError (naming the shape) on a bad spec, leaving
    the scene without any of this call's items."""
    if not isinstance(shapes, list) or not shapes:
        raise ShapeError("`shapes` must be a non-empty array.")
    k = _px_per_mm(scene)
    existing = scene.vector_items()
    top_z = max((it.zValue() for it in existing), default=None)
    added = []
    try:
        for i, spec in enumerate(shapes):
            try:
                added += _build(scene, spec, k)
            except ShapeError as exc:
                raise ShapeError(f"shapes[{i}]: {exc}") from None
    except ShapeError:
        for it in added:
            if it.scene() is scene:
                scene.removeItem(it)
        raise
    if top_z is not None:       # appended shapes stay above a loaded drawing
        for it in added:
            it.setZValue(top_z + 1)
    scene.clearSelection()
    return len(added)


# ------------------------------------------------------------ reading

def _r(v: float) -> float:
    return round(v, 2)


def _style(item, k) -> dict:
    d = {}
    pen = item.pen()
    if pen.style() == Qt.NoPen:
        d["stroke"] = None
    else:
        d["stroke"] = pen.color().name()
        d["width"] = _r(pen.widthF() / k)
        if dash_name(pen) != "solid":
            d["dash"] = dash_name(pen)
    if hasattr(item, "brush"):
        b = item.brush()
        d["fill"] = None if b.style() == Qt.NoBrush else b.color().name()
    return d


def _common(item, d):
    if abs(item.rotation()) > 1e-6:
        d["rotation"] = _r(item.rotation())
    if item.opacity() < 1:
        d["opacity"] = _r(item.opacity())
    if hasattr(item, "label") and callable(item.label) and item.label():
        d["label"] = item.label()
        d["font_size"] = item.label_font().pointSize()
    return d


def item_to_shape(item, k: float) -> dict:
    """One top-level canvas item in the authoring schema."""
    pos = item.pos()
    sym = getattr(item, "symbol", None)
    if sym:
        box = item.sceneBoundingRect()
        lib, _, name = str(sym).partition(":")
        d = {"type": "symbol", "symbol": f"{lib}/{name}",
             "x": _r(box.center().x() / k), "y": _r(box.center().y() / k),
             "w": _r(box.width() / k), "h": _r(box.height() / k)}
        texts = [c.toPlainText() for c in _leaves(item)
                 if isinstance(c, TextItem)] if isinstance(
                     item, GroupItem) else []
        if texts:
            d["label"] = texts[0]
        return _common(item, d)
    if isinstance(item, (ArrowItem, LineItem)) and not hasattr(item, "unit"):
        ln = item.line()
        kind = "line"
        if isinstance(item, ArrowItem):
            kind = "double_arrow" if item.head == "double" else "arrow"
        d = {"type": kind, "points": [
            [_r((ln.x1() + pos.x()) / k), _r((ln.y1() + pos.y()) / k)],
            [_r((ln.x2() + pos.x()) / k), _r((ln.y2() + pos.y()) / k)]],
             **_style(item, k)}
        d.pop("fill", None)
        if kind == "arrow" and item.head != "filled":
            d["head"] = item.head
        return _common(item, d)
    if isinstance(item, (RectItem, EllipseItem, RoundedRectItem)):
        r = item.rect().translated(pos)
        kind = {RectItem: "rect", EllipseItem: "ellipse"}.get(
            type(item), "rounded_rect")
        if kind == "ellipse" and abs(r.width() - r.height()) < 0.5:
            d = {"type": "circle", "x": _r(r.center().x() / k),
                 "y": _r(r.center().y() / k), "r": _r(r.width() / 2 / k)}
        else:
            d = {"type": kind, "x": _r(r.x() / k), "y": _r(r.y() / k),
                 "w": _r(r.width() / k), "h": _r(r.height() / k)}
        if kind == "rounded_rect":
            d["radius"] = _r(item.radius() / k)
        d.update(_style(item, k))
        return _common(item, d)
    if isinstance(item, PolygonItem) and item.kind == "polygon":
        d = {"type": "polygon",
             "points": [[_r((p.x() + pos.x()) / k), _r((p.y() + pos.y()) / k)]
                        for p in item.polygon()], **_style(item, k)}
        return _common(item, d)
    if isinstance(item, PathItem) and item.brush().style() == Qt.NoBrush:
        path = item.path()
        els = [path.elementAt(i) for i in range(path.elementCount())]
        if els and all(e.isLineTo() or e.isMoveTo() for e in els) and \
                sum(e.isMoveTo() for e in els) == 1:
            d = {"type": "polyline",
                 "points": [[_r((e.x + pos.x()) / k), _r((e.y + pos.y()) / k)]
                            for e in els], **_style(item, k)}
            d.pop("fill", None)
            return _common(item, d)
    if isinstance(item, TextItem):
        f = item.font()
        d = {"type": "text", "text": item.toPlainText(),
             "x": _r(pos.x() / k), "y": _r(pos.y() / k), "anchor": "topleft",
             "font_size": _r(f.pointSizeF()),
             "color": item.defaultTextColor().name()}
        if f.bold():
            d["bold"] = True
        if f.italic():
            d["italic"] = True
        return _common(item, d)
    box = item.sceneBoundingRect()
    return {"type": "other", "item_type": type(item).__name__,
            "bbox_mm": [_r(box.x() / k), _r(box.y() / k),
                        _r(box.width() / k), _r(box.height() / k)]}


def scene_to_shapes(scene: PaintScene) -> list[dict]:
    k = _px_per_mm(scene)
    return [item_to_shape(it, k) for it in scene.vector_items()]
