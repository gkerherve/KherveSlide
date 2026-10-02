"""Welcome page shown at start: what to open, and how to work.

The layout choice is asked every time (unless the page is switched off)
because it depends on the task — the same choice KherveTeX offers: the
Visual slide editor with the live PDF beside it (or in its own window)
when the LaTeX output matters, or the Visual editor alone, like
PowerPoint, with the PDF and console hidden and no background compiles.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QRadioButton,
    QVBoxLayout, QWidget,
)

LAYOUT_SIDE = "side"        # Visual + PDF side by side
LAYOUT_WINDOW = "window"    # Visual + PDF in its own window
LAYOUT_VISUAL = "visual"    # Visual only (PDF / console hidden)
LAYOUTS = (LAYOUT_SIDE, LAYOUT_WINDOW, LAYOUT_VISUAL)

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
    return mode if mode in LAYOUTS else LAYOUT_SIDE


class WelcomeDialog(QDialog):
    """Returns, via `choice` and `layout_mode`, what the user picked.

    choice is one of ("continue",), ("new",), ("open",), ("pptx",),
    ("template", name) or ("recent", Path)."""

    def __init__(self, recent: list, templates: list[str],
                 layout: str = LAYOUT_SIDE, show_at_start: bool = True,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to KherveSlide")
        self.setMinimumSize(QSize(860, 560))
        self.choice: tuple = ("continue",)
        self.layout_mode = normalise_layout(layout)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(14)

        # ── header ────────────────────────────────────────────
        from . import __version__, icons
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(64, 64))
        head.addWidget(logo)
        titles = QVBoxLayout()
        t = QLabel("KherveSlide")
        f = QFont()
        f.setPointSizeF(22)
        f.setBold(True)
        t.setFont(f)
        titles.addWidget(t)
        titles.addWidget(QLabel(
            "Design like in PowerPoint, present in LaTeX — version "
            f"{__version__}"))
        head.addLayout(titles, 1)
        root.addLayout(head)

        # ── start / templates / recent ────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(16)

        start = QVBoxLayout()
        start.addWidget(self._heading("Start"))
        for label, tip, choice in (
                ("\U0001F4C4  New presentation", "A blank presentation",
                 ("new",)),
                ("\U0001F4C2  Open…", "Open a KherveSlide presentation",
                 ("open",)),
                ("\U0001F4CA  Import PowerPoint…",
                 "Turn a .pptx into a beamer presentation", ("pptx",)),
                ("→  Continue", "Keep the presentation already open behind "
                 "this page", ("continue",))):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setMinimumHeight(34)
            b.setStyleSheet("text-align: left; padding-left: 12px;")
            b.clicked.connect(lambda _=False, c=choice: self._finish(c))
            start.addWidget(b)
        start.addStretch(1)
        cols.addLayout(start, 3)

        tpl_col = QVBoxLayout()
        tpl_col.addWidget(self._heading("Templates"))
        self._templates = QListWidget()
        for name in templates:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            self._templates.addItem(item)
        self._templates.itemActivated.connect(
            lambda it: self._finish(("template", it.data(Qt.UserRole))))
        tpl_col.addWidget(self._templates, 1)
        cols.addLayout(tpl_col, 3)

        rec_col = QVBoxLayout()
        rec_col.addWidget(self._heading("Recent"))
        self._recent = QListWidget()
        for p in recent:
            p = Path(p)
            item = QListWidgetItem(f"{p.name}\n   {p.parent}")
            item.setToolTip(str(p))
            item.setData(Qt.UserRole, str(p))
            if not p.exists():
                item.setFlags(Qt.NoItemFlags)
            self._recent.addItem(item)
        if not recent:
            empty = QListWidgetItem("No recent presentations yet")
            empty.setFlags(Qt.NoItemFlags)
            self._recent.addItem(empty)
        self._recent.itemActivated.connect(
            lambda it: it.data(Qt.UserRole) and self._finish(
                ("recent", Path(it.data(Qt.UserRole)))))
        rec_col.addWidget(self._recent, 1)
        cols.addLayout(rec_col, 4)
        root.addLayout(cols, 1)

        # ── how to work ───────────────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        root.addWidget(line)
        root.addWidget(self._heading("How do you want to work?"))
        modes = QGridLayout()
        modes.setHorizontalSpacing(24)
        modes.setVerticalSpacing(10)
        self._group = QButtonGroup(self)
        for n, mode in enumerate(LAYOUTS):
            title, text = LAYOUT_TEXT[mode]
            box = QVBoxLayout()
            rb = QRadioButton(title)
            f = rb.font()
            f.setBold(True)
            rb.setFont(f)
            rb.setChecked(mode == self.layout_mode)
            rb.toggled.connect(
                lambda on, m=mode: on and setattr(self, "layout_mode", m))
            self._group.addButton(rb)
            box.addWidget(rb)
            desc = QLabel(text)
            desc.setWordWrap(True)
            desc.setContentsMargins(24, 0, 0, 0)
            box.addWidget(desc)
            box.addStretch(1)
            holder = QWidget()
            holder.setLayout(box)
            modes.addWidget(holder, 0, n)
        root.addLayout(modes)

        bottom = QHBoxLayout()
        self._show_again = QCheckBox(
            "Show this page when KherveSlide starts")
        self._show_again.setChecked(show_at_start)
        bottom.addWidget(self._show_again)
        bottom.addStretch(1)
        go = QPushButton("Start designing")
        go.setDefault(True)
        go.setMinimumWidth(150)
        go.clicked.connect(lambda: self._finish(("continue",)))
        bottom.addWidget(go)
        root.addLayout(bottom)

    @staticmethod
    def _heading(text: str) -> QLabel:
        lab = QLabel(text)
        f = lab.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 1.5)
        lab.setFont(f)
        return lab

    def show_at_start(self) -> bool:
        return self._show_again.isChecked()

    def _finish(self, choice: tuple) -> None:
        self.choice = choice
        self.accept()
