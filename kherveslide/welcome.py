"""The Welcome page's layout choice — how to work, worded as KherveTeX.

The page itself is start_page.StartPage, shown inside the main window.
The layout choice is offered on it because it depends on the task: the
Visual slide editor with the live PDF beside it (or in its own window)
when the LaTeX output matters, or the Visual editor alone, like
PowerPoint, with the PDF and console hidden and no background compiles.
"""
from __future__ import annotations

LAYOUT_SIDE = "side"        # Visual + PDF side by side
LAYOUT_WINDOW = "window"    # Visual + PDF in its own window
LAYOUT_VISUAL = "visual"    # Visual only (PDF / console hidden)
LAYOUTS = (LAYOUT_SIDE, LAYOUT_WINDOW, LAYOUT_VISUAL)
# First launch: the PDF in its own window, so the Visual editor gets the
# whole main window and the two can be compared side by side.
LAYOUT_DEFAULT = LAYOUT_WINDOW

LAYOUT_TEXT = {
    LAYOUT_SIDE: ("Visual + PDF side by side",
                  "Design the slide on the left and watch the compiled "
                  "beamer PDF on the right, updated as you edit."),
    LAYOUT_WINDOW: ("Visual + PDF in its own window",
                    "The PDF and console in a separate window you can put "
                    "on a second screen; close it to dock it back."),
    LAYOUT_VISUAL: ("Visual only",
                    "Just the slides and the Visual editor. The PDF and "
                    "console are hidden and nothing compiles while you "
                    "work."),
}


def normalise_layout(mode) -> str:
    if mode in ("slide", "page"):     # v0.123's "just the slide"
        return LAYOUT_VISUAL
    return mode if mode in LAYOUTS else LAYOUT_DEFAULT
