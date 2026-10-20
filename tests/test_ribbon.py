"""The PowerPoint ribbon replaces the toolbars, including the vertical
Insert bar, and can be swapped with the classic layout at run time."""
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


def _window(monkeypatch):
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    for name in ("_start_compile", "_start_backdrop",
                 "_maybe_autodownload_packages"):
        monkeypatch.setattr(window.SlideWindow, name, lambda self, *a: None)
    return window.SlideWindow()


def test_ribbon_has_powerpoint_tabs(monkeypatch):
    w = _window(monkeypatch)
    w._apply_toolbar_style("powerpoint")
    tabs = [w._ribbon.tabText(i) for i in range(w._ribbon.count())]
    assert tabs[:5] == ["Home", "Insert", "Design", "Slide Show", "Review"]
    assert "View" in tabs and "Help" in tabs
    assert not any(b.isVisibleTo(w) for b in w._classic_bars)
    assert w.act_style_ribbon.isChecked()
    w.close()


def test_swapping_styles_keeps_shared_widgets_alive(monkeypatch):
    w = _window(monkeypatch)
    w.show()
    w._apply_toolbar_style("classic")
    QApplication.processEvents()
    assert w._ribbon is None
    assert all(b.isVisible() for b in w._classic_bars)
    w._apply_toolbar_style("powerpoint")
    QApplication.processEvents()
    assert w.fmt_font.isVisible() and w.type_combo.isVisible()
    w._apply_toolbar_style("classic")
    QApplication.processEvents()
    assert w.fmt_font.isVisible()
    w.close()


def test_contextual_picture_tab(monkeypatch):
    w = _window(monkeypatch)
    w._apply_toolbar_style("powerpoint")
    rb = w._ribbon
    names = {rb.tabText(i): i for i in range(rb.count())}
    assert not rb.isTabVisible(names["Picture Format"])
    rb.show_context("picture")
    assert rb.isTabVisible(names["Picture Format"])
    assert not rb.isTabVisible(names["Table Layout"])
    w.close()
