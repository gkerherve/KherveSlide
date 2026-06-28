"""Entry point: ``python -m kherveslide`` opens KherveSlide."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from . import icons, themes
from .model import deck_from_json
from .window import SlideWindow


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
    win.show()

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and Path(args[0]).exists():
        try:
            win.deck = deck_from_json(Path(args[0]).read_text(encoding="utf-8"))
            win.path = Path(args[0])
            win.current = 0
            win._reload_all()
        except Exception:
            pass
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
