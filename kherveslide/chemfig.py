"""Palette templates and preview plumbing for the chemfig structure editor.

Unlike the equation and chemistry editors — whose previews are matplotlib
mathtext — chemfig is TikZ and *cannot* be rendered by mathtext at all. The
live preview therefore compiles a real ``standalone`` document with tectonic
and rasterises the PDF (see ``build_preview_doc`` and the ChemfigEditorDialog
worker). The source the user builds is inserted verbatim as a RawLatex block,
so the compiled document draws native, vector chemfig.

``\\square`` doubles as the tab-navigable placeholder, exactly as in the
equation editor — it compiles fine inside ``\\chemfig{}`` (it renders as an
empty box until filled), so a half-built structure still previews.
"""
from __future__ import annotations

# Tab-navigable empty slot. Reused from the equation editor: it compiles
# inside \chemfig{} (as an empty box) so a partial structure still renders.
PLACEHOLDER = r"\square"
_S = PLACEHOLDER


# Each entry is `(latex_fragment, label)`. The fragment is inserted at the
# cursor in the source field; the label names the palette button. Some groups
# hold whole constructs (\chemfig{...}, \schemestart...\schemestop); others
# hold fragments meant to drop inside an existing \chemfig{}.
#
# Every complete template below is compile-verified against tectonic (see
# tests/test_chemfig.py — the contact-sheet compile) so a palette click can
# never insert something the preview refuses to render.
CHEMFIG_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Structures", [
        (r"\chemfig{" + _S + "}", "chemfig{}"),
        (r"\chemfig{*6(=-=-=-)}", "benzene"),
        (r"\chemfig{CH_3-CH_2-OH}", "ethanol"),
        (r"\chemfig{[:30]CH_3O-C(=[:120]O)-CH(-[:-90]CH_3)-S-C(=[:120]S)-S-[4]CH_2CH_2CH_2CH_3}",
         "MBTPA"),
        (r"\chemfig{CH_2=CH-C(=[:120]O)-O-CH_2CH_2-R}", "acrylate"),
        (r"\chemfig{[6]-(-[2])(-[6])-[@{op}]CH_2-CH(-[6]C(=[:-120]O)-O-R)-[@{cl}]}",
         "repeat unit"),
    ]),
    ("Molecules", [
        (r"\chemfig{H-[:37.5]O-[:-37.5]H}", "water"),
        (r"\chemfig{N(-[:90]H)(-[:210]H)-[:-30]H}", "ammonia"),
        (r"\chemfig{C(-[:90]H)(-[:180]H)(-[:-90]H)-H}", "methane"),
        (r"\chemfig{O=C=O}", "CO2"),
        (r"\chemfig{CH_3-OH}", "methanol"),
        (r"\chemfig{H_2C=O}", "formaldehyde"),
        (r"\chemfig{CH_3-C(=[:90]O)-OH}", "acetic acid"),
        (r"\chemfig{CH_3-C(=[:90]O)-CH_3}", "acetone"),
        (r"\chemfig{H_2N-C(=[:90]O)-NH_2}", "urea"),
        (r"\chemfig{HO-OH}", "peroxide"),
    ]),
    ("Hydrocarbons", [
        (r"\chemfig{CH_3-CH_3}", "ethane"),
        (r"\chemfig{CH_3-CH_2-CH_3}", "propane"),
        (r"\chemfig{-[:30]-[:-30]-[:30]}", "butane (skel.)"),
        (r"\chemfig{-[:30]-[:-30]-[:30]-[:-30]-[:30]}", "hexane (skel.)"),
        (r"\chemfig{CH_3-CH(-[:90]CH_3)-CH_3}", "isobutane"),
        (r"\chemfig{H_2C=CH_2}", "ethylene"),
        (r"\chemfig{HC~CH}", "acetylene"),
        (r"\chemfig{CH_2=CH-CH=CH_2}", "butadiene"),
    ]),
    ("Aromatics", [
        (r"\chemfig{*6(=-=-=-)}", "benzene"),
        (r"\chemfig{*6(=-=-=(-CH_3)-)}", "toluene"),
        (r"\chemfig{*6(=-=-=(-OH)-)}", "phenol"),
        (r"\chemfig{*6(=-=-=(-NH_2)-)}", "aniline"),
        (r"\chemfig{*6(=-=-=(-CH=CH_2)-)}", "styrene"),
        (r"\chemfig{*6(=-=-=(-CHO)-)}", "benzaldehyde"),
        (r"\chemfig{*6(=-=-=(-COOH)-)}", "benzoic acid"),
        (r"\chemfig{*6(=-=-=(-NO_2)-)}", "nitrobenzene"),
        (r"\chemfig{*6(=(-CH_3)-=-(-CH_3)=-)}", "p-xylene"),
        (r"\chemfig{*6(=-(*6(-=-=-))=-=-)}", "naphthalene"),
    ]),
    ("Heterocycles", [
        (r"\chemfig{N*6(-=-=-=)}", "pyridine"),
        (r"\chemfig{O*5(-=-=-)}", "furan"),
        (r"\chemfig{S*5(-=-=-)}", "thiophene"),
        (r"\chemfig{[:-90]HN*5(-=-=-)}", "pyrrole"),
        (r"\chemfig{N*6(-=N-=-=)}", "pyrimidine"),
        (r"\chemfig{O*6(------)}", "THP (pyran)"),
    ]),
    ("Rings", [
        (r"*6(=-=-=-)", "benzene"),
        (r"**6(------)", "aromatic"),
        (r"*6(------)", "cyclohexane"),
        (r"*5(-----)", "cyclopentane"),
        (r"*4(----)", "cyclobutane"),
        (r"*3(---)", "cyclopropane"),
        (r"*7(-------)", "cycloheptane"),
        (f"*6(=-=-=(-{_S})-)", "substituted"),
    ]),
    ("Bonds", [
        (r"-", "single"),
        (r"=", "double"),
        (r"~", "triple"),
        (r"-[:30]", "angle"),
        (r"-[::30]", "rel. angle"),
        (r"-[,1.5]", "long bond"),
        (r">", "wedge up"),
        (r"<", "wedge down"),
        (r">:", "hash up"),
        (r"<:", "hash down"),
        (r">|", "plain wedge"),
        (r"<|", "plain hash"),
    ]),
    ("Groups", [
        (r"-OH", "hydroxyl"),
        (r"(=[:120]O)", "carbonyl"),
        (r"-CHO", "aldehyde"),
        (r"-C(=[:120]O)-OH", "carboxyl"),
        (r"-C(=[:120]O)-O-", "ester"),
        (r"-C(=[:120]O)-NH_2", "amide"),
        (r"-O-", "ether"),
        (r"-NH_2", "amine"),
        (r"-NO_2", "nitro"),
        (r"-CH_3", "methyl"),
        (r"-C~N", "nitrile"),
        (r"-SH", "thiol"),
        (r"-SO_3H", "sulfonic"),
        (r"-O-PO_3H_2", "phosphate"),
        (r"-F", "fluoro"),
        (r"-Cl", "chloro"),
        (r"-Br", "bromo"),
        (r"-I", "iodo"),
    ]),
    ("Stereo", [
        (f"\\chemfig{{{_S}-C(<[:110]{_S})(<:[:70]{_S})-{_S}}}", "chiral C"),
        (f"(<[:60]{_S})", "wedge sub"),
        (f"(<:[:120]{_S})", "hash sub"),
        (f"\\chemfig{{{_S}-C(-[:90]{_S})(-[:-90]{_S})-{_S}}}", "Fischer"),
        (r"\chemfig{R-C(-[:135]H)=C(-[:45]H)-R}", "cis alkene"),
        (r"\chemfig{R-C(-[:135]H)=C(-[:-45]H)-R}", "trans alkene"),
    ]),
    ("Bio", [
        (r"\chemfig{H_2N-CH_2-C(=[:90]O)-OH}", "glycine"),
        (r"\chemfig{H_2N-CH(-[:-90]CH_3)-C(=[:90]O)-OH}", "alanine"),
        (r"\chemfig{H_2N-CH(-[:-90]R)-C(=[:90]O)-OH}", "amino acid"),
        (f"\\chemfig{{{_S}-C(=[:90]O)-NH-{_S}}}", "peptide bond"),
        (r"\chemfig{HO-CH_2-CH(-[:90]OH)-CH_2-OH}", "glycerol"),
        (r"\chemfig{CH_3-CH(-[:90]OH)-C(=[:60]O)-[:-60]OH}", "lactic acid"),
    ]),
    ("Charges", [
        (f"\\chemabove{{{_S}}}{{\\scriptstyle+}}", "cation +"),
        (f"\\chemabove{{{_S}}}{{\\scriptstyle-}}", "anion -"),
        (r"\chemfig{H-\chemabove{N}{\scriptstyle+}(-[:90]H)(-[:-90]H)-H}",
         "ammonium"),
        (f"\\chemfig{{{_S}-\\chemabove{{C}}{{\\scriptstyle+}}(-[:90]{_S})-{_S}}}",
         "carbocation"),
        (f"\\chemfig{{{_S}-\\chembelow{{C}}{{\\scriptstyle-}}(-[:90]{_S})-{_S}}}",
         "carbanion"),
        (r"\chemfig{H-\chemabove{O}{\scriptstyle+}(-[:90]H)-H}", "hydronium"),
    ]),
    ("Scheme", [
        (f"\\schemestart\n\\chemfig{{{_S}}}\n\\arrow\n\\chemfig{{{_S}}}\n\\schemestop",
         "A -> B"),
        # Arrow labels are text mode, and \square is math-only, so the
        # placeholder needs $...$ (mirrors chemistry.PLACEHOLDER) — with a
        # bare \square the template wouldn't preview until filled in.
        (f"\\arrow{{->[${_S}$]}}", "arrow +label"),
        (f"\\arrow{{->[${_S}$][${_S}$]}}", "label +/-"),
        (r"\arrow{->[$\Delta$]}", "heat"),
        (r"\arrow{<=>}", "reversible"),
        (r"\arrow{<->}", "resonance"),
        (r"\+", "plus"),
        (f"\\schemestart\n\\chemfig{{{_S}}} \\+ \\chemfig{{{_S}}}\n"
         f"\\arrow{{->[${_S}$]}}\n\\chemfig{{{_S}}}\n\\schemestop",
         "A + B -> C"),
    ]),
    ("Polymer", [
        (r"-[@{op}]CH_2-CH(-[6]R)-[@{cl}]", "backbone"),
        (r"\polymerdelim[height=6pt,depth=6pt]{op}{cl}", "brackets"),
        (r"\polymerdelim[height=6pt,depth=6pt,indice=$n$]{op}{cl}", "bracket_n"),
        (r"\polymerdelim[height=6pt,depth=6pt,indice=$x$]{op}{cl}", "bracket_x"),
    ]),
]


def all_templates() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for _, items in CHEMFIG_GROUPS:
        out.extend(items)
    return out


# The extra packages a chemfig preview / document needs beyond chemfig itself.
# amssymb supplies \square (the placeholder); the polymer templates use it too.
_PREVIEW_PACKAGES = ("chemfig", "amssymb")


def build_preview_doc(body: str) -> str:
    """A minimal ``standalone`` document that draws *body* cropped to its
    bounding box, for the live-preview compile."""
    lines = [r"\documentclass[border=4pt]{standalone}"]
    lines += [f"\\usepackage{{{p}}}" for p in _PREVIEW_PACKAGES]
    lines += [r"\begin{document}", body.strip(), r"\end{document}", ""]
    return "\n".join(lines)
