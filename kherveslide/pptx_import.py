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
    # "\\" itself, so adding our own doubled them ("\\ \\" → "There's no
    # line here to end"). An empty paragraph keeps its gap as an empty box.
    return "\n".join(ln if ln.strip() else "\\mbox{}" for ln in lines)


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
                    objs.append(SlidePicture(
                        x=x, y=y, w=w or 0.3, h=h or 0.3, path=fname,
                        keep_aspect=False, locked=False))
                elif shape.shape_type == MSO_SHAPE_TYPE.MEDIA:
                    vid_n += 1
                    video, poster = _extract_movie(shape, media, vid_n)
                    if video:
                        objs.append(SlideVideo(
                            x=x, y=y, w=w or 0.5, h=h or 0.4,
                            path=video, poster=poster, locked=False))
                elif shape.shape_type == MSO_SHAPE_TYPE.LINE:
                    objs.append(SlideLine(x=x, y=y, w=w, h=h, locked=False))
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
