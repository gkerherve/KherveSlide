"""Pre-cache exactly what KherveSlide compiles, for fast offline use.

KherveTeX's generic bundle download doesn't cache the beamer themes,
textpos, tikz or colortbl that KherveSlide emits, so the first real
compile still hit the network. This warms the tectonic cache with a
beamer document per theme / colour theme plus all the packages, so once
it's run online every later compile is fully offline.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from .compiler import compile_tex, tectonic_available

_THEMES = [
    "default", "AnnArbor", "Antibes", "Bergen", "Berkeley", "Berlin",
    "Boadilla", "CambridgeUS", "Copenhagen", "Darmstadt", "Dresden",
    "Frankfurt", "Goettingen", "Hannover", "Ilmenau", "JuanLesPins",
    "Luebeck", "Madrid", "Malmoe", "Marburg", "Montpellier", "PaloAlto",
    "Pittsburgh", "Rochester", "Singapore", "Szeged", "Warsaw",
    "metropolis", "Auriga", "Trigon", "sintef",
]
_COLOUR = ["default", "albatross", "beaver", "beetle", "crane", "dolphin",
           "dove", "fly", "lily", "monarca", "orchid", "rose", "seagull",
           "seahorse", "spruce", "structure", "whale", "wolverine"]

# Every package / tikz library the serializer can emit, so warming caches
# them all (a deck using cropped images, shadows or tables then needs no net).
_PKGS = (
    "\\usepackage{lmodern}"
    "\\usepackage[absolute,overlay]{textpos}"
    "\\usepackage{graphicx}\\usepackage{tikz}"
    "\\usetikzlibrary{arrows.meta}\\usetikzlibrary{shadows}"
    "\\usepackage{adjustbox}\\usepackage{colortbl}\\usepackage{geometry}")
_BODY = ("\\begin{document}\\begin{frame}{T}Hi "
         "\\begin{itemize}\\item a\\end{itemize}\\end{frame}\\end{document}")


def _documents() -> list[tuple[str, str]]:
    docs = [("packages",
             "\\documentclass[aspectratio=169]{beamer}" + _PKGS
             + "\\geometry{papersize={20cm,12cm}}" + _BODY)]
    for t in _THEMES:
        docs.append((f"theme {t}",
                     f"\\documentclass{{beamer}}\\usetheme{{{t}}}" + _PKGS + _BODY))
    for c in _COLOUR:
        docs.append((f"colours {c}",
                     f"\\documentclass{{beamer}}\\usecolortheme{{{c}}}"
                     + _PKGS + _BODY))
    # The theme builder's typefaces (serializer.FONT_FAMILIES) are extra
    # CTAN packages — warm them too so a themed deck compiles offline.
    from .serializer import FONT_FAMILIES
    for key, (_label, pkg_lines) in FONT_FAMILIES.items():
        docs.append((f"font {key}",
                     "\\documentclass{beamer}" + _PKGS + "".join(pkg_lines)
                     + _BODY))
    return docs


def packages_cached() -> bool:
    """True when tectonic can compile a representative KherveSlide document
    from its LOCAL CACHE alone (``--only-cached``, no network).

    Lets the app notice an already-warmed cache — packages fetched on an
    earlier run, or by the sister app / another install sharing tectonic's
    cache — instead of relying solely on a per-machine settings flag (which is
    why a prior download "wasn't seen"). The tectonic cache persists on disk,
    so once warm it stays warm."""
    if not tectonic_available():
        return False
    wd = Path(tempfile.gettempdir()) / "kherveslide_cachecheck"
    tex = ("\\documentclass[aspectratio=169]{beamer}" + _PKGS
           + "\\geometry{papersize={20cm,12cm}}" + _BODY)
    return compile_tex(tex, wd, "probe", only_cached=True).ok


def download_offline(on_output=None, force=False) -> bool:
    """Warm tectonic's cache with a beamer doc for the core packages and every
    theme / colour theme, so later compiles are fully offline.

    Each doc that already compiles from the cache alone is skipped (a fast
    ``--only-cached`` probe), so this is idempotent and only fetches what's
    genuinely missing — it no longer bails out just because the *core* packages
    are cached (which left every theme un-warmed and still hitting the net).
    Pass ``force=True`` to re-warm everything regardless."""
    if not tectonic_available():
        return False
    wd = Path(tempfile.gettempdir()) / "kherveslide_warm"
    docs = _documents()
    n = len(docs)
    ok = True
    fetched = 0
    for i, (name, tex) in enumerate(docs, 1):
        # Skip docs already fully cached so we don't re-download them.
        if not force and compile_tex(tex, wd / "probe", "p", only_cached=True).ok:
            if on_output:
                on_output(f"[{i}/{n}] {name}: already cached")
            continue
        if on_output:
            on_output(f"[{i}/{n}] caching {name}…")
        if compile_tex(tex, wd, "warm").ok:
            fetched += 1
        else:
            ok = False
    if on_output:
        if ok and fetched == 0:
            on_output("Offline cache already complete — nothing to download.")
        elif ok:
            on_output(f"Offline cache ready ({fetched} newly cached) — "
                      "compiling now works without internet.")
        else:
            on_output("Some packages could not be cached (check your "
                      "connection) — the rest are ready for offline use.")
    return ok
