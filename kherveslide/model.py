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
    keep_aspect: bool = False
    type: str = "SlidePicture"


SlideObject = Union[SlideText, SlidePicture]


# ---------------- Slide + deck ----------------

@dataclass
class Slide:
    objects: list[SlideObject] = field(default_factory=list)
    title: str = ""               # optional \frametitle
    bg: str = ""                  # hex background colour, "" = theme default
    type: str = "Slide"


@dataclass
class Deck:
    slides: list[Slide] = field(default_factory=list)
    title: str = "Presentation"
    author: str = ""
    theme: str = "default"        # beamer theme name (\usetheme)
    color_theme: str = ""         # beamer colour theme (\usecolortheme)
    aspect: str = "169"           # "169" | "43" | "1610" | "32"
    template: str = "Blank"       # name of the template this deck started from
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
        )
    if t == "SlidePicture":
        return SlidePicture(
            x=float(d.get("x", 0.1)), y=float(d.get("y", 0.1)),
            w=float(d.get("w", 0.3)), h=float(d.get("h", 0.3)),
            path=str(d.get("path", "")),
            keep_aspect=bool(d.get("keep_aspect", False)),
        )
    raise ValueError(f"Unknown slide object type: {t!r}")


def _build_slide(d: dict) -> Slide:
    return Slide(
        objects=[_build_object(o) for o in d.get("objects", [])],
        title=str(d.get("title", "")),
        bg=str(d.get("bg", "")),
    )


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
