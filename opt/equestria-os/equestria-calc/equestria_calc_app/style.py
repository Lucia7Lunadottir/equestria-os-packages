"""calc: style."""
from __future__ import annotations

from equestria_kit import qt as kit_qt, themes as kit_themes


KEYS = kit_themes.KEYS


THEMES = kit_themes.THEMES


DEFAULT_THEME = kit_themes.DEFAULT_THEME


THEME: dict = dict(THEMES[DEFAULT_THEME])


QSS = """
QMainWindow { background: @base@; }
QWidget { color: @text@; font-size: 18px; }
QLabel { background: transparent; }
QLabel#expr { color: @subtext@; font-size: 18px; }
QLabel#result { font-size: 44px; font-weight: 700; color: @accent@; }
QLabel#result[error="true"] { color: @red@; }
QLabel#hint { color: @subtext@; font-size: 15px; }
QLabel#h2 { color: @accent@; font-size: 15px; font-weight: 700; }
QLabel#out { font-size: 20px; font-weight: 600; }
QPushButton { background: @surface0@; border: none; border-radius: 12px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#num { background: @mantle@; }
QPushButton#num:hover { background: @surface0@; }
QPushButton#fn { background: @mantle@; color: @subtext@; font-size: 15px; }
QPushButton#fn:hover { background: @surface0@; }
QPushButton#op { color: @accent@; }
QPushButton#eq { background: @accent@; color: @base@; }
QPushButton#eq:hover { background: @accent_hover@; }
QPushButton#clr { color: @red@; }
QPushButton#small { padding: 6px 14px; font-size: 14px; border-radius: 10px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QPushButton#row { background: transparent; text-align: left; padding: 6px 12px;
    border-radius: 8px; font-size: 15px; }
QPushButton#row:hover { background: @surface0@; }
QPushButton#row:checked { background: @surface0@; color: @accent@; }
QLineEdit { background: @surface0@; border: 2px solid transparent; border-radius: 10px;
    padding: 8px 12px; font-size: 20px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QLineEdit[error="true"] { border-color: @red@; }
QListWidget { background: transparent; border: none; outline: 0; font-size: 15px; }
QListWidget::item { background: @surface0@; border-radius: 8px; padding: 8px 12px; margin: 3px 0; }
QListWidget::item:hover { background: @surface1@; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
QToolTip { background: @surface1@; color: @text@; border: none; padding: 4px 8px; }
"""


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME)


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)
