"""Slideshow: presenting the compiled PDF full screen."""
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KHERVESLIDE_NO_UPDATE", "1")

from PySide6.QtCore import QEvent, QSize, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kherveslide import slideshow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _pdf(n=3) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    for i in range(n):
        page = doc.new_page(width=453.5, height=255.1)
        page.insert_text((40, 120), f"Slide {i + 1}", fontsize=40)
    return doc.tobytes()


def _key(k, text=""):
    return QKeyEvent(QEvent.KeyPress, k, Qt.NoModifier, text)


def test_pages_render_to_fit(qapp):
    pages = slideshow.PdfPages(_pdf())
    assert len(pages) == 3 and abs(pages.aspect() - 16 / 9) < 0.01
    pm = pages.pixmap(0, QSize(800, 800))
    assert pm.width() == 800 and abs(pm.height() - 450) <= 1   # fits


def test_navigation_blanking_and_jumps(qapp):
    show = slideshow.Slideshow(slideshow.PdfPages(_pdf(5)), start=1)
    seen = []
    show.changed.connect(lambda: seen.append(show.index))
    show.next(); show.next()
    assert show.index == 3
    show.go(99)
    assert show.index == 4            # clamped to the last page
    show.prev()
    assert show.index == 3
    show.handle_key(_key(Qt.Key_B, "b"))
    assert show.blank == "black"
    show.next()                       # leaving a blank screen
    assert show.blank is None and show.index == 3
    for ch, k in (("2", Qt.Key_2),):
        show.handle_key(_key(k, ch))
    show.handle_key(_key(Qt.Key_Return))
    assert show.index == 1            # typed "2" + Enter = slide 2
    show.handle_key(_key(Qt.Key_End))
    assert show.index == 4
    show.handle_key(_key(Qt.Key_Home))
    assert show.index == 0 and seen


def test_timer_pauses(qapp, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(slideshow.time, "monotonic", lambda: clock[0])
    show = slideshow.Slideshow(slideshow.PdfPages(_pdf(1)))
    clock[0] = 160.0
    assert show.elapsed() == 60.0
    show.pause(True)
    clock[0] = 500.0
    assert show.elapsed() == 60.0 and show.paused
    show.pause(False)
    clock[0] = 510.0
    assert show.elapsed() == 70.0
    show.reset_timer()
    assert show.elapsed() == 0.0


@pytest.mark.parametrize("mode,views", [("full", 1), ("presenter", 2),
                                        ("next", 2)])
def test_modes_open_and_escape_closes_all(qapp, mode, views):
    from PySide6.QtWidgets import QWidget
    host = QWidget()
    show = slideshow.start(slideshow.PdfPages(_pdf()), mode, 1, host)
    assert len(show.views) == views and show.index == 1
    ended = []
    show.finished.connect(lambda: ended.append(True))
    show.handle_key(_key(Qt.Key_Escape))
    assert ended == [True] and not show.views
    qapp.processEvents()


def test_window_presents_the_compiled_pdf(qapp, tmp_path, monkeypatch):
    from kherveslide.window import SlideWindow
    for name in ("_start_compile", "_start_backdrop",
                 "_maybe_autodownload_packages"):
        monkeypatch.setattr(SlideWindow, name, lambda self, *a: None)
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(_pdf(2))
    monkeypatch.setattr(SlideWindow, "_slideshow_pdf", lambda self: pdf)
    w = SlideWindow()
    w.current = 1
    w.start_slideshow("full", from_current=True)
    show = w._slideshow
    assert show is not None and show.index == 1
    show.prev()
    show.end()
    assert w._slideshow is None and w.current == 0   # lands where it ended
    w.close()
