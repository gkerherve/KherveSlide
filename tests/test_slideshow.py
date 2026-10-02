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


# --- the user guide (Help > User Guide, F1) ---

def test_user_guide_loads_with_its_contents(qapp):
    from kherveslide.help import HelpDialog, parse_headings, user_guide_path
    md = user_guide_path().read_text(encoding="utf-8")
    heads = [t for _lvl, t, _o in parse_headings(md)]
    for chapter in ("Getting started", "Ways of working", "Themes",
                    "Slideshow", "Keyboard shortcuts"):
        assert chapter in heads
    dlg = HelpDialog()
    assert dlg.toc.count() == len(heads)
    dlg.toc_filter.setText("theme")
    visible = [dlg.toc.item(i).text() for i in range(dlg.toc.count())
               if not dlg.toc.item(i).isHidden()]
    assert visible and all("theme" in v.lower() for v in visible)
    dlg.close()


def test_user_guide_matches_the_app(qapp, monkeypatch):
    """The guide names every top-level menu and only shortcuts the
    window really has, so it can't silently drift from the app."""
    import re
    from kherveslide.help import user_guide_path
    from kherveslide.window import SlideWindow
    for name in ("_start_compile", "_start_backdrop",
                 "_maybe_autodownload_packages"):
        monkeypatch.setattr(SlideWindow, name, lambda self, *a: None)
    md = user_guide_path().read_text(encoding="utf-8")
    w = SlideWindow()
    menus = [a.text().replace("&", "") for a in w.menuBar().actions()]
    for m in menus:
        assert f"**{m}" in md or f"{m} →" in md or f"{m} menu" in md, m
    keys = set()
    for a in w.findChildren(type(w.act_undo)):
        for seq in a.shortcuts():
            keys.add(seq.toString())
    for shortcut in re.findall(r"`((?:Ctrl|Alt|Shift|F\d)[^`]*)`", md):
        if any(s in shortcut for s in ("↑", "↓")) or not (
                "+" in shortcut or re.fullmatch(r"F\d+", shortcut)):
            continue
        assert shortcut in keys or shortcut in ("Ctrl+I", "Shift+Tab"), \
            shortcut
    w.close()


# --- automatic slideshow ---

def test_auto_show_once_ends_after_the_last_slide(qapp):
    auto = slideshow.AutoPlay(seconds=5, repeat="once")
    show = slideshow.Slideshow(slideshow.PdfPages(_pdf(3)), auto=auto)
    ended = []
    show.finished.connect(lambda: ended.append(True))
    show._arm()
    assert show.auto_remaining() is not None
    show._auto_next(); show._auto_next()
    assert show.index == 2 and not ended
    show._auto_next()
    assert ended == [True]


def test_auto_show_loops_and_pauses(qapp):
    show = slideshow.Slideshow(slideshow.PdfPages(_pdf(2)),
                               auto=slideshow.AutoPlay(1, "loop"))
    show._arm()
    show._auto_next()
    show._auto_next()
    assert show.index == 0                     # wrapped round
    show.handle_key(_key(Qt.Key_S, "s"))
    assert show.auto_paused and show.auto_remaining() is None
    show.handle_key(_key(Qt.Key_S, "s"))
    assert not show.auto_paused and show.auto_remaining() is not None
    show.toggle_blank("black")                 # a blank screen holds it
    assert show.auto_remaining() is None
    show.end()


def test_auto_show_for_a_set_time(qapp, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(slideshow.time, "monotonic", lambda: clock[0])
    show = slideshow.Slideshow(slideshow.PdfPages(_pdf(2)),
                               auto=slideshow.AutoPlay(10, "for", 1))
    ended = []
    show.finished.connect(lambda: ended.append(True))
    show._auto_next(); show._auto_next()
    assert show.index == 0 and not ended       # still looping
    clock[0] = 61.0
    show._auto_next()
    assert ended == [True]


def test_auto_show_really_advances_on_its_timer(qapp):
    import time
    show = slideshow.Slideshow(slideshow.PdfPages(_pdf(3)),
                               auto=slideshow.AutoPlay(0.2, "once"))
    show._arm()
    end = time.monotonic() + 3
    while show.index < 1 and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.02)
    assert show.index >= 1
    show.end()


def test_auto_dialog_returns_the_choices(qapp):
    dlg = slideshow.AutoSlideshowDialog(
        slideshow.AutoPlay(7, "for", 12), "presenter", True)
    a = dlg.result_auto()
    assert (a.seconds, a.repeat, a.minutes) == (7, "for", 12)
    assert dlg.mode.currentData() == "presenter"
    assert dlg.from_current.isChecked()


# --- flowchart builder in the window ---

def test_flowchart_inserted_as_picture_and_reopened(qapp, tmp_path,
                                                    monkeypatch):
    from kherveslide import flowchart as F
    from kherveslide import flowchart_builder as FB
    from kherveslide.window import SlideWindow
    from kherveslide.model import SlidePicture
    for name in ("_start_compile", "_start_backdrop",
                 "_maybe_autodownload_packages"):
        monkeypatch.setattr(SlideWindow, name, lambda self, *a: None)
    monkeypatch.setattr(SlideWindow, "_figures_dir", lambda self: tmp_path)
    seen = {}

    def fake_exec(self):
        seen["chart"] = self.fc
        self.result_chart = self.fc
        self.result_pdf = _pdf(1)
        self.result_tikz = F.to_tikz(self.fc)
        return True
    monkeypatch.setattr(FB.FlowchartBuilderDialog, "exec", fake_exec)
    monkeypatch.setattr(FB.FlowchartBuilderDialog, "_schedule",
                        lambda self: None)
    w = SlideWindow()
    n = len(w.slide.objects)
    w._add_flowchart()
    pic = w.slide.objects[-1]
    assert len(w.slide.objects) == n + 1 and isinstance(pic, SlidePicture)
    pdf = tmp_path / "flowchart_001.pdf"
    assert pic.path == str(pdf) and pdf.exists()
    assert (tmp_path / "flowchart_001.flow.json").exists()
    assert "\\begin{tikzpicture}" in (tmp_path / "flowchart_001.tikz"
                                      ).read_text()
    # double-click reopens the builder on the saved chart
    item = w._items[-1]
    seen.clear()
    w._on_double_click(item)
    assert seen["chart"].to_json() == F.template_simple().to_json()
    assert len(w.slide.objects) == n + 1        # replaced, not added
    w.close()


def test_flowchart_builder_arrow_and_line_tools(qapp, monkeypatch):
    from kherveslide import flowchart as F
    from kherveslide import flowchart_builder as FB
    monkeypatch.setattr(FB.FlowchartBuilderDialog, "_schedule",
                        lambda self: None)
    fc = F.Flowchart()
    a = fc.add("process", "A")
    b = fc.add("process", "B")
    dlg = FB.FlowchartBuilderDialog(chart=fc)
    items = {i.node.id: i for i in dlg.scene.items()
             if isinstance(i, FB.NodeItem)}
    dlg._tool_buttons["none"].setChecked(True)      # the Line tool
    assert dlg.view.connect_mode
    dlg._tool_click(items[a.id])
    dlg._tool_click(items[b.id])
    assert [(e.src, e.dst, e.head) for e in dlg.fc.edges] == \
        [(a.id, b.id, "none")]
    dlg._tool_click(None)                           # empty space: stop
    assert not dlg.view.connect_mode
    dlg._tool_buttons["curve"].setChecked(True)     # the Curve tool
    assert not dlg._tool_buttons["none"].isChecked()
    items = {i.node.id: i for i in dlg.scene.items()     # rebuilt
             if isinstance(i, FB.NodeItem)}
    dlg._tool_click(items[b.id])
    dlg._tool_click(items[a.id])
    curve = dlg.fc.edges[-1]
    assert (curve.src, curve.route, curve.head) == (b.id, "curve", "end")
    item = next(i for i in dlg.scene.items()
                if isinstance(i, FB.EdgeItem) and i.edge is curve)
    assert len(item._pts) > 10                      # drawn as a curve
    dlg._tool_buttons["curve"].setChecked(False)
    dlg.fc.edges.remove(curve)
    dlg._commit()
    # choose the sides and the heads from the edge panel
    edge = next(i for i in dlg.scene.items() if isinstance(i, FB.EdgeItem))
    dlg.scene.clearSelection()
    edge.setSelected(True)
    assert dlg._selected_edge is edge
    dlg._set_edge(head="both", src_side="east", dst_side="west")
    e = dlg.fc.edges[0]
    assert (e.head, e.src_side, e.dst_side) == ("both", "east", "west")
    edge = next(i for i in dlg.scene.items() if isinstance(i, FB.EdgeItem))
    assert len(edge._pts) >= 3                      # stub + elbow
    dlg._reverse_edge()
    dlg.close()


def test_bottom_bar_views_overview_and_master(qapp, monkeypatch):
    from kherveslide.window import SlideWindow
    from kherveslide.model import SlideText
    from kherveslide.view_bar import VIEW_MASTER, VIEW_NORMAL, VIEW_OVERVIEW
    from kherveslide.welcome import LAYOUT_SIDE, LAYOUT_VISUAL
    for name in ("_start_compile", "_start_backdrop",
                 "_maybe_autodownload_packages"):
        monkeypatch.setattr(SlideWindow, name, lambda self, *a: None)
    w = SlideWindow()
    w.apply_layout_mode(LAYOUT_SIDE)
    n = len(w.deck.slides)
    assert w.view_bar.counter.text() == f"Slide 1 of {n}"
    # Overview: a tab in the right frame, one mini page per slide
    w.view_bar.views[VIEW_OVERVIEW].click()
    assert w.right_tabs.currentWidget() is w.overview
    w.overview._rebuild()
    assert w.overview.grid.count() == n
    w.overview.slideChosen.emit(1)
    assert w.current == 1 and w.view_bar.counter.text() == f"Slide 2 of {n}"
    w.overview.slideOpened.emit(0)              # double-click: edit it
    assert w.current == 0 and w._view_mode == VIEW_NORMAL
    assert w.right_tabs.currentWidget() is w.pdf_view
    # Visual only: the overview takes the slide's place
    w.apply_layout_mode(LAYOUT_VISUAL)
    w.set_view_mode(VIEW_OVERVIEW)
    assert w._right_stack.currentWidget() is w._overview_center
    w.set_view_mode(VIEW_NORMAL)
    assert w._right_stack.currentWidget() is w._canvas_box
    # Master: the canvas edits deck.master, undoably
    w.set_view_mode(VIEW_MASTER)
    assert w.slide is w.deck.master and w.nav.count() == 1
    assert w.view_bar.counter.text() == "Master"
    assert not w.f_frame_title.isEnabled()
    w._capture_state()
    w.slide.objects.append(SlideText(text="LOGO"))
    w._reload_scene()
    w._touch_current()
    w._capture_state()
    assert "LOGO" in w.latex_view.toPlainText() \
        if hasattr(w.latex_view, "toPlainText") else True
    assert [o.text for o in w.deck.master.objects][-1] == "LOGO"
    w._undo()
    assert not any(getattr(o, "text", "") == "LOGO"
                   for o in w.deck.master.objects)
    w.set_view_mode(VIEW_NORMAL)
    assert w.slide is w.deck.slides[w.current]
    assert w.nav.count() == n and w.f_frame_title.isEnabled()
    w.close()


def test_windowed_show_and_its_full_screen_toggle(qapp):
    from PySide6.QtWidgets import QWidget
    host = QWidget()
    show = slideshow.start(slideshow.PdfPages(_pdf(3)), "window", 0, host)
    view = show.views[0]
    assert view.windowed and not view.isFullScreen()
    assert "slide 1 of 3" in view.windowTitle()
    show.next()
    assert "slide 2 of 3" in view.windowTitle()
    view.keyPressEvent(_key(Qt.Key_F, "f"))       # F: full screen…
    view.keyPressEvent(_key(Qt.Key_F, "f"))       # …and back
    show.end()


def test_windowed_automatic_show(qapp):
    from PySide6.QtWidgets import QWidget
    host = QWidget()            # the parent must outlive the show
    show = slideshow.start(slideshow.PdfPages(_pdf(2)), "window", 0,
                           host, auto=slideshow.AutoPlay(5, "loop"))
    assert show.auto_remaining() is not None
    show._auto_next(); show._auto_next()
    assert show.index == 0                       # loops in the window too
    show.end()
    dlg = slideshow.AutoSlideshowDialog(slideshow.AutoPlay(), "window")
    assert dlg.mode.currentData() == "window"


def test_window_show_has_player_bar_and_goes_automatic(qapp):
    from PySide6.QtWidgets import QWidget
    host = QWidget()
    show = slideshow.start(slideshow.PdfPages(_pdf(3)), "window", 0, host)
    screen = show.views[0]
    bar = screen.bar
    assert bar is not None and show.keep_open
    assert not show.auto_running                 # started by hand
    # The slide is drawn above the bar, not under it.
    assert screen._slide_rect().height() == screen.height() - bar.HEIGHT
    bar.play.click()                             # Play → automatic
    assert show.auto_running and show.auto.repeat == "loop"
    assert show.auto_remaining() is not None
    bar.seconds.setValue(3)                      # change the time per slide
    assert show.auto.seconds == 3
    show.toggle_auto()                           # S pauses
    assert not show.auto_running
    show.end()


def test_window_show_once_stops_at_last_slide_instead_of_closing(qapp):
    from PySide6.QtWidgets import QWidget
    host = QWidget()
    auto = slideshow.AutoPlay(seconds=1, repeat="once")
    show = slideshow.start(slideshow.PdfPages(_pdf(2)), "window", 1, host,
                           auto=auto)
    ended = []
    show.finished.connect(lambda: ended.append(True))
    assert show.auto_running
    show._auto_next()                            # timer fires on the last
    assert not ended and not show.auto_running and show.index == 1
    show.toggle_auto()                           # Play again: resumes
    assert show.auto_running
    show.end()
    assert ended


def test_full_screen_manual_show_ignores_s(qapp):
    show = slideshow.Slideshow(slideshow.PdfPages(_pdf(2)))
    show.toggle_auto()                           # no defaults → no-op
    assert show.auto is None
