"""Tests for the WYSIWYG beamer deck: model, serializer, templates."""
import json

import pytest

from kherveslide.model import (
    Deck, Slide, SlideText, SlidePicture, SlideTable, SlideLine, ThemeSpec,
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
        SlideText(x=0.25, y=0.5, w=0.4, h=0.1, text="X", locked=False)])])
    tex = serialize_deck(deck)
    assert "\\begin{textblock}{0.4}(0.25,0.5)" in tex
    assert "\\textblockorigin{0\\paperwidth}{0\\paperheight}" in tex


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
    deck = Deck(slides=[Slide()], page_number="number")
    tex = serialize_deck(deck)
    assert "\\insertframenumber" in tex
    assert "\\inserttotalframenumber" not in tex


def test_page_number_of_total():
    deck = Deck(slides=[Slide(), Slide()], page_number="of_total")
    tex = serialize_deck(deck)
    assert "\\inserttotalframenumber" in tex
    # One number block per slide.
    assert tex.count("\\insertframenumber") == 2


def test_page_number_round_trip():
    deck = Deck(slides=[Slide()], page_number="of_total")
    assert deck_from_json(deck_to_json(deck)) == deck


def test_nav_symbols_shown_by_default():
    # The prev/next symbols are overlaid at the bottom-right of each frame
    # (works on plain frames too), with beamer's own placement cleared.
    tex = serialize_deck(_sample_deck())
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
    assert "\\colorbox[HTML]{808080}" in tex


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
    assert "\\begin{tikzpicture}[overlay,remember picture]" in tex
    assert "-{Stealth}" in tex
    assert "current page.north west" in tex


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
    deck = Deck(slides=[Slide(bg="#123456")])
    tex = serialize_deck(deck)
    assert "\\colorbox[HTML]{123456}" in tex


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


def test_serialize_empty_picture_path_skipped():
    deck = Deck(slides=[Slide(objects=[SlidePicture(path="")])])
    tex = serialize_deck(deck)
    assert "\\includegraphics" not in tex


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
    assert "\\rowcolor{ksTblHead}" in tex          # coloured header row
    assert "\\textcolor{ksTblHeadFg}{\\textbf{a}}" in tex
    assert "c & d \\\\" in tex                      # body row plain
    assert "\\arrayrulecolor{ksTblRule}\\hline" in tex
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


def test_placement_combo_sets_box_locked(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kherveslide import window
    monkeypatch.setattr(window, "tectonic_available", lambda: False)
    w = window.SlideWindow()
    w.slide.objects.append(SlideText(text="x", locked=True))
    w._reload_scene()
    item = w._items[-1]
    item.setSelected(True)
    assert w.placement_combo.isEnabled()
    # data is (locked, block): index 1 = Beamer-placed, 0 = Free, 2 = Block.
    assert w.placement_combo.currentData() == (True, "")     # Beamer-placed
    w.placement_combo.setCurrentIndex(0)                     # Free
    assert item.obj.locked is False
    w.placement_combo.setCurrentIndex(2)                     # Block
    assert item.obj.locked is True and item.obj.block == "block"
    assert not hasattr(w, "theme_combo")                     # moved to the menu


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


def test_drawing_dialog_background_and_fill():
    from PySide6.QtWidgets import QApplication, QGraphicsRectItem
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QPixmap, QColor, QImage, QPainter
    from PySide6.QtCore import QRectF, Qt
    import tempfile
    from pathlib import Path
    from kherveslide.drawing_dialog import DrawingDialog
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
