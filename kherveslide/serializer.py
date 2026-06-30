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

from .model import (
    Deck, Slide, SlideText, SlidePicture, SlideTable, SlideLine,
    blend_over_white, TABLE_HEADER_BG, TABLE_HEADER_FG, TABLE_RULE,
    TABLE_CAPTION_FG,
)


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


def _text_inner(obj: SlideText) -> str:
    content = _styled_text(obj)
    fill = _hex_to_rgb_arg(obj.fill)
    if fill:
        return (f"\\colorbox[HTML]{{{fill}}}{{\\begin{{minipage}}{{\\linewidth}}"
                f"{content}\\end{{minipage}}}}")
    return f"{{{content}\\par}}"


def _serialize_text(obj: SlideText) -> str:
    return (f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"{_text_inner(obj)}\n"
            f"\\end{{textblock}}")


def _picture_graphic(obj: SlidePicture, rel: str = "\\paperwidth",
                     rel_h: str = "\\paperheight") -> str:
    path = obj.path.replace("\\", "/")
    opts = f"width={_fmt(obj.w)}{rel},height={_fmt(obj.h)}{rel_h}"
    if obj.keep_aspect:
        opts += ",keepaspectratio"
    graphic = f"\\includegraphics[{opts}]{{{path}}}"
    if obj.opacity < 1.0:
        graphic = f"\\transparent{{{_fmt(max(0.0, obj.opacity))}}}{graphic}"
    return graphic


def _serialize_picture(obj: SlidePicture) -> str:
    if not obj.path:
        return ""
    return (f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"{_picture_graphic(obj)}\n"
            f"\\end{{textblock}}")


def _table_inner(obj: SlideTable) -> str:
    rows = obj.rows or [[""]]
    ncols = max((len(r) for r in rows), default=1)
    sep = "|" if obj.border else ""
    colspec = sep + sep.join("l" for _ in range(ncols)) + sep
    rule = ("\\arrayrulecolor{ksTblRule}\\hline\n" if obj.border else "")
    body = []
    for i, row in enumerate(rows):
        cells = list(row) + [""] * (ncols - len(row))
        if i == 0 and obj.header:
            cells = [f"\\textcolor{{ksTblHeadFg}}{{\\textbf{{{c}}}}}"
                     for c in cells]
            line = "  \\rowcolor{ksTblHead}" + " & ".join(cells) + " \\\\"
        else:
            line = "  " + " & ".join(cells) + " \\\\"
        body.append(line)
    table = (f"\\begin{{tabular}}{{{colspec}}}\n{rule}"
             + ("\n" + rule).join(body)
             + f"\n{rule}\\end{{tabular}}")
    color = _hex_to_rgb_arg(obj.color)
    if color and color != "000000":
        table = f"\\textcolor[HTML]{{{color}}}{{{table}}}"
    if obj.caption:
        table += ("\\\\[2pt]{\\footnotesize\\itshape"
                  f"\\textcolor{{ksTblCap}}{{{obj.caption}}}}}")
    lead = int(round(obj.font_pt * 1.2))
    sized = f"\\fontsize{{{obj.font_pt}}}{{{lead}}}\\selectfont"
    return f"{{{sized} {table}}}"


def _serialize_table(obj: SlideTable) -> str:
    return (f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"{_table_inner(obj)}\n"
            f"\\end{{textblock}}")


def _serialize_slide_standard(slide: Slide) -> str:
    """Standard beamer frame: content flows in the body, beamer places it.
    Top-aligned so a large title/heading isn't pushed off the top by
    beamer's default vertical centering."""
    parts = ["\\begin{frame}[t]"]
    if slide.title:
        parts.append(f"\\frametitle{{{slide.title}}}")
    for obj in slide.objects:
        if isinstance(obj, SlideText):
            # Leading \par: without it beamer swallows the first styled
            # paragraph when several are stacked in a [t] frame.
            parts.append("\\par " + _text_inner(obj) + "\\medskip")
        elif isinstance(obj, SlideTable):
            parts.append("\\begin{center}" + _table_inner(obj)
                         + "\\end{center}")
        elif isinstance(obj, SlidePicture) and obj.path:
            parts.append("\\begin{center}"
                         + _picture_graphic(obj, "\\textwidth", "\\textheight")
                         + "\\end{center}")
        # Lines have no flow position, so they're omitted in standard mode.
    parts.append("\\end{frame}")
    return "\n".join(parts)


_SIZE_MACRO = {"small": "\\small", "normal": "\\normalsize",
               "large": "\\large", "Large": "\\Large", "huge": "\\huge"}


def _theme_spec_lines(spec) -> list[str]:
    """The preamble lines for a user-built theme — sub-themes, bullet
    style, colours (via \\definecolor) and the frametitle font."""
    if spec is None or not getattr(spec, "enabled", False):
        return []
    lines: list[str] = []
    if spec.inner:
        lines.append(f"\\useinnertheme{{{spec.inner}}}")
    if spec.outer:
        lines.append(f"\\useoutertheme{{{spec.outer}}}")
    if spec.fonts:
        lines.append(f"\\usefonttheme{{{spec.fonts}}}")
    if spec.bullets:
        lines.append(f"\\setbeamertemplate{{itemize items}}[{spec.bullets}]")

    # Colours: one \definecolor per value, then merged \setbeamercolor.
    counter = [0]

    def cname(hex_color):
        h = _hex_to_rgb_arg(hex_color)
        if not h:
            return None
        n = f"ksth{counter[0]}"
        counter[0] += 1
        lines.append(f"\\definecolor{{{n}}}{{HTML}}{{{h}}}")
        return n

    def set_color(element, fg=None, bg=None):
        keys = []
        if fg:
            c = cname(fg)
            if c:
                keys.append(f"fg={c}")
        if bg:
            c = cname(bg)
            if c:
                keys.append(f"bg={c}")
        if keys:
            lines.append(
                f"\\setbeamercolor{{{element}}}{{{','.join(keys)}}}")

    set_color("structure", fg=spec.structure)
    set_color("normal text", fg=spec.text_fg)
    set_color("background canvas", bg=spec.canvas_bg)
    set_color("frametitle", fg=spec.title_fg, bg=spec.title_bg)
    set_color("title", fg=spec.title_fg)
    set_color("block title", bg=spec.block_bg)
    if spec.frametitle_size in _SIZE_MACRO:
        lines.append(
            f"\\setbeamerfont{{frametitle}}{{size={_SIZE_MACRO[spec.frametitle_size]}}}")
    return lines


def _serialize_line(obj: SlideLine, gap: float, idx: int) -> str:
    span = 1 - 2 * gap
    px1, py1 = gap + obj.x * span, gap + obj.y * span
    px2, py2 = gap + (obj.x + obj.w) * span, gap + (obj.y + obj.h) * span
    colour = _hex_to_rgb_arg(obj.color) or "000000"
    if obj.arrow_start and obj.arrow_end:
        arrow = ", {Stealth}-{Stealth}"
    elif obj.arrow_end:
        arrow = ", -{Stealth}"
    elif obj.arrow_start:
        arrow = ", {Stealth}-"
    else:
        arrow = ""
    nw = "current page.north west"
    return (
        f"\\definecolor{{ksline{idx}}}{{HTML}}{{{colour}}}\n"
        f"\\begin{{tikzpicture}}[overlay,remember picture]\n"
        f"\\draw[line width={_fmt(obj.width_pt)}pt,color=ksline{idx}{arrow}] "
        f"([xshift={_fmt(px1)}\\paperwidth,yshift=-{_fmt(py1)}\\paperheight]{nw}) -- "
        f"([xshift={_fmt(px2)}\\paperwidth,yshift=-{_fmt(py2)}\\paperheight]{nw});\n"
        f"\\end{{tikzpicture}}")


def _serialize_slide(slide: Slide, plain: bool = True, gap: float = 0.0,
                     counter: list | None = None) -> str:
    if not slide.free:
        return _serialize_slide_standard(slide)
    parts = ["\\begin{frame}[plain]" if plain else "\\begin{frame}"]
    # A frame title makes the chosen theme render its standard title bar.
    if slide.title:
        parts.append(f"\\frametitle{{{slide.title}}}")
    bg = _hex_to_rgb_arg(blend_over_white(slide.bg, slide.bg_alpha))
    if bg:
        # Full-slide coloured panel behind everything else. The textpos grid
        # is inset by the gap, so place this block back at the page corner
        # (and size it to the full page) in module units.
        span = 1 / (1 - 2 * gap) if gap < 0.5 else 1.0
        off = -gap / (1 - 2 * gap) if gap < 0.5 else 0.0
        parts.append(
            f"\\begin{{textblock}}{{{_fmt(span)}}}({_fmt(off)},{_fmt(off)})\n"
            f"\\colorbox[HTML]{{{bg}}}{{\\rule{{0pt}}{{\\paperheight}}"
            "\\hspace{\\paperwidth}}\n"
            "\\end{textblock}")
    if counter is None:
        counter = [0]
    for obj in slide.objects:
        if isinstance(obj, SlideText):
            parts.append(_serialize_text(obj))
        elif isinstance(obj, SlideTable):
            parts.append(_serialize_table(obj))
        elif isinstance(obj, SlideLine):
            parts.append(_serialize_line(obj, gap, counter[0]))
            counter[0] += 1
        elif isinstance(obj, SlidePicture):
            block = _serialize_picture(obj)
            if block:
                parts.append(block)
    parts.append("\\end{frame}")
    return "\n".join(parts)


def serialize_deck(deck: Deck) -> str:
    aspect = _ASPECT_OPTS.get(deck.aspect, "aspectratio=169")
    class_opts = f"[{aspect}]" if aspect else ""

    custom_size = deck.page_w_cm > 0 and deck.page_h_cm > 0
    lines = [f"\\documentclass{class_opts}{{beamer}}"]
    if custom_size:
        lines.append("\\usepackage{geometry}")
        lines.append(
            f"\\geometry{{papersize={{{_fmt(deck.page_w_cm)}cm,"
            f"{_fmt(deck.page_h_cm)}cm}}}}")
    lines.append(f"\\usetheme{{{deck.theme or 'default'}}}")
    if deck.color_theme:
        lines.append(f"\\usecolortheme{{{deck.color_theme}}}")
    # User-built theme overrides, layered on top of the base theme.
    lines += _theme_spec_lines(getattr(deck, "theme_spec", None))
    # lmodern: scalable fonts for the arbitrary \fontsize sizes the boxes use.
    lines.append("\\usepackage{lmodern}")
    if any(isinstance(o, SlideLine) for s in deck.slides for o in s.objects):
        lines.append("\\usepackage{tikz}")
        lines.append("\\usetikzlibrary{arrows.meta}")
    if any(isinstance(o, SlidePicture) and o.opacity < 1.0
           for s in deck.slides for o in s.objects):
        lines.append("\\usepackage{transparent}")
    if any(isinstance(o, SlideTable) for s in deck.slides for o in s.objects):
        lines.append("\\usepackage{colortbl}")
        for name, hexv in (("ksTblHead", TABLE_HEADER_BG),
                           ("ksTblHeadFg", TABLE_HEADER_FG),
                           ("ksTblRule", TABLE_RULE),
                           ("ksTblCap", TABLE_CAPTION_FG)):
            lines.append(f"\\definecolor{{{name}}}{{HTML}}{{{_hex_to_rgb_arg(hexv)}}}")
    lines += [
        "\\usepackage[absolute,overlay]{textpos}",
        "\\usepackage{graphicx}",
    ]
    # The content "gap": inset the textpos grid so 0..1 maps inside the
    # page minus the margin, matching the canvas.
    g = max(0.0, min(0.45, deck.gap))
    span = _fmt(1 - 2 * g)
    lines += [
        f"\\setlength{{\\TPHorizModule}}{{{span}\\paperwidth}}",
        f"\\setlength{{\\TPVertModule}}{{{span}\\paperheight}}",
        f"\\textblockorigin{{{_fmt(g)}\\paperwidth}}{{{_fmt(g)}\\paperheight}}",
    ]
    if not deck.nav_symbols:
        lines.append("\\setbeamertemplate{navigation symbols}{}")
    if deck.title:
        lines.append(f"\\title{{{deck.title}}}")
    if deck.author:
        lines.append(f"\\author{{{deck.author}}}")
    lines.append("\\begin{document}")
    counter = [0]
    for slide in deck.slides:
        lines.append(_serialize_slide(slide, deck.plain_frames, g, counter))
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n"
