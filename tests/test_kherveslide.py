"""Tests for the WYSIWYG beamer deck: model, serializer, templates."""
import json

import pytest

from kherveslide.model import (
    Deck, Slide, SlideText, SlidePicture, SlideTable,
    deck_to_json, deck_from_json,
    raise_object, lower_object, to_front, to_back,
)
from kherveslide.serializer import serialize_deck
from kherveslide import templates


# --- model round-trip ---

def _sample_deck():
    return Deck(
        title="Talk", author="Me", theme="Madrid", aspect="169",
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
        SlideText(x=0.25, y=0.5, w=0.4, h=0.1, text="X")])])
    tex = serialize_deck(deck)
    assert "\\begin{textblock}{0.4}(0.25,0.5)" in tex
    assert "\\textblockorigin{0\\paperwidth}{0\\paperheight}" in tex


def test_serialize_frames_are_plain():
    tex = serialize_deck(_sample_deck())
    assert "\\begin{frame}[plain]" in tex


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


def test_nav_symbols_suppressed_by_default():
    tex = serialize_deck(_sample_deck())
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
    assert "\\colorbox[HTML]{808080}" in tex


def test_background_alpha_round_trip():
    deck = Deck(slides=[Slide(bg="#3366CC", bg_alpha=0.4)])
    assert deck_from_json(deck_to_json(deck)) == deck


def test_nav_symbols_kept_when_enabled():
    deck = _sample_deck()
    deck.nav_symbols = True
    tex = serialize_deck(deck)
    assert "\\setbeamertemplate{navigation symbols}{}" not in tex
    assert deck_from_json(deck_to_json(deck)) == deck


def test_serialize_text_styling():
    deck = Deck(slides=[Slide(objects=[
        SlideText(text="Hi", font_pt=30, color="#FF0000", align="center",
                  bold=True, italic=True, fill="#00FF00")])])
    tex = serialize_deck(deck)
    assert "\\fontsize{30}" in tex
    assert "\\textcolor[HTML]{FF0000}" in tex
    assert "\\textbf{" in tex and "\\textit{" in tex
    assert "\\colorbox[HTML]{00FF00}" in tex
    assert "\\centering" in tex


def test_serialize_picture():
    deck = Deck(slides=[Slide(objects=[
        SlidePicture(x=0.1, y=0.1, w=0.3, h=0.4, path="img/a.png")])])
    tex = serialize_deck(deck)
    expect = ("\\includegraphics[width=0.3\\paperwidth,"
              "height=0.4\\paperheight]{img/a.png}")
    assert expect in tex


def test_serialize_frame_count_matches_slides():
    tex = serialize_deck(_sample_deck())
    assert tex.count("\\begin{frame}") == 2
    assert tex.count("\\end{frame}") == 2


def test_serialize_slide_background():
    # Frame titles are intentionally not emitted (the user composes titles
    # as free text boxes); the slide background still renders.
    deck = Deck(slides=[Slide(title="Heading", bg="#123456")])
    tex = serialize_deck(deck)
    assert "\\frametitle" not in tex
    assert "\\colorbox[HTML]{123456}" in tex


def test_serialize_empty_picture_path_skipped():
    deck = Deck(slides=[Slide(objects=[SlidePicture(path="")])])
    tex = serialize_deck(deck)
    assert "\\includegraphics" not in tex


# --- tables ---

def test_table_round_trip():
    deck = Deck(slides=[Slide(objects=[
        SlideTable(rows=[["a", "b"], ["c", "d"]], border=True, font_pt=16)])])
    assert deck_from_json(deck_to_json(deck)) == deck


def test_serialize_table_tabular():
    deck = Deck(slides=[Slide(objects=[
        SlideTable(x=0.1, y=0.1, w=0.5, h=0.25,
                   rows=[["a", "b"], ["c", "d"]])])])
    tex = serialize_deck(deck)
    assert "\\begin{textblock}{0.5}(0.1,0.1)" in tex
    assert "\\begin{tabular}{|c|c|}" in tex
    assert "a & b \\\\" in tex
    assert "\\hline" in tex


def test_serialize_table_no_border():
    deck = Deck(slides=[Slide(objects=[
        SlideTable(rows=[["x", "y"]], border=False)])])
    tex = serialize_deck(deck)
    assert "\\begin{tabular}{cc}" in tex
    assert "\\hline" not in tex


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


# --- canvas LaTeX -> HTML preview ---

def test_latex_to_html_itemize_is_bullet_list():
    from kherveslide.canvas import latex_to_html
    h = latex_to_html("\\begin{itemize}\n\\item A\n\\item B\n\\end{itemize}")
    assert "<ul>" in h and h.count("<li>") == 2


def test_latex_to_html_enumerate_is_numbered_list():
    from kherveslide.canvas import latex_to_html
    h = latex_to_html("\\begin{enumerate}\n\\item X\n\\end{enumerate}")
    assert "<ol>" in h


def test_latex_to_html_inline_formatting():
    from kherveslide.canvas import latex_to_html
    assert "<b>Hi</b>" in latex_to_html("\\textbf{Hi}")
    assert "<i>yo</i>" in latex_to_html("\\textit{yo}")


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
