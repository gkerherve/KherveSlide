"""The start page — the Welcome page, inside the main window.

Instead of a dialog, the slide area shows one big blank slide on a soft
background, and on it: Start (new / open / import / continue), the
templates and the example presentations as picture cards, and the "How
do you want to work?" layout choice (worded as KherveTeX). The slides
frame on the left shows the recent presentations meanwhile
(:class:`RecentPanel`). Help ▸ Welcome page brings it back; Continue or
Esc returns to the slides.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

from .welcome import LAYOUT_TEXT, LAYOUTS, normalise_layout

CARD_W = 168          # card thumbnail width (logical px)


def _heading(text: str, size: float = 1.5) -> QLabel:
    lab = QLabel(text)
    f = lab.font()
    f.setBold(True)
    f.setPointSizeF(f.pointSizeF() + size)
    lab.setFont(f)
    lab.setStyleSheet("color:#333333; background: transparent;")
    return lab


class _CardList(QListWidget):
    """A single row of picture cards (thumbnail above its name)."""

    picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListWidget.Static)
        self.setIconSize(QSize(CARD_W, CARD_W * 9 // 16))
        self.setSpacing(8)
        self.setWordWrap(True)
        self.setHorizontalScrollMode(QListWidget.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFixedHeight(CARD_W * 9 // 16 + 58)
        self.setFrameShape(QListWidget.NoFrame)
        self.setStyleSheet(
            "QListWidget { background: transparent; }"
            "QListWidget::item { color: #333333; border-radius: 6px;"
            " padding: 4px; }"
            "QListWidget::item:hover { background: rgba(222,106,20,40); }"
            "QListWidget::item:selected { background: rgba(222,106,20,70);"
            " color: #222222; }")
        self.itemClicked.connect(lambda it: self.picked.emit(
            it.data(Qt.UserRole)))

    def add_card(self, key: str, label: str, pixmap: QPixmap | None,
                 tip: str = "") -> QListWidgetItem:
        item = QListWidgetItem(QIcon(pixmap) if pixmap else QIcon(), label)
        item.setData(Qt.UserRole, key)
        item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
        if tip:
            item.setToolTip(tip)
        self.addItem(item)
        self.fit()
        return item

    def fit(self) -> None:
        """Size the cards so the whole row fits the width — no scrolling."""
        n = max(1, self.count())
        avail = self.viewport().width() - 2
        w = int(max(90, min(CARD_W, avail / n - 2 * self.spacing() - 16)))
        h = w * 9 // 16
        self.setIconSize(QSize(w, h))
        self.setFixedHeight(h + 58)
        for i in range(self.count()):
            self.item(i).setSizeHint(QSize(w + 16, h + 46))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()


class StartPage(QWidget):
    """Signals carry the user's choice; the window acts on them."""

    newRequested = Signal()
    openRequested = Signal()
    importRequested = Signal()
    continueRequested = Signal()
    templateChosen = Signal(str)
    exampleChosen = Signal(str)
    layoutChosen = Signal(str)
    showAtStartChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self._content = QWidget(self)
        self._content.setAttribute(Qt.WA_TranslucentBackground)
        root = QVBoxLayout(self._content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # header
        from . import __version__, icons
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(52, 52))
        head.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        t = QLabel("KherveSlide")
        f = QFont()
        f.setPointSizeF(24)
        f.setBold(True)
        t.setFont(f)
        t.setStyleSheet("color:#222222;")
        titles.addWidget(t)
        sub = QLabel("Design like in PowerPoint, present in LaTeX — "
                     f"version {__version__}")
        sub.setStyleSheet("color:#666666;")
        titles.addWidget(sub)
        head.addLayout(titles, 1)
        self.show_at_start = QCheckBox("Show this page when KherveSlide "
                                       "starts")
        self.show_at_start.setStyleSheet("color:#444444;")
        self.show_at_start.toggled.connect(self.showAtStartChanged)
        head.addWidget(self.show_at_start, 0, Qt.AlignTop)
        root.addLayout(head)

        # start buttons
        row = QHBoxLayout()
        row.setSpacing(10)
        for text, signal in (("\U0001F4C4  New presentation",
                              self.newRequested),
                             ("\U0001F4C2  Open…", self.openRequested),
                             ("\U0001F4CA  Import PowerPoint…",
                              self.importRequested),
                             ("Continue  →", self.continueRequested)):
            b = QPushButton(text)
            b.setMinimumHeight(36)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton { background: #FFFFFF; border: 1px solid"
                " #D8D2CC; border-radius: 8px; padding: 6px 14px;"
                " color:#222222; }"
                "QPushButton:hover { border-color: #DE6A14;"
                " background: #FFF4EC; }")
            b.clicked.connect(signal)
            row.addWidget(b)
        row.addStretch(1)
        root.addLayout(row)

        root.addWidget(_heading("Templates"))
        self.templates = _CardList()
        self.templates.picked.connect(self.templateChosen)
        root.addWidget(self.templates)
        root.addWidget(_heading("Example presentations"))
        self.examples = _CardList()
        self.examples.picked.connect(self.exampleChosen)
        root.addWidget(self.examples)

        root.addWidget(_heading("How do you want to work?", 0.5))
        modes = QHBoxLayout()
        self._mode_group = QButtonGroup(self)
        self._mode_buttons: dict = {}
        for mode in LAYOUTS:
            title, text = LAYOUT_TEXT[mode]
            rb = QRadioButton(title)
            rb.setToolTip(text)
            rb.setStyleSheet("color:#222222;")
            rb.toggled.connect(
                lambda on, m=mode: on and self.layoutChosen.emit(m))
            self._mode_group.addButton(rb)
            self._mode_buttons[mode] = rb
            modes.addWidget(rb)
        modes.addStretch(1)
        root.addLayout(modes)
        root.addStretch(1)

    # ---- state from the window ----
    def set_layout(self, mode: str) -> None:
        rb = self._mode_buttons.get(normalise_layout(mode))
        if rb is not None:
            rb.blockSignals(True)
            rb.setChecked(True)
            rb.blockSignals(False)

    def set_show_at_start(self, on: bool) -> None:
        self.show_at_start.blockSignals(True)
        self.show_at_start.setChecked(on)
        self.show_at_start.blockSignals(False)

    # ---- drawing: a big blank slide on a soft background ----
    def slide_rect(self) -> QRectF:
        m = 28.0
        w = max(10.0, self.width() - 2 * m)
        h = max(10.0, self.height() - 2 * m)
        if w / h > 16 / 9:
            w = h * 16 / 9
        else:
            h = w * 9 / 16
        # Never smaller than the content needs: then it simply fills.
        hint = self._content.sizeHint()
        if w < hint.width() + 60 or h < hint.height() + 50:
            return QRectF(8, 8, self.width() - 16, self.height() - 16)
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        r = self.slide_rect()
        mx, my = r.width() * 0.045, r.height() * 0.06
        self._content.setGeometry(r.adjusted(mx, my, -mx, -my).toRect())

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QLinearGradient(0, 0, self.width(), self.height())
        bg.setColorAt(0.0, QColor("#E9E4DF"))
        bg.setColorAt(1.0, QColor("#CFC6BE"))
        p.fillRect(self.rect(), bg)
        r = self.slide_rect()
        for k, alpha in enumerate((28, 18, 10)):        # soft shadow
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawRoundedRect(r.translated(0, 4 + 3 * k).adjusted(
                -k, -k, k, k), 10, 10)
        slide = QLinearGradient(r.topLeft(), r.bottomLeft())
        slide.setColorAt(0.0, QColor("#FFFFFF"))
        slide.setColorAt(1.0, QColor("#FBF7F3"))
        p.setBrush(QBrush(slide))
        p.drawRoundedRect(r, 10, 10)
        # a thin brand band along the slide's top, like a theme bar
        band = QPainterPath()
        band.addRoundedRect(QRectF(r.x(), r.y(), r.width(), 8), 4, 4)
        p.fillPath(band, QColor("#DE6A14"))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.continueRequested.emit()
        else:
            super().keyPressEvent(event)


class RecentPanel(QWidget):
    """The slides frame while the start page shows: recent files."""

    chosen = Signal(str)
    openRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setStyleSheet("QListWidget::item { padding: 6px 4px; }")
        self.list.itemActivated.connect(self._activate)
        self.list.itemClicked.connect(self._activate)
        lay.addWidget(self.list, 1)
        b = QPushButton("Open other…")
        b.clicked.connect(self.openRequested)
        lay.addWidget(b)

    def _activate(self, item):
        path = item.data(Qt.UserRole)
        if path:
            self.chosen.emit(path)

    def set_files(self, files: list[str]) -> None:
        self.list.clear()
        for f in files:
            p = Path(f)
            item = QListWidgetItem(f"{p.stem}\n{p.parent}")
            item.setToolTip(str(p))
            item.setData(Qt.UserRole, str(p))
            if not p.exists():
                item.setFlags(Qt.NoItemFlags)
            self.list.addItem(item)
        if not files:
            empty = QListWidgetItem("No recent presentations yet")
            empty.setFlags(Qt.NoItemFlags)
            self.list.addItem(empty)
