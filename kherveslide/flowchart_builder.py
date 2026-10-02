"""Flowchart builder — build a LaTeX (TikZ) flowchart by clicking.

Like the equation builder: a palette of the classic flowchart shapes;
clicking one adds that box after the selected one and joins them with an
arrow, so a chart grows as fast as you can click. Drag boxes to move
them (they snap to a grid), Ctrl/⌘-click a box to draw an arrow to it
from the selected one, and edit the text of a box or the label of an
arrow in the panel on the right (LaTeX maths welcome). The preview below
it is compiled with LaTeX — exactly what lands on the slide. Tidy up
lays the chart out by itself; Show LaTeX gives the TikZ code.

The model and the TikZ live in flowchart.py; this is only the editor.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QThread, QTimer, \
    Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QIcon, QImage, QPainter, QPainterPath,
    QPainterPathStroker, QPen, QPixmap, QPolygonF, QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGraphicsItem, QGraphicsObject, QGraphicsScene,
    QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from . import flowchart as F

GX, GY = 160.0, 90.0          # px per grid column / row on the editor
NODE_W, NODE_H = 128.0, 50.0


# ----------------------------------------------------------- shape paths
def shape_path(kind: str, r: QRectF) -> QPainterPath:
    """The outline of a flowchart shape in *r* (editor and icons)."""
    p = QPainterPath()
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    if kind == "terminal":
        p.addRoundedRect(r, h / 2, h / 2)
    elif kind == "decision":
        p.addPolygon(QPolygonF([QPointF(x + w / 2, y), QPointF(x + w, y + h / 2),
                                QPointF(x + w / 2, y + h), QPointF(x, y + h / 2),
                                QPointF(x + w / 2, y)]))
    elif kind == "io":
        k = h * 0.35
        p.addPolygon(QPolygonF([QPointF(x + k, y), QPointF(x + w, y),
                                QPointF(x + w - k, y + h), QPointF(x, y + h),
                                QPointF(x + k, y)]))
    elif kind == "document":
        p.moveTo(x, y)
        p.lineTo(x + w, y)
        p.lineTo(x + w, y + h * 0.82)
        p.cubicTo(x + w * 0.75, y + h * 0.6, x + w * 0.25, y + h * 1.05,
                  x, y + h * 0.82)
        p.closeSubpath()
    elif kind == "database":
        e = h * 0.18
        p.addRect(QRectF(x, y + e / 2, w, h - e))
        p.addEllipse(QRectF(x, y, w, e))
        p.addEllipse(QRectF(x, y + h - e, w, e))
    elif kind == "connector":
        d = min(w, h)
        p.addEllipse(QRectF(x + (w - d) / 2, y + (h - d) / 2, d, d))
    else:                                       # process, subprocess, note
        p.addRect(r)
        if kind == "subprocess":
            p.addRect(r.adjusted(5, 0, -5, 0))
    return p


def kind_icon(kind: str, fill: str = "#DEEBF7", size: int = 40) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(2)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(3, size * 0.25, size - 6, size * 0.5)
    if kind == "decision":
        r = QRectF(3, size * 0.15, size - 6, size * 0.7)
    if kind == "connector":
        r = QRectF(size * 0.25, size * 0.25, size * 0.5, size * 0.5)
    pen = QPen(QColor("#404040"), 1.4)
    if kind == "note":
        pen.setStyle(Qt.DashLine)
    p.setPen(pen)
    p.setBrush(QColor(fill))
    p.drawPath(shape_path(kind, r))
    p.end()
    return QIcon(pm)


# ------------------------------------------------------------ the editor
class NodeItem(QGraphicsObject):
    moved = Signal(object)          # self, after a drag

    def __init__(self, node: F.Node, fill: str, text_col: str):
        super().__init__()
        self.node = node
        self.fill = fill
        self.text_col = text_col
        w = 46.0 if node.kind == "connector" else NODE_W
        h = 46.0 if node.kind == "connector" else (
            64.0 if node.kind == "decision" else NODE_H)
        self.rect = QRectF(-w / 2, -h / 2, w, h)
        self.setFlags(QGraphicsItem.ItemIsMovable
                      | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setPos(node.x * GX, node.y * GY)
        self.setZValue(1)
        self.setCursor(Qt.SizeAllCursor)

    def boundingRect(self):
        return self.rect.adjusted(-4, -4, 4, 4)

    def shape(self):
        p = QPainterPath()
        p.addRect(self.rect)
        return p

    def paint(self, p, _opt, _w=None):
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#404040"), 1.4)
        if self.node.kind == "note":
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(self.node.fill or self.fill))
        p.drawPath(shape_path(self.node.kind, self.rect))
        from .canvas import _pretty_inline_html
        doc = QTextDocument()
        f = QFont()
        f.setPixelSize(12)
        doc.setDefaultFont(f)
        opt = QTextOption(Qt.AlignHCenter)
        opt.setWrapMode(QTextOption.WordWrap)
        doc.setDefaultTextOption(opt)
        text = self.node.text.replace("\\\\", "\n")
        html = "<br>".join(_pretty_inline_html(t) for t in text.split("\n"))
        doc.setHtml(f'<div style="color:{self.text_col}">{html}</div>')
        tw = self.rect.width() - (30 if self.node.kind in ("decision", "io")
                                  else 10)
        doc.setTextWidth(tw)
        p.save()
        p.translate(-tw / 2, -doc.size().height() / 2)
        doc.drawContents(p)
        p.restore()
        if self.isSelected():
            p.setPen(QPen(QColor("#DE6A14"), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.rect.adjusted(-3, -3, 3, 3))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # snap to a quarter of the grid
            return QPointF(round(value.x() / (GX / 4)) * (GX / 4),
                           round(value.y() / (GY / 4)) * (GY / 4))
        if change == QGraphicsItem.ItemPositionHasChanged and \
                self.scene() is not None:
            self.scene().node_moving(self)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        x, y = self.pos().x() / GX, self.pos().y() / GY
        if (round(x, 3), round(y, 3)) != (round(self.node.x, 3),
                                           round(self.node.y, 3)):
            self.node.x, self.node.y = round(x, 3), round(y, 3)
            self.moved.emit(self)

    def mouseDoubleClickEvent(self, event):
        self.scene().edit_requested.emit(self)


class EdgeItem(QGraphicsItem):
    def __init__(self, edge: F.Edge, a: NodeItem, b: NodeItem,
                 direction: str):
        super().__init__()
        self.edge, self.a, self.b, self.direction = edge, a, b, direction
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setZValue(0)
        self.setCursor(Qt.PointingHandCursor)
        self._path = QPainterPath()
        self.update_path()

    def _anchor(self, item: NodeItem, toward: QPointF) -> QPointF:
        """Where a line from the centre toward *toward* leaves the box."""
        c = item.pos()
        r = item.rect
        dx, dy = toward.x() - c.x(), toward.y() - c.y()
        if abs(dx) * r.height() > abs(dy) * r.width():
            return QPointF(c.x() + (r.right() if dx > 0 else r.left()),
                           c.y())
        return QPointF(c.x(), c.y() + (r.bottom() if dy > 0 else r.top()))

    def update_path(self):
        self.prepareGeometryChange()
        a, b = self.a.pos(), self.b.pos()
        path = QPainterPath()
        tb = self.direction == "TB"
        straight = (self.edge.route == "straight" or abs(a.x() - b.x()) < 1
                    or abs(a.y() - b.y()) < 1)
        back = (tb and b.y() < a.y() and abs(a.x() - b.x()) < 1) or \
            (not tb and b.x() < a.x() and abs(a.y() - b.y()) < 1)
        if back:
            off = -(self.a.rect.width() / 2 + 30) if tb else \
                (self.a.rect.height() / 2 + 30)
            if tb:
                p1 = QPointF(a.x() + self.a.rect.left(), a.y())
                p4 = QPointF(b.x() + self.b.rect.left(), b.y())
                pts = [p1, QPointF(a.x() + off, a.y()),
                       QPointF(a.x() + off, b.y()), p4]
            else:
                p1 = QPointF(a.x(), a.y() + self.a.rect.bottom())
                p4 = QPointF(b.x(), b.y() + self.b.rect.bottom())
                pts = [p1, QPointF(a.x(), a.y() + off),
                       QPointF(b.x(), a.y() + off), p4]
        elif straight:
            pts = [self._anchor(self.a, b), self._anchor(self.b, a)]
        else:
            across_first = (self.a.node.kind == "decision") == tb
            corner = QPointF(b.x(), a.y()) if across_first \
                else QPointF(a.x(), b.y())
            pts = [self._anchor(self.a, corner), corner,
                   self._anchor(self.b, corner)]
        path.moveTo(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        self._path = path
        self._pts = pts

    def boundingRect(self):
        return self._path.boundingRect().adjusted(-40, -20, 40, 20)

    def shape(self):
        s = QPainterPathStroker()
        s.setWidth(10)
        return s.createStroke(self._path)

    def paint(self, p, _opt, _w=None):
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor("#DE6A14") if self.isSelected() else QColor("#404040")
        pen = QPen(col, 2 if self.isSelected() else 1.4)
        if self.edge.dashed:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(self._path)
        # arrowhead at the last point
        tip, prev = self._pts[-1], self._pts[-2]
        v = QPointF(tip.x() - prev.x(), tip.y() - prev.y())
        length = max(1e-6, (v.x() ** 2 + v.y() ** 2) ** 0.5)
        ux, uy = v.x() / length, v.y() / length
        size = 9
        left = QPointF(tip.x() - ux * size - uy * size * 0.45,
                       tip.y() - uy * size + ux * size * 0.45)
        right = QPointF(tip.x() - ux * size + uy * size * 0.45,
                        tip.y() - uy * size - ux * size * 0.45)
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([tip, left, right]))
        if self.edge.label:
            a, b = self._pts[0], self._pts[1]
            mid = QPointF(a.x() + (b.x() - a.x()) * 0.3,
                          a.y() + (b.y() - a.y()) * 0.3)
            f = QFont()
            f.setPixelSize(11)
            p.setFont(f)
            p.setPen(QColor("#222222"))
            p.drawText(QRectF(mid.x() + 4, mid.y() - 16, 80, 16),
                       Qt.AlignLeft | Qt.AlignVCenter, self.edge.label)

    def mouseDoubleClickEvent(self, event):
        self.scene().edit_requested.emit(self)


class FlowScene(QGraphicsScene):
    edit_requested = Signal(object)
    changed_by_user = Signal()

    def __init__(self):
        super().__init__()
        self.edges: list[EdgeItem] = []

    def node_moving(self, _item):
        for e in self.edges:
            e.update_path()
        self.update()

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor("#FAFAF8"))
        painter.setPen(QPen(QColor(0, 0, 0, 16), 0))
        x = int(rect.left() // (GX / 2)) * (GX / 2)
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += GX / 2
        y = int(rect.top() // (GY / 2)) * (GY / 2)
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += GY / 2


class FlowView(QGraphicsView):
    connect_requested = Signal(object)        # NodeItem Ctrl/⌘-clicked
    delete_requested = Signal()
    menu_requested = Signal(object, object)   # item | None, global pos

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        while item is not None and not isinstance(item, NodeItem) and \
                item.parentItem() is not None:
            item = item.parentItem()
        if (event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier)
                and isinstance(item, NodeItem)
                and event.button() == Qt.LeftButton):
            self.connect_requested.emit(item)
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_requested.emit()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        f = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(f, f)

    def contextMenuEvent(self, event):
        self.menu_requested.emit(self.itemAt(event.pos()), event.globalPos())


# --------------------------------------------------------- live preview
class _PreviewWorker(QThread):
    done = Signal(object, str, str)        # pdf bytes | None, log, tex

    def __init__(self, tex: str):
        super().__init__()
        self._tex = tex

    def run(self):
        from .compiler import compile_tex
        data, log = None, ""
        try:
            r = compile_tex(self._tex, Path(tempfile.gettempdir())
                            / "kherveslide_flowprev", "flow")
            log = r.log or ""
            if r.ok and r.pdf_path:
                data = Path(r.pdf_path).read_bytes()
        except Exception as exc:
            log = str(exc)
        self.done.emit(data, log, self._tex)


def _pdf_to_pixmap(data: bytes, width: int) -> QPixmap | None:
    try:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            page = doc[0]
            z = width / max(1.0, page.rect.width)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format_RGB888).copy()
        return QPixmap.fromImage(img)
    except Exception:
        return None


# ---------------------------------------------------------------- dialog
class FlowchartBuilderDialog(QDialog):
    """On accept: ``result_chart`` (Flowchart), ``result_pdf`` (bytes of
    the compiled chart) and ``result_tikz`` (the TikZ code)."""

    def __init__(self, parent=None, chart: F.Flowchart | None = None,
                 primary: str = "#1F4E79"):
        super().__init__(parent)
        self.setWindowTitle("Flowchart builder")
        self.resize(1240, 780)
        self.primary = primary
        self.fc = chart or F.template_simple()
        self.result_chart = None
        self.result_pdf: bytes | None = None
        self.result_tikz = ""
        self._history = [self.fc.to_json()]
        self._hist_i = 0
        self._worker: _PreviewWorker | None = None
        self._pending = False
        self._last_pdf: tuple[str, bytes] | None = None   # (tex, pdf)
        self._items: dict[str, NodeItem] = {}
        self._selected_edge: EdgeItem | None = None

        root = QVBoxLayout(self)

        # --- top bar -----------------------------------------------------
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Start from:"))
        self.template = QComboBox()
        self.template.addItem("—")
        self.template.addItems(list(F.TEMPLATES))
        self.template.activated.connect(self._use_template)
        bar.addWidget(self.template)
        bar.addSpacing(10)
        bar.addWidget(QLabel("Direction:"))
        self.direction = QComboBox()
        self.direction.addItem("Top to bottom", "TB")
        self.direction.addItem("Left to right", "LR")
        self.direction.currentIndexChanged.connect(self._set_direction)
        bar.addWidget(self.direction)
        bar.addSpacing(10)
        bar.addWidget(QLabel("Colours:"))
        self.scheme = QComboBox()
        self.scheme.addItems(F.SCHEME_NAMES)
        self.scheme.currentTextChanged.connect(
            lambda s: self._change(lambda: setattr(self.fc, "scheme", s)))
        bar.addWidget(self.scheme)
        bar.addSpacing(10)
        bar.addWidget(QLabel("Text:"))
        self.font_pt = QSpinBox()
        self.font_pt.setRange(6, 24)
        self.font_pt.setSuffix(" pt")
        self.font_pt.valueChanged.connect(
            lambda v: self._change(lambda: setattr(self.fc, "font_pt", v)))
        bar.addWidget(self.font_pt)
        bar.addSpacing(10)
        tidy = QPushButton("✨ Tidy up")
        tidy.setToolTip("Lay the chart out automatically")
        tidy.clicked.connect(lambda: self._change(
            lambda: F.auto_layout(self.fc), rebuild=True))
        bar.addWidget(tidy)
        bar.addStretch(1)
        self.undo_btn = QToolButton()
        self.undo_btn.setText("↶")
        self.undo_btn.setToolTip("Undo (Ctrl+Z)")
        self.undo_btn.setShortcut("Ctrl+Z")
        self.undo_btn.clicked.connect(lambda: self._step(-1))
        self.redo_btn = QToolButton()
        self.redo_btn.setText("↷")
        self.redo_btn.setToolTip("Redo (Ctrl+Y)")
        self.redo_btn.setShortcut("Ctrl+Y")
        self.redo_btn.clicked.connect(lambda: self._step(1))
        bar.addWidget(self.undo_btn)
        bar.addWidget(self.redo_btn)
        root.addLayout(bar)

        # --- shape palette ----------------------------------------------
        pal = QHBoxLayout()
        pal.setSpacing(4)
        cols = F.colours(self.fc, primary)
        self._palette_buttons = []
        for kind, (label, _opts) in F.KINDS.items():
            b = QToolButton()
            b.setIcon(kind_icon(kind, cols[kind][0]))
            b.setIconSize(QSize(40, 40))
            b.setText(label)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setMinimumWidth(92)
            b.setAutoRaise(True)
            b.setToolTip(f"Add a “{label}” box after the selected one, "
                         "joined by an arrow")
            b.clicked.connect(lambda _=False, k=kind: self._add(k))
            pal.addWidget(b)
            self._palette_buttons.append((b, kind))
        pal.addStretch(1)
        root.addLayout(pal)

        # --- editor | properties + preview --------------------------------
        split = QSplitter(Qt.Horizontal)
        self.scene = FlowScene()
        self.scene.edit_requested.connect(self._edit_item)
        self.scene.selectionChanged.connect(self._on_selection)
        self.view = FlowView(self.scene)
        self.view.connect_requested.connect(self._connect_to)
        self.view.delete_requested.connect(self._delete_selected)
        self.view.menu_requested.connect(self._context_menu)
        split.addWidget(self.view)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 0, 0, 0)
        self.props = QStackedWidget()
        self.props.addWidget(self._hint_page())
        self.props.addWidget(self._node_page())
        self.props.addWidget(self._edge_page())
        rv.addWidget(self.props)
        rv.addWidget(QLabel("<b>Preview</b> — compiled with LaTeX"))
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(360, 260)
        self.preview.setStyleSheet("background:#FFFFFF; border:1px solid"
                                   " #D0D0D0;")
        rv.addWidget(self.preview, 1)
        self.status = QLabel()
        self.status.setStyleSheet("color:#666;")
        self.status.setWordWrap(True)
        rv.addWidget(self.status)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        root.addWidget(split, 1)

        self.code = QPlainTextEdit()
        self.code.setReadOnly(True)
        self.code.setFont(QFont("Menlo"))
        self.code.setMaximumHeight(180)
        self.code.hide()
        root.addWidget(self.code)

        bottom = QHBoxLayout()
        show = QPushButton("Show LaTeX")
        show.setCheckable(True)
        show.toggled.connect(self.code.setVisible)
        bottom.addWidget(show)
        hint = QLabel("Click a shape to add it after the selected box · "
                      "drag to move · Ctrl/⌘-click a box to draw an arrow "
                      "to it · Delete removes")
        hint.setStyleSheet("color:#777;")
        bottom.addWidget(hint, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.insert_btn = buttons.addButton("Insert", QDialogButtonBox.AcceptRole)
        self.insert_btn.setDefault(True)
        buttons.accepted.connect(self._insert)
        buttons.rejected.connect(self.reject)
        bottom.addWidget(buttons)
        root.addLayout(bottom)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._start_preview)

        self._sync_controls()
        self._rebuild()
        QTimer.singleShot(0, self._fit)

    # ---- property pages ----
    def _hint_page(self) -> QWidget:
        w = QLabel("Select a box or an arrow to edit it.\n\n"
                   "Text may contain LaTeX maths, e.g. $x > 0$; "
                   "\\\\ starts a new line.")
        w.setWordWrap(True)
        w.setAlignment(Qt.AlignTop)
        w.setStyleSheet("color:#666; padding:6px;")
        return w

    def _node_page(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.node_text = QLineEdit()
        self.node_text.setPlaceholderText("Text (LaTeX allowed)")
        self.node_text.textEdited.connect(self._node_text_edited)
        self.node_text.editingFinished.connect(self._commit_text_edit)
        f.addRow("Text", self.node_text)
        self.node_kind = QComboBox()
        for kind, (label, _o) in F.KINDS.items():
            self.node_kind.addItem(kind_icon(kind), label, kind)
        self.node_kind.activated.connect(self._node_kind_changed)
        f.addRow("Shape", self.node_kind)
        row = QHBoxLayout()
        self.node_fill = QPushButton("Choose…")
        self.node_fill.clicked.connect(self._pick_fill)
        auto = QPushButton("Automatic")
        auto.clicked.connect(lambda: self._set_node(fill=""))
        row.addWidget(self.node_fill)
        row.addWidget(auto)
        f.addRow("Colour", row)
        return w

    def _edge_page(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.edge_label = QLineEdit()
        self.edge_label.setPlaceholderText("e.g. Yes / No")
        self.edge_label.textEdited.connect(self._edge_label_edited)
        self.edge_label.editingFinished.connect(self._commit_text_edit)
        f.addRow("Label", self.edge_label)
        self.edge_route = QComboBox()
        self.edge_route.addItem("Automatic", "auto")
        self.edge_route.addItem("Straight", "straight")
        self.edge_route.addItem("Elbow", "elbow")
        self.edge_route.activated.connect(lambda _i: self._set_edge(
            route=self.edge_route.currentData()))
        f.addRow("Route", self.edge_route)
        self.edge_dashed = QCheckBox("Dashed")
        self.edge_dashed.toggled.connect(
            lambda on: self._set_edge(dashed=on))
        f.addRow("", self.edge_dashed)
        rev = QPushButton("Reverse direction")
        rev.clicked.connect(self._reverse_edge)
        f.addRow("", rev)
        return w

    # ---- building the editor from the model ----
    def _rebuild(self) -> None:
        sel_node = self._selected_node_id()
        self.scene.blockSignals(True)
        self.scene.clear()
        self.scene.blockSignals(False)
        self.scene.edges = []
        self._items = {}
        cols = F.colours(self.fc, self.primary)
        for n in self.fc.nodes:
            fill, text = cols.get(n.kind, ("#FFFFFF", "#000000"))
            item = NodeItem(n, fill, text)
            item.moved.connect(lambda _it: self._commit(rebuild=False))
            self.scene.addItem(item)
            self._items[n.id] = item
        for e in self.fc.edges:
            a, b = self._items.get(e.src), self._items.get(e.dst)
            if a and b:
                ei = EdgeItem(e, a, b, self.fc.direction)
                self.scene.addItem(ei)
                self.scene.edges.append(ei)
        if sel_node in self._items:
            self._items[sel_node].setSelected(True)
        r = self.scene.itemsBoundingRect().adjusted(-200, -150, 200, 150)
        self.scene.setSceneRect(r)
        self._refresh_code()
        self._schedule()

    def _fit(self):
        r = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self.view.fitInView(r, Qt.KeepAspectRatio)
        if self.view.transform().m11() > 1.2:
            self.view.resetTransform()
            self.view.centerOn(r.center())

    def _sync_controls(self):
        for w, v in ((self.direction, self.direction.findData(
                self.fc.direction)), (self.scheme,
                                      self.scheme.findText(self.fc.scheme)),):
            w.blockSignals(True)
            w.setCurrentIndex(max(0, v))
            w.blockSignals(False)
        self.font_pt.blockSignals(True)
        self.font_pt.setValue(self.fc.font_pt)
        self.font_pt.blockSignals(False)

    # ---- model changes (all undoable) ----
    def _commit(self, rebuild: bool = True) -> None:
        snap = self.fc.to_json()
        if snap != self._history[self._hist_i]:
            del self._history[self._hist_i + 1:]
            self._history.append(snap)
            self._hist_i += 1
        if rebuild:
            self._rebuild()
        else:
            for e in self.scene.edges:
                e.update_path()
            self._refresh_code()
            self._schedule()

    def _change(self, fn, rebuild: bool = True) -> None:
        fn()
        self._commit(rebuild)

    def _step(self, delta: int) -> None:
        i = self._hist_i + delta
        if 0 <= i < len(self._history):
            self._hist_i = i
            self.fc = F.Flowchart.from_json(self._history[i])
            self._sync_controls()
            self._rebuild()

    def _selected_node_id(self) -> str | None:
        for it in self.scene.selectedItems():
            if isinstance(it, NodeItem):
                return it.node.id
        return None

    def _add(self, kind: str) -> None:
        after = self._selected_node_id()
        if after is None and self.fc.nodes:
            after = self.fc.nodes[-1].id
        n = self.fc.add(kind, after=after)
        self._commit()
        self.scene.clearSelection()
        self._items[n.id].setSelected(True)
        self.view.ensureVisible(self._items[n.id], 40, 40)
        self.node_text.setFocus()
        self.node_text.selectAll()

    def _connect_to(self, target: NodeItem) -> None:
        src = self._selected_node_id()
        if src is None:
            target.setSelected(True)
            return
        if self.fc.connect(src, target.node.id) is not None:
            self._commit()
            self.status.setText("Arrow added. Select it to give it a label.")

    def _delete_selected(self) -> None:
        changed = False
        for it in self.scene.selectedItems():
            if isinstance(it, NodeItem):
                self.fc.remove(it.node.id)
                changed = True
            elif isinstance(it, EdgeItem) and it.edge in self.fc.edges:
                self.fc.edges.remove(it.edge)
                changed = True
        if changed:
            self._commit()

    def _use_template(self, index: int) -> None:
        if index <= 0:
            return
        self.fc = F.TEMPLATES[self.template.itemText(index)]()
        self._sync_controls()
        self._commit()
        self.template.setCurrentIndex(0)
        QTimer.singleShot(0, self._fit)

    def _set_direction(self, _i: int) -> None:
        d = self.direction.currentData()
        if d == self.fc.direction:
            return

        def go():
            self.fc.direction = d
            for n in self.fc.nodes:          # turn the chart round
                n.x, n.y = n.y, n.x
        self._change(go)
        QTimer.singleShot(0, self._fit)

    # ---- selection / properties ----
    def _on_selection(self) -> None:
        sel = self.scene.selectedItems()
        node = next((i for i in sel if isinstance(i, NodeItem)), None)
        edge = next((i for i in sel if isinstance(i, EdgeItem)), None)
        if node is not None:
            n = node.node
            self.node_text.setText(n.text)
            self.node_kind.setCurrentIndex(self.node_kind.findData(n.kind))
            self.node_fill.setText(n.fill or "Choose…")
            self.node_fill.setStyleSheet(
                f"background:{n.fill};" if n.fill else "")
            self.props.setCurrentIndex(1)
        elif edge is not None:
            e = edge.edge
            self.edge_label.setText(e.label)
            self.edge_route.setCurrentIndex(self.edge_route.findData(e.route))
            self.edge_dashed.blockSignals(True)
            self.edge_dashed.setChecked(e.dashed)
            self.edge_dashed.blockSignals(False)
            self._selected_edge = edge
            self.props.setCurrentIndex(2)
        else:
            self.props.setCurrentIndex(0)

    def _edit_item(self, item) -> None:
        self.scene.clearSelection()
        item.setSelected(True)
        target = self.node_text if isinstance(item, NodeItem) \
            else self.edge_label
        target.setFocus()
        target.selectAll()

    def _node_text_edited(self, text: str) -> None:
        nid = self._selected_node_id()
        if nid and nid in self._items:
            self.fc.node(nid).text = text
            self._items[nid].update()
            self._refresh_code()
            self._schedule()

    def _edge_label_edited(self, text: str) -> None:
        e = self._selected_edge
        if e is not None and e.edge in self.fc.edges:
            e.edge.label = text
            e.update()
            self._refresh_code()
            self._schedule()

    def _commit_text_edit(self) -> None:
        self._commit(rebuild=False)

    def _set_node(self, **kw) -> None:
        nid = self._selected_node_id()
        if nid:
            for k, v in kw.items():
                setattr(self.fc.node(nid), k, v)
            self._commit()

    def _node_kind_changed(self, _i: int) -> None:
        self._set_node(kind=self.node_kind.currentData())

    def _pick_fill(self) -> None:
        nid = self._selected_node_id()
        if not nid:
            return
        c = QColorDialog.getColor(QColor(self.fc.node(nid).fill or "#DEEBF7"),
                                  self, "Box colour")
        if c.isValid():
            self._set_node(fill=c.name().upper())

    def _set_edge(self, **kw) -> None:
        e = self._selected_edge
        if e is not None and e.edge in self.fc.edges:
            for k, v in kw.items():
                setattr(e.edge, k, v)
            self._commit()

    def _reverse_edge(self) -> None:
        e = self._selected_edge
        if e is not None and e.edge in self.fc.edges:
            e.edge.src, e.edge.dst = e.edge.dst, e.edge.src
            self._commit()

    def _context_menu(self, item, pos) -> None:
        menu = QMenu(self)
        if isinstance(item, NodeItem):
            self.scene.clearSelection()
            item.setSelected(True)
            shapes = menu.addMenu("Change shape")
            for kind, (label, _o) in F.KINDS.items():
                shapes.addAction(kind_icon(kind), label,
                                 lambda k=kind: self._set_node(kind=k))
            menu.addAction("Edit text", lambda: self._edit_item(item))
            menu.addAction("Delete", self._delete_selected)
        elif isinstance(item, EdgeItem):
            self.scene.clearSelection()
            item.setSelected(True)
            menu.addAction("Label…", lambda: self._edit_item(item))
            menu.addAction("Reverse direction", self._reverse_edge)
            menu.addAction("Delete", self._delete_selected)
        else:
            for kind, (label, _o) in F.KINDS.items():
                menu.addAction(kind_icon(kind), f"Add {label.lower()}",
                               lambda k=kind: self._add(k))
            menu.addSeparator()
            menu.addAction("Tidy up", lambda: self._change(
                lambda: F.auto_layout(self.fc)))
        menu.exec(pos)

    # ---- preview ----
    def _tex(self) -> str:
        return F.standalone_doc(self.fc, self.primary)

    def _refresh_code(self) -> None:
        self.code.setPlainText(F.to_tikz(self.fc, self.primary))

    def _schedule(self) -> None:
        from .compiler import tectonic_available
        if tectonic_available():
            self._timer.start()
        else:
            self.status.setText("LaTeX is not available — no preview.")

    def _start_preview(self) -> None:
        if self._worker is not None:
            self._pending = True
            return
        if not self.fc.nodes:
            self.preview.clear()
            return
        self.status.setText("Updating the preview…")
        self._worker = _PreviewWorker(self._tex())
        self._worker.done.connect(self._on_preview)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    def _on_preview(self, data, log, tex) -> None:
        if data is None:
            errs = [ln for ln in log.splitlines() if ln.startswith("!")]
            self.status.setText("The chart could not be compiled: "
                                + (errs[0] if errs else "see the LaTeX."))
            return
        self._last_pdf = (tex, data)
        pm = _pdf_to_pixmap(data, max(300, self.preview.width() * 2))
        if pm is not None:
            pm.setDevicePixelRatio(2)
            target = self.preview.size() * 2
            pm = pm.scaled(target, Qt.KeepAspectRatio,
                           Qt.SmoothTransformation)
            pm.setDevicePixelRatio(2)
            self.preview.setPixmap(pm)
        if self._last_pdf[0] == self._tex():
            self.status.setText("")

    def _on_worker_done(self) -> None:
        w, self._worker = self._worker, None
        if w is not None:
            w.deleteLater()
        if self._pending:
            self._pending = False
            self._start_preview()

    # ---- insert ----
    def _insert(self) -> None:
        if not self.fc.nodes:
            self.reject()
            return
        tex = self._tex()
        if self._last_pdf is None or self._last_pdf[0] != tex:
            # The preview is behind: compile now (keeping the UI alive).
            import threading
            from PySide6.QtWidgets import QApplication
            from .compiler import compile_tex
            box: dict = {}
            t = threading.Thread(target=lambda: box.update(
                r=compile_tex(tex, Path(tempfile.gettempdir())
                              / "kherveslide_flowfinal", "flow")),
                daemon=True)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                t.start()
                while t.is_alive():
                    QApplication.processEvents()
                    t.join(0.03)
            finally:
                QApplication.restoreOverrideCursor()
            r = box.get("r")
            if r is None or not (r.ok and r.pdf_path):
                QMessageBox.warning(self, "Flowchart",
                                    "The chart could not be compiled.")
                return
            self._last_pdf = (tex, Path(r.pdf_path).read_bytes())
        self.result_chart = self.fc
        self.result_pdf = self._last_pdf[1]
        self.result_tikz = F.to_tikz(self.fc, self.primary)
        self.accept()

    def done(self, r):
        self._timer.stop()
        if self._worker is not None:
            self._worker.wait(4000)
        super().done(r)
