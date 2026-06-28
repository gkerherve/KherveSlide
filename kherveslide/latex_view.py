"""Editable LaTeX source view with syntax highlighting and autocompletion.

When the user edits this view KherveTeX reparses the source through
khervedoc.importers.import_tex and updates the Formatted tab + PDF
preview, giving you a two-way binding between the rendered document
and its LaTeX source.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QRegularExpression, QSize, QStringListModel, QTimer, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QCompleter, QMenu, QPlainTextEdit, QVBoxLayout, QWidget,
)


# ---- colour schemes ----

_LIGHT_COLORS = {
    "command": "#1a6dd8",
    "brace": "#7a4c00",
    "math_fg": "#1a3a8c",
    "comment": "#888888",
    "section_bg": "#e8f0fe",
    "section_fg": "#1a3a8c",
    "math_bg": "#eef3ff",
    "figure_bg": "#e8f5e9",
    "figure_fg": "#2e7d32",
    "table_bg": "#fff3e0",
    "table_fg": "#e65100",
    "list_bg": "#f5f5f7",
    "list_fg": "#444444",
    "abstract_bg": "#fff5d6",
    "abstract_fg": "#7a4c00",
    "cite_bg": "#f3e5f5",
    "cite_fg": "#6a1b9a",
    "code_bg": "#eef2f7",
    "code_fg": "#1a3a8c",
}
_DARK_COLORS = {
    "command": "#6cb4ff",
    "brace": "#e5a835",
    "math_fg": "#8cc4ff",
    "comment": "#6a9955",
    "section_bg": "#1e3a5f",
    "section_fg": "#8cc4ff",
    "math_bg": "#1a2a4a",
    "figure_bg": "#1e3d1e",
    "figure_fg": "#66bb6a",
    "table_bg": "#3d2e1a",
    "table_fg": "#ffab40",
    "list_bg": "#2a2a2e",
    "list_fg": "#b0b0b0",
    "abstract_bg": "#3d3520",
    "abstract_fg": "#e5c46a",
    "cite_bg": "#2d1b3d",
    "cite_fg": "#ce93d8",
    "code_bg": "#1a2530",
    "code_fg": "#8cc4ff",
}


# ---- multi-line block state encoding ----
# QSyntaxHighlighter stores an int per block via setCurrentBlockState.
_STATE_NORMAL = 0
_STATE_MATH = 1
_STATE_FIGURE = 2
_STATE_TABLE = 3
_STATE_LIST = 4
_STATE_ABSTRACT = 5
_STATE_CITE = 6
_STATE_CODE = 7


_MATH_ENVS = (
    "equation", "equation*", "align", "align*", "alignat", "alignat*",
    "gather", "gather*", "multline", "multline*", "displaymath",
    "eqnarray", "eqnarray*", "split",
)
_LIST_ENVS = ("itemize", "enumerate", "description")
_ABSTRACT_ENVS = ("abstract",)
_CITE_ENVS = ("thebibliography", "references")
_CODE_ENVS = ("verbatim", "lstlisting", "minted", "listing")


def _env_re(envs: tuple[str, ...], begin: bool = True) -> QRegularExpression:
    tag = "begin" if begin else "end"
    pat = r"^\s*\\" + tag + r"\{(" + "|".join(
        e.replace("*", r"\*") for e in envs) + r")\}"
    return QRegularExpression(pat)


# Precompiled regexes for \begin{env} / \end{env}.
_BEGIN_MATH_RE = _env_re(_MATH_ENVS, begin=True)
_END_MATH_RE = _env_re(_MATH_ENVS, begin=False)
_BEGIN_FIGURE_RE = QRegularExpression(r"^\s*\\begin\{figure\*?\}")
_END_FIGURE_RE = QRegularExpression(r"^\s*\\end\{figure\*?\}")
_BEGIN_TABLE_RE = QRegularExpression(r"^\s*\\begin\{table\*?\}")
_END_TABLE_RE = QRegularExpression(r"^\s*\\end\{table\*?\}")
_BEGIN_LIST_RE = _env_re(_LIST_ENVS, begin=True)
_END_LIST_RE = _env_re(_LIST_ENVS, begin=False)
_BEGIN_ABSTRACT_RE = _env_re(_ABSTRACT_ENVS, begin=True)
_END_ABSTRACT_RE = _env_re(_ABSTRACT_ENVS, begin=False)
# Wiley-style \abstract[...]{...} command (not environment).
_ABSTRACT_CMD_RE = QRegularExpression(r"^\s*\\abstract\b")
_BEGIN_CITE_RE = _env_re(_CITE_ENVS, begin=True)
_END_CITE_RE = _env_re(_CITE_ENVS, begin=False)
_BEGIN_CODE_RE = _env_re(_CODE_ENVS, begin=True)
_END_CODE_RE = _env_re(_CODE_ENVS, begin=False)
_SECTION_RE = QRegularExpression(
    r"^\s*\\(section|subsection|subsubsection|paragraph|subparagraph|chapter|part)\*?"
    r"(\{|\[)")

# Map block state → (format attr name, end regex).
_ENV_FMT_MAP = {
    _STATE_MATH:     ("_math_block_fmt", _END_MATH_RE),
    _STATE_FIGURE:   ("_figure_fmt",     _END_FIGURE_RE),
    _STATE_TABLE:    ("_table_fmt",      _END_TABLE_RE),
    _STATE_LIST:     ("_list_fmt",       _END_LIST_RE),
    _STATE_ABSTRACT: ("_abstract_fmt",   _END_ABSTRACT_RE),
    _STATE_CITE:     ("_cite_fmt",       _END_CITE_RE),
    _STATE_CODE:     ("_code_fmt",       _END_CODE_RE),
}


class LatexHighlighter(QSyntaxHighlighter):
    def __init__(self, parent: QTextDocument, dark: bool = False):
        super().__init__(parent)
        self._dark = dark
        self._build_rules()

    def set_dark(self, dark: bool) -> None:
        if dark == self._dark:
            return
        self._dark = dark
        self._build_rules()
        self.rehighlight()

    def _build_rules(self) -> None:
        c = _DARK_COLORS if self._dark else _LIGHT_COLORS
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        cmd_fmt = QTextCharFormat()
        cmd_fmt.setForeground(QColor(c["command"]))
        cmd_fmt.setFontWeight(QFont.Bold)
        self._rules.append((QRegularExpression(r"\\[A-Za-z@]+\*?"), cmd_fmt))

        brace_fmt = QTextCharFormat()
        brace_fmt.setForeground(QColor(c["brace"]))
        self._rules.append((QRegularExpression(r"[\{\}]"), brace_fmt))

        math_fmt = QTextCharFormat()
        math_fmt.setForeground(QColor(c["math_fg"]))
        math_fmt.setBackground(QColor(c["math_bg"]))
        math_fmt.setFontItalic(True)
        self._rules.append((QRegularExpression(r"\$[^$]*\$"), math_fmt))

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor(c["comment"]))
        comment_fmt.setFontItalic(True)
        self._rules.append((QRegularExpression(r"%[^\n]*"), comment_fmt))

        # Block-level formats.
        self._section_fmt = QTextCharFormat()
        self._section_fmt.setBackground(QColor(c["section_bg"]))
        self._section_fmt.setForeground(QColor(c["section_fg"]))
        self._section_fmt.setFontWeight(QFont.Bold)

        self._math_block_fmt = QTextCharFormat()
        self._math_block_fmt.setBackground(QColor(c["math_bg"]))
        self._math_block_fmt.setForeground(QColor(c["math_fg"]))

        self._figure_fmt = QTextCharFormat()
        self._figure_fmt.setBackground(QColor(c["figure_bg"]))
        self._figure_fmt.setForeground(QColor(c["figure_fg"]))

        self._table_fmt = QTextCharFormat()
        self._table_fmt.setBackground(QColor(c["table_bg"]))
        self._table_fmt.setForeground(QColor(c["table_fg"]))

        self._list_fmt = QTextCharFormat()
        self._list_fmt.setBackground(QColor(c["list_bg"]))
        self._list_fmt.setForeground(QColor(c["list_fg"]))

        self._abstract_fmt = QTextCharFormat()
        self._abstract_fmt.setBackground(QColor(c["abstract_bg"]))
        self._abstract_fmt.setForeground(QColor(c["abstract_fg"]))

        self._cite_fmt = QTextCharFormat()
        self._cite_fmt.setBackground(QColor(c["cite_bg"]))
        self._cite_fmt.setForeground(QColor(c["cite_fg"]))

        self._code_fmt = QTextCharFormat()
        self._code_fmt.setBackground(QColor(c["code_bg"]))
        self._code_fmt.setForeground(QColor(c["code_fg"]))

    def highlightBlock(self, text: str) -> None:
        prev = self.previousBlockState()
        if prev < 0:
            prev = _STATE_NORMAL
        state = prev

        # Check for environment opens/closes on this line.
        if state == _STATE_NORMAL:
            if _BEGIN_MATH_RE.match(text).hasMatch():
                state = _STATE_MATH
            elif _BEGIN_FIGURE_RE.match(text).hasMatch():
                state = _STATE_FIGURE
            elif _BEGIN_TABLE_RE.match(text).hasMatch():
                state = _STATE_TABLE
            elif _BEGIN_LIST_RE.match(text).hasMatch():
                state = _STATE_LIST
            elif _BEGIN_ABSTRACT_RE.match(text).hasMatch():
                state = _STATE_ABSTRACT
            elif _BEGIN_CITE_RE.match(text).hasMatch():
                state = _STATE_CITE
            elif _BEGIN_CODE_RE.match(text).hasMatch():
                state = _STATE_CODE

        block_fmt = None
        is_section = False
        if state in _ENV_FMT_MAP:
            attr, end_re = _ENV_FMT_MAP[state]
            block_fmt = getattr(self, attr)
            if end_re.match(text).hasMatch():
                state = _STATE_NORMAL
        elif _ABSTRACT_CMD_RE.match(text).hasMatch():
            block_fmt = self._abstract_fmt
        elif _SECTION_RE.match(text).hasMatch():
            block_fmt = self._section_fmt
            is_section = True

        self.setCurrentBlockState(state)

        # Apply token-level highlights first.
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

        # Overlay block background on every character without touching the
        # foreground colour set by the token rules above.
        if block_fmt is not None:
            bg = block_fmt.background().color()
            for i in range(len(text)):
                f = self.format(i)
                f.setBackground(bg)
                # For section lines, also apply bold + section foreground
                # to characters that weren't coloured by a token rule
                # (i.e. the plain-text portion of the heading).
                if is_section and not f.fontWeight() > QFont.Normal:
                    f.setForeground(block_fmt.foreground())
                    f.setFontWeight(QFont.Bold)
                self.setFormat(i, 1, f)


# ---- LaTeX command dictionary for autocomplete ----

_LATEX_COMMANDS = [
    r"\section{}", r"\subsection{}", r"\subsubsection{}",
    r"\paragraph{}", r"\subparagraph{}", r"\chapter{}",
    r"\begin{}", r"\end{}",
    r"\begin{equation}", r"\end{equation}",
    r"\begin{align}", r"\end{align}",
    r"\begin{figure}", r"\end{figure}",
    r"\begin{table}", r"\end{table}",
    r"\begin{itemize}", r"\end{itemize}",
    r"\begin{enumerate}", r"\end{enumerate}",
    r"\begin{tabular}{}", r"\end{tabular}",
    r"\begin{center}", r"\end{center}",
    r"\begin{flushleft}", r"\end{flushleft}",
    r"\begin{flushright}", r"\end{flushright}",
    r"\begin{abstract}", r"\end{abstract}",
    r"\begin{multicols}{}", r"\end{multicols}",
    r"\begin{lstlisting}", r"\end{lstlisting}",
    r"\begin{verbatim}", r"\end{verbatim}",
    r"\begin{thebibliography}{}", r"\end{thebibliography}",
    r"\textbf{}", r"\textit{}", r"\texttt{}", r"\underline{}",
    r"\emph{}", r"\textsc{}", r"\textrm{}", r"\textsf{}",
    r"\includegraphics{}", r"\includegraphics[width=]{}",
    r"\caption{}", r"\label{}", r"\ref{}", r"\eqref{}", r"\pageref{}",
    r"\cite{}", r"\citep{}", r"\citet{}",
    r"\footnote{}", r"\href{}{}", r"\url{}",
    r"\frac{}{}", r"\sqrt{}", r"\sum", r"\prod", r"\int",
    r"\alpha", r"\beta", r"\gamma", r"\delta", r"\epsilon",
    r"\theta", r"\lambda", r"\mu", r"\sigma", r"\omega",
    r"\pi", r"\phi", r"\psi", r"\chi", r"\rho", r"\tau",
    r"\partial", r"\nabla", r"\infty", r"\forall", r"\exists",
    r"\mathbb{}", r"\mathcal{}", r"\mathfrak{}",
    r"\left", r"\right", r"\bigl", r"\bigr",
    r"\hspace{}", r"\vspace{}", r"\quad", r"\qquad",
    r"\newpage", r"\clearpage", r"\newline",
    r"\title{}", r"\author{}", r"\date{}", r"\maketitle",
    r"\tableofcontents", r"\listoffigures", r"\listoftables",
    r"\usepackage{}", r"\documentclass{}",
    r"\newcommand{}{}", r"\renewcommand{}{}",
    r"\providecommand{}{}",
    r"\setlength{}{}", r"\addtolength{}{}",
    r"\hrulefill", r"\dotfill",
    r"\centering", r"\raggedright", r"\raggedleft",
    r"\item", r"\bibitem{}",
    r"\Kstroke",
]


class _LineNumberArea(QWidget):
    """Gutter widget that draws line numbers alongside a QPlainTextEdit."""

    def __init__(self, editor: "_NumberedPlainTextEdit"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:
        self._editor.line_number_area_paint(event)


class _NumberedPlainTextEdit(QPlainTextEdit):
    """QPlainTextEdit with a line-number gutter on the left."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._line_area = _LineNumberArea(self)
        self._dark = False
        self._theme: dict[str, str] | None = None
        self.blockCountChanged.connect(lambda _: self._update_line_area_width())
        self.updateRequest.connect(self._update_line_area)
        self._update_line_area_width()

    def set_dark(self, dark: bool, theme: dict[str, str] | None = None) -> None:
        self._dark = dark
        self._theme = theme
        self._line_area.update()

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 8 + self.fontMetrics().horizontalAdvance("9") * (digits + 1)

    def _update_line_area_width(self) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_area(self, rect, dy) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(),
                                   self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(
            QRect(cr.left(), cr.top(),
                  self.line_number_area_width(), cr.height()))

    def line_number_area_paint(self, event) -> None:
        painter = QPainter(self._line_area)
        t = self._theme
        if t:
            painter.fillRect(event.rect(), QColor(t["surface"]))
            num_color = QColor(t["text_muted"])
        elif self._dark:
            painter.fillRect(event.rect(), QColor("#252526"))
            num_color = QColor("#858585")
        else:
            painter.fillRect(event.rect(), QColor("#f0f0f0"))
            num_color = QColor("#999999")
        painter.setPen(num_color)
        block = self.firstVisibleBlock()
        block_num = block.blockNumber()
        top = int(self.blockBoundingGeometry(block)
                  .translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(0, top,
                                 self._line_area.width() - 4,
                                 self.fontMetrics().height(),
                                 Qt.AlignRight, str(block_num + 1))
            block = block.next()
            if not block.isValid():
                break
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_num += 1
        painter.end()


class LatexView(QWidget):
    """Two-way editable LaTeX source view with autocomplete."""

    latexEdited = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._edit = _NumberedPlainTextEdit(self)
        f = QFont("Consolas"); f.setStyleHint(QFont.Monospace); f.setPointSize(11)
        self._edit.setFont(f)
        self._highlighter = LatexHighlighter(self._edit.document())

        # Autocomplete for LaTeX commands.
        self._completer = QCompleter(self)
        self._completer.setWidget(self._edit)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitive)
        self._completer.setModel(QStringListModel(_LATEX_COMMANDS, self._completer))
        self._completer.activated.connect(self._insert_completion)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._edit)

        self._suppress_signal = False
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(1500)
        self._debounce.timeout.connect(self._emit_edited)
        self._edit.textChanged.connect(self._on_text_changed)

        self._extra_context_actions: list[tuple[str, object]] = []
        self._edit.setContextMenuPolicy(Qt.CustomContextMenu)
        self._edit.customContextMenuRequested.connect(self._show_context_menu)

    # ----- public API -----

    def set_source(self, src: str) -> None:
        """Replace the visible source without firing latexEdited."""
        if self._edit.toPlainText() == src:
            return
        cursor_pos = self._edit.textCursor().position()
        scroll = self._edit.verticalScrollBar().value()
        self._suppress_signal = True
        try:
            self._edit.setPlainText(src)
        finally:
            self._suppress_signal = False
        self._edit.verticalScrollBar().setValue(scroll)
        cursor = self._edit.textCursor()
        cursor.setPosition(min(cursor_pos, len(src)))
        self._edit.setTextCursor(cursor)

    def source(self) -> str:
        return self._edit.toPlainText()

    def cursor_snippet(self, max_chars: int = 40) -> str:
        """Return a short plain-text snippet around the cursor for
        cross-tab navigation. Strips LaTeX commands to get usable text."""
        cursor = self._edit.textCursor()
        block = cursor.block()
        text = block.text().strip()
        # Strip common LaTeX noise to get searchable plain text
        import re
        text = re.sub(r"\\[a-zA-Z]+\*?\{?", " ", text)
        text = re.sub(r"[{}\\&%$]", "", text)
        text = " ".join(text.split()).strip()
        if len(text) > max_chars:
            pos = cursor.positionInBlock()
            start = max(0, pos - max_chars // 2)
            text = text[start:start + max_chars]
        return text.strip()

    def scroll_to_snippet(self, snippet: str) -> bool:
        """Find *snippet* in the LaTeX source and scroll to it."""
        if not snippet:
            return False
        import re
        src = self._edit.toPlainText()
        idx = src.find(snippet)
        if idx < 0:
            words = snippet.split()[:3]
            if words:
                pattern = r"[\s\\{}]*".join(re.escape(w) for w in words)
                m = re.search(pattern, src)
                if m:
                    idx = m.start()
        if idx < 0:
            return False
        cursor = self._edit.textCursor()
        cursor.setPosition(idx)
        self._edit.setTextCursor(cursor)
        self._edit.centerCursor()
        return True

    def _show_context_menu(self, pos) -> None:
        menu = self._edit.createStandardContextMenu()
        if self._extra_context_actions:
            menu.addSeparator()
            for label, callback in self._extra_context_actions:
                menu.addAction(label, callback)
        menu.exec(self._edit.viewport().mapToGlobal(pos))

    def set_dark(self, dark: bool, theme: dict[str, str] | None = None) -> None:
        self._highlighter.set_dark(dark)
        self._edit.set_dark(dark, theme)
        if theme:
            self._edit.setStyleSheet(
                f"QPlainTextEdit {{ background: {theme['base']};"
                f" color: {theme['text']}; }}")
        elif dark:
            self._edit.setStyleSheet(
                "QPlainTextEdit { background: #1e1e1e; color: #d4d4d4; }")
        else:
            self._edit.setStyleSheet(
                "QPlainTextEdit { background: #ffffff; color: #1c1c1c; }")

    # ----- autocomplete -----

    def _text_under_cursor(self) -> str:
        """Return the current word being typed, including the leading backslash."""
        cursor = self._edit.textCursor()
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        line_to_cursor = cursor.selectedText()
        # Find the last backslash and return everything from it.
        idx = line_to_cursor.rfind("\\")
        if idx < 0:
            return ""
        return line_to_cursor[idx:]

    def _insert_completion(self, completion: str) -> None:
        prefix = self._completer.completionPrefix()
        cursor = self._edit.textCursor()
        # Remove the prefix the user already typed, then insert the full completion.
        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(prefix))
        cursor.insertText(completion)
        self._edit.setTextCursor(cursor)

    # ----- signal plumbing -----

    def _on_text_changed(self) -> None:
        if self._suppress_signal:
            return
        self._debounce.start()

        # Drive the completer from the current prefix.
        prefix = self._text_under_cursor()
        if len(prefix) >= 2:  # at least \ + one letter
            self._completer.setCompletionPrefix(prefix)
            if self._completer.completionCount() > 0:
                popup = self._completer.popup()
                popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
                cr = self._edit.cursorRect()
                cr.setWidth(280)
                self._completer.complete(cr)
            else:
                self._completer.popup().hide()
        else:
            self._completer.popup().hide()

    def _emit_edited(self) -> None:
        self.latexEdited.emit(self._edit.toPlainText())
