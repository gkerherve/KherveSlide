"""Regenerate the application icon files from icons.app_icon_pixmap.

The window/taskbar icon is drawn at runtime, but the frozen .exe needs a
real file at build time, so this renders the same QPainter art into:

    assets/kherveslide.ico       (16/24/32/48/64/128/256, PNG-in-ICO)
    assets/kherveslide_256.png   (store page / installer / README art)

Run whenever the icon design changes:  py tools/make_app_icon.py
Point PyInstaller at it with:          --icon assets/kherveslide.ico
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kherveslide.icons import app_icon_pixmap  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def _png_bytes(sz: int) -> bytes:
    buf = QBuffer()
    buf.open(QBuffer.WriteOnly)
    app_icon_pixmap(sz).save(buf, "PNG")
    return bytes(buf.data())


def build_ico(path: Path) -> None:
    """Pack one PNG per size into a .ico (PNG-in-ICO, Vista+)."""
    pngs = [(sz, _png_bytes(sz)) for sz in SIZES]
    header = struct.pack("<HHH", 0, 1, len(pngs))
    entries = b""
    offset = len(header) + 16 * len(pngs)
    for sz, data in pngs:
        b = sz % 256          # 0 means 256 in the ICO directory
        entries += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32,
                               len(data), offset)
        offset += len(data)
    path.write_bytes(header + entries + b"".join(d for _, d in pngs))


def main() -> None:
    QApplication.instance() or QApplication([])
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    build_ico(out / "kherveslide.ico")
    app_icon_pixmap(256).save(str(out / "kherveslide_256.png"), "PNG")
    print(f"wrote {out / 'kherveslide.ico'} ({SIZES} px)")
    print(f"wrote {out / 'kherveslide_256.png'}")


if __name__ == "__main__":
    main()
