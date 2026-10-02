"""Startup splash screen, painted with QPainter at runtime (no image file,
crisp at any DPI, carries the live version) — the same picture-plus-progress
splash as KherveTeX and KherveSheet, in KherveSlide's orange."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import QApplication, QSplashScreen

WIDTH, HEIGHT = 640, 380
_TOP = QColor("#F5924C")
_BOTTOM = QColor("#A9470A")
_INK = QColor("#ffffff")
_ACCENT = QColor("#2c3e7a")   # a beamer-blue title bar on the slides

#: The steps main() reports, in order; the bar advances through them.
STEPS = ("Loading the designer", "Building the window",
         "Opening the presentation", "Ready")


def _slides(p: QPainter, rect: QRectF) -> None:
    """Two stacked 16:9 slides — a frame-title bar, bullets, a picture and
    a footline: the beamer slide the app produces."""
    for k, (dx, dy, alpha) in enumerate(((30, -22, 70), (0, 0, 240))):
        s = QRectF(rect.left() + dx, rect.top() + dy,
                   rect.width(), rect.width() * 9 / 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawRoundedRect(s.translated(3, 4), 3, 3)
        p.setBrush(QColor(255, 255, 255, alpha))
        p.drawRoundedRect(s, 3, 3)
        if k == 0:
            continue
        # frame title bar
        bar = QRectF(s.left(), s.top() + 8, s.width(), 22)
        p.setBrush(_ACCENT)
        p.drawRect(bar)
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawRoundedRect(QRectF(bar.left() + 12, bar.center().y() - 3,
                                 92, 6), 3, 3)
        # bullets
        y = bar.bottom() + 16
        for i in range(4):
            p.setBrush(_ACCENT)
            p.drawEllipse(QPointF(s.left() + 16, y + 2), 2.6, 2.6)
            p.setBrush(QColor(40, 50, 80, 110))
            w = (s.width() * 0.48) * (0.6 if i == 3 else 1.0)
            p.drawRoundedRect(QRectF(s.left() + 24, y, w, 4), 2, 2)
            y += 15
        # picture box: a little mountain landscape
        pic = QRectF(s.left() + s.width() * 0.62, bar.bottom() + 10,
                     s.width() * 0.32, s.height() * 0.42)
        p.setBrush(QColor("#cfe0f5"))
        p.drawRect(pic)
        p.setBrush(QColor("#6f9a54"))
        path = QPainterPath()
        path.moveTo(pic.bottomLeft())
        path.lineTo(pic.left() + pic.width() * 0.35, pic.top() + pic.height() * 0.4)
        path.lineTo(pic.left() + pic.width() * 0.55, pic.top() + pic.height() * 0.65)
        path.lineTo(pic.left() + pic.width() * 0.75, pic.top() + pic.height() * 0.3)
        path.lineTo(pic.bottomRight())
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QColor("#f2c14e"))
        p.drawEllipse(QPointF(pic.right() - 10, pic.top() + 9), 4.5, 4.5)
        # footline
        foot = QRectF(s.left(), s.bottom() - 9, s.width(), 9)
        p.setBrush(_ACCENT.lighter(130))
        p.drawRect(foot)
        # selection handles round the picture: it's a WYSIWYG designer
        p.setPen(QPen(QColor("#DE6A14"), 1.2, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(pic.adjusted(-3, -3, 3, 3))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#DE6A14"))
        for c in (pic.topLeft(), pic.topRight(), pic.bottomLeft(),
                  pic.bottomRight()):
            p.drawRect(QRectF(c.x() - 5, c.y() - 5, 7, 7).translated(1, 1))


def splash_pixmap(dpr: float = 1.0) -> QPixmap:
    from . import __version__, icons
    pm = QPixmap(int(WIDTH * dpr), int(HEIGHT * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    frame = QRectF(0, 0, WIDTH, HEIGHT)
    bg = QLinearGradient(frame.topLeft(), frame.bottomRight())
    bg.setColorAt(0.0, _TOP)
    bg.setColorAt(1.0, _BOTTOM)
    clip = QPainterPath()
    clip.addRoundedRect(frame, 14, 14)
    p.setClipPath(clip)
    p.fillRect(frame, bg)
    p.setPen(QPen(QColor(255, 255, 255, 20), 1))
    for i in range(0, WIDTH + 160, 32):
        p.drawLine(QPointF(i, 0), QPointF(i - 120, HEIGHT))
    _slides(p, QRectF(350, 110, 250, 0))

    mark = icons.app_icon_pixmap(int(96 * dpr))
    mark.setDevicePixelRatio(dpr)
    p.setPen(QPen(QColor(255, 255, 255, 120), 2))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(39, 51, 98, 98), 18, 18)
    p.drawPixmap(QPointF(40, 52), mark)
    p.setPen(_INK)
    title = QFont()
    title.setPointSizeF(34)
    title.setBold(True)
    p.setFont(title)
    p.drawText(QRectF(40, 170, 330, 54), Qt.AlignLeft | Qt.AlignVCenter,
               "KherveSlide")
    sub = QFont()
    sub.setPointSizeF(12.5)
    p.setFont(sub)
    p.setPen(QColor(255, 255, 255, 225))
    p.drawText(QRectF(42, 222, 300, 44), Qt.AlignLeft | Qt.TextWordWrap,
               "Design like in PowerPoint,\npresent in LaTeX")
    small = QFont()
    small.setPointSizeF(9.5)
    p.setFont(small)
    p.setPen(QColor(255, 255, 255, 170))
    p.drawText(QRectF(42, HEIGHT - 34, 300, 20),
               Qt.AlignLeft | Qt.AlignVCenter, f"Version {__version__}")
    p.drawText(QRectF(WIDTH - 322, HEIGHT - 34, 300, 20),
               Qt.AlignRight | Qt.AlignVCenter,
               "© 2026 Gwilherm Kerherve · GPL-3.0")
    p.end()
    return pm


class Splash(QSplashScreen):
    """The start-up picture plus a status line and a progress bar."""

    def __init__(self):
        screen = QApplication.primaryScreen()
        ratio = screen.devicePixelRatio() if screen is not None else 1.0
        super().__init__(splash_pixmap(max(1.0, ratio)),
                         Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.step_text = STEPS[0]
        self.fraction = 0.0

    def step(self, text: str) -> None:
        self.step_text = text
        if text in STEPS:
            self.fraction = STEPS.index(text) / (len(STEPS) - 1)
        self.repaint()
        QApplication.processEvents()

    def drawContents(self, p: QPainter) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        bar = QRectF(42, HEIGHT - 62, 290, 5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 45))
        p.drawRoundedRect(bar, 2.5, 2.5)
        if self.fraction > 0:
            p.setBrush(QColor("#ffffff"))
            p.drawRoundedRect(QRectF(bar.x(), bar.y(),
                                     bar.width() * self.fraction,
                                     bar.height()), 2.5, 2.5)
        p.setPen(QColor(255, 255, 255, 215))
        small = QFont()
        small.setPointSizeF(10.5)
        p.setFont(small)
        dots = "" if self.step_text == STEPS[-1] else "…"
        p.drawText(QRectF(42, HEIGHT - 86, 330, 20),
                   Qt.AlignLeft | Qt.AlignVCenter, self.step_text + dots)
