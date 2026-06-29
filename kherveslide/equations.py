"""Templated equation snippets grouped for the equation-builder palette.

Each entry is `(latex_template, preview)`. The latex template is what
the editor inserts at the cursor; the preview is what the palette
button shows. We use the literal box character (□) as a placeholder
inside templates so users can quickly tab through and replace each
slot with their own content.
"""
from __future__ import annotations

import re as _re
from io import BytesIO as _BytesIO


EQUATION_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Fractions & roots", [
        (r"\frac{\square}{\square}", "□/□"),
        (r"\tfrac{\square}{\square}", "small □/□"),
        (r"\dfrac{\square}{\square}", "display □/□"),
        (r"\sqrt{\square}", "√□"),
        (r"\sqrt[\square]{\square}", "ⁿ√□"),
        (r"\binom{\square}{\square}", "(□ □)"),
    ]),
    ("Sums, products, limits", [
        (r"\sum_{\square}^{\square} \square", "∑_□^□"),
        (r"\sum_{i=1}^{n} \square", "∑ᵢ₌₁ⁿ"),
        (r"\prod_{\square}^{\square} \square", "∏_□^□"),
        (r"\lim_{\square \to \square} \square", "lim_□→□"),
        (r"\liminf_{\square \to \square} \square", "lim inf"),
        (r"\limsup_{\square \to \square} \square", "lim sup"),
    ]),
    ("Integrals", [
        (r"\int_{\square}^{\square} \square \, d\square", "∫_□^□"),
        (r"\int \square \, d\square", "∫ □ d□"),
        (r"\iint_{\square} \square \, dA", "∬ dA"),
        (r"\iiint_{\square} \square \, dV", "∭ dV"),
        (r"\oint_{\square} \square \, d\square", "∮"),
        (r"\int_{-\infty}^{\infty} \square \, d\square", "∫_-∞^∞"),
    ]),
    ("Subscripts & superscripts", [
        (r"\square^{\square}", "x^□"),
        (r"\square_{\square}", "x_□"),
        (r"\square_{\square}^{\square}", "x_□^□"),
        (r"e^{\square}", "e^□"),
        (r"10^{\square}", "10^□"),
        (r"\square^{-1}", "x⁻¹"),
    ]),
    ("Derivatives", [
        (r"\frac{d\square}{d\square}", "d□/d□"),
        (r"\frac{d^{2}\square}{d\square^{2}}", "d²□/d□²"),
        (r"\frac{\partial \square}{\partial \square}", "∂□/∂□"),
        (r"\frac{\partial^{2} \square}{\partial \square^{2}}", "∂²□/∂□²"),
        (r"\nabla \square", "∇ □"),
        (r"\nabla^{2} \square", "∇² □"),
    ]),
    ("Greek inline", [
        (r"\alpha", "α"), (r"\beta", "β"), (r"\gamma", "γ"),
        (r"\Delta", "Δ"), (r"\theta", "θ"), (r"\lambda", "λ"),
        (r"\mu", "μ"), (r"\pi", "π"), (r"\sigma", "σ"),
        (r"\Sigma", "Σ"), (r"\phi", "φ"), (r"\omega", "ω"),
    ]),
    ("Vectors & matrices", [
        (r"\vec{\square}", "→x"),
        (r"\hat{\square}", "x̂"),
        (r"\bar{\square}", "x̄"),
        (r"\begin{pmatrix} \square & \square \\ \square & \square \end{pmatrix}", "(2×2)"),
        (r"\begin{bmatrix} \square & \square \\ \square & \square \end{bmatrix}", "[2×2]"),
        (r"\begin{vmatrix} \square & \square \\ \square & \square \end{vmatrix}", "|2×2|"),
    ]),
    ("Brackets", [
        (r"\left( \square \right)", "(□)"),
        (r"\left[ \square \right]", "[□]"),
        (r"\left\{ \square \right\}", "{□}"),
        (r"\left| \square \right|", "|□|"),
        (r"\left\| \square \right\|", "‖□‖"),
        (r"\left\langle \square \right\rangle", "⟨□⟩"),
        (r"\left\lfloor \square \right\rfloor", "⌊□⌋"),
        (r"\left\lceil \square \right\rceil", "⌈□⌉"),
    ]),
    ("Relations & operators", [
        (r"\square = \square", "□ = □"),
        (r"\square \approx \square", "□ ≈ □"),
        (r"\square \neq \square", "□ ≠ □"),
        (r"\square \leq \square", "□ ≤ □"),
        (r"\square \geq \square", "□ ≥ □"),
        (r"\square \propto \square", "□ ∝ □"),
        (r"\square \cdot \square", "□ · □"),
        (r"\square \times \square", "□ × □"),
    ]),
    ("Functions", [
        (r"\sin(\square)", "sin"),
        (r"\cos(\square)", "cos"),
        (r"\tan(\square)", "tan"),
        (r"\exp(\square)", "exp"),
        (r"\ln(\square)", "ln"),
        (r"\log_{\square}(\square)", "log"),
        (r"\arctan(\square)", "arctan"),
    ]),
    ("Display environments", [
        (r"\begin{equation}\n\square\n\end{equation}", "equation"),
        (r"\begin{align}\n\square &= \square \\\\\n\square &= \square\n\end{align}", "align"),
        (r"\begin{cases}\n\square & \text{if } \square \\\\\n\square & \text{otherwise}\n\end{cases}", "cases"),
    ]),
]


def all_templates() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for _, items in EQUATION_GROUPS:
        out.extend(items)
    return out


# ---- rendered template previews for the equation builder UI ----

_PREVIEW_CACHE: dict[str, object] = {}  # latex → QPixmap

_ENV_RE = _re.compile(
    r"\\begin\{(\w+\*?)\}(.*?)\\end\{\1\}", _re.DOTALL)


def render_template_preview(latex: str, font_size: int = 16):
    """Render a LaTeX template to a QPixmap for use as a button icon.

    Returns a QPixmap or None on failure. Results are cached in memory.
    """
    from PySide6.QtGui import QImage, QPixmap

    if latex in _PREVIEW_CACHE:
        return _PREVIEW_CACHE[latex]
    try:
        from matplotlib.figure import Figure as MplFigure
    except ImportError:
        _PREVIEW_CACHE[latex] = None
        return None

    raw = latex.strip()
    # Templates store literal two-char sequences \n for newlines.
    # Convert known environment delimiters so the env regex can match.
    for env in ("equation", "align", "gather", "multline",
                "cases", "pmatrix", "bmatrix", "vmatrix"):
        raw = raw.replace(f"\\begin{{{env}}}" + "\\n",
                          f"\\begin{{{env}}}\n")
        raw = raw.replace("\\n" + f"\\end{{{env}}}",
                          f"\n\\end{{{env}}}")
    # Also convert remaining standalone \n between content lines
    raw = raw.replace("\\n", "\n")
    # Strip \begin{...}\end{...} wrappers
    m = _ENV_RE.search(raw)
    if m:
        raw = m.group(2).strip()
    raw = raw.strip("$").strip()
    # Replace placeholder □ with a visible glyph mathtext supports
    raw = raw.replace(r"\square", r"\bullet")
    # Translate commands mathtext doesn't support
    raw = raw.replace("\\left", "")
    raw = raw.replace("\\right", "")
    raw = raw.replace("\\tfrac", "\\frac")
    raw = raw.replace("\\dfrac", "\\frac")
    raw = raw.replace("\\text{", "\\mathrm{")
    raw = raw.replace("\\operatorname{", "\\mathrm{")
    raw = raw.replace("\\displaystyle", "")
    raw = raw.replace("\\textstyle", "")
    raw = raw.replace("\\liminf", "\\lim\\inf")
    raw = raw.replace("\\limsup", "\\lim\\sup")
    # Handle multi-line: split on \\, strip &
    lines = _re.split(r"\\\\", raw)
    lines = [ln.replace("&", " ").strip() for ln in lines]
    lines = [ln for ln in lines if ln]
    if not lines:
        _PREVIEW_CACHE[latex] = None
        return None
    try:
        n = len(lines)
        line_height = 0.3
        fig_h = max(0.35, n * line_height)
        fig = MplFigure(figsize=(2.4, fig_h), dpi=120)
        fig.patch.set_alpha(0)
        for i, line in enumerate(lines):
            y = 1.0 - (i + 0.5) / n
            fig.text(0.5, y, f"${line}$", fontsize=font_size,
                     ha="center", va="center", math_fontfamily="cm")
        buf = _BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight",
                    pad_inches=0.02, transparent=True)
        buf.seek(0)
        img = QImage()
        img.loadFromData(buf.read())
        if img.isNull():
            _PREVIEW_CACHE[latex] = None
            return None
        px = QPixmap.fromImage(img)
        _PREVIEW_CACHE[latex] = px
        return px
    except Exception:
        _PREVIEW_CACHE[latex] = None
        return None


_LIVE_CACHE: dict[str, object] = {}


def render_live_preview(latex: str, font_size: int = 20):
    """Render LaTeX to a large QPixmap for the live equation editor.

    Same pipeline as ``render_template_preview`` but tuned for a bigger,
    higher-quality display.  Results are cached separately.
    """
    from PySide6.QtGui import QImage, QPixmap

    if latex in _LIVE_CACHE:
        return _LIVE_CACHE[latex]
    try:
        from matplotlib.figure import Figure as MplFigure
    except ImportError:
        _LIVE_CACHE[latex] = None
        return None

    raw = latex.strip()
    for env in ("equation", "align", "gather", "multline",
                "cases", "pmatrix", "bmatrix", "vmatrix"):
        raw = raw.replace(f"\\begin{{{env}}}" + "\\n",
                          f"\\begin{{{env}}}\n")
        raw = raw.replace("\\n" + f"\\end{{{env}}}",
                          f"\n\\end{{{env}}}")
    raw = raw.replace("\\n", "\n")
    m = _ENV_RE.search(raw)
    if m:
        raw = m.group(2).strip()
    raw = raw.strip("$").strip()
    raw = raw.replace(r"\square", r"\bullet")
    raw = raw.replace("\\left", "")
    raw = raw.replace("\\right", "")
    raw = raw.replace("\\tfrac", "\\frac")
    raw = raw.replace("\\dfrac", "\\frac")
    raw = raw.replace("\\text{", "\\mathrm{")
    raw = raw.replace("\\operatorname{", "\\mathrm{")
    raw = raw.replace("\\displaystyle", "")
    raw = raw.replace("\\textstyle", "")
    raw = raw.replace("\\liminf", "\\lim\\inf")
    raw = raw.replace("\\limsup", "\\lim\\sup")
    lines = _re.split(r"\\\\", raw)
    lines = [ln.replace("&", " ").strip() for ln in lines]
    lines = [ln for ln in lines if ln]
    if not lines:
        _LIVE_CACHE[latex] = None
        return None
    try:
        n = len(lines)
        line_height = 0.45
        fig_h = max(0.5, n * line_height)
        fig = MplFigure(figsize=(5.0, fig_h), dpi=150)
        fig.patch.set_alpha(0)
        for i, line in enumerate(lines):
            y = 1.0 - (i + 0.5) / n
            fig.text(0.5, y, f"${line}$", fontsize=font_size,
                     ha="center", va="center", math_fontfamily="cm")
        buf = _BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight",
                    pad_inches=0.05, transparent=True)
        buf.seek(0)
        img = QImage()
        img.loadFromData(buf.read())
        if img.isNull():
            _LIVE_CACHE[latex] = None
            return None
        px = QPixmap.fromImage(img)
        _LIVE_CACHE[latex] = px
        return px
    except Exception:
        _LIVE_CACHE[latex] = None
        return None
