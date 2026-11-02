"""Общая библиотека Equestria OS (equestria-qt-kit): темы персонажей и переводы на 10 языков."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    _ROOT = Path(__file__).resolve().parents[2]
    for _p in (_ROOT / "equestria-packages" / "opt" / "equestria-os" / "equestria-qt-kit", _ROOT / "equestria-qt-kit"):
        if _p.is_dir():
            sys.path.insert(0, str(_p))
            break

from PyQt6.QtCore import QLibraryInfo, QLocale, QTranslator
from PyQt6.QtWidgets import QApplication

from equestria_kit import i18n as kit_i18n
from equestria_kit import qt as kit_qt  # noqa: F401 — реэкспорт для theme.py и виджетов

_catalog = kit_i18n.install("equestria-unreal", __file__).__self__
_qt_translator: QTranslator | None = None

# Названия языков — на самих языках, их не переводят
LANGUAGES = (("ru", "Русский"), ("en", "English"), ("de", "Deutsch"), ("fr", "Français"), ("es", "Español"),
             ("pt", "Português"), ("pl", "Polski"), ("uk", "Українська"), ("zh", "简体中文"), ("zh_TW", "繁體中文"),
             ("ja", "日本語"), ("ko", "한국어"))


def tr(text: str, *args, **kwargs) -> str:
    return _catalog.tr(text, *args, **kwargs)


def set_language(code: str) -> str:
    """code — один из LANGUAGES или '' (как в системе). Возвращает действующий язык.
    Заодно переводит стандартные кнопки Qt (Да/Нет/Отмена в QMessageBox)."""
    global _qt_translator
    lang = code if code in dict(LANGUAGES) else kit_i18n.detect_language()
    _catalog.lang = lang
    app = QApplication.instance()
    if app is not None:
        if _qt_translator is not None:
            app.removeTranslator(_qt_translator)
        _qt_translator = QTranslator(app)
        if _qt_translator.load(QLocale(lang), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            app.installTranslator(_qt_translator)
    return lang
