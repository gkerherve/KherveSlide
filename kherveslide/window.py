"""KherveSlide main window — a dedicated WYSIWYG slide designer.

Layout mirrors KherveTeX: the left side is the **WYSIWYG** editing area
(a visual slide navigator you can drag to reorder, plus the live slide
canvas), and the right side shows the generated **LaTeX** source and the
compiler **console** — kept live so what you build on the left is always
reflected on the right. Object properties live in a dock on the left.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDockWidget, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGraphicsView, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QToolBar, QVBoxLayout,
    QWidget,
)

from . import icons, templates
from .canvas import SlideScene, make_item, scene_width
from .compiler import compile_tex, tectonic_available
from .latex_view import LatexView
from .model import (
    Deck, Slide, SlideText, SlidePicture, deck_to_json, deck_from_json,
    raise_object, lower_object, to_front, to_back,
)
from .navigator import SlideNavigator
from .preview import PdfPreview
from .serializer import serialize_deck


class SlideWindow(QMainWindow):
    def __init__(self, parent=None, *, dark=False, theme=None):
        super().__init__(parent)
        self.setWindowTitle("KherveSlide — WYSIWYG slides")
        self.setWindowIcon(icons.app_icon())
        self.resize(1360, 820)
        self._dark = dark
        self._theme = theme
        self.store = templates.TemplateStore()
        self.deck: Deck = templates.instantiate_builtin("Title + content")
        self.current = 0
        self.path: Path | None = None
        self._items = []
        self._loading = False

        self._build_toolbar()
        self._build_ui()
        self._reload_all()

    # ---------------- toolbar ----------------
    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        def act(icon, text, slot):
            a = QAction(icon, text, self)
            a.setToolTip(text)
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        act(icons.file_new(), "New", self._new_deck)
        act(icons.file_open(), "Open", self._open_deck)
        act(icons.file_save(), "Save", self._save_deck)
        act(icons.export_pdf(), "Export .tex", self._export_tex)
        tb.addSeparator()
        act(icons.slide_add(), "Add slide", self._add_slide)
        act(icons.text_box(), "Add text box", self._add_text)
        act(icons.image_box(), "Add image box", self._add_picture)
        act(icons.delete_box(), "Delete object", self._delete_selected)
        tb.addSeparator()
        act(icons.raise_box(), "Raise", lambda: self._zorder("raise"))
        act(icons.lower_box(), "Lower", lambda: self._zorder("lower"))
        act(icons.raise_box(), "To front", lambda: self._zorder("front"))
        act(icons.lower_box(), "To back", lambda: self._zorder("back"))
        tb.addSeparator()
        act(icons.templates_icon(), "Templates", self._templates_menu)
        act(icons.compile_pdf(), "Compile", self._compile)

    # ---------------- layout ----------------
    def _build_ui(self):
        # --- LEFT: the WYSIWYG side (navigator + canvas) ---
        self.nav = SlideNavigator()
        self.nav.slideSelected.connect(self._on_slide_changed)
        self.nav.slidesReordered.connect(self._on_reorder)

        nav_panel = QWidget()
        nv = QVBoxLayout(nav_panel); nv.setContentsMargins(4, 4, 4, 4)
        nv.addWidget(QLabel("Slides"))
        nv.addWidget(self.nav)
        row = QHBoxLayout()
        b_add = QPushButton("+ Slide"); b_add.clicked.connect(self._add_slide)
        b_del = QPushButton("−"); b_del.clicked.connect(self._del_slide)
        b_del.setMaximumWidth(34)
        row.addWidget(b_add); row.addWidget(b_del)
        nv.addLayout(row)

        self.scene = SlideScene(self.deck.aspect)
        self.scene.selectionChanged.connect(self._on_selection)
        self.view = QGraphicsView(self.scene)

        left = QSplitter(Qt.Horizontal)
        left.addWidget(nav_panel)
        left.addWidget(self.view)
        left.setStretchFactor(1, 1)
        left.setSizes([220, 720])

        # --- RIGHT: LaTeX + console (+ PDF) ---
        self.latex_view = LatexView()
        self.latex_view._edit.setReadOnly(True)
        self.latex_view.set_dark(self._dark, self._theme)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        cf = QFont("Consolas"); cf.setStyleHint(QFont.Monospace); cf.setPointSize(10)
        self.console.setFont(cf)
        self.pdf_view = PdfPreview()

        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self.latex_view, "LaTeX")
        self.right_tabs.addTab(self.console, "Console")
        self.right_tabs.addTab(self.pdf_view, "PDF")

        main = QSplitter(Qt.Horizontal)
        main.addWidget(left)
        main.addWidget(self.right_tabs)
        main.setStretchFactor(0, 1)
        main.setStretchFactor(1, 1)
        main.setSizes([760, 600])
        self.setCentralWidget(main)

        # --- Properties dock (part of the WYSIWYG side) ---
        self.props_dock = QDockWidget("Properties", self)
        self.props_dock.setWidget(self._build_props_panel())
        self.props_dock.setAllowedAreas(Qt.LeftDockWidgetArea
                                        | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.props_dock)

        self.statusBar().showMessage("Ready")

    def _build_props_panel(self) -> QWidget:
        w = QWidget(); w.setMinimumWidth(260)
        v = QVBoxLayout(w)

        v.addWidget(QLabel("<b>Deck</b>"))
        deck_form = QFormLayout()
        self.f_title = QLineEdit(); self.f_title.editingFinished.connect(self._apply_deck)
        self.f_author = QLineEdit(); self.f_author.editingFinished.connect(self._apply_deck)
        self.f_theme = QComboBox(); self.f_theme.setEditable(True)
        self.f_theme.addItems(["default", "Madrid", "Berlin", "Copenhagen",
                               "Frankfurt", "Singapore", "Warsaw", "metropolis",
                               "CambridgeUS", "Boadilla", "Pittsburgh"])
        self.f_theme.currentTextChanged.connect(self._apply_deck)
        self.f_color = QComboBox(); self.f_color.setEditable(True)
        self.f_color.addItems(["", "default", "beaver", "crane", "dolphin",
                               "seagull", "wolverine", "orchid", "whale"])
        self.f_color.currentTextChanged.connect(self._apply_deck)
        self.f_aspect = QComboBox()
        self.f_aspect.addItems(["169", "1610", "43", "32", "54", "141"])
        self.f_aspect.currentTextChanged.connect(self._apply_aspect)
        deck_form.addRow("Title", self.f_title)
        deck_form.addRow("Author", self.f_author)
        deck_form.addRow("Theme", self.f_theme)
        deck_form.addRow("Colours", self.f_color)
        deck_form.addRow("Aspect", self.f_aspect)
        v.addLayout(deck_form)

        v.addWidget(QLabel("<b>Slide</b>"))
        slide_form = QFormLayout()
        self.f_slide_title = QLineEdit()
        self.f_slide_title.editingFinished.connect(self._apply_slide)
        self.b_slide_bg = QPushButton("Background…")
        self.b_slide_bg.clicked.connect(self._pick_slide_bg)
        slide_form.addRow("Frame title", self.f_slide_title)
        slide_form.addRow("", self.b_slide_bg)
        v.addLayout(slide_form)

        v.addWidget(QLabel("<b>Selected object</b>"))
        self.obj_form = QFormLayout()
        self.f_text = QPlainTextEdit(); self.f_text.setMaximumHeight(90)
        self.f_text.textChanged.connect(self._apply_obj_text)
        self.f_font = QSpinBox(); self.f_font.setRange(6, 160)
        self.f_font.valueChanged.connect(self._apply_obj)
        self.b_color = QPushButton("Text colour…")
        self.b_color.clicked.connect(lambda: self._pick_obj_color("color"))
        self.b_fill = QPushButton("Fill…")
        self.b_fill.clicked.connect(lambda: self._pick_obj_color("fill"))
        self.f_align = QComboBox(); self.f_align.addItems(["left", "center", "right"])
        self.f_align.currentTextChanged.connect(self._apply_obj)
        self.c_bold = QCheckBox("Bold"); self.c_bold.toggled.connect(self._apply_obj)
        self.c_italic = QCheckBox("Italic"); self.c_italic.toggled.connect(self._apply_obj)
        self.b_img = QPushButton("Image file…"); self.b_img.clicked.connect(self._pick_image)
        self.c_aspect = QCheckBox("Keep aspect"); self.c_aspect.toggled.connect(self._apply_obj)
        self.f_x = self._pct(); self.f_y = self._pct()
        self.f_w = self._pct(); self.f_h = self._pct()
        for s in (self.f_x, self.f_y, self.f_w, self.f_h):
            s.valueChanged.connect(self._apply_obj_geometry)
        self.obj_form.addRow("Text", self.f_text)
        self.obj_form.addRow("Font pt", self.f_font)
        self.obj_form.addRow("", self.b_color)
        self.obj_form.addRow("", self.b_fill)
        self.obj_form.addRow("Align", self.f_align)
        self.obj_form.addRow(self.c_bold, self.c_italic)
        self.obj_form.addRow("", self.b_img)
        self.obj_form.addRow("", self.c_aspect)
        self.obj_form.addRow("X %", self.f_x)
        self.obj_form.addRow("Y %", self.f_y)
        self.obj_form.addRow("W %", self.f_w)
        self.obj_form.addRow("H %", self.f_h)
        v.addLayout(self.obj_form)
        v.addStretch(1)
        self._set_obj_enabled(False)
        return w

    def _pct(self):
        s = QDoubleSpinBox(); s.setRange(0, 100); s.setSuffix(" %")
        s.setDecimals(1); s.setSingleStep(1.0)
        return s

    # ---------------- reload ----------------
    @property
    def slide(self) -> Slide:
        return self.deck.slides[self.current]

    def _reload_all(self):
        self.nav.refresh(self.deck, self.current)
        self._reload_scene()

    def _reload_scene(self):
        self._loading = True
        self._items = []
        self.scene.set_aspect(self.deck.aspect)
        self.scene.clear()
        sw = scene_width(self.deck.aspect)
        for obj in self.slide.objects:
            item = make_item(obj, sw)
            item.geometryChanged.connect(self._on_item_geometry)
            self.scene.addItem(item)
            self._items.append(item)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self._load_deck_fields()
        self._load_slide_fields()
        self._set_obj_enabled(False)
        self._loading = False
        self._refresh_latex()

    def _refresh_latex(self):
        """Keep the right-hand LaTeX view in sync with the deck."""
        self.latex_view.set_source(serialize_deck(self.deck))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    # ---------------- slides ----------------
    def _on_slide_changed(self, row):
        if self._loading or not (0 <= row < len(self.deck.slides)):
            return
        self.current = row
        self._reload_scene()

    def _on_reorder(self, order):
        self.deck.slides = [self.deck.slides[i] for i in order]
        self.current = order.index(self.current) if self.current in order else 0
        self._reload_all()

    def _add_slide(self):
        self.deck.slides.insert(self.current + 1, Slide())
        self.current += 1
        self._reload_all()

    def _del_slide(self):
        if len(self.deck.slides) <= 1:
            return
        del self.deck.slides[self.current]
        self.current = max(0, self.current - 1)
        self._reload_all()

    def _touch_current(self):
        """After editing the current slide: refresh its thumbnail and the
        live LaTeX."""
        if self._loading:
            return
        self.nav.refresh_one(self.deck, self.current)
        self._refresh_latex()

    # ---------------- objects ----------------
    def _add_text(self):
        self.slide.objects.append(SlideText())
        self._reload_scene()
        self._select_last()
        self._touch_current()

    def _add_picture(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", "",
            "Images (*.png *.jpg *.jpeg *.pdf *.gif *.bmp)")
        self.slide.objects.append(SlidePicture(path=path or ""))
        self._reload_scene()
        self._select_last()
        self._touch_current()

    def _select_last(self):
        if self._items:
            self._items[-1].setSelected(True)

    def _delete_selected(self):
        item = self._selected_item()
        if item is None:
            return
        self.slide.objects.remove(item.obj)
        self._reload_scene()
        self._touch_current()

    def _zorder(self, how):
        item = self._selected_item()
        if item is None:
            return
        idx = self.slide.objects.index(item.obj)
        fn = {"raise": raise_object, "lower": lower_object,
              "front": to_front, "back": to_back}[how]
        new_idx = fn(self.slide, idx)
        self._reload_scene()
        if 0 <= new_idx < len(self._items):
            self._items[new_idx].setSelected(True)
        self._touch_current()

    def _selected_item(self):
        for it in self._items:
            if it.isSelected():
                return it
        return None

    # ---------------- property syncing ----------------
    def _on_selection(self):
        if self._loading:
            return
        item = self._selected_item()
        if item is None:
            self._set_obj_enabled(False)
            return
        self._load_obj_fields(item.obj)

    def _on_item_geometry(self):
        item = self._selected_item()
        if item is not None:
            self._load_obj_geometry(item.obj)
            self._touch_current()

    def _set_obj_enabled(self, on, is_text=True, is_pic=False):
        for wdg in (self.f_text, self.f_font, self.b_color, self.b_fill,
                    self.f_align, self.c_bold, self.c_italic):
            wdg.setEnabled(on and is_text)
        for wdg in (self.b_img, self.c_aspect):
            wdg.setEnabled(on and is_pic)
        for wdg in (self.f_x, self.f_y, self.f_w, self.f_h):
            wdg.setEnabled(on)

    def _load_obj_geometry(self, obj):
        self._loading = True
        self.f_x.setValue(obj.x * 100); self.f_y.setValue(obj.y * 100)
        self.f_w.setValue(obj.w * 100); self.f_h.setValue(obj.h * 100)
        self._loading = False

    def _load_obj_fields(self, obj):
        self._loading = True
        is_text = isinstance(obj, SlideText)
        self._set_obj_enabled(True, is_text=is_text, is_pic=not is_text)
        if is_text:
            self.f_text.setPlainText(obj.text)
            self.f_font.setValue(obj.font_pt)
            self.f_align.setCurrentText(obj.align)
            self.c_bold.setChecked(obj.bold)
            self.c_italic.setChecked(obj.italic)
        else:
            self.c_aspect.setChecked(obj.keep_aspect)
        self._load_obj_geometry(obj)
        self._loading = False

    def _apply_obj(self):
        if self._loading:
            return
        item = self._selected_item()
        if item is None:
            return
        obj = item.obj
        if isinstance(obj, SlideText):
            obj.font_pt = self.f_font.value()
            obj.align = self.f_align.currentText()
            obj.bold = self.c_bold.isChecked()
            obj.italic = self.c_italic.isChecked()
        else:
            obj.keep_aspect = self.c_aspect.isChecked()
        item.update()
        self._touch_current()

    def _apply_obj_text(self):
        if self._loading:
            return
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlideText):
            return
        item.obj.text = self.f_text.toPlainText()
        item.update()
        self._touch_current()

    def _apply_obj_geometry(self):
        if self._loading:
            return
        item = self._selected_item()
        if item is None:
            return
        obj = item.obj
        obj.x = self.f_x.value() / 100; obj.y = self.f_y.value() / 100
        obj.w = self.f_w.value() / 100; obj.h = self.f_h.value() / 100
        item.sync_from_model()
        self._touch_current()

    def _pick_obj_color(self, which):
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlideText):
            return
        cur = getattr(item.obj, which) or "#000000"
        col = QColorDialog.getColor(QColor(cur), self)
        if col.isValid():
            setattr(item.obj, which, col.name())
            item.update()
            self._touch_current()

    def _pick_image(self):
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlidePicture):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", "",
            "Images (*.png *.jpg *.jpeg *.pdf *.gif *.bmp)")
        if path:
            item.obj.path = path
            item.update()
            self._touch_current()

    # ---------------- deck/slide fields ----------------
    def _load_deck_fields(self):
        self._loading = True
        self.f_title.setText(self.deck.title)
        self.f_author.setText(self.deck.author)
        self.f_theme.setCurrentText(self.deck.theme)
        self.f_color.setCurrentText(self.deck.color_theme)
        self.f_aspect.setCurrentText(self.deck.aspect)
        self._loading = False

    def _load_slide_fields(self):
        self._loading = True
        self.f_slide_title.setText(self.slide.title)
        self._loading = False

    def _apply_deck(self):
        if self._loading:
            return
        self.deck.title = self.f_title.text()
        self.deck.author = self.f_author.text()
        self.deck.theme = self.f_theme.currentText()
        self.deck.color_theme = self.f_color.currentText()
        self._refresh_latex()

    def _apply_aspect(self, aspect):
        if self._loading:
            return
        self.deck.aspect = aspect
        self._reload_all()

    def _apply_slide(self):
        if self._loading:
            return
        self.slide.title = self.f_slide_title.text()
        self._touch_current()

    def _pick_slide_bg(self):
        cur = self.slide.bg or "#FFFFFF"
        col = QColorDialog.getColor(QColor(cur), self, "Slide background")
        if col.isValid():
            self.slide.bg = col.name()
            self._touch_current()

    # ---------------- templates ----------------
    def _templates_menu(self):
        choices = (["New from: " + n for n in self.store.all_names()]
                   + ["— Save current deck as template…",
                      "— Rename a template…",
                      "— Delete a template…"])
        choice, ok = QInputDialog.getItem(
            self, "Templates", "Choose an action:", choices, 0, False)
        if not ok:
            return
        if choice.startswith("New from: "):
            self.deck = self.store.instantiate(choice[len("New from: "):])
            self.current = 0
            self._reload_all()
        elif "Save current" in choice:
            self._save_as_template()
        elif "Rename" in choice:
            self._rename_template()
        elif "Delete" in choice:
            self._delete_template()

    def _save_as_template(self):
        name, ok = QInputDialog.getText(self, "Save template", "New template name:")
        if not ok or not name.strip():
            return
        try:
            self.store.save_deck_as(name.strip(), self.deck)
            self.statusBar().showMessage(f"Saved template '{name.strip()}'")
        except ValueError as e:
            QMessageBox.warning(self, "Template", str(e))

    def _rename_template(self):
        names = self.store.names()
        if not names:
            QMessageBox.information(self, "Rename", "No user templates yet.")
            return
        old, ok = QInputDialog.getItem(self, "Rename template", "Template:",
                                       names, 0, False)
        if not ok:
            return
        new, ok = QInputDialog.getText(self, "Rename template", "New name:",
                                       text=old)
        if not ok:
            return
        try:
            self.store.rename(old, new.strip())
        except (ValueError, KeyError) as e:
            QMessageBox.warning(self, "Rename", str(e))

    def _delete_template(self):
        names = self.store.names()
        if not names:
            QMessageBox.information(self, "Delete", "No user templates yet.")
            return
        name, ok = QInputDialog.getItem(self, "Delete template", "Template:",
                                        names, 0, False)
        if ok:
            self.store.delete(name)

    # ---------------- compile / IO ----------------
    def _compile(self):
        tex = serialize_deck(self.deck)
        self.latex_view.set_source(tex)
        if not tectonic_available():
            self.console.setPlainText("tectonic is not available on this system.")
            self.right_tabs.setCurrentWidget(self.console)
            return
        self.statusBar().showMessage("Compiling…")
        self.setCursor(Qt.WaitCursor)
        try:
            workdir = Path(tempfile.gettempdir()) / "kherveslide_build"
            src_dir = self.path.parent if self.path else None
            result = compile_tex(tex, workdir, "slides", source_dir=src_dir)
        finally:
            self.unsetCursor()
        self.console.setPlainText(result.log or "")
        if result.ok and result.pdf_path:
            self.pdf_view.show_pdf(Path(result.pdf_path))
            self.right_tabs.setCurrentWidget(self.pdf_view)
            self.statusBar().showMessage("Compiled OK")
        else:
            self.right_tabs.setCurrentWidget(self.console)
            self.statusBar().showMessage("Compile failed — see Console")

    def _new_deck(self):
        self.deck = templates.instantiate_builtin("Blank")
        self.current = 0
        self.path = None
        self._reload_all()

    def _save_deck(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save deck", "", "KherveSlide deck (*.kslide.json)")
        if not path:
            return
        Path(path).write_text(deck_to_json(self.deck), encoding="utf-8")
        self.path = Path(path)
        self.statusBar().showMessage(f"Saved {path}")

    def _open_deck(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open deck", "", "KherveSlide deck (*.kslide.json *.json)")
        if not path:
            return
        try:
            self.deck = deck_from_json(Path(path).read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Open", str(e))
            return
        if not self.deck.slides:
            self.deck.slides = [Slide()]
        self.path = Path(path)
        self.current = 0
        self._reload_all()

    def _export_tex(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export LaTeX", "",
                                              "LaTeX (*.tex)")
        if not path:
            return
        Path(path).write_text(serialize_deck(self.deck), encoding="utf-8")
        self.statusBar().showMessage(f"Exported {path}")
