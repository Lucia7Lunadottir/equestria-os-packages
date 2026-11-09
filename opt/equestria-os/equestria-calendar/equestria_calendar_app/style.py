"""calendar: style."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from datetime import date
from equestria_kit import qt as kit_qt, themes as kit_themes
from .dates import moon_info
from .localization import live_i18n
from .moon_drawing import draw_moon
from .paths import CONF_DIR


KEYS = kit_themes.KEYS


THEMES = kit_themes.THEMES


DEFAULT_THEME = kit_themes.DEFAULT_THEME


THEME: dict = dict(THEMES[DEFAULT_THEME])


SWATCHES = ["#cba6f7", "#89b4fa", "#94e2d5", "#a6e3a1", "#f9e2af", "#fab387", "#f38ba8", "#f5c2e7"]


MOON_LIGHT = "#f2ecd0"


QSS = """
QMainWindow, QDialog, QMessageBox, QInputDialog { background: @base@; }
QWidget { color: @text@; font-size: 15px; }
QLabel { background: transparent; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#h2 { color: @accent@; font-size: 14px; font-weight: 700; }
QLabel#h3 { font-size: 20px; font-weight: 700; }
QLabel#big { font-size: 26px; font-weight: 700; }
QPushButton { background: @surface0@; border: none; border-radius: 10px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @base@; }
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#danger { color: @red@; }
QPushButton#small { padding: 6px 12px; font-size: 13px; border-radius: 9px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QPushButton::menu-indicator { width: 0; }
QLineEdit { background: @surface0@; border: 2px solid transparent; border-radius: 9px;
    padding: 7px 10px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QComboBox { background: @surface0@; border: none; border-radius: 9px; padding: 7px 12px; }
QComboBox:hover { background: @surface1@; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: @mantle@; border: 1px solid @surface1@; outline: 0;
    selection-background-color: @surface1@; selection-color: @text@; padding: 4px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator, QListWidget::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked, QListWidget::indicator:unchecked { image: url(@chk_off@); }
QCheckBox::indicator:checked, QListWidget::indicator:checked { image: url(@chk_on@); }
QPlainTextEdit { background: @mantle@; border: none; border-radius: 12px; padding: 8px;
    selection-background-color: @accent@; selection-color: @base@; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { background: @surface0@; border-radius: 9px; padding: 7px 10px; margin: 2px 0; }
QListWidget::item:hover { background: @surface1@; }
QListWidget::item:selected { background: @surface2@; color: @text@; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: @surface1@; }
QCalendarWidget QToolButton { color: @text@; background: transparent; border: none; border-radius: 8px;
    padding: 4px 10px; font-weight: 700; }
QCalendarWidget QToolButton:hover { background: @surface2@; }
QCalendarWidget QMenu { background: @mantle@; color: @text@; }
QCalendarWidget QSpinBox { background: @surface0@; color: @text@; selection-background-color: @accent@; }
QCalendarWidget QAbstractItemView:enabled { background: @mantle@; color: @text@; outline: 0;
    selection-background-color: @accent@; selection-color: @base@; }
QCalendarWidget QAbstractItemView:disabled { color: @surface2@; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
QToolTip { background: @surface1@; color: @text@; border: none; padding: 4px 8px; }
"""


def make_check_icons():
    """Квадратики-галочки для QSS рисуем сами: QSS без картинки не показывает «птичку»."""
    try:
        d = CONF_DIR / "icons"
        d.mkdir(parents=True, exist_ok=True)
        tag = "".join(THEME[k].lstrip("#") for k in ("accent", "surface1", "base"))
        off, on = d / f"off_{tag}.png", d / f"on_{tag}.png"
        if not (off.exists() and on.exists()):
            for path, checked in ((off, False), (on, True)):
                pm = QPixmap(18, 18)
                pm.fill(Qt.GlobalColor.transparent)
                p = QPainter(pm)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(THEME["accent" if checked else "surface1"]))
                p.drawRoundedRect(QRectF(0.5, 0.5, 17, 17), 5, 5)
                if checked:
                    p.setPen(QPen(QColor(THEME["base"]), 2.4, Qt.PenStyle.SolidLine,
                                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                    p.drawPolyline(QPolygonF([QPointF(4.5, 9.5), QPointF(7.8, 12.8), QPointF(13.5, 5.5)]))
                p.end()
                pm.save(str(path))
        return off.as_posix(), on.as_posix()
    except OSError:
        return "", ""


def make_icon(d: date) -> QIcon:
    """Иконка приложения: листок календаря с сегодняшним числом и фазой луны."""
    ic = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(sz, sz)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        body = QRectF(sz * 0.07, sz * 0.12, sz * 0.86, sz * 0.82)
        path = QPainterPath()
        path.addRoundedRect(body, sz * 0.17, sz * 0.17)
        p.fillPath(path, QColor(THEME["text"]))
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(body.left(), body.top(), body.width(), sz * 0.27), QColor(THEME["accent"]))
        p.restore()
        if sz >= 24:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(THEME["base"]))
            for x in (0.31, 0.69):
                p.drawRoundedRect(QRectF(sz * x - sz * 0.03, sz * 0.04, sz * 0.06, sz * 0.15), sz * 0.03, sz * 0.03)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(max(8, int(sz * (0.42 if sz >= 32 else 0.5))))
        p.setFont(f)
        p.setPen(QColor(THEME["base"]))
        w = body.width() * (0.72 if sz >= 32 else 1.0)
        live_i18n.call(p.drawText, QRectF(body.left(), sz * 0.38, w, sz * 0.46), Qt.AlignmentFlag.AlignCenter, str(d.day))
        if sz >= 32:
            m = QRectF(sz * 0.62, sz * 0.60, sz * 0.27, sz * 0.27)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(THEME["base"]))
            p.drawEllipse(m.adjusted(-sz * 0.02, -sz * 0.02, sz * 0.02, sz * 0.02))
            draw_moon(p, m, moon_info(d)["f"], THEME, MOON_LIGHT)
        p.end()
        ic.addPixmap(pm)
    return ic


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME, extras=lambda t: dict(zip(("chk_off", "chk_on"), make_check_icons())))


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)


def pfont(px: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def alpha(color: str, a: int) -> QColor:
    c = QColor(color)
    c.setAlpha(a)
    return c
