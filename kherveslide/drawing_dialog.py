"""Vector drawing dialog (Insert > Drawing).

A KhervePaint-style editor built on the ported engine in `kherveslide.paint`:
tool palette on the left, stroke/fill/text options on top, a properties
panel on the right and the canvas in the middle.

On OK the drawing is written as three siblings in the document's images
folder: ``drawing_NNN.svg`` (editable source, re-opened on double-click),
``drawing_NNN.pdf`` (vector, cropped to the content, what LaTeX includes)
and ``drawing_NNN.png`` (preview shown in the visual editor, and the path
the Figure node stores). Drawings made by the old dialog (PNG + JSON
sidecar) are converted on re-open.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QMimeData, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QKeySequence,
                           QPainterPath, QPen, QPixmap, QUndoCommand,
                           QUndoStack)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFontComboBox,
    QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMenu, QScrollArea, QSpinBox, QToolButton,
    QVBoxLayout, QWidget,
)

from . import icons
from .paint import canvas as C
from .paint import document, export, gradient
from .paint.canvas import (ArcShapeItem, ArrowItem, DimensionItem,
                           EllipseItem, GroupItem, ImageItem, LineItem,
                           PaintScene, PaintView, PathItem, PolygonItem,
                           RectItem, RoundedRectItem, TextItem)

MIME_ITEMS = "application/x-kherveslide-drawing-items"

_PALETTE = ["#000000", "#ffffff", "#7a7a7a", "#1a6dd8", "#d8000c",
            "#0a8f3c", "#d96b00", "#8e44ad", "#f2c500", "#17a2b8"]
LINE_WIDTHS = [0.5, 1, 1.5, 2, 3, 4, 6, 8, 12]
DASHES = [("solid", "Solid"), ("dash", "Dashed"), ("dot", "Dotted"),
          ("dashdot", "Dash-dot")]
HEADS = [("filled", "Filled"), ("open", "Open"), ("stealth", "Stealth"),
         ("double", "Double-ended")]
FILL_STYLES = [("solid", "Solid"), ("linear", "Linear gradient"),
               ("radial", "Radial gradient"), ("sun", "Sphere highlight")]

#: Single-button tools: (tool id, icon name, label, shortcut).
DIRECT_TOOLS = [
    (C.POINTER, "pointer", "Select / move / resize (double-click: rotate)", "V"),
    (C.PENCIL, "pencil", "Pencil (freehand)", "P"),
    (C.ERASER, "eraser", "Eraser (removes shapes)", "X"),
    (C.BUCKET, "bucket", "Bucket fill", "B"),
    (C.PICKER, "picker", "Colour picker (Shift+click: fill colour)", "K"),
    (C.TEXT, "text", "Text", "T"),
    (C.LINE, "line", "Line", "L"),
    (C.ARROW, "arrow", "Arrow", "A"),
    (C.DIMENSION, "dimension", "Dimension line (length in mm)", "M"),
    (C.PROTRACTOR, "protractor", "Protractor (three clicks)", None),
    (C.RECT, "rect", "Rectangle", "R"),
    (C.ROUNDRECT, "roundrect", "Rounded rectangle", None),
    (C.CIRCLE, "circle", "Circle", "C"),
    (C.ELLIPSE, "ellipse", "Ellipse", "E"),
    (C.HALFCIRCLE, "halfcircle", "Half circle", None),
    (C.QUARTERCIRCLE, "quartercircle", "Quarter circle", None),
]

#: Dropdown shape groups: (icon of the button, tooltip, [(tool, label)]).
SHAPE_GROUPS = [
    ("Polygons", [(C.TRIANGLE, "Triangle"),
                  (C.RIGHT_TRIANGLE, "Right triangle"),
                  (C.DIAMOND, "Diamond"), (C.PARALLELOGRAM, "Parallelogram"),
                  (C.TRAPEZOID, "Trapezoid"), (C.PENTAGON, "Pentagon"),
                  (C.HEXAGON, "Hexagon"), (C.HEPTAGON, "Heptagon"),
                  (C.OCTAGON, "Octagon")]),
    ("Stars & symbols", [(C.STAR, "Star (5-point)"), (C.STAR6, "Star (6-point)"),
                         (C.PLUS, "Cross / plus"), (C.CHEVRON, "Chevron"),
                         (C.ARROW_RIGHT, "Block arrow"),
                         (C.LIGHTNING, "Lightning bolt"), (C.HOUSE, "House")]),
]

#: Lazily-imported symbol libraries: (icon, tooltip, module name,
#: scene attribute holding the chosen element, placement tool).
SYMBOL_LIBRARIES = [
    ("flowchart", "Flowchart symbols", "flowchart", "flow_element",
     C.FLOW_PLACE),
    ("electrical", "Electrical / circuit symbols", "electrical",
     "elec_element", C.ELEC_PLACE),
    ("optics", "Optics (lasers, lenses, mirrors)", "optics",
     "optics_element", C.OPTICS_PLACE),
    ("maths", "Maths (axes, graphs, vectors)", "maths", "math_element",
     C.MATH_PLACE),
    ("labware", "Lab glassware", "labware", "labware_element",
     C.LABWARE_PLACE),
    ("arrows", "Annotation arrows & callouts", "arrows", "arrow_element",
     C.ARROW_PLACE),
]

CHEM_BONDS = [(C.CHEM_SINGLE, "Single bond"), (C.CHEM_CHAIN, "Chain"),
              (C.CHEM_DOUBLE, "Double bond"), (C.CHEM_TRIPLE, "Triple bond"),
              (C.CHEM_WEDGE, "Wedge (up)"), (C.CHEM_HASH, "Hash (down)"),
              (C.CHEM_HBOND, "Hydrogen bond")]
CHEM_RINGS = [(C.CHEM_BENZENE, "Benzene"), (C.CHEM_CYCLOHEXANE, "Cyclohexane"),
              (C.CHEM_CYCLOPENTANE, "Cyclopentane")]

_TYPE_NAMES = [(DimensionItem, "Dimension"), (ArrowItem, "Arrow"),
               (LineItem, "Line"), (RoundedRectItem, "Rounded rectangle"),
               (RectItem, "Rectangle"), (EllipseItem, "Ellipse"),
               (PolygonItem, "Polygon"), (ArcShapeItem, "Arc"),
               (PathItem, "Path"), (ImageItem, "Image"), (GroupItem, "Group"),
               (TextItem, "Text")]


def _type_name(item) -> str:
    for cls, name in _TYPE_NAMES:
        if isinstance(item, cls):
            return name
    return type(item).__name__


def _leaves(items):
    """Selected items with groups expanded into their members."""
    out = []
    for it in items:
        if isinstance(it, GroupItem):
            out.extend(_leaves(it.childItems()))
        else:
            out.append(it)
    return out


class _SnapshotCommand(QUndoCommand):
    """Swap the whole drawing between two serialised snapshots. The change
    is already on screen when pushed, so the first redo() is a no-op."""

    def __init__(self, dialog, before: dict, after: dict):
        super().__init__("Edit")
        self._dialog, self._before, self._after = dialog, before, after
        self._first = True

    def redo(self):
        if self._first:
            self._first = False
            return
        self._dialog._restore_snapshot(self._after)

    def undo(self):
        self._dialog._restore_snapshot(self._before)


# ---------------------------------------------------------------- legacy

def load_legacy_json(scene: PaintScene, data: dict) -> int:
    """Rebuild a drawing saved by the old dialog (PNG + JSON sidecar) as
    editable items. Returns the number of items created."""
    count = 0
    for d in data.get("items", []):
        pen = QPen(QColor(d.get("color", "#000000")), float(d.get("width", 2)))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        t = d.get("type", "")
        item = None
        if t == "text":
            item = TextItem(d.get("text", ""))
            f = QFont(C.DEFAULT_FONT_FAMILY)
            f.setPointSize(int(d.get("font_size", 14)))
            item.setFont(f)
            item.setDefaultTextColor(QColor(d.get("color", "#000000")))
            item.setPos(d.get("x", 0), d.get("y", 0))
        elif t == "line":
            from PySide6.QtCore import QLineF
            item = LineItem(QLineF(d.get("x1", 0), d.get("y1", 0),
                                   d.get("x2", 0), d.get("y2", 0)))
            item.setPen(pen)
        elif t in ("rect", "ellipse"):
            rect = QRectF(d.get("x", 0), d.get("y", 0), d.get("w", 0),
                          d.get("h", 0))
            item = RectItem(rect) if t == "rect" else EllipseItem(rect)
            item.setPen(pen)
            item.setBrush(QBrush(Qt.NoBrush))
        elif t in ("path", "arrow"):
            els = d.get("elements", [])
            if t == "arrow" and len(els) >= 2:
                from PySide6.QtCore import QLineF
                item = ArrowItem(QLineF(els[0]["x"], els[0]["y"],
                                        els[1]["x"], els[1]["y"]))
                item.set_head("open")
            else:
                path = QPainterPath()
                for el in els:
                    if el.get("t") == "M":
                        path.moveTo(el["x"], el["y"])
                    else:
                        path.lineTo(el["x"], el["y"])
                item = PathItem(path)
                item.setBrush(QBrush(Qt.NoBrush))
            item.setPen(pen)
        if item is not None:
            scene.addItem(item)
            count += 1
    return count


def drawing_source_for(png_path: Path) -> Path | None:
    """The editable source of a drawing preview: the SVG, else a legacy
    JSON sidecar, else None (not a drawing)."""
    png_path = Path(png_path)
    for ext in (".svg", ".json"):
        cand = png_path.with_suffix(ext)
        if cand.exists():
            return cand
    return None


def next_drawing_path(images_dir: Path) -> Path:
    """First free ``drawing_NNN.png`` in *images_dir* (no sibling of any
    drawing extension may exist either)."""
    i = 1
    while True:
        stem = Path(images_dir) / f"drawing_{i:03d}"
        if not any(stem.with_suffix(e).exists()
                   for e in (".png", ".svg", ".pdf", ".json")):
            return stem.with_suffix(".png")
        i += 1


# ---------------------------------------------------------------- widgets

class _ColorButton(QToolButton):
    """Colour chip that opens a colour dialog (with alpha)."""

    colorChanged = Signal(QColor)

    def __init__(self, color: QColor, tip: str, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setToolTip(tip)
        self.setAutoRaise(True)
        self.setIconSize(QSize(20, 20))
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor, emit=False):
        self._color = QColor(color)
        self._refresh()
        if emit:
            self.colorChanged.emit(QColor(color))

    def _refresh(self):
        self.setIcon(icons.color_swatch(self._color.name(), 20))

    def _pick(self):
        c = QColorDialog.getColor(self._color, self, self.toolTip(),
                                  QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self.set_color(c, emit=True)


class DrawingDialog(QDialog):
    """Modal drawing editor. `saved_path()` returns the PNG preview path
    after OK (siblings .svg and .pdf are written next to it)."""

    drawingSaved = Signal(str)   # absolute path to the saved PNG

    def __init__(self, images_dir: Path, parent: QWidget | None = None,
                 existing_path: Path | None = None):
        super().__init__(parent)
        self._images_dir = Path(images_dir)
        self._images_dir.mkdir(parents=True, exist_ok=True)
        self._saved_path: Path | None = None
        self._existing_path = Path(existing_path) if existing_path else None
        self._restoring = False
        self._syncing = False

        self.setWindowTitle("Edit Drawing" if self._existing_path
                            else "Drawing")
        self.resize(1280, 820)
        self.setSizeGripEnabled(True)

        self.scene = PaintScene(900, 600, self)
        self.scene.grid_mm = 5.0
        self.scene.show_grid = True
        self.scene.snap_enabled = False
        self.scene.infinite = True
        # Symbols keep one size whatever the page is cropped to.
        self.scene.symbol_page_px = 900
        self.scene.symbol_min_px = 90
        self.view = PaintView(self.scene, self)
        self.view.apply_scroll_bounds()
        self.view.setMinimumSize(420, 320)

        self._undo = QUndoStack(self)
        self._undo.setUndoLimit(100)

        self._tool_buttons: dict[str, QToolButton] = {}
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)

        palette = self._build_palette()
        optbar = self._build_options_bar()
        props = self._build_properties_panel()

        self._status = QLabel("")
        self._status.setStyleSheet("color: palette(mid);")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_and_save)
        buttons.rejected.connect(self.reject)
        #: Set when the user closed the dialog via "Open in KhervePaint";
        #: the editor then launches it on the saved drawing.
        self.handoff_to_khervepaint = False
        kp = buttons.addButton("Open in KhervePaint…",
                               QDialogButtonBox.ActionRole)
        kp.setToolTip("Save this drawing and continue editing it in the "
                      "full KhervePaint app. Its saves update the figure.")
        kp.clicked.connect(self._open_in_khervepaint)
        for b in buttons.buttons():
            b.setAutoDefault(False)
            b.setDefault(False)

        middle = QHBoxLayout()
        middle.setSpacing(6)
        middle.addWidget(palette)
        middle.addWidget(self.view, 1)
        middle.addWidget(props)

        bottom = QHBoxLayout()
        bottom.addWidget(self._status, 1)
        bottom.addWidget(buttons)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)
        outer.addWidget(optbar)
        outer.addLayout(middle, 1)
        outer.addLayout(bottom)

        self._build_shortcuts()

        self.scene.changed_by_user.connect(self._capture_change)
        self.scene.selectionChanged.connect(self._sync_properties)
        self.scene.changed_by_user.connect(self._sync_properties)
        self.scene.color_picked.connect(self._on_color_picked)
        self.view.cursor_moved.connect(self._on_cursor)
        self.view.item_context.connect(self._item_menu)

        if self._existing_path is not None:
            self._load_existing(self._existing_path)
        else:
            self.view.centerOn(self.scene.sceneRect().center())
        self._reset_history()
        self.set_tool(C.PENCIL if self._existing_path is None else C.POINTER)
        self._sync_properties()

    # ------------------------------------------------------------ public
    def saved_path(self) -> Path | None:
        return self._saved_path

    def set_tool(self, tool: str) -> None:
        self.scene.end_chain()
        self.scene.end_angle()
        self.scene.tool = tool
        self.view.set_tool_cursor(tool)
        if tool != C.POINTER:
            self.scene.clear_handles()
        btn = self._tool_buttons.get(tool)
        if btn is None:
            btn = self._tool_buttons.get(self._group_of.get(tool, ""))
        if btn is not None:
            btn.setChecked(True)
        self._arrow_row_visible()

    # ------------------------------------------------------------ palette
    def _tool_button(self, icon_name, tip, shortcut=None) -> QToolButton:
        b = QToolButton()
        b.setIcon(icons.paint_tool(icon_name))
        b.setIconSize(QSize(24, 24))
        b.setFixedSize(38, 38)
        b.setCheckable(True)
        b.setAutoRaise(True)
        b.setToolTip(f"{tip} ({shortcut})" if shortcut else tip)
        return b

    def _build_palette(self) -> QWidget:
        box = QFrame()
        box.setObjectName("drawPalette")
        box.setStyleSheet(
            "#drawPalette { background: palette(base); border: 1px solid "
            "palette(mid); border-radius: 6px; }"
            "#drawPalette QToolButton:checked { background: #d6e6fb; "
            "border: 1px solid #1a6dd8; border-radius: 4px; }"
            "#drawPalette QLabel { color: palette(mid); font-size: 10px; }")
        grid = QGridLayout(box)
        grid.setContentsMargins(4, 6, 4, 6)
        grid.setSpacing(2)
        self._group_of: dict[str, str] = {}
        row = col = 0

        def put(widget):
            nonlocal row, col
            grid.addWidget(widget, row, col)
            col += 1
            if col == 2:
                row, col = row + 1, 0

        def section(title):
            nonlocal row, col
            if col:
                row, col = row + 1, 0
            lab = QLabel(title)
            lab.setAlignment(Qt.AlignCenter)
            grid.addWidget(lab, row, 0, 1, 2)
            row += 1

        for i, (tool, icon_name, label, sc) in enumerate(DIRECT_TOOLS):
            if i == 0:
                section("Tools")
            if tool == C.LINE:
                section("Lines")
            if tool == C.RECT:
                section("Shapes")
            b = self._tool_button(icon_name, label, sc)
            b.clicked.connect(lambda _=False, t=tool: self.set_tool(t))
            self._tool_group.addButton(b)
            self._tool_buttons[tool] = b
            put(b)

        for title, items in SHAPE_GROUPS:
            b = self._tool_button(items[0][0], title)
            b.setPopupMode(QToolButton.InstantPopup)
            menu = QMenu(b)
            for tool, label in items:
                act = menu.addAction(icons.paint_tool(tool), label)
                act.triggered.connect(
                    lambda _=False, t=tool, btn=b: self._pick_grouped(btn, t))
                self._group_of[tool] = title
            b.setMenu(menu)
            self._tool_group.addButton(b)
            self._tool_buttons[title] = b
            put(b)

        section("Symbols")
        chem = self._tool_button("chemistry", "Chemistry: bonds, rings, atoms")
        chem.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(chem)
        menu.addSection("Bonds")
        for tool, label in CHEM_BONDS:
            menu.addAction(label, lambda t=tool, b=chem: self._pick_grouped(b, t))
            self._group_of[tool] = "chemistry"
        menu.addSection("Rings")
        for tool, label in CHEM_RINGS:
            menu.addAction(label, lambda t=tool, b=chem: self._pick_grouped(b, t))
            self._group_of[tool] = "chemistry"
        atoms = menu.addMenu("Atom / group label")
        from .paint import chemistry
        for sym in chemistry.ATOMS:
            atoms.addAction(sym, lambda s=sym, b=chem: self._pick_atom(b, s))
        self._group_of[C.CHEM_ATOM] = "chemistry"
        chem.setMenu(menu)
        self._tool_group.addButton(chem)
        self._tool_buttons["chemistry"] = chem
        put(chem)

        for icon_name, tip, module, attr, tool in SYMBOL_LIBRARIES:
            b = self._tool_button(icon_name, tip)
            b.setPopupMode(QToolButton.InstantPopup)
            menu = QMenu(b)
            # Filled on first open: the libraries are only imported when
            # the user actually looks at them.
            menu.aboutToShow.connect(
                lambda m=menu, mod=module, a=attr, t=tool, btn=b:
                self._fill_library_menu(m, mod, a, t, btn))
            b.setMenu(menu)
            self._group_of[tool] = icon_name
            self._tool_group.addButton(b)
            self._tool_buttons[icon_name] = b
            put(b)

        section("Insert")
        img = self._tool_button("image", "Insert image…")
        img.setCheckable(False)
        img.clicked.connect(self._insert_image)
        put(img)

        grid.setRowStretch(row + 1, 1)
        box.setFixedWidth(88)
        scroll = QScrollArea()
        scroll.setWidget(box)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(100)
        return scroll

    def _pick_grouped(self, button: QToolButton, tool: str):
        if tool in C.POLYGON_KINDS or tool in C.ARC_KINDS:
            button.setIcon(icons.paint_tool(tool))
        self.set_tool(tool)
        button.setChecked(True)

    def _pick_atom(self, button, symbol):
        self.scene.chem_atom = symbol
        self._pick_grouped(button, C.CHEM_ATOM)

    def _fill_library_menu(self, menu: QMenu, module: str, attr: str,
                           tool: str, button: QToolButton):
        if menu.actions():
            return
        import importlib
        mod = importlib.import_module(f".paint.{module}", __package__)
        labels = getattr(mod, "LABELS", {})
        for cat, names in getattr(mod, "CATEGORIES", [("", list(mod.SIZES))]):
            if cat:
                menu.addSection(cat)
            for name in names:
                menu.addAction(labels.get(name, name.replace("_", " ")),
                               lambda n=name: self._pick_symbol(
                                   attr, n, tool, button))

    def _pick_symbol(self, attr, name, tool, button):
        setattr(self.scene, attr, name)
        self._pick_grouped(button, tool)
        self._status.setText("Click on the canvas to place the symbol.")

    # ------------------------------------------------------------ options
    def _build_options_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("drawOptions")
        bar.setStyleSheet("#drawOptions { background: palette(base); border: "
                          "1px solid palette(mid); border-radius: 6px; }")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(4)

        def tb(icon, tip, slot):
            b = QToolButton()
            b.setIcon(icon)
            b.setIconSize(QSize(20, 20))
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            lay.addWidget(b)
            return b

        def sep():
            line = QFrame()
            line.setFrameShape(QFrame.VLine)
            line.setFrameShadow(QFrame.Sunken)
            lay.addWidget(line)

        self._undo_btn = tb(icons.undo(), "Undo (Ctrl+Z)", self._undo.undo)
        self._redo_btn = tb(icons.redo(), "Redo (Ctrl+Shift+Z)", self._undo.redo)
        self._undo.canUndoChanged.connect(self._undo_btn.setEnabled)
        self._undo.canRedoChanged.connect(self._redo_btn.setEnabled)
        self._undo_btn.setEnabled(False)
        self._redo_btn.setEnabled(False)
        sep()

        lay.addWidget(QLabel("Stroke"))
        self._stroke_btn = _ColorButton(self.scene.pen.color(), "Stroke colour")
        self._stroke_btn.colorChanged.connect(self._set_stroke_color)
        lay.addWidget(self._stroke_btn)

        self._width_combo = QComboBox()
        self._width_combo.setToolTip("Line width (px)")
        self._width_combo.setIconSize(QSize(44, 16))
        for w in LINE_WIDTHS:
            self._width_combo.addItem(icons.pen_preview(w), f"{w:g}", w)
        self._width_combo.setCurrentIndex(LINE_WIDTHS.index(2))
        self._width_combo.currentIndexChanged.connect(self._set_width)
        lay.addWidget(self._width_combo)

        self._dash_combo = QComboBox()
        self._dash_combo.setToolTip("Line style")
        self._dash_combo.setIconSize(QSize(44, 16))
        for key, label in DASHES:
            self._dash_combo.addItem(icons.pen_preview(2, key), "", key)
            self._dash_combo.setItemData(self._dash_combo.count() - 1,
                                         label, Qt.ToolTipRole)
        self._dash_combo.currentIndexChanged.connect(self._set_dash)
        lay.addWidget(self._dash_combo)

        self._head_combo = QComboBox()
        self._head_combo.setToolTip("Arrowhead")
        self._head_combo.setIconSize(QSize(44, 16))
        for key, label in HEADS:
            self._head_combo.addItem(icons.pen_preview(2, "solid", key), "", key)
            self._head_combo.setItemData(self._head_combo.count() - 1,
                                         label, Qt.ToolTipRole)
        self._head_combo.currentIndexChanged.connect(self._set_head)
        lay.addWidget(self._head_combo)
        sep()

        self._fill_check = QCheckBox("Fill")
        self._fill_check.setToolTip("Fill new shapes")
        self._fill_check.toggled.connect(self._set_fill_enabled)
        lay.addWidget(self._fill_check)
        self._fill_btn = _ColorButton(self.scene.fill_color, "Fill colour")
        self._fill_btn.colorChanged.connect(self._set_fill_color)
        lay.addWidget(self._fill_btn)
        self._fill_style = QComboBox()
        self._fill_style.setToolTip("Fill style")
        for key, label in FILL_STYLES:
            self._fill_style.addItem(label, key)
        self._fill_style.currentIndexChanged.connect(self._set_fill_style)
        lay.addWidget(self._fill_style)
        self._fill2_btn = _ColorButton(self.scene.fill_color2,
                                       "Gradient end colour")
        self._fill2_btn.colorChanged.connect(self._set_fill_color2)
        lay.addWidget(self._fill2_btn)
        self._fill2_btn.setEnabled(False)
        sep()

        self._font_combo = QFontComboBox()
        self._font_combo.setToolTip("Text font")
        self._font_combo.setCurrentFont(self.scene.text_font)
        self._font_combo.setMaximumWidth(150)
        self._font_combo.currentFontChanged.connect(self._set_font)
        lay.addWidget(self._font_combo)
        self._font_size = QSpinBox()
        self._font_size.setRange(4, 144)
        self._font_size.setValue(self.scene.text_font.pointSize())
        self._font_size.setSuffix(" pt")
        self._font_size.setToolTip("Text size")
        self._font_size.valueChanged.connect(self._set_font)
        lay.addWidget(self._font_size)
        self._bold_btn = QToolButton()
        self._bold_btn.setIcon(icons.bold())
        self._bold_btn.setCheckable(True)
        self._bold_btn.setAutoRaise(True)
        self._bold_btn.setToolTip("Bold text")
        self._bold_btn.toggled.connect(self._set_font)
        lay.addWidget(self._bold_btn)
        self._italic_btn = QToolButton()
        self._italic_btn.setIcon(icons.italic())
        self._italic_btn.setCheckable(True)
        self._italic_btn.setAutoRaise(True)
        self._italic_btn.setToolTip("Italic text")
        self._italic_btn.toggled.connect(self._set_font)
        lay.addWidget(self._italic_btn)
        sep()

        for hexc in _PALETTE:
            b = QToolButton()
            b.setAutoRaise(True)
            b.setIcon(icons.color_swatch(hexc, 16))
            b.setIconSize(QSize(16, 16))
            b.setToolTip(f"{hexc} — click: stroke, right-click: fill")
            b.clicked.connect(lambda _=False, c=hexc: self._palette_stroke(c))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(
                lambda _p, c=hexc: self._palette_fill(c))
            lay.addWidget(b)
        lay.addStretch(1)

        tb(icons.zoom_out(),
           "Zoom out", lambda: self.view.zoom(1 / 1.25))
        self._zoom_label = QToolButton()
        self._zoom_label.setAutoRaise(True)
        self._zoom_label.setToolTip("Reset zoom to 100%")
        self._zoom_label.setMinimumWidth(48)
        self._zoom_label.setText("100%")
        self._zoom_label.clicked.connect(self.view.zoom_reset)
        lay.addWidget(self._zoom_label)
        tb(icons.zoom_in(),
           "Zoom in", lambda: self.view.zoom(1.25))
        tb(icons.paint_tool("fit"), "Zoom to drawing", self._zoom_to_content)
        self.view.zoom_changed.connect(
            lambda z: self._zoom_label.setText(f"{round(z * 100)}%"))
        return bar

    def _arrow_row_visible(self):
        self._head_combo.setEnabled(
            self.scene.tool == C.ARROW
            or any(isinstance(i, ArrowItem)
                   for i in _leaves(self.scene.selectedItems())))

    # ------------------------------------------------------------ properties
    def _build_properties_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        sel = QGroupBox("Selection")
        form = QFormLayout(sel)
        form.setContentsMargins(8, 6, 8, 8)
        form.setSpacing(5)
        self._p_type = QLabel("—")
        form.addRow("Type", self._p_type)

        def spin(lo, hi, suffix="", dec=1, step=1.0):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(dec)
            s.setSingleStep(step)
            s.setSuffix(suffix)
            s.setKeyboardTracking(False)
            return s

        self._p_x = spin(-99999, 99999, " px")
        self._p_y = spin(-99999, 99999, " px")
        self._p_x.valueChanged.connect(self._apply_position)
        self._p_y.valueChanged.connect(self._apply_position)
        form.addRow("X", self._p_x)
        form.addRow("Y", self._p_y)
        self._p_size = QLabel("")
        form.addRow("Size", self._p_size)
        self._p_rot = spin(-360, 360, "°", 1, 5)
        self._p_rot.valueChanged.connect(self._apply_rotation)
        form.addRow("Rotation", self._p_rot)
        self._p_opacity = QSpinBox()
        self._p_opacity.setRange(0, 100)
        self._p_opacity.setSuffix(" %")
        self._p_opacity.setKeyboardTracking(False)
        self._p_opacity.valueChanged.connect(self._apply_opacity)
        form.addRow("Opacity", self._p_opacity)
        self._p_label = QLineEdit()
        self._p_label.setPlaceholderText("Text inside the shape")
        self._p_label.editingFinished.connect(self._apply_label)
        form.addRow("Label", self._p_label)
        lay.addWidget(sel)

        arr = QGroupBox("Arrange")
        g = QGridLayout(arr)
        g.setContentsMargins(6, 6, 6, 6)
        g.setSpacing(2)
        actions = [
            ("front", "Bring to front (Ctrl+Shift+])", lambda: self._reorder("front")),
            ("forward", "Bring forward (Ctrl+])", lambda: self._reorder("forward")),
            ("backward", "Send backward (Ctrl+[)", lambda: self._reorder("backward")),
            ("back", "Send to back (Ctrl+Shift+[)", lambda: self._reorder("back")),
            ("group", "Group (Ctrl+G)", self.scene.group_selection),
            ("ungroup", "Ungroup (Ctrl+Shift+G)", self.scene.ungroup_selection),
            ("flip_h", "Flip horizontal", lambda: self.scene.mirror_selection(True)),
            ("flip_v", "Flip vertical", lambda: self.scene.mirror_selection(False)),
            ("rotate", "Rotate (drag the round handle)", self._rotate_mode),
            ("explode", "Break shape into its edges", self.scene.explode_selection),
            ("duplicate", "Duplicate (Ctrl+D)", self.duplicate_selection),
            ("delete", "Delete (Del)", self.delete_selection),
        ]
        self._arrange_buttons = []
        for i, (name, tip, slot) in enumerate(actions):
            b = QToolButton()
            b.setIcon(icons.paint_tool(name))
            b.setIconSize(QSize(22, 22))
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            g.addWidget(b, i // 4, i % 4)
            self._arrange_buttons.append(b)
        lay.addWidget(arr)

        cv = QGroupBox("Canvas")
        cf = QFormLayout(cv)
        cf.setContentsMargins(8, 6, 8, 8)
        cf.setSpacing(5)
        self._grid_check = QCheckBox("Show grid")
        self._grid_check.setChecked(self.scene.show_grid)
        self._grid_check.toggled.connect(self._set_show_grid)
        cf.addRow(self._grid_check)
        self._snap_check = QCheckBox("Snap to grid")
        self._snap_check.setChecked(self.scene.snap_enabled)
        self._snap_check.toggled.connect(self._set_snap)
        cf.addRow(self._snap_check)
        self._grid_mm = spin(0.5, 50, " mm", 1, 0.5)
        self._grid_mm.setValue(self.scene.grid_mm)
        self._grid_mm.valueChanged.connect(self._set_grid_mm)
        cf.addRow("Grid", self._grid_mm)
        self._rulers_check = QCheckBox("Rulers")
        self._rulers_check.toggled.connect(self.view.set_rulers_visible)
        cf.addRow(self._rulers_check)
        self._cw = QSpinBox(); self._cw.setRange(50, 20000)
        self._ch = QSpinBox(); self._ch.setRange(50, 20000)
        self._cw.setSuffix(" px"); self._ch.setSuffix(" px")
        self._cw.setKeyboardTracking(False); self._ch.setKeyboardTracking(False)
        self._cw.valueChanged.connect(self._resize_canvas)
        self._ch.valueChanged.connect(self._resize_canvas)
        cf.addRow("Width", self._cw)
        cf.addRow("Height", self._ch)
        fit = QToolButton()
        fit.setText("Crop page to drawing")
        fit.setIcon(icons.paint_tool("fit"))
        fit.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        fit.setToolTip("Shrink the page to the drawing's bounding box. The "
                       "exported figure is always cropped to the content.")
        fit.clicked.connect(lambda: self.scene.fit_to_content(margin=10))
        cf.addRow(fit)
        lay.addWidget(cv)

        hint = QLabel("Double-click a shape to rotate it, a text to edit "
                      "it. Right-click for more. Shift/Ctrl+click adds to "
                      "the selection.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid); font-size: 11px;")
        lay.addWidget(hint)
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(236)
        return scroll

    def _sync_properties(self, *_):
        if self._syncing or self._restoring:
            return
        try:
            items = self._selected_top_items()
        except RuntimeError:
            return
        self._syncing = True
        try:
            single = items[0] if len(items) == 1 else None
            for w in (self._p_x, self._p_y, self._p_rot, self._p_opacity):
                w.setEnabled(single is not None)
            for b in self._arrange_buttons:
                b.setEnabled(bool(items))
            if not items:
                self._p_type.setText("—")
                self._p_size.setText("")
                self._p_label.setEnabled(False)
                self._p_label.setText("")
            elif single is None:
                self._p_type.setText(f"{len(items)} items")
                r = QRectF()
                for it in items:
                    r = r.united(it.sceneBoundingRect())
                self._p_size.setText(self._mm_text(r.width(), r.height()))
                self._p_label.setEnabled(False)
            else:
                self._p_type.setText(_type_name(single))
                br = single.sceneBoundingRect()
                self._p_x.setValue(br.x())
                self._p_y.setValue(br.y())
                if isinstance(single, LineItem):
                    k = 25.4 / max(self.scene.dpi, 1)
                    self._p_size.setText(
                        f"length {single.line().length() * k:.1f} mm")
                else:
                    self._p_size.setText(self._mm_text(br.width(), br.height()))
                self._p_rot.setValue(single.rotation())
                self._p_opacity.setValue(round(single.opacity() * 100))
                has_label = hasattr(single, "set_label")
                self._p_label.setEnabled(has_label)
                self._p_label.setText(getattr(single, "_label", "") or ""
                                      if has_label else "")
            self._pull_style_from(single)
            self._arrow_row_visible()
            r = self.scene.sceneRect()
            self._cw.setValue(int(r.width()))
            self._ch.setValue(int(r.height()))
        finally:
            self._syncing = False

    def _mm_text(self, w, h) -> str:
        k = 25.4 / max(self.scene.dpi, 1)
        return f"{w * k:.1f} × {h * k:.1f} mm"

    def _pull_style_from(self, item):
        """Mirror a single selected item's style in the option bar, so the
        controls show what the item looks like."""
        if item is None or isinstance(item, (GroupItem, ImageItem)):
            return
        if isinstance(item, TextItem):
            self._stroke_btn.set_color(item.defaultTextColor())
            f = item.font()
            self._font_combo.setCurrentFont(f)
            self._font_size.setValue(max(4, f.pointSize()))
            self._bold_btn.setChecked(f.bold())
            self._italic_btn.setChecked(f.italic())
            return
        if not hasattr(item, "pen"):
            return
        pen = item.pen()
        if pen.style() != Qt.NoPen:
            self._stroke_btn.set_color(pen.color())
            w = pen.widthF()
            idx = min(range(len(LINE_WIDTHS)),
                      key=lambda i: abs(LINE_WIDTHS[i] - w))
            self._width_combo.setCurrentIndex(idx)
            dash = document.dash_name(pen)
            self._dash_combo.setCurrentIndex(
                [k for k, _ in DASHES].index(dash))
        if isinstance(item, ArrowItem):
            self._head_combo.setCurrentIndex(
                [k for k, _ in HEADS].index(item.head))
        if hasattr(item, "brush") and not isinstance(item, LineItem):
            brush = item.brush()
            self._fill_check.setChecked(brush.style() != Qt.NoBrush)
            spec = gradient.brush_spec(brush)
            if spec is not None:
                self._fill_btn.set_color(QColor(spec["c1"]))
                self._fill2_btn.set_color(QColor(spec["c2"]))
                self._fill_style.setCurrentIndex(
                    [k for k, _ in FILL_STYLES].index(spec.get("kind", "linear")))
            elif brush.style() != Qt.NoBrush:
                self._fill_btn.set_color(brush.color())
                self._fill_style.setCurrentIndex(0)

    # ------------------------------------------------------------ style
    def _style_selection(self, fn) -> None:
        """Apply *fn* to every selected leaf item (groups expanded) and
        record one undo step."""
        if self._syncing:
            return
        items = _leaves(self._selected_top_items())
        if not items:
            return
        for it in items:
            fn(it)
            it.update()
        self.scene.changed_by_user.emit()

    @staticmethod
    def _with_pen(item, change):
        if not hasattr(item, "setPen") or isinstance(item, ImageItem):
            return
        pen = QPen(item.pen())
        if pen.style() == Qt.NoPen:
            return
        change(pen)
        item.setPen(pen)

    def _set_stroke_color(self, color: QColor):
        self.scene.pen.setColor(color)

        def apply(it):
            if isinstance(it, TextItem):
                it.setDefaultTextColor(color)
            else:
                self._with_pen(it, lambda p: p.setColor(color))
        self._style_selection(apply)

    def _set_width(self, idx: int):
        w = float(self._width_combo.itemData(idx))
        self.scene.pen.setWidthF(w)
        self._style_selection(
            lambda it: self._with_pen(it, lambda p: p.setWidthF(w)))

    def _set_dash(self, idx: int):
        style = document.DASH_STYLES[self._dash_combo.itemData(idx)]
        self.scene.pen.setStyle(style)
        self._style_selection(
            lambda it: self._with_pen(it, lambda p: p.setStyle(style)))

    def _set_head(self, idx: int):
        head = self._head_combo.itemData(idx)
        self.scene.arrow_head = head
        self._style_selection(
            lambda it: it.set_head(head) if isinstance(it, ArrowItem) else None)

    def _fillable(self, it) -> bool:
        return (hasattr(it, "setBrush") and not isinstance(it, LineItem)
                and not isinstance(it, (TextItem, ImageItem)))

    def _apply_brush_to_selection(self):
        brush = self.scene.current_brush()
        self._style_selection(
            lambda it: it.setBrush(QBrush(brush)) if self._fillable(it) else None)

    def _set_fill_enabled(self, on: bool):
        self.scene.fill_enabled = on
        self._apply_brush_to_selection()

    def _set_fill_color(self, color: QColor):
        self.scene.fill_color = color
        if not self._fill_check.isChecked():
            self._fill_check.setChecked(True)     # applies via toggled
        else:
            self._apply_brush_to_selection()

    def _set_fill_color2(self, color: QColor):
        self.scene.fill_color2 = color
        self._apply_brush_to_selection()

    def _set_fill_style(self, idx: int):
        self.scene.fill_style = self._fill_style.itemData(idx)
        self._fill2_btn.setEnabled(self.scene.fill_style != "solid")
        if self._fill_check.isChecked():
            self._apply_brush_to_selection()

    def _set_font(self, *_):
        f = QFont(self._font_combo.currentFont().family(),
                  self._font_size.value())
        f.setBold(self._bold_btn.isChecked())
        f.setItalic(self._italic_btn.isChecked())
        self.scene.text_font = f

        def apply(it):
            if isinstance(it, TextItem):
                it.setFont(QFont(f))
            elif hasattr(it, "set_label_font"):
                it.set_label_font(QFont(f))
        self._style_selection(apply)

    def _palette_stroke(self, hexc):
        self._stroke_btn.set_color(QColor(hexc), emit=True)

    def _palette_fill(self, hexc):
        self._fill_btn.set_color(QColor(hexc), emit=True)

    def _on_color_picked(self, name: str, which: str):
        btn = self._fill_btn if which == "fill" else self._stroke_btn
        btn.set_color(QColor(name))
        if which == "fill":
            self._fill_check.setChecked(True)

    # ------------------------------------------------------------ properties edits
    def _single(self):
        items = self._selected_top_items()
        return items[0] if len(items) == 1 else None

    def _apply_position(self, *_):
        it = self._single()
        if it is None or self._syncing:
            return
        br = it.sceneBoundingRect()
        was = self.scene.snap_enabled
        self.scene.snap_enabled = False
        it.moveBy(self._p_x.value() - br.x(), self._p_y.value() - br.y())
        self.scene.snap_enabled = was
        self.scene.refresh_handles()
        self.scene.changed_by_user.emit()

    def _apply_rotation(self, *_):
        it = self._single()
        if it is None or self._syncing:
            return
        C.center_origin(it)
        it.setRotation(self._p_rot.value())
        self.scene.refresh_handles()
        self.scene.changed_by_user.emit()

    def _apply_opacity(self, *_):
        it = self._single()
        if it is None or self._syncing:
            return
        it.setOpacity(self._p_opacity.value() / 100.0)
        self.scene.changed_by_user.emit()

    def _apply_label(self):
        it = self._single()
        if it is None or not hasattr(it, "set_label"):
            return
        if (getattr(it, "_label", "") or "") == self._p_label.text():
            return
        it.set_label(self._p_label.text())
        self.scene.changed_by_user.emit()

    def _set_show_grid(self, on):
        self.scene.show_grid = on
        self.view.viewport().update()

    def _set_snap(self, on):
        self.scene.snap_enabled = on

    def _set_grid_mm(self, mm):
        self.scene.grid_mm = mm
        self.view.viewport().update()

    def _resize_canvas(self, *_):
        if self._syncing:
            return
        self.scene.resize_canvas(self._cw.value(), self._ch.value())

    def _zoom_to_content(self):
        r = export.content_rect(self.scene)
        if r.isEmpty():
            r = self.scene.sceneRect()
        self.view.fitInView(r.adjusted(-30, -30, 30, 30), Qt.KeepAspectRatio)
        # Never blow a small sketch up past 200 %.
        if self.view.current_zoom() > 2.0:
            self.view.set_zoom(2.0)
            self.view.centerOn(r.center())
        self.view.zoom_changed.emit(self.view.current_zoom())

    def _on_cursor(self, pos: QPointF):
        k = 25.4 / max(self.scene.dpi, 1)
        self._status.setText(f"x {pos.x() * k:.1f} mm   y {pos.y() * k:.1f} mm")

    def _rotate_mode(self):
        it = self._single()
        if it is not None:
            self.set_tool(C.POINTER)
            self.scene.enter_rotate_mode(it)

    def _reorder(self, where: str):
        items = self._selected_top_items()
        if len(items) != 1:
            return
        item = items[0]
        stack = self.scene.vector_items()
        if item not in stack or len(stack) < 2:
            return
        for idx, it in enumerate(stack):
            it.setZValue(idx)
        i, n = stack.index(item), len(stack)
        if where == "front":
            item.setZValue(n)
        elif where == "back":
            item.setZValue(-1)
        elif where == "forward" and i < n - 1:
            item.setZValue(i + 1); stack[i + 1].setZValue(i)
        elif where == "backward" and i > 0:
            item.setZValue(i - 1); stack[i - 1].setZValue(i)
        else:
            return
        self.scene.changed_by_user.emit()

    def _item_menu(self, item, global_pos):
        menu = QMenu(self)
        if isinstance(item, TextItem):
            menu.addAction("Edit text", item.start_editing)
        if isinstance(item, ImageItem):
            menu.addAction("Crop image", lambda: self.scene.begin_crop(item))
        menu.addAction(icons.paint_tool("rotate"), "Rotate", self._rotate_mode)
        menu.addAction(icons.paint_tool("duplicate"), "Duplicate",
                       self.duplicate_selection)
        menu.addAction(icons.paint_tool("copy"), "Copy", self.copy_selection)
        menu.addAction(icons.paint_tool("delete"), "Delete",
                       self.delete_selection)
        menu.addSeparator()
        for name, label in (("front", "Bring to front"),
                            ("forward", "Bring forward"),
                            ("backward", "Send backward"),
                            ("back", "Send to back")):
            menu.addAction(icons.paint_tool(name), label,
                           lambda w=name: self._reorder(w))
        menu.addSeparator()
        menu.addAction(icons.paint_tool("flip_h"), "Flip horizontal",
                       lambda: self.scene.mirror_selection(True))
        menu.addAction(icons.paint_tool("flip_v"), "Flip vertical",
                       lambda: self.scene.mirror_selection(False))
        if isinstance(item, GroupItem):
            menu.addAction(icons.paint_tool("ungroup"), "Ungroup",
                           self.scene.ungroup_selection)
        else:
            menu.addAction(icons.paint_tool("group"), "Group selection",
                           self.scene.group_selection)
            menu.addAction(icons.paint_tool("explode"), "Break into edges",
                           self.scene.explode_selection)
        menu.exec(global_pos)

    # ------------------------------------------------------------ shortcuts
    def _build_shortcuts(self):
        def add(seq, slot):
            act = QAction(self)
            act.setShortcut(QKeySequence(seq))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            act.triggered.connect(slot)
            self.addAction(act)
            return act

        for tool, _icon, _label, sc in DIRECT_TOOLS:
            if sc:
                add(sc, lambda t=tool: self._shortcut_tool(t))
        add(QKeySequence.Undo, self._undo.undo)
        add(QKeySequence.Redo, self._undo.redo)
        add("Ctrl+Y", self._undo.redo)
        add(QKeySequence.Copy, self.copy_selection)
        add(QKeySequence.Cut, self.cut_selection)
        add(QKeySequence.Paste, self.paste)
        add("Ctrl+D", self.duplicate_selection)
        add(QKeySequence.Delete, self.delete_selection)
        add("Backspace", self.delete_selection)
        add(QKeySequence.SelectAll, self._select_all)
        add("Ctrl+G", self.scene.group_selection)
        add("Ctrl+Shift+G", self.scene.ungroup_selection)
        add("Ctrl+]", lambda: self._reorder("forward"))
        add("Ctrl+[", lambda: self._reorder("backward"))
        add("Ctrl+Shift+]", lambda: self._reorder("front"))
        add("Ctrl+Shift+[", lambda: self._reorder("back"))
        add("Ctrl+=", lambda: self.view.zoom(1.25))
        add("Ctrl++", lambda: self.view.zoom(1.25))
        add("Ctrl+-", lambda: self.view.zoom(1 / 1.25))
        add("Ctrl+0", self._zoom_to_content)

    def _text_editing(self) -> bool:
        focus = self.scene.focusItem()
        if isinstance(focus, TextItem) and focus.textInteractionFlags():
            return True
        w = QApplication.focusWidget()
        return isinstance(w, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox))

    def _shortcut_tool(self, tool):
        if not self._text_editing():
            self.set_tool(tool)

    def keyPressEvent(self, event):
        # Esc must not throw the drawing away: it ends the current gesture
        # and drops back to the pointer instead.
        if event.key() == Qt.Key_Escape:
            if self.scene.selectedItems():
                self.scene.clearSelection()
            else:
                self.set_tool(C.POINTER)
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------ edit ops
    def _selected_top_items(self):
        return [i for i in self.scene.selectedItems() if i.parentItem() is None]

    def _select_all(self):
        if self._text_editing():
            return
        self.set_tool(C.POINTER)
        for item in self.scene.vector_items():
            item.setSelected(True)

    def delete_selection(self):
        if self._text_editing():
            return
        if self._selected_top_items():
            self.scene.delete_selection()

    def copy_selection(self):
        if self._text_editing():
            return
        items = self._selected_top_items()
        if not items:
            return
        payload = json.dumps([document.item_to_dict(i) for i in items])
        mime = QMimeData()
        mime.setData(MIME_ITEMS, payload.encode("utf-8"))
        QApplication.clipboard().setMimeData(mime)

    def cut_selection(self):
        if self._text_editing():
            return
        self.copy_selection()
        self.delete_selection()

    def paste(self):
        if self._text_editing():
            return
        mime = QApplication.clipboard().mimeData()
        if mime is None:
            return
        if mime.hasFormat(MIME_ITEMS):
            dicts = json.loads(bytes(mime.data(MIME_ITEMS)).decode("utf-8"))
            self._spawn(dicts, 20)
        elif mime.hasImage():
            pm = QPixmap.fromImage(QApplication.clipboard().image())
            if not pm.isNull():
                self._place_image(pm)

    def duplicate_selection(self):
        items = self._selected_top_items()
        if items:
            self._spawn([document.item_to_dict(i) for i in items], 20)

    def _spawn(self, dicts, offset):
        self.set_tool(C.POINTER)
        self.scene.clearSelection()
        created = []
        for d in dicts:
            item = document.item_from_dict(d)
            item.moveBy(offset, offset)
            self.scene.addItem(item)
            item.setSelected(True)
            created.append(item)
        if created:
            self.scene.changed_by_user.emit()
        return created

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert image", str(self._images_dir),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)")
        if path:
            pm = QPixmap(path)
            if not pm.isNull():
                self._place_image(pm)

    def _place_image(self, pm: QPixmap):
        max_side = 400
        if max(pm.width(), pm.height()) > max_side:
            pm = pm.scaled(max_side, max_side, Qt.KeepAspectRatio,
                           Qt.SmoothTransformation)
        item = ImageItem(pm)
        centre = self.view.mapToScene(self.view.viewport().rect().center())
        item.setPos(centre - QPointF(pm.width() / 2, pm.height() / 2))
        self.set_tool(C.POINTER)
        self.scene.clearSelection()
        self.scene.addItem(item)
        item.setSelected(True)
        self.scene.changed_by_user.emit()

    # ------------------------------------------------------------ history
    def _capture_change(self):
        if self._restoring:
            return
        after = document.scene_to_dict(self.scene)
        if after == self._snapshot:
            return
        self._undo.push(_SnapshotCommand(self, self._snapshot, after))
        self._snapshot = after

    def _restore_snapshot(self, state: dict):
        self._restoring = True
        try:
            self.scene.clear_handles()
            document.dict_to_scene(state, self.scene)
            self._snapshot = state
            self.scene.clear_handles()
            self.view.viewport().update()
        finally:
            self._restoring = False
        self._sync_properties()

    def _reset_history(self):
        self._snapshot = document.scene_to_dict(self.scene)
        self._undo.clear()

    # ------------------------------------------------------------ load / save
    def _load_existing(self, png_path: Path):
        src = drawing_source_for(png_path)
        if src is None:
            return
        try:
            if src.suffix == ".svg":
                export.load_svg(self.scene, src)
                # The editor always uses its own grid defaults.
                self.scene.show_grid = self._grid_check.isChecked()
                self.scene.snap_enabled = self._snap_check.isChecked()
                self.scene.grid_mm = self._grid_mm.value()
                self.scene.infinite = True
            else:
                with open(src, "r", encoding="utf-8") as fh:
                    load_legacy_json(self.scene, json.load(fh))
        except (OSError, ValueError) as exc:
            self._status.setText(f"Could not load drawing: {exc}")
            return
        self.view.apply_scroll_bounds()
        self._fit_on_show = True

    def showEvent(self, event):
        super().showEvent(event)
        # The viewport has its real size only once shown.
        if getattr(self, "_fit_on_show", False):
            self._fit_on_show = False
            self._zoom_to_content()

    def _target_path(self) -> Path:
        if self._existing_path is not None:
            return self._existing_path.with_suffix(".png")
        return next_drawing_path(self._images_dir)

    def _accept_and_save(self) -> None:
        if self._save():
            self.accept()

    def _open_in_khervepaint(self) -> None:
        """Save what is on the canvas, then hand it to KhervePaint; the
        editor watches the SVG and picks up KhervePaint's saves."""
        if not self.scene.vector_items() and self._existing_path is None:
            self._status.setText("Draw something first: KhervePaint opens "
                                 "the saved drawing.")
            return
        if self._save():
            self.handoff_to_khervepaint = True
            self.accept()

    def _save(self) -> bool:
        focus = self.scene.focusItem()
        if focus is not None:
            focus.clearFocus()            # commit an in-progress text edit
        self.scene.cancel_crop()
        target = self._target_path()
        try:
            ok = export.save_drawing(self.scene, target)
        except OSError as exc:
            self._status.setText(f"Could not save: {exc}")
            return False
        if not ok:
            self.reject()
            return False
        self._saved_path = target
        self.drawingSaved.emit(str(target))
        return True
