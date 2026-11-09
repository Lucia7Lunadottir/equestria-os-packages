"""closer: style."""
from __future__ import annotations

from PyQt6.QtGui import QColor
from equestria_kit import qt as kit_qt, themes as kit_themes


KEYS = kit_themes.KEYS


THEMES = kit_themes.THEMES


DEFAULT_THEME = kit_themes.DEFAULT_THEME


THEME: dict = dict(THEMES[DEFAULT_THEME])


QSS = """
QMainWindow, QDialog, QMessageBox { background: @base@; }
QWidget { color: @text@; font-size: 15px; }
QLabel { background: transparent; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#h2 { color: @accent@; font-size: 14px; font-weight: 700; }
QLabel#out { font-size: 18px; font-weight: 700; }
QPushButton { background: @surface0@; border: none; border-radius: 10px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @base@; }
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#primary:disabled { background: @surface1@; color: @surface2@; }
QPushButton#danger { background: @red@; color: @base@; }
QPushButton#danger:hover { background: @red_hover@; }
QPushButton#danger:disabled { background: @surface1@; color: @surface2@; }
QPushButton#small { padding: 6px 12px; font-size: 13px; border-radius: 9px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QLineEdit { background: @surface0@; border: 2px solid transparent; border-radius: 9px;
    padding: 7px 10px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { background: @surface0@; border-radius: 9px; padding: 7px 12px; margin: 2px 0; }
QListWidget::item:hover { background: @surface1@; }
QListWidget::item:selected { background: @surface2@; color: @text@; }
QTreeWidget { background: @mantle@; border: none; border-radius: 10px; padding: 4px; outline: 0; }
QTreeWidget::item { padding: 3px 2px; border-radius: 6px; }
QTreeWidget::item:selected { background: @surface1@; color: @text@; }
QHeaderView::section { background: @surface0@; color: @subtext@; border: none; padding: 5px 8px; font-size: 13px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: @surface1@; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
QToolTip { background: @surface1@; color: @text@; border: none; padding: 4px 8px; }
"""


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME, extras=lambda t: {"red_hover": QColor(t["red"]).lighter(112).name()})


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)
