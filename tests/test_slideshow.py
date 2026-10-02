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


# --- drag & drop a presentation onto the window (kept with the other
# window-level tests that build a real SlideWindow) ---

def _drop(qapp, target, path):
    from PySide6.QtCore import QMimeData, QPointF, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    enter = QDragEnterEvent(target.rect().center(), Qt.CopyAction, mime,
                            Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(target, enter)
    drop = QDropEvent(QPointF(target.rect().center()), Qt.CopyAction, mime,
                      Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(target, drop)
    for _ in range(5):
        qapp.processEvents()
    return enter.isAccepted(), drop.isAccepted()


def test_dropping_a_kslide_anywhere_opens_it(qapp, tmp_path, monkeypatch):
    from kherveslide.model import Deck, Slide, deck_to_json
    from kherveslide.window import SlideWindow
    for name in ("_start_compile", "_start_backdrop",
                 "_maybe_autodownload_packages", "_add_recent"):
        monkeypatch.setattr(SlideWindow, name, lambda self, *a: None)
    f = tmp_path / "dropped.kslide"
    f.write_text(deck_to_json(Deck(title="Dropped", slides=[Slide(), Slide(),
                                                            Slide()])))
    w = SlideWindow()
    w.show()
    # onto the LaTeX editor — a text widget that would otherwise paste
    # the path — and onto the canvas
    for target in (w.latex_view, w.view.viewport()):
        w._new_deck()
        assert _drop(qapp, target, f) == (True, True)
        assert w.deck.title == "Dropped" and len(w.deck.slides) == 3
        assert w.path == f
    # an image is not a presentation: left to the canvas as before
    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG")
    assert SlideWindow.dropped_presentation(None) is None
    from PySide6.QtCore import QMimeData, QUrl
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(img))])
    assert SlideWindow.dropped_presentation(m) is None
    w.close()


# --- the start page (Welcome page inside the window) ---

def test_start_page_shows_in_window_and_leaves_on_a_choice(qapp, tmp_path,
                                                           monkeypatch):
    from kherveslide.window import SlideWindow
    for name in ("_start_compile", "_start_backdrop",
                 "_maybe_autodownload_packages", "_fill_start_cards"):
        monkeypatch.setattr(SlideWindow, name, lambda self, *a: None)
    monkeypatch.setattr(SlideWindow, "examples_dir",
                        staticmethod(lambda: tmp_path))
    w = SlideWindow()
    w.show()
    w.show_welcome()
    assert w.start_page_shown()
    assert w._nav_stack.currentWidget() is w._recent_panel
    assert w._nav_title.text() == "Recent"
    # Continue (or Esc) goes back to the slides
    w._start_page.continueRequested.emit()
    assert not w.start_page_shown() and w._nav_title.text() == "Slides"
    # choosing an example opens it and leaves the start page
    w.show_welcome()
    w._start_page.exampleChosen.emit("Maths seminar")
    assert not w.start_page_shown()
    assert w.deck.title == "The Gaussian integral"
    # any other way of opening something also leaves it
    w.show_welcome()
    w._new_deck()
    assert not w.start_page_shown()
    w.close()


def test_thumbnails_render_at_high_resolution(qapp):
    from kherveslide import templates
    from kherveslide.canvas import render_thumbnail, thumbnail_dpr
    deck = templates.instantiate_builtin("Title + content")
    pm = render_thumbnail(deck.slides[0], deck, 200, dpr=2.0)
    assert pm.devicePixelRatio() == 2.0 and pm.width() == 400
    assert pm.deviceIndependentSize().width() == 200
    assert thumbnail_dpr() >= 2.0
