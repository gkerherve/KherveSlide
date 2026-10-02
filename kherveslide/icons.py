"""Programmatically-drawn toolbar icons.

QPainter draws each icon onto a transparent QPixmap so we never ship binary
image files. Every icon function returns a QIcon.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap,
    QPolygonF,
)

_SIZE = 24
_LINE_W = 2.0

# Mutable theme state — call set_dark() to switch.
_dark = False

def _fg() -> QColor:
    return QColor("#ddd") if _dark else QColor("#222")

def _accent() -> QColor:
    return QColor("#6cb4ff") if _dark else QColor("#1a6dd8")

def _accent2() -> QColor:
    return QColor("#f0a050") if _dark else QColor("#d96b00")

def set_dark(dark: bool) -> None:
    global _dark
    _dark = dark


def _new_canvas() -> tuple[QPixmap, QPainter]:
    px = QPixmap(_SIZE, _SIZE)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    return px, p


def _glyph_icon(letter: str, *, bold=False, italic=False, underline=False,
                strike=False, color: QColor | None = None) -> QIcon:
    px, p = _new_canvas()
    f = QFont("Georgia")
    f.setPointSize(15)
    f.setBold(bold)
    f.setItalic(italic)
    f.setUnderline(underline)
    f.setStrikeOut(strike)
    p.setFont(f)
    p.setPen(color if color is not None else _fg())
    p.drawText(QRect(0, 0, _SIZE, _SIZE), Qt.AlignCenter, letter)
    p.end()
    return QIcon(px)


def app_icon_pixmap(sz: int) -> QPixmap:
    """One square of the application icon at *sz* px — PowerPoint-orange
    rounded square, white lettering. Sizes up to 32 px (taskbar / title
    bar) collapse to a "KS" monogram; larger ones show a big "K" with
    "Slide" beneath it. Shared by the runtime QIcon and the .ico
    generator (tools/make_app_icon.py) so the exe matches the window."""
    from PySide6.QtGui import QLinearGradient
    px = QPixmap(sz, sz)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    radius = sz * 0.18
    grad = QLinearGradient(0, 0, 0, sz)     # the app's Office-orange theme
    grad.setColorAt(0.0, QColor("#F5924C"))
    grad.setColorAt(1.0, QColor("#DE6A14"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(QRectF(0, 0, sz, sz), radius, radius)
    p.setPen(QColor("#ffffff"))
    if sz <= 32:
        # Mini: compact "KS" monogram.
        f = QFont("Georgia"); f.setPixelSize(int(sz * 0.56)); f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, sz, sz), Qt.AlignCenter, "KS")
    else:
        # Large: big "K" over small "Slide".
        fk = QFont("Georgia"); fk.setPixelSize(int(sz * 0.62)); fk.setBold(True)
        p.setFont(fk)
        p.drawText(QRectF(0, -sz * 0.08, sz, sz),
                   Qt.AlignHCenter | Qt.AlignVCenter, "K")
        fs = QFont("Helvetica"); fs.setPixelSize(int(sz * 0.20))
        fs.setBold(True)
        p.setFont(fs)
        p.drawText(QRectF(0, sz * 0.62, sz, sz * 0.34),
                   Qt.AlignHCenter | Qt.AlignTop, "Slide")
    p.end()
    return px


def app_icon() -> QIcon:
    """Application icon, rendered at several sizes for crisp scaling."""
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_icon_pixmap(sz))
    return icon


# ----- text formatting -----

def bold() -> QIcon:       return _glyph_icon("B", bold=True)
def italic() -> QIcon:     return _glyph_icon("I", italic=True)


def _script_icon(sup: bool) -> QIcon:
    """An 'x' with a small raised (super) or lowered (sub) '2'."""
    px, p = _new_canvas()
    p.setPen(_fg())
    fx = QFont("Georgia"); fx.setPixelSize(14)
    p.setFont(fx)
    p.drawText(QRect(2, 2, 14, 20), Qt.AlignVCenter | Qt.AlignLeft, "x")
    fs = QFont("Georgia"); fs.setPixelSize(9); fs.setBold(True)
    p.setFont(fs)
    y = 1 if sup else 9
    p.drawText(QRect(13, y, 10, 14), Qt.AlignTop | Qt.AlignLeft, "2")
    p.end()
    return QIcon(px)


def superscript() -> QIcon:  return _script_icon(True)
def subscript() -> QIcon:    return _script_icon(False)
def underline() -> QIcon:  return _glyph_icon("U", underline=True)
def strike() -> QIcon:     return _glyph_icon("S", strike=True)
def code() -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), _LINE_W, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([QPointF(9, 6), QPointF(4, 12), QPointF(9, 18)])
    p.drawPolyline([QPointF(15, 6), QPointF(20, 12), QPointF(15, 18)])
    p.end()
    return QIcon(px)
def smallcaps() -> QIcon:
    px, p = _new_canvas()
    f1 = QFont("Georgia"); f1.setPointSize(15); f1.setBold(True)
    f2 = QFont("Georgia"); f2.setPointSize(11); f2.setBold(True)
    p.setPen(_fg())
    p.setFont(f1)
    p.drawText(QRect(2, 0, 12, _SIZE), Qt.AlignCenter, "A")
    p.setFont(f2)
    p.drawText(QRect(12, 0, 12, _SIZE), Qt.AlignCenter, "A")
    p.end()
    return QIcon(px)
def superscript() -> QIcon:
    px, p = _new_canvas()
    p.setPen(_fg())
    f1 = QFont("Georgia"); f1.setPointSize(13); f1.setBold(True)
    p.setFont(f1)
    p.drawText(QRect(0, 4, 16, 20), Qt.AlignCenter, "X")
    f2 = QFont("Georgia"); f2.setPointSize(10); f2.setBold(True)
    p.setFont(f2)
    p.drawText(QRect(12, 0, 12, 12), Qt.AlignLeft | Qt.AlignTop, "2")
    p.end()
    return QIcon(px)


def subscript() -> QIcon:
    px, p = _new_canvas()
    p.setPen(_fg())
    f1 = QFont("Georgia"); f1.setPointSize(13); f1.setBold(True)
    p.setFont(f1)
    p.drawText(QRect(0, 0, 16, 20), Qt.AlignCenter, "X")
    f2 = QFont("Georgia"); f2.setPointSize(10); f2.setBold(True)
    p.setFont(f2)
    p.drawText(QRect(12, 12, 12, 12), Qt.AlignLeft | Qt.AlignTop, "2")
    p.end()
    return QIcon(px)


# ----- headings -----

def heading(level: int) -> QIcon:
    px, p = _new_canvas()
    f = QFont("Georgia"); f.setBold(True)
    f.setPointSize({1: 14, 2: 13, 3: 12, 4: 11, 5: 10}.get(level, 12))
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(0, 0, _SIZE, _SIZE), Qt.AlignCenter, f"H{level}")
    p.end()
    return QIcon(px)


# ----- math -----

def math_inline() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Cambria Math"); f.setPointSize(15); f.setItalic(True)
    p.setFont(f); p.setPen(_accent())
    p.drawText(QRect(0, 0, _SIZE, _SIZE), Qt.AlignCenter, "ƒx")
    p.end()
    return QIcon(px)


def math_block() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Cambria Math"); f.setPointSize(13); f.setItalic(True)
    p.setFont(f); p.setPen(_accent())
    p.drawText(QRect(0, 0, _SIZE, _SIZE), Qt.AlignCenter, "Σxᵢ")
    p.end()
    return QIcon(px)


# ----- structure -----

def bullet_list() -> QIcon:
    px, p = _new_canvas()
    p.setBrush(QBrush(_fg())); p.setPen(Qt.NoPen)
    for y in (6, 12, 18):
        p.drawEllipse(QRect(4, y - 2, 4, 4))
    p.setPen(QPen(_fg(), _LINE_W, Qt.SolidLine, Qt.RoundCap))
    for y in (6, 12, 18):
        p.drawLine(11, y, 21, y)
    p.end()
    return QIcon(px)


def numbered_list() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Arial"); f.setPointSize(7); f.setBold(True)
    p.setFont(f); p.setPen(_fg())
    for i, y in enumerate((6, 12, 18), start=1):
        p.drawText(QRect(2, y - 6, 8, 12), Qt.AlignCenter, f"{i}.")
    p.setPen(QPen(_fg(), _LINE_W, Qt.SolidLine, Qt.RoundCap))
    for y in (6, 12, 18):
        p.drawLine(11, y, 21, y)
    p.end()
    return QIcon(px)


def link() -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_accent(), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawArc(3, 8, 10, 10, 90 * 16, 180 * 16)
    p.drawArc(11, 6, 10, 10, -90 * 16, 180 * 16)
    p.drawLine(9, 12, 15, 12)
    p.end()
    return QIcon(px)


def footnote() -> QIcon:
    px, p = _new_canvas()
    f1 = QFont("Georgia"); f1.setPointSize(14)
    f2 = QFont("Georgia"); f2.setPointSize(9); f2.setBold(True)
    p.setPen(_fg())
    p.setFont(f1); p.drawText(QRect(0, 4, 14, _SIZE), Qt.AlignLeft | Qt.AlignVCenter, "T")
    p.setFont(f2); p.drawText(QRect(12, 0, 10, _SIZE), Qt.AlignLeft | Qt.AlignTop, "1")
    p.end()
    return QIcon(px)


def citation() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Arial"); f.setPointSize(11); f.setBold(True)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(0, 0, _SIZE, _SIZE), Qt.AlignCenter, "[1]")
    p.end()
    return QIcon(px)


def cross_ref() -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_accent2(), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(5, 14, 19, 14)
    p.drawPolyline([QPointF(15, 10), QPointF(19, 14), QPointF(15, 18)])
    f = QFont("Georgia"); f.setPointSize(8); f.setBold(True)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(0, 0, _SIZE, 10), Qt.AlignCenter, "ref")
    p.end()
    return QIcon(px)


def figure() -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.6))
    p.setBrush(QBrush(QColor("#3a3a3a") if _dark else QColor("#f4f4f4")))
    p.drawRect(3, 5, 18, 14)
    p.setBrush(QBrush(_accent2())); p.setPen(Qt.NoPen)
    p.drawEllipse(QRect(15, 8, 4, 4))
    p.setBrush(QBrush(_accent())); p.setPen(Qt.NoPen)
    p.drawPolygon([QPointF(4, 18), QPointF(10, 11), QPointF(14, 15), QPointF(20, 18)])
    p.end()
    return QIcon(px)


def table() -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.4))
    p.setBrush(Qt.NoBrush)
    rect = QRect(3, 5, 18, 14)
    p.drawRect(rect)
    p.drawLine(3, 10, 21, 10)
    p.drawLine(3, 14, 21, 14)
    p.drawLine(9, 5, 9, 19)
    p.drawLine(15, 5, 15, 19)
    header_bg = QColor("#2a3a5a") if _dark else QColor("#e8efff")
    p.setBrush(QBrush(header_bg)); p.setPen(Qt.NoPen)
    p.drawRect(QRect(4, 6, 16, 3))
    p.end()
    return QIcon(px)


def drawing() -> QIcon:
    """Pencil over a small wavy line — "freehand drawing"."""
    px, p = _new_canvas()
    # Wavy line below to suggest a sketch.
    p.setPen(QPen(_accent(), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    path = QPainterPath()
    path.moveTo(3, 18)
    path.cubicTo(QPointF(7, 14), QPointF(11, 22), QPointF(15, 18))
    path.cubicTo(QPointF(18, 16), QPointF(20, 20), QPointF(22, 18))
    p.drawPath(path)
    # Pencil — angled rectangle + triangular tip.
    p.setPen(QPen(_fg(), 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QBrush(_accent2()))
    pencil = QPolygonF([
        QPointF(15, 3), QPointF(19, 7), QPointF(9, 17),
        QPointF(5, 13),
    ])
    p.drawPolygon(pencil)
    # Pencil tip
    p.setBrush(QBrush(_fg()))
    p.drawPolygon(QPolygonF([
        QPointF(5, 13), QPointF(9, 17), QPointF(4, 18),
    ]))
    p.end()
    return QIcon(px)


# ----- file ops + history -----

def file_new() -> QIcon:
    px, p = _new_canvas()
    page_bg = QColor("#2d2d2d") if _dark else Qt.white
    p.setPen(QPen(_fg(), 1.6)); p.setBrush(QBrush(page_bg))
    p.drawPolygon([QPointF(5, 3), QPointF(15, 3), QPointF(19, 7),
                   QPointF(19, 21), QPointF(5, 21)])
    p.drawPolyline([QPointF(15, 3), QPointF(15, 7), QPointF(19, 7)])
    p.setPen(QPen(_accent(), 2)); p.drawLine(12, 11, 12, 17); p.drawLine(9, 14, 15, 14)
    p.end()
    return QIcon(px)


def project_open() -> QIcon:
    """Folder with stacked pages — represents a multi-chapter project."""
    px, p = _new_canvas()
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(_fg(), 1.4)
    p.setPen(pen)
    # Back page
    p.setBrush(QBrush(QColor("#c8daf0") if not _dark else QColor("#3a4a60")))
    p.drawRect(QRect(7, 4, 13, 16))
    # Front page
    p.setBrush(QBrush(QColor("#e8f0fe") if not _dark else QColor("#4a5a70")))
    p.drawRect(QRect(4, 6, 13, 16))
    # Lines on front page
    p.setPen(QPen(_fg(), 0.8))
    for y in (10, 13, 16, 19):
        p.drawLine(6, y, 15, y)
    p.end()
    return QIcon(px)


def file_open() -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.6)); p.setBrush(QBrush(QColor("#ffd073")))
    p.drawPolygon([QPointF(3, 8), QPointF(9, 8), QPointF(11, 6),
                   QPointF(20, 6), QPointF(20, 19), QPointF(3, 19)])
    p.end()
    return QIcon(px)


def file_save() -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.6)); p.setBrush(QBrush(_accent()))
    p.drawPolygon([QPointF(4, 4), QPointF(17, 4), QPointF(20, 7),
                   QPointF(20, 20), QPointF(4, 20)])
    p.setBrush(QBrush(Qt.white)); p.setPen(Qt.NoPen)
    p.drawRect(QRect(7, 4, 8, 5))
    p.drawRect(QRect(7, 13, 10, 7))
    p.end()
    return QIcon(px)


def _turn_arrow(mirror: bool) -> QIcon:
    """The classic undo arrow, ↶: an arc over the top that comes down on
    the left into an arrowhead (mirrored for redo, ↷). KherveSlide draws
    it arching upward; KherveTeX's hooks downward (intentional
    divergence)."""
    px, p = _new_canvas()
    p.setRenderHint(QPainter.Antialiasing, True)
    if mirror:
        p.translate(24, 0)
        p.scale(-1, 1)
    p.setPen(QPen(_fg(), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(19, 18)
    path.cubicTo(20, 9, 13, 5.5, 7.5, 9.5)
    p.drawPath(path)
    p.setBrush(QBrush(_fg())); p.setPen(Qt.NoPen)
    p.drawPolygon([QPointF(3.5, 14.5), QPointF(4.5, 6.5), QPointF(11, 11.5)])
    p.end()
    return QIcon(px)


def undo() -> QIcon:
    return _turn_arrow(False)


def redo() -> QIcon:
    return _turn_arrow(True)


def export_pdf() -> QIcon:
    px, p = _new_canvas()
    page_bg = QColor("#2d2d2d") if _dark else Qt.white
    p.setPen(QPen(_fg(), 1.6)); p.setBrush(QBrush(page_bg))
    p.drawPolygon([QPointF(5, 3), QPointF(15, 3), QPointF(19, 7),
                   QPointF(19, 21), QPointF(5, 21)])
    f = QFont("Arial"); f.setPointSize(7); f.setBold(True)
    p.setFont(f); p.setPen(QColor("#ff5555") if _dark else QColor("#c00"))
    p.drawText(QRect(5, 10, 14, 10), Qt.AlignCenter, "PDF")
    p.end()
    return QIcon(px)


def history() -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2, Qt.SolidLine, Qt.RoundCap)); p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRect(4, 4, 16, 16))
    p.drawLine(12, 8, 12, 12)
    p.drawLine(12, 12, 16, 14)
    p.end()
    return QIcon(px)


def commit() -> QIcon:
    px, p = _new_canvas()
    dot_bg = QColor("#2d2d2d") if _dark else Qt.white
    p.setPen(QPen(_fg(), 2)); p.setBrush(QBrush(dot_bg))
    p.drawLine(12, 3, 12, 8); p.drawLine(12, 16, 12, 21)
    p.drawEllipse(QRect(7, 8, 10, 10))
    p.end()
    return QIcon(px)


def branch() -> QIcon:
    """Git branch icon — a forking line with two dots."""
    px, p = _new_canvas()
    col = _accent()
    p.setPen(QPen(col, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    # Main trunk
    p.drawLine(8, 4, 8, 20)
    # Fork line
    p.drawLine(8, 12, 16, 6)
    # Dots
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(col))
    p.drawEllipse(QRect(5, 17, 6, 6))  # trunk tip
    p.drawEllipse(QRect(13, 3, 6, 6))  # fork tip
    p.end()
    return QIcon(px)


def spell_check() -> QIcon:
    """ABC with a red wavy underline — the universal "spell check"
    toolbar glyph. Renders cleanly at 24×24 in both light and dark
    themes; the underline is the same red the highlighter uses."""
    px, p = _new_canvas()
    f = QFont("Arial"); f.setPointSize(11); f.setBold(True)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(0, 0, _SIZE, 18), Qt.AlignCenter, "ABC")
    # Wavy red underline: a three-bump zigzag, hand-drawn so it
    # reads as the same squiggle Qt's SpellCheckUnderline produces.
    p.setPen(QPen(QColor("#d8000c"), 1.4, Qt.SolidLine, Qt.RoundCap,
                  Qt.RoundJoin))
    y_top = 18
    y_bot = 21
    xs = [4, 7, 10, 13, 16, 19]
    pts: list[QPointF] = []
    for i, x in enumerate(xs):
        pts.append(QPointF(x, y_bot if i % 2 == 0 else y_top))
    p.drawPolyline(pts)
    p.end()
    return QIcon(px)


def page_break() -> QIcon:
    px, p = _new_canvas()
    page_bg = QColor("#2d2d2d") if _dark else Qt.white
    p.setPen(QPen(_fg(), 1.6)); p.setBrush(QBrush(page_bg))
    p.drawRect(QRect(4, 3, 16, 7))
    p.drawRect(QRect(4, 14, 16, 7))
    p.setPen(QPen(_accent(), 2, Qt.DashLine))
    p.drawLine(2, 12, 22, 12)
    p.end()
    return QIcon(px)


def horizontal_rule() -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2.5, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(3, 12, 21, 12)
    p.end()
    return QIcon(px)


# ----- alignment -----

def _alignment_icon(lines: list[tuple[int, int, int]]) -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2.0, Qt.SolidLine, Qt.RoundCap))
    for y, x1, x2 in lines:
        p.drawLine(x1, y, x2, y)
    p.end()
    return QIcon(px)


def align_left() -> QIcon:
    return _alignment_icon([(6, 3, 21), (11, 3, 16), (16, 3, 19), (21, 3, 14)])


def align_center() -> QIcon:
    return _alignment_icon([(6, 3, 21), (11, 7, 17), (16, 5, 19), (21, 6, 18)])


def align_right() -> QIcon:
    return _alignment_icon([(6, 3, 21), (11, 8, 21), (16, 5, 21), (21, 10, 21)])


def align_justify() -> QIcon:
    return _alignment_icon([(6, 3, 21), (11, 3, 21), (16, 3, 21), (21, 3, 21)])


def _columns_icon(n: int) -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    outer = QRect(3, 3, 18, 18)
    p.drawRect(outer)
    if n >= 2:
        col_w = outer.width() / n
        p.setPen(QPen(_accent(), 1.4, Qt.SolidLine, Qt.RoundCap))
        for c in range(n):
            x0 = outer.left() + int(col_w * c) + 2
            x1 = outer.left() + int(col_w * (c + 1)) - 2
            for dy in (7, 11, 15, 19):
                p.drawLine(x0, dy - 1, x1, dy - 1)
        p.setPen(QPen(_fg(), 1.2, Qt.DashLine))
        for c in range(1, n):
            x = outer.left() + int(col_w * c)
            p.drawLine(x, outer.top() + 2, x, outer.bottom() - 2)
    else:
        p.setPen(QPen(_accent(), 1.4, Qt.SolidLine, Qt.RoundCap))
        for dy in (7, 11, 15, 19):
            p.drawLine(outer.left() + 2, dy - 1, outer.right() - 2, dy - 1)
    p.end()
    return QIcon(px)


def one_column() -> QIcon:   return _columns_icon(1)
def two_columns() -> QIcon:  return _columns_icon(2)
def three_columns() -> QIcon: return _columns_icon(3)


def zoom_in() -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRect(4, 4, 12, 12))
    p.drawLine(15, 15, 20, 20)
    p.drawLine(7, 10, 13, 10); p.drawLine(10, 7, 10, 13)
    p.end()
    return QIcon(px)


def symbol() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Cambria Math")
    f.setPointSize(17); f.setItalic(True)
    p.setFont(f); p.setPen(_accent())
    p.drawText(QRect(0, 0, _SIZE, _SIZE), Qt.AlignCenter, "\u03b1")
    p.end()
    return QIcon(px)


def equation_builder() -> QIcon:
    px, p = _new_canvas()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(_accent(), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(4, 5, 4, 19); p.drawLine(4, 5, 6, 5); p.drawLine(4, 19, 6, 19)
    p.drawLine(20, 5, 20, 19); p.drawLine(20, 5, 18, 5); p.drawLine(20, 19, 18, 19)
    f = QFont("Cambria Math"); f.setPointSize(8); f.setItalic(True)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(6, 3, 12, 10), Qt.AlignCenter, "x")
    p.drawText(QRect(6, 13, 12, 10), Qt.AlignCenter, "y")
    p.setPen(QPen(_fg(), 1.4)); p.drawLine(7, 12, 17, 12)
    p.end()
    return QIcon(px)


def zoom_out() -> QIcon:
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRect(4, 4, 12, 12))
    p.drawLine(15, 15, 20, 20)
    p.drawLine(7, 10, 13, 10)
    p.end()
    return QIcon(px)


def fit_width() -> QIcon:
    """Double-headed horizontal arrow between two vertical bars."""
    px, p = _new_canvas()
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(_fg(), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    # Left bar
    p.drawLine(4, 5, 4, 19)
    # Right bar
    p.drawLine(20, 5, 20, 19)
    # Horizontal arrow shaft
    p.drawLine(6, 12, 18, 12)
    # Left arrowhead
    p.drawLine(6, 12, 9, 9); p.drawLine(6, 12, 9, 15)
    # Right arrowhead
    p.drawLine(18, 12, 15, 9); p.drawLine(18, 12, 15, 15)
    p.end()
    return QIcon(px)


# ---- equation builder category icons ----

def eq_fractions() -> QIcon:
    px, p = _new_canvas()
    p.setRenderHint(QPainter.Antialiasing, True)
    f = QFont("Cambria Math"); f.setPointSize(7); f.setItalic(True)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(4, 2, 16, 10), Qt.AlignCenter, "a+b")
    p.setPen(QPen(_fg(), 1.4)); p.drawLine(5, 12, 19, 12)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(4, 12, 16, 10), Qt.AlignCenter, "c")
    p.end()
    return QIcon(px)


def eq_sums() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Cambria Math"); f.setPointSize(16)
    p.setFont(f); p.setPen(_accent())
    p.drawText(QRect(0, 0, _SIZE, _SIZE), Qt.AlignCenter, "\u03a3")
    p.end()
    return QIcon(px)


def eq_integrals() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Cambria Math"); f.setPointSize(18)
    p.setFont(f); p.setPen(_accent())
    p.drawText(QRect(0, -1, _SIZE, _SIZE), Qt.AlignCenter, "\u222b")
    p.end()
    return QIcon(px)


def eq_scripts() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Cambria Math"); f.setPointSize(12); f.setItalic(True)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(2, 4, 14, 16), Qt.AlignCenter, "x")
    f2 = QFont("Cambria Math"); f2.setPointSize(7); f2.setItalic(True)
    p.setFont(f2); p.setPen(_accent())
    p.drawText(QRect(13, 2, 10, 10), Qt.AlignLeft | Qt.AlignTop, "2")
    p.drawText(QRect(13, 12, 10, 10), Qt.AlignLeft | Qt.AlignTop, "i")
    p.end()
    return QIcon(px)


def eq_derivatives() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Cambria Math"); f.setPointSize(8); f.setItalic(True)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(2, 2, 20, 10), Qt.AlignCenter, "dy")
    p.setPen(QPen(_fg(), 1.2)); p.drawLine(5, 12, 19, 12)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(2, 12, 20, 10), Qt.AlignCenter, "dx")
    p.end()
    return QIcon(px)


def eq_greek() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Cambria Math"); f.setPointSize(11); f.setItalic(True)
    p.setFont(f); p.setPen(_accent())
    p.drawText(QRect(-2, 0, _SIZE, _SIZE), Qt.AlignCenter, "\u03b1\u03b2")
    p.end()
    return QIcon(px)


def eq_vectors() -> QIcon:
    px, p = _new_canvas()
    p.setRenderHint(QPainter.Antialiasing, True)
    # Arrow over x
    p.setPen(QPen(_accent(), 1.4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(6, 7, 18, 7)
    p.drawLine(15, 4, 18, 7); p.drawLine(15, 10, 18, 7)
    f = QFont("Cambria Math"); f.setPointSize(11); f.setItalic(True)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(0, 6, _SIZE, 16), Qt.AlignCenter, "x")
    p.end()
    return QIcon(px)


def eq_brackets() -> QIcon:
    px, p = _new_canvas()
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(_accent(), 1.6, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    # Left parenthesis arc
    p.drawArc(4, 3, 8, 18, 110 * 16, 140 * 16)
    # Right parenthesis arc
    p.drawArc(12, 3, 8, 18, -70 * 16, 140 * 16)
    p.end()
    return QIcon(px)


def eq_relations() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Cambria Math"); f.setPointSize(12)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRect(0, 0, _SIZE, _SIZE), Qt.AlignCenter, "\u2264\u2265")
    p.end()
    return QIcon(px)


def eq_functions() -> QIcon:
    px, p = _new_canvas()
    f = QFont("Cambria Math"); f.setPointSize(10)
    p.setFont(f); p.setPen(_accent())
    p.drawText(QRect(0, 0, _SIZE, _SIZE), Qt.AlignCenter, "sin")
    p.end()
    return QIcon(px)


def eq_environments() -> QIcon:
    px, p = _new_canvas()
    p.setRenderHint(QPainter.Antialiasing, True)
    # Left brace
    p.setPen(QPen(_accent(), 1.6, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(8, 4, 6, 4); p.drawLine(6, 4, 6, 10)
    p.drawLine(6, 10, 4, 12); p.drawLine(4, 12, 6, 14)
    p.drawLine(6, 14, 6, 20); p.drawLine(6, 20, 8, 20)
    # Lines representing equation rows
    p.setPen(QPen(_fg(), 1.2, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(10, 8, 20, 8)
    p.drawLine(10, 12, 18, 12)
    p.drawLine(10, 16, 20, 16)
    p.end()
    return QIcon(px)


# ----- review -----

def highlight(color: str = "#FFFF00") -> QIcon:
    """Marker pen icon filled with the given highlight colour."""
    px, p = _new_canvas()
    # Marker pen body (tilted rectangle)
    pen_path = QPainterPath()
    pen_path.moveTo(6, 18)
    pen_path.lineTo(10, 4)
    pen_path.lineTo(18, 6)
    pen_path.lineTo(14, 20)
    pen_path.closeSubpath()
    p.setBrush(QBrush(QColor(color)))
    p.setPen(QPen(_fg(), 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(pen_path)
    # Tip
    p.setPen(QPen(_fg(), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(QPointF(6, 18), QPointF(4, 22))
    p.end()
    return QIcon(px)


def comment() -> QIcon:
    """Speech bubble icon for reviewer comments."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QBrush(QColor("#e0ecff") if not _dark else QColor("#2a4060")))
    # Bubble body
    bubble = QPainterPath()
    bubble.addRoundedRect(QRectF(2, 3, 20, 14), 3, 3)
    p.drawPath(bubble)
    # Tail
    tail = QPolygonF([QPointF(6, 17), QPointF(10, 17), QPointF(5, 22)])
    p.drawPolygon(tail)
    # Lines inside bubble
    p.setPen(QPen(_fg(), 1.0, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(6, 8, 18, 8)
    p.drawLine(6, 12, 15, 12)
    p.end()
    return QIcon(px)


def accept_change() -> QIcon:
    """Green checkmark for accepting a comment/change."""
    px, p = _new_canvas()
    p.setPen(QPen(QColor("#2e7d32"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([QPointF(5, 13), QPointF(10, 18), QPointF(19, 6)])
    p.end()
    return QIcon(px)


def reject_change() -> QIcon:
    """Red X for rejecting a comment/change."""
    px, p = _new_canvas()
    p.setPen(QPen(QColor("#c62828"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(QPointF(6, 6), QPointF(18, 18))
    p.drawLine(QPointF(18, 6), QPointF(6, 18))
    p.end()
    return QIcon(px)


def prev_comment() -> QIcon:
    """Left arrow for navigating to previous comment."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([QPointF(14, 6), QPointF(7, 12), QPointF(14, 18)])
    p.drawLine(QPointF(7, 12), QPointF(20, 12))
    p.end()
    return QIcon(px)


def next_comment() -> QIcon:
    """Right arrow for navigating to next comment."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([QPointF(10, 6), QPointF(17, 12), QPointF(10, 18)])
    p.drawLine(QPointF(4, 12), QPointF(17, 12))
    p.end()
    return QIcon(px)


# ----- compile / auto-compile -----

def compile_pdf() -> QIcon:
    """Play-triangle over a small PDF page — "compile now" button."""
    px, p = _new_canvas()
    page_bg = QColor("#2d2d2d") if _dark else Qt.white
    p.setPen(QPen(_fg(), 1.2)); p.setBrush(QBrush(page_bg))
    p.drawPolygon([QPointF(3, 2), QPointF(13, 2), QPointF(16, 5),
                   QPointF(16, 18), QPointF(3, 18)])
    green = QColor("#5fba7d") if _dark else QColor("#2a8c4a")
    p.setPen(Qt.NoPen); p.setBrush(QBrush(green))
    p.drawPolygon([QPointF(13, 8), QPointF(13, 20), QPointF(22, 14)])
    p.end()
    return QIcon(px)


def auto_compile_on() -> QIcon:
    """Circular arrow (sync) — auto-compile is ON."""
    px, p = _new_canvas()
    green = QColor("#5fba7d") if _dark else QColor("#2a8c4a")
    p.setPen(QPen(green, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.arcMoveTo(QRectF(4, 4, 16, 16), 60)
    path.arcTo(QRectF(4, 4, 16, 16), 60, -300)
    p.drawPath(path)
    tip = path.currentPosition()
    p.setPen(Qt.NoPen); p.setBrush(QBrush(green))
    p.drawPolygon([QPointF(tip.x() - 4, tip.y() - 1),
                   QPointF(tip.x() + 1, tip.y() - 5),
                   QPointF(tip.x() + 1, tip.y() + 3)])
    p.end()
    return QIcon(px)


def play() -> QIcon:
    """Green play triangle — force / compile now."""
    px, p = _new_canvas()
    green = QColor("#5fba7d") if _dark else QColor("#2a8c4a")
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(green))
    p.drawPolygon([QPointF(6, 4), QPointF(6, 20), QPointF(20, 12)])
    p.end()
    return QIcon(px)


def grid() -> QIcon:
    """A small 3x3 grid — snap-to-grid toggle."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.3, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawRect(4, 4, 15, 15)
    for i in (1, 2):
        v = 4 + i * 5
        p.drawLine(QPointF(v, 4), QPointF(v, 19))
        p.drawLine(QPointF(4, v), QPointF(19, v))
    p.end()
    return QIcon(px)


def refresh() -> QIcon:
    """Green circular arrow — refresh / compile now."""
    px, p = _new_canvas()
    green = QColor("#5fba7d") if _dark else QColor("#2a8c4a")
    p.setPen(QPen(green, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.arcMoveTo(QRectF(4, 4, 16, 16), 60)
    path.arcTo(QRectF(4, 4, 16, 16), 60, -300)
    p.drawPath(path)
    tip = path.currentPosition()
    p.setPen(Qt.NoPen); p.setBrush(QBrush(green))
    p.drawPolygon([QPointF(tip.x() - 4, tip.y() - 1),
                   QPointF(tip.x() + 1, tip.y() - 5),
                   QPointF(tip.x() + 1, tip.y() + 3)])
    p.end()
    return QIcon(px)


def auto_compile_off() -> QIcon:
    """Circular arrow (sync) with a diagonal strike — auto-compile is OFF."""
    px, p = _new_canvas()
    grey = QColor("#888") if _dark else QColor("#999")
    p.setPen(QPen(grey, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.arcMoveTo(QRectF(4, 4, 16, 16), 60)
    path.arcTo(QRectF(4, 4, 16, 16), 60, -300)
    p.drawPath(path)
    tip = path.currentPosition()
    p.setPen(Qt.NoPen); p.setBrush(QBrush(grey))
    p.drawPolygon([QPointF(tip.x() - 4, tip.y() - 1),
                   QPointF(tip.x() + 1, tip.y() - 5),
                   QPointF(tip.x() + 1, tip.y() + 3)])
    red = QColor("#ff5555") if _dark else QColor("#c00")
    p.setPen(QPen(red, 2.4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(5, 5), QPointF(19, 19))
    p.end()
    return QIcon(px)


def compile_no_images() -> QIcon:
    """Page with a crossed-out image icon — compile without images."""
    px, p = _new_canvas()
    page_bg = QColor("#2d2d2d") if _dark else Qt.white
    p.setPen(QPen(_fg(), 1.2)); p.setBrush(QBrush(page_bg))
    p.drawPolygon([QPointF(3, 2), QPointF(13, 2), QPointF(16, 5),
                   QPointF(16, 18), QPointF(3, 18)])
    # Small "mountain + sun" image icon on the page
    grey = QColor("#999") if _dark else QColor("#888")
    p.setPen(QPen(grey, 1.0)); p.setBrush(Qt.NoBrush)
    p.drawRect(5, 7, 8, 6)
    # Diagonal cross-out
    red = QColor("#ff5555") if _dark else QColor("#c00")
    p.setPen(QPen(red, 2.0, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(4, 6), QPointF(14, 14))
    p.end()
    return QIcon(px)


def compile_range() -> QIcon:
    """Page with two horizontal bracket lines — compile-range toggle."""
    px, p = _new_canvas()
    page_bg = QColor("#2d2d2d") if _dark else Qt.white
    p.setPen(QPen(_fg(), 1.2)); p.setBrush(QBrush(page_bg))
    p.drawPolygon([QPointF(3, 2), QPointF(13, 2), QPointF(16, 5),
                   QPointF(16, 18), QPointF(3, 18)])
    green = QColor("#5fba7d") if _dark else QColor("#2a8c4a")
    p.setPen(QPen(green, 1.8, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(5, 8), QPointF(14, 8))
    red = QColor("#ff5555") if _dark else QColor("#c00")
    p.setPen(QPen(red, 1.8, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(5, 14), QPointF(14, 14))
    p.end()
    return QIcon(px)


# ----- kherveSlide: slide-designer icons -----

def slide_add() -> QIcon:
    """Slide rectangle with a plus — add a new slide."""
    px, p = _new_canvas()
    page_bg = QColor("#2d2d2d") if _dark else Qt.white
    p.setPen(QPen(_fg(), 1.6)); p.setBrush(QBrush(page_bg))
    p.drawRect(3, 6, 18, 12)
    p.setPen(QPen(_accent(), 2))
    p.drawLine(12, 9, 12, 15); p.drawLine(9, 12, 15, 12)
    p.end()
    return QIcon(px)


def text_box() -> QIcon:
    """Dashed box with a serif "T" — add a text box."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.2, Qt.DashLine)); p.setBrush(Qt.NoBrush)
    p.drawRect(3, 4, 18, 16)
    f = QFont("Georgia"); f.setPointSize(12); f.setBold(True)
    p.setFont(f); p.setPen(_accent())
    p.drawText(QRect(3, 4, 18, 16), Qt.AlignCenter, "T")
    p.end()
    return QIcon(px)


def image_box() -> QIcon:
    """Picture frame with hill + sun — add an image box."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.6))
    p.setBrush(QBrush(QColor("#3a3a3a") if _dark else QColor("#f4f4f4")))
    p.drawRect(3, 5, 18, 14)
    p.setBrush(QBrush(_accent2())); p.setPen(Qt.NoPen)
    p.drawEllipse(QRect(15, 8, 4, 4))
    p.setBrush(QBrush(_accent()))
    p.drawPolygon([QPointF(4, 18), QPointF(10, 11), QPointF(14, 15),
                   QPointF(20, 18)])
    p.end()
    return QIcon(px)


def video_box() -> QIcon:
    """Film frame with a play triangle — add a video box."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.6))
    p.setBrush(QBrush(QColor("#3a3a3a") if _dark else QColor("#f4f4f4")))
    p.drawRect(3, 5, 18, 14)
    # Sprocket holes down the left/right edges make it read as film.
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(_fg()))
    for y in (7, 11, 15):
        p.drawRect(QRect(4, y, 2, 2))
        p.drawRect(QRect(18, y, 2, 2))
    p.setBrush(QBrush(_accent()))
    p.drawPolygon([QPointF(10, 8.5), QPointF(10, 15.5), QPointF(16, 12)])
    p.end()
    return QIcon(px)


def _stack_icon(front: bool) -> QIcon:
    """Two overlapping squares; the highlighted one is the moved layer."""
    px, p = _new_canvas()
    back = QColor("#555") if _dark else QColor("#bbb")
    p.setPen(QPen(_fg(), 1.2))
    if front:
        p.setBrush(QBrush(back)); p.drawRect(6, 6, 10, 10)
        p.setBrush(QBrush(_accent())); p.drawRect(10, 10, 10, 10)
    else:
        p.setBrush(QBrush(_accent())); p.drawRect(4, 4, 10, 10)
        p.setBrush(QBrush(back)); p.drawRect(8, 8, 10, 10)
    p.end()
    return QIcon(px)


def raise_box() -> QIcon:   return _stack_icon(front=True)
def lower_box() -> QIcon:   return _stack_icon(front=False)


def _stack_extreme_icon(front: bool) -> QIcon:
    """Like _stack_icon but with a double chevron meaning 'all the way'."""
    px, p = _new_canvas()
    back = QColor("#555") if _dark else QColor("#bbb")
    p.setPen(QPen(_fg(), 1.2))
    if front:
        p.setBrush(QBrush(back)); p.drawRect(5, 7, 9, 9)
        p.setBrush(QBrush(_accent())); p.drawRect(9, 11, 9, 9)
    else:
        p.setBrush(QBrush(_accent())); p.drawRect(5, 4, 9, 9)
        p.setBrush(QBrush(back)); p.drawRect(9, 8, 9, 9)
    p.setPen(QPen(_accent2(), 1.8))
    p.setBrush(Qt.NoBrush)
    if front:                       # chevrons pointing up
        for dy in (0, 4):
            p.drawPolyline([QPointF(15, 8 + dy), QPointF(18, 5 + dy),
                            QPointF(21, 8 + dy)])
    else:                           # chevrons pointing down
        for dy in (0, 4):
            p.drawPolyline([QPointF(15, 14 + dy), QPointF(18, 17 + dy),
                            QPointF(21, 14 + dy)])
    p.end()
    return QIcon(px)


def to_front() -> QIcon:    return _stack_extreme_icon(front=True)
def to_back() -> QIcon:     return _stack_extreme_icon(front=False)


def delete_box() -> QIcon:
    """Trash-can outline — delete the selected object."""
    px, p = _new_canvas()
    red = QColor("#ff5555") if _dark else QColor("#c00")
    p.setPen(QPen(red, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(5, 7, 19, 7)
    p.drawLine(9, 7, 9, 4); p.drawLine(15, 7, 15, 4)
    p.drawPolyline([QPointF(6, 7), QPointF(7, 20), QPointF(17, 20),
                    QPointF(18, 7)])
    p.drawLine(10, 10, 10, 17); p.drawLine(14, 10, 14, 17)
    p.end()
    return QIcon(px)


def templates_icon() -> QIcon:
    """Grid of small slides — template gallery."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.2))
    p.setBrush(QBrush(_accent()))
    p.drawRect(3, 4, 7, 6)
    p.setBrush(QBrush(QColor("#555") if _dark else QColor("#ccc")))
    p.drawRect(13, 4, 7, 6); p.drawRect(3, 14, 7, 6); p.drawRect(13, 14, 7, 6)
    p.end()
    return QIcon(px)


def slide_remove() -> QIcon:
    """Slide rectangle with a minus — remove the active slide."""
    px, p = _new_canvas()
    page_bg = QColor("#2d2d2d") if _dark else Qt.white
    p.setPen(QPen(_fg(), 1.6)); p.setBrush(QBrush(page_bg))
    p.drawRect(3, 6, 18, 12)
    red = QColor("#ff5555") if _dark else QColor("#c00")
    p.setPen(QPen(red, 2)); p.drawLine(9, 12, 15, 12)
    p.end()
    return QIcon(px)


def move_up() -> QIcon:
    """Upward chevron — move the active slide up."""
    px, p = _new_canvas()
    p.setPen(QPen(_accent(), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([QPointF(6, 15), QPointF(12, 8), QPointF(18, 15)])
    p.end()
    return QIcon(px)


def move_down() -> QIcon:
    """Downward chevron — move the active slide down."""
    px, p = _new_canvas()
    p.setPen(QPen(_accent(), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([QPointF(6, 9), QPointF(12, 16), QPointF(18, 9)])
    p.end()
    return QIcon(px)


def prev_slide() -> QIcon:
    """Filled up-triangle — go to the previous slide."""
    px, p = _new_canvas()
    p.setBrush(QBrush(_accent())); p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(12, 6), QPointF(19, 17), QPointF(5, 17)]))
    p.end()
    return QIcon(px)


def next_slide() -> QIcon:
    """Filled down-triangle — go to the next slide."""
    px, p = _new_canvas()
    p.setBrush(QBrush(_accent())); p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(5, 7), QPointF(19, 7), QPointF(12, 18)]))
    p.end()
    return QIcon(px)


def toggle_navigator() -> QIcon:
    """A panel with a highlighted left column — show / hide the navigator."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(4, 5, 16, 14), 2, 2)
    p.setBrush(QBrush(_accent())); p.setPen(Qt.NoPen)
    p.drawRect(QRectF(5, 6, 5, 12))
    p.end()
    return QIcon(px)


def pdf_side_panel() -> QIcon:
    """A window split in two, the right half a red-tagged PDF page — show
    the compiled PDF beside the slide (off = Visual only)."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(2.5, 4.5, 19, 15), 2, 2)
    p.drawLine(QPointF(12, 5), QPointF(12, 19))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(_accent()))
    p.drawRect(QRectF(4.5, 7, 5.5, 3))          # slide title bar (left)
    p.setBrush(QBrush(QColor("#c62828")))
    p.drawRect(QRectF(14, 7, 6, 3.2))            # PDF tag (right)
    p.setBrush(QBrush(_fg()))
    for i in range(3):
        p.drawRect(QRectF(14, 12 + i * 2.4, 6 - (2 if i == 2 else 0), 1.1))
    p.end()
    return QIcon(px)


def line_tool() -> QIcon:
    """A plain diagonal line."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2.0, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(4, 20, 20, 4)
    p.end()
    return QIcon(px)


def arrow_tool() -> QIcon:
    """A diagonal line with an arrowhead."""
    px, p = _new_canvas()
    p.setPen(QPen(_accent(), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(4, 20, 17, 7)
    p.setBrush(QBrush(_accent())); p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(19, 5), QPointF(11, 7),
                             QPointF(17, 13)]))
    p.end()
    return QIcon(px)


def rect_tool() -> QIcon:
    """A hollow rounded rectangle."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(4, 7, 16, 10), 2.5, 2.5)
    p.end()
    return QIcon(px)


def ellipse_tool() -> QIcon:
    """A hollow circle / ellipse."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2.0, Qt.SolidLine))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(4, 5, 16, 14))
    p.end()
    return QIcon(px)


def select_cursor() -> QIcon:
    """A mouse-pointer arrow — the Select tool."""
    px, p = _new_canvas()
    p.setBrush(QBrush(_fg())); p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([
        QPointF(6, 4), QPointF(6, 18), QPointF(10, 14), QPointF(13, 20),
        QPointF(15, 19), QPointF(12, 13), QPointF(17, 13)]))
    p.end()
    return QIcon(px)


def pen() -> QIcon:
    """A pen / nib — the freehand Pen tool."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2.4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(6, 18, 14, 10)
    p.setBrush(QBrush(_accent())); p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(14, 10), QPointF(18, 6), QPointF(19, 11),
                             QPointF(15, 14)]))
    p.setBrush(QBrush(_fg()))
    p.drawPolygon(QPolygonF([QPointF(5, 19), QPointF(7, 17), QPointF(8, 20)]))
    p.end()
    return QIcon(px)


def text_tool() -> QIcon:
    """A capital T — the Text tool."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2.4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(6, 7, 18, 7)
    p.drawLine(12, 7, 12, 18)
    p.end()
    return QIcon(px)


def eraser() -> QIcon:
    """A tilted eraser block."""
    px, p = _new_canvas()
    p.save()
    p.translate(12, 13); p.rotate(-32)
    p.setPen(QPen(_fg(), 1.4)); p.setBrush(QBrush(QColor("#f4b183")))
    p.drawRoundedRect(QRectF(-7, -4.5, 14, 9), 1.5, 1.5)
    p.drawLine(QPointF(0, -4.5), QPointF(0, 4.5))
    p.restore()
    p.end()
    return QIcon(px)


def clear_all() -> QIcon:
    """A waste-bin — clear the drawing."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawLine(5, 8, 19, 8)
    p.drawLine(10, 6, 14, 6)
    p.drawPolyline([QPointF(7, 8), QPointF(8, 19), QPointF(16, 19),
                    QPointF(17, 8)])
    p.drawLine(10, 10, 10, 17)
    p.drawLine(14, 10, 14, 17)
    p.end()
    return QIcon(px)


def grid_icon() -> QIcon:
    """A hash grid — toggle the drawing grid."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.3))
    for i in (8, 12, 16):
        p.drawLine(i, 5, i, 19)
        p.drawLine(5, i, 19, i)
    p.end()
    return QIcon(px)


def snap_icon() -> QIcon:
    """A grid with a highlighted node — toggle snapping."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.1))
    for i in (7, 12, 17):
        p.drawLine(i, 6, i, 18)
        p.drawLine(6, i, 18, i)
    p.setBrush(QBrush(_accent())); p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(12, 12), 3.0, 3.0)
    p.end()
    return QIcon(px)


def _rotate_icon(cw: bool) -> QIcon:
    """A circular arrow — rotate clockwise or counter-clockwise."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2.0, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    # 270° arc leaving a gap at the top where the arrowhead sits.
    p.drawArc(QRectF(5, 5, 14, 14), 120 * 16, 300 * 16)
    p.setBrush(QBrush(_fg())); p.setPen(Qt.NoPen)
    if cw:
        p.drawPolygon(QPolygonF([QPointF(18, 4), QPointF(19, 11),
                                 QPointF(13, 8)]))
    else:
        p.drawPolygon(QPolygonF([QPointF(6, 4), QPointF(5, 11),
                                 QPointF(11, 8)]))
    p.end()
    return QIcon(px)


def rotate_left() -> QIcon:   return _rotate_icon(cw=False)
def rotate_right() -> QIcon:  return _rotate_icon(cw=True)


def crop_reset() -> QIcon:
    """Two overlapping crop corners — reset the crop to the full image."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([QPointF(8, 3), QPointF(8, 16), QPointF(21, 16)])
    p.drawPolyline([QPointF(3, 8), QPointF(16, 8), QPointF(16, 21)])
    p.end()
    return QIcon(px)


def paste() -> QIcon:
    """Clipboard with a sheet — paste from clipboard."""
    px, p = _new_canvas()
    p.setPen(QPen(_fg(), 1.6)); p.setBrush(QBrush(_accent()))
    p.drawRoundedRect(QRectF(5, 4, 14, 17), 2, 2)
    p.setBrush(QBrush(_fg() if not _dark else QColor("#222")))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(9, 2.5, 6, 3.5), 1, 1)   # the clip
    p.setBrush(QBrush(QColor("#fff")))
    p.setPen(QPen(QColor("#bbb"), 1))
    p.drawRect(QRectF(8, 9, 8, 9))                    # sheet
    p.end()
    return QIcon(px)


def remove_bg() -> QIcon:
    """A checkerboard (transparency) with a wand — make background clear."""
    px, p = _new_canvas()
    p.setPen(Qt.NoPen)
    light = QColor("#888") if _dark else QColor("#ccc")
    p.setBrush(QBrush(light))
    for r in range(3):
        for c in range(3):
            if (r + c) % 2 == 0:
                p.drawRect(4 + c * 5, 4 + r * 5, 5, 5)
    p.setPen(QPen(_accent2(), 2.2, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(11, 18, 20, 9)                         # wand
    p.setBrush(QBrush(_accent2())); p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(18, 6, 5, 5))                # wand tip
    p.end()
    return QIcon(px)


# ----- drawing dialog (paint tools) -----
# Drawn on a 24-unit grid but rendered at 2x so the larger palette buttons
# stay crisp on hi-DPI screens.

def _paint_canvas() -> tuple[QPixmap, QPainter]:
    px = QPixmap(_SIZE * 2, _SIZE * 2)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.scale(2, 2)
    return px, p


def _pen(color, w=1.6) -> QPen:
    return QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def _fill_soft() -> QColor:
    c = QColor(_accent())
    c.setAlpha(60)
    return c


def _pt_pointer(p):
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(QBrush(_fg()))
    p.drawPolygon(QPolygonF([QPointF(6, 3), QPointF(6, 19), QPointF(10, 15),
                             QPointF(13, 21), QPointF(15.5, 20),
                             QPointF(12.5, 14), QPointF(18, 14)]))


def _pt_pencil(p):
    p.setPen(_pen(_fg(), 1.3)); p.setBrush(QBrush(_accent2()))
    p.drawPolygon(QPolygonF([QPointF(16, 3), QPointF(21, 8), QPointF(9, 20),
                             QPointF(4, 15)]))
    p.setBrush(QBrush(_fg()))
    p.drawPolygon(QPolygonF([QPointF(4, 15), QPointF(9, 20), QPointF(3, 21)]))
    p.setPen(_pen(_fg(), 1.1))
    p.drawLine(QPointF(14, 5), QPointF(19, 10))


def _pt_eraser(p):
    p.setPen(_pen(_fg(), 1.3))
    p.setBrush(QBrush(QColor("#f28b9b")))
    p.drawPolygon(QPolygonF([QPointF(13, 3), QPointF(21, 11), QPointF(14, 18),
                             QPointF(6, 10)]))
    p.setBrush(QBrush(QColor("#ffffff") if not _dark else QColor("#666")))
    p.drawPolygon(QPolygonF([QPointF(6, 10), QPointF(14, 18), QPointF(11, 21),
                             QPointF(7, 21), QPointF(3, 17), QPointF(3, 13)]))
    p.drawLine(QPointF(11, 21), QPointF(21, 21))


def _pt_bucket(p):
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(QBrush(_fill_soft()))
    p.drawPolygon(QPolygonF([QPointF(10, 3), QPointF(18, 11), QPointF(11, 18),
                             QPointF(3, 10)]))
    p.drawLine(QPointF(10, 3), QPointF(8, 1.5))
    p.setPen(Qt.NoPen); p.setBrush(QBrush(_accent()))
    path = QPainterPath(QPointF(19.5, 13))
    path.cubicTo(QPointF(22, 17), QPointF(22.5, 20), QPointF(19.5, 20.5))
    path.cubicTo(QPointF(16.5, 20), QPointF(17, 17), QPointF(19.5, 13))
    p.drawPath(path)


def _pt_picker(p):
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(QBrush(_fg()))
    p.drawEllipse(QPointF(18, 6), 3.2, 3.2)
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(15, 7), QPointF(17, 9))
    p.setPen(_pen(_fg(), 2.2))
    p.drawLine(QPointF(15.5, 8.5), QPointF(6, 18))
    p.setPen(_pen(_accent(), 2.2))
    p.drawLine(QPointF(6, 18), QPointF(4, 20))


def _pt_line(p):
    p.setPen(_pen(_fg(), 2.0))
    p.drawLine(QPointF(4, 20), QPointF(20, 4))
    p.setBrush(QBrush(_accent())); p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(4, 20), 2, 2); p.drawEllipse(QPointF(20, 4), 2, 2)


def _pt_arrow(p):
    p.setPen(_pen(_fg(), 2.0))
    p.drawLine(QPointF(4, 20), QPointF(17, 7))
    p.setBrush(QBrush(_fg()))
    p.drawPolygon(QPolygonF([QPointF(21, 3), QPointF(19.5, 12),
                             QPointF(12, 4.5)]))


def _pt_dimension(p):
    p.setPen(_pen(_fg(), 1.3))
    p.drawLine(QPointF(3, 7), QPointF(3, 19)); p.drawLine(QPointF(21, 7), QPointF(21, 19))
    p.drawLine(QPointF(4, 13), QPointF(20, 13))
    p.setBrush(QBrush(_fg()))
    p.drawPolygon(QPolygonF([QPointF(4, 13), QPointF(8, 11), QPointF(8, 15)]))
    p.drawPolygon(QPolygonF([QPointF(20, 13), QPointF(16, 11), QPointF(16, 15)]))
    f = QFont(); f.setPixelSize(7); f.setBold(True); p.setFont(f)
    p.setPen(_accent())
    p.drawText(QRectF(4, 3, 16, 9), Qt.AlignCenter, "mm")


def _pt_protractor(p):
    p.setPen(_pen(_fg(), 1.5)); p.setBrush(QBrush(_fill_soft()))
    path = QPainterPath(QPointF(3, 19))
    path.arcTo(QRectF(3, 5, 18, 28), 180, -180)
    path.closeSubpath()
    p.drawPath(path)
    p.setPen(_pen(_accent(), 1.5))
    p.drawLine(QPointF(12, 19), QPointF(17, 9))


def _pt_shape(p, kind):
    p.setPen(_pen(_fg(), 1.7)); p.setBrush(QBrush(_fill_soft()))
    box = QRectF(3.5, 5.5, 17, 13)
    if kind == "rect":
        p.drawRect(box)
    elif kind == "roundrect":
        p.drawRoundedRect(box, 4, 4)
    elif kind == "circle":
        p.drawEllipse(QRectF(4, 4, 16, 16))
    elif kind == "ellipse":
        p.drawEllipse(QRectF(2.5, 6.5, 19, 11))
    else:
        from .paint import canvas
        r = QRectF(3.5, 3.5, 17, 17)
        if kind in canvas.ARC_KINDS:
            p.drawPath(canvas.arc_path(kind, r))
        else:
            p.drawPolygon(canvas.polygon_for_kind(kind, r))


def _pt_text(p):
    f = QFont("Georgia"); f.setPixelSize(19); f.setBold(True)
    p.setFont(f); p.setPen(_fg())
    p.drawText(QRectF(0, 0, 24, 24), Qt.AlignCenter, "T")
    p.setPen(_pen(_accent(), 1.2))
    p.drawLine(QPointF(19, 5), QPointF(19, 19))


def _pt_image(p):
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
    p.setBrush(QBrush(_accent())); p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(4.5, 18.5), QPointF(10, 11),
                             QPointF(14, 15.5), QPointF(16, 13.5),
                             QPointF(19.5, 18.5)]))
    p.setBrush(QBrush(_accent2()))
    p.drawEllipse(QPointF(16, 8.5), 2, 2)


def _pt_group(p, ungroup=False):
    p.setPen(QPen(_accent(), 1.2, Qt.DashLine)); p.setBrush(Qt.NoBrush)
    if not ungroup:
        p.drawRect(QRectF(2.5, 2.5, 19, 19))
    p.setPen(_pen(_fg(), 1.5)); p.setBrush(QBrush(_fill_soft()))
    d = 1.5 if ungroup else 0
    p.drawRect(QRectF(5 - d, 5 - d, 8, 8))
    p.drawEllipse(QRectF(11 + d, 11 + d, 8, 8))


def _pt_zorder(p, up: bool, full: bool):
    back = QColor("#b9c3cf") if not _dark else QColor("#666")
    front = _accent()
    p.setPen(_pen(_fg(), 1.2))
    lo, hi = (QRectF(3, 9, 11, 11), QRectF(10, 4, 11, 11))
    p.setBrush(QBrush(back if up else front)); p.drawRect(lo if up else hi)
    p.setBrush(QBrush(front if up else back)); p.drawRect(hi if up else lo)
    if full:
        p.setPen(_pen(_fg(), 1.6))
        y = 2 if up else 22
        p.drawLine(QPointF(3, y), QPointF(8, y))


def _pt_copy(p):
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(4, 3, 11, 13), 1.5, 1.5)
    p.setBrush(QBrush(QColor("#ffffff") if not _dark else QColor("#333")))
    p.drawRoundedRect(QRectF(9, 8, 11, 13), 1.5, 1.5)


def _pt_paste(p):
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(QBrush(_fill_soft()))
    p.drawRoundedRect(QRectF(4, 4, 16, 18), 2, 2)
    p.setBrush(QBrush(_fg()))
    p.drawRoundedRect(QRectF(8.5, 2, 7, 4), 1, 1)


def _pt_duplicate(p):
    _pt_copy(p)
    p.setPen(_pen(_accent(), 1.6))
    p.drawLine(QPointF(14.5, 11.5), QPointF(14.5, 17.5))
    p.drawLine(QPointF(11.5, 14.5), QPointF(17.5, 14.5))


def _pt_delete(p):
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(4, 6), QPointF(20, 6))
    p.drawRect(QRectF(9.5, 3, 5, 3))
    p.drawPolygon(QPolygonF([QPointF(6, 6), QPointF(18, 6), QPointF(17, 21),
                             QPointF(7, 21)]))
    p.drawLine(QPointF(10, 9.5), QPointF(10, 18))
    p.drawLine(QPointF(14, 9.5), QPointF(14, 18))


def _pt_grid(p):
    p.setPen(_pen(_fg(), 1.0))
    for v in (4, 10, 16, 22):
        p.drawLine(QPointF(v - 1, 3), QPointF(v - 1, 21))
        p.drawLine(QPointF(3, v - 1), QPointF(21, v - 1))


def _pt_snap(p):
    _pt_grid(p)
    p.setPen(Qt.NoPen); p.setBrush(QBrush(_accent()))
    p.drawEllipse(QPointF(9, 9), 3, 3)


def _pt_fit(p):
    p.setPen(QPen(_accent(), 1.2, Qt.DashLine)); p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(6, 6, 12, 12))
    p.setPen(_pen(_fg(), 1.6))
    for (x, y, dx, dy) in ((3, 3, 1, 1), (21, 3, -1, 1), (3, 21, 1, -1),
                           (21, 21, -1, -1)):
        p.drawLine(QPointF(x, y), QPointF(x + 4 * dx, y))
        p.drawLine(QPointF(x, y), QPointF(x, y + 4 * dy))


def _pt_flip(p, vertical=False):
    if vertical:
        p.translate(24, 0); p.rotate(90)
    p.setPen(QPen(_fg(), 1.1, Qt.DashLine))
    p.drawLine(QPointF(12, 2), QPointF(12, 22))
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(QBrush(_fg()))
    p.drawPolygon(QPolygonF([QPointF(10, 5), QPointF(10, 19), QPointF(3, 19)]))
    p.setBrush(QBrush(_fill_soft()))
    p.drawPolygon(QPolygonF([QPointF(14, 5), QPointF(14, 19), QPointF(21, 19)]))


def _pt_rotate(p):
    p.setPen(_pen(_fg(), 1.8)); p.setBrush(Qt.NoBrush)
    path = QPainterPath(QPointF(19, 12))
    path.arcTo(QRectF(5, 5, 14, 14), 0, 270)
    p.drawPath(path)
    p.setBrush(QBrush(_fg())); p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(15.5, 2), QPointF(15.5, 10),
                             QPointF(9.5, 5.5)]))


def _pt_explode(p):
    p.setPen(_pen(_fg(), 1.6))
    p.drawLine(QPointF(3, 8), QPointF(10, 3))
    p.drawLine(QPointF(14, 3), QPointF(21, 8))
    p.drawLine(QPointF(21, 13), QPointF(21, 21))
    p.drawLine(QPointF(3, 13), QPointF(3, 21))
    p.drawLine(QPointF(7, 21), QPointF(17, 21))


def _pt_flowchart(p):
    p.setPen(_pen(_fg(), 1.3)); p.setBrush(QBrush(_fill_soft()))
    p.drawRoundedRect(QRectF(7, 1.5, 10, 5), 2.5, 2.5)
    p.drawPolygon(QPolygonF([QPointF(12, 9), QPointF(17, 12.5),
                             QPointF(12, 16), QPointF(7, 12.5)]))
    p.drawRect(QRectF(7, 18.5, 10, 4.5))
    p.drawLine(QPointF(12, 6.5), QPointF(12, 9))
    p.drawLine(QPointF(12, 16), QPointF(12, 18.5))


def _pt_electrical(p):
    p.setPen(_pen(_fg(), 1.5)); p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(2, 12), QPointF(6, 12))
    p.drawPolyline(QPolygonF([QPointF(6, 12), QPointF(7.5, 8), QPointF(10, 16),
                              QPointF(12.5, 8), QPointF(15, 16),
                              QPointF(17.5, 8), QPointF(18.5, 12)]))
    p.drawLine(QPointF(18.5, 12), QPointF(22, 12))


def _pt_optics(p):
    p.setPen(_pen(QColor("#d8000c"), 1.4))
    p.drawLine(QPointF(2, 8), QPointF(12, 12)); p.drawLine(QPointF(2, 16), QPointF(12, 12))
    p.drawLine(QPointF(12, 12), QPointF(22, 12))
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(QBrush(_fill_soft()))
    path = QPainterPath(QPointF(9, 3))
    path.quadTo(QPointF(14, 12), QPointF(9, 21))
    path.quadTo(QPointF(4, 12), QPointF(9, 3))
    p.drawPath(path)


def _pt_maths(p):
    p.setPen(_pen(_fg(), 1.3))
    p.drawLine(QPointF(3, 21), QPointF(21, 21)); p.drawLine(QPointF(3, 21), QPointF(3, 3))
    p.setPen(_pen(_accent(), 1.6)); p.setBrush(Qt.NoBrush)
    path = QPainterPath(QPointF(4, 19))
    path.cubicTo(QPointF(9, 19), QPointF(10, 4), QPointF(13, 4))
    path.cubicTo(QPointF(16, 4), QPointF(17, 17), QPointF(21, 17))
    p.drawPath(path)


def _pt_callout(p):
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(QBrush(_fill_soft()))
    path = QPainterPath()
    path.addRoundedRect(QRectF(2.5, 3, 19, 12), 3, 3)
    tail = QPainterPath()
    tail.addPolygon(QPolygonF([QPointF(7, 14), QPointF(6, 21), QPointF(12, 14)]))
    p.drawPath(path.united(tail))


def _pt_labware(p):
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(Qt.NoBrush)
    outline = QPolygonF([QPointF(9, 2.5), QPointF(9, 9), QPointF(3.5, 20),
                         QPointF(4.5, 21.5), QPointF(19.5, 21.5),
                         QPointF(20.5, 20), QPointF(15, 9), QPointF(15, 2.5)])
    p.setBrush(QBrush(_fill_soft()))
    p.drawPolygon(outline)
    p.setPen(_pen(_accent(), 1.2))
    p.drawLine(QPointF(6.5, 15.5), QPointF(17.5, 15.5))


def _pt_chemistry(p):
    import math
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(Qt.NoBrush)
    pts = [QPointF(12 + 8.5 * math.cos(math.radians(90 + 60 * k)),
                   12 + 8.5 * math.sin(math.radians(90 + 60 * k)))
           for k in range(6)]
    p.drawPolygon(QPolygonF(pts))
    p.setPen(_pen(_accent(), 1.3))
    p.drawEllipse(QPointF(12, 12), 4.8, 4.8)


def _pt_canvas(p):
    p.setPen(_pen(_fg(), 1.4)); p.setBrush(QBrush(QColor("#ffffff")))
    p.drawRect(QRectF(5, 5, 14, 14))
    p.setPen(_pen(_accent(), 1.4))
    p.drawLine(QPointF(2, 5), QPointF(2, 19)); p.drawLine(QPointF(5, 22), QPointF(19, 22))


_PAINT_TOOLS = {
    "pointer": _pt_pointer, "pencil": _pt_pencil, "eraser": _pt_eraser,
    "bucket": _pt_bucket, "picker": _pt_picker, "line": _pt_line,
    "arrow": _pt_arrow, "dimension": _pt_dimension,
    "protractor": _pt_protractor, "text": _pt_text, "image": _pt_image,
    "group": _pt_group, "ungroup": lambda p: _pt_group(p, True),
    "front": lambda p: _pt_zorder(p, True, True),
    "forward": lambda p: _pt_zorder(p, True, False),
    "backward": lambda p: _pt_zorder(p, False, False),
    "back": lambda p: _pt_zorder(p, False, True),
    "copy": _pt_copy, "paste": _pt_paste, "duplicate": _pt_duplicate,
    "delete": _pt_delete, "grid": _pt_grid, "snap": _pt_snap, "fit": _pt_fit,
    "flip_h": _pt_flip, "flip_v": lambda p: _pt_flip(p, True),
    "rotate": _pt_rotate, "explode": _pt_explode,
    "flowchart": _pt_flowchart, "electrical": _pt_electrical,
    "optics": _pt_optics, "maths": _pt_maths, "arrows": _pt_callout,
    "labware": _pt_labware, "chemistry": _pt_chemistry, "canvas": _pt_canvas,
}


def paint_tool(name: str) -> QIcon:
    """Icon for a drawing-dialog tool or action. Shape tools (rect, circle,
    polygons, arcs…) are drawn from the shape's own geometry."""
    px, p = _paint_canvas()
    fn = _PAINT_TOOLS.get(name)
    if fn is not None:
        fn(p)
    else:
        _pt_shape(p, name)
    p.end()
    return QIcon(px)


def color_swatch(color: str, size: int = 16, *, none: bool = False) -> QIcon:
    """A rounded colour chip; *none* draws the "no colour" red slash."""
    px = QPixmap(size * 2, size * 2)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(2, 2)
    r = QRectF(1, 1, size - 2, size - 2)
    p.setPen(QPen(QColor("#777"), 1))
    p.setBrush(QBrush(QColor("#ffffff") if none else QColor(color)))
    p.drawRoundedRect(r, 3, 3)
    if none:
        p.setPen(QPen(QColor("#d8000c"), 1.6))
        p.drawLine(r.bottomLeft() + QPointF(2, -2), r.topRight() + QPointF(-2, 2))
    p.end()
    return QIcon(px)


def pen_preview(width: float = 2.0, dash: str = "solid", head: str = "",
                length: int = 44) -> QIcon:
    """A short stroke sample for the width / dash / arrowhead pickers."""
    h = 16
    px = QPixmap(length * 2, h * 2)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(2, 2)
    styles = {"solid": Qt.SolidLine, "dash": Qt.DashLine, "dot": Qt.DotLine,
              "dashdot": Qt.DashDotLine}
    pen = QPen(_fg(), min(width, h - 4), styles.get(dash, Qt.SolidLine),
               Qt.FlatCap if dash != "dot" else Qt.RoundCap)
    p.setPen(pen)
    x0, x1 = 3.0, length - 3.0
    if head:
        x1 -= 4
        if head == "double":
            x0 += 4
    p.drawLine(QPointF(x0, h / 2), QPointF(x1, h / 2))
    if head:
        p.setPen(_pen(_fg(), 1.3))

        def tip(x, sign):
            a, b = QPointF(x - sign * 8, h / 2 - 4.5), QPointF(x - sign * 8, h / 2 + 4.5)
            if head == "open":
                p.setBrush(Qt.NoBrush)
                p.drawPolyline(QPolygonF([a, QPointF(x, h / 2), b]))
            elif head == "stealth":
                p.setBrush(QBrush(_fg()))
                p.drawPolygon(QPolygonF([QPointF(x, h / 2), a,
                                         QPointF(x - sign * 5, h / 2), b]))
            else:
                p.setBrush(QBrush(_fg()))
                p.drawPolygon(QPolygonF([QPointF(x, h / 2), a, b]))
        tip(length - 2.0, 1)
        if head == "double":
            tip(2.0, -1)
    p.end()
    return QIcon(px)
