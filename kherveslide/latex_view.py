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
    QCompleter, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)


# ---- colour schemes ----

_LIGHT_COLORS = {
    "command": "#1a6dd8",
    "keyword": "#af00db",
    "env": "#267f99",
    "option": "#b35900",
    "number": "#098658",
    "special": "#a31515",
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
    "keyword": "#c586c0",
    "env": "#4ec9b0",
    "option": "#ce9178",
    "number": "#b5cea8",
    "special": "#d16969",
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


_MONOKAI_COLORS = {
    "command": "#66d9ef", "keyword": "#f92672", "env": "#a6e22e",
    "option": "#fd971f", "number": "#ae81ff", "special": "#f92672",
    "brace": "#f8f8f2", "math_fg": "#e6db74", "comment": "#75715e",
    "section_bg": "#3e3d32", "section_fg": "#a6e22e",
    "math_bg": "#2d2e26", "figure_bg": "#2d3326", "figure_fg": "#a6e22e",
    "table_bg": "#332b26", "table_fg": "#fd971f",
    "list_bg": "#2e2e2a", "list_fg": "#cfcfc2",
    "abstract_bg": "#332f26", "abstract_fg": "#e6db74",
    "cite_bg": "#2f2833", "cite_fg": "#ae81ff",
    "code_bg": "#2d2e26", "code_fg": "#66d9ef",
}
_SOLARIZED_LIGHT_COLORS = {
    "command": "#268bd2", "keyword": "#d33682", "env": "#2aa198",
    "option": "#cb4b16", "number": "#859900", "special": "#dc322f",
    "brace": "#b58900", "math_fg": "#6c71c4", "comment": "#93a1a1",
    "section_bg": "#eee8d5", "section_fg": "#268bd2",
    "math_bg": "#eee8d5", "figure_bg": "#eef3e0", "figure_fg": "#859900",
    "table_bg": "#f6ecd8", "table_fg": "#cb4b16",
    "list_bg": "#f1ece0", "list_fg": "#657b83",
    "abstract_bg": "#f3eed8", "abstract_fg": "#b58900",
    "cite_bg": "#f0e8ec", "cite_fg": "#d33682",
    "code_bg": "#eee8d5", "code_fg": "#268bd2",
}
_SOLARIZED_DARK_COLORS = {
    "command": "#268bd2", "keyword": "#d33682", "env": "#2aa198",
    "option": "#cb4b16", "number": "#859900", "special": "#dc322f",
    "brace": "#b58900", "math_fg": "#6c71c4", "comment": "#586e75",
    "section_bg": "#073642", "section_fg": "#268bd2",
    "math_bg": "#073642", "figure_bg": "#0a3a2a", "figure_fg": "#859900",
    "table_bg": "#0a3340", "table_fg": "#cb4b16",
    "list_bg": "#073642", "list_fg": "#93a1a1",
    "abstract_bg": "#0a3540", "abstract_fg": "#b58900",
    "cite_bg": "#0a2f40", "cite_fg": "#d33682",
    "code_bg": "#073642", "code_fg": "#268bd2",
}

# Named editor colour schemes for the LaTeX source view. Each bundles the
# syntax palette with the editor background/foreground and the line-number
# gutter colours. "Match app theme" (None) follows the app Appearance.
EDITOR_SCHEMES: dict[str, dict] = {
    "Default (light)": {"colors": _LIGHT_COLORS, "bg": "#ffffff",
                        "fg": "#1c1c1c", "gutter_bg": "#f0f0f0",
                        "gutter_fg": "#999999"},
    "Dark": {"colors": _DARK_COLORS, "bg": "#1e1e1e", "fg": "#d4d4d4",
             "gutter_bg": "#252526", "gutter_fg": "#858585"},
    "Monokai": {"colors": _MONOKAI_COLORS, "bg": "#272822", "fg": "#f8f8f2",
                "gutter_bg": "#2d2e28", "gutter_fg": "#75715e"},
    "Solarized Light": {"colors": _SOLARIZED_LIGHT_COLORS, "bg": "#fdf6e3",
                        "fg": "#657b83", "gutter_bg": "#eee8d5",
                        "gutter_fg": "#93a1a1"},
    "Solarized Dark": {"colors": _SOLARIZED_DARK_COLORS, "bg": "#002b36",
                       "fg": "#93a1a1", "gutter_bg": "#073642",
                       "gutter_fg": "#586e75"},
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
        self._colors = _DARK_COLORS if dark else _LIGHT_COLORS
        self._build_rules()

    def set_dark(self, dark: bool) -> None:
        if dark == self._dark and self._colors in (_LIGHT_COLORS, _DARK_COLORS):
            return
        self._dark = dark
        self._colors = _DARK_COLORS if dark else _LIGHT_COLORS
        self._build_rules()
        self.rehighlight()

    def set_colors(self, colors: dict[str, str]) -> None:
        """Drive the syntax palette from an explicit editor colour scheme."""
        self._colors = colors
        self._build_rules()
        self.rehighlight()

    def _build_rules(self) -> None:
        c = self._colors
        # Each rule is (regex, format, capture-group). Group 0 = whole match.
        # Later rules win on overlapping characters, so order is significant.
        self._rules: list[tuple[QRegularExpression, QTextCharFormat, int]] = []

        def rule(pattern, fmt, group=0):
            self._rules.append((QRegularExpression(pattern), fmt, group))

        def fmt(color=None, *, bold=False, italic=False):
            f = QTextCharFormat()
            if color:
                f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Bold)
            if italic:
                f.setFontItalic(True)
            return f

        # 1. Any control sequence (\command or \@macro).
        rule(r"\\[A-Za-z@]+\*?", fmt(c["command"], bold=True))
        # 2. Structural keywords get their own colour, on top of (1).
        rule(r"\\(?:begin|end|documentclass|usepackage|usetheme|usecolortheme"
             r"|RequirePackage|newcommand|renewcommand|providecommand|def"
             r"|input|include|setbeamertemplate|setbeamercolor|setbeamerfont"
             r"|usefonttheme|useinnertheme|useoutertheme)\b\*?",
             fmt(c["keyword"], bold=True))
        # 3. The environment name inside \begin{...}/\end{...} (group 1).
        rule(r"\\(?:begin|end)\*?\{([A-Za-z0-9@]+\*?)\}", fmt(c["env"]), 1)
        # 4. Optional arguments [key=value, ...].
        rule(r"\[[^\]\n]*\]", fmt(c["option"]))
        # 5. Braces.
        rule(r"[{}]", fmt(c["brace"]))
        # 6. Numbers and dimensions.
        rule(r"\b\d+(?:\.\d+)?\b", fmt(c["number"]))
        # 7. Alignment & row-break separators.
        rule(r"\\\\|&|~", fmt(c["special"], bold=True))
        # 8. Inline maths (overrides the above within $...$).
        math_fmt = fmt(c["math_fg"], italic=True)
        math_fmt.setBackground(QColor(c["math_bg"]))
        rule(r"\$[^$]*\$", math_fmt)
        # 9. Comments win over everything to end of line.
        rule(r"%[^\n]*", fmt(c["comment"], italic=True))

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
        for pattern, fmt, group in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                start = m.capturedStart(group)
                length = m.capturedLength(group)
                if start >= 0 and length > 0:
                    self.setFormat(start, length, fmt)

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
        self._gutter_override: tuple[str, str] | None = None
        self.blockCountChanged.connect(lambda _: self._update_line_area_width())
        self.updateRequest.connect(self._update_line_area)
        self._update_line_area_width()

    def set_dark(self, dark: bool, theme: dict[str, str] | None = None) -> None:
        self._dark = dark
        self._theme = theme
        self._line_area.update()

    def set_gutter(self, override: tuple[str, str] | None) -> None:
        """Force explicit (bg, fg) gutter colours, or None to follow theme."""
        self._gutter_override = override
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
        if self._gutter_override:
            bg, fg = self._gutter_override
            painter.fillRect(event.rect(), QColor(bg))
            num_color = QColor(fg)
        elif t:
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
    regenerateRequested = Signal()      # user clicked "Regenerate from slides"

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

        # Banner shown when the user has manually edited the source: it warns
        # that the slides won't overwrite the edits and offers to re-sync.
        self._banner = QWidget()
        _bl = QHBoxLayout(self._banner)
        _bl.setContentsMargins(8, 4, 8, 4)
        _lbl = QLabel("Manual LaTeX edits — the slides won't overwrite them.")
        _btn = QPushButton("Regenerate from slides")
        _btn.setToolTip("Discard the manual LaTeX edits and rebuild the source "
                        "from the Visual slides")
        _btn.clicked.connect(lambda: self.regenerateRequested.emit())
        _bl.addWidget(_lbl)
        _bl.addStretch(1)
        _bl.addWidget(_btn)
        self._banner.setStyleSheet(
            "QWidget { background:#fff3cd; } QLabel { color:#664d03; }")
        self._banner.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._banner)
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

        # Editor colour scheme: None = follow the app Appearance theme;
        # otherwise an EDITOR_SCHEMES key that overrides it.
        self._scheme: str | None = None
        self._last_dark = False
        self._last_theme: dict[str, str] | None = None

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

    def set_overridden(self, on: bool) -> None:
        """Show/hide the 'manual LaTeX edits' banner."""
        self._banner.setVisible(on)

    def find(self, text: str, backwards: bool = False) -> bool:
        """Find *text* from the cursor, wrapping around. Returns True if a
        match was selected."""
        if not text:
            return False
        flags = (QTextDocument.FindBackward if backwards
                 else QTextDocument.FindFlag(0))
        if self._edit.find(text, flags):
            return True
        # Wrap around from the opposite end.
        cur = self._edit.textCursor()
        cur.movePosition(QTextCursor.End if backwards else QTextCursor.Start)
        self._edit.setTextCursor(cur)
        return self._edit.find(text, flags)

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
        self._last_dark = dark
        self._last_theme = theme
        if self._scheme is not None:
            return  # an explicit editor scheme overrides the app theme
        self._highlighter.set_dark(dark)
        self._edit.set_dark(dark, theme)
        self._edit.set_gutter(None)
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

    def editor_scheme(self) -> str | None:
        return self._scheme

    def set_editor_scheme(self, name: str | None) -> None:
        """Apply a named EDITOR_SCHEMES palette, or None to follow the app
        Appearance theme."""
        if name is not None and name not in EDITOR_SCHEMES:
            name = None
        self._scheme = name
        if name is None:
            self.set_dark(self._last_dark, self._last_theme)
            return
        s = EDITOR_SCHEMES[name]
        self._highlighter.set_colors(s["colors"])
        self._edit.setStyleSheet(
            f"QPlainTextEdit {{ background: {s['bg']}; color: {s['fg']}; }}")
        self._edit.set_gutter((s["gutter_bg"], s["gutter_fg"]))

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
