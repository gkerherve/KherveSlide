"""Example presentations — what KherveSlide can do, slide by slide.

Templates ▸ Example presentations (and the Welcome page) open one of
these as a new, untitled presentation. Each is a complete, realistic deck
that shows off a different side of the app: custom university-style
themes, equations, chemistry, tables, charts, diagrams built from shapes,
beamer blocks, timelines, KPI cards, process flows…

Everything is free-positioned (``locked=False``) so the canvas and the
PDF agree. Charts are drawn with matplotlib into *assets* when a deck is
built, so no image files ship with the app. Qt-free (the model only).
"""
from __future__ import annotations

from pathlib import Path

from .model import (
    Deck, Slide, SlideLine, SlidePicture, SlideShape, SlideTable, SlideText,
)
from .theme_kit import ThemeKit, presets

# ----------------------------------------------------------------- helpers
_PAGE_H_PT = 9.0 * 72.27 / 2.54          # a 16:9 beamer slide is 9 cm high


def _t(text, x, y, w, h, pt=18, **kw) -> SlideText:
    return SlideText(text=text, x=x, y=y, w=w, h=h, font_pt=pt,
                     locked=False, **kw)


def _items(*lines, enum=False) -> str:
    """itemize / enumerate; a line starting with "- " is a sub-item."""
    env = "enumerate" if enum else "itemize"
    out = [f"\\begin{{{env}}}"]
    sub = False
    for line in lines:
        if line.startswith("- "):
            if not sub:
                out.append("\\begin{itemize}")
                sub = True
            out.append(f"\\item {line[2:]}")
        else:
            if sub:
                out.append("\\end{itemize}")
                sub = False
            out.append(f"\\item {line}")
    if sub:
        out.append("\\end{itemize}")
    out.append(f"\\end{{{env}}}")
    return "\n".join(out)


def _eq(latex, x, y, w, h, pt=24, **kw) -> SlideText:
    return _t(f"\\[{latex}\\]", x, y, w, h, pt, align="center", **kw)


def _shape(kind, x, y, w, h, fill, border="", opacity=1.0, **kw):
    return SlideShape(shape=kind, x=x, y=y, w=w, h=h, fill=fill,
                      border_color=border, border_width=1.2 if border else 0,
                      opacity=opacity, **kw)


def _label(text, x, y, w, h, pt=16, color="#FFFFFF", bold=True, **kw):
    """A one-line label centred in a box (e.g. on a shape): the first
    baseline sits one cap-height below the top, so centre the cap-height."""
    cap = 0.7 * pt / _PAGE_H_PT
    return _t(text, x, y + (h - cap) / 2 - 0.004, w, cap + 0.02, pt,
              align="center", color=color, bold=bold, **kw)


def _table(rows, x, y, w, h, colour, pt=14, **kw) -> SlideTable:
    """A table in the deck's colour: white header text, a soft grid."""
    return SlideTable(rows=rows, x=x, y=y, w=w, h=h, font_pt=pt,
                      header_bg=colour, header_fg="#FFFFFF",
                      rule_color="#C8C8C8", align="center", locked=False,
                      **kw)


def _arrow(x1, y1, x2, y2, color="#555555", width=2.0, **kw) -> SlideLine:
    return SlideLine(x=x1, y=y1, w=x2 - x1, h=y2 - y1, color=color,
                     width_pt=width, arrow_end=True, **kw)


def _card(x, y, w, h, value, caption, colour, value_pt=30):
    """A KPI card: a filled rounded box, a big number and a caption."""
    return [
        _shape("rounded_rect", x, y, w, h, colour),
        _label(value, x, y + 0.02, w, h * 0.55, value_pt),
        _label(caption, x, y + h * 0.52, w, h * 0.4, 12, bold=False),
    ]


def _kit(name: str, **changes) -> ThemeKit:
    kit = next(k for k in presets() if k.name == name)
    return ThemeKit.from_dict({**kit.to_dict(), **changes})


def _themed(deck: Deck, kit: ThemeKit) -> Deck:
    t = kit.to_theme(deck.master)
    deck.theme, deck.color_theme = t["base_theme"], t["color_theme"]
    deck.theme_spec = t["spec"]
    return deck


def _title_slide(title, subtitle, author, colour, *, dark=False):
    ink = "#F2F2F2" if dark else "#1A1A1A"
    soft = "#BBBBBB" if dark else "#555555"
    return Slide(objects=[
        _t(title, 0.08, 0.16, 0.84, 0.32, 32, align="center", bold=True,
           color=ink),
        SlideLine(x=0.38, y=0.52, w=0.24, h=0.0, color=colour,
                  width_pt=2.5),
        _t(subtitle, 0.08, 0.57, 0.84, 0.12, 17, align="center",
           color=soft),
        _t(author, 0.08, 0.76, 0.84, 0.08, 13, align="center", color=soft),
    ])


# ------------------------------------------------------------------ charts
def _charts(assets: Path) -> dict[str, str]:
    """Draw the example charts (once) and return name -> png path."""
    assets.mkdir(parents=True, exist_ok=True)
    paths = {k: assets / f"example_{k}.png"
             for k in ("spectrum", "bars", "growth")}
    if all(p.exists() for p in paths.values()):
        return {k: str(p) for k, p in paths.items()}
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    import numpy as np

    def save(fig, key):
        fig.savefig(paths[key], dpi=200, bbox_inches="tight",
                    transparent=True)

    # 1) photoluminescence-like spectra for three sizes
    fig = Figure(figsize=(5.2, 3.4))
    ax = fig.add_subplot()
    x = np.linspace(450, 750, 400)
    for c, (mu, col) in enumerate(((520, "#0091D4"), (580, "#2E8B57"),
                                   (640, "#C8102E"))):
        ax.plot(x, np.exp(-((x - mu) / 22) ** 2) * (1 - 0.15 * c),
                color=col, lw=2.2, label=f"{3 + c} nm")
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("PL intensity (a.u.)")
    ax.legend(frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    save(fig, "spectrum")

    # 2) progress per work package
    fig = Figure(figsize=(5.2, 3.2))
    ax = fig.add_subplot()
    wps = ["WP1", "WP2", "WP3", "WP4", "WP5"]
    done = [100, 85, 60, 35, 10]
    ax.barh(wps, [100] * 5, color="#E3EDE3")
    ax.barh(wps, done, color="#2E6B30")
    for i, v in enumerate(done):
        ax.text(v + 2 if v < 90 else v - 12, i, f"{v}%", va="center",
                color="#1A1A1A" if v < 90 else "white", fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, 105)
    ax.set_xlabel("Completed (%)")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    save(fig, "bars")

    # 3) growth curve with error bars
    fig = Figure(figsize=(5.0, 3.2))
    ax = fig.add_subplot()
    t = np.arange(0, 11)
    y = 100 / (1 + np.exp(-(t - 5) * 0.9))
    ax.errorbar(t, y, yerr=3 + 0.4 * t, fmt="o", color="#7FB2FF",
                ecolor="#7FB2FF", capsize=3)
    ax.plot(np.linspace(0, 10, 200),
            100 / (1 + np.exp(-(np.linspace(0, 10, 200) - 5) * 0.9)),
            color="#F2C14E", lw=2)
    ax.set_xlabel("Week", color="#E6EAF2")
    ax.set_ylabel("Users (thousands)", color="#E6EAF2")
    ax.tick_params(colors="#E6EAF2")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#E6EAF2")
    save(fig, "growth")
    return {k: str(p) for k, p in paths.items()}


# ===================================================== 1. research talk
def research_talk(assets: Path) -> Deck:
    charts = _charts(assets)
    navy, blue = "#003E74", "#0091D4"
    s = []
    s.append(_title_slide(
        "Quantum dots for brighter LEDs",
        "Size-tuned emission from colloidal perovskite nanocrystals",
        "A. Researcher  ·  Department of Materials  ·  \\today", navy))
    s.append(Slide(title="Outline", objects=[
        _t(_items("Why quantum dots?", "Synthesis and size control",
                  "Optical results", "Towards a working device",
                  "Conclusions and outlook", enum=True),
           0.08, 0.24, 0.5, 0.6, 20),
        _t("Colloidal nanocrystals whose colour is set by their size — "
           "no new chemistry needed for each colour.",
           0.62, 0.3, 0.32, 0.3, 15, block="exampleblock",
           block_title="In one sentence"),
    ]))
    s.append(Slide(title="Motivation", objects=[
        _t("\\textbf{Today's LEDs}", 0.06, 0.22, 0.42, 0.06, 18,
           color=navy),
        _t(_items("Phosphors limit colour purity", "Rare-earth supply risk",
                  "Efficiency drops at high current"),
           0.06, 0.3, 0.42, 0.4, 15),
        _t("\\textbf{Quantum dots}", 0.52, 0.22, 0.42, 0.06, 18,
           color=navy),
        _t(_items("Narrow, tunable emission", "Solution processed",
                  "Near-unity quantum yield"),
           0.52, 0.3, 0.42, 0.4, 15),
        _t("\\textbf{Goal:} a green QD-LED above 20\\,\\% external "
           "quantum efficiency.", 0.1, 0.74, 0.8, 0.08, 15,
           align="center", fill="#E6EEF6", border_color=navy,
           corner="rounded"),
    ]))
    method = [
        _t("Confinement shifts the gap with size:", 0.05, 0.22, 0.52,
           0.06, 15),
        _eq("E_g(r) = E_g^{\\mathrm{bulk}} + \\frac{\\hbar^2\\pi^2}"
            "{2\\mu r^2}", 0.04, 0.32, 0.5, 0.14, 22),
        _t("Smaller dots $\\Rightarrow$ larger gap $\\Rightarrow$ "
           "bluer light.", 0.05, 0.6, 0.52, 0.06, 15),
    ]
    steps = [("Synthesis", 0.29), ("Purification", 0.47),
             ("Spectroscopy", 0.65)]
    for i, (name, y) in enumerate(steps):
        method += [_shape("rounded_rect", 0.62, y, 0.3, 0.11,
                          (navy, blue, "#2E8B57")[i]),
                   _label(name, 0.62, y, 0.3, 0.11, 15)]
        if i:
            method.append(_arrow(0.77, steps[i - 1][1] + 0.11, 0.77, y - 0.005))
    method.append(_t("Hot injection, 160\\,°C, 5 s", 0.05, 0.75, 0.45,
                     0.06, 13, italic=True, color="#666666"))
    s.append(Slide(title="Method", objects=method))
    s.append(Slide(title="Results: size-tuned emission", objects=[
        SlidePicture(path=charts["spectrum"], x=0.04, y=0.2, w=0.52,
                     h=0.62, keep_aspect=True, locked=False),
        _t(_items("Peak shifts by 120\\,nm", "FWHM below 25\\,nm",
                  "Quantum yield up to 92\\,\\%"),
           0.6, 0.22, 0.36, 0.3, 16),
        _table([["Size", "Peak", "QY"],
                ["3 nm", "520 nm", "92\\,\\%"],
                ["4 nm", "580 nm", "88\\,\\%"],
                ["5 nm", "640 nm", "81\\,\\%"]],
               0.6, 0.55, 0.36, 0.25, navy, 13),
    ]))
    s.append(Slide(title="Surface chemistry", objects=[
        _t("Ligand exchange passivates surface traps:", 0.06, 0.22,
           0.88, 0.06, 16),
        _t("$\\ce{PbBr2 + CsBr -> CsPbBr3}$", 0.06, 0.31, 0.88, 0.1, 20,
           align="center"),
        _t("$\\ce{Pb^2+ + 2Br- <=> PbBr2}$", 0.06, 0.45, 0.88, 0.1, 20,
           align="center"),
        _t("Shorter ligands also speed up charge injection in the "
           "device.", 0.15, 0.62, 0.7, 0.12, 15, block="alertblock",
           block_title="Why it matters"),
    ]))
    cards = []
    for i, (v, cap, col) in enumerate((("92\\,\\%", "quantum yield", navy),
                                       ("120 nm", "colour range", blue),
                                       ("21\\,\\%", "LED efficiency",
                                        "#2E8B57"))):
        cards += _card(0.08 + i * 0.3, 0.22, 0.24, 0.22, v, cap, col)
    s.append(Slide(title="Conclusions", objects=cards + [
        _t(_items("Size alone sets the colour across the visible",
                  "Ligand exchange is key to efficiency",
                  "Next: stability under continuous drive"),
           0.08, 0.52, 0.84, 0.32, 17),
    ]))
    s.append(Slide(objects=[
        _t("Thank you", 0.1, 0.3, 0.8, 0.15, 40, align="center",
           bold=True, color=navy),
        _t("Questions?", 0.1, 0.48, 0.8, 0.1, 22, align="center",
           color="#555555"),
        _t("a.researcher@university.ac.uk", 0.1, 0.66, 0.8, 0.08, 14,
           align="center", color=blue),
    ]))
    deck = Deck(title="Quantum dots for brighter LEDs",
                author="A. Researcher", aspect="169", slides=s,
                page_number="of_total")
    return _themed(deck, _kit("Imperial-style navy", footer_style="bar"))


# ========================================================== 2. lecture
def lecture(assets: Path) -> Deck:
    s = [_title_slide("Thermodynamics, lecture 4",
                      "The first law and its applications",
                      "Physics 101  ·  Week 4", "#1F4E79")]
    s.append(Slide(title="Learning objectives", objects=[
        _t("By the end of this lecture you can:", 0.06, 0.22, 0.88, 0.06,
           17),
        _t(_items("State the first law of thermodynamics",
                  "Tell work from heat",
                  "- sign conventions", "- path dependence",
                  "Apply it to ideal-gas processes"),
           0.06, 0.3, 0.88, 0.5, 18),
    ]))
    s.append(Slide(title="The first law", objects=[
        _t("The internal energy $U$ of a system is a state function.",
           0.06, 0.22, 0.88, 0.1, 15, block="definition"),
        _t("For any process, the change in internal energy equals the "
           "heat added minus the work done by the system.",
           0.06, 0.42, 0.88, 0.14, 15, block="theorem",
           block_title="First law"),
        _eq("\\Delta U = Q - W", 0.25, 0.66, 0.5, 0.12, 30),
    ]))
    s.append(Slide(title="Worked example", objects=[
        _t("One mole of ideal gas expands isothermally at 300 K from "
           "10 L to 20 L. Find $Q$ and $W$.", 0.04, 0.22, 0.42, 0.3, 14,
           block="block", block_title="Problem"),
        _t(_items("Isothermal: $\\Delta U = 0$, so $Q = W$",
                  "$W = nRT\\ln(V_2/V_1)$",
                  "$W = 8.314 \\times 300 \\times \\ln 2$",
                  "$W = Q \\approx 1.73$ kJ", enum=True),
           0.5, 0.22, 0.46, 0.5, 15),
        _eq("W=\\int_{V_1}^{V_2} p\\,dV", 0.04, 0.6, 0.42, 0.15, 20),
    ]))
    s.append(Slide(title="Typical values", objects=[
        _table([["Process", "Constant", "$\\Delta U$", "$W$"],
                         ["Isothermal", "$T$", "0", "$nRT\\ln(V_2/V_1)$"],
                         ["Isobaric", "$p$", "$nC_v\\Delta T$",
                          "$p\\,\\Delta V$"],
                         ["Isochoric", "$V$", "$nC_v\\Delta T$", "0"],
                         ["Adiabatic", "$Q=0$", "$-W$",
                          "$\\frac{p_1V_1-p_2V_2}{\\gamma-1}$"]],
               0.08, 0.22, 0.84, 0.5, "#3333B3", striped=True,
               stripe_color="#EEEEF8", caption="Ideal gas, $n$ moles"),
    ]))
    quiz = [_t("Gas is compressed adiabatically. Its temperature…",
               0.06, 0.22, 0.88, 0.08, 17)]
    for i, (letter, text, col) in enumerate((
            ("A", "rises", "#2E7D4F"), ("B", "stays the same", "#1F4E79"),
            ("C", "falls", "#B03A3A"))):
        x = 0.08 + i * 0.29
        quiz += [_shape("rounded_rect", x, 0.36, 0.25, 0.22, col),
                 _label(letter, x, 0.37, 0.25, 0.1, 26),
                 _label(text, x, 0.47, 0.25, 0.08, 14, bold=False)]
    quiz.append(_t("Hint: $Q = 0$, $W < 0$.", 0.06, 0.68, 0.88, 0.08, 14,
                   italic=True, align="center", color="#666666"))
    s.append(Slide(title="Check your understanding", objects=quiz))
    s.append(Slide(title="Summary", objects=[
        _t(_items("$\\Delta U = Q - W$ — energy is conserved",
                  "$U$ depends on the state, $Q$ and $W$ on the path",
                  "Four ideal-gas processes, four sets of results"),
           0.06, 0.24, 0.88, 0.4, 19),
        _t("Next week: the second law and entropy.", 0.06, 0.7, 0.88,
           0.08, 15, align="center", italic=True, color="#1F4E79"),
    ]))
    deck = Deck(title="Thermodynamics, lecture 4", author="Dr. Teacher",
                aspect="169", slides=s, theme="Madrid",
                page_number="of_total")
    return deck


# ==================================================== 3. project update
def project_update(assets: Path) -> Deck:
    charts = _charts(assets)
    green, light = "#2E6B30", "#E3EDE3"
    s = [_title_slide("Project SOLAR",
                      "Quarterly update — progress, risks and next steps",
                      "Steering committee  ·  Q3", green)]
    tl = [SlideLine(x=0.06, y=0.5, w=0.88, h=0.0, color="#888888",
                    width_pt=3.0)]
    for i, (when, what) in enumerate((("Jan", "Kick-off"),
                                      ("Mar", "Prototype"),
                                      ("Jun", "Field test"),
                                      ("Sep", "Pilot"),
                                      ("Dec", "Launch"))):
        x = 0.1 + i * 0.2
        done = i <= 3
        now = i == 3
        r = 0.04 if now else 0.025
        tl += [_shape("circle", x - r, 0.5 - r * 16 / 9, 2 * r,
                      2 * r * 16 / 9,
                      "#F2C14E" if now else (green if done else "#FFFFFF"),
                      border=green),
               _label(when, x - 0.08, 0.33 if i % 2 == 0 else 0.6,
                      0.16, 0.06, 16, color=green),
               _label(what, x - 0.08, 0.39 if i % 2 == 0 else 0.66,
                      0.16, 0.06, 13, color="#333333", bold=False)]
    tl.append(_t("we are here", 0.62, 0.76, 0.16, 0.06, 12, italic=True,
                 align="center", color="#B8860B"))
    s.append(Slide(title="Timeline", objects=tl))
    cards = []
    for i, (v, cap) in enumerate((("£2.1M", "budget spent"),
                                  ("87\\,\\%", "on time"),
                                  ("12", "partners"), ("3", "patents"))):
        cards += _card(0.05 + i * 0.235, 0.24, 0.2, 0.24, v, cap,
                       (green, "#4F8F3A", "#6FA34A", "#8DB85A")[i], 26)
    cards.append(_t("Spend is 4\\,\\% under plan; one milestone moved to Q4.",
                    0.05, 0.6, 0.9, 0.08, 16, align="center"))
    s.append(Slide(title="Key numbers", objects=cards))
    s.append(Slide(title="Progress by work package", objects=[
        SlidePicture(path=charts["bars"], x=0.04, y=0.2, w=0.52, h=0.62,
                     keep_aspect=True, locked=False),
        _t(_items("WP1–2 essentially complete",
                  "WP3 field test running",
                  "WP4 waits on supplier", "WP5 starts in Q4"),
           0.6, 0.24, 0.36, 0.5, 16),
    ]))
    s.append(Slide(title="Risks", objects=[
        _table([["Risk", "Likelihood", "Impact", "Action"],
                         ["Supplier delay", "\\textcolor{orange}{Medium}",
                          "\\textcolor{red}{High}", "Second source"],
                         ["Cell efficiency", "\\textcolor{green!50!black}"
                          "{Low}", "\\textcolor{orange}{Medium}",
                          "Extra test batch"],
                         ["Permits", "\\textcolor{orange}{Medium}",
                          "\\textcolor{orange}{Medium}", "Early filing"]],
               0.06, 0.24, 0.88, 0.42, green, striped=True,
               stripe_color=light),
    ]))
    steps = ["Install", "Measure", "Certify", "Launch"]
    flow = []
    for i, name in enumerate(steps):
        x = 0.05 + i * 0.225
        flow += [_shape("chevron", x, 0.36, 0.23, 0.2,
                        (green, "#4F8F3A", "#6FA34A", "#8DB85A")[i]),
                 _label(name, x + 0.045, 0.36, 0.15, 0.2, 14)]
    flow.append(_t("Decision needed today: approve the pilot site.",
                   0.1, 0.66, 0.8, 0.1, 16, align="center", bold=True,
                   fill=light, corner="rounded"))
    s.append(Slide(title="Next steps", objects=flow))
    s.append(Slide(objects=[
        _shape("rect", 0.0, 0.0, 1.0, 1.0, light),
        _t("“The best way to predict the future is to build it.”",
           0.12, 0.34, 0.76, 0.2, 28, align="center", italic=True,
           color=green),
        _t("— the team", 0.12, 0.58, 0.76, 0.08, 16, align="center",
           color="#555555"),
    ]))
    deck = Deck(title="Project SOLAR", author="Project office",
                aspect="169", slides=s, page_number="number")
    return _themed(deck, _kit("Forest green", footer_style="line"))


# ===================================================== 4. maths seminar
def maths_seminar(assets: Path) -> Deck:
    blue = "#002147"
    s = [_title_slide("The Gaussian integral",
                      "Three proofs and a picture",
                      "Analysis seminar", blue)]
    s.append(Slide(title="Statement", objects=[
        _t("$f(x) = e^{-x^2}$ is integrable on $\\mathbb{R}$.",
           0.06, 0.22, 0.88, 0.1, 15, block="definition"),
        _t("\\[\\int_{-\\infty}^{\\infty} e^{-x^2}\\,dx = \\sqrt{\\pi}\\]",
           0.06, 0.4, 0.88, 0.22, 18, block="theorem",
           block_title="Gauss"),
        _t("Square it, then switch to polar coordinates.",
           0.06, 0.74, 0.88, 0.1, 15, block="proof"),
    ]))
    rows = (("I^2 = \\int\\int e^{-(x^2+y^2)}\\,dx\\,dy", "square"),
            ("= \\int_0^{2\\pi}\\int_0^{\\infty} e^{-r^2}\\,r\\,dr\\,"
             "d\\theta", "polar"),
            ("= 2\\pi \\cdot \\frac{1}{2} = \\pi", "integrate"))
    obj = []
    for i, (latex, why) in enumerate(rows):
        y = 0.2 + i * 0.19
        obj += [_eq(latex, 0.04, y, 0.66, 0.15, 22),
                _t(f"\\textit{{{why}}}", 0.74, y + 0.04, 0.22, 0.08, 15,
                   color="#666666")]
    obj.append(_t("Hence $I = \\sqrt{\\pi}$.", 0.04, 0.84, 0.9, 0.08, 18,
                  align="center", bold=True, color=blue))
    s.append(Slide(title="Proof by polar coordinates", objects=obj))
    pic = [_shape("circle", 0.1, 0.22, 0.32, 0.57, "", border=blue),
           SlideLine(x=0.06, y=0.505, w=0.4, h=0.0, color="#888888",
                     width_pt=1.0, arrow_end=True),
           SlideLine(x=0.26, y=0.84, w=0.0, h=-0.66, color="#888888",
                     width_pt=1.0, arrow_end=True),
           SlideLine(x=0.26, y=0.505, w=0.12, h=-0.2, color="#C8102E",
                     width_pt=2.0),
           _t("$r$", 0.33, 0.33, 0.05, 0.06, 18, color="#C8102E"),
           _t("$\\theta$", 0.3, 0.44, 0.05, 0.06, 16)]
    pic += [_t(_items("The integrand depends on $r$ only",
                      "Rings of radius $r$ have length $2\\pi r$",
                      "That extra $r$ makes it integrable"),
               0.52, 0.26, 0.44, 0.5, 16)]
    s.append(Slide(title="The picture behind it", objects=pic))
    s.append(Slide(title="Open questions", objects=[
        _t(_items("A proof without polar coordinates?",
                  "Which other integrals yield to squaring?",
                  "Higher dimensions: $\\int_{\\mathbb{R}^n} e^{-|x|^2}"
                  "\\,dx = \\pi^{n/2}$", enum=True),
           0.06, 0.24, 0.88, 0.5, 19),
    ]))
    deck = Deck(title="The Gaussian integral", author="Analysis seminar",
                aspect="169", slides=s)
    return _themed(deck, _kit("Oxford-style blue", title_style="underline",
                              footer_style="none", bullets="ball"))


# ================================================ 5. diagrams & workflows
def diagrams(assets: Path) -> Deck:
    purple, pink = "#500778", "#AC145A"
    s = [_title_slide("Diagrams with shapes", "Flowcharts, Venn diagrams, "
                      "processes and comparisons", "KherveSlide examples",
                      purple)]
    fc = [
        _shape("ellipse", 0.06, 0.4, 0.14, 0.16, purple),
        _label("Start", 0.06, 0.4, 0.14, 0.16, 14),
        _arrow(0.2, 0.48, 0.25, 0.48),
        _shape("rounded_rect", 0.25, 0.39, 0.18, 0.18, "#7A3B98"),
        _label("Collect data", 0.25, 0.39, 0.18, 0.18, 13),
        _arrow(0.43, 0.48, 0.48, 0.48),
        _shape("diamond", 0.48, 0.34, 0.2, 0.28, pink),
        _label("Valid?", 0.48, 0.34, 0.2, 0.28, 14),
        _arrow(0.68, 0.48, 0.76, 0.48),
        _t("yes", 0.69, 0.41, 0.06, 0.05, 11, color="#333333"),
        _shape("ellipse", 0.76, 0.4, 0.16, 0.16, purple),
        _label("Publish", 0.76, 0.4, 0.16, 0.16, 14),
        _arrow(0.58, 0.62, 0.58, 0.74),
        _t("no", 0.6, 0.65, 0.06, 0.05, 11, color="#333333"),
        _shape("rounded_rect", 0.48, 0.74, 0.2, 0.12, "#C9A3D9"),
        _label("Clean \\& retry", 0.48, 0.74, 0.2, 0.12, 13, color="#2B0A3D"),
        _arrow(0.48, 0.8, 0.34, 0.8),
        _arrow(0.34, 0.8, 0.34, 0.575),
    ]
    s.append(Slide(title="Flowchart", objects=fc))
    venn = []
    for (x, y, col, name) in ((0.2, 0.2, purple, "Theory"),
                              (0.36, 0.2, pink, "Experiment"),
                              (0.28, 0.43, "#0E7D7D", "Simulation")):
        venn += [_shape("circle", x, y, 0.26, 0.46, col, opacity=0.45)]
    venn += [_label("Theory", 0.19, 0.3, 0.16, 0.06, 15, color="#2B0A3D"),
             _label("Experiment", 0.45, 0.3, 0.2, 0.06, 15,
                    color="#4A0723"),
             _label("Simulation", 0.33, 0.75, 0.16, 0.06, 15,
                    color="#063B3B"),
             _label("Insight", 0.35, 0.46, 0.12, 0.06, 14, color="#FFFFFF"),
             _t(_items("Trust what all three agree on",
                       "Three see-through circles"),
                0.7, 0.3, 0.28, 0.4, 14)]
    s.append(Slide(title="Venn diagram", objects=venn))
    proc = []
    for i, (name, desc) in enumerate((("Plan", "aims and scope"),
                                      ("Build", "prototype fast"),
                                      ("Test", "measure honestly"),
                                      ("Learn", "decide what next"))):
        x = 0.04 + i * 0.235
        col = (purple, "#7A3B98", pink, "#D0587E")[i]
        proc += [_shape("pentagon_arrow", x, 0.3, 0.24, 0.18, col),
                 _label(name, x, 0.3, 0.2, 0.18, 17),
                 _label(desc, x, 0.52, 0.2, 0.06, 13, color="#333333",
                        bold=False)]
    proc.append(_arrow(0.9, 0.7, 0.1, 0.7, color=pink, style="dashed"))
    proc.append(_t("repeat", 0.42, 0.72, 0.16, 0.05, 12, italic=True,
                   align="center", color=pink))
    s.append(Slide(title="A cycle as a process", objects=proc))
    s.append(Slide(title="Comparison", objects=[
        _table([["", "KherveSlide", "Word", "Whiteboard"],
                         ["Equations", "native", "add-in", "by hand"],
                         ["Reuse a theme", "yes", "partly", "no"],
                         ["Version control", "git", "no", "photo"],
                         ["Exact layout", "yes", "mostly", "no"]],
               0.1, 0.22, 0.8, 0.46, purple, 15, striped=True,
               stripe_color="#F3E9F7"),
        _t("Tip: right-click a table to restyle it.", 0.06, 0.74, 0.88,
           0.06, 13, italic=True, align="center", color="#666666"),
    ]))
    deck = Deck(title="Diagrams with shapes", author="KherveSlide",
                aspect="169", slides=s)
    return _themed(deck, _kit("UCL-style purple", footer_style="line"))


# ====================================================== 6. lightning talk
def lightning_talk(assets: Path) -> Deck:
    charts = _charts(assets)
    gold, ink = "#F2C14E", "#E6EAF2"
    s = [_title_slide("Five minutes on growth", "A lightning talk",
                      "@startup  ·  Demo day", gold, dark=True)]
    s.append(Slide(objects=[
        _t("One idea:", 0.1, 0.3, 0.8, 0.1, 20, align="center",
           color="#AAB4C8"),
        _t("make the first minute delightful", 0.06, 0.42, 0.88, 0.2, 34,
           align="center", bold=True, color=gold),
    ]))
    s.append(Slide(title="It worked", objects=[
        SlidePicture(path=charts["growth"], x=0.05, y=0.2, w=0.55, h=0.62,
                     keep_aspect=True, locked=False),
        *_card(0.65, 0.24, 0.3, 0.22, "10×", "users in 10 weeks",
               "#2B3A5C", 32),
        *_card(0.65, 0.52, 0.3, 0.22, "4.8", "app rating (out of 5)",
               "#2B3A5C", 32),
    ]))
    s.append(Slide(title="What we changed", objects=[
        _t(_items("Onboarding cut from 7 screens to 2",
                  "A sample project ready on first launch",
                  "Every action undoable"),
           0.08, 0.26, 0.84, 0.5, 22, color=ink),
    ]))
    s.append(Slide(objects=[
        _t("Thank you", 0.1, 0.36, 0.8, 0.16, 40, align="center",
           bold=True, color=gold),
        _t("slides made with KherveSlide", 0.1, 0.56, 0.8, 0.08, 15,
           align="center", color="#AAB4C8"),
    ]))
    deck = Deck(title="Five minutes on growth", author="@startup",
                aspect="169", slides=s)
    return _themed(deck, _kit("Dark", accent=gold, footer_style="none"))


# ---------------------------------------------------------- science charts
def _science_charts(assets: Path) -> dict[str, str]:
    """XPS fit, XRD pattern, Tauc plot, budget split, convergence — drawn
    once with matplotlib, like :func:`_charts`."""
    assets.mkdir(parents=True, exist_ok=True)
    keys = ("xps", "xrd", "tauc", "budget", "energy")
    paths = {k: assets / f"example_{k}.png" for k in keys}
    if all(p.exists() for p in paths.values()):
        return {k: str(p) for k, p in paths.items()}
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    import numpy as np

    def tidy(ax):
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

    def save(fig, key):
        fig.savefig(paths[key], dpi=200, bbox_inches="tight",
                    transparent=True)

    def pv(x, mu, fwhm, eta=0.3):
        g = np.exp(-4 * np.log(2) * ((x - mu) / fwhm) ** 2)
        lo = 1 / (1 + 4 * ((x - mu) / fwhm) ** 2)
        return eta * lo + (1 - eta) * g

    # 1) XPS Ti 2p: a spin-orbit doublet over a Shirley-like background
    be = np.linspace(470, 452, 500)
    comps = [(458.6, 1.1, 1.0, "#0091D4", "Ti$^{4+}$ 2p$_{3/2}$"),
             (464.3, 2.0, 0.5, "#0091D4", "Ti$^{4+}$ 2p$_{1/2}$"),
             (457.1, 1.3, 0.12, "#C8102E", "Ti$^{3+}$ 2p$_{3/2}$"),
             (462.8, 2.2, 0.06, "#C8102E", "Ti$^{3+}$ 2p$_{1/2}$")]
    peaks = sum(a * pv(be, mu, w) for mu, w, a, _c, _l in comps)
    bg = 0.08 + 0.25 * np.cumsum(peaks[::-1])[::-1] / peaks.sum()
    rng = np.random.default_rng(3)
    data = bg + peaks + rng.normal(0, 0.012, be.size)
    fig = Figure(figsize=(5.2, 3.4))
    ax = fig.add_subplot()
    ax.plot(be, data, "o", ms=2, color="#555555", label="data")
    for mu, w, a, col, lab in comps:
        ax.fill_between(be, bg, bg + a * pv(be, mu, w), color=col,
                        alpha=0.35, lw=0)
    ax.plot(be, bg, color="#888888", lw=1, ls="--", label="Shirley")
    ax.plot(be, bg + peaks, color="#1A1A1A", lw=1.6, label="envelope")
    ax.set_xlim(470, 452)
    ax.set_xlabel("Binding energy (eV)")
    ax.set_ylabel("Intensity (a.u.)")
    ax.set_yticks([])
    ax.legend(frameon=False, fontsize=9)
    tidy(ax)
    save(fig, "xps")

    # 2) XRD of anatase TiO2
    tt = np.linspace(20, 70, 1500)
    refl = [(25.3, 1.0, "(101)"), (37.8, 0.2, "(004)"),
            (48.0, 0.35, "(200)"), (53.9, 0.2, "(105)"),
            (55.1, 0.18, "(211)"), (62.7, 0.14, "(204)")]
    y = sum(a * pv(tt, mu, 0.35, 0.5) for mu, a, _h in refl)
    y += 0.03 + rng.normal(0, 0.006, tt.size)
    fig = Figure(figsize=(5.2, 3.2))
    ax = fig.add_subplot()
    ax.plot(tt, y, color="#003E74", lw=1.2)
    for mu, a, hkl in refl:
        ax.annotate(hkl, (mu, a + 0.06), ha="center", fontsize=8)
    ax.set_xlabel(r"2$\theta$ (°)")
    ax.set_ylabel("Intensity (a.u.)")
    ax.set_yticks([])
    tidy(ax)
    save(fig, "xrd")

    # 3) Tauc plot: (alpha h nu)^2 against photon energy
    e = np.linspace(2.8, 4.0, 200)
    t = np.clip(e - 3.22, 0, None) * 40 + rng.normal(0, 0.3, e.size)
    fig = Figure(figsize=(4.4, 3.2))
    ax = fig.add_subplot()
    ax.plot(e, t, color="#2E8B57", lw=2)
    ax.plot([3.22, 3.95], [0, 0.73 * 40], color="#C8102E", ls="--")
    ax.annotate("$E_g$ = 3.22 eV", (3.22, 0), (3.3, 22),
                arrowprops=dict(arrowstyle="->"), fontsize=10)
    ax.set_xlabel(r"$h\nu$ (eV)")
    ax.set_ylabel(r"$(\alpha h\nu)^2$ (a.u.)")
    tidy(ax)
    save(fig, "tauc")

    # 4) budget split (donut)
    fig = Figure(figsize=(3.6, 3.6))
    ax = fig.add_subplot()
    ax.pie([45, 25, 15, 10, 5],
           labels=["Staff", "Equipment", "Consumables", "Travel",
                   "Other"],
           colors=["#5B2C83", "#8E5CB5", "#B996D6", "#D9C6EA",
                   "#EEE6F5"], startangle=90, counterclock=False,
           wedgeprops=dict(width=0.42, edgecolor="white"),
           autopct="%d%%", pctdistance=0.79, textprops={"fontsize": 9})
    ax.set_aspect("equal")
    save(fig, "budget")

    # 5) geometry optimisation: energy against step
    step = np.arange(0, 25)
    en = -76.42 + 0.35 * np.exp(-step / 4) + rng.normal(0, 0.004,
                                                         step.size)
    fig = Figure(figsize=(4.6, 3.2))
    ax = fig.add_subplot()
    ax.plot(step, en, "o-", color="#00787A", ms=4)
    ax.set_xlabel("Optimisation step")
    ax.set_ylabel("Energy (Hartree)")
    tidy(ax)
    save(fig, "energy")
    return {k: str(p) for k, p in paths.items()}


def _gantt(tasks, months, x0, y0, w, h, colour, light, now=None):
    """A Gantt chart built from shapes: one row per (name, start, length,
    done) task, months as column headers, an optional "today" line."""
    label_w = 0.22
    cw = (w - label_w) / months
    rh = h / (len(tasks) + 1)
    out = []
    for m in range(months):
        mx = x0 + label_w + m * cw
        if m % 2 == 0:
            out.append(_shape("rect", mx, y0 + rh, cw, h - rh, light))
        out.append(_label(f"M{m + 1}", mx, y0, cw, rh, 10,
                          color="#555555", bold=False))
    for i, (name, start, length, done) in enumerate(tasks):
        y = y0 + (i + 1) * rh
        out.append(_t(name, x0, y + rh * 0.18, label_w - 0.01, rh, 12))
        bx = x0 + label_w + start * cw
        out.append(_shape("rounded_rect", bx, y + rh * 0.2, length * cw,
                          rh * 0.6, light, border=colour))
        if done:
            out.append(_shape("rounded_rect", bx, y + rh * 0.2,
                              length * cw * done, rh * 0.6, colour))
    if now is not None:
        nx = x0 + label_w + now * cw
        out.append(SlideLine(x=nx, y=y0 + rh * 0.8, w=0.0, h=h - rh * 0.8,
                             color="#C8102E", width_pt=1.5, style="dashed"))
        out.append(_t("today", nx - 0.04, y0 + h + 0.005, 0.08, 0.05, 10,
                      align="center", color="#C8102E", italic=True))
    return out


# =================================================== 7. project kick-off
def project_kickoff(assets: Path) -> Deck:
    charts = _science_charts(assets)
    purple, light = "#5B2C83", "#EEE6F5"
    s = [_title_slide("Project NOVA — kick-off",
                      "Scope, plan, roles and budget for the next 12 "
                      "months", "Project manager  ·  Kick-off meeting",
                      purple)]
    s.append(Slide(title="Why this project?", objects=[
        _t("Problem", 0.06, 0.22, 0.27, 0.06, 18, bold=True, color=purple),
        _t("Thin-film coatings degrade in humid air within weeks.",
           0.06, 0.3, 0.27, 0.3, 15),
        _t("Objective", 0.37, 0.22, 0.27, 0.06, 18, bold=True,
           color=purple),
        _t("A coating that keeps 90\\,\\% of its performance after "
           "1000\\,h damp-heat.", 0.37, 0.3, 0.27, 0.3, 15),
        _t("Outcome", 0.68, 0.22, 0.27, 0.06, 18, bold=True, color=purple),
        _t("A validated process transferred to the pilot line.",
           0.68, 0.3, 0.27, 0.3, 15),
        _t("Success = 1000\\,h stability, < 5\\,\\% cost increase, one "
           "pilot customer.", 0.1, 0.7, 0.8, 0.09, 15, align="center",
           fill=light, border_color=purple, corner="rounded"),
    ]))
    tasks = [("WP1 Requirements", 0, 2, 1.0), ("WP2 Synthesis", 1, 4, 0.6),
             ("WP3 Analysis", 2, 6, 0.3),
             ("WP4 Ageing tests", 5, 5, 0.0), ("WP5 Scale-up", 8, 4, 0.0),
             ("WP6 Reporting", 0, 12, 0.2)]
    gantt = _gantt(tasks, 12, 0.04, 0.2, 0.92, 0.58, purple, light,
                   now=2.6)
    for m, name in ((2, "M1"), (6, "M2"), (12, "M3")):
        mx = 0.04 + 0.22 + m * (0.92 - 0.22) / 12
        gantt.append(_shape("diamond", mx - 0.012, 0.815, 0.024, 0.043,
                            "#F2C14E", border=purple))
        gantt.append(_t(name, mx - 0.03, 0.86, 0.06, 0.05, 10,
                        align="center", color=purple))
    s.append(Slide(title="Plan (Gantt)", objects=gantt))
    R = "\\textbf{R}"
    s.append(Slide(title="Who does what (RACI)", objects=[
        _table([["Work package", "PI", "Postdoc", "PhD", "Partner"],
                ["Requirements", "A", R, "C", "C"],
                ["Synthesis", "A", "C", R, "I"],
                ["Characterisation", "A", R, R, "I"],
                ["Ageing tests", "I", "A", "C", R],
                ["Scale-up", "A", "C", "I", R]],
               0.06, 0.22, 0.6, 0.56, purple, 13, striped=True,
               stripe_color=light),
        _t(_items("\\textbf{R}esponsible", "\\textbf{A}ccountable",
                  "\\textbf{C}onsulted", "\\textbf{I}nformed"),
           0.7, 0.3, 0.26, 0.4, 14),
    ]))
    s.append(Slide(title="Budget", objects=[
        SlidePicture(path=charts["budget"], x=0.04, y=0.18, w=0.42,
                     h=0.66, keep_aspect=True, locked=False),
        *_card(0.52, 0.22, 0.2, 0.2, "£480k", "total", purple, 24),
        *_card(0.76, 0.22, 0.2, 0.2, "12", "months", "#8E5CB5", 24),
        _t(_items("Staff: one postdoc, one PhD student",
                  "Equipment: humidity chamber",
                  "10\\,\\% contingency held centrally"),
           0.52, 0.5, 0.44, 0.3, 14),
    ]))
    s.append(Slide(title="Governance \\& communication", objects=[
        _shape("rounded_rect", 0.38, 0.2, 0.24, 0.12, purple),
        _label("Steering board", 0.38, 0.2, 0.24, 0.12, 14),
        _arrow(0.5, 0.32, 0.5, 0.42, purple),
        _shape("rounded_rect", 0.38, 0.42, 0.24, 0.12, "#8E5CB5"),
        _label("Project manager", 0.38, 0.42, 0.24, 0.12, 14),
        *[o for i, wp in enumerate(("WP1–2", "WP3–4", "WP5–6"))
          for o in (_arrow(0.5, 0.54, 0.2 + i * 0.3, 0.64, purple),
                    _shape("rounded_rect", 0.1 + i * 0.3, 0.64, 0.2, 0.1,
                           light, border=purple),
                    _label(wp, 0.1 + i * 0.3, 0.64, 0.2, 0.1, 13,
                           color=purple))],
        _t("Weekly stand-up  ·  monthly report  ·  quarterly board",
           0.1, 0.82, 0.8, 0.06, 13, align="center", italic=True,
           color="#555555"),
    ]))
    s.append(Slide(title="Decisions today", objects=[
        _t(_items("Approve the work-package leads",
                  "Approve the purchase of the humidity chamber",
                  "Fix the date of the first steering board", enum=True),
           0.08, 0.26, 0.84, 0.4, 20),
        _t("Next meeting: end of month 2 (milestone M1).", 0.15, 0.72,
           0.7, 0.1, 15, block="exampleblock", block_title="Next"),
    ]))
    deck = Deck(title="Project NOVA — kick-off", author="Project office",
                aspect="169", slides=s, page_number="of_total")
    return _themed(deck, _kit("UCL-style purple", footer_style="line"))


# ================================================= 8. materials science
def materials_talk(assets: Path) -> Deck:
    charts = _science_charts(assets)
    navy, blue, teal = "#003E74", "#0091D4", "#2E8B57"
    s = [_title_slide("Oxygen vacancies in TiO$_2$ thin films",
                      "Sputter deposition, XRD, XPS and optical band gap",
                      "A. Researcher  ·  Surface Analysis Group  ·  "
                      "\\today", navy)]
    flow = []
    for i, (name, col) in enumerate((("Sputter", navy),
                                     ("Anneal", blue),
                                     ("XRD", teal), ("XPS", "#C8102E"),
                                     ("UV–Vis", "#B8860B"))):
        x = 0.04 + i * 0.19
        flow += [_shape("chevron", x, 0.24, 0.2, 0.16, col),
                 _label(name, x + 0.02, 0.24, 0.16, 0.16, 11)]
    flow += [
        _t(_items("Reactive DC sputtering, Ar/O$_2$ = 4:1, 300\\,W",
                  "Anneal 450\\,°C, 2\\,h, in air or vacuum",
                  "Films 200\\,nm on Si and quartz"),
           0.06, 0.5, 0.56, 0.32, 15),
        _t("Vacuum anneal removes lattice oxygen: "
           "$\\ce{TiO2 -> TiO_{2-x} + x/2 O2}$", 0.65, 0.5, 0.3, 0.3, 13,
           block="block", block_title="Hypothesis"),
    ]
    s.append(Slide(title="Samples and workflow", objects=flow))
    s.append(Slide(title="Structure: anatase only", objects=[
        SlidePicture(path=charts["xrd"], x=0.03, y=0.18, w=0.56, h=0.66,
                     keep_aspect=True, locked=False),
        _t("Crystallite size (Scherrer):", 0.62, 0.22, 0.34, 0.06, 14),
        _eq("D = \\frac{K\\lambda}{\\beta\\cos\\theta}", 0.62, 0.28, 0.34,
            0.13, 18),
        _table([["Anneal", "$D$ (nm)"], ["air", "18"], ["vacuum", "21"]],
               0.66, 0.52, 0.26, 0.2, navy, 13),
        _t("No rutile or brookite detected.", 0.62, 0.77, 0.34, 0.06, 12,
           italic=True, color="#555555"),
    ]))
    s.append(Slide(title="Chemistry: Ti 2p XPS", objects=[
        SlidePicture(path=charts["xps"], x=0.03, y=0.18, w=0.56, h=0.66,
                     keep_aspect=True, locked=False),
        _t(_items("Doublet split 5.7\\,eV, area ratio 2:1",
                  "Ti$^{3+}$ shoulder at 457.1\\,eV",
                  "Shirley background, pseudo-Voigt"),
           0.61, 0.2, 0.36, 0.36, 13),
        _table([["", "Ti$^{4+}$", "Ti$^{3+}$"], ["air", "100\\,\\%", "—"],
                ["vacuum", "89\\,\\%", "11\\,\\%"]],
               0.62, 0.64, 0.34, 0.18, navy, 12),
    ]))
    s.append(Slide(title="Optical band gap", objects=[
        SlidePicture(path=charts["tauc"], x=0.04, y=0.18, w=0.48, h=0.66,
                     keep_aspect=True, locked=False),
        _t("Tauc relation (indirect gap, $n=2$):", 0.56, 0.22, 0.4, 0.06,
           14),
        _eq("(\\alpha h\\nu)^{1/n} = A\\,(h\\nu - E_g)", 0.55, 0.3, 0.42,
            0.12, 20),
        _t("Vacancies add states 0.8\\,eV below the conduction band "
           "→ visible absorption, grey-blue films.", 0.56, 0.52, 0.4,
           0.24, 13, block="alertblock", block_title="Observation"),
    ]))
    cards = []
    for i, (v, cap, col) in enumerate((("11\\,\\%", "Ti$^{3+}$ after "
                                        "vacuum", navy),
                                       ("3.22 eV", "band gap", blue),
                                       ("21 nm", "crystallites", teal))):
        cards += _card(0.08 + i * 0.3, 0.22, 0.24, 0.22, v, cap, col, 26)
    s.append(Slide(title="Conclusions", objects=cards + [
        _t(_items("Vacuum annealing creates Ti$^{3+}$ without a phase "
                  "change", "XPS quantifies it; XRD and UV–Vis confirm",
                  "Next: photocatalysis against vacancy density"),
           0.08, 0.52, 0.84, 0.32, 16),
        _t("Spectra fitted in KherveFitting  ·  slides in KherveSlide",
           0.1, 0.86, 0.8, 0.05, 10, align="center", color="#777777"),
    ]))
    deck = Deck(title="Oxygen vacancies in TiO2 thin films",
                author="A. Researcher", aspect="169", slides=s,
                page_number="of_total")
    return _themed(deck, _kit("Imperial-style navy", footer_style="bar"))


# ===================================================== 9. Kherve suite
_SUITE = [
    ("KherveTeX", "LaTeX, visually", "#003E74"),
    ("KherveFitting", "XPS peak fitting", "#C8102E"),
    ("KherveCAD", "3D parts, drawings", "#2E6B30"),
    ("KherveMol", "Molecules in 3D", "#00787A"),
    ("KherveSlide", "Beamer slides", "#5B2C83"),
]


def kherve_suite(assets: Path) -> Deck:
    charts = _science_charts(assets)
    ink = "#1A1A1A"
    s = [_title_slide("The Kherve suite",
                      "Open-source tools for writing, analysing, "
                      "designing and presenting science",
                      "github.com/gkerherve", "#003E74")]
    hub = [_shape("ellipse", 0.4, 0.42, 0.2, 0.2, "#F2C14E"),
           _label("your\\\\research", 0.4, 0.42, 0.2, 0.2, 14, color=ink)]
    spots = [(0.06, 0.2), (0.7, 0.2), (0.06, 0.66), (0.7, 0.66),
             (0.38, 0.75)]
    for (name, what, col), (x, y) in zip(_SUITE, spots):
        hub += [_shape("rounded_rect", x, y, 0.24, 0.14, col),
                _label(name, x, y + 0.005, 0.24, 0.08, 15),
                _label(what, x, y + 0.065, 0.24, 0.06, 10, bold=False)]
        cx, cy = x + 0.12, y + 0.07
        dy = 0.07 if cy < 0.5 else -0.07
        hub.insert(0, SlideLine(x=cx, y=cy + dy, w=0.5 - cx,
                                h=0.52 - cy - dy, color="#BBBBBB",
                                width_pt=1.5))
    s.append(Slide(title="One family of tools", objects=hub))
    for name, what, col in _SUITE[:4]:
        body = {
            "KherveTeX": (
                _items("Visual and source editing side by side",
                       "Equation, chemistry and drawing builders",
                       "Compiles with tectonic — no TeX install"),
                "\\[\\int_0^\\infty e^{-x^2}\\,dx = "
                "\\frac{\\sqrt{\\pi}}{2}\\]"),
            "KherveFitting": (
                _items("Shirley, Tougaard and linear backgrounds",
                       "Pseudo-Voigt and doublet components",
                       "Constraints, quantification, report tables"),
                None),
            "KherveCAD": (
                _items("Parametric parts from sketches",
                       "Assemblies and 2D drawings",
                       "Export for 3D printing and figures"),
                None),
            "KherveMol": (
                _items("Draw or import molecules",
                       "3D view, geometry optimisation",
                       "Figures straight into papers and slides"),
                "\\chemfig{*6(-=-(-OH)=-=)}"),
        }[name]
        objs = [_shape("rect", 0.0, 0.17, 0.012, 0.7, col),
                _t(what, 0.05, 0.2, 0.9, 0.07, 18, italic=True, color=col),
                _t(body[0], 0.05, 0.32, 0.5, 0.45, 16)]
        if name == "KherveFitting":
            objs.append(SlidePicture(path=charts["xps"], x=0.56, y=0.28,
                                     w=0.4, h=0.56, keep_aspect=True,
                                     locked=False))
        elif name == "KherveCAD":
            objs += [_shape("rect", 0.62, 0.4, 0.2, 0.3, "#E3EDE3",
                            border=col),
                     _shape("ellipse", 0.68, 0.48, 0.08, 0.14, "#FFFFFF",
                            border=col),
                     SlideLine(x=0.62, y=0.76, w=0.2, h=0.0, color=col,
                               width_pt=1.0, arrow_start=True,
                               arrow_end=True),
                     _t("40.0", 0.68, 0.77, 0.08, 0.05, 11, align="center",
                        color=col)]
        else:
            objs.append(_t(body[1], 0.58, 0.36, 0.38, 0.3, 22,
                           align="center"))
        s.append(Slide(title=name, objects=objs))
    s.append(Slide(title="A typical workflow", objects=[
        *[o for i, (name, _w, col) in enumerate(
            (_SUITE[3], _SUITE[1], _SUITE[0], _SUITE[4]))
          for o in (_shape("chevron", 0.04 + i * 0.23, 0.3, 0.24, 0.18,
                           col),
                    _label(name, 0.075 + i * 0.23, 0.3, 0.17, 0.18, 10))],
        _t(_items("Build the molecule, export a figure",
                  "Fit the spectra, export the table",
                  "Write the paper around both",
                  "Present it — same figures, same fonts", enum=True),
           0.12, 0.56, 0.76, 0.32, 15),
    ]))
    s.append(Slide(objects=[
        _t("Free and open source", 0.1, 0.34, 0.8, 0.12, 32,
           align="center", bold=True, color="#003E74"),
        _t("github.com/gkerherve", 0.1, 0.52, 0.8, 0.08, 18,
           align="center", color="#0091D4"),
    ]))
    deck = Deck(title="The Kherve suite", author="G. Kerherve",
                aspect="169", slides=s, page_number="number")
    return _themed(deck, _kit("Clean blue", footer_style="line"))


# ================================================= 10. KherveFitting tutorial
def fitting_tutorial(assets: Path) -> Deck:
    charts = _science_charts(assets)
    red, light = "#C8102E", "#FBE9EC"
    s = [_title_slide("Fitting XPS spectra with KherveFitting",
                      "From raw counts to a quantified table in five steps",
                      "Training session  ·  Surface Analysis Lab", red)]
    steps = ["Import", "Calibrate", "Background", "Components", "Report"]
    flow = []
    for i, name in enumerate(steps):
        x = 0.04 + i * 0.185
        flow += [_shape("chevron", x, 0.3, 0.2, 0.16,
                        red if i == 0 else "#E07A8A"),
                 _label(name, x + 0.03, 0.3, 0.14, 0.16, 12)]
    flow.append(_t(_items(".vms, .xlsx or Avantage exports",
                          "Charge-correct to adventitious C 1s = "
                          "284.8\\,eV", "Then fit region by region"),
                   0.1, 0.56, 0.8, 0.3, 16))
    s.append(Slide(title="The workflow", objects=flow))
    s.append(Slide(title="Backgrounds", objects=[
        _t("\\textbf{Shirley} — the background at $E$ grows with the "
           "peak area above it:", 0.05, 0.22, 0.9, 0.08, 15),
        _eq("B(E) = I_2 + (I_1 - I_2)\\,\\frac{\\int_E^{E_2} "
            "[I(E')-B(E')]\\,dE'}{\\int_{E_1}^{E_2}[I(E')-B(E')]\\,dE'}",
            0.05, 0.32, 0.9, 0.16, 20),
        _table([["Background", "Use for"],
                ["Linear", "Insulators, narrow windows"],
                ["Shirley", "Most core levels"],
                ["Tougaard", "Quantitative depth info"]],
               0.2, 0.55, 0.6, 0.3, red, 13, striped=True,
               stripe_color=light),
    ]))
    s.append(Slide(title="Line shapes", objects=[
        _t("Pseudo-Voigt: a Gaussian–Lorentzian mix", 0.05, 0.22, 0.9,
           0.06, 16),
        _eq("PV(x) = \\eta\\,L(x) + (1-\\eta)\\,G(x)", 0.05, 0.3, 0.9,
            0.12, 22),
        _t("Doublets", 0.06, 0.5, 0.4, 0.06, 16, bold=True, color=red),
        _t(_items("Fix the splitting (Ti 2p: 5.7\\,eV)",
                  "Fix the area ratio (p 1:2, d 2:3, f 3:4)",
                  "Link the widths"), 0.06, 0.57, 0.42, 0.3, 14),
        _t("Never fit more components than the chemistry allows.",
           0.54, 0.56, 0.4, 0.2, 14, block="alertblock",
           block_title="Rule of thumb"),
    ]))
    s.append(Slide(title="Result", objects=[
        SlidePicture(path=charts["xps"], x=0.03, y=0.18, w=0.56, h=0.66,
                     keep_aspect=True, locked=False),
        _table([["Peak", "BE (eV)", "FWHM", "At.\\,\\%"],
                ["Ti$^{4+}$ 2p$_{3/2}$", "458.6", "1.1", "29.4"],
                ["Ti$^{3+}$ 2p$_{3/2}$", "457.1", "1.3", "3.6"],
                ["O 1s lattice", "529.9", "1.2", "61.0"],
                ["C 1s", "284.8", "1.4", "6.0"]],
               0.6, 0.24, 0.37, 0.4, red, 11),
        _t("$\\chi^2_\\nu = 1.04$  ·  residuals flat", 0.6, 0.7, 0.37,
           0.06, 12, align="center", italic=True, color="#555555"),
    ]))
    s.append(Slide(title="Checklist", objects=[
        _t(_items("Energy scale calibrated?", "Background end points "
                  "on flat regions?", "Doublet constraints set?",
                  "FWHM physically sensible?", "Residuals without "
                  "structure?"), 0.1, 0.24, 0.8, 0.55, 18),
    ]))
    deck = Deck(title="Fitting XPS spectra with KherveFitting",
                author="Surface Analysis Lab", aspect="169", slides=s,
                page_number="of_total")
    return _themed(deck, _kit("Crimson", footer_style="line"))


# ============================================ 11. KherveMol & KherveCAD
def mol_and_cad(assets: Path) -> Deck:
    charts = _science_charts(assets)
    teal, green = "#00787A", "#2E6B30"
    s = [_title_slide("From molecule to model",
                      "Designing with KherveMol and KherveCAD",
                      "Lab meeting  ·  \\today", teal)]
    s.append(Slide(title="Draw it: KherveMol", objects=[
        _t("\\chemfig{*6(-=-(-COOH)=-(-OH)=)}", 0.04, 0.24, 0.4, 0.4,
           12, align="center"),
        _t("Salicylic acid", 0.04, 0.68, 0.44, 0.06, 13, align="center",
           italic=True, color="#555555"),
        _t(_items("Sketch in 2D, view in 3D",
                  "SMILES / MOL import",
                  "Bond lengths and angles on click"),
           0.56, 0.26, 0.4, 0.4, 16),
        _t("$\\ce{C7H6O3}$  ·  $M = 138.12$\\,g\\,mol$^{-1}$", 0.52,
           0.7, 0.44, 0.06, 14, color=teal),
    ]))
    s.append(Slide(title="Relax it: geometry optimisation", objects=[
        SlidePicture(path=charts["energy"], x=0.04, y=0.2, w=0.5, h=0.62,
                     keep_aspect=True, locked=False),
        _eq("\\mathbf{x}_{k+1} = \\mathbf{x}_k - \\mathbf{H}_k^{-1}"
            "\\nabla E(\\mathbf{x}_k)", 0.55, 0.26, 0.42, 0.12, 18),
        _t("Converged in 20 steps; the O–H$\\cdots$O hydrogen bond "
           "locks the conformer.", 0.57, 0.48, 0.38, 0.24, 13,
           block="exampleblock", block_title="Result"),
    ]))
    s.append(Slide(title="Build the hardware: KherveCAD", objects=[
        _shape("rect", 0.08, 0.3, 0.36, 0.36, "#E3EDE3", border=green),
        *[_shape("ellipse", 0.12 + c * 0.1, 0.38 + r * 0.14, 0.06, 0.1,
                 "#FFFFFF", border=green)
          for r in range(2) for c in range(3)],
        SlideLine(x=0.08, y=0.72, w=0.36, h=0.0, color=green,
                  width_pt=1.0, arrow_start=True, arrow_end=True),
        _t("60.0 mm", 0.18, 0.73, 0.16, 0.05, 11, align="center",
           color=green),
        _t("A six-well sample holder for the XPS stage", 0.08, 0.2, 0.4,
           0.06, 13, italic=True, color="#555555"),
        _t(_items("Sketch → extrude → pocket",
                  "Parameters: well size, pitch, depth",
                  "STL for printing, PDF drawing for the workshop"),
           0.52, 0.28, 0.44, 0.4, 16),
    ]))
    s.append(Slide(title="Parameters drive the design", objects=[
        _table([["Parameter", "Value", "Driven by"],
                ["Well diameter", "8.0 mm", "sample size"],
                ["Pitch", "12.0 mm", "diameter + 4"],
                ["Depth", "1.5 mm", "sample thickness"],
                ["Plate", "60 × 30 mm", "pitch × wells"]],
               0.12, 0.24, 0.76, 0.4, green, 14, striped=True,
               stripe_color="#E3EDE3"),
        _t("Change one number — the whole part follows.", 0.15, 0.72,
           0.7, 0.08, 16, align="center", bold=True, color=green),
    ]))
    s.append(Slide(objects=[
        _t("Molecule → measurement → model", 0.06, 0.36, 0.88, 0.14, 30,
           align="center", bold=True, color=teal),
        _t("KherveMol  ·  KherveFitting  ·  KherveCAD  ·  KherveSlide",
           0.1, 0.56, 0.8, 0.08, 15, align="center", color="#555555"),
    ]))
    deck = Deck(title="From molecule to model", author="Lab meeting",
                aspect="169", slides=s, page_number="number")
    return _themed(deck, _kit("Cambridge-style teal", footer_style="line"))


#: (name, description, factory(assets) -> Deck), in menu order.
EXAMPLES = [
    ("Research talk", "University-style theme with a logo bar, equations, "
     "chemistry, a chart, a table, a diagram and KPI cards", research_talk),
    ("Lecture", "Madrid theme: objectives, definition / theorem blocks, a "
     "worked example, a table of formulas and a quiz", lecture),
    ("Project update", "Timeline, KPI cards, progress chart, risk table and "
     "a process flow", project_update),
    ("Maths seminar", "Definition, theorem and proof blocks, a derivation "
     "step by step, and a geometric picture", maths_seminar),
    ("Diagrams & workflows", "Flowchart, Venn diagram, process arrows and a "
     "comparison table — all built from shapes", diagrams),
    ("Lightning talk (dark)", "Dark theme, big statements, a chart with "
     "headline numbers", lightning_talk),
    ("Project kick-off", "Gantt chart, RACI table, budget donut, "
     "governance tree and decisions", project_kickoff),
    ("Materials science talk", "TiO2 films: workflow, XRD, XPS fit, "
     "Tauc plot, Scherrer equation and conclusions", materials_talk),
    ("The Kherve suite", "KherveTeX, KherveFitting, KherveCAD, KherveMol "
     "and KherveSlide — one slide each and a workflow", kherve_suite),
    ("XPS fitting tutorial", "KherveFitting training: backgrounds, line "
     "shapes, doublets and a quantified result", fitting_tutorial),
    ("Molecule to model", "KherveMol and KherveCAD: chemfig structure, "
     "geometry optimisation, a parametric part", mol_and_cad),
]


def example_names() -> list[str]:
    return [name for name, _d, _f in EXAMPLES]


def build_example(name: str, assets: Path) -> Deck:
    for n, _desc, factory in EXAMPLES:
        if n == name:
            return factory(Path(assets))
    raise KeyError(name)
