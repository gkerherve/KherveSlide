# KherveSlide

A dedicated **WYSIWYG slide designer** that produces beamer LaTeX.

Drag, resize and stack text and picture boxes exactly where you want
them on the slide; the left side is the what-you-see-is-what-you-get
canvas (with a visual slide navigator you can drag to reorder), and the
right side shows the generated LaTeX and the compiler console, kept live
as you edit. Compile to PDF with [tectonic](https://tectonic-typesetting.github.io/).

Sister project to [KherveTeX](https://github.com/gkerherve/kherveDOC) —
it shares KherveTeX's look (themes, runtime-drawn icons) and its
tectonic/preview engine, but is its own application.

## Run

Easiest: right-click **`KherveSlide.py`** at the project root and **Run**
(or double-click it). It's a thin launcher around the package.

Or from a terminal:

```sh
pip install -r requirements.txt
python -m kherveslide      # equivalent to running KherveSlide.py
```

A working `tectonic` binary on `PATH` (or installed via KherveTeX) is
needed to compile slides to PDF; the designer itself runs without it.

## Layout

- **Left — WYSIWYG:** slide navigator (drag thumbnails to reorder) + the
  live slide canvas. Move boxes by dragging, resize from any of eight
  handles, raise/lower in the z-stack. **Double-click an object to edit
  it in place** — type into a text box, double-click a table cell to
  edit it, double-click a picture to swap it. No side panel; a compact
  Format toolbar handles font, bold/italic, alignment and colours.
- **Insert:** text boxes, pictures, **tables** (in-place cell editing,
  add/remove rows & columns from the Table menu), **equations** (enter
  LaTeX, dropped in as a centred math box) and freehand **drawings**
  (sketch in a dialog, inserted as an image).
- **Right — LaTeX + Console:** the generated beamer source (live) and
  the compiler output, plus a PDF preview tab.

## Files

Decks save as `*.kslide.json`. Export the LaTeX with **Export .tex**.

## Layout of the code

| Module | Role |
|---|---|
| `model.py` | Deck / Slide / SlideText / SlidePicture (source of truth) |
| `serializer.py` | deck → beamer LaTeX via `textpos` absolute positioning |
| `templates.py` | built-in + saveable/renameable user templates |
| `canvas.py` | graphics scene, draggable/resizable boxes, thumbnails |
| `navigator.py` | left visual slide strip with drag-to-reorder |
| `window.py` | main window (toolbar, navigator, canvas, LaTeX/console) |
| `icons.py`, `themes.py`, `compiler.py`, `style_manager.py`, `preview.py`, `latex_view.py` | vendored from KherveTeX |
