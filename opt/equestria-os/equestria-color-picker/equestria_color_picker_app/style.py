"""color-picker: style."""
from __future__ import annotations

from equestria_kit import qt as kit_qt, themes as kit_themes


KEYS = kit_themes.KEYS


THEMES = kit_themes.THEMES


DEFAULT_THEME = kit_themes.DEFAULT_THEME


THEME: dict = dict(THEMES[DEFAULT_THEME])


QSS = """
QMainWindow, QDialog { background: @base@; }
QWidget { color: @text@; font-size: 15px; }
QLabel { background: transparent; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#h2 { color: @accent@; font-size: 14px; font-weight: 700; }
QLabel#out { font-size: 16px; font-weight: 600; }
QPushButton { background: @surface0@; border: none; border-radius: 10px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @base@; }
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#primary:disabled { background: @surface1@; color: @surface2@; }
QPushButton#small { padding: 6px 12px; font-size: 13px; border-radius: 9px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QLineEdit { background: @surface0@; border: 2px solid transparent; border-radius: 9px;
    padding: 7px 10px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QLineEdit[error="true"] { border-color: @red@; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { background: @surface0@; border-radius: 9px; padding: 7px 12px; margin: 2px 0; }
QListWidget::item:hover { background: @surface1@; }
QListWidget::item:selected { background: @surface1@; color: @text@; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QSlider::groove:horizontal { height: 6px; background: @surface1@; border-radius: 3px; }
QSlider::sub-page:horizontal { background: @accent@; border-radius: 3px; }
QSlider::handle:horizontal { background: @accent@; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
QToolTip { background: @surface1@; color: @text@; border: none; padding: 4px 8px; }
"""


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME)


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)
