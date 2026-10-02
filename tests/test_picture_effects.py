"""Picture effects: model round-trip, baking, serializer and pptx mapping."""
from PIL import Image

from kherveslide import image_effects, pptx_import, serializer
from kherveslide.model import (
    Deck, Slide, SlidePicture, deck_from_json, deck_to_json,
)


def _png(tmp_path, size=(40, 20)):
    p = tmp_path / "a.png"
    Image.new("RGB", size, "red").save(p)
    return str(p)


def test_effects_round_trip():
    pic = SlidePicture(path="x.png", fade="left", fade_start=0.1,
                       fade_end=0.4, soft_edge=0.1, recolor="sepia",
                       glow_color="#ff0000", glow_size=0.1, reflection=0.3)
    back = deck_from_json(deck_to_json(Deck(slides=[Slide(objects=[pic])])))
    got = back.slides[0].objects[0]
    for k in image_effects.EFFECT_FIELDS:
        assert getattr(got, k) == getattr(pic, k)


def test_no_effects_by_default(tmp_path):
    assert not image_effects.has_effects(SlidePicture(path=_png(tmp_path)))


def test_fade_makes_left_transparent(tmp_path):
    pic = SlidePicture(path=_png(tmp_path), fade="left",
                       fade_start=0.2, fade_end=0.6)
    with Image.open(pic.path) as im:
        out = image_effects.render(im, pic)
    a = out.getchannel("A")
    assert a.getpixel((0, 10)) == 0 and a.getpixel((39, 10)) == 255


def test_reflection_pads_below(tmp_path):
    pic = SlidePicture(path=_png(tmp_path), reflection=0.5)
    assert image_effects.padding(pic) == (0, 0, 0, 0.5)
    with Image.open(pic.path) as im:
        assert image_effects.render(im, pic).size == (40, 30)


def test_serializer_uses_baked_png(tmp_path):
    pic = SlidePicture(path=_png(tmp_path), soft_edge=0.2, crop_l=0.1)
    tex = serializer._serialize_picture(pic)
    assert "kherveslide_effects" in tex and "adjincludegraphics" not in tex


def test_white_overlay_becomes_picture_fade():
    pic = SlidePicture(x=0.2, y=0, w=0.8, h=1, path="p.png")
    # Gradient running right-to-left: clear at the overlay's right edge,
    # solid white from half-way along it.
    overlay = (180.0, [(0.0, 0.0), (0.5, 1.0), (1.0, 1.0)])
    pptx_import._apply_fade_overlay([pic], (0, 0, 0.6, 1), overlay)
    assert pic.fade == "left"
    assert abs(pic.fade_start - 0.125) < 1e-6
    assert abs(pic.fade_end - 0.5) < 1e-6


def test_overlay_solid_on_start_side():
    pic = SlidePicture(x=0.2, y=0, w=0.8, h=1, path="p.png")
    overlay = (0.0, [(0.0, 1.0), (0.5, 0.5), (1.0, 0.0)])
    pptx_import._apply_fade_overlay([pic], (0.2, 0, 0.4, 1), overlay)
    assert pic.fade == "left"
    assert abs(pic.fade_start - 0.0) < 1e-6
    assert abs(pic.fade_end - 0.5) < 1e-6


def test_radial_overlay():
    pic = SlidePicture(x=0, y=0, w=1, h=1, path="p.png")
    overlay = ("radial", [(0.42, 0.0), (0.78, 1.0), (1.0, 1.0)])
    pptx_import._apply_fade_overlay([pic], (0, 0, 1, 1), overlay)
    assert pic.fade == "radial"
    assert abs(pic.fade_start - 0.22) < 1e-6
    assert abs(pic.fade_end - 0.58) < 1e-6
