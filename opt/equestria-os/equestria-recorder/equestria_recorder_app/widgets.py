"""Виджеты диктофона: карточка, подтверждение, индикатор уровня, волна с маркерами."""
from __future__ import annotations

from functools import partial

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QMessageBox, QWidget

from equestria_kit import live_i18n, widgets as kit_widgets

from .localization import tr
from .style import THEME

card = partial(kit_widgets.card, upper=True, margins=(16, 10, 16, 12), spacing=6)


def confirm(parent, text: str, yes: str) -> bool:
    box = QMessageBox(parent)
    live_i18n.call(box.setWindowTitle, tr("widgets.confirmation"))
    live_i18n.call(box.setText, text)
    ok = live_i18n.call(box.addButton, yes, QMessageBox.ButtonRole.AcceptRole)
    live_i18n.call(box.addButton, tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is ok


class LevelMeter(QWidget):
    """Полоса громкости с плавным спадом и отметкой пика."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(26)
        self.target = self.level = self.peak = 0.0
        self.hold = 0
        t = QTimer(self)
        t.setInterval(30)
        t.timeout.connect(self._tick)
        t.start()

    def set_level(self, lv: float) -> None:
        self.target = max(self.target, lv)

    def _tick(self) -> None:
        self.level = self.target if self.target > self.level else max(self.target, self.level - 0.04)
        self.target = 0.0
        if self.level >= self.peak:
            self.peak, self.hold = self.level, 30
        elif self.hold > 0:
            self.hold -= 1
        else:
            self.peak = max(self.level, self.peak - 0.015)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(THEME["surface0"]))
        p.drawRoundedRect(r, 8, 8)
        w = r.width() * self.level
        if w > 1:
            g = QLinearGradient(0, 0, r.width(), 0)
            g.setColorAt(0.0, QColor(THEME["green"]))
            g.setColorAt(0.7, QColor(THEME["green"]))
            g.setColorAt(0.85, QColor(THEME["yellow"]))
            g.setColorAt(1.0, QColor(THEME["red"]))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(0, 0, w, r.height()), 8, 8)
        if self.peak > 0.02:
            p.setBrush(QColor(THEME["text"]))
            p.drawRoundedRect(QRectF(r.width() * self.peak - 2, 3, 3, r.height() - 6), 1.5, 1.5)


class Waveform(QWidget):
    """Волна звука с двумя маркерами (начало и конец выделения)."""
    changed = pyqtSignal()
    PAD = 10
    GAP = 0.002

    def __init__(self, peaks):
        super().__init__()
        self.peaks = peaks
        self.s, self.e = 0.0, 1.0
        self.cut = False
        self.play = None
        self.drag = None
        self.setMinimumHeight(130)
        self.setCursor(Qt.CursorShape.SplitHCursor)

    def set_range(self, s: float, e: float) -> None:
        s = max(0.0, min(s, e - self.GAP))
        e = min(1.0, max(e, s + self.GAP))
        self.s, self.e = s, e
        self.update()

    def _x(self, f: float) -> float:
        return self.PAD + f * (self.width() - 2 * self.PAD)

    def _f(self, x: float) -> float:
        return max(0.0, min(1.0, (x - self.PAD) / max(1, self.width() - 2 * self.PAD)))

    def _move(self, f: float) -> None:
        if self.drag == "s":
            self.set_range(f, self.e)
        else:
            self.set_range(self.s, f)
        self.changed.emit()

    def mousePressEvent(self, ev) -> None:
        f = self._f(ev.position().x())
        self.drag = "s" if abs(f - self.s) <= abs(f - self.e) else "e"
        self._move(f)

    def mouseMoveEvent(self, ev) -> None:
        if self.drag:
            self._move(self._f(ev.position().x()))

    def mouseReleaseEvent(self, ev) -> None:
        self.drag = None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(THEME["mantle"]))
        p.drawRoundedRect(QRectF(0, 0, W, H), 10, 10)
        n, span, mid = len(self.peaks), W - 2 * self.PAD, H / 2
        pen = QPen()
        pen.setWidthF(max(1.0, span / n * 0.7))
        for i, pk in enumerate(self.peaks):
            f = (i + 0.5) / n
            kept = (self.s <= f <= self.e) != self.cut
            pen.setColor(QColor(THEME["accent"] if kept else THEME["surface2"]))
            p.setPen(pen)
            hh = max(1.0, pk * (mid - 10))
            x = self.PAD + f * span
            p.drawLine(QPointF(x, mid - hh), QPointF(x, mid + hh))
        col = QColor(THEME["red"] if self.cut else THEME["accent"])
        col.setAlpha(50)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRect(QRectF(self._x(self.s), 0, self._x(self.e) - self._x(self.s), H))
        p.setPen(QPen(QColor(THEME["text"]), 2))
        p.setBrush(QColor(THEME["text"]))
        for f in (self.s, self.e):
            x = self._x(f)
            p.drawLine(QPointF(x, 0), QPointF(x, H))
            p.drawEllipse(QPointF(x, 9), 6, 6)
            p.drawEllipse(QPointF(x, H - 9), 6, 6)
        if self.play is not None:
            p.setPen(QPen(QColor(THEME["yellow"]), 2))
            x = self._x(max(0.0, min(1.0, self.play)))
            p.drawLine(QPointF(x, 0), QPointF(x, H))
