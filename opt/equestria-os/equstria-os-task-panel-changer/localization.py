"""Строки интерфейса из locales/<язык>.json (ключ -> текст) через общий каталог equestria_kit."""
from __future__ import annotations

from equestria_kit import live_i18n


class Localizer:
    def __init__(self, path: str = ""):  # path оставлен для совместимости, переводы ищутся рядом с этим файлом
        self.catalog = live_i18n.Catalog("equestria-os-task-panel-changer", __file__)
        # языки — найденные файлы locales/*.json, без списка в коде
        self.languages: list[str] = list(self.catalog.languages)

    @property
    def lang(self) -> str:
        return self.catalog.lang

    @lang.setter
    def lang(self, code: str) -> None:
        self.catalog.set_language(code)  # ещё и сохраняет выбор

    def has(self, key: str) -> bool:
        return any(key in rows for rows in self.catalog.translations.values())

    def t(self, key: str, *args) -> str:
        text = str(self.catalog.tr(key))
        for i, arg in enumerate(args):
            text = text.replace("{%d}" % i, str(arg))
        return text
