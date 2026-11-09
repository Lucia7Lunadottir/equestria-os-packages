"""Общее для окон установщика: переводы и тема Equestria (equestria-qt-kit)."""
from __future__ import annotations

import html
import os
import sys

from pathlib import Path
_local_kit = Path(__file__).resolve().parent.parent / "opt/equestria-os/equestria-qt-kit"
if (_local_kit / "equestria_kit/live_i18n.py").is_file():
    sys.path.insert(0, str(_local_kit))
from equestria_kit import live_i18n, qt as kit_qt

catalog = live_i18n.Catalog("equestria-installer", __file__)
tr = catalog.tr


def ui_call(fn, *args, **kwargs):
    result = live_i18n.call(fn, *args, **kwargs)
    if getattr(fn, "__name__", "") == "setSubTitle" and isinstance(args[0], live_i18n.Text):
        catalog.bind(fn.__self__, ("subTitle", "setSubTitle"), args[0], str(args[0]))
    return result


BRIDGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "foreign_bridge.py")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "equestria-installer")

QSS = """
QWidget { color: @text@; font-size: 14px; }
QMainWindow, QDialog, QWizard, QWizardPage { background: @base@; }
QLabel { background: transparent; }
QLabel#title { font-size: 20px; font-weight: 700; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#path { color: @accent@; font-style: italic; }
QLabel#warn { color: @red@; }
QLabel#ok { color: @green@; font-weight: 700; }
QFrame#card { background: @mantle@; border-radius: 14px; }
QPushButton { background: @surface0@; border: none; border-radius: 10px; padding: 8px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @on_accent@; }
QPushButton#danger { background: @red%35@; }
QPushButton#danger:hover { background: @red%55@; }
QTextEdit, QPlainTextEdit { background: @crust@; color: @text@; border: 1px solid @surface1@; border-radius: 10px;
    font-family: monospace; font-size: 13px; padding: 6px; }
QTreeWidget { background: @mantle@; border: none; border-radius: 12px; outline: 0; padding: 4px; }
QTreeWidget::item { padding: 8px 6px; border-radius: 6px; }
QTreeWidget::item:selected { background: @surface1@; color: @text@; }
QHeaderView::section { background: transparent; color: @subtext@; border: none; padding: 6px; font-weight: 600; }
QCheckBox { spacing: 8px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QProgressBar { background: @surface0@; border: none; border-radius: 6px; height: 10px; text-align: center; }
QProgressBar::chunk { background: @accent@; border-radius: 6px; }
"""


def colored(text: str, role: str) -> str:
    """Строка журнала установки в цвете роли темы (HTML для QTextEdit)."""
    def render():
        return f"<span style='color: {kit_qt.theme_color(role).name()};'>{html.escape(str(text))}</span>"
    return live_i18n.Text(text.catalog, render) if isinstance(text, live_i18n.Text) else render()
