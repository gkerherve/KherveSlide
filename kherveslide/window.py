"""KherveSlide main window — a dedicated WYSIWYG slide designer.

Editing happens directly on the objects, PowerPoint-style: double-click a
text box to type into it in place, double-click a picture to swap the
image. There is no separate properties panel — frequent text formatting
lives on a compact Format toolbar, and deck/slide settings live in the
menus. The left side is the WYSIWYG (a slide navigator you drag to
reorder + the live canvas); the right side shows the generated LaTeX and
the compiler console, kept live as you edit.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import (
    QByteArray, QMimeData, QPointF, QSettings, QSize, QThread, QTimer, Qt,
    Signal,
)
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QFont, QTextCharFormat, QTextListFormat,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGraphicsView, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QTextEdit, QToolBar,
    QVBoxLayout, QWidget,
)

from . import icons, spellcheck, templates, themes, version_string
from .canvas import (
    SlideScene, SlideView, TextBoxItem, PictureBoxItem, TableBoxItem,
    make_item, page_size_px, FONT_SCALE, latex_to_html, document_to_latex,
    _dropped_image,
)
from .compiler import compile_tex, tectonic_available
from .drawing_dialog import DrawingDialog
from .latex_view import LatexView
from .model import (
    Deck, Slide, SlideText, SlidePicture, SlideTable, SlideLine,
    blend_over_white, deck_to_json, deck_from_json,
    object_to_dict, build_object,
    raise_object, lower_object, to_front, to_back,
)
from .navigator import SlideNavigator
from .preview import PdfPreview
from .serializer import serialize_deck


# The full set of beamer's built-in presentation themes and colour themes
# (no extra packages needed, so they all work with the bundled engine).
_THEMES = [
    "default", "AnnArbor", "Antibes", "Bergen", "Berkeley", "Berlin",
    "Boadilla", "CambridgeUS", "Copenhagen", "Darmstadt", "Dresden",
    "Frankfurt", "Goettingen", "Hannover", "Ilmenau", "JuanLesPins",
    "Luebeck", "Madrid", "Malmoe", "Marburg", "Montpellier", "PaloAlto",
    "Pittsburgh", "Rochester", "Singapore", "Szeged", "Warsaw",
    # Third-party themes (fetched by tectonic; verified to compile).
    "metropolis", "Auriga", "Trigon", "sintef",
]
_COLOUR_THEMES = [
    "", "default", "albatross", "beaver", "beetle", "crane", "dolphin",
    "dove", "fly", "lily", "monarca", "orchid", "rose", "seagull",
    "seahorse", "spruce", "structure", "whale", "wolverine",
]
_ASPECTS = ["169", "1610", "43", "32", "54", "141"]
_ASPECT_LABELS = {
    "169": "16:9", "1610": "16:10", "43": "4:3",
    "32": "3:2", "54": "5:4", "141": "1.41:1",
}


class _CompileWorker(QThread):
    """Runs a tectonic compile off the UI thread so auto-compile on every
    edit never freezes the canvas."""

    done = Signal(object)   # CompileResult

    def __init__(self, tex, workdir, src_dir):
        super().__init__()
        self._tex = tex
        self._workdir = workdir
        self._src_dir = src_dir

    def run(self):
        result = compile_tex(self._tex, self._workdir, "slides",
                             source_dir=self._src_dir)
        self.done.emit(result)


class _DownloadWorker(QThread):
    """Pre-downloads the tectonic TeX packages so compiles are fast and
    fully offline. Runs off the UI thread; streams progress lines."""

    line = Signal(str)
    done = Signal(bool)

    def run(self):
        from .offline import download_offline
        ok = download_offline(on_output=lambda s: self.line.emit(s.rstrip()))
        self.done.emit(ok)


class _InlineEditor(QTextEdit):
    """A rich text-box editor that floats over the object being edited:
    bullet/numbered lists show as real lists (not \\item source), and it
    commits when it loses focus (or Escape is pressed). Ctrl+B / Ctrl+I
    bold/italicise just the selection, so one box can mix styles.
    Misspelled words get a red wavy underline with right-click corrections."""

    editingFinished = Signal()

    # Toggled from the View menu; persisted in QSettings.
    spellcheck_enabled = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self._speller = spellcheck.SpellHighlighter(self.document())
        self._speller.enabled = (self.spellcheck_enabled
                                 and spellcheck.available())

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clearFocus()
            return
        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_B:
                self.toggle_bold()
                return
            if event.key() == Qt.Key_I:
                self.toggle_italic()
                return
        super().keyPressEvent(event)

    def toggle_bold(self):
        fmt = QTextCharFormat()
        on = self.fontWeight() > QFont.Normal
        fmt.setFontWeight(QFont.Normal if on else QFont.Bold)
        self._merge_format(fmt)

    def toggle_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.fontItalic())
        self._merge_format(fmt)

    def _merge_format(self, fmt):
        # Apply to the selection if there is one, and to whatever is typed
        # next (so Ctrl+B with no selection starts a bold run).
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        self.mergeCurrentCharFormat(fmt)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        if self._speller.enabled:
            cursor = self.cursorForPosition(event.pos())
            cursor.select(cursor.SelectionType.WordUnderCursor)
            word = cursor.selectedText()
            if word and spellcheck.is_misspelled(word):
                menu.addSeparator()
                sugg = spellcheck.suggestions(word)
                if sugg:
                    for s in sugg:
                        act = menu.addAction(s)
                        act.triggered.connect(
                            lambda _=False, c=cursor, t=s: self._replace(c, t))
                else:
                    menu.addAction("(no suggestions)").setEnabled(False)
                menu.addAction(
                    f'Add "{word}" to dictionary',
                    lambda w=word: self._learn(w))
        menu.exec(event.globalPos())

    def _replace(self, cursor, text):
        cursor.insertText(text)

    def _learn(self, word):
        spellcheck.add_word(word)
        self._speller.rehighlight()


class SlideWindow(QMainWindow):
    def __init__(self, parent=None, *, dark=False, theme=None):
        super().__init__(parent)
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
        self._edit_proxy = None
        self._edit_commit = None
        self._font_scale = FONT_SCALE

        # Auto-compile: debounce edits, run tectonic off-thread.
        self._worker: _CompileWorker | None = None
        self._compile_pending = False
        self._dl_worker: _DownloadWorker | None = None
        self._theme_cache: dict = {}   # theme name -> preview QPixmap

        # Undo/redo: a debounced snapshot history of the whole presentation
        # (it is fully JSON-serialisable, so every action is captured).
        self._history: list[str] = []
        self._hist_index = -1
        self._restoring = False
        self._undo_timer = QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.setInterval(350)
        self._undo_timer.timeout.connect(self._capture_state)
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.setInterval(900)
        self._auto_timer.timeout.connect(self._start_compile)

        self._theme_name = QSettings("kherveDOC", "KherveSlide").value(
            "theme_name", "Light")
        # (action, icon-factory) pairs so a theme switch can recolour icons.
        self._themed_icons: list = []
        self._update_title()
        self._build_menus()
        self._build_toolbar()
        self._build_slide_toolbar()
        self._build_ui()
        self._reload_all()
        self._reset_history()
        self._maybe_autodownload_packages()

    # ---------------- menus ----------------
    def _build_menus(self):
        mb = self.menuBar()
        m_file = mb.addMenu("&File")
        m_file.addAction("New", self._new_deck).setShortcut("Ctrl+N")
        m_file.addAction("Open…", self._open_deck).setShortcut("Ctrl+O")
        self._recent_menu = m_file.addMenu("Open recent")
        self._recent_menu.aboutToShow.connect(self._populate_recent_menu)
        m_file.addSeparator()
        m_file.addAction("Save", self._save_deck).setShortcut("Ctrl+S")
        m_file.addAction("Save As…", self._save_deck_as).setShortcut("Ctrl+Shift+S")
        self._act_open_loc = m_file.addAction(
            "Open file location", self._open_file_location)
        m_file.addSeparator()
        m_file.addAction("Export LaTeX (.tex)…", self._export_tex)
        m_file.addAction("Export PDF…", self._export_pdf)
        m_file.addAction("Compile to PDF", self._compile).setShortcut("Ctrl+R")
        m_file.addSeparator()
        m_file.addAction("Download LaTeX packages (offline)…",
                         self._download_packages)
        m_file.addSeparator()
        m_file.addAction("Quit", self.close).setShortcut("Ctrl+Q")

        m_edit = mb.addMenu("&Edit")
        self.act_undo = m_edit.addAction(icons.undo(), "Undo", self._undo)
        self.act_undo.setShortcut("Ctrl+Z")
        self.act_redo = m_edit.addAction(icons.redo(), "Redo", self._redo)
        self.act_redo.setShortcut("Ctrl+Y")
        self._themed_icons += [(self.act_undo, icons.undo),
                               (self.act_redo, icons.redo)]
        m_edit.addSeparator()
        m_edit.addAction("Copy", self._copy_selected).setShortcut("Ctrl+C")
        m_edit.addAction("Cut", self._cut_selected).setShortcut("Ctrl+X")
        m_edit.addAction("Paste", self._paste).setShortcut("Ctrl+V")
        m_edit.addAction("Duplicate", self._duplicate_selected).setShortcut("Ctrl+D")
        m_edit.addSeparator()
        m_edit.addAction("Page setup…", self._page_setup)

        m_view = mb.addMenu("&View")
        self.act_show_nav = m_view.addAction("Show slide navigator")
        self.act_show_nav.setCheckable(True)
        self.act_show_nav.setChecked(True)
        self.act_show_nav.setShortcut("Ctrl+B")
        self.act_show_nav.toggled.connect(self._toggle_navigator)
        m_view.addSeparator()
        self.act_spell = m_view.addAction("Check spelling")
        self.act_spell.setCheckable(True)
        spell_on = QSettings("kherveDOC", "KherveSlide").value(
            "spellcheck_enabled", True, type=bool) and spellcheck.available()
        self.act_spell.setChecked(spell_on)
        self.act_spell.setEnabled(spellcheck.available())
        if not spellcheck.available():
            self.act_spell.setToolTip(
                "Install pyspellchecker to enable spell checking.")
        _InlineEditor.spellcheck_enabled = spell_on
        self.act_spell.toggled.connect(self._toggle_spellcheck)

        m_appear = m_view.addMenu("Appearance")
        self._theme_group = QActionGroup(self)
        self._theme_actions = {}
        for name in themes.THEME_NAMES:
            a = m_appear.addAction(name)
            a.setCheckable(True)
            a.setChecked(name == self._theme_name)
            a.triggered.connect(lambda _=False, n=name: self._apply_named_theme(n))
            self._theme_group.addAction(a)
            self._theme_actions[name] = a

        m_pres = mb.addMenu("&Presentation")
        m_pres.addAction("Title…", self._set_deck_title)
        m_pres.addAction("Author…", self._set_deck_author)
        m_pres.addAction("Colour theme…", self._set_colour_theme)
        m_pres.addAction("Theme builder (custom theme)…", self._open_theme_builder)
        self.act_nav = m_pres.addAction("Navigation symbols (prev / next)")
        self.act_nav.setCheckable(True)
        self.act_nav.setChecked(self.deck.nav_symbols)
        self.act_nav.toggled.connect(self._toggle_nav_symbols)

        m_pgnum = m_pres.addMenu("Slide numbers")
        self._pgnum_group = QActionGroup(self)
        self._pgnum_actions = {}
        for mode, label in (("none", "Off"),
                            ("number", "Slide number"),
                            ("of_total", "Slide number / total")):
            a = m_pgnum.addAction(label)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, m=mode: self._set_page_number(m))
            self._pgnum_group.addAction(a)
            self._pgnum_actions[mode] = a
        # Theme + decorations live on the toolbar (see _build_toolbar).

        m_slide = mb.addMenu("&Slide")
        m_slide.addAction("Add slide", self._add_slide)
        m_slide.addAction("Delete slide", self._del_slide)
        m_slide.addAction("Frame title…", self._set_frame_title)
        m_slide.addAction("Background colour…", self._pick_slide_bg)
        m_slide.addAction("Clear background", self._clear_slide_bg)

        m_insert = mb.addMenu("&Insert")
        m_insert.addAction("Text box", self._add_text)
        m_insert.addAction("Picture", self._add_picture)
        m_insert.addAction("Table", self._add_table)
        m_insert.addAction("Equation…", self._add_equation)
        m_insert.addAction("Drawing…", self._add_drawing)

        m_table = mb.addMenu("&Table")
        m_table.addAction("Add row", lambda: self._table_op("add_row"))
        m_table.addAction("Add column", lambda: self._table_op("add_col"))
        m_table.addAction("Delete row", lambda: self._table_op("del_row"))
        m_table.addAction("Delete column", lambda: self._table_op("del_col"))
        m_table.addSeparator()
        m_table.addAction("Toggle header row", lambda: self._table_op("header"))
        m_table.addAction("Caption…", lambda: self._table_op("caption"))

        m_tpl = mb.addMenu("Te&mplates")
        self._m_tpl_new = m_tpl.addMenu("New presentation from template")
        self._m_tpl_new.aboutToShow.connect(self._populate_templates_menu)
        m_tpl.addSeparator()
        m_tpl.addAction("Save current presentation as template…", self._save_as_template)
        m_tpl.addAction("Rename template…", self._rename_template)
        m_tpl.addAction("Delete template…", self._delete_template)

    # ---------------- toolbars ----------------
    def _build_toolbar(self):
        # Row 1 — document actions: file, history, build, zoom, theme.
        tb = QToolBar("Main"); tb.setMovable(False); self.addToolBar(tb)
        tb.setIconSize(QSize(24, 24))

        def act(factory, text, slot):
            a = QAction(factory(), text, self); a.setToolTip(text)
            a.triggered.connect(slot); tb.addAction(a)
            self._themed_icons.append((a, factory))
            return a

        act(icons.file_new, "New", self._new_deck)
        act(icons.file_open, "Open", self._open_deck)
        act(icons.file_save, "Save", self._save_deck)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        act(icons.templates_icon, "Templates", self._templates_menu)
        act(icons.compile_pdf, "Compile", self._compile)
        act(icons.export_pdf, "Export PDF", self._export_pdf)
        tb.addSeparator()
        act(icons.zoom_out, "Zoom out", lambda: self.view.zoom_by(1 / 1.25))
        act(icons.fit_width, "Fit slide to window",
            lambda: self.view.fit_to_window())
        act(icons.zoom_in, "Zoom in", lambda: self.view.zoom_by(1.25))
        tb.addSeparator()
        tb.addWidget(QLabel(" Theme "))
        self.theme_combo = QComboBox()
        self.theme_combo.setEditable(True)
        self.theme_combo.addItems(_THEMES)
        self.theme_combo.setToolTip("Beamer theme")
        self.theme_combo.currentTextChanged.connect(self._on_theme_combo)
        tb.addWidget(self.theme_combo)
        self.act_gallery = QAction("Preview…", self)
        self.act_gallery.setToolTip("Preview themes visually and pick one")
        self.act_gallery.triggered.connect(self._open_theme_gallery)
        tb.addAction(self.act_gallery)
        self.act_deco = QAction("Decorations", self, checkable=True)
        self.act_deco.setToolTip("Show the theme's title bars / footers")
        self.act_deco.toggled.connect(self._toggle_decorations)
        tb.addAction(self.act_deco)

        # Formatting controls continue on the same single horizontal bar.
        tb.addSeparator()
        ftb = tb
        self._fmt_tb = ftb

        ftb.addWidget(QLabel(" Font "))
        self.fmt_font = QSpinBox(); self.fmt_font.setRange(6, 160)
        self.fmt_font.setToolTip("Font size (pt)")
        self.fmt_font.valueChanged.connect(self._apply_text_format)
        ftb.addWidget(self.fmt_font)

        self.act_bold = QAction(icons.bold(), "Bold", self, checkable=True)
        self.act_bold.triggered.connect(self._apply_text_format)
        self.act_italic = QAction(icons.italic(), "Italic", self, checkable=True)
        self.act_italic.triggered.connect(self._apply_text_format)
        ftb.addAction(self.act_bold); ftb.addAction(self.act_italic)
        self._themed_icons += [(self.act_bold, icons.bold),
                               (self.act_italic, icons.italic)]
        ftb.addSeparator()

        self._align_group = QActionGroup(self)
        self._align_actions = {}
        for key, factory, tip in (("left", icons.align_left, "Align left"),
                                  ("center", icons.align_center, "Centre"),
                                  ("right", icons.align_right, "Align right")):
            a = QAction(factory(), tip, self, checkable=True)
            a.triggered.connect(lambda _=False, k=key: self._set_align(k))
            self._align_group.addAction(a); ftb.addAction(a)
            self._align_actions[key] = a
            self._themed_icons.append((a, factory))
        ftb.addSeparator()

        tc_factory = lambda: icons._glyph_icon("A", color=QColor("#1a6dd8"))
        fill_factory = lambda: icons._glyph_icon("█", color=QColor("#d96b00"))
        self.act_textcolor = QAction(tc_factory(), "Text colour", self)
        self.act_textcolor.triggered.connect(lambda: self._pick_obj_color("color"))
        self.act_fill = QAction(fill_factory(), "Fill colour", self)
        self.act_fill.triggered.connect(lambda: self._pick_obj_color("fill"))
        ftb.addAction(self.act_textcolor); ftb.addAction(self.act_fill)
        self._themed_icons += [(self.act_textcolor, tc_factory),
                               (self.act_fill, fill_factory)]
        ftb.addSeparator()

        a_bul = ftb.addAction(icons.bullet_list(), "Insert bullet list",
                              self._insert_bullets)
        a_num = ftb.addAction(icons.numbered_list(), "Insert numbered list",
                              self._insert_numbered)
        self._themed_icons += [(a_bul, icons.bullet_list),
                               (a_num, icons.numbered_list)]
        ftb.addSeparator()

        self.act_pic = QAction(icons.image_box(), "Replace image…", self)
        self.act_pic.triggered.connect(self._pick_image)
        ftb.addAction(self.act_pic)
        self._themed_icons.append((self.act_pic, icons.image_box))

        self._enable_format(False)

    def _build_slide_toolbar(self):
        """Vertical toolbar on the left edge: slide management, object
        insertion and z-order — everything that adds or arranges content."""
        tb = QToolBar("Insert & arrange")
        tb.setIconSize(QSize(24, 24))
        tb.setMovable(False)
        self.addToolBar(Qt.LeftToolBarArea, tb)

        def vact(factory, text, slot):
            a = tb.addAction(factory(), text, slot)
            self._themed_icons.append((a, factory))
            return a

        # Slides
        vact(icons.slide_add, "Add slide", self._add_slide)
        vact(icons.slide_remove, "Remove active slide", self._del_slide)
        vact(icons.move_up, "Move slide up", lambda: self._move_slide(-1))
        vact(icons.move_down, "Move slide down", lambda: self._move_slide(1))
        tb.addSeparator()
        # Insert objects (moved here from the horizontal toolbar)
        vact(icons.text_box, "Add text box", self._add_text)
        vact(icons.image_box, "Add image", self._add_picture)
        vact(icons.table, "Add table", self._add_table)
        vact(icons.math_block, "Add equation", self._add_equation)
        vact(icons.symbol, "Insert symbol…", self._insert_symbol)
        vact(icons.drawing, "Add drawing", self._add_drawing)
        vact(icons.line_tool, "Add line", self._add_line)
        vact(icons.arrow_tool, "Add arrow", self._add_arrow)
        tb.addSeparator()
        # Z-order
        vact(icons.raise_box, "Raise object", lambda: self._zorder("raise"))
        vact(icons.lower_box, "Lower object", lambda: self._zorder("lower"))
        vact(icons.to_front, "Bring to front", lambda: self._zorder("front"))
        vact(icons.to_back, "Send to back", lambda: self._zorder("back"))
        tb.addSeparator()
        vact(icons.delete_box, "Delete object", self._delete_selected)

    def _add_line(self):
        self.slide.objects.append(SlideLine())
        self._reload_scene()
        self._select_last()
        self._touch_current()

    def _add_arrow(self):
        self.slide.objects.append(SlideLine(arrow_end=True))
        self._reload_scene()
        self._select_last()
        self._touch_current()

    def _enable_format(self, on, is_text=True, is_pic=False):
        for w in (self.fmt_font, self.act_bold, self.act_italic,
                  self.act_textcolor, self.act_fill, *self._align_actions.values()):
            w.setEnabled(on and is_text)
        self.act_pic.setEnabled(on and is_pic)

    # ---------------- layout ----------------
    def _build_ui(self):
        self.nav = SlideNavigator()
        self.nav.slideSelected.connect(self._on_slide_changed)
        self.nav.slidesReordered.connect(self._on_reorder)
        self.nav.slideMenuRequested.connect(self._slide_context_menu)

        nav_panel = QWidget()
        self._nav_panel = nav_panel
        nv = QVBoxLayout(nav_panel); nv.setContentsMargins(4, 4, 4, 4)
        nv.addWidget(QLabel("Slides"))
        nv.addWidget(self.nav)

        self.scene = SlideScene(self.deck.aspect)
        self.scene.selectionChanged.connect(self._on_selection)
        self.view = SlideView(self.scene)
        self.view.imageDropped.connect(self._on_image_dropped)
        self.view.deleteRequested.connect(self._delete_selected)
        self.view.contextMenuRequested.connect(self._canvas_context_menu)
        # The grey "desk" + white page are painted in SlideScene.drawBackground;
        # we must NOT set a view backgroundBrush here, or the view stops
        # delegating to the scene and the page never gets drawn.
        self.view.setFrameShape(QGraphicsView.NoFrame)

        # Inline header above the slide: frame title (this slide) + the
        # presentation title and author — editable without the menus.
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 4, 8, 4)
        self.f_frame_title = QLineEdit()
        self.f_frame_title.setPlaceholderText("Frame title (this slide)")
        self.f_frame_title.editingFinished.connect(self._apply_frame_title)
        self.f_deck_title = QLineEdit()
        self.f_deck_title.setPlaceholderText("Presentation title")
        self.f_deck_title.editingFinished.connect(self._apply_deck_title)
        self.f_deck_author = QLineEdit()
        self.f_deck_author.setPlaceholderText("Author")
        self.f_deck_author.editingFinished.connect(self._apply_deck_author)
        hl.addWidget(QLabel("Frame:"))
        hl.addWidget(self.f_frame_title, 3)
        hl.addWidget(QLabel("Title:"))
        hl.addWidget(self.f_deck_title, 2)
        hl.addWidget(QLabel("Author:"))
        hl.addWidget(self.f_deck_author, 2)

        canvas_box = QWidget()
        cv = QVBoxLayout(canvas_box)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cv.addWidget(header)
        cv.addWidget(self.view, 1)

        wysiwyg = QSplitter(Qt.Horizontal)
        wysiwyg.addWidget(nav_panel)
        wysiwyg.addWidget(canvas_box)
        wysiwyg.setStretchFactor(1, 1)
        wysiwyg.setSizes([220, 760])

        # LEFT tabs: the WYSIWYG (default) and the live LaTeX source.
        self.latex_view = LatexView()
        self.latex_view._edit.setReadOnly(True)
        self.latex_view.set_dark(self._dark, self._theme)
        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(wysiwyg, "WYSIWYG")
        self.left_tabs.addTab(self.latex_view, "LaTeX")
        self.left_tabs.setCurrentIndex(0)

        # RIGHT tabs: the PDF preview (default) and the compiler Console.
        self.console = QPlainTextEdit(); self.console.setReadOnly(True)
        cf = QFont("Consolas"); cf.setStyleHint(QFont.Monospace); cf.setPointSize(10)
        self.console.setFont(cf)
        self.pdf_view = PdfPreview()
        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self.pdf_view, "PDF")
        self.right_tabs.addTab(self.console, "Console")
        self.right_tabs.setCurrentIndex(0)

        main = QSplitter(Qt.Horizontal)
        main.addWidget(self.left_tabs)
        main.addWidget(self.right_tabs)
        main.setStretchFactor(0, 1); main.setStretchFactor(1, 1)
        main.setSizes([800, 560])
        self.setCentralWidget(main)
        self.statusBar().showMessage(
            "Double-click to edit • while editing, Ctrl+B / Ctrl+I "
            "bold/italicise the selection")

    # ---------------- reload ----------------
    @property
    def slide(self) -> Slide:
        return self.deck.slides[self.current]

    def _reload_all(self):
        self.act_deco.blockSignals(True)
        self.act_deco.setChecked(not self.deck.plain_frames)
        self.act_deco.blockSignals(False)
        self.act_nav.blockSignals(True)
        self.act_nav.setChecked(self.deck.nav_symbols)
        self.act_nav.blockSignals(False)
        mode = getattr(self.deck, "page_number", "none")
        self._pgnum_actions.get(mode, self._pgnum_actions["none"]).setChecked(True)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentText(self.deck.theme)
        self.theme_combo.blockSignals(False)
        self.nav.refresh(self.deck, self.current)
        self._reload_scene()

    def _reload_scene(self):
        self._cancel_edit()
        self._loading = True
        self._items = []
        pw, ph, self._font_scale = page_size_px(
            self.deck.aspect, self.deck.page_w_cm, self.deck.page_h_cm)
        self.scene.set_page(pw, ph, self.deck.gap)
        self.scene.page_color = (blend_over_white(self.slide.bg,
                                                  self.slide.bg_alpha)
                                 if self.slide.bg else "#FFFFFF")
        # Silence selectionChanged while clearing — otherwise it fires with
        # the just-deleted items still referenced.
        self.scene.blockSignals(True)
        self.scene.clear()
        self.scene.blockSignals(False)
        for obj in self.slide.objects:
            item = make_item(obj, pw, ph, self.deck.gap, self._font_scale)
            item.geometryChanged.connect(self._on_item_geometry)
            item.lockToggled.connect(self._on_lock_toggled)
            if isinstance(item, TableBoxItem):
                item.cellDoubleClicked.connect(
                    lambda r, c, it=item: self._edit_table_cell(it, r, c))
            else:
                item.doubleClicked.connect(
                    lambda it=item: self._on_double_click(it))
            self.scene.addItem(item)
            self._items.append(item)
        if self.view.fit_mode:
            self.view.fit_to_window()
        self._enable_format(False)
        self._sync_top_fields()
        self._loading = False
        self._refresh_latex()

    def _sync_top_fields(self):
        if not hasattr(self, "f_frame_title"):
            return
        for widget, val in ((self.f_frame_title, self.slide.title),
                            (self.f_deck_title, self.deck.title),
                            (self.f_deck_author, self.deck.author)):
            widget.blockSignals(True)
            widget.setText(val)
            widget.blockSignals(False)

    def _apply_frame_title(self):
        if not self._loading and self.slide.title != self.f_frame_title.text():
            self.slide.title = self.f_frame_title.text()
            self._touch_current()

    def _apply_deck_title(self):
        if not self._loading and self.deck.title != self.f_deck_title.text():
            self.deck.title = self.f_deck_title.text()
            self._refresh_latex()

    def _apply_deck_author(self):
        if not self._loading and self.deck.author != self.f_deck_author.text():
            self.deck.author = self.f_deck_author.text()
            self._refresh_latex()

    def _refresh_latex(self):
        self.latex_view.set_source(serialize_deck(self.deck))
        self._schedule_compile()
        if not self._loading and not self._restoring:
            self._undo_timer.start()   # debounced snapshot for undo

    # ---------------- undo / redo ----------------
    def _reset_history(self):
        self._history = [deck_to_json(self.deck)]
        self._hist_index = 0
        self._update_undo_actions()

    def _capture_state(self):
        if self._restoring:
            return
        cur = deck_to_json(self.deck)
        if self._history and cur == self._history[self._hist_index]:
            return
        del self._history[self._hist_index + 1:]      # drop redo tail
        self._history.append(cur)
        if len(self._history) > 200:                  # cap memory
            self._history.pop(0)
        self._hist_index = len(self._history) - 1
        self._update_undo_actions()

    def _flush_pending_capture(self):
        if self._undo_timer.isActive():
            self._undo_timer.stop()
            self._capture_state()

    def _undo(self):
        self._flush_pending_capture()
        if self._hist_index > 0:
            self._hist_index -= 1
            self._restore(self._history[self._hist_index])

    def _redo(self):
        self._flush_pending_capture()
        if self._hist_index < len(self._history) - 1:
            self._hist_index += 1
            self._restore(self._history[self._hist_index])

    def _restore(self, snapshot):
        self._restoring = True
        try:
            self.deck = deck_from_json(snapshot)
            if not self.deck.slides:
                self.deck.slides = [Slide()]
            self.current = min(self.current, len(self.deck.slides) - 1)
            self._reload_all()
        finally:
            self._restoring = False
        self._update_undo_actions()
        if tectonic_available():
            self._auto_timer.stop()
            self._start_compile()

    def _update_undo_actions(self):
        if hasattr(self, "act_undo"):
            self.act_undo.setEnabled(self._hist_index > 0)
            self.act_redo.setEnabled(self._hist_index < len(self._history) - 1)

    def _update_title(self):
        name = self.path.name if self.path else "Untitled"
        self.setWindowTitle(f"KherveSlide {version_string()} — {name}")

    # ---------------- auto-compile ----------------
    def _schedule_compile(self):
        """Debounce: (re)start the timer so a compile fires shortly after
        the last change. Skipped while bulk-loading."""
        if not self._loading and tectonic_available():
            self._auto_timer.start()

    def _start_compile(self):
        if not tectonic_available():
            return
        # Guard on "a worker object exists" — not isRunning(), which is
        # still False in the gap between start() and the thread actually
        # entering run(); replacing the worker in that gap GC's it mid-run.
        if self._worker is not None:
            self._compile_pending = True   # coalesce: run again when done
            return
        tex = serialize_deck(self.deck)
        workdir = Path(tempfile.gettempdir()) / "kherveslide_build"
        src_dir = self.path.parent if self.path else None
        self.statusBar().showMessage("Compiling…")
        worker = _CompileWorker(tex, workdir, src_dir)
        worker.done.connect(self._on_compiled)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    @staticmethod
    def _clean_log(log):
        # Drop the harmless, scary-looking xdvipdfmx/fontconfig warning on
        # Windows (no fontconfig config file) — it doesn't affect output.
        return "\n".join(
            ln for ln in (log or "").splitlines()
            if "Fontconfig error" not in ln)

    def _on_compiled(self, result):
        self.console.setPlainText(self._clean_log(result.log))
        if result.ok and result.pdf_path:
            self.pdf_view.show_pdf(Path(result.pdf_path))
            self.statusBar().showMessage("Compiled OK")
        else:
            self.statusBar().showMessage("Compile failed — see Console tab")

    def _on_worker_finished(self):
        # Runs after the thread's run() has returned, so it's safe to drop
        # the reference here (never inside the cross-thread done handler).
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if self._compile_pending:
            self._compile_pending = False
            self._start_compile()

    # ---------------- offline package download ----------------
    def _maybe_autodownload_packages(self):
        """On first launch, pre-fetch the TeX packages in the background so
        compiling is fast and works offline — done by default, once."""
        settings = QSettings("kherveDOC", "KherveSlide")
        # v2 key: the v1 download used a generic bundle that missed beamer
        # themes/textpos/tikz, so re-warm with the KherveSlide-specific set.
        if settings.value("offline_packages_v2", False, type=bool):
            return
        if not tectonic_available():
            return
        self._download_packages(auto=True)

    def _download_packages(self, auto=False):
        if self._dl_worker is not None:
            return
        if not tectonic_available():
            QMessageBox.warning(self, "Download", "tectonic is not available.")
            return
        self.console.appendPlainText(
            "Pre-downloading LaTeX packages for fast offline compiling…")
        if not auto:
            self.right_tabs.setCurrentWidget(self.console)
        self.statusBar().showMessage("Downloading LaTeX packages…")
        self._dl_worker = _DownloadWorker()
        self._dl_worker.line.connect(self.console.appendPlainText)
        self._dl_worker.done.connect(self._on_download_done)
        self._dl_worker.finished.connect(self._on_dl_finished)
        self._dl_worker.start()

    def _on_download_done(self, ok):
        self.statusBar().showMessage(
            "LaTeX packages ready (offline)" if ok else "Package download failed")
        if ok:
            QSettings("kherveDOC", "KherveSlide").setValue(
                "offline_packages_v2", True)

    def _on_dl_finished(self):
        worker = self._dl_worker
        self._dl_worker = None
        if worker is not None:
            worker.deleteLater()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.view.fit_mode:
            self.view.fit_to_window()

    def closeEvent(self, event):
        # Don't tear down while a worker thread is still running.
        self._auto_timer.stop()
        if self._worker is not None:
            self._worker.wait(4000)
        if self._dl_worker is not None:
            self._dl_worker.wait(2000)
        super().closeEvent(event)

    # ---------------- in-place editing ----------------
    def _on_double_click(self, item):
        if isinstance(item, TextBoxItem):
            self._edit_text_item(item)
        elif isinstance(item, PictureBoxItem):
            self._edit_picture(item)

    def _edit_picture(self, item=None):
        item = item or self._selected_item()
        if item is None or not isinstance(item.obj, SlidePicture):
            return
        from .picture_editor import PictureEditDialog
        dlg = PictureEditDialog(item.obj, self)
        if not dlg.exec():
            return
        o = item.obj
        o.path = dlg.path
        o.crop_l, o.crop_t, o.crop_r, o.crop_b = dlg.crop
        o.rotation = dlg.rotation
        item._pix_path = None        # force pixmap reload if path changed
        item.update()
        self._touch_current()

    def _rotate_selected(self, delta):
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlidePicture):
            return
        a = (getattr(item.obj, "rotation", 0.0) + delta) % 360
        item.obj.rotation = a - 360 if a > 180 else a
        item.update()
        self._touch_current()

    def _begin_inline_edit(self, rect, initial, *, font_pt, commit):
        """Float a *rich* editor over *rect* (lists show as real bullets,
        not \\item source); on focus-out call commit(latex)."""
        self._cancel_edit()
        editor = _InlineEditor()
        f = QFont("Helvetica")
        f.setPixelSize(max(8, int(font_pt * self._font_scale)))
        editor.setFont(f)
        editor.setHtml(latex_to_html(initial))
        editor.setStyleSheet(
            "QTextEdit { background: rgba(255,255,255,235);"
            " border: 1px solid #2878dc; }")
        proxy = self.scene.addWidget(editor)
        proxy.setGeometry(rect)
        proxy.setZValue(1e6)
        self._edit_proxy = proxy
        self._edit_commit = commit
        editor.editingFinished.connect(self._finish_edit)
        editor.setFocus()
        editor.selectAll()

    def _edit_text(self):
        """The rich editor's current content, converted back to LaTeX."""
        return document_to_latex(self._edit_proxy.widget().document())

    def _edit_text_item(self, item):
        self._begin_inline_edit(
            item.scene_rect(), item.obj.text, font_pt=item.obj.font_pt,
            commit=lambda t: self._commit_obj_text(item, t))

    def _commit_obj_text(self, item, text):
        item.obj.text = text
        item.update()
        item.setSelected(True)

    # ---------------- insert into text ----------------
    def _insert_into_text(self, latex):
        """Insert LaTeX where it makes sense: at the cursor if a box is
        being edited, else into the selected text box, else a new box."""
        if self._edit_proxy is not None:
            self._edit_proxy.widget().insertPlainText(latex)
            return
        item = self._selected_item()
        if item is not None and isinstance(item.obj, SlideText):
            item.obj.text += latex
            item.update()
            self._touch_current()
        else:
            self.slide.objects.append(SlideText(text=latex))
            self._reload_scene()
            self._select_last()
            self._touch_current()

    def _insert_bullets(self):
        self._make_list(QTextListFormat.ListDisc,
                        "\\begin{itemize}\n  \\item First point\n"
                        "  \\item Second point\n\\end{itemize}")

    def _insert_numbered(self):
        self._make_list(QTextListFormat.ListDecimal,
                        "\\begin{enumerate}\n  \\item First point\n"
                        "  \\item Second point\n\\end{enumerate}")

    def _make_list(self, style, template):
        # When editing a box, turn the current line into a real list (so
        # you type items and see bullets); otherwise drop in a new box.
        if self._edit_proxy is not None:
            self._edit_proxy.widget().textCursor().createList(style)
        else:
            self._insert_into_text(template)

    def _insert_symbol(self):
        from .symbol_palette import SymbolPalette
        dlg = SymbolPalette(self)
        if dlg.exec() and dlg.chosen:
            self._insert_into_text(f"${dlg.chosen}$")

    def _edit_table_cell(self, item, r, c):
        rows = item.obj.rows
        cur = rows[r][c] if c < len(rows[r]) else ""
        self._begin_inline_edit(
            item.cell_scene_rect(r, c), cur, font_pt=item.obj.font_pt,
            commit=lambda t: self._commit_cell(item, r, c, t))

    def _commit_cell(self, item, r, c, text):
        item.obj.rows[r][c] = text
        item.update()
        item.setSelected(True)

    def _finish_edit(self):
        if self._edit_proxy is None:
            return
        proxy = self._edit_proxy
        commit = self._edit_commit
        text = document_to_latex(proxy.widget().document())
        # Clear state first so the removal's focus change can't re-enter.
        self._edit_proxy = None
        self._edit_commit = None
        self.scene.removeItem(proxy)
        if commit is not None:
            commit(text)
        self._touch_current()

    def _cancel_edit(self):
        # Removing a still-focused embedded editor aborts Qt, so drop its
        # focus (and the scene's focus item) and disconnect its signal
        # first. Clearing _edit_proxy up front also makes any re-entrant
        # editingFinished a no-op.
        proxy = self._edit_proxy
        if proxy is None:
            return
        self._edit_proxy = None
        self._edit_commit = None
        editor = proxy.widget()
        if editor is not None:
            try:
                editor.editingFinished.disconnect()
            except (RuntimeError, TypeError):
                pass
            editor.clearFocus()
        if self.scene.focusItem() is proxy:
            self.scene.setFocusItem(None)
        self.scene.removeItem(proxy)

    def _pick_image_for(self, item):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", "",
            "Images (*.png *.jpg *.jpeg *.pdf *.gif *.bmp)")
        if path:
            item.obj.path = path
            item.update()
            self._touch_current()

    # ---------------- slides ----------------
    def _on_slide_changed(self, row):
        if self._loading or not (0 <= row < len(self.deck.slides)):
            return
        self.current = row
        self._reload_scene()
        # Jump the PDF preview to the matching page (each slide is one page).
        self.pdf_view.go_to_page(row)

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

    def _move_slide(self, delta):
        j = self.current + delta
        if 0 <= j < len(self.deck.slides):
            s = self.deck.slides
            s[self.current], s[j] = s[j], s[self.current]
            self.current = j
            self._reload_all()

    def _slide_context_menu(self, row, global_pos):
        if not (0 <= row < len(self.deck.slides)):
            return
        menu = QMenu(self)
        lay = menu.addMenu("Apply layout to this slide")
        for name in templates.slide_layout_names():
            lay.addAction(name, lambda n=name, r=row: self._apply_layout(r, n))
        menu.addSeparator()
        menu.addAction("Duplicate slide", lambda: self._duplicate_slide(row))
        menu.addAction("New blank slide after",
                       lambda: self._new_slide_after(row))
        menu.addAction("Delete slide", lambda: self._delete_slide_at(row))
        menu.exec(global_pos)

    def _apply_layout(self, row, name):
        layout = templates.instantiate_slide_layout(name)
        self.deck.slides[row] = layout
        self.current = row
        self._reload_all()

    def _duplicate_slide(self, row):
        import copy
        self.deck.slides.insert(row + 1, copy.deepcopy(self.deck.slides[row]))
        self.current = row + 1
        self._reload_all()

    def _new_slide_after(self, row):
        self.deck.slides.insert(row + 1, Slide())
        self.current = row + 1
        self._reload_all()

    def _delete_slide_at(self, row):
        if len(self.deck.slides) <= 1:
            return
        del self.deck.slides[row]
        self.current = min(row, len(self.deck.slides) - 1)
        self._reload_all()

    def _touch_current(self):
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

    def _on_image_dropped(self, path, scene_pos):
        """An image file was dragged onto the canvas — place a picture box
        centred on the drop point."""
        g = self.scene.gap
        cw = (1 - 2 * g) * self.scene.page_w
        ch = (1 - 2 * g) * self.scene.page_h
        ox, oy = g * self.scene.page_w, g * self.scene.page_h
        w = h = 0.3
        x = (scene_pos.x() - ox) / cw - w / 2
        y = (scene_pos.y() - oy) / ch - h / 2
        x = max(0.0, min(1 - w, x))
        y = max(0.0, min(1 - h, y))
        self.slide.objects.append(SlidePicture(
            x=round(x, 4), y=round(y, 4), w=w, h=h, path=path,
            keep_aspect=True))
        self._reload_scene()
        self._select_last()
        self._touch_current()

    def _add_table(self):
        self.slide.objects.append(SlideTable())
        self._reload_scene()
        self._select_last()
        self._touch_current()

    def _add_equation(self):
        from .equation_editor import EquationEditorDialog
        dlg = EquationEditorDialog(self)
        if dlg.exec() and dlg.latex():
            obj = SlideText(text=f"${dlg.latex()}$", font_pt=28,
                            align="center")
            self.slide.objects.append(obj)
            self._reload_scene()
            self._select_last()
            self._touch_current()

    def _add_drawing(self):
        images_dir = (self.path.parent if self.path
                      else Path(tempfile.gettempdir()) / "kherveslide_drawings")
        dlg = DrawingDialog(images_dir, self)
        dlg.drawingSaved.connect(self._on_drawing_saved)
        dlg.exec()

    def _on_drawing_saved(self, png_path):
        self.slide.objects.append(
            SlidePicture(path=png_path, w=0.4, h=0.4, keep_aspect=True))
        self._reload_scene()
        self._select_last()
        self._touch_current()

    def _table_op(self, op):
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlideTable):
            self.statusBar().showMessage("Select a table first")
            return
        rows = item.obj.rows
        ncols = max((len(r) for r in rows), default=1)
        if op == "add_row":
            rows.append([""] * ncols)
        elif op == "add_col":
            for r in rows:
                r.append("")
        elif op == "del_row" and len(rows) > 1:
            rows.pop()
        elif op == "del_col" and ncols > 1:
            for r in rows:
                if len(r) > 1:
                    r.pop()
        elif op == "header":
            item.obj.header = not item.obj.header
        elif op == "caption":
            text, ok = QInputDialog.getText(self, "Table caption", "Caption:",
                                            text=item.obj.caption)
            if not ok:
                return
            item.obj.caption = text
        self._reload_scene()
        if self._items:
            self._items[self.slide.objects.index(item.obj)].setSelected(True)
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
            try:
                if it.isSelected():
                    return it
            except RuntimeError:
                # The underlying C++ item was deleted (e.g. a stale entry
                # during a scene rebuild) — skip it rather than crash.
                continue
        return None

    # ---------------- clipboard: copy / cut / paste / duplicate ----------
    _OBJ_MIME = "application/x-kherveslide-objects"

    def _copy_selected(self):
        item = self._selected_item()
        if item is None:
            return
        data = json.dumps([object_to_dict(item.obj)]).encode("utf-8")
        md = QMimeData()
        md.setData(self._OBJ_MIME, QByteArray(data))
        QApplication.clipboard().setMimeData(md)
        self.statusBar().showMessage("Copied")

    def _cut_selected(self):
        if self._selected_item() is not None:
            self._copy_selected()
            self._delete_selected()

    def _duplicate_selected(self):
        item = self._selected_item()
        if item is None:
            return
        self._add_object(build_object(object_to_dict(item.obj)), offset=True)

    def _can_paste(self):
        md = QApplication.clipboard().mimeData()
        return bool(md and (md.hasFormat(self._OBJ_MIME) or md.hasImage()
                            or _dropped_image(md)))

    def _paste(self, scene_pos=None):
        if not isinstance(scene_pos, QPointF):   # menu/shortcut pass a bool
            scene_pos = None
        cb = QApplication.clipboard()
        md = cb.mimeData()
        if md.hasFormat(self._OBJ_MIME):
            try:
                objs = json.loads(bytes(md.data(self._OBJ_MIME)).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return
            last = None
            for d in objs:
                last = build_object(d)
                self._offset(last)
                self.slide.objects.append(last)
            self._reload_scene()
            self._select_last()
            self._touch_current()
            return
        img = cb.image()
        if img is not None and not img.isNull():
            path = self._save_clipboard_image(img)
            if path:
                if scene_pos is None:
                    scene_pos = QPointF(self.scene.page_w / 2,
                                        self.scene.page_h / 2)
                self._on_image_dropped(path, scene_pos)
            return
        path = _dropped_image(md)
        if path:
            self._on_image_dropped(
                path, scene_pos or QPointF(self.scene.page_w / 2,
                                           self.scene.page_h / 2))

    def _add_object(self, obj, offset=False):
        if offset:
            self._offset(obj)
        self.slide.objects.append(obj)
        self._reload_scene()
        self._select_last()
        self._touch_current()

    @staticmethod
    def _offset(obj):
        if hasattr(obj, "x"):
            obj.x = round(min(0.92, obj.x + 0.03), 4)
            obj.y = round(min(0.92, obj.y + 0.03), 4)

    def _save_clipboard_image(self, img):
        base = (self.path.parent if self.path
                else Path(tempfile.gettempdir()) / "kherveslide_pasted")
        base.mkdir(parents=True, exist_ok=True)
        i = 1
        while True:
            p = base / f"pasted_{i:03d}.png"
            if not p.exists():
                break
            i += 1
        img.save(str(p), "PNG")
        return str(p)

    # ---------------- canvas right-click menu ----------------
    def _canvas_context_menu(self, global_pos, scene_pos):
        menu = QMenu(self)
        item = self._selected_item()
        if item is not None:
            menu.addAction("Copy", self._copy_selected)
            menu.addAction("Cut", self._cut_selected)
            menu.addAction("Duplicate", self._duplicate_selected)
            menu.addAction("Delete", self._delete_selected)
            menu.addSeparator()
            locked = getattr(item.obj, "locked", True)
            lk = menu.addAction("Locked (beamer places it)")
            lk.setCheckable(True)
            lk.setChecked(locked)
            lk.setToolTip("Locked: beamer lays the box out. "
                          "Unlocked: drag it anywhere on the slide.")
            lk.toggled.connect(self._set_selected_locked)
            menu.addSeparator()
            menu.addAction("Bring to front", lambda: self._zorder("front"))
            menu.addAction("Send to back", lambda: self._zorder("back"))
            if isinstance(item.obj, SlidePicture):
                menu.addSeparator()
                menu.addAction("Crop && rotate…", self._edit_picture)
                menu.addAction("Rotate left 90°",
                               lambda: self._rotate_selected(-90))
                menu.addAction("Rotate right 90°",
                               lambda: self._rotate_selected(90))
                lock = menu.addAction("Lock aspect ratio")
                lock.setCheckable(True)
                lock.setChecked(item.obj.keep_aspect)
                lock.toggled.connect(self._toggle_pic_lock)
                menu.addAction("Transparency…", self._set_pic_opacity)
                menu.addAction("Replace image…", self._pick_image)
            menu.addSeparator()
        paste = menu.addAction("Paste", lambda: self._paste(scene_pos))
        paste.setEnabled(self._can_paste())
        menu.exec(global_pos)

    def _toggle_pic_lock(self, on):
        item = self._selected_item()
        if item is not None and isinstance(item.obj, SlidePicture):
            item.obj.keep_aspect = on
            item.update()
            self._touch_current()

    def _set_pic_opacity(self):
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlidePicture):
            return
        pct, ok = QInputDialog.getInt(
            self, "Transparency", "Opacity (%):",
            int(round(item.obj.opacity * 100)), 0, 100)
        if ok:
            item.obj.opacity = pct / 100.0
            item.update()
            self._touch_current()

    # ---------------- selection → format toolbar ----------------
    def _on_selection(self):
        if self._loading:
            return
        item = self._selected_item()
        if item is None:
            self._enable_format(False)
            return
        obj = item.obj
        is_text = isinstance(obj, SlideText)
        self._enable_format(True, is_text=is_text, is_pic=not is_text)
        if is_text:
            self._loading = True
            self.fmt_font.setValue(obj.font_pt)
            self.act_bold.setChecked(obj.bold)
            self.act_italic.setChecked(obj.italic)
            self._align_actions.get(obj.align, self._align_actions["left"]).setChecked(True)
            self._loading = False

    def _on_item_geometry(self):
        # An object was dragged or resized on the canvas — keep the
        # thumbnail and live LaTeX in step.
        self._touch_current()

    def _apply_text_format(self):
        if self._loading:
            return
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlideText):
            return
        obj = item.obj
        obj.font_pt = self.fmt_font.value()
        obj.bold = self.act_bold.isChecked()
        obj.italic = self.act_italic.isChecked()
        item.update()
        self._touch_current()

    def _set_align(self, key):
        if self._loading:
            return
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlideText):
            return
        item.obj.align = key
        item.update()
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
        if isinstance(item, PictureBoxItem):
            self._pick_image_for(item)

    # ---------------- deck / slide settings (menus) ----------------
    def _set_deck_title(self):
        t, ok = QInputDialog.getText(self, "Presentation title", "Title:",
                                     text=self.deck.title)
        if ok:
            self.deck.title = t; self._sync_top_fields(); self._refresh_latex()

    def _set_deck_author(self):
        t, ok = QInputDialog.getText(self, "Author", "Author:",
                                     text=self.deck.author)
        if ok:
            self.deck.author = t; self._sync_top_fields(); self._refresh_latex()

    def _on_theme_combo(self, text):
        if self._loading or not text:
            return
        self.deck.theme = text
        self._recompile_now()

    def _open_theme_gallery(self):
        from .theme_gallery import ThemeGallery
        dlg = ThemeGallery(_THEMES, self.deck.aspect, self.deck.theme, self,
                           cache=self._theme_cache)
        if dlg.exec() and dlg.chosen:
            self.deck.theme = dlg.chosen
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentText(dlg.chosen)
            self.theme_combo.blockSignals(False)
            # Previews show decorations, so turn them on to match what was seen.
            self.deck.plain_frames = False
            self.act_deco.blockSignals(True)
            self.act_deco.setChecked(True)
            self.act_deco.blockSignals(False)
            self._recompile_now()

    def _set_colour_theme(self):
        cur = (_COLOUR_THEMES.index(self.deck.color_theme)
               if self.deck.color_theme in _COLOUR_THEMES else 0)
        t, ok = QInputDialog.getItem(self, "Colour theme", "Colour theme:",
                                     _COLOUR_THEMES, cur, True)
        if ok:
            self.deck.color_theme = t; self._recompile_now()

    def _page_setup(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Page setup")
        form = QFormLayout(dlg)
        aspect = QComboBox()
        for code in _ASPECTS:
            aspect.addItem(_ASPECT_LABELS.get(code, code), code)
        cur = _ASPECTS.index(self.deck.aspect) if self.deck.aspect in _ASPECTS else 0
        aspect.setCurrentIndex(cur)
        custom = QCheckBox("Use custom size instead of aspect ratio")
        is_custom = self.deck.page_w_cm > 0 and self.deck.page_h_cm > 0
        custom.setChecked(is_custom)
        w_cm = QDoubleSpinBox(); w_cm.setRange(1, 200); w_cm.setSuffix(" cm")
        w_cm.setValue(self.deck.page_w_cm or 12.8)
        h_cm = QDoubleSpinBox(); h_cm.setRange(1, 200); h_cm.setSuffix(" cm")
        h_cm.setValue(self.deck.page_h_cm or 9.6)
        gap = QDoubleSpinBox(); gap.setRange(0, 45); gap.setSuffix(" %")
        gap.setValue(self.deck.gap * 100)
        form.addRow("Aspect ratio", aspect)
        form.addRow(custom)
        form.addRow("Width", w_cm)
        form.addRow("Height", h_cm)
        form.addRow("Margin / gap", gap)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if not dlg.exec():
            return
        self.deck.aspect = aspect.currentData()
        if custom.isChecked():
            self.deck.page_w_cm = w_cm.value()
            self.deck.page_h_cm = h_cm.value()
        else:
            self.deck.page_w_cm = 0.0
            self.deck.page_h_cm = 0.0
        self.deck.gap = gap.value() / 100.0
        self._reload_all()
        self._recompile_now()

    def _recompile_now(self):
        """For theme/decoration changes: update LaTeX, show the PDF tab and
        compile straight away so the effect is immediately visible."""
        self._refresh_latex()
        if tectonic_available():
            self.right_tabs.setCurrentWidget(self.pdf_view)
            self._auto_timer.stop()
            self._start_compile()

    def _toggle_decorations(self, on):
        # on = show the beamer theme's title bars / footers (frames not plain)
        self.deck.plain_frames = not on
        self._recompile_now()

    def _toggle_nav_symbols(self, on):
        self.deck.nav_symbols = on
        self._recompile_now()

    def _set_page_number(self, mode):
        self.deck.page_number = mode
        self._recompile_now()

    def _on_lock_toggled(self):
        # A box was locked/unlocked from its lock badge: re-flow the LaTeX
        # and record the change for undo.
        self._touch_current()

    def _set_selected_locked(self, locked: bool):
        item = self._selected_item()
        if item is not None and getattr(item.obj, "locked", True) != locked:
            item.toggle_lock()

    def _open_theme_builder(self):
        from .theme_builder import ThemeBuilderDialog
        dlg = ThemeBuilderDialog(self.deck.theme_spec, self.deck.theme,
                                 self.deck.color_theme, self.deck.aspect, self)
        if dlg.exec() and dlg.result_spec is not None:
            self.deck.theme_spec = dlg.result_spec
            if dlg.result_spec.enabled:
                # Custom themes touch decorated elements — show them.
                self.deck.plain_frames = False
                self.act_deco.blockSignals(True)
                self.act_deco.setChecked(True)
                self.act_deco.blockSignals(False)
            self._recompile_now()

    def _set_frame_title(self):
        text, ok = QInputDialog.getText(
            self, "Frame title",
            "Title shown in the theme's title bar (decorations on):",
            text=self.slide.title)
        if ok:
            self.slide.title = text
            self._sync_top_fields()
            self._touch_current()

    def _pick_slide_bg(self):
        cur = QColor(self.slide.bg or "#FFFFFF")
        cur.setAlphaF(self.slide.bg_alpha)
        col = QColorDialog.getColor(
            cur, self, "Slide background (drag the opacity slider for a tint)",
            QColorDialog.ShowAlphaChannel)
        if col.isValid():
            self.slide.bg = col.name()          # #rrggbb
            self.slide.bg_alpha = col.alphaF()  # transparency level
            self.scene.page_color = blend_over_white(self.slide.bg,
                                                      self.slide.bg_alpha)
            self.scene.invalidate()             # repaint the page immediately
            self._touch_current()

    def _clear_slide_bg(self):
        self.slide.bg = ""
        self.slide.bg_alpha = 1.0
        self.scene.page_color = "#FFFFFF"
        self.scene.invalidate()
        self._touch_current()

    # ---------------- templates ----------------
    def _populate_templates_menu(self):
        m = self._m_tpl_new
        m.clear()
        for name in self.store.all_names():
            m.addAction(name, lambda n=name: self._new_from_template(n))

    def _new_from_template(self, name):
        self.deck = self.store.instantiate(name)
        self.current = 0
        self.path = None
        self._update_title()
        self._reload_all()
        self._reset_history()

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

    # ---------------- view ----------------
    def _toggle_navigator(self, show):
        self._nav_panel.setVisible(show)

    def _toggle_spellcheck(self, on):
        _InlineEditor.spellcheck_enabled = on
        QSettings("kherveDOC", "KherveSlide").setValue(
            "spellcheck_enabled", on)

    def _refresh_icons(self):
        """Recolour every toolbar/menu icon for the current light/dark theme."""
        for action, factory in self._themed_icons:
            try:
                action.setIcon(factory())
            except RuntimeError:
                pass            # action was deleted

    def _apply_named_theme(self, name):
        """Switch the application's appearance theme live and remember it."""
        app = QApplication.instance()
        t = themes.apply_theme(app, name)
        self._theme = t
        self._theme_name = name
        self._dark = themes.is_dark(name)
        icons.set_dark(self._dark)
        self._refresh_icons()
        self.latex_view.set_dark(self._dark, t)
        QSettings("kherveDOC", "KherveSlide").setValue("theme_name", name)
        act = self._theme_actions.get(name)
        if act is not None and not act.isChecked():
            act.setChecked(True)
        self.statusBar().showMessage(f"Theme: {name}", 3000)

    def _open_file_location(self):
        if self.path is None:
            QMessageBox.information(
                self, "Open file location",
                "Save the presentation first — it has no file yet.")
            return
        target = Path(self.path).resolve()
        try:
            if sys.platform == "win32":
                # /select highlights the file in a new Explorer window.
                subprocess.run(["explorer", "/select,", str(target)])
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", str(target)])
            else:
                subprocess.run(["xdg-open", str(target.parent)])
        except OSError as e:
            QMessageBox.warning(self, "Open file location", str(e))

    # ---------------- compile / IO ----------------
    def _export_pdf(self):
        if not tectonic_available():
            QMessageBox.warning(
                self, "Export PDF",
                "tectonic is not available, so the PDF cannot be built.")
            return
        default = (str(self.path.with_suffix(".pdf")) if self.path
                   else "presentation.pdf")
        out, _ = QFileDialog.getSaveFileName(
            self, "Export PDF", default, "PDF document (*.pdf)")
        if not out:
            return
        self.statusBar().showMessage("Exporting PDF…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            workdir = Path(tempfile.gettempdir()) / "kherveslide_export"
            src_dir = self.path.parent if self.path else None
            result = compile_tex(serialize_deck(self.deck), workdir,
                                 basename="presentation", source_dir=src_dir)
        finally:
            QApplication.restoreOverrideCursor()
        if result.ok and result.pdf_path:
            try:
                shutil.copyfile(result.pdf_path, out)
            except OSError as e:
                QMessageBox.warning(self, "Export PDF", str(e))
                return
            self.statusBar().showMessage(f"Exported PDF to {out}")
        else:
            self.console.setPlainText(self._clean_log(result.log))
            self.right_tabs.setCurrentWidget(self.console)
            self.statusBar().showMessage("PDF export failed — see Console tab")
            QMessageBox.warning(
                self, "Export PDF",
                "Compilation failed; see the Console tab for the log.")

    def _compile(self):
        """Manual compile — force it now and show the PDF."""
        self.latex_view.set_source(serialize_deck(self.deck))
        if not tectonic_available():
            self.console.setPlainText("tectonic is not available on this system.")
            self.right_tabs.setCurrentWidget(self.console)
            return
        self.right_tabs.setCurrentWidget(self.pdf_view)
        self._auto_timer.stop()
        self._start_compile()

    def _new_deck(self):
        self.deck = templates.instantiate_builtin("Blank")
        self.current = 0
        self.path = None
        self._update_title()
        self._reload_all()
        self._reset_history()

    def _save_deck(self):
        if self.path is None:
            return self._save_deck_as()
        self.path.write_text(deck_to_json(self.deck), encoding="utf-8")
        self._add_recent(self.path)
        self.statusBar().showMessage(f"Saved {self.path}")

    def _save_deck_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save presentation as", "",
            "KherveSlide presentation (*.kslide)")
        if not path:
            return
        self.path = Path(path)
        self.path.write_text(deck_to_json(self.deck), encoding="utf-8")
        self._add_recent(self.path)
        self._update_title()
        self.statusBar().showMessage(f"Saved {path}")

    def _open_deck(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open presentation", "",
            "KherveSlide presentation (*.kslide *.kslide.json *.json)")
        if path:
            self.open_path(path)

    def open_path(self, path):
        """Open a presentation file (shared by Open, Open recent, CLI)."""
        p = Path(path)
        if not p.exists():
            QMessageBox.warning(self, "Open", f"File not found:\n{path}")
            self._forget_recent(p)
            return
        try:
            self.deck = deck_from_json(p.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Open", str(e))
            return
        if not self.deck.slides:
            self.deck.slides = [Slide()]
        self.path = p
        self.current = 0
        self._add_recent(p)
        self._update_title()
        self._reload_all()
        self._reset_history()

    # ---------------- recent files ----------------
    _RECENT_KEY = "recent_files"
    _RECENT_MAX = 20

    def _recent_files(self) -> list[str]:
        val = QSettings("kherveDOC", "KherveSlide").value(self._RECENT_KEY, [])
        if val is None:
            return []
        if isinstance(val, str):
            val = [val]
        return [str(p) for p in val]

    def _set_recent_files(self, files):
        QSettings("kherveDOC", "KherveSlide").setValue(self._RECENT_KEY, files)

    def _add_recent(self, path):
        p = str(Path(path))
        files = [f for f in self._recent_files() if f != p]
        files.insert(0, p)
        del files[self._RECENT_MAX:]
        self._set_recent_files(files)

    def _forget_recent(self, path):
        p = str(Path(path))
        self._set_recent_files([f for f in self._recent_files() if f != p])

    def _populate_recent_menu(self):
        m = self._recent_menu
        m.clear()
        files = self._recent_files()
        if not files:
            act = m.addAction("(no recent files)")
            act.setEnabled(False)
            return
        for p in files:
            act = m.addAction(Path(p).name)
            act.setToolTip(p)
            act.triggered.connect(lambda _=False, path=p: self.open_path(path))
        m.addSeparator()
        m.addAction("Clear recent files",
                    lambda: self._set_recent_files([]))

    def _export_tex(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export LaTeX", "",
                                              "LaTeX (*.tex)")
        if not path:
            return
        Path(path).write_text(serialize_deck(self.deck), encoding="utf-8")
        self.statusBar().showMessage(f"Exported {path}")
