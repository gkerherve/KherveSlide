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

from dataclasses import replace
from pathlib import Path

from . import shapes as _shapes
from .model import (
    Deck, Slide, SlideText, SlidePicture, SlideTable, SlideLine, SlideShape,
    SlideVideo, blend_over_white, TABLE_HEADER_BG, TABLE_HEADER_FG,
    TABLE_RULE, TABLE_CAPTION_FG,
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
    fam = {"rm": "\\rmfamily", "sf": "\\sffamily",
           "tt": "\\ttfamily"}.get(getattr(obj, "font_family", ""), "")
    align_cmd = {"center": "\\centering", "right": "\\raggedleft",
                 "left": "\\raggedright"}.get(obj.align, "\\raggedright")
    lead = int(round(obj.font_pt * 1.2))
    sized = f"\\fontsize{{{obj.font_pt}}}{{{lead}}}\\selectfont"
    return f"{align_cmd}{fam}{sized} {body}"


# Coloured beamer blocks take their title as {title}; theorem-like
# environments (built into beamer) take it as [title].
_BLOCK_ENVS = {"block", "alertblock", "exampleblock"}
_THEOREM_ENVS = {"theorem", "definition", "corollary", "lemma", "example",
                 "proof", "fact"}
_ALL_BLOCK_ENVS = _BLOCK_ENVS | _THEOREM_ENVS


def _text_inner(obj: SlideText) -> str:
    content = _styled_text(obj)
    block = getattr(obj, "block", "")
    title = getattr(obj, "block_title", "") or ""
    if block in _BLOCK_ENVS:
        content = f"\\begin{{{block}}}{{{title}}}{content}\\end{{{block}}}"
    elif block in _THEOREM_ENVS:
        arg = f"[{title}]" if title else ""
        content = f"\\begin{{{block}}}{arg}{content}\\end{{{block}}}"
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
        st = {"dashed": "dashed", "dotted": "dotted"}.get(
            getattr(obj, "border_style", "solid"))
        if st:
            opts.append(st)
    if fc:
        pre.append(f"\\definecolor{{ksBoxFill}}{{HTML}}{{{fc}}}")
        fc2 = _hex_to_rgb_arg(getattr(obj, "fill2", ""))
        if fc2:
            # Gradient box background (top→bottom or left→right).
            pre.append(f"\\definecolor{{ksBoxFillB}}{{HTML}}{{{fc2}}}")
            if getattr(obj, "gradient", "vertical") == "horizontal":
                opts += ["left color=ksBoxFill", "right color=ksBoxFillB"]
            else:
                opts += ["top color=ksBoxFill", "bottom color=ksBoxFillB"]
        else:
            opts.append("fill=ksBoxFill")
        fo = getattr(obj, "fill_opacity", 1.0)
        if fo < 1.0:
            opts.append(f"fill opacity={_fmt(fo)}")
    if getattr(obj, "corner", "sharp") == "rounded":
        opts.append(f"rounded corners={_fmt(getattr(obj, 'corner_radius', 4.0))}pt")
    if getattr(obj, "shadow", False):
        opts.append("drop shadow")
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


def _picture_placeholder_box(width_expr: str, height_expr: str) -> str:
    r"""An empty framed box of the given width/height — the visual stand-in for
    a picture that has no image yet. Never prints a path."""
    return (r"{\setlength{\fboxsep}{0pt}\framebox[" + width_expr
            + r"]{\rule{0pt}{" + height_expr + r"}}}")


def _picture_placeholder(obj: SlidePicture) -> str:
    r"""Absolutely-placed empty box the size of the picture, shown where an
    image would go when none has been added."""
    box = _picture_placeholder_box(f"{_fmt(obj.w)}\\paperwidth",
                                   f"{_fmt(obj.h)}\\paperheight")
    return (f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"{box}\n\\end{{textblock}}")


_TEX_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".pdf", ".eps"}


def _serialize_picture(obj: SlidePicture) -> str:
    # A format XeTeX can't include (gif, wmf...) would be read as TeX
    # source and wreck the compile — show the empty box instead.
    if not obj.path or Path(obj.path).suffix.lower() not in _TEX_IMAGE_EXTS:
        return _picture_placeholder(obj)
    return (f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"{_frame_wrap(_picture_graphic(obj), obj)}\n"
            f"\\end{{textblock}}")


def _video_face(obj: SlideVideo) -> str:
    r"""What the video shows on the page: the poster image stretched to the
    box, or a dark player-style placeholder with a white play triangle.
    The placeholder is deliberately built from TEXT material (colorbox +
    parbox + an amssymb glyph), not tikz or \rule: xdvipdfmx sizes link
    annotations to the glyphs/images inside, so a drawn-only face loses
    its click area entirely (verified — the link vanishes from the PDF)."""
    h = f"{_fmt(obj.h)}\\TPVertModule"
    if obj.poster:
        poster = obj.poster.replace("\\", "/")
        return (f"\\includegraphics[width=\\linewidth,height={h}]"
                f"{{{poster}}}")
    return ("{\\setlength{\\fboxsep}{0pt}\\colorbox[HTML]{262626}"
            f"{{\\parbox[b][{h}][c]{{\\linewidth}}"
            "{\\centering\\textcolor{white}"
            "{\\Huge$\\blacktriangleright$}}}}")


def _serialize_video(obj: SlideVideo) -> str:
    r"""A click-to-play video area: a hyperref ``file:`` launch link over
    the poster/placeholder, so clicking it in the finished PDF opens the
    video in the system player. This is deliberately NOT beamer's
    ``\movie`` (the ``multimedia`` package): under tectonic's XeTeX +
    xdvipdfmx pipeline \movie is silently dropped, while a file: link
    survives as a real /Launch annotation (verified)."""
    face = _video_face(obj)
    path = (obj.path or "").replace("\\", "/")
    if path:
        face = f"\\href{{file:{path}}}{{{face}}}"
    return (f"\\begin{{textblock}}{{{_fmt(obj.w)}}}({_fmt(obj.x)},{_fmt(obj.y)})\n"
            f"{face}\n\\end{{textblock}}")


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
        if block in _ALL_BLOCK_ENVS:
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
    if isinstance(obj, SlidePicture):
        if obj.path:
            inner = _frame_wrap(
                _picture_graphic(obj, "\\textwidth", "\\textheight"), obj)
        else:
            inner = _picture_placeholder_box(f"{_fmt(obj.w)}\\textwidth",
                                             f"{_fmt(obj.h)}\\textheight")
        return "\\begin{center}" + inner + "\\end{center}"
    return None


def _column_content(obj) -> str | None:
    """A locked object's content when it sits inside a beamer column —
    sized to the column (\\linewidth), no full-width centring."""
    if isinstance(obj, SlideText):
        return _text_inner(obj)
    if isinstance(obj, SlideTable):
        return _table_inner(obj)
    if isinstance(obj, SlidePicture):
        if obj.path:
            # Fill the column width (the box width already set the column
            # size), capping the height to the box's slide-fraction.
            return _frame_wrap(_picture_graphic(obj, rel_h="\\textheight",
                                                width_expr="\\linewidth"), obj)
        return _picture_placeholder_box("\\linewidth",
                                        f"{_fmt(obj.h)}\\textheight")
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

# Theme typefaces (PowerPoint's "theme fonts"): key → (display name,
# preamble lines). All packages are on CTAN so tectonic fetches them on
# first use. Serif faces also switch beamer to its serif font theme,
# otherwise beamer keeps typesetting in the sans default and the package
# appears to do nothing. Emitted AFTER \usepackage{lmodern} (lmodern
# resets the default families, so it must not come last).
FONT_FAMILIES: dict[str, tuple[str, list[str]]] = {
    "helvetica": ("Helvetica / Arial-like",
                  ["\\usepackage[scaled=0.95]{helvet}",
                   "\\renewcommand{\\familydefault}{\\sfdefault}"]),
    "fira": ("Fira Sans", ["\\usepackage[sfdefault]{FiraSans}"]),
    "sourcesans": ("Source Sans Pro",
                   ["\\usepackage[default]{sourcesanspro}"]),
    "lato": ("Lato", ["\\usepackage[default]{lato}"]),
    "opensans": ("Open Sans", ["\\usepackage[default]{opensans}"]),
    "roboto": ("Roboto", ["\\usepackage[sfdefault]{roboto}"]),
    "times": ("Times (serif)",
              ["\\usepackage{newtxtext}", "\\usefonttheme{serif}"]),
    "palatino": ("Palatino (serif)",
                 ["\\usepackage{newpxtext}", "\\usefonttheme{serif}"]),
    "charter": ("Charter (serif)",
                ["\\usepackage{XCharter}", "\\usefonttheme{serif}"]),
}

# The full set of beamer presentation themes and colour themes KherveSlide
# offers. Canonical here (Qt-free) so the UI dropdowns (window.py) AND the
# offline warm-up (offline.py) read the SAME lists — add a theme in one place
# and it is both selectable and pre-cached for offline use. The first block is
# beamer's built-ins; the second is third-party themes tectonic fetches (all
# verified to compile). COLOR_THEMES has no "" entry — that "(none)" choice is
# a UI concern window.py prepends itself.
BEAMER_THEMES: list[str] = [
    "default", "AnnArbor", "Antibes", "Bergen", "Berkeley", "Berlin",
    "Boadilla", "CambridgeUS", "Copenhagen", "Darmstadt", "Dresden",
    "Frankfurt", "Goettingen", "Hannover", "Ilmenau", "JuanLesPins",
    "Luebeck", "Madrid", "Malmoe", "Marburg", "Montpellier", "PaloAlto",
    "Pittsburgh", "Rochester", "Singapore", "Szeged", "Warsaw",
    # Third-party themes (fetched by tectonic; verified to compile).
    "metropolis", "Auriga", "Trigon", "sintef",
]
BEAMER_COLOR_THEMES: list[str] = [
    "default", "albatross", "beaver", "beetle", "crane", "dolphin",
    "dove", "fly", "lily", "monarca", "orchid", "rose", "seagull",
    "seahorse", "spruce", "structure", "whale", "wolverine",
]


def _font_family_lines(spec) -> list[str]:
    """Preamble lines for the theme's typeface. Kept separate from
    ``_theme_spec_lines`` because they must land after ``lmodern``."""
    if spec is None or not getattr(spec, "enabled", False):
        return []
    entry = FONT_FAMILIES.get(getattr(spec, "font_family", "") or "")
    return list(entry[1]) if entry else []


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
    bg1 = _hex_to_rgb_arg(spec.canvas_bg or "")
    bg2 = _hex_to_rgb_arg(getattr(spec, "canvas_bg2", "") or "")
    if bg1 and bg2:
        # Gradient slide background: beamer's vertical-shading canvas.
        lines.append(f"\\definecolor{{ksBgTop}}{{HTML}}{{{bg1}}}")
        lines.append(f"\\definecolor{{ksBgBot}}{{HTML}}{{{bg2}}}")
        lines.append("\\setbeamertemplate{background canvas}"
                     "[vertical shading][top=ksBgTop,bottom=ksBgBot]")
    else:
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
    if getattr(spec, "footer_bar", False):
        # A full-width bar in the title-bar colours: author | title | n / N.
        # Without a title bar, title_fg is the bar colour itself, so pick
        # whichever of black / white reads on the bar instead.
        bar = spec.title_bg or spec.structure or "#1F4E79"
        fg = cname(spec.title_fg if spec.title_bg else _readable_on(bar))
        bg = cname(bar)
        lines += [
            f"\\setbeamercolor{{ks footer bar}}{{fg={fg},bg={bg}}}",
            "\\setbeamertemplate{footline}{%",
            "\\leavevmode\\hbox{\\begin{beamercolorbox}[wd=\\paperwidth,"
            "ht=2.6ex,dp=1.1ex,leftskip=1.5ex,rightskip=1.5ex]{ks footer bar}%",
            "\\usebeamerfont{author in head/foot}\\insertshortauthor\\hfill"
            "\\insertshorttitle\\hfill"
            "\\insertframenumber\\,/\\,\\inserttotalframenumber",
            "\\end{beamercolorbox}}\\vskip0pt}"]
    return lines


def _readable_on(hex_color: str) -> str:
    """Black or white text, whichever reads better on *hex_color*."""
    h = _hex_to_rgb_arg(hex_color)
    if not h:
        return "#FFFFFF"
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return "#000000" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55 \
        else "#FFFFFF"


def _logo_lines(spec) -> list[str]:
    """The theme logo, drawn from the footline as a page overlay so it
    sits ON TOP of the title bar (a background-layer logo would be hidden
    under it). Emitted after every other footline definition, since a
    later \\setbeamertemplate{footline} would drop the hook. Needs tikz."""
    if spec is None or not getattr(spec, "enabled", False):
        return []
    path = (getattr(spec, "logo", "") or "").replace("\\", "/")
    if not path:
        return []
    corner = getattr(spec, "logo_corner", "tr")
    if corner not in ("tr", "tl", "br", "bl"):
        corner = "tr"
    v = "north" if corner[0] == "t" else "south"
    h = "east" if corner[1] == "r" else "west"
    size = _fmt(max(0.03, min(0.4, getattr(spec, "logo_size", 0.12))))
    dx = "-0.025" if h == "east" else "0.025"
    # Bottom logos clear a footer bar / line.
    low = spec.footer_bar or spec.footline_rule
    dy = "-0.025" if v == "north" else ("0.07" if low else "0.025")
    return [
        "\\addtobeamertemplate{footline}{%",
        "\\begin{tikzpicture}[remember picture,overlay]"
        f"\\node[anchor={v} {h},inner sep=0pt] at "
        f"([xshift={dx}\\paperheight,yshift={dy}\\paperheight]"
        f"current page.{v} {h})"
        f"{{\\includegraphics[height={size}\\paperheight]{{{path}}}}};"
        "\\end{tikzpicture}}{}"]


def theme_to_sty(spec, name: str, base_theme: str = "",
                 color_theme: str = "") -> str:
    """A standalone ``beamertheme<name>.sty`` for the user-built theme —
    the same mechanism every published beamer theme (Madrid, metropolis,
    the Overleaf gallery ones) uses. Drop the file next to any .tex and
    ``\\usetheme{<name>}`` it, inside or outside KherveSlide."""
    from dataclasses import replace
    safe = "".join(c for c in name if c.isalnum()) or "Custom"
    lines = [
        f"% beamertheme{safe}.sty - generated by KherveSlide.",
        "% Use with:  \\usetheme{" + safe + "}",
        "\\NeedsTeXFormat{LaTeX2e}",
        f"\\ProvidesPackage{{beamertheme{safe}}}",
        "\\mode<presentation>",
    ]
    # Layer over the base theme exactly as the app compiles it.
    if base_theme and base_theme != "default":
        lines.append(f"\\usetheme{{{base_theme}}}")
    if color_theme:
        lines.append(f"\\usecolortheme{{{color_theme}}}")
    spec_on = replace(spec, enabled=True)
    logo = _logo_lines(spec_on)
    if logo:
        lines.append("\\RequirePackage{tikz}")
    lines += _theme_spec_lines(spec_on)
    lines += _font_family_lines(spec_on)
    lines += logo
    lines += ["\\mode<all>", ""]
    return "\n".join(lines)


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
    # Endpoints may run in any direction, so place the textblock at the
    # bounding-box corner with a positive width and draw between the two ends
    # as box-fractions (a textblock width can't be negative).
    left, top = min(obj.x, obj.x + obj.w), min(obj.y, obj.y + obj.h)
    bw, bh = abs(obj.w), abs(obj.h)
    f1x = 0.0 if bw == 0 else (obj.x - left) / bw
    f2x = 0.0 if bw == 0 else (obj.x + obj.w - left) / bw
    f1y = 0.0 if bh == 0 else (obj.y - top) / bh
    f2y = 0.0 if bh == 0 else (obj.y + obj.h - top) / bh
    wlen, hlen = "\\linewidth", f"{_fmt(bh)}\\TPVertModule"

    def loc(fx, fy):
        return f"({_fmt(fx)}\\linewidth,-{_fmt(fy * bh)}\\TPVertModule)"

    pic = (
        f"\\begin{{tikzpicture}}\n"
        f"\\useasboundingbox (0,0) rectangle ({wlen},-{hlen});\n"
        f"\\draw[line width={_fmt(obj.width_pt)}pt,color=ksline{idx}"
        f"{arrow}{dash}{opacity}] {loc(f1x, f1y)} -- {loc(f2x, f2y)};\n"
        f"\\end{{tikzpicture}}")
    return (f"\\definecolor{{ksline{idx}}}{{HTML}}{{{colour}}}\n"
            f"\\begin{{textblock}}{{{_fmt(bw)}}}({_fmt(left)},{_fmt(top)})\n"
            f"{pic}\n\\end{{textblock}}")


def _eff_shape(obj: SlideShape) -> str:
    if obj.shape == "rect" and getattr(obj, "corner", "sharp") == "rounded":
        return "rounded_rect"
    return obj.shape


def _shape_tikz(obj: SlideShape, idx: int, pt, center: str,
                xr: str, yr: str) -> tuple[str, str, str]:
    """Build (color-defs, path-options, path-body) for a shape from its
    normalised outline. *pt(nx, ny)* formats a box-relative point as a tikz
    coordinate; *center*/*xr*/*yr* size the ellipse case."""
    kind = _shapes.outline(_eff_shape(obj))
    defs, opts = "", []
    if obj.fill:
        defs += (f"\\definecolor{{ksfill{idx}}}{{HTML}}"
                 f"{{{_hex_to_rgb_arg(obj.fill) or 'ffffff'}}}%\n")
        if getattr(obj, "fill2", ""):
            # Gradient fill: tikz shades between the two colours, top→bottom
            # (vertical) or left→right (horizontal).
            defs += (f"\\definecolor{{ksfillb{idx}}}{{HTML}}"
                     f"{{{_hex_to_rgb_arg(obj.fill2) or 'ffffff'}}}%\n")
            if getattr(obj, "gradient", "vertical") == "horizontal":
                opts += [f"left color=ksfill{idx}", f"right color=ksfillb{idx}"]
            else:
                opts += [f"top color=ksfill{idx}", f"bottom color=ksfillb{idx}"]
        else:
            opts.append(f"fill=ksfill{idx}")
    if obj.border_color and obj.border_width > 0:
        defs += (f"\\definecolor{{ksshape{idx}}}{{HTML}}"
                 f"{{{_hex_to_rgb_arg(obj.border_color) or '000000'}}}%\n")
        opts.append(f"draw=ksshape{idx}")
        opts.append(f"line width={_fmt(obj.border_width)}pt")
        st = {"dashed": "dashed", "dotted": "dotted"}.get(
            getattr(obj, "style", "solid"))
        if st:
            opts.append(st)
    if obj.opacity < 1.0:
        opts.append(f"opacity={_fmt(obj.opacity)}")
    if kind[0] == "rect" and kind[1]:
        opts.append("rounded corners=6pt")
    if obj.rotation:
        opts.append(f"rotate around={{{_fmt(-obj.rotation)}:{center}}}")
    if kind[0] == "ellipse":
        body = f"{center} ellipse [x radius={xr}, y radius={yr}]"
    elif kind[0] == "rect":
        body = f"{pt(0, 0)} rectangle {pt(1, 1)}"
    else:
        body = " -- ".join(pt(nx, ny) for nx, ny in kind[1]) + " -- cycle"
    return defs, ", ".join(opts), body


def _serialize_shape(obj: SlideShape, gap: float, idx: int) -> str:
    wlen, hlen = "\\linewidth", f"{_fmt(obj.h)}\\TPVertModule"

    def pt(nx, ny):
        return (f"({_fmt(nx)}\\linewidth,"
                f"-{_fmt(ny * obj.h)}\\TPVertModule)")

    center = pt(0.5, 0.5)
    xr, yr = "0.5\\linewidth", f"{_fmt(0.5 * obj.h)}\\TPVertModule"
    defs, opts, body = _shape_tikz(obj, idx, pt, center, xr, yr)
    pic = (f"\\begin{{tikzpicture}}\n"
           f"\\useasboundingbox (0,0) rectangle ({wlen},-{hlen});\n"
           f"\\path[{opts}] {body};\n"
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
    nw = "current page.north west"

    def pt(nx, ny):
        x = gap + (obj.x + nx * obj.w) * span
        y = gap + (obj.y + ny * obj.h) * span
        return (f"([xshift={_fmt(x)}\\paperwidth,"
                f"yshift=-{_fmt(y)}\\paperheight]{nw})")

    center = pt(0.5, 0.5)
    xr = f"{_fmt(0.5 * obj.w * span)}\\paperwidth"
    yr = f"{_fmt(0.5 * obj.h * span)}\\paperheight"
    defs, opts, body = _shape_tikz(obj, idx, pt, center, xr, yr)
    return (defs +
            "\\begin{tikzpicture}[remember picture,overlay]\n"
            f"\\path[{opts}] {body};\n"
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


def _master_background_block(master, gap: float, counter: list) -> list[str]:
    """Render the master slide's objects as the bottom background layer of a
    frame — painted behind the slide's own content. Master objects are always
    absolute (never flowed, whatever their ``locked`` flag): text / pictures /
    tables via textpos, lines / shapes via the overlay (remember picture) tikz
    emitters, same as a slide's own "behind" shapes. List order = z-order, so
    later master objects paint on top of earlier ones (but all under the
    slide). ``counter`` is the deck-wide index shared with the slide so line /
    shape colour names never collide."""
    blocks: list[str] = []
    for o in getattr(master, "objects", []):
        if isinstance(o, SlideLine):
            blocks.append(_serialize_line_bg(o, gap, counter[0]))
            counter[0] += 1
        elif isinstance(o, SlideShape):
            blocks.append(_serialize_shape_bg(o, gap, counter[0]))
            counter[0] += 1
        elif isinstance(o, SlideText):
            blocks.append(_serialize_text(o))
        elif isinstance(o, SlideTable):
            blocks.append(_serialize_table(o))
        elif isinstance(o, SlidePicture):
            blocks.append(_serialize_picture(o))
    return [b for b in blocks if b]


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
    if isinstance(obj, SlideVideo):
        return _serialize_video(obj)
    return None


def _page_number_block(mode: str, gap: float) -> str:
    """A small slide-number overlay at the bottom-right corner. Placed via
    textpos so it shows on plain frames too (where the theme footline is
    suppressed)."""
    inner = _page_number_macro(mode) or "\\insertframenumber"
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
              SlideShape: "shape", SlideVideo: "video"}


def _obj_label(obj) -> str:
    return _OBJ_LABEL.get(type(obj), "object")


def _serialize_slide(slide: Slide, plain: bool = True, gap: float = 0.0,
                     counter: list | None = None,
                     page_number: str = "none",
                     nav_symbols: bool = False, index: int = 0,
                     master=None) -> str:
    if counter is None:
        counter = [0]
    # [t] top-aligns the flowed (locked) content so a tall heading isn't
    # pushed off-screen by beamer's default vertical centering.
    opts = ("plain," if plain else "") + "t"
    bar = "% " + "=" * 70
    head = f"% Slide {index + 1}" + (f" - {slide.title}" if slide.title else "")

    def _is_flow(o) -> bool:
        return (getattr(o, "locked", True)
                and not isinstance(o, (SlideLine, SlideShape, SlideVideo)))

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

    # The slide's own background COLOUR is set via beamer's "background canvas"
    # colour — the true bottom layer, painted behind every bit of frame content
    # (flow body included). A textpos \colorbox overlay can't do this: textpos
    # blocks are placed in a late shipout stage and paint ON TOP of the body,
    # so the old overlay covered the text. Scoped to this frame with a group.
    bg = _hex_to_rgb_arg(blend_over_white(slide.bg, slide.bg_alpha))
    bg_canvas = []
    if bg:
        cname = f"ksbg{index}"
        # [default] resets any theme-level shading template so this slide's
        # flat colour actually shows (a shading ignores the bg beamercolor).
        bg_canvas = [f"\\definecolor{{{cname}}}{{HTML}}{{{bg}}}",
                     f"\\setbeamercolor{{background canvas}}{{bg={cname}}}",
                     "\\setbeamertemplate{background canvas}[default]"]

    # The frame background TEMPLATE (drawn behind the flow body, over the
    # canvas) carries the master slide and this slide's "behind" shapes.
    master_blocks = _master_background_block(master, gap, counter) if master else []
    parts = [bar, head, bar]
    tmpl_parts = list(master_blocks)
    for o in behind:
        blk = _overlay_behind(o, gap, counter)
        if blk:
            tmpl_parts.append(blk)
    scoped = bool(bg_canvas or tmpl_parts)
    if scoped:
        parts.append("{%  scoped: slide background colour + behind-content layer")
        parts.extend(bg_canvas)
        if tmpl_parts:
            parts.append("\\setbeamertemplate{background}{%")
            parts.extend(tmpl_parts)
            parts.append("}")
    parts.append(f"\\begin{{frame}}[{opts}]")
    if slide.title:
        parts.append(f"  \\frametitle{{{slide.title}}}")
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
    if nav_symbols and plain:
        # Plain frames drop beamer's native symbols along with the footline,
        # so overlay them here; decorated frames show the native ones instead.
        parts.append("\n  % navigation symbols (bottom-right)")
        parts.append(_nav_symbols_block(gap))
    if page_number and page_number != "none" and plain:
        # Plain frames drop the footline, so the number (normally in the right
        # foot) is overlaid at the bottom-right here instead.
        parts.append("\n  % slide number (plain frame — no footline)")
        parts.append(_page_number_block(page_number, gap))
    parts.append("\\end{frame}")
    if scoped:
        parts.append("}")     # close the scoped-background group
    return "\n".join(parts)


def _page_number_macro(mode: str) -> str:
    """The beamer counters for the slide number: just the frame number, or
    'frame / total'. Empty when off."""
    if mode == "number":
        return "\\insertframenumber"
    if mode == "of_total":
        return "\\insertframenumber\\,/\\,\\inserttotalframenumber"
    return ""


def _header_footer_lines(deck) -> list[str]:
    """Custom headline / footline templates from the deck's header and footer
    slots, plus the slide number in the right foot. They only show when frames
    aren't [plain] (decorations on); on plain frames the head/foot lines are
    suppressed and the slide number falls back to a textpos overlay instead."""
    lines: list[str] = []
    header = getattr(deck, "header", "")
    fl = getattr(deck, "foot_left", "")
    fc = getattr(deck, "foot_center", "")
    fr = getattr(deck, "foot_right", "")
    # The slide number lives in the right foot, as beamer's own counters. On
    # plain decks the footline is hidden, so leave it out here (an overlay
    # carries it instead) to avoid emitting the number where it won't show.
    num = _page_number_macro(getattr(deck, "page_number", "none"))
    spec = getattr(deck, "theme_spec", None)
    if spec is not None and spec.enabled and getattr(spec, "footer_bar",
                                                     False):
        num = ""        # the theme's footer bar already shows n / N
    if num and not getattr(deck, "plain_frames", False):
        fr = f"{fr}\\quad {num}" if fr else num
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
    # The theme's typeface must load after lmodern (which resets the
    # default families) to actually take effect.
    lines += _font_family_lines(getattr(deck, "theme_spec", None))
    # Scan the slides AND the master together, so a package (tikz / adjustbox /
    # colortbl / shadows) is pulled in even when only the master needs it.
    _all_objs = [o for s in deck.slides for o in s.objects]
    _all_objs += list(getattr(deck, "master", Slide()).objects)
    # Chemistry typed into boxes (the chemistry editor writes \ce{…};
    # chemfig structures are normally placed as compiled pictures).
    _texts = " ".join(
        [getattr(o, "text", "") or "" for o in _all_objs]
        + [c for o in _all_objs if isinstance(o, SlideTable)
           for row in o.rows for c in row])
    if "\\ce{" in _texts or "\\pu{" in _texts:
        lines.append("\\usepackage[version=4]{mhchem}")
    if "\\chemfig" in _texts:
        lines.append("\\usepackage{chemfig}")
    if any(isinstance(o, SlideVideo) and not o.poster for o in _all_objs):
        # the ▶ glyph on the video placeholder
        lines.append("\\usepackage{amssymb}")
    needs_tikz = any(isinstance(o, (SlideLine, SlideShape)) or _has_frame(o)
                     for o in _all_objs)
    needs_opacity = any(isinstance(o, SlidePicture) and o.opacity < 1.0
                        for o in _all_objs)
    needs_shadow = any(getattr(o, "shadow", False) for o in _all_objs)
    logo = _logo_lines(getattr(deck, "theme_spec", None))
    if needs_tikz or needs_opacity or logo:
        # tikz also drives image opacity (a node with opacity= tints it).
        lines.append("\\usepackage{tikz}")
    if needs_tikz:
        lines.append("\\usetikzlibrary{arrows.meta}")
        if needs_shadow:
            lines.append("\\usetikzlibrary{shadows}")
    if any(isinstance(o, SlidePicture) and _has_crop(o) for o in _all_objs):
        # adjustbox supplies \adjincludegraphics with \width-relative trim.
        lines.append("\\usepackage{adjustbox}")
    if any(isinstance(o, SlideTable) for o in _all_objs):
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
    # Navigation symbols. On decorated frames beamer already shows them at the
    # bottom-right, so we leave its template alone — the native, single-command
    # behaviour, with no per-frame overlay. We only clear the template (and
    # re-insert the symbols per frame via textpos) for plain frames, where
    # beamer drops them along with the footline; or clear it outright to hide
    # them when the user turned them off.
    # beamer shrinks nested list items to a fixed \small / \footnotesize
    # (10 / 8 pt) whatever the box's \fontsize, so a sub-item in a 24 pt box
    # came out tiny. Keep the box's size, as the canvas shows it.
    lines += ["\\setbeamerfont{itemize/enumerate subbody}{size=\\relax}",
              "\\setbeamerfont{itemize/enumerate subsubbody}{size=\\relax}"]
    if not (deck.nav_symbols and not deck.plain_frames):
        lines.append("\\setbeamertemplate{navigation symbols}{}")
    lines += _header_footer_lines(deck)
    lines += logo           # last: a later footline definition drops it
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
                                      deck.nav_symbols, i,
                                      master=getattr(deck, "master", None)))
    lines += ["", "\\end{document}"]
    return "\n".join(lines) + "\n"


# Bullet probes: extra pages at the end of the backdrop PDF, each holding a
# real itemize at one font size — level 1, 2 and 3 on rows at the fractions
# below — so the canvas can copy the theme's actual bullets (shape, colour,
# size and offset from the text) instead of guessing them.
PROBE_SIZES = (11, 18, 28, 40)         # pt; the canvas scales the nearest
PROBE_LEVELS = 3
_PROBE_X, _PROBE_W = 0.04, 0.6         # textblock column (module units)
_PROBE_ROWS = (0.04, 0.36, 0.68)       # textblock tops (module units)
_PROBE_ROW_H = 0.3


def probe_cell(deck: Deck, level: int) -> tuple[float, float, float, float]:
    """Where bullet probe *level* (1-based) sits on its page, as fractions
    of the page: (x0, y0, x1, y1). Mirrors the textpos grid of
    serialize_deck (the deck's gap insets the modules)."""
    g = max(0.0, min(0.45, deck.gap))
    span = 1 - 2 * g
    y = _PROBE_ROWS[level - 1]
    return (g + (_PROBE_X - 0.02) * span, g + y * span,
            g + (_PROBE_X + _PROBE_W) * span, g + (y + _PROBE_ROW_H) * span)


def probe_list_left(deck: Deck) -> float:
    """x of the probe lists' left edge, as a fraction of the page."""
    g = max(0.0, min(0.45, deck.gap))
    return g + _PROBE_X * (1 - 2 * g)


def _probe_frame(size: int) -> list[str]:
    lead = int(round(size * 1.2))
    lines = ["{%  bullet probe (KherveSlide canvas) — not a slide",
             "\\setbeamercolor{background canvas}{bg=white}",
             "\\setbeamertemplate{background canvas}[default]",
             "\\setbeamertemplate{background}{}",
             "\\setbeamertemplate{navigation symbols}{}",
             "\\begin{frame}[plain,noframenumbering]"]
    for level in range(1, PROBE_LEVELS + 1):
        y = _PROBE_ROWS[level - 1]
        # Outer levels get an empty label so only the probed bullet inks.
        body = "\\item x"
        for _ in range(level - 1):
            body = f"\\item[] \\begin{{itemize}}{body}\\end{{itemize}}"
        lines += [
            f"\\begin{{textblock}}{{{_fmt(_PROBE_W)}}}"
            f"({_fmt(_PROBE_X)},{_fmt(y)})",
            f"{{\\raggedright\\fontsize{{{size}}}{{{lead}}}\\selectfont "
            f"\\begin{{itemize}}{body}\\end{{itemize}}\\par}}",
            "\\end{textblock}"]
    lines += ["\\end{frame}", "}"]
    return lines


def serialize_backdrop(deck: Deck) -> str:
    """The presentation with every slide's own objects removed — only what
    the beamer theme draws around them is left: the frame title bar,
    headline / footline, slide numbers, navigation symbols, background and
    the master slide. Page *i* of its PDF is the "empty" themed slide *i*;
    the canvas lays it under the editable boxes so the Visual page looks
    like the LaTeX one. Each frame keeps an invisible ``\\mbox{}`` so an
    empty slide still ships out a page and the page numbers line up.

    After the slides come one bullet-probe page per PROBE_SIZES entry
    ([plain,noframenumbering], so the slide count is unchanged)."""
    slides = [Slide(objects=[], title=s.title, bg=s.bg, bg_alpha=s.bg_alpha,
                    free=s.free)
              for s in deck.slides]
    bare = replace(deck, slides=slides)
    tex = serialize_deck(bare)
    tex = tex.replace("\\end{frame}", "  \\mbox{}\n\\end{frame}")
    probes = []
    for size in PROBE_SIZES:
        probes += [""] + _probe_frame(size)
    return tex.replace("\n\\end{document}",
                       "\n" + "\n".join(probes) + "\n\n\\end{document}")


def deck_body_family(deck: Deck) -> str:
    """"rm" when the deck's theme sets the slides in a serif face (beamer's
    serif font theme, or a serif typeface picked in the theme builder),
    else "sf" — beamer's sans default. The canvas follows it."""
    spec = getattr(deck, "theme_spec", None)
    if spec is None or not getattr(spec, "enabled", False):
        return "sf"
    if getattr(spec, "fonts", "") == "serif":
        return "rm"
    entry = FONT_FAMILIES.get(getattr(spec, "font_family", "") or "")
    if entry and "\\usefonttheme{serif}" in entry[1]:
        return "rm"
    return "sf"
