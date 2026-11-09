"""Оформление: цвета темы и QSS."""
from __future__ import annotations

from ._kit import kit_qt, kit_themes

# Темы общие для всех приложений Equestria OS: см. equestria_kit/themes.py.
# Свои темы — файлы ~/.config/equestria-os/themes/*.json.
THEME: dict = dict(kit_themes.THEMES[kit_themes.DEFAULT_THEME])

QSS = """
QMainWindow { background: @base@; }
QWidget { color: @text@; font-size: 15px; }
QLabel { background: transparent; }
QLabel#h2 { color: @accent@; font-size: 13px; font-weight: 700; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#warn { color: @red@; font-size: 13px; font-weight: 700; }
QLabel#preview { background: @mantle@; color: @subtext@; border-radius: 10px; }
QFrame#card { background: @mantle@; border-radius: 14px; }
QPushButton { background: @surface0@; border: none; border-radius: 12px;
    padding: 10px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @base@; font-size: 17px; padding: 14px; }
QPushButton#primary:hover { background: @accent@; }
QPushButton#primary:disabled { background: @surface1@; color: @surface2@; }
QPushButton#small { padding: 6px 14px; font-size: 13px; border-radius: 10px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QPushButton#mode { padding: 10px 16px; border-radius: 12px; }
QPushButton#mode:checked { background: @accent@; color: @base@; }
QLineEdit, QDoubleSpinBox { background: @surface0@; border: 2px solid transparent; border-radius: 10px;
    padding: 8px 12px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus, QDoubleSpinBox:focus { border-color: @accent@; }
QLineEdit[error="true"] { border-color: @red@; }
QComboBox { padding: 6px 10px; }
QComboBox QAbstractItemView { background: @surface0@; color: @text@; outline: 0;
    selection-background-color: @surface1@; selection-color: @text@; }
QListWidget { background: @surface0@; border: none; border-radius: 10px; outline: 0; padding: 4px; }
QListWidget::item { background: transparent; border-radius: 6px; padding: 6px 8px; }
QListWidget::item:selected { background: @surface1@; color: @accent@; }
QProgressBar { background: @surface0@; border: none; border-radius: 6px; min-height: 12px; max-height: 12px; }
QProgressBar::chunk { background: @accent@; border-radius: 6px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
"""

_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME)


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)
