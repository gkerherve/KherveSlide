"""A theme described the simple way — the theme wizard's model.

Instead of beamer's dozens of colour slots, sub-themes and templates, a
:class:`ThemeKit` holds what a person thinks about when copying a
university template (Imperial, UCL, Oxford…): its main colour, an accent,
text and background colours, what the frame title looks like, what runs
along the bottom, a logo in one corner and a typeface. ``to_theme`` turns
it into the app's real theme (base theme + :class:`ThemeSpec` + master
slide), so the wizard, the PowerPoint / picture importers and the MCP
server all build themes through this one function.

No Qt and no LaTeX here (LaTeX stays in serializer.py).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .model import Slide, ThemeSpec

TITLE_STYLES = {
    "bar": "Coloured bar across the top",
    "plain": "Coloured title, no bar",
    "underline": "Title with a line under it",
}
FOOTER_STYLES = {
    "bar": "Coloured bar: author · title · slide number",
    "line": "A thin coloured line",
    "none": "Nothing",
}
LOGO_CORNERS = {
    "tr": "Top right", "tl": "Top left",
    "br": "Bottom right", "bl": "Bottom left",
}
BULLET_STYLES = {
    "": "Theme default (triangle)", "ball": "Ball", "circle": "Circle",
    "square": "Square", "triangle": "Triangle",
}


@dataclass
class ThemeKit:
    name: str = "My theme"
    primary: str = "#1F4E79"      # title bar, footer bar, bullets, structure
    accent: str = ""              # lines / rules ("" = primary)
    text: str = "#212121"
    background: str = "#FFFFFF"
    title_text: str = "#FFFFFF"   # text on the title / footer bar
    title_style: str = "bar"
    footer_style: str = "bar"
    logo: str = ""                # image file ("" = no logo)
    logo_corner: str = "tr"
    logo_size: float = 0.12       # logo height as a fraction of the slide
    font: str = ""                # serializer.FONT_FAMILIES key, "" = LM Sans
    bullets: str = ""

    # ---- conversion ----
    def to_spec(self) -> ThemeSpec:
        accent = self.accent or self.primary
        bar = self.title_style == "bar"
        return ThemeSpec(
            enabled=True,
            structure=self.primary,
            text_fg=self.text,
            canvas_bg=self.background if self.background.upper() != "#FFFFFF"
            else "",
            title_fg=self.title_text if bar else self.primary,
            title_bg=self.primary if bar else "",
            block_bg=_tint(self.primary, 0.82),
            font_family=self.font,
            bullets=self.bullets,
            title_rule=self.title_style == "underline",
            footline_rule=self.footer_style == "line",
            rule_color=accent,
            rule_width=1.5,
            footer_bar=self.footer_style == "bar",
            logo=self.logo,
            logo_corner=self.logo_corner,
            logo_size=self.logo_size,
        )

    def to_theme(self, master: Slide | None = None) -> dict:
        """{"base_theme", "color_theme", "spec", "master"} ready for the
        deck. The master slide is passed through untouched (the logo is
        part of the theme itself, drawn above the title bar)."""
        return {"base_theme": "default", "color_theme": "",
                "spec": self.to_spec(),
                "master": master if master is not None else Slide()}

    # ---- persistence ----
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ThemeKit":
        names = {f.name for f in fields(cls)}
        kit = cls(**{k: v for k, v in (d or {}).items() if k in names})
        kit.logo_size = float(kit.logo_size)
        return kit


def kit_from_theme(spec: ThemeSpec, name: str = "My theme") -> ThemeKit:
    """Best-effort reverse of ThemeKit.to_spec, so the wizard can open on
    the presentation's current custom theme."""
    kit = ThemeKit(name=name)
    if spec is None or not spec.enabled:
        return kit
    kit.primary = spec.title_bg or spec.structure or kit.primary
    kit.accent = spec.rule_color if spec.rule_color != kit.primary else ""
    kit.text = spec.text_fg or kit.text
    kit.background = spec.canvas_bg or "#FFFFFF"
    if spec.title_bg:
        kit.title_style = "bar"
        kit.title_text = spec.title_fg or "#FFFFFF"
    elif spec.title_rule:
        kit.title_style = "underline"
    else:
        kit.title_style = "plain"
    kit.footer_style = ("bar" if spec.footer_bar else
                        "line" if spec.footline_rule else "none")
    kit.font = spec.font_family
    kit.bullets = spec.bullets
    kit.logo = spec.logo
    kit.logo_corner = spec.logo_corner or "tr"
    kit.logo_size = spec.logo_size or 0.12
    return kit


# ---- presets: a starting point, recoloured to taste ----

def presets() -> list[ThemeKit]:
    """Ready-made starting points. The university ones only borrow the
    institution's published main colour — bring your own logo."""
    return [
        ThemeKit("Clean blue", primary="#1F4E79"),
        ThemeKit("Imperial-style navy", primary="#003E74", accent="#0091D4",
                 footer_style="line", logo_corner="tr"),
        ThemeKit("UCL-style purple", primary="#500778", accent="#AC145A",
                 title_style="underline", footer_style="line",
                 logo_corner="tr"),
        ThemeKit("Oxford-style blue", primary="#002147", accent="#A79D96",
                 logo_corner="tr"),
        ThemeKit("Cambridge-style teal", primary="#0E7D7D",
                 accent="#85B09A", title_style="plain"),
        ThemeKit("Edinburgh-style", primary="#041E42", accent="#C8102E",
                 footer_style="line"),
        ThemeKit("Forest green", primary="#2E6B30", footer_style="line"),
        ThemeKit("Crimson", primary="#9E1B32"),
        ThemeKit("Minimal black & white", primary="#000000",
                 title_style="underline", footer_style="none"),
        ThemeKit("Dark", primary="#7FB2FF", text="#E6EAF2",
                 background="#1B2233", title_text="#0B1020",
                 footer_style="line"),
    ]


def _tint(hex_color: str, amount: float) -> str:
    """Mix *hex_color* with white (amount 0 = colour, 1 = white)."""
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return ""
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return ""
    mix = [round(c + (255 - c) * amount) for c in (r, g, b)]
    return "#" + "".join(f"{c:02X}" for c in mix)


def contrast_text(hex_color: str) -> str:
    """Black or white, whichever reads better on *hex_color*."""
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return "#FFFFFF"
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#000000" if lum > 0.55 else "#FFFFFF"


def logo_exists(kit: ThemeKit) -> bool:
    return bool(kit.logo) and Path(kit.logo).exists()
