"""Imported PowerPoint pictures/text must compile under XeTeX."""
import io

from kherveslide import pptx_import, serializer
from kherveslide.model import SlidePicture


def test_gif_is_converted_to_png(tmp_path):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="GIF")
    out = pptx_import._save_image(buf.getvalue(), "gif", tmp_path / "img_001")
    assert out.endswith(".png")


def test_unconvertible_image_becomes_placeholder(tmp_path):
    out = pptx_import._save_image(b"not an image", "wmf", tmp_path / "img_001")
    assert out == ""


def test_png_kept_as_is(tmp_path):
    out = pptx_import._save_image(b"x", "png", tmp_path / "img_001")
    assert out.endswith("img_001.png")


def test_serializer_skips_unincludable_formats():
    tex = serializer._serialize_picture(
        SlidePicture(x=0, y=0, w=0.2, h=0.2, path="/a/b.wmf"))
    assert "includegraphics" not in tex and "framebox" in tex


class _Para:
    def __init__(self, text):
        self.text = text
        self.runs = []


class _TF:
    def __init__(self, texts):
        self.paragraphs = [_Para(t) for t in texts]


def test_empty_paragraphs_never_make_bare_linebreaks():
    body = pptx_import._text_of(_TF(["a", "", "", "b"]))
    assert body == "a\n\\mbox{}\n\\mbox{}\nb"
