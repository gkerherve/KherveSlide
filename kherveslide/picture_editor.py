"""Interactive picture editor: crop, rotate and apply PowerPoint-style
effects (corrections, colour, artistic, transparency/fade, soft edges,
glow, reflection) to a :class:`SlidePicture`.

The crop rectangle is defined on the *unrotated* image (the serializer
trims first, then rotates), so the crop canvas never rotates — rotation
is a numeric control with a small live preview of the final result.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QImage, QPainter, QPen, QPixmap, QTransform,
)
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSlider, QTabWidget, QToolBar, QVBoxLayout,
    QWidget,
)

from . import icons
from . import image_effects

_HANDLE = 7.0
_MIN_FRAC = 0.05          # the crop must keep at least this fraction each axis


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class _CropCanvas(QWidget):
    """Shows the image fit-to-widget with a draggable / resizable crop box.
    Crop is stored as fractions trimmed from (left, top, right, bottom)."""

    changed = Signal()

    def __init__(self, pixmap: QPixmap | None, crop, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 320)
        self._pm = pixmap
        self.l, self.t, self.r, self.b = crop
        self._drag = None            # which handle / 'move'
        self._press = QPointF()
        self._start = None
        self.setMouseTracking(True)

    def set_pixmap(self, pm: QPixmap | None):
        self._pm = pm
        self.update()

    def crop(self):
        return (round(self.l, 4), round(self.t, 4),
                round(self.r, 4), round(self.b, 4))

    def reset(self):
        self.l = self.t = self.r = self.b = 0.0
        self.changed.emit()
        self.update()

    # -- geometry ---------------------------------------------------
    def _img_rect(self) -> QRectF:
        """Where the whole image is drawn inside the widget (fit, centred)."""
        if self._pm is None or self._pm.isNull():
            return QRectF(0, 0, self.width(), self.height())
        iw, ih = self._pm.width(), self._pm.height()
        ww, wh = self.width() - 20, self.height() - 20
        scale = min(ww / iw, wh / ih)
        w, h = iw * scale, ih * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _crop_rect(self) -> QRectF:
        ir = self._img_rect()
        return QRectF(ir.x() + self.l * ir.width(),
                      ir.y() + self.t * ir.height(),
                      (1 - self.l - self.r) * ir.width(),
                      (1 - self.t - self.b) * ir.height())

    def _handles(self) -> dict:
        c = self._crop_rect()
        cx, cy = c.center().x(), c.center().y()
        return {
            "tl": QPointF(c.left(), c.top()), "tr": QPointF(c.right(), c.top()),
            "bl": QPointF(c.left(), c.bottom()),
            "br": QPointF(c.right(), c.bottom()),
            "t": QPointF(cx, c.top()), "b": QPointF(cx, c.bottom()),
            "l": QPointF(c.left(), cy), "r": QPointF(c.right(), cy),
        }

    def _hit(self, pos: QPointF):
        for name, pt in self._handles().items():
            if (abs(pos.x() - pt.x()) <= _HANDLE
                    and abs(pos.y() - pt.y()) <= _HANDLE):
                return name
        if self._crop_rect().contains(pos):
            return "move"
        return None

    # -- mouse ------------------------------------------------------
    def mousePressEvent(self, e):
        self._drag = self._hit(e.position())
        self._press = e.position()
        self._start = (self.l, self.t, self.r, self.b)

    def mouseMoveEvent(self, e):
        if self._drag is None:
            self.setCursor(Qt.SizeAllCursor if self._hit(e.position()) == "move"
                           else (Qt.ArrowCursor if self._hit(e.position()) is None
                                 else Qt.CrossCursor))
            return
        ir = self._img_rect()
        if ir.width() <= 0 or ir.height() <= 0:
            return
        dx = (e.position().x() - self._press.x()) / ir.width()
        dy = (e.position().y() - self._press.y()) / ir.height()
        l, t, r, b = self._start
        if self._drag == "move":
            dx = _clamp(dx, -l, r)
            dy = _clamp(dy, -t, b)
            l, r = l + dx, r - dx
            t, b = t + dy, b - dy
        else:
            if "l" in self._drag:
                l = _clamp(l + dx, 0.0, 1 - r - _MIN_FRAC)
            if "r" in self._drag:
                r = _clamp(r - dx, 0.0, 1 - l - _MIN_FRAC)
            if "t" in self._drag:
                t = _clamp(t + dy, 0.0, 1 - b - _MIN_FRAC)
            if "b" in self._drag:
                b = _clamp(b - dy, 0.0, 1 - t - _MIN_FRAC)
        self.l, self.t, self.r, self.b = l, t, r, b
        self.changed.emit()
        self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None

    # -- painting ---------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.fillRect(self.rect(), QColor("#2b2b2b"))
        ir = self._img_rect()
        if self._pm is not None and not self._pm.isNull():
            p.drawPixmap(ir, self._pm, QRectF(self._pm.rect()))
        else:
            p.setPen(QPen(QColor(180, 180, 180)))
            p.drawText(ir, Qt.AlignCenter, "No image")
            return
        # Dim the trimmed-away border, outline the kept crop.
        cr = self._crop_rect()
        shade = QColor(0, 0, 0, 120)
        p.setPen(Qt.NoPen)
        p.setBrush(shade)
        p.drawRect(QRectF(ir.x(), ir.y(), ir.width(), cr.top() - ir.y()))
        p.drawRect(QRectF(ir.x(), cr.bottom(), ir.width(),
                          ir.bottom() - cr.bottom()))
        p.drawRect(QRectF(ir.x(), cr.top(), cr.left() - ir.x(), cr.height()))
        p.drawRect(QRectF(cr.right(), cr.top(), ir.right() - cr.right(),
                          cr.height()))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(40, 150, 255), 1.5))
        p.drawRect(cr)
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.setPen(QPen(QColor(40, 150, 255), 1))
        for pt in self._handles().values():
            p.drawRect(QRectF(pt.x() - _HANDLE, pt.y() - _HANDLE,
                              2 * _HANDLE, 2 * _HANDLE))


class PictureEditDialog(QDialog):
    """Crop, rotate and (optionally) replace a picture. Read the results
    from :attr:`crop`, :attr:`rotation` and :attr:`path` after ``exec()``."""

    def __init__(self, obj, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit picture")
        self.resize(900, 600)
        self.path = obj.path
        self.effects = {n: getattr(obj, n, v)
                        for n, v in image_effects.EFFECT_FIELDS.items()}
        self.opacity = float(getattr(obj, "opacity", 1.0))
        self._crop0 = (obj.crop_l, obj.crop_t, obj.crop_r, obj.crop_b)
        self.rotation = float(getattr(obj, "rotation", 0.0))
        self._src = QPixmap(self.path) if self.path else QPixmap()

        self._canvas = _CropCanvas(
            self._src if not self._src.isNull() else None,
            (obj.crop_l, obj.crop_t, obj.crop_r, obj.crop_b), self)
        self._canvas.changed.connect(self._update_preview)

        root = QVBoxLayout(self)

        tb = QToolBar()
        tb.setIconSize(QSize(22, 22))
        tb.addAction(icons.rotate_left(), "Rotate left 90°",
                     lambda: self._nudge(-90))
        tb.addAction(icons.rotate_right(), "Rotate right 90°",
                     lambda: self._nudge(90))
        tb.addWidget(QLabel(" Rot° "))
        self._rot = QDoubleSpinBox()
        self._rot.setRange(-180.0, 180.0)
        self._rot.setSingleStep(1.0)
        self._rot.setValue(self.rotation)
        self._rot.valueChanged.connect(self._on_rot)
        tb.addWidget(self._rot)
        tb.addSeparator()
        tb.addAction(icons.crop_reset(), "Reset crop", self._canvas.reset)
        tb.addSeparator()
        tb.addAction(icons.file_open(), "Replace image…", self._replace)
        tb.addAction(icons.paste(), "Paste from clipboard", self._paste)
        tb.addAction(icons.remove_bg(), "Make the background transparent",
                     self._remove_background)
        tb.addAction(icons.drawing(), "Draw / annotate (pen, lines, fill)…",
                     self._annotate)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addWidget(QLabel("Result: "))
        self._preview = QLabel()
        self._preview.setFixedSize(150, 110)
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setStyleSheet("border:1px solid #888;background:#fff;")
        tb.addWidget(self._preview)
        root.addWidget(tb)            # toolbar on top
        body = QHBoxLayout()
        body.addWidget(self._canvas, 1)
        body.addWidget(self._build_effects(), 0)
        root.addLayout(body, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self._update_preview()

    # ------------------------------------------------------------ effects
    def _build_effects(self) -> QWidget:
        """The Picture Format panel: PowerPoint's picture effects grouped
        as tabs. Every control writes into :attr:`effects`."""
        self._fx_widgets = {}
        tabs = QTabWidget()
        tabs.setMinimumWidth(290)

        def page(rows):
            w = QWidget()
            f = QFormLayout(w)
            for label, widget in rows:
                f.addRow(label, widget)
            return w

        def slider(name, lo, hi, scale=100):
            s = QSlider(Qt.Horizontal)
            s.setRange(int(lo * scale), int(hi * scale))
            s.setValue(int(round(self.effects[name] * scale)))
            s.valueChanged.connect(
                lambda v, n=name: self._set_fx(n, v / scale))
            self._fx_widgets[name] = (s, scale)
            return s

        def combo(name, items):
            c = QComboBox()
            for value, text in items:
                c.addItem(text, value)
            c.setCurrentIndex(max(0, c.findData(self.effects[name])))
            c.currentIndexChanged.connect(
                lambda _i, n=name, c=c: self._set_fx(n, c.currentData()))
            self._fx_widgets[name] = (c, None)
            return c

        def colour(name, default):
            b = QPushButton()
            self._paint_swatch(b, self.effects[name] or default)

            def pick(_=False, n=name, b=b):
                c = QColorDialog.getColor(
                    QColor(self.effects[n] or default), self, "Colour")
                if c.isValid():
                    self._paint_swatch(b, c.name())
                    self._set_fx(n, c.name())
            b.clicked.connect(pick)
            self._fx_widgets[name] = (b, default)
            return b

        tabs.addTab(page([
            ("Brightness", slider("brightness", -1, 1)),
            ("Contrast", slider("contrast", -1, 1)),
            ("Sharpen / soften", slider("sharpness", -1, 1)),
        ]), "Corrections")
        tabs.addTab(page([
            ("Saturation", slider("saturation", 0, 2)),
            ("Temperature", slider("temperature", -1, 1)),
            ("Recolour", combo("recolor", [
                ("", "None"), ("grayscale", "Grayscale"),
                ("sepia", "Sepia"), ("washout", "Washout"),
                ("bw", "Black and white"), ("duotone", "Duotone")])),
            ("Duotone colour", colour("recolor_color", "#1f4e79")),
        ]), "Colour")
        tabs.addTab(page([
            ("Effect", combo("artistic", [
                ("", "None"), ("blur", "Blur"),
                ("pencil", "Pencil sketch"),
                ("line_drawing", "Line drawing"), ("mosaic", "Mosaic"),
                ("posterize", "Posterize"), ("emboss", "Emboss"),
                ("glow_edges", "Glowing edges"),
                ("watercolor", "Watercolour")])),
            ("Strength", slider("artistic_amount", 0, 1)),
        ]), "Artistic")
        op = QSlider(Qt.Horizontal)
        op.setRange(0, 100)
        op.setValue(int(round((1 - self.opacity) * 100)))
        op.valueChanged.connect(self._set_transparency)
        self._op_slider = op
        tabs.addTab(page([
            ("Transparency", op),
            ("Fade", combo("fade", [
                ("", "None"), ("left", "From the left"),
                ("right", "From the right"), ("top", "From the top"),
                ("bottom", "From the bottom"),
                ("radial", "Towards the edges")])),
            ("Fade starts", slider("fade_start", 0, 1)),
            ("Fade ends", slider("fade_end", 0, 1)),
            ("Soft edges", slider("soft_edge", 0, 0.5)),
            ("Shape", combo("mask", [
                ("", "Rectangle"), ("ellipse", "Oval"),
                ("rounded", "Rounded rectangle")])),
        ]), "Transparency")
        tabs.addTab(page([
            ("Glow colour", colour("glow_color", "#ffd966")),
            ("Glow size", slider("glow_size", 0, 0.3)),
            ("Reflection", slider("reflection", 0, 1)),
        ]), "Glow && reflection")

        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(tabs, 1)
        reset = QPushButton("Reset all effects")
        reset.clicked.connect(self._reset_effects)
        v.addWidget(reset)
        return box

    @staticmethod
    def _paint_swatch(button, colour):
        button.setStyleSheet(f"background:{colour};min-width:60px;")

    def _set_fx(self, name, value):
        self.effects[name] = value
        if name == "glow_size" and value and not self.effects["glow_color"]:
            self.effects["glow_color"] = "#ffd966"
        self._update_preview()

    def _set_transparency(self, v):
        self.opacity = 1 - v / 100
        self._update_preview()

    def _reset_effects(self):
        for name, neutral in image_effects.EFFECT_FIELDS.items():
            self.effects[name] = neutral
            w, extra = self._fx_widgets.get(name, (None, None))
            if isinstance(w, QSlider):
                w.blockSignals(True)
                w.setValue(int(round(neutral * extra)))
                w.blockSignals(False)
            elif isinstance(w, QComboBox):
                w.blockSignals(True)
                w.setCurrentIndex(max(0, w.findData(neutral)))
                w.blockSignals(False)
            elif isinstance(w, QPushButton):
                self._paint_swatch(w, extra)
        self._op_slider.setValue(0)
        self.opacity = 1.0
        self._update_preview()

    @property
    def crop(self):
        return self._canvas.crop()

    def _on_rot(self, v):
        self.rotation = float(v)
        self._update_preview()

    def _nudge(self, delta):
        v = self._rot.value() + delta
        while v > 180:
            v -= 360
        while v < -180:
            v += 360
        self._rot.setValue(v)

    def _replace(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.pdf)")
        if path:
            self._set_image(path)

    # Clipboard tag used when a whole picture box is copied from a slide
    # (kept in sync with SlideWindow._OBJ_MIME).
    _OBJ_MIME = "application/x-kherveslide-objects"

    @classmethod
    def _pasted_picture_path(cls, md) -> str | None:
        """If the clipboard holds a picture box copied from a slide, return
        its image path."""
        if md is None or not md.hasFormat(cls._OBJ_MIME):
            return None
        import json
        try:
            objs = json.loads(bytes(md.data(cls._OBJ_MIME)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        for d in objs:
            if d.get("type") == "SlidePicture" and d.get("path"):
                return str(d["path"])
        return None

    def _paste(self):
        """Bring in an image from the clipboard — a picture copied from a
        slide (our object clipboard), a raw bitmap (e.g. a screenshot), or a
        copied image file."""
        md = QApplication.clipboard().mimeData()
        # 1) A picture box copied from a slide: reuse its image path directly.
        path = self._pasted_picture_path(md)
        if path and QPixmap(path).isNull() is False:
            self._set_image(path)
            return
        # 2) A raw image on the clipboard (screenshot, copied from a browser…).
        img = QApplication.clipboard().image()
        if img is not None and not img.isNull():
            d = Path(tempfile.gettempdir()) / "kherveslide_pasted"
            d.mkdir(parents=True, exist_ok=True)
            i = 1
            while (d / f"pasted_{i:03d}.png").exists():
                i += 1
            p = d / f"pasted_{i:03d}.png"
            img.save(str(p), "PNG")
            self._set_image(str(p))
            return
        # 3) A copied image *file* (URL on the clipboard).
        from .canvas import _dropped_image
        fp = _dropped_image(md)
        if fp:
            self._set_image(fp)

    def _annotate(self):
        """Open the drawing dialog with this image as the background, so the
        user can draw on it (pen, lines, shapes, fill); bake the result back."""
        if self._src.isNull() or not self.path:
            return
        from .annotate_dialog import DrawingDialog as AnnotateDialog
        d = Path(tempfile.gettempdir()) / "kherveslide_pasted"
        dlg = AnnotateDialog(d, self, background_path=Path(self.path))
        if dlg.exec() and dlg.saved_path():
            self._set_image(str(dlg.saved_path()))

    def _set_image(self, path):
        self.path = path
        self._src = QPixmap(path)
        self._canvas.set_pixmap(self._src if not self._src.isNull() else None)
        self._update_preview()

    def _remove_background(self):
        """Make the image's background colour transparent — sampled from the
        top-left corner, with a tolerance, written out as a transparent PNG."""
        if self._src.isNull():
            return
        img = self._src.toImage().convertToFormat(QImage.Format_RGBA8888)
        w, h = img.width(), img.height()
        bg = img.pixelColor(0, 0)
        tol = 40
        try:
            import numpy as np
            buf = img.constBits()
            arr = np.frombuffer(buf, np.uint8).reshape((h, img.bytesPerLine()))
            arr = arr[:, :w * 4].reshape((h, w, 4)).copy()
            ref = np.array([bg.red(), bg.green(), bg.blue()], dtype=np.int16)
            diff = np.abs(arr[:, :, :3].astype(np.int16) - ref).max(axis=2)
            arr[diff <= tol, 3] = 0
            data = arr.tobytes()
            out = QImage(data, w, h, QImage.Format_RGBA8888)
        except Exception:
            out = img            # numpy missing: fall back per-pixel (slow)
            for y in range(h):
                for x in range(w):
                    c = out.pixelColor(x, y)
                    if (abs(c.red() - bg.red()) <= tol
                            and abs(c.green() - bg.green()) <= tol
                            and abs(c.blue() - bg.blue()) <= tol):
                        out.setPixelColor(x, y, QColor(0, 0, 0, 0))
        d = Path(tempfile.gettempdir()) / "kherveslide_pasted"
        d.mkdir(parents=True, exist_ok=True)
        i = 1
        while (d / f"nobg_{i:03d}.png").exists():
            i += 1
        p = d / f"nobg_{i:03d}.png"
        out.save(str(p), "PNG")
        self._set_image(str(p))

    def _update_preview(self):
        if self._src.isNull():
            self._preview.clear()
            return
        pm = self._effects_preview()
        if pm is None:
            l, t, r, b = self._canvas.crop()
            w, h = self._src.width(), self._src.height()
            pm = self._src.copy(int(l * w), int(t * h),
                                max(1, int((1 - l - r) * w)),
                                max(1, int((1 - t - b) * h)))
        if self.rotation:
            pm = pm.transformed(
                QTransform().rotate(self.rotation), Qt.SmoothTransformation)
        if self.opacity < 1:
            faded = QPixmap(pm.size())
            faded.fill(Qt.transparent)
            p = QPainter(faded)
            p.setOpacity(max(0.0, self.opacity))
            p.drawPixmap(0, 0, pm)
            p.end()
            pm = faded
        self._preview.setPixmap(pm.scaled(
            self._preview.width() - 4, self._preview.height() - 4,
            Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _effects_preview(self) -> QPixmap | None:
        """The cropped picture with its effects, from a downscaled copy of
        the source so dragging a slider stays responsive."""
        if not self.path:
            return None
        from types import SimpleNamespace
        l, t, r, b = self._canvas.crop()
        probe = SimpleNamespace(path=self.path, crop_l=l, crop_t=t,
                                crop_r=r, crop_b=b, **self.effects)
        if not image_effects.has_effects(probe):
            return None
        try:
            from PIL import Image
            with Image.open(self.path) as im:
                im = im.convert("RGBA")
                im.thumbnail((360, 360))
                out = image_effects.render(im, probe)
        except Exception:
            return None
        data = out.tobytes("raw", "RGBA")
        img = QImage(data, out.width, out.height, QImage.Format_RGBA8888)
        return QPixmap.fromImage(img.copy())
