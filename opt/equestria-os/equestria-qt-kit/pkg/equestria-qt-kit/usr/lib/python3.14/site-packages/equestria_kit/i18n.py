# -*- coding: utf-8 -*-
"""
Локализация Equestria-приложений на 10 языков.

В коде строки пишутся по-русски и оборачиваются в tr():
    tr("Обновить")            → "Refresh" / "Aktualisieren" / ...
    tr("Найдено: {}", n)      → подстановка через str.format

Переводы лежат в одном файле i18n.json рядом с приложением
(после установки — /usr/share/<app>/i18n.json):
    {"Обновить": {"en": "Refresh", "de": "Aktualisieren", ...}, ...}
Нет перевода на нужный язык → английский → исходная русская строка.

Язык: EQUESTRIA_LANG, затем LANGUAGE / LC_ALL / LC_MESSAGES / LANG; иначе английский.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

LANGS = ("en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja")
SOURCE_LANG = "ru"


def detect_language() -> str:
    for env in ("EQUESTRIA_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        code = (os.environ.get(env) or "").split(":")[0][:2].lower()
        if code in LANGS:
            return code
    return "en"


class Catalog:
    """Переводы одного приложения."""

    def __init__(self, entries: dict, lang: str):
        self.entries = entries
        self.lang = lang

    @classmethod
    def load(cls, candidates: list, lang: str | None = None) -> "Catalog":
        for path in candidates:
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                return cls(data, lang or detect_language())
        return cls({}, lang or detect_language())

    def tr(self, text: str, *args, **kwargs) -> str:
        out = text
        if self.lang != SOURCE_LANG:
            row = self.entries.get(text)
            if isinstance(row, dict):
                out = row.get(self.lang) or row.get("en") or text
        if args or kwargs:
            try:
                return out.format(*args, **kwargs)
            except (IndexError, KeyError, ValueError):
                return text.format(*args, **kwargs)
        return out


def install(app_id: str, script_file: str, lang: str | None = None):
    """Загрузить i18n.json приложения и вернуть функцию tr."""
    here = Path(script_file).resolve().parent
    # рядом со скриптом (запуск из исходников), затем каталоги данных XDG
    data_dirs = (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    catalog = Catalog.load([here / "i18n.json"] + [Path(d) / app_id / "i18n.json" for d in data_dirs if d], lang)
    return catalog.tr
