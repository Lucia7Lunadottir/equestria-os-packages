"""Подключение equestria_kit (общая библиотека Equestria OS) и перевод tr()."""
from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "equestria-qt-kit"))

from equestria_kit import qt as kit_qt
from equestria_kit import themes as kit_themes
from equestria_kit import widgets as kit_widgets

from .localization import catalog

tr = catalog.tr

card = partial(kit_widgets.card, upper=True, margins=(16, 10, 16, 12), spacing=6)
small_btn = kit_widgets.small_btn
