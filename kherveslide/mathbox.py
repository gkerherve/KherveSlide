"""Structured math model behind the WYSIWYG equation editor.

An equation is a tree: a :class:`Row` holds a list of nodes, and every
structure (fraction, root, scripts, matrix, ...) owns one or more Rows as
its *slots*. The :class:`Editor` keeps a cursor ``(row, index)`` — the gap
before ``row.children[index]`` — and implements Word/MathType-style typing
on top of the tree. :func:`to_latex` and :func:`parse_latex` convert to and
from LaTeX; anything the parser does not understand becomes a :class:`Raw`
node so no user LaTeX is ever lost.

Pure Python: no Qt here, so the model is testable headless.
"""
from __future__ import annotations

import copy
import re

PLACEHOLDER = r"\square"

# ------------------------------------------------------------------ tables

_GREEK_LOWER = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    # TeX's \epsilon is the lunate form and \varepsilon the open one.
    "epsilon": "ϵ", "varepsilon": "ε", "zeta": "ζ", "eta": "η",
    "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "omicron": "ο",
    "pi": "π", "varpi": "ϖ", "rho": "ρ", "varrho": "ϱ", "sigma": "σ",
    "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "ϕ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
}
_GREEK_UPPER = {
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω",
}
_BIN = {
    "pm": "±", "mp": "∓", "times": "×", "div": "÷", "cdot": "⋅",
    "ast": "∗", "star": "⋆", "circ": "∘", "bullet": "∙", "oplus": "⊕",
    "ominus": "⊖", "otimes": "⊗", "oslash": "⊘", "odot": "⊙",
    "dagger": "†", "ddagger": "‡", "cap": "∩", "cup": "∪",
    "setminus": "∖", "land": "∧", "lor": "∨", "wedge": "∧", "vee": "∨",
    "diamond": "⋄", "uplus": "⊎", "sqcup": "⊔", "sqcap": "⊓",
}
_REL = {
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "equiv": "≡", "sim": "∼", "simeq": "≃", "cong": "≅",
    "propto": "∝", "ll": "≪", "gg": "≫", "subset": "⊂", "supset": "⊃",
    "subseteq": "⊆", "supseteq": "⊇", "in": "∈", "notin": "∉", "ni": "∋",
    "perp": "⊥", "parallel": "∥", "mid": "∣", "to": "→",
    "leftarrow": "←", "rightarrow": "→", "gets": "←", "Rightarrow": "⇒",
    "Leftarrow": "⇐", "Leftrightarrow": "⇔", "leftrightarrow": "↔",
    "uparrow": "↑", "downarrow": "↓", "Uparrow": "⇑", "Downarrow": "⇓",
    "mapsto": "↦", "hookrightarrow": "↪", "longrightarrow": "⟶",
    "longleftarrow": "⟵", "Longrightarrow": "⟹", "Longleftarrow": "⟸",
    "longleftrightarrow": "⟷", "Longleftrightarrow": "⟺",
    "rightleftharpoons": "⇌", "leftrightharpoons": "⇋", "iff": "⟺",
    "implies": "⟹", "doteq": "≐", "models": "⊨", "vdash": "⊢",
    "prec": "≺", "succ": "≻", "asymp": "≍", "nearrow": "↗",
    "searrow": "↘", "coloneqq": "≔", "lesssim": "≲", "gtrsim": "≳",
    "leqslant": "⩽", "geqslant": "⩾", "nleq": "≰", "ngeq": "≱",
}
_ORD = {
    "partial": "∂", "nabla": "∇", "infty": "∞", "forall": "∀",
    "exists": "∃", "nexists": "∄", "neg": "¬", "lnot": "¬",
    "emptyset": "∅", "varnothing": "⌀", "degree": "°", "angle": "∠",
    "triangle": "△", "dots": "…", "ldots": "…", "cdots": "⋯",
    "vdots": "⋮", "ddots": "⋱", "hbar": "ℏ", "hslash": "ℏ", "ell": "ℓ",
    "Re": "ℜ", "Im": "ℑ", "aleph": "ℵ", "wp": "℘", "prime": "′",
    "top": "⊤", "bot": "⊥", "imath": "ı", "jmath": "ȷ", "flat": "♭",
    "sharp": "♯", "natural": "♮", "circledast": "⊛", "Box": "□",
    "copyright": "©", "textregistered": "®", "texttrademark": "™",
    "backslash": "∖", "checkmark": "✓", "dag": "†", "S": "§",
    "P": "¶", "surd": "√", "blacksquare": "■",
}
_OPEN = {"langle": "⟨", "lfloor": "⌊", "lceil": "⌈", "lbrace": "{",
         "lvert": "|", "lVert": "‖"}
_CLOSE = {"rangle": "⟩", "rfloor": "⌋", "rceil": "⌉", "rbrace": "}",
          "rvert": "|", "rVert": "‖"}

#: cmd (without backslash) -> (glyph, class)
SYMBOLS: dict[str, tuple[str, str]] = {}
for _tbl, _cls in ((_GREEK_LOWER, "ord"), (_GREEK_UPPER, "ord"),
                   (_BIN, "bin"), (_REL, "rel"), (_ORD, "ord"),
                   (_OPEN, "open"), (_CLOSE, "close")):
    for _k, _v in _tbl.items():
        SYMBOLS[_k] = (_v, _cls)
SYMBOLS["colon"] = (":", "punct")
SYMBOLS["vert"] = ("|", "ord")
SYMBOLS["Vert"] = ("‖", "ord")
SYMBOLS["|"] = ("‖", "ord")
SYMBOLS["{"] = ("{", "open")
SYMBOLS["}"] = ("}", "close")
SYMBOLS["%"] = ("%", "ord")
SYMBOLS["#"] = ("#", "ord")
SYMBOLS["&"] = ("&", "ord")
SYMBOLS["$"] = ("$", "ord")
SYMBOLS["_"] = ("_", "ord")

GREEK_LOWER_GLYPHS = frozenset(_GREEK_LOWER.values())

#: Upright operator names; the ones LaTeX lacks go out as \operatorname.
FUNCS = (
    "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh", "coth", "log", "ln", "lg", "exp", "det", "dim",
    "ker", "gcd", "deg", "arg", "max", "min", "sup", "inf", "Pr", "hom",
)
_LATEX_FUNCS = frozenset(FUNCS)
#: Names recognised while typing plain letters (Word's math autocorrect).
AUTO_FUNCS = ("sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos",
              "arctan", "sinh", "cosh", "tanh", "coth", "log", "ln", "exp",
              "det", "max", "min", "lim")

#: Large operators: name -> glyph ('' = drawn as an upright word).
BIGOPS = {
    "sum": "∑", "prod": "∏", "coprod": "∐", "int": "∫", "iint": "∬",
    "iiint": "∭", "oint": "∮", "oiint": "∯", "bigcup": "⋃", "bigcap": "⋂",
    "bigoplus": "⨁", "bigotimes": "⨂", "bigodot": "⨀", "bigvee": "⋁",
    "bigwedge": "⋀", "bigsqcup": "⨆",
    "lim": "", "liminf": "", "limsup": "",
}
INTEGRALS = frozenset({"int", "iint", "iiint", "oint", "oiint"})

ACCENTS = ("hat", "widehat", "bar", "overline", "vec", "overrightarrow",
           "dot", "ddot", "tilde", "widetilde", "acute", "grave", "check",
           "breve", "underline", "mathring")
STYLES = ("mathrm", "mathbf", "mathit", "mathbb", "mathcal", "mathfrak",
          "mathsf", "mathtt", "boldsymbol", "bm", "mathscr")
FRACS = ("frac", "dfrac", "tfrac", "cfrac", "binom", "dbinom", "tbinom")
MATRIX_ENVS = ("matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix",
               "Vmatrix", "smallmatrix", "cases", "aligned", "gathered",
               "split", "align", "align*", "gather", "gather*",
               "equation", "equation*", "multline", "multline*")

SPACES = {",": 3, ":": 4, ">": 4, ";": 5, "!": -3, "quad": 18,
          "qquad": 36, " ": 6, "~": 6, "enspace": 9, "thinspace": 3}

# \left/\right delimiters: latex token -> glyph
DELIMS = {
    "(": "(", ")": ")", "[": "[", "]": "]", r"\{": "{", r"\}": "}",
    "|": "|", r"\|": "‖", r"\lvert": "|", r"\rvert": "|", r"\lVert": "‖",
    r"\rVert": "‖", r"\vert": "|", r"\Vert": "‖",
    r"\langle": "⟨", r"\rangle": "⟩", r"\lfloor": "⌊", r"\rfloor": "⌋",
    r"\lceil": "⌈", r"\rceil": "⌉", r"\lbrace": "{", r"\rbrace": "}",
    ".": "", "<": "⟨", ">": "⟩", "/": "/", r"\uparrow": "↑",
    r"\downarrow": "↓",
}
_DELIM_PAIRS = {"(": ")", "[": "]", r"\{": r"\}", "|": "|", r"\|": r"\|",
                r"\langle": r"\rangle", r"\lfloor": r"\rfloor",
                r"\lceil": r"\rceil"}

# ------------------------------------------------------------------ nodes


class Row:
    __slots__ = ("children", "owner")

    def __init__(self, children=None):
        self.children: list = list(children or [])
        self.owner = None

    def __len__(self):
        return len(self.children)

    def is_empty(self) -> bool:
        return not self.children

    def __repr__(self):
        return f"Row({self.children!r})"


class Node:
    parent: Row | None = None
    cls = "ord"

    def slots(self) -> list[Row]:
        return []

    def __repr__(self):
        return f"{type(self).__name__}()"


class Atom(Node):
    """A single typed character. ``kind`` is its TeX math class; 'text'
    marks characters inside \\text{}."""

    def __init__(self, char: str, kind: str | None = None):
        self.char = char
        self.kind = kind or classify_char(char)

    @property
    def cls(self):
        return "ord" if self.kind == "text" else self.kind

    def __repr__(self):
        return f"Atom({self.char!r})"


class Symbol(Node):
    def __init__(self, cmd: str):
        self.cmd = cmd.lstrip("\\")

    @property
    def glyph(self) -> str:
        return SYMBOLS.get(self.cmd, (self.cmd, "ord"))[0]

    @property
    def cls(self):
        return SYMBOLS.get(self.cmd, ("", "ord"))[1]

    def __repr__(self):
        return f"Symbol({self.cmd!r})"


class Func(Node):
    cls = "op"

    def __init__(self, name: str, operatorname: bool = False):
        self.name = name
        self.operatorname = operatorname or name not in _LATEX_FUNCS

    def __repr__(self):
        return f"Func({self.name!r})"


class Placeholder(Node):
    """An empty slot sitting inside a non-empty row (e.g. ``□ = □``)."""


class Raw(Node):
    """LaTeX the model does not understand, kept verbatim."""

    def __init__(self, latex: str):
        self.latex = latex

    def __repr__(self):
        return f"Raw({self.latex!r})"


class Space(Node):
    cls = "space"

    def __init__(self, cmd: str):
        self.cmd = cmd

    @property
    def mu(self) -> int:
        return SPACES.get(self.cmd, 3)


class CmdInput(Node):
    """The half-typed ``\\name`` while the user is entering a command."""

    def __init__(self, text: str = ""):
        self.text = text


class Frac(Node):
    cls = "inner"

    def __init__(self, num=None, den=None, cmd: str = "frac"):
        self.num = num or Row()
        self.den = den or Row()
        self.cmd = cmd

    def slots(self):
        return [self.num, self.den]


class Sqrt(Node):
    def __init__(self, body=None, index=None):
        self.body = body or Row()
        self.index = index

    def slots(self):
        return [self.index, self.body] if self.index is not None \
            else [self.body]


class Scripts(Node):
    """Sub/superscript attached to whatever node precedes it."""

    def __init__(self, sub=None, sup=None):
        self.sub = sub
        self.sup = sup

    def slots(self):
        return [r for r in (self.sub, self.sup) if r is not None]


class BigOp(Node):
    cls = "op"

    def __init__(self, op: str, lower=None, upper=None):
        self.op = op
        self.lower = lower
        self.upper = upper

    def slots(self):
        return [r for r in (self.lower, self.upper) if r is not None]


class Delim(Node):
    cls = "inner"

    def __init__(self, left="(", right=")", body=None, sized=None):
        self.left = left
        self.right = right
        self.body = body or Row()
        # True: came from \left..\right; None: auto (sized when tall).
        self.sized = sized

    def slots(self):
        return [self.body]


class Matrix(Node):
    cls = "inner"

    def __init__(self, env="pmatrix", rows=None):
        self.env = env
        self.rows: list[list[Row]] = rows or [[Row(), Row()], [Row(), Row()]]

    def slots(self):
        return [c for r in self.rows for c in r]

    def ncols(self) -> int:
        return max((len(r) for r in self.rows), default=0)


class Accent(Node):
    def __init__(self, cmd="hat", body=None):
        self.cmd = cmd
        self.body = body or Row()

    def slots(self):
        return [self.body]


class Styled(Node):
    """\\mathbb{R}, \\mathrm{d}, \\mathbf{v}, ..."""

    def __init__(self, cmd="mathrm", body=None):
        self.cmd = cmd
        self.body = body or Row()

    def slots(self):
        return [self.body]


class Text(Node):
    """\\text{...}: its row holds Atom(kind='text') characters."""

    def __init__(self, body=None):
        self.body = body or Row()

    def slots(self):
        return [self.body]


class Group(Node):
    """A braced group that must stay grouped, e.g. ``{a+b}^2``."""

    def __init__(self, body=None):
        self.body = body or Row()

    def slots(self):
        return [self.body]


def classify_char(ch: str) -> str:
    if ch in "+-*":
        return "bin"
    if ch in "=<>:":
        return "rel"
    if ch in ",;":
        return "punct"
    if ch in "([":
        return "open"
    if ch in ")]":
        return "close"
    return "ord"


def link(row: Row, owner=None) -> Row:
    """(Re)set parent/owner pointers below *row*."""
    row.owner = owner
    for n in row.children:
        n.parent = row
        for s in n.slots():
            link(s, n)
    return row


def walk_rows(row: Row):
    """Every row in document order (depth first, slot order)."""
    yield row
    for n in row.children:
        for s in n.slots():
            yield from walk_rows(s)


def _index_of(seq, item) -> int:
    for i, x in enumerate(seq):
        if x is item:
            return i
    raise ValueError("not found")


# ------------------------------------------------------------ serializer

_CTRL_WORD_END = re.compile(r"\\[A-Za-z]+$")
_TEXT_ESC = {"{": r"\{", "}": r"\}", "%": r"\%", "#": r"\#", "&": r"\&",
             "$": r"\$", "_": r"\_", "\\": r"\textbackslash{}",
             "^": r"\^{}", "~": r"\~{}"}
_ATOM_TEX = {"{": r"\{", "}": r"\}", "%": r"\%", "#": r"\#", "&": r"\&",
             "$": r"\$", "_": r"\_", "−": "-", "′": "'"}
_TALL = (Frac, BigOp, Matrix, Sqrt)


def to_latex(row: Row, placeholder: str = "{}") -> str:
    """Serialise *row*. Empty slots become *placeholder*: ``{}`` for the
    document, :data:`PLACEHOLDER` for the editable source view."""
    return _row(row, placeholder).strip()


def _row(row: Row, ph: str, slot: bool = False,
         compact: bool = False) -> str:
    if not row.children:
        return ph if slot else ""
    out = ""
    prev = None
    for i, n in enumerate(row.children):
        tok = _node(n, ph, prev)
        if isinstance(prev, (BigOp, Space)) and not isinstance(n, Scripts):
            out += " "
        if compact and not (isinstance(n, Symbol) and n.cls in ("bin", "rel")
                            and prev is not None):
            if out and _CTRL_WORD_END.search(out) and tok[:1].isalpha():
                out += " "
            out += tok
            prev = n
            continue
        if n.cls in ("bin", "rel") and isinstance(n, (Atom, Symbol)) \
                and prev is not None and not isinstance(prev, Space):
            unary = n.cls == "bin" and (prev.cls in ("bin", "rel", "open",
                                                     "punct", "op"))
            if not unary:
                out = out.rstrip() + " " + tok + " "
                prev = n
                continue
        if prev is None and n.cls == "rel" and isinstance(n, (Atom, Symbol)):
            out = tok + " "
            prev = n
            continue
        if isinstance(prev, (Atom, Symbol)) and prev.cls == "punct":
            out = out.rstrip() + " "
        if out and _CTRL_WORD_END.search(out) and tok[:1].isalpha():
            out += " "
        out += tok
        prev = n
    return out


def _arg(row: Row | None, ph: str, compact: bool = False) -> str:
    if row is None or not row.children:
        return "{}" if ph == "{}" else "{" + ph + "}"
    return "{" + _row(row, ph, True, compact).strip() + "}"


def _script_arg(row: Row, ph: str) -> str:
    if len(row.children) == 1:
        n = row.children[0]
        if isinstance(n, Atom) and (n.char.isalnum()) and n.kind != "text":
            return n.char
    return _arg(row, ph, compact=True)


def _node(n, ph: str, prev) -> str:
    if isinstance(n, Atom):
        if n.kind == "text":
            return _TEXT_ESC.get(n.char, n.char)
        return _ATOM_TEX.get(n.char, n.char)
    if isinstance(n, Symbol):
        return "\\" + n.cmd
    if isinstance(n, Func):
        return (r"\operatorname{%s}" % n.name) if n.operatorname \
            else "\\" + n.name
    if isinstance(n, Placeholder):
        return ph
    if isinstance(n, Raw):
        return n.latex
    if isinstance(n, Space):
        return "~" if n.cmd == "~" else "\\" + n.cmd
    if isinstance(n, CmdInput):
        return "\\" + n.text
    if isinstance(n, Frac):
        return "\\" + n.cmd + _arg(n.num, ph) + _arg(n.den, ph)
    if isinstance(n, Sqrt):
        idx = ""
        if n.index is not None:
            idx = "[%s]" % ("" if ph == "{}" and not n.index.children
                            else _row(n.index, ph, True).strip())
        return r"\sqrt" + idx + _arg(n.body, ph)
    if isinstance(n, Scripts):
        base = ""
        if prev is None or isinstance(prev, (Scripts, Space)) or (
                isinstance(prev, (Atom, Symbol))
                and prev.cls in ("bin", "rel", "punct")):
            base = "{}"
        s = base
        if n.sub is not None:
            s += "_" + _script_arg(n.sub, ph)
        if n.sup is not None:
            s += "^" + _script_arg(n.sup, ph)
        return s
    if isinstance(n, BigOp):
        s = "\\" + n.op
        for mark, r in (("_", n.lower), ("^", n.upper)):
            if r is None or (r.is_empty() and ph == "{}"):
                continue
            s += mark + _script_arg(r, ph)
        return s
    if isinstance(n, Delim):
        body = _row(n.body, ph, slot=False).strip()
        if not n.body.children and ph != "{}":
            body = ph
        tall = any(isinstance(c, _TALL) for c in n.body.children)
        plain_ok = n.left in _PLAIN_DELIMS and n.right in _PLAIN_DELIMS
        if n.sized or (n.sized is None and tall) or not plain_ok:
            return r"\left%s %s \right%s" % (n.left or ".", body,
                                              n.right or ".")
        left, right = n.left or "", n.right or ""
        if _CTRL_WORD_END.search(left) and body[:1].isalpha():
            left += " "
        return left + body + right
    if isinstance(n, Matrix):
        sep = " \\\\\n" if n.env in _DISPLAY_ENVS else r" \\ "
        rows = []
        for r in n.rows:
            cells = [_row(c, ph, slot=True).strip() for c in r]
            if n.env in _ALIGN_ENVS:
                rows.append(" &".join(cells) if len(cells) > 1
                            else cells[0])
            else:
                rows.append(" & ".join(cells))
        nl = "\n" if n.env in _DISPLAY_ENVS else " "
        return (r"\begin{%s}" % n.env + nl + sep.join(rows) + nl
                + r"\end{%s}" % n.env)
    if isinstance(n, Accent):
        return "\\" + n.cmd + _arg(n.body, ph)
    if isinstance(n, Styled):
        return "\\" + n.cmd + _arg(n.body, ph)
    if isinstance(n, Text):
        return r"\text{" + "".join(
            _node(c, ph, None) for c in n.body.children) + "}"
    if isinstance(n, Group):
        return _arg(n.body, ph)
    raise TypeError(n)


_PLAIN_DELIMS = frozenset({"(", ")", "[", "]", r"\{", r"\}", "|", r"\|"})
_DISPLAY_ENVS = frozenset({"align", "align*", "gather", "gather*",
                           "equation", "equation*", "multline",
                           "multline*"})
_ALIGN_ENVS = frozenset({"align", "align*", "aligned", "split"})

# ----------------------------------------------------------------- parser

_TOKEN = re.compile(r"\\([A-Za-z]+)\*?|\\(.)|(\s+)|(.)", re.DOTALL)


class _Tok:
    __slots__ = ("kind", "val", "start", "end")

    def __init__(self, kind, val, start, end):
        self.kind, self.val, self.start, self.end = kind, val, start, end

    def __repr__(self):
        return f"{self.kind}:{self.val}"


def _tokenize(s: str) -> list[_Tok]:
    toks = []
    for m in _TOKEN.finditer(s):
        if m.group(1) is not None:
            name = m.group(0)[1:]
            toks.append(_Tok("cmd", name, m.start(), m.end()))
        elif m.group(2) is not None:
            toks.append(_Tok("sym", m.group(2), m.start(), m.end()))
        elif m.group(3) is not None:
            toks.append(_Tok("ws", m.group(3), m.start(), m.end()))
        else:
            toks.append(_Tok("ch", m.group(4), m.start(), m.end()))
    return toks


def normalize_template(s: str) -> str:
    r"""Templates in :mod:`equations` store line breaks as the two
    characters ``\n``; turn them into real newlines."""
    s = re.sub(r"\\n(?![A-Za-z])", "\n", s)
    return re.sub(r"(\\\\\s*){2,}", r"\\\\ ", s)


class _Parser:
    def __init__(self, src: str):
        self.src = src
        self.toks = _tokenize(src)
        self.i = 0

    # -- token helpers
    def peek(self, skip_ws=True):
        j = self.i
        while skip_ws and j < len(self.toks) and self.toks[j].kind == "ws":
            j += 1
        return self.toks[j] if j < len(self.toks) else None

    def next(self, skip_ws=True):
        while skip_ws and self.i < len(self.toks) \
                and self.toks[self.i].kind == "ws":
            self.i += 1
        if self.i >= len(self.toks):
            return None
        t = self.toks[self.i]
        self.i += 1
        return t

    @staticmethod
    def is_(t, kind, val=None):
        return t is not None and t.kind == kind and (val is None
                                                      or t.val == val)

    # -- grammar
    def parse_row(self, stops=frozenset()) -> Row:
        nodes: list = []
        while True:
            t = self.peek()
            if t is None or self._is_stop(t, stops):
                break
            self.parse_item(nodes, stops)
        return _tidy(Row(nodes))

    def _is_stop(self, t, stops) -> bool:
        if t.kind == "ch" and t.val in "}":
            return True
        if t.kind == "ch" and t.val in stops:
            return True
        if t.kind == "ch" and t.val == "&" and "&" in stops:
            return True
        if t.kind == "sym" and t.val == "\\" and "\\\\" in stops:
            return True
        if t.kind == "sym" and t.val == "}" and "\\}" in stops:
            return True
        if t.kind == "cmd" and t.val in ("end", "right") \
                and t.val in stops:
            return True
        return False

    def group_or_token(self) -> Row:
        """A macro argument: ``{...}`` or a single token."""
        t = self.peek()
        if t is None:
            return Row()
        if self.is_(t, "ch", "{"):
            self.next()
            r = self.parse_row()
            if self.is_(self.peek(), "ch", "}"):
                self.next()
            return r
        nodes: list = []
        self.parse_item(nodes, frozenset(), single=True)
        return _tidy(Row(nodes))

    def braced_raw(self) -> str | None:
        """Verbatim text of the next ``{...}`` group (without braces)."""
        t = self.peek()
        if not self.is_(t, "ch", "{"):
            return None
        self.next()
        start = t.end
        depth = 1
        while self.i < len(self.toks):
            u = self.toks[self.i]
            self.i += 1
            if u.kind == "ch" and u.val == "{":
                depth += 1
            elif u.kind == "ch" and u.val == "}":
                depth -= 1
                if depth == 0:
                    return self.src[start:u.start]
        return self.src[start:]

    def parse_item(self, nodes: list, stops, single=False) -> None:
        t = self.next()
        if t.kind == "ch":
            c = t.val
            if c == "{":
                r = self.parse_row()
                if self.is_(self.peek(), "ch", "}"):
                    self.next()
                nxt = self.peek()
                if not r.children and (self.is_(nxt, "ch", "^")
                                       or self.is_(nxt, "ch", "_")):
                    return          # "{}^2": scripts with no base
                if len(r.children) > 1 and (self.is_(nxt, "ch", "^")
                                            or self.is_(nxt, "ch", "_")):
                    nodes.append(Group(r))
                elif single and len(r.children) != 1:
                    nodes.append(Group(r))
                else:
                    nodes.extend(r.children)
                return
            if c in "^_":
                arg = self.group_or_token()
                _attach_script(nodes, c, arg)
                return
            if c in "([" and not single:
                close = ")" if c == "(" else "]"
                save = self.i
                body = self.parse_row(stops | {close})
                if self.is_(self.peek(), "ch", close):
                    self.next()
                    nodes.append(Delim(c, close, body, sized=False))
                    return
                self.i = save
                nodes.append(Atom(c))
                return
            if c == "~":
                nodes.append(Space("~"))
                return
            if c == "'":
                nodes.append(Atom("′", "ord"))
                return
            if c == "&" or c == "}":
                nodes.append(Raw(c))
                return
            nodes.append(Atom(c))
            return
        if t.kind == "sym":
            v = t.val
            if v in SPACES:
                nodes.append(Space(v))
            elif v == "{" and not single:
                save = self.i
                body = self.parse_row(stops | {"\\}"})
                if self.is_(self.peek(), "sym", "}"):
                    self.next()
                    nodes.append(Delim(r"\{", r"\}", body, sized=False))
                    return
                self.i = save
                nodes.append(Symbol("{"))
            elif v in SYMBOLS:
                nodes.append(Symbol(v))
            elif v == "\\":
                nodes.append(Raw(r"\\"))
            else:
                nodes.append(Raw("\\" + v))
            return
        if t.kind == "ws":
            return
        self.parse_command(t, nodes, stops)

    def parse_command(self, t, nodes, stops) -> None:
        name = t.val
        starred = self.src[t.start:t.end].endswith("*")
        if name == "square":
            nodes.append(Placeholder())
        elif name in FRACS:
            a = self.group_or_token()
            b = self.group_or_token()
            nodes.append(Frac(a, b, name))
        elif name == "sqrt":
            index = None
            if self.is_(self.peek(), "ch", "["):
                self.next()
                index = self.parse_row(frozenset({"]"}))
                if self.is_(self.peek(), "ch", "]"):
                    self.next()
            nodes.append(Sqrt(self.group_or_token(), index))
        elif name in BIGOPS:
            nodes.append(BigOp(name))
        elif name in ("limits", "nolimits", "displaystyle", "textstyle",
                      "scriptstyle", "nonumber", "notag"):
            nodes.append(Raw("\\" + name))
        elif name in FUNCS:
            nodes.append(Func(name))
        elif name == "operatorname":
            txt = self.braced_raw()
            if txt is None:
                nodes.append(Raw(r"\operatorname"))
            elif starred:
                nodes.append(Raw(r"\operatorname*{%s}" % txt))
            else:
                nodes.append(Func(txt.strip(), operatorname=True))
        elif name in ACCENTS:
            nodes.append(Accent(name, self.group_or_token()))
        elif name in STYLES:
            nodes.append(Styled(name, self.group_or_token()))
        elif name in ("text", "textrm", "mbox", "textnormal"):
            txt = self.braced_raw()
            if txt is None:
                nodes.append(Raw("\\" + name))
            elif name != "text" or re.search(r"\\(?!(?:[{}%#&$_ ]))|\$",
                                             txt):
                nodes.append(Raw("\\%s{%s}" % (name, txt)))
            else:
                nodes.append(Text(Row(
                    [Atom(c, "text") for c in _unescape_text(txt)])))
        elif name == "left":
            left = self._delim_token()
            body = self.parse_row(frozenset({"right"}))
            right = "."
            if self.is_(self.peek(), "cmd", "right"):
                self.next()
                right = self._delim_token()
            nodes.append(Delim("" if left == "." else left,
                               "" if right == "." else right, body,
                               sized=True))
        elif name == "begin":
            self._parse_env(nodes)
        elif name in SPACES:
            nodes.append(Space(name))
        elif name in SYMBOLS:
            nodes.append(Symbol(name))
        else:
            # Unknown macro: keep it and its braced/bracketed arguments
            # verbatim so re-serialising never changes its meaning.
            start = t.start
            end = t.end
            while True:
                p = self.peek()
                if self.is_(p, "ch", "{"):
                    self.braced_raw()
                    end = self.toks[self.i - 1].end
                elif self.is_(p, "ch", "[") and end == p.start:
                    depth = 0
                    while self.i < len(self.toks):
                        u = self.toks[self.i]
                        self.i += 1
                        if u.kind == "ch" and u.val == "[":
                            depth += 1
                        elif u.kind == "ch" and u.val == "]":
                            depth -= 1
                            if depth == 0:
                                break
                    end = self.toks[self.i - 1].end
                else:
                    break
            nodes.append(Raw(self.src[start:end]))

    def _delim_token(self) -> str:
        t = self.next()
        if t is None:
            return "."
        if t.kind == "ch":
            return t.val
        if t.kind == "sym":
            return "\\" + t.val
        return "\\" + t.val

    def _parse_env(self, nodes) -> None:
        start_tok = self.toks[self.i - 1]
        env = self.braced_raw() or ""
        env = env.strip()
        if env not in MATRIX_ENVS:
            # Unknown environment: capture verbatim through its \end.
            depth = 1
            while self.i < len(self.toks):
                u = self.toks[self.i]
                self.i += 1
                if u.kind == "cmd" and u.val in ("begin", "end"):
                    save = self.i
                    e = self.braced_raw()
                    if e is not None and e.strip() == env:
                        depth += 1 if u.val == "begin" else -1
                        if depth == 0:
                            break
                    elif e is None:
                        self.i = save
            end = self.toks[self.i - 1].end if self.i else len(self.src)
            nodes.append(Raw(self.src[start_tok.start:end]))
            return
        rows: list[list[Row]] = []
        cells: list[Row] = []
        stops = frozenset({"&", "\\\\", "end"})
        while True:
            cell = self.parse_row(stops)
            cells.append(cell)
            t = self.peek()
            if t is None:
                break
            if self.is_(t, "ch", "&"):
                self.next()
                continue
            if self.is_(t, "sym", "\\"):
                self.next()
                if self.is_(self.peek(), "ch", "["):   # \\[2pt]
                    self.parse_row(frozenset({"]"}))
                    self.next()
                rows.append(cells)
                cells = []
                continue
            if self.is_(t, "cmd", "end"):
                self.next()
                self.braced_raw()
                break
            if self.is_(t, "ch", "}"):
                self.next()     # stray brace: skip it
                continue
            break
        if cells and not (len(cells) == 1 and not cells[0].children
                          and rows):
            rows.append(cells)
        if not rows:
            rows = [[Row()]]
        width = max(len(r) for r in rows)
        for r in rows:
            while len(r) < width:
                r.append(Row())
        nodes.append(Matrix(env, rows))


def _unescape_text(s: str) -> str:
    return re.sub(r"\\([{}%#&$_ ])", r"\1", s)


def _attach_script(nodes: list, mark: str, arg: Row) -> None:
    prev = nodes[-1] if nodes else None
    attr = "sub" if mark == "_" else "sup"
    if isinstance(prev, BigOp):
        battr = "lower" if mark == "_" else "upper"
        if getattr(prev, battr) is None:
            setattr(prev, battr, arg)
            return
    if isinstance(prev, Scripts) and getattr(prev, attr) is None:
        setattr(prev, attr, arg)
        return
    s = Scripts()
    setattr(s, attr, arg)
    nodes.append(s)


def _tidy(row: Row) -> Row:
    """A slot holding just ``\\square`` is simply an empty slot."""
    if len(row.children) == 1 and isinstance(row.children[0], Placeholder):
        row.children = []
    return row


def parse_latex(s: str) -> Row:
    """Parse LaTeX math into a tree. Never raises: anything unknown is
    kept verbatim in :class:`Raw` nodes."""
    p = _Parser(normalize_template(s or ""))
    nodes: list = []
    while p.peek() is not None:
        row = p.parse_row()
        nodes.extend(row.children)
        t = p.next()
        if t is not None:   # stray closer
            nodes.append(Raw(p.src[t.start:t.end]))
    return link(_tidy(Row(nodes)))


# ------------------------------------------------------------ commands

def _cmd_entries():
    out = []
    for k, (g, _c) in SYMBOLS.items():
        if k.isalpha():
            out.append((k, g))
    for f in FUNCS:
        out.append((f, f))
    for k, g in BIGOPS.items():
        out.append((k, g or k))
    for k in FRACS:
        out.append((k, "a⁄b" if "frac" in k else "(ⁿₖ)"))
    out += [("sqrt", "√"), ("nthroot", "ⁿ√"), ("text", "abc"),
            ("abs", "|x|"), ("norm", "‖x‖")]
    for a in ACCENTS:
        out.append((a, "x̂"))
    for s in STYLES:
        out.append((s, s[4:] if s.startswith("math") else s))
    for e in ("matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix",
              "Vmatrix", "cases", "aligned"):
        out.append((e, "▦"))
    for k in ("quad", "qquad"):
        out.append((k, "␣"))
    seen, uniq = set(), []
    for k, g in out:
        if k not in seen:
            seen.add(k)
            uniq.append((k, g))
    return uniq


COMMANDS = _cmd_entries()
_COMMAND_NAMES = {k for k, _ in COMMANDS}


def completions(prefix: str, limit: int = 12) -> list[tuple[str, str]]:
    """Commands starting with *prefix* (exact match first, then the most
    common/shortest)."""
    if not prefix:
        return []
    hits = [(k, g) for k, g in COMMANDS if k.startswith(prefix)]
    hits.sort(key=lambda kg: (kg[0] != prefix, len(kg[0]), kg[0]))
    return hits[:limit]


def command_nodes(name: str) -> tuple[list, Row | None]:
    """Nodes for a typed ``\\name`` and the row the caret should enter
    (None: caret goes after the nodes)."""
    if name in FRACS:
        f = Frac(cmd=name)
        return [f], f.num
    if name == "sqrt":
        s = Sqrt()
        return [s], s.body
    if name in ("nthroot", "root"):
        s = Sqrt(index=Row())
        return [s], s.index
    if name in BIGOPS:
        op = BigOp(name, Row(), None if name.startswith("lim") else Row())
        return [op], op.lower
    if name in FUNCS:
        return [Func(name)], None
    if name in ACCENTS:
        a = Accent(name)
        return [a], a.body
    if name in STYLES:
        s = Styled(name)
        return [s], s.body
    if name in ("text", "textrm", "mbox"):
        t = Text()
        return [t], t.body
    if name in ("abs", "norm"):
        d = "|" if name == "abs" else r"\|"
        n = Delim(d, d)
        return [n], n.body
    if name in ("langle", "lfloor", "lceil"):
        n = Delim("\\" + name, "\\" + _DELIM_PAIRS["\\" + name][1:])
        return [n], n.body
    if name in MATRIX_ENVS:
        m = Matrix(name)
        return [m], m.rows[0][0]
    if name in SPACES:
        return [Space(name)], None
    if name == "square":
        return [Placeholder()], None
    if name in SYMBOLS:
        return [Symbol(name)], None
    return [Raw("\\" + name)], None


# ---------------------------------------------------------------- editor

_AUTO_REPLACE = {
    ("-", ">"): "to", ("<", "="): "leq", (">", "="): "geq",
    ("!", "="): "neq", ("+", "-"): "pm", ("=", ">"): "Rightarrow",
    ("<", "-"): "leftarrow", ("~", "="): "approx",
}
_CLOSERS = {")": "(", "]": "[", "}": r"\{"}


class Editor:
    """Cursor, selection and editing operations on a math tree."""

    def __init__(self, root: Row | None = None):
        self.root = link(root or Row())
        self.row = self.root
        self.idx = len(self.root.children)
        self.anchor: tuple[Row, int] | None = None
        self._undo: list = []
        self._redo: list = []
        self.cmd: CmdInput | None = None
        self.version = 0

    # ---- loading / output
    def set_latex(self, latex: str) -> None:
        self.cmd = None
        self.root = parse_latex(latex)
        self.row, self.idx = self.root, len(self.root.children)
        self.anchor = None
        self._changed()

    def latex(self, placeholder: str = "{}") -> str:
        return to_latex(self.root, placeholder)

    def _changed(self) -> None:
        link(self.root)
        self.version += 1

    # ---- undo
    def _path(self, row: Row) -> list[tuple[int, int]]:
        path = []
        while row.owner is not None:
            node = row.owner
            path.append((_index_of(node.parent.children, node),
                         _index_of(node.slots(), row)))
            row = node.parent
        return path[::-1]

    def _row_at(self, root: Row, path) -> Row:
        row = root
        for ni, si in path:
            row = row.children[ni].slots()[si]
        return row

    def snapshot(self):
        self.commit_cmd_if_any()
        return (copy.deepcopy(self.root), self._path(self.row), self.idx)

    def _restore(self, snap) -> None:
        root, path, idx = snap
        self.root = link(copy.deepcopy(root))
        try:
            self.row = self._row_at(self.root, path)
        except (IndexError, AttributeError):
            self.row = self.root
        self.idx = min(idx, len(self.row.children))
        self.anchor = None
        self.version += 1

    def push_undo(self) -> None:
        self._undo.append(self.snapshot())
        del self._undo[:-200]
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.snapshot())
        self._restore(self._redo.pop())
        return True

    # ---- selection
    def has_selection(self) -> bool:
        return self.anchor is not None and self.anchor[0] is self.row \
            and self.anchor[1] != self.idx

    def selection(self) -> tuple[Row, int, int] | None:
        if not self.has_selection():
            return None
        a = self.anchor[1]
        return self.row, min(a, self.idx), max(a, self.idx)

    def clear_selection(self) -> None:
        self.anchor = None

    def select_all(self) -> None:
        self.row = self.root
        self.anchor = (self.root, 0)
        self.idx = len(self.root.children)

    def _chain(self, row: Row, idx: int):
        """[(row, idx, inside)] from *row* up to the root."""
        out = [(row, idx, False)]
        while row.owner is not None:
            node = row.owner
            row = node.parent
            out.append((row, _index_of(row.children, node), True))
        return out

    def set_selection(self, a_row, a_idx, c_row, c_idx) -> None:
        """Select from anchor to caret, lifting both ends to their deepest
        common row so selections always cover whole nodes."""
        ca = self._chain(a_row, a_idx)
        cc = self._chain(c_row, c_idx)
        for r, ci, cin in cc:
            for ra, ai, ain in ca:
                if ra is r:
                    if cin and ain and ci == ai:
                        # Both ends inside the same node: select it whole.
                        self.row, self.anchor = r, (r, ci)
                        self.idx = ci + 1
                        return
                    if cin:
                        ci = ci + 1 if ci >= ai else ci
                    if ain:
                        ai = ai + 1 if ai >= ci else ai
                    self.row, self.idx = r, ci
                    self.anchor = (r, ai)
                    return
        self.row, self.idx, self.anchor = c_row, c_idx, None

    def selected_nodes(self) -> list:
        sel = self.selection()
        if not sel:
            return []
        row, i, j = sel
        return row.children[i:j]

    def _take_selection(self) -> list:
        """Remove and return the selected nodes (caret at their spot)."""
        sel = self.selection()
        self.anchor = None
        if not sel:
            return []
        row, i, j = sel
        taken = row.children[i:j]
        del row.children[i:j]
        self.row, self.idx = row, i
        return taken

    def delete_selection(self) -> bool:
        if not self.has_selection():
            return False
        self.push_undo()
        self._take_selection()
        self._changed()
        return True

    # ---- caret placement helpers
    def set_cursor(self, row: Row, idx: int, keep_anchor=False) -> None:
        self.commit_cmd_if_any()
        if not keep_anchor:
            self.anchor = None
        self.row, self.idx = row, max(0, min(idx, len(row.children)))

    def _enter_start(self, row: Row):
        self.row, self.idx = row, 0

    def _enter_end(self, row: Row):
        self.row, self.idx = row, len(row.children)

    def _after(self, node) -> None:
        self.row = node.parent
        self.idx = _index_of(self.row.children, node) + 1

    def _before(self, node) -> None:
        self.row = node.parent
        self.idx = _index_of(self.row.children, node)

    # ---- insertion
    def _eat_placeholder(self) -> None:
        ch = self.row.children
        if self.idx < len(ch) and isinstance(ch[self.idx], Placeholder):
            del ch[self.idx]
        elif self.idx > 0 and isinstance(ch[self.idx - 1], Placeholder):
            del ch[self.idx - 1]
            self.idx -= 1

    def _insert(self, nodes: list) -> None:
        self._eat_placeholder()
        self.row.children[self.idx:self.idx] = nodes
        self.idx += len(nodes)
        link(self.root)

    def insert_nodes(self, nodes: list, wrap_selection=True) -> None:
        """Insert a structure; the selection (if any) fills its first
        empty slot, and the caret lands in the next empty slot."""
        self.commit_cmd_if_any()
        self.push_undo()
        link(Row(nodes))
        taken = self._take_selection()
        first = None
        if taken and wrap_selection:
            first = _first_empty(nodes)
            if first is not None:
                if isinstance(first, Placeholder):
                    top = [k for k, n in enumerate(nodes) if n is first]
                    if top:
                        nodes = nodes[:top[0]] + taken + nodes[top[0] + 1:]
                    else:
                        r = first.parent
                        k = _index_of(r.children, first)
                        r.children[k:k + 1] = taken
                else:
                    first.children[:] = taken
            else:
                nodes = taken + nodes
        self._insert(nodes)
        self._changed()
        target = _first_empty(nodes)
        if target is None:
            return
        if isinstance(target, Placeholder):
            self.row = target.parent
            self.idx = _index_of(self.row.children, target)
        else:
            self._enter_start(target)

    def insert_latex(self, latex: str) -> None:
        self.insert_nodes(list(parse_latex(latex).children))

    def type_text(self, text: str) -> None:
        for ch in text:
            self.type_char(ch)

    def type_char(self, ch: str) -> None:
        if self.cmd is not None:
            self._cmd_char(ch)
            return
        if isinstance(self.row.owner, Text):
            self.push_undo()
            self._take_selection()
            self._insert([Atom(ch, "text")])
            self._changed()
            return
        if ch == "\\":
            self.push_undo()
            self._take_selection()
            self.cmd = CmdInput()
            self._insert([self.cmd])
            self._changed()
            return
        if ch == "/":
            self.make_fraction()
            return
        if ch in "^_":
            self.make_script(ch)
            return
        if ch in ")]}|" and self._close_delim(ch):
            return
        if ch in "([{|":
            self.make_delim(ch)
            return
        if ch.isspace():
            return
        self.push_undo()
        self._take_selection()
        if ch in "{}":
            node = Symbol(ch)
        elif ch == "'":
            node = Atom("′", "ord")
        else:
            node = Atom(ch)
        prev = self.row.children[self.idx - 1] if self.idx else None
        if isinstance(prev, Atom) and (prev.char, ch) in _AUTO_REPLACE:
            self.row.children[self.idx - 1] = Symbol(
                _AUTO_REPLACE[(prev.char, ch)])
            self._changed()
            return
        if isinstance(prev, Symbol) and prev.cmd == "leftarrow" and ch == ">":
            self.row.children[self.idx - 1] = Symbol("leftrightarrow")
            self._changed()
            return
        self._insert([node])
        if ch.isalpha() and ch.isascii():
            self._recognise_function()
        self._changed()

    def _recognise_function(self) -> None:
        ch = self.row.children
        k = self.idx
        prev = ch[k - 2] if k >= 2 else None
        last = ch[k - 1]
        if isinstance(prev, Func) and prev.name + last.char in AUTO_FUNCS:
            prev.name += last.char
            del ch[k - 1]
            self.idx -= 1
            return
        letters = ""
        j = k
        while j > 0 and len(letters) < 6:
            n = ch[j - 1]
            if isinstance(n, Atom) and n.kind == "ord" and n.char.isascii() \
                    and n.char.isalpha():
                letters = n.char + letters
                j -= 1
            else:
                break
        for L in range(len(letters), 1, -1):
            name = letters[-L:]
            if name in AUTO_FUNCS:
                start = k - L
                if name == "lim":
                    node = BigOp("lim", Row(), None)
                    ch[start:k] = [node]
                    link(self.root)
                    self._enter_start(node.lower)
                else:
                    ch[start:k] = [Func(name)]
                    self.idx = start + 1
                return

    def _close_delim(self, ch: str) -> bool:
        """Typing the closer at the end of a bracket's body steps out."""
        row, idx = self.row, self.idx
        while True:
            if idx != len(row.children):
                return False
            o = row.owner
            if o is None:
                return False
            if isinstance(o, Delim) and (
                    (ch == "|" and o.right in ("|", r"\|"))
                    or o.left == _CLOSERS.get(ch)):
                self.commit_cmd_if_any()
                self.anchor = None
                self._after(o)
                self.version += 1
                return True
            if not isinstance(o, (Scripts, Accent, Styled, Frac, Sqrt,
                                  Group)):
                return False
            row = o.parent
            idx = _index_of(row.children, o) + 1

    def make_delim(self, ch: str) -> None:
        pairs = {"(": ("(", ")"), "[": ("[", "]"), "{": (r"\{", r"\}"),
                 "|": ("|", "|")}
        left, right = pairs[ch]
        self.insert_nodes([Delim(left, right)])

    def make_fraction(self) -> None:
        self.push_undo()
        if self.has_selection():
            num = self._take_selection()
        else:
            num = self._take_operand()
        if len(num) == 1 and isinstance(num[0], Delim) \
                and num[0].left == "(" and num[0].body.children:
            num = list(num[0].body.children)
        f = Frac(Row(num), Row())
        self._insert([f])
        self._changed()
        self._enter_start(f.den if num else f.num)

    def _take_operand(self) -> list:
        ch = self.row.children
        j = self.idx
        while j > 0:
            n = ch[j - 1]
            if isinstance(n, (Atom, Symbol)) and n.cls == "ord":
                j -= 1
            elif isinstance(n, (Scripts, Frac, Sqrt, Delim, Accent, Styled,
                                Group, Text)):
                j -= 1
            else:
                break
        taken = ch[j:self.idx]
        del ch[j:self.idx]
        self.idx = j
        return taken

    def make_script(self, mark: str) -> None:
        attr = "sub" if mark == "_" else "sup"
        self.push_undo()
        self._take_selection()
        ch = self.row.children
        nxt = ch[self.idx] if self.idx < len(ch) else None
        prev = ch[self.idx - 1] if self.idx else None
        target = None
        if isinstance(nxt, Scripts):
            target = nxt
        elif isinstance(prev, Scripts):
            target = prev
        elif isinstance(prev, BigOp):
            battr = "lower" if mark == "_" else "upper"
            if getattr(prev, battr) is None:
                setattr(prev, battr, Row())
            self._changed()
            self._enter_end(getattr(prev, battr))
            return
        if target is None:
            target = Scripts()
            self._insert([target])
        if getattr(target, attr) is None:
            setattr(target, attr, Row())
        self._changed()
        self._enter_end(getattr(target, attr))

    # ---- command buffer
    def _cmd_char(self, ch: str) -> None:
        c = self.cmd
        if ch.isalpha() and ch.isascii():
            c.text += ch
            self.version += 1
            return
        if not c.text and ch in r"{}|,;:!% #&$_\ ":
            name = ch
            self._replace_cmd(name if ch != " " else " ")
            return
        self.commit_cmd()
        if not ch.isspace():
            self.type_char(ch)

    def cmd_backspace(self) -> None:
        if self.cmd is None:
            return
        if self.cmd.text:
            self.cmd.text = self.cmd.text[:-1]
            self.version += 1
        else:
            self.cancel_cmd()

    def cancel_cmd(self) -> None:
        if self.cmd is None:
            return
        row = self.cmd.parent
        k = _index_of(row.children, self.cmd)
        del row.children[k]
        self.row, self.idx = row, k
        self.cmd = None
        self._changed()

    def commit_cmd_if_any(self) -> None:
        if self.cmd is not None:
            self.commit_cmd()

    def commit_cmd(self, name: str | None = None) -> None:
        c = self.cmd
        if c is None:
            return
        self._replace_cmd(name if name is not None else c.text)

    def _replace_cmd(self, name: str) -> None:
        c = self.cmd
        self.cmd = None
        row = c.parent
        k = _index_of(row.children, c)
        del row.children[k]
        self.row, self.idx = row, k
        if not name:
            self._changed()
            return
        if name in ("{", "}"):
            nodes, enter = [Symbol(name)], None
        elif name in SPACES or name == " ":
            nodes, enter = [Space(name)], None
        elif name in "|%#&$_":
            nodes, enter = [Symbol(name)], None
        else:
            nodes, enter = command_nodes(name)
        self._insert(nodes)
        self._changed()
        if enter is not None:
            self._enter_start(enter)

    # ---- deletion
    def backspace(self) -> None:
        if self.cmd is not None:
            self.cmd_backspace()
            return
        if self.delete_selection():
            return
        row, i = self.row, self.idx
        if i > 0:
            n = row.children[i - 1]
            slots = n.slots()
            if slots and any(s.children for s in slots):
                self._enter_end(slots[-1])
                self.version += 1
                return
            self.push_undo()
            del row.children[i - 1]
            self.idx -= 1
            self._changed()
            return
        owner = row.owner
        if owner is None:
            return
        self.push_undo()
        self._unwrap(owner, row)
        self._changed()

    def delete(self) -> None:
        if self.cmd is not None:
            self.commit_cmd()
        if self.delete_selection():
            return
        row, i = self.row, self.idx
        if i < len(row.children):
            n = row.children[i]
            slots = n.slots()
            if slots and any(s.children for s in slots):
                self._enter_start(slots[0])
                self.version += 1
                return
            self.push_undo()
            del row.children[i]
            self._changed()
            return
        owner = row.owner
        if owner is None:
            return
        if not any(s.children for s in owner.slots()):
            self.push_undo()
            self._before(owner)
            del self.row.children[self.idx]
            self._changed()
        else:
            self.move_right()

    def _unwrap(self, owner, row: Row) -> None:
        """Backspace at the start of a slot dissolves the structure,
        keeping everything that was typed into it."""
        parent = owner.parent
        k = _index_of(parent.children, owner)
        if isinstance(owner, Matrix):
            cells = owner.slots()
            ci = _index_of(cells, row)
            if ci > 0:
                self._enter_end(cells[ci - 1])
                return
            if any(c.children for c in cells):
                self.row, self.idx = parent, k
                return
            del parent.children[k]
            self.row, self.idx = parent, k
            return
        slots = owner.slots()
        if isinstance(owner, Scripts):
            # Deleting one script keeps the other.
            content = list(row.children)
            if owner.sub is row:
                owner.sub = None
            else:
                owner.sup = None
            if owner.slots():
                parent.children[k + 1:k + 1] = content
                self.row, self.idx = parent, k + 1
            else:
                parent.children[k:k + 1] = content
                self.row, self.idx = parent, k
            return
        before = []
        for s in slots:
            if s is row:
                break
            before.extend(s.children)
        content = []
        for s in slots:
            content.extend(s.children)
        parent.children[k:k + 1] = content
        self.row, self.idx = parent, k + len(before)

    # ---- movement
    def move_left(self, select=False) -> None:
        self.commit_cmd_if_any()
        if select:
            a = self.anchor or (self.row, self.idx)
            if self.idx > 0:
                self.idx -= 1
            elif self.row.owner is not None:
                self._before(self.row.owner)
            self.set_selection(a[0], a[1], self.row, self.idx)
            return
        if self.has_selection():
            _, i, _ = self.selection()
            self.idx, self.anchor = i, None
            return
        self.anchor = None
        if self.idx > 0:
            n = self.row.children[self.idx - 1]
            slots = n.slots()
            if slots:
                self._enter_end(slots[-1])
            else:
                self.idx -= 1
            return
        owner = self.row.owner
        if owner is None:
            return
        slots = owner.slots()
        k = _index_of(slots, self.row)
        if k > 0 and not isinstance(owner, Scripts):
            self._enter_end(slots[k - 1])
        else:
            self._before(owner)

    def move_right(self, select=False) -> None:
        self.commit_cmd_if_any()
        if select:
            a = self.anchor or (self.row, self.idx)
            if self.idx < len(self.row.children):
                self.idx += 1
            elif self.row.owner is not None:
                self._after(self.row.owner)
            self.set_selection(a[0], a[1], self.row, self.idx)
            return
        if self.has_selection():
            _, _, j = self.selection()
            self.idx, self.anchor = j, None
            return
        self.anchor = None
        if self.idx < len(self.row.children):
            n = self.row.children[self.idx]
            slots = n.slots()
            if slots:
                self._enter_start(slots[0])
            else:
                self.idx += 1
            return
        owner = self.row.owner
        if owner is None:
            return
        slots = owner.slots()
        k = _index_of(slots, self.row)
        if k < len(slots) - 1 and not isinstance(owner, Scripts):
            self._enter_start(slots[k + 1])
        else:
            self._after(owner)

    def home(self, select=False) -> None:
        self._jump(0, select)

    def end(self, select=False) -> None:
        self._jump(len(self.row.children), select)

    def _jump(self, idx, select) -> None:
        self.commit_cmd_if_any()
        a = self.anchor or (self.row, self.idx)
        self.idx = idx
        if select:
            self.anchor = a if a[0] is self.row else (self.row, a[1])
        else:
            self.anchor = None

    def move_vertical(self, up: bool) -> bool:
        """Move to the slot above/below (numerator/denominator, sup/sub,
        limits, matrix rows). Returns False when there is none."""
        self.commit_cmd_if_any()
        self.anchor = None
        row = self.row
        frac_idx = self.idx
        while row.owner is not None:
            o = row.owner
            target = None
            if isinstance(o, Frac):
                if up and row is o.den:
                    target = o.num
                elif not up and row is o.num:
                    target = o.den
            elif isinstance(o, Scripts):
                if up and row is o.sub and o.sup is not None:
                    target = o.sup
                elif not up and row is o.sup and o.sub is not None:
                    target = o.sub
            elif isinstance(o, BigOp):
                if up and row is o.lower and o.upper is not None:
                    target = o.upper
                elif not up and row is o.upper and o.lower is not None:
                    target = o.lower
            elif isinstance(o, Matrix):
                for ri, r in enumerate(o.rows):
                    for ci, c in enumerate(r):
                        if c is row:
                            rj = ri - 1 if up else ri + 1
                            if 0 <= rj < len(o.rows):
                                target = o.rows[rj][ci]
            elif isinstance(o, Sqrt) and o.index is not None:
                if up and row is o.body:
                    target = o.index
                elif not up and row is o.index:
                    target = o.body
            if target is not None:
                self.row = target
                self.idx = min(frac_idx, len(target.children))
                return True
            frac_idx = _index_of(o.parent.children, o)
            row = o.parent
        # From the base row, step into an adjacent structure's slot.
        ch = self.row.children
        for n in (ch[self.idx] if self.idx < len(ch) else None,
                  ch[self.idx - 1] if self.idx else None):
            if isinstance(n, Frac):
                self._enter_start(n.num if up else n.den)
                return True
            if isinstance(n, Scripts):
                r = n.sup if up else n.sub
                if r is not None:
                    self._enter_start(r)
                    return True
        return False

    def next_slot(self, forward=True) -> None:
        """Tab: jump to the next empty slot (wrapping); when every slot is
        filled, step out of the current structure."""
        self.commit_cmd_if_any()
        self.anchor = None
        stops = _empty_stops(self.root)
        if stops:
            here = self._order_key(self.row, self.idx)
            keys = sorted(((self._order_key(r, i), r, i) for r, i in stops),
                          key=lambda k: k[0])
            if forward:
                later = [k for k in keys if k[0] > here]
                pick = later[0] if later else keys[0]
            else:
                earlier = [k for k in keys if k[0] < here]
                pick = earlier[-1] if earlier else keys[-1]
            _, self.row, self.idx = pick
            return
        owner = self.row.owner
        if owner is None:
            return
        slots = owner.slots()
        k = _index_of(slots, self.row)
        if forward and k < len(slots) - 1:
            self._enter_start(slots[k + 1])
        elif not forward and k > 0:
            self._enter_end(slots[k - 1])
        elif forward:
            self._after(owner)
        else:
            self._before(owner)

    def _order_key(self, row: Row, idx: int) -> tuple:
        key = []
        r = row
        tail = [idx]
        while r.owner is not None:
            o = r.owner
            key.append((_index_of(o.parent.children, o),
                        _index_of(o.slots(), r)))
            r = o.parent
        flat = []
        for ni, si in reversed(key):
            flat += [ni, si]
        return tuple(flat + tail)

    # ---- matrices
    def matrix_add_row(self) -> bool:
        row = self.row
        while row.owner is not None and not isinstance(row.owner, Matrix):
            row = row.owner.parent
        m = row.owner
        if not isinstance(m, Matrix):
            return False
        self.push_undo()
        ri = next(i for i, r in enumerate(m.rows)
                  if any(c is row for c in r))
        new = [Row() for _ in range(m.ncols())]
        m.rows.insert(ri + 1, new)
        self._changed()
        self._enter_start(new[0])
        return True

    def matrix_add_col(self) -> bool:
        row = self.row
        while row.owner is not None and not isinstance(row.owner, Matrix):
            row = row.owner.parent
        m = row.owner
        if not isinstance(m, Matrix):
            return False
        self.push_undo()
        ci = 0
        for r in m.rows:
            for j, c in enumerate(r):
                if c is row:
                    ci = j
        for r in m.rows:
            r.insert(ci + 1, Row())
        self._changed()
        self._enter_start(next(r[ci + 1] for r in m.rows
                               if any(c is row for c in r)))
        return True

    # ---- clipboard helpers
    def selection_latex(self) -> str:
        nodes = self.selected_nodes()
        return to_latex(Row(nodes)) if nodes else ""

    def paste_latex(self, latex: str) -> None:
        nodes = list(parse_latex(latex).children)
        self.commit_cmd_if_any()
        self.push_undo()
        self._take_selection()
        self._insert(nodes)
        self._changed()


def _first_empty(nodes: list):
    """First empty slot Row (or Placeholder) within *nodes*."""
    for n in nodes:
        if isinstance(n, Placeholder):
            return n
        for s in n.slots():
            if not s.children:
                return s
            hit = _first_empty(s.children)
            if hit is not None:
                return hit
    return None


def _empty_stops(root: Row) -> list[tuple[Row, int]]:
    out = []
    for r in walk_rows(root):
        if r is not root and not r.children:
            out.append((r, 0))
        for i, n in enumerate(r.children):
            if isinstance(n, Placeholder):
                out.append((r, i))
    return out


def count_empty(root: Row) -> int:
    return len(_empty_stops(root))
