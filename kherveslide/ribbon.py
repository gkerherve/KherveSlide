"""PowerPoint-style ribbon (vendored from KherveTeX's Word ribbon): tabs
of labelled groups, big buttons for the main command of a group and rows
of small buttons beside them.

The ribbon only arranges things the window already owns — QActions and
a few widgets (combos, galleries) — so the classic toolbars and the
ribbon can be swapped at run time without rebuilding any state."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QTabWidget,
    QToolButton, QVBoxLayout, QWidget,
)

_LARGE = QSize(32, 32)
_SMALL = QSize(20, 20)


def _button(action: QAction, large: bool, text: bool) -> QToolButton:
    b = QToolButton()
    b.setDefaultAction(action)
    b.setAutoRaise(True)
    # Clicking a ribbon button must not blur (and commit) the in-place
    # text editor — Bold etc. then format just the selected run.
    b.setFocusPolicy(Qt.NoFocus)
    # A drop-down beside the button (PowerPoint's Paste ▾), kept off the action
    # itself so the action stays a plain item in the menu bar.
    menu = action.property("ribbon_menu")
    if menu is not None:
        b.setMenu(menu)
        b.setPopupMode(QToolButton.InstantPopup
                       if action.property("ribbon_instant")
                       else QToolButton.MenuButtonPopup)
    if large:
        b.setIconSize(_LARGE)
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        b.setMinimumWidth(52)
    else:
        b.setIconSize(_SMALL)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if text
                             else Qt.ToolButtonIconOnly)
    return b


def _short(action: QAction) -> str:
    """Menu text without the & accelerator or a trailing ellipsis."""
    return action.text().replace("&", "").rstrip(".…").strip()


class RibbonTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(4, 2, 4, 0)
        self._lay.setSpacing(0)
        self._lay.addStretch(1)

    def add_group(self, label: str, *, large=(), rows=(),
                  text: bool = False) -> None:
        """A group: `large` actions/widgets as big buttons, then `rows`
        (lists of actions/widgets) stacked as small buttons; `text`
        shows labels beside the small icons."""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(6, 0, 6, 0)
        v.setSpacing(0)
        body = QHBoxLayout()
        body.setSpacing(2)
        for it in large:
            if isinstance(it, QAction):
                btn = _button(it, True, True)
                btn.setText(_short(it))
                body.addWidget(btn, 0, Qt.AlignTop)
            else:
                body.addWidget(it, 0, Qt.AlignTop)
        if rows:
            # Each row packs on its own (PowerPoint's Font group: combos on
            # top, B / I / x² below), not in shared grid columns.
            grid = QVBoxLayout()
            grid.setSpacing(1)
            for r, row in enumerate(rows):
                line = QHBoxLayout()
                line.setSpacing(1)
                grid.addLayout(line)
                for c, it in enumerate(row):
                    if isinstance(it, QAction):
                        btn = _button(it, False, text)
                        if text:
                            btn.setText(_short(it))
                        line.addWidget(btn)
                    else:
                        line.addWidget(it)
                line.addStretch(1)
            body.addLayout(grid)
        v.addLayout(body)
        v.addStretch(1)
        cap = QLabel(label)
        cap.setAlignment(Qt.AlignHCenter)
        cap.setStyleSheet("color: palette(mid); font-size: 10px;")
        v.addWidget(cap)
        self._lay.insertWidget(self._lay.count() - 1, box)
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: palette(midlight);")
        self._lay.insertWidget(self._lay.count() - 1, sep)


class Ribbon(QTabWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDocumentMode(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(122)
        # PowerPoint: flat text tabs, no boxes; the open tab is bold with
        # a short coloured bar under it, and the groups sit on a plain band.
        self.setStyleSheet("""
            QTabWidget::pane { border: none;
                border-top: 1px solid palette(midlight); top: -1px; }
            QTabBar { qproperty-drawBase: 0; }
            QTabBar::tab { background: transparent; border: none;
                padding: 7px 11px 5px 11px; margin: 0 1px;
                font-size: 13px; }
            QTabBar::tab:hover { background: palette(midlight);
                border-radius: 4px; }
            QTabBar::tab:selected { font-weight: 600;
                border-bottom: 3px solid #c43e1c;
                padding-bottom: 2px; }
        """)

    def add_tab(self, name: str) -> RibbonTab:
        tab = RibbonTab()
        self.addTab(tab, name)
        return tab

    def add_contextual_tab(self, name: str, kind: str) -> RibbonTab:
        """A tab that appears only while the caret is in that kind of
        object (PowerPoint's Shape Format / Picture Format / Table tabs)."""
        tab = self.add_tab(name)
        idx = self.indexOf(tab)
        self.tabBar().setTabTextColor(idx, QColor("#c43e1c"))
        self.setTabVisible(idx, False)
        self._contextual = getattr(self, "_contextual", [])
        self._contextual.append((kind, tab))
        return tab

    def show_context(self, kind: str | None) -> None:
        for k, tab in getattr(self, "_contextual", []):
            idx = self.indexOf(tab)
            visible = k == kind
            if self.isTabVisible(idx) != visible:
                if not visible and self.currentIndex() == idx:
                    self.setCurrentIndex(0)
                self.setTabVisible(idx, visible)

    def set_corner(self, actions, corner: Qt.Corner) -> None:
        """Always-visible buttons beside the tabs (PowerPoint's Quick Access)."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(4, 0, 4, 0)
        h.setSpacing(0)
        for a in actions:
            if a is None:
                line = QFrame(); line.setFrameShape(QFrame.VLine)
                h.addWidget(line)
            else:
                h.addWidget(_button(a, False, False))
        self.setCornerWidget(w, corner)


def menu_action(icon, text: str, menu, parent) -> QAction:
    """A ribbon button that only opens `menu` (PowerPoint's Shapes ▾,
    Themes ▾); in a menu bar it is a plain submenu entry."""
    a = QAction(icon, text, parent)
    a.setMenu(menu)
    a.setProperty("ribbon_menu", menu)
    a.setProperty("ribbon_instant", True)
    return a
