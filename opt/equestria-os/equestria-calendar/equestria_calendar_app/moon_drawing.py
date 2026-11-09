"""Moon rendering primitive, independent of application theme management."""
import math
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath

def draw_moon(p: QPainter, rect: QRectF, f: float, theme: dict, moon_light: str) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme["surface2"]))
    p.drawEllipse(rect)
    c, r = rect.center(), rect.width() / 2
    k = math.cos(2 * math.pi * f)  # 1 — новолуние, -1 — полнолуние
    half = QPainterPath()
    half.moveTo(c.x(), c.y() - r)
    half.arcTo(rect, 90, -180 if f < 0.5 else 180)  # растущая — справа, убывающая — слева
    half.closeSubpath()
    ell = QPainterPath()
    ell.addEllipse(QRectF(c.x() - abs(k) * r, c.y() - r, 2 * abs(k) * r, 2 * r))
    lit = half.united(ell) if k < 0 else half.subtracted(ell)
    p.fillPath(lit, QColor(moon_light))
    p.restore()
