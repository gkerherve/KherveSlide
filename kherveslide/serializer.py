"""Serialize a WYSIWYG :class:`~kherveslide.model.Deck` to LaTeX.

Absolute placement uses the ``textpos`` package in ``absolute,overlay``
mode. The grid modules are bound to the whole slide::

    \\setlength{\\TPHorizModule}{\\paperwidth}
    \\setlength{\\TPVertModule}{\\paperheight}
    \\textblockorigin{0pt}{0pt}

so the model's ``0..1`` fractions drop straight into the (unstarred)
``textblock`` whose width and coordinates are both in module units::

    \\begin{textblock}{<w>}(<x>,<y>)   % w,x,y are fractions of the slide
        ...
    \\end{textblock}

A box at ``x=0.25`` sits a quarter across, ``w=0.5`` is half the slide
wide — exactly what the canvas drew. Frames are ``[plain]`` so the
theme's title bars / headlines / footlines don't fight the absolute
layout; the user composes the slide entirely from boxes.
"""
from __future__ import annotations

from .model import Deck, Slide, SlideText, SlidePicture


def _hex_to_rgb_arg(hex_color: str) -> str:
    h = (hex_color or "").lstrip("#").strip()
    if len(h) != 6:
        return ""
    try:
        int(h, 16)
    except ValueError:
        return ""
    return h.upper()


_ASPECT_OPTS = {
    "169": "aspectratio=169",
    "1610": "aspectratio=1610",
    "43": "",            # beamer's native default
    "32": "aspectratio=32",
    "54": "aspectratio=54",
    "141": "aspectratio=141",
}


def _fmt(v: float) -> str:
    """Trim a fraction to 4 dp without trailing zeros."""
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def _styled_text(obj: SlideText) -> str:
    """The inner (font/colour/weight/alignment-styled) content of a text
    box, sized to the block width."""
    body = obj.text or ""
    if obj.bold:
        body = f"\\textbf{{{body}}}"
    if obj.italic:
        body = f"\\textit{{{body}}}"
    color = _hex_to_rgb_arg(obj.color)
    if color and color != "000000":
        body = f"\\textcolor[HTML]{{{color}}}{{{body}}}"
    align_cmd = {"center": "\\centering", "right": "\\raggedleft",
                 "left": "\\raggedright"}.get(obj.align, "\\raggedright")
    lead = int(round(obj.font_pt * 1.2))
    sized = f"\\fontsize{{{obj.font_pt}}}{{{lead}}}\\selectfont"
    return f"{align_cmd}{sized} {body}"


def _serialize_text(obj: SlideText) -> str:
    content = _styled_text(obj)
    fill = _hex_to_rgb_arg(obj.fill)
    if fill:
        inner = (f"\\colorbox[HTML]{{{fill}}}{{\\begin{{minipage}}{{\\linewidth}}"
                 f"{content}\\end{{minipage}}}}")
    else:
        inner = f"{{{content}\\par}}"
    return (f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"{inner}\n"
            f"\\end{{textblock}}")


def _serialize_picture(obj: SlidePicture) -> str:
    if not obj.path:
        return ""
    path = obj.path.replace("\\", "/")
    if obj.keep_aspect:
        opts = (f"width={_fmt(obj.w)}\\paperwidth,"
                f"height={_fmt(obj.h)}\\paperheight,keepaspectratio")
    else:
        opts = (f"width={_fmt(obj.w)}\\paperwidth,"
                f"height={_fmt(obj.h)}\\paperheight")
    return (f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"\\includegraphics[{opts}]{{{path}}}\n"
            f"\\end{{textblock}}")


def _serialize_slide(slide: Slide) -> str:
    parts = ["\\begin{frame}[plain]"]
    bg = _hex_to_rgb_arg(slide.bg)
    if bg:
        # Full-slide coloured panel behind everything else.
        parts.append(
            "\\begin{textblock}{1}(0,0)\n"
            f"\\colorbox[HTML]{{{bg}}}{{\\rule{{0pt}}{{\\paperheight}}"
            "\\hspace{\\paperwidth}}\n"
            "\\end{textblock}")
    for obj in slide.objects:
        if isinstance(obj, SlideText):
            parts.append(_serialize_text(obj))
        elif isinstance(obj, SlidePicture):
            block = _serialize_picture(obj)
            if block:
                parts.append(block)
    parts.append("\\end{frame}")
    return "\n".join(parts)


def serialize_deck(deck: Deck) -> str:
    aspect = _ASPECT_OPTS.get(deck.aspect, "aspectratio=169")
    class_opts = f"[{aspect}]" if aspect else ""

    lines = [
        f"\\documentclass{class_opts}{{beamer}}",
        f"\\usetheme{{{deck.theme or 'default'}}}",
    ]
    if deck.color_theme:
        lines.append(f"\\usecolortheme{{{deck.color_theme}}}")
    lines += [
        "\\usepackage[absolute,overlay]{textpos}",
        "\\usepackage{graphicx}",
        "\\setlength{\\TPHorizModule}{\\paperwidth}",
        "\\setlength{\\TPVertModule}{\\paperheight}",
        "\\textblockorigin{0pt}{0pt}",
        "\\setbeamertemplate{navigation symbols}{}",
    ]
    if deck.title:
        lines.append(f"\\title{{{deck.title}}}")
    if deck.author:
        lines.append(f"\\author{{{deck.author}}}")
    lines.append("\\begin{document}")
    for slide in deck.slides:
        lines.append(_serialize_slide(slide))
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n"
