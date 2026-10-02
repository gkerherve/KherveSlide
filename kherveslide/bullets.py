"""The theme's real itemize bullets, cut out of the bullet-probe pages.

serializer.serialize_backdrop appends probe pages, each holding a real
beamer ``itemize`` (levels 1–3) at one font size on a white background.
Rendering a probe row gives the bullet, then a gap, then an "x". From that
we keep the bullet's pixels (made transparent against the white, so they
sit on any slide background) and where it sits relative to the text, in
em of the probe size: the canvas then draws the theme's own bullet — ball,
triangle, square or circle, in the theme's colour — next to each list item.

Plain numpy over raw RGB bytes, so it is testable without Qt or a PDF.
"""
from __future__ import annotations

from dataclasses import dataclass

_INK = 0.10          # alpha above which a pixel counts as ink
_GAP = 2             # empty columns that separate the bullet from the text


@dataclass
class BulletGlyph:
    level: int
    size_pt: float        # probe font size
    rgba: bytes           # straight-alpha RGBA of the bullet crop
    w_px: int
    h_px: int
    width_em: float       # bullet ink width / font size
    height_em: float
    top_em: float         # bullet ink top above the text baseline
    gap_em: float         # bullet right edge → text left edge
    indent_em: float      # list left edge → text left edge
    baseline_em: float = 0.0   # crop top → first baseline (probe row)


def _coverage(rgb: bytes, width: int, height: int, stride: int):
    """Per-pixel coverage over white ("colour to alpha"), as a float array
    of shape (height, width), plus the RGB array."""
    import numpy as np
    arr = np.frombuffer(rgb, dtype=np.uint8)[:height * stride]
    arr = arr.reshape(height, stride)[:, :width * 3].reshape(height, width, 3)
    return (255 - arr.min(axis=2)).astype(np.float32) / 255.0, arr


def _runs(flags, gap: int) -> list[tuple[int, int]]:
    """[start, end) spans of True, merging holes shorter than *gap*."""
    runs: list[list[int]] = []
    for i, on in enumerate(flags):
        if not on:
            continue
        if runs and i - runs[-1][1] < gap:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1])
    return [(a, b) for a, b in runs]


def analyse_cell(rgb: bytes, width: int, height: int, stride: int,
                 px_per_pt: float, size_pt: float, level: int,
                 text_origin_px: float = 0.0) -> BulletGlyph | None:
    """Find the bullet and the "x" in one rendered probe row.

    *text_origin_px* is the x of the list's left edge inside the crop,
    used for the indent. Returns None when the row doesn't look like
    "bullet, gap, x" (e.g. a white-on-white theme)."""
    import numpy as np
    if width <= 0 or height <= 0:
        return None
    alpha, arr = _coverage(rgb, width, height, stride)
    ink = alpha > _INK
    groups = _runs(ink.any(axis=0).tolist(), _GAP)
    if len(groups) < 2:
        return None
    (bx0, bx1), (tx0, tx1) = groups[0], groups[-1]

    def rows_of(x0: int, x1: int):
        ys = np.nonzero(ink[:, x0:x1].any(axis=1))[0]
        return (int(ys[0]), int(ys[-1]) + 1) if len(ys) else None

    brow, trow = rows_of(bx0, bx1), rows_of(tx0, tx1)
    if brow is None or trow is None:
        return None
    by0, by1 = brow
    baseline = trow[1]                  # "x" has no descender
    # Crop with a 1px margin for the anti-aliased edge.
    cx0, cx1 = max(0, bx0 - 1), min(width, bx1 + 1)
    cy0, cy1 = max(0, by0 - 1), min(height, by1 + 1)
    a = alpha[cy0:cy1, cx0:cx1]
    c = arr[cy0:cy1, cx0:cx1].astype(np.float32)
    safe = np.where(a > 0, a, 1.0)[..., None]
    # Un-mix from white: c = a*ink + (1-a)*255.
    colour = np.clip((c - (1 - a[..., None]) * 255) / safe, 0, 255)
    rgba = np.dstack([colour, a * 255]).round().astype(np.uint8)
    rgba[a <= 0] = 0
    em = px_per_pt * size_pt
    return BulletGlyph(
        level=level, size_pt=size_pt, rgba=rgba.tobytes(),
        w_px=cx1 - cx0, h_px=cy1 - cy0,
        width_em=(cx1 - cx0) / em, height_em=(cy1 - cy0) / em,
        top_em=(baseline - cy0) / em,
        gap_em=(tx0 - cx1) / em,
        indent_em=(tx0 - text_origin_px) / em,
        baseline_em=baseline / em)


def glyphs_from_pdf(pdf, deck, zoom: float = 6.0) -> dict[int, list[BulletGlyph]]:
    """Analyse the bullet-probe pages at the end of a backdrop PDF (a
    pymupdf document). Returns {level: [glyph per probe size]}."""
    import pymupdf
    from .serializer import (PROBE_LEVELS, PROBE_SIZES, probe_cell,
                             probe_list_left)
    out: dict[int, list[BulletGlyph]] = {}
    first = pdf.page_count - len(PROBE_SIZES)
    if first < 0:
        return out
    for k, size in enumerate(PROBE_SIZES):
        page = pdf[first + k]
        pw, ph = page.rect.width, page.rect.height
        for level in range(1, PROBE_LEVELS + 1):
            x0, y0, x1, y1 = probe_cell(deck, level)
            clip = pymupdf.Rect(x0 * pw, y0 * ph, x1 * pw, y1 * ph)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom),
                                  clip=clip, alpha=False)
            origin = (probe_list_left(deck) - x0) * pw * zoom
            g = analyse_cell(pix.samples, pix.width, pix.height, pix.stride,
                             zoom, size, level, origin)
            if g is not None:
                out.setdefault(level, []).append(g)
    return out


def nearest(glyphs: list[BulletGlyph], size_pt: float) -> BulletGlyph | None:
    """The probe closest in size to *size_pt* (bullets don't all scale
    linearly with the font — beamer's ball is a fixed size)."""
    if not glyphs:
        return None
    return min(glyphs, key=lambda g: abs(g.size_pt - size_pt))
