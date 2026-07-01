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

_PKGS = (
    "\\usepackage{lmodern}"
    "\\usepackage[absolute,overlay]{textpos}"
    "\\usepackage{graphicx}\\usepackage{tikz}\\usetikzlibrary{arrows.meta}"
    "\\usepackage{colortbl}\\usepackage{geometry}")
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


def download_offline(on_output=None) -> bool:
    """Compile a representative doc for every theme/colour/package combo so
    tectonic caches them. Returns True if all compiled (or already cached)."""
    if not tectonic_available():
        return False
    # Already warmed? Then there's nothing to fetch — detect it up front so we
    # don't re-cache everything on each launch / click.
    if packages_cached():
        if on_output:
            on_output("Offline packages already cached — nothing to download.")
        return True
    wd = Path(tempfile.gettempdir()) / "kherveslide_warm"
    docs = _documents()
    n = len(docs)
    ok = True
    for i, (name, tex) in enumerate(docs, 1):
        if on_output:
            on_output(f"[{i}/{n}] caching {name}…")
        result = compile_tex(tex, wd, "warm")
        if not result.ok:
            ok = False
    if on_output:
        on_output("Offline cache ready — compiling now works without internet."
                  if ok else
                  "Some packages could not be cached (check your connection).")
    return ok
