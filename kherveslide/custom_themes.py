"""Saved custom themes + imported beamer ``.sty`` themes.

Two stores back the theme builder's "My themes" workflow:

1. **Saved themes** — the PowerPoint "save current theme" equivalent.
   Each theme is one JSON file (spec + base/colour theme + master slide)
   in a per-user ``slide_themes/`` folder, so themes built in one
   presentation can be reapplied to any other.

2. **Imported ``.sty`` themes** — real beamer theme files (e.g. from an
   Overleaf template or GitHub). ``import_sty`` copies them into the
   user styles folder that the compiler already exposes to tectonic via
   TEXINPUTS / workdir copies, making ``\\usetheme{<name>}`` work.

No Qt and no LaTeX here: JSON I/O only (LaTeX stays in serializer.py).
Every function takes an optional ``directory`` so tests can use a temp
folder; the default resolves next to the QSettings data dir, like
``style_manager``.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path

from .model import Slide, ThemeSpec, _build_slide, _build_theme_spec


def _default_dir() -> Path:
    from PySide6.QtCore import QSettings
    return (Path(QSettings("kherveDOC", "kherveDOC").fileName()).parent
            / "slide_themes")


def themes_dir(directory: Path | None = None) -> Path:
    d = Path(directory) if directory is not None else _default_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_stem(name: str) -> str:
    keep = "".join(c if (c.isalnum() or c in " -_") else "_" for c in name)
    return keep.strip() or "theme"


def save_theme(name: str, spec: ThemeSpec, master: Slide,
               base_theme: str = "default", color_theme: str = "",
               directory: Path | None = None, kit: dict | None = None) -> Path:
    """Persist a named theme (overwrites an existing theme of that name).
    *kit* is the theme wizard's simple description (ThemeKit.to_dict()),
    kept so the wizard reopens on the same choices."""
    payload = {
        "name": name,
        "base_theme": base_theme or "default",
        "color_theme": color_theme or "",
        "spec": asdict(spec),
        "master": asdict(master),
    }
    if kit:
        payload["kit"] = dict(kit)
    path = themes_dir(directory) / f"{_safe_stem(name)}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path


def load_themes(directory: Path | None = None) -> dict[str, dict]:
    """All saved themes, ``name -> {spec, master, base_theme, color_theme}``
    with the spec/master already rebuilt into model objects."""
    out: dict[str, dict] = {}
    d = themes_dir(directory)
    for p in sorted(d.glob("*.json")):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = str(raw.get("name") or p.stem)
        out[name] = {
            "base_theme": str(raw.get("base_theme", "default")),
            "color_theme": str(raw.get("color_theme", "")),
            "spec": _build_theme_spec(raw.get("spec", {})),
            "master": _build_slide(raw.get("master", {})),
            "kit": raw.get("kit") or None,
            "path": p,
        }
    return out


def delete_theme(name: str, directory: Path | None = None) -> bool:
    path = themes_dir(directory) / f"{_safe_stem(name)}.json"
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


# ---------------- imported beamer .sty themes ----------------

def _sty_dir(directory: Path | None = None) -> Path:
    if directory is not None:
        return Path(directory)
    from .style_manager import user_styles_dir
    return user_styles_dir()


def import_sty(src: Path, directory: Path | None = None) -> str:
    """Copy a beamer theme ``.sty`` into the user styles folder and return
    the theme name to pass to ``\\usetheme``. A ``beamertheme<X>.sty``
    file yields ``X``; any other ``.sty`` is copied as a support file and
    returns ""."""
    src = Path(src)
    dest_dir = _sty_dir(directory)
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / src.name)
    stem = src.stem
    if stem.lower().startswith("beamertheme"):
        return stem[len("beamertheme"):]
    return ""


def installed_sty_themes(directory: Path | None = None) -> list[str]:
    """Theme names of every user-imported ``beamertheme*.sty``."""
    d = _sty_dir(directory)
    if not d.is_dir():
        return []
    return sorted(p.stem[len("beamertheme"):] for p in d.glob("*.sty")
                  if p.stem.lower().startswith("beamertheme")
                  and len(p.stem) > len("beamertheme"))
