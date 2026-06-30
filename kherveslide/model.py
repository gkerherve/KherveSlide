"""WYSIWYG beamer deck model — free-positioned slide objects.

This is the source of truth for the Beamer Studio (the slide designer).
It is deliberately separate from the flow-based ``Frame`` block in
``model.py``: a deck is a list of slides, and every object on a slide
carries an *absolute* position and size so the canvas can place it
exactly where the user dragged it, and the serializer can reproduce that
placement with the ``textpos`` package.

Coordinate system: ``x``, ``y``, ``w``, ``h`` are fractions ``0.0..1.0``
of the slide width / height, with ``(0, 0)`` at the top-left corner.
That keeps the model independent of the chosen aspect ratio — the same
deck looks right whether rendered 16:9 or 4:3 — and maps cleanly onto
both the Qt canvas (multiply by the scene size) and beamer's
``\\paperwidth`` / ``\\paperheight``.

Z-order is the position in ``Slide.objects``: later items paint on top,
so "raise" / "lower" are list reorders.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Union


# ---------------- Slide objects ----------------

@dataclass
class SlideText:
    """A free-floating text box. ``text`` is treated as LaTeX source so
    the user can drop in maths (``$\\alpha$``), so the canvas shows it
    verbatim and the PDF preview is the true WYSIWYG check."""
    x: float = 0.1
    y: float = 0.1
    w: float = 0.4
    h: float = 0.15
    text: str = "Text"
    font_pt: int = 20
    color: str = "#000000"        # hex, foreground
    fill: str = ""                # hex box background, "" = transparent
    align: str = "left"           # left | center | right
    bold: bool = False
    italic: bool = False
    # Box frame: a rectangle drawn around the box. "" border = none.
    border_color: str = ""
    border_width: float = 1.0     # pt
    corner: str = "sharp"         # sharp | rounded
    border_style: str = "solid"   # solid | dashed | dotted
    fill_opacity: float = 1.0     # 0..1 (fill transparency)
    shadow: bool = False          # drop shadow behind the box
    corner_radius: float = 4.0    # pt, used when corner == rounded
    # Locked: beamer places the box in the standard flow (you can't drag it).
    # Unlocked: free absolute positioning at (x, y) via textpos.
    locked: bool = True
    # Optional beamer block wrapper: "" | block | alertblock | exampleblock.
    block: str = ""
    block_title: str = ""
    type: str = "SlideText"


@dataclass
class SlidePicture:
    """A free-floating image box. ``path`` is stored as given (absolute or
    relative to the deck file); the box is stretched to ``w`` x ``h`` so
    the canvas and the PDF agree pixel-for-pixel."""
    x: float = 0.1
    y: float = 0.1
    w: float = 0.3
    h: float = 0.3
    path: str = ""
    keep_aspect: bool = True    # lock aspect ratio by default (no distortion)
    opacity: float = 1.0        # 0..1 image transparency
    # Fraction trimmed from each edge of the source image (0..0.9 each side).
    crop_l: float = 0.0
    crop_t: float = 0.0
    crop_r: float = 0.0
    crop_b: float = 0.0
    rotation: float = 0.0       # degrees, clockwise, about the centre
    fill: str = ""              # box background colour ("" = none)
    border_color: str = ""      # box frame colour ("" = none)
    border_width: float = 1.0
    corner: str = "sharp"
    border_style: str = "solid"
    fill_opacity: float = 1.0
    shadow: bool = False
    corner_radius: float = 4.0
    locked: bool = True         # see SlideText.locked
    type: str = "SlidePicture"


def _default_rows() -> list[list[str]]:
    return [["", ""], ["", ""]]


# KherveTeX-style table palette (orange header / light rules).
TABLE_HEADER_BG = "#FCE4D6"
TABLE_HEADER_FG = "#C55A11"
TABLE_RULE = "#F4B183"
TABLE_CAPTION_FG = "#808080"


@dataclass
class SlideTable:
    """A free-floating table. ``rows`` is a list of rows, each a list of
    cell strings (cells may contain LaTeX). The grid is stretched to the
    box; cells are edited in place on the canvas."""
    x: float = 0.1
    y: float = 0.1
    w: float = 0.5
    h: float = 0.25
    rows: list[list[str]] = field(default_factory=_default_rows)
    font_pt: int = 18
    color: str = "#000000"
    border: bool = True        # legacy flag; migrated to ``grid`` on load
    header: bool = True        # first row styled as a coloured header
    caption: str = ""          # optional caption shown under the table
    # --- full table styling ---
    align: str = "left"        # cell text alignment: left | center | right
    grid: str = "all"          # rules: all | horizontal | outer | none
    rule_color: str = TABLE_RULE     # grid line colour
    rule_width: float = 0.8    # grid line thickness in pt
    header_bg: str = TABLE_HEADER_BG    # header row background
    header_fg: str = TABLE_HEADER_FG    # header row text colour
    striped: bool = False      # zebra-stripe the body rows
    stripe_color: str = "#F5F5F5"       # alternate body-row colour
    # Box frame (drawn around the whole table box, separate from the grid).
    fill: str = ""             # box background colour ("" = none)
    border_color: str = ""     # box frame colour ("" = none)
    border_width: float = 1.0
    corner: str = "sharp"
    border_style: str = "solid"
    fill_opacity: float = 1.0
    shadow: bool = False
    corner_radius: float = 4.0
    locked: bool = True        # see SlideText.locked
    type: str = "SlideTable"


@dataclass
class SlideLine:
    """A straight line / arrow drawn along the diagonal of its box (from
    the top-left corner to the bottom-right). Arrowheads optional."""
    x: float = 0.3
    y: float = 0.4
    w: float = 0.4
    h: float = 0.0
    color: str = "#000000"
    width_pt: float = 1.5
    arrow_start: bool = False
    arrow_end: bool = False
    style: str = "solid"        # solid | dashed | dotted
    opacity: float = 1.0        # 0..1
    head_size: float = 1.0      # arrowhead scale (Stealth length multiplier)
    # A line is inherently positioned, so it is always drawn absolutely in
    # the PDF; locked only governs whether it can be dragged on the canvas.
    locked: bool = True
    type: str = "SlideLine"


@dataclass
class SlideShape:
    """A vector shape (rectangle or ellipse) drawn to fill its box. All of
    its appearance — fill, outline colour/width/style, rounded corners,
    opacity and rotation — is editable from the right-click property
    dialog. Like a line it is always positioned absolutely in the PDF;
    ``locked`` only governs whether it can be dragged on the canvas."""
    x: float = 0.3
    y: float = 0.3
    w: float = 0.28
    h: float = 0.22
    shape: str = "rect"         # rect | ellipse
    fill: str = ""              # hex fill colour ("" = no fill)
    border_color: str = "#000000"   # outline colour ("" = no outline)
    border_width: float = 1.5   # pt
    style: str = "solid"        # solid | dashed | dotted
    corner: str = "sharp"       # sharp | rounded (rectangles only)
    opacity: float = 1.0        # 0..1
    rotation: float = 0.0       # degrees, clockwise, about the centre
    locked: bool = False        # freely draggable by default
    type: str = "SlideShape"


SlideObject = Union[SlideText, SlidePicture, SlideTable, SlideLine, SlideShape]


# ---------------- Slide + deck ----------------

@dataclass
class Slide:
    objects: list[SlideObject] = field(default_factory=list)
    title: str = ""               # optional \frametitle
    bg: str = ""                  # hex background colour, "" = theme default
    bg_alpha: float = 1.0         # background opacity 0..1 (blended over white)
    # True: free positioning (absolute textpos). False: standard beamer
    # layout — content flows in the frame body and beamer places it.
    free: bool = True
    type: str = "Slide"


@dataclass
class ThemeSpec:
    """A user-built beamer theme layered on top of the base \\usetheme:
    inner/outer/font sub-themes, bullet style, key colours and the
    frametitle font size. Empty fields are left to the base theme."""
    enabled: bool = False
    inner: str = ""            # default|circles|rectangles|rounded|inmargin
    outer: str = ""            # default|infolines|miniframes|smoothbars|…|tree
    fonts: str = ""            # default|serif|professionalfonts|structurebold|…
    bullets: str = ""          # default|circle|square|ball|triangle
    structure: str = ""        # hex — drives many derived beamer colours
    text_fg: str = ""          # normal text
    canvas_bg: str = ""        # slide background canvas
    title_fg: str = ""         # frametitle / title foreground
    title_bg: str = ""         # frametitle background
    block_bg: str = ""         # block title background
    frametitle_size: str = ""  # small|normal|large|Large|huge
    # Decorative rules (lines).
    title_rule: bool = False   # a rule under the frame title
    footline_rule: bool = False  # a coloured bar along the bottom edge
    rule_color: str = ""       # hex for the rules; "" = use structure colour
    rule_width: float = 1.5    # rule thickness in pt
    type: str = "ThemeSpec"


@dataclass
class Deck:
    slides: list[Slide] = field(default_factory=list)
    title: str = "Presentation"
    author: str = ""
    theme: str = "default"        # beamer theme name (\usetheme)
    color_theme: str = ""         # beamer colour theme (\usecolortheme)
    aspect: str = "169"           # "169" | "43" | "1610" | "32"
    template: str = "Blank"       # name of the template this deck started from
    # Theme decorations (title bars / footers / nav) are shown by default.
    # Turn this on to strip them to [plain] frames (handy when absolutely
    # positioned boxes would overlap the theme furniture).
    plain_frames: bool = False
    # Custom page size in cm (both > 0 overrides the aspect ratio). 0 = use
    # the aspect preset (beamer's default ~12.8 x 9.6 cm for 16:9).
    page_w_cm: float = 0.0
    page_h_cm: float = 0.0
    # Uniform content margin ("gap") as a fraction of the page (0..0.45).
    # Object coordinates are 0..1 within the page minus this gap, so every
    # box keeps the same breathing room from the slide edge.
    gap: float = 0.0
    # beamer's prev/next navigation symbols, shown on the PDF itself. On by
    # default — that's the native way to page through the slides. (They make
    # xdvipdfmx emit a harmless out-of-page annotation warning, filtered from
    # the console.) Turn off from Presentation ▸ Navigation symbols.
    nav_symbols: bool = True
    # Slide/page number shown at the bottom-right of every slide:
    # "none" | "number" (just the slide number) | "of_total" (n / N).
    page_number: str = "none"
    # Custom header line and footer slots (shown when decorations are on).
    header: str = ""
    foot_left: str = ""
    foot_center: str = ""
    foot_right: str = ""
    # User-built theme overrides (see ThemeSpec). Applied when enabled.
    theme_spec: ThemeSpec = field(default_factory=ThemeSpec)
    type: str = "Deck"


# ---------------- JSON serialisation ----------------

def deck_to_json(deck: Deck) -> str:
    return json.dumps(asdict(deck), indent=2, ensure_ascii=False)


def deck_from_json(s: str) -> Deck:
    return _build_deck(json.loads(s))


def _build_object(d: dict) -> SlideObject:
    t = d.get("type")
    if t == "SlideText":
        return SlideText(
            x=float(d.get("x", 0.1)), y=float(d.get("y", 0.1)),
            w=float(d.get("w", 0.4)), h=float(d.get("h", 0.15)),
            text=str(d.get("text", "")),
            font_pt=int(d.get("font_pt", 20)),
            color=str(d.get("color", "#000000")),
            fill=str(d.get("fill", "")),
            align=str(d.get("align", "left")),
            bold=bool(d.get("bold", False)),
            italic=bool(d.get("italic", False)),
            border_color=str(d.get("border_color", "")),
            border_width=float(d.get("border_width", 1.0)),
            corner=str(d.get("corner", "sharp")),
            border_style=str(d.get("border_style", "solid")),
            fill_opacity=float(d.get("fill_opacity", 1.0)),
            shadow=bool(d.get("shadow", False)),
            corner_radius=float(d.get("corner_radius", 4.0)),
            locked=bool(d.get("locked", True)),
            block=str(d.get("block", "")),
            block_title=str(d.get("block_title", "")),
        )
    if t == "SlidePicture":
        return SlidePicture(
            x=float(d.get("x", 0.1)), y=float(d.get("y", 0.1)),
            w=float(d.get("w", 0.3)), h=float(d.get("h", 0.3)),
            path=str(d.get("path", "")),
            keep_aspect=bool(d.get("keep_aspect", True)),
            opacity=float(d.get("opacity", 1.0)),
            crop_l=float(d.get("crop_l", 0.0)),
            crop_t=float(d.get("crop_t", 0.0)),
            crop_r=float(d.get("crop_r", 0.0)),
            crop_b=float(d.get("crop_b", 0.0)),
            rotation=float(d.get("rotation", 0.0)),
            fill=str(d.get("fill", "")),
            border_color=str(d.get("border_color", "")),
            border_width=float(d.get("border_width", 1.0)),
            corner=str(d.get("corner", "sharp")),
            border_style=str(d.get("border_style", "solid")),
            fill_opacity=float(d.get("fill_opacity", 1.0)),
            shadow=bool(d.get("shadow", False)),
            corner_radius=float(d.get("corner_radius", 4.0)),
            locked=bool(d.get("locked", True)),
        )
    if t == "SlideTable":
        rows = d.get("rows") or _default_rows()
        border = bool(d.get("border", True))
        # Migrate the legacy on/off ``border`` flag to the richer ``grid``.
        grid = str(d.get("grid", "")) or ("all" if border else "none")
        return SlideTable(
            x=float(d.get("x", 0.1)), y=float(d.get("y", 0.1)),
            w=float(d.get("w", 0.5)), h=float(d.get("h", 0.25)),
            rows=[[str(c) for c in row] for row in rows],
            font_pt=int(d.get("font_pt", 18)),
            color=str(d.get("color", "#000000")),
            border=border,
            header=bool(d.get("header", True)),
            caption=str(d.get("caption", "")),
            align=str(d.get("align", "left")),
            grid=grid,
            rule_color=str(d.get("rule_color", TABLE_RULE)),
            rule_width=float(d.get("rule_width", 0.8)),
            header_bg=str(d.get("header_bg", TABLE_HEADER_BG)),
            header_fg=str(d.get("header_fg", TABLE_HEADER_FG)),
            striped=bool(d.get("striped", False)),
            stripe_color=str(d.get("stripe_color", "#F5F5F5")),
            fill=str(d.get("fill", "")),
            border_color=str(d.get("border_color", "")),
            border_width=float(d.get("border_width", 1.0)),
            corner=str(d.get("corner", "sharp")),
            border_style=str(d.get("border_style", "solid")),
            fill_opacity=float(d.get("fill_opacity", 1.0)),
            shadow=bool(d.get("shadow", False)),
            corner_radius=float(d.get("corner_radius", 4.0)),
            locked=bool(d.get("locked", True)),
        )
    if t == "SlideLine":
        return SlideLine(
            x=float(d.get("x", 0.3)), y=float(d.get("y", 0.4)),
            w=float(d.get("w", 0.4)), h=float(d.get("h", 0.0)),
            color=str(d.get("color", "#000000")),
            width_pt=float(d.get("width_pt", 1.5)),
            arrow_start=bool(d.get("arrow_start", False)),
            arrow_end=bool(d.get("arrow_end", False)),
            style=str(d.get("style", "solid")),
            opacity=float(d.get("opacity", 1.0)),
            head_size=float(d.get("head_size", 1.0)),
            locked=bool(d.get("locked", True)),
        )
    if t == "SlideShape":
        return SlideShape(
            x=float(d.get("x", 0.3)), y=float(d.get("y", 0.3)),
            w=float(d.get("w", 0.28)), h=float(d.get("h", 0.22)),
            shape=str(d.get("shape", "rect")),
            fill=str(d.get("fill", "")),
            border_color=str(d.get("border_color", "#000000")),
            border_width=float(d.get("border_width", 1.5)),
            style=str(d.get("style", "solid")),
            corner=str(d.get("corner", "sharp")),
            opacity=float(d.get("opacity", 1.0)),
            rotation=float(d.get("rotation", 0.0)),
            locked=bool(d.get("locked", False)),
        )
    raise ValueError(f"Unknown slide object type: {t!r}")


def object_to_dict(obj) -> dict:
    """Serialise a single slide object (for clipboard copy/paste)."""
    return asdict(obj)


def build_object(d: dict) -> SlideObject:
    """Rebuild a single slide object from its dict (clipboard paste)."""
    return _build_object(d)


def _build_slide(d: dict) -> Slide:
    # Locking moved from per-slide (`free`) to per-object (`locked`). Decks
    # saved before that have no per-object flag, so migrate from the slide:
    # an old "free" slide had freely placed objects (unlocked); an old
    # standard slide had beamer-placed objects (locked).
    slide_free = bool(d.get("free", True))
    objs = []
    for od in d.get("objects", []):
        obj = _build_object(od)
        if "locked" not in od:
            obj.locked = not slide_free
        objs.append(obj)
    return Slide(
        objects=objs,
        title=str(d.get("title", "")),
        bg=str(d.get("bg", "")),
        bg_alpha=float(d.get("bg_alpha", 1.0)),
        free=slide_free,
    )


def blend_over_white(hex_color: str, alpha: float) -> str:
    """Composite *hex_color* at *alpha* (0..1) over white — the slide page
    is white, so a semi-transparent background reads as a tint. Returns a
    solid ``#RRGGBB`` so it works without any LaTeX transparency package."""
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return hex_color
    a = max(0.0, min(1.0, alpha))
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return hex_color
    r = round(r * a + 255 * (1 - a))
    g = round(g * a + 255 * (1 - a))
    b = round(b * a + 255 * (1 - a))
    return f"#{r:02X}{g:02X}{b:02X}"


def _build_deck(d: dict) -> Deck:
    if d.get("type") != "Deck":
        raise ValueError("Not a beamer deck")
    return Deck(
        slides=[_build_slide(s) for s in d.get("slides", [])],
        title=str(d.get("title", "Presentation")),
        author=str(d.get("author", "")),
        theme=str(d.get("theme", "default")),
        color_theme=str(d.get("color_theme", "")),
        aspect=str(d.get("aspect", "169")),
        template=str(d.get("template", "Blank")),
        plain_frames=bool(d.get("plain_frames", False)),
        page_w_cm=float(d.get("page_w_cm", 0.0)),
        page_h_cm=float(d.get("page_h_cm", 0.0)),
        gap=float(d.get("gap", 0.0)),
        nav_symbols=bool(d.get("nav_symbols", True)),
        page_number=str(d.get("page_number", "none")),
        header=str(d.get("header", "")),
        foot_left=str(d.get("foot_left", "")),
        foot_center=str(d.get("foot_center", "")),
        foot_right=str(d.get("foot_right", "")),
        theme_spec=_build_theme_spec(d.get("theme_spec", {})),
    )


def _build_theme_spec(d: dict) -> ThemeSpec:
    return ThemeSpec(
        enabled=bool(d.get("enabled", False)),
        inner=str(d.get("inner", "")),
        outer=str(d.get("outer", "")),
        fonts=str(d.get("fonts", "")),
        bullets=str(d.get("bullets", "")),
        structure=str(d.get("structure", "")),
        text_fg=str(d.get("text_fg", "")),
        canvas_bg=str(d.get("canvas_bg", "")),
        title_fg=str(d.get("title_fg", "")),
        title_bg=str(d.get("title_bg", "")),
        block_bg=str(d.get("block_bg", "")),
        frametitle_size=str(d.get("frametitle_size", "")),
        title_rule=bool(d.get("title_rule", False)),
        footline_rule=bool(d.get("footline_rule", False)),
        rule_color=str(d.get("rule_color", "")),
        rule_width=float(d.get("rule_width", 1.5)),
    )


# ---------------- Z-order helpers ----------------

def raise_object(slide: Slide, index: int) -> int:
    """Move the object one step up the z-stack (towards the front).
    Returns the new index."""
    if 0 <= index < len(slide.objects) - 1:
        slide.objects[index], slide.objects[index + 1] = (
            slide.objects[index + 1], slide.objects[index])
        return index + 1
    return index


def lower_object(slide: Slide, index: int) -> int:
    """Move the object one step down the z-stack (towards the back)."""
    if 0 < index < len(slide.objects):
        slide.objects[index], slide.objects[index - 1] = (
            slide.objects[index - 1], slide.objects[index])
        return index - 1
    return index


def to_front(slide: Slide, index: int) -> int:
    if 0 <= index < len(slide.objects):
        obj = slide.objects.pop(index)
        slide.objects.append(obj)
        return len(slide.objects) - 1
    return index


def to_back(slide: Slide, index: int) -> int:
    if 0 <= index < len(slide.objects):
        obj = slide.objects.pop(index)
        slide.objects.insert(0, obj)
        return 0
    return index
