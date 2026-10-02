"""PowerPoint-style picture effects, rendered with Pillow.

A picture's effects (corrections, colour, artistic filters, fade, soft
edges, glow, reflection) are baked into a cached PNG of the *cropped*
image. The canvas and the serializer both use that same file, so the
Visual matches the PDF. Rotation, opacity and the box frame/shadow stay
live (they are applied on top, as before).

Glow and reflection draw outside the picture's box: the baked image is
padded and :func:`padding` says by how much (fractions of the content
width/height), so callers grow the drawn rect accordingly.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

# (field, neutral value) — a picture "has effects" when any differs.
from .model import _PICTURE_EFFECTS as EFFECT_FIELDS  # noqa: E402

RECOLORS = ["", "grayscale", "sepia", "washout", "bw", "duotone"]
ARTISTIC = ["", "blur", "pencil", "line_drawing", "mosaic", "posterize",
            "emboss", "glow_edges", "watercolor"]
FADES = ["", "left", "right", "top", "bottom", "radial"]


def _active(obj, name) -> bool:
    neutral = EFFECT_FIELDS[name]
    v = getattr(obj, name, neutral)
    if name in ("recolor_color", "artistic_amount", "fade_start",
                "fade_end", "glow_color"):
        return False          # only modifiers of another effect
    if name == "glow_size":
        return bool(v) and bool(getattr(obj, "glow_color", ""))
    return v != neutral


def has_effects(obj) -> bool:
    return bool(getattr(obj, "path", "")) and any(
        _active(obj, n) for n in EFFECT_FIELDS)


def padding(obj) -> tuple[float, float, float, float]:
    """(left, top, right, bottom) the baked image extends beyond the
    content, as fractions of the content width/height."""
    if not has_effects(obj):
        return (0.0, 0.0, 0.0, 0.0)
    g = (max(0.0, getattr(obj, "glow_size", 0.0))
         if getattr(obj, "glow_color", "") else 0.0)
    w, h = _content_size(obj)
    side = min(w, h) or 1
    gx, gy = g * side / (w or 1), g * side / (h or 1)
    refl = max(0.0, min(1.0, getattr(obj, "reflection", 0.0)))
    return (gx, gy, gx, gy + refl)


def _content_size(obj) -> tuple[int, int]:
    try:
        from PIL import Image
        with Image.open(obj.path) as im:
            w, h = im.size
    except Exception:
        return (1, 1)
    cl, ct, cr, cb = _crop(obj)
    return (max(1, int((1 - cl - cr) * w)), max(1, int((1 - ct - cb) * h)))


def _crop(obj):
    return tuple(max(0.0, min(0.9, getattr(obj, k, 0.0)))
                 for k in ("crop_l", "crop_t", "crop_r", "crop_b"))


def _cache_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "kherveslide_effects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key(obj) -> str:
    try:
        mtime = os.path.getmtime(obj.path)
    except OSError:
        mtime = 0
    data = {n: getattr(obj, n, v) for n, v in EFFECT_FIELDS.items()}
    data.update(path=str(obj.path), mtime=mtime, crop=_crop(obj))
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def baked_path(obj) -> str:
    """Path of the effect-baked PNG for *obj* (rendered on first use).
    Returns "" if the source can't be read."""
    out = _cache_dir() / f"fx_{_key(obj)}.png"
    if not out.exists():
        try:
            from PIL import Image
            with Image.open(obj.path) as im:
                img = render(im, obj)
            img.save(out)
        except Exception:
            return ""
    return str(out)


# ---------------------------------------------------------------- rendering
def _hex(c: str, default=(255, 255, 255)):
    c = (c or "").lstrip("#")
    if len(c) != 6:
        return default
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def render(im, obj):
    """Apply *obj*'s crop and effects to a PIL image; returns RGBA."""
    import numpy as np
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    img = im.convert("RGBA")
    w, h = img.size
    cl, ct, cr, cb = _crop(obj)
    img = img.crop((int(cl * w), int(ct * h),
                    max(int(cl * w) + 1, int((1 - cr) * w)),
                    max(int(ct * h) + 1, int((1 - cb) * h))))
    w, h = img.size
    alpha = img.getchannel("A")
    rgb = img.convert("RGB")

    # --- corrections
    sh = getattr(obj, "sharpness", 0.0)
    if sh > 0:
        rgb = ImageEnhance.Sharpness(rgb).enhance(1 + 3 * sh)
    elif sh < 0:
        rgb = rgb.filter(ImageFilter.GaussianBlur(-sh * min(w, h) / 60))
    br = getattr(obj, "brightness", 0.0)
    if br:
        rgb = ImageEnhance.Brightness(rgb).enhance(max(0.0, 1 + br))
    co = getattr(obj, "contrast", 0.0)
    if co:
        rgb = ImageEnhance.Contrast(rgb).enhance(max(0.0, 1 + co))

    # --- colour
    sat = getattr(obj, "saturation", 1.0)
    if sat != 1.0:
        rgb = ImageEnhance.Color(rgb).enhance(max(0.0, sat))
    temp = getattr(obj, "temperature", 0.0)
    if temp:
        a = np.asarray(rgb).astype(np.float32)
        a[..., 0] *= 1 + 0.25 * temp
        a[..., 2] *= 1 - 0.25 * temp
        rgb = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    rec = getattr(obj, "recolor", "")
    if rec == "grayscale":
        rgb = ImageOps.grayscale(rgb).convert("RGB")
    elif rec == "sepia":
        rgb = ImageOps.colorize(ImageOps.grayscale(rgb),
                                (40, 26, 13), (255, 240, 205))
    elif rec == "washout":
        rgb = Image.blend(ImageEnhance.Contrast(rgb).enhance(0.5),
                          Image.new("RGB", rgb.size, "white"), 0.55)
    elif rec == "bw":
        rgb = ImageOps.grayscale(rgb).point(
            lambda v: 255 if v > 127 else 0).convert("RGB")
    elif rec == "duotone":
        rgb = ImageOps.colorize(ImageOps.grayscale(rgb),
                                _hex(getattr(obj, "recolor_color", ""),
                                     (31, 78, 121)), (255, 255, 255))

    # --- artistic
    art = getattr(obj, "artistic", "")
    amt = max(0.0, min(1.0, getattr(obj, "artistic_amount", 0.5)))
    side = min(w, h)
    if art == "blur":
        rgb = rgb.filter(ImageFilter.GaussianBlur(1 + amt * side / 25))
    elif art == "pencil":
        g = ImageOps.grayscale(rgb)
        inv = ImageOps.invert(g).filter(
            ImageFilter.GaussianBlur(1 + amt * side / 80))
        ga, ia = (np.asarray(g, np.float32), np.asarray(inv, np.float32))
        dodge = np.clip(ga * 255 / np.maximum(1, 255 - ia), 0, 255)
        rgb = Image.fromarray(dodge.astype(np.uint8)).convert("RGB")
    elif art == "line_drawing":
        e = ImageOps.grayscale(rgb).filter(ImageFilter.FIND_EDGES)
        e = e.point(lambda v: 0 if v > 20 + (1 - amt) * 60 else 255)
        rgb = e.convert("RGB")
    elif art == "mosaic":
        n = max(2, int(side * (0.01 + 0.06 * amt)))
        rgb = rgb.resize((max(1, w // n), max(1, h // n)),
                         Image.BILINEAR).resize((w, h), Image.NEAREST)
    elif art == "posterize":
        rgb = ImageOps.posterize(rgb, max(1, int(round(6 - 5 * amt))))
    elif art == "emboss":
        rgb = rgb.filter(ImageFilter.EMBOSS)
    elif art == "glow_edges":
        rgb = ImageOps.autocontrast(rgb.filter(ImageFilter.FIND_EDGES))
    elif art == "watercolor":
        rgb = rgb.filter(ImageFilter.ModeFilter(3 + int(amt * 6))) \
                 .filter(ImageFilter.SMOOTH_MORE)

    # --- transparency masks (fade, soft edges)
    a = np.asarray(alpha, np.float32) / 255.0
    fade = getattr(obj, "fade", "")
    if fade:
        s = max(0.0, min(1.0, getattr(obj, "fade_start", 0.0)))
        e = max(0.0, min(1.0, getattr(obj, "fade_end", 0.5)))
        xs = (np.arange(w, dtype=np.float32) + 0.5) / w
        ys = (np.arange(h, dtype=np.float32) + 0.5) / h
        X, Y = np.meshgrid(xs, ys)
        t = {"left": X, "right": 1 - X, "top": Y, "bottom": 1 - Y}.get(fade)
        if t is None:     # radial: distance from the centre, edges fade
            t = 1 - np.minimum(1, np.hypot(X - 0.5, Y - 0.5) / 0.7071)
        if e <= s:
            m = (t >= s).astype(np.float32)
        else:
            m = np.clip((t - s) / (e - s), 0, 1)
        a = a * m
    se = max(0.0, min(0.5, getattr(obj, "soft_edge", 0.0)))
    if se:
        r = se * side
        xs = np.arange(w, dtype=np.float32) + 0.5
        ys = np.arange(h, dtype=np.float32) + 0.5
        dx = np.minimum(xs, w - xs)[None, :]
        dy = np.minimum(ys, h - ys)[:, None]
        a = a * np.clip(np.minimum(dx, dy) / r, 0, 1)
    out = rgb.convert("RGBA")
    out.putalpha(Image.fromarray((a * 255).astype(np.uint8)))

    # --- glow and reflection (drawn outside the content)
    pl, pt, pr, pb = padding(obj)
    if pl or pt or pr or pb:
        W = w + int(round((pl + pr) * w))
        H = h + int(round((pt + pb) * h))
        ox, oy = int(round(pl * w)), int(round(pt * h))
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if getattr(obj, "glow_color", "") and getattr(obj, "glow_size", 0):
            gr = max(1, ox)
            mask = Image.new("L", (W, H), 0)
            mask.paste(out.getchannel("A"), (ox, oy))
            mask = mask.filter(ImageFilter.MaxFilter(
                min(31, (gr // 2) * 2 + 1))).filter(
                ImageFilter.GaussianBlur(gr / 2))
            mask = mask.point(lambda v: int(v * 0.75))
            glow = Image.new("RGBA", (W, H),
                             _hex(obj.glow_color) + (255,))
            glow.putalpha(mask)
            canvas = Image.alpha_composite(canvas, glow)
        refl = getattr(obj, "reflection", 0.0)
        if refl:
            rh = max(1, int(round(refl * h)))
            flip = ImageOps.flip(out).crop((0, 0, w, rh))
            ra = np.asarray(flip.getchannel("A"), np.float32)
            ramp = np.linspace(0.5, 0.0, rh, dtype=np.float32)[:, None]
            flip.putalpha(Image.fromarray((ra * ramp).astype(np.uint8)))
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            layer.paste(flip, (ox, oy + h))
            canvas = Image.alpha_composite(canvas, layer)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        layer.paste(out, (ox, oy))
        out = Image.alpha_composite(canvas, layer)
    return out
