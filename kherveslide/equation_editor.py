"""Live-preview equation editor — vendored from KherveTeX so KherveSlide
has the same builder. Templates + a matplotlib-rendered live preview; the
chosen LaTeX is read back via EquationEditorDialog.latex()."""
from __future__ import annotations

import re

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QFrame, QGridLayout, QLabel,
    QPlainTextEdit, QScrollArea, QStackedWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from . import icons, equations

_BEGIN_RE = re.compile(r"\begin\{(\w+\*?)\}$")

class _EquationLatexEdit(QPlainTextEdit):
    """LaTeX input field that intercepts Tab/Shift+Tab to navigate
    between \\square placeholders instead of inserting tab chars."""

    _PLACEHOLDER = r"\square"

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
        self.insertPlainText(f"}}\n\\square\n\\end{{{env}}}")
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


class EquationEditorDialog(QDialog):
    """Live-preview equation editor.

    Shows a rendered preview that updates as you type, a category
    toolbar with template buttons, and a LaTeX input field with
    Tab-navigable placeholders. Clicking Insert emits the final
    LaTeX for insertion into the document.
    """

    _CATEGORY_ICONS = [
        icons.eq_fractions, icons.eq_sums, icons.eq_integrals,
        icons.eq_scripts, icons.eq_derivatives, icons.eq_greek,
        icons.eq_vectors, icons.eq_brackets, icons.eq_relations,
        icons.eq_functions, icons.eq_environments,
    ]

    def __init__(self, parent: QWidget | None = None,
                 initial_latex: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Equation editor")
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
            "<span style='color:#999;'>Click a template to start "
            "building your equation</span>")
        root.addWidget(self._preview)

        # ---- category toolbar (2 rows x 5 cols) ----
        toolbar = QFrame()
        toolbar.setFrameShape(QFrame.StyledPanel)
        tb_grid = QGridLayout(toolbar)
        tb_grid.setSpacing(2)
        tb_grid.setContentsMargins(4, 4, 4, 4)
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        groups = equations.EQUATION_GROUPS
        cols = 6
        for idx, (group_name, _items) in enumerate(groups):
            btn = QToolButton()
            btn.setCheckable(True)
            icon_fn = (self._CATEGORY_ICONS[idx]
                       if idx < len(self._CATEGORY_ICONS)
                       else icons.eq_fractions)
            btn.setIcon(icon_fn())
            btn.setIconSize(QSize(24, 24))
            btn.setToolTip(group_name)
            btn.setFixedSize(40, 34)
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
        latex_label = QLabel("LaTeX source:")
        latex_label.setStyleSheet("color: #666; font-size: 9pt;")
        root.addWidget(latex_label)
        self._edit = _EquationLatexEdit()
        self._edit.setMaximumHeight(72)
        from PySide6.QtGui import QFont as _QFont
        mf = _QFont("Consolas"); mf.setStyleHint(_QFont.Monospace)
        mf.setPointSize(10)
        self._edit.setFont(mf)
        self._edit.setPlaceholderText(
            r"e.g.  \frac{x+1}{2} + \sqrt{y}")
        root.addWidget(self._edit)

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

        # Seed with initial LaTeX if provided
        if initial_latex:
            self._edit.setPlainText(initial_latex)

    def latex(self) -> str:
        return self._edit.toPlainText().strip()

    # ---- category / template plumbing (reused from old builder) ----

    def _show_category(self, index: int) -> None:
        groups = equations.EQUATION_GROUPS
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
            pixmap = equations.render_template_preview(latex)
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
                "<span style='color:#999;'>Click a template to start "
                "building your equation</span>")
            return
        px = equations.render_live_preview(text)
        if px and not px.isNull():
            self._preview.setText("")
            self._preview.setPixmap(px)
        else:
            self._preview.setPixmap(QPixmap())
            self._preview.setText(
                f"<span style='color:#c00;'>Cannot render: check "
                f"LaTeX syntax</span>")
