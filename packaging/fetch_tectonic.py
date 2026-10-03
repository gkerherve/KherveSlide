"""Download the official tectonic release binary into build/tectonic/.

    python packaging/fetch_tectonic.py

The specs bundle it so the installed app compiles slides out of the box.
The official release binaries are self-contained; a Homebrew tectonic is
NOT (it links /opt/homebrew ICU, HarfBuzz, FreeType...), so it would run
on the build Mac and fail on every user's. spec_common.find_tectonic
takes this binary first.

Copyright (C) 2026 Gwilherm Kerherve
"""

import io
import platform
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "0.17.0"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "tectonic"
_BASE = ("https://github.com/tectonic-typesetting/tectonic/releases/download/"
         f"tectonic%40{VERSION}/tectonic-{VERSION}-")


def target() -> tuple[str, str]:
    """(release asset suffix, binary name) for this machine."""
    if sys.platform == "win32":
        return "x86_64-pc-windows-msvc.zip", "tectonic.exe"
    if sys.platform == "darwin":
        arch = {"arm64": "aarch64", "x86_64": "x86_64"}[platform.machine()]
        return f"{arch}-apple-darwin.tar.gz", "tectonic"
    raise SystemExit(f"no tectonic release for {sys.platform}")


def binary_path() -> Path:
    return OUT / target()[1]


def fetch() -> Path:
    asset, name = target()
    out = OUT / name
    stamp = OUT / "VERSION"
    if out.is_file() and stamp.is_file() and stamp.read_text() == f"{VERSION} {asset}":
        return out
    url = _BASE + asset
    print(f"downloading {url}", flush=True)
    data = urllib.request.urlopen(url, timeout=120).read()
    OUT.mkdir(parents=True, exist_ok=True)
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            member = next(m for m in z.namelist() if m.endswith(name))
            out.write_bytes(z.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            member = next(m for m in t.getmembers() if m.name.endswith(name))
            out.write_bytes(t.extractfile(member).read())
    out.chmod(0o755)
    stamp.write_text(f"{VERSION} {asset}")
    return out


if __name__ == "__main__":
    print(fetch())
