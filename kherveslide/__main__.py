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


_silence_fontconfig()

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from . import icons, themes
from .window import SlideWindow


def _center_on_main_screen(win) -> None:
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    geo = screen.availableGeometry()
    win.move(geo.center().x() - win.width() // 2,
             geo.center().y() - win.height() // 2)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("KherveSlide")
    app.setWindowIcon(icons.app_icon())
    settings = QSettings("kherveDOC", "KherveSlide")
    theme_name = settings.value("theme_name", "Light")
    theme = themes.apply_theme(app, theme_name)
    dark = themes.is_dark(theme_name)
    icons.set_dark(dark)

    win = SlideWindow(dark=dark, theme=theme)
    _center_on_main_screen(win)
    win.show()

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and Path(args[0]).exists():
        win.open_path(args[0])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
