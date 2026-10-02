"""What every toolbar icon does, and how to use it — as in KherveCAD.

Each entry is (title, what it does, [how-to steps], tip). `rich()` turns
one into the HTML tooltip the icon shows on hover — wide enough to read,
with the steps numbered — and `summary()` gives the one-line status-bar
text. Help ▸ User Guide covers the same tools at length; these are the
version you get without leaving the slide.

Copyright (C) 2026 Gwilherm Kerherve — GPL-3.0.
"""
from __future__ import annotations

#: tooltip width in pixels — QToolTip otherwise lays a long paragraph
#: out on a single line as wide as the screen
WIDTH = 380

_PICK_BOX = "Click a box on the slide first (it gets a selection frame)."

TIPS = {
    # ------------------------------------------------------- file & edit
    "new": (
        "New presentation",
        "Starts a fresh presentation with a title slide and a content "
        "slide, in the default theme. The one you have open is not lost: "
        "you are offered to save it first if it has changes.",
        ["Click New.",
         "Save it with Save (Ctrl+S) to choose its name and folder.",
         "Pick a look from the Theme button at the bottom, or View ▸ Slide "
         "theme."],
        "For a ready-made start, use Templates or File ▸ Example "
        "presentations instead."),
    "open": (
        "Open presentation",
        "Opens a KherveSlide presentation (.kslide) — or imports a "
        "PowerPoint file (.pptx), turning each of its slides into "
        "editable boxes.",
        ["Click Open and choose the file.",
         "It replaces the presentation on screen (you are asked to save "
         "that one first if it changed).",
         "Recent files are on the Welcome page (Help ▸ Welcome) too."],
        "You can also drop a .kslide or .pptx file anywhere on the "
        "window."),
    "save": (
        "Save",
        "Saves the presentation as a .kslide file — every slide, box, "
        "picture link, the theme and the master. The first time it asks "
        "where to save.",
        ["Click Save (or press Ctrl+S).",
         "The first time, choose a folder and a name.",
         "Pictures, drawings and flowcharts go in a figures folder beside "
         "it."],
        "File ▸ Save As… makes a copy under a new name."),
    "undo": (
        "Undo",
        "Takes back the last change to the presentation — typing, moving "
        "or resizing a box, adding or deleting slides, a theme change, "
        "hiding a slide… every action can be undone.",
        ["Click Undo (or press Ctrl+Z).",
         "Click again to go further back, one step at a time."],
        "Redo (Ctrl+Y) brings back what you undid."),
    "redo": (
        "Redo",
        "Brings back a change you just undid — one step for each Undo, "
        "in the same order.",
        ["After an Undo, click Redo (or press Ctrl+Y).",
         "Click again for each step to bring back."],
        "Making a new change after an Undo clears what could be redone."),
    "templates": (
        "Templates",
        "Your own templates: start a new presentation from one, or keep "
        "the current presentation (theme, master, layouts) as a template "
        "to reuse.",
        ["Click Templates.",
         "Choose “New from: …” to start from a template, or “Save current "
         "presentation as template…”.",
         "Rename and delete templates from the same list."],
        "Built-in layouts are on the + (Add slide) arrow; complete example "
        "presentations are in File ▸ Example presentations."),
    "export_pdf": (
        "Export PDF",
        "Compiles the whole presentation with LaTeX (beamer) and saves "
        "the PDF where you choose — the file to present, print or send.",
        ["Click Export PDF.",
         "Choose the folder and file name.",
         "Wait a few seconds while it compiles; the status bar says when "
         "it is done."],
        "Hidden slides are left out. If it fails, the Console tab shows "
        "the LaTeX log."),
    # ------------------------------------------------------------- zoom
    "zoom_out": (
        "Zoom out",
        "Makes the slide smaller on screen, to see it whole or the area "
        "around it. The slide itself does not change.",
        ["Click to zoom out one step.",
         "Or turn the mouse wheel over the slide."],
        "Fit brings the slide back to fill the window."),
    "fit": (
        "Fit slide to window",
        "Sizes the slide to fill the editing area exactly, and keeps it "
        "fitted when you resize the window.",
        ["Click Fit after zooming in or out."],
        "Zooming with the wheel or the buttons leaves fit mode."),
    "zoom_in": (
        "Zoom in",
        "Makes the slide bigger on screen, for precise placing of small "
        "boxes and text. The slide itself does not change.",
        ["Click to zoom in one step.",
         "Or turn the mouse wheel over the slide (it zooms around the "
         "pointer).",
         "Scroll to move around a zoomed slide."],
        "Fit brings the whole slide back."),
    # ------------------------------------------------------ box & format
    "box_type": (
        "Box type",
        "What the selected box is: plain text, a beamer block (Block, "
        "Alert block, Example block), a theorem-like box (Theorem, "
        "Definition, Lemma, Proof…), an equation, an image or a table.",
        [_PICK_BOX,
         "Choose its type in this list.",
         "Text keeps its words inside the new block; switching to Image "
         "or Table keeps the box's place and size but replaces what is "
         "inside."],
        "Blocks take their colours from the slide theme."),
    "font_family": (
        "Font",
        "The typeface of the selected text box: the theme's default, "
        "sans-serif, serif or monospace (typewriter).",
        [_PICK_BOX,
         "Pick the font in the list — the whole box changes."],
        "The theme's own typeface is set in View ▸ Slide theme."),
    "font_size": (
        "Font size",
        "The size of the text in the selected box, in points — as in "
        "the PDF.",
        [_PICK_BOX,
         "Type a size or use the arrows; the box updates as you go."],
        "Titles read well at 28–40 pt, body text at 18–24 pt."),
    "bold": (
        "Bold",
        "Makes text bold. While you are typing in a box it applies to "
        "the selected words; otherwise to the whole selected box.",
        ["Double-click a box to type in it and select some words — or "
         "just click the box for all of it.",
         "Click Bold (or press Ctrl+B while typing)."],
        "Click again to remove bold."),
    "italic": (
        "Italic",
        "Makes text italic. While you are typing in a box it applies to "
        "the selected words; otherwise to the whole selected box.",
        ["Double-click a box and select some words — or click the box "
         "for all of it.",
         "Click Italic (or press Ctrl+I while typing)."],
        "Click again to remove italic."),
    "superscript": (
        "Superscript",
        "Raises text above the line, smaller — x², 10⁻³, 1ˢᵗ. While "
        "typing it applies to the selected characters, otherwise to the "
        "whole box.",
        ["Double-click a box and select the characters to raise.",
         "Click Superscript."],
        "For real mathematics use the Equation builder."),
    "subscript": (
        "Subscript",
        "Lowers text below the line, smaller — H₂O, xᵢ. While typing it "
        "applies to the selected characters, otherwise to the whole box.",
        ["Double-click a box and select the characters to lower.",
         "Click Subscript."],
        "Chemical formulas look best with the Chemical reaction builder."),
    "align_left": (
        "Align left",
        "Lines the text of the selected box up on its left edge — the "
        "usual choice for bullets and paragraphs.",
        [_PICK_BOX, "Click Align left."], None),
    "align_center": (
        "Centre",
        "Centres each line of the selected box between its edges — for "
        "titles, captions and short statements.",
        [_PICK_BOX, "Click Centre."], None),
    "align_right": (
        "Align right",
        "Lines the text of the selected box up on its right edge — for "
        "dates, credits and numbers.",
        [_PICK_BOX, "Click Align right."], None),
    "text_colour": (
        "Text colour",
        "Colours the text of the selected box — on the slide and in the "
        "PDF.",
        [_PICK_BOX,
         "Click Text colour and pick a colour.",
         "Click OK — the slide and the PDF follow."],
        "Leave text in the theme's colour for a consistent look; keep "
        "colour for emphasis."),
    "fill_colour": (
        "Fill colour",
        "Paints the background of the selected box — a coloured panel "
        "behind its text.",
        [_PICK_BOX,
         "Click Fill colour and pick a colour."],
        "Right-click the box for its border, rounded corners, shadow and "
        "transparency."),
    "bullets": (
        "Bullet list",
        "Starts a bullet list. While typing in a box, the current line "
        "becomes a bullet; otherwise a new box with two bullets is "
        "added.",
        ["Double-click a text box and put the cursor on a line — or "
         "just click Bullet list for a new box.",
         "Type each point; Enter starts the next bullet.",
         "Tab indents a point one level, Shift+Tab brings it back."],
        "The bullets are the theme's own (balls, triangles…), as in the "
        "PDF."),
    "numbered": (
        "Numbered list",
        "Starts a numbered list (1, 2, 3…). While typing in a box, the "
        "current line becomes item 1; otherwise a new box is added.",
        ["Double-click a text box and put the cursor on a line — or "
         "just click Numbered list for a new box.",
         "Type each step; Enter starts the next number.",
         "Tab indents a step one level."],
        None),
    "replace_image": (
        "Replace image",
        "Swaps the picture in the selected image box for another file, "
        "keeping the box's place and size.",
        ["Click an image box on the slide.",
         "Click Replace image and choose the new picture."],
        "Double-clicking an image does the same; right-click it for "
        "crop, effects and layout."),
    # ------------------------------------------------------ compiling
    "pdf_side": (
        "Visual + PDF side by side",
        "Shows the compiled PDF beside the slide you are editing, kept "
        "up to date as you work. Click again for Visual only (no PDF, no "
        "background compiles).",
        ["Click to switch between Visual + PDF and Visual only.",
         "View ▸ “Visual + PDF in its own window” (Ctrl+5) puts the PDF "
         "on another screen — close that window to dock it back."],
        "Ctrl+4 side by side, Ctrl+5 own window, Ctrl+6 Visual only."),
    "skip_images": (
        "Skip images",
        "Compiles faster by drawing grey placeholders instead of loading "
        "the pictures — handy for big photos while you work on the text.",
        ["Click to turn it on (the PDF shows placeholders).",
         "Click again to bring the pictures back."],
        "It only affects the preview: Export PDF and the slideshow always "
        "include the pictures."),
    "compile": (
        "Compile now",
        "Builds the PDF from the presentation straight away with LaTeX "
        "(beamer), and shows it in the PDF panel.",
        ["Click Compile now (or press Ctrl+R).",
         "Watch the status bar; a few seconds later the PDF updates."],
        "With Auto-compile on you rarely need it. Errors are listed in "
        "the Console tab."),
    "auto_compile": (
        "Auto-compile",
        "Recompiles the PDF by itself a moment after each change, so the "
        "PDF panel always matches the slides. Green when on, struck "
        "through when off.",
        ["Click to turn it on or off."],
        "Turn it off on a slow computer or a very long presentation, "
        "and use Compile now (Ctrl+R) instead."),
    # ------------------------------------------------- slides (left bar)
    "prev_slide": (
        "Previous slide",
        "Goes to the slide before the one you are editing, and shows it "
        "in the Visual editor and the PDF.",
        ["Click to move up one slide."],
        "Or click any slide in the slides list."),
    "next_slide": (
        "Next slide",
        "Goes to the slide after the one you are editing, and shows it "
        "in the Visual editor and the PDF.",
        ["Click to move down one slide."],
        "Or click any slide in the slides list."),
    "slides_list": (
        "Show / hide the slides list",
        "Folds the slides list on the left away to a thin strip, for a "
        "bigger slide — and brings it back.",
        ["Click to hide or show the list (or press Ctrl+B).",
         "When hidden, click the thin “Slides” strip to bring it back."],
        "In the list: drag a slide up or down to move it; right-click "
        "for delete, hide / show, duplicate…"),
    "add_slide": (
        "Add slide",
        "Adds a new slide after the current one. Click for a blank "
        "slide; the ▾ arrow offers layouts (title, title + content, two "
        "columns, picture + text, comparison…) with a picture of each.",
        ["Click the + for a blank slide — or the ▾ arrow and pick a "
         "layout.",
         "The new slide opens for editing; type into its boxes by "
         "double-clicking them."],
        "Right-click a slide in the list ▸ “Apply layout” to change an "
        "existing slide's layout."),
    "remove_slide": (
        "Remove slide",
        "Deletes the slide you are editing (the last remaining slide is "
        "kept).",
        ["Go to the slide to delete.",
         "Click Remove slide."],
        "Changed your mind? Undo (Ctrl+Z). To keep a slide but leave it "
        "out of the show, right-click it ▸ Hide slide."),
    # ----------------------------------------------------- insert (left)
    "text_box": (
        "Add text box",
        "Adds a text box to the slide, below the existing boxes. It is "
        "unlocked: drag it anywhere, resize it from its handles.",
        ["Click Add text box.",
         "Double-click it to type; click outside (or Esc) to finish.",
         "Drag it into place and resize it from its corners."],
        "LaTeX works inside: $x^2$ for maths, \\textbf{…} for bold. The "
        "padlock badge locks a box so beamer places it."),
    "picture": (
        "Add image",
        "Inserts a picture (PNG, JPG, PDF, GIF, SVG, WMF / EMF…) in a "
        "box you can move and resize.",
        ["Click Add image and choose the file.",
         "Drag it into place; drag a corner to resize (the proportions "
         "are kept).",
         "Right-click it for crop, effects (fade, soft edges, glow…), "
         "colour and layout."],
        "You can also drop picture files straight onto the slide."),
    "video": (
        "Add video",
        "Inserts a video that plays in the PDF (in viewers that support "
        "it), shown with its first frame as a poster.",
        ["Click Add video and choose the file.",
         "Move and resize it like a picture.",
         "Right-click it for the poster frame and playback options."],
        "Test the PDF in the viewer you will present with."),
    "table": (
        "Add table",
        "Adds a 2 × 2 table. Double-click a cell to type in it; "
        "right-click the table to add or remove rows and columns and to "
        "choose a style.",
        ["Click Add table.",
         "Double-click a cell and type; Tab moves to the next cell.",
         "Right-click for rows, columns and table styles."],
        "Insert ▸ Table lets you pick the size and a style first."),
    "equation": (
        "Equation builder",
        "Builds an equation by clicking — fractions, sums, integrals, "
        "matrices, Greek letters — with a live LaTeX preview, the same "
        "builder as KherveTeX.",
        ["Click Equation builder (Ctrl+Shift+E).",
         "Click the parts you need from the categories, or type LaTeX.",
         "Click Insert: the equation lands on the slide as a box."],
        "Double-click an equation box to edit it again."),
    "chemistry": (
        "Chemical reaction",
        "Writes chemical formulas and reactions (mhchem): H₂O, "
        "2H₂ + O₂ → 2H₂O, equilibria, states and charges.",
        ["Click Chemical reaction (Ctrl+Shift+R).",
         "Type or click the formula; the preview shows the result.",
         "Click Insert."],
        "For drawn molecules use Chemical structure."),
    "chemfig": (
        "Chemical structure",
        "Draws a molecule's structure (chemfig) — rings, bonds, "
        "groups — and places it on the slide.",
        ["Click Chemical structure (Ctrl+Shift+T).",
         "Build the molecule from the templates or draw it.",
         "Click Insert."],
        "Double-click the structure on the slide to edit it again."),
    "flowchart": (
        "Flowchart builder",
        "Builds a LaTeX (TikZ) flowchart by clicking: start / end, "
        "process, decision, input / output and more, joined by arrows, "
        "lines or curves — top to bottom or left to right.",
        ["Click Flowchart builder (Ctrl+Shift+F).",
         "Click shapes in the palette to add them after the selected "
         "box; use Arrow, Curve or Line to join two boxes.",
         "Double-click a box to type in it; select a link for its "
         "arrowheads, sides and bend.",
         "Click Insert."],
        "Double-click the flowchart on the slide to edit it again."),
    "symbol": (
        "Insert symbol",
        "Opens a palette of symbols — Greek letters, arrows, operators, "
        "relations — and inserts the one you choose.",
        ["Double-click a text box and put the cursor where the symbol "
         "goes (or just select the box).",
         "Click Insert symbol and pick a symbol."],
        "Symbols are written as LaTeX, so they look the same in the PDF."),
    "drawing": (
        "Add drawing",
        "Opens the drawing editor: sketch with pens, shapes, arrows, "
        "dimension lines and ready-made science symbols (flowchart, "
        "electrical, optics, labware…), then place it as a picture.",
        ["Click Add drawing.",
         "Draw with the tools on the left; set colours and line widths.",
         "Save: the drawing appears on the slide."],
        "Double-click it on the slide to edit it again."),
    "line": (
        "Add line",
        "Adds a straight line you can move and stretch — to underline, "
        "divide or connect.",
        ["Click Add line.",
         "Drag the line to move it; drag an end to stretch or turn it.",
         "Right-click it for colour, thickness, dashes and arrowheads."],
        "Hold Shift while dragging an end to keep it straight."),
    "arrow": (
        "Add arrow",
        "Adds an arrow you can move, stretch and point anywhere.",
        ["Click Add arrow.",
         "Drag it into place; drag its ends to point it.",
         "Right-click for colour, thickness, dashes and the arrowheads "
         "at each end."],
        None),
    "rect": (
        "Add rectangle",
        "Adds a rectangle — a frame, a highlight or a coloured panel.",
        ["Click Add rectangle.",
         "Drag it into place and resize it from its handles.",
         "Right-click for fill, border, rounded corners, shadow and "
         "transparency; Insert ▸ Shapes has many more shapes."],
        "Send it to the back to put it behind text."),
    "ellipse": (
        "Add circle / ellipse",
        "Adds a circle you can stretch into an ellipse — to circle or "
        "highlight something.",
        ["Click Add circle / ellipse.",
         "Drag it into place; resize it from its handles.",
         "Right-click for fill, border and transparency."],
        "A transparent fill with a thick border circles a detail."),
    # -------------------------------------------------- arrange (left)
    "raise": (
        "Raise object",
        "Brings the selected box one step forward, over the box just in "
        "front of it.",
        [_PICK_BOX, "Click Raise object (repeat to go further up)."],
        "Objects stack in the order they were added — the last on top."),
    "lower": (
        "Lower object",
        "Sends the selected box one step back, behind the box just "
        "behind it.",
        [_PICK_BOX, "Click Lower object (repeat to go further down)."],
        None),
    "front": (
        "Bring to front",
        "Puts the selected box on top of everything else on the slide, "
        "so nothing covers it.",
        [_PICK_BOX, "Click Bring to front."], None),
    "back": (
        "Send to back",
        "Puts the selected box behind everything else on the slide — "
        "for background panels and pictures.",
        [_PICK_BOX, "Click Send to back."],
        "Things on every slide (a logo, a band) belong on the Master."),
    "delete": (
        "Delete object",
        "Removes the selected box(es) from the slide.",
        ["Click a box — Shift-click or drag a frame around several.",
         "Click Delete object (or press Delete)."],
        "Undo (Ctrl+Z) brings it back."),
    # ------------------------------------------------- bottom view bar
    "theme": (
        "Slide theme",
        "The look of every slide: the beamer presentation theme, its "
        "colours, the theme wizard (make one, or import a university / "
        "PowerPoint template) and the theme decorations.",
        ["Click Theme.",
         "Choose a Presentation theme (the whole look) and, if you like, "
         "a Colour theme (colours only).",
         "Preview themes… shows them all side by side."],
        "The same menu is in View ▸ Slide theme."),
    "view_normal": (
        "Normal view",
        "Edit one slide at a time in the Visual editor, with the slides "
        "list on the left — the usual view.",
        ["Click Normal."],
        None),
    "view_overview": (
        "Overview of all the slides",
        "Shows every slide as a mini page — in the right frame beside "
        "the slide, or in the slide's place when you work in Visual "
        "only.",
        ["Click Overview.",
         "Click a mini page to go to that slide; double-click to edit it.",
         "Drag a mini page to reorder; right-click for the slide menu.",
         "The Size slider makes the mini pages bigger or smaller."],
        None),
    "view_master": (
        "Master",
        "The template behind every slide. What you put on it — a logo, "
        "a band, a line, a text — shows on all the slides, behind their "
        "own content.",
        ["Click Master: an orange bar shows you are on the master.",
         "Add and arrange boxes as on any slide.",
         "Click Close master view (or Normal) to go back."],
        "Leave the slide titles and footers to the theme; put branding "
        "on the master."),
    "slideshow": (
        "Slideshow",
        "Presents the compiled PDF full screen from the current slide. "
        "The ▾ arrow offers: from the beginning, presenter view, current "
        "+ next slide, in a window, and the automatic slideshow.",
        ["Click to start from the slide you are on (Shift+F5); F5 starts "
         "from the beginning.",
         "Arrows, Space or a click move on; Esc ends the show."],
        "Hidden slides are skipped. Slideshow ▸ Show the slides on picks "
        "the screen."),
}

#: Keys that also act as the bottom bar's zoom buttons.
TIPS["view_zoom_out"] = TIPS["zoom_out"]
TIPS["view_fit"] = TIPS["fit"]
TIPS["view_zoom_in"] = TIPS["zoom_in"]


def entry(key):
    return TIPS[key]


def summary(key) -> str:
    """One line for the status bar: the title and what it does."""
    title, what, _steps, _tip = TIPS[key]
    first = what.split(". ")[0].rstrip(".")
    return f"{title} — {first}."


def rich(key, shortcut: str = "", footer: str = "") -> str:
    """The HTML tooltip for *key*: title (+ shortcut), what it does,
    numbered how-to steps and a tip."""
    title, what, steps, tip = TIPS[key]
    keys = (f" &nbsp;<span style='color:#8a8a8a'>{shortcut}</span>"
            if shortcut else "")
    parts = [f"<b>{title}</b>{keys}",
             f"<p style='margin:4px 0 0 0'>{what}</p>"]
    if steps:
        items = "".join(f"<li>{s}</li>" for s in steps)
        parts.append("<p style='margin:6px 0 0 0'><b>How to use</b></p>"
                     f"<ol style='margin:2px 0 0 0'>{items}</ol>")
    if tip:
        parts.append(f"<p style='margin:4px 0 0 0; color:#8a8a8a'>"
                     f"<i>Tip:</i> {tip}</p>")
    if footer:
        parts.append(f"<p style='margin:6px 0 0 0; color:#8a8a8a'>"
                     f"{footer}</p>")
    return (f"<table width='{WIDTH}' cellspacing='0' cellpadding='0'>"
            f"<tr><td>{''.join(parts)}</td></tr></table>")


def apply(target, key, shortcut: str = "") -> None:
    """Give a QAction / QWidget its rich tooltip and status-bar text. The
    shortcut defaults to the action's own."""
    if not shortcut and hasattr(target, "shortcut"):
        try:
            from PySide6.QtGui import QKeySequence
            shortcut = target.shortcut().toString(
                QKeySequence.NativeText)
        except Exception:
            shortcut = ""
    target.setToolTip(rich(key, shortcut))
    if hasattr(target, "setStatusTip"):
        target.setStatusTip(summary(key))
