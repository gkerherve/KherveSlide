"""One-shot Windows build: frozen app + installer + portable zip.

Run from anywhere on Windows, with the interpreter that has PyInstaller:

    python packaging/build_installer.py                 # everything
    python packaging/build_installer.py --skip-freeze   # reuse dist/KherveSlide

Produces, in ``dist/``:

* ``KherveSlide-Setup-<version>.exe``    — per-user Inno Setup installer
* ``KherveSlide-<version>-portable.zip`` — the same folder, extract and run
* ``KherveSlide-Setup.exe``              — stable-name copy; the website links
                                           to it by filename through the GitHub
                                           "latest release" URL, so it must
                                           exist on every release

The steps, in order:

1. Stamp ``kherveslide/VERSION`` from git. A frozen build has no ``.git`` and
   would otherwise report the bare ``__version__``.
2. Freeze with ``KherveSlide.spec`` (one folder, ``dist/KherveSlide``).
3. Zip the folder; the zip's root is ``KherveSlide/`` so it extracts in place.
4. Compile ``packaging/KherveSlide.iss`` with Inno Setup 6, then copy the
   stable name.

The macOS counterpart is ``build_macos.py``. Both take their version from
``spec_common.git_version``, so a Windows and a macOS build of the
same commit carry the same ``<major>.<minor>.<n>``.

Copyright (C) 2026 Gwilherm Kerherve
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent           # packaging/
_ROOT = _HERE.parent                              # project root
_DIST = _ROOT / "dist"
_APP = "KherveSlide"
_SPEC = _ROOT / "KherveSlide.spec"


def _find_iscc() -> Path:
    """Inno Setup's compiler: KHERVESLIDE_ISCC, else the per-user install,
    else the machine-wide one (where GitHub's Windows runners have it)."""
    if os.environ.get("KHERVESLIDE_ISCC"):
        return Path(os.environ["KHERVESLIDE_ISCC"])
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ]
    found = next((c for c in candidates if c.is_file()), None)
    if found is None and shutil.which("iscc"):
        found = Path(shutil.which("iscc"))
    return found or candidates[0]


def _run(cmd, **kwargs):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def stamp_version() -> str:
    """Write ``kherveslide/VERSION`` from git and return ``0.158.N`` (no
    sha: safe in file names, Inno and Info.plist). Rewritten on every
    build; refuses a shallow clone, which would give the wrong count."""
    sys.path.insert(0, str(_HERE))
    import spec_common
    full, short = spec_common.stamp_version()
    print(f"{_APP} {full}", flush=True)
    return short


def freeze() -> None:
    _run([sys.executable, "-m", "PyInstaller", _SPEC, "--noconfirm"], cwd=_ROOT)


def build_zip(version: str) -> Path:
    out = _DIST / f"{_APP}-{version}-portable.zip"
    out.unlink(missing_ok=True)
    root = _DIST / _APP
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                # zip root is the app folder, so it extracts as KherveSlide/
                archive.write(path, Path(_APP) / path.relative_to(root))
    return out


def build_installer(version: str) -> Path:
    iscc = _find_iscc()
    if not iscc.is_file():
        raise SystemExit(f"Inno Setup not found at {iscc} "
                         "(https://jrsoftware.org/isinfo.php, or KHERVESLIDE_ISCC)")
    icon = _ROOT / "build" / f"{_APP}.ico"           # rendered by the spec
    if not icon.is_file():
        raise SystemExit(f"{icon} missing — the spec renders it from the app's own mark")
    _run([iscc,
          f"/DAPP_VERSION={version}",
          f"/DSRC_DIR={_DIST / _APP}",
          f"/DOUT_DIR={_DIST}",
          f"/DICON_FILE={icon}",
          _HERE / "KherveSlide.iss"])
    out = _DIST / f"{_APP}-Setup-{version}.exe"
    if not out.is_file():
        raise SystemExit(f"installer not produced: {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-freeze", action="store_true",
                        help="reuse the existing dist/KherveSlide folder")
    args = parser.parse_args()

    if sys.platform != "win32":
        raise SystemExit("build_installer.py only runs on Windows "
                         "(PyInstaller cannot cross-compile; macOS is build_macos.py)")
    version = stamp_version()
    if not args.skip_freeze:
        freeze()
    if not (_DIST / _APP / f"{_APP}.exe").is_file():
        raise SystemExit(f"{_DIST / _APP / (_APP + '.exe')} not found — did the freeze run?")

    zip_path = build_zip(version)
    exe_path = build_installer(version)
    stable = _DIST / f"{_APP}-Setup.exe"
    shutil.copy2(exe_path, stable)

    print()
    for path in (exe_path, zip_path, stable):
        print(f"{path.name:<40} {path.stat().st_size / 1e6:>7.1f} MB")


if __name__ == "__main__":
    main()
