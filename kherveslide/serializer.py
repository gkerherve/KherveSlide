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


def _has_crop(obj: SlidePicture) -> bool:
    return any(getattr(obj, k, 0.0) > 0.0
               for k in ("crop_l", "crop_t", "crop_r", "crop_b"))


def _picture_graphic(obj: SlidePicture, rel: str = "\\paperwidth",
                     rel_h: str = "\\paperheight",
                     width_expr: str | None = None) -> str:
    path = obj.path.replace("\\", "/")
    # width_expr overrides the box-fraction width (used to fill a column).
    w = width_expr or f"{_fmt(obj.w)}{rel}"
    opts = f"width={w},height={_fmt(obj.h)}{rel_h}"
    if obj.keep_aspect:
        opts += ",keepaspectratio"
    if _has_crop(obj):
        # adjustbox lets trim use \width/\height (the image's natural size),
        # so a fractional crop needs no knowledge of the pixel dimensions.
        # graphicx trim order is: left bottom right top.
        trim = (f"trim={{{_fmt(obj.crop_l)}\\width}} {{{_fmt(obj.crop_b)}\\height}} "
                f"{{{_fmt(obj.crop_r)}\\width}} {{{_fmt(obj.crop_t)}\\height}}")
        graphic = f"\\adjincludegraphics[{trim},clip,{opts}]{{{path}}}"
    else:
        graphic = f"\\includegraphics[{opts}]{{{path}}}"
    angle = getattr(obj, "rotation", 0.0)
    if angle:
        graphic = f"\\rotatebox[origin=c]{{{_fmt(angle)}}}{{{graphic}}}"
    if obj.opacity < 1.0:
        # A TikZ node with opacity actually tints the image; the older
        # \transparent package silently no-op'd here (it printed its value
        # as literal text under tectonic) so the image stayed opaque.
        graphic = (f"\\begin{{tikzpicture}}\\node[opacity={_fmt(max(0.0, obj.opacity))},"
                   f"inner sep=0]{{{graphic}}};\\end{{tikzpicture}}")
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


def _flow_object(obj) -> str | None:
    """A locked object's representation in the standard beamer flow (beamer
    places it). Returns None for objects that have no flow form."""
    if isinstance(obj, SlideText):
        # Leading \par: without it beamer swallows the first styled
        # paragraph when several are stacked in a [t] frame.
        return "\\par " + _text_inner(obj) + "\\medskip"
    if isinstance(obj, SlideTable):
        return "\\begin{center}" + _table_inner(obj) + "\\end{center}"
    if isinstance(obj, SlidePicture) and obj.path:
        return ("\\begin{center}"
                + _picture_graphic(obj, "\\textwidth", "\\textheight")
                + "\\end{center}")
    return None


def _column_content(obj) -> str | None:
    """A locked object's content when it sits inside a beamer column —
    sized to the column (\\linewidth), no full-width centring."""
    if isinstance(obj, SlideText):
        return _text_inner(obj)
    if isinstance(obj, SlideTable):
        return _table_inner(obj)
    if isinstance(obj, SlidePicture) and obj.path:
        # Fill the column width (the box width already set the column size),
        # capping the height to the box's slide-fraction.
        return _picture_graphic(obj, rel_h="\\textheight",
                                width_expr="\\linewidth")
    return None


def _h_disjoint(a, b) -> bool:
    return a.x + a.w <= b.x + 1e-6 or b.x + b.w <= a.x + 1e-6


def _group_rows(objs: list) -> list[list]:
    """Cluster locked objects into visual rows. Objects whose vertical
    extents overlap *and* that sit side by side (no horizontal overlap)
    share a row → they become beamer columns. Everything else is its own
    row and simply flows."""
    rows: list[list] = []
    for o in sorted(objs, key=lambda o: (round(o.y, 3), o.x)):
        for row in rows:
            top = min(m.y for m in row)
            bot = max(m.y + m.h for m in row)
            v_overlap = o.y < bot - 0.02 and (o.y + o.h) > top + 0.02
            if v_overlap and all(_h_disjoint(o, m) for m in row):
                row.append(o)
                break
        else:
            rows.append([o])
    rows.sort(key=lambda row: min(m.y for m in row))
    return rows


def _serialize_flow(objs: list) -> list[str]:
    """Lay out locked objects as standard beamer flow, turning side-by-side
    groups into columns."""
    parts: list[str] = []
    for row in _group_rows(objs):
        if len(row) == 1:
            block = _flow_object(row[0])
            if block:
                parts.append(block)
            continue
        row = sorted(row, key=lambda o: o.x)
        parts.append("\\begin{columns}[t]")
        for o in row:
            content = _column_content(o)
            if content is None:
                continue
            w = max(0.1, min(0.92, o.w))
            parts.append(f"\\begin{{column}}{{{_fmt(w)}\\textwidth}}")
            parts.append(content)
            parts.append("\\end{column}")
        parts.append("\\end{columns}")
    return parts


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

    # Decorative rules (lines). They borrow the structure colour unless the
    # user picked a dedicated rule colour.
    if getattr(spec, "title_rule", False) or getattr(spec, "footline_rule", False):
        rc = _hex_to_rgb_arg(getattr(spec, "rule_color", "") or "")
        if rc:
            lines.append(f"\\definecolor{{ksRule}}{{HTML}}{{{rc}}}")
            rule_color = "ksRule"
        else:
            rule_color = "structure"
        w = _fmt(max(0.2, getattr(spec, "rule_width", 1.5)))
        if spec.title_rule:
            # Appended after the frame title, spanning the title's width.
            lines.append(
                "\\addtobeamertemplate{frametitle}{}{%\n"
                f"\\vskip2pt{{\\color{{{rule_color}}}\\hrule height {w}pt}}}}")
        if spec.footline_rule:
            lines.append(
                "\\setbeamertemplate{footline}{%\n"
                f"\\hbox{{\\color{{{rule_color}}}\\rule{{\\paperwidth}}{{{w}pt}}}}"
                "\\vskip0pt}")
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


def _overlay_object(obj, gap: float, counter: list) -> str | None:
    """An unlocked object's absolutely-positioned (textpos / tikz) form."""
    if isinstance(obj, SlideText):
        return _serialize_text(obj)
    if isinstance(obj, SlideTable):
        return _serialize_table(obj)
    if isinstance(obj, SlideLine):
        block = _serialize_line(obj, gap, counter[0])
        counter[0] += 1
        return block
    if isinstance(obj, SlidePicture):
        return _serialize_picture(obj) or None
    return None


def _page_number_block(mode: str, gap: float) -> str:
    """A small slide-number overlay at the bottom-right corner. Placed via
    textpos so it shows on plain frames too (where the theme footline is
    suppressed)."""
    inner = ("\\insertframenumber\\,/\\,\\inserttotalframenumber"
             if mode == "of_total" else "\\insertframenumber")
    # Pin to the page's bottom-right regardless of the content gap, the same
    # way the background panel un-insets the textpos grid.
    span = 1 / (1 - 2 * gap) if gap < 0.5 else 1.0
    off = -gap / (1 - 2 * gap) if gap < 0.5 else 0.0
    x = off + 0.78 * span
    y = off + 0.955 * span
    w = 0.2 * span
    return (f"\\begin{{textblock}}{{{_fmt(w)}}}({_fmt(x)},{_fmt(y)})\n"
            f"\\raggedleft{{\\small\\color{{black!55}}{inner}}}\n"
            f"\\end{{textblock}}")


# beamer's clickable prev/next (and section/doc) navigation glyphs.
_NAV_SYMBOLS = (
    "\\insertslidenavigationsymbol\\insertframenavigationsymbol"
    "\\insertsubsectionnavigationsymbol\\insertsectionnavigationsymbol"
    "\\insertdocnavigationsymbol\\insertbackfindforwardnavigationsymbol")


def _nav_symbols_block(gap: float) -> str:
    """Overlay beamer's navigation symbols at the bottom-right corner of the
    frame. We place them ourselves (instead of relying on the theme footline)
    so they appear even on the plain frames free positioning uses."""
    span = 1 / (1 - 2 * gap) if gap < 0.5 else 1.0
    off = -gap / (1 - 2 * gap) if gap < 0.5 else 0.0
    x = off + 0.50 * span
    y = off + 0.93 * span
    w = 0.48 * span
    return (f"\\begin{{textblock}}{{{_fmt(w)}}}({_fmt(x)},{_fmt(y)})\n"
            f"\\raggedleft{{{_NAV_SYMBOLS}}}\n"
            f"\\end{{textblock}}")


def _serialize_slide(slide: Slide, plain: bool = True, gap: float = 0.0,
                     counter: list | None = None,
                     page_number: str = "none",
                     nav_symbols: bool = False) -> str:
    if counter is None:
        counter = [0]
    # [t] top-aligns the flowed (locked) content so a tall heading isn't
    # pushed off-screen by beamer's default vertical centering.
    opts = ("plain," if plain else "") + "t"
    parts = [f"\\begin{{frame}}[{opts}]"]
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
    # Locked objects flow in the frame body (beamer lays them out); lines
    # are always absolute, so they never flow. Side-by-side locked objects
    # become beamer columns.
    locked_flow = [o for o in slide.objects
                   if getattr(o, "locked", True) and not isinstance(o, SlideLine)]
    parts.extend(_serialize_flow(locked_flow))
    # Unlocked objects (and all lines) are placed absolutely on top.
    for obj in slide.objects:
        if not getattr(obj, "locked", True) or isinstance(obj, SlideLine):
            block = _overlay_object(obj, gap, counter)
            if block:
                parts.append(block)
    if nav_symbols:
        parts.append(_nav_symbols_block(gap))
    if page_number and page_number != "none":
        parts.append(_page_number_block(page_number, gap))
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
    needs_tikz = any(isinstance(o, SlideLine) for s in deck.slides
                     for o in s.objects)
    needs_opacity = any(isinstance(o, SlidePicture) and o.opacity < 1.0
                        for s in deck.slides for o in s.objects)
    if needs_tikz or needs_opacity:
        # tikz also drives image opacity (a node with opacity= tints it).
        lines.append("\\usepackage{tikz}")
    if needs_tikz:
        lines.append("\\usetikzlibrary{arrows.meta}")
    if any(isinstance(o, SlidePicture) and _has_crop(o)
           for s in deck.slides for o in s.objects):
        # adjustbox supplies \adjincludegraphics with \width-relative trim.
        lines.append("\\usepackage{adjustbox}")
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
    # Always clear beamer's own placement; when enabled we re-insert the
    # symbols at the bottom-right of each frame ourselves (works on plain
    # frames too, where the theme footline — and its symbols — are gone).
    lines.append("\\setbeamertemplate{navigation symbols}{}")
    if deck.title:
        lines.append(f"\\title{{{deck.title}}}")
    if deck.author:
        lines.append(f"\\author{{{deck.author}}}")
    lines.append("\\begin{document}")
    counter = [0]
    for slide in deck.slides:
        lines.append(_serialize_slide(slide, deck.plain_frames, g, counter,
                                      getattr(deck, "page_number", "none"),
                                      deck.nav_symbols))
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n"
