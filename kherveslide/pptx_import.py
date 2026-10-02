"""Import Microsoft PowerPoint (.pptx) decks into the KherveSlide model.

PowerPoint positions every shape absolutely, which maps cleanly onto our
free-positioned (unlocked) objects: each shape's EMU geometry becomes a
0..1 fraction of the slide, and the deck's page size is set to the
PowerPoint slide size so fonts (in points) land at the right scale.

Best-effort: text runs keep bold/italic/colour/alignment, pictures and
embedded videos (with their poster frames) are extracted to a media
folder, tables and straight connectors come across. Anything
unrecognised is skipped rather than aborting the import. Needs the
optional ``python-pptx`` package.
"""
from __future__ import annotations

from pathlib import Path

from .model import (
    Deck, Slide, SlideText, SlidePicture, SlideTable, SlideLine, SlideVideo,
)

_EMU_PER_CM = 360000.0


def available() -> bool:
    try:
        import pptx  # noqa: F401
        return True
    except Exception:
        return False


_SPECIALS = [("\\", "\\textbackslash{}"), ("&", "\\&"), ("%", "\\%"),
             ("$", "\\$"), ("#", "\\#"), ("_", "\\_"), ("{", "\\{"),
             ("}", "\\}"), ("~", "\\textasciitilde{}"),
             ("^", "\\textasciicircum{}")]


def _escape(text: str) -> str:
    out = text or ""
    for ch, rep in _SPECIALS:
        out = out.replace(ch, rep)
    return out


def _frac(value, total) -> float:
    if value is None or not total:
        return 0.0
    return round(max(0.0, min(1.0, value / total)), 4)


def _run_latex(run) -> str:
    t = _escape(run.text)
    if not t:
        return ""
    f = run.font
    if f.italic:
        t = f"\\textit{{{t}}}"
    if f.bold:
        t = f"\\textbf{{{t}}}"
    return t


def _text_of(tf) -> str:
    """Paragraphs joined with LaTeX line breaks, runs styled."""
    lines = []
    for para in tf.paragraphs:
        parts = [_run_latex(r) for r in para.runs]
        line = "".join(p for p in parts if p)
        if not line and para.text:
            line = _escape(para.text)
        lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    # One paragraph per line: the serializer turns each newline into a
    # "\\" (and an empty line into a visible blank line) itself.
    return "\n".join(lines)


# Formats XeTeX's \\includegraphics reads; anything else (gif, bmp,
# tiff, wmf, emf...) is read as TeX source and fills the log with garbage.
TEX_IMAGE_EXTS = {"png", "jpg", "jpeg", "pdf", "eps"}


def _save_image(blob: bytes, ext: str, stem: Path) -> str:
    """Write a picture into the media folder in a format XeTeX can include,
    converting with Pillow when needed. Returns its path, or "" when it
    cannot be converted (e.g. WMF/EMF off Windows) — the picture then
    imports as an empty placeholder the user can fill."""
    ext = (ext or "").lower()
    if ext in TEX_IMAGE_EXTS:
        out = stem.with_suffix(f".{ext}")
        out.write_bytes(blob)
        return str(out)
    try:
        import io
        from PIL import Image
        with Image.open(io.BytesIO(blob)) as im:
            out = stem.with_suffix(".png")
            im.convert("RGBA").save(out)
            return str(out)
    except Exception:
        return ""


def _first_font_pt(tf, default: int) -> int:
    for para in tf.paragraphs:
        for run in para.runs:
            if run.font.size is not None:
                return max(6, int(round(run.font.size.pt)))
    return default


def _first_color(tf) -> str:
    for para in tf.paragraphs:
        for run in para.runs:
            try:
                if run.font.color and run.font.color.type is not None:
                    rgb = run.font.color.rgb
                    if rgb is not None:
                        return f"#{str(rgb)}"
            except Exception:
                pass
    return "#000000"


def _alignment(tf) -> str:
    from pptx.enum.text import PP_ALIGN
    for para in tf.paragraphs:
        a = para.alignment
        if a == PP_ALIGN.CENTER:
            return "center"
        if a == PP_ALIGN.RIGHT:
            return "right"
        if a == PP_ALIGN.LEFT:
            return "left"
    return "left"


def _is_title(shape) -> bool:
    try:
        if shape.is_placeholder:
            from pptx.enum.shapes import PP_PLACEHOLDER
            return shape.placeholder_format.type in (
                PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE)
    except Exception:
        pass
    return False


def _extract_movie(shape, media: Path, n: int) -> tuple[str, str]:
    """Pull the video (and its poster frame) out of a movie shape.
    Returns ``(video_path, poster_path)``, empty strings when missing.

    An embedded video lives as a media part inside the .pptx zip, pointed
    at by the shape's ``<a:videoFile r:link="rIdN"/>``; its bytes are
    written out next to the extracted images. A *linked* (not embedded)
    video keeps its original location. Audio media has ``a:audioFile``
    instead and is skipped."""
    from pptx.oxml.ns import qn

    els = shape._element.xpath(".//a:videoFile")
    if not els:
        return "", ""
    rel = shape.part.rels[els[0].get(qn("r:link"))]
    if rel.is_external:
        video = rel.target_ref
    else:
        part = rel.target_part
        ext = Path(str(part.partname)).suffix or ".mp4"
        media.mkdir(parents=True, exist_ok=True)
        out = media / f"video_{n:03d}{ext}"
        out.write_bytes(part.blob)
        video = str(out)
    poster = ""
    try:
        img = shape.poster_frame
        if img is not None:
            media.mkdir(parents=True, exist_ok=True)
            p = media / f"video_{n:03d}_poster.{img.ext}"
            p.write_bytes(img.blob)
            poster = str(p)
    except Exception:
        poster = ""              # no poster is fine — placeholder shows
    return video, poster


# ------------------------------------------------------- picture effects
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_A14 = "{http://schemas.microsoft.com/office/drawing/2010/main}"


def _pct(el, attr, default=0.0) -> float:
    """A DrawingML percentage attribute (100000 = 100 %) as a fraction."""
    v = el.get(attr) if el is not None else None
    return int(v) / 100000.0 if v not in (None, "") else default


def _clr_hex(parent) -> str:
    """First srgbClr under *parent* as #rrggbb ("" if none / scheme)."""
    if parent is None:
        return ""
    el = parent.find(f".//{_A}srgbClr")
    return f"#{el.get('val').lower()}" if el is not None else ""


def _picture_effects(shape, pic: SlidePicture) -> None:
    """Carry PowerPoint's picture formatting onto *pic*: crop, transparency,
    corrections, colour, artistic effects, soft edges, glow, reflection
    and shadow. Anything unreadable is left at its neutral value."""
    for side in ("left", "top", "right", "bottom"):
        try:
            v = float(getattr(shape, f"crop_{side}"))
        except Exception:
            v = 0.0
        setattr(pic, f"crop_{side[0]}", max(0.0, min(0.9, v)))
    el = shape._element
    blip = el.find(f".//{_A}blip")
    if blip is not None:
        amf = blip.find(f"{_A}alphaModFix")
        if amf is not None:
            pic.opacity = _pct(amf, "amt", 1.0)
        if blip.find(f"{_A}grayscl") is not None:
            pic.recolor = "grayscale"
        duo = blip.find(f"{_A}duotone")
        if duo is not None:
            pic.recolor = "duotone"
            pic.recolor_color = _clr_hex(duo) or "#1f4e79"
        if blip.find(f"{_A}biLevel") is not None:
            pic.recolor = "bw"
        lum = blip.find(f"{_A}lum")
        if lum is not None:
            pic.brightness = _pct(lum, "bright")
            pic.contrast = _pct(lum, "contrast")
        # Office 2010 image effects live in an extension list.
        for eff in blip.iter(f"{_A14}imgEffect"):
            for child in eff:
                tag = child.tag.replace(_A14, "")
                if tag == "brightnessContrast":
                    pic.brightness = _pct(child, "bright")
                    pic.contrast = _pct(child, "contrast")
                elif tag == "saturation":
                    pic.saturation = _pct(child, "sat", 1.0)
                elif tag == "colorTemperature":
                    t = int(child.get("colorTemp", "6500"))
                    pic.temperature = max(-1.0, min(1.0, (6500 - t) / 4000))
                elif tag == "sharpenSoften":
                    pic.sharpness = _pct(child, "amount")
                elif tag.startswith("artistic"):
                    pic.artistic = _ARTISTIC_MAP.get(tag, "")
    effects = el.find(f".//{_A}effectLst")
    if effects is not None:
        ext = el.find(f".//{_A}xfrm/{_A}ext")
        side = min(int(ext.get("cx")), int(ext.get("cy"))) if ext is not None else 0
        soft = effects.find(f"{_A}softEdge")
        if soft is not None and side:
            pic.soft_edge = min(0.5, int(soft.get("rad", "0")) / side)
        glow = effects.find(f"{_A}glow")
        if glow is not None and side:
            pic.glow_color = _clr_hex(glow) or "#ffd966"
            pic.glow_size = min(0.3, int(glow.get("rad", "0")) / side)
        refl = effects.find(f"{_A}reflection")
        if refl is not None:
            pic.reflection = max(0.05, _pct(refl, "endPos", 0.5))
        if effects.find(f"{_A}outerShdw") is not None:
            pic.shadow = True


_ARTISTIC_MAP = {
    "artisticBlur": "blur", "artisticPencilSketch": "pencil",
    "artisticPencilGrayscale": "pencil", "artisticLineDrawing": "line_drawing",
    "artisticMosaicBubbles": "mosaic", "artisticPastelsSmooth": "watercolor",
    "artisticWatercolorSponge": "watercolor", "artisticPaintStrokes":
    "watercolor", "artisticCutout": "posterize", "artisticPhotocopy": "bw",
    "artisticGlowEdges": "glow_edges", "artisticGlowDiffused": "blur",
    "artisticChalkSketch": "pencil", "artisticMarker": "posterize",
    "artisticCement": "emboss", "artisticTexturizer": "emboss",
    "artisticPlasticWrap": "emboss", "artisticFilmGrain": "",
    "artisticCrisscrossEtching": "pencil", "artisticLightScreen": "washout",
}


def _white_fade_overlay(shape):
    """A rectangle filled with a white (background) gradient that runs
    from see-through to solid — PowerPoint's usual way of fading a photo
    into the slide. Returns ``(angle_deg, [(pos, alpha), ...])`` or None."""
    el = shape._element
    if not el.tag.endswith("}sp"):
        return None
    if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
        return None
    grad = el.find(f".//{_A}gradFill")
    if grad is None:
        return None
    stops = []
    for gs in grad.iter(f"{_A}gs"):
        clr = gs[0] if len(gs) else None
        if clr is None:
            return None
        tag = clr.tag.replace(_A, "")
        val = (clr.get("val") or "").lower()
        if not ((tag == "schemeClr" and val in ("bg1", "lt1"))
                or (tag == "srgbClr" and val == "ffffff")
                or (tag == "prstClr" and val == "white")):
            return None
        a = clr.find(f"{_A}alpha")
        stops.append((int(gs.get("pos", "0")) / 100000.0,
                      _pct(a, "val", 1.0) if a is not None else 1.0))
    if len(stops) < 2 or min(a for _, a in stops) > 0.05:
        return None
    if grad.find(f"{_A}path") is not None:
        return "radial", sorted(stops)
    lin = grad.find(f"{_A}lin")
    ang = int(lin.get("ang", "0")) / 60000.0 if lin is not None else 0.0
    return ang % 360, sorted(stops)


def _apply_fade_overlay(objs, rect, overlay) -> None:
    """Turn a white fade overlay into a fade on the picture beneath it.
    The picture is see-through where the overlay is solid, so the slide's
    white shows through exactly as in PowerPoint."""
    ang, stops = overlay
    rx, ry, rw, rh = rect
    pic = next((o for o in reversed(objs) if isinstance(o, SlidePicture)
                and o.path and o.x < rx + rw and rx < o.x + o.w
                and o.y < ry + rh and ry < o.y + o.h), None)
    if pic is None:
        return
    clear = next(p for p, a in stops if a <= 0.05)
    # The solid stop nearest the clear one bounds the fade.
    solid = min((p for p, a in stops if a >= 0.95),
                key=lambda p: abs(p - clear), default=1.0)
    if ang == "radial":
        # Path gradients run from the centre (pos 0) to the edges.
        pic.fade = "radial"
        pic.fade_start = max(0.0, min(1.0, 1 - solid))
        pic.fade_end = max(0.0, min(1.0, 1 - clear))
        return
    axis = int(round(ang / 90.0)) % 4       # 0 →, 1 ↓, 2 ←, 3 ↑
    if axis in (0, 2):
        lo, size, plo, psize = rx, rw, pic.x, pic.w
    else:
        lo, size, plo, psize = ry, rh, pic.y, pic.h

    def at(p):                 # slide coordinate of gradient position p
        return lo + p * size if axis in (0, 1) else lo + size - p * size

    sv, cv = at(solid), at(clear)
    if sv < cv:                # see-through towards the left / top
        pic.fade = "left" if axis in (0, 2) else "top"
        to_t = lambda v: (v - plo) / psize
    else:
        pic.fade = "right" if axis in (0, 2) else "bottom"
        to_t = lambda v: (plo + psize - v) / psize
    pic.fade_start = max(0.0, min(1.0, to_t(sv)))
    pic.fade_end = max(0.0, min(1.0, to_t(cv)))


def import_pptx(path, media_dir) -> Deck:
    """Parse *path* (a .pptx) into a :class:`Deck`. Extracted images are
    written under *media_dir*."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(str(path))
    sw, sh = prs.slide_width, prs.slide_height
    media = Path(media_dir)
    img_n = 0
    vid_n = 0
    slides: list[Slide] = []

    for slide in prs.slides:
        objs: list = []
        for shape in slide.shapes:
            try:
                x, y = _frac(shape.left, sw), _frac(shape.top, sh)
                w, h = _frac(shape.width, sw), _frac(shape.height, sh)
                if shape.has_table:
                    tbl = shape.table
                    rows = [[_escape(c.text) for c in row.cells]
                            for row in tbl.rows]
                    objs.append(SlideTable(x=x, y=y, w=w or 0.5, h=h or 0.25,
                                           rows=rows, locked=False))
                elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    img = shape.image
                    img_n += 1
                    media.mkdir(parents=True, exist_ok=True)
                    fname = _save_image(img.blob, img.ext,
                                        media / f"img_{img_n:03d}")
                    pic = SlidePicture(
                        x=x, y=y, w=w or 0.3, h=h or 0.3, path=fname,
                        keep_aspect=False, locked=False)
                    _picture_effects(shape, pic)
                    objs.append(pic)
                elif shape.shape_type == MSO_SHAPE_TYPE.MEDIA:
                    vid_n += 1
                    video, poster = _extract_movie(shape, media, vid_n)
                    if video:
                        objs.append(SlideVideo(
                            x=x, y=y, w=w or 0.5, h=h or 0.4,
                            path=video, poster=poster, locked=False))
                elif shape.shape_type == MSO_SHAPE_TYPE.LINE:
                    objs.append(SlideLine(x=x, y=y, w=w, h=h, locked=False))
                elif (overlay := _white_fade_overlay(shape)) is not None:
                    _apply_fade_overlay(objs, (x, y, w, h), overlay)
                elif shape.has_text_frame and shape.text_frame.text.strip():
                    tf = shape.text_frame
                    objs.append(SlideText(
                        x=x, y=y, w=w or 0.4, h=h or 0.15,
                        text=_text_of(tf),
                        font_pt=_first_font_pt(tf, 32 if _is_title(shape) else 18),
                        color=_first_color(tf),
                        align=_alignment(tf),
                        locked=False))
            except Exception:
                continue          # skip a shape we can't read, keep going
        slides.append(Slide(objects=objs))

    if not slides:
        slides = [Slide()]
    return Deck(
        slides=slides,
        title=(prs.core_properties.title or "Imported presentation"),
        page_w_cm=round(sw / _EMU_PER_CM, 3) if sw else 0.0,
        page_h_cm=round(sh / _EMU_PER_CM, 3) if sh else 0.0,
        plain_frames=True,
        template="PowerPoint import",
    )
