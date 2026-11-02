# -*- coding: utf-8 -*-
"""
Локализация Equestria-приложений на 12 языков.

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

# zh — упрощённый китайский, zh_TW — традиционный (Тайвань, Гонконг, Макао)
LANGS = ("en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "zh_TW", "ja", "ko")
SOURCE_LANG = "ru"
# Названия языков — на самих языках, их не переводят
LANGUAGE_NAMES = {
    "en": "English", "ru": "Русский", "de": "Deutsch", "fr": "Français", "es": "Español",
    "pt": "Português", "pl": "Polski", "uk": "Українська", "zh": "简体中文", "zh_TW": "繁體中文",
    "ja": "日本語", "ko": "한국어",
}
_TRADITIONAL = ("zh_tw", "zh_hk", "zh_mo", "zh_hant", "zh-tw", "zh-hk", "zh-mo", "zh-hant")


def normalize(locale_name: str) -> str:
    """«zh_TW.UTF-8», «zh-Hant-HK», «ko_KR» … → код из LANGS («» — язык не поддерживается).
    Просто взять первые две буквы нельзя: zh_TW превратился бы в упрощённый китайский."""
    name = (locale_name or "").split(":")[0].split(".")[0].split("@")[0].strip().lower()
    if name.startswith(_TRADITIONAL):
        return "zh_TW"
    code = name[:2]
    return code if code in LANGS else ""


def detect_language() -> str:
    for env in ("EQUESTRIA_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        for part in (os.environ.get(env) or "").split(":"):
            code = normalize(part)
            if code:
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
                # традиционного китайского нет — лучше упрощённый, чем английский
                fallback = row.get("zh") if self.lang == "zh_TW" else None
                out = row.get(self.lang) or fallback or row.get("en") or text
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
