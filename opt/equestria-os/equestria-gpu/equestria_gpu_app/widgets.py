"""gpu: widgets."""
from __future__ import annotations

import re
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QLabel
from equestria_kit import qt as kit_qt
from equestria_kit.widgets import card as _card
from .localization import live_i18n


def card(title: str = ""):
    """Карточка + её layout (так удобнее строить страницы этого приложения)."""
    f = _card(title)
    return f, f.layout()


def lvl_color(lvl: str) -> str:
    # цвета текущей темы — и в отдельном окне, и внутри «Настроек»
    return kit_qt.theme_color({"ok": "green", "warn": "yellow", "fail": "red"}.get(lvl, "subtext")).name()


def dot_icon(lvl: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(lvl_color(lvl)))
    p.drawEllipse(1, 1, 12, 12)
    p.end()
    return QIcon(pm)


def lvl_label(text: str, lvl: str, name: str = "chip") -> QLabel:
    lab = live_i18n.call(QLabel, text)
    lab.setObjectName(name)
    lab.setProperty("lvl", lvl)
    return lab


def clean_line(s: str) -> str:
    s = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)
    return s.split("\r")[-1] if "\r" in s else s
