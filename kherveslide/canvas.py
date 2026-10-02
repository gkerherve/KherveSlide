"""The slide canvas — graphics scene plus the movable / resizable boxes.

Geometry is stored in the model as ``0..1`` fractions of the slide; here
those map onto a fixed-height scene so the boxes can be dragged and
resized directly, and the same drawing code renders the little
thumbnails shown in the slide navigator.
"""
from __future__ import annotations

import html as _html
import math
import re

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QLinearGradient, QPainter,
    QPainterPath, QPen,
    QPixmap, QPolygonF, QTextBlockFormat, QTextCharFormat, QTextCursor,
    QTextDocument, QTextListFormat, QTextOption,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsView,
)

from .model import (
    Slide, SlideText, SlidePicture, SlideTable, SlideLine, SlideShape,
    SlideVideo, TABLE_HEADER_BG, TABLE_HEADER_FG, TABLE_RULE, line_path,
)
from . import shapes as _shapes


def effective_shape(obj) -> str:
    """A plain rectangle with rounded corners is drawn as a rounded rect."""
    if obj.shape == "rect" and getattr(obj, "corner", "sharp") == "rounded":
        return "rounded_rect"
    return obj.shape


def _inline_html(s: str) -> str:
    """Best-effort LaTeX inline → HTML for the canvas preview."""
    s = _html.escape(s)
    s = re.sub(r"\\textbf\{([^}]*)\}", r"<b>\1</b>", s)
    s = re.sub(r"\\textit\{([^}]*)\}", r"<i>\1</i>", s)
    s = re.sub(r"\\emph\{([^}]*)\}", r"<i>\1</i>", s)
    s = re.sub(r"\\textsuperscript\{([^}]*)\}", r"<sup>\1</sup>", s)
    s = re.sub(r"\\textsubscript\{([^}]*)\}", r"<sub>\1</sub>", s)
    # Keep inline-maths delimiters ($…$) visible: stripping them meant that
    # editing a box (and committing) silently dropped the $ and turned maths
    # into plain text. Showing the source lets it round-trip intact.
    # Escapes (\\% \\& \\_ …) stay as source here: the in-place editor
    # shows this, and whatever it shows is turned back into LaTeX on
    # commit — a bare % would comment out the rest of the line. Painting
    # resolves them (_pretty_inline_html).
    s = s.replace("\\\\", "<br>")
    return s


# ---- painting-only rendering of inline LaTeX (see latex_to_html) ----

_MATH_EXTRA = {
    "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔",
    "rightarrow": "→", "to": "→", "leftarrow": "←", "mapsto": "↦",
    "times": "×", "cdot": "·", "approx": "≈", "sim": "∼", "infty": "∞",
    "pm": "±", "mp": "∓", "le": "≤", "ge": "≥", "leq": "≤", "geq": "≥",
    "neq": "≠", "ne": "≠", "equiv": "≡", "propto": "∝", "partial": "∂",
    "nabla": "∇", "hbar": "ℏ", "int": "∫", "iint": "∬", "oint": "∮",
    "sum": "∑", "prod": "∏", "in": "∈", "notin": "∉", "subset": "⊂",
    "cup": "∪", "cap": "∩", "forall": "∀", "exists": "∃", "degree": "°",
    "ldots": "…", "dots": "…", "cdots": "⋯", "circ": "∘", "ell": "ℓ",
    "langle": "⟨", "rangle": "⟩", "|": "‖", "prime": "′",
}
_MATH_FUNCS = {"sin", "cos", "tan", "ln", "log", "exp", "max", "min",
               "lim", "det", "sinh", "cosh", "tanh", "arg", "dim"}
_BLACKBOARD = {"R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ", "P": "ℙ"}
_SPACES = {",": "\u2009", ";": " ", ":": " ", " ": " ", "!": "",
           "quad": "\u2003", "qquad": "\u2003\u2003"}
_NAMED = {"red": "#FF0000", "green": "#00A000", "blue": "#0000FF",
          "orange": "#FF8000", "black": "#000000", "white": "#FFFFFF",
          "gray": "#808080", "purple": "#BF0040", "teal": "#008080",
          "cyan": "#00FFFF", "magenta": "#FF00FF", "brown": "#BF8040",
          "violet": "#800080", "olive": "#808000", "darkgray": "#404040"}
_symbol_glyphs: dict | None = None


def _math_glyphs() -> dict:
    global _symbol_glyphs
    if _symbol_glyphs is None:
        from . import symbols
        _symbol_glyphs = {latex[1:]: glyph
                          for latex, glyph in symbols.all_symbols()
                          if latex.startswith("\\") and len(glyph) <= 2}
        _symbol_glyphs.update(_MATH_EXTRA)
    return _symbol_glyphs


def _group(src: str, j: int) -> tuple[str, int]:
    """The {…} group (or single token) starting at *j*."""
    while j < len(src) and src[j] == " ":
        j += 1
    if j >= len(src):
        return "", j
    if src[j] == "{":
        depth = 0
        for k in range(j, len(src)):
            depth += {"{": 1, "}": -1}.get(src[k], 0)
            if depth == 0:
                return src[j + 1:k], k + 1
        return src[j + 1:], len(src)
    if src[j] == "\\":
        m = re.match(r"\\([A-Za-z]+|.)", src[j:])
        return m.group(0), j + len(m.group(0))
    return src[j], j + 1


_BINARY = {"=": " = ", "+": " + ", "-": " − ", "<": " &lt; ",
           ">": " &gt; "}
# Commands TeX spaces like binary operators / relations.
_SPACED_CMDS = {"times", "cdot", "approx", "pm", "mp", "le", "ge", "leq",
                "geq", "neq", "ne", "equiv", "sim", "propto", "to",
                "rightarrow", "Rightarrow", "leftarrow", "Leftarrow",
                "Leftrightarrow", "in", "notin", "subset"}


def math_to_html(src: str, top: bool = True) -> str:
    """Inline maths as readable HTML: italic variables, upright numbers
    and functions, Unicode symbols, sub/superscripts, a/b fractions, √.
    Relations and +/− get spaces at the top level, as TeX sets them."""
    glyphs = _math_glyphs()
    out: list[str] = []
    i = 0
    while i < len(src):
        c = src[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", src[i:])
            name = m.group(1)
            i += len(m.group(0))
            if name in ("frac", "dfrac", "tfrac"):
                a, i = _group(src, i)
                b, i = _group(src, i)
                # Brackets where a / b would be ambiguous: (a − b)/(c + d).
                fa, fb = math_to_html(a, False), math_to_html(b, False)
                fa = f"({fa})" if re.search(r"[-+]", a.strip()[1:]) else fa
                fb = f"({fb})" if re.search(r"[-+]", b.strip()[1:]) else fb
                out.append(f"{fa}/{fb}")
            elif name == "sqrt":
                a, i = _group(src, i)
                inner = math_to_html(a, False)
                out.append("√" + (inner if len(a) <= 1 else f"({inner})"))
            elif name == "mathbb":
                a, i = _group(src, i)
                out.append("".join(_BLACKBOARD.get(ch, ch) for ch in a))
            elif name in ("mathrm", "text", "textrm", "operatorname",
                          "mathsf", "textup"):
                a, i = _group(src, i)
                out.append(_html.escape(a))
            elif name in ("mathbf", "boldsymbol", "textbf"):
                a, i = _group(src, i)
                out.append(f"<b>{math_to_html(a, False)}</b>")
            elif name in ("left", "right", "displaystyle", "big", "Big",
                          "bigl", "bigr", "limits", "nolimits"):
                pass
            elif name in _MATH_FUNCS:
                nxt = src[i:].lstrip()[:1]
                out.append(name if nxt in ("(", "", "^", "_")
                           else name + "\u2009")
            elif name in _SPACES:
                out.append(_SPACES[name])
            elif name in glyphs:
                g = _html.escape(glyphs[name])
                out.append(f" {g} " if top and name in _SPACED_CMDS and out
                           else g)
            elif len(name) == 1:                 # \{ \% \& …
                out.append(_html.escape(name))
            else:
                out.append(_html.escape(name))
        elif c in "^_":
            a, i = _group(src, i + 1)
            tag = "sup" if c == "^" else "sub"
            out.append(f"<{tag}>{math_to_html(a, False)}</{tag}>")
        elif c.isalpha():
            out.append(f"<i>{c}</i>")
            i += 1
        elif c in "{} ":
            i += 1
        elif c == "'":
            out.append("′")
            i += 1
        elif top and c in _BINARY and out:      # not a leading sign
            out.append(_BINARY[c])
            i += 1
        elif c == "-":
            out.append("−")
            i += 1
        else:
            out.append(_html.escape(c))
            i += 1
    return "".join(out)


def _textcolor(s: str) -> str:
    """\\textcolor{name}{x} / \\textcolor[HTML]{RRGGBB}{x} → coloured span
    (on already-converted text)."""
    pat = re.compile(r"\\textcolor(?:\[HTML\])?\{([^}]*)\}\{")
    while True:
        m = pat.search(s)
        if not m:
            return s
        body, end = _group(s, m.end() - 1)
        spec = m.group(1)
        if re.fullmatch(r"[0-9A-Fa-f]{6}", spec):
            colour = "#" + spec
        else:
            colour = _NAMED.get(spec.split("!")[0], "#000000")
        s = (s[:m.start()] + f'<span style="color:{colour}">{body}</span>'
             + s[end:])


def _pretty_inline_html(s: str) -> str:
    """Text as it prints: maths rendered, escapes and dashes resolved."""
    parts = re.split(r"(?<!\\)\$(.+?)(?<!\\)\$|\\\((.+?)\\\)", s)
    out: list[str] = []
    for k, part in enumerate(parts):
        if part is None:
            continue
        if k % 3 == 0:                            # plain text
            t = _inline_html(part)
            t = t.replace("\\textbar{}", "|").replace("\\textbar", "|")
            t = t.replace("\\&amp;", "&amp;").replace("\\%", "%")
            t = t.replace("\\_", "_").replace("\\#", "#")
            t = t.replace("\\{", "{").replace("\\}", "}")
            t = t.replace("\\,", "\u2009").replace("\\;", " ")
            t = t.replace("\\ ", " ").replace("~", "\u00a0")
            t = t.replace("\\$", "$").replace("---", "—").replace("--", "–")
            t = t.replace("\\today", _today())
            out.append(t)
        else:                                     # $…$ or \(…\)
            out.append(math_to_html(part))
    return _textcolor("".join(out))


def _today() -> str:
    from datetime import date
    d = date.today()
    return f"{d:%B} {d.day}, {d.year}"


def _math_only(text: str) -> str | None:
    """If *text* is a single math expression ($…$, \\[…\\] or \\(…\\)),
    return the inner LaTeX; otherwise None."""
    t = (text or "").strip()
    if len(t) >= 2 and t.startswith("$") and t.endswith("$") \
            and "$" not in t[1:-1]:
        return t[1:-1].strip()
    if t.startswith("\\[") and t.endswith("\\]"):
        return t[2:-2].strip()
    if t.startswith("\\(") and t.endswith("\\)"):
        return t[2:-2].strip()
    return None


def rewrap_math(original: str, latex: str) -> str:
    """Put *latex* back inside whichever delimiters *original* used, so
    re-editing a display equation doesn't silently demote it to inline."""
    t = (original or "").strip()
    if t.startswith("\\["):
        return f"\\[{latex}\\]"
    if t.startswith("\\("):
        return f"\\({latex}\\)"
    return f"${latex}$"


def latex_to_html(text: str, pretty: bool = False) -> str:
    """Render a text box's LaTeX-ish content as HTML so itemize/enumerate
    look like real bullet / numbered lists on the canvas — including nested
    sub-levels (an itemize/enumerate opened inside an \\item).

    *pretty* is for painting only: inline maths, escapes, dashes and
    colours are shown as they print. The in-place editor keeps it False,
    because what it shows is converted back to LaTeX on commit."""
    inline = _pretty_inline_html if pretty else _inline_html
    out: list[str] = []
    tags: list[str] = []        # open list tags, outermost first
    li_open: list[bool] = []    # is there an unclosed <li> at each level

    def close_li():
        if li_open and li_open[-1]:
            out.append("</li>")
            li_open[-1] = False

    def close_all():
        while tags:
            close_li()
            out.append(f"</{tags.pop()}>")
            li_open.pop()

    for raw in (text or "").split("\n"):
        s = raw.strip()
        mb = re.match(r"\\begin\{(itemize|enumerate)\}", s)
        if mb:
            tag = "ol" if mb.group(1) == "enumerate" else "ul"
            out.append(f"<{tag}>")          # nests inside the open <li> if any
            tags.append(tag)
            li_open.append(False)
            continue
        if re.match(r"\\end\{(itemize|enumerate)\}", s):
            close_li()
            if tags:
                out.append(f"</{tags.pop()}>")
                li_open.pop()
            continue
        if s.startswith("\\item") and tags:
            close_li()
            out.append(f"<li>{inline(s[len('\\item'):].strip())}")
            li_open[-1] = True
            continue
        close_all()
        out.append(f"<div>{inline(s)}</div>" if s else "<br>")
    close_all()
    return "".join(out) or "&nbsp;"


def _block_latex(block) -> str:
    """One QTextBlock -> LaTeX, wrapping bold/italic runs."""
    parts = []
    it = block.begin()
    seen = False
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid():
            seen = True
            t = frag.text()
            cf = frag.charFormat()
            f = cf.font()
            va = cf.verticalAlignment()
            if va == QTextCharFormat.AlignSuperScript:
                t = f"\\textsuperscript{{{t}}}"
            elif va == QTextCharFormat.AlignSubScript:
                t = f"\\textsubscript{{{t}}}"
            if f.italic():
                t = f"\\textit{{{t}}}"
            if f.bold():
                t = f"\\textbf{{{t}}}"
            parts.append(t)
        it += 1
    return "".join(parts) if seen else block.text()


def document_to_latex(doc: QTextDocument) -> str:
    """Inverse of :func:`latex_to_html`: turn the rich edited document back
    into LaTeX — bullet/numbered lists become itemize/enumerate, bold and
    italic runs become \\textbf/\\textit. Other text passes through, so
    inline maths like ``$x^2$`` survives a round-trip."""
    lines: list[str] = []
    stack: list[str] = []        # open envs, one per nesting level
    _ENUM = (QTextListFormat.ListDecimal, QTextListFormat.ListLowerAlpha,
             QTextListFormat.ListUpperAlpha, QTextListFormat.ListLowerRoman,
             QTextListFormat.ListUpperRoman)

    def close_to(depth):
        while len(stack) > depth:
            lines.append(f"\\end{{{stack.pop()}}}")

    block = doc.begin()
    while block.isValid():
        tl = block.textList()
        text = _block_latex(block)
        if tl is not None:
            level = max(1, tl.format().indent())
            env = "enumerate" if tl.format().style() in _ENUM else "itemize"
            close_to(level)                       # leave deeper levels
            if len(stack) == level and stack[-1] != env:
                lines.append(f"\\end{{{stack.pop()}}}")
            while len(stack) < level:             # open up to this level
                lines.append(f"\\begin{{{env}}}")
                stack.append(env)
            lines.append("  " * level + f"\\item {text}")
        else:
            close_to(0)
            lines.append(text)
        block = block.next()
    close_to(0)
    return "\n".join(lines).strip("\n")


SCENE_H = 720.0                 # slide height in scene units (px)
# Turns a font's pt size into canvas pixels: px per pt on a default 16:9 slide (beamer's 9 cm high page); decks with
# another aspect get theirs from page_size_px.
FONT_SCALE = SCENE_H / (9.0 * 72.27 / 2.54)
HANDLE = 9.0                    # half-size of a resize handle, in px
MIN_PX = 24.0                   # smallest box dimension

# WYSIWYG body font: beamer's own Latin Modern Sans (loaded from tectonic's
# cache by latex_fonts), so the canvas text has the PDF's shapes and widths.
# Calibri / Carlito are the closest stand-ins until the cache has the fonts;
# the trailing families keep it sane on other machines.
CANVAS_FONT_FAMILIES = ["Latin Modern Sans", "Calibri", "Carlito",
                        "Segoe UI", "Helvetica"]
SERIF_FONT_FAMILIES = ["Latin Modern Roman", "Georgia", "Times New Roman",
                       "serif"]
MONO_FONT_FAMILIES = ["Latin Modern Mono", "Consolas", "Courier New",
                      "monospace"]
# The deck-wide default family ("sf" or "rm"), following the theme's font
# choice: beamer's serif font theme sets the whole slide in Roman.
_body_family = "sf"


# A theme typeface's Qt family (e.g. "Carlito") drawn in front of the
# sans stack, so the canvas wraps text where the PDF does.
_body_typeface = ""


def set_body_family(family: str, typeface: str = "") -> None:
    global _body_family, _body_typeface
    _body_family = "rm" if family == "rm" else "sf"
    _body_typeface = typeface or ""


def _sans_families() -> list[str]:
    return ([_body_typeface] if _body_typeface else []) + CANVAS_FONT_FAMILIES


# The theme's own itemize bullets, cut from the backdrop's probe pages
# (see bullets.py): {level: [(BulletGlyph, QImage), ...]}. Empty until a
# backdrop compile has run — the canvas then keeps Qt's plain discs.
_BULLETS: dict = {}


def set_bullet_glyphs(glyphs: dict) -> None:
    global _BULLETS
    _BULLETS = dict(glyphs or {})


def _bullet_for(level: int, size_pt: float):
    if not _BULLETS:
        return None
    entries = _BULLETS.get(level) or _BULLETS.get(max(_BULLETS))
    if not entries:
        return None
    return min(entries, key=lambda e: abs(e[0].size_pt - size_pt))


_BULLET_STYLES = (QTextListFormat.ListDisc, QTextListFormat.ListCircle,
                  QTextListFormat.ListSquare,
                  QTextListFormat.ListStyleUndefined)


def bullet_blocks(doc: QTextDocument) -> list:
    """(block, level) of every bulleted (not numbered) list item."""
    items = []
    block = doc.begin()
    while block.isValid():
        lst = block.textList()
        if lst is not None and lst.format().style() in _BULLET_STYLES:
            items.append((block, max(1, lst.format().indent())))
        block = block.next()
    return items


def hide_list_markers(doc: QTextDocument) -> bool:
    """Give bulleted lists the marker-less style (Qt draws nothing for it,
    and it still converts back to itemize) so the theme's bullets can be
    painted instead. Returns True if anything changed."""
    changed = False
    seen = set()
    block = doc.begin()
    while block.isValid():
        lst = block.textList()
        if lst is not None and id(lst) not in seen:
            seen.add(id(lst))
            fmt = lst.format()
            if fmt.style() in _BULLET_STYLES[:3]:
                fmt.setStyle(QTextListFormat.ListStyleUndefined)
                lst.setFormat(fmt)
                changed = True
        block = block.next()
    return changed


def _prepare_bullets(doc: QTextDocument, size_pt: float,
                     font_px: float) -> list:
    """Swap Qt's list markers for the theme's bullets: hide the markers,
    indent like beamer, and return the (block, level) pairs _draw_bullets
    paints next to."""
    if not _BULLETS:
        return []
    first = _bullet_for(1, size_pt)
    if first is not None and first[0].indent_em > 0:
        doc.setIndentWidth(first[0].indent_em * font_px)
    hide_list_markers(doc)
    return bullet_blocks(doc)


def themed_bullets() -> bool:
    """True once the theme's bullets are known (a backdrop compiled)."""
    return bool(_BULLETS)


def style_box_document(doc: QTextDocument, obj, text: str,
                       font_scale: float, editing: bool = False
                       ) -> tuple[float, list]:
    """Lay a text box's content into *doc* exactly as the canvas draws it
    — font, weight, colour, alignment, TeX spacing and the theme's
    bullets. Shared by the canvas painter and the in-place editor, so
    editing a box doesn't change how it looks. Returns (font_px, bullet
    blocks)."""
    font = canvas_font(max(6, int(obj.font_pt * font_scale)))
    _apply_font_family(font, getattr(obj, "font_family", ""))
    font.setBold(obj.bold)
    font.setItalic(obj.italic)
    doc.setDefaultFont(font)
    align = {"center": Qt.AlignHCenter, "right": Qt.AlignRight}.get(
        obj.align, Qt.AlignLeft)
    opt = QTextOption(align)
    opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    doc.setDefaultTextOption(opt)
    colour = obj.color or "#000000"
    doc.setHtml(f'<div style="color:{colour}">'
                f'{latex_to_html(text, pretty=not editing)}</div>')
    font_px = obj.font_pt * font_scale
    bullets = _prepare_bullets(doc, obj.font_pt, font_px)
    # Same leading as the serializer's \fontsize{pt}{lead}.
    _apply_tex_spacing(doc, round(obj.font_pt * 1.2) * font_scale,
                       font_scale)
    doc.setDocumentMargin(0)
    return font_px, bullets


# beamer's list spacing (beamerbaselocalstructure.sty), in pt: the gap
# before a list (\topsep) and between its items (\itemsep), per level.
_TOPSEP_PT = {1: 3.0}
_ITEMSEP_PT = {1: 3.0}
_NESTED_TOPSEP_PT = 2.0


def _list_level(block) -> int:
    lst = block.textList()
    return max(1, lst.format().indent()) if lst is not None else 0


def _apply_tex_spacing(doc: QTextDocument, lead_px: float,
                       pt_px: float) -> None:
    """Lay the text out with TeX's spacing instead of Qt's: lines exactly
    one baselineskip apart (the lead of the box's fontsize), and beamer's
    topsep / itemsep around and between list items."""
    prev = 0
    block = doc.begin()
    while block.isValid():
        level = _list_level(block)
        top = 0.0
        if level and level > prev:          # a list (or sub-list) opens
            top = _TOPSEP_PT.get(level, _NESTED_TOPSEP_PT)
        elif level and level == prev:       # next item, same level
            top = _ITEMSEP_PT.get(level, 0.0)
        elif level and level < prev:        # back out of a sub-list
            top = max(_NESTED_TOPSEP_PT, _ITEMSEP_PT.get(level, 0.0))
        elif prev and not level:            # text after a list
            top = _TOPSEP_PT.get(prev, _NESTED_TOPSEP_PT)
        fmt = block.blockFormat()
        fmt.setTopMargin(top * pt_px)
        fmt.setBottomMargin(0)
        fmt.setLineHeight(lead_px,
                          QTextBlockFormat.LineHeightTypes.FixedHeight.value)
        QTextCursor(block).setBlockFormat(fmt)
        prev = level
        block = block.next()


def _first_baseline_shift(doc: QTextDocument) -> float:
    """How far to move the laid-out text so its first baseline sits where
    TeX puts it: the tallest glyph of the first line touching the top of
    the box (plus any list topsep), not Qt's full font ascent below it."""
    doc.documentLayout().documentSize()     # Qt lays out lazily
    block = doc.begin()
    layout = block.layout() if block.isValid() else None
    if layout is None or layout.lineCount() == 0:
        return 0.0
    line = layout.lineAt(0)
    text = block.text()[line.textStart():line.textStart() + line.textLength()]
    it = block.begin()
    font = doc.defaultFont()
    if not it.atEnd():
        font = it.fragment().charFormat().font()
    tall = -QFontMetricsF(font).tightBoundingRect(text or "x").top()
    actual = layout.position().y() + line.y() + line.ascent()
    want = block.blockFormat().topMargin() + tall
    return want - actual


def _draw_bullets(painter, items: list, size_pt: float,
                  font_px: float) -> None:
    for block, level in items:
        hit = _bullet_for(level, size_pt)
        layout = block.layout()
        if hit is None or layout is None or layout.lineCount() == 0:
            continue
        g, img = hit
        line = layout.lineAt(0)
        pos = layout.position()
        text_x = pos.x() + line.x()
        baseline = pos.y() + line.y() + line.ascent()
        w, h = g.width_em * font_px, g.height_em * font_px
        painter.drawImage(
            QRectF(text_x - g.gap_em * font_px - w,
                   baseline - g.top_em * font_px, w, h), img)


def canvas_font(pixel_size: int = 0, *, stretch: int = 0) -> QFont:
    """A QFont using the WYSIWYG body family stack."""
    fams = SERIF_FONT_FAMILIES if _body_family == "rm" else _sans_families()
    f = QFont(fams[0])
    f.setFamilies(fams)
    if pixel_size:
        f.setPixelSize(pixel_size)
    if stretch:
        f.setStretch(stretch)
    return f


def _apply_font_family(font: QFont, family: str) -> None:
    """Reflect a box's LaTeX font type (rm/sf/tt) on the canvas."""
    if family == "rm":
        font.setFamilies(SERIF_FONT_FAMILIES)
        font.setStyleHint(QFont.Serif)
    elif family == "tt":
        font.setFamilies(MONO_FONT_FAMILIES)
        font.setStyleHint(QFont.Monospace)
    elif family == "sf":
        font.setFamilies(_sans_families())
        font.setStyleHint(QFont.SansSerif)

_ASPECT_RATIO = {              # width : height multiplier
    "169": 16 / 9, "1610": 16 / 10, "43": 4 / 3,
    "32": 3 / 2, "54": 5 / 4, "141": 1.41,
}

# Resize-handle ids, clockwise from top-left.
TL, T, TR, R, BR, B, BL, L = range(8)
_LEFT = {TL, L, BL}
_RIGHT = {TR, R, BR}
_TOP = {TL, T, TR}
_BOTTOM = {BL, B, BR}


def scene_width(aspect: str) -> float:
    return SCENE_H * _ASPECT_RATIO.get(aspect, 16 / 9)


_CM_TO_PT = 72.27 / 2.54
# beamer's paper height per aspectratio preset, in cm (beamer.cls). The
# canvas page is SCENE_H px high whatever the aspect, so px-per-pt — and
# with it every font size on the canvas — depends on the real height: a
# 16:9 slide is 9 cm, not the 9.6 cm of 4:3.
_BEAMER_H_CM = {"169": 9.0, "1610": 10.0, "43": 9.6, "32": 9.0,
                "54": 10.0, "141": 10.5}


def page_size_px(aspect: str, w_cm: float = 0.0, h_cm: float = 0.0):
    """Return (page_w_px, page_h_px, font_scale). Height is fixed at
    SCENE_H; width follows the aspect or custom cm size. font_scale turns
    a pt font size into canvas pixels for the page's real height."""
    if w_cm > 0 and h_cm > 0:
        ratio = w_cm / h_cm
        h_pt = h_cm * _CM_TO_PT
    else:
        ratio = _ASPECT_RATIO.get(aspect, 16 / 9)
        h_pt = _BEAMER_H_CM.get(aspect, 9.0) * _CM_TO_PT
    return SCENE_H * ratio, SCENE_H, SCENE_H / h_pt


class BoxItem(QGraphicsObject):
    """A movable, eight-handle-resizable rectangle bound to a model
    object. Coordinates are 0..1 within the page's content area (page
    minus the deck's gap); this maps them to scene pixels. Subclasses
    paint the content."""

    geometryChanged = Signal()
    doubleClicked = Signal()
    lockToggled = Signal()

    def __init__(self, obj, page_w: float, page_h: float, gap: float = 0.0,
                 font_scale: float = FONT_SCALE):
        super().__init__()
        self.obj = obj
        self._pw = page_w
        self._ph = page_h
        self._gap = gap
        self._font_scale = font_scale
        self._hover = False
        cw, ch, ox, oy = self._content()
        self._rect = QRectF(0, 0, max(MIN_PX, obj.w * cw),
                            max(MIN_PX, obj.h * ch))
        self.setPos(ox + obj.x * cw, oy + obj.y * ch)
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self._resize_handle: int | None = None
        self._press_scene = QPointF()
        self._start_rect = QRectF()
        self._start_pos = QPointF()
        self._apply_lock()

    def _aspect_locked(self) -> bool:
        return False

    def _is_locked(self) -> bool:
        return bool(getattr(self.obj, "locked", True))

    def _apply_lock(self) -> None:
        """A locked box is beamer-controlled: it can be selected (to edit or
        unlock) but not dragged or resized."""
        self.setFlag(QGraphicsItem.ItemIsMovable, not self._is_locked())

    def _lock_rect(self) -> QRectF:
        """The clickable lock toggle, on the box's right side near the top."""
        s = 26.0
        r = self._rect
        return QRectF(r.right() - s - 4, r.top() + 4, s, s)

    # -- geometry --------------------------------------------------
    def boundingRect(self) -> QRectF:
        m = HANDLE + 1
        return self._rect.adjusted(-m, -m, m, m)

    def _handle_rects(self) -> dict[int, QRectF]:
        r = self._rect
        cx, cy = r.center().x(), r.center().y()
        pts = {
            TL: (r.left(), r.top()), T: (cx, r.top()), TR: (r.right(), r.top()),
            R: (r.right(), cy), BR: (r.right(), r.bottom()),
            B: (cx, r.bottom()), BL: (r.left(), r.bottom()), L: (r.left(), cy),
        }
        return {h: QRectF(x - HANDLE, y - HANDLE, 2 * HANDLE, 2 * HANDLE)
                for h, (x, y) in pts.items()}

    def _handle_at(self, pos: QPointF) -> int | None:
        # Locked boxes can still be *resized* (e.g. to size a picture or set
        # a column's width) — they just can't be dragged to a new position.
        for h, rect in self._handle_rects().items():
            if rect.contains(pos):
                return h
        return None

    # -- mouse -----------------------------------------------------
    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event):
        if self._lock_rect().contains(event.pos()):
            self.setCursor(Qt.PointingHandCursor)
            super().hoverMoveEvent(event)
            return
        h = self._handle_at(event.pos()) if self.isSelected() else None
        cursors = {
            TL: Qt.SizeFDiagCursor, BR: Qt.SizeFDiagCursor,
            TR: Qt.SizeBDiagCursor, BL: Qt.SizeBDiagCursor,
            T: Qt.SizeVerCursor, B: Qt.SizeVerCursor,
            L: Qt.SizeHorCursor, R: Qt.SizeHorCursor,
        }
        default = Qt.ArrowCursor if self._is_locked() else Qt.SizeAllCursor
        self.setCursor(cursors.get(h, default))
        super().hoverMoveEvent(event)

    def toggle_lock(self) -> None:
        self.obj.locked = not self._is_locked()
        self._apply_lock()
        self.update()
        self.lockToggled.emit()

    def mousePressEvent(self, event):
        # The lock badge is always visible, so it's always clickable — it's
        # the only control on a locked box.
        if self._lock_rect().contains(event.pos()):
            self.toggle_lock()
            event.accept()
            return
        h = self._handle_at(event.pos()) if self.isSelected() else None
        if h is not None:
            self._resize_handle = h
            self._press_scene = event.scenePos()
            self._start_rect = QRectF(self._rect)
            self._start_pos = self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_handle is None:
            super().mouseMoveEvent(event)
            return
        sp = event.scenePos()
        sc = self.scene()
        if hasattr(sc, "snap_point"):
            sp = sc.snap_point(sp, exclude=self)
        d = sp - self._press_scene
        x, y = self._start_pos.x(), self._start_pos.y()
        w, h = self._start_rect.width(), self._start_rect.height()
        hd = self._resize_handle
        if hd in _LEFT:
            x += d.x(); w -= d.x()
        if hd in _RIGHT:
            w += d.x()
        if hd in _TOP:
            y += d.y(); h -= d.y()
        if hd in _BOTTOM:
            h += d.y()
        if w < MIN_PX:
            if hd in _LEFT:
                x = self._start_pos.x() + self._start_rect.width() - MIN_PX
            w = MIN_PX
        if h < MIN_PX:
            if hd in _TOP:
                y = self._start_pos.y() + self._start_rect.height() - MIN_PX
            h = MIN_PX
        # Locked aspect (e.g. pictures): corner drags keep the box ratio.
        if self._aspect_locked() and hd in (TL, TR, BL, BR) \
                and self._start_rect.height() > 0:
            ratio = self._start_rect.width() / self._start_rect.height()
            h = max(MIN_PX, w / ratio)
            if hd in _TOP:
                y = self._start_pos.y() + self._start_rect.height() - h
        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, w, h)
        self.setPos(x, y)
        self.update()
        self._write_geometry()
        self.geometryChanged.emit()

    def mouseReleaseEvent(self, event):
        self._resize_handle = None
        self._write_geometry()
        self.geometryChanged.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        # PowerPoint-style: double-click edits the object in place.
        self.doubleClicked.emit()
        event.accept()

    def scene_rect(self) -> QRectF:
        """The box's rectangle in scene coordinates (for placing an
        in-place editor over it)."""
        return QRectF(self.pos().x(), self.pos().y(),
                      self._rect.width(), self._rect.height())

    def key_points(self):
        """Snap targets in scene coords — the four corners and the centre."""
        r = self._rect
        return [self.mapToScene(r.topLeft()), self.mapToScene(r.topRight()),
                self.mapToScene(r.bottomLeft()), self.mapToScene(r.bottomRight()),
                self.mapToScene(r.center())]

    def _content(self):
        """Content area in scene px: (width, height, origin_x, origin_y)."""
        g = self._gap
        return ((1 - 2 * g) * self._pw, (1 - 2 * g) * self._ph,
                g * self._pw, g * self._ph)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            sc = self.scene()
            pos = value
            # Snap the top-left to the grid / other objects when enabled.
            if hasattr(sc, "snap_point"):
                pos = sc.snap_point(QPointF(value), exclude=self)
            # Allow parking a box on the grey pasteboard around the slide (it
            # just won't render in the PDF) — clamp only to the scene rect so
            # it can't be dragged out of reach entirely.
            sr = sc.sceneRect()
            nx = min(max(sr.left(), pos.x()), sr.right() - self._rect.width())
            ny = min(max(sr.top(), pos.y()), sr.bottom() - self._rect.height())
            return QPointF(nx, ny)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._write_geometry()
            self.geometryChanged.emit()
        return super().itemChange(change, value)

    def _write_geometry(self) -> None:
        cw, ch, ox, oy = self._content()
        self.obj.x = round((self.pos().x() - ox) / cw, 4)
        self.obj.y = round((self.pos().y() - oy) / ch, 4)
        self.obj.w = round(self._rect.width() / cw, 4)
        self.obj.h = round(self._rect.height() / ch, 4)

    def sync_from_model(self) -> None:
        """Re-read geometry from the model (after spinbox edits)."""
        cw, ch, ox, oy = self._content()
        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, max(MIN_PX, self.obj.w * cw),
                            max(MIN_PX, self.obj.h * ch))
        self.setPos(ox + self.obj.x * cw, oy + self.obj.y * ch)
        self.update()

    # -- painting helpers -----------------------------------------
    def _paint_selection(self, painter):
        if not self.isSelected():
            # An unselected box shows no chrome at all — the slide reads like
            # the PDF. Hovering reveals a faint outline + lock badge so empty
            # boxes are still discoverable and the lock stays clickable.
            if getattr(self, "_hover", False):
                painter.setPen(QPen(QColor(150, 150, 150), 0, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(self._rect)
                self._paint_lock(painter)
            return
        painter.setPen(QPen(QColor(40, 120, 220), 0, Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self._rect)
        # Resize handles are shown even when locked (resize is allowed; only
        # moving is blocked), so a locked picture's size can be set.
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(QPen(QColor(40, 120, 220), 0))
        for rect in self._handle_rects().values():
            painter.drawRect(rect)
        self._paint_lock(painter)

    def _paint_decoration(self, painter, border_only=False):
        """Box fill + border rectangle (sharp/rounded) with optional dash
        style, fill opacity and drop shadow. No-op unless a fill or border
        colour is set."""
        o = self.obj
        fill = "" if border_only else getattr(o, "fill", "")
        bc = getattr(o, "border_color", "")
        bw = getattr(o, "border_width", 1.0)
        rounded = getattr(o, "corner", "sharp") == "rounded"
        rad = getattr(o, "corner_radius", 4.0) * self._font_scale * 0.5
        if not fill and not bc:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        def _draw():
            if rounded:
                painter.drawRoundedRect(self._rect, rad, rad)
            else:
                painter.drawRect(self._rect)

        if getattr(o, "shadow", False):
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 55))
            painter.translate(3, 3)
            _draw()
            painter.restore()
        if fill:
            painter.setBrush(fill_brush(o, self._rect,
                                        getattr(o, "fill_opacity", 1.0)))
        else:
            painter.setBrush(Qt.NoBrush)
        if bc and bw > 0:
            pen = QPen(QColor(bc), max(1.0, bw * 1.5))
            pen.setStyle(_PEN_STYLE.get(getattr(o, "border_style", "solid"),
                                        Qt.SolidLine))
            painter.setPen(pen)
        else:
            painter.setPen(Qt.NoPen)
        _draw()
        painter.restore()

    def _paint_lock(self, painter):
        """A bold padlock badge so the lock state reads at a glance —
        amber & closed when locked, green & open when freely positioned.
        Click it to toggle."""
        r = self._lock_rect()
        locked = self._is_locked()
        accent = QColor(217, 119, 6) if locked else QColor(34, 160, 86)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Filled, high-contrast disc with a white padlock drawn on top.
        painter.setBrush(QBrush(QColor(0, 0, 0, 40)))      # soft shadow
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(r.translated(0, 1))
        painter.setBrush(QBrush(accent))
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.drawEllipse(r)
        white = QColor(255, 255, 255)
        # Body of the padlock.
        bw, bh = r.width() * 0.46, r.height() * 0.30
        body = QRectF(r.center().x() - bw / 2,
                      r.center().y() - bh / 2 + r.height() * 0.08, bw, bh)
        painter.setBrush(QBrush(white))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(body, 1.5, 1.5)
        # Shackle: a closed loop when locked, lifted to the side when open.
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(white, 2.0))
        sw = bw * 0.74
        sx = r.center().x() - sw / 2
        sy = body.top() - sw * 0.62
        arc = QRectF(sx, sy, sw, sw)
        if locked:
            painter.drawArc(arc, 0, 180 * 16)
            painter.drawLine(QPointF(arc.left(), arc.center().y()),
                             QPointF(arc.left(), body.top()))
            painter.drawLine(QPointF(arc.right(), arc.center().y()),
                             QPointF(arc.right(), body.top()))
        else:
            painter.drawArc(arc.translated(sw * 0.5, 0), 20 * 16, 180 * 16)
            painter.drawLine(QPointF(arc.left(), arc.center().y()),
                             QPointF(arc.left(), body.top()))
        painter.restore()


class TextBoxItem(BoxItem):
    def boundingRect(self):
        # Allow text taller than the box (e.g. a big heading in a short box)
        # to render without being clipped or leaving paint artifacts — it
        # flows downward from the top, just like the textblock in the PDF.
        r = super().boundingRect()
        return QRectF(r.x(), r.y(), r.width(), r.height() * 2 + 40)

    def paint(self, painter, option, widget=None):
        obj: SlideText = self.obj
        # While this box is being edited, the floating editor shows its
        # content — don't also paint the box's own (overflowing) text, or it
        # appears doubled outside the box. Keep the selection chrome so the
        # handles still frame it.
        if getattr(self, "_editing", False):
            # The transparent in-place editor draws the text; keep the
            # box's fill / frame / block header under it so editing looks
            # exactly like the finished slide.
            self._paint_decoration(painter)
            if getattr(obj, "block", ""):
                self._paint_block(painter)
            self._paint_selection(painter)
            return
        self._paint_decoration(painter)

        # A pure math box ($…$, \[…\]) is rendered as real maths, like the
        # equation editor's preview, rather than shown as raw LaTeX.
        inner = _math_only(obj.text)
        if inner is not None:
            from . import chemistry, equations
            body = chemistry.unwrap_ce(inner)
            pm = (chemistry.render_live_preview(body, 24) if body is not None
                  else equations.render_live_preview(inner, 24))
            if pm is not None and not pm.isNull():
                area = self._rect.adjusted(4, 2, -4, -2)
                scaled = pm.scaled(area.size().toSize(), Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
                x = self._rect.x() + (self._rect.width() - scaled.width()) / 2
                y = self._rect.y() + (self._rect.height() - scaled.height()) / 2
                painter.drawPixmap(QPointF(x, y), scaled)
                self._paint_selection(painter)
                return

        # A beamer block: coloured title bar + tinted body, text sits below.
        body_top = self._rect.y()
        if getattr(obj, "block", ""):
            body_top = self._paint_block(painter)

        doc = QTextDocument()
        font_px, bullets = style_box_document(doc, obj, obj.text,
                                              self._font_scale)
        self._underline_misspelled(doc)
        inner = self._text_rect(body_top)
        doc.setTextWidth(inner.width())
        shift = _first_baseline_shift(doc)

        painter.save()
        painter.translate(inner.topLeft() + QPointF(0, shift))
        # Clip generously below so glyphs/descenders and overflow aren't cut.
        painter.setClipRect(QRectF(-font_px, -2, inner.width() + font_px,
                                   max(inner.height(), doc.size().height()) + 6))
        doc.drawContents(painter)
        _draw_bullets(painter, bullets, obj.font_pt, font_px)
        painter.restore()
        self._paint_selection(painter)

    def _block_header_h(self) -> float:
        return max(16.0, self.obj.font_pt * self._font_scale * 0.85)

    def _text_rect(self, body_top: float | None = None) -> QRectF:
        """Where the text lays out: flush with the box as textpos puts it,
        inset only for a framed box (tikz "inner sep=3pt") or a block."""
        obj = self.obj
        if body_top is None:
            body_top = self._rect.y()
            if getattr(obj, "block", ""):
                body_top += self._block_header_h()
        from .serializer import _has_frame
        pad = 3 * self._font_scale if _has_frame(obj) else 0.0
        if getattr(obj, "block", ""):
            pad = max(pad, 4.0)
        return QRectF(self._rect.x() + pad, body_top + pad,
                      self._rect.width() - 2 * pad,
                      self._rect.bottom() - body_top - 2 * pad)

    def text_scene_rect(self) -> QRectF:
        """_text_rect in scene coordinates (for the in-place editor)."""
        return self.mapRectToScene(self._text_rect())

    _BLOCK_COLORS = {"block": QColor("#3b5ba9"),
                     "alertblock": QColor("#b03a3a"),
                     "exampleblock": QColor("#2e7d4f"),
                     "theorem": QColor("#3b5ba9"),
                     "definition": QColor("#3b5ba9"),
                     "corollary": QColor("#3b5ba9"),
                     "lemma": QColor("#3b5ba9"),
                     "example": QColor("#2e7d4f"),
                     "proof": QColor("#6b7280"),
                     "fact": QColor("#3b5ba9")}
    # Environments whose title beamer prints as "Name." even without a title.
    _THEOREM_LABELS = {"theorem": "Theorem", "definition": "Definition",
                       "corollary": "Corollary", "lemma": "Lemma",
                       "example": "Example", "proof": "Proof",
                       "fact": "Fact"}

    def _paint_block(self, painter) -> float:
        """Draw the block's coloured title bar + tinted body; return the
        y where the body text should start."""
        obj = self.obj
        c = self._BLOCK_COLORS.get(obj.block, self._BLOCK_COLORS["block"])
        # Theorem-like environments always show a label (e.g. "Theorem"),
        # with the optional title in parentheses.
        if obj.block in self._THEOREM_LABELS:
            label = self._THEOREM_LABELS[obj.block]
            title = f"{label} ({obj.block_title})" if obj.block_title else label
        else:
            title = obj.block_title or ""
        bh = self._block_header_h()
        hdr = QRectF(self._rect.x(), self._rect.y(), self._rect.width(), bh)
        body = QRectF(self._rect.x(), hdr.bottom(), self._rect.width(),
                      max(0.0, self._rect.bottom() - hdr.bottom()))
        painter.save()
        painter.fillRect(body, QColor(c.red(), c.green(), c.blue(), 28))
        painter.fillRect(hdr, c)
        painter.setPen(QColor("#ffffff"))
        f = canvas_font(max(8, int(bh * 0.6)))
        f.setBold(True); painter.setFont(f)
        painter.drawText(hdr.adjusted(6, 0, -6, 0),
                         int(Qt.AlignVCenter | Qt.AlignLeft), title)
        painter.restore()
        return hdr.bottom()

    def _underline_misspelled(self, doc):
        from . import spellcheck
        if getattr(self.scene(), "thumbnail", False):
            return                  # previews don't show spelling marks
        if not (spellcheck.enabled() and spellcheck.available()):
            return
        spans = spellcheck.misspelled_spans(doc.toPlainText())
        if not spans:
            return
        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
        fmt.setUnderlineColor(QColor(220, 40, 40))
        cur = QTextCursor(doc)
        for start, end in spans:
            cur.setPosition(start)
            cur.setPosition(end, QTextCursor.KeepAnchor)
            cur.mergeCharFormat(fmt)


def _mtime(path: str) -> float:
    import os
    try:
        return os.path.getmtime(path) if path else 0.0
    except OSError:
        return 0.0


def load_picture(path: str, pdf_width: int = 1600) -> QPixmap | None:
    """A picture box's image: any Qt-readable image, or the first page of
    a PDF (drawings and chemical structures are vector PDFs, so the slide
    stays sharp) rendered with PyMuPDF."""
    if not path:
        return None
    if path.lower().endswith(".pdf"):
        try:
            import pymupdf
            from PySide6.QtGui import QImage
            with pymupdf.open(path) as doc:
                page = doc[0]
                z = pdf_width / max(1.0, page.rect.width)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=True)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                             QImage.Format_RGBA8888).copy()
            return QPixmap.fromImage(img)
        except Exception:
            return None
    pm = QPixmap(path)
    return pm if not pm.isNull() else None


class PictureBoxItem(BoxItem):
    def __init__(self, obj, page_w, page_h, gap=0.0, font_scale=FONT_SCALE):
        super().__init__(obj, page_w, page_h, gap, font_scale)
        self._pix: QPixmap | None = None
        self._pix_path = None

    def _pixmap(self) -> QPixmap | None:
        # Keyed on the file's mtime too, so a drawing or chemical structure
        # re-saved under the same name shows its new content.
        from . import image_effects
        fx = image_effects.has_effects(self.obj)
        path = image_effects.baked_path(self.obj) if fx else self.obj.path
        key = (path, _mtime(self.obj.path))
        if key != self._pix_path:
            self._pix_path = key
            self._pix = load_picture(path or self.obj.path)
            self._baked = bool(fx and path)
        return self._pix

    def _pad(self):
        from . import image_effects
        return (image_effects.padding(self.obj)
                if getattr(self, "_baked", False) else (0.0, 0.0, 0.0, 0.0))

    def boundingRect(self) -> QRectF:
        # Glow and reflection paint beyond the box.
        r = super().boundingRect()
        pl, pt, pr, pb = self._pad()
        w, h = self._rect.width(), self._rect.height()
        return r.adjusted(-pl * w, -pt * h, pr * w, pb * h)

    def _aspect_locked(self):
        return bool(self.obj.keep_aspect)

    def _source_rect(self, pm: QPixmap) -> QRectF:
        """The kept (un-cropped) region of the source pixmap."""
        o = self.obj
        if getattr(self, "_baked", False):      # crop is baked in
            return QRectF(0, 0, pm.width(), pm.height())
        cl = max(0.0, min(0.9, getattr(o, "crop_l", 0.0)))
        ct = max(0.0, min(0.9, getattr(o, "crop_t", 0.0)))
        cr = max(0.0, min(0.9, getattr(o, "crop_r", 0.0)))
        cb = max(0.0, min(0.9, getattr(o, "crop_b", 0.0)))
        w, h = pm.width(), pm.height()
        return QRectF(cl * w, ct * h,
                      max(1.0, (1 - cl - cr) * w), max(1.0, (1 - ct - cb) * h))

    def paint(self, painter, option, widget=None):
        self._paint_decoration(painter)
        pm = self._pixmap()
        if pm is not None:
            src = self._source_rect(pm)
            pl, pt, pr, pb = self._pad()
            if pl or pt or pr or pb:
                # Measure the aspect on the content, not the padding.
                src = QRectF(0, 0, src.width() / (1 + pl + pr),
                             src.height() / (1 + pt + pb))
            # Target rect inside the box, honouring the *cropped* aspect.
            if self.obj.keep_aspect and src.height() > 0:
                ratio = src.width() / src.height()
                tw, th = self._rect.width(), self._rect.height()
                if tw / th > ratio:
                    tw = th * ratio
                else:
                    th = tw / ratio
            else:
                tw, th = self._rect.width(), self._rect.height()
            cx = self._rect.x() + self._rect.width() / 2
            cy = self._rect.y() + self._rect.height() / 2
            target = QRectF(cx - tw / 2, cy - th / 2, tw, th)
            painter.save()
            painter.setOpacity(max(0.0, min(1.0, self.obj.opacity)))
            angle = getattr(self.obj, "rotation", 0.0)
            if angle:
                painter.translate(cx, cy)
                painter.rotate(angle)
                painter.translate(-cx, -cy)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            if pl or pt or pr or pb:
                tw, th = target.width(), target.height()
                target = target.adjusted(-pl * tw, -pt * th, pr * tw, pb * th)
                src = QRectF(0, 0, pm.width(), pm.height())
            painter.drawPixmap(target, pm, src)
            painter.restore()
        else:
            painter.fillRect(self._rect, QColor(235, 235, 235))
            painter.setPen(QPen(QColor(150, 150, 150)))
            painter.drawText(self._rect, Qt.AlignCenter, "Image\n(set path)")
        self._paint_selection(painter)


class VideoBoxItem(BoxItem):
    """A video box: shows the poster image if one is set, else a dark
    placeholder — always with a play-button badge and the filename so the
    canvas reads like PowerPoint's video frame. Double-click swaps the
    video file (handled by the window)."""

    def __init__(self, obj, page_w, page_h, gap=0.0, font_scale=FONT_SCALE):
        super().__init__(obj, page_w, page_h, gap, font_scale)
        self._pix: QPixmap | None = None
        self._pix_path = None

    def _poster(self) -> QPixmap | None:
        if self.obj.poster != self._pix_path:
            self._pix_path = self.obj.poster
            pm = QPixmap(self.obj.poster) if self.obj.poster else QPixmap()
            self._pix = pm if not pm.isNull() else None
        return self._pix

    def paint(self, painter, option, widget=None):
        pm = self._poster()
        if pm is not None:
            painter.save()
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(self._rect, pm, QRectF(pm.rect()))
            painter.restore()
        else:
            painter.fillRect(self._rect, QColor(38, 38, 38))
        # Play badge: translucent disc + white triangle, centred.
        r = min(self._rect.width(), self._rect.height()) * 0.18
        cx, cy = self._rect.center().x(), self._rect.center().y()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 130))
        painter.drawEllipse(QPointF(cx, cy), r, r)
        tri = QPolygonF([QPointF(cx - r * 0.35, cy - r * 0.55),
                         QPointF(cx - r * 0.35, cy + r * 0.55),
                         QPointF(cx + r * 0.65, cy)])
        painter.setBrush(QColor("#ffffff"))
        painter.drawPolygon(tri)
        painter.restore()
        # Filename strip along the bottom (or a hint when no file yet).
        import os
        label = (os.path.basename(self.obj.path) if self.obj.path
                 else "Video (double-click to choose a file)")
        painter.setPen(QPen(QColor(255, 255, 255)))
        f = painter.font()
        f.setPixelSize(max(9, int(self._rect.height() * 0.07)))
        painter.setFont(f)
        strip = QRectF(self._rect.x(), self._rect.bottom() - f.pixelSize() * 2,
                       self._rect.width(), f.pixelSize() * 2)
        painter.fillRect(strip, QColor(0, 0, 0, 110))
        painter.drawText(strip, Qt.AlignCenter, label)
        self._paint_selection(painter)


class TableBoxItem(BoxItem):
    """A grid of cells stretched to the box. Double-clicking a cell asks
    the window to edit that cell in place."""

    cellDoubleClicked = Signal(int, int)

    def _dims(self):
        rows = self.obj.rows or [[""]]
        nrows = len(rows)
        ncols = max((len(r) for r in rows), default=1)
        return rows, nrows, ncols

    def cell_scene_rect(self, r: int, c: int) -> QRectF:
        _, nrows, ncols = self._dims()
        cw = self._rect.width() / ncols
        ch = self._rect.height() / nrows
        return QRectF(self.pos().x() + c * cw, self.pos().y() + r * ch, cw, ch)

    def _cell_at(self, pos: QPointF):
        _, nrows, ncols = self._dims()
        cw = self._rect.width() / ncols
        ch = self._rect.height() / nrows
        c = min(ncols - 1, max(0, int(pos.x() // cw)))
        r = min(nrows - 1, max(0, int(pos.y() // ch)))
        return r, c

    def mouseDoubleClickEvent(self, event):
        r, c = self._cell_at(event.pos())
        self.cellDoubleClicked.emit(r, c)
        event.accept()

    def paint(self, painter, option, widget=None):
        obj: SlideTable = self.obj
        rows, nrows, ncols = self._dims()
        cw = self._rect.width() / ncols
        ch = self._rect.height() / nrows
        grid = getattr(obj, "grid", "all")
        if not getattr(obj, "border", True) and grid == "all":
            grid = "none"
        striped = getattr(obj, "striped", False)
        stripe = QColor(getattr(obj, "stripe_color", "#F5F5F5") or "#F5F5F5")
        header_bg = QColor(getattr(obj, "header_bg", "") or TABLE_HEADER_BG)
        header_fg = QColor(getattr(obj, "header_fg", "") or TABLE_HEADER_FG)
        rule_col = QColor(getattr(obj, "rule_color", "") or TABLE_RULE)
        align = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter,
                 "right": Qt.AlignRight}.get(getattr(obj, "align", "left"),
                                             Qt.AlignLeft)
        painter.fillRect(self._rect, QColor(getattr(obj, "fill", "") or "#FFFFFF"))
        # Row backgrounds: coloured header, optional zebra striping.
        for r in range(nrows):
            row_rect = QRectF(self._rect.x(), self._rect.y() + r * ch,
                              self._rect.width(), ch)
            if obj.header and r == 0:
                painter.fillRect(row_rect, header_bg)
            elif striped and (r - (1 if obj.header else 0)) % 2 == 1:
                painter.fillRect(row_rect, stripe)
        # Grid lines per the chosen style.
        if grid != "none":
            painter.setPen(QPen(rule_col,
                                max(0.6, getattr(obj, "rule_width", 0.8)
                                    * self._font_scale * 0.6)))
            if grid == "all":
                for i in range(ncols + 1):
                    x = self._rect.x() + i * cw
                    painter.drawLine(QPointF(x, self._rect.y()),
                                     QPointF(x, self._rect.bottom()))
            if grid in ("all", "horizontal"):
                for j in range(nrows + 1):
                    y = self._rect.y() + j * ch
                    painter.drawLine(QPointF(self._rect.x(), y),
                                     QPointF(self._rect.right(), y))
            elif grid == "outer":
                painter.drawLine(self._rect.topLeft(), self._rect.topRight())
                painter.drawLine(self._rect.bottomLeft(),
                                 self._rect.bottomRight())
        base_font = canvas_font(max(6, int(obj.font_pt * self._font_scale)))
        for r in range(nrows):
            is_head = obj.header and r == 0
            font = QFont(base_font)
            font.setBold(is_head)
            painter.setFont(font)
            painter.setPen(QPen(header_fg if is_head
                                else QColor(obj.color or "#000000")))
            for c in range(ncols):
                text = rows[r][c] if c < len(rows[r]) else ""
                cell = QRectF(self._rect.x() + c * cw, self._rect.y() + r * ch,
                              cw, ch)
                if "$" in text or "\\" in text:
                    _draw_rich_cell(painter, cell.adjusted(5, 1, -5, -1),
                                    text, font, painter.pen().color(), align)
                else:
                    painter.drawText(
                        cell.adjusted(5, 1, -5, -1),
                        int(Qt.AlignVCenter | align | Qt.TextWordWrap), text)
        self._paint_decoration(painter, border_only=True)
        self._paint_selection(painter)


def _draw_rich_cell(painter, rect: QRectF, text: str, font: QFont,
                    colour: QColor, align) -> None:
    """A table cell with LaTeX in it (maths, \\%, \\textcolor…), drawn as
    it prints and centred vertically like a plain cell."""
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    doc.setDefaultFont(font)
    h_align = {Qt.AlignHCenter: "center", Qt.AlignRight: "right"}.get(
        align, "left")
    doc.setHtml(f'<div align="{h_align}" style="color:{colour.name()}">'
                f'{_pretty_inline_html(text)}</div>')
    doc.setTextWidth(rect.width())
    dy = max(0.0, (rect.height() - doc.size().height()) / 2)
    painter.save()
    painter.translate(rect.x(), rect.y() + dy)
    doc.drawContents(painter, QRectF(0, 0, rect.width(), rect.height()))
    painter.restore()


class LineBoxItem(BoxItem):
    """A line / arrow between two endpoints. Each end has its own handle and
    can be dragged anywhere (so the line can point in any direction); the
    box's (w, h) are the signed deltas from end 1 to end 2."""

    def __init__(self, obj, page_w, page_h, gap=0.0, font_scale=FONT_SCALE):
        self._drag_end = None
        self._suppress_write = True
        super().__init__(obj, page_w, page_h, gap, font_scale)
        self._resync()
        self._suppress_write = False

    # Lines use their own endpoint handles, not the 8 box handles.
    def _handle_rects(self):
        return {}

    def _resync(self):
        # Place the item at the bounding-box top-left and size it to the
        # absolute extent, so a line in any direction matches its geometry.
        cw, ch, ox, oy = self._content()
        o = self.obj
        left, top = min(o.x, o.x + o.w), min(o.y, o.y + o.h)
        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, abs(o.w) * cw, abs(o.h) * ch)
        prev = self._suppress_write
        self._suppress_write = True
        self.setPos(ox + left * cw, oy + top * ch)
        self._suppress_write = prev
        self.update()

    def sync_from_model(self):
        self._resync()

    def _endpoints_local(self):
        cw, ch, _, _ = self._content()
        o = self.obj
        left, top = min(o.x, o.x + o.w), min(o.y, o.y + o.h)
        p1 = QPointF((o.x - left) * cw, (o.y - top) * ch)
        p2 = QPointF((o.x + o.w - left) * cw, (o.y + o.h - top) * ch)
        return p1, p2

    def _curve_local(self):
        """All path points in item coordinates (ends + Bézier controls)."""
        cw, ch, _, _ = self._content()
        o = self.obj
        left, top = min(o.x, o.x + o.w), min(o.y, o.y + o.h)
        return [QPointF((px - left) * cw, (py - top) * ch)
                for px, py in line_path(o)]

    def _curve_path(self):
        pts = self._curve_local()
        path = QPainterPath(pts[0])
        if len(pts) == 2:
            path.lineTo(pts[1])
        for i in range(1, len(pts) - 2, 3):
            path.cubicTo(pts[i], pts[i + 1], pts[i + 2])
        return path

    def boundingRect(self) -> QRectF:
        r = super().boundingRect()
        if getattr(self.obj, "curve", None):
            m = HANDLE + 1 + max(4.0, self.obj.width_pt * self._font_scale * 4)
            r = r.united(self._curve_path().boundingRect().adjusted(
                -m, -m, m, m))
        return r

    def _end_handles(self):
        p1, p2 = self._endpoints_local()
        h = HANDLE + 1
        return {"P1": QRectF(p1.x() - h, p1.y() - h, 2 * h, 2 * h),
                "P2": QRectF(p2.x() - h, p2.y() - h, 2 * h, 2 * h)}

    def _endpoint_at(self, pos):
        for key, rect in self._end_handles().items():
            if rect.contains(pos):
                return key
        return None

    # -- geometry write-back --------------------------------------
    def _write_geometry(self):
        # Whole-line move: derive end 1 (x, y) from the new bbox top-left,
        # keeping the signed deltas (w, h). Endpoint drags write directly.
        if self._drag_end is not None or getattr(self, "_suppress_write", False):
            return
        cw, ch, ox, oy = self._content()
        o = self.obj
        left = (self.pos().x() - ox) / cw
        top = (self.pos().y() - oy) / ch
        o.x = round(left + (0.0 if o.w >= 0 else -o.w), 4)
        o.y = round(top + (0.0 if o.h >= 0 else -o.h), 4)

    # -- mouse ----------------------------------------------------
    def mousePressEvent(self, event):
        if self._lock_rect().contains(event.pos()):
            self.toggle_lock()
            event.accept()
            return
        if self.isSelected():
            h = self._endpoint_at(event.pos())
            if h is not None:
                self._drag_end = h
                event.accept()
                return
        self._drag_end = None
        super().mousePressEvent(event)

    def key_points(self):
        p1, p2 = self._endpoints_local()
        return [self.mapToScene(p1), self.mapToScene(p2)]

    def mouseMoveEvent(self, event):
        if self._drag_end is None:
            super().mouseMoveEvent(event)
            return
        sp = event.scenePos()
        sc = self.scene()
        if hasattr(sc, "snap_point"):
            sp = sc.snap_point(sp, exclude=self)
        cw, ch, ox, oy = self._content()
        fx = (sp.x() - ox) / cw
        fy = (sp.y() - oy) / ch
        o = self.obj
        if self._drag_end == "P2":
            o.w = round(fx - o.x, 4)
            o.h = round(fy - o.y, 4)
        else:                            # dragging end 1; keep end 2 fixed
            p2x, p2y = o.x + o.w, o.y + o.h
            o.x, o.y = round(fx, 4), round(fy, 4)
            o.w, o.h = round(p2x - o.x, 4), round(p2y - o.y, 4)
        self._resync()
        self.geometryChanged.emit()

    def mouseReleaseEvent(self, event):
        if self._drag_end is not None:
            self._drag_end = None
            self.geometryChanged.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        if self._lock_rect().contains(event.pos()):
            self.setCursor(Qt.PointingHandCursor)
        elif self.isSelected() and self._endpoint_at(event.pos()):
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.ArrowCursor if self._is_locked()
                           else Qt.SizeAllCursor)
        super(BoxItem, self).hoverMoveEvent(event)

    def _arrowhead(self, painter, frm, to, wpx):
        ang = math.atan2(to.y() - frm.y(), to.x() - frm.x())
        size = max(8.0, wpx * 4)
        a1, a2 = ang + math.radians(150), ang - math.radians(150)
        poly = QPolygonF([
            to,
            QPointF(to.x() + size * math.cos(a1), to.y() + size * math.sin(a1)),
            QPointF(to.x() + size * math.cos(a2), to.y() + size * math.sin(a2)),
        ])
        painter.setBrush(QColor(self.obj.color or "#000000"))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(poly)

    def paint(self, painter, option, widget=None):
        obj: SlideLine = self.obj
        p1, p2 = self._endpoints_local()
        wpx = max(1.0, obj.width_pt * self._font_scale)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setOpacity(max(0.0, min(1.0, getattr(obj, "opacity", 1.0))))
        pen = QPen(QColor(obj.color or "#000000"))
        pen.setWidthF(wpx)
        pen.setCapStyle(Qt.RoundCap)
        pen.setStyle(_PEN_STYLE.get(getattr(obj, "style", "solid"),
                                    Qt.SolidLine))
        painter.setPen(pen)
        if getattr(obj, "curve", None):
            pts = self._curve_local()
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self._curve_path())
            # Arrowheads follow the curve's tangent at each end.
            if obj.arrow_end:
                self._arrowhead(painter, pts[-2], pts[-1], wpx)
            if obj.arrow_start:
                self._arrowhead(painter, pts[1], pts[0], wpx)
        else:
            painter.drawLine(p1, p2)
            if obj.arrow_end:
                self._arrowhead(painter, p1, p2, wpx)
            if obj.arrow_start:
                self._arrowhead(painter, p2, p1, wpx)
        painter.restore()
        self._paint_line_chrome(painter)

    def _paint_line_chrome(self, painter):
        """Endpoint handles when selected; lock badge on hover/selection."""
        if not self.isSelected():
            if getattr(self, "_hover", False):
                self._paint_lock(painter)
            return
        painter.save()
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(QPen(QColor(40, 120, 220), 0))
        p1, p2 = self._endpoints_local()
        for p in (p1, p2):
            painter.drawRect(QRectF(p.x() - HANDLE, p.y() - HANDLE,
                                    2 * HANDLE, 2 * HANDLE))
        painter.restore()
        self._paint_lock(painter)


_PEN_STYLE = {"solid": Qt.SolidLine, "dashed": Qt.DashLine,
              "dotted": Qt.DotLine}


def fill_brush(obj, rect, alpha: float = 1.0) -> QBrush:
    """The brush for an object's fill: a linear gradient from ``fill`` to
    ``fill2`` (top→bottom or left→right) when both are set, else the solid
    ``fill`` colour. *alpha* multiplies in the fill opacity."""
    c1 = QColor(obj.fill)
    c1.setAlphaF(max(0.0, min(1.0, alpha)))
    fill2 = getattr(obj, "fill2", "")
    if not fill2:
        return QBrush(c1)
    c2 = QColor(fill2)
    c2.setAlphaF(c1.alphaF())
    if getattr(obj, "gradient", "vertical") == "horizontal":
        g = QLinearGradient(rect.topLeft(), rect.topRight())
    else:
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0.0, c1)
    g.setColorAt(1.0, c2)
    return QBrush(g)


class ShapeBoxItem(BoxItem):
    """Any vector shape (rectangle, ellipse, polygon, arrow, star…) with
    editable fill / outline / corners / rotation."""

    def paint(self, painter, option, widget=None):
        obj: SlideShape = self.obj
        r = self._rect
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setOpacity(max(0.0, min(1.0, getattr(obj, "opacity", 1.0))))
        if obj.rotation:
            c = r.center()
            painter.translate(c)
            painter.rotate(obj.rotation)
            painter.translate(-c)
        if obj.fill:
            painter.setBrush(fill_brush(obj, r))
        else:
            painter.setBrush(Qt.NoBrush)
        if obj.border_color and obj.border_width > 0:
            pen = QPen(QColor(obj.border_color))
            pen.setWidthF(max(1.0, obj.border_width * self._font_scale))
            pen.setStyle(_PEN_STYLE.get(getattr(obj, "style", "solid"),
                                        Qt.SolidLine))
            pen.setJoinStyle(Qt.MiterJoin)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.NoPen)
        painter.drawPath(_shapes.qt_path(effective_shape(obj), r))
        painter.restore()
        self._paint_selection(painter)


def make_item(obj, page_w, page_h, gap=0.0, font_scale=FONT_SCALE) -> BoxItem:
    if isinstance(obj, SlideText):
        return TextBoxItem(obj, page_w, page_h, gap, font_scale)
    if isinstance(obj, SlideVideo):
        return VideoBoxItem(obj, page_w, page_h, gap, font_scale)
    if isinstance(obj, SlideTable):
        return TableBoxItem(obj, page_w, page_h, gap, font_scale)
    if isinstance(obj, SlideLine):
        return LineBoxItem(obj, page_w, page_h, gap, font_scale)
    if isinstance(obj, SlideShape):
        return ShapeBoxItem(obj, page_w, page_h, gap, font_scale)
    return PictureBoxItem(obj, page_w, page_h, gap, font_scale)


class SlideScene(QGraphicsScene):
    def __init__(self, aspect="169"):
        super().__init__()
        self.aspect = aspect
        self.page_color = "#FFFFFF"   # current slide background
        # Optional page backdrop: a rendered image of the page (e.g. the live
        # themed slide) drawn in place of the flat page colour. None = plain.
        self.backdrop = None
        self.gap = 0.0
        self.page_w = scene_width(aspect)
        self.page_h = SCENE_H
        # Drawing aids (toggled from the View menu).
        self.show_grid = False
        self.snap_grid = False
        self.snap_objects = False
        self.grid_frac = 0.025        # grid spacing as a fraction of the page
        self._set_rect()

    def grid_step(self):
        return self.grid_frac * self.page_w, self.grid_frac * self.page_h

    def snap_point(self, pt, exclude=None):
        """Snap a scene point to the grid and/or nearby object key points
        (corners / centres / line ends), whichever is closer. No-op unless a
        snap mode is on."""
        if not (self.snap_grid or self.snap_objects):
            return pt
        x, y = pt.x(), pt.y()
        thr = 9.0
        nx, ny = x, y
        bdx = bdy = thr
        if self.snap_objects:
            for it in self.items():
                if it is exclude or not isinstance(it, BoxItem):
                    continue
                try:
                    kps = it.key_points()
                except RuntimeError:
                    continue
                for kp in kps:
                    if abs(kp.x() - x) < bdx:
                        nx, bdx = kp.x(), abs(kp.x() - x)
                    if abs(kp.y() - y) < bdy:
                        ny, bdy = kp.y(), abs(kp.y() - y)
        if self.snap_grid:
            gx, gy = self.grid_step()
            cx, cy = round(x / gx) * gx, round(y / gy) * gy
            if bdx >= thr and abs(cx - x) < thr:
                nx = cx
            if bdy >= thr and abs(cy - y) < thr:
                ny = cy
        return QPointF(nx, ny)

    def page_rect(self) -> QRectF:
        """The slide page itself (white area), independent of the scene rect
        which extends into a grey pasteboard so objects can be dragged off
        the slide."""
        return QRectF(0, 0, self.page_w, self.page_h)

    def _set_rect(self):
        # Surround the page with a generous pasteboard so a box / tool can be
        # parked outside the slide (it just won't render in the PDF). The view
        # still fits the page, so the pasteboard only appears when you drag
        # something out or zoom away.
        mx, my = 0.6 * self.page_w, 0.6 * self.page_h
        self.setSceneRect(-mx, -my, self.page_w + 2 * mx, self.page_h + 2 * my)

    def set_aspect(self, aspect):
        self.aspect = aspect
        self.page_w = scene_width(aspect)
        self.page_h = SCENE_H
        self._set_rect()

    def set_page(self, page_w, page_h, gap):
        self.page_w = page_w
        self.page_h = page_h
        self.gap = gap
        self._set_rect()

    def drawBackground(self, painter, rect):
        # Fill the whole exposed area (incl. the margins beyond the page)
        # with grey "desk", then lay the white page on top with a soft
        # shadow and a thin edge. Done here — not via the view's
        # backgroundBrush — because setting that brush stops the view from
        # ever calling this, leaving the page unpainted.
        painter.fillRect(rect, QColor("#9aa0a6"))
        r = self.page_rect()
        painter.fillRect(r.translated(7, 7), QColor(0, 0, 0, 45))
        bd = getattr(self, "backdrop", None)
        if bd is not None and not bd.isNull():
            # A pre-rendered image of the themed page sits under the objects.
            painter.fillRect(r, QColor("#FFFFFF"))
            painter.save()
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(r, bd, QRectF(bd.rect()))
            painter.restore()
        else:
            painter.fillRect(r, QColor(self.page_color or "#FFFFFF"))
        if self.show_grid:
            gx, gy = self.grid_step()
            painter.setPen(QPen(QColor(0, 0, 0, 28), 0))
            x = 0.0
            while x <= self.page_w + 0.5:
                painter.drawLine(QPointF(x, 0), QPointF(x, self.page_h))
                x += gx
            y = 0.0
            while y <= self.page_h + 0.5:
                painter.drawLine(QPointF(0, y), QPointF(self.page_w, y))
                y += gy
        painter.setPen(QPen(QColor(150, 150, 150), 0))
        painter.drawRect(r)
        if self.gap > 0:
            # Dashed guide showing the content "safe area".
            g = self.gap
            guide = QRectF(g * self.page_w, g * self.page_h,
                           (1 - 2 * g) * self.page_w, (1 - 2 * g) * self.page_h)
            painter.setPen(QPen(QColor(120, 160, 210), 0, Qt.DashLine))
            painter.drawRect(guide)


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".pdf")


def _dropped_image(mime) -> str | None:
    if mime is not None and mime.hasUrls():
        for url in mime.urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(_IMAGE_EXTS):
                return url.toLocalFile()
    return None


class SlideView(QGraphicsView):
    """Canvas view with mouse-wheel zoom (zoom around the cursor) and
    drag-and-drop of image files. Plain fit-to-window is the default;
    scrolling the wheel switches to free zoom, and fit_to_window() snaps
    back."""

    _MIN = 0.1
    _MAX = 12.0

    imageDropped = Signal(str, QPointF)   # (local path, scene position)
    deleteRequested = Signal()            # Delete pressed with a selection
    contextMenuRequested = Signal(object, object)   # (globalPos, scenePos)
    zoomChanged = Signal()                # zoomed, or fitted to the window

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setAcceptDrops(True)
        self.fit_mode = True

    def mousePressEvent(self, event):
        # Alt+click cycles selection down through overlapping boxes, so a
        # shape hidden under a text box can still be picked (the topmost box
        # otherwise swallows every click).
        if event.button() == Qt.LeftButton \
                and (event.modifiers() & Qt.AltModifier) and self.scene():
            sp = self.mapToScene(event.position().toPoint())
            stack = [it for it in self.scene().items(sp)
                     if isinstance(it, BoxItem)]   # topmost first
            if stack:
                cur = [it for it in stack if it.isSelected()]
                nxt = (stack[(stack.index(cur[0]) + 1) % len(stack)]
                       if cur else stack[0])
                self.scene().clearSelection()
                nxt.setSelected(True)
                event.accept()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        # Delete the selected object — but NOT while editing text: then the
        # inline editor is the scene's focus item and must get Delete itself.
        if event.key() == Qt.Key_Delete and self.scene() \
                and self.scene().selectedItems() \
                and self.scene().focusItem() is None:
            self.deleteRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if _dropped_image(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if _dropped_image(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        path = _dropped_image(event.mimeData())
        if path:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.imageDropped.emit(path, scene_pos)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def contextMenuEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        self.contextMenuRequested.emit(event.globalPos(), scene_pos)
        event.accept()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        scale = self.transform().m11() * factor
        if scale < self._MIN or scale > self._MAX:
            event.accept()
            return
        self.fit_mode = False
        self.scale(factor, factor)
        event.accept()

    def zoom_by(self, factor):
        scale = self.transform().m11() * factor
        if self._MIN <= scale <= self._MAX:
            self.fit_mode = False
            self.scale(factor, factor)
            self.zoomChanged.emit()

    def fit_to_window(self):
        scene = self.scene()
        if scene is not None:
            # Fit the slide page (not the wider pasteboard) so the slide stays
            # the focus; the grey margins appear only on zoom-out / drag-out.
            rect = (scene.page_rect() if hasattr(scene, "page_rect")
                    else scene.sceneRect())
            self.fitInView(rect, Qt.KeepAspectRatio)
            self.fit_mode = True
            self.zoomChanged.emit()


def thumbnail_dpr() -> float:
    """Pixel density for thumbnails: the screen's, and never below 2 — a
    supersampled thumbnail keeps small text readable even on 1x screens."""
    from PySide6.QtGui import QGuiApplication
    screen = QGuiApplication.primaryScreen()
    return max(2.0, screen.devicePixelRatio() if screen else 1.0)


def render_thumbnail(slide: Slide, deck, width_px: int = 160,
                     backdrop: QPixmap | None = None,
                     dpr: float | None = None) -> QPixmap:
    """Render *slide* to a small pixmap for the navigator — reuses the
    same item painting as the live canvas so the thumbnail matches.
    *backdrop* is the slide's themed page, drawn under the objects. The
    pixmap is *width_px* logical pixels wide, rendered at *dpr* (default
    thumbnail_dpr()) so it is sharp on high-resolution screens."""
    pw, ph, fs = page_size_px(deck.aspect, deck.page_w_cm, deck.page_h_cm)
    scene = SlideScene(deck.aspect)
    scene.set_page(pw, ph, deck.gap)
    scene.page_color = slide.bg or "#FFFFFF"
    scene.backdrop = backdrop
    scene.thumbnail = True
    for obj in slide.objects:
        item = make_item(obj, pw, ph, deck.gap, fs)
        item.setSelected(False)
        scene.addItem(item)
    dpr = dpr or thumbnail_dpr()
    height_px = int(width_px * ph / pw)
    pm = QPixmap(int(round(width_px * dpr)), int(round(height_px * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(QColor("#FFFFFF"))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    scene.render(painter, QRectF(0, 0, width_px, height_px), scene.page_rect())
    painter.end()
    return pm
