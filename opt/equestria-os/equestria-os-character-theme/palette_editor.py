"""Предпросмотр палитры персонажа для редактора: два маленьких «окна» — ночь и день.

Рисуется теми же ролями KDE, по которым пишется настоящая цветовая схема
(kde_laf.kde_roles), поэтому предпросмотр не расходится с тем, что получится в Dolphin."""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

import kde_laf
import palette_model


def _c(hex_color: str) -> QColor:
    return QColor(hex_color)


class PalettePreview(QWidget):
    """Миниатюра файлового менеджера: заголовок, боковая панель, область просмотра со
    строками (обычная / выделенная / неактивная), кнопка, ссылка и подсказка."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._roles: dict = {}
        self._titles = {"Dark": "Night", "Light": "Day"}

    def set_titles(self, night: str, day: str) -> None:
        self._titles = {"Dark": night, "Light": day}
        self.update()

    def set_character(self, character: dict) -> None:
        """character — словарь персонажа (с UiPalette и AccentColor)."""
        self._roles = {v: kde_laf.character_roles(character, v) for v in ("Dark", "Light")}
        self.update()

    # ---- рисование
    def paintEvent(self, _event) -> None:
        if not self._roles:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gap = 12
        w = (self.width() - gap) / 2
        for i, variant in enumerate(("Dark", "Light")):
            self._draw_window(p, QRectF(i * (w + gap), 0, w, self.height()), self._roles[variant], variant)
        p.end()

    def _draw_window(self, p: QPainter, r: QRectF, roles: dict, variant: str) -> None:
        win, view, btn = roles["Window"], roles["View"], roles["Button"]
        sel, head, tip = roles["Selection"], roles["Header"], roles["Tooltip"]
        font = QFont(self.font())
        font.setPixelSize(12)
        p.setFont(font)

        p.save()
        path_clip = QRectF(r)
        p.setClipRect(path_clip)
        p.setPen(Qt.PenStyle.NoPen)
        # заголовок окна
        title_h = 24
        p.setBrush(_c(head["BackgroundNormal"]))
        p.drawRect(QRectF(r.x(), r.y(), r.width(), title_h))
        p.setPen(_c(head["ForegroundNormal"]))
        p.drawText(QRectF(r.x() + 10, r.y(), r.width() - 20, title_h),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._titles[variant])
        body = QRectF(r.x(), r.y() + title_h, r.width(), r.height() - title_h)
        # боковая панель = фон окна
        side_w = body.width() * 0.32
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_c(win["BackgroundNormal"]))
        p.drawRect(QRectF(body.x(), body.y(), side_w, body.height()))
        p.setPen(_c(win["ForegroundInactive"]))
        p.drawText(QRectF(body.x() + 8, body.y() + 8, side_w - 12, 16), Qt.AlignmentFlag.AlignLeft, "• • •")
        p.setPen(_c(win["ForegroundNormal"]))
        p.drawText(QRectF(body.x() + 8, body.y() + 28, side_w - 12, 16), Qt.AlignmentFlag.AlignLeft, "Aa Bb")
        p.setPen(_c(win["ForegroundLink"]))
        p.drawText(QRectF(body.x() + 8, body.y() + 48, side_w - 12, 16), Qt.AlignmentFlag.AlignLeft, "link")
        # область просмотра
        vx = body.x() + side_w
        vw = body.width() - side_w
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_c(view["BackgroundNormal"]))
        p.drawRect(QRectF(vx, body.y(), vw, body.height()))
        rows = ((view["ForegroundNormal"], None), (sel["ForegroundNormal"], sel["BackgroundNormal"]),
                (view["ForegroundInactive"], None))
        for n, (fg, bg) in enumerate(rows):
            row = QRectF(vx + 6, body.y() + 8 + n * 24, vw - 12, 20)
            if bg:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_c(bg))
                p.drawRoundedRect(row, 4, 4)
            p.setPen(_c(fg))
            p.drawText(row.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       ("Text", "Selected", "Inactive")[n])
        # кнопка с рамкой фокуса
        b = QRectF(vx + 6, body.bottom() - 34, 70, 24)
        p.setBrush(_c(btn["BackgroundNormal"]))
        p.setPen(QPen(_c(btn["DecorationFocus"]), 1.5))
        p.drawRoundedRect(b, 5, 5)
        p.setPen(_c(btn["ForegroundNormal"]))
        p.drawText(b, Qt.AlignmentFlag.AlignCenter, "OK")
        # подсказка
        t = QRectF(vx + 84, body.bottom() - 34, vw - 90, 24)
        p.setBrush(_c(tip["BackgroundNormal"]))
        p.setPen(QPen(_c(tip["ForegroundInactive"]), 0.8))
        p.drawRoundedRect(t, 4, 4)
        p.setPen(_c(tip["ForegroundNormal"]))
        p.drawText(t, Qt.AlignmentFlag.AlignCenter, "tooltip")
        p.restore()
        # тонкая рамка окна, чтобы светлая миниатюра не сливалась с фоном
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(128, 128, 128, 90), 1))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
