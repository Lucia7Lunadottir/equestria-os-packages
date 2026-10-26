# -*- coding: utf-8 -*-
"""
Общие маленькие виджеты и настройки приложений Equestria OS — то, что раньше
было скопировано в каждый файл (small_btn, card, scrolled, load_config).
Вид задаётся objectName, а цвета — стилем темы (#small, #card, #h2).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLayout, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)


def small_btn(text: str, checkable: bool = False, tip: str = "") -> QPushButton:
    """Маленькая кнопка панели инструментов (#small), не забирает фокус."""
    b = QPushButton(text)
    b.setObjectName("small")
    b.setCheckable(checkable)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if tip:
        b.setToolTip(tip)
    return b


def card(title: str = "", *items, header: QWidget | None = None, upper: bool = False,
         margins: tuple = (18, 14, 18, 14), spacing: int = 8) -> QFrame:
    """Карточка-секция (#card) с заголовком (#h2); items — виджеты или layout'ы.
    Содержимое можно добавлять и потом: card(...).layout().addWidget(...)."""
    c = QFrame()
    c.setObjectName("card")
    v = QVBoxLayout(c)
    v.setContentsMargins(*margins)
    v.setSpacing(spacing)
    if title or header is not None:
        top = QHBoxLayout()
        t = QLabel(title.upper() if upper else title)
        t.setObjectName("h2")
        top.addWidget(t)
        top.addStretch()
        if header is not None:
            top.addWidget(header)
        v.addLayout(top)
    for w in items:
        v.addLayout(w) if isinstance(w, QLayout) else v.addWidget(w)
    return c


def scrolled(widget: QWidget) -> QScrollArea:
    """Прокрутка без рамки вокруг виджета."""
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QFrame.Shape.NoFrame)
    s.setWidget(widget)
    return s


def load_typed_config(path: Path, defaults: dict) -> dict:
    """Настройки из JSON: берётся только то, что совпадает по типу со значением
    по умолчанию (испорченный или старый файл не роняет приложение)."""
    cfg = copy.deepcopy(defaults)
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    if isinstance(raw, dict):
        for k, dv in defaults.items():
            if k in raw and type(raw[k]) is type(dv):
                cfg[k] = raw[k]
    return cfg


def save_config(path: Path, data: dict) -> bool:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(path).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError:
        return False


_font_cache: dict = {}


def load_font(path: str | Path, fallback: str = "sans-serif") -> str:
    """Подключить шрифт из файла (например equestria_cyrillic.ttf) и вернуть
    имя семейства; файла нет или он битый — fallback. Повторно не грузит."""
    key = str(path)
    if key not in _font_cache:
        fam = fallback
        if Path(path).is_file():
            fid = QFontDatabase.addApplicationFont(key)
            fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            if fams:
                fam = fams[0]
        _font_cache[key] = fam
    return _font_cache[key]


def font_families(path: str | Path) -> list:
    """Подключить шрифт из файла и вернуть список его семейств ([] — нет файла)."""
    fam = load_font(path, "")
    return [fam] if fam else []
