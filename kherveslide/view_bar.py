"""The bar at the bottom of the window, as in PowerPoint: where you are
(slide 3 of 12), the slide theme, the views — Normal, Overview of all
the slides, Master — the slideshow, and the zoom.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QToolButton, QWidget,
)

from . import icons

VIEW_NORMAL, VIEW_OVERVIEW, VIEW_MASTER = "normal", "overview", "master"

VIEW_TEXT = {
    VIEW_NORMAL: ("Normal", "Normal — edit one slide (Visual)"),
    VIEW_OVERVIEW: ("Overview", "Overview — all the slides as mini pages"),
    VIEW_MASTER: ("Master", "Master — the template behind every slide: "
                  "what you put on it (logo, text, lines…) shows on all "
                  "the slides"),
}


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet("color:#c8ccd2;")
    return f


class ViewBar(QWidget):
    viewChosen = Signal(str)
    slideshowRequested = Signal()       # from the current slide
    zoomOutRequested = Signal()
    zoomInRequested = Signal()
    fitRequested = Signal()

    def __init__(self, theme_menu=None, show_menu=None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(2)
        self.counter = QLabel("")
        self.counter.setStyleSheet("color:#4b5563; padding:0 8px;")
        lay.addWidget(self.counter)
        lay.addWidget(_sep())

        def button(icon, text, tip, *, checkable=False) -> QToolButton:
            b = QToolButton()
            b.setIcon(icon)
            b.setIconSize(QSize(18, 18))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setCheckable(checkable)
            if text:
                b.setText(text)
                b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            lay.addWidget(b)
            return b

        self.theme = button(icons.theme_palette(), "Theme",
                            "Slide theme — the look of every slide "
                            "(also in View ▸ Slide theme)")
        if theme_menu is not None:
            self.theme.setMenu(theme_menu)
            self.theme.setPopupMode(QToolButton.InstantPopup)
        lay.addWidget(_sep())

        self.views: dict[str, QToolButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, icon in ((VIEW_NORMAL, icons.view_normal),
                          (VIEW_OVERVIEW, icons.view_overview),
                          (VIEW_MASTER, icons.view_master)):
            text, tip = VIEW_TEXT[key]
            b = button(icon(), "", tip, checkable=True)
            b.setAccessibleName(text)
            b.clicked.connect(lambda _c=False, k=key: self.viewChosen.emit(k))
            group.addButton(b)
            self.views[key] = b
        self.views[VIEW_NORMAL].setChecked(True)

        self.show_btn = button(icons.slideshow(), "",
                               "Slideshow from the current slide (Shift+F5)"
                               " — the arrow offers the other ways")
        self.show_btn.clicked.connect(self.slideshowRequested)
        if show_menu is not None:
            self.show_btn.setMenu(show_menu)
            self.show_btn.setPopupMode(QToolButton.MenuButtonPopup)
        lay.addWidget(_sep())

        for icon, tip, sig in ((icons.zoom_out, "Zoom out",
                                self.zoomOutRequested),
                               (icons.fit_width, "Fit the slide to the "
                                "window", self.fitRequested),
                               (icons.zoom_in, "Zoom in",
                                self.zoomInRequested)):
            b = button(icon(), "", tip)
            b.clicked.connect(sig)

    def set_view(self, key: str) -> None:
        b = self.views.get(key)
        if b is not None and not b.isChecked():
            b.setChecked(True)

    def set_counter(self, text: str) -> None:
        self.counter.setText(text)
