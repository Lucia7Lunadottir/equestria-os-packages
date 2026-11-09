"""color-picker: widgets."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QLineEdit, QSizePolicy, QWidget


class SVBox(QWidget):
    changed = pyqtSignal(float, float)

    def __init__(self):
        super().__init__()
        self.h, self.s, self.v = 0.0, 1.0, 1.0
        self.setMinimumSize(240, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_hsv(self, h, s, v):
        self.h, self.s, self.v = h, s, v
        self.update()

    def _rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(2, 2, -2, -2)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._rect()
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        p.setClipPath(path)
        p.fillRect(r, QColor.fromHsvF(min(self.h, 0.9999), 1, 1))
        g = QLinearGradient(r.left(), 0, r.right(), 0)
        g.setColorAt(0, QColor(255, 255, 255))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(r, g)
        g2 = QLinearGradient(0, r.top(), 0, r.bottom())
        g2.setColorAt(0, QColor(0, 0, 0, 0))
        g2.setColorAt(1, QColor(0, 0, 0))
        p.fillRect(r, g2)
        p.setClipping(False)
        pt = QPointF(r.left() + self.s * r.width(), r.top() + (1 - self.v) * r.height())
        p.setPen(QPen(QColor(0, 0, 0, 170), 1))
        p.drawEllipse(pt, 8.5, 8.5)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawEllipse(pt, 7, 7)

    def _pick(self, e):
        r = self._rect()
        pos = e.position()
        self.s = min(max((pos.x() - r.left()) / r.width(), 0.0), 1.0)
        self.v = 1 - min(max((pos.y() - r.top()) / r.height(), 0.0), 1.0)
        self.update()
        self.changed.emit(self.s, self.v)

    mousePressEvent = _pick
    mouseMoveEvent = _pick


class HueBar(QWidget):
    changed = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.h = 0.0
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_hue(self, h):
        self.h = h
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 4, -2, -4)
        g = QLinearGradient(r.left(), 0, r.right(), 0)
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF(min(i / 6, 0.9999), 1, 1))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, 7, 7)
        x = r.left() + self.h * r.width()
        p.setPen(QPen(QColor(0, 0, 0, 170), 1))
        p.setBrush(QColor.fromHsvF(min(self.h, 0.9999), 1, 1))
        p.drawEllipse(QPointF(x, self.height() / 2), 9, 9)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawEllipse(QPointF(x, self.height() / 2), 8, 8)

    def _pick(self, e):
        r = QRectF(self.rect()).adjusted(2, 4, -2, -4)
        self.h = min(max((e.position().x() - r.left()) / r.width(), 0.0), 1.0)
        self.update()
        self.changed.emit(self.h)

    mousePressEvent = _pick
    mouseMoveEvent = _pick


class Swatch(QWidget):
    def __init__(self):
        super().__init__()
        self.color = QColor("#cba6f7")
        self.setFixedHeight(86)

    def set_color(self, c: QColor):
        self.color = c
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        p.setClipPath(path)
        sz = 10
        for y in range(0, self.height(), sz):
            for x in range(0, self.width(), sz):
                p.fillRect(x, y, sz, sz, QColor("#bdbdbd") if (x // sz + y // sz) % 2 == 0 else QColor("#ffffff"))
        p.fillRect(self.rect(), self.color)


def flag(edit: QLineEdit, bad: bool) -> None:
    edit.setProperty("error", bad)
    edit.style().unpolish(edit)
    edit.style().polish(edit)
