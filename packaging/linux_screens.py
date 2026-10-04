"""Screenshots of KherveSlide on a Linux desktop (CI: Xvfb + xfwm4).

    python packaging/linux_screens.py OUTDIR "Example name:slide" ...

Opens each example, the Visual window on the left and the PDF in its own
window on the right, waits for the compile, then grabs the whole X screen
(window frames included) with ImageMagick's ``import``.
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("MPLBACKEND", "Agg")
from PySide6.QtCore import QTimer                      # noqa: E402
from PySide6.QtWidgets import QApplication             # noqa: E402

OUT = Path(sys.argv[1])
JOBS = [(n, int(s)) for n, s in (a.rsplit(":", 1) for a in sys.argv[2:])]
app = QApplication(sys.argv)
app.setApplicationName("KherveSlide")
from kherveslide import icons, latex_fonts, themes     # noqa: E402
from kherveslide.welcome import LAYOUT_WINDOW          # noqa: E402
from kherveslide.window import SlideWindow             # noqa: E402

theme = themes.apply_theme(app, themes.DEFAULT_THEME)
icons.set_dark(False)
latex_fonts.ensure_loaded()
win = SlideWindow(dark=False, theme=theme)
win.setGeometry(10, 30, 1260, 940)
win.show()
win.apply_layout_mode(LAYOUT_WINDOW)
win._pdf_window.setGeometry(1300, 30, 840, 940)
state = {"i": 0}


def nxt():
    if state["i"] >= len(JOBS):
        os._exit(0)
    name, slide = JOBS[state["i"]]
    win.open_example(name, ask=False)
    QTimer.singleShot(1500, lambda: pick(slide))


def pick(slide):
    win.current = slide
    win._reload_all()
    QTimer.singleShot(90000, goto)


def goto():
    win.pdf_view.go_to_page(win._pdf_page_of(win.current))
    QTimer.singleShot(3000, shoot)


def shoot():
    name, slide = JOBS[state["i"]]
    out = OUT / f"linux-{name.split()[0].lower()}-{slide}.png"
    subprocess.run(["import", "-window", "root", str(out)], check=True)
    print("saved", out, flush=True)
    state["i"] += 1
    nxt()


QTimer.singleShot(2000, nxt)
app.exec()
