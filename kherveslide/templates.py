"""Beamer slide templates — the "dedicated template module".

A *template* is a named, reusable starting point for a deck: a beamer
theme, an aspect ratio, and a set of starter slides with their objects
already laid out. Built-in templates are defined here in code; the user
can save the current deck as a new template, rename it, or delete it,
and those user templates persist to a JSON file under the user's home so
they survive restarts.

Kept free of Qt so it can be unit-tested and reused headless.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .model import Deck, Slide, SlideText, SlidePicture, _build_slide


# ---------------- Built-in templates ----------------

def _title(text, *, x=0.1, y=0.32, w=0.8, h=0.18, pt=40, align="center",
           bold=True, color="#1A1A1A"):
    return SlideText(x=x, y=y, w=w, h=h, text=text, font_pt=pt,
                     align=align, bold=bold, color=color)


def _body(text, *, x=0.08, y=0.28, w=0.84, h=0.5, pt=22, align="left"):
    return SlideText(x=x, y=y, w=w, h=h, text=text, font_pt=pt, align=align)


def _blank() -> Deck:
    return Deck(slides=[Slide()], theme="default", aspect="169",
                template="Blank")


def _title_slide() -> Deck:
    return Deck(
        title="Presentation title", author="Author",
        theme="Madrid", aspect="169", template="Title slide",
        slides=[Slide(objects=[
            _title("Presentation Title", y=0.36, pt=44),
            SlideText(x=0.1, y=0.56, w=0.8, h=0.1, text="Subtitle",
                      font_pt=24, align="center", color="#555555"),
            SlideText(x=0.1, y=0.78, w=0.8, h=0.08, text="Author \\textbar{} Date",
                      font_pt=18, align="center", color="#777777"),
        ])])


def _title_content() -> Deck:
    return Deck(
        theme="Madrid", aspect="169", template="Title + content",
        slides=[
            Slide(objects=[_title("Presentation Title", y=0.36, pt=44),
                           SlideText(x=0.1, y=0.56, w=0.8, h=0.1,
                                     text="Subtitle", font_pt=24,
                                     align="center", color="#555555")]),
            Slide(title="Section heading", objects=[
                _title("Heading", x=0.06, y=0.06, w=0.88, h=0.12, pt=32,
                       align="left"),
                _body("\\begin{itemize}\n  \\item First point\n"
                      "  \\item Second point\n\\end{itemize}",
                      y=0.26),
            ]),
        ])


def _two_columns() -> Deck:
    return Deck(
        theme="default", aspect="169", template="Two columns",
        slides=[Slide(objects=[
            _title("Two columns", x=0.06, y=0.06, w=0.88, h=0.12, pt=32,
                   align="left"),
            _body("Left column text.", x=0.06, y=0.26, w=0.42, h=0.6),
            _body("Right column text.", x=0.52, y=0.26, w=0.42, h=0.6),
        ])])


def _picture_text() -> Deck:
    return Deck(
        theme="default", aspect="169", template="Picture + text",
        slides=[Slide(objects=[
            _title("Picture and text", x=0.06, y=0.06, w=0.88, h=0.12,
                   pt=32, align="left"),
            SlidePicture(x=0.06, y=0.26, w=0.42, h=0.6, path=""),
            _body("Describe the picture here.", x=0.52, y=0.26, w=0.42,
                  h=0.6),
        ])])


def _section_divider() -> Deck:
    return Deck(
        theme="Madrid", aspect="169", template="Section divider",
        slides=[Slide(bg="#1F3A5F", objects=[
            _title("Section", y=0.42, pt=48, color="#FFFFFF"),
        ])])


# name -> zero-arg factory returning a fresh Deck
_BUILTINS: dict[str, callable] = {
    "Blank": _blank,
    "Title slide": _title_slide,
    "Title + content": _title_content,
    "Two columns": _two_columns,
    "Picture + text": _picture_text,
    "Section divider": _section_divider,
}


def builtin_names() -> list[str]:
    return list(_BUILTINS.keys())


def instantiate_builtin(name: str) -> Deck:
    factory = _BUILTINS.get(name, _blank)
    return factory()


# ---------------- User template store ----------------

def _default_store_path() -> Path:
    return Path.home() / ".khervetex" / "slide_templates.json"


class TemplateStore:
    """Named user templates persisted to a single JSON file.

    Each template stores the deck-level theme/aspect plus its slides, so
    applying it reproduces the original layout. Names are unique;
    built-in names are reserved and cannot be overwritten or renamed.
    """

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else _default_store_path()
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8")

    def names(self) -> list[str]:
        return sorted(self._data.keys())

    def all_names(self) -> list[str]:
        """Built-ins first, then user templates."""
        return builtin_names() + self.names()

    def save_deck_as(self, name: str, deck: Deck) -> None:
        """Save *deck*'s theme + slides as a reusable template called
        *name*. Refuses to shadow a built-in name."""
        name = name.strip()
        if not name:
            raise ValueError("Template name cannot be empty")
        if name in _BUILTINS:
            raise ValueError(f"{name!r} is a built-in template name")
        self._data[name] = {
            "theme": deck.theme,
            "color_theme": deck.color_theme,
            "aspect": deck.aspect,
            "slides": [asdict(s) for s in deck.slides],
        }
        self._save()

    def rename(self, old: str, new: str) -> None:
        new = new.strip()
        if old not in self._data:
            raise KeyError(f"No user template named {old!r}")
        if new in _BUILTINS:
            raise ValueError(f"{new!r} is a built-in template name")
        if not new:
            raise ValueError("Template name cannot be empty")
        if new in self._data and new != old:
            raise ValueError(f"A template named {new!r} already exists")
        self._data[new] = self._data.pop(old)
        self._save()

    def delete(self, name: str) -> None:
        if name in self._data:
            del self._data[name]
            self._save()

    def instantiate(self, name: str) -> Deck:
        """Build a fresh deck from any template — built-in or user."""
        if name in _BUILTINS:
            return instantiate_builtin(name)
        d = self._data.get(name)
        if d is None:
            return instantiate_builtin("Blank")
        return Deck(
            theme=d.get("theme", "default"),
            color_theme=d.get("color_theme", ""),
            aspect=d.get("aspect", "169"),
            template=name,
            slides=[_build_slide(s) for s in d.get("slides", [])] or [Slide()],
        )
