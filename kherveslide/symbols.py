"""Catalogue of common LaTeX symbols, grouped for the picker dialog.

Each entry is `(latex, glyph)` where `latex` is what we insert into the
document (as an inline math span or a raw character) and `glyph` is the
on-screen label so users can recognise the symbol at a glance.

If the glyph is the literal LaTeX command (because the symbol isn't a
single Unicode codepoint or because we want the LaTeX form visible),
the entry uses the same string for both fields.
"""
from __future__ import annotations


# Each group is (group name, list of (latex, glyph) pairs).
SYMBOL_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Greek (lowercase)", [
        (r"\alpha", "α"), (r"\beta", "β"), (r"\gamma", "γ"),
        (r"\delta", "δ"), (r"\epsilon", "ε"), (r"\varepsilon", "ɛ"),
        (r"\zeta", "ζ"), (r"\eta", "η"), (r"\theta", "θ"),
        (r"\vartheta", "ϑ"), (r"\iota", "ι"), (r"\kappa", "κ"),
        (r"\lambda", "λ"), (r"\mu", "μ"), (r"\nu", "ν"),
        (r"\xi", "ξ"), (r"\pi", "π"), (r"\varpi", "ϖ"),
        (r"\rho", "ρ"), (r"\varrho", "ϱ"), (r"\sigma", "σ"),
        (r"\varsigma", "ς"), (r"\tau", "τ"), (r"\upsilon", "υ"),
        (r"\phi", "φ"), (r"\varphi", "ϕ"), (r"\chi", "χ"),
        (r"\psi", "ψ"), (r"\omega", "ω"),
    ]),
    ("Greek (uppercase)", [
        (r"\Gamma", "Γ"), (r"\Delta", "Δ"), (r"\Theta", "Θ"),
        (r"\Lambda", "Λ"), (r"\Xi", "Ξ"), (r"\Pi", "Π"),
        (r"\Sigma", "Σ"), (r"\Upsilon", "Υ"), (r"\Phi", "Φ"),
        (r"\Psi", "Ψ"), (r"\Omega", "Ω"),
    ]),
    ("Operators", [
        (r"\pm", "±"), (r"\mp", "∓"), (r"\times", "×"),
        (r"\div", "÷"), (r"\cdot", "·"), (r"\ast", "∗"),
        (r"\star", "⋆"), (r"\circ", "∘"), (r"\bullet", "•"),
        (r"\oplus", "⊕"), (r"\ominus", "⊖"), (r"\otimes", "⊗"),
        (r"\oslash", "⊘"), (r"\odot", "⊙"), (r"\dagger", "†"),
        (r"\ddagger", "‡"),
    ]),
    ("Relations", [
        (r"\leq", "≤"), (r"\geq", "≥"), (r"\neq", "≠"),
        (r"\approx", "≈"), (r"\equiv", "≡"), (r"\sim", "∼"),
        (r"\simeq", "≃"), (r"\cong", "≅"), (r"\propto", "∝"),
        (r"\ll", "≪"), (r"\gg", "≫"), (r"\subset", "⊂"),
        (r"\supset", "⊃"), (r"\subseteq", "⊆"), (r"\supseteq", "⊇"),
        (r"\in", "∈"), (r"\notin", "∉"), (r"\ni", "∋"),
        (r"\perp", "⊥"), (r"\parallel", "∥"), (r"\mid", "∣"),
    ]),
    ("Arrows", [
        (r"\to", "→"), (r"\leftarrow", "←"), (r"\rightarrow", "→"),
        (r"\Rightarrow", "⇒"), (r"\Leftarrow", "⇐"),
        (r"\Leftrightarrow", "⇔"), (r"\leftrightarrow", "↔"),
        (r"\uparrow", "↑"), (r"\downarrow", "↓"),
        (r"\Uparrow", "⇑"), (r"\Downarrow", "⇓"),
        (r"\mapsto", "↦"), (r"\hookrightarrow", "↪"),
        (r"\longrightarrow", "⟶"), (r"\longleftarrow", "⟵"),
    ]),
    ("Calculus", [
        (r"\int", "∫"), (r"\iint", "∬"), (r"\iiint", "∭"),
        (r"\oint", "∮"), (r"\sum", "∑"), (r"\prod", "∏"),
        (r"\coprod", "∐"), (r"\partial", "∂"), (r"\nabla", "∇"),
        (r"\infty", "∞"), (r"\sqrt{x}", "√x"), (r"\frac{a}{b}", "a/b"),
        (r"\lim", "lim"), (r"\sup", "sup"), (r"\inf", "inf"),
    ]),
    ("Logic & sets", [
        (r"\forall", "∀"), (r"\exists", "∃"), (r"\nexists", "∄"),
        (r"\neg", "¬"), (r"\land", "∧"), (r"\lor", "∨"),
        (r"\cap", "∩"), (r"\cup", "∪"), (r"\setminus", "∖"),
        (r"\emptyset", "∅"), (r"\varnothing", "⌀"),
        (r"\mathbb{R}", "ℝ"), (r"\mathbb{N}", "ℕ"),
        (r"\mathbb{Z}", "ℤ"), (r"\mathbb{Q}", "ℚ"),
        (r"\mathbb{C}", "ℂ"),
    ]),
    ("Misc & punctuation", [
        (r"\degree", "°"), (r"\angle", "∠"), (r"\triangle", "△"),
        (r"\square", "□"), (r"\diamond", "⋄"),
        (r"\dots", "…"), (r"\cdots", "⋯"), (r"\vdots", "⋮"),
        (r"\ddots", "⋱"), (r"\hbar", "ℏ"), (r"\ell", "ℓ"),
        (r"\Re", "ℜ"), (r"\Im", "ℑ"), (r"\aleph", "ℵ"),
        (r"\copyright", "©"), (r"\textregistered", "®"),
        (r"\texttrademark", "™"),
    ]),
    ("Accents (over a letter)", [
        (r"\hat{a}", "â"), (r"\bar{a}", "ā"), (r"\tilde{a}", "ã"),
        (r"\vec{a}", "→a"), (r"\dot{a}", "ȧ"), (r"\ddot{a}", "ä"),
        (r"\acute{a}", "á"), (r"\grave{a}", "à"),
        (r"\check{a}", "ǎ"), (r"\breve{a}", "ă"),
    ]),
    # \Kstroke renders a capital K with a diagonal stroke through the
    # right leg — a Breton spelling abbreviation the author uses for
    # surnames like "Kerherve". The macro is provided by KherveTeX in
    # the preamble (see serializer._KSTROKE_PROVIDE), so users get the
    # glyph without having to copy a \newcommand into every document.
    ("KherveTeX", [
        (r"\Kstroke", "Ꝁ"),
    ]),
]


def all_symbols() -> list[tuple[str, str]]:
    """Flat list of every (latex, glyph) entry across all groups."""
    out: list[tuple[str, str]] = []
    for _, items in SYMBOL_GROUPS:
        out.extend(items)
    return out


# Symbols whose LaTeX is a TEXT-mode macro (i.e. would break or render
# badly inside $...$). The Symbol picker inserts these as InlineRaw via
# DocumentEditor.insert_raw_inline_with instead of wrapping in inline
# math. \Kstroke uses \hspace/\raisebox/\rotatebox — all valid only in
# (or most naturally used in) text mode.
TEXT_MODE_SYMBOLS = frozenset({r"\Kstroke"})


def is_text_mode_symbol(latex: str) -> bool:
    return latex in TEXT_MODE_SYMBOLS
