"""Переводы Equestria OS Proton Starter — один каталог на все три программы
(настройки, запуск .exe, очистка кэша).

Тексты лежат в locales/<язык>.json рядом с этим файлом: ключ -> перевод.
Язык выбирается автоматически и запоминается после выбора в списке языков.
"""
import os
import sys

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import live_i18n

SYSTEM_PATH = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
CATALOG = live_i18n.Catalog("equestria-os-proton-starter", os.path.join(SYSTEM_PATH, "proton_i18n.py"))


def current_lang() -> str:
    return CATALOG.lang or "en"


def set_language(code: str) -> str:
    """Переключить язык (и запомнить выбор); вернуть код выбранного языка."""
    return CATALOG.set_language(code) or code


def t(key: str, *args) -> str:
    """Перевод по ключу; {0}, {1}… заменяются на args."""
    text = str(CATALOG.tr(key))
    for i, val in enumerate(args):
        text = text.replace("{%d}" % i, str(val))
    return text
