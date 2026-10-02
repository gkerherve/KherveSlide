"""The WYSIWYG equation canvas: paints a :mod:`mathbox` tree as typeset
math and edits it with the keyboard and mouse, Word-equation style."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QKeySequence, QPainter, QPen,
)
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QWidget

from . import mathbox as mb
from . import mathlayout as ml

_SEL = QColor("#cfe0ff")
_SLOT = QColor(47, 111, 222, 18)
_CARET = QColor("#1f5fd1")
_MARGIN = 28


class _Completer(QListWidget):
    """Backslash-command suggestions shown under the caret."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setStyleSheet(
            "QListWidget { background: white; border: 1px solid #c8d0db;"
            " border-radius: 6px; padding: 3px; font-size: 13px; }"
            "QListWidget::item { padding: 3px 8px; border-radius: 4px; }"
            "QListWidget::item:selected { background: #2f6fde;"
            " color: white; }")
        self.hide()

    def set_items(self, items) -> None:
        self.clear()
        fam = ml.font_info()["family"]
        for name, glyph in items:
            it = QListWidgetItem(f"{glyph:<3}  \\{name}")
            it.setData(Qt.UserRole, name)
            f = QFont(fam)
            f.setPixelSize(15)
            it.setFont(f)
            self.addItem(it)
        if items:
            self.setCurrentRow(0)
        self.setFixedWidth(240)

    def current_name(self) -> str | None:
        it = self.currentItem()
        return it.data(Qt.UserRole) if it else None


class MathEditWidget(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.editor = mb.Editor()
        self._px = 34.0
        self._display = True
        self._box = None
        self._rows: dict = {}
        self._origin = QPointF(_MARGIN, _MARGIN)
        self._drag_anchor = None
        self._seen_version = -1
        self._layout_version = None
        self._caret_on = True
        self._blink = QTimer(self)
        self._blink.setInterval(530)
        self._blink.timeout.connect(self._toggle_caret)
        self._completer: _Completer | None = None
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.IBeamCursor)
        self.setAttribute(Qt.WA_InputMethodEnabled, False)
        self.setMinimumSize(200, 120)
        self._relayout()

    # ------------------------------------------------------------ API
    def set_latex(self, latex: str) -> None:
        self.editor.set_latex(latex)
        self._after_edit(emit=False)

    def latex(self, placeholder: str = "{}") -> str:
        return self.editor.latex(placeholder)

    def insert_latex(self, latex: str) -> None:
        self.editor.insert_latex(latex)
        self._after_edit()

    def insert_nodes(self, nodes) -> None:
        self.editor.insert_nodes(nodes)
        self._after_edit()

    def set_display(self, display: bool) -> None:
        self._display = display
        self._layout_version = None
        self._relayout()
        self.update()

    def zoom(self, factor: float | None) -> None:
        self._px = 34.0 if factor is None else \
            max(16.0, min(96.0, self._px * factor))
        self._layout_version = None
        self._relayout()
        self.update()

    def font_px(self) -> float:
        return self._px

    # --------------------------------------------------------- layout
    def _relayout(self) -> None:
        key = (self.editor.version, id(self.editor.root), self._px,
               self._display)
        if key == self._layout_version and self._box is not None:
            self._place()
            return
        self._layout_version = key
        self._box = ml.Layout(self._px, self._display).layout(
            self.editor.root)
        self._place()
        need = QSize(int(self._box.w + 2 * _MARGIN),
                     int(self._box.asc + self._box.desc + 2 * _MARGIN))
        if need.width() > self.minimumWidth() or \
                need.height() > self.minimumHeight():
            self.setMinimumSize(max(200, need.width()),
                                max(120, need.height()))

    def _place(self) -> None:
        b = self._box
        x = max(_MARGIN, (self.width() - b.w) / 2)
        y = max(_MARGIN + b.asc, (self.height() - b.asc - b.desc) / 2
                + b.asc)
        self._origin = QPointF(x, y)
        self._rows = ml.collect_rows(b, x, y)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._box is not None:
            self._place()

    def sizeHint(self) -> QSize:
        return QSize(560, 220)

    # ------------------------------------------------------- painting
    def _active_ref(self):
        e = self.editor
        if not e.row.children:
            return e.row
        ch = e.row.children
        if e.idx < len(ch) and isinstance(ch[e.idx], mb.Placeholder):
            return ch[e.idx]
        if e.idx > 0 and isinstance(ch[e.idx - 1], mb.Placeholder):
            return ch[e.idx - 1]
        return None

    def paintEvent(self, ev):
        self._relayout()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.fillRect(self.rect(), Qt.white)
        e = self.editor
        g = self._rows.get(id(e.row))
        focus = self.hasFocus()
        if g is not None and e.row is not e.root and e.row.children:
            r = g.rect().adjusted(-3, -2, 3, 2)
            p.setPen(Qt.NoPen)
            p.setBrush(_SLOT)
            p.drawRoundedRect(r, 3, 3)
        sel = e.selection()
        if sel is not None and g is not None:
            _, i, j = sel
            top, bot = g.caret_span()
            p.fillRect(QRectF(g.gaps[i], top, g.gaps[j] - g.gaps[i],
                              bot - top), _SEL)
        ml.paint(p, self._box, self._origin.x(), self._origin.y(),
                 ml.PaintCtx(active=self._active_ref() if focus else None))
        if not e.root.children:
            f = QFont(ml.font_info()["family"])
            f.setPixelSize(int(self._px * 0.42))
            f.setItalic(True)
            p.setFont(f)
            p.setPen(QColor("#a7b0bc"))
            p.drawText(QRectF(0, self._origin.y() + self._px * 0.35,
                              self.width(), self._px), Qt.AlignHCenter
                       | Qt.AlignTop, "Type an equation here")
        if g is not None and focus and self._caret_on and sel is None:
            x = g.gaps[min(e.idx, len(g.gaps) - 1)]
            top, bot = g.caret_span()
            pen = QPen(_CARET, max(1.5, self._px / 22))
            p.setPen(pen)
            p.drawLine(QPointF(x, top), QPointF(x, bot))
        p.end()

    def _toggle_caret(self):
        self._caret_on = not self._caret_on
        self.update()

    def focusInEvent(self, ev):
        super().focusInEvent(ev)
        self._caret_on = True
        self._blink.start()
        self.update()

    def focusOutEvent(self, ev):
        super().focusOutEvent(ev)
        self._blink.stop()
        if self._completer is not None:
            self._completer.hide()
        self.update()

    # -------------------------------------------------------- hit test
    def hit(self, pos: QPointF) -> tuple[mb.Row, int]:
        self._relayout()
        best = None
        for g in self._rows.values():
            r = g.rect().adjusted(-2, -2, 2, 2)
            if r.contains(pos):
                area = r.width() * r.height()
                if best is None or area < best[0]:
                    best = (area, g)
        if best is None:
            def dist(g):
                r = g.rect()
                dx = max(r.left() - pos.x(), 0, pos.x() - r.right())
                dy = max(r.top() - pos.y(), 0, pos.y() - r.bottom())
                return dx * dx + dy * dy
            g = min(self._rows.values(), key=dist)
        else:
            g = best[1]
        idx = min(range(len(g.gaps)), key=lambda k: abs(g.gaps[k]
                                                         - pos.x()))
        return g.row, idx

    def caret_rect(self) -> QRectF:
        self._relayout()
        g = self._rows.get(id(self.editor.row))
        if g is None:
            return QRectF()
        top, bot = g.caret_span()
        x = g.gaps[min(self.editor.idx, len(g.gaps) - 1)]
        return QRectF(x, top, 1, bot - top)

    # ----------------------------------------------------------- mouse
    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return super().mousePressEvent(ev)
        self.setFocus()
        row, idx = self.hit(ev.position())
        if ev.modifiers() & Qt.ShiftModifier:
            a = self.editor.anchor or (self.editor.row, self.editor.idx)
            self.editor.set_selection(a[0], a[1], row, idx)
            self._drag_anchor = a
        else:
            self.editor.set_cursor(row, idx)
            self._drag_anchor = (row, idx)
        self._after_edit()

    def mouseMoveEvent(self, ev):
        if self._drag_anchor is None or not (ev.buttons() & Qt.LeftButton):
            return
        row, idx = self.hit(ev.position())
        a = self._drag_anchor
        self.editor.set_selection(a[0], a[1], row, idx)
        self._after_edit()

    def mouseReleaseEvent(self, ev):
        self._drag_anchor = None

    def mouseDoubleClickEvent(self, ev):
        row, _ = self.hit(ev.position())
        self.editor.set_cursor(row, 0)
        self.editor.set_selection(row, 0, row, len(row.children))
        self._after_edit()

    # -------------------------------------------------------- keyboard
    def focusNextPrevChild(self, nxt):
        return False        # Tab moves between slots, not widgets

    def event(self, ev):
        # Grab editing shortcuts before the dialog turns them into
        # actions (Ctrl+Z etc. would otherwise never reach us).
        if ev.type() == ev.Type.ShortcutOverride:
            ev.accept()
            return True
        return super().event(ev)

    def keyPressEvent(self, ev):
        e = self.editor
        key = ev.key()
        mods = ev.modifiers()
        shift = bool(mods & Qt.ShiftModifier)
        comp = self._completer
        popup = comp is not None and comp.isVisible() and comp.count()

        if popup and key in (Qt.Key_Up, Qt.Key_Down):
            r = comp.currentRow() + (1 if key == Qt.Key_Down else -1)
            comp.setCurrentRow(max(0, min(comp.count() - 1, r)))
            return
        if popup and key in (Qt.Key_Tab, Qt.Key_Return, Qt.Key_Enter):
            self._accept_completion()
            return
        if ev.matches(QKeySequence.Undo):
            e.undo()
        elif ev.matches(QKeySequence.Redo) or (
                key == Qt.Key_Y and mods & Qt.ControlModifier):
            e.redo()
        elif ev.matches(QKeySequence.Copy):
            self.copy()
            return
        elif ev.matches(QKeySequence.Cut):
            self.copy()
            e.delete_selection()
        elif ev.matches(QKeySequence.Paste):
            text = QGuiApplication.clipboard().text()
            if text:
                e.paste_latex(text.strip().strip("$"))
        elif ev.matches(QKeySequence.SelectAll):
            e.select_all()
        elif mods & Qt.ControlModifier and key in (Qt.Key_Plus,
                                                   Qt.Key_Equal):
            self.zoom(1.15)
            return
        elif mods & Qt.ControlModifier and key == Qt.Key_Minus:
            self.zoom(1 / 1.15)
            return
        elif mods & Qt.ControlModifier and key == Qt.Key_0:
            self.zoom(None)
            return
        elif key == Qt.Key_Left:
            e.move_left(select=shift)
        elif key == Qt.Key_Right:
            e.move_right(select=shift)
        elif key == Qt.Key_Home:
            e.home(select=shift)
        elif key == Qt.Key_End:
            e.end(select=shift)
        elif key == Qt.Key_Up:
            e.move_vertical(up=True)
        elif key == Qt.Key_Down:
            e.move_vertical(up=False)
        elif key == Qt.Key_Backtab or (key == Qt.Key_Tab and shift):
            e.next_slot(forward=False)
        elif key == Qt.Key_Tab:
            e.next_slot(forward=True)
        elif key == Qt.Key_Backspace:
            e.backspace()
        elif key == Qt.Key_Delete:
            e.delete()
        elif key == Qt.Key_Escape:
            if e.cmd is not None:
                e.cancel_cmd()
            elif e.has_selection():
                e.clear_selection()
            else:
                ev.ignore()
                return
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if e.cmd is not None:
                e.commit_cmd()
            elif mods & Qt.ShiftModifier and e.matrix_add_col():
                pass
            elif not e.matrix_add_row():
                ev.ignore()      # let the dialog's Insert button fire
                return
        else:
            text = ev.text()
            if text and not (mods & Qt.ControlModifier) and \
                    all(c.isprintable() for c in text):
                if isinstance(e.row.owner, mb.Text) or e.cmd is not None \
                        or text != " ":
                    e.type_text(text)
                else:
                    e.type_char(" ")
            else:
                return super().keyPressEvent(ev)
        self._after_edit()

    def copy(self) -> None:
        text = self.editor.selection_latex() or self.editor.latex()
        if text:
            QGuiApplication.clipboard().setText(text)

    # ----------------------------------------------------- completion
    def _update_completer(self) -> None:
        e = self.editor
        if e.cmd is None or not e.cmd.text:
            if self._completer is not None:
                self._completer.hide()
            return
        items = mb.completions(e.cmd.text)
        if self._completer is None:
            self._completer = _Completer(self.window())
            self._completer.itemClicked.connect(
                lambda _it: self._accept_completion())
        c = self._completer
        if not items:
            c.hide()
            return
        c.set_items(items)
        r = self.caret_rect()
        top_left = self.mapTo(self.window(),
                              QPointF(r.x(), r.bottom() + 6).toPoint())
        h = min(len(items), 8) * 26 + 10
        c.setGeometry(top_left.x(), top_left.y(), 220, h)
        c.raise_()
        c.show()

    def _accept_completion(self) -> None:
        name = self._completer.current_name() if self._completer else None
        self.editor.commit_cmd(name)
        self._after_edit()
        self.setFocus()

    def _after_edit(self, emit=True) -> None:
        self._relayout()
        self._caret_on = True
        if self.hasFocus():
            self._blink.start()
        self._update_completer()
        self.update()
        if emit and self.editor.version != self._seen_version:
            self._seen_version = self.editor.version
            self.changed.emit()
        elif not emit:
            self._seen_version = self.editor.version
