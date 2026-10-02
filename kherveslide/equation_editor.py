"""Equation editors: the structured WYSIWYG math editor, plus the
live-preview template editors for mhchem chemistry and chemfig.

Kept out of ``mainwindow`` so ``editor`` can open these dialogs when the
user double-clicks a rendered equation without importing the main window
(which imports ``editor``). Mirrors KherveSlide's ``equation_editor``.
"""
from __future__ import annotations

import re as _re
import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QIcon, QImage, QPixmap, QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea,
    QStackedWidget, QTabWidget, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from . import (chemfig, chemistry, equations, mathbox, mathlayout,
               symbols)
from .math_widget import MathEditWidget


_BEGIN_RE = _re.compile(r"\\begin\{(\w+\*?)\}$")


class _EquationLatexEdit(QPlainTextEdit):
    """LaTeX input field that intercepts Tab/Shift+Tab to navigate
    between placeholder slots instead of inserting tab chars.

    Placeholders are first-class here: every occurrence is highlighted so
    the user can see the empty slots at a glance, and a single click on
    one selects the whole token so typing replaces it — no more manually
    dragging over ``\\square`` character by character.

    The slot token is configurable because mhchem chokes on a bare
    ``\\square`` — see ``chemistry.PLACEHOLDER``."""

    def __init__(self, placeholder: str = r"\square", parent=None):
        super().__init__(parent)
        self._PLACEHOLDER = placeholder
        self.textChanged.connect(self._highlight_placeholders)

    # ---- placeholder plumbing ----

    def placeholder_spans(self) -> list[tuple[int, int]]:
        """(start, end) of every placeholder occurrence in the source."""
        text = self.toPlainText()
        ph = self._PLACEHOLDER
        spans = []
        idx = text.find(ph)
        while idx >= 0:
            spans.append((idx, idx + len(ph)))
            idx = text.find(ph, idx + len(ph))
        return spans

    def _highlight_placeholders(self) -> None:
        sels = []
        for start, end in self.placeholder_spans():
            sel = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#cfe4fb"))
            fmt.setForeground(QColor("#1a4d8f"))
            sel.format = fmt
            cur = self.textCursor()
            cur.setPosition(start)
            cur.setPosition(end, QTextCursor.KeepAnchor)
            sel.cursor = cur
            sels.append(sel)
        self.setExtraSelections(sels)

    def _select_placeholder_at(self, pos: int) -> bool:
        """Select the placeholder containing (or ending at) *pos*."""
        for start, end in self.placeholder_spans():
            if start <= pos <= end:
                cur = self.textCursor()
                cur.setPosition(start)
                cur.setPosition(end, QTextCursor.KeepAnchor)
                self.setTextCursor(cur)
                return True
        return False

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        # Only promote a plain click to a placeholder selection; keep
        # drag-selections exactly as the user made them.
        if not self.textCursor().hasSelection():
            self._select_placeholder_at(self.textCursor().position())

    def mouseDoubleClickEvent(self, ev):
        cur = self.cursorForPosition(ev.position().toPoint())
        if self._select_placeholder_at(cur.position()):
            return
        super().mouseDoubleClickEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Tab and not ev.modifiers():
            self._jump_placeholder(forward=True)
            return
        if ev.key() == Qt.Key_Backtab or (
                ev.key() == Qt.Key_Tab
                and ev.modifiers() == Qt.ShiftModifier):
            self._jump_placeholder(forward=False)
            return
        if ev.text() == "}":
            if self._auto_close_begin():
                return
        super().keyPressEvent(ev)

    def _auto_close_begin(self) -> bool:
        """If the cursor sits right after ``\\begin{xxx``, insert the
        closing ``}`` plus ``\\n\\square\\n\\end{xxx}`` and return True."""
        cursor = self.textCursor()
        text = self.toPlainText()
        before = text[:cursor.position()]
        m = _BEGIN_RE.search(before + "}")
        if not m:
            return False
        env = m.group(1)
        self.insertPlainText(f"}}\n{self._PLACEHOLDER}\n\\end{{{env}}}")
        return True

    def _jump_placeholder(self, forward: bool) -> None:
        text = self.toPlainText()
        cursor = self.textCursor()
        pos = cursor.position()
        ph = self._PLACEHOLDER
        if forward:
            idx = text.find(ph, pos)
            if idx < 0:
                idx = text.find(ph)  # wrap around
        else:
            idx = text.rfind(ph, 0, pos)
            if idx < 0:
                idx = text.rfind(ph)  # wrap around
        if idx < 0:
            return
        cursor.setPosition(idx)
        cursor.setPosition(idx + len(ph), QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)


class _TemplatePaletteDialog(QDialog):
    """Shared shell for the equation and chemistry editors.

    Shows a rendered preview that updates as you type, a category
    toolbar with template buttons, and a source field with
    Tab-navigable placeholders. Clicking Insert emits the final
    LaTeX for insertion into the document.

    Subclasses supply the template data, the two preview renderers and
    the placeholder token; everything else is identical.
    """

    _TITLE = "Template editor"
    # Each entry is a zero-arg QIcon factory, or a str to label the button
    # with text when no drawn icon exists for that category.
    _CATEGORY_ICONS: list = []
    _CAT_COLS = 6
    _CAT_BTN_SIZE = (40, 34)
    _EMPTY_HINT = "Click a template to start"
    _EDIT_HINT = ""
    _SOURCE_LABEL = "LaTeX source:"
    _PLACEHOLDER = r"\square"

    def _groups(self) -> list:
        raise NotImplementedError

    def _render_template(self, latex: str):
        raise NotImplementedError

    def _render_live(self, latex: str):
        raise NotImplementedError

    def _extra_widgets(self, root: QVBoxLayout) -> None:
        """Hook for subclass controls between the source field and the
        button box."""

    def __init__(self, parent: QWidget | None = None,
                 initial_latex: str = ""):
        super().__init__(parent)
        self.setWindowTitle(self._TITLE)
        self.resize(640, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ---- live preview ----
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumHeight(80)
        self._preview.setStyleSheet(
            "QLabel { background: white; border: 1px solid #ccc; "
            "border-radius: 4px; padding: 12px; }")
        self._preview.setText(
            f"<span style='color:#999;'>{self._EMPTY_HINT}</span>")
        root.addWidget(self._preview)

        # ---- category toolbar ----
        toolbar = QFrame()
        toolbar.setFrameShape(QFrame.StyledPanel)
        tb_grid = QGridLayout(toolbar)
        tb_grid.setSpacing(2)
        tb_grid.setContentsMargins(4, 4, 4, 4)
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        groups = self._groups()
        cols = self._CAT_COLS
        for idx, (group_name, _items) in enumerate(groups):
            btn = QToolButton()
            btn.setCheckable(True)
            spec = (self._CATEGORY_ICONS[idx]
                    if idx < len(self._CATEGORY_ICONS) else None)
            if callable(spec):
                btn.setIcon(spec())
                btn.setIconSize(QSize(24, 24))
            else:
                btn.setText(spec if spec else group_name[:3])
            btn.setToolTip(group_name)
            btn.setFixedSize(*self._CAT_BTN_SIZE)
            btn.setStyleSheet(
                "QToolButton { border: 1px solid transparent; "
                "border-radius: 3px; }"
                "QToolButton:checked { border: 1px solid #1a6dd8; "
                "background: #e0edfa; }")
            self._btn_group.addButton(btn, idx)
            tb_grid.addWidget(btn, idx // cols, idx % cols)
        root.addWidget(toolbar)

        # ---- category label ----
        self._cat_label = QLabel()
        self._cat_label.setStyleSheet(
            "font-weight: bold; color: #444; padding: 2px 4px;")
        root.addWidget(self._cat_label)

        # ---- template panel (stacked, one page per category) ----
        self._stack = QStackedWidget()
        self._populated: set[int] = set()
        for _ in groups:
            page = QWidget()
            QVBoxLayout(page)
            self._stack.addWidget(page)
        self._stack.setMaximumHeight(160)
        root.addWidget(self._stack)

        self._btn_group.idClicked.connect(self._show_category)
        first = self._btn_group.button(0)
        if first:
            first.setChecked(True)
            self._show_category(0)

        # ---- LaTeX input field ----
        latex_label = QLabel(self._SOURCE_LABEL)
        latex_label.setStyleSheet("color: #666; font-size: 9pt;")
        root.addWidget(latex_label)
        self._edit = _EquationLatexEdit(self._PLACEHOLDER)
        self._edit.setMaximumHeight(72)
        from PySide6.QtGui import QFont as _QFont
        mf = _QFont("Consolas"); mf.setStyleHint(_QFont.Monospace)
        mf.setPointSize(10)
        self._edit.setFont(mf)
        self._edit.setPlaceholderText(self._EDIT_HINT)
        root.addWidget(self._edit)

        # ---- placeholder hint (live count + how to fill them) ----
        self._ph_hint = QLabel()
        self._ph_hint.setStyleSheet("color: #888; font-size: 8pt;")
        root.addWidget(self._ph_hint)
        self._edit.textChanged.connect(self._update_placeholder_hint)
        self._update_placeholder_hint()

        self._extra_widgets(root)

        # ---- Insert / Cancel buttons ----
        btn_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("Insert")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

        # ---- debounced live preview ----
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._update_preview)
        self._edit.textChanged.connect(self._preview_timer.start)

        # Seed with initial LaTeX if provided, with the first empty slot
        # pre-selected so the user can start typing straight away.
        if initial_latex:
            self._edit.setPlainText(initial_latex)
            self._edit._jump_placeholder(forward=True)
            self._edit.setFocus()

    def latex(self) -> str:
        return self._edit.toPlainText().strip()

    def _update_placeholder_hint(self) -> None:
        n = len(self._edit.placeholder_spans())
        if n:
            plural = "s" if n != 1 else ""
            self._ph_hint.setText(
                f"{n} empty slot{plural} — click one (or press Tab) to "
                "select it, then type to fill it in.")
        else:
            self._ph_hint.setText("")

    # ---- category / template plumbing (reused from old builder) ----

    def _show_category(self, index: int) -> None:
        groups = self._groups()
        if index < 0 or index >= len(groups):
            return
        group_name, items = groups[index]
        self._cat_label.setText(group_name)
        self._stack.setCurrentIndex(index)
        if index not in self._populated:
            self._populate_page(index, items)
            self._populated.add(index)

    def _populate_page(self, index: int, items: list) -> None:
        page = self._stack.widget(index)
        old_layout = page.layout()
        if old_layout:
            while old_layout.count():
                old_layout.takeAt(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setSpacing(4)
        grid.setContentsMargins(4, 4, 4, 4)
        btn_cols = 5
        for i, (latex, preview_text) in enumerate(items):
            btn = QToolButton()
            btn.setToolTip(f"{preview_text}\n{latex}")
            pixmap = self._render_template(latex)
            if pixmap and not pixmap.isNull():
                btn.setIcon(QIcon(pixmap))
                pw, ph = pixmap.width(), pixmap.height()
                btn.setIconSize(QSize(min(pw, 100), min(ph, 50)))
                btn.setFixedSize(min(pw + 12, 112), min(ph + 8, 58))
            else:
                btn.setText(preview_text)
                btn.setFixedSize(80, 40)
            btn.setStyleSheet(
                "QToolButton { border: 1px solid #ccc; "
                "border-radius: 3px; padding: 2px; }"
                "QToolButton:hover { border: 1px solid #1a6dd8; "
                "background: #e8f0fa; }")
            btn.clicked.connect(
                lambda checked=False, tex=latex: self._insert_template(tex))
            grid.addWidget(btn, i // btn_cols, i % btn_cols)
        scroll.setWidget(inner)
        old_layout.addWidget(scroll)

    def _insert_template(self, latex: str) -> None:
        """Insert a template at the cursor, replacing the selected
        placeholder if one is selected."""
        cursor = self._edit.textCursor()
        cursor.insertText(latex)
        self._edit.setFocus()
        # Jump to first placeholder in what we just inserted
        self._edit._jump_placeholder(forward=True)

    def _update_preview(self) -> None:
        text = self._edit.toPlainText().strip()
        if not text:
            self._preview.setPixmap(QPixmap())
            self._preview.setText(
                f"<span style='color:#999;'>{self._EMPTY_HINT}</span>")
            return
        px = self._render_live(text)
        if px and not px.isNull():
            self._preview.setText("")
            self._preview.setPixmap(px)
        else:
            self._preview.setPixmap(QPixmap())
            self._preview.setText(
                "<span style='color:#c00;'>Cannot render: check "
                "syntax</span>")


_TEMPLATE_NAMES = {
    r"\frac{\square}{\square}": "Fraction",
    r"\tfrac{\square}{\square}": "Small fraction",
    r"\dfrac{\square}{\square}": "Display fraction",
    r"\sqrt{\square}": "Square root",
    r"\sqrt[\square]{\square}": "n-th root",
    r"\binom{\square}{\square}": "Binomial coefficient",
    r"\sum_{\square}^{\square} \square": "Summation",
    r"\sum_{i=1}^{n} \square": "Sum from i = 1 to n",
    r"\prod_{\square}^{\square} \square": "Product",
    r"\lim_{\square \to \square} \square": "Limit",
    r"\liminf_{\square \to \square} \square": "Limit inferior",
    r"\limsup_{\square \to \square} \square": "Limit superior",
    r"\int_{\square}^{\square} \square \, d\square": "Definite integral",
    r"\int \square \, d\square": "Indefinite integral",
    r"\iint_{\square} \square \, dA": "Double integral",
    r"\iiint_{\square} \square \, dV": "Triple integral",
    r"\oint_{\square} \square \, d\square": "Contour integral",
    r"\int_{-\infty}^{\infty} \square \, d\square": "Integral over ℝ",
    r"\square^{\square}": "Superscript",
    r"\square_{\square}": "Subscript",
    r"\square_{\square}^{\square}": "Subscript and superscript",
    r"e^{\square}": "Exponential",
    r"10^{\square}": "Power of ten",
    r"\square^{-1}": "Inverse",
    r"\frac{d\square}{d\square}": "Derivative",
    r"\frac{d^{2}\square}{d\square^{2}}": "Second derivative",
    r"\frac{\partial \square}{\partial \square}": "Partial derivative",
    r"\frac{\partial^{2} \square}{\partial \square^{2}}":
        "Second partial derivative",
    r"\nabla \square": "Gradient",
    r"\nabla^{2} \square": "Laplacian",
    r"\vec{\square}": "Vector arrow",
    r"\hat{\square}": "Hat",
    r"\bar{\square}": "Bar",
    r"\left( \square \right)": "Parentheses",
    r"\left[ \square \right]": "Square brackets",
    r"\left\{ \square \right\}": "Curly braces",
    r"\left| \square \right|": "Absolute value",
    r"\left\| \square \right\|": "Norm",
    r"\left\langle \square \right\rangle": "Angle brackets",
    r"\left\lfloor \square \right\rfloor": "Floor",
    r"\left\lceil \square \right\rceil": "Ceiling",
    r"\square = \square": "Equals",
    r"\square \approx \square": "Approximately equal",
    r"\square \neq \square": "Not equal",
    r"\square \leq \square": "Less than or equal",
    r"\square \geq \square": "Greater than or equal",
    r"\square \propto \square": "Proportional to",
    r"\square \cdot \square": "Dot product",
    r"\square \times \square": "Cross product",
    r"\log_{\square}(\square)": "Logarithm with base",
    r"\ln(\square)": "Natural logarithm",
    r"\exp(\square)": "Exponential function",
}
_ENV_NAMES = {"pmatrix": "2×2 matrix (parentheses)",
              "bmatrix": "2×2 matrix (brackets)",
              "vmatrix": "2×2 determinant", "equation": "Single equation",
              "align": "Aligned equations", "cases": "Cases (piecewise)"}

# (label under the button, sample drawn on it) per EQUATION_GROUPS entry.
_CATEGORY_FACES = [
    ("Fraction", r"\frac{x}{y}"), ("Large op", r"\sum"),
    ("Integral", r"\int"), ("Script", r"x^{2}"),
    ("Derivative", r"\frac{dy}{dx}"), ("Greek", r"\alpha\beta"),
    ("Matrix", r"\begin{pmatrix}a&b\\c&d\end{pmatrix}"),
    ("Bracket", r"\{x\}"), ("Relation", r"\leq"),
    ("Function", r"\sin\theta"),
    ("Multi-line", r"\begin{cases}a\\b\end{cases}"),
]

_SYMBOL_TABS = [
    ("Greek", "α"), ("Capitals", "Ω"), ("Operators", "±"),
    ("Relations", "≤"), ("Arrows", "→"), ("Calculus", "∫"),
    ("Sets & logic", "∀"), ("Misc", "∞"), ("Accents", "â"),
]

_NICE = {
    "pm": "Plus-minus", "mp": "Minus-plus", "times": "Times",
    "div": "Divide", "cdot": "Centre dot", "leq": "Less or equal",
    "geq": "Greater or equal", "neq": "Not equal", "approx": "Approximately",
    "equiv": "Identical to", "propto": "Proportional to",
    "infty": "Infinity", "partial": "Partial", "nabla": "Nabla",
    "to": "Tends to", "Rightarrow": "Implies", "Leftrightarrow": "If and only if",
    "in": "Element of", "notin": "Not an element of",
    "forall": "For all", "exists": "There exists", "hbar": "h-bar",
    "sum": "Summation", "prod": "Product", "int": "Integral",
    "iint": "Double integral", "iiint": "Triple integral",
    "oint": "Contour integral", "sqrt": "Square root", "frac": "Fraction",
    "ll": "Much less than", "gg": "Much greater than", "sim": "Similar to",
    "cong": "Congruent", "perp": "Perpendicular", "parallel": "Parallel",
    "degree": "Degree", "emptyset": "Empty set", "cap": "Intersection",
    "cup": "Union", "subset": "Subset", "subseteq": "Subset or equal",
}


def _nice_name(latex: str) -> str:
    m = _re.match(r"\\([A-Za-z]+)", latex)
    if not m:
        return latex
    name = m.group(1)
    if name in _NICE:
        return _NICE[name]
    if name.lower() in mathbox._GREEK_LOWER or name in mathbox._GREEK_UPPER:
        return ("Capital " if name[0].isupper() else "") + name.lower()
    return name[0].upper() + name[1:]


def _template_name(latex: str, fallback: str) -> str:
    if latex in _TEMPLATE_NAMES:
        return _TEMPLATE_NAMES[latex]
    m = _re.match(r"\\begin\{(\w+)\}", latex)
    if m and m.group(1) in _ENV_NAMES:
        return _ENV_NAMES[m.group(1)]
    m = _re.match(r"\\([a-z]+)\(", latex)
    if m:
        return {"sin": "Sine", "cos": "Cosine", "tan": "Tangent",
                "arctan": "Inverse tangent"}.get(m.group(1), m.group(1))
    if latex.startswith("\\") and "{" not in latex:
        return _nice_name(latex)
    return fallback


def _symbol_insert_latex(latex: str) -> str:
    """Palette entries like ``\\hat{a}`` insert an empty slot, not 'a'."""
    if latex.startswith(r"\mathbb"):
        return latex
    return _re.sub(r"\{[a-z]\}", r"{\\square}", latex)


_DIALOG_QSS = """
QDialog#EquationEditor { background: #f4f6f9; }
QFrame#Ribbon { background: #ffffff; border-bottom: 1px solid #dde2e8; }
QFrame#Ribbon QStackedWidget, QFrame#Ribbon QScrollArea,
QWidget#PaletteHost { background: #ffffff; }
QTabBar::tab { padding: 6px 16px; margin-right: 2px; border: none;
    color: #5b6573; font-weight: 600; background: transparent; }
QTabBar::tab:selected { color: #1f5fd1; border-bottom: 2px solid #2f6fde; }
QTabBar::tab:hover { color: #1f2937; }
QTabWidget::pane { border: none; }
QToolButton#Cat { border: 1px solid transparent; border-radius: 6px;
    padding: 3px 2px; color: #374151; font-size: 11px; }
QToolButton#Cat:hover { background: #eef3fb; border-color: #d4e1f7; }
QToolButton#Cat:checked { background: #e3edfd; border-color: #9dbcf2;
    color: #1f5fd1; }
QToolButton#Tpl, QToolButton#Sym { background: #ffffff;
    border: 1px solid #e3e7ed; border-radius: 6px; }
QToolButton#Tpl:hover, QToolButton#Sym:hover { background: #eef4ff;
    border-color: #8fb2ef; }
QToolButton#Tpl:pressed, QToolButton#Sym:pressed { background: #dce8fd; }
QFrame#Canvas { background: #ffffff; border: 1px solid #d6dce4;
    border-radius: 10px; }
QLabel#Hint { color: #8a94a3; font-size: 11px; }
QLabel#SlotHint { color: #1f5fd1; font-size: 11px; }
QPlainTextEdit#Source { background: #fbfcfd; border: 1px solid #d6dce4;
    border-radius: 6px; padding: 4px; }
QPushButton { padding: 6px 16px; border-radius: 6px;
    border: 1px solid #cfd6df; background: #ffffff; }
QPushButton:hover { background: #f1f4f8; }
QPushButton#Primary { background: #2f6fde; color: white;
    border-color: #2f6fde; font-weight: 600; }
QPushButton#Primary:hover { background: #245fcb; }
QToolButton#Toggle { border: 1px solid #cfd6df; border-radius: 6px;
    padding: 5px 10px; background: #ffffff; color: #374151; }
QToolButton#Toggle:checked { background: #e3edfd; border-color: #9dbcf2;
    color: #1f5fd1; }
"""


class EquationEditorDialog(QDialog):
    """Structured WYSIWYG equation editor.

    The equation is edited as typeset math (fractions, scripts, roots,
    matrices ...) in :class:`math_widget.MathEditWidget`; the LaTeX is
    generated from the tree and only shown on request.
    """

    _TITLE = "Equation editor"

    def __init__(self, parent=None, initial_latex: str = "",
                 show_layout: bool | None = None, display: bool = True,
                 numbered: bool = True):
        super().__init__(parent)
        self.setObjectName("EquationEditor")
        self.setWindowTitle(self._TITLE)
        self.setStyleSheet(_DIALOG_QSS)
        self.resize(860, 640)
        self._initial = (initial_latex or "").strip()
        self._dirty = False
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_ribbon())

        body = QVBoxLayout()
        body.setContentsMargins(16, 14, 16, 12)
        body.setSpacing(8)
        root.addLayout(body, 1)

        # ---- the equation canvas ----
        canvas = QFrame()
        canvas.setObjectName("Canvas")
        cl = QVBoxLayout(canvas)
        cl.setContentsMargins(1, 1, 1, 6)
        cl.setSpacing(0)
        self._math = MathEditWidget()
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("background: white;")
        self._scroll.setWidget(self._math)
        cl.addWidget(self._scroll, 1)
        hint = QLabel(
            "Type to build the equation  ·  /  fraction  ·  ^  superscript"
            "  ·  _  subscript  ·  \\  commands (e.g. \\alpha)  ·  "
            "Tab  next slot  ·  Ctrl + / −  zoom")
        hint.setObjectName("Hint")
        hint.setAlignment(Qt.AlignCenter)
        cl.addWidget(hint)
        body.addWidget(canvas, 1)

        # ---- LaTeX source (hidden until asked for) ----
        self._source_panel = QWidget()
        sp = QVBoxLayout(self._source_panel)
        sp.setContentsMargins(0, 0, 0, 0)
        sp.setSpacing(4)
        lab = QLabel("LaTeX — edit here to change the equation")
        lab.setObjectName("Hint")
        sp.addWidget(lab)
        self._edit = _EquationLatexEdit(r"\square")
        self._edit.setObjectName("Source")
        mf = QFont("Menlo")
        mf.setStyleHint(QFont.Monospace)
        mf.setPointSize(11)
        self._edit.setFont(mf)
        self._edit.setFixedHeight(84)
        sp.addWidget(self._edit)
        self._source_panel.setVisible(False)
        body.addWidget(self._source_panel)

        # ---- bottom bar ----
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self._latex_toggle = QToolButton()
        self._latex_toggle.setObjectName("Toggle")
        self._latex_toggle.setText("Show LaTeX")
        self._latex_toggle.setCheckable(True)
        self._latex_toggle.toggled.connect(self._toggle_source)
        bar.addWidget(self._latex_toggle)
        self._display_cb = QCheckBox("Display on its own line")
        self._display_cb.setChecked(display)
        self._display_cb.setToolTip(
            "Checked: a display equation on its own line.\n"
            "Unchecked: inline math inside the current paragraph.")
        self._display_cb.toggled.connect(self._math.set_display)
        bar.addWidget(self._display_cb)
        self._numbered_cb = QCheckBox("Numbered")
        self._numbered_cb.setChecked(numbered)
        self._numbered_cb.setEnabled(display)
        self._numbered_cb.setToolTip(
            "Give the display equation a number, e.g. (1).")
        self._display_cb.toggled.connect(self._numbered_cb.setEnabled)
        bar.addWidget(self._numbered_cb)
        self._math.set_display(display)
        self._ph_hint = QLabel()
        self._ph_hint.setObjectName("SlotHint")
        bar.addWidget(self._ph_hint)
        bar.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self._insert_btn = QPushButton("Insert")
        self._insert_btn.setObjectName("Primary")
        self._insert_btn.setDefault(True)
        self._insert_btn.clicked.connect(self.accept)
        bar.addWidget(cancel)
        bar.addWidget(self._insert_btn)
        body.addLayout(bar)

        self._math.changed.connect(self._on_math_changed)
        self._edit.textChanged.connect(self._on_source_changed)

        if show_layout is None:
            # Double-click re-edit replaces the equation in place, so
            # whether it is inline or display is already decided.
            show_layout = not self._initial
        if not show_layout:
            self._display_cb.hide()
            self._numbered_cb.hide()
        if self._initial:
            self._syncing = True
            self._math.set_latex(self._initial)
            self._edit.setPlainText(
                self._math.latex(mathbox.PLACEHOLDER))
            self._syncing = False
            ed = self._math.editor
            if mathbox.count_empty(ed.root):
                ed.set_cursor(ed.root, 0)
                ed.next_slot()
            self._edit._jump_placeholder(forward=True)
        self._update_slot_hint()
        self._math.setFocus()

    # ---------------------------------------------------------- ribbon
    def _build_ribbon(self) -> QWidget:
        ribbon = QFrame()
        ribbon.setObjectName("Ribbon")
        lay = QVBoxLayout(ribbon)
        lay.setContentsMargins(10, 4, 10, 8)
        lay.setSpacing(4)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._build_structures(), "Structures")
        tabs.addTab(self._build_symbols(), "Symbols")
        lay.addWidget(tabs)
        self._tabs = tabs
        return ribbon

    def _build_structures(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(6)
        strip = QHBoxLayout()
        strip.setSpacing(2)
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        groups = equations.EQUATION_GROUPS
        for idx, (group_name, _items) in enumerate(groups):
            label, sample = _CATEGORY_FACES[idx] \
                if idx < len(_CATEGORY_FACES) else (group_name, "")
            btn = QToolButton()
            btn.setObjectName("Cat")
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setText(label)
            btn.setToolTip(group_name)
            if sample:
                btn.setIcon(QIcon(mathlayout.render_pixmap(sample, 15)))
                btn.setIconSize(QSize(34, 26))
            btn.setFixedSize(68, 54)
            self._btn_group.addButton(btn, idx)
            strip.addWidget(btn)
        strip.addStretch(1)
        v.addLayout(strip)
        self._stack = QStackedWidget()
        self._populated: set[int] = set()
        for _ in groups:
            self._stack.addWidget(QWidget())
        self._stack.setFixedHeight(112)
        v.addWidget(self._stack)
        self._btn_group.idClicked.connect(self._show_category)
        self._btn_group.button(0).setChecked(True)
        self._show_category(0)
        return page

    def _show_category(self, index: int) -> None:
        groups = equations.EQUATION_GROUPS
        if not 0 <= index < len(groups):
            return
        self._stack.setCurrentIndex(index)
        if index in self._populated:
            return
        self._populated.add(index)
        page = self._stack.widget(index)
        grid_host = _flow_grid(page)
        for latex, preview_text in groups[index][1]:
            btn = QToolButton()
            btn.setObjectName("Tpl")
            name = _template_name(latex, preview_text)
            btn.setToolTip(name)
            px = mathlayout.render_pixmap(
                mathbox.normalize_template(latex), 17, display=True)
            dpr = px.devicePixelRatio() or 1.0
            w, h = px.width() / dpr, px.height() / dpr
            if w > 150 or h > 84:
                s = min(150 / w, 84 / h)
                w, h = w * s, h * s
            btn.setIcon(QIcon(px))
            btn.setIconSize(QSize(int(w), int(h)))
            btn.setFixedSize(max(int(w) + 18, 52), max(int(h) + 12, 44))
            btn.clicked.connect(
                lambda _c=False, tex=latex: self._insert_template(tex))
            grid_host.addWidget(btn)
        grid_host.addStretch(1)

    def _build_symbols(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(6)
        strip = QHBoxLayout()
        strip.setSpacing(2)
        self._sym_group = QButtonGroup(self)
        self._sym_stack = QStackedWidget()
        self._sym_stack.setFixedHeight(142)
        fam = mathlayout.font_info()["family"]
        groups = [g for g in symbols.SYMBOL_GROUPS if g[0] != "KherveTeX"]
        for idx, (gname, items) in enumerate(groups):
            label, glyph = _SYMBOL_TABS[idx] if idx < len(_SYMBOL_TABS) \
                else (gname, "")
            tb = QToolButton()
            tb.setObjectName("Cat")
            tb.setCheckable(True)
            tb.setText(f"{glyph}  {label}".replace("&", "&&"))
            tb.setToolTip(gname)
            tb.setFixedHeight(28)
            self._sym_group.addButton(tb, idx)
            strip.addWidget(tb)
            host = QWidget()
            host.setObjectName("PaletteHost")
            grid = QGridLayout(host)
            grid.setSpacing(3)
            grid.setContentsMargins(0, 0, 0, 0)
            cols = 18
            for i, (latex, glyph_txt) in enumerate(items):
                if symbols.is_text_mode_symbol(latex):
                    continue
                b = QToolButton()
                b.setObjectName("Sym")
                f = QFont(fam)
                f.setPixelSize(19)
                b.setFont(f)
                ins = _symbol_insert_latex(latex)
                if len(glyph_txt) <= 2 and "{" not in latex:
                    b.setText(glyph_txt)
                else:
                    b.setIcon(QIcon(mathlayout.render_pixmap(ins, 15)))
                    b.setIconSize(QSize(28, 24))
                b.setToolTip(_nice_name(latex))
                b.setFixedSize(36, 34)
                b.clicked.connect(
                    lambda _c=False, tex=ins: self._insert_template(tex))
                grid.addWidget(b, i // cols, i % cols)
            grid.setColumnStretch(cols, 1)
            grid.setRowStretch(grid.rowCount(), 1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(host)
            self._sym_stack.addWidget(scroll)
        strip.addStretch(1)
        v.addLayout(strip)
        v.addWidget(self._sym_stack)
        self._sym_group.idClicked.connect(self._sym_stack.setCurrentIndex)
        self._sym_group.button(0).setChecked(True)
        return page

    # --------------------------------------------------------- editing
    def _insert_template(self, latex: str) -> None:
        self._math.insert_latex(mathbox.normalize_template(latex))
        self._math.setFocus()

    def _toggle_source(self, on: bool) -> None:
        self._source_panel.setVisible(on)
        self._latex_toggle.setText("Hide LaTeX" if on else "Show LaTeX")

    def _on_math_changed(self) -> None:
        self._dirty = True
        if not self._syncing:
            self._syncing = True
            self._edit.setPlainText(self._math.latex(mathbox.PLACEHOLDER))
            self._syncing = False
        self._update_slot_hint()

    def _on_source_changed(self) -> None:
        if self._syncing:
            return
        self._dirty = True
        self._syncing = True
        self._math.set_latex(self._edit.toPlainText())
        self._syncing = False
        self._update_slot_hint()

    def _update_slot_hint(self) -> None:
        n = mathbox.count_empty(self._math.editor.root)
        if n:
            plural = "s" if n != 1 else ""
            self._ph_hint.setText(
                f"{n} empty slot{plural} — press Tab to jump between them")
        else:
            self._ph_hint.setText("")

    # ------------------------------------------------------------- API
    def latex(self) -> str:
        if not self._dirty:
            return self._initial
        return self._math.latex().strip()

    def is_display(self) -> bool:
        return self._display_cb.isChecked()

    def is_numbered(self) -> bool:
        return self.is_display() and self._numbered_cb.isChecked()


def _flow_grid(page: QWidget) -> QHBoxLayout:
    """A horizontally scrolling row of template buttons inside *page*."""
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    inner = QWidget()
    inner.setObjectName("PaletteHost")
    row = QHBoxLayout(inner)
    row.setContentsMargins(2, 2, 2, 2)
    row.setSpacing(6)
    row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    scroll.setWidget(inner)
    outer.addWidget(scroll)
    return row


class ChemistryEditorDialog(_TemplatePaletteDialog):
    """Live-preview editor for mhchem chemical equations.

    The source field holds the *body* of ``\\ce{...}`` — the user never
    types the wrapper. :meth:`latex` adds it back.
    """

    _TITLE = "Chemistry editor"
    _EMPTY_HINT = "Click a template to start building your reaction"
    _EDIT_HINT = "e.g.  2H2 + O2 -> 2H2O"
    _SOURCE_LABEL = "Formula (mhchem syntax, inserted inside \\ce{…}):"
    _PLACEHOLDER = chemistry.PLACEHOLDER
    _CAT_COLS = 5
    _CAT_BTN_SIZE = (48, 34)
    _CATEGORY_ICONS = ["A→B", "→", "(s)", "±", "H₂O",
                       "A−B", "Δ", "pH", "e⁻", "α"]

    def _groups(self):
        return chemistry.CHEM_GROUPS

    def _render_template(self, latex: str):
        return chemistry.render_template_preview(latex)

    def _render_live(self, latex: str):
        return chemistry.render_live_preview(latex)

    def _extra_widgets(self, root: QVBoxLayout) -> None:
        self._display_cb = QCheckBox(
            "Display on its own line (numbered equation)")
        root.addWidget(self._display_cb)
        hint = QLabel(
            "For 2-D molecular structures (rings, bonds, wedges) use "
            "Insert ▸ Chemical structure… — it draws native chemfig.")
        hint.setStyleSheet("color: #888; font-size: 8pt;")
        hint.setWordWrap(True)
        root.addWidget(hint)

    def is_display(self) -> bool:
        return self._display_cb.isChecked()

    def latex(self) -> str:
        return chemistry.wrap_ce(self._edit.toPlainText())


class _ChemfigPreviewWorker(QThread):
    """Compiles a chemfig snippet with tectonic off the UI thread and hands
    back a rendered QImage. chemfig is TikZ — there is no mathtext shortcut,
    so every preview is a real (~1-2 s) LaTeX compile."""

    done = Signal(bool, object, str)   # ok, QImage | None, log tail

    def __init__(self, body: str, workdir: Path, parent=None):
        super().__init__(parent)
        self._body = body
        self._workdir = workdir

    def run(self) -> None:
        from .compiler import compile_tex, render_pdf_pages

        doc = chemfig.build_preview_doc(self._body)
        res = compile_tex(doc, self._workdir, basename="chemfig_preview")
        if not res.ok or res.pdf_path is None:
            self.done.emit(False, None, res.log or res.error or "")
            return
        try:
            pages = render_pdf_pages(res.pdf_path, dpi=200)
        except Exception as exc:                       # pragma: no cover
            self.done.emit(False, None, str(exc))
            return
        if not pages:
            self.done.emit(False, None, "empty PDF")
            return
        p = pages[0]
        # QImage over the raw buffer, then .copy() so it owns its pixels once
        # the RenderedPage is gone. QImage is safe to build off-thread;
        # QPixmap is not, so the UI slot does that conversion.
        img = QImage(p.rgb, p.width, p.height, p.stride,
                     QImage.Format_RGB888).copy()
        self.done.emit(True, img, res.log)


class ChemfigEditorDialog(_TemplatePaletteDialog):
    """Live-preview editor for chemfig structures and reaction schemes.

    The preview is a real tectonic compile rendered off-thread, not mathtext,
    so it is slower and debounced harder than the equation editor. The source
    the user builds is inserted verbatim as a RawLatex block.
    """

    _TITLE = "Chemical structure editor"
    _EMPTY_HINT = "Pick a structure or scheme template to start"
    _EDIT_HINT = r"e.g.  \chemfig{*6(======)}"
    _SOURCE_LABEL = "chemfig source (inserted as-is into the document):"
    _PLACEHOLDER = chemfig.PLACEHOLDER
    _CAT_COLS = 7
    _CAT_BTN_SIZE = (58, 30)
    _CATEGORY_ICONS = ["struct", "molec", "hydro", "arom", "hetero",
                       "rings", "bonds", "groups", "stereo", "bio",
                       "charge", "scheme", "poly"]

    def __init__(self, parent=None, initial_latex: str = ""):
        self._worker: _ChemfigPreviewWorker | None = None
        self._pending = False
        self._tmpdir = Path(tempfile.mkdtemp(prefix="kherveslide-chemfig-"))
        super().__init__(parent, initial_latex)
        self.setWindowTitle(self._TITLE)
        self.resize(680, 620)
        self._preview.setMinimumHeight(200)
        # tectonic is far slower than mathtext; don't compile on every keystroke
        self._preview_timer.setInterval(700)
        if initial_latex:
            self._update_preview()

    def _groups(self):
        return chemfig.CHEMFIG_GROUPS

    def _render_template(self, latex: str):
        # No per-button previews: one tectonic compile per palette button
        # would be unusable. Buttons fall back to their text label.
        return None

    def _render_live(self, latex: str):        # unused; preview is async
        return None

    def _update_preview(self) -> None:
        text = self._edit.toPlainText().strip()
        if not text:
            self._preview.setPixmap(QPixmap())
            self._preview.setText(
                f"<span style='color:#999;'>{self._EMPTY_HINT}</span>")
            return
        if self._worker is not None and self._worker.isRunning():
            self._pending = True      # coalesce; re-kick when the current one ends
            return
        self._preview.setPixmap(QPixmap())
        self._preview.setText(
            "<span style='color:#888;'>Rendering…</span>")
        self._worker = _ChemfigPreviewWorker(text, self._tmpdir, self)
        self._worker.done.connect(self._on_preview_done)
        self._worker.start()

    def _on_preview_done(self, ok: bool, img, log: str) -> None:
        self._worker = None
        if self._pending:
            self._pending = False
            self._update_preview()
            return
        if ok and img is not None and not img.isNull():
            self._preview.setText("")
            self._preview.setPixmap(QPixmap.fromImage(img))
        else:
            self._preview.setPixmap(QPixmap())
            self._preview.setText(
                "<span style='color:#c00;'>Cannot render — check the chemfig "
                "syntax.</span>")

    def latex(self) -> str:
        return self._edit.toPlainText().strip()

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(3000)
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        super().closeEvent(event)
