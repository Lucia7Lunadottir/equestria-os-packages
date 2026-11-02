"""Оформление: QSS-шаблон с ролями общей темы Equestria OS.

Цвета не хранятся здесь — их выдаёт equestria_kit по выбору в переключателе
«Тема персонажа»; при смене темы там лаунчер перекрашивается на лету."""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from equestria_ue.kit import kit_qt


QSS = """
QMainWindow, QDialog { background: @base@; }
QWidget { color: @text@; font-size: 14px; }
QLabel { background: transparent; }
QLabel#logo { font-size: 18px; font-weight: 800; color: @accent@; }
QLabel#title { font-size: 22px; font-weight: 800; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#h2 { color: @accent@; font-size: 14px; font-weight: 700; }
QLabel#big { font-size: 26px; font-weight: 800; }
QLabel#rowname { font-size: 15px; font-weight: 600; }
QLabel#chip { background: @mantle@; border-radius: 9px; padding: 3px 10px; font-size: 12px; font-weight: 700; color: @subtext@; }
QLabel#chip[lvl="ok"] { color: @green@; }
QLabel#chip[lvl="warn"] { color: @yellow@; }
QLabel#chip[lvl="fail"] { color: @red@; }
QFrame#side { background: @crust@; }
QFrame#card { background: @surface0@; border-radius: 14px; }
QFrame#hero { background: @mantle@; border-radius: 16px; }

QPushButton { background: @surface0@; border: none; border-radius: 10px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @on_accent@; }
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#primary:pressed { background: @accent%70@; }
QPushButton#primary:disabled { background: @surface1@; color: @surface2@; }
QPushButton#danger { background: @red@; color: @on_red@; }
QPushButton#danger:hover { background: @red%85@; }
QPushButton#small { padding: 6px 12px; font-size: 13px; border-radius: 9px; }
QPushButton#nav { background: transparent; text-align: left; padding: 12px 16px; border-radius: 10px;
    font-size: 15px; color: @subtext@; }
QPushButton#nav:hover { background: @mantle@; color: @text@; }
QPushButton#nav:pressed { background: @surface1@; }
QPushButton#nav:checked { background: @surface0@; color: @accent@; }
/* нажатие видно у всех кнопок: заливка темнеет и надпись чуть опускается */
QPushButton:pressed { padding-top: 10px; padding-bottom: 8px; }
QPushButton#small:pressed { padding-top: 7px; padding-bottom: 5px; background: @surface2@; }
QPushButton#danger:pressed { background: @red%70@; }

QLineEdit, QComboBox { background: @mantle@; border: 2px solid transparent; border-radius: 9px; padding: 8px 12px;
    selection-background-color: @accent@; selection-color: @on_accent@; }
QLineEdit:focus, QComboBox:focus { border-color: @accent@; }
QComboBox { padding-right: 28px; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url("@icon:arrow_down@"); width: 12px; height: 8px; }
QComboBox QAbstractItemView { background: @surface0@; color: @text@; border: none;
    selection-background-color: @surface1@; selection-color: @text@; outline: 0; padding: 4px; }
QCheckBox { spacing: 10px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; background: @mantle@; border: 2px solid @surface2@; }
QCheckBox::indicator:checked { background: @accent@; border-color: @accent@; image: url("@icon:check_mark@"); }
QPlainTextEdit { background: @crust@; border: none; border-radius: 10px; padding: 8px; font-size: 13px;
    selection-background-color: @accent@; selection-color: @on_accent@; }
QProgressBar { background: @mantle@; border: none; border-radius: 6px; height: 12px; text-align: center; font-size: 11px; }
QProgressBar::chunk { background: @accent@; border-radius: 6px; }

QListWidget { background: transparent; border: none; outline: 0; }
QListWidget#grid::item { background: @surface0@; border-radius: 12px; padding: 8px; }
QListWidget#grid::item:hover { background: @surface1@; }
QListWidget#grid::item:selected { background: @surface2@; color: @text@; }
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


def install_theme(app: QApplication) -> kit_qt.ThemeManager:
    """Подключает приложение к общей теме и следит за её сменой."""
    return kit_qt.ThemeManager(app, QSS)
