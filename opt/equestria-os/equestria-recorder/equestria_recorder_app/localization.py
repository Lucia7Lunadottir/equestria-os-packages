"""Каталог переводов: языки — файлы locales/<код>.json, списка языков в коде нет."""
from pathlib import Path

from equestria_kit import live_i18n

catalog = live_i18n.Catalog("equestria-recorder", Path(__file__).resolve().parents[1] / "equestria_recorder.py")
tr = catalog.tr
