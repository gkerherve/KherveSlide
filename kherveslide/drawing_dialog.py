"""Freehand / shape drawing dialog.

Lets the user sketch a quick diagram inside the editor and have it
inserted as a Figure block — the figure path points at a PNG the
dialog wrote into the document's images folder, so \\includegraphics
in the compiled PDF picks it up automatically.

Tools: select (drag/move), pen (freehand), straight line, rectangle,
ellipse, arrow, text caption, eraser.  Plus Undo — the canvas keeps
a flat list of QGraphicsItems so undo just pops the last one off.

The canvas shows a snap-able grid drawn by the *view* (not the scene),
so it never appears in the exported PNG.  A JSON sidecar file is saved
alongside each PNG so drawings can be re-opened and edited later.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction, QActionGroup, QBrush, QColor, QFont, QImage, QKeySequence,
    QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QButtonGroup, QColorDialog, QDialog, QDialogButtonBox, QGraphicsEllipseItem,
    QGraphicsItem, QGraphicsLineItem, QGraphicsPathItem, QGraphicsRectItem,
    QGraphicsScene, QGraphicsTextItem, QGraphicsView, QHBoxLayout,
    QInputDialog, QLabel, QPushButton, QSlider, QSpinBox, QToolBar,
    QToolButton, QVBoxLayout, QWidget,
)


# Pre-set colour palette — clicking a swatch sets the current pen.
_PALETTE = [
    "#000000",  # black
    "#1a6dd8",  # blue (KherveTeX accent)
    "#d8000c",  # red
    "#0a6f00",  # green
    "#d96b00",  # orange
    "#8e44ad",  # purple
    "#7a7a7a",  # grey
]

# Item-data key used to tag the drawing-tool type on each QGraphicsItem
# so we can serialize and deserialize faithfully.
_DATA_TOOL = 0


class _Canvas(QGraphicsView):
    """A QGraphicsView that builds items from mouse events according
    to the currently-selected tool."""

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setBackgroundBrush(QBrush(QColor("white")))
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.NoDrag)
        self._tool = "pen"
        self._pen_color = QColor("#000000")
        self._pen_width = 2
        self._font_size = 14
        self._origin: QPointF | None = None
        self._active_item = None
        self._pen_path: QPainterPath | None = None
        self._show_grid = True
        self._grid_spacing = 20
        self._snap_enabled = False
        self._history: list[list] = []

    # ----- tool / style accessors -------------------------------------

    def set_tool(self, tool: str) -> None:
        if self._tool == "select" and tool != "select":
            self._disable_selection()
        self._tool = tool
        if tool == "select":
            self._enable_selection()

    def set_color(self, color: QColor) -> None:
        self._pen_color = color

    def set_width(self, width: int) -> None:
        self._pen_width = max(1, int(width))

    def set_font_size(self, size: int) -> None:
        self._font_size = max(8, int(size))

    def set_grid_visible(self, visible: bool) -> None:
        self._show_grid = visible
        self.viewport().update()

    def set_snap_enabled(self, enabled: bool) -> None:
        self._snap_enabled = enabled

    def _pen(self) -> QPen:
        pen = QPen(self._pen_color, self._pen_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        return pen

    def _snap(self, pos: QPointF) -> QPointF:
        if not self._snap_enabled:
            return pos
        s = self._grid_spacing
        return QPointF(round(pos.x() / s) * s, round(pos.y() / s) * s)

    # ----- grid painting ----------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        if not self._show_grid:
            return
        s = self._grid_spacing
        pen = QPen(QColor("#e0e0e0"), 0.5)
        painter.setPen(pen)
        left = int(rect.left()) - (int(rect.left()) % s)
        top = int(rect.top()) - (int(rect.top()) % s)
        x = left
        while x <= rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += s
        y = top
        while y <= rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += s

    # ----- select / drag helpers --------------------------------------

    def _enable_selection(self) -> None:
        self.setDragMode(QGraphicsView.RubberBandDrag)
        for item in self.scene().items():
            item.setFlag(QGraphicsItem.ItemIsMovable, True)
            item.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def _disable_selection(self) -> None:
        self.scene().clearSelection()
        self.setDragMode(QGraphicsView.NoDrag)
        for item in self.scene().items():
            item.setFlag(QGraphicsItem.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.ItemIsSelectable, False)

    # ----- mouse handling ---------------------------------------------

    def mousePressEvent(self, ev):
        if self._tool == "select":
            return super().mousePressEvent(ev)
        if ev.button() != Qt.LeftButton:
            return super().mousePressEvent(ev)
        scene_pos = self._snap(self.mapToScene(ev.position().toPoint()))
        if self._tool == "pen":
            self._pen_path = QPainterPath(scene_pos)
            self._active_item = QGraphicsPathItem(self._pen_path)
            self._active_item.setPen(self._pen())
            self._active_item.setData(_DATA_TOOL, "path")
            self.scene().addItem(self._active_item)
        elif self._tool == "line":
            self._origin = scene_pos
            self._active_item = QGraphicsLineItem(
                scene_pos.x(), scene_pos.y(),
                scene_pos.x(), scene_pos.y())
            self._active_item.setPen(self._pen())
            self._active_item.setData(_DATA_TOOL, "line")
            self.scene().addItem(self._active_item)
        elif self._tool == "rect":
            self._origin = scene_pos
            self._active_item = QGraphicsRectItem(
                QRectF(scene_pos, scene_pos))
            self._active_item.setPen(self._pen())
            self._active_item.setData(_DATA_TOOL, "rect")
            self.scene().addItem(self._active_item)
        elif self._tool == "ellipse":
            self._origin = scene_pos
            self._active_item = QGraphicsEllipseItem(
                QRectF(scene_pos, scene_pos))
            self._active_item.setPen(self._pen())
            self._active_item.setData(_DATA_TOOL, "ellipse")
            self.scene().addItem(self._active_item)
        elif self._tool == "arrow":
            self._origin = scene_pos
            self._active_item = QGraphicsPathItem()
            self._active_item.setPen(self._pen())
            self._active_item.setData(_DATA_TOOL, "arrow")
            self.scene().addItem(self._active_item)
        elif self._tool == "eraser":
            item = self.scene().itemAt(scene_pos, self.transform())
            if item is not None:
                self.scene().removeItem(item)
                self._history.append([("removed", item)])
        elif self._tool == "text":
            text, ok = QInputDialog.getText(self, "Add text", "Text:")
            if ok and text:
                item = QGraphicsTextItem(text)
                f = QFont("Arial")
                f.setPointSize(self._font_size)
                item.setFont(f)
                item.setDefaultTextColor(self._pen_color)
                item.setPos(scene_pos)
                item.setData(_DATA_TOOL, "text")
                self.scene().addItem(item)
                self._history.append([("added", item)])
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._tool == "select":
            return super().mouseMoveEvent(ev)
        if self._active_item is None:
            return super().mouseMoveEvent(ev)
        scene_pos = self._snap(self.mapToScene(ev.position().toPoint()))
        if self._tool == "pen" and self._pen_path is not None:
            self._pen_path.lineTo(scene_pos)
            self._active_item.setPath(self._pen_path)
        elif self._tool == "line" and self._origin is not None:
            self._active_item.setLine(
                self._origin.x(), self._origin.y(),
                scene_pos.x(), scene_pos.y())
        elif self._tool in ("rect", "ellipse") and self._origin is not None:
            r = QRectF(self._origin, scene_pos).normalized()
            self._active_item.setRect(r)
        elif self._tool == "arrow" and self._origin is not None:
            self._active_item.setPath(
                self._arrow_path(self._origin, scene_pos))
        return super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._tool == "select":
            return super().mouseReleaseEvent(ev)
        if self._active_item is not None:
            self._history.append([("added", self._active_item)])
        self._active_item = None
        self._origin = None
        self._pen_path = None
        return super().mouseReleaseEvent(ev)

    def _arrow_path(self, start: QPointF, end: QPointF) -> QPainterPath:
        """Straight line from start to end with a small triangular
        head at the end. Head size scales with pen width."""
        path = QPainterPath(start)
        path.lineTo(end)
        dx, dy = end.x() - start.x(), end.y() - start.y()
        length = math.hypot(dx, dy)
        if length < 1e-3:
            return path
        head_len = 6 + self._pen_width * 2
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        base_x = end.x() - ux * head_len
        base_y = end.y() - uy * head_len
        wing_a = QPointF(base_x + px * head_len * 0.4,
                         base_y + py * head_len * 0.4)
        wing_b = QPointF(base_x - px * head_len * 0.4,
                         base_y - py * head_len * 0.4)
        path.moveTo(end)
        path.lineTo(wing_a)
        path.moveTo(end)
        path.lineTo(wing_b)
        return path

    # ----- history actions --------------------------------------------

    def undo(self) -> None:
        if not self._history:
            return
        last = self._history.pop()
        for action, item in last:
            if action == "added":
                self.scene().removeItem(item)
            elif action == "removed":
                self.scene().addItem(item)

    def clear_all(self) -> None:
        items = list(self.scene().items())
        for it in items:
            self.scene().removeItem(it)
        if items:
            self._history.append([("removed", it) for it in items])

    # ----- serialization ----------------------------------------------

    def serialize_scene(self) -> dict:
        """Return a JSON-serializable dict of every item on the scene."""
        items_data: list[dict] = []
        # scene.items() returns descending z-order; reverse for ascending
        for item in reversed(list(self.scene().items())):
            d = self._serialize_item(item)
            if d is not None:
                items_data.append(d)
        return {"version": 1, "items": items_data}

    def _serialize_item(self, item) -> dict | None:
        tool = item.data(_DATA_TOOL)
        if isinstance(item, QGraphicsTextItem):
            return {
                "type": "text",
                "x": round(item.pos().x(), 1),
                "y": round(item.pos().y(), 1),
                "text": item.toPlainText(),
                "color": item.defaultTextColor().name(),
                "font_size": item.font().pointSize(),
            }
        if isinstance(item, QGraphicsLineItem):
            ln = item.line()
            p = item.pos()
            return {
                "type": "line",
                "x1": round(ln.x1() + p.x(), 1),
                "y1": round(ln.y1() + p.y(), 1),
                "x2": round(ln.x2() + p.x(), 1),
                "y2": round(ln.y2() + p.y(), 1),
                "color": item.pen().color().name(),
                "width": item.pen().widthF(),
            }
        if isinstance(item, QGraphicsRectItem):
            r = item.rect()
            p = item.pos()
            return {
                "type": "rect",
                "x": round(r.x() + p.x(), 1),
                "y": round(r.y() + p.y(), 1),
                "w": round(r.width(), 1),
                "h": round(r.height(), 1),
                "color": item.pen().color().name(),
                "width": item.pen().widthF(),
            }
        if isinstance(item, QGraphicsEllipseItem):
            r = item.rect()
            p = item.pos()
            return {
                "type": "ellipse",
                "x": round(r.x() + p.x(), 1),
                "y": round(r.y() + p.y(), 1),
                "w": round(r.width(), 1),
                "h": round(r.height(), 1),
                "color": item.pen().color().name(),
                "width": item.pen().widthF(),
            }
        if isinstance(item, QGraphicsPathItem):
            path = item.path()
            p = item.pos()
            elements = []
            for i in range(path.elementCount()):
                el = path.elementAt(i)
                t = {
                    QPainterPath.ElementType.MoveToElement: "M",
                    QPainterPath.ElementType.LineToElement: "L",
                    QPainterPath.ElementType.CurveToElement: "C",
                    QPainterPath.ElementType.CurveToDataElement: "c",
                }.get(el.type, "L")
                elements.append({
                    "t": t,
                    "x": round(el.x + p.x(), 1),
                    "y": round(el.y + p.y(), 1),
                })
            return {
                "type": tool if tool in ("path", "arrow") else "path",
                "elements": elements,
                "color": item.pen().color().name(),
                "width": item.pen().widthF(),
            }
        return None

    def deserialize_scene(self, data: dict) -> None:
        """Reconstruct scene items from a previously-serialized dict."""
        self.scene().clear()
        self._history.clear()
        for d in data.get("items", []):
            item = self._deserialize_item(d)
            if item is not None:
                self.scene().addItem(item)
                self._history.append([("added", item)])

    def _deserialize_item(self, d: dict):
        t = d.get("type", "")
        color = QColor(d.get("color", "#000000"))
        width = d.get("width", 2)
        pen = QPen(color, width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)

        if t == "text":
            item = QGraphicsTextItem(d.get("text", ""))
            f = QFont("Arial")
            f.setPointSize(d.get("font_size", 14))
            item.setFont(f)
            item.setDefaultTextColor(color)
            item.setPos(d.get("x", 0), d.get("y", 0))
            item.setData(_DATA_TOOL, "text")
            return item

        if t == "line":
            item = QGraphicsLineItem(
                d.get("x1", 0), d.get("y1", 0),
                d.get("x2", 0), d.get("y2", 0))
            item.setPen(pen)
            item.setData(_DATA_TOOL, "line")
            return item

        if t == "rect":
            item = QGraphicsRectItem(QRectF(
                d.get("x", 0), d.get("y", 0),
                d.get("w", 0), d.get("h", 0)))
            item.setPen(pen)
            item.setData(_DATA_TOOL, "rect")
            return item

        if t == "ellipse":
            item = QGraphicsEllipseItem(QRectF(
                d.get("x", 0), d.get("y", 0),
                d.get("w", 0), d.get("h", 0)))
            item.setPen(pen)
            item.setData(_DATA_TOOL, "ellipse")
            return item

        if t in ("path", "arrow"):
            path = QPainterPath()
            for el in d.get("elements", []):
                if el["t"] == "M":
                    path.moveTo(el["x"], el["y"])
                else:
                    path.lineTo(el["x"], el["y"])
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            item.setData(_DATA_TOOL, t)
            return item

        return None


class DrawingDialog(QDialog):
    """Modal dialog: draw something, click OK, get a PNG path back.

    The PNG is written into `images_dir` so the inserted Figure
    block's `\\includegraphics{...}` path resolves both in the
    editor's preview and in any downstream LaTeX build.

    Pass *existing_path* to reopen a previously-saved drawing for
    editing — the dialog loads the JSON sidecar and reconstructs
    the scene.  On accept the same file is overwritten."""

    drawingSaved = Signal(str)   # absolute path to the saved PNG

    def __init__(self, images_dir: Path, parent: QWidget | None = None,
                 existing_path: Path | None = None):
        super().__init__(parent)
        self._images_dir = Path(images_dir)
        self._images_dir.mkdir(parents=True, exist_ok=True)
        self._saved_path: Path | None = None
        self._existing_path = Path(existing_path) if existing_path else None

        if self._existing_path:
            self.setWindowTitle("Edit Drawing")
        else:
            self.setWindowTitle("Drawing")
        self.resize(900, 660)

        # ---- canvas ------------------------------------------------------
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(0, 0, 1200, 800)
        self._canvas = _Canvas(self._scene, self)

        # ---- tool toolbar ------------------------------------------------
        tb = QToolBar(self)
        tb.setIconSize(tb.iconSize())
        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusive(True)
        for name, label in (
            ("select", "⇱ Select"),
            ("pen", "✎ Pen"),
            ("line", "／ Line"),
            ("rect", "▭ Rect"),
            ("ellipse", "◯ Ellipse"),
            ("arrow", "→ Arrow"),
            ("text", "T Text"),
            ("eraser", "✗ Eraser"),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.triggered.connect(
                lambda checked=False, n=name: self._canvas.set_tool(n))
            self._tool_group.addAction(act)
            tb.addAction(act)
            if name == "pen":
                act.setChecked(True)
        tb.addSeparator()
        undo_act = QAction("⤺ Undo", self)
        undo_act.setShortcut(QKeySequence.Undo)
        undo_act.triggered.connect(self._canvas.undo)
        tb.addAction(undo_act)
        clear_act = QAction("Clear", self)
        clear_act.triggered.connect(self._canvas.clear_all)
        tb.addAction(clear_act)
        tb.addSeparator()
        grid_act = QAction("# Grid", self)
        grid_act.setCheckable(True)
        grid_act.setChecked(True)
        grid_act.toggled.connect(self._canvas.set_grid_visible)
        tb.addAction(grid_act)
        snap_act = QAction("⊞ Snap", self)
        snap_act.setCheckable(True)
        snap_act.setChecked(False)
        snap_act.toggled.connect(self._canvas.set_snap_enabled)
        tb.addAction(snap_act)

        # ---- color palette + width slider + font size --------------------
        palette_row = QHBoxLayout()
        palette_row.setSpacing(4)
        palette_row.addWidget(QLabel("Colour:"))
        for color in _PALETTE:
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setStyleSheet(
                f"background:{color}; border:1px solid #888;"
                "border-radius:11px;")
            btn.setToolTip(color)
            btn.clicked.connect(
                lambda checked=False, c=color: self._canvas.set_color(QColor(c)))
            palette_row.addWidget(btn)
        custom = QPushButton("…")
        custom.setFixedSize(28, 22)
        custom.setToolTip("Pick a custom colour")
        custom.clicked.connect(self._pick_custom_color)
        palette_row.addWidget(custom)
        palette_row.addSpacing(16)
        palette_row.addWidget(QLabel("Width:"))
        self._width_slider = QSlider(Qt.Horizontal)
        self._width_slider.setRange(1, 20)
        self._width_slider.setValue(2)
        self._width_slider.setFixedWidth(140)
        self._width_slider.valueChanged.connect(self._canvas.set_width)
        palette_row.addWidget(self._width_slider)
        self._width_label = QLabel("2 px")
        palette_row.addWidget(self._width_label)
        self._width_slider.valueChanged.connect(
            lambda v: self._width_label.setText(f"{v} px"))
        palette_row.addSpacing(16)
        palette_row.addWidget(QLabel("Font:"))
        self._font_spin = QSpinBox()
        self._font_spin.setRange(8, 72)
        self._font_spin.setValue(14)
        self._font_spin.setSuffix(" pt")
        self._font_spin.valueChanged.connect(self._canvas.set_font_size)
        palette_row.addWidget(self._font_spin)
        palette_row.addStretch(1)

        # ---- buttons -----------------------------------------------------
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_and_save)
        buttons.rejected.connect(self.reject)

        # ---- layout ------------------------------------------------------
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(tb)
        outer.addLayout(palette_row)
        outer.addWidget(self._canvas, 1)
        outer.addWidget(buttons)

        # ---- load existing drawing if re-editing -------------------------
        if self._existing_path:
            sidecar = self._existing_path.with_suffix(".json")
            if sidecar.exists():
                try:
                    with open(sidecar, "r", encoding="utf-8") as fh:
                        self._canvas.deserialize_scene(json.load(fh))
                except (json.JSONDecodeError, OSError):
                    pass

    def saved_path(self) -> Path | None:
        return self._saved_path

    # ---- actions -------------------------------------------------------

    def _pick_custom_color(self) -> None:
        c = QColorDialog.getColor(QColor("#000000"), self,
                                   "Pick colour")
        if c.isValid():
            self._canvas.set_color(c)

    def _accept_and_save(self) -> None:
        items = list(self._scene.items())
        if not items:
            self.reject()
            return
        bounds = self._scene.itemsBoundingRect()
        if bounds.isEmpty():
            self.reject()
            return
        pad = 16
        bounds.adjust(-pad, -pad, pad, pad)
        scale = 2
        img = QImage(int(bounds.width() * scale),
                     int(bounds.height() * scale),
                     QImage.Format_ARGB32)
        img.fill(QColor("white"))
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        self._scene.render(painter, target=QRectF(img.rect()),
                           source=bounds)
        painter.end()

        if self._existing_path is not None:
            target = self._existing_path
        else:
            i = 1
            while True:
                target = self._images_dir / f"drawing_{i:03d}.png"
                if not target.exists():
                    break
                i += 1

        if not img.save(str(target), "PNG"):
            self.reject()
            return

        # Save JSON sidecar alongside the PNG for future re-editing.
        sidecar = target.with_suffix(".json")
        try:
            with open(sidecar, "w", encoding="utf-8") as fh:
                json.dump(self._canvas.serialize_scene(), fh, indent=2)
        except OSError:
            pass

        self._saved_path = target
        self.drawingSaved.emit(str(target))
        self.accept()
