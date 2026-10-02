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


def test_blank_lines_become_visible_blank_lines():
    tex = serializer._apply_linebreaks("a\n\n\nb")
    assert tex == "a \\\\\n\\mbox{} \\\\\n\\mbox{} \\\\\nb"


def test_trailing_and_list_blank_lines_left_alone():
    assert serializer._apply_linebreaks("a\n\n") == "a\n\n"
    body = "\\begin{itemize}\n\\item x\n\n\\end{itemize}"
    assert serializer._apply_linebreaks(body) == body


def test_legacy_mbox_lines_load_as_empty_lines():
    from kherveslide.model import deck_from_json, deck_to_json, Deck, Slide, SlideText
    deck = Deck(slides=[Slide(objects=[SlideText(text="a\n\\mbox{}\nb")])])
    back = deck_from_json(deck_to_json(deck))
    assert back.slides[0].objects[0].text == "a\n\nb"
