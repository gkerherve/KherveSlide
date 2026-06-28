"""Manage bundled and user-installed LaTeX style files (.cls / .sty).

Two directories are searched (in order) when the compiler builds TEXINPUTS:

  1. **Bundled styles** — ``khervedoc/styles/`` inside the package.
     Ships with the app and is read-only from the user's perspective.

  2. **User styles** — a ``styles/`` folder next to the QSettings data
     directory (platform-dependent). Users can copy files here via the
     GUI ("Manage styles…") or by dropping files into the folder manually.

Both directories are added to TEXINPUTS so tectonic (or any TeX engine)
finds .cls and .sty files in them automatically.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QSettings


def bundled_styles_dir() -> Path:
    """Directory of .cls/.sty files shipped with KherveTeX."""
    return Path(__file__).resolve().parent / "styles"


def user_styles_dir() -> Path:
    """Per-user directory for additional .cls/.sty files.
    Created on first access."""
    d = Path(QSettings("kherveDOC", "kherveDOC").fileName()).parent / "styles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def all_style_dirs() -> list[Path]:
    """Return [user_styles_dir, bundled_styles_dir] — user dir first
    so user-supplied files take precedence over bundled ones."""
    dirs = []
    usd = user_styles_dir()
    if usd.is_dir():
        dirs.append(usd)
    bsd = bundled_styles_dir()
    if bsd.is_dir():
        dirs.append(bsd)
    return dirs


def list_styles(directory: Path) -> list[dict]:
    """List .cls and .sty files in *directory*.

    Each entry is a dict with:
      - name:     filename (e.g. 'elsarticle.cls')
      - path:     absolute Path
      - ext:      '.cls' or '.sty'
      - stem:     name without extension
    """
    out: list[dict] = []
    if not directory.is_dir():
        return out
    for p in sorted(directory.iterdir()):
        if p.suffix.lower() in (".cls", ".sty", ".bst"):
            out.append({
                "name": p.name,
                "path": p,
                "ext": p.suffix.lower(),
                "stem": p.stem,
            })
    return out


def import_style(src: Path, user: bool = True) -> Path:
    """Copy a .cls/.sty/.bst file into the user (or bundled) styles dir.

    Returns the destination Path. Overwrites if a file with the same
    name already exists."""
    dest_dir = user_styles_dir() if user else bundled_styles_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest


def remove_style(path: Path) -> bool:
    """Delete a style file. Returns True on success."""
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False
