"""WMF / EMF → PNG: synthetic metafiles exercising the main records."""
import struct

from kherveslide import metafile, pptx_import


def _wmf(records: list[tuple[int, bytes]], placeable=True) -> bytes:
    body = b""
    for fn, params in records + [(0, b"")]:
        if len(params) % 2:
            params += b"\0"
        body += struct.pack("<IH", 3 + len(params) // 2, fn) + params
    header = struct.pack("<HHHIHIH", 1, 9, 0x300, (18 + len(body)) // 2,
                         4, 100, 0)
    data = header + body
    if placeable:
        ph = struct.pack("<IHhhhhHI", metafile.WMF_PLACEABLE, 0, 0, 0,
                         1000, 500, 1000, 0)
        data = ph + struct.pack("<H", 0) + data
    return data


def _h(*vals):
    return struct.pack(f"<{len(vals)}h", *vals)


def test_wmf_draws_filled_rectangle_line_and_text():
    data = _wmf([
        (0x020B, _h(0, 0)),                      # SETWINDOWORG y, x
        (0x020C, _h(500, 1000)),                 # SETWINDOWEXT y, x
        (0x02FC, struct.pack("<HIH", 0, 0x0000FF, 0)),     # red brush
        (0x02FA, struct.pack("<HhhI", 0, 10, 0, 0x000000)),  # black pen
        (0x012D, _h(0)), (0x012D, _h(1)),
        (0x041B, _h(400, 400, 100, 100)),        # RECTANGLE b r t l
        (0x0325, _h(2, 600, 100, 900, 400)),     # POLYLINE
        (0x0209, struct.pack("<I", 0xFF0000)),   # blue text
        (0x0521, _h(5) + b"Hello\0" + _h(450, 500)),       # TEXTOUT
    ])
    assert metafile.kind(data) == "wmf"
    img = metafile.to_image(data)
    assert img is not None and img.width > img.height
    w, h = img.size
    r, g, b, a = img.getpixel((int(w * 0.25), int(h * 0.5)))
    assert a > 200 and r > 200 and g < 60 and b < 60     # inside the rect
    assert img.getpixel((int(w * 0.98), int(h * 0.05)))[3] == 0  # empty


def _emf_with_bitmap() -> bytes:
    W, H = 4, 2
    bmi = struct.pack("<IiiHHIIiiII", 40, W, H, 1, 24, 0, 0, 0, 0, 0, 0)
    row = bytes([0, 255, 0] * W)                         # green (BGR)
    bits = row * H
    rec_fixed = 8 + 16 + 14 * 4
    off_bmi = rec_fixed
    off_bits = off_bmi + len(bmi)
    stretch = struct.pack("<II", 81, off_bits + len(bits)) \
        + struct.pack("<iiii", 0, 0, 100, 50) \
        + struct.pack("<iiiiiiIIIIIIii", 0, 0, 0, 0, W, H, off_bmi, len(bmi),
                      off_bits, len(bits), 0, 0xCC0020, 100, 50) + bmi + bits
    eof = struct.pack("<IIIII", 14, 20, 0, 0, 20)
    header_size = 88
    header = struct.pack("<II", 1, header_size) \
        + struct.pack("<iiii", 0, 0, 100, 50) \
        + struct.pack("<iiii", 0, 0, 2646, 1323) \
        + b" EMF" + struct.pack("<IIIHH", 0x10000, 0, 3, 0, 0) \
        + struct.pack("<III", 0, 0, 0) \
        + struct.pack("<ii", 96, 96) + struct.pack("<ii", 25, 25)
    header = header[:header_size].ljust(header_size, b"\0")
    data = header + stretch + eof
    return data[:48] + struct.pack("<I", len(data)) + data[52:]


def test_emf_stretchdibits_bitmap():
    data = _emf_with_bitmap()
    assert metafile.kind(data) == "emf"
    img = metafile.to_image(data)
    assert img is not None
    r, g, b, a = img.getpixel((img.width // 2, img.height // 2))
    assert g > 200 and r < 40 and a == 255


def test_ensure_raster_and_pptx_save(tmp_path):
    src = tmp_path / "graph.emf"
    src.write_bytes(_emf_with_bitmap())
    out = metafile.ensure_raster(str(src))
    assert out.endswith("graph.png")
    assert metafile.ensure_raster(str(tmp_path / "x.png")).endswith("x.png")
    saved = pptx_import._save_image(_emf_with_bitmap(), "wmf",
                                    tmp_path / "img_001")
    assert saved.endswith(".png")
    assert metafile.to_image(b"not a metafile") is None


class _Mime:
    def __init__(self, fmt, data):
        self._f, self._d = fmt, data

    def formats(self):
        return [self._f]

    def data(self, f):
        return self._d


def test_clipboard_metafile_becomes_png():
    path = metafile.from_mime(_Mime("application/x-emf", _emf_with_bitmap()))
    assert path and path.endswith(".png")
    assert metafile.from_mime(_Mime("text/plain", b"hi")) is None
