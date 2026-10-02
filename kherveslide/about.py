"""Help ▸ About KherveSlide: the app, its author and khervetools.com.

Laid out like KherveTeX's About — the big app icon beside the name and
version, then the author, the Kherve tools family on khervetools.com, and
what KherveSlide is built with.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QTextBrowser,
    QVBoxLayout,
)

from . import icons

KHERVETOOLS_URL = "https://khervetools.com"
GITHUB_URL = "https://github.com/gkerherve/KherveSlide"

#: The family, as listed on khervetools.com.
KHERVE_TOOLS = (
    ("KherveFitting", "peak fitting for XPS spectra"),
    ("KhervePlot", "Origin-style plotting and data analysis"),
    ("KherveTeX", "Word-like writing that produces LaTeX"),
    ("KherveSlide", "PowerPoint-like slides that produce beamer LaTeX"),
    ("KherveCAD", "easy CAD with OpenSCAD as the engine"),
    ("KherveSheet", "spreadsheets"),
    ("KherveBook", "notebooks"),
    ("KhervePDF", "reading and annotating PDFs"),
    ("KhervePaint", "drawing and scientific sketches"),
)


def _ver(mod: str) -> str:
    try:
        return str(__import__(mod).__version__)
    except Exception:
        return "—"


def about_html(version: str) -> str:
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    tools = "".join(
        f"<li><b>{name}</b> — {what}</li>" for name, what in KHERVE_TOOLS)
    return (
        "<h3>About the author</h3>"
        "<p><b>Gwilherm Kerherv&eacute;</b> &nbsp;—&nbsp; Research "
        "Associate, Department of Materials, "
        "<a href='https://www.imperial.ac.uk/materials/'>Imperial College "
        "London</a>.</p>"
        "<p>Works on surface analysis and X-ray Photoelectron Spectroscopy "
        "(XPS), with a focus on materials for energy storage and "
        "catalysis, and writes free, open-source tools for scientists. "
        "KherveSlide grew out of the same everyday need as KherveTeX: "
        "talks and lectures in proper LaTeX (beamer) without leaving the "
        "drag-and-drop comfort of PowerPoint.</p>"
        "<p><a href='mailto:g.kerherve@imperial.ac.uk'>"
        "g.kerherve@imperial.ac.uk</a> &nbsp;·&nbsp; "
        "<a href='https://github.com/gkerherve'>github.com/gkerherve</a></p>"
        "<hr>"
        f"<h3><a href='{KHERVETOOLS_URL}'>khervetools.com</a></h3>"
        "<p>The home of the <b>Kherve</b> family of free, open-source "
        "desktop apps for science, teaching and everyday work — "
        "downloads, user guides, news and workshops (free to attend). "
        "They share one look and feel, and many talk to an AI assistant "
        "(Claude) through MCP.</p>"
        f"<ul style='margin-top:2px'>{tools}</ul>"
        f"<p>Visit <a href='{KHERVETOOLS_URL}'>khervetools.com</a> for "
        "the latest versions and the other tools.</p>"
        "<hr>"
        "<h3>KherveSlide</h3>"
        "<p>Design slides like in PowerPoint — drag, resize and stack "
        "text, pictures, equations, chemistry and flowcharts freely — and "
        "get beamer LaTeX, compiled to PDF with tectonic. Press <b>F1</b> "
        "for the User Guide.</p>"
        f"<p style='color:#666'>Version {version} &nbsp;·&nbsp; "
        f"<a href='{GITHUB_URL}'>source on GitHub</a></p>"
        "<p style='color:#666'><b>Built with</b> Python "
        f"{sys.version.split()[0]}, Qt {qVersion()}, PySide6 "
        f"{pyside_version}, PyMuPDF {_ver('pymupdf')} and the tectonic "
        "LaTeX engine.</p>"
        "<p style='color:#888;font-size:9pt'>Every icon is drawn at "
        "runtime with QPainter — no image files ship with the app.</p>"
        "<p>Copyright &copy; 2026 Gwilherm Kerherv&eacute; — licensed "
        "under the <a href='https://www.gnu.org/licenses/gpl-3.0.html'>GNU "
        "GPL v3.0</a>.</p>")


class AboutDialog(QDialog):
    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About KherveSlide")
        self.resize(640, 720)
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_icon_pixmap(96))
        logo.setFixedSize(96, 96)
        head.addWidget(logo, 0, Qt.AlignTop)
        name = QLabel(
            "<h2 style='margin-bottom:0'>"
            "<span style='color:#1F4E79'>Kherve</span>"
            "<span style='color:#DE6A14'>Slide</span></h2>"
            f"<p style='color:gray;margin-top:2px'>{version}</p>"
            "<p>Slides like PowerPoint, typeset like LaTeX.<br>"
            f"Part of <a href='{KHERVETOOLS_URL}'>khervetools.com</a>.</p>")
        name.setOpenExternalLinks(True)
        head.addWidget(name, 1)
        lay.addLayout(head)
        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        self.text.setHtml(about_html(version))
        lay.addWidget(self.text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
