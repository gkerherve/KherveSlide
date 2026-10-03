"""Print and print preview, PowerPoint-style.

One window (File ▸ Print…, Ctrl+P, or File ▸ Print preview…): the
settings on the left, the live preview of the printed sheets on the right
and Print… at the bottom, which opens the system print dialog (printer,
copies, paper). What is printed is the compiled PDF of the presentation —
exactly what the slideshow shows — laid out as:

* **Full page slides** — one slide per sheet, landscape;
* **Handouts** — 2, 3 (with lines for notes), 4, 6 or 9 slides per
  sheet, portrait.

Options: which slides (all, the current one, or a range like 1-3, 5),
colour or greyscale, a thin frame round each slide, and a header (the
presentation's title and the date) with page numbers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPageLayout, QPageSize, \
    QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton, QToolButton,
    QVBoxLayout, QWidget,
)

#: layout key → (label, slides per sheet, columns, rows, landscape)
LAYOUTS = {
    "slides": ("Full page slides", 1, 1, 1, True),
    "handout2": ("Handouts — 2 slides per page", 2, 1, 2, False),
    "handout3": ("Handouts — 3 slides per page, with lines for notes",
                 3, 1, 3, False),
    "handout4": ("Handouts — 4 slides per page", 4, 2, 2, False),
    "handout6": ("Handouts — 6 slides per page", 6, 2, 3, False),
    "handout9": ("Handouts — 9 slides per page", 9, 3, 3, False),
}


@dataclass
class PrintSettings:
    layout: str = "slides"
    which: str = "all"              # all | current | range
    range_text: str = ""
    current: int = 0                # 0-based page of the current slide
    greyscale: bool = False
    frame: bool = True
    header: bool = True
    title: str = ""


def parse_range(text: str, count: int) -> list[int]:
    """“1-3, 5” → [0, 1, 2, 4] (0-based, in order, no repeats); numbers
    past the end are dropped. ValueError for anything else."""
    out: list[int] = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            lo, hi = int(a.strip() or 1), int(b.strip() or count)
        else:
            lo = hi = int(part)
        if lo < 1 or hi < lo:
            raise ValueError(part)
        out += [k - 1 for k in range(lo, hi + 1) if k <= count]
    seen: set = set()
    return [k for k in out if not (k in seen or seen.add(k))]


def chosen_pages(s: PrintSettings, count: int) -> list[int]:
    if s.which == "current":
        return [min(max(0, s.current), count - 1)] if count else []
    if s.which == "range":
        return parse_range(s.range_text, count)
    return list(range(count))


def sheets_for(pages: list[int], layout: str) -> list[list[int]]:
    per = LAYOUTS[layout][1]
    return [pages[k:k + per] for k in range(0, len(pages), per)]


def _slide_image(doc, index: int, dpi: int, grey: bool) -> QImage:
    import pymupdf
    pix = doc[index].get_pixmap(
        dpi=dpi, alpha=False,
        colorspace=pymupdf.csGRAY if grey else pymupdf.csRGB)
    fmt = QImage.Format_Grayscale8 if grey else QImage.Format_RGB888
    return QImage(pix.samples, pix.width, pix.height, pix.stride,
                  fmt).copy()


def paint(printer, doc, s: PrintSettings, dpi: int = 200) -> int:
    """Lay the chosen slides of *doc* (a PyMuPDF document) out on
    *printer* (a QPrinter or QPagedPaintDevice). Returns the sheets
    printed."""
    pages = chosen_pages(s, doc.page_count)
    sheets = sheets_for(pages, s.layout)
    if not sheets:
        return 0
    _label, _per, cols, rows, _land = LAYOUTS[s.layout]
    res = printer.resolution()
    area = printer.pageLayout().paintRectPixels(res)
    w, h = float(area.width()), float(area.height())
    pt = res / 72.0
    painter = QPainter()
    if not painter.begin(printer):
        return 0
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.Antialiasing)
    small = QFont("Helvetica")
    # Windows has no Helvetica: the hint makes Qt fall back to Arial
    # instead of a face that prints nothing.
    small.setStyleHint(QFont.SansSerif)
    small.setPixelSize(max(1, int(9 * pt)))
    head_h = 16 * pt if s.header else 0
    foot_h = 14 * pt if s.header else 0
    ratio = doc[0].rect.width / doc[0].rect.height
    today = f"{date.today():%d %B %Y}".lstrip("0")
    for n, sheet in enumerate(sheets):
        if n:
            printer.newPage()
        if s.header:
            painter.setFont(small)
            painter.setPen(QColor("#555555"))
            painter.drawText(QRectF(0, 0, w, head_h),
                             Qt.AlignLeft | Qt.AlignTop, s.title or "")
            painter.drawText(QRectF(0, 0, w, head_h),
                             Qt.AlignRight | Qt.AlignTop, today)
            painter.drawText(QRectF(0, h - foot_h, w, foot_h),
                             Qt.AlignHCenter | Qt.AlignBottom,
                             f"Page {n + 1} of {len(sheets)}")
        body = QRectF(0, head_h, w, h - head_h - foot_h)
        gap = 14 * pt if s.layout != "slides" else 0
        lines = s.layout == "handout3"
        cell_w = (body.width() - gap * (cols - 1)) / cols
        cell_h = (body.height() - gap * (rows - 1)) / rows
        for k, page in enumerate(sheet):
            c, r = k % cols, k // cols
            cell = QRectF(body.left() + c * (cell_w + gap),
                          body.top() + r * (cell_h + gap), cell_w, cell_h)
            slot = QRectF(cell)
            if lines:                       # slide left, notes lines right
                slot.setWidth(cell.width() * 0.5)
            sw = min(slot.width(), slot.height() * ratio)
            sh = sw / ratio
            target = QRectF(slot.left() + (slot.width() - sw) / 2
                            if not lines else slot.left(),
                            slot.top() + (slot.height() - sh) / 2, sw, sh)
            painter.drawImage(target, _slide_image(doc, page, dpi,
                                                   s.greyscale))
            if s.frame:
                painter.setPen(QPen(QColor("#9a9a9a"), max(1.0, 0.6 * pt)))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(target)
            if lines:
                painter.setPen(QPen(QColor("#b5b5b5"), max(1.0, 0.5 * pt)))
                x0 = cell.left() + cell.width() * 0.56
                step = 22 * pt
                y = target.top() + step * 0.6
                while y <= target.bottom():
                    painter.drawLine(int(x0), int(y), int(cell.right()),
                                     int(y))
                    y += step
    painter.end()
    return len(sheets)


def set_orientation(printer, layout: str) -> None:
    landscape = LAYOUTS[layout][4]
    printer.setPageOrientation(QPageLayout.Landscape if landscape
                               else QPageLayout.Portrait)


class PrintDialog(QDialog):
    """Settings on the left, the live preview on the right, Print…"""

    def __init__(self, pdf_path, settings: PrintSettings, parent=None):
        super().__init__(parent)
        import pymupdf
        from PySide6.QtPrintSupport import QPrinter, QPrintPreviewWidget
        self.setWindowTitle("Print")
        self.resize(1180, 820)
        self.doc = pymupdf.open(str(pdf_path))
        self.s = settings
        self.printer = QPrinter(QPrinter.HighResolution)
        self.printer.setPageSize(QPageSize(QPageSize.A4))
        self.printer.setPageMargins(QMarginsF(12, 12, 12, 12),
                                    QPageLayout.Millimeter)
        self.printer.setDocName(settings.title or "Presentation")
        set_orientation(self.printer, settings.layout)

        root = QHBoxLayout(self)
        side = QWidget()
        side.setFixedWidth(330)
        form = QFormLayout(side)
        form.setLabelAlignment(Qt.AlignRight)
        title = QLabel("<b>Print</b>")
        form.addRow(title)

        self.layout_box = QComboBox()
        for key, (label, *_rest) in LAYOUTS.items():
            self.layout_box.addItem(label, key)
        self.layout_box.setCurrentIndex(self.layout_box.findData(
            settings.layout))
        self.layout_box.currentIndexChanged.connect(self._on_layout)
        form.addRow("Layout", self.layout_box)

        which = QWidget()
        wl = QVBoxLayout(which)
        wl.setContentsMargins(0, 0, 0, 0)
        self.r_all = QRadioButton("All slides")
        self.r_cur = QRadioButton(f"Current slide ({settings.current + 1})")
        self.r_range = QRadioButton("Slides:")
        self.range_edit = QLineEdit(settings.range_text)
        self.range_edit.setPlaceholderText("e.g. 1-3, 5")
        self.range_edit.textChanged.connect(
            lambda _t: (self.r_range.setChecked(True), self._update()))
        rr = QHBoxLayout()
        rr.addWidget(self.r_range)
        rr.addWidget(self.range_edit, 1)
        {"all": self.r_all, "current": self.r_cur,
         "range": self.r_range}[settings.which].setChecked(True)
        for b in (self.r_all, self.r_cur, self.r_range):
            b.toggled.connect(lambda on: on and self._update())
        wl.addWidget(self.r_all)
        wl.addWidget(self.r_cur)
        wl.addLayout(rr)
        form.addRow("Print", which)

        self.colour = QComboBox()
        self.colour.addItem("Colour", False)
        self.colour.addItem("Greyscale", True)
        self.colour.setCurrentIndex(1 if settings.greyscale else 0)
        self.colour.currentIndexChanged.connect(lambda _i: self._update())
        form.addRow("Colour", self.colour)
        self.frame = QCheckBox("Frame the slides")
        self.frame.setChecked(settings.frame)
        self.frame.toggled.connect(lambda _on: self._update())
        form.addRow("", self.frame)
        self.header = QCheckBox("Title, date and page numbers")
        self.header.setChecked(settings.header)
        self.header.toggled.connect(lambda _on: self._update())
        form.addRow("", self.header)
        self.info = QLabel()
        self.info.setStyleSheet("color:#555;")
        self.info.setWordWrap(True)
        form.addRow(self.info)
        note = QLabel("Prints the compiled PDF — exactly what the slideshow "
                      "shows (hidden slides are left out). The printer, "
                      "copies and paper are chosen in the next window.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#777; font-size:11px;")
        form.addRow(note)
        root.addWidget(side)

        right = QVBoxLayout()
        bar = QHBoxLayout()
        self.preview = QPrintPreviewWidget(self.printer)
        self.preview.paintRequested.connect(
            lambda printer: paint(printer, self.doc, self._settings(), 110))
        self.preview.previewChanged.connect(self._sync_page)
        for text, tip, slot in (
                ("◀", "Previous page", lambda: self._go(-1)),
                ("▶", "Next page", lambda: self._go(1)),
                ("−", "Zoom out", lambda: self.preview.zoomOut()),
                ("+", "Zoom in", lambda: self.preview.zoomIn()),
                ("Fit", "Whole page", self.preview.fitInView)):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            bar.addWidget(b)
        self.page_label = QLabel()
        bar.addWidget(self.page_label)
        bar.addStretch(1)
        right.addLayout(bar)
        right.addWidget(self.preview, 1)
        buttons = QHBoxLayout()
        pdf_btn = QPushButton("Save as PDF…")
        pdf_btn.setToolTip("Save the printed pages (e.g. the handouts) as "
                           "a PDF file")
        pdf_btn.clicked.connect(self._save_pdf)
        buttons.addWidget(pdf_btn)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        self.print_btn = QPushButton("Print…")
        self.print_btn.setDefault(True)
        self.print_btn.clicked.connect(self._print)
        buttons.addWidget(close)
        buttons.addWidget(self.print_btn)
        right.addLayout(buttons)
        root.addLayout(right, 1)
        self._update()

    # ---- settings ----
    def _settings(self) -> PrintSettings:
        s = self.s
        s.layout = self.layout_box.currentData()
        s.which = ("current" if self.r_cur.isChecked() else
                   "range" if self.r_range.isChecked() else "all")
        s.range_text = self.range_edit.text()
        s.greyscale = bool(self.colour.currentData())
        s.frame = self.frame.isChecked()
        s.header = self.header.isChecked()
        return s

    def _on_layout(self, _i) -> None:
        set_orientation(self.printer, self.layout_box.currentData())
        self._update()

    def _update(self) -> None:
        s = self._settings()
        try:
            pages = chosen_pages(s, self.doc.page_count)
            ok = bool(pages)
            msg = (f"{len(pages)} slide{'s' * (len(pages) != 1)} on "
                   f"{len(sheets_for(pages, s.layout))} page"
                   f"{'s' * (len(sheets_for(pages, s.layout)) != 1)}"
                   if ok else "No slide in that range.")
        except ValueError:
            ok, msg = False, "Write the slides like 1-3, 5."
        self.info.setText(msg)
        self.print_btn.setEnabled(ok)
        self.preview.updatePreview()

    def _go(self, step: int) -> None:
        self.preview.setCurrentPage(self.preview.currentPage() + step)

    def _sync_page(self) -> None:
        n = self.preview.pageCount()
        self.page_label.setText(
            f"  Page {self.preview.currentPage()} of {n}" if n else "")

    # ---- output ----
    def _print(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog
        dlg = QPrintDialog(self.printer, self)
        dlg.setWindowTitle("Print the presentation")
        if dlg.exec() != QDialog.Accepted:
            return
        dpi = min(300, max(150, self.printer.resolution()))
        if paint(self.printer, self.doc, self._settings(), dpi):
            self.accept()

    def _save_pdf(self) -> None:
        from PySide6.QtPrintSupport import QPrinter
        out, _ = QFileDialog.getSaveFileName(
            self, "Save as PDF", (self.s.title or "presentation") + ".pdf",
            "PDF document (*.pdf)")
        if not out:
            return
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(out)
        printer.setPageLayout(self.printer.pageLayout())
        if paint(printer, self.doc, self._settings(), 220):
            QMessageBox.information(self, "Save as PDF", f"Saved {out}")
