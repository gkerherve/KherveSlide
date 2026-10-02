"""Tests for the WYSIWYG beamer deck: model, serializer, templates."""
import json
from pathlib import Path

import pytest

from kherveslide.model import (
    Deck, Slide, SlideText, SlidePicture, SlideTable, SlideLine, SlideShape,
    ThemeSpec, deck_to_json, deck_from_json,
    raise_object, lower_object, to_front, to_back,
)
from kherveslide.serializer import serialize_deck
from kherveslide import templates


# --- model round-trip ---

def _sample_deck():
    return Deck(
        title="Talk", author="Me", theme="Madrid", aspect="169",
        plain_frames=True,
        slides=[
            Slide(title="Intro", bg="#FFEECC", objects=[
                SlideText(x=0.1, y=0.2, w=0.5, h=0.3, text="Hello $x^2$",
                          font_pt=28, color="#112233", align="center",
                          bold=True),
                SlidePicture(x=0.6, y=0.1, w=0.3, h=0.4, path="img/a.png"),
            ]),
            Slide(objects=[SlideText(text="Second")]),
        ])


def test_deck_round_trip():
    deck = _sample_deck()
    assert deck_from_json(deck_to_json(deck)) == deck


def test_deck_json_is_valid_json():
    json.loads(deck_to_json(_sample_deck()))


def test_deck_from_json_rejects_non_deck():
    with pytest.raises(ValueError):
        deck_from_json(json.dumps({"type": "Document"}))


# --- z-order ---

def test_zorder_raise_lower():
    s = Slide(objects=[SlideText(text="a"), SlideText(text="b"),
                       SlideText(text="c")])
    assert raise_object(s, 0) == 1
    assert s.objects[1].text == "a"
    assert lower_object(s, 1) == 0
    assert s.objects[0].text == "a"


def test_zorder_front_back():
    s = Slide(objects=[SlideText(text="a"), SlideText(text="b"),
                       SlideText(text="c")])
    assert to_front(s, 0) == 2
    assert s.objects[-1].text == "a"
    assert to_back(s, 2) == 0
    assert s.objects[0].text == "a"


def test_zorder_bounds_are_noops():
    s = Slide(objects=[SlideText(text="a"), SlideText(text="b")])
    assert raise_object(s, 1) == 1     # already top
    assert lower_object(s, 0) == 0     # already bottom


# --- serializer ---

def test_serialize_uses_textpos_absolute():
    tex = serialize_deck(_sample_deck())
    assert "\\usepackage[absolute,overlay]{textpos}" in tex
    # gap=0 -> the full page is the content area (1 * paperwidth/height)
    assert "\\setlength{\\TPHorizModule}{1\\paperwidth}" in tex
    assert "\\setlength{\\TPVertModule}{1\\paperheight}" in tex


def test_serialize_documentclass_aspect_and_theme():
    tex = serialize_deck(_sample_deck())
    assert "\\documentclass[aspectratio=169]{beamer}" in tex
    assert "\\usetheme{Madrid}" in tex


def test_serialize_43_has_no_aspect_option():
    tex = serialize_deck(Deck(aspect="43", slides=[Slide()]))
    assert "\\documentclass{beamer}" in tex


def test_serialize_textblock_coordinates():
    # Unstarred textblock with module-relative width and coordinates: the
    # modules are bound to \paperwidth/\paperheight so a bare 0.4 is half
    # the slide's quarter-width and (0.25,0.5) is the box's top-left.
    deck = Deck(slides=[Slide(objects=[
        SlideText(x=0.25, y=0.5, w=0.4, h=0.1, text="X", locked=False)])])
    tex = serialize_deck(deck)
    assert "\\begin{textblock}{0.4}(0.25,0.5)" in tex
    assert "\\textblockorigin{0\\paperwidth}{0\\paperheight}" in tex


def test_decorations_shown_by_default():
    # A fresh deck now shows theme decorations (frames are not [plain]).
    assert Deck().plain_frames is False
    tex = serialize_deck(Deck(theme="Madrid", slides=[Slide()],
                              nav_symbols=False))
    assert "[plain" not in tex


def test_serialize_shape_rectangle_and_ellipse():
    from kherveslide.model import SlideShape
    deck = Deck(slides=[Slide(objects=[
        SlideShape(shape="rect", fill="#ff0000", border_color="#0000ff",
                   border_width=2.0, style="dashed", corner="rounded"),
        SlideShape(shape="ellipse", border_color="#00aa00", rotation=30.0),
    ])], nav_symbols=False, plain_frames=True)
    tex = serialize_deck(deck)
    assert "\\usepackage{tikz}" in tex
    assert "ellipse" in tex                               # ellipse path
    assert "rounded corners=6pt" in tex                  # rect with rounded corners
    assert "fill=ksfill0" in tex
    assert "dashed" in tex
    assert "rotate around={-30" in tex                   # screen CW → tikz CCW


def test_shapes_library_all_serialize():
    from kherveslide import shapes
    from kherveslide.model import SlideShape
    # Every catalogued shape produces a closed tikz path or ellipse and
    # serialises without error.
    for key in shapes.ALL:
        tex = serialize_deck(Deck(slides=[Slide(objects=[
            SlideShape(shape=key, fill="#abcdef")])], nav_symbols=False))
        assert "\\begin{tikzpicture}" in tex
        kind = shapes.outline(key)
        if kind[0] == "poly":
            assert "-- cycle" in tex
        elif kind[0] == "ellipse":
            assert "ellipse [x radius=" in tex


def test_add_shape_appends_shape(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    from kherveslide.model import SlideShape
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.clear()
    w._add_shape("octagon")
    assert isinstance(w.slide.objects[-1], SlideShape)
    assert w.slide.objects[-1].shape == "octagon"


def test_shape_inline_obeys_zorder():
    from kherveslide.model import SlideShape
    # No beamer-placed object: the shape is placed inline via textpos (so it
    # z-stacks by source order), NOT a page-absolute overlay.
    tex = serialize_deck(Deck(slides=[Slide(objects=[
        SlideShape(shape="rect", fill="#ff0000")])], nav_symbols=False))
    assert "\\begin{textblock}" in tex
    assert "remember picture" not in tex


def test_shape_sent_behind_locked_uses_background():
    from kherveslide.model import SlideShape
    # Shape FIRST, beamer-placed text AFTER → the shape was sent to the back,
    # so it is drawn in the frame's background template (the only layer under
    # the flow body), using a page-absolute tikz overlay.
    behind = serialize_deck(Deck(slides=[Slide(objects=[
        SlideShape(shape="rect", fill="#ff0000"),
        SlideText(text="Hi", locked=True)])], nav_symbols=False))
    assert "\\setbeamertemplate{background}" in behind
    assert "remember picture" in behind
    # Shape AFTER the text → ordinary inline foreground, no background template.
    front = serialize_deck(Deck(slides=[Slide(objects=[
        SlideText(text="Hi", locked=True),
        SlideShape(shape="rect", fill="#ff0000")])], nav_symbols=False))
    assert "\\setbeamertemplate{background}" not in front


def test_scene_has_pasteboard_around_page():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide.canvas import SlideScene
    s = SlideScene("169")
    pr, sr = s.page_rect(), s.sceneRect()
    # The scene extends past the page on every side so a box can be parked off
    # the slide, while the page rect still reports just the slide.
    assert sr.left() < pr.left() and sr.top() < pr.top()
    assert sr.right() > pr.right() and sr.bottom() > pr.bottom()
    assert (pr.width(), pr.height()) == (s.page_w, s.page_h)


def test_line_endpoints_any_direction():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide.canvas import LineBoxItem, page_size_px
    from kherveslide.model import SlideLine
    pw, ph, fs = page_size_px("169", 0.0, 0.0)
    o = SlideLine(x=0.7, y=0.6, w=-0.4, h=-0.3)   # runs up-and-left
    it = LineBoxItem(o, pw, ph, 0.0, fs)
    assert abs(it._rect.width() - 0.4 * pw) < 1.0
    assert abs(it._rect.height() - 0.3 * ph) < 1.0
    p1, p2 = it._endpoints_local()
    assert p1.x() > p2.x() and p1.y() > p2.y()


def test_reversed_line_serialises_positive_width():
    from kherveslide.model import SlideLine
    tex = serialize_deck(Deck(slides=[Slide(objects=[
        SlideLine(x=0.7, y=0.6, w=-0.4, h=-0.3)])], nav_symbols=False))
    # the textblock width is the absolute extent, never negative
    assert "\\begin{textblock}{0.4}(0.3,0.3)" in tex


def test_serialize_line_style_and_opacity():
    deck = Deck(slides=[Slide(objects=[
        SlideLine(arrow_end=True, style="dotted", opacity=0.4)])],
        nav_symbols=False, plain_frames=True)
    tex = serialize_deck(deck)
    assert "dotted" in tex
    assert "draw opacity=0.4" in tex
    assert "Stealth" in tex


def test_add_rect_appends_shape(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    from kherveslide.model import SlideShape
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.clear()
    w._add_rect()
    w._add_ellipse()
    kinds = [(o.type, getattr(o, "shape", None)) for o in w.slide.objects]
    assert ("SlideShape", "rect") in kinds
    assert ("SlideShape", "ellipse") in kinds


def test_serialize_frames_are_plain():
    tex = serialize_deck(_sample_deck())
    assert "\\begin{frame}[plain,t]" in tex


def test_serialize_decorated_frames_when_not_plain():
    deck = _sample_deck()
    deck.plain_frames = False
    tex = serialize_deck(deck)
    assert "\\begin{frame}[plain]" not in tex
    assert "\\begin{frame}" in tex


def test_plain_frames_round_trip():
    deck = _sample_deck()
    deck.plain_frames = False
    assert deck_from_json(deck_to_json(deck)) == deck


# --- page setup: size + gap ---

def test_serialize_loads_lmodern():
    assert "\\usepackage{lmodern}" in serialize_deck(_sample_deck())


def test_serialize_custom_page_size():
    deck = Deck(page_w_cm=20, page_h_cm=12, slides=[Slide()])
    tex = serialize_deck(deck)
    assert "\\usepackage{geometry}" in tex
    assert "papersize={20cm,12cm}" in tex


def test_serialize_no_geometry_without_custom_size():
    assert "\\usepackage{geometry}" not in serialize_deck(_sample_deck())


def test_serialize_gap_insets_textpos():
    deck = Deck(gap=0.1, slides=[Slide()])
    tex = serialize_deck(deck)
    assert "\\setlength{\\TPHorizModule}{0.8\\paperwidth}" in tex
    assert "\\textblockorigin{0.1\\paperwidth}{0.1\\paperheight}" in tex


def test_serialize_zero_gap_is_full_page():
    tex = serialize_deck(_sample_deck())
    assert "\\setlength{\\TPHorizModule}{1\\paperwidth}" in tex
    assert "\\textblockorigin{0\\paperwidth}{0\\paperheight}" in tex


def test_page_fields_round_trip():
    deck = _sample_deck()
    deck.page_w_cm, deck.page_h_cm, deck.gap = 25.0, 14.0, 0.08
    assert deck_from_json(deck_to_json(deck)) == deck


def test_page_number_off_by_default():
    tex = serialize_deck(Deck(slides=[Slide()]))
    assert "\\insertframenumber" not in tex


def test_page_number_simple():
    # The number goes in the footline's right foot as \insertframenumber.
    deck = Deck(slides=[Slide()], page_number="number")
    tex = serialize_deck(deck)
    assert "\\insertframenumber" in tex
    assert "\\inserttotalframenumber" not in tex
    assert "\\setbeamertemplate{footline}" in tex


def test_page_number_of_total():
    deck = Deck(slides=[Slide(), Slide()], page_number="of_total")
    tex = serialize_deck(deck)
    # The right foot carries a single footline template (not one per slide).
    assert "\\insertframenumber\\,/\\,\\inserttotalframenumber" in tex
    assert "\\setbeamertemplate{footline}" in tex
    assert tex.count("\\insertframenumber") == 1


def test_page_number_plain_frames_use_overlay():
    # Plain frames suppress the footline, so the number is overlaid per slide.
    deck = Deck(slides=[Slide(), Slide()], page_number="number",
                plain_frames=True)
    tex = serialize_deck(deck)
    assert tex.count("\\insertframenumber") == 2      # one overlay per slide
    assert "\\begin{textblock}" in tex


def test_page_number_round_trip():
    deck = Deck(slides=[Slide()], page_number="of_total")
    assert deck_from_json(deck_to_json(deck)) == deck


def test_nav_symbols_shown_by_default():
    # _sample_deck uses plain frames, where beamer drops the native symbols
    # with the footline — so we overlay them per frame and clear beamer's own.
    tex = serialize_deck(_sample_deck())
    assert "\\insertslidenavigationsymbol" in tex
    assert "\\setbeamertemplate{navigation symbols}{}" in tex


def test_nav_symbols_native_on_decorated_frames():
    # On decorated (non-plain) frames beamer shows the navigation symbols
    # natively, so we neither clear its template nor overlay them per frame —
    # no repeated per-slide navigation block.
    deck = Deck(slides=[Slide(objects=[SlideText(text="Hi", locked=True)])],
                plain_frames=False, nav_symbols=True)
    tex = serialize_deck(deck)
    assert "\\insertslidenavigationsymbol" not in tex
    assert "\\setbeamertemplate{navigation symbols}{}" not in tex


def test_nav_symbols_overlaid_on_plain_frames():
    deck = Deck(slides=[Slide(objects=[SlideText(text="Hi", locked=True)])],
                plain_frames=True, nav_symbols=True)
    tex = serialize_deck(deck)
    assert "\\insertslidenavigationsymbol" in tex
    assert "\\setbeamertemplate{navigation symbols}{}" in tex


def test_background_alpha_blends_over_white():
    from kherveslide.model import blend_over_white
    # 50% black over white -> mid grey
    assert blend_over_white("#000000", 0.5) == "#808080"
    assert blend_over_white("#000000", 1.0) == "#000000"
    assert blend_over_white("#3366CC", 0.0) == "#FFFFFF"


def test_serialize_background_uses_blended_colour():
    deck = Deck(slides=[Slide(bg="#000000", bg_alpha=0.5)])
    tex = serialize_deck(deck)
    # The blended colour becomes beamer's background canvas (behind content).
    assert "{HTML}{808080}" in tex
    assert "\\setbeamercolor{background canvas}{bg=" in tex


def test_background_alpha_round_trip():
    deck = Deck(slides=[Slide(bg="#3366CC", bg_alpha=0.4)])
    assert deck_from_json(deck_to_json(deck)) == deck


# --- per-object lock / layout mode ---

def test_unlocked_object_uses_textpos():
    deck = Deck(slides=[Slide(objects=[SlideText(text="Hi", locked=False)])])
    tex = serialize_deck(deck)
    assert "\\begin{textblock}" in tex


def test_locked_object_flows_no_textpos():
    # nav_symbols off: a locked-only slide should emit no textblock at all.
    deck = Deck(slides=[Slide(title="Heading", objects=[
        SlideText(text="Body", locked=True),
        SlideText(text="\\begin{itemize}\\item a\\end{itemize}",
                  locked=True)])], nav_symbols=False)
    tex = serialize_deck(deck)
    assert "\\frametitle{Heading}" in tex
    assert "\\begin{textblock}" not in tex
    assert "Body" in tex


def test_side_by_side_locked_boxes_become_columns():
    # Two locked text boxes at the same height but different x are columns.
    deck = Deck(slides=[Slide(objects=[
        SlideText(x=0.05, y=0.3, w=0.4, h=0.4, text="Left", locked=True),
        SlideText(x=0.55, y=0.3, w=0.4, h=0.4, text="Right", locked=True)])])
    tex = serialize_deck(deck)
    assert "\\begin{columns}" in tex
    assert tex.count("\\begin{column}") == 2
    assert tex.index("Left") < tex.index("Right")     # ordered by x


def test_stacked_locked_boxes_do_not_make_columns():
    # Different heights → they flow one above the other, no columns.
    deck = Deck(slides=[Slide(objects=[
        SlideText(x=0.1, y=0.1, w=0.8, h=0.15, text="Top", locked=True),
        SlideText(x=0.1, y=0.5, w=0.8, h=0.3, text="Bottom", locked=True)])])
    tex = serialize_deck(deck)
    assert "\\begin{columns}" not in tex


def test_object_defaults_locked():
    assert SlideText().locked is True
    assert SlidePicture().locked is True
    assert SlideTable().locked is True


def test_mixed_lock_flows_and_overlays():
    # nav_symbols off so the only textblock is the unlocked object's.
    deck = Deck(slides=[Slide(objects=[
        SlideText(text="Flowed", locked=True),
        SlideText(text="Floated", locked=False)])], nav_symbols=False)
    tex = serialize_deck(deck)
    assert "Flowed" in tex
    assert "\\begin{textblock}" in tex          # the unlocked one
    # The flowed box is not wrapped in a textblock.
    assert tex.count("\\begin{textblock}") == 1


def test_legacy_free_slide_migrates_to_unlocked():
    # A deck saved before per-object locking (only slide.free) loads with
    # its objects' lock state derived from the slide.
    import json
    raw = json.dumps({"type": "Deck", "slides": [
        {"type": "Slide", "free": True,
         "objects": [{"type": "SlideText", "text": "x"}]},
        {"type": "Slide", "free": False,
         "objects": [{"type": "SlideText", "text": "y"}]}]})
    deck = deck_from_json(raw)
    assert deck.slides[0].objects[0].locked is False   # was free
    assert deck.slides[1].objects[0].locked is True    # was standard


def test_lock_round_trip():
    deck = Deck(slides=[Slide(objects=[SlideText(locked=False)])])
    assert deck_from_json(deck_to_json(deck)) == deck


# --- picture: opacity + clipboard helpers ---

def test_picture_defaults_locked_aspect():
    assert SlidePicture().keep_aspect is True


def test_serialize_picture_opacity():
    deck = Deck(slides=[Slide(objects=[
        SlidePicture(path="img/a.png", opacity=0.4, locked=False)])])
    tex = serialize_deck(deck)
    # Opacity is rendered with a TikZ node (the \transparent package
    # silently failed under tectonic), so tikz must be loaded.
    assert "\\usepackage{tikz}" in tex
    assert "node[opacity=0.4" in tex
    assert "\\transparent" not in tex


def test_serialize_opaque_picture_no_tikz():
    deck = Deck(slides=[Slide(objects=[SlidePicture(path="img/a.png")])])
    tex = serialize_deck(deck)
    assert "\\usepackage{tikz}" not in tex
    assert "node[opacity" not in tex


# --- spell check (optional pyspellchecker) ---

def test_spellcheck_misspelled_words_ignores_latex():
    from kherveslide import spellcheck
    if not spellcheck.available():
        pytest.skip("pyspellchecker not installed")
    # \textbf, itemize, item etc. are LaTeX, not prose — must not be flagged;
    # the genuine typo "teh" must be.
    text = "\\begin{itemize}\\item \\textbf{teh} cat $x^2$\\end{itemize}"
    words = spellcheck.misspelled_words(text)
    assert "teh" in words
    assert "textbf" not in words and "itemize" not in words


def test_spellcheck_flags_and_suggests():
    from kherveslide import spellcheck
    if not spellcheck.available():
        pytest.skip("pyspellchecker not installed")
    assert spellcheck.is_misspelled("teh") is True
    assert spellcheck.is_misspelled("physics") is False
    assert "the" in [s.lower() for s in spellcheck.suggestions("teh")]


def test_spellcheck_personal_dictionary(monkeypatch):
    from kherveslide import spellcheck
    if not spellcheck.available():
        pytest.skip("pyspellchecker not installed")
    # A word in the personal list is never flagged.
    assert spellcheck.is_misspelled("Kherve") is True
    monkeypatch.setattr(spellcheck, "_personal", lambda: {"kherve"})
    assert spellcheck.is_misspelled("Kherve") is False


def test_object_clipboard_round_trip():
    from kherveslide.model import object_to_dict, build_object
    obj = SlideText(text="hi", font_pt=22, bold=True)
    assert build_object(object_to_dict(obj)) == obj
    pic = SlidePicture(path="x.png", opacity=0.5, keep_aspect=False)
    assert build_object(object_to_dict(pic)) == pic


# --- lines / arrows ---

def test_line_round_trip():
    deck = Deck(slides=[Slide(objects=[
        SlideLine(x=0.1, y=0.2, w=0.5, h=0.3, color="#FF0000",
                  width_pt=2.0, arrow_end=True)])])
    assert deck_from_json(deck_to_json(deck)) == deck


def test_serialize_line_uses_tikz():
    deck = Deck(slides=[Slide(objects=[SlideLine(arrow_end=True)])])
    tex = serialize_deck(deck)
    assert "\\usepackage{tikz}" in tex
    assert "\\usetikzlibrary{arrows.meta}" in tex
    assert "\\begin{tikzpicture}" in tex
    assert "-{Stealth" in tex                    # sized Stealth arrowhead
    # placed inline via textpos so it obeys z-order (no page-absolute overlay)
    assert "\\begin{textblock}" in tex


def test_serialize_plain_line_has_no_arrowhead():
    deck = Deck(slides=[Slide(objects=[SlideLine()])])
    tex = serialize_deck(deck)
    assert "Stealth" not in tex


def test_no_tikz_without_lines():
    assert "\\usepackage{tikz}" not in serialize_deck(_sample_deck())


# --- theme builder ---

def test_theme_spec_disabled_emits_nothing():
    deck = Deck(slides=[Slide()], theme_spec=ThemeSpec(enabled=False,
                                                       inner="circles"))
    assert "\\useinnertheme" not in serialize_deck(deck)


def test_theme_spec_emits_subthemes_and_colours():
    spec = ThemeSpec(enabled=True, inner="circles", outer="miniframes",
                     fonts="serif", bullets="square", structure="#CC3300",
                     title_bg="#003366", frametitle_size="Large")
    tex = serialize_deck(Deck(slides=[Slide()], theme_spec=spec))
    assert "\\useinnertheme{circles}" in tex
    assert "\\useoutertheme{miniframes}" in tex
    assert "\\usefonttheme{serif}" in tex
    assert "\\setbeamertemplate{itemize items}[square]" in tex
    assert "\\setbeamercolor{structure}{fg=" in tex
    assert "\\definecolor{ksth0}{HTML}{CC3300}" in tex
    assert "\\setbeamerfont{frametitle}{size=\\Large}" in tex


def test_theme_spec_round_trip():
    deck = Deck(slides=[Slide()],
                theme_spec=ThemeSpec(enabled=True, outer="split",
                                     structure="#123456"))
    assert deck_from_json(deck_to_json(deck)) == deck


def test_nav_symbols_suppressed_when_disabled():
    deck = _sample_deck()
    deck.nav_symbols = False
    tex = serialize_deck(deck)
    assert "\\insertslidenavigationsymbol" not in tex
    assert "\\setbeamertemplate{navigation symbols}{}" in tex
    assert deck_from_json(deck_to_json(deck)) == deck


def test_serialize_text_styling():
    deck = Deck(slides=[Slide(objects=[
        SlideText(text="Hi", font_pt=30, color="#FF0000", align="center",
                  bold=True, italic=True, fill="#00FF00")])])
    tex = serialize_deck(deck)
    assert "\\fontsize{30}" in tex
    assert "\\textcolor[HTML]{FF0000}" in tex
    assert "\\textbf{" in tex and "\\textit{" in tex
    # Fill is now drawn with the box-frame tikz node, not \colorbox.
    assert "\\definecolor{ksBoxFill}{HTML}{00FF00}" in tex
    assert "fill=ksBoxFill" in tex
    assert "\\centering" in tex


def test_serialize_picture():
    deck = Deck(slides=[Slide(objects=[
        SlidePicture(x=0.1, y=0.1, w=0.3, h=0.4, path="img/a.png",
                     keep_aspect=False, locked=False)])])
    tex = serialize_deck(deck)
    expect = ("\\includegraphics[width=0.3\\paperwidth,"
              "height=0.4\\paperheight]{img/a.png}")
    assert expect in tex


def test_serialize_has_readable_comments():
    deck = Deck(slides=[Slide(title="Intro", objects=[
        SlideText(text="hi", locked=False)])], nav_symbols=False)
    tex = serialize_deck(deck)
    assert "% Slide 1 - Intro" in tex          # slide banner with title
    assert "% text box (free-positioned)" in tex
    assert "generated by KherveSlide" in tex   # preamble header


def test_serialize_frame_count_matches_slides():
    tex = serialize_deck(_sample_deck())
    assert tex.count("\\begin{frame}") == 2
    assert tex.count("\\end{frame}") == 2


def test_serialize_frame_title_when_set():
    deck = Deck(slides=[Slide(title="Key Results")])
    assert "\\frametitle{Key Results}" in serialize_deck(deck)


def test_no_frame_title_when_empty():
    assert "\\frametitle" not in serialize_deck(Deck(slides=[Slide()]))


def test_serialize_slide_background():
    # The slide colour is painted behind everything via beamer's background
    # canvas colour — not a textpos overlay (which would cover the content).
    deck = Deck(slides=[Slide(bg="#123456")])
    tex = serialize_deck(deck)
    assert "{HTML}{123456}" in tex
    assert "\\setbeamercolor{background canvas}{bg=" in tex


def test_box_border_uses_tikz_frame():
    deck = Deck(slides=[Slide(objects=[
        SlideText(text="x", border_color="#C00000", border_width=2.0,
                  corner="rounded", locked=False)])], nav_symbols=False)
    tex = serialize_deck(deck)
    assert "\\usepackage{tikz}" in tex
    assert "\\definecolor{ksBorder}{HTML}{C00000}" in tex
    assert "draw=ksBorder" in tex and "line width=2pt" in tex
    assert "rounded corners" in tex


def test_no_box_frame_without_border_or_fill():
    deck = Deck(slides=[Slide(objects=[SlideText(text="plain", locked=False)])],
                nav_symbols=False)
    tex = serialize_deck(deck)
    assert "ksBorder" not in tex and "ksBoxFill" not in tex


def test_block_text_wraps_in_beamer_block():
    deck = Deck(slides=[Slide(objects=[
        SlideText(text="body", block="alertblock", block_title="Warning",
                  locked=True)])], nav_symbols=False)
    tex = serialize_deck(deck)
    assert "\\begin{alertblock}{Warning}" in tex
    assert "\\end{alertblock}" in tex


def test_box_style_full_options():
    t = SlideText(text="x", locked=False, fill="#ffd966", fill_opacity=0.6,
                  border_color="#1f4e79", border_width=2.0,
                  border_style="dashed", corner="rounded", corner_radius=8.0,
                  shadow=True)
    tex = serialize_deck(Deck(slides=[Slide(objects=[t])], nav_symbols=False))
    assert "dashed" in tex
    assert "fill opacity=0.6" in tex
    assert "rounded corners=8pt" in tex
    assert "drop shadow" in tex
    assert "\\usetikzlibrary{shadows}" in tex
    # the new fields survive a round trip
    deck = Deck(slides=[Slide(objects=[t])])
    assert deck_from_json(deck_to_json(deck)) == deck


def test_theorem_block_uses_bracket_title():
    t = SlideText(text="a^2+b^2=c^2", block="theorem",
                  block_title="Pythagoras", locked=True)
    tex = serialize_deck(Deck(slides=[Slide(objects=[t])], nav_symbols=False))
    assert "\\begin{theorem}[Pythagoras]" in tex
    assert "\\end{theorem}" in tex


def test_theorem_block_without_title_has_no_bracket():
    t = SlideText(text="Q.E.D.", block="proof", locked=True)
    tex = serialize_deck(Deck(slides=[Slide(objects=[t])], nav_symbols=False))
    assert "\\begin{proof}" in tex
    assert "\\begin{proof}[" not in tex


def test_coloured_block_still_uses_brace_title():
    t = SlideText(text="body", block="alertblock", block_title="Warning",
                  locked=True)
    tex = serialize_deck(Deck(slides=[Slide(objects=[t])], nav_symbols=False))
    assert "\\begin{alertblock}{Warning}" in tex


def test_line_and_arrow_unlocked_by_default():
    from kherveslide.model import SlideLine
    assert SlideLine().locked is False
    assert SlideLine(arrow_end=True).locked is False


def test_scene_snap_to_grid():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtCore import QPointF
    from kherveslide.canvas import SlideScene
    s = SlideScene("169")
    p = QPointF(105.0, 55.0)
    assert s.snap_point(p) == p            # no snapping until a mode is on
    s.snap_grid = True
    gx, gy = s.grid_step()
    sp = s.snap_point(QPointF(gx * 2 + 3, gy * 3 - 2))
    assert abs(sp.x() - gx * 2) < 0.5 and abs(sp.y() - gy * 3) < 0.5


def test_grid_divisions_changeable(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w._set_grid_divisions(20)
    assert abs(w.scene.grid_frac - 0.05) < 1e-9
    gx20, _ = w.scene.grid_step()
    w._set_grid_divisions(40)
    gx40, _ = w.scene.grid_step()
    assert abs(gx40 - gx20 / 2) < 0.5      # finer grid → half the spacing


def test_group_select_move_and_ungroup(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    from kherveslide.model import SlideShape, SlideText
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.clear()
    w.slide.objects += [SlideShape(shape="rect"), SlideText(text="a"),
                        SlideShape(shape="ellipse")]
    w._reload_scene()
    for it in w._items[:2]:
        it.setSelected(True)
    w._group_selected()
    gids = [o.group for o in w.slide.objects]
    assert gids[0] == gids[1] != 0 and gids[2] == 0
    # Selecting one group member selects the whole group.
    w.scene.clearSelection()
    w._items[0].setSelected(True)
    assert len(w._selected_items()) == 2
    w._ungroup_selected()
    assert all(o.group == 0 for o in w.slide.objects)


def test_layout_menu_shows_previews(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMenu
    QApplication.instance() or QApplication([])
    from kherveslide import window, templates
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    pm = w._layout_pixmap("Two columns")
    assert not pm.isNull() and pm.width() > 0
    m = QMenu()
    w._fill_new_slide_menu(m)
    assert len(m.actions()) == len(templates.slide_layout_names())


def test_hf_insert_adds_token(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.f_foot_r.clear()
    w._hf_insert(w.f_foot_r, "\\today", w._apply_headfoot)
    assert w.deck.foot_right == "\\today"
    w.f_frame_title.clear()
    w._hf_insert(w.f_frame_title, "\\insertsectionhead", w._apply_frame_title)
    assert w.slide.title == "\\insertsectionhead"


def test_theme_preview_disk_cache_round_trips():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QPixmap, QColor
    from kherveslide import theme_gallery as tg
    pm = QPixmap(120, 70); pm.fill(QColor("#123456"))
    # The cache now lives in the package's theme_previews_generated folder, so
    # clean up the test's file rather than leaving it there to be committed.
    path = tg._disk_cache_path("ZzTestTheme", "zzcol", "169")
    try:
        tg._save_disk_preview(pm, "ZzTestTheme", "zzcol", "169")
        loaded = tg._load_disk_preview("ZzTestTheme", "zzcol", "169")
        assert loaded is not None and not loaded.isNull()
        # a different colour / aspect is a cache miss
        assert tg._load_disk_preview("ZzTestTheme", "other", "169") is None
        assert tg._load_disk_preview("ZzTestTheme", "zzcol", "43") is None
    finally:
        path.unlink(missing_ok=True)


def test_superscript_subscript_round_trip():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QTextDocument
    from kherveslide.canvas import latex_to_html, document_to_latex
    src = "H\\textsubscript{2}O and x\\textsuperscript{2}"
    html = latex_to_html(src)
    assert "<sub>2</sub>" in html and "<sup>2</sup>" in html
    doc = QTextDocument(); doc.setHtml(html)
    out = document_to_latex(doc)
    assert "\\textsubscript{2}" in out
    assert "\\textsuperscript{2}" in out


def test_script_wraps_whole_box_when_not_editing(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    from kherveslide.model import SlideText
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.clear()
    w.slide.objects.append(SlideText(text="2", locked=False))
    w._reload_scene()
    w._items[-1].setSelected(True)
    w._on_super()
    assert w.slide.objects[-1].text == "\\textsuperscript{2}"


def test_font_family_serialises():
    for key, cmd in (("rm", "\\rmfamily"), ("sf", "\\sffamily"),
                     ("tt", "\\ttfamily")):
        tex = serialize_deck(Deck(slides=[Slide(objects=[
            SlideText(text="x", font_family=key, locked=True)])],
            nav_symbols=False))
        assert cmd in tex
    plain = serialize_deck(Deck(slides=[Slide(objects=[
        SlideText(text="x", locked=True)])], nav_symbols=False))
    assert "rmfamily" not in plain and "ttfamily" not in plain


def test_font_family_round_trips():
    deck = Deck(slides=[Slide(objects=[SlideText(text="x", font_family="tt")])])
    assert deck_from_json(deck_to_json(deck)) == deck


def test_auto_compile_toggle_gates_scheduling(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: True)
    # Only the scheduling is under test: no real compiles / downloads,
    # which would otherwise start threads that outlive the test.
    for name in ("_start_compile", "_start_backdrop",
                 "_maybe_autodownload_packages"):
        monkeypatch.setattr(window.SlideWindow, name, lambda self, *a: None)
    w = window.SlideWindow()
    w._toggle_auto_compile(False)
    assert w._auto_compile is False
    w._auto_timer.stop()
    w._schedule_compile()
    assert not w._auto_timer.isActive()      # gated off
    w._toggle_auto_compile(True)
    w._schedule_compile()
    assert w._auto_timer.isActive()
    w._auto_timer.stop()
    w.close()


def test_group_round_trips():
    from kherveslide.model import SlideShape
    deck = Deck(slides=[Slide(objects=[
        SlideShape(shape="rect", group=5), SlideShape(shape="ellipse", group=5)])])
    assert deck_from_json(deck_to_json(deck)) == deck


def test_delete_removes_all_selected(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    from kherveslide.model import SlideShape
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.clear()
    w.slide.objects += [SlideShape(shape="rect"), SlideShape(shape="ellipse"),
                        SlideShape(shape="triangle")]
    w._reload_scene()
    w._items[0].setSelected(True)
    w._items[2].setSelected(True)
    w._delete_selected()
    assert len(w.slide.objects) == 1
    assert w.slide.objects[0].shape == "ellipse"


def test_grid_snap_menu_actions_drive_scene(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.act_grid.setChecked(True); assert w.scene.show_grid is True
    w.act_snap_grid.setChecked(True); assert w.scene.snap_grid is True
    w.act_snap_obj.setChecked(True); assert w.scene.snap_objects is True
    w.act_grid.setChecked(False); assert w.scene.show_grid is False


def test_beamer_placed_block_honours_width():
    # A narrow beamer-placed block is wrapped in a sized minipage so it is
    # exactly as wide as its box; a full-width one is not.
    narrow = Deck(slides=[Slide(objects=[
        SlideText(text="body", block="block", w=0.5, locked=True)])],
        nav_symbols=False)
    tex = serialize_deck(narrow)
    assert "\\begin{minipage}{0.5\\textwidth}" in tex
    assert "\\begin{block}" in tex

    full = Deck(slides=[Slide(objects=[
        SlideText(text="body", block="block", w=0.98, locked=True)])],
        nav_symbols=False)
    assert "minipage" not in serialize_deck(full)


def test_no_block_no_block_env():
    deck = Deck(slides=[Slide(objects=[SlideText(text="plain", locked=True)])],
                nav_symbols=False)
    tex = serialize_deck(deck)
    assert "block}" not in tex


def test_header_footer_templates():
    deck = Deck(slides=[Slide()], header="My header",
                foot_left="L", foot_center="C", foot_right="R")
    tex = serialize_deck(deck)
    assert "\\setbeamertemplate{headline}" in tex
    assert "\\setbeamertemplate{footline}" in tex
    assert "My header" in tex and "L" in tex and "C" in tex and "R" in tex


def test_no_header_footer_by_default():
    tex = serialize_deck(Deck(slides=[Slide()]))
    assert "\\setbeamertemplate{headline}" not in tex
    assert "\\setbeamertemplate{footline}" not in tex


def test_text_line_break_becomes_latex_break():
    # A newline the user typed between two plain lines must render as a
    # LaTeX line break, not collapse to a space.
    deck = Deck(slides=[Slide(objects=[
        SlideText(text="Column one.\nCol 2", locked=False)])], nav_symbols=False)
    tex = serialize_deck(deck)
    assert "Column one. \\\\" in tex
    assert "Col 2" in tex


def test_itemize_newlines_not_turned_into_breaks():
    # Structural newlines inside itemize must stay as-is (no stray \\).
    deck = Deck(slides=[Slide(objects=[SlideText(
        text="\\begin{itemize}\n\\item A\n\\item B\n\\end{itemize}",
        locked=False)])], nav_symbols=False)
    tex = serialize_deck(deck)
    assert "\\begin{itemize}" in tex
    assert "\\item A" in tex and "\\item B" in tex
    assert "\\item A \\\\" not in tex          # no spurious line break


def test_serialize_empty_picture_shows_empty_box():
    # No image added → an empty framed box where the picture would go (never a
    # \includegraphics, never a path splattered on the slide).
    deck = Deck(slides=[Slide(objects=[SlidePicture(path="")])])
    tex = serialize_deck(deck)
    assert "\\includegraphics" not in tex
    assert "\\framebox" in tex


def test_strip_images_and_missing_show_no_path():
    # Skip-images and missing-image placeholders draw an empty box, not the
    # file path.
    from kherveslide.compiler import _strip_images, _empty_image_box
    src = "\\includegraphics[width=0.3\\paperwidth,height=0.2\\paperheight]" \
          "{C:/secret/path/to/image.png}"
    stripped = _strip_images(src)
    assert "image.png" not in stripped and "secret" not in stripped
    assert "\\framebox" in stripped
    assert "path" not in _empty_image_box("width=1cm,height=1cm")


def test_serialize_picture_crop_uses_adjustbox():
    deck = Deck(slides=[Slide(objects=[
        SlidePicture(path="a.png", crop_l=0.1, crop_t=0.2, crop_r=0.05,
                     crop_b=0.0, locked=False)])])
    tex = serialize_deck(deck)
    assert "\\usepackage{adjustbox}" in tex
    assert "\\adjincludegraphics[" in tex
    # graphicx trim order is left bottom right top.
    assert "trim={0.1\\width} {0\\height} {0.05\\width} {0.2\\height}" in tex


def test_serialize_picture_no_adjustbox_without_crop():
    deck = Deck(slides=[Slide(objects=[
        SlidePicture(path="a.png", locked=False)])])
    tex = serialize_deck(deck)
    assert "adjustbox" not in tex
    assert "\\includegraphics[" in tex


def test_serialize_picture_rotation_uses_rotatebox():
    deck = Deck(slides=[Slide(objects=[
        SlidePicture(path="a.png", rotation=90, locked=False)])])
    tex = serialize_deck(deck)
    assert "\\rotatebox[origin=c]{90}{" in tex


def test_picture_crop_rotate_round_trip():
    deck = Deck(slides=[Slide(objects=[
        SlidePicture(path="a.png", crop_l=0.1, crop_b=0.2, rotation=45.0,
                     locked=False)])])
    assert deck_from_json(deck_to_json(deck)) == deck


# --- tables ---

def test_table_round_trip():
    deck = Deck(slides=[Slide(objects=[
        SlideTable(rows=[["a", "b"], ["c", "d"]], border=True, font_pt=16)])])
    assert deck_from_json(deck_to_json(deck)) == deck


def test_serialize_table_styled():
    deck = Deck(slides=[Slide(objects=[
        SlideTable(x=0.1, y=0.1, w=0.5, h=0.25,
                   rows=[["a", "b"], ["c", "d"]], caption="cap",
                   locked=False)])])
    tex = serialize_deck(deck)
    assert "\\begin{textblock}{0.5}(0.1,0.1)" in tex
    assert "\\begin{tabular}{|l|l|}" in tex
    assert "\\usepackage{colortbl}" in tex
    # header row gets a coloured background + bold header-fg text (the colour
    # names are now suffixed with the hex so two tables never clash).
    assert "\\rowcolor{ksTHFCE4D6}" in tex          # coloured header row
    assert "\\textcolor{ksTFC55A11}{\\textbf{a}}" in tex
    assert "c & d \\\\" in tex                      # body row plain
    assert "\\arrayrulecolor{ksTRF4B183}" in tex    # default rule colour
    assert "\\hline" in tex
    assert "\\textcolor{ksTblCap}{cap}" in tex      # caption


def test_serialize_table_no_border_no_header():
    deck = Deck(slides=[Slide(objects=[
        SlideTable(rows=[["x", "y"]], border=False, header=False)])])
    tex = serialize_deck(deck)
    assert "\\begin{tabular}{ll}" in tex
    assert "\\hline" not in tex
    assert "\\rowcolor" not in tex


def test_table_header_caption_round_trip():
    deck = Deck(slides=[Slide(objects=[
        SlideTable(header=False, caption="My table")])])
    assert deck_from_json(deck_to_json(deck)) == deck


def test_table_grid_styles():
    def tex_for(grid):
        return serialize_deck(Deck(slides=[Slide(objects=[
            SlideTable(rows=[["a", "b"], ["c", "d"]], header=False,
                       grid=grid, border=True)])], nav_symbols=False))
    horiz = tex_for("horizontal")
    assert "\\begin{tabular}{ll}" in horiz      # no vertical bars
    assert "\\hline" in horiz                   # but horizontal rules
    none = tex_for("none")
    assert "\\hline" not in none
    outer = tex_for("outer")
    # outer = top & bottom rule only (exactly two \hline, no inner ones)
    assert outer.count("\\hline") == 2


def test_table_align_and_striped():
    tex = serialize_deck(Deck(slides=[Slide(objects=[
        SlideTable(rows=[["h"], ["1"], ["2"], ["3"]], header=True,
                   align="right", striped=True, stripe_color="#abcdef")])],
        nav_symbols=False))
    assert "\\begin{tabular}{|r|}" in tex
    assert "\\rowcolor{ksTSABCDEF}" in tex      # an alternate body row striped


def test_table_custom_header_colour():
    tex = serialize_deck(Deck(slides=[Slide(objects=[
        SlideTable(rows=[["h", "i"]], header=True,
                   header_bg="#102030", header_fg="#ffffff")])],
        nav_symbols=False))
    assert "\\definecolor{ksTH102030}{HTML}{102030}" in tex
    assert "\\rowcolor{ksTH102030}" in tex


def test_table_full_fields_round_trip():
    deck = Deck(slides=[Slide(objects=[
        SlideTable(align="center", grid="horizontal", rule_color="#123456",
                   rule_width=1.5, header_bg="#222222", header_fg="#eeeeee",
                   striped=True, stripe_color="#fafafa")])])
    assert deck_from_json(deck_to_json(deck)) == deck


def test_table_style_gallery_applies_fields():
    from kherveslide.table_styles import TABLE_STYLES, apply_table_style
    from kherveslide.model import SlideTable
    st = next(s for s in TABLE_STYLES if s["name"] == "Blue banded")
    t = SlideTable(rows=[["a", "b"], ["c", "d"], ["e", "f"]])
    apply_table_style(t, st)
    assert t.header_bg == "#2E75B6" and t.striped is True
    assert t.grid == "horizontal" and t.border is True
    tex = serialize_deck(Deck(slides=[Slide(objects=[t])], nav_symbols=False))
    assert "\\definecolor{ksTH2E75B6}" in tex      # header colour emitted


def test_insert_table_dimensions(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    from kherveslide.model import SlideTable
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.clear()
    w._insert_table(4, 3)
    t = w.slide.objects[-1]
    assert isinstance(t, SlideTable)
    assert len(t.rows) == 4 and all(len(r) == 3 for r in t.rows)


def test_table_legacy_border_migrates_to_grid():
    from kherveslide.model import build_object
    o = build_object({"type": "SlideTable", "rows": [["x"]], "border": False})
    assert o.grid == "none"
    o2 = build_object({"type": "SlideTable", "rows": [["x"]], "border": True})
    assert o2.grid == "all"


# --- templates ---

def test_builtin_templates_instantiate():
    for name in templates.builtin_names():
        deck = templates.instantiate_builtin(name)
        assert isinstance(deck, Deck)
        assert deck.slides            # at least one slide
        serialize_deck(deck)          # must serialize without error


def test_template_store_save_rename_delete(tmp_path):
    store = templates.TemplateStore(tmp_path / "tpl.json")
    deck = _sample_deck()
    store.save_deck_as("My layout", deck)
    assert "My layout" in store.names()
    # persists across instances
    store2 = templates.TemplateStore(tmp_path / "tpl.json")
    again = store2.instantiate("My layout")
    assert again.theme == deck.theme
    assert len(again.slides) == len(deck.slides)
    store2.rename("My layout", "Renamed")
    assert "Renamed" in store2.names() and "My layout" not in store2.names()
    store2.delete("Renamed")
    assert "Renamed" not in store2.names()


def test_template_store_rejects_builtin_name(tmp_path):
    store = templates.TemplateStore(tmp_path / "tpl.json")
    with pytest.raises(ValueError):
        store.save_deck_as("Blank", _sample_deck())


# --- per-slide layouts ---

def test_slide_layouts_instantiate():
    for name in templates.slide_layout_names():
        s = templates.instantiate_slide_layout(name)
        assert isinstance(s, Slide)
    # applying a layout into a deck still serializes
    deck = Deck(slides=[templates.instantiate_slide_layout("Two columns")])
    serialize_deck(deck)


def test_slide_layout_unknown_falls_back_to_blank():
    assert templates.instantiate_slide_layout("nope").objects == []


def test_new_slide_layouts_present():
    names = templates.slide_layout_names()
    for n in ("Title only", "Three columns", "Comparison",
              "Picture left + bullets", "Full picture", "Quote",
              "Two images + text", "Text + two images", "Three pictures"):
        assert n in names


def test_picture_layouts_serialize():
    for n in ("Two images + text", "Text + two images", "Three pictures"):
        deck = Deck(slides=[templates.instantiate_slide_layout(n)])
        serialize_deck(deck)


def test_locked_column_picture_fills_column():
    # A locked picture in a column fills the column width (\linewidth),
    # not box-fraction × column width (which made it tiny).
    deck = Deck(slides=[Slide(objects=[
        SlidePicture(x=0.06, y=0.3, w=0.4, h=0.5, path="a.png", locked=True),
        SlideText(x=0.54, y=0.3, w=0.4, h=0.5, text="text", locked=True)])],
        nav_symbols=False)
    tex = serialize_deck(deck)
    assert "\\begin{columns}" in tex
    assert "width=\\linewidth" in tex


def test_comparison_layout_serializes_as_columns():
    deck = Deck(slides=[templates.instantiate_slide_layout("Comparison")])
    tex = serialize_deck(deck)
    assert "\\begin{columns}" in tex


# --- theme builder: decorative rules ---

def test_theme_builder_title_rule_emits_template():
    deck = Deck(slides=[Slide()],
                theme_spec=ThemeSpec(enabled=True, title_rule=True,
                                     structure="#ED7D31"))
    tex = serialize_deck(deck)
    assert "\\addtobeamertemplate{frametitle}" in tex


def test_theme_builder_footline_rule_uses_rule_colour():
    deck = Deck(slides=[Slide()],
                theme_spec=ThemeSpec(enabled=True, footline_rule=True,
                                     rule_color="#123456"))
    tex = serialize_deck(deck)
    assert "\\setbeamertemplate{footline}" in tex
    assert "ksRule" in tex
    assert "123456" in tex


def test_disabled_theme_spec_emits_no_rules():
    deck = Deck(slides=[Slide()],
                theme_spec=ThemeSpec(enabled=False, title_rule=True))
    tex = serialize_deck(deck)
    assert "addtobeamertemplate" not in tex


def test_theme_spec_rules_round_trip():
    deck = Deck(slides=[Slide()],
                theme_spec=ThemeSpec(enabled=True, title_rule=True,
                                     footline_rule=True, rule_color="#abcdef",
                                     rule_width=2.0))
    assert deck_from_json(deck_to_json(deck)) == deck


# --- app appearance themes ---

def test_orange_theme_present_and_light():
    from kherveslide import themes
    assert "Orange" in themes.THEME_NAMES
    assert themes.is_dark("Orange") is False
    assert themes.THEMES["Orange"]["accent"].lower() == "#ed7d31"


def test_all_themes_share_the_same_keys():
    from kherveslide import themes
    expected = set(themes.THEMES["Light"])
    for name, t in themes.THEMES.items():
        assert set(t) == expected, f"{name} has mismatched keys"


# --- LaTeX source highlighter ---

def test_latex_highlighter_distinguishes_tokens():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QTextDocument
    from kherveslide.latex_view import LatexHighlighter, _LIGHT_COLORS as C
    line = "\\begin{frame}[plain,t] x=0.4 & \\textbf{hi}"
    doc = QTextDocument()
    doc.setPlainText(line)
    LatexHighlighter(doc).rehighlight()
    formats = doc.firstBlock().layout().formats()

    def color_at(idx):
        col = None
        for fr in formats:
            if fr.start <= idx < fr.start + fr.length:
                col = fr.format.foreground().color().name()
        return col

    assert color_at(line.index("begin")) == C["keyword"]   # \begin
    assert color_at(line.index("frame")) == C["env"]        # env name
    assert color_at(line.index("[plain")) == C["option"]    # optional arg
    assert color_at(line.index("0.4")) == C["number"]
    assert color_at(line.index("&")) == C["special"]
    assert color_at(line.index("textbf")) == C["command"]   # \textbf


# --- canvas LaTeX -> HTML preview ---

def test_latex_to_html_itemize_is_bullet_list():
    from kherveslide.canvas import latex_to_html
    h = latex_to_html("\\begin{itemize}\n\\item A\n\\item B\n\\end{itemize}")
    assert "<ul>" in h and h.count("<li>") == 2


def test_nested_itemize_round_trips():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QTextDocument
    from kherveslide.canvas import latex_to_html, document_to_latex
    src = ("\\begin{itemize}\n\\item parent\n\\begin{itemize}\n"
           "\\item child\n\\end{itemize}\n\\item parent2\n\\end{itemize}")
    html = latex_to_html(src)
    assert "<ul><li>parent<ul>" in html        # child list nested in the <li>
    doc = QTextDocument(); doc.setHtml(html)
    out = document_to_latex(doc)
    # two nested itemize environments, child indented deeper than parent
    assert out.count("\\begin{itemize}") == 2
    assert "    \\item child" in out
    assert "  \\item parent2" in out


def test_inline_editor_paste_is_plain(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtCore import QMimeData
    from kherveslide import window
    ed = window._InlineEditor()
    md = QMimeData()
    md.setHtml('<span style="font-size:48pt;color:red">Big red</span>')
    md.setText("Big red")
    ed.insertFromMimeData(md)
    assert ed.toPlainText() == "Big red"
    # nothing in the document carries the pasted 48pt size
    assert "48" not in ed.toHtml()


def test_latex_to_html_enumerate_is_numbered_list():
    from kherveslide.canvas import latex_to_html
    h = latex_to_html("\\begin{enumerate}\n\\item X\n\\end{enumerate}")
    assert "<ol>" in h


def test_latex_to_html_inline_formatting():
    from kherveslide.canvas import latex_to_html
    assert "<b>Hi</b>" in latex_to_html("\\textbf{Hi}")
    assert "<i>yo</i>" in latex_to_html("\\textit{yo}")


def test_math_only_detects_pure_equations():
    from kherveslide.canvas import _math_only
    assert _math_only("$\\dfrac{x}{y}$") == "\\dfrac{x}{y}"
    assert _math_only("  $a+b$  ") == "a+b"
    assert _math_only("\\[E=mc^2\\]") == "E=mc^2"
    assert _math_only("\\(x\\)") == "x"
    # Prose with inline math, or trailing text, is not a pure equation.
    assert _math_only("Hello $x$ world") is None
    assert _math_only("$a$ and $b$") is None
    assert _math_only("plain text") is None
    assert _math_only("") is None


def test_inline_editor_claims_editing_shortcuts():
    # Ctrl+B etc. must reach the editor, not fire the window's menu actions
    # (the navigator toggle also lives on Ctrl+B).
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from kherveslide.window import _InlineEditor
    ed = _InlineEditor()
    for key in (Qt.Key_B, Qt.Key_I, Qt.Key_C, Qt.Key_V):
        ev = QKeyEvent(QEvent.Type.ShortcutOverride, key, Qt.ControlModifier)
        assert ed.event(ev) is True and ev.isAccepted()
    # Unrelated combos (e.g. Ctrl+N = New) are left for the menus.
    assert Qt.Key_N not in _InlineEditor._GRAB_KEYS


def test_right_click_selects_box_under_cursor(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.append(SlideText(x=0.1, y=0.1, w=0.4, h=0.2, text="A",
                                     locked=False))
    w._reload_scene()
    item = w._items[-1]
    assert not item.isSelected()
    w._select_box_at(item.scene_rect().center())     # right-click hit-test
    assert item.isSelected()


def test_delete_key_ignored_while_editing(monkeypatch):
    # While the inline editor is up, the scene has a focus item, so the
    # view's Delete shortcut must not fire (it would delete the box).
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.append(SlideText(text="hello", locked=False))
    w._reload_scene()
    item = w._items[-1]
    item.setSelected(True)
    w._edit_text_item(item)
    assert w.scene.focusItem() is not None      # editor holds scene focus


def test_find_in_slides_navigates(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    from kherveslide.model import Slide
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.deck.slides = [Slide(objects=[SlideText(text="alpha needle")]),
                     Slide(objects=[SlideText(text="needle two")])]
    w.current = 0
    w._reload_all()
    w._find_in_slides("needle")
    assert w.current == 0 and any(i.isSelected() for i in w._items)
    w._find_in_slides("needle")          # next match
    assert w.current == 1
    assert w._find_count.text() == "2 / 2"
    w._find_in_slides("zzz")
    assert w._find_count.text() == "0 / 0"


def test_latex_view_find():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide.latex_view import LatexView
    v = LatexView()
    v.set_source("first line\nsecond TARGET line")
    assert v.find("TARGET") is True
    assert v.find("absent-word") is False


def test_latex_editor_scheme_overrides_app_theme():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide.latex_view import LatexView, EDITOR_SCHEMES
    v = LatexView()
    # A named scheme paints its own background regardless of dark/light.
    v.set_editor_scheme("Monokai")
    assert v.editor_scheme() == "Monokai"
    assert EDITOR_SCHEMES["Monokai"]["bg"] in v._edit.styleSheet()
    # The app theme must not clobber a chosen scheme.
    v.set_dark(False, None)
    assert EDITOR_SCHEMES["Monokai"]["bg"] in v._edit.styleSheet()
    # Reverting to "Match app theme" follows the app again.
    v.set_editor_scheme(None)
    assert v.editor_scheme() is None
    assert "#ffffff" in v._edit.styleSheet()


def test_new_object_stacks_below_previous(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.clear()
    first = SlideText(text="A", x=0.1, y=0.1, w=0.8, h=0.2)
    w.slide.objects.append(first)
    w._add_text()                       # appends a second text box
    second = w.slide.objects[-1]
    # The new box sits below the first (no overlap) and inherits its x/width.
    assert second.y >= first.y + first.h
    assert second.x == first.x
    assert second.w == first.w


def _combo_index_for(combo, kind):
    for i in range(combo.count()):
        if combo.itemData(i) == kind:
            return i
    raise AssertionError(f"no combo entry for {kind}")


def test_type_combo_changes_box_type(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    from kherveslide.model import SlidePicture, SlideTable
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.clear()
    w.slide.objects.append(SlideText(text="x", x=0.2, y=0.3, w=0.6, h=0.2,
                                     locked=True))
    w._reload_scene()
    item = w._items[-1]
    item.setSelected(True)
    assert w.type_combo.isEnabled()
    assert w.type_combo.currentData() == "text"
    # Text → Block keeps the same object, just tags it.
    w.type_combo.setCurrentIndex(_combo_index_for(w.type_combo, "block"))
    assert w.slide.objects[0].block == "block"
    assert isinstance(w.slide.objects[0], SlideText)
    # Block → Table converts the box but keeps its geometry.
    w._items[-1].setSelected(True)
    w.type_combo.setCurrentIndex(_combo_index_for(w.type_combo, "table"))
    new = w.slide.objects[0]
    assert isinstance(new, SlideTable)
    assert (new.x, new.y, new.w, new.h, new.locked) == (0.2, 0.3, 0.6, 0.2, True)
    # The old Free/Beamer-placed combo is gone.
    assert not hasattr(w, "placement_combo")
    assert not hasattr(w, "theme_combo")


def test_manual_latex_edits_are_not_overwritten(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    assert w._latex_overridden is False
    # Hand-edit the source and enter manual-edit mode.
    edited = w.latex_view.source() + "\n% MANUAL EDIT"
    w.latex_view._edit.setPlainText(edited)
    w._on_latex_edited(w.latex_view.source())
    assert w._latex_overridden is True
    # A navigation / incidental refresh (deck UNCHANGED) must NOT overwrite it.
    w._refresh_latex()
    assert "% MANUAL EDIT" in w.latex_view.source()
    # Regenerating from the slides drops the override and the manual edit.
    w._regenerate_latex_from_slides()
    assert w._latex_overridden is False
    assert "% MANUAL EDIT" not in w.latex_view.source()


def test_slide_edit_exits_latex_override(monkeypatch):
    # Editing a SLIDE while in manual-LaTeX mode hands control back to the
    # WYSIWYG: the source regenerates so the change reaches the PDF.
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    from kherveslide.model import SlideText
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.latex_view._edit.setPlainText(w.latex_view.source() + "\n% MANUAL EDIT")
    w._on_latex_edited(w.latex_view.source())
    assert w._latex_overridden is True
    # Now change a slide, then refresh (as _touch_current would).
    w.deck.slides[w.current].objects.append(
        SlideText(text="BRANDNEWCONTENT", locked=True))
    w._refresh_latex()
    assert w._latex_overridden is False               # WYSIWYG took over
    assert "BRANDNEWCONTENT" in w.latex_view.source()  # regenerated
    assert "% MANUAL EDIT" not in w.latex_view.source()


def test_deck_replace_clears_latex_override(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.latex_view._edit.setPlainText("junk")
    w._on_latex_edited("junk")
    assert w._latex_overridden is True
    w._new_deck()          # deck replacement re-syncs the source
    assert w._latex_overridden is False
    assert "junk" not in w.latex_view.source()


# --- gradient fills + gradient background ---

def test_gradient_fields_round_trip():
    deck = Deck(slides=[Slide(objects=[
        SlideShape(shape="rect", fill="#FF0000", fill2="#0000FF",
                   gradient="horizontal"),
        SlideText(text="x", fill="#FFFFFF", fill2="#CCCCCC"),
    ])], theme_spec=ThemeSpec(enabled=True, canvas_bg="#FFFFFF",
                              canvas_bg2="#DDEEFF"))
    assert deck_from_json(deck_to_json(deck)) == deck


def test_shape_gradient_uses_tikz_shading():
    deck = Deck(slides=[Slide(objects=[
        SlideShape(shape="rect", fill="#FF0000", fill2="#0000FF")])],
        nav_symbols=False)
    tex = serialize_deck(deck)
    assert "top color=ksfill" in tex and "bottom color=ksfillb" in tex
    assert "fill=ksfill0" not in tex          # shading replaces the flat fill

    deck.slides[0].objects[0].gradient = "horizontal"
    tex = serialize_deck(deck)
    assert "left color=ksfill" in tex and "right color=ksfillb" in tex


def test_box_gradient_uses_tikz_shading():
    deck = Deck(slides=[Slide(objects=[
        SlideText(text="x", fill="#FFFFFF", fill2="#AACCEE",
                  locked=False)])], nav_symbols=False)
    tex = serialize_deck(deck)
    assert "top color=ksBoxFill" in tex and "bottom color=ksBoxFillB" in tex


def test_theme_background_gradient():
    deck = Deck(slides=[Slide()], theme_spec=ThemeSpec(
        enabled=True, canvas_bg="#FFFFFF", canvas_bg2="#CCE0FF"))
    tex = serialize_deck(deck)
    assert ("\\setbeamertemplate{background canvas}"
            "[vertical shading][top=ksBgTop,bottom=ksBgBot]") in tex
    # A flat background (no 2nd colour) keeps the plain beamercolor route.
    deck.theme_spec.canvas_bg2 = ""
    tex = serialize_deck(deck)
    assert "vertical shading" not in tex


def test_slide_bg_resets_shading_template():
    # A per-slide flat colour must beat a theme-level gradient: the scoped
    # group resets the canvas template to [default].
    deck = Deck(slides=[Slide(bg="#123456")], theme_spec=ThemeSpec(
        enabled=True, canvas_bg="#FFFFFF", canvas_bg2="#CCE0FF"))
    tex = serialize_deck(deck)
    assert "\\setbeamertemplate{background canvas}[default]" in tex


def test_nav_tickbox_and_menu_stay_in_sync(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w._set_nav_symbols(False)
    assert w.deck.nav_symbols is False
    assert not w.chk_nav.isChecked() and not w.act_nav.isChecked()
    w._set_nav_symbols(True)
    assert w.deck.nav_symbols is True
    assert w.chk_nav.isChecked() and w.act_nav.isChecked()


def test_paste_image_fills_selected_picture_box(monkeypatch):
    # A clipboard image pasted while a picture box is selected fills that
    # box instead of creating a new floating image.
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QImage, QColor
    from PySide6.QtCore import QPointF
    from kherveslide import window
    from kherveslide.model import SlidePicture
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    img = QImage(60, 40, QImage.Format_RGB32)
    img.fill(QColor("#33aa55"))
    QApplication.clipboard().setImage(img)
    w = window.SlideWindow()
    w.slide.objects.append(SlidePicture(x=0.1, y=0.1, w=0.4, h=0.4, path=""))
    w._reload_scene()
    item = w._items[-1]
    item.setSelected(True)
    n = len(w.slide.objects)
    w._paste(QPointF(100, 100))
    assert len(w.slide.objects) == n            # filled, not added
    assert item.obj.path                        # picture now has a file


def test_annotate_dialog_background_and_fill():
    from PySide6.QtWidgets import QApplication, QGraphicsRectItem
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QPixmap, QColor, QImage, QPainter
    from PySide6.QtCore import QRectF, Qt
    import tempfile
    from pathlib import Path
    from kherveslide.annotate_dialog import DrawingDialog
    wd = Path(tempfile.mkdtemp(prefix="ks_dd_"))
    src = wd / "bg.png"
    pm = QPixmap(60, 40); pm.fill(QColor("#3478f6")); pm.save(str(src))
    dlg = DrawingDialog(wd, None, background_path=src)
    assert dlg._bg_item is not None
    assert dlg._scene.sceneRect().width() == 60
    # A fill colour applies to a shape.
    dlg._canvas.set_fill(QColor("#ff0000"))
    item = QGraphicsRectItem(QRectF(5, 5, 20, 15))
    item.setBrush(dlg._canvas._brush())
    assert item.brush().color().name() == "#ff0000"
    dlg._scene.addItem(item)
    img = QImage(60, 40, QImage.Format_ARGB32); img.fill(Qt.transparent)
    p = QPainter(img); dlg._scene.render(p, QRectF(img.rect()),
                                         dlg._scene.sceneRect()); p.end()
    assert img.pixelColor(40, 30).name() == "#3478f6"     # background kept
    assert img.pixelColor(12, 11).name() == "#ff0000"     # fill drawn


def test_picture_editor_remove_background():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QPixmap, QColor, QImage, QPainter
    import tempfile
    from pathlib import Path
    from kherveslide.model import SlidePicture
    from kherveslide.picture_editor import PictureEditDialog
    wd = Path(tempfile.mkdtemp(prefix="ks_bg_"))
    pm = QPixmap(40, 30)
    pm.fill(QColor("white"))
    p = QPainter(pm); p.fillRect(12, 9, 16, 12, QColor("#cc2222")); p.end()
    src = wd / "img.png"
    pm.save(str(src))
    dlg = PictureEditDialog(SlidePicture(path=str(src)))
    dlg._remove_background()
    out = QImage(dlg.path)
    assert out.pixelColor(0, 0).alpha() == 0        # white corner cleared
    assert out.pixelColor(20, 15).alpha() == 255    # red kept


def test_toolbar_prev_next_slide(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w._add_slide(); w._add_slide()             # navigator stays in sync
    last = len(w.deck.slides) - 1
    assert last >= 2
    w.nav.setCurrentRow(0)
    assert w.current == 0
    w._next_slide(); assert w.current == 1
    w.nav.setCurrentRow(last)
    w._next_slide(); assert w.current == last   # clamped at the last slide
    w._prev_slide(); assert w.current == last - 1
    w.nav.setCurrentRow(0)
    w._prev_slide(); assert w.current == 0       # clamped at the first slide


def test_editing_suppresses_box_paint_but_keeps_selection(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    from kherveslide.model import SlideText
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.append(SlideText(text="one\ntwo\nthree", locked=False))
    w._reload_scene()
    item = w._items[-1]
    item.setSelected(True)
    w._edit_text_item(item)
    # the box stops painting its own (overflowing) text but stays selected
    assert getattr(item, "_editing", False) is True
    assert item.isSelected()
    w._finish_edit()
    assert getattr(w._items[-1], "_editing", False) is False


def test_toolbar_bold_targets_selection_while_editing(monkeypatch):
    # Clicking the toolbar Bold button mid-edit must bold only the selected
    # run, not the whole box (the box-level flag stays off).
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QTextCursor
    from kherveslide import window
    from kherveslide.model import SlideText
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.append(SlideText(text="alpha beta gamma", locked=False))
    w._reload_scene()
    item = w._items[-1]
    item.setSelected(True)                  # enables the format toolbar
    w._edit_text_item(item)
    ed = w._edit_proxy.widget()
    cur = ed.textCursor()
    cur.setPosition(6)
    cur.setPosition(10, QTextCursor.KeepAnchor)   # select "beta"
    ed.setTextCursor(cur)
    w.act_bold.trigger()                    # click the toolbar Bold button
    w._finish_edit()
    assert item.obj.text == "alpha \\textbf{beta} gamma"
    assert item.obj.bold is False


def test_inline_editor_bolds_only_the_selection():
    # One text box can mix styles: bolding a selection wraps just that run.
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QTextCursor
    from kherveslide.window import _InlineEditor
    from kherveslide.canvas import document_to_latex
    ed = _InlineEditor()
    ed.setPlainText("alpha beta")
    cur = ed.textCursor()
    cur.setPosition(0)
    cur.setPosition(5, QTextCursor.KeepAnchor)      # select "alpha"
    ed.setTextCursor(cur)
    ed.toggle_bold()
    out = document_to_latex(ed.document())
    assert "\\textbf{alpha}" in out
    assert "beta" in out and "\\textbf{beta}" not in out


def test_inline_maths_round_trip():
    # Editing a box with inline maths must keep the $…$ (it used to be stripped
    # on display and then lost on commit).
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QTextDocument
    from kherveslide.canvas import latex_to_html, document_to_latex
    doc = QTextDocument()
    doc.setHtml(latex_to_html("Energy $E = mc^2$ here"))
    assert document_to_latex(doc) == "Energy $E = mc^2$ here"


def test_inline_editor_copy_keeps_formatting():
    # Copying a selection from one KherveSlide box and pasting into another
    # preserves bullets, bold/italic and maths (foreign content stays plain,
    # see test_inline_editor_paste_is_plain).
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    from kherveslide.canvas import latex_to_html, document_to_latex
    src = ("\\begin{itemize}\n\\item First\n"
           "\\item \\textbf{Second} $x^2$\n\\end{itemize}")
    a = window._InlineEditor()
    a.setHtml(latex_to_html(src))
    a.selectAll()
    a.copy()
    cb = QApplication.clipboard().mimeData()
    assert cb.hasFormat(window._InlineEditor._TEXT_MIME)
    b = window._InlineEditor()
    b.paste()
    out = document_to_latex(b.document())
    assert "\\begin{itemize}" in out and out.count("\\item") == 2
    assert "\\textbf{Second}" in out
    assert "$x^2$" in out


def test_picture_editor_pastes_copied_box():
    # Copying a picture box from a slide (our object clipboard) and pasting in
    # the crop/rotate dialog should load that image.
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    import json, tempfile
    from pathlib import Path
    from PySide6.QtCore import QByteArray, QMimeData
    from PySide6.QtGui import QColor, QPixmap
    from kherveslide.model import SlidePicture, object_to_dict
    from kherveslide.picture_editor import PictureEditDialog
    imgp = Path(tempfile.gettempdir()) / "ks_pastesrc_test.png"
    pm = QPixmap(40, 30); pm.fill(QColor("#3388cc")); pm.save(str(imgp), "PNG")
    md = QMimeData()
    md.setData(PictureEditDialog._OBJ_MIME, QByteArray(json.dumps(
        [object_to_dict(SlidePicture(path=str(imgp)))]).encode("utf-8")))
    QApplication.clipboard().setMimeData(md)
    dlg = PictureEditDialog(SlidePicture(path=""))
    assert dlg.path == ""
    dlg._paste()
    assert dlg.path == str(imgp)


def test_rich_edit_round_trip_keeps_lists():
    # Editing renders bullets (not \item); committing turns them back into
    # itemize. Needs a Qt app for QTextDocument.
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QTextDocument
    from kherveslide.canvas import latex_to_html, document_to_latex
    doc = QTextDocument()
    doc.setHtml(latex_to_html("\\begin{itemize}\n\\item First\n"
                              "\\item Second\n\\end{itemize}"))
    out = document_to_latex(doc)
    assert "\\begin{itemize}" in out
    assert out.count("\\item") == 2
    assert "\\end{itemize}" in out
    assert "First" in out and "Second" in out


# --- PowerPoint import ---

def test_pptx_import_maps_shapes(tmp_path):
    from kherveslide import pptx_import
    if not pptx_import.available():
        pytest.skip("python-pptx not installed")
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])   # blank layout
    tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    tb.text_frame.text = "Hello"
    tb.text_frame.paragraphs[0].runs[0].font.bold = True
    src = tmp_path / "deck.pptx"
    prs.save(str(src))

    deck = pptx_import.import_pptx(src, tmp_path / "media")
    assert len(deck.slides) == 1
    texts = [o for o in deck.slides[0].objects
             if isinstance(o, SlideText)]
    assert any("Hello" in o.text for o in texts)
    assert any("\\textbf{Hello}" in o.text for o in texts)   # bold run kept
    # Imported objects are freely positioned, and the page matches the pptx.
    assert all(o.locked is False for o in deck.slides[0].objects)
    assert deck.page_w_cm > 0 and deck.page_h_cm > 0
    serialize_deck(deck)            # the imported deck serialises cleanly


def test_pptx_import_extracts_embedded_video(tmp_path):
    from kherveslide import pptx_import
    from kherveslide.model import SlideVideo
    if not pptx_import.available():
        pytest.skip("python-pptx not installed")
    from pptx import Presentation
    from pptx.util import Inches
    payload = b"\x00fake-video-bytes"
    src_vid = tmp_path / "clip.mp4"
    src_vid.write_bytes(payload)
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])   # blank layout
    slide.shapes.add_movie(str(src_vid), Inches(1), Inches(1),
                           Inches(4), Inches(3), mime_type="video/mp4")
    src = tmp_path / "deck.pptx"
    prs.save(str(src))

    deck = pptx_import.import_pptx(src, tmp_path / "media")
    vids = [o for o in deck.slides[0].objects if isinstance(o, SlideVideo)]
    assert len(vids) == 1
    v = vids[0]
    # The embedded bytes are extracted next to the images, byte-for-byte.
    assert v.path.endswith(".mp4")
    from pathlib import Path as _P
    assert _P(v.path).read_bytes() == payload
    # PowerPoint's poster frame comes across as the box's poster image.
    assert v.poster and _P(v.poster).exists()
    assert v.locked is False
    assert 0 < v.x < 1 and 0 < v.w < 1
    serialize_deck(deck)            # the imported deck serialises cleanly


# --- master slide (painted behind every slide) ---

def _master_deck():
    master = Slide(objects=[
        SlideShape(shape="rect", x=0.0, y=0.9, w=1.0, h=0.1, fill="#00AA7F"),
        SlideLine(x=0.05, y=0.88, w=0.9, h=0.0, color="#00AA7F"),
        SlideText(x=0.05, y=0.91, w=0.6, h=0.07, text="MASTERMARK",
                  color="#FFFFFF"),
    ])
    return Deck(
        master=master,
        slides=[
            Slide(objects=[SlideText(text="BODYONE", locked=True)], title="A"),
            Slide(objects=[SlideText(text="BODYTWO", locked=True)], title="B"),
        ])


def test_master_round_trips():
    deck = _master_deck()
    assert deck_from_json(deck_to_json(deck)) == deck
    assert len(deck_from_json(deck_to_json(deck)).master.objects) == 3


def test_deck_without_master_key_is_backward_compatible():
    # A deck saved before the master feature has no "master" key.
    raw = json.dumps({"type": "Deck", "slides": [
        {"type": "Slide", "objects": []}]})
    deck = deck_from_json(raw)
    assert deck.master.objects == []
    serialize_deck(deck)            # and still serialises cleanly


def test_master_painted_behind_every_slide():
    deck = _master_deck()
    tex = serialize_deck(deck)
    # The master text renders once per slide, inside a background template,
    # ahead of the frame body content.
    assert tex.count("MASTERMARK") == len(deck.slides)
    assert "\\setbeamertemplate{background}" in tex
    bg_i = tex.index("\\setbeamertemplate{background}")
    frame_i = tex.index("\\begin{frame}")
    body_i = tex.index("BODYONE")
    assert bg_i < frame_i < body_i        # master is under the frame body


def test_master_only_object_pulls_in_packages():
    # Even with plain slides, a master object must trigger its LaTeX packages.
    deck = Deck(master=Slide(objects=[SlideShape(shape="rect")]),
                slides=[Slide(objects=[SlideText(text="x", locked=True)])])
    assert "\\usepackage{tikz}" in serialize_deck(deck)

    deck = Deck(master=Slide(objects=[SlideTable()]),
                slides=[Slide(objects=[SlideText(text="x", locked=True)])])
    assert "\\usepackage{colortbl}" in serialize_deck(deck)

    deck = Deck(
        master=Slide(objects=[SlidePicture(path="a.png", crop_l=0.1)]),
        slides=[Slide(objects=[SlideText(text="x", locked=True)])])
    assert "\\usepackage{adjustbox}" in serialize_deck(deck)


def test_master_line_uses_overlay_anchoring():
    deck = Deck(master=Slide(objects=[SlideLine()]),
                slides=[Slide(objects=[SlideText(text="x", locked=True)])])
    assert "remember picture,overlay" in serialize_deck(deck)


# --- theme fonts, .sty export, custom theme store ---

def test_font_family_round_trip():
    deck = Deck(slides=[Slide()],
                theme_spec=ThemeSpec(enabled=True, font_family="fira"))
    assert deck_from_json(deck_to_json(deck)) == deck


def test_font_family_emits_package_after_lmodern():
    deck = Deck(slides=[Slide()],
                theme_spec=ThemeSpec(enabled=True, font_family="fira"))
    tex = serialize_deck(deck)
    assert "\\usepackage[sfdefault]{FiraSans}" in tex
    # lmodern resets the default families, so the typeface must come after.
    assert tex.index("\\usepackage{lmodern}") < tex.index("FiraSans")


def test_serif_font_family_switches_font_theme():
    deck = Deck(slides=[Slide()],
                theme_spec=ThemeSpec(enabled=True, font_family="palatino"))
    tex = serialize_deck(deck)
    assert "\\usepackage{newpxtext}" in tex
    assert "\\usefonttheme{serif}" in tex


def test_font_family_disabled_or_unknown_emits_nothing():
    tex = serialize_deck(Deck(slides=[Slide()], theme_spec=ThemeSpec(
        enabled=False, font_family="fira")))
    assert "FiraSans" not in tex
    tex = serialize_deck(Deck(slides=[Slide()], theme_spec=ThemeSpec(
        enabled=True, font_family="nosuch")))
    assert "nosuch" not in tex


def test_theme_to_sty_is_a_usable_beamer_theme():
    from kherveslide.serializer import theme_to_sty
    spec = ThemeSpec(structure="#CC3300", title_rule=True, font_family="fira")
    sty = theme_to_sty(spec, "My Cool Theme!", base_theme="Madrid",
                       color_theme="beaver")
    assert "\\ProvidesPackage{beamerthemeMyCoolTheme}" in sty
    assert "\\mode<presentation>" in sty and "\\mode<all>" in sty
    assert "\\usetheme{Madrid}" in sty
    assert "\\usecolortheme{beaver}" in sty
    assert "\\definecolor{ksth0}{HTML}{CC3300}" in sty
    # The export always emits the overrides, even if the spec was toggled
    # off in the deck (an exported theme with nothing in it is useless).
    assert "FiraSans" in sty


def test_custom_theme_store_round_trip(tmp_path):
    from kherveslide import custom_themes
    spec = ThemeSpec(enabled=True, structure="#123456", font_family="lato")
    master = Slide(objects=[SlideText(text="LOGO", x=0.8, y=0.9,
                                      w=0.15, h=0.06)])
    custom_themes.save_theme("Corp deck", spec, master, base_theme="Berlin",
                             color_theme="seagull", directory=tmp_path)
    loaded = custom_themes.load_themes(directory=tmp_path)
    assert list(loaded) == ["Corp deck"]
    t = loaded["Corp deck"]
    assert t["spec"] == spec
    assert t["master"].objects == master.objects
    assert t["base_theme"] == "Berlin" and t["color_theme"] == "seagull"
    # Saving under the same name overwrites; deleting empties the store.
    custom_themes.save_theme("Corp deck", ThemeSpec(), Slide(),
                             directory=tmp_path)
    assert (custom_themes.load_themes(directory=tmp_path)["Corp deck"]["spec"]
            == ThemeSpec())
    assert custom_themes.delete_theme("Corp deck", directory=tmp_path)
    assert custom_themes.load_themes(directory=tmp_path) == {}


def test_import_sty_names_beamer_themes(tmp_path):
    from kherveslide import custom_themes
    src = tmp_path / "src"
    src.mkdir()
    theme = src / "beamerthemeNord.sty"
    theme.write_text("% theme", encoding="utf-8")
    helper = src / "colors.sty"
    helper.write_text("% helper", encoding="utf-8")
    dest = tmp_path / "styles"
    assert custom_themes.import_sty(theme, directory=dest) == "Nord"
    # A non-theme .sty is copied as a support file, not offered as a theme.
    assert custom_themes.import_sty(helper, directory=dest) == ""
    assert custom_themes.installed_sty_themes(directory=dest) == ["Nord"]
    assert (dest / "colors.sty").exists()


# --- video boxes (click-to-play file: links) ---

def test_video_round_trip():
    from kherveslide.model import SlideVideo
    deck = Deck(slides=[Slide(objects=[SlideVideo(
        path="demo.mp4", poster="p.png", x=0.2, y=0.3, w=0.5, h=0.4)])])
    assert deck_from_json(deck_to_json(deck)) == deck


def test_video_emits_file_launch_link():
    # NOT beamer's \movie: under tectonic (XeTeX + xdvipdfmx) \movie is
    # silently dropped from the PDF, while an \href{file:...} survives as
    # a real /Launch annotation. Guard against a well-meaning "upgrade".
    from kherveslide.model import SlideVideo
    deck = Deck(slides=[Slide(objects=[SlideVideo(path="C:\\vids\\demo.mp4")])],
                nav_symbols=False)
    tex = serialize_deck(deck)
    assert "\\href{file:C:/vids/demo.mp4}" in tex   # backslashes normalised
    assert "\\movie" not in tex and "multimedia" not in tex
    # No poster -> a text-built placeholder (colorbox + play glyph). It must
    # NOT be tikz or \rule: xdvipdfmx sizes link annotations to glyphs and
    # images, so a drawn-only face loses its click area entirely.
    assert "\\colorbox[HTML]{262626}" in tex
    assert "\\blacktriangleright" in tex
    assert "\\usepackage{amssymb}" in tex
    assert "\\usepackage{tikz}" not in tex


def test_video_poster_replaces_placeholder():
    from kherveslide.model import SlideVideo
    deck = Deck(slides=[Slide(objects=[SlideVideo(
        path="demo.mp4", poster="poster.png")])], nav_symbols=False)
    tex = serialize_deck(deck)
    assert "\\includegraphics[width=\\linewidth" in tex
    assert "\\blacktriangleright" not in tex
    assert "\\usepackage{amssymb}" not in tex


def test_video_without_file_is_placeholder_only():
    from kherveslide.model import SlideVideo
    deck = Deck(slides=[Slide(objects=[SlideVideo()])], nav_symbols=False)
    tex = serialize_deck(deck)
    assert "\\href" not in tex           # no file yet -> nothing to launch
    assert "\\colorbox[HTML]{262626}" in tex   # but the placeholder shows


def test_video_never_flows_even_when_locked():
    # A locked video must still be absolutely placed (textpos), never
    # handed to beamer's flow layout.
    from kherveslide.model import SlideVideo
    deck = Deck(slides=[Slide(objects=[SlideVideo(path="a.mp4", locked=True)])],
                nav_symbols=False)
    tex = serialize_deck(deck)
    assert "% video (free-positioned)" in tex
    assert "\\begin{textblock}" in tex


def test_window_themes_define_the_full_key_set():
    # Every appearance theme must define every colour key the QPalette
    # builder and QSS generators read — a missing key is a runtime KeyError
    # the moment that theme is picked from View > Appearance.
    from kherveslide.themes import DEFAULT_THEME, THEMES
    reference = set(THEMES["Light"])
    for name, theme in THEMES.items():
        assert set(theme) == reference, f"{name} palette keys differ"
        assert theme["dark"] in ("0", "1")
    # The startup default must always name a real theme.
    assert DEFAULT_THEME in THEMES


def test_compile_defaults_to_offline_first():
    # KherveSlide is an offline app: the in-app compile must prefer the local
    # cache by default so a normal compile never reaches the network.
    import inspect
    from kherveslide.compiler import compile_tex
    sig = inspect.signature(compile_tex)
    assert sig.parameters["prefer_cached"].default is True


def test_missing_resource_triggers_network_but_syntax_error_does_not():
    # The one-shot network fallback must fire only for a fetchable missing
    # package/font — never for an ordinary LaTeX error in the user's source,
    # otherwise a source typo would drag the live preview onto the network.
    from kherveslide.compiler import _log_wants_network
    missing_sty = "! LaTeX Error: File `beamerthemeMetropolis.sty' not found."
    missing_cls = "! LaTeX Error: File `revtex4-2.cls' not found."
    assert _log_wants_network(missing_sty)
    assert _log_wants_network(missing_cls)
    # Fonts the cache lacks (the PDF stage or a size not yet fetched).
    assert _log_wants_network(
        'warning: Could not locate a virtual/physical font for TFM "rm-lmss12".')
    assert _log_wants_network(
        'caused by: Cannot proceed without .vf or "physical" font for PDF output...')
    assert _log_wants_network(
        "! Font OT1/lmss/m/n/11=rm-lmss12 at 11.0pt not loadable: Metric (TFM) "
        "file or installed font not found.")
    assert _log_wants_network(
        "! Package tikz Error: I did not find the tikz library "
        "'shapes.geometric'.")
    # Source-level errors: no network retry.
    assert not _log_wants_network("! Undefined control sequence.")
    assert not _log_wants_network("! Missing $ inserted.")
    assert not _log_wants_network("")
    # A missing IMAGE is handled up front (placeholder box), so it must not be
    # mistaken for a fetchable resource and drag the compile onto the network.
    assert not _log_wants_network("! Package pdftex.def Error: File `p.png' not found")


def test_offline_warmup_covers_every_offered_theme_and_font():
    # The offline pre-cache (offline.py) must warm EVERY beamer theme,
    # colour theme and font the app can emit — otherwise picking one the
    # warm-up skipped would still hit the network. offline.py reads its
    # lists straight from serializer, so this guards that the single
    # source stays authoritative and that fonts stay wired through.
    from kherveslide import offline
    from kherveslide.serializer import (
        BEAMER_THEMES, BEAMER_COLOR_THEMES, FONT_FAMILIES,
    )
    names = {n for n, _tex in offline._documents()}
    for t in BEAMER_THEMES:
        assert f"theme {t}" in names, f"offline warm-up misses theme {t}"
    for c in BEAMER_COLOR_THEMES:
        assert f"colours {c}" in names, f"offline warm-up misses colours {c}"
    for key in FONT_FAMILIES:
        assert f"font {key}" in names, f"offline warm-up misses font {key}"
    docs = dict(offline._documents())
    from kherveslide.flowchart import TIKZ_LIBRARIES
    for lib in TIKZ_LIBRARIES:                 # the flowchart builder
        assert lib in docs["flowchart"]
    assert "mhchem" in docs["chemistry"] and "chemfig" in docs["chemistry"]


# --- double-click an equation box reopens the equation editor ---

def test_math_only_detects_each_delimiter():
    from kherveslide.canvas import _math_only
    assert _math_only(r"$\frac{x}{y}$") == r"\frac{x}{y}"
    assert _math_only(r"\[E=mc^2\]") == "E=mc^2"
    assert _math_only(r"\(a+b\)") == "a+b"


def test_math_only_rejects_prose_and_mixed_content():
    from kherveslide.canvas import _math_only
    assert _math_only("Hello world") is None
    assert _math_only("cost is $5 and $6") is None
    assert _math_only("") is None


def test_rewrap_math_preserves_the_original_delimiters():
    """Re-editing a display equation must not silently demote it to inline."""
    from kherveslide.canvas import rewrap_math
    assert rewrap_math(r"\[E=mc^2\]", "a+b") == r"\[a+b\]"
    assert rewrap_math(r"\(E=mc^2\)", "a+b") == r"\(a+b\)"
    assert rewrap_math(r"$E=mc^2$", "a+b") == "$a+b$"


def test_math_only_rewrap_round_trip():
    from kherveslide.canvas import _math_only, rewrap_math
    for original in (r"$\frac{x}{y}$", r"\[E=mc^2\]", r"\(a+b\)"):
        inner = _math_only(original)
        assert _math_only(rewrap_math(original, inner)) == inner


# --- themed backdrop: the canvas page looks like the LaTeX one ---

def test_backdrop_keeps_theme_furniture_but_drops_objects():
    from kherveslide.serializer import serialize_backdrop
    d = _sample_deck()
    d.plain_frames = False
    d.page_number = "of_total"
    tex = serialize_backdrop(d)
    assert "\\usetheme{Madrid}" in tex
    assert "\\frametitle{Intro}" in tex          # the title bar stays
    assert "Hello" not in tex                    # the boxes are gone
    assert "img/a.png" not in tex
    assert "\\inserttotalframenumber" in tex     # numbers still line up
    # one page per slide, even for slides that end up empty, then the
    # bullet probes — unnumbered, so the slide numbers stay right
    from kherveslide.serializer import PROBE_SIZES
    assert tex.count("\\begin{frame}[t]") == len(d.slides)
    assert tex.count("\\mbox{}\n\\end{frame}") == len(d.slides)
    assert tex.count("[plain,noframenumbering]") == len(PROBE_SIZES)


def test_backdrop_leaves_the_deck_untouched():
    from kherveslide.serializer import serialize_backdrop
    d = _sample_deck()
    before = deck_to_json(d)
    serialize_backdrop(d)
    assert deck_to_json(d) == before


def test_backdrop_keeps_slide_background_and_master():
    from kherveslide.serializer import serialize_backdrop
    d = _sample_deck()
    d.master = Slide(objects=[SlideText(text="LOGO", x=0.8, y=0.9,
                                        w=0.1, h=0.05)])
    tex = serialize_backdrop(d)
    assert "FFEECC" in tex      # Intro slide's background colour
    assert "LOGO" in tex        # the master is part of the backdrop


def test_deck_body_family_follows_serif_themes():
    from kherveslide.serializer import deck_body_family
    d = _sample_deck()
    assert deck_body_family(d) == "sf"
    d.theme_spec = ThemeSpec(enabled=True, fonts="serif")
    assert deck_body_family(d) == "rm"
    d.theme_spec = ThemeSpec(enabled=True, font_family="palatino")
    assert deck_body_family(d) == "rm"
    d.theme_spec = ThemeSpec(enabled=True, font_family="fira")
    assert deck_body_family(d) == "sf"
    d.theme_spec = ThemeSpec(enabled=False, fonts="serif")
    assert deck_body_family(d) == "sf"


# --- Latin Modern for the canvas ---

def test_latex_fonts_finds_the_cache_folder(tmp_path):
    from kherveslide import latex_fonts
    assert latex_fonts.find_font_dir([tmp_path]) is None
    d = tmp_path / "data" / "abc123"
    d.mkdir(parents=True)
    (d / "lmsans10-regular.otf").write_bytes(b"")
    assert latex_fonts.find_font_dir([tmp_path / "nope", tmp_path]) == d


# --- welcome page layout modes ---

def test_layout_modes_normalise_to_side():
    from kherveslide.welcome import (
        LAYOUTS, LAYOUT_SIDE, LAYOUT_TEXT, LAYOUT_VISUAL, LAYOUT_WINDOW,
        normalise_layout)
    assert LAYOUTS == (LAYOUT_SIDE, LAYOUT_WINDOW, LAYOUT_VISUAL)
    for m in LAYOUTS:
        assert normalise_layout(m) == m
        assert LAYOUT_TEXT[m][0].startswith("Visual")
    assert normalise_layout("slide") == LAYOUT_VISUAL   # old saved mode
    assert normalise_layout("bogus") == LAYOUT_SIDE
    assert normalise_layout(None) == LAYOUT_SIDE


# --- updater ---

def test_updater_version_parsing():
    from kherveslide.updater import parse_version, newer_release
    assert parse_version("v0.123") == (0, 123)
    assert parse_version("0.12.345+abc1234") == (0, 12, 345)
    assert parse_version("nonsense") is None
    assert newer_release("v0.124", "0.123")
    assert newer_release("v1.0", "0.999")
    assert not newer_release("v0.123", "0.123")
    assert not newer_release("garbage", "0.1")


def test_updater_status_only_fast_forwards_clean_checkouts():
    from kherveslide.updater import Status
    assert Status(behind=2).can_fast_forward
    assert not Status(behind=0).available
    dirty = Status(behind=1, dirty=True)
    assert dirty.available and not dirty.can_fast_forward
    assert "uncommitted" in dirty.why_not()
    ahead = Status(behind=1, ahead=2, upstream="origin/dev")
    assert not ahead.can_fast_forward
    assert "2 commit(s)" in ahead.why_not()


def test_updater_changelog_bolds_the_prefix():
    from kherveslide.updater import changelog_markdown
    md = changelog_markdown(["v0.123: welcome page", "plain subject"])
    assert md.splitlines() == ["- **v0.123** — welcome page",
                               "- plain subject"]


def test_updater_against_a_local_remote(tmp_path):
    """A clean clone behind its remote is fast-forwarded; a dirty one is
    left alone."""
    import shutil
    import subprocess
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    from kherveslide import updater

    def git(cwd, *a):
        subprocess.run(["git", *a], cwd=cwd, check=True,
                       capture_output=True)
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    git(origin, "config", "user.email", "t@t")
    git(origin, "config", "user.name", "t")
    (origin / "a.txt").write_text("1")
    git(origin, "add", "a.txt")
    git(origin, "commit", "-q", "-m", "v0.1: first")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    st = updater.check(clone)
    assert st.behind == 0 and not st.available
    (origin / "a.txt").write_text("2")
    git(origin, "commit", "-q", "-am", "v0.2: second")
    st = updater.check(clone)
    assert st.behind == 1 and st.can_fast_forward
    assert st.subjects == ["v0.2: second"]
    updater.fast_forward(clone, st)
    assert (clone / "a.txt").read_text() == "2"
    (origin / "a.txt").write_text("3")
    git(origin, "commit", "-q", "-am", "v0.3: third")
    (clone / "a.txt").write_text("local edit")
    st = updater.check(clone)
    assert st.available and not st.can_fast_forward
    with pytest.raises(updater.UpdateError):
        updater.fast_forward(clone, st)


# --- the theme's own bullets on the canvas ---

def test_backdrop_probes_real_itemize_at_every_size_and_level():
    from kherveslide.serializer import (
        serialize_backdrop, PROBE_SIZES, PROBE_LEVELS)
    tex = serialize_backdrop(_sample_deck())
    probes = tex[tex.index("bullet probe"):]
    for size in PROBE_SIZES:
        assert f"\\fontsize{{{size}}}" in probes
    # level 3 = two empty-label outer items around the probed one
    assert probes.count("\\item[] \\begin{itemize}\\item[] ") == len(PROBE_SIZES)
    assert probes.count("\\item x") == len(PROBE_SIZES) * PROBE_LEVELS
    # white page, no nav symbols: only the bullet and the "x" ink
    assert "bg=white" in probes
    assert "\\setbeamertemplate{navigation symbols}{}" in probes
    assert probes.rstrip().endswith("\\end{document}")


def test_probe_cells_follow_the_deck_gap():
    from kherveslide.serializer import probe_cell, probe_list_left
    d = _sample_deck()
    for level in (1, 2, 3):
        x0, y0, x1, y1 = probe_cell(d, level)
        assert 0 <= x0 < probe_list_left(d) < x1 <= 1
        assert 0 <= y0 < y1 <= 1
    assert probe_cell(d, 2)[1] > probe_cell(d, 1)[3] - 0.01   # rows apart
    d.gap = 0.1
    assert probe_list_left(d) > 0.1


def _probe_row(w=60, h=30):
    """White RGB row: a 4x4 blue bullet at x 10..14, y 12..16, then an
    "x" (black block) at x 20..26 sitting on baseline y=18."""
    buf = bytearray(b"\xff" * (w * h * 3))
    def put(x, y, rgb):
        i = (y * w + x) * 3
        buf[i:i + 3] = bytes(rgb)
    for y in range(12, 16):
        for x in range(10, 14):
            put(x, y, (0, 0, 200))
    for y in range(13, 18):
        for x in range(20, 26):
            put(x, y, (0, 0, 0))
    return bytes(buf), w, h, w * 3


def test_bullet_analysis_finds_bullet_gap_and_baseline():
    from kherveslide.bullets import analyse_cell
    rgb, w, h, stride = _probe_row()
    # 2 px per pt, 10 pt probe => 20 px per em
    g = analyse_cell(rgb, w, h, stride, 2.0, 10.0, 1, text_origin_px=4)
    assert g is not None and g.level == 1
    assert (g.w_px, g.h_px) == (6, 6)            # 4x4 ink + 1px margin
    assert g.top_em == (18 - 11) / 20            # baseline below crop top
    assert g.gap_em == (20 - 15) / 20
    assert g.indent_em == (20 - 4) / 20
    # the crop keeps the bullet's colour, fully opaque in its middle
    px = g.rgba[(1 * g.w_px + 1) * 4:(1 * g.w_px + 2) * 4]
    assert tuple(px) == (0, 0, 200, 255)
    # and is transparent round the edge
    assert g.rgba[3] == 0


def test_bullet_analysis_gives_up_without_text():
    from kherveslide.bullets import analyse_cell, nearest
    w, h = 40, 20
    blank = b"\xff" * (w * h * 3)
    assert analyse_cell(blank, w, h, w * 3, 1.0, 10.0, 1) is None
    assert nearest([], 12) is None


def test_nested_list_items_keep_the_box_size():
    tex = serialize_deck(_sample_deck())
    assert "\\setbeamerfont{itemize/enumerate subbody}{size=\\relax}" in tex
    assert "\\setbeamerfont{itemize/enumerate subsubbody}{size=\\relax}" in tex


def test_canvas_page_height_matches_beamer_paper():
    """px-per-pt follows beamer's real paper height per aspect ratio:
    a 16:9 slide is 9 cm high, a 4:3 one 9.6 cm."""
    from kherveslide.canvas import page_size_px, SCENE_H, FONT_SCALE
    cm = 72.27 / 2.54
    _, h, fs169 = page_size_px("169")
    assert h == SCENE_H and abs(fs169 - SCENE_H / (9.0 * cm)) < 1e-9
    assert fs169 == FONT_SCALE
    _, _, fs43 = page_size_px("43")
    assert abs(fs43 - SCENE_H / (9.6 * cm)) < 1e-9
    _, _, fs1610 = page_size_px("1610")
    assert abs(fs1610 - SCENE_H / (10.0 * cm)) < 1e-9
    _, _, custom = page_size_px("169", 20.0, 10.0)
    assert abs(custom - SCENE_H / (10.0 * cm)) < 1e-9


# --- theme kit: the simple theme description behind the wizard ---

def test_theme_kit_bar_style_maps_to_title_bar_and_footer():
    from kherveslide.theme_kit import ThemeKit
    kit = ThemeKit(primary="#003E74", accent="#0091D4", title_text="#FFFFFF",
                   title_style="bar", footer_style="bar")
    spec = kit.to_spec()
    assert spec.enabled and spec.structure == "#003E74"
    assert spec.title_bg == "#003E74" and spec.title_fg == "#FFFFFF"
    assert spec.footer_bar and not spec.footline_rule
    assert spec.rule_color == "#0091D4"
    assert spec.block_bg.startswith("#") and spec.block_bg != "#003E74"


def test_theme_kit_plain_and_underline_titles():
    from kherveslide.theme_kit import ThemeKit
    plain = ThemeKit(primary="#500778", title_style="plain",
                     footer_style="line").to_spec()
    assert plain.title_bg == "" and plain.title_fg == "#500778"
    assert plain.footline_rule and not plain.footer_bar
    under = ThemeKit(title_style="underline", footer_style="none").to_spec()
    assert under.title_rule and not under.footline_rule and not under.footer_bar


def test_theme_kit_round_trips_through_spec_and_dict():
    from kherveslide.theme_kit import ThemeKit, kit_from_theme
    kit = ThemeKit(name="Uni", primary="#002147", accent="#A79D96",
                   text="#111111", background="#FAFAFA", title_style="bar",
                   footer_style="line", logo="/x/logo.png", logo_corner="bl",
                   logo_size=0.1, bullets="ball")
    back = kit_from_theme(kit.to_spec(), name="Uni")
    for f in ("primary", "accent", "text", "background", "title_style",
              "footer_style", "logo", "logo_corner", "logo_size", "bullets"):
        assert getattr(back, f) == getattr(kit, f), f
    assert ThemeKit.from_dict(kit.to_dict()) == kit
    assert ThemeKit.from_dict({"primary": "#123456", "bogus": 1}).primary \
        == "#123456"


def test_theme_kit_keeps_the_master_slide():
    from kherveslide.theme_kit import ThemeKit
    master = Slide(objects=[SlideText(text="watermark")])
    t = ThemeKit().to_theme(master)
    assert t["master"] is master and t["base_theme"] == "default"


def test_presets_are_all_valid_kits():
    from kherveslide.theme_kit import presets, TITLE_STYLES, FOOTER_STYLES
    kits = presets()
    assert len({k.name for k in kits}) == len(kits) >= 5
    for k in kits:
        assert k.title_style in TITLE_STYLES and k.footer_style in FOOTER_STYLES
        assert k.to_spec().enabled


def test_footer_bar_and_logo_latex():
    from kherveslide.model import ThemeSpec
    d = _sample_deck()
    d.theme_spec = ThemeSpec(enabled=True, title_bg="#003E74",
                             title_fg="#FFFFFF", footer_bar=True,
                             logo="/tmp/logo.png", logo_corner="br")
    tex = serialize_deck(d)
    assert "{ks footer bar}" in tex and "\\insertshortauthor" in tex
    assert "\\usepackage{tikz}" in tex
    # the logo hook comes after every footline definition
    assert tex.rindex("\\addtobeamertemplate{footline}") > \
        tex.rindex("\\setbeamertemplate{footline}")
    assert "current page.south east" in tex
    assert "yshift=0.07\\paperheight" in tex      # clears the footer bar
    assert "\\includegraphics[height=0.12\\paperheight]{/tmp/logo.png}" in tex


def test_footer_bar_text_is_readable_without_a_title_bar():
    from kherveslide.model import ThemeSpec
    from kherveslide.serializer import _theme_spec_lines, _readable_on
    assert _readable_on("#500778") == "#FFFFFF"
    assert _readable_on("#F5E663") == "#000000"
    lines = "\n".join(_theme_spec_lines(ThemeSpec(
        enabled=True, structure="#500778", title_fg="#500778",
        footer_bar=True)))
    assert "{HTML}{FFFFFF}" in lines


def test_theme_to_sty_carries_the_logo():
    from kherveslide.model import ThemeSpec
    from kherveslide.serializer import theme_to_sty
    sty = theme_to_sty(ThemeSpec(logo="logo.pdf"), "Uni")
    assert "\\RequirePackage{tikz}" in sty and "{logo.pdf}" in sty
    assert "logo" not in theme_to_sty(ThemeSpec(), "Uni").split(
        "ProvidesPackage")[1]


def test_saved_theme_keeps_its_kit(tmp_path):
    from kherveslide import custom_themes
    from kherveslide.theme_kit import ThemeKit
    kit = ThemeKit(name="Uni", primary="#002147")
    custom_themes.save_theme("Uni", kit.to_spec(), Slide(),
                             directory=tmp_path, kit=kit.to_dict())
    loaded = custom_themes.load_themes(tmp_path)["Uni"]
    assert ThemeKit.from_dict(loaded["kit"]) == kit
    custom_themes.save_theme("Old", ThemeSpec(), Slide(), directory=tmp_path)
    assert custom_themes.load_themes(tmp_path)["Old"]["kit"] is None


# --- importing a university template ---

def _make_pptx(path):
    """A template whose slide master has a navy bar across the top and a
    small logo top-right (python-pptx can't add to a master directly, so
    the shapes are built on a slide and moved over)."""
    pptx = pytest.importorskip("pptx")
    from pptx.oxml.shapes.picture import CT_Picture
    from pptx.util import Emu
    prs = pptx.Presentation()
    master = prs.slide_masters[0]
    sw, sh = int(prs.slide_width), int(prs.slide_height)
    scratch = prs.slides.add_slide(prs.slide_layouts[6])
    bar = scratch.shapes.add_shape(1, 0, 0, Emu(sw), Emu(int(sh * 0.12)))
    bar.fill.solid()
    bar.fill.fore_color.rgb = pptx.dml.color.RGBColor(0x00, 0x3E, 0x74)
    master.shapes._spTree.append(bar._element)
    import pymupdf
    logo = path.parent / "logo.png"
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 20), 0)
    pix.clear_with(200)
    pix.save(str(logo))
    _part, rid = master.part.get_or_add_image_part(str(logo))
    master.shapes._spTree.append(CT_Picture.new_pic(
        99, "Logo", "", rid, int(sw * 0.85), int(sh * 0.02),
        int(sw * 0.12), int(sh * 0.08)))
    prs.save(str(path))
    return path


def test_pptx_template_gives_colours_bar_and_logo(tmp_path):
    from kherveslide.theme_import import kit_from_pptx
    src = _make_pptx(tmp_path / "Uni_Template.pptx")
    kit = kit_from_pptx(src, tmp_path / "assets")
    assert kit.name == "Uni Template"
    assert kit.primary == "#003E74" and kit.title_style == "bar"
    assert kit.title_text == "#FFFFFF"
    assert kit.logo and Path(kit.logo).exists()
    assert kit.logo_corner == "tr" and 0.05 <= kit.logo_size <= 0.3
    assert kit.text.startswith("#") and kit.background.startswith("#")


def test_potx_template_opens_too(tmp_path):
    import zipfile
    from kherveslide.theme_import import kit_from_pptx
    src = _make_pptx(tmp_path / "t.pptx")
    potx = tmp_path / "t.potx"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(potx, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "[Content_Types].xml":
                data = data.replace(b"presentationml.presentation.main+xml",
                                    b"presentationml.template.main+xml")
            zout.writestr(item, data)
    assert kit_from_pptx(potx).primary == "#003E74"


def test_powerpoint_fonts_map_to_latex_typefaces():
    from kherveslide.theme_import import font_key
    assert font_key("Arial") == "helvetica"
    assert font_key("Times New Roman") == "times"
    assert font_key("Calibri") == ""
    assert font_key("Fira Sans") == "fira"


def test_picture_of_a_slide_gives_bar_and_background(tmp_path):
    import numpy as np
    import pymupdf
    from kherveslide.theme_import import kit_from_picture
    h, w = 360, 640
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    img[:40] = (0x50, 0x07, 0x78)           # purple title bar
    img[-14:] = (0xAC, 0x14, 0x5A)          # magenta footer
    img[100:110, 40:400] = (0x22, 0x22, 0x22)   # a line of dark text
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, img.tobytes(), 0)
    path = tmp_path / "slide.png"
    pix.save(str(path))
    kit = kit_from_picture(path)
    assert kit.title_style == "bar"
    assert abs(int(kit.primary[1:3], 16) - 0x50) < 10
    assert kit.background == "#FFFFFF"
    assert kit.footer_style in ("bar", "line") and kit.accent
    assert kit.title_text == "#FFFFFF"


def test_beamer_zip_installs_theme_with_its_images(tmp_path):
    import zipfile
    from kherveslide.theme_import import install_beamer_theme
    z = tmp_path / "uni-beamer.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("uni-beamer/beamerthemeUni.sty", "% theme")
        zf.writestr("uni-beamer/beamercolorthemeUni.sty", "% colours")
        zf.writestr("uni-beamer/logos/crest.png", b"png")
        zf.writestr("uni-beamer/example.tex", "\\documentclass{beamer}")
        zf.writestr("__MACOSX/uni-beamer/._beamerthemeUni.sty", "junk")
    styles = tmp_path / "styles"
    assert install_beamer_theme(z, styles) == "Uni"
    assert (styles / "beamerthemeUni.sty").exists()
    assert (styles / "beamercolorthemeUni.sty").exists()
    assert (styles / "logos" / "crest.png").exists()
    assert not (styles / "example.tex").exists()


def test_beamer_import_rejects_other_files(tmp_path):
    from kherveslide.theme_import import install_beamer_theme
    plain = tmp_path / "notatheme.sty"
    plain.write_text("%")
    with pytest.raises(ValueError):
        install_beamer_theme(plain, tmp_path / "s")
    with pytest.raises(ValueError):
        install_beamer_theme(tmp_path / "x.docx", tmp_path / "s")


# --- chemistry from the KherveTeX builders ---

def test_mhchem_and_chemfig_packages_follow_the_content():
    d = _sample_deck()
    assert "mhchem" not in serialize_deck(d)
    d.slides[1].objects.append(SlideText(text="$\\ce{2H2 + O2 -> 2H2O}$"))
    tex = serialize_deck(d)
    assert "\\usepackage[version=4]{mhchem}" in tex and "chemfig" not in tex
    d.slides[1].objects.append(SlideTable(rows=[["\\chemfig{A-B}"]]))
    assert "\\usepackage{chemfig}" in serialize_deck(d)


def test_canvas_loads_pdf_pictures(tmp_path):
    import pymupdf
    from kherveslide.canvas import load_picture
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    pdf = tmp_path / "fig.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    page.draw_rect(pymupdf.Rect(10, 10, 190, 90), color=(1, 0, 0), fill=(1, 0, 0))
    doc.save(str(pdf))
    pm = load_picture(str(pdf), pdf_width=400)
    assert pm is not None and pm.width() == 400 and pm.height() == 200
    assert load_picture(str(tmp_path / "missing.pdf")) is None
    assert load_picture("") is None


def test_slide_numbers_dont_replace_the_theme_footer_bar():
    from kherveslide.model import ThemeSpec
    d = _sample_deck()
    d.plain_frames = False
    d.page_number = "of_total"
    d.theme_spec = ThemeSpec(enabled=True, footer_bar=True,
                             title_bg="#003E74")
    tex = serialize_deck(d)
    # only the bar's footline, which carries the number itself
    assert tex.count("\\setbeamertemplate{footline}") == 1
    assert "{ks footer bar}" in tex and "\\inserttotalframenumber" in tex
    d.foot_left = "My talk"          # explicit slots still win
    assert tex.count("\\setbeamertemplate{footline}") < serialize_deck(
        d).count("\\setbeamertemplate{footline}")


# --- example presentations ---

_EXAMPLE_MEDIA = (Path(__file__).resolve().parent.parent / "kherveslide"
                  / "example_media")


def test_every_example_builds_and_serializes(tmp_path):
    from kherveslide.examples import EXAMPLES, build_example, example_names
    assert len(example_names()) == len(EXAMPLES) >= 5
    for name in example_names():
        deck = build_example(name, tmp_path)
        assert len(deck.slides) >= 5, name
        tex = serialize_deck(deck)
        assert tex.count("\\begin{frame}") == len(deck.slides), name
        # nothing unescaped that LaTeX would read as a comment / tab
        for s in deck.slides:
            for o in s.objects:
                for text in [getattr(o, "text", "")] + [
                        c for row in getattr(o, "rows", []) for c in row]:
                    assert " %" not in text.replace("\\%", ""), (name, text)
                    assert "&" not in text.replace("\\&", ""), (name, text)
        # pictures point at charts drawn into the assets folder
        for s in deck.slides:
            for o in s.objects:
                if isinstance(o, SlidePicture):
                    assert Path(o.path).exists() and \
                        Path(o.path).parent in (tmp_path, _EXAMPLE_MEDIA)
        assert deck_from_json(deck_to_json(deck)) == deck
    with pytest.raises(KeyError):
        build_example("Nope", tmp_path)


# --- canvas shows inline LaTeX as it prints; the editor keeps the source ---

def test_painted_text_renders_inline_maths_and_escapes():
    from kherveslide.canvas import latex_to_html, math_to_html
    html = latex_to_html("Smaller $\\Rightarrow$ bluer, 20\\,\\% -- done",
                         pretty=True)
    assert "⇒" in html and "\\Rightarrow" not in html
    assert "20\u2009%" in html and "–" in html and "\\%" not in html
    assert math_to_html("\\Delta U = Q - W") == \
        "Δ<i>U</i> = <i>Q</i> − <i>W</i>"
    assert math_to_html("V_2^{n}") == "<i>V</i><sub>2</sub><sup><i>n</i></sup>"
    assert math_to_html("\\frac{a}{b}") == "<i>a</i>/<i>b</i>"
    assert "ℝ" in math_to_html("\\mathbb{R}")
    coloured = latex_to_html("\\textcolor{orange}{Medium}", pretty=True)
    assert 'color:#FF8000">Medium</span>' in coloured


def test_editor_text_keeps_escapes_so_they_survive_a_commit():
    """The in-place editor shows latex_to_html(pretty=False) and converts
    it back with document_to_latex: \\% must come back as \\%, not a bare
    % (a LaTeX comment that swallows the rest of the line)."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QTextDocument
    from kherveslide.canvas import document_to_latex, latex_to_html
    QApplication.instance() or QApplication([])
    for src in ("Up 20\\,\\% this year", "R\\&D and $x^2$",
                "\\begin{itemize}\n  \\item 5\\% off\n\\end{itemize}"):
        doc = QTextDocument()
        doc.setHtml(latex_to_html(src))
        assert document_to_latex(doc) == src


def test_app_examples_show_bundled_screenshots(tmp_path):
    from kherveslide.examples import build_example
    for name in ("The Kherve tools", "XPS fitting tutorial",
                 "Molecule to model"):
        pics = [o for s in build_example(name, tmp_path).slides
                for o in s.objects if isinstance(o, SlidePicture)
                and Path(o.path).parent == _EXAMPLE_MEDIA]
        assert len(pics) >= 6, name
        assert all(Path(p.path).exists() for p in pics)


def test_backdrop_without_the_master_for_master_view():
    from kherveslide.model import Deck, Slide, SlideText
    from kherveslide.serializer import NO_MASTER_MARK, serialize_backdrop
    deck = Deck(slides=[Slide(title="One")])
    deck.master.objects.append(SlideText(text="MASTERLOGO"))
    with_master = serialize_backdrop(deck)
    assert "MASTERLOGO" in with_master
    assert not with_master.startswith(NO_MASTER_MARK)
    bare = serialize_backdrop(deck, master=False)
    assert "MASTERLOGO" not in bare and bare.startswith(NO_MASTER_MARK)
    assert "One" in bare                      # the theme's page stays
    assert deck.master.objects                # the deck is untouched


# --- flowchart builder model (flowchart.py) ---

def test_flowchart_add_chains_and_connects():
    from kherveslide.flowchart import Flowchart
    fc = Flowchart()
    a = fc.add("terminal", "Start")
    b = fc.add("process", after=a.id)
    c = fc.add("decision", "OK?", after=b.id, label="")
    assert (b.x, b.y) == (0, 1) and (c.x, c.y) == (0, 2)
    assert [(e.src, e.dst) for e in fc.edges] == [(a.id, b.id), (b.id, c.id)]
    assert b.text == "Process"                 # the shape's name by default
    d = fc.add("process", "side", after=b.id)  # spot taken: sidesteps
    assert (d.x, d.y) == (1, 2)
    assert fc.connect(a.id, a.id) is None      # no self-loops
    assert fc.connect(a.id, b.id) is fc.edges[0]   # no duplicates
    fc.remove(b.id)
    assert fc.node(b.id) is None
    assert all(b.id not in (e.src, e.dst) for e in fc.edges)


def test_flowchart_left_to_right_and_json_round_trip():
    from kherveslide.flowchart import Flowchart
    fc = Flowchart(direction="LR")
    a = fc.add("database", "Data")
    b = fc.add("process", "Clean", after=a.id)
    assert (b.x, b.y) == (1, 0)
    fc.edges[0].label = "raw"
    fc.nodes[0].fill = "#FF0000"
    back = Flowchart.from_json(fc.to_json())
    assert back == fc


def test_flowchart_tikz_shapes_routes_and_colours():
    from kherveslide.flowchart import (
        TEMPLATES, TIKZ_LIBRARIES, standalone_doc, to_tikz)
    fc = TEMPLATES["Algorithm (sum to n)"]()
    assert len({n.id for n in fc.nodes}) == len(fc.nodes)   # unique ids
    tikz = to_tikz(fc, "#003E74")
    assert tikz.count("\\node[") == len(fc.nodes)
    assert tikz.count("\\draw[") == len(fc.edges)
    assert "diamond" in tikz and "trapezium" in tikz
    assert "rounded rectangle" in tikz
    assert "{HTML}{003E74}" in tikz            # presentation colours
    assert "node[pos=0.25" in tikz and "{Yes}" in tikz
    # the loop back to the decision goes round the left side
    assert ".west) -- ++(-1.9,0)" in tikz
    doc = standalone_doc(fc)
    for lib in TIKZ_LIBRARIES:
        assert lib in doc
    assert doc.startswith("\\documentclass[border=4pt]{standalone}")
    for name, make in TEMPLATES.items():
        assert make().nodes, name


def test_flowchart_arrowheads_lines_and_chosen_sides():
    from kherveslide.flowchart import Flowchart, to_tikz
    fc = Flowchart()
    a = fc.add("process", "A")
    b = fc.add("process", "B", after=a.id)
    e = fc.edges[0]
    assert (e.head, e.src_side, e.dst_side) == ("end", "auto", "auto")
    assert "\\draw[line, ->]" in to_tikz(fc)
    e.head = "both"
    assert "\\draw[line, <->]" in to_tikz(fc)
    e.head = "none"                            # a plain line
    e.dashed = True
    assert "\\draw[line, -, dashed]" in to_tikz(fc)
    e.head, e.dashed = "start", False
    assert "\\draw[line, <-]" in to_tikz(fc)
    # leave from the right, come back into the right: stub then |-
    e.src_side = e.dst_side = "east"
    assert (f"({a.id}.east) -- ++(0.35,0) |- ({b.id}.east);"
            in to_tikz(fc))
    e.dst_side = "north"                       # into the top: -|
    assert f"({a.id}.east) -- ++(0.35,0) -| ({b.id}.north);" in to_tikz(fc)
    e.route = "straight"
    assert f"({a.id}.east) -- ++(0.35,0) -- ({b.id}.north);" in to_tikz(fc)
    back = Flowchart.from_json(fc.to_json())
    assert back == fc and back.edges[0].head == "start"
    # charts saved before these options still load
    d = json.loads(fc.to_json())
    for k in ("head", "src_side", "dst_side"):
        d["edges"][0].pop(k)
    old = Flowchart.from_json(json.dumps(d))
    assert (old.edges[0].head, old.edges[0].src_side) == ("end", "auto")


def test_flowchart_curved_links():
    from kherveslide.flowchart import Flowchart, to_tikz
    fc = Flowchart()
    a = fc.add("process", "A")
    b = fc.add("process", "B", after=a.id)
    e = fc.edges[0]
    e.route = "curve"
    assert f"({a.id}) to[bend left=30] ({b.id});" in to_tikz(fc)
    e.bend = -45
    assert f"({a.id}) to[bend right=45] ({b.id});" in to_tikz(fc)
    e.bend = 0                                 # no bow: a straight line
    assert f"({a.id}) -- ({b.id});" in to_tikz(fc)
    e.src_side, e.dst_side = "east", "north"   # follows both sides
    assert (f"({a.id}.east) to[out=0, in=90] ({b.id}.north);"
            in to_tikz(fc))
    e.label = "loop"
    assert "to[out=0, in=90] node[pos=0.25" in to_tikz(fc)
    assert Flowchart.from_json(fc.to_json()).edges[0].bend == 0


def test_flowchart_auto_layout_ranks_by_path():
    from kherveslide.flowchart import Flowchart, auto_layout, Node
    fc = Flowchart()
    for nid in ("a", "b", "c", "d"):
        fc.nodes.append(Node(nid, "process", nid, 5, 5))
    fc.connect("a", "b"); fc.connect("a", "c"); fc.connect("b", "d")
    fc.connect("c", "d"); fc.connect("d", "a")          # a loop back
    auto_layout(fc)
    y = {n.id: n.y for n in fc.nodes}
    assert y == {"a": 0, "b": 1, "c": 1, "d": 2}
    xs = sorted(n.x for n in fc.nodes if n.id in "bc")
    assert xs == [-0.5, 0.5]                           # spread around 0


def test_console_is_a_main_window_tab_after_latex(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide.window import SlideWindow
    for name in ("_start_compile", "_start_backdrop",
                 "_maybe_autodownload_packages"):
        monkeypatch.setattr(SlideWindow, name, lambda self, *a: None)
    w = SlideWindow()
    tabs = [w.left_tabs.tabText(i) for i in range(w.left_tabs.count())]
    assert tabs == ["Visual", "LaTeX", "Console"]
    assert w.left_tabs.widget(2) is w.console
    assert w.right_tabs.indexOf(w.console) == -1     # not with the PDF
    w.close()
