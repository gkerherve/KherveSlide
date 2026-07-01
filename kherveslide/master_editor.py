"""MasterSlideEditor — a compact WYSIWYG canvas for the master slide.

Embedded in the Theme builder, it lets you drop text, pictures, lines,
arrows, rectangles and shapes onto a single "master" slide whose objects
are painted behind every real slide (see ``serializer._master_background_block``).

It reuses the same canvas primitives as the main editor — ``SlideScene``,
``SlideView``, ``make_item`` and the ``BoxItem`` drag/resize/endpoint
handles — so a box behaves exactly as it does on a normal slide. The object
appearance dialogs are shared with the main window via ``object_props``.
Editing mutates ``self.master.objects`` in place and emits ``changed`` so the
dialog can refresh; there is no undo inside the editor — the whole master is
captured as one undo step when the dialog is applied back to the deck.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QFileDialog, QMenu, QSpinBox, QTextEdit, QToolBar,
    QToolButton, QVBoxLayout, QWidget,
)

from . import icons, shapes
from .canvas import (
    PictureBoxItem, SlideScene, SlideView, TableBoxItem, TextBoxItem,
    canvas_font, document_to_latex, latex_to_html, make_item, page_size_px,
)
from .model import (
    Slide, SlideLine, SlidePicture, SlideShape, SlideText,
    lower_object, raise_object, to_back, to_front,
)
from .object_props import edit_box_style, edit_line, edit_shape


class _MasterInlineEditor(QTextEdit):
    """A tiny floating rich editor that commits when it loses focus or on
    Escape (the master slide's boxes rarely need the full spell-checked
    editor from the main window)."""

    editingFinished = Signal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.editingFinished.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class MasterSlideEditor(QWidget):
    """Interactive editor for a single master ``Slide``. Emits ``changed``
    on any edit so the host can mirror the model / refresh a preview."""

    changed = Signal()

    def __init__(self, master: Slide, aspect="169", gap=0.0,
                 page_w_cm=0.0, page_h_cm=0.0, page_color="#FFFFFF",
                 parent=None):
        super().__init__(parent)
        self.master = master
        self._aspect = aspect
        self._gap = gap
        self._page_w_cm = page_w_cm
        self._page_h_cm = page_h_cm
        self._page_color = page_color or "#FFFFFF"
        self._items: list = []
        self._font_scale = 1.0
        self._loading = False
        self._fmt_updating = False
        self._edit_proxy = None
        self._edit_item = None

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self._build_toolbar())

        self.scene = SlideScene(self._aspect)
        self.scene.selectionChanged.connect(self._on_selection)
        self.view = SlideView(self.scene)
        self.view.imageDropped.connect(self._on_image_dropped)
        self.view.deleteRequested.connect(self._delete_selected)
        self.view.contextMenuRequested.connect(self._context_menu)
        v.addWidget(self.view, 1)

        self._reload()
        self._on_selection()          # start with the format controls disabled

    # ---------------- toolbar ----------------
    def _build_toolbar(self) -> QToolBar:
        tb = QToolBar("Master insert")
        tb.setIconSize(QSize(22, 22))
        tb.addAction(icons.text_box(), "Add text box", self._add_text)
        tb.addAction(icons.image_box(), "Add image", self._add_picture)
        tb.addAction(icons.line_tool(), "Add line", self._add_line)
        tb.addAction(icons.arrow_tool(), "Add arrow", self._add_arrow)
        tb.addAction(icons.rect_tool(), "Add rectangle", self._add_rect)
        tb.addAction(icons.ellipse_tool(), "Add circle / ellipse",
                     self._add_ellipse)

        shape_btn = QToolButton()
        shape_btn.setIcon(icons.drawing())
        shape_btn.setToolTip("Insert a shape")
        shape_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(shape_btn)
        for group, items in shapes.GROUPS:
            sub = menu.addMenu(group)
            for key, label in items:
                sub.addAction(label, lambda _=False, k=key: self._add_shape(k))
        shape_btn.setMenu(menu)
        tb.addWidget(shape_btn)

        # --- text format: acts on the selected text box ---
        tb.addSeparator()
        self._fsize = QSpinBox()
        self._fsize.setRange(4, 160)
        self._fsize.setToolTip("Font size (pt)")
        self._fsize.valueChanged.connect(self._set_font_size)
        tb.addWidget(self._fsize)

        self._btn_color = QToolButton()
        self._btn_color.setText("A")
        self._btn_color.setToolTip("Text colour")
        self._btn_color.clicked.connect(self._pick_text_color)
        tb.addWidget(self._btn_color)

        self._act_bold = tb.addAction(icons.bold(), "Bold", self._toggle_bold)
        self._act_bold.setCheckable(True)
        self._act_italic = tb.addAction(icons.italic(), "Italic",
                                        self._toggle_italic)
        self._act_italic.setCheckable(True)

        self._align_actions = {}
        for key, factory, tip in (("left", icons.align_left, "Align left"),
                                  ("center", icons.align_center, "Centre"),
                                  ("right", icons.align_right, "Align right")):
            a = tb.addAction(factory(), tip,
                             lambda _=False, k=key: self._set_align(k))
            a.setCheckable(True)
            self._align_actions[key] = a

        self._fmt_widgets = [self._fsize, self._btn_color, self._act_bold,
                             self._act_italic, *self._align_actions.values()]

        tb.addSeparator()
        tb.addAction(icons.raise_box(), "Raise", lambda: self._zorder("raise"))
        tb.addAction(icons.lower_box(), "Lower", lambda: self._zorder("lower"))
        tb.addAction(icons.to_front(), "Bring to front",
                     lambda: self._zorder("front"))
        tb.addAction(icons.to_back(), "Send to back",
                     lambda: self._zorder("back"))
        tb.addSeparator()
        tb.addAction(icons.delete_box(), "Delete object", self._delete_selected)
        return tb

    # ---------------- scene ----------------
    def set_page_color(self, hex_color: str):
        """Recolour the canvas page (e.g. to follow the theme's background)."""
        self._page_color = hex_color or "#FFFFFF"
        self.scene.page_color = self._page_color
        self.scene.invalidate()

    def set_backdrop(self, pixmap):
        """Show *pixmap* (a rendered image of the themed slide) under the
        master objects, so the master is built directly over the live theme.
        Pass ``None`` to fall back to the flat page colour."""
        self.scene.backdrop = pixmap
        self.scene.invalidate()

    # ---------------- text format ----------------
    def _selected_text(self):
        item = self._selected_item()
        return item if isinstance(item, TextBoxItem) else None

    def _on_selection(self):
        """Enable / sync the text-format controls to the selected text box."""
        item = self._selected_text()
        on = item is not None
        self._fmt_updating = True
        for w in self._fmt_widgets:
            w.setEnabled(on)
        if on:
            o = item.obj
            self._fsize.setValue(int(o.font_pt))
            self._act_bold.setChecked(bool(o.bold))
            self._act_italic.setChecked(bool(o.italic))
            for k, a in self._align_actions.items():
                a.setChecked(o.align == k)
            self._btn_color.setStyleSheet(
                f"QToolButton {{ color: {o.color or '#000000'}; "
                f"font-weight: bold; }}")
        self._fmt_updating = False

    def _refresh_text(self, item):
        """Rebuild the edited text item in place, keeping it selected."""
        idx = self.master.objects.index(item.obj)
        self._reload()
        if 0 <= idx < len(self._items):
            self._items[idx].setSelected(True)
        self.changed.emit()

    def _set_font_size(self, value):
        if self._fmt_updating:
            return
        item = self._selected_text()
        if item is not None:
            item.obj.font_pt = int(value)
            self._refresh_text(item)

    def _pick_text_color(self):
        item = self._selected_text()
        if item is None:
            return
        c = QColorDialog.getColor(QColor(item.obj.color or "#000000"), self,
                                  "Text colour")
        if c.isValid():
            item.obj.color = c.name()
            self._refresh_text(item)

    def _toggle_bold(self, checked):
        if self._fmt_updating:
            return
        item = self._selected_text()
        if item is not None:
            item.obj.bold = bool(checked)
            self._refresh_text(item)

    def _toggle_italic(self, checked):
        if self._fmt_updating:
            return
        item = self._selected_text()
        if item is not None:
            item.obj.italic = bool(checked)
            self._refresh_text(item)

    def _set_align(self, key):
        if self._fmt_updating:
            return
        item = self._selected_text()
        if item is not None:
            item.obj.align = key
            self._refresh_text(item)

    def _reload(self):
        self._cancel_edit()
        self._loading = True
        self._items = []
        pw, ph, self._font_scale = page_size_px(
            self._aspect, self._page_w_cm, self._page_h_cm)
        self.scene.set_page(pw, ph, self._gap)
        self.scene.page_color = self._page_color
        self.scene.blockSignals(True)
        self.scene.clear()
        self.scene.blockSignals(False)
        for z, obj in enumerate(self.master.objects):
            # Master objects are always drawn absolutely by the serializer, so
            # they should all be freely draggable here — never beamer-locked.
            obj.locked = False
            item = make_item(obj, pw, ph, self._gap, self._font_scale)
            item.setZValue(z)
            item.geometryChanged.connect(self._on_geometry)
            if isinstance(item, TableBoxItem):
                item.cellDoubleClicked.connect(
                    lambda r, c, it=item: self._edit_table_cell(it, r, c))
            else:
                item.doubleClicked.connect(
                    lambda it=item: self._on_double_click(it))
            self.scene.addItem(item)
            self._items.append(item)
        if self.view.fit_mode:
            self.view.fit_to_window()
        self._loading = False

    def _on_geometry(self):
        # A box was dragged / resized; the item already wrote its 0..1
        # geometry back into the model object, so just signal the change.
        if not self._loading:
            self.changed.emit()

    # ---------------- insert objects ----------------
    def _place_stacked(self, obj):
        """Stack a new object just below the bottom-most existing one so
        boxes don't all land on top of each other."""
        others = [o for o in self.master.objects
                  if o is not obj and hasattr(o, "y") and hasattr(o, "h")]
        if not others:
            return
        last = max(others, key=lambda o: o.y + o.h)
        obj.x = round(last.x, 4)
        if not isinstance(obj, SlidePicture):
            obj.w = last.w
        new_y = last.y + last.h + 0.02
        if new_y + obj.h > 1.0:
            new_y = max(0.0, 1.0 - obj.h)
        obj.y = round(new_y, 4)

    def _add(self, obj, *, stack=True):
        if stack:
            self._place_stacked(obj)
        self.master.objects.append(obj)
        self._reload()
        self._select_last()
        self.changed.emit()

    def _add_text(self):
        self._add(SlideText())

    def _add_picture(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", "",
            "Images (*.png *.jpg *.jpeg *.pdf *.gif *.bmp)")
        self._add(SlidePicture(path=path or ""))

    def _add_line(self):
        self._add(SlideLine(), stack=False)

    def _add_arrow(self):
        self._add(SlideLine(arrow_end=True), stack=False)

    def _add_rect(self):
        self._add(SlideShape(shape="rect"))

    def _add_ellipse(self):
        self._add(SlideShape(shape="ellipse", w=0.22, h=0.22))

    def _add_shape(self, key):
        round_ish = ("circle", "ellipse", "star4", "star5", "star6", "plus",
                     "pentagon", "hexagon", "heptagon", "octagon")
        h = 0.22 if key in round_ish else 0.18
        self._add(SlideShape(shape=key, w=0.22, h=h))

    def _on_image_dropped(self, path, scene_pos):
        g = self.scene.gap
        cw = (1 - 2 * g) * self.scene.page_w
        ch = (1 - 2 * g) * self.scene.page_h
        ox, oy = g * self.scene.page_w, g * self.scene.page_h
        w = h = 0.3
        x = max(0.0, min(1 - w, (scene_pos.x() - ox) / cw - w / 2))
        y = max(0.0, min(1 - h, (scene_pos.y() - oy) / ch - h / 2))
        self.master.objects.append(SlidePicture(
            x=round(x, 4), y=round(y, 4), w=w, h=h, path=path, keep_aspect=True))
        self._reload()
        self._select_last()
        self.changed.emit()

    # ---------------- selection / z-order / delete ----------------
    def _selected_item(self):
        for it in self._items:
            try:
                if it.isSelected():
                    return it
            except RuntimeError:
                continue
        return None

    def _select_last(self):
        if self._items:
            self._items[-1].setSelected(True)

    def _select_box_at(self, scene_pos):
        from .canvas import BoxItem
        for it in self.scene.items(scene_pos):
            if isinstance(it, BoxItem):
                self.scene.clearSelection()
                it.setSelected(True)
                return it
        return None

    def _zorder(self, how):
        item = self._selected_item()
        if item is None:
            return
        idx = self.master.objects.index(item.obj)
        fn = {"raise": raise_object, "lower": lower_object,
              "front": to_front, "back": to_back}[how]
        new_idx = fn(self.master, idx)
        self._reload()
        if 0 <= new_idx < len(self._items):
            self._items[new_idx].setSelected(True)
        self.changed.emit()

    def _delete_selected(self):
        item = self._selected_item()
        if item is None:
            return
        self.master.objects.remove(item.obj)
        self._reload()
        self.changed.emit()

    # ---------------- double-click editing ----------------
    def _on_double_click(self, item):
        if isinstance(item, TextBoxItem):
            self._begin_inline_edit(item)
        elif isinstance(item, PictureBoxItem):
            self._edit_picture(item)

    def _edit_picture(self, item):
        if not isinstance(item.obj, SlidePicture):
            return
        from .picture_editor import PictureEditDialog
        dlg = PictureEditDialog(item.obj, self)
        if not dlg.exec():
            return
        o = item.obj
        o.path = dlg.path
        o.crop_l, o.crop_t, o.crop_r, o.crop_b = dlg.crop
        o.rotation = dlg.rotation
        item._pix_path = None
        item.update()
        self.changed.emit()

    def _edit_table_cell(self, item, r, c):
        rows = item.obj.rows
        cur = rows[r][c] if c < len(rows[r]) else ""
        self._begin_inline_edit(item, rect=item.cell_scene_rect(r, c),
                                initial=cur,
                                commit=lambda t: self._commit_cell(item, r, c, t))

    def _commit_cell(self, item, r, c, text):
        item.obj.rows[r][c] = text
        item.update()

    # ---------------- inline text editor ----------------
    def _begin_inline_edit(self, item, *, rect=None, initial=None, commit=None):
        self._cancel_edit()
        if initial is None:
            initial = item.obj.text
        if rect is None:
            rect = item.scene_rect()
        if commit is None:
            commit = lambda t: self._commit_text(item, t)
        editor = _MasterInlineEditor()
        editor.setFont(canvas_font(max(8, int(item.obj.font_pt * self._font_scale))))
        editor.setHtml(latex_to_html(initial))
        bg = getattr(item.obj, "fill", "") or "#ffffff"
        editor.setStyleSheet(
            f"QTextEdit {{ background: {bg}; border: 1px solid #2878dc; }}")
        proxy = self.scene.addWidget(editor)
        proxy.setGeometry(rect)
        proxy.setZValue(1e6)
        self._edit_proxy = proxy
        self._edit_item = item
        self._edit_commit = commit
        try:
            item._editing = True
            item.update()
        except RuntimeError:
            self._edit_item = None
        editor.editingFinished.connect(self._finish_edit)
        editor.setFocus()
        editor.selectAll()

    def _finish_edit(self):
        if self._edit_proxy is None:
            return
        proxy = self._edit_proxy
        commit = self._edit_commit
        text = document_to_latex(proxy.widget().document())
        self._edit_proxy = None
        self._edit_commit = None
        self._restore_edit_item()
        self.scene.removeItem(proxy)
        if commit is not None:
            commit(text)
        self.changed.emit()

    def _cancel_edit(self):
        proxy = getattr(self, "_edit_proxy", None)
        if proxy is None:
            return
        self._edit_proxy = None
        self._edit_commit = None
        try:
            proxy.widget().editingFinished.disconnect()
        except (RuntimeError, TypeError):
            pass
        if self.scene.focusItem() is proxy:
            self.scene.setFocusItem(None)
        self._restore_edit_item()
        self.scene.removeItem(proxy)

    def _restore_edit_item(self):
        item = self._edit_item
        self._edit_item = None
        if item is not None:
            try:
                item._editing = False
                item.update()
            except RuntimeError:
                pass

    def _commit_text(self, item, text):
        item.obj.text = text
        item.update()
        item.setSelected(True)

    # ---------------- context menu ----------------
    def _context_menu(self, global_pos, scene_pos):
        on_canvas = isinstance(scene_pos, QPointF)
        hit = self._select_box_at(scene_pos) if on_canvas else None
        menu = QMenu(self)
        if on_canvas and hit is None:
            self.scene.clearSelection()
            menu.addAction("Add text box", self._add_text)
            menu.addAction("Add image…", self._add_picture)
            menu.addAction("Add rectangle", self._add_rect)
            menu.addAction("Add line", self._add_line)
            menu.exec(global_pos)
            return
        item = self._selected_item()
        if item is None:
            return
        menu.addAction("Delete", self._delete_selected)
        menu.addAction("Bring to front", lambda: self._zorder("front"))
        menu.addAction("Send to back", lambda: self._zorder("back"))
        menu.addSeparator()
        o = item.obj
        if isinstance(o, SlideShape):
            menu.addAction("Shape properties…",
                           lambda: self._props(item, edit_shape))
        elif isinstance(o, SlideLine):
            menu.addAction("Line / arrow properties…",
                           lambda: self._props(item, edit_line))
        elif isinstance(o, SlidePicture):
            menu.addAction("Crop && rotate…", lambda: self._edit_picture(item))
            menu.addAction("Box style (border / fill)…",
                           lambda: self._props(item, edit_box_style))
        else:
            menu.addAction("Box style (border / fill)…",
                           lambda: self._props(item, edit_box_style))
        menu.exec(global_pos)

    def _props(self, item, editor_fn):
        if editor_fn(item.obj, self):
            item.update()
            self.changed.emit()
