"""Тема диктофона: роли общей темы Equestria OS (equestria_kit/themes.py) и QSS-шаблон."""
from __future__ import annotations

from equestria_kit import qt as kit_qt, themes as kit_themes

KEYS = kit_themes.KEYS
THEMES = kit_themes.THEMES
DEFAULT_THEME = kit_themes.DEFAULT_THEME
# Текущие цвета; ThemeApplier обновляет словарь на месте — paintEvent читает его напрямую
THEME: dict = dict(THEMES[DEFAULT_THEME])

QSS = """
QMainWindow, QDialog { background: @base@; }
QWidget { color: @text@; font-size: 15px; }
QLabel { background: transparent; }
QLabel#time { font-size: 48px; font-weight: 700; }
QLabel#h2 { color: @accent@; font-size: 13px; font-weight: 700; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#db { color: @subtext@; min-width: 64px; }
QLabel#warn { color: @red@; font-weight: 700; font-size: 13px; }
QFrame#card { background: @mantle@; border-radius: 14px; }
QPushButton { background: @surface0@; border: none; border-radius: 12px;
    padding: 10px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#rec { background: @red@; color: @base@; font-size: 17px; padding: 14px; }
QPushButton#rec:hover { background: @red@; }
QPushButton#rec:disabled { background: @surface1@; color: @surface2@; }
QPushButton#primary { background: @accent@; color: @base@; }
QPushButton#primary:hover { background: @accent@; }
QPushButton#small { padding: 6px 14px; font-size: 13px; border-radius: 10px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QLineEdit { background: @surface0@; border: 2px solid transparent; border-radius: 10px;
    padding: 8px 12px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QComboBox { padding: 6px 10px; }
QComboBox QAbstractItemView { background: @surface0@; color: @text@; outline: 0;
    selection-background-color: @surface1@; selection-color: @text@; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { background: @surface0@; border-radius: 8px; padding: 8px 12px; margin: 2px 0; }
QListWidget::item:selected { background: @surface1@; color: @accent@; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSlider::groove:horizontal { height: 6px; background: @surface1@; border-radius: 3px; }
QSlider::sub-page:horizontal { background: @accent@; border-radius: 3px; }
QSlider::handle:horizontal { background: @accent@; width: 16px; height: 16px;
    margin: -5px 0; border-radius: 8px; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
"""


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME)


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)
