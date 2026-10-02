"""TeX-like box layout and QPainter rendering for :mod:`mathbox` trees.

Every node becomes a :class:`Box` (width, ascent, descent, drawing ops and
positioned child boxes). Row boxes remember the x position of each caret
gap so the editor widget can hit-test clicks and draw the caret without
knowing anything about the individual structures.

Glyphs come from Latin Modern Math (the font unicode-math uses) out of
tectonic's cache, with Unicode math-alphanumeric codepoints giving true
math italics; matplotlib's STIX fonts are the fallback.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QPainter,
    QPainterPath, QPen, QPixmap,
)

from . import mathbox as mb

INK = QColor("#16181d")
PH_PEN = QColor("#9aa6b6")
PH_ACTIVE = QColor("#2f6fde")
PH_ACTIVE_FILL = QColor("#e8f0ff")

# ------------------------------------------------------------------ fonts

_font_state: dict = {}


def _find_math_font() -> Path | None:
    from .compiler import (_find_tectonic, default_tectonic_cache_dir,
                           query_tectonic_cache_dir)
    roots = [default_tectonic_cache_dir()]
    hit = _glob_font(roots)
    if hit:
        return hit
    tec = _find_tectonic()
    if tec:
        d = query_tectonic_cache_dir(tec)
        if d is not None:
            return _glob_font([d])
    return None


def _glob_font(roots) -> Path | None:
    for root in roots:
        try:
            hits = sorted(Path(root).glob("data/*/latinmodern-math.otf"))
        except OSError:
            hits = []
        if hits:
            return hits[0]
    return None


def _stix_dir() -> Path | None:
    try:
        import matplotlib
    except ImportError:
        return None
    d = Path(os.path.dirname(matplotlib.__file__)) / "mpl-data/fonts/ttf"
    return d if (d / "STIXGeneral.ttf").exists() else None


def font_info() -> dict:
    """{'family', 'unicode_math', 'italic_family'} — loaded once."""
    if _font_state:
        return _font_state
    fam = None
    uni = False
    path = _find_math_font()
    if path is not None:
        fid = QFontDatabase.addApplicationFont(str(path))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams:
            fam, uni = fams[0], True
    if fam is None:
        d = _stix_dir()
        if d is not None:
            for name in ("STIXGeneral.ttf", "STIXGeneralItalic.ttf",
                         "STIXGeneralBol.ttf", "STIXGeneralBolIta.ttf"):
                fid = QFontDatabase.addApplicationFont(str(d / name))
                fams = QFontDatabase.applicationFontFamilies(fid) \
                    if fid >= 0 else []
                if fams and fam is None:
                    fam = fams[0]
    if fam is None:
        fam = "Times New Roman"
    _font_state.update(family=fam, unicode_math=uni)
    return _font_state


_fonts: dict = {}


def qfont(px: float, kind: str = "rm") -> QFont:
    """Math font at *px* pixels. kind: rm | it | bf | bi | mono."""
    key = (round(px * 4) / 4, kind)
    f = _fonts.get(key)
    if f is None:
        if kind == "mono":
            f = QFont("Menlo")
            f.setStyleHint(QFont.Monospace)
        else:
            f = QFont(font_info()["family"])
            f.setItalic(kind in ("it", "bi"))
            f.setBold(kind in ("bf", "bi"))
        f.setPixelSize(max(1, int(round(px))))
        f.setHintingPreference(QFont.PreferNoHinting)
        f.setKerning(True)
        _fonts[key] = f
    return f


_metrics: dict = {}


def glyph_metrics(font: QFont, text: str) -> tuple[float, float, float]:
    """(advance, ink ascent, ink descent, ink right edge) of *text*."""
    key = (font.pixelSize(), font.family(), font.italic(), font.bold(),
           text)
    m = _metrics.get(key)
    if m is None:
        fm = QFontMetricsF(font)
        r = fm.tightBoundingRect(text)
        m = (fm.horizontalAdvance(text), max(0.0, -r.top()),
             max(0.0, r.bottom()), r.right())
        _metrics[key] = m
    return m


# -------------------------------------------------------- letter mapping

def _alpha(ch, upper, lower, exc=None, digits=None):
    if exc and ch in exc:
        return exc[ch]
    if "A" <= ch <= "Z" and upper:
        return chr(upper + ord(ch) - 65)
    if "a" <= ch <= "z" and lower:
        return chr(lower + ord(ch) - 97)
    if "0" <= ch <= "9" and digits:
        return chr(digits + ord(ch) - 48)
    return ch


_VARIANTS = {
    "it": (0x1D434, 0x1D44E, {"h": "ℎ"}, None),
    "bf": (0x1D400, 0x1D41A, None, 0x1D7CE),
    "bi": (0x1D468, 0x1D482, None, 0x1D7CE),
    "bb": (0x1D538, 0x1D552, {"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ",
                              "Q": "ℚ", "R": "ℝ", "Z": "ℤ"}, 0x1D7D8),
    "cal": (0x1D49C, 0x1D4B6, {"B": "ℬ", "E": "ℰ", "F": "ℱ", "H": "ℋ",
                               "I": "ℐ", "L": "ℒ", "M": "ℳ", "R": "ℛ",
                               "e": "ℯ", "g": "ℊ", "o": "ℴ"}, None),
    "frak": (0x1D504, 0x1D51E, {"C": "ℭ", "H": "ℌ", "I": "ℑ", "R": "ℜ",
                                "Z": "ℨ"}, None),
    "sf": (0x1D5A0, 0x1D5BA, None, 0x1D7E2),
    "tt": (0x1D670, 0x1D68A, None, 0x1D7F6),
}
_STYLE_VARIANT = {"mathbf": "bf", "mathbb": "bb", "mathcal": "cal",
                  "mathscr": "cal", "mathfrak": "frak", "mathsf": "sf",
                  "mathtt": "tt", "boldsymbol": "bi", "bm": "bi",
                  "mathit": "it", "mathrm": "rm", "text": "text"}
_GREEK_IT = {"ϵ": 0x1D716, "ϑ": 0x1D717, "ϰ": 0x1D718, "ϕ": 0x1D719,
             "ϱ": 0x1D71A, "ϖ": 0x1D71B, "∂": 0x1D715}


def styled_char(ch: str, variant: str | None, italic_default: bool):
    """(text, font kind) for one character under a style variant."""
    uni = font_info()["unicode_math"]
    v = variant
    if v in (None, "it"):
        want_it = italic_default if v is None else ch.isalpha()
        if not want_it:
            return ch, "rm"
        if not uni:
            return ch, "it"
        if ch.isascii() and ch.isalpha():
            return _alpha(ch, *_VARIANTS["it"]), "rm"
        if "α" <= ch <= "ω":
            return chr(0x1D6FC + ord(ch) - ord("α")), "rm"
        if ch in _GREEK_IT:
            return chr(_GREEK_IT[ch]), "rm"
        return ch, "rm"
    if v in ("rm", "text"):
        return ch, "rm"
    if not uni:
        return ch, {"bf": "bf", "bi": "bi"}.get(v, "rm")
    return _alpha(ch, *_VARIANTS[v]), "rm"


# ------------------------------------------------------------------ boxes


class Box:
    __slots__ = ("w", "asc", "desc", "ops", "kids", "row", "gaps", "em",
                 "italic", "node", "charlike", "ink_r")

    def __init__(self, w=0.0, asc=0.0, desc=0.0):
        self.w, self.asc, self.desc = w, asc, desc
        self.ops: list = []
        self.kids: list = []      # (dx, dy, Box); dy positive = down
        self.row = None
        self.gaps: list[float] = []
        self.em = 0.0
        self.italic = False
        self.node = None
        self.charlike = False
        self.ink_r = None

    def add(self, dx, dy, box: "Box") -> None:
        self.kids.append((dx, dy, box))


class St:
    """Math style: level 0=display 1=text 2=script 3=scriptscript."""
    __slots__ = ("level", "variant", "base")

    def __init__(self, base, level=0, variant=None):
        self.base, self.level, self.variant = base, level, variant

    @property
    def em(self) -> float:
        return self.base * (1.0, 1.0, 0.7, 0.5)[self.level]

    def sup(self) -> "St":
        return St(self.base, 2 if self.level < 2 else 3, self.variant)

    def frac(self) -> "St":
        return St(self.base, min(self.level + 1, 3) if self.level else 1,
                  self.variant)

    def with_level(self, lv) -> "St":
        return St(self.base, lv, self.variant)

    def with_variant(self, v) -> "St":
        return St(self.base, self.level, v)


_SP = {
    ("ord", "op"): 3, ("ord", "bin"): 4, ("ord", "rel"): 5,
    ("ord", "inner"): 3,
    ("op", "ord"): 3, ("op", "op"): 3, ("op", "rel"): 5, ("op", "inner"): 3,
    ("bin", "ord"): 4, ("bin", "op"): 4, ("bin", "open"): 4,
    ("bin", "inner"): 4,
    ("rel", "ord"): 5, ("rel", "op"): 5, ("rel", "open"): 5,
    ("rel", "inner"): 5,
    ("close", "op"): 3, ("close", "bin"): 4, ("close", "rel"): 5,
    ("close", "inner"): 3,
    ("punct", "ord"): 3, ("punct", "op"): 3, ("punct", "rel"): 3,
    ("punct", "open"): 3, ("punct", "close"): 3, ("punct", "punct"): 3,
    ("punct", "inner"): 3,
    ("inner", "ord"): 3, ("inner", "op"): 3, ("inner", "bin"): 4,
    ("inner", "rel"): 5, ("inner", "open"): 3, ("inner", "punct"): 3,
    ("inner", "inner"): 3,
}
_SP_SCRIPT = {("ord", "op"), ("op", "ord"), ("op", "op"), ("close", "op"),
              ("inner", "op")}

_ATOM_GLYPH = {"-": "−", "*": "∗", "'": "′"}


def _left_cls(n) -> str | None:
    if isinstance(n, (mb.Space, mb.Scripts)):
        return None
    if isinstance(n, mb.Delim):
        return "open"
    if isinstance(n, (mb.Placeholder, mb.CmdInput, mb.Raw)):
        return "ord"
    return n.cls


def _right_cls(n) -> str | None:
    if isinstance(n, mb.Space):
        return None
    if isinstance(n, mb.Delim):
        return "close"
    if isinstance(n, (mb.Placeholder, mb.CmdInput, mb.Raw)):
        return "ord"
    return n.cls


class Layout:
    """Lays out a row at a base pixel size."""

    def __init__(self, base_px: float = 32.0, display: bool = True):
        self.base = base_px
        self.display = display

    # ---------------------------------------------------------- basics
    def layout(self, row: mb.Row) -> Box:
        return self.row(row, St(self.base, 0 if self.display else 1))

    def glyph(self, text: str, st: St, kind="rm", scale=1.0) -> Box:
        f = qfont(st.em * scale, kind)
        adv, a, d, right = glyph_metrics(f, text)
        b = Box(adv, a, d)
        b.ink_r = right
        b.ops.append(("t", 0.0, 0.0, f, text))
        b.em = st.em
        b.charlike = True
        return b

    def ph_box(self, st: St, ref) -> Box:
        em = st.em
        b = Box(0.56 * em, 0.66 * em, 0.08 * em)
        b.ops.append(("ph", 0.03 * em, -0.66 * em, 0.5 * em, 0.74 * em,
                      ref))
        b.em = em
        return b

    # ------------------------------------------------------------ rows
    def row(self, row: mb.Row, st: St, lead: str | None = None) -> Box:
        em = st.em
        if not row.children:
            b = self.ph_box(st, row)
            b.row = row
            b.gaps = [b.w / 2]
            return b
        boxes = []
        prev_box = None
        for n in row.children:
            if isinstance(n, mb.Scripts):
                bx = self.scripts(n, st, prev_box)
            else:
                bx = self.node(n, st)
            bx.node = n
            boxes.append(bx)
            prev_box = bx
        # TeX spacing between math classes; a binary operator with
        # nothing to bind on its left (or right) acts as an ordinary.
        kids = row.children
        n_k = len(kids)
        lefts = [_left_cls(k) for k in kids]
        b = Box()
        b.row = row
        b.em = em
        x = 0.0
        gaps = [0.0]
        prev_r = lead
        for i, bx in enumerate(boxes):
            k = kids[i]
            cur = lefts[i]
            if cur == "bin":
                nxt = next((lefts[j] for j in range(i + 1, n_k)
                            if lefts[j] is not None), None)
                if prev_r in (None, "bin", "op", "rel", "open", "punct") \
                        or nxt in (None, "rel", "close", "punct"):
                    cur = "ord"
            sp = 0.0
            if cur is not None and prev_r is not None:
                mu = _SP.get((prev_r, cur), 0)
                if st.level >= 2 and (prev_r, cur) not in _SP_SCRIPT:
                    mu = 0
                sp = mu * em / 18.0
            if i > 0:
                gaps.append(x + sp / 2)
            x += sp
            b.add(x, 0.0, bx)
            x += bx.w
            b.asc = max(b.asc, bx.asc)
            b.desc = max(b.desc, bx.desc)
            if isinstance(k, mb.Space):
                prev_r = None
            elif not isinstance(k, mb.Scripts):
                prev_r = cur if cur in ("ord", "bin") and \
                    lefts[i] == "bin" else _right_cls(k)
        gaps.append(x)
        b.gaps = gaps
        b.w = x
        return b

    # ----------------------------------------------------------- nodes
    def node(self, n, st: St) -> Box:
        em = st.em
        if isinstance(n, mb.Atom):
            return self.atom(n, st)
        if isinstance(n, mb.Symbol):
            g = n.glyph
            italic = g in mb.GREEK_LOWER_GLYPHS or g == "∂"
            if n.cmd in ("{", "}", "|", "%", "#", "&", "$", "_"):
                italic = False
            t, kind = styled_char(g, st.variant if st.variant not in
                                  ("bb", "cal", "frak", "sf", "tt")
                                  else "rm", italic) if len(g) == 1 \
                else (g, "rm")
            b = self.glyph(t, st, kind)
            b.italic = italic
            return b
        if isinstance(n, mb.Func):
            return self.word(n.name, st)
        if isinstance(n, mb.Placeholder):
            return self.ph_box(st, n)
        if isinstance(n, mb.Space):
            return Box(n.mu * em / 18.0, 0, 0)
        if isinstance(n, mb.Raw):
            return self.chip(n.latex, st, "raw")
        if isinstance(n, mb.CmdInput):
            return self.chip("\\" + n.text, st, "cmd")
        if isinstance(n, mb.Frac):
            return self.frac(n, st)
        if isinstance(n, mb.Sqrt):
            return self.sqrt(n, st)
        if isinstance(n, mb.BigOp):
            return self.bigop(n, st)
        if isinstance(n, mb.Delim):
            body = self.row(n.body, st)
            return self.wrap_delims(body, mb.DELIMS.get(n.left, n.left),
                                    mb.DELIMS.get(n.right, n.right), st)
        if isinstance(n, mb.Matrix):
            return self.matrix(n, st)
        if isinstance(n, mb.Accent):
            return self.accent(n, st)
        if isinstance(n, mb.Styled):
            return self.row(n.body, st.with_variant(
                _STYLE_VARIANT.get(n.cmd, "rm")))
        if isinstance(n, mb.Text):
            return self.row(n.body, st.with_variant("text"))
        if isinstance(n, mb.Group):
            return self.row(n.body, st)
        if isinstance(n, mb.Scripts):
            return self.scripts(n, st, None)
        return self.chip("?", st, "raw")

    def atom(self, n: mb.Atom, st: St) -> Box:
        ch = n.char
        if n.kind == "text" or st.variant == "text":
            if ch == " ":
                return Box(0.333 * st.em, 0, 0)
            return self.glyph(ch, st, "rm")
        if ch in ("′", "'"):
            sub = st.sup()
            g = self.glyph("′", sub)
            b = Box(g.w + 0.02 * st.em, g.asc + 0.38 * st.em, 0)
            b.add(0.0, -0.38 * st.em, g)
            return b
        ch = _ATOM_GLYPH.get(ch, ch)
        italic = ch.isascii() and ch.isalpha()
        t, kind = styled_char(ch, st.variant, italic)
        b = self.glyph(t, st, kind)
        b.italic = italic and st.variant in (None, "it", "bi")
        return b

    def word(self, text: str, st: St) -> Box:
        b = self.glyph(text, st, "rm")
        b.charlike = True
        return b

    def chip(self, text: str, st: St, kind: str) -> Box:
        em = st.em
        f = qfont(0.5 * em, "mono")
        fm = QFontMetricsF(f)
        w = fm.horizontalAdvance(text) + 0.36 * em
        b = Box(w + 0.08 * em, 0.68 * em, 0.2 * em)
        b.ops.append(("chip", 0.04 * em, -0.68 * em, w, 0.88 * em, text, f,
                      kind))
        return b

    # -------------------------------------------------------- fraction
    def frac(self, n: mb.Frac, st: St) -> Box:
        em = st.em
        if n.cmd in ("dfrac", "cfrac", "dbinom"):
            inner = St(st.base, 1, st.variant)
            outer_disp = True
        elif n.cmd in ("tfrac", "tbinom"):
            inner = St(st.base, 2, st.variant)
            outer_disp = False
        else:
            inner = st.frac()
            outer_disp = st.level == 0
        num = self.row(n.num, inner)
        den = self.row(n.den, inner)
        t = max(1.0, 0.04 * em)
        axis = 0.25 * em
        binom = "binom" in n.cmd
        clr = (3 * t if outer_disp else t) if not binom else \
            (7 * t if outer_disp else 3 * t)
        u = max(0.677 * em if outer_disp else 0.394 * em,
                axis + t / 2 + clr + num.desc)
        v = max(0.686 * em if outer_disp else 0.345 * em,
                den.asc + clr + t / 2 - axis)
        if binom:
            u = max(u, axis + clr / 2 + num.desc)
            v = max(v, den.asc + clr / 2 - axis)
        m = 0.08 * em
        inner_w = max(num.w, den.w) + 0.16 * em
        b = Box(inner_w + 2 * m, u + num.asc, v + den.desc)
        b.add(m + (inner_w - num.w) / 2, -u, num)
        b.add(m + (inner_w - den.w) / 2, v, den)
        if not binom:
            b.ops.append(("rule", m, -axis - t / 2, inner_w, t))
            return b
        return self.wrap_delims(b, "(", ")", st)

    # ------------------------------------------------------------ root
    def sqrt(self, n: mb.Sqrt, st: St) -> Box:
        em = st.em
        body = self.row(n.body, st)
        t = max(1.0, 0.045 * em)
        gap = t + (0.18 * em if st.level == 0 else 0.1 * em)
        top = -(max(body.asc, 0.62 * em) + gap + t)
        bot = max(body.desc, 0.05 * em) + 0.08 * em
        H = bot - top
        sw = min(0.52 * em + 0.08 * H, 1.0 * em)
        ix = 0.0
        idx_box = None
        if n.index is not None:
            idx_box = self.row(n.index, St(st.base, 3, st.variant))
            ix = max(0.0, idx_box.w - 0.5 * sw)
        b = Box()
        x0 = ix
        mid = bot - min(0.55 * em, H * 0.46)
        p = QPainterPath()
        p.moveTo(x0 + 0.02 * em, mid + 0.06 * em)
        p.lineTo(x0 + 0.16 * sw, mid - 0.02 * em)
        p.lineTo(x0 + 0.45 * sw, bot)
        p.lineTo(x0 + sw, top + t / 2)
        p.lineTo(x0 + sw + body.w + 0.1 * em, top + t / 2)
        b.ops.append(("stroke", p, t))
        thick = QPainterPath()
        thick.moveTo(x0 + 0.16 * sw, mid - 0.02 * em)
        thick.lineTo(x0 + 0.45 * sw, bot)
        b.ops.append(("stroke", thick, 2.3 * t))
        b.add(x0 + sw + 0.04 * em, 0.0, body)
        b.w = x0 + sw + body.w + 0.14 * em
        b.asc = -top
        b.desc = bot
        if idx_box is not None:
            iy = mid - 0.12 * em - idx_box.desc
            b.add(max(0.0, x0 + 0.5 * sw - idx_box.w), iy, idx_box)
            b.asc = max(b.asc, -iy + idx_box.asc)
        return b

    # --------------------------------------------------------- scripts
    def scripts(self, n: mb.Scripts, st: St, base: Box | None) -> Box:
        em = st.em
        sst = st.sup()
        sup = self.row(n.sup, sst) if n.sup is not None else None
        sub = self.row(n.sub, sst) if n.sub is not None else None
        char = base is None or base.charlike
        b_asc = base.asc if base is not None else 0.45 * em
        b_desc = base.desc if base is not None else 0.0
        t = max(1.0, 0.04 * em)
        u = v = 0.0
        if sup is not None:
            u = max(0.413 * em if st.level == 0 else 0.363 * em,
                    sup.desc + 0.25 * 0.43 * em)
            if not char:
                u = max(u, b_asc - 0.25 * em)
        if sub is not None:
            v = max(0.15 * em, sub.asc - 0.8 * 0.43 * em)
            if not char:
                v = max(v, b_desc + 0.05 * em)
        if sup is not None and sub is not None:
            v = max(v, 0.247 * em)
            clash = (u - sup.desc) - (sub.asc - v)
            if clash < 4 * t:
                v += 4 * t - clash
        # Tuck scripts against the ink of a single glyph rather than its
        # advance, which in the math italics carries generous bearings.
        ic = sub_x = 0.0
        if base is not None and base.ink_r is not None:
            ic = min(0.0, base.ink_r - base.w) + (0.04 * em if base.italic
                                                  else 0.02 * em)
            sub_x = min(0.0, base.ink_r - base.w) * 0.6
        b = Box()
        w = 0.0
        if sup is not None:
            b.add(ic, -u, sup)
            w = max(w, ic + sup.w)
            b.asc = max(b.asc, u + sup.asc)
            b.desc = max(b.desc, sup.desc - u)
        if sub is not None:
            b.add(sub_x, v, sub)
            w = max(w, sub_x + sub.w)
            b.desc = max(b.desc, v + sub.desc)
            b.asc = max(b.asc, sub.asc - v)
        b.w = w + 0.05 * em
        return b

    # ------------------------------------------------------ big operator
    def bigop(self, n: mb.BigOp, st: St) -> Box:
        em = st.em
        glyph = mb.BIGOPS.get(n.op, "")
        integral = n.op in mb.INTEGRALS
        disp = st.level == 0
        sst = st.sup()
        up = self.row(n.upper, sst) if n.upper is not None else None
        lo = self.row(n.lower, sst) if n.lower is not None else None
        axis = 0.25 * em
        if glyph:
            scale = (2.0 if integral else 1.42) if disp else \
                (1.28 if integral else 1.06)
            g = self.glyph(glyph, st, "rm", scale)
            # centre the operator on the math axis
            shift = (g.asc - g.desc) / 2 - axis
            op = Box(g.w, g.asc - shift, g.desc + shift)
            op.add(0.0, shift, g)
        else:
            label = {"lim": "lim", "liminf": "lim inf",
                     "limsup": "lim sup"}[n.op]
            op = self.word(label, st)
        limits = disp and not integral
        b = Box()
        if limits or (not glyph and disp):
            w = max(op.w, up.w if up else 0, lo.w if lo else 0)
            ox = (w - op.w) / 2
            b.add(ox, 0.0, op)
            b.asc, b.desc = op.asc, op.desc
            if up is not None:
                y = -op.asc - 0.14 * em - up.desc
                b.add((w - up.w) / 2, y, up)
                b.asc = -y + up.asc
            if lo is not None:
                y = op.desc + 0.14 * em + lo.asc
                b.add((w - lo.w) / 2, y, lo)
                b.desc = y + lo.desc
            b.w = w
            return b
        b.add(0.0, 0.0, op)
        b.asc, b.desc = op.asc, op.desc
        w = op.w
        if integral and glyph:
            kern = 0.3 * em * (2.0 if disp else 1.1)
            if up is not None:
                y = -op.asc + up.asc * 0.95
                b.add(op.w, y, up)
                w = max(w, op.w + up.w)
                b.asc = max(b.asc, -y + up.asc)
            if lo is not None:
                y = op.desc - lo.desc * 0.4
                x = max(0.0, op.w - kern)
                b.add(x, y, lo)
                w = max(w, x + lo.w)
                b.desc = max(b.desc, y + lo.desc)
            b.w = w + 0.08 * em
            return b
        sc = mb.Scripts(n.lower, n.upper)
        s = self.scripts(sc, st, op)
        b.add(op.w, 0.0, s)
        b.asc = max(b.asc, s.asc)
        b.desc = max(b.desc, s.desc)
        b.w = op.w + s.w
        return b

    # --------------------------------------------------------- delimiters
    def wrap_delims(self, body: Box, left: str, right: str, st: St) -> Box:
        em = st.em
        axis = 0.25 * em
        delta = max(body.asc - axis, body.desc + axis)
        H = max(2 * delta * 0.901, 2 * delta - 0.5 * em)
        b = Box()
        x = 0.0
        lb = self.delim(left, H, st)
        rb = self.delim(right, H, st)
        b.add(x, 0.0, lb)
        x += lb.w
        b.add(x, 0.0, body)
        x += body.w
        b.add(x, 0.0, rb)
        b.w = x + rb.w
        b.asc = max(lb.asc, rb.asc, body.asc)
        b.desc = max(lb.desc, rb.desc, body.desc)
        return b

    def delim(self, ch: str, H: float, st: St) -> Box:
        em = st.em
        if not ch:
            return Box(0.1 * em, 0, 0)
        g = self.glyph(ch, st, "rm")
        natural = g.asc + g.desc
        if H <= natural * 1.08 or ch not in _DRAWABLE:
            return g
        axis = 0.25 * em
        h = H / 2
        top, bot = -axis - h, -axis + h
        return _draw_delim(ch, top, bot, em)

    # ---------------------------------------------------------- matrix
    def matrix(self, n: mb.Matrix, st: St) -> Box:
        em = st.em
        env = n.env.rstrip("*")
        display_env = env in ("align", "gather", "equation", "multline",
                              "aligned", "gathered", "split")
        cst = St(st.base, 0 if display_env else max(st.level, 1),
                 st.variant)
        if env == "smallmatrix":
            cst = St(st.base, 2, st.variant)
        # In align-like environments the right-hand column continues the
        # left one ("x &= 1"), so its leading relation keeps its spacing.
        align_like = env in ("align", "aligned", "split")
        grid = [[self.row(c, cst, "ord" if align_like and j % 2 else None)
                 for j, c in enumerate(r)] for r in n.rows]
        ncol = max((len(r) for r in grid), default=0)
        colw = [0.0] * ncol
        for r in grid:
            for j, c in enumerate(r):
                colw[j] = max(colw[j], c.w)
        if env in ("align", "aligned", "split"):
            aligns = ["r" if j % 2 == 0 else "l" for j in range(ncol)]
            gaps = [0.0 if j % 2 == 0 else 1.6 * em
                    for j in range(ncol - 1)]
        elif env == "cases":
            aligns = ["l"] * ncol
            gaps = [1.0 * em] * (ncol - 1)
        else:
            aligns = ["c"] * ncol
            gaps = [(0.6 if env == "smallmatrix" else 1.0) * em] * \
                (ncol - 1)
        jot = 0.3 * em if display_env else 0.0
        rows_geo = []
        y = 0.0
        min_a, min_d = 0.72 * cst.em, 0.3 * cst.em
        for i, r in enumerate(grid):
            a = max([min_a] + [c.asc for c in r])
            d = max([min_d] + [c.desc for c in r])
            if i:
                y += jot + a
            else:
                y = a
            rows_geo.append(y)
            y += d
        total = y
        inner = Box()
        for i, r in enumerate(grid):
            x = 0.0
            for j in range(ncol):
                c = r[j] if j < len(r) else None
                if c is not None:
                    al = aligns[j]
                    off = 0.0 if al == "l" else (colw[j] - c.w) if al == "r" \
                        else (colw[j] - c.w) / 2
                    inner.add(x + off, rows_geo[i], c)
                x += colw[j] + (gaps[j] if j < ncol - 1 else 0.0)
        inner.w = sum(colw) + sum(gaps)
        axis = 0.25 * em
        shift = -axis - total / 2
        body = Box(inner.w + 0.2 * em, -shift, total + shift)
        body.add(0.1 * em, shift, inner)
        pairs = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"),
                 "Bmatrix": ("{", "}"), "vmatrix": ("|", "|"),
                 "Vmatrix": ("‖", "‖"), "cases": ("{", "")}
        if env in pairs:
            l, r = pairs[env]
            return self.wrap_delims(body, l, r, st)
        return body

    # ---------------------------------------------------------- accents
    def accent(self, n: mb.Accent, st: St) -> Box:
        em = st.em
        body = self.row(n.body, st)
        single = len(n.body.children) == 1 and body.kids and \
            body.kids[0][2].italic
        skew = 0.08 * em if single else 0.0
        t = max(1.0, 0.045 * em)
        top = -max(body.asc, 0.45 * em) - 0.1 * em
        cx = body.w / 2 + skew
        cmd = n.cmd
        b = Box(body.w, 0, body.desc)
        b.add(0.0, 0.0, body)
        wide = cmd in ("widehat", "widetilde", "overline",
                       "overrightarrow", "underline")
        aw = body.w if wide else min(max(0.32 * em, body.w * 0.55),
                                     0.5 * em)
        x0 = (body.w - aw) / 2 + (skew if not wide else 0.0)
        acc_h = 0.18 * em
        p = QPainterPath()
        kind = "stroke"
        if cmd in ("hat", "widehat", "check"):
            h = acc_h * (1.0 if cmd != "widehat" else 1.2)
            if cmd == "check":
                p.moveTo(x0, top - h)
                p.lineTo(x0 + aw / 2, top)
                p.lineTo(x0 + aw, top - h)
            else:
                p.moveTo(x0, top)
                p.lineTo(x0 + aw / 2, top - h)
                p.lineTo(x0 + aw, top)
            b.asc = -top + h + t
        elif cmd in ("bar", "overline"):
            if cmd == "bar":
                p.moveTo(x0, top - 0.05 * em)
                p.lineTo(x0 + aw, top - 0.05 * em)
            else:
                p.moveTo(0.0, top)
                p.lineTo(body.w, top)
            b.asc = -top + 0.05 * em + t
        elif cmd == "underline":
            y = body.desc + 0.1 * em
            p.moveTo(0.0, y)
            p.lineTo(body.w, y)
            b.asc = body.asc
            b.desc = y + t
        elif cmd in ("vec", "overrightarrow"):
            y = top - 0.08 * em
            w = aw if cmd == "vec" else body.w
            xs = x0 if cmd == "vec" else 0.0
            p.moveTo(xs, y)
            p.lineTo(xs + w, y)
            p.moveTo(xs + w - 0.12 * em, y - 0.08 * em)
            p.lineTo(xs + w, y)
            p.lineTo(xs + w - 0.12 * em, y + 0.08 * em)
            b.asc = -y + 0.09 * em + t
        elif cmd in ("tilde", "widetilde"):
            y = top - 0.07 * em
            h = 0.06 * em
            p.moveTo(x0, y + h)
            p.cubicTo(x0 + aw * 0.3, y - 2 * h, x0 + aw * 0.7, y + 2 * h,
                      x0 + aw, y - h)
            b.asc = -y + 2 * h + t
        elif cmd in ("dot", "ddot", "mathring"):
            r = 0.05 * em
            y = top - 0.07 * em
            kind = "fill"
            if cmd == "dot":
                p.addEllipse(QPointF(cx, y), r, r)
            elif cmd == "ddot":
                p.addEllipse(QPointF(cx - 0.12 * em, y), r, r)
                p.addEllipse(QPointF(cx + 0.12 * em, y), r, r)
            else:
                kind = "stroke"
                p.addEllipse(QPointF(cx, y - 0.02 * em), 0.07 * em,
                             0.07 * em)
            b.asc = -y + 0.1 * em
        elif cmd in ("acute", "grave"):
            y = top
            if cmd == "acute":
                p.moveTo(cx - 0.04 * em, y)
                p.lineTo(cx + 0.1 * em, y - 0.16 * em)
            else:
                p.moveTo(cx + 0.04 * em, y)
                p.lineTo(cx - 0.1 * em, y - 0.16 * em)
            b.asc = -y + 0.17 * em
        elif cmd == "breve":
            y = top - 0.02 * em
            p.moveTo(x0, y - 0.14 * em)
            p.quadTo(cx, y + 0.06 * em, x0 + aw, y - 0.14 * em)
            b.asc = -y + 0.16 * em
        b.ops.append((kind, p, t))
        b.asc = max(b.asc, body.asc)
        return b


_DRAWABLE = set("()[]{}|‖⟨⟩⌊⌋⌈⌉/")


def _draw_delim(ch: str, top: float, bot: float, em: float) -> Box:
    H = bot - top
    mid = (top + bot) / 2
    b = Box()
    b.asc, b.desc = -top, bot
    t = max(1.0, 0.05 * em)
    p = QPainterPath()
    side = 0.09 * em
    if ch in "()":
        w = min(0.3 * em + 0.06 * H, 0.62 * em)
        tm = 0.075 * em + 0.012 * H
        te = 0.025 * em
        xo, xi = side, side + w          # outer bulge x, end x
        k = H * 0.02
        if ch == "(":
            c = xi - (xi - xo) / 0.75
            p.moveTo(xi, top)
            p.cubicTo(c, top + H * 0.28 + k, c, bot - H * 0.28 - k, xi, bot)
            c2 = xi - (xi - (xo + tm)) / 0.75
            p.lineTo(xi + te, bot - te)
            p.cubicTo(c2 + te, bot - H * 0.3, c2 + te, top + H * 0.3,
                      xi + te, top + te)
            p.closeSubpath()
        else:
            xo, xi = side + w + te, side
            c = xi + (xo - xi) / 0.75
            p.moveTo(xi + te, top)
            p.cubicTo(c + te, top + H * 0.28 + k, c + te,
                      bot - H * 0.28 - k, xi + te, bot)
            c2 = xi + ((xo - tm) - xi) / 0.75
            p.lineTo(xi, bot - te)
            p.cubicTo(c2, bot - H * 0.3, c2, top + H * 0.3, xi, top + te)
            p.closeSubpath()
        b.ops.append(("fill", p, 0))
        b.w = w + te + 2 * side
        return b
    if ch in "[]⌊⌋⌈⌉":
        w = 0.3 * em
        stem = 0.05 * em
        bar = 0.04 * em
        left = ch in "[⌊⌈"
        x = side if left else side + w - stem
        p.addRect(QRectF(x, top, stem, H))
        tops = ch in "[]⌈⌉"
        bots = ch in "[]⌊⌋"
        hx = side if left else side
        if tops:
            p.addRect(QRectF(hx, top, w, bar))
        if bots:
            p.addRect(QRectF(hx, bot - bar, w, bar))
        b.ops.append(("fill", p, 0))
        b.w = w + 2 * side
        return b
    if ch in "{}":
        w = 0.42 * em
        r = min(0.2 * em, H / 5)
        xm = side + w / 2
        xl, xr = side, side + w
        if ch == "}":
            xl, xr = xr, xl
        p.moveTo(xr, top)
        p.quadTo(xm, top, xm, top + r)
        p.lineTo(xm, mid - r)
        p.quadTo(xm, mid, xl, mid)
        p.quadTo(xm, mid, xm, mid + r)
        p.lineTo(xm, bot - r)
        p.quadTo(xm, bot, xr, bot)
        b.ops.append(("stroke", p, 0.06 * em))
        b.w = w + 2 * side
        return b
    if ch in "|‖":
        xs = [side + 0.03 * em] if ch == "|" else \
            [side + 0.03 * em, side + 0.17 * em]
        for x in xs:
            p.moveTo(x, top)
            p.lineTo(x, bot)
        b.ops.append(("stroke", p, 0.045 * em))
        b.w = xs[-1] + 0.03 * em + side
        return b
    if ch in "⟨⟩":
        w = min(0.25 * em + 0.08 * H, 0.55 * em)
        if ch == "⟨":
            p.moveTo(side + w, top)
            p.lineTo(side, mid)
            p.lineTo(side + w, bot)
        else:
            p.moveTo(side, top)
            p.lineTo(side + w, mid)
            p.lineTo(side, bot)
        b.ops.append(("stroke", p, 0.045 * em))
        b.w = w + 2 * side
        return b
    w = 0.12 * H
    p.moveTo(side + w, top)
    p.lineTo(side, bot)
    b.ops.append(("stroke", p, t))
    b.w = w + 2 * side
    return b


# ------------------------------------------------------------ geometry

class RowGeom:
    __slots__ = ("row", "x", "y", "w", "asc", "desc", "gaps", "em")

    def __init__(self, row, x, y, box: Box):
        self.row = row
        self.x, self.y = x, y
        self.w, self.asc, self.desc = box.w, box.asc, box.desc
        self.gaps = [x + g for g in box.gaps]
        self.em = box.em

    def caret_span(self) -> tuple[float, float]:
        return (self.y - max(self.asc, 0.72 * self.em),
                self.y + max(self.desc, 0.22 * self.em))

    def rect(self) -> QRectF:
        a, d = self.caret_span()
        return QRectF(self.x, a, max(self.w, 1.0), d - a)


def collect_rows(box: Box, x=0.0, y=0.0, out=None) -> dict:
    """id(row) -> RowGeom for every row box, in absolute coordinates."""
    if out is None:
        out = {}
    if box.row is not None:
        out[id(box.row)] = RowGeom(box.row, x, y, box)
    for dx, dy, k in box.kids:
        collect_rows(k, x + dx, y + dy, out)
    return out


def collect_nodes(box: Box, x=0.0, y=0.0, out=None) -> dict:
    """id(node) -> QRectF of that node's box."""
    if out is None:
        out = {}
    if box.node is not None:
        out[id(box.node)] = QRectF(x, y - box.asc, box.w,
                                   box.asc + box.desc)
    for dx, dy, k in box.kids:
        collect_nodes(k, x + dx, y + dy, out)
    return out


# ------------------------------------------------------------ painting

class PaintCtx:
    def __init__(self, active=None, ink: QColor = INK,
                 show_placeholders=True):
        self.active = active          # Row or Placeholder under the caret
        self.ink = ink
        self.show_placeholders = show_placeholders


def paint(p: QPainter, box: Box, x: float, y: float,
          ctx: PaintCtx | None = None) -> None:
    ctx = ctx or PaintCtx()
    _paint(p, box, x, y, ctx)


def _paint(p: QPainter, box: Box, x: float, y: float, ctx: PaintCtx):
    for op in box.ops:
        kind = op[0]
        if kind == "t":
            _, dx, dy, f, text = op
            p.setFont(f)
            p.setPen(ctx.ink)
            p.drawText(QPointF(x + dx, y + dy), text)
        elif kind == "rule":
            _, dx, dy, w, h = op
            p.fillRect(QRectF(x + dx, y + dy, w, h), ctx.ink)
        elif kind in ("stroke", "fill"):
            _, path, width = op
            p.save()
            p.translate(x, y)
            if kind == "fill":
                p.setPen(Qt.NoPen)
                p.setBrush(ctx.ink)
            else:
                pen = QPen(ctx.ink, width)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            p.restore()
        elif kind == "ph":
            if not ctx.show_placeholders:
                continue
            _, dx, dy, w, h, ref = op
            active = ref is ctx.active
            r = QRectF(x + dx, y + dy, w, h)
            p.save()
            if active:
                p.fillRect(r, PH_ACTIVE_FILL)
            pen = QPen(PH_ACTIVE if active else PH_PEN,
                       max(1.0, h / 30))
            pen.setStyle(Qt.CustomDashLine)
            pen.setDashPattern([2.0, 2.0])
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            p.restore()
        elif kind == "chip":
            _, dx, dy, w, h, text, f, ck = op
            r = QRectF(x + dx, y + dy, w, h)
            p.save()
            if ck == "cmd":
                p.setBrush(QColor("#fff6dc"))
                p.setPen(QPen(QColor("#e2b54a"), 1))
                tc = QColor("#7a5300")
            else:
                p.setBrush(QColor("#eef1f5"))
                p.setPen(QPen(QColor("#c9d0da"), 1))
                tc = QColor("#4a5566")
            p.drawRoundedRect(r, h * 0.18, h * 0.18)
            p.setFont(f)
            p.setPen(tc)
            p.drawText(r, Qt.AlignCenter, text)
            p.restore()
    for dx, dy, k in box.kids:
        _paint(p, k, x + dx, y + dy, ctx)


def render_image(row: mb.Row, px: float = 20.0, display: bool = False,
                 dpr: float = 2.0, pad: float = 4.0,
                 ink: QColor = INK) -> QImage:
    """Rasterise *row* tightly (transparent background)."""
    box = Layout(px, display).layout(row)
    w = int(math.ceil((box.w + 2 * pad) * dpr))
    h = int(math.ceil((box.asc + box.desc + 2 * pad) * dpr))
    img = QImage(max(w, 1), max(h, 1), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    img.setDevicePixelRatio(dpr)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    paint(p, box, pad, pad + box.asc, PaintCtx(ink=ink))
    p.end()
    return img


def render_pixmap(latex: str, px: float = 20.0, display: bool = False,
                  dpr: float = 2.0) -> QPixmap:
    return QPixmap.fromImage(render_image(mb.parse_latex(latex), px,
                                          display, dpr))

