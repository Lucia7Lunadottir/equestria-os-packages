"""clock: style."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from equestria_kit import qt as kit_qt, themes as kit_themes
from .paths import CACHE_DIR, CONFIG_DIR


THEMES = kit_themes.THEMES


ALL_THEMES = THEMES


DEFAULT_THEME = kit_themes.DEFAULT_THEME


THEME: dict = dict(THEMES[DEFAULT_THEME])


_LEGACY_THEMES = kit_themes.JsonDictThemes(CONFIG_DIR / "themes.json")


def load_all_themes() -> None:
    """Перечитать темы (включая старый themes.json часов)."""
    reg = kit_themes.registry()
    if _LEGACY_THEMES not in reg.sources:
        reg.sources.insert(1, _LEGACY_THEMES)
    reg.reload()


QSS = """
QMainWindow, QDialog { background: @base@; }
QWidget { color: @text@; font-size: 14px; }
QLabel { background: transparent; }
QLabel#bigclock { font-size: 44px; font-weight: 700; color: @accent@; }
QLabel#subtle { color: @subtext@; }
QLabel#ringtitle { font-size: 28px; font-weight: 700; color: @accent@; }
QLabel#rowtime { font-size: 30px; font-weight: 700; }
QLabel#rowname { font-size: 15px; font-weight: 600; }
QLabel#colon { font-size: 40px; font-weight: 700; color: @subtext@; }
QLabel#swdisplay { font-size: 54px; font-weight: 700; }

QTabWidget::pane { border: none; }
QTabBar { background: transparent; }
QTabBar::tab { background: transparent; color: @subtext@; padding: 10px 22px;
    border: none; border-bottom: 3px solid transparent; font-size: 15px; font-weight: 600; }
QTabBar::tab:selected { color: @accent@; border-bottom: 3px solid @accent@; }
QTabBar::tab:hover:!selected { color: @text@; }

QPushButton { background: @surface0@; border: none; border-radius: 10px;
    padding: 10px 18px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @base@; }
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#primary:disabled { background: @surface1@; color: @surface2@; }
QPushButton#danger { background: @red@; color: @base@; }
QPushButton#flat { background: transparent; padding: 6px 10px; }
QPushButton#flat:hover { background: @surface1@; }
QPushButton#icon { padding: 8px 0; min-width: 44px; max-width: 44px; }
QPushButton#day { padding: 8px 0; min-width: 42px; border-radius: 8px; }
QPushButton#day:checked { background: @accent@; color: @base@; }
QPushButton#step { background: transparent; color: @subtext@; padding: 2px 0;
    font-size: 12px; border-radius: 6px; }
QPushButton#step:hover { color: @accent@; background: transparent; }

QFrame#card { background: @surface0@; border-radius: 14px; }

QLineEdit, QSpinBox, QComboBox { background: @surface0@; border: 2px solid transparent;
    border-radius: 8px; padding: 8px 12px;
    selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: @accent@; }

QSpinBox#bigspin {
    color: @text@;
    background: @surface0@;
    font-size: 40px;
    font-weight: 700;
    padding: 4px 8px;
    min-width: 84px;
    min-height: 54px;
    border: none;
}

/* Явно задаем стиль для внутреннего QLineEdit */
QSpinBox#bigspin QLineEdit {
    color: @text@;
    background: transparent;
    font-size: 40px;
    font-weight: 700;
    padding: 0px;
    margin: 0px;
    border: none;
    min-height: 0px;
    selection-color: @base@;
    selection-background-color: @accent@;
}

QLineEdit#bigedit {
    color: @text@;
    background: @surface0@;
    font-size: 40px;
    font-weight: 700;
    padding: 0px 8px;
    min-width: 84px;
    max-width: 84px;
    min-height: 54px;
    max-height: 54px;
    border: 2px solid transparent;
    border-radius: 8px;
}
QLineEdit#bigedit:focus { border-color: @accent@; }

QComboBox { padding-right: 30px; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox::down-arrow { image: url("@arrow@"); width: 12px; height: 8px; }
QComboBox QAbstractItemView { background: @surface0@; color: @text@; border: none;
    selection-background-color: @surface1@; selection-color: @text@; outline: 0; padding: 4px; }

QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { background: @surface0@; border-radius: 8px; padding: 8px 12px; margin: 3px 0; }

QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QSlider::groove:horizontal { height: 6px; background: @surface1@; border-radius: 3px; }
QSlider::sub-page:horizontal { background: @accent@; border-radius: 3px; }
QSlider::handle:horizontal { background: @accent@; width: 16px; height: 16px;
    margin: -5px 0; border-radius: 8px; }

QToolTip { background: @surface1@; color: @text@; border: none; padding: 4px 8px; }
QMenu { background: @mantle@; color: @text@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
"""


def make_arrow_png(color: str) -> str:
    """Маленькая стрелочка для выпадающих списков (в цвет темы)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"arrow-{color.lstrip('#')}.png"
    if not path.exists():
        pm = QPixmap(12, 8)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([QPointF(1, 1.5), QPointF(11, 1.5), QPointF(6, 6.5)]))
        p.end()
        pm.save(str(path))
    return path.as_posix()


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME, extras=lambda t: {"arrow": make_arrow_png(t["subtext"])})


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)


def make_icon() -> QIcon:
    pm = QPixmap(128, 128)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(THEME["accent"]))
    p.drawEllipse(8, 8, 112, 112)
    pen = QPen(QColor(THEME["base"]), 9)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(64, 64, 64, 30)
    p.drawLine(64, 64, 88, 78)
    p.end()
    return QIcon(pm)
