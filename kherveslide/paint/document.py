""".kpaint (de)serialisation and PNG import/export.

`.kpaint` is JSON: format/version header, canvas size, grid settings,
the raster layer as a base64 PNG, and the vector items (recursively
through groups). All item properties must round-trip — when adding a
property, update item_to_dict() and item_from_dict() together and
extend the round-trip test.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import base64
import json

from PySide6.QtCore import (QBuffer, QByteArray, QLineF, QMarginsF, QPointF,
                          QRectF, QSize, QSizeF, Qt)
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPageSize, QPainter,
                         QPainterPath, QPdfWriter, QPen, QPixmap, QPolygonF,
                         QTransform)
from PySide6.QtSvg import QSvgGenerator

from . import gradient
from .canvas import (ArcShapeItem, ArrowItem, DimensionItem, EllipseItem,
                     GroupItem, ImageItem, LabelMixin, LineItem, PaintScene,
                     PathItem, PolygonItem, RectItem, RoundedRectItem,
                     TextItem, center_origin)

FORMAT_VERSION = 13     # 13: palette-symbol identity ("symbol")
                        # 12: rotatable 3D solids ("solid")
                        # 11: re-editable reaction schemes ("reaction")


# ---------------------------------------------------------------- pens
#: Named dash styles <-> Qt pen styles (shared with svgio).
DASH_STYLES = {"solid": Qt.SolidLine, "dash": Qt.DashLine,
               "dot": Qt.DotLine, "dashdot": Qt.DashDotLine}


def dash_name(pen: QPen) -> str:
    for name, style in DASH_STYLES.items():
        if pen.style() == style:
            return name
    return "solid"


def _pen_to_dict(pen: QPen) -> dict:
    d = {"color": pen.color().name(QColor.HexArgb), "width": pen.widthF()}
    if pen.style() == Qt.NoPen:
        d["none"] = True
    elif dash_name(pen) != "solid":
        d["dash"] = dash_name(pen)
    return d


def _pen_from_dict(d: dict) -> QPen:
    if d.get("none"):
        return QPen(Qt.NoPen)
    pen = QPen(QColor(d.get("color", "#ff1a1a1a")), d.get("width", 2))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setStyle(DASH_STYLES.get(d.get("dash", "solid"), Qt.SolidLine))
    return pen


def _brush_to_dict(brush: QBrush):
    if brush.style() == Qt.NoBrush:
        return None
    spec = gradient.brush_spec(brush)
    if spec is not None:
        return {"gradient": spec}
    return {"color": brush.color().name(QColor.HexArgb)}


def _brush_from_dict(d) -> QBrush:
    if not d:
        return QBrush(Qt.NoBrush)
    if "gradient" in d:
        return gradient.brush_from_spec(d["gradient"])
    return QBrush(QColor(d.get("color", "#ff4aa3ff")))


# ---------------------------------------------------------------- labels
def _label_to_dict(item) -> dict:
    if not isinstance(item, LabelMixin) or not item.label():
        return {}
    return {"label": item.label(),
            "labelColor": item.label_color().name(QColor.HexArgb),
            "labelFamily": item._label_family, "labelSize": item._label_size,
            "labelBold": item._label_bold, "labelItalic": item._label_italic}


def _apply_label(item, d: dict):
    if not isinstance(item, LabelMixin) or not d.get("label"):
        return
    item.set_label(d["label"])
    font = QFont(d.get("labelFamily", "Segoe UI"), d.get("labelSize", 14))
    font.setBold(d.get("labelBold", False))
    font.setItalic(d.get("labelItalic", False))
    item.set_label_font(font)
    item.set_label_color(QColor(d.get("labelColor", "#ff1a1a1a")))


# ---------------------------------------------------------------- paths
def painterpath_to_cmds(path: QPainterPath) -> list:
    """A QPainterPath as a JSON-friendly command list (M/L/C)."""
    cmds, i = [], 0
    while i < path.elementCount():
        e = path.elementAt(i)
        if e.isMoveTo():
            cmds.append(["M", e.x, e.y])
            i += 1
        elif e.isLineTo():
            cmds.append(["L", e.x, e.y])
            i += 1
        else:                                   # curve: e + 2 data points
            c2, ep = path.elementAt(i + 1), path.elementAt(i + 2)
            cmds.append(["C", e.x, e.y, c2.x, c2.y, ep.x, ep.y])
            i += 3
    return cmds


def cmds_to_painterpath(cmds: list) -> QPainterPath:
    path = QPainterPath()
    for c in cmds:
        if c[0] == "M":
            path.moveTo(c[1], c[2])
        elif c[0] == "L":
            path.lineTo(c[1], c[2])
        elif c[0] == "C":
            path.cubicTo(c[1], c[2], c[3], c[4], c[5], c[6])
    return path


# ---------------------------------------------------------------- items
def _dimension_to_dict(item) -> dict:
    """The style fields that distinguish a dimension from a plain line."""
    return {"capStyle": item.cap_style, "extension": item.extension,
            "dash": item.dash, "unit": item.unit, "decimals": item.decimals,
            "prefix": item.prefix, "suffix": item.suffix}


def _apply_dimension(item, d):
    item.cap_style = d.get("capStyle", "arrows")
    item.extension = d.get("extension", False)
    item.dash = d.get("dash", False)
    item.unit = d.get("unit", "mm")
    item.decimals = d.get("decimals", 1)
    item.prefix = d.get("prefix", "")
    item.suffix = d.get("suffix", "")


def item_to_dict(item) -> dict:
    pos = {"x": item.pos().x(), "y": item.pos().y()}
    common = {"pos": pos, "opacity": item.opacity(),
              "rotation": item.rotation(), "z": item.zValue(),
              "scale": item.scale()}
    if getattr(item, "symbol", None):      # palette symbol identity
        common["symbol"] = item.symbol
    if isinstance(item, DimensionItem):
        ln = item.line()
        return {"type": "dimension", "pen": _pen_to_dict(item.pen()),
                "x1": ln.x1(), "y1": ln.y1(), "x2": ln.x2(), "y2": ln.y2(),
                **_dimension_to_dict(item), **common}
    if isinstance(item, (ArrowItem, LineItem)):
        ln = item.line()
        d = {"type": "arrow" if isinstance(item, ArrowItem) else "line",
             "pen": _pen_to_dict(item.pen()),
             "x1": ln.x1(), "y1": ln.y1(), "x2": ln.x2(), "y2": ln.y2(),
             **common}
        bend = item.bend()
        if bend is not None:
            d["bend"] = [bend.x(), bend.y()]
        if isinstance(item, ArrowItem) and item.head != "filled":
            d["head"] = item.head
        return d
    if isinstance(item, RoundedRectItem):
        r = item.rect()
        return {"type": "roundrect", "pen": _pen_to_dict(item.pen()),
                "brush": _brush_to_dict(item.brush()), "radius": item.radius(),
                "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                **_label_to_dict(item), **common}
    if isinstance(item, ArcShapeItem):
        r = item.rect()
        return {"type": "arc", "kind": item.kind,
                "pen": _pen_to_dict(item.pen()),
                "brush": _brush_to_dict(item.brush()),
                "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                "flipH": item.flip_h, "flipV": item.flip_v,
                **_label_to_dict(item), **common}
    if isinstance(item, PolygonItem):
        return {"type": "polygon", "pen": _pen_to_dict(item.pen()),
                "brush": _brush_to_dict(item.brush()), "kind": item.kind,
                "points": [[p.x(), p.y()] for p in item.polygon()],
                **_label_to_dict(item), **common}
    if isinstance(item, PathItem):
        return {"type": "path", "pen": _pen_to_dict(item.pen()),
                "brush": _brush_to_dict(item.brush()),
                "cmds": painterpath_to_cmds(item.path()), **common}
    if isinstance(item, ImageItem):
        parent = item.parentItem()
        m = (item.itemTransform(parent) if parent is not None
             else item.sceneTransform())
        return {"type": "image", "image": _pixmap_to_b64(item.pixmap()),
                "matrix": [m.m11(), m.m12(), m.m21(), m.m22(),
                           m.dx(), m.dy()], **common}
    if isinstance(item, (RectItem, EllipseItem)):
        r = item.rect()
        return {"type": "rect" if isinstance(item, RectItem) else "ellipse",
                "pen": _pen_to_dict(item.pen()),
                "brush": _brush_to_dict(item.brush()),
                "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                **_label_to_dict(item), **common}
    if isinstance(item, TextItem):
        return {"type": "text", "text": item.toPlainText(),
                "color": item.defaultTextColor().name(QColor.HexArgb),
                "family": item.font().family(),
                "size": item.font().pointSize(),
                "bold": item.font().bold(),
                "italic": item.font().italic(), **common}
    if isinstance(item, GroupItem):
        from .handles import Handle
        d = {"type": "group",
             "children": [item_to_dict(c) for c in item.childItems()
                          if not isinstance(c, Handle)],
             **common}
        tf = item.transform()
        if not tf.isIdentity():       # non-uniform (X/Y-only) group resize
            d["matrix"] = [tf.m11(), tf.m12(), tf.m21(), tf.m22(),
                           tf.dx(), tf.dy()]
        if getattr(item, "mol_name", None):   # 3D molecule/crystal model
            d["model"] = item.mol_name
            d["model_az"] = getattr(item, "mol_az", None)
            d["model_el"] = getattr(item, "mol_el", None)
            d["model_bond"] = getattr(item, "mol_bond", None)
            d["model_box"] = getattr(item, "mol_box", None)
            d["model_repr"] = getattr(item, "mol_repr", None)
            if getattr(item, "mol_cells", None):   # stacked supercell counts
                d["model_cells"] = list(item.mol_cells)
            if getattr(item, "mol_colors", None):  # colour override map
                d["model_colors"] = dict(item.mol_colors)
            if getattr(item, "mol_tilts", None):   # per-cell tilt map
                d["model_tilts"] = dict(item.mol_tilts)
            if getattr(item, "mol_poly", False):   # coordination polyhedra
                d["model_poly"] = True
            if getattr(item, "mol_atoms", None):   # hand-built structure
                d["model_atoms"] = item.mol_atoms
                d["model_bonds"] = item.mol_bonds
        if getattr(item, "solid", None):      # rotatable 3D solid
            d["solid"] = dict(item.solid)
        if getattr(item, "rxn_data", None):   # re-editable reaction scheme
            import copy
            d["reaction"] = copy.deepcopy(item.rxn_data)
        return d
    raise ValueError(f"unserialisable item: {type(item).__name__}")


def item_from_dict(d: dict):
    kind = d.get("type")
    if kind in ("line", "arrow", "dimension"):
        cls = {"arrow": ArrowItem, "dimension": DimensionItem}.get(
            kind, LineItem)
        item = cls(QLineF(d["x1"], d["y1"], d["x2"], d["y2"]))
        item.setPen(_pen_from_dict(d.get("pen", {})))
        if kind == "dimension":
            _apply_dimension(item, d)
        elif d.get("bend") is not None:
            item.set_bend(QPointF(d["bend"][0], d["bend"][1]))
        if kind == "arrow":
            item.set_head(d.get("head", "filled"))
    elif kind in ("rect", "ellipse"):
        cls = RectItem if kind == "rect" else EllipseItem
        item = cls(QRectF(d["x"], d["y"], d["w"], d["h"]))
        item.setPen(_pen_from_dict(d.get("pen", {})))
        item.setBrush(_brush_from_dict(d.get("brush")))
    elif kind == "roundrect":
        item = RoundedRectItem(QRectF(d["x"], d["y"], d["w"], d["h"]),
                               d.get("radius", 12))
        item.setPen(_pen_from_dict(d.get("pen", {})))
        item.setBrush(_brush_from_dict(d.get("brush")))
    elif kind == "arc":
        item = ArcShapeItem(QRectF(d["x"], d["y"], d["w"], d["h"]),
                            kind=d.get("kind", "halfcircle"))
        item.flip_h = d.get("flipH", False)
        item.flip_v = d.get("flipV", False)
        item._rebuild()
        item.setPen(_pen_from_dict(d.get("pen", {})))
        item.setBrush(_brush_from_dict(d.get("brush")))
    elif kind == "polygon":
        poly = QPolygonF([QPointF(x, y) for x, y in d.get("points", [])])
        item = PolygonItem(poly, kind=d.get("kind", "polygon"))
        item.setPen(_pen_from_dict(d.get("pen", {})))
        item.setBrush(_brush_from_dict(d.get("brush")))
    elif kind == "path":
        item = PathItem(cmds_to_painterpath(d.get("cmds", [])))
        item.setPen(_pen_from_dict(d.get("pen", {})))
        item.setBrush(_brush_from_dict(d.get("brush")))
    elif kind == "image":
        item = ImageItem(_pixmap_from_b64(d["image"]))
    elif kind == "text":
        item = TextItem(d.get("text", ""))
        item.setDefaultTextColor(QColor(d.get("color", "#ff1a1a1a")))
        font = QFont(d.get("family", "Segoe UI"), d.get("size", 14))
        font.setBold(d.get("bold", False))
        font.setItalic(d.get("italic", False))
        item.setFont(font)
    elif kind == "group":
        item = GroupItem()
        for child_dict in d.get("children", []):
            child = item_from_dict(child_dict)
            # addToGroup (not setParentItem) so the group's cached
            # bounding rect is updated — otherwise it stays empty and the
            # group's centre/scale origin and sceneBoundingRect are wrong
            # after a load or undo. Safe to snap-free here: the group is
            # still detached from any scene.
            item.addToGroup(child)
        if d.get("model"):                    # 3D molecule/crystal model tag
            item.mol_name = d["model"]
            item.mol_az = d.get("model_az")
            item.mol_el = d.get("model_el")
            item.mol_bond = d.get("model_bond")
            item.mol_box = d.get("model_box")
            item.mol_repr = d.get("model_repr", "3d")
            cells = d.get("model_cells")
            item.mol_cells = tuple(cells) if cells else None
            item.mol_colors = d.get("model_colors")
            item.mol_tilts = d.get("model_tilts")
            item.mol_poly = bool(d.get("model_poly", False))
            item.mol_atoms = d.get("model_atoms")
            item.mol_bonds = d.get("model_bonds")
        if isinstance(d.get("solid"), dict):      # rotatable 3D solid tag
            item.solid = dict(d["solid"])
        if isinstance(d.get("reaction"), dict):   # reaction scheme tag
            import copy
            item.rxn_data = copy.deepcopy(d["reaction"])
    else:
        raise ValueError(f"unknown item type: {kind!r}")
    _apply_label(item, d)
    if d.get("symbol"):
        item.symbol = str(d["symbol"])
    item.setOpacity(d.get("opacity", 1.0))
    item.setZValue(d.get("z", 0.0))
    if kind == "image" and "matrix" in d:
        mx = d["matrix"]
        item.setTransformOriginPoint(0, 0)
        item.setTransform(QTransform(mx[0], mx[1], mx[2], mx[3], 0, 0))
        item.setPos(mx[4], mx[5])
    else:
        pos = d.get("pos", {})
        item.setPos(pos.get("x", 0), pos.get("y", 0))
        center_origin(item)      # rotate/scale about centre as it saved
        item.setRotation(d.get("rotation", 0.0))
        item.setScale(d.get("scale", 1.0))
        if "matrix" in d:        # group X/Y-only resize transform
            m = d["matrix"]
            item.setTransform(QTransform(m[0], m[1], m[2], m[3], m[4], m[5]))
    return item


# ---------------------------------------------------------------- raster
def _pixmap_to_b64(pixmap: QPixmap) -> str:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return base64.b64encode(bytes(data)).decode("ascii")


def _pixmap_from_b64(text: str) -> QPixmap:
    pixmap = QPixmap()
    pixmap.loadFromData(base64.b64decode(text), "PNG")
    return pixmap


# ---------------------------------------------------------------- files
def scene_to_dict(scene: PaintScene) -> dict:
    rect = scene.sceneRect()
    return {"format": "kpaint", "version": FORMAT_VERSION,
            "width": int(rect.width()), "height": int(rect.height()),
            "dpi": getattr(scene, "dpi", 96),
            "grid": {"mm": scene.grid_mm, "show": scene.show_grid,
                     "snap": scene.snap_enabled, "infinite": scene.infinite},
            "raster": _pixmap_to_b64(scene.raster_item.pixmap()),
            "items": [item_to_dict(i) for i in scene.vector_items()]}


def dict_to_scene(data: dict, scene: PaintScene):
    if data.get("format") != "kpaint":
        raise ValueError("not a KhervePaint document")
    width = data.get("width", 800)
    scene.new_document(width, data.get("height", 600))
    scene.dpi = data.get("dpi", 96)
    grid = data.get("grid", {})
    if "mm" in grid:
        scene.grid_mm = float(grid["mm"])
    elif "divisions" in grid:     # legacy: grid was divisions across width
        px = (width or 1) / max(grid["divisions"], 1)
        scene.grid_mm = px / scene.dpi * 25.4
    elif "size" in grid:          # legacy: grid was a pixel spacing
        scene.grid_mm = float(grid["size"]) / scene.dpi * 25.4
    scene.show_grid = grid.get("show", True)
    scene.snap_enabled = grid.get("snap", True)
    scene.infinite = grid.get("infinite", False)
    if data.get("raster"):
        scene.set_raster_pixmap(_pixmap_from_b64(data["raster"]))
    for item_dict in data.get("items", []):
        scene.addItem(item_from_dict(item_dict))


def save_kpaint(scene: PaintScene, path: str):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(scene_to_dict(scene), fh, indent=1)


def load_kpaint(scene: PaintScene, path: str):
    with open(path, encoding="utf-8") as fh:
        dict_to_scene(json.load(fh), scene)


def open_png(scene: PaintScene, path: str):
    """Load *path* into the raster layer, resizing the canvas to fit."""
    pixmap = QPixmap(path)
    if pixmap.isNull():
        raise ValueError(f"cannot read image: {path}")
    scene.set_raster_pixmap(pixmap)


def export_png(scene: PaintScene, path: str):
    """Render raster + vector layers flattened to a PNG (no grid)."""
    scene.clearSelection()
    rect = scene.sceneRect()
    image = QImage(int(rect.width()), int(rect.height()),
                   QImage.Format_ARGB32)
    image.fill(Qt.white)
    dpm = round(getattr(scene, "dpi", 96) / 0.0254)   # dots per metre
    image.setDotsPerMeterX(dpm)
    image.setDotsPerMeterY(dpm)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    scene.render(painter, target=QRectF(image.rect()), source=rect)
    painter.end()
    if not image.save(path, "PNG"):
        raise ValueError(f"cannot write image: {path}")


def export_svg(scene: PaintScene, path: str):
    """Render raster + vector layers to an SVG (raster embedded)."""
    scene.clearSelection()
    rect = scene.sceneRect()
    generator = QSvgGenerator()
    generator.setFileName(path)
    generator.setSize(QSize(int(rect.width()), int(rect.height())))
    generator.setViewBox(QRectF(0, 0, rect.width(), rect.height()))
    generator.setTitle("KhervePaint export")
    painter = QPainter(generator)
    painter.setRenderHint(QPainter.Antialiasing)
    scene.render(painter, source=rect)
    painter.end()


def export_pdf(scene: PaintScene, path: str):
    """Render to a single-page PDF sized to the canvas at its dpi, so
    the page is the figure's true physical size."""
    scene.clearSelection()
    rect = scene.sceneRect()
    dpi = getattr(scene, "dpi", 96)
    writer = QPdfWriter(path)
    writer.setResolution(round(dpi))
    # Page size in points (1/72 inch); canvas pixels / dpi = inches.
    writer.setPageSize(QPageSize(
        QSizeF(rect.width() * 72 / dpi, rect.height() * 72 / dpi),
        QPageSize.Point))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    painter = QPainter(writer)
    painter.setRenderHint(QPainter.Antialiasing)
    scene.render(painter,
                 target=QRectF(0, 0, writer.width(), writer.height()),
                 source=rect)
    painter.end()
