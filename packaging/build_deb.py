"""One-shot Linux build: frozen app + a Debian package (.deb).

Run on Linux with the interpreter that has PyInstaller:

    python packaging/build_deb.py                 # this machine's architecture
    python packaging/build_deb.py --skip-freeze   # reuse dist/KherveSlide

Produces, in ``dist/``:

* ``KherveSlide_<version>_amd64.deb`` on x86_64 (Debian, Ubuntu, Mint...)
* ``KherveSlide_<version>_arm64.deb`` on aarch64 (64-bit Raspberry Pi OS,
  Debian / Ubuntu on ARM)
* ``KherveSlide-linux-<arch>.deb`` — stable-name copy for "latest" links

Install with ``sudo apt install ./KherveSlide_<version>_<arch>.deb``; apt
pulls in the Qt runtime libraries listed in Depends. The package puts the
one-folder build in /opt/kherveslide, a ``kherveslide`` command in
/usr/bin, a menu entry, the icon, and the .kslide file type.

Like the Windows and macOS builds it bundles tectonic (the static musl
release) and the warmed LaTeX package cache, so slides compile offline
from the first launch. PyInstaller cannot cross-compile: the arm64
package comes from an arm64 machine (GitHub's ubuntu-22.04-arm runner,
or a Raspberry Pi 4/5 itself).

Copyright (C) 2026 Gwilherm Kerherve
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent           # packaging/
_ROOT = _HERE.parent
_DIST = _ROOT / "dist"
_APP = "KherveSlide"
_PKG = "kherveslide"
_SPEC = _ROOT / "KherveSlide.spec"                 # one-folder; no Windows bits on Linux

# Runtime libraries a PySide6 (Qt 6) app needs from the system on X11 and
# Wayland. PyInstaller bundles Qt itself, not these. Names exist on
# Debian 12, Ubuntu 22.04+ and Raspberry Pi OS (bookworm).
_DEPENDS = [
    "libc6 (>= 2.35)", "libgl1", "libegl1", "libfontconfig1", "libfreetype6",
    "libdbus-1-3", "libxkbcommon0", "libxkbcommon-x11-0", "libx11-xcb1",
    "libxcb-cursor0", "libxcb-icccm4", "libxcb-image0", "libxcb-keysyms1",
    "libxcb-randr0", "libxcb-render-util0", "libxcb-shape0", "libxcb-xinerama0",
    "libxcb-xkb1", "libwayland-client0", "libwayland-cursor0", "libwayland-egl1",
    "libnss3", "libasound2 | libasound2t64",
]


def _run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def deb_arch() -> str:
    m = platform.machine()
    return {"x86_64": "amd64", "amd64": "amd64",
            "aarch64": "arm64", "arm64": "arm64"}.get(m) or sys.exit(
        f"unsupported architecture {m!r}")


def stamp_version() -> str:
    sys.path.insert(0, str(_HERE))
    import spec_common
    full, short = spec_common.stamp_version()
    print(f"{_APP} {full}", flush=True)
    return short


def _icon_png(size: int) -> bytes:
    sys.path.insert(0, str(_HERE))
    from make_icons import _ensure_qt, _png_bytes
    _app = _ensure_qt()  # noqa: F841 — keeps the QGuiApplication alive
    return _png_bytes(size)


def build_deb(version: str, arch: str) -> Path:
    stage = _ROOT / "build" / "deb" / f"{_PKG}_{version}_{arch}"
    shutil.rmtree(stage, ignore_errors=True)
    opt = stage / "opt" / _PKG
    shutil.copytree(_DIST / _APP, opt, symlinks=True)

    (stage / "usr" / "bin").mkdir(parents=True)
    os.symlink(f"/opt/{_PKG}/{_APP}", stage / "usr" / "bin" / _PKG)

    for size in (48, 128, 256, 512):
        d = stage / "usr/share/icons/hicolor" / f"{size}x{size}" / "apps"
        d.mkdir(parents=True)
        (d / f"{_PKG}.png").write_bytes(_icon_png(size))

    apps = stage / "usr/share/applications"
    apps.mkdir(parents=True)
    (apps / f"{_PKG}.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={_APP}\n"
        "GenericName=Slide designer\n"
        "Comment=WYSIWYG slide designer that produces Beamer LaTeX\n"
        f"Exec={_PKG} %f\n"
        f"Icon={_PKG}\n"
        "Terminal=false\n"
        "Categories=Office;Presentation;Education;\n"
        "MimeType=application/x-kslide;\n"
        f"StartupWMClass={_APP}\n", encoding="utf-8")

    mime = stage / "usr/share/mime/packages"
    mime.mkdir(parents=True)
    (mime / f"{_PKG}.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">\n'
        '  <mime-type type="application/x-kslide">\n'
        "    <comment>KherveSlide presentation</comment>\n"
        '    <glob pattern="*.kslide"/>\n'
        "  </mime-type>\n"
        "</mime-info>\n", encoding="utf-8")

    debian = stage / "DEBIAN"
    debian.mkdir()
    size_kb = sum(p.stat().st_size for p in stage.rglob("*")
                  if p.is_file() and not p.is_symlink()) // 1024
    (debian / "control").write_text(
        f"Package: {_PKG}\n"
        f"Version: {version}\n"
        f"Architecture: {arch}\n"
        "Maintainer: Gwilherm Kerherve <gwilherm.kerherve@gmail.com>\n"
        f"Installed-Size: {size_kb}\n"
        f"Depends: {', '.join(_DEPENDS)}\n"
        "Section: editors\n"
        "Priority: optional\n"
        "Homepage: https://khervetools.com/tools/kherveslide\n"
        "Description: WYSIWYG slide designer that produces Beamer LaTeX\n"
        " Drag, resize and stack text and picture boxes on a slide; the\n"
        " generated Beamer LaTeX and the compiled PDF stay live as you edit.\n"
        " Ships the tectonic engine and its LaTeX packages, so slides\n"
        " compile offline from the first launch.\n", encoding="utf-8")
    for name in ("postinst", "postrm"):
        script = debian / name
        script.write_text(
            "#!/bin/sh\nset -e\n"
            "command -v update-desktop-database >/dev/null 2>&1 && "
            "update-desktop-database -q /usr/share/applications || true\n"
            "command -v update-mime-database >/dev/null 2>&1 && "
            "update-mime-database /usr/share/mime || true\n"
            "command -v gtk-update-icon-cache >/dev/null 2>&1 && "
            "gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true\n",
            encoding="utf-8")
        script.chmod(0o755)

    out = _DIST / f"{_APP}_{version}_{arch}.deb"
    out.unlink(missing_ok=True)
    _run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", stage, out])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-freeze", action="store_true",
                    help="reuse the existing dist/KherveSlide folder")
    args = ap.parse_args()
    if not sys.platform.startswith("linux"):
        sys.exit("build_deb.py only runs on Linux (PyInstaller cannot cross-compile)")
    if not shutil.which("dpkg-deb"):
        sys.exit("dpkg-deb not found (sudo apt install dpkg-dev)")
    arch = deb_arch()
    version = stamp_version()
    if not args.skip_freeze:
        _run([sys.executable, "-m", "PyInstaller", _SPEC, "--noconfirm"], cwd=_ROOT)
    if not (_DIST / _APP / _APP).is_file():
        sys.exit(f"{_DIST / _APP / _APP} not found — did the freeze run?")
    deb = build_deb(version, arch)
    stable = _DIST / f"{_APP}-linux-{arch}.deb"
    shutil.copy2(deb, stable)
    print()
    for p in (deb, stable):
        print(f"{p.name:<44} {p.stat().st_size / 1e6:>7.1f} MB")


if __name__ == "__main__":
    main()
