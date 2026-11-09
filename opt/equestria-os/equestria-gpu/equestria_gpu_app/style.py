"""gpu: style."""
from __future__ import annotations

from equestria_kit import qt as kit_qt, themes as kit_themes


KEYS = kit_themes.KEYS


THEMES = kit_themes.THEMES


DEFAULT_THEME = kit_themes.DEFAULT_THEME


THEME: dict = dict(THEMES[DEFAULT_THEME])


QSS = """
QMainWindow, QDialog { background: @base@; }
QWidget { color: @text@; font-size: 14px; }
QLabel { background: transparent; }
QLabel#title { font-size: 17px; font-weight: 700; color: @accent@; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#h2 { color: @accent@; font-size: 14px; font-weight: 700; }
QLabel#rowname { font-size: 15px; font-weight: 600; }
QLabel#out { font-size: 16px; font-weight: 600; }
QLabel#dot { font-size: 18px; color: @subtext@; }
QLabel#dot[lvl="ok"] { color: @green@; }
QLabel#dot[lvl="warn"] { color: @yellow@; }
QLabel#dot[lvl="fail"] { color: @red@; }
QLabel#chip { background: @surface0@; border-radius: 10px; padding: 5px 12px; font-weight: 600; color: @subtext@; }
QLabel#chip[lvl="ok"] { color: @green@; }
QLabel#chip[lvl="warn"] { color: @yellow@; }
QLabel#chip[lvl="fail"] { color: @red@; }

QTabWidget::pane { border: none; }
QTabBar { background: transparent; }
QTabBar::tab { background: transparent; color: @subtext@; padding: 9px 20px; border: none;
    border-bottom: 3px solid transparent; font-size: 15px; font-weight: 600; }
QTabBar::tab:selected { color: @accent@; border-bottom: 3px solid @accent@; }
QTabBar::tab:hover:!selected { color: @text@; }

QPushButton { background: @surface0@; border: none; border-radius: 10px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @base@; }
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#primary:disabled { background: @surface1@; color: @surface2@; }
QPushButton#small { padding: 6px 12px; font-size: 13px; border-radius: 9px; }

QFrame#card { background: @surface0@; border-radius: 14px; }
QCheckBox { spacing: 10px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; background: @mantle@; border: 2px solid @surface2@; }
QCheckBox::indicator:checked { background: @accent@; border-color: @accent@; image: url("@icon:check_mark@"); }
QCheckBox::indicator:disabled { background: @mantle@; border-color: @surface1@; }
QCheckBox:disabled { color: @surface2@; }

QLineEdit { background: @mantle@; border: 2px solid transparent; border-radius: 9px; padding: 8px 12px;
    selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QPlainTextEdit { background: @crust@; border: none; border-radius: 10px; padding: 8px;
    selection-background-color: @accent@; selection-color: @base@; font-size: 13px; }

QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { background: @surface0@; border-radius: 10px; padding: 8px 10px; margin: 3px 0; }
QListWidget::item:hover { background: @surface1@; }
QListWidget::item:selected { background: @surface2@; color: @text@; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
QToolTip { background: @surface1@; color: @text@; border: none; padding: 4px 8px; }
"""


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME)


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)
