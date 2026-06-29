"""Entry point: ``python -m kherveslide`` opens KherveSlide."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Render the equation-editor previews off-screen (no display needed).
os.environ.setdefault("MPLBACKEND", "Agg")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from . import icons, themes
from .model import deck_from_json
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
        try:
            win.deck = deck_from_json(Path(args[0]).read_text(encoding="utf-8"))
            win.path = Path(args[0])
            win.current = 0
            win._reload_all()
            win._reset_history()
        except Exception:
            pass
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
