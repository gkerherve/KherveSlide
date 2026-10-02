"""Windows metafiles (WMF and EMF) → PNG, in pure Python.

XeTeX can't include metafiles, Qt can't read them and macOS has no
converter, yet PowerPoint decks, Origin/Excel graphs and the Windows
clipboard are full of them. This module plays the metafile's drawing
records onto a Pillow canvas: pens, brushes, fonts, lines, polygons,
rectangles, ellipses, arcs, Bézier paths, (rotated) text, embedded DIB
bitmaps, clipping rectangles, save/restore, window/viewport mapping and
(EMF) world transforms. EMF+ comments are skipped — every EMF+ file
carries the plain EMF drawing too.

The drawing is rendered at twice the output size and scaled down, which
antialiases Pillow's hard-edged primitives.

    png_bytes = metafile.to_png(data)          # None if not a metafile
    metafile.convert_file("graph.emf", "graph.png")
"""
from __future__ import annotations

import io
import math
import struct
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

WMF_PLACEABLE = 0x9AC6CDD7
_SUPERSAMPLE = 2
_MAX_SIDE = 2400          # output pixels on the longest side
_DEFAULT_DPI = 200


def kind(data: bytes) -> str:
    """"wmf", "emf" or "" for anything else."""
    if len(data) >= 44 and struct.unpack_from("<I", data, 0)[0] == 1 \
            and data[40:44] == b" EMF":
        return "emf"
    if len(data) >= 4 and struct.unpack_from("<I", data, 0)[0] == WMF_PLACEABLE:
        return "wmf"
    if len(data) >= 18:
        typ, hsize = struct.unpack_from("<HH", data, 0)
        if typ in (1, 2) and hsize == 9:
            return "wmf"
    return ""


def to_image(data: bytes):
    """Render metafile bytes to a Pillow RGBA image (None if unreadable)."""
    k = kind(data)
    try:
        if k == "emf":
            return _EMF(data).render()
        if k == "wmf":
            return _WMF(data).render()
    except Exception:
        return None
    return None


def to_png(data: bytes) -> bytes | None:
    img = to_image(data)
    if img is None:
        return None
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def convert_file(src, dst) -> bool:
    png = to_png(Path(src).read_bytes())
    if png is None:
        return False
    Path(dst).write_bytes(png)
    return True


# ===================================================================== fonts
_FONT_DIRS = [
    "/System/Library/Fonts", "/System/Library/Fonts/Supplemental",
    "/Library/Fonts", str(Path.home() / "Library/Fonts"),
    "C:/Windows/Fonts", "/usr/share/fonts", "/usr/local/share/fonts",
    str(Path.home() / ".fonts"), str(Path.home() / ".local/share/fonts"),
]
# Metric-compatible stand-ins for the usual Office faces.
_FONT_ALIASES = {
    "calibri": ["Calibri", "Carlito"],
    "cambria": ["Cambria", "Caladea"],
    "arial": ["Arial", "Liberation Sans", "Arimo", "Helvetica"],
    "helvetica": ["Helvetica", "Arial", "Liberation Sans"],
    "times new roman": ["Times New Roman", "Liberation Serif", "Tinos",
                        "Times"],
    "courier new": ["Courier New", "Liberation Mono", "Cousine", "Courier"],
    "symbol": ["Symbol"],
}
_font_index: dict | None = None
_font_cache: dict = {}


def _index_fonts() -> dict:
    """lower-case file stem → path, for every TrueType/OpenType font."""
    global _font_index
    if _font_index is not None:
        return _font_index
    idx: dict = {}
    dirs = list(_FONT_DIRS)
    try:                       # tectonic's cache holds Carlito & friends
        from . import latex_fonts
        for root in latex_fonts._candidate_roots():
            dirs += [str(p) for p in Path(root).glob("data/*")]
    except Exception:
        pass
    for d in dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        for f in p.rglob("*"):
            if f.suffix.lower() in (".ttf", ".otf", ".ttc"):
                idx.setdefault(f.stem.lower(), str(f))
    _font_index = idx
    return idx


def _font_file(face: str, bold: bool, italic: bool) -> str | None:
    idx = _index_fonts()
    names = _FONT_ALIASES.get(face.lower(), [face]) + \
        ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans", "Carlito"]
    style = ("bolditalic" if bold and italic else "bold" if bold
             else "italic" if italic else "")
    for name in names:
        base = name.lower().replace(" ", "")
        spaced = name.lower()
        keys = []
        if style:
            keys += [f"{base}-{style}", f"{base}{style}", f"{spaced} {style}",
                     f"{base}-{style[0]}", f"{base}bd" if bold else "",
                     f"{base}i" if italic and not bold else "",
                     f"{base}bi" if bold and italic else ""]
        keys += [base, f"{base}-regular", spaced, f"{spaced} regular"]
        for k in keys:
            if k and k in idx:
                return idx[k]
    return None


def _font(face: str, px: float, bold: bool, italic: bool):
    from PIL import ImageFont
    size = max(1, int(round(px)))
    key = (face.lower(), size, bold, italic)
    if key in _font_cache:
        return _font_cache[key]
    f = None
    path = _font_file(face or "Arial", bold, italic)
    if path:
        try:
            f = ImageFont.truetype(path, size)
        except Exception:
            f = None
    if f is None:
        try:
            f = ImageFont.load_default(size)
        except TypeError:               # Pillow < 10.1
            f = ImageFont.load_default()
    _font_cache[key] = f
    return f


# ================================================================ DIBs
def dib_image(bmi: bytes, bits: bytes | None = None):
    """A Pillow image from a device-independent bitmap: *bmi* is the
    BITMAPINFO (header + colour table), *bits* the pixels (or appended to
    *bmi* when None — packed DIB)."""
    from PIL import Image
    hsize = struct.unpack_from("<I", bmi, 0)[0]
    if hsize == 12:                                  # BITMAPCOREHEADER
        w, h, _, bpp = struct.unpack_from("<HHHH", bmi, 4)
        comp, used, entry = 0, 0, 3
    else:
        w, h, _, bpp, comp = struct.unpack_from("<iiHHI", bmi, 4)
        used = struct.unpack_from("<I", bmi, 32)[0] if hsize >= 36 else 0
        entry = 4
    ncolors = used or (1 << bpp if bpp <= 8 else 0)
    table = ncolors * entry + (12 if comp == 3 and hsize == 40 else 0)
    head = bmi[:hsize + table]
    if bits is None:
        bits = bmi[hsize + table:]
    if comp in (4, 5):                               # embedded JPEG / PNG
        return Image.open(io.BytesIO(bits)).convert("RGBA")
    offset = 14 + len(head)
    bmp = b"BM" + struct.pack("<IHHI", offset + len(bits), 0, 0, offset) \
        + head + bits
    img = Image.open(io.BytesIO(bmp))
    img.load()
    if bpp == 32 and comp == 0:
        # Alpha is usually unused (all zero) in metafile DIBs.
        raw = img.convert("RGBA")
        a = raw.getchannel("A")
        if a.getextrema() == (0, 0):
            raw.putalpha(255)
        return raw
    return img.convert("RGBA")


# ============================================================ device state
@dataclass
class Pen:
    color: tuple = (0, 0, 0)
    width: float = 0.0          # logical units; 0 = one device pixel
    style: int = 0              # 0 solid, 1 dash, 2 dot, 3/4 dashdot, 5 null
    cosmetic: bool = False


@dataclass
class Brush:
    color: tuple = (255, 255, 255)
    style: int = 0              # 0 solid, 1 null, 2 hatched, 3+ pattern
    image: object = None        # pattern bitmap (drawn as its mean colour)


@dataclass
class Font:
    height: float = -12.0
    escapement: float = 0.0     # tenths of a degree, anticlockwise
    weight: int = 400
    italic: bool = False
    underline: bool = False
    face: str = "Arial"


@dataclass
class DC:
    pen: Pen = field(default_factory=Pen)
    brush: Brush = field(default_factory=Brush)
    font: Font = field(default_factory=Font)
    text_color: tuple = (0, 0, 0)
    bk_color: tuple = (255, 255, 255)
    bk_mode: int = 2            # 1 transparent, 2 opaque
    text_align: int = 0
    fill_mode: int = 1          # 1 alternate, 2 winding
    win_org: tuple = (0.0, 0.0)
    win_ext: tuple = (1.0, 1.0)
    vp_org: tuple = (0.0, 0.0)
    vp_ext: tuple = (1.0, 1.0)
    map_mode: int = 1
    world: tuple = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)   # eM11 eM12 eM21 eM22 dx dy
    clip: tuple | None = None   # output-pixel rectangle (l, t, r, b)
    pos: tuple = (0.0, 0.0)


def _colorref(v: int) -> tuple:
    return (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF)


def _bezier(p0, p1, p2, p3, steps=16):
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0]
                    + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1]
                    + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


class _Canvas:
    """Draws in output pixels, honouring the DC's clip rectangle."""

    def __init__(self, w: int, h: int):
        from PIL import Image
        self.w, self.h = w, h
        self.image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        self.layer = None
        self.layer_clip = None
        self.dirty = None

    def _target(self, clip):
        from PIL import Image, ImageDraw
        if clip != self.layer_clip:
            self.flush()
            self.layer_clip = clip
        if clip is None:
            return ImageDraw.Draw(self.image)
        if self.layer is None:
            self.layer = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        self.dirty = True
        return ImageDraw.Draw(self.layer)

    def flush(self):
        if self.layer is not None and self.dirty and self.layer_clip:
            l, t, r, b = (int(round(v)) for v in self.layer_clip)
            l, t = max(0, l), max(0, t)
            r, b = min(self.w, r), min(self.h, b)
            if r > l and b > t:
                part = self.layer.crop((l, t, r, b))
                self.image.alpha_composite(part, (l, t))
        self.layer = None
        self.dirty = None

    def draw(self, clip):
        return self._target(clip)

    def paste(self, img, xy, clip):
        """Composite an RGBA image at *xy*, clipped."""
        from PIL import Image
        x, y = int(round(xy[0])), int(round(xy[1]))
        if clip is not None:
            l, t, r, b = (int(round(v)) for v in clip)
            box = (max(l, x), max(t, y), min(r, x + img.width),
                   min(b, y + img.height))
            if box[2] <= box[0] or box[3] <= box[1]:
                return
            img = img.crop((box[0] - x, box[1] - y, box[2] - x, box[3] - y))
            x, y = box[0], box[1]
        if x >= self.w or y >= self.h or x + img.width <= 0 \
                or y + img.height <= 0:
            return
        self.flush()
        layer = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        layer.paste(img, (x, y))
        self.image.alpha_composite(layer)


class _Player:
    """Shared drawing machinery for the WMF and EMF readers."""

    def __init__(self):
        self.dc = DC()
        self.stack: list[DC] = []
        self.objects: dict = {}
        self.canvas: _Canvas | None = None
        self.scale = (1.0, 1.0)     # reference device units → output px
        self.origin = (0.0, 0.0)    # reference device origin in its units
        self.path: list | None = None    # list of (points, closed) figures
        self.figure: list = []

    # ---- coordinates -------------------------------------------------
    def _device(self, x, y):
        """Logical → reference device units (window/viewport mapping)."""
        d = self.dc
        m = d.world
        x, y = x * m[0] + y * m[2] + m[4], x * m[1] + y * m[3] + m[5]
        if d.map_mode in (7, 8):            # anisotropic / isotropic
            sx = d.vp_ext[0] / (d.win_ext[0] or 1)
            sy = d.vp_ext[1] / (d.win_ext[1] or 1)
            if d.map_mode == 8:
                s = min(abs(sx), abs(sy))
                sx, sy = math.copysign(s, sx), math.copysign(s, sy)
        else:
            sx = sy = self._fixed_scale(d.map_mode)
        return ((x - d.win_org[0]) * sx + d.vp_org[0],
                (y - d.win_org[1]) * sy + d.vp_org[1])

    def _fixed_scale(self, mode):
        return 1.0

    def pt(self, x, y):
        dx, dy = self._device(x, y)
        return ((dx - self.origin[0]) * self.scale[0],
                (dy - self.origin[1]) * self.scale[1])

    def length(self, v):
        """A logical length (pen width, font height) in output px."""
        a = self.pt(0, 0)
        b = self.pt(v, 0)
        c = self.pt(0, v)
        return max(math.hypot(b[0] - a[0], b[1] - a[1]),
                   math.hypot(c[0] - a[0], c[1] - a[1]))

    # ---- state ---------------------------------------------------------
    def save(self):
        self.stack.append(replace(self.dc))

    def restore(self, n=-1):
        if not self.stack:
            return
        idx = n if n < 0 else n - 1
        try:
            dc = self.stack[idx]
            del self.stack[idx:]
        except IndexError:
            dc = self.stack.pop()
        self.dc = dc

    def clip_rect(self, l, t, r, b):
        p1, p2 = self.pt(l, t), self.pt(r, b)
        rect = (min(p1[0], p2[0]), min(p1[1], p2[1]),
                max(p1[0], p2[0]), max(p1[1], p2[1]))
        c = self.dc.clip
        if c is not None:
            rect = (max(rect[0], c[0]), max(rect[1], c[1]),
                    min(rect[2], c[2]), min(rect[3], c[3]))
        self.dc.clip = rect

    def select(self, obj):
        if isinstance(obj, Pen):
            self.dc.pen = obj
        elif isinstance(obj, Brush):
            self.dc.brush = obj
        elif isinstance(obj, Font):
            self.dc.font = obj

    # ---- drawing -------------------------------------------------------
    def _pen_px(self):
        pen = self.dc.pen
        if pen.style == 5:
            return 0
        if pen.cosmetic or pen.width <= 0:
            return max(1, int(round(_SUPERSAMPLE)))
        return max(1, int(round(self.length(pen.width))))

    def _brush_fill(self):
        b = self.dc.brush
        if b.style == 1:
            return None
        if b.style == 2:                       # hatch → its colour, light
            return b.color + (110,)
        if b.image is not None:
            return b.image
        return b.color + (255,)

    def polygon(self, pts, fill=True, stroke=True):
        if self.path is not None:
            self.path.append((list(pts), True))
            return
        if len(pts) < 2:
            return
        d = self.canvas.draw(self.dc.clip)
        dev = [self.pt(*p) for p in pts]
        f = self._brush_fill() if fill else None
        if f is not None and len(dev) >= 3:
            d.polygon(dev, fill=f)
        w = self._pen_px() if stroke else 0
        if w:
            d.line(dev + [dev[0]], fill=self.dc.pen.color + (255,),
                   width=w, joint="curve")

    def polypolygon(self, polys):
        if self.path is not None:
            for p in polys:
                self.path.append((list(p), True))
            return
        f = self._brush_fill()
        if f is not None:
            self._fill_even_odd([[self.pt(*p) for p in poly] for poly in polys],
                                f)
        w = self._pen_px()
        if w:
            d = self.canvas.draw(self.dc.clip)
            for poly in polys:
                dev = [self.pt(*p) for p in poly]
                if len(dev) >= 2:
                    d.line(dev + [dev[0]], fill=self.dc.pen.color + (255,),
                           width=w, joint="curve")

    def _fill_even_odd(self, polys, colour):
        from PIL import Image, ImageChops, ImageDraw
        pts = [p for poly in polys for p in poly]
        if not pts:
            return
        l = max(0, int(min(p[0] for p in pts)) - 1)
        t = max(0, int(min(p[1] for p in pts)) - 1)
        r = min(self.canvas.w, int(max(p[0] for p in pts)) + 2)
        b = min(self.canvas.h, int(max(p[1] for p in pts)) + 2)
        if r <= l or b <= t:
            return
        mask = Image.new("L", (r - l, b - t), 0)
        for poly in polys:
            if len(poly) < 3:
                continue
            m = Image.new("L", mask.size, 0)
            ImageDraw.Draw(m).polygon([(x - l, y - t) for x, y in poly],
                                      fill=255)
            mask = ImageChops.logical_xor(mask.convert("1"),
                                          m.convert("1")).convert("L") \
                if self.dc.fill_mode == 1 else ImageChops.lighter(mask, m)
        if isinstance(colour, tuple):
            tile = Image.new("RGBA", mask.size, colour[:3] + (255,))
            alpha = colour[3] if len(colour) > 3 else 255
            if alpha < 255:
                mask = mask.point(lambda v: v * alpha // 255)
            tile.putalpha(mask)
            self.canvas.paste(tile, (l, t), self.dc.clip)

    def polyline(self, pts):
        if self.path is not None:
            self.path.append((list(pts), False))
            return
        w = self._pen_px()
        if not w or len(pts) < 2:
            return
        d = self.canvas.draw(self.dc.clip)
        dev = [self.pt(*p) for p in pts]
        if self.dc.pen.style in (1, 2, 3, 4):
            self._dashed(d, dev, w)
        else:
            d.line(dev, fill=self.dc.pen.color + (255,), width=w,
                   joint="curve")

    def _dashed(self, d, dev, w):
        on, off = {1: (6, 3), 2: (1.5, 2), 3: (6, 2), 4: (6, 2)}[
            self.dc.pen.style]
        on, off = on * w, off * w
        colour = self.dc.pen.color + (255,)
        draw_on, left = True, on
        for (x1, y1), (x2, y2) in zip(dev, dev[1:]):
            seg = math.hypot(x2 - x1, y2 - y1)
            pos = 0.0
            while pos < seg:
                step = min(left, seg - pos)
                if draw_on:
                    a, b = pos / seg, (pos + step) / seg
                    d.line([(x1 + (x2 - x1) * a, y1 + (y2 - y1) * a),
                            (x1 + (x2 - x1) * b, y1 + (y2 - y1) * b)],
                           fill=colour, width=w)
                pos += step
                left -= step
                if left <= 1e-6:
                    draw_on = not draw_on
                    left = on if draw_on else off

    def rectangle(self, l, t, r, b):
        self.polygon([(l, t), (r, t), (r, b), (l, b)])

    def ellipse_pts(self, l, t, r, b, a0=0.0, a1=2 * math.pi, n=72):
        cx, cy, rx, ry = (l + r) / 2, (t + b) / 2, (r - l) / 2, (b - t) / 2
        steps = max(8, int(n * abs(a1 - a0) / (2 * math.pi)))
        return [(cx + rx * math.cos(a0 + (a1 - a0) * i / steps),
                 cy + ry * math.sin(a0 + (a1 - a0) * i / steps))
                for i in range(steps + 1)]

    def ellipse(self, l, t, r, b):
        self.polygon(self.ellipse_pts(l, t, r, b)[:-1])

    def round_rect(self, l, t, r, b, ew, eh):
        rx, ry = min(abs(ew) / 2, abs(r - l) / 2), min(abs(eh) / 2,
                                                       abs(b - t) / 2)
        pts = []
        for cx, cy, a in ((r - rx, t + ry, -math.pi / 2), (r - rx, b - ry, 0),
                          (l + rx, b - ry, math.pi / 2),
                          (l + rx, t + ry, math.pi)):
            for i in range(9):
                ang = a + math.pi / 2 * i / 8
                pts.append((cx + rx * math.cos(ang), cy + ry * math.sin(ang)))
        self.polygon(pts)

    def arc(self, l, t, r, b, xs, ys, xe, ye, mode):
        """mode: "arc" (outline), "pie", "chord"."""
        cx, cy = (l + r) / 2, (t + b) / 2
        rx, ry = (r - l) / 2 or 1, (b - t) / 2 or 1
        a0 = math.atan2((ys - cy) / ry, (xs - cx) / rx)
        a1 = math.atan2((ye - cy) / ry, (xe - cx) / rx)
        # GDI arcs run anticlockwise in logical space (y down → negative).
        while a1 >= a0:
            a1 -= 2 * math.pi
        pts = self.ellipse_pts(l, t, r, b, a0, a1)
        if mode == "arc":
            self.polyline(pts)
        elif mode == "pie":
            self.polygon([(cx, cy)] + pts)
        else:
            self.polygon(pts)

    def text(self, x, y, s, dx=None):
        if not s:
            return
        from PIL import Image, ImageDraw
        f = self.dc.font
        px = self.length(abs(f.height) or 12)
        if f.height > 0:                       # cell height → char height
            px *= 0.85
        font = _font(f.face, px, f.weight >= 600, f.italic)
        try:
            bbox = font.getbbox(s)
            ascent, descent = font.getmetrics()
        except Exception:
            bbox, ascent, descent = (0, 0, len(s) * px / 2, px), px * .8, px * .2
        width = max(1, int(math.ceil(bbox[2])) + 2)
        height = max(1, int(ascent + descent) + 2)
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        dl = ImageDraw.Draw(layer)
        if self.dc.bk_mode == 2 and False:     # opaque background — rare
            dl.rectangle((0, 0, width, height), fill=self.dc.bk_color)
        dl.text((0, 0), s, font=font, fill=self.dc.text_color + (255,))
        if f.underline:
            dl.line((0, ascent + 1, width, ascent + 1),
                    fill=self.dc.text_color + (255,), width=max(1, int(px / 14)))
        align = self.dc.text_align
        # Anchor offset inside the text layer (before rotation).
        ax = {0: 0, 2: width, 6: width / 2}.get(align & 6, 0)
        ay = {0: 0, 8: ascent + descent, 24: ascent}.get(align & 24, 0)
        angle = f.escapement / 10.0
        ox, oy = self.pt(x, y)
        if (align & 1) and self.dc.pos:        # TA_UPDATECP
            ox, oy = self.pt(*self.dc.pos)
        if angle:
            big = layer.rotate(angle, expand=True, resample=Image.BICUBIC)
            # Where the anchor lands after rotating about the layer centre.
            cx, cy = width / 2, height / 2
            rad = math.radians(angle)
            vx, vy = ax - cx, ay - cy
            rx = vx * math.cos(rad) + vy * math.sin(rad)
            ry = -vx * math.sin(rad) + vy * math.cos(rad)
            self.canvas.paste(big, (ox - (big.width / 2 + rx),
                                    oy - (big.height / 2 + ry)), self.dc.clip)
        else:
            self.canvas.paste(layer, (ox - ax, oy - ay), self.dc.clip)

    def bitmap(self, img, x, y, w, h):
        """Stretch a Pillow image into the logical rectangle."""
        from PIL import Image
        p1, p2 = self.pt(x, y), self.pt(x + w, y + h)
        l, t = min(p1[0], p2[0]), min(p1[1], p2[1])
        tw, th = int(round(abs(p2[0] - p1[0]))), int(round(abs(p2[1] - p1[1])))
        if tw < 1 or th < 1:
            return
        if p2[0] < p1[0]:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        if p2[1] < p1[1]:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        img = img.convert("RGBA").resize((tw, th), Image.LANCZOS)
        self.canvas.paste(img, (l, t), self.dc.clip)

    # ---- paths (EMF) ---------------------------------------------------
    def begin_path(self):
        self.path = []

    def end_path(self):
        pass

    def stroke_fill_path(self, stroke, fill):
        figures = self.path or []
        self.path = None
        if fill:
            closed = [pts for pts, _ in figures if len(pts) >= 3]
            if closed:
                saved = self.dc.pen
                self.dc.pen = replace(saved, style=5)
                self.polypolygon(closed)
                self.dc.pen = saved
        if stroke:
            for pts, closed in figures:
                self.polyline(pts + ([pts[0]] if closed and pts else []))

    # ---- output size ---------------------------------------------------
    def make_canvas(self, dev_w, dev_h, phys_w_in=None):
        """Size the output for a reference-device rectangle."""
        dpi_scale = 1.0
        if phys_w_in:
            dpi_scale = phys_w_in * _DEFAULT_DPI / max(1.0, abs(dev_w))
        w, h = abs(dev_w) * dpi_scale, abs(dev_h) * dpi_scale
        longest = max(w, h, 1)
        if longest > _MAX_SIDE:
            dpi_scale *= _MAX_SIDE / longest
        elif longest < 1200:              # keep small graphs crisp
            dpi_scale *= 1200 / longest
        s = dpi_scale * _SUPERSAMPLE
        self.scale = (s, s)
        W = max(1, int(round(abs(dev_w) * s)))
        H = max(1, int(round(abs(dev_h) * s)))
        self.canvas = _Canvas(W, H)

    def finish(self):
        from PIL import Image
        self.canvas.flush()
        img = self.canvas.image
        out = img.resize((max(1, img.width // _SUPERSAMPLE),
                          max(1, img.height // _SUPERSAMPLE)), Image.LANCZOS)
        return out


# ===================================================================== WMF
class _WMF(_Player):
    def __init__(self, data: bytes):
        super().__init__()
        self.data = data

    def _alloc(self, obj):
        i = 0
        while i in self.objects:
            i += 1
        self.objects[i] = obj

    def render(self):
        d = self.data
        off = 0
        bbox = None
        inch = 1440
        if struct.unpack_from("<I", d, 0)[0] == WMF_PLACEABLE:
            l, t, r, b, inch = struct.unpack_from("<hhhhH", d, 6)
            bbox = (l, t, r, b)
            off = 22
        hsize = struct.unpack_from("<H", d, off + 2)[0]
        off += hsize * 2
        records = []
        pos = off
        while pos + 6 <= len(d):
            size, fn = struct.unpack_from("<IH", d, pos)
            if size < 3:
                break
            records.append((fn, pos + 6, size * 2 - 6))
            if fn == 0:
                break
            pos += size * 2
        # Find the window to size the output (first SETWINDOWORG/EXT).
        org, ext = None, None
        for fn, p, n in records:
            if fn == 0x020B and org is None:
                y, x = struct.unpack_from("<hh", d, p)
                org = (x, y)
            elif fn == 0x020C and ext is None:
                y, x = struct.unpack_from("<hh", d, p)
                ext = (x, y)
        # The picture is the window (first SETWINDOWORG/EXT), else the
        # placeable bounding box; the placeable header gives its size.
        if org is not None and ext is not None:
            rect = (org[0], org[1], ext[0], ext[1])
        elif bbox is not None:
            l, t, r, b = bbox
            rect = (l, t, r - l, b - t)
        else:
            rect = (0, 0, 1000, 1000)
        if bbox is not None:
            phys = abs(bbox[2] - bbox[0]) / (inch or 1440)
        else:
            phys = abs(rect[2]) / 1440
        self.dc.win_org = (rect[0], rect[1])
        self.dc.win_ext = (rect[2] or 1, rect[3] or 1)
        self.make_canvas(rect[2] or 1, rect[3] or 1, phys)
        for fn, p, n in records:
            try:
                self._record(fn, p, n)
            except Exception:
                continue
        return self.finish()

    def pt(self, x, y):
        """Window coordinates straight onto the output image."""
        d = self.dc
        return ((x - d.win_org[0]) / (d.win_ext[0] or 1) * self.canvas.w,
                (y - d.win_org[1]) / (d.win_ext[1] or 1) * self.canvas.h)

    def _record(self, fn, p, n):
        d = self.data
        h = lambda i: struct.unpack_from("<h", d, p + 2 * i)[0]   # noqa
        H = lambda i: struct.unpack_from("<H", d, p + 2 * i)[0]   # noqa
        if fn == 0x020B:                                   # SETWINDOWORG
            self.dc.win_org = (h(1), h(0))
        elif fn == 0x020C:                                 # SETWINDOWEXT
            self.dc.win_ext = (h(1) or 1, h(0) or 1)
        elif fn == 0x02FA:                                 # CREATEPENINDIRECT
            style, w = H(0), h(1)
            self._alloc(Pen(_colorref(struct.unpack_from("<I", d, p + 6)[0]),
                            float(w), style & 0x0F))
        elif fn == 0x02FC:                                 # CREATEBRUSHINDIRECT
            style = H(0)
            col = _colorref(struct.unpack_from("<I", d, p + 2)[0])
            self._alloc(Brush(col, style if style in (0, 1, 2) else 1))
        elif fn == 0x02FB:                                 # CREATEFONTINDIRECT
            height, _w, esc, _o, weight = (h(0), h(1), h(2), h(3), h(4))
            italic, underline = d[p + 10], d[p + 11]
            face = d[p + 18:p + 18 + 32].split(b"\0")[0].decode(
                "latin-1", "replace")
            self._alloc(Font(float(height), float(esc), weight,
                             bool(italic), bool(underline), face or "Arial"))
        elif fn in (0x0142, 0x01F9):                       # pattern brushes
            img = None
            try:
                if fn == 0x0142:
                    img = dib_image(d[p + 4:p + n])
            except Exception:
                img = None
            col = (128, 128, 128)
            if img is not None:
                small = img.convert("RGB").resize((1, 1))
                col = small.getpixel((0, 0))
            self._alloc(Brush(col, 0))
        elif fn in (0x00F7, 0x06FF):                       # palette, region
            self._alloc(None)
        elif fn == 0x012D:                                 # SELECTOBJECT
            obj = self.objects.get(H(0))
            if obj is not None:
                self.select(obj)
        elif fn == 0x01F0:                                 # DELETEOBJECT
            self.objects.pop(H(0), None)
        elif fn == 0x001E:                                 # SAVEDC
            self.save()
        elif fn == 0x0127:                                 # RESTOREDC
            self.restore(h(0))
        elif fn == 0x0201:
            self.dc.bk_color = _colorref(struct.unpack_from("<I", d, p)[0])
        elif fn == 0x0209:
            self.dc.text_color = _colorref(struct.unpack_from("<I", d, p)[0])
        elif fn == 0x0102:
            self.dc.bk_mode = H(0)
        elif fn == 0x012E:
            self.dc.text_align = H(0)
        elif fn == 0x0106:
            self.dc.fill_mode = H(0)
        elif fn == 0x0214:                                 # MOVETO
            self.dc.pos = (h(1), h(0))
        elif fn == 0x0213:                                 # LINETO
            x, y = h(1), h(0)
            self.polyline([self.dc.pos, (x, y)])
            self.dc.pos = (x, y)
        elif fn in (0x0325, 0x0324):                       # POLYLINE/POLYGON
            cnt = H(0)
            pts = [struct.unpack_from("<hh", d, p + 2 + 4 * i)
                   for i in range(cnt)]
            (self.polyline if fn == 0x0325 else self.polygon)(pts)
        elif fn == 0x0538:                                 # POLYPOLYGON
            npolys = H(0)
            counts = [H(1 + i) for i in range(npolys)]
            q = p + 2 + 2 * npolys
            polys = []
            for c in counts:
                polys.append([struct.unpack_from("<hh", d, q + 4 * i)
                              for i in range(c)])
                q += 4 * c
            self.polypolygon(polys)
        elif fn == 0x041B:                                 # RECTANGLE
            b, r, t, l = h(0), h(1), h(2), h(3)
            self.rectangle(l, t, r, b)
        elif fn == 0x0418:                                 # ELLIPSE
            b, r, t, l = h(0), h(1), h(2), h(3)
            self.ellipse(l, t, r, b)
        elif fn == 0x061C:                                 # ROUNDRECT
            eh, ew, b, r, t, l = (h(i) for i in range(6))
            self.round_rect(l, t, r, b, ew, eh)
        elif fn in (0x0817, 0x081A, 0x0830):               # ARC/PIE/CHORD
            ye, xe, ys, xs, b, r, t, l = (h(i) for i in range(8))
            self.arc(l, t, r, b, xs, ys, xe, ye,
                     {0x0817: "arc", 0x081A: "pie", 0x0830: "chord"}[fn])
        elif fn == 0x0416:                                 # INTERSECTCLIPRECT
            b, r, t, l = h(0), h(1), h(2), h(3)
            self.clip_rect(l, t, r, b)
        elif fn == 0x0521:                                 # TEXTOUT
            cnt = H(0)
            s = d[p + 2:p + 2 + cnt]
            q = p + 2 + cnt + (cnt & 1)
            y, x = struct.unpack_from("<hh", d, q)
            self.text(x, y, s.decode("cp1252", "replace"))
        elif fn == 0x0A32:                                 # EXTTEXTOUT
            y, x, cnt, opts = h(0), h(1), H(2), H(3)
            q = p + 8 + (8 if opts & 0x06 else 0)
            s = d[q:q + cnt]
            self.text(x, y, s.decode(self._codepage(), "replace"))
        elif fn in (0x0940, 0x0B41, 0x0F43):               # bitmaps
            self._blit(fn, p, n)

    def _codepage(self):
        return "cp1252"

    def _blit(self, fn, p, n):
        d = self.data
        h = lambda i: struct.unpack_from("<h", d, p + 2 * i)[0]   # noqa
        if fn == 0x0F43:                                   # STRETCHDIB
            # rop(4) usage(2) srcH srcW ySrc xSrc destH destW yDst xDst DIB
            sh, sw, ys, xs, dh, dw, yd, xd = (h(3 + i) for i in range(8))
            dib = d[p + 22:p + n]
        elif fn == 0x0B41:                                 # DIBSTRETCHBLT
            sh, sw, ys, xs, dh, dw, yd, xd = (h(2 + i) for i in range(8))
            dib = d[p + 20:p + n]
        else:                                              # DIBBITBLT
            ys, xs, dh, dw, yd, xd = (h(2 + i) for i in range(6))
            sh, sw = dh, dw
            dib = d[p + 16:p + n]
        img = dib_image(dib)
        if (xs, ys, sw, sh) != (0, 0, img.width, img.height) and sw and sh:
            # Source rect is bottom-up in DIB terms for positive heights.
            top = img.height - ys - abs(sh)
            img = img.crop((xs, max(0, top), xs + abs(sw),
                            max(0, top) + abs(sh)))
        self.bitmap(img, xd, yd, dw, dh)


# ===================================================================== EMF
_STOCK = {
    0x80000000: Brush((255, 255, 255), 0), 0x80000001: Brush((192, 192, 192), 0),
    0x80000002: Brush((128, 128, 128), 0), 0x80000003: Brush((64, 64, 64), 0),
    0x80000004: Brush((0, 0, 0), 0), 0x80000005: Brush((0, 0, 0), 1),
    0x80000006: Pen((255, 255, 255), 0, 0), 0x80000007: Pen((0, 0, 0), 0, 0),
    0x80000008: Pen((0, 0, 0), 0, 5),
    0x8000000A: Font(-12, 0, 400, False, False, "Courier New"),
    0x8000000B: Font(-12, 0, 400, False, False, "Courier New"),
    0x8000000C: Font(-12, 0, 400, False, False, "Arial"),
    0x8000000D: Font(-12, 0, 400, False, False, "Arial"),
    0x8000000E: Font(-12, 0, 400, False, False, "Arial"),
    0x80000010: Font(-12, 0, 400, False, False, "Arial"),
    0x80000011: Font(-12, 0, 400, False, False, "Arial"),
}


class _EMF(_Player):
    def __init__(self, data: bytes):
        super().__init__()
        self.data = data

    def _fixed_scale(self, mode):
        # Metric map modes in reference-device pixels.
        mm = {2: 0.1, 3: 0.01, 4: 0.254, 5: 0.0254, 6: 25.4 / 1440}.get(mode)
        if mm is None:
            return 1.0
        return mm * self.px_per_mm

    def _device(self, x, y):
        dx, dy = super()._device(x, y)
        if self.dc.map_mode in (2, 3, 4, 5, 6):
            dy = -dy                                  # y grows upward
        return dx, dy

    def render(self):
        d = self.data
        bounds = struct.unpack_from("<iiii", d, 8)
        frame = struct.unpack_from("<iiii", d, 24)
        dev_px = struct.unpack_from("<ii", d, 72)
        dev_mm = struct.unpack_from("<ii", d, 80)
        self.px_per_mm = dev_px[0] / max(1, dev_mm[0])
        ppmy = dev_px[1] / max(1, dev_mm[1])
        # The picture frame (0.01 mm) in reference-device pixels.
        fl, ft = frame[0] / 100 * self.px_per_mm, frame[1] / 100 * ppmy
        fr, fb = frame[2] / 100 * self.px_per_mm, frame[3] / 100 * ppmy
        if fr - fl < 1 or fb - ft < 1:
            fl, ft, fr, fb = bounds
        self.origin = (fl, ft)
        self.make_canvas(fr - fl, fb - ft,
                         (frame[2] - frame[0]) / 2540.0 or None)
        pos = 0
        while pos + 8 <= len(d):
            typ, size = struct.unpack_from("<II", d, pos)
            if size < 8:
                break
            try:
                self._record(typ, pos + 8, size - 8, pos)
            except Exception:
                pass
            if typ == 14:
                break
            pos += size
        return self.finish()

    def _pts32(self, p, cnt):
        return [struct.unpack_from("<ii", self.data, p + 8 * i)
                for i in range(cnt)]

    def _pts16(self, p, cnt):
        return [struct.unpack_from("<hh", self.data, p + 4 * i)
                for i in range(cnt)]

    def _bezier_pts(self, start, pts):
        out = [start]
        cur = start
        for i in range(0, len(pts) - 2, 3):
            out += _bezier(cur, pts[i], pts[i + 1], pts[i + 2])
            cur = pts[i + 2]
        return out

    def _poly_to(self, pts):
        """LineTo/BezierTo style records continue the current figure."""
        if self.path is not None:
            if not self.figure:
                self.figure = [self.dc.pos]
            self.figure += pts
        else:
            self.polyline([self.dc.pos] + pts)
        if pts:
            self.dc.pos = pts[-1]

    def _flush_figure(self, closed=False):
        if self.path is not None and len(self.figure) > 1:
            self.path.append((self.figure, closed))
        self.figure = []

    def _record(self, typ, p, n, rec):
        d = self.data
        i32 = lambda k: struct.unpack_from("<i", d, p + 4 * k)[0]   # noqa
        u32 = lambda k: struct.unpack_from("<I", d, p + 4 * k)[0]   # noqa
        dc = self.dc
        if typ == 9:
            dc.win_ext = (i32(0), i32(1))
        elif typ == 10:
            dc.win_org = (i32(0), i32(1))
        elif typ == 11:
            dc.vp_ext = (i32(0), i32(1))
        elif typ == 12:
            dc.vp_org = (i32(0), i32(1))
        elif typ == 17:
            dc.map_mode = u32(0)
        elif typ == 18:
            dc.bk_mode = u32(0)
        elif typ == 19:
            dc.fill_mode = u32(0)
        elif typ == 22:
            dc.text_align = u32(0)
        elif typ == 24:
            dc.text_color = _colorref(u32(0))
        elif typ == 25:
            dc.bk_color = _colorref(u32(0))
        elif typ == 27:                                   # MOVETOEX
            self._flush_figure()
            dc.pos = (i32(0), i32(1))
        elif typ == 54:                                   # LINETO
            self._poly_to([(i32(0), i32(1))])
        elif typ == 33:
            self.save()
        elif typ == 34:
            self.restore(i32(0))
        elif typ == 35:                                   # SETWORLDTRANSFORM
            dc.world = struct.unpack_from("<6f", d, p)
        elif typ == 36:                                   # MODIFYWORLDTRANSFORM
            m = struct.unpack_from("<6f", d, p)
            mode = u32(6)
            if mode == 1:
                dc.world = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
            elif mode in (2, 3):
                a, b = (m, dc.world) if mode == 2 else (dc.world, m)
                dc.world = (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
                            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
                            a[4] * b[0] + a[5] * b[2] + b[4],
                            a[4] * b[1] + a[5] * b[3] + b[5])
            elif mode == 4:
                dc.world = m
        elif typ == 30:                                   # INTERSECTCLIPRECT
            self.clip_rect(i32(0), i32(1), i32(2), i32(3))
        elif typ == 38:                                   # CREATEPEN
            self.objects[u32(0)] = Pen(_colorref(u32(4)), float(i32(2)),
                                       u32(1) & 0x0F)
        elif typ == 95:                                   # EXTCREATEPEN
            style = u32(5)
            self.objects[u32(0)] = Pen(_colorref(u32(8)), float(u32(6)),
                                       style & 0x0F,
                                       cosmetic=not (style & 0x10000))
        elif typ == 39:                                   # CREATEBRUSHINDIRECT
            style = u32(1)
            self.objects[u32(0)] = Brush(_colorref(u32(2)),
                                         style if style in (0, 1, 2) else 1)
        elif typ in (93, 94):                             # pattern brushes
            ih, _usage, off_bmi, cb_bmi, off_bits, cb_bits = (
                u32(k) for k in range(6))
            col = (128, 128, 128)
            try:
                img = dib_image(d[rec + off_bmi:rec + off_bmi + cb_bmi],
                                d[rec + off_bits:rec + off_bits + cb_bits])
                col = img.convert("RGB").resize((1, 1)).getpixel((0, 0))
            except Exception:
                pass
            self.objects[ih] = Brush(col, 0)
        elif typ == 82:                                   # EXTCREATEFONTINDIRECTW
            height, _w, esc, _o, weight = (i32(1), i32(2), i32(3), i32(4),
                                           i32(5))
            italic, underline = d[p + 24], d[p + 25]
            face = d[p + 32:p + 32 + 64].decode("utf-16-le", "replace") \
                .split("\0")[0]
            self.objects[u32(0)] = Font(float(height), float(esc), weight,
                                        bool(italic), bool(underline),
                                        face or "Arial")
        elif typ == 37:                                   # SELECTOBJECT
            ih = u32(0)
            obj = _STOCK.get(ih) if ih & 0x80000000 else self.objects.get(ih)
            if obj is not None:
                self.select(obj)
        elif typ == 40:
            self.objects.pop(u32(0), None)
        elif typ == 43:                                   # RECTANGLE
            self.rectangle(i32(0), i32(1), i32(2), i32(3))
        elif typ == 42:                                   # ELLIPSE
            self.ellipse(i32(0), i32(1), i32(2), i32(3))
        elif typ == 44:                                   # ROUNDRECT
            self.round_rect(i32(0), i32(1), i32(2), i32(3), i32(4), i32(5))
        elif typ in (45, 46, 47):                         # ARC, CHORD, PIE
            self.arc(i32(0), i32(1), i32(2), i32(3), i32(4), i32(5), i32(6),
                     i32(7), {45: "arc", 46: "chord", 47: "pie"}[typ])
        elif typ in (3, 4, 86, 87, 2, 85):                # poly / bezier
            cnt = u32(4)
            pts = self._pts16(p + 20, cnt) if typ in (86, 87, 85) \
                else self._pts32(p + 20, cnt)
            if typ in (2, 85):
                pts = self._bezier_pts(pts[0], pts[1:])
                self.polyline(pts)
            elif typ in (3, 86):
                self.polygon(pts)
            else:
                self.polyline(pts)
        elif typ in (6, 89, 5, 88):                       # ...TO variants
            cnt = u32(4)
            pts = self._pts16(p + 20, cnt) if typ in (89, 88) \
                else self._pts32(p + 20, cnt)
            if typ in (5, 88):
                pts = self._bezier_pts(self.dc.pos, pts)[1:]
            self._poly_to(pts)
        elif typ in (7, 8, 90, 91):                       # POLYPOLY…
            npolys, total = u32(4), u32(5)
            counts = [u32(6 + k) for k in range(npolys)]
            q = p + 24 + 4 * npolys
            small = typ in (90, 91)
            polys = []
            for c in counts:
                polys.append(self._pts16(q, c) if small else self._pts32(q, c))
                q += c * (4 if small else 8)
            if typ in (8, 90):
                self.polypolygon(polys)
            else:
                for poly in polys:
                    self.polyline(poly)
        elif typ == 59:                                   # BEGINPATH
            self.begin_path()
            self.figure = []
        elif typ == 60:                                   # ENDPATH
            self._flush_figure()
        elif typ == 61:                                   # CLOSEFIGURE
            self._flush_figure(closed=True)
        elif typ in (62, 63, 64):                         # FILL/STROKE PATH
            self._flush_figure()
            self.stroke_fill_path(stroke=typ in (63, 64), fill=typ in (62, 63))
        elif typ == 84:                                   # EXTTEXTOUTW
            q = p + 28                                    # EMRTEXT
            rx, ry, nchars, off_str, opts = struct.unpack_from("<iiIII", d, q)
            s = d[rec + off_str:rec + off_str + 2 * nchars].decode(
                "utf-16-le", "replace")
            self.text(rx, ry, s)
        elif typ == 83:                                   # EXTTEXTOUTA
            q = p + 28
            rx, ry, nchars, off_str, opts = struct.unpack_from("<iiIII", d, q)
            s = d[rec + off_str:rec + off_str + nchars].decode(
                "cp1252", "replace")
            self.text(rx, ry, s)
        elif typ == 81:                                   # STRETCHDIBITS
            (xd, yd, xs, ys, sw, sh, off_bmi, cb_bmi, off_bits, cb_bits,
             _usage, _rop, dw, dh) = struct.unpack_from("<iiiiiiIIIIIIii",
                                                         d, p + 16)
            self._dib(rec, off_bmi, cb_bmi, off_bits, cb_bits,
                      xs, ys, sw, sh, xd, yd, dw, dh)
        elif typ == 80:                                   # SETDIBITSTODEVICE
            (xd, yd, xs, ys, sw, sh, off_bmi, cb_bmi, off_bits,
             cb_bits) = struct.unpack_from("<iiiiiiIIII", d, p + 16)
            self._dib(rec, off_bmi, cb_bmi, off_bits, cb_bits,
                      xs, ys, sw, sh, xd, yd, sw, sh)
        elif typ in (76, 77):                             # BITBLT / STRETCHBLT
            xd, yd, dw, dh = (i32(4), i32(5), i32(6), i32(7))
            # dwRop, xSrc, ySrc, xform(24), bkColor, usage, offBmi, cbBmi,
            # offBits, cbBits[, cxSrc, cySrc]
            q = p + 32
            xs, ys = struct.unpack_from("<ii", d, q + 4)
            off_bmi, cb_bmi, off_bits, cb_bits = struct.unpack_from(
                "<IIII", d, q + 12 + 24 + 8)
            sw, sh = dw, dh
            if typ == 77:
                sw, sh = struct.unpack_from("<ii", d, q + 12 + 24 + 24)
            if cb_bmi:
                self._dib(rec, off_bmi, cb_bmi, off_bits, cb_bits,
                          xs, ys, sw, sh, xd, yd, dw, dh)
            else:                                         # PATCOPY fill
                self.dc, saved = replace(self.dc, pen=Pen(style=5)), self.dc
                self.rectangle(xd, yd, xd + dw, yd + dh)
                self.dc = saved

    def _dib(self, rec, off_bmi, cb_bmi, off_bits, cb_bits,
             xs, ys, sw, sh, xd, yd, dw, dh):
        d = self.data
        img = dib_image(d[rec + off_bmi:rec + off_bmi + cb_bmi],
                        d[rec + off_bits:rec + off_bits + cb_bits])
        if sw > 0 and sh > 0 and (xs, ys, sw, sh) != (0, 0, img.width,
                                                       img.height):
            img = img.crop((xs, ys, min(img.width, xs + sw),
                            min(img.height, ys + sh)))
        self.bitmap(img, xd, yd, dw, dh)


# ============================================================ app helpers
METAFILE_EXTS = (".wmf", ".emf")


def _out_dir() -> Path:
    import tempfile
    d = Path(tempfile.gettempdir()) / "kherveslide_metafiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_raster(path: str) -> str:
    """A picture path XeTeX and Qt can use: a .wmf/.emf file is converted
    to a PNG beside it (or in a temp folder when that isn't writable).
    Other paths come back unchanged; "" if a metafile can't be read."""
    if not path or not path.lower().endswith(METAFILE_EXTS):
        return path
    src = Path(path)
    try:
        png = to_png(src.read_bytes())
    except OSError:
        return ""
    if png is None:
        return ""
    for dst in (src.with_suffix(".png"),
                _out_dir() / f"{src.stem}_{abs(hash(str(src))) % 10**8}.png"):
        try:
            if dst.exists() and dst.read_bytes() != png and dst.parent == \
                    src.parent:
                continue              # never overwrite an unrelated PNG
            dst.write_bytes(png)
            return str(dst)
        except OSError:
            continue
    return ""


# Clipboard flavours that carry metafile bytes (Windows, macOS Office).
_MIME_HINTS = ("emf", "wmf", "metafile", "enhanced")


def from_mime(md) -> str | None:
    """Convert a metafile on the clipboard / in a drop to a PNG file;
    returns its path, or None when there is none."""
    if md is None:
        return None
    try:
        formats = list(md.formats())
    except Exception:
        return None
    for f in formats:
        if not any(h in f.lower() for h in _MIME_HINTS):
            continue
        try:
            data = bytes(md.data(f))
        except Exception:
            continue
        if not kind(data):
            continue
        png = to_png(data)
        if png is None:
            continue
        d = _out_dir()
        i = 1
        while (d / f"pasted_{i:03d}.png").exists():
            i += 1
        out = d / f"pasted_{i:03d}.png"
        out.write_bytes(png)
        return str(out)
    return None


def main(argv=None) -> int:
    """``python -m kherveslide.metafile in.wmf|in.emf [out.png]``"""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(main.__doc__)
        return 2
    src = Path(argv[0])
    dst = Path(argv[1]) if len(argv) > 1 else src.with_suffix(".png")
    ok = convert_file(src, dst)
    print(dst if ok else f"not a readable WMF/EMF: {src}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
