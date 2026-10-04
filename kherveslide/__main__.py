"""Entry point: ``python -m kherveslide`` opens KherveSlide."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Render the equation-editor previews off-screen (no display needed).
os.environ.setdefault("MPLBACKEND", "Agg")


def _silence_fontconfig() -> None:
    """xdvipdfmx (inside tectonic) prints "Fontconfig error: Cannot load
    default config file" on Windows when no fontconfig config exists.
    Point it at a tiny valid config so it stops complaining. Harmless if
    fontconfig isn't used."""
    if os.environ.get("FONTCONFIG_FILE"):
        return
    cfg = Path(tempfile.gettempdir()) / "kherveslide_fonts.conf"
    try:
        if not cfg.exists():
            cfg.write_text("<?xml version=\"1.0\"?>\n<fontconfig></fontconfig>\n",
                           encoding="utf-8")
        os.environ["FONTCONFIG_FILE"] = str(cfg)
    except OSError:
        pass



def _seed_tectonic_cache() -> None:
    """Copy the tectonic packages shipped in the installer into the user's
    tectonic cache, so a brand-new install compiles at once and offline.

    Without it the first compile found an empty cache, tectonic could not
    even build its LaTeX format, and no slide compiled until something
    filled the cache from the internet. Only missing files are copied, so
    it is quick after the first launch and never overwrites newer ones."""
    if not getattr(sys, "frozen", False):
        return
    import shutil
    bundled = Path(sys._MEIPASS) / "kherveslide" / "tectonic_cache"
    if not bundled.is_dir():
        return
    try:
        from .compiler import (_find_tectonic, default_tectonic_cache_dir,
                               query_tectonic_cache_dir)
        # Ask the bundled binary itself: the path differs per OS (and
        # honours TECTONIC_CACHE_DIR), and a mismatch leaves it empty.
        tec = _find_tectonic()
        dest = (query_tectonic_cache_dir(tec) if tec else None) \
            or default_tectonic_cache_dir()
        # tectonic reports <cache>/bundles; the shipped copy is the whole
        # cache (bundles/ + formats/), so it goes one level up.
        if dest.name == "bundles":
            dest = dest.parent
        dest.mkdir(parents=True, exist_ok=True)
        for src in bundled.rglob("*"):
            dst = dest / src.relative_to(bundled)
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            elif not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    except Exception:
        pass     # a compile can still fetch what it needs online

_silence_fontconfig()

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from . import icons, latex_fonts, themes
from .window import SlideWindow


def _center_on_main_screen(win) -> None:
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    geo = screen.availableGeometry()
    win.move(geo.center().x() - win.width() // 2,
             geo.center().y() - win.height() // 2)


def main() -> int:
    if "--mcp-server" in sys.argv:
        # A frozen build re-executes itself as the MCP stdio server (no Qt).
        from .mcp_server import main as mcp_main
        return mcp_main([a for a in sys.argv[1:] if a != "--mcp-server"])
    app = QApplication(sys.argv)
    app.setApplicationName("KherveSlide")
    app.setWindowIcon(icons.app_icon())
    settings = QSettings("kherveDOC", "KherveSlide")
    theme_name = settings.value("theme_name", themes.DEFAULT_THEME)
    theme = themes.apply_theme(app, theme_name)
    dark = themes.is_dark(theme_name)
    icons.set_dark(dark)

    from .splash import Splash
    splash = Splash()
    splash.show()
    splash.step("Preparing the LaTeX packages")
    _seed_tectonic_cache()
    splash.step("Loading the designer")
    # beamer's own Latin Modern faces for the canvas (from tectonic's cache).
    latex_fonts.ensure_loaded()
    splash.step("Building the window")
    win = SlideWindow(dark=dark, theme=theme)
    # Before the event loop runs, so "WYSIWYG only" never starts a compile.
    from .welcome import LAYOUT_DEFAULT
    win.apply_layout_mode(settings.value("layout_mode", LAYOUT_DEFAULT))
    _center_on_main_screen(win)
    splash.step("Opening the presentation")
    win.show()
    splash.step("Ready")
    splash.finish(win)

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    opened = False
    if args and Path(args[0]).exists():
        win.open_path(args[0])
        opened = True
    if not opened and settings.value("show_welcome", True, type=bool):
        QTimer.singleShot(0, win.show_welcome)
    if win.updater is not None:
        win.updater.schedule()
    win.start_mcp_if_enabled()
    app.aboutToQuit.connect(_release_clipboard)
    return app.exec()


def _release_clipboard():
    """Hand our clipboard contents back to Qt before shutdown. A QMimeData
    we set from Python is otherwise destroyed after QApplication, during
    interpreter exit, and segfaults ("Python quit unexpectedly"). Plain
    text survives for other apps; slide/picture data is only useful
    inside KherveSlide anyway."""
    cb = QApplication.clipboard()
    try:
        if cb.ownsClipboard():
            text = cb.text()
            cb.clear()
            if text:
                cb.setText(text)
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
