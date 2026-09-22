"""Generate the ElectroMind app icon (brain-circuit theme).

Draws the icon with QPainter and saves:
    assets/icon.ico   (multi-size, for the window/taskbar)
    assets/icon.png   (256x256, for README/docs)

Run:  python make_icon.py
"""
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (QGuiApplication, QIcon, QPainter, QPen, QBrush,
                         QColor, QFont, QPixmap, QLinearGradient, QPainterPath)

ASSETS = Path(__file__).parent / "assets"

# theme colors
BG_DARK = QColor("#101826")
BG_LIGHT = QColor("#1b2a44")
BLUE = QColor("#3d8bff")
CYAN = QColor("#39d8e8")
AMBER = QColor("#ffb648")
NODE = QColor("#7fd0ff")


def draw_icon(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 256.0  # design in a 256x256 coordinate space

    # ---- rounded background with gradient
    grad = QLinearGradient(0, 0, 256 * s, 256 * s)
    grad.setColorAt(0.0, BG_LIGHT)
    grad.setColorAt(1.0, BG_DARK)
    p.setBrush(QBrush(grad))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(0, 0, 256 * s, 256 * s), 52 * s, 52 * s)

    # ---- "brain" half: circuit traces (left hemisphere)
    pen = QPen(BLUE, 7 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
               Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    def trace(points, color=BLUE, width=7.0):
        pen.setColor(color)
        pen.setWidthF(width * s)
        p.setPen(pen)
        path = QPainterPath(QPointF(points[0][0] * s, points[0][1] * s))
        for x, y in points[1:]:
            path.lineTo(x * s, y * s)
        p.drawPath(path)

    # main trace from center to the left edge with turns
    trace([(126, 128), (86, 128), (66, 108), (66, 74), (46, 54)])
    trace([(126, 140), (92, 140), (74, 158), (44, 158)])
    trace([(126, 116), (98, 116), (80, 92), (80, 58)])
    trace([(126, 152), (104, 152), (88, 174), (88, 198)], color=CYAN)

    # ---- "circuit" half: right-angled traces (right hemisphere)
    trace([(130, 128), (172, 128), (192, 108), (192, 66), (212, 46)], color=CYAN)
    trace([(130, 140), (166, 140), (184, 158), (212, 158)])
    trace([(130, 116), (158, 116), (176, 92), (176, 58)], color=CYAN)
    trace([(130, 152), (152, 152), (168, 174), (168, 198)], color=AMBER)

    # ---- solder pads / nodes
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(NODE))
    for x, y in [(46, 54), (44, 158), (80, 58), (88, 198)]:
        p.drawEllipse(QPointF(x * s, y * s), 9 * s, 9 * s)
    p.setBrush(QBrush(CYAN))
    for x, y in [(212, 46), (212, 158), (176, 58), (168, 198)]:
        p.drawEllipse(QPointF(x * s, y * s), 9 * s, 9 * s)
    p.setBrush(QBrush(AMBER))
    p.drawEllipse(QPointF(168 * s, 198 * s), 9 * s, 9 * s)

    # ---- central chip (the "mind")
    p.setBrush(QBrush(QColor("#0d1420")))
    pen.setColor(QColor("#e8f4ff"))
    pen.setWidthF(6 * s)
    p.setPen(pen)
    chip = QRectF(104 * s, 104 * s, 48 * s, 48 * s)
    p.drawRoundedRect(chip, 10 * s, 10 * s)
    p.setBrush(QBrush(BLUE))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(128 * s, 128 * s), 11 * s, 11 * s)

    p.end()
    return pm


def main():
    import sys
    app = QGuiApplication(sys.argv)
    ASSETS.mkdir(exist_ok=True)

    pm256 = draw_icon(256)
    png_path = ASSETS / "icon.png"
    pm256.save(str(png_path), "PNG")
    print(f"saved {png_path}")

    # multi-size .ico: Windows picks the best size for window/taskbar/alt-tab
    ico = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ico.addPixmap(draw_icon(size))
    ico_path = ASSETS / "icon.ico"
    with open(ico_path, "wb") as f:
        data = bytes(ico.pixmap(256, 256).toImage().bitPlaneCount())  # noqa: F841
    # QIcon can't write .ico directly; write via pixmap save loop supported by Qt:
    ok = pm256.scaled(256, 256).save(str(ico_path), "ICO")
    if ok:
        print(f"saved {ico_path}")
    else:
        print("ICO save failed - PNG only")
    app.quit()


if __name__ == "__main__":
    main()
