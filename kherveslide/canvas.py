"""The slide canvas — graphics scene plus the movable / resizable boxes.

Geometry is stored in the model as ``0..1`` fractions of the slide; here
those map onto a fixed-height scene so the boxes can be dragged and
resized directly, and the same drawing code renders the little
thumbnails shown in the slide navigator.
"""
from __future__ import annotations

import html as _html
import math
import re

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPen, QPixmap, QPolygonF, QTextCharFormat,
    QTextCursor, QTextDocument, QTextListFormat, QTextOption,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsView,
)

from .model import (
    Slide, SlideText, SlidePicture, SlideTable, SlideLine,
    TABLE_HEADER_BG, TABLE_HEADER_FG, TABLE_RULE,
)


def _inline_html(s: str) -> str:
    """Best-effort LaTeX inline → HTML for the canvas preview."""
    s = _html.escape(s)
    s = re.sub(r"\\textbf\{([^}]*)\}", r"<b>\1</b>", s)
    s = re.sub(r"\\textit\{([^}]*)\}", r"<i>\1</i>", s)
    s = re.sub(r"\\emph\{([^}]*)\}", r"<i>\1</i>", s)
    s = re.sub(r"\$([^$]*)\$", r"\1", s)          # show maths source, no $
    s = s.replace("\\textbar{}", "|").replace("\\textbar", "|")
    s = s.replace("\\\\", "<br>")
    s = s.replace("\\&", "&amp;").replace("\\%", "%").replace("\\_", "_")
    s = s.replace("\\#", "#").replace("\\{", "{").replace("\\}", "}")
    return s


def _math_only(text: str) -> str | None:
    """If *text* is a single math expression ($…$, \\[…\\] or \\(…\\)),
    return the inner LaTeX; otherwise None."""
    t = (text or "").strip()
    if len(t) >= 2 and t.startswith("$") and t.endswith("$") \
            and "$" not in t[1:-1]:
        return t[1:-1].strip()
    if t.startswith("\\[") and t.endswith("\\]"):
        return t[2:-2].strip()
    if t.startswith("\\(") and t.endswith("\\)"):
        return t[2:-2].strip()
    return None


def latex_to_html(text: str) -> str:
    """Render a text box's LaTeX-ish content as HTML so itemize/enumerate
    look like real bullet / numbered lists on the canvas."""
    out: list[str] = []
    buf: list[str] = []
    env: str | None = None

    def flush():
        nonlocal buf, env
        if env and buf:
            tag = "ol" if env == "enumerate" else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{x}</li>" for x in buf)
                       + f"</{tag}>")
        buf = []

    for raw in (text or "").split("\n"):
        s = raw.strip()
        mb = re.match(r"\\begin\{(itemize|enumerate)\}", s)
        if mb:
            flush(); env = mb.group(1); buf = []
            continue
        if re.match(r"\\end\{(itemize|enumerate)\}", s):
            flush(); env = None
            continue
        if s.startswith("\\item"):
            buf.append(_inline_html(s[len("\\item"):].strip()))
            continue
        flush(); env = None
        out.append(f"<div>{_inline_html(s)}</div>" if s else "<br>")
    flush()
    return "".join(out) or "&nbsp;"


def _block_latex(block) -> str:
    """One QTextBlock -> LaTeX, wrapping bold/italic runs."""
    parts = []
    it = block.begin()
    seen = False
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid():
            seen = True
            t = frag.text()
            f = frag.charFormat().font()
            if f.italic():
                t = f"\\textit{{{t}}}"
            if f.bold():
                t = f"\\textbf{{{t}}}"
            parts.append(t)
        it += 1
    return "".join(parts) if seen else block.text()


def document_to_latex(doc: QTextDocument) -> str:
    """Inverse of :func:`latex_to_html`: turn the rich edited document back
    into LaTeX — bullet/numbered lists become itemize/enumerate, bold and
    italic runs become \\textbf/\\textit. Other text passes through, so
    inline maths like ``$x^2$`` survives a round-trip."""
    lines: list[str] = []
    env: str | None = None
    block = doc.begin()
    while block.isValid():
        tl = block.textList()
        text = _block_latex(block)
        if tl is not None:
            style = tl.format().style()
            new_env = ("enumerate"
                       if style in (QTextListFormat.ListDecimal,
                                    QTextListFormat.ListLowerAlpha,
                                    QTextListFormat.ListUpperAlpha,
                                    QTextListFormat.ListLowerRoman,
                                    QTextListFormat.ListUpperRoman)
                       else "itemize")
            if env != new_env:
                if env:
                    lines.append(f"\\end{{{env}}}")
                lines.append(f"\\begin{{{new_env}}}")
                env = new_env
            lines.append(f"  \\item {text}")
        else:
            if env:
                lines.append(f"\\end{{{env}}}")
                env = None
            lines.append(text)
        block = block.next()
    if env:
        lines.append(f"\\end{{{env}}}")
    return "\n".join(lines).strip("\n")


SCENE_H = 720.0                 # slide height in scene units (px)
# beamer's slide height is ~96 mm ≈ 272.8 pt for every aspect ratio, so
# this turns a font's pt size into canvas pixels for WYSIWYG sizing.
FONT_SCALE = SCENE_H / 272.8
HANDLE = 9.0                    # half-size of a resize handle, in px
MIN_PX = 24.0                   # smallest box dimension

_ASPECT_RATIO = {              # width : height multiplier
    "169": 16 / 9, "1610": 16 / 10, "43": 4 / 3,
    "32": 3 / 2, "54": 5 / 4, "141": 1.41,
}

# Resize-handle ids, clockwise from top-left.
TL, T, TR, R, BR, B, BL, L = range(8)
_LEFT = {TL, L, BL}
_RIGHT = {TR, R, BR}
_TOP = {TL, T, TR}
_BOTTOM = {BL, B, BR}


def scene_width(aspect: str) -> float:
    return SCENE_H * _ASPECT_RATIO.get(aspect, 16 / 9)


_CM_TO_PT = 72.27 / 2.54
_BEAMER_H_PT = 272.8        # beamer slide height (~96 mm) for the presets


def page_size_px(aspect: str, w_cm: float = 0.0, h_cm: float = 0.0):
    """Return (page_w_px, page_h_px, font_scale). Height is fixed at
    SCENE_H; width follows the aspect or custom cm size. font_scale turns
    a pt font size into canvas pixels for the page's real height."""
    if w_cm > 0 and h_cm > 0:
        ratio = w_cm / h_cm
        h_pt = h_cm * _CM_TO_PT
    else:
        ratio = _ASPECT_RATIO.get(aspect, 16 / 9)
        h_pt = _BEAMER_H_PT
    return SCENE_H * ratio, SCENE_H, SCENE_H / h_pt


class BoxItem(QGraphicsObject):
    """A movable, eight-handle-resizable rectangle bound to a model
    object. Coordinates are 0..1 within the page's content area (page
    minus the deck's gap); this maps them to scene pixels. Subclasses
    paint the content."""

    geometryChanged = Signal()
    doubleClicked = Signal()
    lockToggled = Signal()

    def __init__(self, obj, page_w: float, page_h: float, gap: float = 0.0,
                 font_scale: float = FONT_SCALE):
        super().__init__()
        self.obj = obj
        self._pw = page_w
        self._ph = page_h
        self._gap = gap
        self._font_scale = font_scale
        self._hover = False
        cw, ch, ox, oy = self._content()
        self._rect = QRectF(0, 0, max(MIN_PX, obj.w * cw),
                            max(MIN_PX, obj.h * ch))
        self.setPos(ox + obj.x * cw, oy + obj.y * ch)
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self._resize_handle: int | None = None
        self._press_scene = QPointF()
        self._start_rect = QRectF()
        self._start_pos = QPointF()
        self._apply_lock()

    def _aspect_locked(self) -> bool:
        return False

    def _is_locked(self) -> bool:
        return bool(getattr(self.obj, "locked", True))

    def _apply_lock(self) -> None:
        """A locked box is beamer-controlled: it can be selected (to edit or
        unlock) but not dragged or resized."""
        self.setFlag(QGraphicsItem.ItemIsMovable, not self._is_locked())

    def _lock_rect(self) -> QRectF:
        """The clickable lock toggle, on the box's right side near the top."""
        s = 26.0
        r = self._rect
        return QRectF(r.right() - s - 4, r.top() + 4, s, s)

    # -- geometry --------------------------------------------------
    def boundingRect(self) -> QRectF:
        m = HANDLE + 1
        return self._rect.adjusted(-m, -m, m, m)

    def _handle_rects(self) -> dict[int, QRectF]:
        r = self._rect
        cx, cy = r.center().x(), r.center().y()
        pts = {
            TL: (r.left(), r.top()), T: (cx, r.top()), TR: (r.right(), r.top()),
            R: (r.right(), cy), BR: (r.right(), r.bottom()),
            B: (cx, r.bottom()), BL: (r.left(), r.bottom()), L: (r.left(), cy),
        }
        return {h: QRectF(x - HANDLE, y - HANDLE, 2 * HANDLE, 2 * HANDLE)
                for h, (x, y) in pts.items()}

    def _handle_at(self, pos: QPointF) -> int | None:
        # Locked boxes can still be *resized* (e.g. to size a picture or set
        # a column's width) — they just can't be dragged to a new position.
        for h, rect in self._handle_rects().items():
            if rect.contains(pos):
                return h
        return None

    # -- mouse -----------------------------------------------------
    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event):
        if self._lock_rect().contains(event.pos()):
            self.setCursor(Qt.PointingHandCursor)
            super().hoverMoveEvent(event)
            return
        h = self._handle_at(event.pos()) if self.isSelected() else None
        cursors = {
            TL: Qt.SizeFDiagCursor, BR: Qt.SizeFDiagCursor,
            TR: Qt.SizeBDiagCursor, BL: Qt.SizeBDiagCursor,
            T: Qt.SizeVerCursor, B: Qt.SizeVerCursor,
            L: Qt.SizeHorCursor, R: Qt.SizeHorCursor,
        }
        default = Qt.ArrowCursor if self._is_locked() else Qt.SizeAllCursor
        self.setCursor(cursors.get(h, default))
        super().hoverMoveEvent(event)

    def toggle_lock(self) -> None:
        self.obj.locked = not self._is_locked()
        self._apply_lock()
        self.update()
        self.lockToggled.emit()

    def mousePressEvent(self, event):
        # The lock badge is always visible, so it's always clickable — it's
        # the only control on a locked box.
        if self._lock_rect().contains(event.pos()):
            self.toggle_lock()
            event.accept()
            return
        h = self._handle_at(event.pos()) if self.isSelected() else None
        if h is not None:
            self._resize_handle = h
            self._press_scene = event.scenePos()
            self._start_rect = QRectF(self._rect)
            self._start_pos = self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_handle is None:
            super().mouseMoveEvent(event)
            return
        d = event.scenePos() - self._press_scene
        x, y = self._start_pos.x(), self._start_pos.y()
        w, h = self._start_rect.width(), self._start_rect.height()
        hd = self._resize_handle
        if hd in _LEFT:
            x += d.x(); w -= d.x()
        if hd in _RIGHT:
            w += d.x()
        if hd in _TOP:
            y += d.y(); h -= d.y()
        if hd in _BOTTOM:
            h += d.y()
        if w < MIN_PX:
            if hd in _LEFT:
                x = self._start_pos.x() + self._start_rect.width() - MIN_PX
            w = MIN_PX
        if h < MIN_PX:
            if hd in _TOP:
                y = self._start_pos.y() + self._start_rect.height() - MIN_PX
            h = MIN_PX
        # Locked aspect (e.g. pictures): corner drags keep the box ratio.
        if self._aspect_locked() and hd in (TL, TR, BL, BR) \
                and self._start_rect.height() > 0:
            ratio = self._start_rect.width() / self._start_rect.height()
            h = max(MIN_PX, w / ratio)
            if hd in _TOP:
                y = self._start_pos.y() + self._start_rect.height() - h
        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, w, h)
        self.setPos(x, y)
        self.update()
        self._write_geometry()
        self.geometryChanged.emit()

    def mouseReleaseEvent(self, event):
        self._resize_handle = None
        self._write_geometry()
        self.geometryChanged.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        # PowerPoint-style: double-click edits the object in place.
        self.doubleClicked.emit()
        event.accept()

    def scene_rect(self) -> QRectF:
        """The box's rectangle in scene coordinates (for placing an
        in-place editor over it)."""
        return QRectF(self.pos().x(), self.pos().y(),
                      self._rect.width(), self._rect.height())

    def _content(self):
        """Content area in scene px: (width, height, origin_x, origin_y)."""
        g = self._gap
        return ((1 - 2 * g) * self._pw, (1 - 2 * g) * self._ph,
                g * self._pw, g * self._ph)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            # Keep the box on the page (it may sit within the gap margin).
            nx = min(max(0.0, value.x()), self._pw - self._rect.width())
            ny = min(max(0.0, value.y()), self._ph - self._rect.height())
            return QPointF(nx, ny)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._write_geometry()
            self.geometryChanged.emit()
        return super().itemChange(change, value)

    def _write_geometry(self) -> None:
        cw, ch, ox, oy = self._content()
        self.obj.x = round((self.pos().x() - ox) / cw, 4)
        self.obj.y = round((self.pos().y() - oy) / ch, 4)
        self.obj.w = round(self._rect.width() / cw, 4)
        self.obj.h = round(self._rect.height() / ch, 4)

    def sync_from_model(self) -> None:
        """Re-read geometry from the model (after spinbox edits)."""
        cw, ch, ox, oy = self._content()
        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, max(MIN_PX, self.obj.w * cw),
                            max(MIN_PX, self.obj.h * ch))
        self.setPos(ox + self.obj.x * cw, oy + self.obj.y * ch)
        self.update()

    # -- painting helpers -----------------------------------------
    def _paint_selection(self, painter):
        locked = self._is_locked()
        if not self.isSelected():
            painter.setPen(QPen(QColor(150, 150, 150), 0, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._rect)
            self._paint_lock(painter)        # always show lock state
            return
        painter.setPen(QPen(QColor(40, 120, 220), 0, Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self._rect)
        # Resize handles are shown even when locked (resize is allowed; only
        # moving is blocked), so a locked picture's size can be set.
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(QPen(QColor(40, 120, 220), 0))
        for rect in self._handle_rects().values():
            painter.drawRect(rect)
        self._paint_lock(painter)

    def _paint_decoration(self, painter, border_only=False):
        """Box fill + border rectangle (sharp or rounded), shared by every
        box type. No-op unless a fill or border colour is set."""
        o = self.obj
        fill = "" if border_only else getattr(o, "fill", "")
        bc = getattr(o, "border_color", "")
        bw = getattr(o, "border_width", 1.0)
        rounded = getattr(o, "corner", "sharp") == "rounded"
        if not fill and not bc:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, rounded)
        painter.setBrush(QColor(fill) if fill else Qt.NoBrush)
        if bc and bw > 0:
            painter.setPen(QPen(QColor(bc), max(1.0, bw * 1.5)))
        else:
            painter.setPen(Qt.NoPen)
        if rounded:
            painter.drawRoundedRect(self._rect, 10, 10)
        else:
            painter.drawRect(self._rect)
        painter.restore()

    def _paint_lock(self, painter):
        """A bold padlock badge so the lock state reads at a glance —
        amber & closed when locked, green & open when freely positioned.
        Click it to toggle."""
        r = self._lock_rect()
        locked = self._is_locked()
        accent = QColor(217, 119, 6) if locked else QColor(34, 160, 86)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Filled, high-contrast disc with a white padlock drawn on top.
        painter.setBrush(QBrush(QColor(0, 0, 0, 40)))      # soft shadow
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(r.translated(0, 1))
        painter.setBrush(QBrush(accent))
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.drawEllipse(r)
        white = QColor(255, 255, 255)
        # Body of the padlock.
        bw, bh = r.width() * 0.46, r.height() * 0.30
        body = QRectF(r.center().x() - bw / 2,
                      r.center().y() - bh / 2 + r.height() * 0.08, bw, bh)
        painter.setBrush(QBrush(white))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(body, 1.5, 1.5)
        # Shackle: a closed loop when locked, lifted to the side when open.
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(white, 2.0))
        sw = bw * 0.74
        sx = r.center().x() - sw / 2
        sy = body.top() - sw * 0.62
        arc = QRectF(sx, sy, sw, sw)
        if locked:
            painter.drawArc(arc, 0, 180 * 16)
            painter.drawLine(QPointF(arc.left(), arc.center().y()),
                             QPointF(arc.left(), body.top()))
            painter.drawLine(QPointF(arc.right(), arc.center().y()),
                             QPointF(arc.right(), body.top()))
        else:
            painter.drawArc(arc.translated(sw * 0.5, 0), 20 * 16, 180 * 16)
            painter.drawLine(QPointF(arc.left(), arc.center().y()),
                             QPointF(arc.left(), body.top()))
        painter.restore()


class TextBoxItem(BoxItem):
    def boundingRect(self):
        # Allow text taller than the box (e.g. a big heading in a short box)
        # to render without being clipped or leaving paint artifacts — it
        # flows downward from the top, just like the textblock in the PDF.
        r = super().boundingRect()
        return QRectF(r.x(), r.y(), r.width(), r.height() * 2 + 40)

    def paint(self, painter, option, widget=None):
        obj: SlideText = self.obj
        self._paint_decoration(painter)

        # A pure math box ($…$, \[…\]) is rendered as real maths, like the
        # equation editor's preview, rather than shown as raw LaTeX.
        inner = _math_only(obj.text)
        if inner is not None:
            from . import equations
            pm = equations.render_live_preview(inner, 24)
            if pm is not None and not pm.isNull():
                area = self._rect.adjusted(4, 2, -4, -2)
                scaled = pm.scaled(area.size().toSize(), Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
                x = self._rect.x() + (self._rect.width() - scaled.width()) / 2
                y = self._rect.y() + (self._rect.height() - scaled.height()) / 2
                painter.drawPixmap(QPointF(x, y), scaled)
                self._paint_selection(painter)
                return

        # A beamer block: coloured title bar + tinted body, text sits below.
        body_top = self._rect.y()
        if getattr(obj, "block", ""):
            body_top = self._paint_block(painter)

        font = QFont("Helvetica")
        font.setPixelSize(max(6, int(obj.font_pt * self._font_scale)))
        # Helvetica is ~10% wider per glyph than the PDF's Latin Modern, so
        # the same text wrapped a line early on the canvas. Condensing the
        # width (height unchanged) lines the canvas wrap up with the PDF.
        font.setStretch(90)
        font.setBold(obj.bold)
        font.setItalic(obj.italic)

        doc = QTextDocument()
        doc.setDefaultFont(font)
        align = {"center": Qt.AlignHCenter, "right": Qt.AlignRight}.get(
            obj.align, Qt.AlignLeft)
        opt = QTextOption(align)
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(opt)
        colour = obj.color or "#000000"
        doc.setHtml(f'<div style="color:{colour}">{latex_to_html(obj.text)}</div>')
        self._underline_misspelled(doc)
        inner = QRectF(self._rect.x() + 6, body_top + 2,
                       self._rect.width() - 12,
                       self._rect.bottom() - body_top - 2)
        doc.setTextWidth(inner.width())

        painter.save()
        painter.translate(inner.topLeft())
        # Clip generously below so glyphs/descenders and overflow aren't cut.
        painter.setClipRect(QRectF(0, -2, inner.width(),
                                   max(inner.height(), doc.size().height()) + 6))
        doc.drawContents(painter)
        painter.restore()
        self._paint_selection(painter)

    _BLOCK_COLORS = {"block": QColor("#3b5ba9"),
                     "alertblock": QColor("#b03a3a"),
                     "exampleblock": QColor("#2e7d4f")}

    def _paint_block(self, painter) -> float:
        """Draw the block's coloured title bar + tinted body; return the
        y where the body text should start."""
        obj = self.obj
        c = self._BLOCK_COLORS.get(obj.block, self._BLOCK_COLORS["block"])
        bh = max(16.0, obj.font_pt * self._font_scale * 0.85)
        hdr = QRectF(self._rect.x(), self._rect.y(), self._rect.width(), bh)
        body = QRectF(self._rect.x(), hdr.bottom(), self._rect.width(),
                      max(0.0, self._rect.bottom() - hdr.bottom()))
        painter.save()
        painter.fillRect(body, QColor(c.red(), c.green(), c.blue(), 28))
        painter.fillRect(hdr, c)
        painter.setPen(QColor("#ffffff"))
        f = QFont("Helvetica"); f.setPixelSize(max(8, int(bh * 0.6)))
        f.setBold(True); painter.setFont(f)
        painter.drawText(hdr.adjusted(6, 0, -6, 0),
                         int(Qt.AlignVCenter | Qt.AlignLeft),
                         obj.block_title or "")
        painter.restore()
        return hdr.bottom()

    def _underline_misspelled(self, doc):
        from . import spellcheck
        if not (spellcheck.enabled() and spellcheck.available()):
            return
        spans = spellcheck.misspelled_spans(doc.toPlainText())
        if not spans:
            return
        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
        fmt.setUnderlineColor(QColor(220, 40, 40))
        cur = QTextCursor(doc)
        for start, end in spans:
            cur.setPosition(start)
            cur.setPosition(end, QTextCursor.KeepAnchor)
            cur.mergeCharFormat(fmt)


class PictureBoxItem(BoxItem):
    def __init__(self, obj, page_w, page_h, gap=0.0, font_scale=FONT_SCALE):
        super().__init__(obj, page_w, page_h, gap, font_scale)
        self._pix: QPixmap | None = None
        self._pix_path = None

    def _pixmap(self) -> QPixmap | None:
        if self.obj.path != self._pix_path:
            self._pix_path = self.obj.path
            pm = QPixmap(self.obj.path) if self.obj.path else QPixmap()
            self._pix = pm if not pm.isNull() else None
        return self._pix

    def _aspect_locked(self):
        return bool(self.obj.keep_aspect)

    def _source_rect(self, pm: QPixmap) -> QRectF:
        """The kept (un-cropped) region of the source pixmap."""
        o = self.obj
        cl = max(0.0, min(0.9, getattr(o, "crop_l", 0.0)))
        ct = max(0.0, min(0.9, getattr(o, "crop_t", 0.0)))
        cr = max(0.0, min(0.9, getattr(o, "crop_r", 0.0)))
        cb = max(0.0, min(0.9, getattr(o, "crop_b", 0.0)))
        w, h = pm.width(), pm.height()
        return QRectF(cl * w, ct * h,
                      max(1.0, (1 - cl - cr) * w), max(1.0, (1 - ct - cb) * h))

    def paint(self, painter, option, widget=None):
        self._paint_decoration(painter)
        pm = self._pixmap()
        if pm is not None:
            src = self._source_rect(pm)
            # Target rect inside the box, honouring the *cropped* aspect.
            if self.obj.keep_aspect and src.height() > 0:
                ratio = src.width() / src.height()
                tw, th = self._rect.width(), self._rect.height()
                if tw / th > ratio:
                    tw = th * ratio
                else:
                    th = tw / ratio
            else:
                tw, th = self._rect.width(), self._rect.height()
            cx = self._rect.x() + self._rect.width() / 2
            cy = self._rect.y() + self._rect.height() / 2
            target = QRectF(cx - tw / 2, cy - th / 2, tw, th)
            painter.save()
            painter.setOpacity(max(0.0, min(1.0, self.obj.opacity)))
            angle = getattr(self.obj, "rotation", 0.0)
            if angle:
                painter.translate(cx, cy)
                painter.rotate(angle)
                painter.translate(-cx, -cy)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(target, pm, src)
            painter.restore()
        else:
            painter.fillRect(self._rect, QColor(235, 235, 235))
            painter.setPen(QPen(QColor(150, 150, 150)))
            painter.drawText(self._rect, Qt.AlignCenter, "Image\n(set path)")
        self._paint_selection(painter)


class TableBoxItem(BoxItem):
    """A grid of cells stretched to the box. Double-clicking a cell asks
    the window to edit that cell in place."""

    cellDoubleClicked = Signal(int, int)

    def _dims(self):
        rows = self.obj.rows or [[""]]
        nrows = len(rows)
        ncols = max((len(r) for r in rows), default=1)
        return rows, nrows, ncols

    def cell_scene_rect(self, r: int, c: int) -> QRectF:
        _, nrows, ncols = self._dims()
        cw = self._rect.width() / ncols
        ch = self._rect.height() / nrows
        return QRectF(self.pos().x() + c * cw, self.pos().y() + r * ch, cw, ch)

    def _cell_at(self, pos: QPointF):
        _, nrows, ncols = self._dims()
        cw = self._rect.width() / ncols
        ch = self._rect.height() / nrows
        c = min(ncols - 1, max(0, int(pos.x() // cw)))
        r = min(nrows - 1, max(0, int(pos.y() // ch)))
        return r, c

    def mouseDoubleClickEvent(self, event):
        r, c = self._cell_at(event.pos())
        self.cellDoubleClicked.emit(r, c)
        event.accept()

    def paint(self, painter, option, widget=None):
        obj: SlideTable = self.obj
        rows, nrows, ncols = self._dims()
        cw = self._rect.width() / ncols
        ch = self._rect.height() / nrows
        painter.fillRect(self._rect, QColor(getattr(obj, "fill", "") or "#FFFFFF"))
        # Coloured header row (KherveTeX-style orange).
        if obj.header and nrows >= 1:
            painter.fillRect(QRectF(self._rect.x(), self._rect.y(),
                                    self._rect.width(), ch),
                             QColor(TABLE_HEADER_BG))
        if obj.border:
            painter.setPen(QPen(QColor(TABLE_RULE), 0))
            for i in range(ncols + 1):
                x = self._rect.x() + i * cw
                painter.drawLine(QPointF(x, self._rect.y()),
                                 QPointF(x, self._rect.bottom()))
            for j in range(nrows + 1):
                y = self._rect.y() + j * ch
                painter.drawLine(QPointF(self._rect.x(), y),
                                 QPointF(self._rect.right(), y))
        base_font = QFont("Helvetica")
        base_font.setPixelSize(max(6, int(obj.font_pt * self._font_scale)))
        for r in range(nrows):
            is_head = obj.header and r == 0
            font = QFont(base_font)
            font.setBold(is_head)
            painter.setFont(font)
            painter.setPen(QPen(QColor(TABLE_HEADER_FG if is_head
                                       else (obj.color or "#000000"))))
            for c in range(ncols):
                text = rows[r][c] if c < len(rows[r]) else ""
                cell = QRectF(self._rect.x() + c * cw, self._rect.y() + r * ch,
                              cw, ch)
                painter.drawText(cell.adjusted(5, 1, -5, -1),
                                 int(Qt.AlignVCenter | Qt.AlignLeft
                                     | Qt.TextWordWrap), text)
        self._paint_decoration(painter, border_only=True)
        self._paint_selection(painter)


class LineBoxItem(BoxItem):
    """A line / arrow along the box diagonal (top-left to bottom-right)."""

    def __init__(self, obj, page_w, page_h, gap=0.0, font_scale=FONT_SCALE):
        super().__init__(obj, page_w, page_h, gap, font_scale)
        self._set_exact_rect()

    def _set_exact_rect(self):
        # Lines aren't floored to MIN_PX, so a flat line stays flat and the
        # canvas matches the serialized geometry exactly.
        cw, ch, _, _ = self._content()
        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, self.obj.w * cw, self.obj.h * ch)

    def sync_from_model(self):
        super().sync_from_model()
        self._set_exact_rect()

    def _arrowhead(self, painter, frm, to, wpx):
        ang = math.atan2(to.y() - frm.y(), to.x() - frm.x())
        size = max(8.0, wpx * 4)
        a1, a2 = ang + math.radians(150), ang - math.radians(150)
        poly = QPolygonF([
            to,
            QPointF(to.x() + size * math.cos(a1), to.y() + size * math.sin(a1)),
            QPointF(to.x() + size * math.cos(a2), to.y() + size * math.sin(a2)),
        ])
        painter.setBrush(QColor(self.obj.color or "#000000"))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(poly)

    def paint(self, painter, option, widget=None):
        obj: SlideLine = self.obj
        p1 = QPointF(0, 0)
        p2 = QPointF(self._rect.width(), self._rect.height())
        wpx = max(1.0, obj.width_pt * self._font_scale)
        pen = QPen(QColor(obj.color or "#000000"))
        pen.setWidthF(wpx)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(p1, p2)
        if obj.arrow_end:
            self._arrowhead(painter, p1, p2, wpx)
        if obj.arrow_start:
            self._arrowhead(painter, p2, p1, wpx)
        self._paint_selection(painter)


def make_item(obj, page_w, page_h, gap=0.0, font_scale=FONT_SCALE) -> BoxItem:
    if isinstance(obj, SlideText):
        return TextBoxItem(obj, page_w, page_h, gap, font_scale)
    if isinstance(obj, SlideTable):
        return TableBoxItem(obj, page_w, page_h, gap, font_scale)
    if isinstance(obj, SlideLine):
        return LineBoxItem(obj, page_w, page_h, gap, font_scale)
    return PictureBoxItem(obj, page_w, page_h, gap, font_scale)


class SlideScene(QGraphicsScene):
    def __init__(self, aspect="169"):
        super().__init__()
        self.aspect = aspect
        self.page_color = "#FFFFFF"   # current slide background
        self.gap = 0.0
        self.page_w = scene_width(aspect)
        self.page_h = SCENE_H
        self._set_rect()

    def _set_rect(self):
        self.setSceneRect(0, 0, self.page_w, self.page_h)

    def set_aspect(self, aspect):
        self.aspect = aspect
        self.page_w = scene_width(aspect)
        self.page_h = SCENE_H
        self._set_rect()

    def set_page(self, page_w, page_h, gap):
        self.page_w = page_w
        self.page_h = page_h
        self.gap = gap
        self._set_rect()

    def drawBackground(self, painter, rect):
        # Fill the whole exposed area (incl. the margins beyond the page)
        # with grey "desk", then lay the white page on top with a soft
        # shadow and a thin edge. Done here — not via the view's
        # backgroundBrush — because setting that brush stops the view from
        # ever calling this, leaving the page unpainted.
        painter.fillRect(rect, QColor("#9aa0a6"))
        r = self.sceneRect()
        painter.fillRect(r.translated(7, 7), QColor(0, 0, 0, 45))
        painter.fillRect(r, QColor(self.page_color or "#FFFFFF"))
        painter.setPen(QPen(QColor(150, 150, 150), 0))
        painter.drawRect(r)
        if self.gap > 0:
            # Dashed guide showing the content "safe area".
            g = self.gap
            guide = QRectF(g * self.page_w, g * self.page_h,
                           (1 - 2 * g) * self.page_w, (1 - 2 * g) * self.page_h)
            painter.setPen(QPen(QColor(120, 160, 210), 0, Qt.DashLine))
            painter.drawRect(guide)


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".pdf")


def _dropped_image(mime) -> str | None:
    if mime is not None and mime.hasUrls():
        for url in mime.urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(_IMAGE_EXTS):
                return url.toLocalFile()
    return None


class SlideView(QGraphicsView):
    """Canvas view with mouse-wheel zoom (zoom around the cursor) and
    drag-and-drop of image files. Plain fit-to-window is the default;
    scrolling the wheel switches to free zoom, and fit_to_window() snaps
    back."""

    _MIN = 0.1
    _MAX = 12.0

    imageDropped = Signal(str, QPointF)   # (local path, scene position)
    deleteRequested = Signal()            # Delete pressed with a selection
    contextMenuRequested = Signal(object, object)   # (globalPos, scenePos)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setAcceptDrops(True)
        self.fit_mode = True

    def keyPressEvent(self, event):
        # Delete the selected object — but NOT while editing text: then the
        # inline editor is the scene's focus item and must get Delete itself.
        if event.key() == Qt.Key_Delete and self.scene() \
                and self.scene().selectedItems() \
                and self.scene().focusItem() is None:
            self.deleteRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if _dropped_image(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if _dropped_image(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        path = _dropped_image(event.mimeData())
        if path:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.imageDropped.emit(path, scene_pos)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def contextMenuEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        self.contextMenuRequested.emit(event.globalPos(), scene_pos)
        event.accept()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        scale = self.transform().m11() * factor
        if scale < self._MIN or scale > self._MAX:
            event.accept()
            return
        self.fit_mode = False
        self.scale(factor, factor)
        event.accept()

    def zoom_by(self, factor):
        scale = self.transform().m11() * factor
        if self._MIN <= scale <= self._MAX:
            self.fit_mode = False
            self.scale(factor, factor)

    def fit_to_window(self):
        if self.scene() is not None:
            self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)
            self.fit_mode = True


def render_thumbnail(slide: Slide, deck, width_px: int = 160) -> QPixmap:
    """Render *slide* to a small pixmap for the navigator — reuses the
    same item painting as the live canvas so the thumbnail matches."""
    pw, ph, fs = page_size_px(deck.aspect, deck.page_w_cm, deck.page_h_cm)
    scene = SlideScene(deck.aspect)
    scene.set_page(pw, ph, deck.gap)
    scene.page_color = slide.bg or "#FFFFFF"
    for obj in slide.objects:
        item = make_item(obj, pw, ph, deck.gap, fs)
        item.setSelected(False)
        scene.addItem(item)
    height_px = int(width_px * ph / pw)
    pm = QPixmap(width_px, height_px)
    pm.fill(QColor("#FFFFFF"))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    scene.render(painter, QRectF(0, 0, width_px, height_px), scene.sceneRect())
    painter.end()
    return pm
