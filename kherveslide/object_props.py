"""Reusable object-property dialogs (box style, shape, line / arrow).

These edit a single slide object's appearance and are shared by the main
canvas (``window.SlideWindow``) and the master-slide editor
(``master_editor.MasterSlideEditor``) so both stay in lock-step. Each editor
mutates the object in place and returns ``True`` when the user accepted, so
the caller can repaint and record an undo step; ``False`` on cancel.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QPushButton,
)

from . import shapes


def colour_button(state: dict, key: str, parent=None, *, allow_none=True):
    """A swatch button bound to ``state[key]``. Click picks a colour;
    right-click clears it to none (when allowed)."""
    btn = QPushButton()

    def refresh():
        v = state[key]
        btn.setText(v or "(none)")
        btn.setStyleSheet(f"background:{v}; color:#fff;" if v else "")

    def pick():
        c = QColorDialog.getColor(QColor(state[key] or "#ffffff"), parent)
        if c.isValid():
            state[key] = c.name()
            refresh()

    btn.clicked.connect(pick)
    if allow_none:
        btn.setToolTip("Click to choose; right-click clears")
        btn.setContextMenuPolicy(Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda _p: (state.__setitem__(key, ""), refresh()))
    refresh()
    return btn


def edit_box_style(o, parent=None) -> bool:
    """Border / fill / corner / shadow style for a text / picture / table
    box. Returns True if the user accepted (and *o* was mutated)."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("Box style")
    form = QFormLayout(dlg)
    state = {"fill": getattr(o, "fill", ""),
             "border_color": getattr(o, "border_color", "")}

    form.addRow("Fill colour", colour_button(state, "fill", dlg))
    fill_op = QDoubleSpinBox(); fill_op.setRange(0.0, 1.0)
    fill_op.setSingleStep(0.05); fill_op.setValue(getattr(o, "fill_opacity", 1.0))
    form.addRow("Fill opacity", fill_op)
    form.addRow("Border colour", colour_button(state, "border_color", dlg))
    width = QDoubleSpinBox(); width.setRange(0.0, 12.0); width.setSingleStep(0.5)
    width.setValue(getattr(o, "border_width", 1.0))
    form.addRow("Border width (pt)", width)
    bstyle = QComboBox(); bstyle.addItems(["solid", "dashed", "dotted"])
    bstyle.setCurrentText(getattr(o, "border_style", "solid"))
    form.addRow("Border style", bstyle)
    corner = QComboBox(); corner.addItems(["sharp", "rounded"])
    corner.setCurrentText(getattr(o, "corner", "sharp"))
    form.addRow("Corners", corner)
    radius = QDoubleSpinBox(); radius.setRange(0.0, 40.0); radius.setSingleStep(1.0)
    radius.setValue(getattr(o, "corner_radius", 4.0))
    form.addRow("Corner radius (pt)", radius)
    shadow = QCheckBox("Drop shadow")
    shadow.setChecked(getattr(o, "shadow", False))
    form.addRow(shadow)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
    form.addRow(bb)
    if not dlg.exec():
        return False
    o.fill = state["fill"]
    o.fill_opacity = fill_op.value()
    o.border_color = state["border_color"]
    o.border_width = width.value()
    o.border_style = bstyle.currentText()
    o.corner = corner.currentText()
    o.corner_radius = radius.value()
    o.shadow = shadow.isChecked()
    return True


def edit_shape(o, parent=None) -> bool:
    """Shape kind / fill / outline / corner / opacity / rotation."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("Shape properties")
    form = QFormLayout(dlg)
    state = {"fill": o.fill, "border_color": o.border_color}

    shape = QComboBox()
    for key, label in shapes.LABELS.items():
        shape.addItem(label, key)
    cur = shape.findData(o.shape)
    shape.setCurrentIndex(cur if cur >= 0 else 0)
    form.addRow("Shape", shape)
    form.addRow("Fill colour", colour_button(state, "fill", dlg))
    form.addRow("Outline colour", colour_button(state, "border_color", dlg))
    width = QDoubleSpinBox(); width.setRange(0.0, 20.0)
    width.setSingleStep(0.5); width.setValue(o.border_width)
    form.addRow("Outline width (pt)", width)
    style = QComboBox(); style.addItems(["solid", "dashed", "dotted"])
    style.setCurrentText(o.style)
    form.addRow("Outline style", style)
    corner = QComboBox(); corner.addItems(["sharp", "rounded"])
    corner.setCurrentText(o.corner)
    form.addRow("Corners (rect)", corner)
    opacity = QDoubleSpinBox(); opacity.setRange(0.0, 1.0)
    opacity.setSingleStep(0.05); opacity.setValue(o.opacity)
    form.addRow("Opacity", opacity)
    rot = QDoubleSpinBox(); rot.setRange(-360.0, 360.0)
    rot.setSingleStep(5.0); rot.setValue(o.rotation)
    form.addRow("Rotation (°)", rot)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
    form.addRow(bb)
    if not dlg.exec():
        return False
    o.shape = shape.currentData()
    o.fill = state["fill"]
    o.border_color = state["border_color"]
    o.border_width = width.value()
    o.style = style.currentText()
    o.corner = corner.currentText()
    o.opacity = opacity.value()
    o.rotation = rot.value()
    return True


def edit_line(o, parent=None) -> bool:
    """Colour / width / dash / arrowheads / opacity for a line or arrow."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("Line / arrow properties")
    form = QFormLayout(dlg)
    state = {"color": o.color}

    form.addRow("Colour", colour_button(state, "color", dlg, allow_none=False))
    width = QDoubleSpinBox(); width.setRange(0.1, 20.0)
    width.setSingleStep(0.5); width.setValue(o.width_pt)
    form.addRow("Width (pt)", width)
    style = QComboBox(); style.addItems(["solid", "dashed", "dotted"])
    style.setCurrentText(o.style)
    form.addRow("Style", style)
    a_start = QCheckBox("Arrowhead at start"); a_start.setChecked(o.arrow_start)
    a_end = QCheckBox("Arrowhead at end"); a_end.setChecked(o.arrow_end)
    form.addRow(a_start)
    form.addRow(a_end)
    head = QDoubleSpinBox(); head.setRange(0.3, 5.0)
    head.setSingleStep(0.1); head.setValue(o.head_size)
    form.addRow("Arrowhead size", head)
    opacity = QDoubleSpinBox(); opacity.setRange(0.0, 1.0)
    opacity.setSingleStep(0.05); opacity.setValue(o.opacity)
    form.addRow("Opacity", opacity)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
    form.addRow(bb)
    if not dlg.exec():
        return False
    o.color = state["color"] or "#000000"
    o.width_pt = width.value()
    o.style = style.currentText()
    o.arrow_start = a_start.isChecked()
    o.arrow_end = a_end.isChecked()
    o.head_size = head.value()
    o.opacity = opacity.value()
    return True
