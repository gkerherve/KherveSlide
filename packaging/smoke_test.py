"""Smoke-test a frozen KherveSlide: is everything inside, and does it start?

    python packaging/smoke_test.py dist/KherveSlide/KherveSlide.exe
    python packaging/smoke_test.py dist/KherveSlide.app/Contents/MacOS/KherveSlide

A freeze fails quietly: a module PyInstaller's analysis missed is only found
when the code that imports it runs. This checks that

* the stamped VERSION is bundled and matches ``--version`` if given;
* the bundled tectonic runs (without it no slide ever compiles);
* the user guide, example media and theme previews are inside;
* on first launch the app copies its bundled LaTeX packages into an
  EMPTY tectonic cache, and a beamer slide then compiles from that cache
  alone (``--only-cached``: no network) — a fresh install works offline;
* the real executable starts on Qt's offscreen platform and is still
  running after ``--wait`` seconds (an import error kills it at once).

Exits non-zero on the first failure.

Copyright (C) 2026 Gwilherm Kerherve
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _fail(message: str):
    print(f"SMOKE TEST FAILED: {message}", flush=True)
    raise SystemExit(1)


def _internal(exe: Path) -> Path:
    """Where PyInstaller put the bundled files (sys._MEIPASS)."""
    if exe.parent.name == "MacOS":                       # .app/Contents/MacOS
        return exe.parent.parent / "Frameworks"
    return exe.parent / "_internal"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("exe", help="the frozen executable")
    parser.add_argument("--version", help="the <major>.<minor>.N it must carry")
    parser.add_argument("--wait", type=int, default=25,
                        help="seconds the app must stay up (default 25)")
    args = parser.parse_args()

    exe = Path(args.exe).resolve()
    if not exe.is_file():
        _fail(f"{exe} not found")
    root = _internal(exe)

    stamped = root / "kherveslide" / "VERSION"
    if not stamped.is_file():
        _fail("kherveslide/VERSION was not bundled")
    version = stamped.read_text(encoding="ascii").strip()
    print(f"version: {version}", flush=True)
    if args.version and version.split("+")[0] != args.version:
        _fail(f"expected version {args.version}, the bundle carries {version}")

    for rel in ("docs/USER_GUIDE.md", "kherveslide/example_media",
                "kherveslide/theme_previews", "kherveslide/theme_previews_generated",
                "kherveslide/tectonic_cache"):
        if not (root / rel).exists():
            _fail(f"{rel} missing from the bundle")

    tectonic = root / ("tectonic.exe" if sys.platform == "win32" else "tectonic")
    if not tectonic.is_file():
        _fail(f"{tectonic.name} missing from the bundle")
    out = subprocess.run([str(tectonic), "--version"], capture_output=True,
                         text=True, timeout=60)
    if out.returncode != 0:
        _fail(f"bundled tectonic does not run: {out.stderr.strip()[-300:]}")
    print(f"bundled {out.stdout.strip()}", flush=True)

    work = Path(tempfile.mkdtemp(prefix="kslide_smoke_"))
    cache = work / "tectonic-cache"          # empty: a brand-new machine
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", TMPDIR=str(work),
               TECTONIC_CACHE_DIR=str(cache))
    log = open(work / "app.log", "w+")
    app = subprocess.Popen([str(exe)], env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + args.wait
        while time.time() < deadline:
            if app.poll() is not None:
                log.seek(0)
                _fail(f"the app exited with code {app.returncode} after start-up:\n"
                      + log.read()[-3000:])
            time.sleep(1)
        print(f"the app is still running after {args.wait} s", flush=True)
        files = [p for p in cache.rglob("*") if p.is_file()] if cache.is_dir() else []
        if len(files) < 50:
            _fail(f"the app did not seed the empty tectonic cache ({len(files)} files)")
        print(f"seeded the empty cache with {len(files)} files", flush=True)
        doc = work / "slide"
        doc.mkdir()
        # What the app itself writes: two example presentations (themes,
        # blocks, equations, charts) from the app's own serializer.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from kherveslide.examples import build_example
        from kherveslide.serializer import serialize_deck
        tex = {name.split()[0].lower(): serialize_deck(
                   build_example(name, work / "assets"))
               for name in ("Lecture", "Materials science talk")}
        for name, source in tex.items():
            (doc / f"{name}.tex").write_text(source, encoding="utf-8")
            out = subprocess.run([str(tectonic), "--only-cached", f"{name}.tex"],
                                 cwd=doc, env=env, capture_output=True, text=True,
                                 timeout=300)
            if out.returncode != 0 or not (doc / f"{name}.pdf").is_file():
                _fail(f"the {name} presentation does not compile offline from "
                      "the seeded cache:\n" + (out.stdout + out.stderr)[-2000:])
        print("two example presentations compile offline from the seeded cache", flush=True)
    finally:
        app.terminate()
        try:
            app.wait(timeout=15)
        except subprocess.TimeoutExpired:
            app.kill()
    print("SMOKE TEST PASSED", flush=True)


if __name__ == "__main__":
    main()
