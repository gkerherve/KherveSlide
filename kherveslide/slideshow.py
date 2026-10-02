"""Slideshow — present the compiled PDF, full screen.

What the audience sees is the real beamer PDF (not the Visual canvas),
one page per slide. Four ways to present, like PowerPoint:

* **Full screen** — the slides on this screen.
* **In a window** — a normal, resizable window (F toggles full screen).
* **Presenter view** — the slides full screen on the other screen; this
  screen shows the current slide, the next one, the slide count, an
  elapsed timer and the clock.
* **Current + next** — two screens: the current slide on one, the next
  slide on the other.

Keys (in any slideshow window): → ↓ Space PageDown Enter N or a click go
forward; ← ↑ Backspace PageUp P or a right-click go back; Home / End;
type a number then Enter to jump; B / W black / white screen; Esc ends.

An **automatic** show (:class:`AutoPlay`) advances by itself every few
seconds — once through, looping for ever (a kiosk), or looping for a set
time. S pauses / resumes it; going back or forward by hand gives the new
slide its full time again; a blanked screen holds the countdown.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, \
    QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QVBoxLayout, QWidget,
)


class PdfPages:
    """The compiled PDF, rendered page by page at whatever size a view
    needs (cached per page and size)."""

    def __init__(self, pdf_bytes: bytes):
        import pymupdf
        self._doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        self._cache: dict = {}

    def __len__(self) -> int:
        return self._doc.page_count

    def aspect(self) -> float:
        r = self._doc[0].rect
        return r.width / r.height if r.height else 16 / 9

    def pixmap(self, index: int, size: QSize, dpr: float = 1.0) -> QPixmap:
        """Page *index* fitted inside *size* (device pixels × dpr)."""
        import pymupdf
        key = (index, size.width(), size.height(), dpr)
        pm = self._cache.get(key)
        if pm is not None:
            return pm
        page = self._doc[index]
        zoom = min(size.width() / page.rect.width,
                   size.height() / page.rect.height) * dpr
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                     QImage.Format_RGB888).copy()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        if len(self._cache) > 60:
            self._cache.clear()
        self._cache[key] = pm
        return pm


REPEATS = {"once": "Once through, then end",
           "loop": "Loop continuously (until Esc)",
           "for": "Loop for a set time"}


@dataclass
class AutoPlay:
    """An automatic show: each slide stays *seconds*; *repeat* is "once",
    "loop" or "for" (loop until *minutes* have passed)."""
    seconds: float = 10.0
    repeat: str = "once"
    minutes: float = 30.0


class Slideshow(QObject):
    """Where the show is (slide index, blanking) — the views follow it."""

    changed = Signal()
    finished = Signal()

    def __init__(self, pages: PdfPages, start: int = 0, parent=None,
                 auto: AutoPlay | None = None):
        super().__init__(parent)
        self.auto = auto
        self.auto_paused = False
        self._auto_started = time.monotonic()
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._auto_next)
        self.changed.connect(self._arm)
        self.pages = pages
        self.index = max(0, min(start, len(pages) - 1))
        self.blank: str | None = None        # None | "black" | "white"
        self.started = time.monotonic()
        self._paused_at: float | None = None
        self._typed = ""
        self._ending = False
        self.views: list[QWidget] = []

    # ---- navigation ----
    def go(self, index: int) -> None:
        index = max(0, min(index, len(self.pages) - 1))
        if index != self.index or self.blank:
            self.index = index
            self.blank = None
            self.changed.emit()

    def next(self) -> None:
        if self.blank:
            self.blank = None
            self.changed.emit()
        else:
            self.go(self.index + 1)

    def prev(self) -> None:
        self.go(self.index - 1)

    def toggle_blank(self, colour: str) -> None:
        self.blank = None if self.blank == colour else colour
        self.changed.emit()

    # ---- automatic advance ----
    def _arm(self) -> None:
        """(Re)start the countdown for the slide now showing."""
        if (self.auto is not None and not self.auto_paused
                and not self.blank and not self._ending):
            self._auto_timer.start(int(max(0.2, self.auto.seconds) * 1000))
        else:
            self._auto_timer.stop()

    def _auto_next(self) -> None:
        a = self.auto
        if a is None or self._ending:
            return
        if a.repeat == "for" and \
                time.monotonic() - self._auto_started >= a.minutes * 60:
            self.end()
            return
        if self.index < len(self.pages) - 1:
            self.go(self.index + 1)
        elif a.repeat in ("loop", "for"):
            if self.index == 0:          # a one-slide show: just re-arm
                self._arm()
            else:
                self.go(0)
        else:
            self.end()

    def toggle_auto(self) -> None:
        if self.auto is None:
            return
        self.auto_paused = not self.auto_paused
        self._arm()
        self.changed.emit()

    def auto_remaining(self) -> float | None:
        """Seconds until the next automatic advance (None when off)."""
        if self.auto is None or self.auto_paused or self.blank:
            return None
        return max(0.0, self._auto_timer.remainingTime() / 1000)

    def end(self) -> None:
        """Close every slideshow window (closing any one ends the show)."""
        if self._ending:
            return
        self._ending = True
        self._auto_timer.stop()
        views, self.views = list(self.views), []
        for v in views:
            v.close()
        self.finished.emit()

    # ---- timer ----
    def elapsed(self) -> float:
        now = self._paused_at if self._paused_at is not None \
            else time.monotonic()
        return max(0.0, now - self.started)

    def pause(self, on: bool) -> None:
        if on and self._paused_at is None:
            self._paused_at = time.monotonic()
        elif not on and self._paused_at is not None:
            self.started += time.monotonic() - self._paused_at
            self._paused_at = None

    @property
    def paused(self) -> bool:
        return self._paused_at is not None

    def reset_timer(self) -> None:
        self.started = time.monotonic()
        if self._paused_at is not None:
            self._paused_at = self.started

    # ---- keys shared by every view ----
    def handle_key(self, event) -> bool:
        k = event.key()
        text = event.text()
        if text.isdigit():
            self._typed += text
            return True
        if k in (Qt.Key_Return, Qt.Key_Enter) and self._typed:
            self.go(int(self._typed) - 1)
            self._typed = ""
            return True
        self._typed = ""
        if k in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Space, Qt.Key_PageDown,
                 Qt.Key_Return, Qt.Key_Enter, Qt.Key_N):
            self.next()
        elif k in (Qt.Key_Left, Qt.Key_Up, Qt.Key_Backspace, Qt.Key_PageUp,
                   Qt.Key_P):
            self.prev()
        elif k == Qt.Key_Home:
            self.go(0)
        elif k == Qt.Key_End:
            self.go(len(self.pages) - 1)
        elif k in (Qt.Key_B, Qt.Key_Period):
            self.toggle_blank("black")
        elif k in (Qt.Key_W, Qt.Key_Comma):
            self.toggle_blank("white")
        elif k == Qt.Key_S:
            self.toggle_auto()
        elif k == Qt.Key_Escape:
            self.end()
        else:
            return False
        return True


class SlideScreen(QWidget):
    """One full-screen slide: the current page (or, with offset=1, the
    next one), letterboxed on black."""

    def __init__(self, show: Slideshow, offset: int = 0, parent=None,
                 windowed: bool = False):
        super().__init__(parent, Qt.Window)
        self.show_ = show
        self.offset = offset
        self.windowed = windowed
        self.setWindowTitle("Slideshow")
        if not windowed:
            self.setCursor(Qt.BlankCursor)
        else:
            self.setMinimumSize(320, 180)
            show.changed.connect(self._title)
            self._title()
        self.setFocusPolicy(Qt.StrongFocus)
        show.changed.connect(self.update)

    def paintEvent(self, _event):
        p = QPainter(self)
        show = self.show_
        if show.blank and self.offset == 0:
            p.fillRect(self.rect(), QColor(show.blank))
            return
        p.fillRect(self.rect(), Qt.black)
        i = show.index + self.offset
        if not 0 <= i < len(show.pages):
            p.setPen(QColor("#888888"))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "End of slideshow" if self.offset == 0
                       else "— end —")
            return
        pm = show.pages.pixmap(i, self.size(), self.devicePixelRatioF())
        w = pm.width() / pm.devicePixelRatio()
        h = pm.height() / pm.devicePixelRatio()
        p.drawPixmap(int((self.width() - w) / 2),
                     int((self.height() - h) / 2), pm)

    def _title(self):
        s = self.show_
        self.setWindowTitle(f"Slideshow — slide {s.index + 1} of "
                            f"{len(s.pages)}  (F: full screen · Esc: end)")

    def keyPressEvent(self, event):
        if self.windowed and event.key() == Qt.Key_F:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            return
        if (self.windowed and event.key() == Qt.Key_Escape
                and self.isFullScreen()):
            self.showNormal()          # Esc leaves full screen first
            return
        if not self.show_.handle_key(event):
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.show_.prev()
        else:
            self.show_.next()

    def wheelEvent(self, event):
        if event.angleDelta().y() < 0:
            self.show_.next()
        elif event.angleDelta().y() > 0:
            self.show_.prev()

    def closeEvent(self, event):
        super().closeEvent(event)
        if self in self.show_.views:
            self.show_.end()


class _Preview(QWidget):
    """A slide picture inside the presenter console."""

    def __init__(self, show: Slideshow, offset: int, parent=None):
        super().__init__(parent)
        self.show_ = show
        self.offset = offset
        self.setMinimumSize(160, 90)
        show.changed.connect(self.update)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#202020"))
        i = self.show_.index + self.offset
        if not 0 <= i < len(self.show_.pages):
            p.setPen(QColor("#888888"))
            p.drawText(self.rect(), Qt.AlignCenter, "End of slideshow")
            return
        pm = self.show_.pages.pixmap(i, self.size(),
                                     self.devicePixelRatioF())
        w = pm.width() / pm.devicePixelRatio()
        h = pm.height() / pm.devicePixelRatio()
        x, y = (self.width() - w) / 2, (self.height() - h) / 2
        p.drawPixmap(int(x), int(y), pm)
        if self.offset == 0 and self.show_.blank:
            p.fillRect(QRectF(x, y, w, h), QColor(0, 0, 0, 170))
            p.setPen(QColor("#FFFFFF"))
            p.drawText(QRectF(x, y, w, h), Qt.AlignCenter,
                       f"Audience sees a {self.show_.blank} screen (press "
                       f"{'B' if self.show_.blank == 'black' else 'W'})")


class PresenterConsole(QWidget):
    """The speaker's screen: current slide, next slide, count, timers."""

    def __init__(self, show: Slideshow, parent=None):
        super().__init__(parent, Qt.Window)
        self.show_ = show
        self.setWindowTitle("Presenter view")
        self.setStyleSheet("PresenterConsole, QWidget#bg { background:"
                           " #111111; } QLabel { color: #EEEEEE; }"
                           " QPushButton { color: #EEEEEE; background:"
                           " #2A2A2A; border: 1px solid #444; padding: 6px"
                           " 14px; border-radius: 4px; }"
                           " QPushButton:hover { background: #3A3A3A; }")
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor("#111111"))
        self.setPalette(pal)
        self.setFocusPolicy(Qt.StrongFocus)
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(18)

        left = QVBoxLayout()
        self._now_label = QLabel()
        left.addWidget(self._now_label)
        left.addWidget(_Preview(show, 0), 1)
        nav = QHBoxLayout()
        for text, slot in (("◀  Previous", show.prev),
                           ("Next  ▶", show.next),
                           ("Black screen", lambda: show.toggle_blank(
                               "black")),
                           ("End show", show.end)):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(slot)
            nav.addWidget(b)
        nav.addStretch(1)
        left.addLayout(nav)
        root.addLayout(left, 3)

        right = QVBoxLayout()
        nxt = QLabel("Next")
        f = nxt.font()
        f.setPointSizeF(f.pointSizeF() + 2)
        nxt.setFont(f)
        right.addWidget(nxt)
        right.addWidget(_Preview(show, 1), 1)
        big = QFont()
        big.setPointSize(34)
        big.setBold(True)
        self._timer_label = QLabel()
        self._timer_label.setFont(big)
        right.addWidget(self._timer_label)
        row = QHBoxLayout()
        self._pause = QPushButton("Pause")
        self._pause.setFocusPolicy(Qt.NoFocus)
        self._pause.clicked.connect(self._toggle_pause)
        reset = QPushButton("Reset")
        reset.setFocusPolicy(Qt.NoFocus)
        reset.clicked.connect(lambda: (show.reset_timer(), self._tick()))
        row.addWidget(self._pause)
        row.addWidget(reset)
        row.addStretch(1)
        right.addLayout(row)
        self._clock = QLabel()
        right.addWidget(self._clock)
        self._auto_label = QLabel()
        self._auto_label.setStyleSheet("color:#F2C14E;")
        right.addWidget(self._auto_label)
        hint = QLabel("→ / Space next · ← back · number + Enter jump · "
                      "B / W blank · Esc end")
        hint.setStyleSheet("color:#888888;")
        hint.setWordWrap(True)
        right.addWidget(hint)
        root.addLayout(right, 2)

        show.changed.connect(self._refresh)
        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._tick)
        self._ticker.start(500)
        self._refresh()
        self._tick()

    def _toggle_pause(self):
        self.show_.pause(not self.show_.paused)
        self._pause.setText("Resume" if self.show_.paused else "Pause")
        self._tick()

    def _refresh(self):
        s = self.show_
        self._now_label.setText(
            f"<span style='font-size:15pt'>Slide <b>{s.index + 1}</b> of "
            f"{len(s.pages)}</span>")

    def _tick(self):
        t = int(self.show_.elapsed())
        self._timer_label.setText(
            f"{t // 3600:d}:{t // 60 % 60:02d}:{t % 60:02d}")
        self._clock.setText(time.strftime("Clock  %H:%M"))
        s = self.show_
        if s.auto is None:
            self._auto_label.setText("")
        elif s.auto_paused:
            self._auto_label.setText("Automatic: paused (S resumes)")
        else:
            left = s.auto_remaining()
            self._auto_label.setText(
                "Automatic: next slide in "
                f"{int(round(left)) if left is not None else '—'} s "
                "(S pauses)")

    def keyPressEvent(self, event):
        if not self.show_.handle_key(event):
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self._ticker.stop()
        super().closeEvent(event)
        if self in self.show_.views:
            self.show_.end()


# ------------------------------------------------------------------ launch
MODES = {
    "full": "Full screen",
    "window": "In a window",
    "presenter": "Presenter view",
    "next": "Current + next slide",
}


def _put_on(widget: QWidget, screen, full: bool = True) -> None:
    widget.show()
    handle = widget.windowHandle()
    if handle is not None and screen is not None:
        handle.setScreen(screen)
    if screen is not None:
        widget.setGeometry(screen.geometry() if full
                           else screen.availableGeometry())
    if full:
        widget.showFullScreen()
    else:
        widget.showMaximized()
    widget.raise_()
    widget.activateWindow()


def screens_for(window) -> tuple:
    """(this screen, the other screen or None)."""
    here = window.screen() or QGuiApplication.primaryScreen()
    others = [s for s in QGuiApplication.screens() if s is not here]
    return here, (others[0] if others else None)


def start(pages: PdfPages, mode: str, start_index: int, window,
          audience_screen=None, auto: AutoPlay | None = None) -> Slideshow:
    """Open the slideshow windows for *mode*; returns the controller.
    *auto* makes it advance by itself."""
    show = Slideshow(pages, start_index, window, auto=auto)
    here, other = screens_for(window)
    audience = audience_screen or other
    if mode == "presenter":
        console = PresenterConsole(show)
        slides = SlideScreen(show)
        show.views += [slides, console]
        if audience is not None and audience is not here:
            _put_on(slides, audience)
            _put_on(console, here, full=False)
        else:
            # One screen: rehearse — console maximized, slides windowed.
            _put_on(console, here, full=False)
            slides.resize(960, int(960 / pages.aspect()))
            slides.setCursor(Qt.ArrowCursor)
            slides.show()
        console.setFocus()
    elif mode == "next":
        current = SlideScreen(show, 0)
        following = SlideScreen(show, 1)
        show.views += [current, following]
        _put_on(current, audience or here)
        if other is not None:
            _put_on(following, here if audience is other else other)
        else:
            following.resize(640, int(640 / pages.aspect()))
            following.show()
        current.setFocus()
    elif mode == "window":
        # A normal, resizable window (e.g. beside other work, or shared
        # in a video call); F switches it to full screen and back.
        slides = SlideScreen(show, windowed=True)
        show.views.append(slides)
        screen = audience_screen or here
        avail = screen.availableGeometry() if screen else None
        w = int(min(1280, (avail.width() if avail else 1280) * 0.7))
        slides.resize(w, int(w / pages.aspect()))
        if avail is not None:
            slides.move(avail.center().x() - slides.width() // 2,
                        avail.center().y() - slides.height() // 2)
        slides.show()
        slides.raise_()
        slides.activateWindow()
        slides.setFocus()
    else:
        slides = SlideScreen(show)
        show.views.append(slides)
        _put_on(slides, here if audience_screen is None else audience)
        slides.setFocus()
    show._arm()
    return show


class AutoSlideshowDialog(QDialog):
    """Slideshow ▸ Automatic slideshow… — how long each slide shows and
    how the show repeats."""

    def __init__(self, auto: AutoPlay, mode: str = "full",
                 from_current: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Automatic slideshow")
        form = QFormLayout(self)
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(1, 3600)
        self.seconds.setDecimals(0)
        self.seconds.setSuffix(" s")
        self.seconds.setValue(auto.seconds)
        form.addRow("Each slide shows for", self.seconds)
        self._repeat = QButtonGroup(self)
        box = QVBoxLayout()
        self._repeat_buttons = {}
        for key, text in REPEATS.items():
            rb = QRadioButton(text)
            rb.setChecked(key == auto.repeat)
            self._repeat.addButton(rb)
            self._repeat_buttons[key] = rb
            if key == "for":
                row = QHBoxLayout()
                row.addWidget(rb)
                self.minutes = QDoubleSpinBox()
                self.minutes.setRange(1, 24 * 60)
                self.minutes.setDecimals(0)
                self.minutes.setSuffix(" min")
                self.minutes.setValue(auto.minutes)
                row.addWidget(self.minutes)
                row.addStretch(1)
                box.addLayout(row)
            else:
                box.addWidget(rb)
        form.addRow("Repeat", box)
        self.mode = QComboBox()
        self.mode.addItem("Full screen", "full")
        self.mode.addItem("In a window", "window")
        self.mode.addItem("Presenter view", "presenter")
        self.mode.setCurrentIndex(max(0, self.mode.findData(mode)))
        form.addRow("Show as", self.mode)
        self.from_current = QCheckBox("Start from the current slide")
        self.from_current.setChecked(from_current)
        form.addRow("", self.from_current)
        hint = QLabel("During the show: S pauses / resumes, the arrow "
                      "keys still move by hand, Esc ends.")
        hint.setStyleSheet("color:#666;")
        hint.setWordWrap(True)
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        go = buttons.addButton("Start", QDialogButtonBox.AcceptRole)
        go.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def result_auto(self) -> AutoPlay:
        repeat = next(k for k, rb in self._repeat_buttons.items()
                      if rb.isChecked())
        return AutoPlay(seconds=self.seconds.value(), repeat=repeat,
                        minutes=self.minutes.value())
