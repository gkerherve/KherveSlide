"""The tools KherveSlide exposes to Claude (or any MCP client).

`TOOLS` is the schema table the stdio server advertises; `ToolExecutor`
runs one tool against a live `SlideWindow` on the GUI thread (the bridge
calls it from Qt's event loop). Every tool returns a plain dict; a dict
with an "error" key is reported to the client as a failed call.

Slides are addressed by 0-based index and the objects on a slide by their
0-based stacking index (0 = bottom). Geometry is the deck model's own:
x, y, w, h as fractions (0..1) of the slide, (x, y) the top-left corner.
Every edit goes through the window's normal change path, so it shows
live, lands in the LaTeX and is one Ctrl+Z (see mcp_bridge).
"""
from __future__ import annotations

import base64
import shutil
import threading
import time
from dataclasses import fields
from pathlib import Path

_INT = {"type": "integer"}
_NUM = {"type": "number"}
_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_GEOM = {"x": _NUM, "y": _NUM, "w": _NUM, "h": _NUM}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props,
            "required": required or [], "additionalProperties": False}


_KIT_PROPS = {
    "name": _STR,
    "primary": {"type": "string", "description": "#RRGGBB main colour: "
                "title bar, footer bar, bullets"},
    "accent": {"type": "string", "description": "#RRGGBB for lines; "
               "\"\" = same as primary"},
    "text": _STR, "background": _STR,
    "title_text": {"type": "string", "description": "#RRGGBB text on the "
                   "title / footer bar"},
    "title_style": {"type": "string", "enum": ["bar", "plain", "underline"]},
    "footer_style": {"type": "string", "enum": ["bar", "line", "none"]},
    "logo": {"type": "string", "description": "image path (png/jpg/pdf); "
             "\"\" removes the logo"},
    "logo_corner": {"type": "string", "enum": ["tr", "tl", "br", "bl"]},
    "logo_size": {"type": "number", "description": "logo height as a "
                  "fraction of the slide height (0.05-0.3)"},
    "font": {"type": "string", "description": "typeface key from "
             "list_themes, \"\" = Latin Modern"},
    "bullets": {"type": "string",
                "enum": ["", "ball", "circle", "square", "triangle"]},
}

TOOLS: list[dict] = [
    # ── reading ──────────────────────────────────────────────────
    {"name": "get_presentation_info",
     "description": "Title, author, file, aspect ratio, theme, slide "
                    "count, header / footer slots, slide numbering, "
                    "whether there are unsaved changes. Call this first.",
     "input_schema": _obj({})},
    {"name": "list_slides",
     "description": "Every slide with its index, frame title and a short "
                    "summary of its objects.",
     "input_schema": _obj({})},
    {"name": "get_slide",
     "description": "All objects on one slide (stacking order, bottom "
                    "first) with every property: kind, x/y/w/h fractions, "
                    "text (LaTeX), font size, colours…",
     "input_schema": _obj({"slide": _INT}, ["slide"])},
    {"name": "get_latex",
     "description": "The complete beamer .tex the presentation compiles "
                    "from.",
     "input_schema": _obj({"max_chars": _INT})},
    {"name": "render_slide",
     "description": "Compile and return one slide as a PNG image, exactly "
                    "as the PDF shows it. Use it to check your work.",
     "input_schema": _obj({"slide": _INT, "width": _INT}, ["slide"])},
    # ── slides ───────────────────────────────────────────────────
    {"name": "add_slide",
     "description": "Insert a slide after `after` (default: at the end), "
                    "optionally from a layout (see list_layouts) and with "
                    "a frame title. Returns its index.",
     "input_schema": _obj({"after": _INT, "layout": _STR, "title": _STR})},
    {"name": "list_layouts",
     "description": "Slide layout names for add_slide / set_slide.",
     "input_schema": _obj({})},
    {"name": "set_slide",
     "description": "Change a slide's frame title, background colour "
                    "(#RRGGBB, \"\" = theme) or replace its content with a "
                    "layout.",
     "input_schema": _obj({"slide": _INT, "title": _STR, "background": _STR,
                           "layout": _STR}, ["slide"])},
    {"name": "delete_slide", "description": "Remove a slide.",
     "input_schema": _obj({"slide": _INT}, ["slide"])},
    {"name": "duplicate_slide", "description": "Copy a slide just after it.",
     "input_schema": _obj({"slide": _INT}, ["slide"])},
    {"name": "move_slide", "description": "Move a slide to a new index.",
     "input_schema": _obj({"slide": _INT, "to": _INT}, ["slide", "to"])},
    # ── objects ──────────────────────────────────────────────────
    {"name": "add_text",
     "description": "Add a text box. `text` is LaTeX: plain text, "
                    "$maths$, \\textbf{}, and bullet lists as "
                    "\\begin{itemize} / \\item lines (one per line). "
                    "block: \"\" | block | alertblock | exampleblock | "
                    "theorem… for a titled beamer block. Free placement "
                    "at x, y unless locked=true (beamer flows it).",
     "input_schema": _obj({"slide": _INT, "text": _STR, **_GEOM,
                           "font_pt": _INT, "bold": _BOOL, "italic": _BOOL,
                           "color": _STR, "align": {"type": "string",
                           "enum": ["left", "center", "right"]},
                           "fill": _STR, "border_color": _STR,
                           "block": _STR, "block_title": _STR,
                           "locked": _BOOL}, ["slide", "text"])},
    {"name": "add_equation",
     "description": "Add a displayed equation; `latex` is the maths alone "
                    "(no $ or \\[ \\]).",
     "input_schema": _obj({"slide": _INT, "latex": _STR, **_GEOM,
                           "font_pt": _INT}, ["slide", "latex"])},
    {"name": "add_picture",
     "description": "Add an image (png / jpg / pdf) from a file path.",
     "input_schema": _obj({"slide": _INT, "path": _STR, **_GEOM},
                          ["slide", "path"])},
    {"name": "add_shape",
     "description": "Add a vector shape: rect, rounded_rect, ellipse, "
                    "circle, triangle, diamond, hexagon, star5, "
                    "arrow_right, chevron, speech… with fill / border.",
     "input_schema": _obj({"slide": _INT, "shape": _STR, **_GEOM,
                           "fill": _STR, "border_color": _STR,
                           "border_width": _NUM, "opacity": _NUM},
                          ["slide", "shape"])},
    {"name": "add_line",
     "description": "Add a line or arrow from (x1, y1) to (x2, y2), "
                    "fractions of the slide.",
     "input_schema": _obj({"slide": _INT, "x1": _NUM, "y1": _NUM,
                           "x2": _NUM, "y2": _NUM, "color": _STR,
                           "width_pt": _NUM, "arrow_end": _BOOL,
                           "arrow_start": _BOOL,
                           "style": {"type": "string",
                                     "enum": ["solid", "dashed", "dotted"]}},
                          ["slide", "x1", "y1", "x2", "y2"])},
    {"name": "add_table",
     "description": "Add a table; rows is a list of rows of cell strings "
                    "(LaTeX allowed); the first row is the header.",
     "input_schema": _obj({"slide": _INT, "rows": {
         "type": "array", "items": {"type": "array", "items": _STR}},
         **_GEOM, "font_pt": _INT, "caption": _STR}, ["slide", "rows"])},
    {"name": "update_object",
     "description": "Change any properties of an object (names as "
                    "get_slide shows them), e.g. {\"text\": …, \"x\": 0.1, "
                    "\"font_pt\": 24, \"color\": \"#003E74\"}.",
     "input_schema": _obj({"slide": _INT, "index": _INT,
                           "changes": {"type": "object"}},
                          ["slide", "index", "changes"])},
    {"name": "delete_object", "description": "Remove an object.",
     "input_schema": _obj({"slide": _INT, "index": _INT},
                          ["slide", "index"])},
    {"name": "arrange_object",
     "description": "Restack an object: front, back, raise or lower.",
     "input_schema": _obj({"slide": _INT, "index": _INT, "how": {
         "type": "string", "enum": ["front", "back", "raise", "lower"]}},
         ["slide", "index", "how"])},
    # ── presentation ─────────────────────────────────────────────
    {"name": "set_presentation",
     "description": "Title, author, aspect (169, 1610, 43, 32, 54, 141), "
                    "slide numbers (none | number | of_total), theme "
                    "decorations, navigation symbols, and the header / "
                    "footer slots (LaTeX, e.g. \\insertframenumber, "
                    "\\today, \\insertauthor).",
     "input_schema": _obj({"title": _STR, "author": _STR, "aspect": _STR,
                           "page_number": {"type": "string", "enum": [
                               "none", "number", "of_total"]},
                           "decorations": _BOOL, "nav_symbols": _BOOL,
                           "header": _STR, "foot_left": _STR,
                           "foot_center": _STR, "foot_right": _STR})},
    # ── themes ───────────────────────────────────────────────────
    {"name": "list_themes",
     "description": "Built-in beamer themes and colour themes, the "
                    "wizard presets, the user's saved themes, typefaces "
                    "and the theme-kit options.",
     "input_schema": _obj({})},
    {"name": "get_theme",
     "description": "The current theme: beamer theme / colour theme, or "
                    "the custom theme as a theme kit (colours, title and "
                    "footer style, logo, typeface, bullets).",
     "input_schema": _obj({})},
    {"name": "set_beamer_theme",
     "description": "Use a built-in (or installed) beamer theme and "
                    "optional colour theme; switches a custom theme off.",
     "input_schema": _obj({"theme": _STR, "color_theme": _STR},
                          ["theme"])},
    {"name": "apply_theme_kit",
     "description": "Build and apply a custom theme the easy way — the "
                    "same model as the Theme wizard. Fields not given keep "
                    "their current value (or come from `preset`). Use it "
                    "to recreate a university template: its main colour, "
                    "accent, title bar or not, footer, logo corner.",
     "input_schema": _obj({**_KIT_PROPS, "preset": _STR,
                           "save_to_library": _BOOL})},
    {"name": "apply_saved_theme",
     "description": "Apply one of the user's saved themes (My themes).",
     "input_schema": _obj({"name": _STR}, ["name"])},
    {"name": "import_theme",
     "description": "Import a template file and apply it: a PowerPoint "
                    "template (.potx / .pptx — colours, fonts, logo), a "
                    "beamer theme (.sty or Overleaf .zip — used as is) or "
                    "a picture / PDF of a slide (colours picked off it).",
     "input_schema": _obj({"path": _STR, "apply": _BOOL}, ["path"])},
    {"name": "export_theme_sty",
     "description": "Write the current custom theme as a standard beamer "
                    "theme beamertheme<Name>.sty (plus its logo) into a "
                    "folder, usable from any LaTeX project.",
     "input_schema": _obj({"folder": _STR, "name": _STR}, ["folder"])},
    # ── build & files ────────────────────────────────────────────
    {"name": "compile",
     "description": "Compile to PDF now; returns success and any LaTeX "
                    "errors. The PDF panel updates.",
     "input_schema": _obj({})},
    {"name": "save_presentation",
     "description": "Save (to its file, or to `path`, a .kslide file).",
     "input_schema": _obj({"path": _STR})},
    {"name": "open_presentation",
     "description": "Open a .kslide file. Refuses to drop unsaved work "
                    "unless discard_unsaved_changes is true.",
     "input_schema": _obj({"path": _STR, "discard_unsaved_changes": _BOOL},
                          ["path"])},
    {"name": "new_presentation",
     "description": "Start a new presentation from a template (see "
                    "list_themes → templates). Refuses to drop unsaved "
                    "work unless discard_unsaved_changes is true.",
     "input_schema": _obj({"template": _STR,
                           "discard_unsaved_changes": _BOOL})},
    {"name": "export_pdf", "description": "Compile and save the PDF.",
     "input_schema": _obj({"path": _STR}, ["path"])},
    {"name": "undo", "description": "Undo the last change.",
     "input_schema": _obj({})},
]

READ_ONLY_TOOLS = frozenset({
    "get_presentation_info", "list_slides", "get_slide", "get_latex",
    "render_slide", "list_layouts", "list_themes", "get_theme",
})
# Tools that don't change the presentation (no undo snapshot needed).
NO_UNDO_BLOCK_TOOLS = READ_ONLY_TOOLS | {
    "compile", "save_presentation", "export_pdf", "export_theme_sty",
    "undo",
}
# Tools that read or write a path the client chooses.
PATH_TOOLS = frozenset({
    "open_presentation", "export_pdf", "add_picture", "import_theme",
    "export_theme_sty",
})

_KINDS = {"SlideText": "text", "SlidePicture": "picture",
          "SlideTable": "table", "SlideLine": "line", "SlideShape": "shape",
          "SlideVideo": "video"}


class ToolError(Exception):
    pass


class ToolExecutor:
    """Runs tools against a live SlideWindow (GUI thread)."""

    def __init__(self, window):
        self._w = window

    # ---------------------------------------------------------- plumbing
    def execute(self, name: str, tool_input: dict) -> dict:
        fn = getattr(self, f"_t_{name}", None)
        if fn is None:
            return {"error": f"Unknown tool {name!r}"}
        try:
            return fn(**(tool_input or {}))
        except ToolError as exc:
            return {"error": str(exc)}
        except TypeError as exc:
            return {"error": f"Bad arguments for {name}: {exc}"}

    @property
    def deck(self):
        return self._w.deck

    def _slide(self, i):
        if not isinstance(i, int) or not 0 <= i < len(self.deck.slides):
            raise ToolError(f"No slide {i}; there are "
                            f"{len(self.deck.slides)} (0-based).")
        return self.deck.slides[i]

    def _object(self, s, i):
        objs = self._slide(s).objects
        if not isinstance(i, int) or not 0 <= i < len(objs):
            raise ToolError(f"No object {i} on slide {s}; it has "
                            f"{len(objs)}.")
        return objs[i]

    def _show(self, slide_index: int | None = None) -> None:
        """Push a change through the window's normal change path (live
        canvas, thumbnails, LaTeX, undo snapshot)."""
        if slide_index is not None:
            self._w.current = max(0, min(slide_index,
                                         len(self.deck.slides) - 1))
        self._w.current = min(self._w.current, len(self.deck.slides) - 1)
        self._w._reload_all()

    @staticmethod
    def _describe(obj, index: int) -> dict:
        from .model import object_to_dict
        d = object_to_dict(obj)
        d.pop("type", None)
        return {"index": index, "kind": _KINDS.get(type(obj).__name__,
                                                   type(obj).__name__), **d}

    def _place(self, obj, geom: dict) -> None:
        for k in ("x", "y", "w", "h"):
            v = geom.get(k)
            if v is not None:
                setattr(obj, k, float(v))

    def _add(self, slide: int, obj) -> dict:
        s = self._slide(slide)
        s.objects.append(obj)
        self._show(slide)
        return {"ok": True, "slide": slide, "index": len(s.objects) - 1}

    def _compile_sync(self, timeout: float = 300.0):
        """Compile the presentation on a worker thread while keeping the
        UI responsive; returns the CompileResult."""
        from PySide6.QtCore import QEventLoop
        from PySide6.QtWidgets import QApplication
        from .compiler import compile_tex, tectonic_available
        import tempfile
        if not tectonic_available():
            raise ToolError("LaTeX (tectonic) is not available here.")
        tex = self._w.latex_view.source()
        src = self._w.path.parent if self._w.path else None
        box: dict = {}

        def run():
            box["r"] = compile_tex(
                tex, Path(tempfile.gettempdir()) / "kherveslide_mcp",
                "slides", source_dir=src)
        t = threading.Thread(target=run, daemon=True)
        t.start()
        end = time.time() + timeout
        while t.is_alive() and time.time() < end:
            QApplication.processEvents(QEventLoop.AllEvents, 50)
            t.join(0.02)
        if "r" not in box:
            raise ToolError("Compile timed out.")
        return box["r"]

    # ----------------------------------------------------------- reading
    def _t_get_presentation_info(self):
        d = self.deck
        spec = d.theme_spec
        return {
            "title": d.title, "author": d.author,
            "file": str(self._w.path) if self._w.path else None,
            "aspect": d.aspect, "slides": len(d.slides),
            "current_slide": self._w.current,
            "beamer_theme": d.theme, "color_theme": d.color_theme,
            "custom_theme": bool(spec.enabled),
            "decorations": not d.plain_frames,
            "page_number": d.page_number, "nav_symbols": d.nav_symbols,
            "header": d.header, "foot_left": d.foot_left,
            "foot_center": d.foot_center, "foot_right": d.foot_right,
            "unsaved_changes": self._w.has_unsaved_changes(),
            "layout_mode": self._w._layout_mode,
        }

    def _t_list_slides(self):
        out = []
        for i, s in enumerate(self.deck.slides):
            parts = []
            for o in s.objects:
                kind = _KINDS.get(type(o).__name__, "object")
                text = getattr(o, "text", "") or ""
                preview = " ".join(text.split())[:50]
                parts.append(f"{kind}: {preview}" if preview else kind)
            out.append({"index": i, "title": s.title,
                        "background": s.bg, "objects": parts})
        return {"slides": out}

    def _t_get_slide(self, slide: int):
        s = self._slide(slide)
        return {"slide": slide, "title": s.title, "background": s.bg,
                "objects": [self._describe(o, i)
                            for i, o in enumerate(s.objects)]}

    def _t_get_latex(self, max_chars: int = 60000):
        src = self._w.latex_view.source()
        return {"latex": src[:max(1000, int(max_chars))],
                "truncated": len(src) > max_chars}

    def _t_render_slide(self, slide: int, width: int = 1100):
        self._slide(slide)
        r = self._compile_sync()
        if not (r.ok and r.pdf_path):
            return {"error": "Compile failed: "
                             + _errors(r.log)[:1500]}
        import pymupdf
        with pymupdf.open(r.pdf_path) as doc:
            if slide >= doc.page_count:
                raise ToolError("That slide has no page in the PDF.")
            page = doc[slide]
            z = max(200, min(2000, int(width))) / page.rect.width
            png = page.get_pixmap(matrix=pymupdf.Matrix(z, z),
                                  alpha=False).tobytes("png")
        return {"slide": slide,
                "image_png_base64": base64.b64encode(png).decode("ascii")}

    def _t_list_layouts(self):
        from . import templates
        return {"layouts": templates.slide_layout_names()}

    # ------------------------------------------------------------ slides
    def _t_add_slide(self, after: int | None = None, layout: str = "",
                     title: str = ""):
        from . import templates
        from .model import Slide
        if layout:
            if layout not in templates.slide_layout_names():
                raise ToolError(f"Unknown layout {layout!r}; see "
                                "list_layouts.")
            new = templates.instantiate_slide_layout(layout)
        else:
            new = Slide()
        if title:
            new.title = title
        at = len(self.deck.slides) if after is None else \
            max(0, min(len(self.deck.slides), int(after) + 1))
        self.deck.slides.insert(at, new)
        self._show(at)
        return {"ok": True, "index": at}

    def _t_set_slide(self, slide: int, title: str | None = None,
                     background: str | None = None, layout: str = ""):
        from . import templates
        s = self._slide(slide)
        if layout:
            if layout not in templates.slide_layout_names():
                raise ToolError(f"Unknown layout {layout!r}.")
            s.objects = templates.instantiate_slide_layout(layout).objects
        if title is not None:
            s.title = title
        if background is not None:
            s.bg = background
        self._show(slide)
        return {"ok": True}

    def _t_delete_slide(self, slide: int):
        self._slide(slide)
        if len(self.deck.slides) == 1:
            raise ToolError("A presentation needs at least one slide.")
        del self.deck.slides[slide]
        self._show(min(slide, len(self.deck.slides) - 1))
        return {"ok": True, "slides": len(self.deck.slides)}

    def _t_duplicate_slide(self, slide: int):
        from .model import deck_from_json, deck_to_json, Deck
        s = self._slide(slide)
        copy = deck_from_json(deck_to_json(Deck(slides=[s]))).slides[0]
        self.deck.slides.insert(slide + 1, copy)
        self._show(slide + 1)
        return {"ok": True, "index": slide + 1}

    def _t_move_slide(self, slide: int, to: int):
        s = self._slide(slide)
        to = max(0, min(len(self.deck.slides) - 1, int(to)))
        self.deck.slides.pop(slide)
        self.deck.slides.insert(to, s)
        self._show(to)
        return {"ok": True, "index": to}

    # ----------------------------------------------------------- objects
    def _t_add_text(self, slide: int, text: str, x=None, y=None, w=None,
                    h=None, font_pt: int = 20, bold: bool = False,
                    italic: bool = False, color: str = "#000000",
                    align: str = "left", fill: str = "",
                    border_color: str = "", block: str = "",
                    block_title: str = "", locked: bool = False):
        from .model import SlideText
        obj = SlideText(text=text, font_pt=int(font_pt), bold=bold,
                        italic=italic, color=color, align=align, fill=fill,
                        border_color=border_color, block=block,
                        block_title=block_title, locked=locked,
                        x=0.08, y=0.25, w=0.84, h=0.2)
        self._place(obj, {"x": x, "y": y, "w": w, "h": h})
        return self._add(slide, obj)

    def _t_add_equation(self, slide: int, latex: str, x=None, y=None,
                        w=None, h=None, font_pt: int = 24):
        from .model import SlideText
        obj = SlideText(text=f"\\[{latex.strip()}\\]", font_pt=int(font_pt),
                        align="center", locked=False,
                        x=0.2, y=0.4, w=0.6, h=0.15)
        self._place(obj, {"x": x, "y": y, "w": w, "h": h})
        return self._add(slide, obj)

    def _t_add_picture(self, slide: int, path: str, x=None, y=None,
                       w=None, h=None):
        from .model import SlidePicture
        p = Path(path).expanduser()
        if not p.exists():
            raise ToolError(f"No such file: {p}")
        obj = SlidePicture(path=str(p), locked=False,
                           x=0.3, y=0.3, w=0.4, h=0.4)
        self._place(obj, {"x": x, "y": y, "w": w, "h": h})
        return self._add(slide, obj)

    def _t_add_shape(self, slide: int, shape: str, x=None, y=None, w=None,
                     h=None, fill: str = "", border_color: str = "#000000",
                     border_width: float = 1.5, opacity: float = 1.0):
        from . import shapes as _shapes
        from .model import SlideShape
        if shape not in _shapes.ALL:
            raise ToolError(f"Unknown shape {shape!r}; one of "
                            f"{_shapes.ALL}")
        obj = SlideShape(shape=shape, fill=fill, border_color=border_color,
                         border_width=float(border_width),
                         opacity=float(opacity))
        self._place(obj, {"x": x, "y": y, "w": w, "h": h})
        return self._add(slide, obj)

    def _t_add_line(self, slide: int, x1: float, y1: float, x2: float,
                    y2: float, color: str = "#000000", width_pt: float = 1.5,
                    arrow_end: bool = False, arrow_start: bool = False,
                    style: str = "solid"):
        from .model import SlideLine
        # A line runs along its box's diagonal from (x, y) to (x+w, y+h).
        obj = SlideLine(x=float(x1), y=float(y1), w=float(x2) - float(x1),
                        h=float(y2) - float(y1), color=color,
                        width_pt=float(width_pt), arrow_end=arrow_end,
                        arrow_start=arrow_start, style=style)
        return self._add(slide, obj)

    def _t_add_table(self, slide: int, rows: list, x=None, y=None, w=None,
                     h=None, font_pt: int = 16, caption: str = ""):
        from .model import SlideTable
        if not rows or not all(isinstance(r, list) for r in rows):
            raise ToolError("rows must be a list of lists of strings.")
        width = max(len(r) for r in rows)
        grid = [[str(c) for c in r] + [""] * (width - len(r)) for r in rows]
        obj = SlideTable(rows=grid, font_pt=int(font_pt), caption=caption,
                         locked=False, x=0.1, y=0.3, w=0.8,
                         h=min(0.6, 0.08 * len(grid)))
        self._place(obj, {"x": x, "y": y, "w": w, "h": h})
        return self._add(slide, obj)

    def _t_update_object(self, slide: int, index: int, changes: dict):
        obj = self._object(slide, index)
        names = {f.name: f for f in fields(obj)}
        bad = [k for k in changes if k not in names or k == "type"]
        if bad:
            raise ToolError(f"Unknown properties {bad}; this "
                            f"{_KINDS.get(type(obj).__name__)} has "
                            f"{sorted(n for n in names if n != 'type')}")
        for k, v in changes.items():
            cur = getattr(obj, k)
            try:
                if isinstance(cur, bool):
                    v = bool(v)
                elif isinstance(cur, int) and not isinstance(cur, bool):
                    v = int(v)
                elif isinstance(cur, float):
                    v = float(v)
                elif isinstance(cur, str):
                    v = str(v)
            except (TypeError, ValueError):
                raise ToolError(f"{k} expects {type(cur).__name__}")
            setattr(obj, k, v)
        self._show(slide)
        return {"ok": True, "object": self._describe(obj, index)}

    def _t_delete_object(self, slide: int, index: int):
        self._object(slide, index)
        del self.deck.slides[slide].objects[index]
        self._show(slide)
        return {"ok": True}

    def _t_arrange_object(self, slide: int, index: int, how: str):
        from .model import lower_object, raise_object, to_back, to_front
        self._object(slide, index)
        fn = {"front": to_front, "back": to_back, "raise": raise_object,
              "lower": lower_object}.get(how)
        if fn is None:
            raise ToolError("how must be front, back, raise or lower.")
        new = fn(self.deck.slides[slide], index)
        self._show(slide)
        return {"ok": True, "index": new}

    # ------------------------------------------------------ presentation
    def _t_set_presentation(self, title=None, author=None, aspect=None,
                            page_number=None, decorations=None,
                            nav_symbols=None, header=None, foot_left=None,
                            foot_center=None, foot_right=None):
        d = self.deck
        if aspect is not None and aspect not in (
                "169", "1610", "43", "32", "54", "141"):
            raise ToolError("aspect must be 169, 1610, 43, 32, 54 or 141.")
        for attr, val in (("title", title), ("author", author),
                          ("aspect", aspect), ("page_number", page_number),
                          ("nav_symbols", nav_symbols), ("header", header),
                          ("foot_left", foot_left),
                          ("foot_center", foot_center),
                          ("foot_right", foot_right)):
            if val is not None:
                setattr(d, attr, val)
        if decorations is not None:
            d.plain_frames = not decorations
        self._show()
        self._w._sync_top_fields()
        return {"ok": True}

    # ------------------------------------------------------------ themes
    def _t_list_themes(self):
        from . import custom_themes, templates
        from .serializer import (BEAMER_COLOR_THEMES, BEAMER_THEMES,
                                 FONT_FAMILIES)
        from .theme_kit import (BULLET_STYLES, FOOTER_STYLES, LOGO_CORNERS,
                                TITLE_STYLES, presets)
        return {
            "beamer_themes": list(BEAMER_THEMES)
            + custom_themes.installed_sty_themes(),
            "color_themes": list(BEAMER_COLOR_THEMES),
            "presets": [k.to_dict() for k in presets()],
            "my_themes": sorted(custom_themes.load_themes()),
            "templates": self._w.store.all_names(),
            "typefaces": {"": "Latin Modern Sans (default)",
                          **{k: v[0] for k, v in FONT_FAMILIES.items()}},
            "title_styles": TITLE_STYLES, "footer_styles": FOOTER_STYLES,
            "logo_corners": LOGO_CORNERS, "bullets": BULLET_STYLES,
            "layouts": templates.slide_layout_names(),
        }

    def _t_get_theme(self):
        from .theme_kit import kit_from_theme
        d = self.deck
        out = {"beamer_theme": d.theme, "color_theme": d.color_theme,
               "custom_theme": bool(d.theme_spec.enabled),
               "decorations": not d.plain_frames}
        if d.theme_spec.enabled:
            out["kit"] = kit_from_theme(d.theme_spec).to_dict()
        return out

    def _apply_kit(self, kit, save: bool) -> dict:
        from . import custom_themes
        from .theme_import import assets_dir
        from .theme_wizard import keep_logo
        kit = keep_logo(kit, assets_dir())
        t = kit.to_theme(self.deck.master)
        d = self.deck
        d.theme, d.color_theme = t["base_theme"], t["color_theme"]
        d.theme_spec = t["spec"]
        d.plain_frames = False
        if save:
            custom_themes.save_theme(kit.name, t["spec"], d.master,
                                     t["base_theme"], t["color_theme"],
                                     kit=kit.to_dict())
        self._show()
        self._w._sync_theme_menus()
        return {"ok": True, "kit": kit.to_dict()}

    def _t_set_beamer_theme(self, theme: str, color_theme: str = ""):
        d = self.deck
        d.theme, d.color_theme = theme, color_theme
        d.theme_spec.enabled = False
        d.plain_frames = False
        self._show()
        self._w._sync_theme_menus()
        return {"ok": True}

    def _t_apply_theme_kit(self, preset: str = "",
                           save_to_library: bool = False, **fields_in):
        from .theme_kit import ThemeKit, kit_from_theme, presets
        if preset:
            match = [k for k in presets() if k.name.lower() == preset.lower()]
            if not match:
                raise ToolError(f"No preset {preset!r}; see list_themes.")
            base = match[0]
        elif self.deck.theme_spec.enabled:
            base = kit_from_theme(self.deck.theme_spec)
        else:
            base = ThemeKit()
        kit = ThemeKit.from_dict({**base.to_dict(), **fields_in})
        if kit.logo and not Path(kit.logo).expanduser().exists():
            raise ToolError(f"Logo file not found: {kit.logo}")
        if kit.logo:
            kit.logo = str(Path(kit.logo).expanduser())
        return self._apply_kit(kit, save_to_library)

    def _t_apply_saved_theme(self, name: str):
        from . import custom_themes
        from .theme_kit import ThemeKit
        saved = custom_themes.load_themes().get(name)
        if saved is None:
            raise ToolError(f"No saved theme {name!r}.")
        if saved.get("kit"):
            return self._apply_kit(ThemeKit.from_dict(saved["kit"]), False)
        d = self.deck
        d.theme, d.color_theme = saved["base_theme"], saved["color_theme"]
        d.theme_spec, d.master = saved["spec"], saved["master"]
        self._show()
        self._w._sync_theme_menus()
        return {"ok": True}

    def _t_import_theme(self, path: str, apply: bool = True):
        from . import theme_import
        p = Path(path).expanduser()
        if not p.exists():
            raise ToolError(f"No such file: {p}")
        ext = p.suffix.lower()
        if ext in (".sty", ".zip"):
            name = theme_import.install_beamer_theme(p)
            if apply:
                self._t_set_beamer_theme(name)
            return {"ok": True, "beamer_theme": name, "applied": apply}
        if ext in (".potx", ".pptx", ".potm", ".pptm"):
            kit = theme_import.kit_from_pptx(p, theme_import.assets_dir())
        elif ext in (".png", ".jpg", ".jpeg", ".pdf"):
            kit = theme_import.kit_from_picture(p)
        else:
            raise ToolError("Use a .potx/.pptx, .sty/.zip, or an image / "
                            "PDF of a slide.")
        if apply:
            return {**self._apply_kit(kit, False), "applied": True}
        return {"ok": True, "kit": kit.to_dict(), "applied": False}

    def _t_export_theme_sty(self, folder: str, name: str = ""):
        from dataclasses import replace
        from .serializer import theme_to_sty
        d = self.deck
        if not d.theme_spec.enabled:
            raise ToolError("The presentation has no custom theme to "
                            "export (it uses the built-in "
                            f"'{d.theme}').")
        out = Path(folder).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        spec = d.theme_spec
        if spec.logo and Path(spec.logo).exists():
            logo = Path(spec.logo)
            shutil.copy2(logo, out / logo.name)
            spec = replace(spec, logo=logo.name)   # relative to the .sty
        safe = "".join(c for c in (name or "Custom") if c.isalnum()) \
            or "Custom"
        sty = out / f"beamertheme{safe}.sty"
        sty.write_text(theme_to_sty(spec, safe, d.theme, d.color_theme),
                       encoding="utf-8")
        return {"ok": True, "file": str(sty),
                "use_with": f"\\usetheme{{{safe}}}"}

    # ------------------------------------------------------ build & files
    def _t_compile(self):
        r = self._compile_sync()
        self._w._on_compiled(r)
        return {"ok": bool(r.ok), "errors": _errors(r.log)[:3000]}

    def _t_save_presentation(self, path: str = ""):
        if path:
            p = Path(path).expanduser()
            if p.suffix.lower() != ".kslide":
                p = p.with_suffix(".kslide")
            self._w.path = p
            self._w._update_title()
        if self._w.path is None:
            raise ToolError("The presentation has never been saved; pass "
                            "a path.")
        self._w._write_deck_to(self._w.path)
        return {"ok": True, "file": str(self._w.path)}

    def _guard_unsaved(self, discard: bool):
        if self._w.has_unsaved_changes() and not discard:
            raise ToolError("The open presentation has unsaved changes. "
                            "Save it first (save_presentation), or pass "
                            "discard_unsaved_changes=true if the user "
                            "agreed to lose them.")

    def _t_open_presentation(self, path: str,
                             discard_unsaved_changes: bool = False):
        self._guard_unsaved(discard_unsaved_changes)
        p = Path(path).expanduser()
        if not p.exists():
            raise ToolError(f"No such file: {p}")
        self._w.open_path(p)
        return {"ok": True, "slides": len(self.deck.slides)}

    def _t_new_presentation(self, template: str = "",
                            discard_unsaved_changes: bool = False):
        self._guard_unsaved(discard_unsaved_changes)
        if template:
            if template not in self._w.store.all_names():
                raise ToolError(f"No template {template!r}.")
            self._w._new_from_template(template)
        else:
            self._w._new_deck()
        return {"ok": True, "slides": len(self.deck.slides)}

    def _t_export_pdf(self, path: str):
        r = self._compile_sync()
        if not (r.ok and r.pdf_path):
            return {"error": "Compile failed: " + _errors(r.log)[:1500]}
        out = Path(path).expanduser()
        if out.suffix.lower() != ".pdf":
            out = out.with_suffix(".pdf")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(r.pdf_path, out)
        return {"ok": True, "file": str(out)}

    def _t_undo(self):
        self._w._undo()
        return {"ok": True}


def _errors(log: str) -> str:
    """The LaTeX error lines of a compile log, deduplicated."""
    seen, out = set(), []
    lines = (log or "").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("!") or "error:" in line.lower():
            chunk = " ".join(lines[i:i + 3]).strip()
            if chunk not in seen:
                seen.add(chunk)
                out.append(chunk)
    return "\n".join(out) or "(no errors reported)"
