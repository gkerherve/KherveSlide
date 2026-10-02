"""Chemical-equation snippets and preview rendering for the chemistry editor.

Documents carry chemistry as ordinary ``MathInline`` / ``MathBlock`` nodes
whose latex is ``\\ce{...}`` (the mhchem package).  Nothing new is added to
the document model — mhchem is a math-mode macro, so the existing math
serialisation already emits it correctly.

The live preview is the awkward part.  matplotlib's mathtext renders the
preview panes everywhere else in the app, and it has no idea what ``\\ce``
means, so :func:`ce_to_mathtext` hand-translates the mhchem body into
something mathtext can draw.  It is deliberately approximate: it exists to
show the user roughly what they are typing, not to replace tectonic.  Real
output always goes through LaTeX.  Anything it cannot parse degrades to a
"cannot render" message while the LaTeX still inserts fine.
"""
from __future__ import annotations

import re as _re
from io import BytesIO as _BytesIO


# The tab-navigable empty slot.  It must be `$\square$`, not the bare
# `\square` the equation builder uses: mhchem parses the \ce{} body itself
# and aborts with "Unexpected input character" on a raw control sequence.
# Wrapping it in $...$ hands it to mhchem as an opaque math island, so a
# template with unfilled slots still compiles.
PLACEHOLDER = r"$\square$"

_S = PLACEHOLDER

# Each entry is `(ce_body_fragment, preview_label)`.  The fragment is what
# gets inserted into the editor field, which holds the *body* of \ce{...} —
# users never type the \ce wrapper themselves.
CHEM_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Reactions", [
        (f"{_S} -> {_S}", "A → B"),
        (f"{_S} + {_S} -> {_S}", "A + B → C"),
        (f"{_S} + {_S} -> {_S} + {_S}", "A + B → C + D"),
        (f"{_S} + {_S} <=> {_S} + {_S}", "A + B ⇌ C + D"),
        (r"2H2 + O2 -> 2H2O", "2H₂ + O₂ → 2H₂O"),
        (r"CH4 + 2O2 -> CO2 + 2H2O", "combustion"),
    ]),
    ("Arrows", [
        (r" -> ", "→"),
        (r" <- ", "←"),
        (r" <=> ", "⇌"),
        (r" <-> ", "↔"),
        (f" ->[{_S}] ", "→ over"),
        (f" ->[{_S}][{_S}] ", "→ over/under"),
    ]),
    ("States", [
        (r"(aq)", "(aq)"),
        (r"(s)", "(s)"),
        (r"(l)", "(l)"),
        (r"(g)", "(g)"),
        (r" v", "↓ precip."),
        (r" ^", "↑ gas"),
    ]),
    ("Charges", [
        (r"^+", "x⁺"),
        (r"^-", "x⁻"),
        (r"^2+", "x²⁺"),
        (r"^2-", "x²⁻"),
        (r"^3+", "x³⁺"),
        (r"e-", "e⁻"),
    ]),
    ("Species", [
        (r"H2O", "H₂O"),
        (r"CO2", "CO₂"),
        (r"H2SO4", "H₂SO₄"),
        (r"NH3", "NH₃"),
        (r"OH-", "OH⁻"),
        (r"SO4^2-", "SO₄²⁻"),
    ]),
    ("Bonds", [
        (f"{_S}-{_S}", "A–B"),
        (f"{_S}={_S}", "A=B"),
        (f"{_S}#{_S}", "A≡B"),
        (r"CuSO4.5H2O", "hydrate"),
        (r"^{227}_{90}Th+", "nuclide"),
        (r"^{13}C", "isotope"),
    ]),
    ("Conditions", [
        (f" ->[$\\Delta$] ", "heat Δ"),
        (f" ->[$h\\nu$] ", "light hν"),
        (r" ->[\text{cat.}] ", "catalyst"),
        (r" ->[\text{Pt}] ", "Pt catalyst"),
        (r" ->[H+] ", "acid"),
        (f" ->[{_S}][{_S}] ", "above/below"),
    ]),
    ("Acids & bases", [
        (r"HCl + NaOH -> NaCl + H2O", "neutralisation"),
        (r"2H2O <=> H3O+ + OH-", "autoionisation"),
        (r"NH3 + H2O <=> NH4+ + OH-", "weak base"),
        (r"CH3COOH <=> CH3COO- + H+", "weak acid"),
        (r"H3O+", "hydronium"),
        (r"NH4+", "ammonium"),
    ]),
    ("Redox", [
        (r"Zn -> Zn^2+ + 2e-", "oxidation"),
        (r"Cu^2+ + 2e- -> Cu", "reduction"),
        (r"Fe^2+ -> Fe^3+ + e-", "Fe(II)→Fe(III)"),
        (r"2H+ + 2e- -> H2", "H+ reduction"),
        (r"O2 + 4H+ + 4e- -> 2H2O", "O2 reduction"),
        (r"MnO4- + 8H+ + 5e- -> Mn^2+ + 4H2O", "permanganate"),
    ]),
    ("Nuclear", [
        (r"^{238}_{92}U -> ^{234}_{90}Th + ^{4}_{2}He", "α decay"),
        (r"^{14}_{6}C -> ^{14}_{7}N + e-", "β decay"),
        (r"^{1}_{0}n", "neutron"),
        (r"^{1}_{1}p", "proton"),
        (r"^{4}_{2}He", "α particle"),
        (r"^{2}_{1}H", "deuterium"),
    ]),
]


def all_templates() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for _, items in CHEM_GROUPS:
        out.extend(items)
    return out


# ---------------------------------------------------------------- transpiler

# Longest first — "<=>" must win over "<-" and "->".
_ARROWS: list[tuple[str, str]] = [
    ("<=>>", r"\rightleftharpoons"),
    ("<<=>", r"\rightleftharpoons"),
    ("<=>", r"\rightleftharpoons"),
    ("<->", r"\leftrightarrow"),
    ("->", r"\rightarrow"),
    ("<-", r"\leftarrow"),
]

_BOND = {"=": "=", "#": r"\equiv ", "~": "-", "-": "-"}

# ^2-, ^{2+}, ^+, ^- ... the charge that follows a formula.
_CHARGE_RE = _re.compile(r"\^\{?([0-9]*[+-]?)\}?")
# A leading stoichiometric coefficient: 2H2O, 1.5O2 — but not the 2 in H2O.
_COEFF_RE = _re.compile(r"\d+(?:\.\d+)?(?=[A-Za-z(\\])")
_MACRO_RE = _re.compile(r"\\[A-Za-z]+")


def _starts_arrow(text: str, i: int) -> bool:
    return any(text.startswith(lit, i) for lit, _ in _ARROWS)


def _species_to_mathtext(tok: str) -> str:
    """Translate one formula token (``2H2O``, ``SO4^2-``, ``(aq)``)."""
    out: list[str] = []
    i, n = 0, len(tok)

    m = _COEFF_RE.match(tok)
    if m:
        out.append(m.group(0))
        i = m.end()

    while i < n:
        c = tok[i]
        if c == "\\":
            m = _MACRO_RE.match(tok, i)
            if m:
                out.append(m.group(0) + " ")
                i = m.end()
                continue
            i += 1
        elif c.isalpha():
            j = i
            while j < n and tok[j].isalpha():
                j += 1
            out.append(r"\mathrm{" + tok[i:j] + "}")
            i = j
        elif c.isdigit():
            j = i
            while j < n and tok[j].isdigit():
                j += 1
            out.append("_{" + tok[i:j] + "}")
            i = j
        elif c == "^":
            m = _CHARGE_RE.match(tok, i)
            if m and m.group(1):
                out.append("^{" + m.group(1) + "}")
                i = m.end()
            else:
                i += 1
        elif c in "+-" and out:
            # A bare +/- trailing a formula is a charge (Na+), but between
            # two atoms it is a bond (C-C).
            nxt = tok[i + 1] if i + 1 < n else ""
            if c == "-" and (nxt.isalpha() or nxt == "\\"):
                out.append("-")
            else:
                out.append("^{" + c + "}")
            i += 1
        elif c in "()":
            out.append(c)
            i += 1
        elif c == ".":
            # Hydrate dot: the digits after it are a coefficient, not a
            # subscript — CuSO4.5H2O is "five waters", not "H-sub-5".
            out.append(r"\cdot ")
            i += 1
            m = _COEFF_RE.match(tok, i)
            if m:
                out.append(m.group(0))
                i = m.end()
        elif c in _BOND:
            out.append(_BOND[c])
            i += 1
        elif c == "_":
            m = _re.match(r"_\{?(\d+)\}?", tok[i:])
            if m:
                out.append("_{" + m.group(1) + "}")
                i += m.end()
            else:
                i += 1
        elif c == "$":
            i += 1
        else:
            i += 1
    return "".join(out)


def ce_to_mathtext(body: str) -> str:
    """Best-effort mhchem ``\\ce{}`` body → mathtext-renderable LaTeX.

    Handles coefficients, subscripts, charges, states, bonds, hydrates and
    the common arrows.  Arrow annotations (``->[cat]``) are dropped, since
    mathtext has no ``\\xrightarrow``.
    """
    body = body.strip()
    if not body:
        return ""

    parts: list[str] = []
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c.isspace():
            i += 1
            continue

        hit = next(((lit, t) for lit, t in _ARROWS if body.startswith(lit, i)), None)
        if hit is not None:
            i += len(hit[0])
            while i < n and body[i] == "[":  # drop ->[above][below]
                depth = 0
                while i < n:
                    if body[i] == "[":
                        depth += 1
                    elif body[i] == "]":
                        depth -= 1
                        if depth == 0:
                            i += 1
                            break
                    i += 1
            parts.append(hit[1])
            continue

        if c == "+":
            parts.append("+")
            i += 1
            continue

        # mhchem writes precipitate/gas as a lone "v"/"^" after a formula.
        if c in "v^" and (i + 1 >= n or body[i + 1].isspace()):
            parts.append(r"\downarrow" if c == "v" else r"\uparrow")
            i += 1
            continue

        # A "+" met inside a formula is a charge, never the plus operator:
        # mhchem requires whitespace around the operator, and whitespace
        # already ends this scan.
        j = i
        while j < n and not (body[j].isspace() or _starts_arrow(body, j)):
            j += 1
        parts.append(_species_to_mathtext(body[i:j]))
        i = j

    return r"\;".join(p for p in parts if p)


# ---------------------------------------------------------------- previews

_PREVIEW_CACHE: dict[str, object] = {}
_LIVE_CACHE: dict[str, object] = {}


def _render(body: str, cache: dict, figsize, dpi: int, font_size: int, pad: float):
    from PySide6.QtGui import QImage, QPixmap

    if body in cache:
        return cache[body]
    try:
        from matplotlib.figure import Figure as MplFigure
    except ImportError:
        cache[body] = None
        return None

    tex = ce_to_mathtext(body).replace(r"\square", r"\bullet")
    if not tex:
        cache[body] = None
        return None
    try:
        fig = MplFigure(figsize=figsize, dpi=dpi)
        fig.patch.set_alpha(0)
        fig.text(0.5, 0.5, f"${tex}$", fontsize=font_size,
                 ha="center", va="center", math_fontfamily="cm")
        buf = _BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight",
                    pad_inches=pad, transparent=True)
        buf.seek(0)
        img = QImage()
        img.loadFromData(buf.read())
        if img.isNull():
            cache[body] = None
            return None
        px = QPixmap.fromImage(img)
        cache[body] = px
        return px
    except Exception:
        cache[body] = None
        return None


def render_template_preview(body: str, font_size: int = 14):
    """Small QPixmap for a palette button icon, or None."""
    return _render(body, _PREVIEW_CACHE, (2.4, 0.35), 120, font_size, 0.02)


def render_live_preview(body: str, font_size: int = 20):
    """Large QPixmap for the live preview pane, or None."""
    return _render(body, _LIVE_CACHE, (5.0, 0.5), 150, font_size, 0.05)


def wrap_ce(body: str) -> str:
    """Wrap a formula body in ``\\ce{}`` unless it already is one."""
    body = body.strip()
    if not body:
        return ""
    if body.startswith(r"\ce{") and body.endswith("}"):
        return body
    return r"\ce{" + body + "}"


def unwrap_ce(latex: str) -> str | None:
    """The body of a single ``\\ce{...}``, or None if *latex* isn't one.

    Used to decide whether a double-clicked equation should reopen the
    chemistry editor rather than the equation builder.
    """
    s = (latex or "").strip()
    if not (s.startswith(r"\ce{") and s.endswith("}")):
        return None
    depth = 0
    for i, ch in enumerate(s[3:], start=3):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                # Only a single \ce{} spanning the whole string counts;
                # "\ce{A} + \ce{B}" is two of them, not one body.
                return s[4:i] if i == len(s) - 1 else None
    return None
