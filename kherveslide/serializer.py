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
    Deck, Slide, SlideText, SlidePicture, SlideTable, SlideLine, SlideShape,
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


def _is_struct_line(line: str) -> bool:
    s = line.lstrip()
    return (s.startswith("\\begin{") or s.startswith("\\end{")
            or s.startswith("\\item"))


def _apply_linebreaks(body: str) -> str:
    """Turn a user line break (Enter → newline between two plain text lines)
    into a LaTeX ``\\\\`` so it shows on a new line. itemize/enumerate
    structure lines and blank-line paragraph breaks are left untouched."""
    lines = body.split("\n")
    if len(lines) <= 1:
        return body
    out = [lines[0]]
    for prev, cur in zip(lines, lines[1:]):
        both_plain = (prev.strip() and cur.strip()
                      and not _is_struct_line(prev) and not _is_struct_line(cur))
        out.append((" \\\\\n" if both_plain else "\n") + cur)
    return "".join(out)


def _styled_text(obj: SlideText) -> str:
    """The inner (font/colour/weight/alignment-styled) content of a text
    box, sized to the block width."""
    body = _apply_linebreaks(obj.text or "")
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


_BLOCK_ENVS = {"block", "alertblock", "exampleblock"}


def _text_inner(obj: SlideText) -> str:
    content = _styled_text(obj)
    block = getattr(obj, "block", "")
    if block in _BLOCK_ENVS:
        title = getattr(obj, "block_title", "") or ""
        content = f"\\begin{{{block}}}{{{title}}}{content}\\end{{{block}}}"
    if _has_frame(obj):
        return _frame_wrap(content, obj, "\\linewidth")
    return f"{{{content}\\par}}"


def _serialize_text(obj: SlideText) -> str:
    return (f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"{_text_inner(obj)}\n"
            f"\\end{{textblock}}")


def _has_crop(obj: SlidePicture) -> bool:
    return any(getattr(obj, k, 0.0) > 0.0
               for k in ("crop_l", "crop_t", "crop_r", "crop_b"))


def _has_frame(obj) -> bool:
    return bool(_hex_to_rgb_arg(getattr(obj, "border_color", ""))
                or _hex_to_rgb_arg(getattr(obj, "fill", "")))


def _frame_wrap(inner: str, obj, text_width: str | None = None) -> str:
    """Wrap *inner* in a tikz node giving the box a fill and/or a border
    rectangle (sharp or rounded). Returns *inner* unchanged if neither set."""
    bc = _hex_to_rgb_arg(getattr(obj, "border_color", ""))
    fc = _hex_to_rgb_arg(getattr(obj, "fill", ""))
    if not bc and not fc:
        return inner
    pre, opts = [], ["inner sep=3pt"]
    if bc:
        pre.append(f"\\definecolor{{ksBorder}}{{HTML}}{{{bc}}}")
        w = _fmt(max(0.2, getattr(obj, "border_width", 1.0)))
        opts += [f"draw=ksBorder", f"line width={w}pt"]
    if fc:
        pre.append(f"\\definecolor{{ksBoxFill}}{{HTML}}{{{fc}}}")
        opts.append("fill=ksBoxFill")
    if getattr(obj, "corner", "sharp") == "rounded":
        opts.append("rounded corners=4pt")
    if text_width:
        opts.append(f"text width={text_width}")
    return ("".join(pre) + "\\begin{tikzpicture}\n"
            f"\\node[{','.join(opts)}]{{{inner}}};\n\\end{{tikzpicture}}")


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
            f"{_frame_wrap(_picture_graphic(obj), obj)}\n"
            f"\\end{{textblock}}")


_ALIGN_COL = {"left": "l", "center": "c", "right": "r"}


def _table_inner(obj: SlideTable) -> str:
    rows = obj.rows or [[""]]
    ncols = max((len(r) for r in rows), default=1)
    grid = getattr(obj, "grid", "all")
    if not getattr(obj, "border", True) and grid == "all":
        grid = "none"      # legacy border=False overrides the default grid
    a = _ALIGN_COL.get(getattr(obj, "align", "left"), "l")
    vbar = "|" if grid == "all" else ""
    colspec = vbar + vbar.join(a for _ in range(ncols)) + vbar
    full_hline = grid in ("all", "horizontal")
    outer_hline = grid in ("all", "horizontal", "outer")
    hrule = "\\hline\n" if full_hline else ""
    edge = "\\hline\n" if outer_hline else ""

    # Per-table colours, named after their hex so two differently-styled
    # tables on the same deck never clash (definecolor is global).
    def cname(prefix, hexv, fallback):
        h = _hex_to_rgb_arg(hexv) or fallback
        return f"ks{prefix}{h}", f"\\definecolor{{ks{prefix}{h}}}{{HTML}}{{{h}}}"

    head_n, head_d = cname("TH", getattr(obj, "header_bg", "#FCE4D6"), "FCE4D6")
    hfg_n, hfg_d = cname("TF", getattr(obj, "header_fg", "#C55A11"), "C55A11")
    rule_n, rule_d = cname("TR", getattr(obj, "rule_color", "#F4B183"), "F4B183")
    stripe_n, stripe_d = cname("TS", getattr(obj, "stripe_color", "#F5F5F5"),
                               "F5F5F5")
    defs = head_d + hfg_d + rule_d + stripe_d
    striped = getattr(obj, "striped", False)

    body = []
    for i, row in enumerate(rows):
        cells = list(row) + [""] * (ncols - len(row))
        if i == 0 and obj.header:
            cells = [f"\\textcolor{{{hfg_n}}}{{\\textbf{{{c}}}}}" for c in cells]
            line = f"  \\rowcolor{{{head_n}}}" + " & ".join(cells) + " \\\\"
        else:
            prefix = "  "
            if striped:
                bi = i - (1 if obj.header else 0)
                if bi % 2 == 1:
                    prefix = f"  \\rowcolor{{{stripe_n}}}"
            line = prefix + " & ".join(cells) + " \\\\"
        body.append(line)

    joiner = ("\n" + hrule) if full_hline else "\n"
    table = (f"\\begin{{tabular}}{{{colspec}}}\n{edge}"
             + joiner.join(body)
             + f"\n{edge}\\end{{tabular}}")
    color = _hex_to_rgb_arg(obj.color)
    if color and color != "000000":
        table = f"\\textcolor[HTML]{{{color}}}{{{table}}}"
    if obj.caption:
        table += ("\\\\[2pt]{\\footnotesize\\itshape"
                  f"\\textcolor{{ksTblCap}}{{{obj.caption}}}}}")
    lead = int(round(obj.font_pt * 1.2))
    sized = f"\\fontsize{{{obj.font_pt}}}{{{lead}}}\\selectfont"
    rule_w = f"\\setlength{{\\arrayrulewidth}}{{{_fmt(obj.rule_width)}pt}}"
    return _frame_wrap(
        f"{{{defs}{rule_w}\\arrayrulecolor{{{rule_n}}} {sized} {table}}}", obj)


def _serialize_table(obj: SlideTable) -> str:
    return (f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"{_table_inner(obj)}\n"
            f"\\end{{textblock}}")


def _flow_object(obj) -> str | None:
    """A locked object's representation in the standard beamer flow (beamer
    places it). Returns None for objects that have no flow form."""
    if isinstance(obj, SlideText):
        # A beamer-placed block honours its box width: when narrower than
        # the text column it is wrapped in a centred minipage so the block
        # is exactly as wide as it looks on the canvas. Plain (non-block)
        # text still flows full width.
        block = getattr(obj, "block", "")
        if block in _BLOCK_ENVS:
            w = max(0.15, min(1.0, obj.w))
            if w < 0.97:
                return ("\\par\\begin{center}\n"
                        f"\\begin{{minipage}}{{{_fmt(w)}\\textwidth}}\n"
                        f"{_text_inner(obj)}\n"
                        "\\end{minipage}\n\\end{center}\\medskip")
        # Leading \par: without it beamer swallows the first styled
        # paragraph when several are stacked in a [t] frame.
        return "\\par " + _text_inner(obj) + "\\medskip"
    if isinstance(obj, SlideTable):
        return "\\begin{center}" + _table_inner(obj) + "\\end{center}"
    if isinstance(obj, SlidePicture) and obj.path:
        return ("\\begin{center}"
                + _frame_wrap(
                    _picture_graphic(obj, "\\textwidth", "\\textheight"), obj)
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
        return _frame_wrap(_picture_graphic(obj, rel_h="\\textheight",
                                            width_expr="\\linewidth"), obj)
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
                parts.append(f"  % {_obj_label(row[0])}")
                parts.append(block)
            continue
        row = sorted(row, key=lambda o: o.x)
        parts.append(f"  % {len(row)} columns")
        parts.append("\\begin{columns}[t]")
        for o in row:
            content = _column_content(o)
            if content is None:
                continue
            w = max(0.1, min(0.92, o.w))
            parts.append(f"  \\begin{{column}}{{{_fmt(w)}\\textwidth}}  % {_obj_label(o)}")
            parts.append(content)
            parts.append("  \\end{column}")
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


_DASH_TIKZ = {"dashed": ", dashed", "dotted": ", dotted"}


# Lines and shapes are placed inline via textpos (NOT a page-absolute
# "overlay,remember picture" tikz layer, which always paints on top of
# everything regardless of source order). Drawing them in local tikz
# coordinates inside a textblock makes them obey the same source-order
# z-stacking as every other box, so raise / lower / send-behind work.

def _serialize_line(obj: SlideLine, gap: float, idx: int) -> str:
    colour = _hex_to_rgb_arg(obj.color) or "000000"
    hs = max(0.3, getattr(obj, "head_size", 1.0))
    head = f"{{Stealth[length={_fmt(2.4 * hs)}mm]}}"
    if obj.arrow_start and obj.arrow_end:
        arrow = f", {head}-{head}"
    elif obj.arrow_end:
        arrow = f", -{head}"
    elif obj.arrow_start:
        arrow = f", {head}-"
    else:
        arrow = ""
    dash = _DASH_TIKZ.get(getattr(obj, "style", "solid"), "")
    op = getattr(obj, "opacity", 1.0)
    opacity = f", draw opacity={_fmt(op)}" if op < 1.0 else ""
    wlen, hlen = "\\linewidth", f"{_fmt(obj.h)}\\TPVertModule"
    pic = (
        f"\\begin{{tikzpicture}}\n"
        f"\\useasboundingbox (0,0) rectangle ({wlen},-{hlen});\n"
        f"\\draw[line width={_fmt(obj.width_pt)}pt,color=ksline{idx}"
        f"{arrow}{dash}{opacity}] (0,0) -- ({wlen},-{hlen});\n"
        f"\\end{{tikzpicture}}")
    return (f"\\definecolor{{ksline{idx}}}{{HTML}}{{{colour}}}\n"
            f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"{pic}\n\\end{{textblock}}")


def _serialize_shape(obj: SlideShape, gap: float, idx: int) -> str:
    wlen, hlen = "\\linewidth", f"{_fmt(obj.h)}\\TPVertModule"
    defs = ""
    opts = [f"minimum width={wlen}", f"minimum height={hlen}",
            "inner sep=0pt", "anchor=center"]
    if obj.shape == "ellipse":
        opts.insert(0, "ellipse")
    elif obj.corner == "rounded":
        opts.append("rounded corners=4pt")
    if obj.border_color and obj.border_width > 0:
        defs += (f"\\definecolor{{ksshape{idx}}}{{HTML}}"
                 f"{{{_hex_to_rgb_arg(obj.border_color) or '000000'}}}\n")
        opts.append(f"draw=ksshape{idx}")
        opts.append(f"line width={_fmt(obj.border_width)}pt")
        opts.append({"dashed": "dashed", "dotted": "dotted"}.get(
            getattr(obj, "style", "solid"), "solid"))
    if obj.fill:
        defs += (f"\\definecolor{{ksfill{idx}}}{{HTML}}"
                 f"{{{_hex_to_rgb_arg(obj.fill) or 'ffffff'}}}\n")
        opts.append(f"fill=ksfill{idx}")
    if obj.opacity < 1.0:
        opts.append(f"opacity={_fmt(obj.opacity)}")
    if obj.rotation:
        opts.append(f"rotate={_fmt(-obj.rotation)}")
    pic = (
        f"\\begin{{tikzpicture}}\n"
        f"\\useasboundingbox (0,0) rectangle ({wlen},-{hlen});\n"
        f"\\node[{', '.join(opts)}] at ($(0,0)!0.5!({wlen},-{hlen})$) {{}};\n"
        f"\\end{{tikzpicture}}")
    return (defs +
            f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"{pic}\n\\end{{textblock}}")


# --- "behind" variants: page-absolute tikz drawn in the frame background
# template, which is the only layer beneath beamer-placed (flow) content.
# Used when a line/shape is sent below a beamer-placed box in the stack.

def _serialize_line_bg(obj: SlideLine, gap: float, idx: int) -> str:
    span = 1 - 2 * gap
    px1, py1 = gap + obj.x * span, gap + obj.y * span
    px2, py2 = gap + (obj.x + obj.w) * span, gap + (obj.y + obj.h) * span
    colour = _hex_to_rgb_arg(obj.color) or "000000"
    hs = max(0.3, getattr(obj, "head_size", 1.0))
    head = f"{{Stealth[length={_fmt(2.4 * hs)}mm]}}"
    if obj.arrow_start and obj.arrow_end:
        arrow = f", {head}-{head}"
    elif obj.arrow_end:
        arrow = f", -{head}"
    elif obj.arrow_start:
        arrow = f", {head}-"
    else:
        arrow = ""
    dash = _DASH_TIKZ.get(getattr(obj, "style", "solid"), "")
    op = getattr(obj, "opacity", 1.0)
    opacity = f", draw opacity={_fmt(op)}" if op < 1.0 else ""
    nw = "current page.north west"
    return (
        f"\\definecolor{{ksline{idx}}}{{HTML}}{{{colour}}}%\n"
        f"\\begin{{tikzpicture}}[remember picture,overlay]\n"
        f"\\draw[line width={_fmt(obj.width_pt)}pt,color=ksline{idx}"
        f"{arrow}{dash}{opacity}] "
        f"([xshift={_fmt(px1)}\\paperwidth,yshift=-{_fmt(py1)}\\paperheight]{nw}) -- "
        f"([xshift={_fmt(px2)}\\paperwidth,yshift=-{_fmt(py2)}\\paperheight]{nw});\n"
        f"\\end{{tikzpicture}}")


def _serialize_shape_bg(obj: SlideShape, gap: float, idx: int) -> str:
    span = 1 - 2 * gap
    cx = gap + (obj.x + obj.w / 2) * span
    cy = gap + (obj.y + obj.h / 2) * span
    w, h = obj.w * span, obj.h * span
    defs = ""
    opts = [f"minimum width={_fmt(w)}\\paperwidth",
            f"minimum height={_fmt(h)}\\paperheight", "inner sep=0pt"]
    if obj.shape == "ellipse":
        opts.insert(0, "ellipse")
    elif obj.corner == "rounded":
        opts.append("rounded corners=4pt")
    if obj.border_color and obj.border_width > 0:
        defs += (f"\\definecolor{{ksshape{idx}}}{{HTML}}"
                 f"{{{_hex_to_rgb_arg(obj.border_color) or '000000'}}}%\n")
        opts.append(f"draw=ksshape{idx}")
        opts.append(f"line width={_fmt(obj.border_width)}pt")
        opts.append({"dashed": "dashed", "dotted": "dotted"}.get(
            getattr(obj, "style", "solid"), "solid"))
    if obj.fill:
        defs += (f"\\definecolor{{ksfill{idx}}}{{HTML}}"
                 f"{{{_hex_to_rgb_arg(obj.fill) or 'ffffff'}}}%\n")
        opts.append(f"fill=ksfill{idx}")
    if obj.opacity < 1.0:
        opts.append(f"opacity={_fmt(obj.opacity)}")
    if obj.rotation:
        opts.append(f"rotate={_fmt(-obj.rotation)}")
    nw = "current page.north west"
    pos = (f"([xshift={_fmt(cx)}\\paperwidth,"
           f"yshift=-{_fmt(cy)}\\paperheight]{nw})")
    return (defs +
            "\\begin{tikzpicture}[remember picture,overlay]\n"
            f"\\node[{', '.join(opts)}] at {pos} {{}};\n"
            "\\end{tikzpicture}")


def _overlay_behind(obj, gap: float, counter: list) -> str | None:
    """A line/shape rendered into the frame background (behind flow)."""
    if isinstance(obj, SlideLine):
        block = _serialize_line_bg(obj, gap, counter[0])
        counter[0] += 1
        return block
    if isinstance(obj, SlideShape):
        block = _serialize_shape_bg(obj, gap, counter[0])
        counter[0] += 1
        return block
    return None


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
    if isinstance(obj, SlideShape):
        block = _serialize_shape(obj, gap, counter[0])
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


_OBJ_LABEL = {SlideText: "text box", SlidePicture: "picture",
              SlideTable: "table", SlideLine: "line / arrow",
              SlideShape: "shape"}


def _obj_label(obj) -> str:
    return _OBJ_LABEL.get(type(obj), "object")


def _serialize_slide(slide: Slide, plain: bool = True, gap: float = 0.0,
                     counter: list | None = None,
                     page_number: str = "none",
                     nav_symbols: bool = False, index: int = 0) -> str:
    if counter is None:
        counter = [0]
    # [t] top-aligns the flowed (locked) content so a tall heading isn't
    # pushed off-screen by beamer's default vertical centering.
    opts = ("plain," if plain else "") + "t"
    bar = "% " + "=" * 70
    head = f"% Slide {index + 1}" + (f" - {slide.title}" if slide.title else "")

    def _is_flow(o) -> bool:
        return (getattr(o, "locked", True)
                and not isinstance(o, (SlideLine, SlideShape)))

    # beamer renders ALL absolutely-placed (textpos / tikz overlay) content
    # above the flow body, so a line/shape that the user sent *below* a
    # beamer-placed box can't sit behind it inline. Those "behind" shapes are
    # drawn in the frame's background template instead — the one layer under
    # the flow body. "Behind" = a line/shape whose stack index is lower than
    # the first beamer-placed object.
    objs = slide.objects
    first_flow = next((k for k, o in enumerate(objs) if _is_flow(o)), None)
    behind = []
    if first_flow is not None:
        behind = [o for k, o in enumerate(objs)
                  if k < first_flow and isinstance(o, (SlideLine, SlideShape))]
    behind_ids = {id(o) for o in behind}

    parts = [bar, head, bar]
    if behind:
        bg_parts = []
        for o in behind:
            blk = _overlay_behind(o, gap, counter)
            if blk:
                bg_parts.append(blk)
        parts.append("{%  scoped background: shapes sent behind the content")
        parts.append("\\setbeamertemplate{background}{%")
        parts.extend(bg_parts)
        parts.append("}")
    parts.append(f"\\begin{{frame}}[{opts}]")
    if slide.title:
        parts.append(f"  \\frametitle{{{slide.title}}}")
    bg = _hex_to_rgb_arg(blend_over_white(slide.bg, slide.bg_alpha))
    if bg:
        # Full-slide coloured panel behind everything else. The textpos grid
        # is inset by the gap, so place this block back at the page corner
        # (and size it to the full page) in module units.
        span = 1 / (1 - 2 * gap) if gap < 0.5 else 1.0
        off = -gap / (1 - 2 * gap) if gap < 0.5 else 0.0
        parts.append("\n  % slide background")
        parts.append(
            f"\\begin{{textblock}}{{{_fmt(span)}}}({_fmt(off)},{_fmt(off)})\n"
            f"\\colorbox[HTML]{{{bg}}}{{\\rule{{0pt}}{{\\paperheight}}"
            "\\hspace{\\paperwidth}}\n"
            "\\end{textblock}")
    # Emit objects in list order so the stack order on the slide matches the
    # canvas (raise / lower / bring-to-front actually move things): later
    # source = drawn on top. A run of consecutive beamer-placed objects flows
    # in the frame body (and side-by-side ones become columns); free objects,
    # lines and shapes are placed absolutely inline at their list position.
    i = 0
    while i < len(objs):
        if id(objs[i]) in behind_ids:
            i += 1                       # already drawn in the background
            continue
        if _is_flow(objs[i]):
            run = []
            while i < len(objs) and _is_flow(objs[i]):
                run.append(objs[i])
                i += 1
            flow = _serialize_flow(run)
            if flow:
                parts.append("\n  % beamer-placed content "
                             "(flows in the frame body)")
                parts.extend(flow)
        else:
            block = _overlay_object(objs[i], gap, counter)
            if block:
                parts.append(f"\n  % {_obj_label(objs[i])} (free-positioned)")
                parts.append(block)
            i += 1
    if nav_symbols:
        parts.append("\n  % navigation symbols (bottom-right)")
        parts.append(_nav_symbols_block(gap))
    if page_number and page_number != "none":
        parts.append("\n  % slide number")
        parts.append(_page_number_block(page_number, gap))
    parts.append("\\end{frame}")
    if behind:
        parts.append("}")     # close the scoped-background group
    return "\n".join(parts)


def _header_footer_lines(deck) -> list[str]:
    """Custom headline / footline templates from the deck's header and
    footer slots. They only show when frames aren't [plain] (decorations
    on); plain frames suppress head/foot lines."""
    lines: list[str] = []
    header = getattr(deck, "header", "")
    fl = getattr(deck, "foot_left", "")
    fc = getattr(deck, "foot_center", "")
    fr = getattr(deck, "foot_right", "")
    if header:
        lines += [
            "\\setbeamertemplate{headline}{%",
            "\\begin{beamercolorbox}[wd=\\paperwidth,ht=2.6ex,dp=1.2ex,"
            "leftskip=1.5ex,rightskip=1.5ex]{section in head/foot}%",
            f"{header}\\hfill\\end{{beamercolorbox}}}}",
        ]
    if fl or fc or fr:
        lines += [
            "\\setbeamertemplate{footline}{%",
            "\\leavevmode\\hbox{%",
            "\\begin{beamercolorbox}[wd=.333\\paperwidth,ht=2.5ex,dp=1.2ex,"
            f"leftskip=1.5ex]{{author in head/foot}}{fl}\\end{{beamercolorbox}}%",
            "\\begin{beamercolorbox}[wd=.334\\paperwidth,ht=2.5ex,dp=1.2ex,"
            f"center]{{title in head/foot}}{fc}\\end{{beamercolorbox}}%",
            "\\begin{beamercolorbox}[wd=.333\\paperwidth,ht=2.5ex,dp=1.2ex,"
            f"rightskip=1.5ex]{{date in head/foot}}\\hfill {fr}"
            "\\end{beamercolorbox}}%",
            "\\vskip0pt}",
        ]
    return lines


def serialize_deck(deck: Deck) -> str:
    aspect = _ASPECT_OPTS.get(deck.aspect, "aspectratio=169")
    class_opts = f"[{aspect}]" if aspect else ""

    custom_size = deck.page_w_cm > 0 and deck.page_h_cm > 0
    bar = "% " + "=" * 70
    lines = [bar,
             "% Beamer presentation - generated by KherveSlide.",
             "% Edit freely; the source is regenerated when you change a slide.",
             bar,
             f"\\documentclass{class_opts}{{beamer}}",
             "",
             "% --- theme & packages ---"]
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
    needs_tikz = any(isinstance(o, (SlideLine, SlideShape)) or _has_frame(o)
                     for s in deck.slides for o in s.objects)
    needs_opacity = any(isinstance(o, SlidePicture) and o.opacity < 1.0
                        for s in deck.slides for o in s.objects)
    needs_ellipse = any(isinstance(o, SlideShape) and o.shape == "ellipse"
                        for s in deck.slides for o in s.objects)
    if needs_tikz or needs_opacity:
        # tikz also drives image opacity (a node with opacity= tints it).
        lines.append("\\usepackage{tikz}")
    if needs_tikz:
        lines.append("\\usetikzlibrary{arrows.meta,calc}")
        if needs_ellipse:
            lines.append("\\usetikzlibrary{shapes.geometric}")
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
    lines += _header_footer_lines(deck)
    if deck.title:
        lines.append(f"\\title{{{deck.title}}}")
    if deck.author:
        lines.append(f"\\author{{{deck.author}}}")
    lines += ["", "\\begin{document}"]
    counter = [0]
    for i, slide in enumerate(deck.slides):
        lines.append("")          # blank line between slides
        lines.append(_serialize_slide(slide, deck.plain_frames, g, counter,
                                      getattr(deck, "page_number", "none"),
                                      deck.nav_symbols, i))
    lines += ["", "\\end{document}"]
    return "\n".join(lines) + "\n"
