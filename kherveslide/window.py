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
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QByteArray, QEvent, QMimeData, QPointF, QSettings, QSize, QThread, QTimer,
    Qt, Signal,
)
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QFont, QPixmap, QTextCharFormat,
    QTextListFormat, QTransform,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGraphicsView, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QTextEdit, QToolBar,
    QToolButton, QVBoxLayout, QWidget,
)

from . import git_backend, icons, shapes, spellcheck, templates, themes, version_string
from .canvas import (
    SlideScene, SlideView, TextBoxItem, PictureBoxItem, TableBoxItem,
    make_item, page_size_px, FONT_SCALE, latex_to_html, document_to_latex,
    canvas_font, _dropped_image,
)
from .compiler import compile_tex, tectonic_available
from .drawing_dialog import DrawingDialog
from .latex_view import LatexView, EDITOR_SCHEMES
from .model import (
    Deck, Slide, SlideText, SlidePicture, SlideTable, SlideLine, SlideShape,
    blend_over_white, deck_to_json, deck_from_json,
    object_to_dict, build_object,
    raise_object, lower_object, to_front, to_back,
)
from .navigator import SlideNavigator
from .preview import PdfPreview
from .serializer import serialize_deck, _ALL_BLOCK_ENVS

_COLOURED_BLOCKS = {"block", "alertblock", "exampleblock"}
_TEXT_KINDS = {"text", "equation"} | _ALL_BLOCK_ENVS


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

    # Editing shortcuts (bold/italic, clipboard, undo, select-all) that the
    # window's menu actions also claim. While the editor has focus it must
    # win them, so accept the ShortcutOverride — otherwise e.g. Ctrl+B just
    # toggles the slide navigator and never reaches the editor.
    _GRAB_KEYS = {Qt.Key_B, Qt.Key_I, Qt.Key_C, Qt.Key_X, Qt.Key_V,
                  Qt.Key_Z, Qt.Key_Y, Qt.Key_A}

    def event(self, e):
        if (e.type() == QEvent.ShortcutOverride
                and (e.modifiers() & Qt.ControlModifier)
                and e.key() in self._GRAB_KEYS):
            e.accept()
            return True
        return super().event(e)

    def insertFromMimeData(self, source):
        # Paste text from other apps as PLAIN text so its foreign font /
        # size / colour don't override the box — it adopts the box's own
        # font (the editor's current char format) instead.
        if source is not None and source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clearFocus()
            return
        # Tab / Shift+Tab change the list sub-level while editing a bullet or
        # numbered list (indent in, out) — like the levels in the slide.
        if event.key() == Qt.Key_Tab and self._change_list_level(1):
            return
        if event.key() == Qt.Key_Backtab and self._change_list_level(-1):
            return
        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_B:
                self.toggle_bold()
                return
            if event.key() == Qt.Key_I:
                self.toggle_italic()
                return
        super().keyPressEvent(event)

    # Bullet glyph varies with depth (disc → circle → square), matching the
    # nested look beamer gives sub-levels.
    _ITEMIZE_STYLES = [QTextListFormat.ListDisc, QTextListFormat.ListCircle,
                       QTextListFormat.ListSquare]

    def _change_list_level(self, delta):
        cursor = self.textCursor()
        lst = cursor.currentList()
        if lst is None:
            return False
        fmt = lst.format()
        new = fmt.indent() + delta
        if new < 1:
            return False
        enumerated = fmt.style() in (
            QTextListFormat.ListDecimal, QTextListFormat.ListLowerAlpha,
            QTextListFormat.ListUpperAlpha, QTextListFormat.ListLowerRoman,
            QTextListFormat.ListUpperRoman)
        nf = QTextListFormat()
        nf.setIndent(new)
        if enumerated:
            nf.setStyle(QTextListFormat.ListDecimal)
        else:
            nf.setStyle(self._ITEMIZE_STYLES[(new - 1) % len(self._ITEMIZE_STYLES)])
        cursor.beginEditBlock()
        cursor.createList(nf)
        cursor.endEditBlock()
        return True

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


class _GitNetworkWorker(QThread):
    """Run pull / push on a background thread so the GUI doesn't lock up
    for the duration of a libgit2 network round-trip. Without this,
    saving or pulling against an unreachable remote freezes the window
    for 30+ seconds (Windows shows it as "Not Responding") — to the user
    that reads as a crash, even though it's just blocked I/O on the main
    thread.

    Emits `finished_with` carrying (operation, success, message). The
    caller decides how to surface that — status bar, message box, etc.
    """
    finished_with = Signal(str, bool, str)  # op, ok, msg

    def __init__(self, op: str, repo_dir: Path, remote_name: str = "origin"):
        super().__init__()
        self._op = op   # "pull" or "push"
        self._repo_dir = repo_dir
        self._remote = remote_name

    def run(self) -> None:
        try:
            if self._op == "pull":
                ok, msg = git_backend.pull(self._repo_dir, self._remote)
            elif self._op == "push":
                ok, msg = git_backend.push(self._repo_dir, self._remote)
            else:
                ok, msg = False, f"Unknown git op: {self._op!r}"
        except Exception as exc:  # pragma: no cover — defensive
            ok, msg = False, f"{self._op} crashed: {exc}"
        self.finished_with.emit(self._op, ok, msg)


class SlideWindow(QMainWindow):
    # Extra windows opened via File ▸ New window, kept referenced so they
    # aren't garbage-collected while open.
    _extra_windows: list = []

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
        self._edit_hidden_item = None
        self._font_scale = FONT_SCALE

        # Auto-compile: debounce edits, run tectonic off-thread.
        self._worker: _CompileWorker | None = None
        self._compile_pending = False
        self._dl_worker: _DownloadWorker | None = None
        self._git_worker: _GitNetworkWorker | None = None
        self._pending_commit_msg: str | None = None
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
        self._editor_scheme = QSettings("kherveDOC", "KherveSlide").value(
            "editor_scheme", None) or None
        if self._editor_scheme not in EDITOR_SCHEMES:
            self._editor_scheme = None
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
        m_file.addAction("New window", self._new_window).setShortcut(
            "Ctrl+Shift+N")
        m_file.addAction("Open…", self._open_deck).setShortcut("Ctrl+O")
        m_file.addAction("Import PowerPoint (.pptx)…", self._import_pptx)
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
        m_edit.addAction("Find…", self._show_find).setShortcut("Ctrl+F")
        m_edit.addAction("Check spelling…", self._check_spelling).setShortcut("F7")
        m_edit.addAction("Page setup…", self._page_setup)

        m_view = mb.addMenu("&View")
        self.act_show_nav = m_view.addAction("Show slide navigator")
        self.act_show_nav.setCheckable(True)
        self.act_show_nav.setChecked(True)
        self.act_show_nav.setShortcut("Ctrl+B")
        self.act_show_nav.toggled.connect(self._toggle_navigator)
        m_view.addSeparator()
        # Drawing aids: grid + snapping, for aligning objects on the slide.
        self.act_grid = m_view.addAction("Show grid")
        self.act_grid.setCheckable(True)
        self.act_grid.setShortcut("Ctrl+'")
        self.act_grid.toggled.connect(self._toggle_grid)
        self.act_snap_grid = m_view.addAction("Snap to grid")
        self.act_snap_grid.setCheckable(True)
        self.act_snap_grid.toggled.connect(self._toggle_snap_grid)
        self.act_snap_obj = m_view.addAction("Snap to objects")
        self.act_snap_obj.setCheckable(True)
        self.act_snap_obj.toggled.connect(self._toggle_snap_objects)
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
        spellcheck.set_enabled(spell_on)
        self.act_spell.toggled.connect(self._toggle_spellcheck)

        m_lang = m_view.addMenu("Spell-check language")
        self._lang_group = QActionGroup(self)
        cur_lang = spellcheck.language()
        for label, code in spellcheck.LANGUAGES.items():
            a = m_lang.addAction(label)
            a.setCheckable(True)
            a.setChecked(code == cur_lang)
            a.triggered.connect(lambda _=False, c=code: self._set_spell_language(c))
            self._lang_group.addAction(a)

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

        # Syntax-highlighting colour scheme for the LaTeX source editor,
        # independent of the app Appearance theme.
        m_eds = m_view.addMenu("LaTeX editor theme")
        self._eds_group = QActionGroup(self)
        a = m_eds.addAction("Match app theme")
        a.setCheckable(True)
        a.setChecked(self._editor_scheme is None)
        a.triggered.connect(lambda _=False: self._set_editor_scheme(None))
        self._eds_group.addAction(a)
        m_eds.addSeparator()
        for name in EDITOR_SCHEMES:
            a = m_eds.addAction(name)
            a.setCheckable(True)
            a.setChecked(name == self._editor_scheme)
            a.triggered.connect(
                lambda _=False, n=name: self._set_editor_scheme(n))
            self._eds_group.addAction(a)

        # One Theme menu for everything that shapes the slide's look: the
        # presentation theme (whole look) AND the colour theme (colours
        # only), plus the gallery, the custom builder and decorations.
        m_theme = mb.addMenu("&Slide Theme")
        m_ptheme = m_theme.addMenu("Presentation theme (whole look)")
        self._ptheme_group = QActionGroup(self)
        self._ptheme_actions = {}
        for name in _THEMES:
            a = m_ptheme.addAction(name)
            a.setCheckable(True)
            a.triggered.connect(
                lambda _=False, n=name: self._set_presentation_theme(n))
            self._ptheme_group.addAction(a)
            self._ptheme_actions[name] = a
        m_ctheme = m_theme.addMenu("Colour theme (colours only)")
        self._ctheme_group = QActionGroup(self)
        self._ctheme_actions = {}
        for name in _COLOUR_THEMES:
            a = m_ctheme.addAction(name or "(theme default)")
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, n=name: self._set_colour_theme(n))
            self._ctheme_group.addAction(a)
            self._ctheme_actions[name] = a
        m_ptheme.aboutToShow.connect(self._sync_theme_menus)
        m_ctheme.aboutToShow.connect(self._sync_theme_menus)
        m_theme.addSeparator()
        m_theme.addAction("Preview themes…", self._open_theme_gallery)
        m_theme.addAction("Custom theme builder…", self._open_theme_builder)
        m_theme.addSeparator()
        self.act_deco = QAction("Show theme decorations", self, checkable=True)
        self.act_deco.setToolTip("Show the theme's title bars / footers")
        self.act_deco.toggled.connect(self._toggle_decorations)
        m_theme.addAction(self.act_deco)

        m_pres = mb.addMenu("&Presentation")
        m_pres.addAction("Title…", self._set_deck_title)
        m_pres.addAction("Author…", self._set_deck_author)
        self.act_nav = m_pres.addAction("Navigation symbols (prev / next)")
        self.act_nav.setCheckable(True)
        self.act_nav.setChecked(self.deck.nav_symbols)
        self.act_nav.toggled.connect(self._set_nav_symbols)

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
        m_slide.addAction("Add blank slide", self._add_slide)
        self._fill_new_slide_menu(m_slide.addMenu("Add slide with layout"))
        m_slide.addAction("Delete slide", self._del_slide)
        m_slide.addAction("Frame title…", self._set_frame_title)
        m_slide.addAction("Background colour…", self._pick_slide_bg)
        m_slide.addAction("Clear background", self._clear_slide_bg)

        m_insert = mb.addMenu("&Insert")
        m_insert.addAction("Text box", self._add_text)
        m_insert.addAction("Picture", self._add_picture)
        m_insert.addAction("Table…", self._insert_table_picker)
        m_insert.addAction("Equation…", self._add_equation)
        m_insert.addAction("Drawing…", self._add_drawing)

        m_shapes = mb.addMenu("S&hapes")
        m_shapes.addAction("Line", self._add_line)
        m_shapes.addAction("Arrow", self._add_arrow)
        m_shapes.addSeparator()
        for group, items in shapes.GROUPS:
            sub = m_shapes.addMenu(group)
            for key, label in items:
                sub.addAction(
                    label,
                    lambda _checked=False, k=key: self._add_shape(k))

        m_table = mb.addMenu("&Table")
        m_table.addAction("Insert table…", self._insert_table_picker)
        m_table.addAction("Table design…", self._table_design_dialog)
        m_table.addSeparator()
        m_table.addAction("Add row", lambda: self._table_op("add_row"))
        m_table.addAction("Add column", lambda: self._table_op("add_col"))
        m_table.addAction("Delete row", lambda: self._table_op("del_row"))
        m_table.addAction("Delete column", lambda: self._table_op("del_col"))
        m_table.addSeparator()
        m_table.addAction("Toggle header row", lambda: self._table_op("header"))
        m_table.addAction("Caption…", lambda: self._table_op("caption"))
        m_table.addSeparator()
        m_table.addAction("Table properties…", self._table_props_dialog)

        m_tpl = mb.addMenu("Te&mplates")
        self._m_tpl_new = m_tpl.addMenu("New presentation from template")
        self._m_tpl_new.aboutToShow.connect(self._populate_templates_menu)
        m_tpl.addSeparator()
        m_tpl.addAction("Save current presentation as template…", self._save_as_template)
        m_tpl.addAction("Rename template…", self._rename_template)
        m_tpl.addAction("Delete template…", self._delete_template)

        # Git — per-presentation version control with cloud backup. Every
        # save auto-commits and (if a remote is set) pushes; the actions
        # below add snapshots-with-a-message, history browsing and remotes.
        m_git = mb.addMenu("&Git")
        self.act_commit_now = QAction(
            icons.commit(), "&Save snapshot and upload", self,
            statusTip="Save your work, create a version snapshot, and "
                      "upload it to the cloud (GitHub, GitLab, etc.)",
            triggered=self._commit_and_maybe_push)
        self.act_pull = QAction(
            "&Download latest from cloud", self,
            statusTip="Download the newest version of this presentation "
                      "from the cloud (e.g. if a collaborator made changes)",
            triggered=self._pull_from_remote)
        self.act_history = QAction(
            icons.history(), "View &version history…", self,
            statusTip="Browse every saved snapshot of this presentation "
                      "and see what changed each time",
            triggered=self._show_history)
        self.act_branches = QAction(
            icons.branch(), "&Branches…", self,
            statusTip="View, create, switch or delete branches",
            triggered=self._show_branches)
        self.act_configure_remotes = QAction(
            "Connect to &GitHub / GitLab…", self,
            statusTip="Set up a cloud link so your presentation is backed "
                      "up online and can be shared with others",
            triggered=self._configure_remotes)
        m_git.addAction(self.act_commit_now)
        m_git.addAction(self.act_pull)
        m_git.addSeparator()
        m_git.addAction(self.act_history)
        m_git.addAction(self.act_branches)
        m_git.addSeparator()
        m_git.addAction(self.act_configure_remotes)

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
        # Per-box beamer placement (the whole theme lives in the Slide Theme
        # menu now). Sets the selected box's locked property.
        tb.addWidget(QLabel(" Box "))
        self.type_combo = QComboBox()
        # data = box-type key. Selecting one changes the selected box's type
        # in place; switching to Image/Table keeps the box geometry but
        # replaces the content. Locking lives on the corner badge / right-click.
        for label, kind in (("Text", "text"),
                            ("Block", "block"),
                            ("Alert block", "alertblock"),
                            ("Example block", "exampleblock"),
                            ("Theorem", "theorem"),
                            ("Definition", "definition"),
                            ("Corollary", "corollary"),
                            ("Lemma", "lemma"),
                            ("Example (thm)", "example"),
                            ("Proof", "proof"),
                            ("Fact", "fact"),
                            ("Equation", "equation"),
                            ("Image", "image"),
                            ("Table", "table")):
            self.type_combo.addItem(label, kind)
        self.type_combo.setToolTip(
            "What this box is. Switching to Image or Table keeps the box's "
            "position and size but replaces its content. Lock / unlock with "
            "the corner badge or the right-click menu.")
        self.type_combo.currentIndexChanged.connect(self._on_type_combo)
        self.type_combo.setEnabled(False)   # until a box is selected
        tb.addWidget(self.type_combo)

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
        self.act_bold.setToolTip("Bold — the selection while editing, "
                                 "else the whole box")
        self.act_bold.triggered.connect(self._on_bold)
        self.act_italic = QAction(icons.italic(), "Italic", self, checkable=True)
        self.act_italic.setToolTip("Italic — the selection while editing, "
                                   "else the whole box")
        self.act_italic.triggered.connect(self._on_italic)
        ftb.addAction(self.act_bold); ftb.addAction(self.act_italic)
        # NoFocus so clicking them mid-edit doesn't blur (and commit) the
        # in-place editor — they then format just the selected run.
        for a in (self.act_bold, self.act_italic):
            btn = ftb.widgetForAction(a)
            if btn is not None:
                btn.setFocusPolicy(Qt.NoFocus)
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

        # Navigation — jump between slides and show/hide the navigator panel.
        vact(icons.prev_slide, "Previous slide", self._prev_slide)
        vact(icons.next_slide, "Next slide", self._next_slide)
        vact(icons.toggle_navigator, "Show / hide slide navigator",
             lambda: self.act_show_nav.toggle())
        tb.addSeparator()

        # Slides — the add button has a dropdown of layouts (click = blank).
        add_btn = QToolButton()
        add_btn.setIcon(icons.slide_add())
        add_btn.setToolTip("Add slide (click for blank, ▾ to pick a layout)")
        add_btn.setPopupMode(QToolButton.MenuButtonPopup)
        add_btn.clicked.connect(self._add_slide)
        add_btn.setMenu(self._fill_new_slide_menu(QMenu(add_btn)))
        tb.addWidget(add_btn)
        self._themed_icons.append((add_btn, icons.slide_add))
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
        vact(icons.rect_tool, "Add rectangle", self._add_rect)
        vact(icons.ellipse_tool, "Add circle / ellipse", self._add_ellipse)
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

    def _add_rect(self):
        self._add_object(SlideShape(shape="rect"), offset=True)

    def _add_ellipse(self):
        self._add_object(SlideShape(shape="ellipse", w=0.22, h=0.22),
                         offset=True)

    def _add_shape(self, key):
        w = 0.22 if key not in ("circle", "ellipse") else 0.22
        h = 0.22 if key in ("circle", "ellipse", "star4", "star5", "star6",
                            "plus", "pentagon", "hexagon", "heptagon",
                            "octagon") else 0.18
        self._add_object(SlideShape(shape=key, w=w, h=h), offset=True)

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

        # Inline header above the slide: the deck's header line and the
        # three footer slots (shown when theme decorations are on). Frame
        # title is in the Slide menu; presentation Title/Author in the
        # Presentation menu.
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 4, 8, 4)
        self.f_frame_title = QLineEdit()
        self.f_frame_title.setPlaceholderText("Frame title (this slide)")
        self.f_frame_title.editingFinished.connect(self._apply_frame_title)
        self.f_header = QLineEdit()
        self.f_header.setPlaceholderText("Header")
        self.f_header.editingFinished.connect(self._apply_headfoot)
        self.f_foot_l = QLineEdit()
        self.f_foot_l.setPlaceholderText("Left foot")
        self.f_foot_l.editingFinished.connect(self._apply_headfoot)
        self.f_foot_c = QLineEdit()
        self.f_foot_c.setPlaceholderText("Centre foot")
        self.f_foot_c.editingFinished.connect(self._apply_headfoot)
        self.f_foot_r = QLineEdit()
        self.f_foot_r.setPlaceholderText("Right foot")
        self.f_foot_r.editingFinished.connect(self._apply_headfoot)
        # The head/foot slots accept LaTeX, so common dynamic bits work:
        _hf_tip = ("Accepts LaTeX — e.g. \\today for the date, "
                   "\\insertframenumber for the slide number, "
                   "\\inserttitle / \\insertauthor.")
        for _f in (self.f_header, self.f_foot_l, self.f_foot_c, self.f_foot_r):
            _f.setToolTip(_hf_tip)
        self.chk_nav = QCheckBox("Nav ▾▴")
        self.chk_nav.setToolTip("Show beamer's prev/next navigation symbols "
                                "at the bottom-right of every slide")
        self.chk_nav.setChecked(self.deck.nav_symbols)
        self.chk_nav.toggled.connect(self._set_nav_symbols)
        hl.addWidget(QLabel("Frame:"))
        hl.addWidget(self.f_frame_title, 2)
        hl.addWidget(QLabel("Header:"))
        hl.addWidget(self.f_header, 2)
        hl.addWidget(self.chk_nav)

        # The three footer slots sit in their own bar *below* the slide, so
        # the on-screen layout mirrors where they appear on the slide.
        footer = QWidget()
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(8, 4, 8, 4)
        fl.addWidget(QLabel("Foot:"))
        fl.addWidget(self.f_foot_l, 2)
        fl.addWidget(self.f_foot_c, 2)
        fl.addWidget(self.f_foot_r, 2)

        canvas_box = QWidget()
        cv = QVBoxLayout(canvas_box)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cv.addWidget(header)
        cv.addWidget(self.view, 1)
        cv.addWidget(footer)

        wysiwyg = QSplitter(Qt.Horizontal)
        wysiwyg.addWidget(nav_panel)
        wysiwyg.addWidget(canvas_box)
        wysiwyg.setStretchFactor(1, 1)
        wysiwyg.setSizes([220, 760])

        # LEFT tabs: the WYSIWYG (default) and the live, editable LaTeX.
        self.latex_view = LatexView()
        self.latex_view.set_dark(self._dark, self._theme)
        self.latex_view.set_editor_scheme(self._editor_scheme)
        # Editing the source recompiles that text; a slide change regenerates
        # it from the model (overwriting manual edits).
        self.latex_view.latexEdited.connect(self._on_latex_edited)
        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(wysiwyg, "WYSIWYG")
        self.left_tabs.addTab(self.latex_view, "LaTeX")
        self.left_tabs.setCurrentIndex(0)

        # RIGHT tabs: the PDF preview (default) and the compiler Console.
        self.console = QPlainTextEdit(); self.console.setReadOnly(True)
        cf = QFont("Consolas"); cf.setStyleHint(QFont.Monospace); cf.setPointSize(10)
        self.console.setFont(cf)
        # Terminal look: black background, light text — independent of theme.
        self.console.setStyleSheet(
            "QPlainTextEdit { background: #0c0c0c; color: #e6e6e6;"
            " selection-background-color: #444; }")
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

        # A find bar shared by both left tabs (LaTeX source / WYSIWYG text),
        # hidden until Ctrl+F.
        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)
        cl.addWidget(main, 1)
        cl.addWidget(self._build_find_bar())
        self.setCentralWidget(container)
        self.statusBar().showMessage(
            "Double-click to edit • while editing, Ctrl+B / Ctrl+I "
            "bold/italicise the selection")

    # ---------------- find ----------------
    def _build_find_bar(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 2, 6, 2)
        self._find_field = QLineEdit()
        self._find_field.setPlaceholderText("Find in slides / LaTeX…")
        self._find_field.returnPressed.connect(lambda: self._find_next(False))
        self._find_field.textChanged.connect(self._on_find_text)
        h.addWidget(self._find_field, 1)
        self._find_count = QLabel("")
        h.addWidget(self._find_count)
        b_prev = QPushButton("▲"); b_prev.setFixedWidth(28)
        b_prev.setToolTip("Previous match")
        b_prev.clicked.connect(lambda: self._find_next(True))
        h.addWidget(b_prev)
        b_next = QPushButton("▼"); b_next.setFixedWidth(28)
        b_next.setToolTip("Next match")
        b_next.clicked.connect(lambda: self._find_next(False))
        h.addWidget(b_next)
        b_close = QPushButton("✕"); b_close.setFixedWidth(28)
        b_close.clicked.connect(self._close_find)
        h.addWidget(b_close)
        self._find_bar = bar
        self._wf_query = None
        bar.hide()
        return bar

    def _show_find(self):
        self._find_bar.show()
        self._find_field.setFocus()
        self._find_field.selectAll()

    def _close_find(self):
        self._find_bar.hide()
        self._find_count.setText("")
        # Return focus to the active editing surface.
        if self.left_tabs.currentWidget() is self.latex_view:
            self.latex_view._edit.setFocus()
        else:
            self.view.setFocus()

    def _on_find_text(self, _text):
        # A new query invalidates the WYSIWYG match cache.
        self._wf_query = None
        self._find_count.setText("")

    def _find_next(self, backwards=False):
        text = self._find_field.text()
        if not text:
            return
        if self.left_tabs.currentWidget() is self.latex_view:
            ok = self.latex_view.find(text, backwards)
            self._find_count.setText("" if ok else "Not found")
        else:
            self.left_tabs.setCurrentIndex(0)   # ensure WYSIWYG visible
            self._find_in_slides(text, backwards)

    @staticmethod
    def _obj_haystack(obj) -> str:
        if isinstance(obj, SlideText):
            return obj.text or ""
        if isinstance(obj, SlideTable):
            return " ".join(" ".join(r) for r in (obj.rows or []))
        return ""

    def _find_in_slides(self, text, backwards=False):
        q = text.lower()
        if q != self._wf_query:
            self._wf_query = q
            self._wf_matches = [
                (si, obj) for si, slide in enumerate(self.deck.slides)
                for obj in slide.objects
                if q in self._obj_haystack(obj).lower()]
            self._wf_idx = -1
        if not self._wf_matches:
            self._find_count.setText("0 / 0")
            return
        n = len(self._wf_matches)
        self._wf_idx = (self._wf_idx + (-1 if backwards else 1)) % n
        si, obj = self._wf_matches[self._wf_idx]
        if si != self.current:
            self.nav.setCurrentRow(si)          # selects slide → reloads scene
        self._select_object(obj)
        self._find_count.setText(f"{self._wf_idx + 1} / {n}")

    def _select_object(self, obj):
        self.scene.clearSelection()
        for it in self._items:
            try:
                if it.obj is obj:
                    it.setSelected(True)
                    self.view.ensureVisible(it)
                    break
            except RuntimeError:
                continue

    # ---------------- reload ----------------
    @property
    def slide(self) -> Slide:
        return self.deck.slides[self.current]

    def _reload_all(self):
        self.act_deco.blockSignals(True)
        self.act_deco.setChecked(not self.deck.plain_frames)
        self.act_deco.blockSignals(False)
        for w in (self.act_nav, self.chk_nav):
            w.blockSignals(True)
            w.setChecked(self.deck.nav_symbols)
            w.blockSignals(False)
        mode = getattr(self.deck, "page_number", "none")
        self._pgnum_actions.get(mode, self._pgnum_actions["none"]).setChecked(True)
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
        for z, obj in enumerate(self.slide.objects):
            item = make_item(obj, pw, ph, self.deck.gap, self._font_scale)
            # Stack strictly by list order so raise / lower / front / back are
            # honoured on the canvas exactly as in the generated slide.
            item.setZValue(z)
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
        if not hasattr(self, "f_header"):
            return
        for widget, val in ((self.f_frame_title, self.slide.title),
                            (self.f_header, self.deck.header),
                            (self.f_foot_l, self.deck.foot_left),
                            (self.f_foot_c, self.deck.foot_center),
                            (self.f_foot_r, self.deck.foot_right)):
            widget.blockSignals(True)
            widget.setText(val)
            widget.blockSignals(False)

    def _apply_frame_title(self):
        if not self._loading and self.slide.title != self.f_frame_title.text():
            self.slide.title = self.f_frame_title.text()
            self._touch_current()

    def _apply_headfoot(self):
        if self._loading:
            return
        changed = False
        for widget, attr in ((self.f_header, "header"),
                             (self.f_foot_l, "foot_left"),
                             (self.f_foot_c, "foot_center"),
                             (self.f_foot_r, "foot_right")):
            if getattr(self.deck, attr) != widget.text():
                setattr(self.deck, attr, widget.text())
                changed = True
        if changed:
            self._recompile_now()

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
        # Compile what's in the LaTeX editor (so manual edits take effect).
        tex = self.latex_view.source()
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
        if self in SlideWindow._extra_windows:
            SlideWindow._extra_windows.remove(self)
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

    def _export_picture_png(self):
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlidePicture):
            return
        o = item.obj
        src = QPixmap(o.path) if o.path else QPixmap()
        if src.isNull():
            QMessageBox.warning(self, "Export to PNG", "This box has no image.")
            return
        # Apply the box's crop and rotation, then save.
        w, h = src.width(), src.height()
        img = src.copy(int(o.crop_l * w), int(o.crop_t * h),
                       max(1, int((1 - o.crop_l - o.crop_r) * w)),
                       max(1, int((1 - o.crop_t - o.crop_b) * h)))
        if getattr(o, "rotation", 0.0):
            img = img.transformed(QTransform().rotate(o.rotation),
                                  Qt.SmoothTransformation)
        out, _ = QFileDialog.getSaveFileName(
            self, "Export image to PNG", "image.png", "PNG image (*.png)")
        if out:
            img.save(out, "PNG")
            self.statusBar().showMessage(f"Exported image to {out}")

    def _begin_inline_edit(self, rect, initial, *, font_pt, commit,
                           hide_item=None, bg="#ffffff"):
        """Float a *rich* editor over *rect* (lists show as real bullets,
        not \\item source); on focus-out call commit(latex). The box being
        edited is hidden meanwhile so its own (possibly overflowing) painted
        text doesn't show doubled behind the editor."""
        self._cancel_edit()
        editor = _InlineEditor()
        f = canvas_font(max(8, int(font_pt * self._font_scale)))
        editor.setFont(f)
        editor.setHtml(latex_to_html(initial))
        # Opaque background (matching the box fill if any) so nothing bleeds
        # through from underneath the editor.
        editor.setStyleSheet(
            f"QTextEdit {{ background: {bg or '#ffffff'};"
            " border: 1px solid #2878dc; }")
        proxy = self.scene.addWidget(editor)
        proxy.setGeometry(rect)
        proxy.setZValue(1e6)
        self._edit_proxy = proxy
        self._edit_commit = commit
        self._edit_hidden_item = hide_item
        if hide_item is not None:
            try:
                hide_item._editing = True      # suppress its own text paint
                hide_item.update()
            except RuntimeError:
                self._edit_hidden_item = None
        editor.editingFinished.connect(self._finish_edit)
        editor.setFocus()
        editor.selectAll()

    def _restore_hidden_item(self):
        item = getattr(self, "_edit_hidden_item", None)
        self._edit_hidden_item = None
        if item is not None:
            try:
                item._editing = False
                item.update()
            except RuntimeError:
                pass

    def _edit_text(self):
        """The rich editor's current content, converted back to LaTeX."""
        return document_to_latex(self._edit_proxy.widget().document())

    def _edit_text_item(self, item):
        self._begin_inline_edit(
            item.scene_rect(), item.obj.text, font_pt=item.obj.font_pt,
            commit=lambda t: self._commit_obj_text(item, t),
            hide_item=item, bg=getattr(item.obj, "fill", "") or "#ffffff")

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
        self._restore_hidden_item()
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
        self._restore_hidden_item()

    def _pick_image_for(self, item):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", "",
            "Images (*.png *.jpg *.jpeg *.pdf *.gif *.bmp)")
        if path:
            item.obj.path = path
            item.update()
            self._touch_current()

    # ---------------- slides ----------------
    def _prev_slide(self):
        if self.current > 0:
            self.nav.setCurrentRow(self.current - 1)

    def _next_slide(self):
        if self.current < len(self.deck.slides) - 1:
            self.nav.setCurrentRow(self.current + 1)

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
        self._add_slide_with_layout("Blank")

    def _add_slide_with_layout(self, name="Blank", row=None):
        at = (self.current if row is None else row) + 1
        self.deck.slides.insert(at, templates.instantiate_slide_layout(name))
        self.current = at
        self._reload_all()

    def _fill_new_slide_menu(self, menu, row=None):
        """Populate *menu* with one entry per slide layout."""
        for name in templates.slide_layout_names():
            menu.addAction(
                name, lambda _=False, n=name, r=row:
                self._add_slide_with_layout(n, r))
        return menu

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
        self._fill_new_slide_menu(menu.addMenu("New slide after"), row)
        menu.addAction("Duplicate slide", lambda: self._duplicate_slide(row))
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
    def _place_stacked(self, obj):
        """Position a freshly created object just below the bottom-most
        existing object so new boxes stack instead of landing on top of
        each other (matches how beamer flows locked content downward)."""
        others = [o for o in self.slide.objects
                  if o is not obj and hasattr(o, "y") and hasattr(o, "h")]
        if not others:
            return
        last = max(others, key=lambda o: o.y + o.h)
        obj.x = round(last.x, 4)
        # Match the previous box's width for text/tables so a second block
        # lines up; keep a picture's own size to preserve its aspect ratio.
        if not isinstance(obj, SlidePicture):
            obj.w = last.w
        new_y = last.y + last.h + 0.02
        if new_y + obj.h > 1.0:
            new_y = max(0.0, 1.0 - obj.h)
        obj.y = round(new_y, 4)

    def _add_text(self):
        obj = SlideText()
        self._place_stacked(obj)
        self.slide.objects.append(obj)
        self._reload_scene()
        self._select_last()
        self._touch_current()

    def _add_picture(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", "",
            "Images (*.png *.jpg *.jpeg *.pdf *.gif *.bmp)")
        obj = SlidePicture(path=path or "")
        self._place_stacked(obj)
        self.slide.objects.append(obj)
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
        self._insert_table(2, 2)

    def _insert_table(self, rows, cols, style=None):
        from .table_styles import apply_table_style
        obj = SlideTable(rows=[["" for _ in range(cols)] for _ in range(rows)])
        if style is not None:
            apply_table_style(obj, style)
        self._place_stacked(obj)
        self.slide.objects.append(obj)
        self._reload_scene()
        self._select_last()
        self._touch_current()

    def _insert_table_picker(self):
        """Pop up the hover-to-size grid (PowerPoint-style)."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu, QWidgetAction
        from .table_styles import TableGridPicker
        menu = QMenu(self)
        picker = TableGridPicker()
        act = QWidgetAction(menu)
        act.setDefaultWidget(picker)
        menu.addAction(act)
        menu.addSeparator()
        menu.addAction("Table design…", self._table_design_dialog)
        picker.picked.connect(
            lambda r, c: (menu.close(), self._insert_table(r, c)))
        menu.exec(QCursor.pos())

    def _table_design_dialog(self):
        from .table_styles import TableStyleGallery, apply_table_style
        item = self._selected_item()
        target = (item.obj if item is not None
                  and isinstance(item.obj, SlideTable) else None)
        dlg = TableStyleGallery(self)
        if dlg.exec() and dlg.chosen is not None:
            if target is None:
                self._insert_table(3, 3, dlg.chosen)
            else:
                apply_table_style(target, dlg.chosen)
                self._reload_scene()
                self._select_object(target)
                self._touch_current()

    def _add_equation(self):
        from .equation_editor import EquationEditorDialog
        dlg = EquationEditorDialog(self)
        if dlg.exec() and dlg.latex():
            obj = SlideText(text=f"${dlg.latex()}$", font_pt=28,
                            align="center")
            self._place_stacked(obj)
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
        obj = SlidePicture(path=png_path, w=0.4, h=0.4, keep_aspect=True)
        self._place_stacked(obj)
        self.slide.objects.append(obj)
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

    def _clipboard_has_image(self):
        md = QApplication.clipboard().mimeData()
        return bool(md and (md.hasImage() or _dropped_image(md)))

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
        path = None
        if img is not None and not img.isNull():
            path = self._save_clipboard_image(img)
        if path is None:
            path = _dropped_image(md)
        if not path:
            return
        # If a picture box is selected, drop the image straight into it
        # (fills an empty placeholder); otherwise add a new floating image.
        item = self._selected_item()
        if item is not None and isinstance(item.obj, SlidePicture):
            self._set_picture_path(item, path)
            return
        self._on_image_dropped(
            path, scene_pos or QPointF(self.scene.page_w / 2,
                                       self.scene.page_h / 2))

    def _set_picture_path(self, item, path):
        item.obj.path = path
        item._pix_path = None          # force pixmap reload
        item.update()
        self._touch_current()
        self.statusBar().showMessage("Image pasted into the picture box")

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
    def _select_box_at(self, scene_pos):
        """Select the topmost box whose rectangle contains *scene_pos*."""
        hit = None
        for it in self._items:            # later items paint on top
            try:
                if it.scene_rect().contains(scene_pos):
                    hit = it
            except RuntimeError:
                continue
        if hit is not None and not hit.isSelected():
            self.scene.clearSelection()
            hit.setSelected(True)
        return hit

    def _canvas_context_menu(self, global_pos, scene_pos):
        # Right-clicking a box selects it first, so the menu always acts on
        # the box under the cursor (no need to left-click it beforehand).
        on_canvas = isinstance(scene_pos, QPointF)
        hit = self._select_box_at(scene_pos) if on_canvas else None
        menu = QMenu(self)
        # Right-click on empty canvas → quick "add object" menu.
        if on_canvas and hit is None:
            self.scene.clearSelection()
            menu.addAction("Add text box", self._add_text)
            menu.addAction("Add image…", self._add_picture)
            menu.addAction("Add table", self._add_table)
            menu.addAction("Add equation…", self._add_equation)
            menu.addSeparator()
            paste = menu.addAction("Paste", lambda: self._paste(scene_pos))
            paste.setEnabled(self._can_paste())
            menu.exec(global_pos)
            return
        item = self._selected_item()
        if item is not None:
            # Clipboard first, with Paste right next to Copy.
            menu.addAction("Copy", self._copy_selected)
            paste = menu.addAction("Paste", lambda: self._paste(scene_pos))
            paste.setEnabled(self._can_paste())
            menu.addAction("Cut", self._cut_selected)
            menu.addAction("Duplicate", self._duplicate_selected)
            menu.addAction("Delete", self._delete_selected)
            menu.addSeparator()
            positioned = isinstance(item.obj, (SlideLine, SlideShape))
            locked = getattr(item.obj, "locked", True)
            lk = menu.addAction("Lock position (no dragging)" if positioned
                                else "Locked (beamer places it)")
            lk.setCheckable(True)
            lk.setChecked(locked)
            lk.setToolTip("Locked: beamer lays the box out. "
                          "Unlocked: drag it anywhere on the slide.")
            lk.toggled.connect(self._set_selected_locked)
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
                pst = menu.addAction("Paste image here",
                                     lambda: self._paste(scene_pos))
                pst.setEnabled(self._clipboard_has_image())
                exp = menu.addAction("Export to PNG…", self._export_picture_png)
                exp.setEnabled(bool(item.obj.path))
            # Property dialogs live at the very bottom of the menu.
            menu.addSeparator()
            if isinstance(item.obj, SlideShape):
                menu.addAction("Shape properties…", self._shape_props_dialog)
            elif isinstance(item.obj, SlideLine):
                menu.addAction("Line / arrow properties…",
                               self._line_props_dialog)
            elif isinstance(item.obj, SlideTable):
                menu.addAction("Table design…", self._table_design_dialog)
                menu.addAction("Table properties…", self._table_props_dialog)
            else:
                menu.addAction("Box style (border / fill)…",
                               self._box_style_dialog)
            if isinstance(item.obj, SlideText) and getattr(item.obj, "block", ""):
                menu.addAction("Block title…", self._set_block_title)
            menu.exec(global_pos)
            return
        paste = menu.addAction("Paste", lambda: self._paste(scene_pos))
        paste.setEnabled(self._can_paste())
        menu.exec(global_pos)

    def _box_style_dialog(self):
        item = self._selected_item()
        if item is None or isinstance(item.obj, SlideLine):
            return
        o = item.obj
        dlg = QDialog(self)
        dlg.setWindowTitle("Box style")
        form = QFormLayout(dlg)
        state = {"fill": getattr(o, "fill", ""),
                 "border_color": getattr(o, "border_color", "")}

        form.addRow("Fill colour", self._colour_button(state, "fill"))
        fill_op = QDoubleSpinBox(); fill_op.setRange(0.0, 1.0)
        fill_op.setSingleStep(0.05); fill_op.setValue(getattr(o, "fill_opacity", 1.0))
        form.addRow("Fill opacity", fill_op)
        form.addRow("Border colour",
                    self._colour_button(state, "border_color"))
        width = QDoubleSpinBox(); width.setRange(0.0, 12.0); width.setSingleStep(0.5)
        width.setValue(getattr(o, "border_width", 1.0))
        form.addRow("Border width (pt)", width)
        bstyle = QComboBox(); bstyle.addItems(["solid", "dashed", "dotted"])
        bstyle.setCurrentText(getattr(o, "border_style", "solid"))
        form.addRow("Border style", bstyle)
        corner = QComboBox(); corner.addItems(["sharp", "rounded"])
        corner.setCurrentText(getattr(o, "corner", "sharp"))
        form.addRow("Corners", corner)
        radius = QDoubleSpinBox(); radius.setRange(0.0, 40.0); radius.setSingleStep(1.0)
        radius.setValue(getattr(o, "corner_radius", 4.0))
        form.addRow("Corner radius (pt)", radius)
        shadow = QCheckBox("Drop shadow")
        shadow.setChecked(getattr(o, "shadow", False))
        form.addRow(shadow)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec():
            o.fill = state["fill"]
            o.fill_opacity = fill_op.value()
            o.border_color = state["border_color"]
            o.border_width = width.value()
            o.border_style = bstyle.currentText()
            o.corner = corner.currentText()
            o.corner_radius = radius.value()
            o.shadow = shadow.isChecked()
            item.update()
            self._touch_current()

    def _colour_button(self, state, key, *, allow_none=True):
        """A swatch button bound to ``state[key]``. Click picks a colour;
        right-click clears it to none (when allowed)."""
        btn = QPushButton()

        def refresh():
            v = state[key]
            btn.setText(v or "(none)")
            btn.setStyleSheet(f"background:{v}; color:#fff;" if v else "")

        def pick():
            from PySide6.QtGui import QColor as _QC
            c = QColorDialog.getColor(_QC(state[key] or "#ffffff"), self)
            if c.isValid():
                state[key] = c.name(); refresh()

        btn.clicked.connect(pick)
        if allow_none:
            btn.setToolTip("Click to choose; right-click clears")
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _p: (state.__setitem__(key, ""), refresh()))
        refresh()
        return btn

    def _shape_props_dialog(self):
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlideShape):
            return
        o = item.obj
        dlg = QDialog(self)
        dlg.setWindowTitle("Shape properties")
        form = QFormLayout(dlg)
        state = {"fill": o.fill, "border_color": o.border_color}

        shape = QComboBox()
        for key, label in shapes.LABELS.items():
            shape.addItem(label, key)
        cur = shape.findData(o.shape)
        shape.setCurrentIndex(cur if cur >= 0 else 0)
        form.addRow("Shape", shape)
        form.addRow("Fill colour", self._colour_button(state, "fill"))
        form.addRow("Outline colour",
                    self._colour_button(state, "border_color"))
        width = QDoubleSpinBox(); width.setRange(0.0, 20.0)
        width.setSingleStep(0.5); width.setValue(o.border_width)
        form.addRow("Outline width (pt)", width)
        style = QComboBox(); style.addItems(["solid", "dashed", "dotted"])
        style.setCurrentText(o.style)
        form.addRow("Outline style", style)
        corner = QComboBox(); corner.addItems(["sharp", "rounded"])
        corner.setCurrentText(o.corner)
        form.addRow("Corners (rect)", corner)
        opacity = QDoubleSpinBox(); opacity.setRange(0.0, 1.0)
        opacity.setSingleStep(0.05); opacity.setValue(o.opacity)
        form.addRow("Opacity", opacity)
        rot = QDoubleSpinBox(); rot.setRange(-360.0, 360.0)
        rot.setSingleStep(5.0); rot.setValue(o.rotation)
        form.addRow("Rotation (°)", rot)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec():
            o.shape = shape.currentData()
            o.fill = state["fill"]
            o.border_color = state["border_color"]
            o.border_width = width.value()
            o.style = style.currentText()
            o.corner = corner.currentText()
            o.opacity = opacity.value()
            o.rotation = rot.value()
            item.update()
            self._touch_current()

    def _line_props_dialog(self):
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlideLine):
            return
        o = item.obj
        dlg = QDialog(self)
        dlg.setWindowTitle("Line / arrow properties")
        form = QFormLayout(dlg)
        state = {"color": o.color}

        form.addRow("Colour",
                    self._colour_button(state, "color", allow_none=False))
        width = QDoubleSpinBox(); width.setRange(0.1, 20.0)
        width.setSingleStep(0.5); width.setValue(o.width_pt)
        form.addRow("Width (pt)", width)
        style = QComboBox(); style.addItems(["solid", "dashed", "dotted"])
        style.setCurrentText(o.style)
        form.addRow("Style", style)
        a_start = QCheckBox("Arrowhead at start"); a_start.setChecked(o.arrow_start)
        a_end = QCheckBox("Arrowhead at end"); a_end.setChecked(o.arrow_end)
        form.addRow(a_start)
        form.addRow(a_end)
        head = QDoubleSpinBox(); head.setRange(0.3, 5.0)
        head.setSingleStep(0.1); head.setValue(o.head_size)
        form.addRow("Arrowhead size", head)
        opacity = QDoubleSpinBox(); opacity.setRange(0.0, 1.0)
        opacity.setSingleStep(0.05); opacity.setValue(o.opacity)
        form.addRow("Opacity", opacity)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec():
            o.color = state["color"] or "#000000"
            o.width_pt = width.value()
            o.style = style.currentText()
            o.arrow_start = a_start.isChecked()
            o.arrow_end = a_end.isChecked()
            o.head_size = head.value()
            o.opacity = opacity.value()
            item.update()
            self._touch_current()

    @staticmethod
    def _resized_rows(rows, nrows, ncols):
        out = []
        for r in range(nrows):
            src = rows[r] if r < len(rows) else []
            out.append([(src[c] if c < len(src) else "") for c in range(ncols)])
        return out

    def _table_props_dialog(self):
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlideTable):
            return
        o = item.obj
        cur_cols = max((len(r) for r in o.rows), default=1)
        dlg = QDialog(self)
        dlg.setWindowTitle("Table properties")
        form = QFormLayout(dlg)
        state = {"header_bg": o.header_bg, "header_fg": o.header_fg,
                 "rule_color": o.rule_color, "stripe_color": o.stripe_color,
                 "color": o.color, "fill": o.fill,
                 "border_color": o.border_color}

        n_rows = QSpinBox(); n_rows.setRange(1, 50); n_rows.setValue(len(o.rows))
        n_cols = QSpinBox(); n_cols.setRange(1, 20); n_cols.setValue(cur_cols)
        form.addRow("Rows", n_rows)
        form.addRow("Columns", n_cols)
        header = QCheckBox("First row is a header")
        header.setChecked(o.header)
        form.addRow(header)
        form.addRow("Header fill",
                    self._colour_button(state, "header_bg", allow_none=False))
        form.addRow("Header text",
                    self._colour_button(state, "header_fg", allow_none=False))
        align = QComboBox(); align.addItems(["left", "center", "right"])
        align.setCurrentText(o.align)
        form.addRow("Cell alignment", align)
        fontsz = QSpinBox(); fontsz.setRange(6, 60); fontsz.setValue(o.font_pt)
        form.addRow("Font size (pt)", fontsz)
        form.addRow("Text colour",
                    self._colour_button(state, "color", allow_none=False))
        grid = QComboBox(); grid.addItems(["all", "horizontal", "outer", "none"])
        grid.setCurrentText(o.grid)
        form.addRow("Grid lines", grid)
        form.addRow("Rule colour",
                    self._colour_button(state, "rule_color", allow_none=False))
        rule_w = QDoubleSpinBox(); rule_w.setRange(0.1, 6.0)
        rule_w.setSingleStep(0.2); rule_w.setValue(o.rule_width)
        form.addRow("Rule width (pt)", rule_w)
        striped = QCheckBox("Zebra-stripe body rows")
        striped.setChecked(o.striped)
        form.addRow(striped)
        form.addRow("Stripe colour",
                    self._colour_button(state, "stripe_color", allow_none=False))
        caption = QLineEdit(o.caption)
        form.addRow("Caption", caption)
        form.addRow("Box fill", self._colour_button(state, "fill"))
        form.addRow("Box frame", self._colour_button(state, "border_color"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec():
            o.rows = self._resized_rows(o.rows, n_rows.value(), n_cols.value())
            o.header = header.isChecked()
            o.header_bg = state["header_bg"]
            o.header_fg = state["header_fg"]
            o.align = align.currentText()
            o.font_pt = fontsz.value()
            o.color = state["color"] or "#000000"
            o.grid = grid.currentText()
            o.border = o.grid != "none"
            o.rule_color = state["rule_color"]
            o.rule_width = rule_w.value()
            o.striped = striped.isChecked()
            o.stripe_color = state["stripe_color"]
            o.caption = caption.text()
            o.fill = state["fill"]
            o.border_color = state["border_color"]
            item.update()
            self._touch_current()

    def _set_block_title(self):
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlideText):
            return
        text, ok = QInputDialog.getText(self, "Block title", "Block title:",
                                        text=item.obj.block_title)
        if ok:
            item.obj.block_title = text
            item.update()
            self._touch_current()

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
        # Lines and shapes have no editable "type"; everything else uses combo.
        no_type = item is not None and isinstance(item.obj,
                                                  (SlideLine, SlideShape))
        self.type_combo.setEnabled(item is not None and not no_type)
        if item is None:
            self._enable_format(False)
            return
        obj = item.obj
        # Reflect this box's type in the toolbar combo.
        want = self._obj_kind(obj)
        self._loading = True
        for i in range(self.type_combo.count()):
            if self.type_combo.itemData(i) == want:
                self.type_combo.setCurrentIndex(i)
                break
        self._loading = False
        is_text = isinstance(obj, SlideText)
        self._enable_format(True, is_text=is_text,
                            is_pic=isinstance(obj, SlidePicture))
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
        # Font-size only; bold/italic go through _on_bold / _on_italic so
        # they can target the selection while editing.
        if self._loading:
            return
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlideText):
            return
        item.obj.font_pt = self.fmt_font.value()
        item.update()
        self._touch_current()

    def _on_bold(self, *_):
        self._toggle_run_or_box("bold")

    def _on_italic(self, *_):
        self._toggle_run_or_box("italic")

    def _toggle_run_or_box(self, kind):
        if self._loading:
            return
        # While a box is being edited, format just the selected run; the
        # toolbar buttons are NoFocus so the editor isn't committed first.
        if self._edit_proxy is not None:
            editor = self._edit_proxy.widget()
            (editor.toggle_bold if kind == "bold" else editor.toggle_italic)()
            return
        # Otherwise toggle the style for the whole box.
        item = self._selected_item()
        if item is None or not isinstance(item.obj, SlideText):
            return
        if kind == "bold":
            item.obj.bold = self.act_bold.isChecked()
        else:
            item.obj.italic = self.act_italic.isChecked()
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

    def _set_presentation_theme(self, name):
        if self._loading or not name:
            return
        # Picking a built-in theme replaces any custom theme-builder layer.
        self.deck.theme = name
        if self.deck.theme_spec.enabled:
            self.deck.theme_spec.enabled = False
        self._recompile_now()

    @staticmethod
    def _obj_kind(obj) -> str:
        """The toolbar-combo key describing an object's current type."""
        if isinstance(obj, SlidePicture):
            return "image"
        if isinstance(obj, SlideTable):
            return "table"
        if isinstance(obj, SlideText):
            block = getattr(obj, "block", "")
            if block in _ALL_BLOCK_ENVS:
                return block
            if "$" in (obj.text or ""):
                return "equation"
            return "text"
        return "text"

    def _on_type_combo(self):
        """Toolbar combo → change the selected box's type in place."""
        if self._loading:
            return
        item = self._selected_item()
        if item is None:
            return
        kind = self.type_combo.currentData()
        obj = item.obj
        if self._obj_kind(obj) == kind:
            return

        # Text-family changes are lossless: keep the same SlideText, just
        # retag its block / equation styling.
        if kind in _TEXT_KINDS and isinstance(obj, SlideText):
            obj.block = "" if kind in ("text", "equation") else kind
            if obj.block in _COLOURED_BLOCKS and not obj.block_title:
                obj.block_title = "Block"
            if kind == "equation" and "$" not in (obj.text or ""):
                t = (obj.text or "").strip()
                obj.text = f"${t}$" if t else "$  $"
                obj.align = "center"
            item.update()
            self._touch_current()
            if obj.block:
                self.statusBar().showMessage(
                    "Block — right-click ▸ Block title… to rename it", 5000)
            return

        # Cross-type conversion: build a new object of the target kind,
        # preserving the box's position, size and lock state.
        new_obj = self._convert_object(kind, obj)
        if new_obj is None:
            return
        idx = self.slide.objects.index(obj)
        self.slide.objects[idx] = new_obj
        self._reload_scene()
        self._select_object(new_obj)
        self._touch_current()

    def _convert_object(self, kind, src):
        """Return a new object of *kind* carrying *src*'s geometry."""
        geo = dict(x=src.x, y=src.y, w=src.w, h=src.h,
                   locked=getattr(src, "locked", True))
        if kind in _TEXT_KINDS:
            text = getattr(src, "text", "") or ""
            block = "" if kind in ("text", "equation") else kind
            o = SlideText(text=text or "Text", block=block, **geo)
            if block in _COLOURED_BLOCKS:
                o.block_title = "Block"
            if kind == "equation":
                t = text.strip()
                o.text = (f"${t}$" if t and "$" not in t else (t or "$  $"))
                o.align = "center"
            return o
        if kind == "image":
            path = getattr(src, "path", "") or ""
            if not path:
                path, _ = QFileDialog.getOpenFileName(
                    self, "Choose image", "",
                    "Images (*.png *.jpg *.jpeg *.pdf *.gif *.bmp)")
            return SlidePicture(path=path or "", keep_aspect=True, **geo)
        if kind == "table":
            return SlideTable(**geo)
        return None

    def _open_theme_gallery(self):
        from .theme_gallery import ThemeGallery
        dlg = ThemeGallery(_THEMES, _COLOUR_THEMES, self.deck.aspect,
                           self.deck.theme, self.deck.color_theme, self,
                           cache=self._theme_cache)
        if dlg.exec() and dlg.chosen:
            self.deck.theme = dlg.chosen
            self.deck.color_theme = dlg.chosen_color
            self.deck.theme_spec.enabled = False   # built-in replaces custom
            # Previews show decorations, so turn them on to match what was seen.
            self.deck.plain_frames = False
            self.act_deco.blockSignals(True)
            self.act_deco.setChecked(True)
            self.act_deco.blockSignals(False)
            self._recompile_now()

    def _set_colour_theme(self, name):
        self.deck.color_theme = name
        self._recompile_now()

    def _sync_theme_menus(self):
        """Tick the active entries in the Theme menu's submenus."""
        base = self.deck.theme
        if base in self._ptheme_actions:
            self._ptheme_actions[base].setChecked(True)
        col = self.deck.color_theme
        if col in self._ctheme_actions:
            self._ctheme_actions[col].setChecked(True)

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

    def _set_nav_symbols(self, on):
        self.deck.nav_symbols = on
        for w in (self.act_nav, self.chk_nav):   # keep menu + tick box in sync
            w.blockSignals(True)
            w.setChecked(on)
            w.blockSignals(False)
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

    def _toggle_grid(self, on):
        self.scene.show_grid = on
        self.scene.update()

    def _toggle_snap_grid(self, on):
        self.scene.snap_grid = on

    def _toggle_snap_objects(self, on):
        self.scene.snap_objects = on

    def _toggle_spellcheck(self, on):
        from . import spellcheck
        _InlineEditor.spellcheck_enabled = on
        spellcheck.set_enabled(on)
        QSettings("kherveDOC", "KherveSlide").setValue(
            "spellcheck_enabled", on)
        self.scene.update()           # repaint canvas underlines

    def _set_spell_language(self, code):
        from . import spellcheck
        spellcheck.set_language(code)
        self.scene.update()           # re-check with the new dictionary

    def _check_spelling(self):
        from . import spellcheck
        if not spellcheck.available():
            QMessageBox.information(
                self, "Spell check",
                "Install pyspellchecker to enable spell checking:\n"
                "  pip install pyspellchecker")
            return
        self._cancel_edit()
        from .spellcheck_dialog import SpellCheckDialog
        dlg = SpellCheckDialog(self.deck, self, on_changed=lambda: None)
        if not dlg.has_issues():
            QMessageBox.information(self, "Spell check",
                                    "No misspellings found.")
            return
        dlg.exec()
        if dlg.changed:
            self._reload_all()
            self._touch_current()
            self.statusBar().showMessage(
                f"Spell check: {dlg.changed} word(s) changed")

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

    def _set_editor_scheme(self, name):
        """Pick a syntax-colour scheme for the LaTeX source editor."""
        self._editor_scheme = name
        self.latex_view.set_editor_scheme(name)
        QSettings("kherveDOC", "KherveSlide").setValue(
            "editor_scheme", name or "")
        self.statusBar().showMessage(
            f"LaTeX editor theme: {name or 'Match app theme'}", 3000)

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
            result = compile_tex(self.latex_view.source(), workdir,
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

    def _on_latex_edited(self, _text):
        # The user edited the LaTeX source — recompile that text.
        self._schedule_compile()

    def _compile(self):
        """Manual compile — force it now and show the PDF (compiles the
        current LaTeX, including any manual edits)."""
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

    def _new_window(self):
        """Open a second, independent KherveSlide window (e.g. to work on
        another presentation, or copy objects between decks)."""
        win = SlideWindow(dark=self._dark, theme=self._theme)
        # Hold a reference so the new window isn't garbage-collected, and
        # offset it a little so it doesn't land exactly on top of this one.
        SlideWindow._extra_windows.append(win)
        win.move(self.x() + 40, self.y() + 40)
        win.show()

    def _save_deck(self):
        if self.path is None:
            return self._save_deck_as()
        self._write_deck_to(self.path)

    def _save_deck_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save presentation as", "",
            "KherveSlide presentation (*.kslide)")
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() not in (".kslide", ".json"):
            p = p.with_suffix(".kslide")
        self.path = p
        self._update_title()
        self._write_deck_to(p)

    @staticmethod
    def _deck_stem(path: Path) -> str:
        """Base name for the presentation, stripping the compound
        ``.kslide.json`` suffix as well as the plain ``.kslide``."""
        if path.name.endswith(".kslide.json"):
            return path.name[:-len(".kslide.json")]
        return path.stem

    def _write_deck_to(self, path: Path) -> None:
        """Write the presentation, then auto-commit (and push if a remote
        is configured). The ``.kslide`` JSON is the source of truth; a
        ``.tex`` beamer export is written alongside so ``git diff`` shows
        meaningful content changes. Push runs on a background thread so a
        slow / dead remote can't freeze the window on every save."""
        path.write_text(deck_to_json(self.deck), encoding="utf-8")
        stem = self._deck_stem(path)
        try:
            (path.parent / f"{stem}.tex").write_text(
                serialize_deck(self.deck), encoding="utf-8")
        except Exception:
            pass  # a .tex export failure must never block saving the model
        self._add_recent(path)

        commit_msg = self._pending_commit_msg or (
            f"Save {path.name} at "
            f"{datetime.now().isoformat(timespec='seconds')}")
        self._pending_commit_msg = None
        if not git_backend.is_available():
            self.statusBar().showMessage(
                f"Saved {path} (install pygit2 to enable version history)",
                5000)
            return
        git_backend.init_repo(path.parent)
        oid = git_backend.commit_all(path.parent, commit_msg, file_stem=stem)
        if not oid:
            self.statusBar().showMessage("✔ Saved (nothing new to snapshot)",
                                         4000)
        elif git_backend.get_remotes(path.parent):
            self.statusBar().showMessage(
                "✔ Saved and snapshot created — uploading…", 0)
            self._start_git_worker("push", path.parent, "origin")
        else:
            self.statusBar().showMessage(
                "✔ Saved and snapshot created "
                "(use Git → Connect to GitHub to enable cloud backup)", 6000)

    def _open_deck(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open presentation", "",
            "KherveSlide presentation (*.kslide *.kslide.json *.json)")
        if path:
            self.open_path(path)

    def _import_pptx(self):
        from . import pptx_import
        if not pptx_import.available():
            QMessageBox.warning(
                self, "Import PowerPoint",
                "The python-pptx package is needed to import .pptx files.\n"
                "Install it with:  pip install python-pptx")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import PowerPoint", "", "PowerPoint (*.pptx)")
        if not path:
            return
        src = Path(path)
        media = src.parent / f"{src.stem}_media"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            deck = pptx_import.import_pptx(src, media)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Import PowerPoint",
                                f"Could not import this file:\n{e}")
            return
        QApplication.restoreOverrideCursor()
        self.deck = deck
        self.current = 0
        self.path = None          # imported — user saves it as a .kslide
        self._update_title()
        self._reload_all()
        self._reset_history()
        self.statusBar().showMessage(
            f"Imported {len(deck.slides)} slide(s) from PowerPoint — "
            "review and Save As a .kslide")

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

    # ---------------- git / version control ----------------

    def _commit_and_maybe_push(self) -> None:
        """Save a snapshot with a custom commit message, then upload."""
        if self.path is None:
            reply = QMessageBox.information(
                self, "Save snapshot",
                "You need to save this presentation to a file first before "
                "a snapshot can be created.\n\n"
                "Save it now?",
                QMessageBox.Yes | QMessageBox.Cancel)
            if reply == QMessageBox.Yes:
                self._save_deck_as()
            return
        default_msg = (f"Save {self.path.name} at "
                       f"{datetime.now().isoformat(timespec='seconds')}")
        msg, ok = QInputDialog.getText(
            self, "Commit message", "Describe what you changed:",
            text=default_msg)
        if not ok:
            return
        self._pending_commit_msg = msg.strip() or default_msg
        self._write_deck_to(self.path)

    def _start_git_worker(self, op: str, repo_dir: Path,
                          remote_name: str) -> None:
        """Spawn a _GitNetworkWorker for pull / push. Kept on
        self._git_worker so we hold a reference (Qt threads get GC'd
        otherwise) and can re-check it before starting another op."""
        worker = _GitNetworkWorker(op, repo_dir, remote_name)
        worker.finished_with.connect(self._on_git_done)
        self._git_worker = worker
        if op == "pull":
            self.statusBar().showMessage(
                f"Downloading latest from {remote_name}…", 0)
        worker.start()

    def _on_git_done(self, op: str, ok: bool, msg: str) -> None:
        if op == "pull":
            if ok:
                if "up to date" in msg.lower():
                    self.statusBar().showMessage(
                        "✔ Already up to date — you have the latest version",
                        5000)
                else:
                    self.statusBar().showMessage(f"✔ {msg}", 6000)
                    self._reload_current()
            else:
                self.statusBar().clearMessage()
                QMessageBox.warning(
                    self, "Download failed",
                    f"{msg}\n\n"
                    "What you can try:\n"
                    "  • Check your internet connection\n"
                    "  • Make sure the cloud URL is correct "
                    "(Git → Connect to GitHub)\n"
                    "  • If the problem says \"diverged\", resolve the "
                    "merge from the git command line")
        elif op == "push":
            if ok:
                self.statusBar().showMessage(
                    "✔ Saved, snapshot created, and uploaded to cloud", 5000)
            else:
                self.statusBar().showMessage(
                    "✔ Saved and snapshot created "
                    "(⚠ upload failed — see dialog)", 8000)
                self._show_push_failure_dialog(msg)
        self._git_worker = None

    def _show_push_failure_dialog(self, error_msg: str) -> None:
        """Surface a real push failure with actionable advice. The most
        common cause on Windows is HTTPS authentication: GitHub stopped
        accepting passwords, so the user needs a Personal Access Token
        stored via Windows Credential Manager (which the system `git` CLI
        talks to). If `git` isn't on PATH at all, that's a separate hint."""
        hints = []
        if "Authentication" in error_msg or "authentication" in error_msg:
            hints.append(
                "GitHub no longer accepts your account password over "
                "HTTPS — you need a <b>Personal Access Token</b>.<br>"
                "&nbsp;&nbsp;1. Go to <a href='https://github.com/settings/tokens'>"
                "github.com/settings/tokens</a> → Generate new token (classic)"
                "<br>&nbsp;&nbsp;2. Tick the <code>repo</code> scope, generate, "
                "copy the token"
                "<br>&nbsp;&nbsp;3. Next time the editor asks for a password, "
                "paste the token instead of your password.")
        elif "not found" in error_msg.lower() or "404" in error_msg:
            hints.append(
                "GitHub says the repository does not exist. Check that "
                "the URL in <b>Git → Connect to GitHub</b> matches the "
                "one shown on the repo's GitHub page (Code → HTTPS).")
        elif "rejected" in error_msg.lower() or "non-fast-forward" in error_msg:
            hints.append(
                "Someone else (or another machine) pushed to this branch "
                "since you last pulled. Use <b>Git → Download latest from "
                "cloud</b> first, then save again.")
        if not git_backend._system_git_available():
            hints.append(
                "<i>Tip: install Git for Windows so the editor can use "
                "your Windows Credential Manager for HTTPS pushes — "
                "<a href='https://git-scm.com/download/win'>"
                "git-scm.com/download/win</a></i>")
        body = (f"<b>Could not upload to cloud.</b><br><br>"
                f"<code>{error_msg}</code>")
        if hints:
            body += "<br><br>" + "<br><br>".join(hints)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Upload failed")
        box.setTextFormat(Qt.RichText)
        box.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        box.setText(body)
        box.exec()

    def _pull_from_remote(self) -> None:
        if self.path is None:
            QMessageBox.information(
                self, "Download latest",
                "You need to save this presentation first.\n\n"
                "Use File → Save (Ctrl+S), then try again.")
            return
        if not git_backend.is_available():
            self._warn_no_pygit2("Download latest")
            return
        remotes = git_backend.get_remotes(self.path.parent)
        if not remotes:
            ask = QMessageBox.question(
                self, "Download latest",
                "This presentation is not connected to a cloud service "
                "yet.\n\nTo download changes from a collaborator you first "
                "need to connect to GitHub, GitLab or another git server.\n\n"
                "Would you like to set that up now?")
            if ask == QMessageBox.Yes:
                self._configure_remotes()
            return
        if len(remotes) == 1:
            remote_name = remotes[0][0]
        else:
            names = [n for n, _ in remotes]
            chosen, ok = QInputDialog.getItem(
                self, "Download from…", "Which cloud service?",
                names, 0, False)
            if not ok:
                return
            remote_name = chosen
        # Refuse a second network op while one is running — otherwise two
        # threads race on the same repo and libgit2 can crash.
        if self._git_worker is not None and self._git_worker.isRunning():
            self.statusBar().showMessage(
                "A git operation is already in progress, please wait…", 4000)
            return
        self._start_git_worker("pull", self.path.parent, remote_name)

    def _configure_remotes(self) -> None:
        if self.path is None:
            QMessageBox.information(
                self, "Connect to cloud",
                "You need to save this presentation first so KherveSlide "
                "knows where to create the connection.\n\n"
                "Use File → Save (Ctrl+S), then try again.")
            return
        if not git_backend.is_available():
            self._warn_no_pygit2("Connect to cloud")
            return
        from .remote_dialog import RemoteDialog
        RemoteDialog(self.path.parent, self).exec()

    def _show_history(self) -> None:
        if self.path is None:
            QMessageBox.information(
                self, "Version history",
                "You need to save this presentation at least once before "
                "there is any history to show.\n\n"
                "Use File → Save (Ctrl+S), then try again.")
            return
        if not git_backend.is_available():
            self._warn_no_pygit2("Version history")
            return
        if not git_backend.history_detailed(self.path.parent, limit=1):
            QMessageBox.information(
                self, "Version history",
                "No snapshots yet. Every time you save, KherveSlide "
                "automatically creates a snapshot.\n\n"
                "Save your presentation and come back here to see its "
                "history.")
            return
        from .history_dialog import HistoryDialog
        HistoryDialog(self.path.parent, self,
                      file_stem=self._deck_stem(self.path)).exec()

    def _show_branches(self) -> None:
        """Open the history dialog (which includes branch management)
        without file_stem filtering so all branches are visible."""
        if self.path is None:
            QMessageBox.information(
                self, "Branches",
                "Save this presentation first so the repository exists.")
            return
        if not git_backend.is_available():
            self._warn_no_pygit2("Branches")
            return
        from .history_dialog import HistoryDialog
        HistoryDialog(self.path.parent, self).exec()

    def _reload_current(self) -> None:
        """Re-read the current presentation from disk after an external
        change (a successful pull, or a restore from the history dialog).
        Best-effort: silently no-ops if the file has gone away."""
        if self.path is None or not self.path.exists():
            return
        try:
            self.open_path(self.path)
        except Exception as exc:
            self.statusBar().showMessage(f"Reload failed: {exc}", 6000)

    def _warn_no_pygit2(self, title: str) -> None:
        QMessageBox.warning(
            self, title,
            "The pygit2 library is not installed, so version control and "
            "cloud features are unavailable.\n\n"
            "To fix this, run:  pip install pygit2")

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
        Path(path).write_text(self.latex_view.source(), encoding="utf-8")
        self.statusBar().showMessage(f"Exported {path}")
