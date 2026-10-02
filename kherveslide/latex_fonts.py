"""Load beamer's own typefaces (Latin Modern) for the WYSIWYG canvas.

beamer sets slides in Latin Modern Sans (the deck loads ``lmodern``), with
Latin Modern Roman for serif text and Latin Modern Mono for typewriter.
With the real faces on screen, the canvas text has the same shapes and
widths as the PDF, so lines break where they will in the compiled slide.

The OpenType files come from tectonic's cache (any compile fills it, and
the offline warm-up downloads them), so nothing extra is bundled. Until
they are there the canvas falls back to its Calibri-like stack; call
:func:`ensure_loaded` again after a compile to pick them up. Same approach
as KherveTeX's ``latex_fonts``.
"""
from __future__ import annotations

import sys
from pathlib import Path

SANS = "Latin Modern Sans"
ROMAN = "Latin Modern Roman"
MONO = "Latin Modern Mono"

# (file stem, styles) — the 10pt design size, beamer's default body cut.
_FILES = (
    ("lmsans10", ("regular", "bold", "oblique", "boldoblique")),
    ("lmroman10", ("regular", "bold", "italic", "bolditalic")),
    ("lmmono10", ("regular", "italic")),
)

_loaded = False
_font_dir: Path | None | bool = False   # False = not looked up yet
_roots: list[Path] | None = None        # asked tectonic once, then reused


def _candidate_roots() -> list[Path]:
    global _roots
    if _roots is not None:
        return _roots
    roots: list[Path] = []
    try:
        from .compiler import _tectonic_cache_dir
        d = _tectonic_cache_dir()
        if d is not None:
            roots.append(Path(d))
    except Exception:
        pass
    home = Path.home()
    if sys.platform == "darwin":
        roots.append(home / "Library" / "Caches"
                     / "TectonicProject.Tectonic" / "bundles")
    elif sys.platform == "win32":
        roots.append(home / "AppData" / "Local" / "TectonicProject"
                     / "Tectonic" / "bundles")
    else:
        roots.append(home / ".cache" / "Tectonic" / "bundles")
    _roots = roots
    return roots


def find_font_dir(roots: list[Path] | None = None) -> Path | None:
    """The cache folder holding ``lmsans10-regular.otf``, or None."""
    for root in roots if roots is not None else _candidate_roots():
        hits = sorted(Path(root).glob("data/*/lmsans10-regular.otf"))
        if hits:
            return hits[0].parent
    return None


def ensure_loaded() -> bool:
    """Register the Latin Modern faces with Qt. Cheap after the first
    success; returns False while the fonts aren't in the cache yet."""
    global _loaded, _font_dir
    if _loaded:
        return True
    if _font_dir is False or _font_dir is None:
        _font_dir = find_font_dir()
    if _font_dir is None:
        return False
    from PySide6.QtGui import QFontDatabase
    ok = False
    for stem, styles in _FILES:
        for style in styles:
            f = _font_dir / f"{stem}-{style}.otf"
            if f.exists() and QFontDatabase.addApplicationFont(str(f)) >= 0:
                ok = True
    _loaded = ok
    return ok


def available() -> bool:
    return _loaded
