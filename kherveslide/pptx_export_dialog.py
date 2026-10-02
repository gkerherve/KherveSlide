"""File ▸ Export PowerPoint (.pptx)…: the choices before exporting."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QRadioButton, QVBoxLayout,
)

from .pptx_export import MODE_EDITABLE, MODE_EXACT, ExportOptions


class PptxExportDialog(QDialog):
    def __init__(self, hidden_count: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export to PowerPoint")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        intro = QLabel("<b>How should the slides arrive in PowerPoint?</b>")
        lay.addWidget(intro)
        self.editable = QRadioButton(
            "Editable — text, pictures, tables and shapes you can change "
            "(recommended)")
        self.editable.setChecked(True)
        lay.addWidget(self.editable)
        ed = QLabel(
            "Titles, text boxes (bold, italic, colours, bullets and "
            "numbering), pictures, tables, shapes, lines and videos become "
            "PowerPoint objects. The theme — title bar, footers, slide "
            "numbers, background and the master — is each slide's "
            "background. Equations, beamer blocks and pictures with effects "
            "come as exact pictures from the PDF.")
        ed.setWordWrap(True)
        ed.setStyleSheet("color:#555; margin-left:22px;")
        lay.addWidget(ed)
        self.exact = QRadioButton(
            "Exact look — each slide as a picture, identical to the PDF")
        lay.addWidget(self.exact)
        ex = QLabel("Nothing can be edited, but every slide looks exactly "
                    "like the PDF — handy for presenting from someone "
                    "else's computer.")
        ex.setWordWrap(True)
        ex.setStyleSheet("color:#555; margin-left:22px;")
        lay.addWidget(ex)
        form = QFormLayout()
        self.dpi = QComboBox()
        for label, dpi in (("Standard (150 dpi) — smaller file", 150),
                           ("High (220 dpi)", 220),
                           ("Very high (300 dpi) — for big screens", 300)):
            self.dpi.addItem(label, dpi)
        self.dpi.setCurrentIndex(1)
        form.addRow("Picture quality", self.dpi)
        self.hidden = QCheckBox(
            f"Include the hidden slides ({hidden_count}), hidden in "
            "PowerPoint too")
        self.hidden.setChecked(True)
        self.hidden.setVisible(hidden_count > 0)
        form.addRow("", self.hidden)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Export…")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def options(self, accent: str = "#1F4E79") -> ExportOptions:
        return ExportOptions(
            mode=MODE_EDITABLE if self.editable.isChecked() else MODE_EXACT,
            include_hidden=self.hidden.isChecked(),
            dpi=int(self.dpi.currentData()), accent=accent)
