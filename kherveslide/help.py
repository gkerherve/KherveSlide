"""In-app User Guide — shows docs/USER_GUIDE.md (Help ▸ User Guide, F1).

The same viewer as KhervePlot's help dialog (a filterable contents list,
find, zoom, back / forward), minus its toolbar-icon chapter. The guide
itself is plain Markdown next to the code, so it can be read on GitHub
too.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QSplitter, QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)


def user_guide_path() -> Path:
    return Path(__file__).resolve().parent.parent / "docs" / "USER_GUIDE.md"


def parse_headings(md: str) -> list[tuple[int, str, int]]:
    """(level, text, char offset) of every ##–#### heading."""
    return [(len(m.group(1)), m.group(2).strip(), m.start())
            for m in re.finditer(r"(?m)^(#{2,4})\s+(.+?)\s*$", md)]


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("KherveSlide — User Guide")
        if parent is not None:
            self.setWindowIcon(parent.windowIcon())
        self.setModal(False)
        self.resize(980, 700)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(4)

        def btn(text, tip, slot):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setIconSize(QSize(16, 16))
            b.clicked.connect(slot)
            top.addWidget(b)

        btn("←", "Back (Alt+Left)", lambda: self.view.backward())
        btn("→", "Forward (Alt+Right)", lambda: self.view.forward())
        btn("⌂", "Top of guide", self._go_home)
        btn("A−", "Zoom out (Ctrl+−)", lambda: self.view.zoomOut(1))
        btn("A+", "Zoom in (Ctrl++)", lambda: self.view.zoomIn(1))
        top.addSpacing(12)
        top.addWidget(QLabel("Find:"))
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find in page…  (Enter = next)")
        self.find_edit.setClearButtonEnabled(True)
        self.find_edit.returnPressed.connect(self._find_next)
        top.addWidget(self.find_edit, 1)
        outer.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split, 1)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(2)
        self.toc_filter = QLineEdit()
        self.toc_filter.setPlaceholderText("Filter contents…")
        self.toc_filter.setClearButtonEnabled(True)
        self.toc_filter.textChanged.connect(self._filter_toc)
        lv.addWidget(self.toc_filter)
        self.toc = QListWidget()
        self.toc.setUniformItemSizes(True)
        lv.addWidget(self.toc, 1)
        left.setMaximumWidth(280)
        split.addWidget(left)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        split.addWidget(self.view)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 740])

        hint = QLabel("F1 toggles this window · Esc closes · Ctrl+F "
                      "focuses Find · Ctrl+± zooms")
        hint.setStyleSheet("color:#888; padding:2px;")
        outer.addWidget(hint)

        self._headings: list[tuple[int, str, int]] = []
        self._load()
        self.toc.currentRowChanged.connect(self._jump)

        QShortcut(QKeySequence("Ctrl+F"), self,
                  activated=lambda: (self.find_edit.setFocus(),
                                     self.find_edit.selectAll()))
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.close)
        QShortcut(QKeySequence(Qt.Key_F1), self, activated=self.close)
        QShortcut(QKeySequence("Alt+Left"), self,
                  activated=lambda: self.view.backward())
        QShortcut(QKeySequence("Alt+Right"), self,
                  activated=lambda: self.view.forward())

    def _load(self):
        path = user_guide_path()
        try:
            md = path.read_text(encoding="utf-8")
        except OSError as e:
            self.view.setPlainText(f"Could not load the user guide:\n{path}"
                                   f"\n\n{e}")
            return
        self.view.setMarkdown(md)
        self._headings = parse_headings(md)
        self.toc.clear()
        for level, text, _ in self._headings:
            it = QListWidgetItem("    " * (level - 2) + text)
            it.setData(Qt.UserRole, text)
            if level == 2:
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            self.toc.addItem(it)

    def _go_home(self):
        self.view.verticalScrollBar().setValue(0)

    def _jump(self, row: int):
        if not 0 <= row < self.toc.count():
            return
        title = self.toc.item(row).data(Qt.UserRole)
        if not title:
            return
        # Search from the top so any heading is found wherever we are.
        c = self.view.textCursor()
        c.movePosition(QTextCursor.Start)
        self.view.setTextCursor(c)
        found = self.view.document().find(title)
        if found.isNull():
            return
        found.movePosition(QTextCursor.StartOfBlock)
        self.view.setTextCursor(found)
        self.view.ensureCursorVisible()

    def _filter_toc(self, text: str):
        needle = text.strip().lower()
        for i in range(self.toc.count()):
            it = self.toc.item(i)
            it.setHidden(bool(needle) and needle not in it.text().lower())

    def _find_next(self):
        needle = self.find_edit.text().strip()
        if needle and not self.view.find(needle):
            c = self.view.textCursor()
            c.movePosition(QTextCursor.Start)
            self.view.setTextCursor(c)
            self.view.find(needle)
