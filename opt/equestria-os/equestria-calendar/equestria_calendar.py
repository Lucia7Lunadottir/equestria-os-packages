#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Equestria Calendar — календарь с фазами луны и напоминаниями (PyQt6).

• Виды: месяц, неделя, год. Двойной клик по дню — новое напоминание.
• Фазы луны в каждой ячейке и подробная карточка выбранного дня.
• Напоминания: в точное время или на весь день; повтор каждый день / неделю
  (можно по дням недели) / месяц / год, «каждые N», дата окончания, заблаговременное
  предупреждение, цвет, заметка, звук (с повтором, пока окно не закрыто).
• Закрытие окна сворачивает в трей — напоминания продолжают работать.
  Автозапуск: меню настроек → «Запускать вместе с системой» (стартует в трей, --hidden).
"""
from __future__ import annotations

import calendar
import json
import math
import os
import re
import struct
import sys
import uuid
import wave
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

from PyQt6.QtCore import QDate, QPointF, QRectF, QRegularExpression, QTime, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QFont, QFontMetrics, QIcon, QKeySequence, QPainter,
                         QPainterPath, QPalette, QPen, QPixmap, QPolygonF, QRegularExpressionValidator,
                         QShortcut, QTextCharFormat)
from PyQt6.QtWidgets import (QAbstractSpinBox, QApplication, QButtonGroup, QCalendarWidget, QCheckBox, QComboBox,
                             QDateEdit, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                             QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QStackedWidget,
                             QSystemTrayIcon, QTimeEdit, QToolButton, QVBoxLayout, QWidget)

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit.widgets import small_btn
from equestria_kit.autostart import Autostart
from equestria_kit import themes as kit_themes
from equestria_kit import i18n as kit_i18n

tr = kit_i18n.install("equestria-calendar", __file__)

try:
    from PyQt6.QtMultimedia import QSoundEffect
except Exception:  # нет QtMultimedia — будет системный «бип»
    QSoundEffect = None

CONF_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-calendar"
DATA_FILE = CONF_DIR / "calendar.json"

# ════════════════════════════════════════════════════════════════════════════
#  ЛОГИКА (без Qt): даты, луна, повторы, звук, хранилище
# ════════════════════════════════════════════════════════════════════════════
# ---- LOGIC START
MONTHS = [tr("Январь"), tr("Февраль"), tr("Март"), tr("Апрель"), tr("Май"), tr("Июнь"), tr("Июль"), tr("Август"),
          tr("Сентябрь"), tr("Октябрь"), tr("Ноябрь"), tr("Декабрь")]
MONTHS_G = [tr("января"), tr("февраля"), tr("марта"), tr("апреля"), tr("мая"), tr("июня"), tr("июля"), tr("августа"),
            tr("сентября"), tr("октября"), tr("ноября"), tr("декабря")]
WD_SHORT = [tr("Пн"), tr("Вт"), tr("Ср"), tr("Чт"), tr("Пт"), tr("Сб"), tr("Вс")]
WD_LONG = [tr("Понедельник"), tr("Вторник"), tr("Среда"), tr("Четверг"), tr("Пятница"), tr("Суббота"), tr("Воскресенье")]
REPEATS = [("none", tr("Не повторять")), ("daily", tr("Каждый день")), ("weekly", tr("Каждую неделю")),
           ("monthly", tr("Каждый месяц")), ("yearly", tr("Каждый год"))]

SYN = 29.530588853
NEW_MOON_REF = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def moon_noon(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12).astimezone(timezone.utc)


def moon_frac(dt: datetime) -> float:
    return (((dt - NEW_MOON_REF).total_seconds() / 86400.0) % SYN) / SYN


def moon_info(d: date) -> dict:
    f = moon_frac(moon_noon(d))
    near = 0.5 / SYN  # фаза «в этот день» — ±12 часов от полудня
    if f < near or f > 1 - near:
        name = tr("Новолуние")
    elif abs(f - 0.25) < near:
        name = tr("Первая четверть")
    elif abs(f - 0.5) < near:
        name = tr("Полнолуние")
    elif abs(f - 0.75) < near:
        name = tr("Последняя четверть")
    elif f < 0.25:
        name = tr("Растущий месяц")
    elif f < 0.5:
        name = tr("Растущая луна")
    elif f < 0.75:
        name = tr("Убывающая луна")
    else:
        name = tr("Убывающий месяц")
    major = name in (tr("Новолуние"), tr("Первая четверть"), tr("Полнолуние"), tr("Последняя четверть"))
    return {"f": f, "name": name, "major": major,
            "illum": (1 - math.cos(2 * math.pi * f)) / 2, "age": f * SYN}


def next_phase(d: date, target: float) -> date:
    """Ближайшая дата фазы (target: 0 новолуние, .25, .5 полнолуние, .75) — средняя, ±полдня."""
    f = moon_frac(moon_noon(d))
    if abs(((f - target + 0.5) % 1.0) - 0.5) < 0.5 / SYN:
        return d
    return (moon_noon(d) + timedelta(days=((target - f) % 1.0) * SYN)).astimezone().date()


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def occurs_on(rem: dict, d: date) -> bool:
    s = date.fromisoformat(rem["date"])
    if d < s or d.isoformat() in rem.get("skip", []):
        return False
    if rem.get("until") and d > date.fromisoformat(rem["until"]):
        return False
    rep, n = rem.get("repeat", "none"), max(1, int(rem.get("every", 1)))
    if rep == "none":
        return d == s
    if rep == "daily":
        return (d - s).days % n == 0
    if rep == "weekly":
        wd = rem.get("wdays") or [s.weekday()]
        if d.weekday() not in wd:
            return False
        w0 = s - timedelta(days=s.weekday())
        return ((d - w0).days // 7) % n == 0
    if rep == "monthly":
        if ((d.year - s.year) * 12 + d.month - s.month) % n:
            return False
        return d.day == min(s.day, calendar.monthrange(d.year, d.month)[1])
    if rep == "yearly":
        if (d.year - s.year) % n or d.month != s.month:
            return False
        return d.day == min(s.day, calendar.monthrange(d.year, d.month)[1])
    return False


def occ_dt(rem: dict, d: date, allday_t: dtime) -> datetime:
    t = allday_t if rem.get("all_day") else dtime.fromisoformat(rem.get("time", "09:00"))
    return datetime.combine(d, t)


def parse_time(text: str, fallback: str = "09:00") -> str:
    m = re.fullmatch(r"(\d{1,2})(?::?(\d{2}))?", text.strip().replace(".", ":").replace(" ", ""))
    if not m:
        return fallback
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else fallback


def sort_key(rem: dict):
    return (0, "") if rem.get("all_day") else (1, rem.get("time", ""))


SOUND_SPECS = {
    "Колокольчик": dict(notes=[(1046.5, 0, 1.6, 1), (1318.5, .18, 1.6, .9), (1568.0, .36, 1.8, .9),
                               (2093.0, .54, 2.0, .8)], decay=2.6, total=2.8),
    "Мягкий": dict(notes=[(659.3, 0, 2.0, 1), (880.0, .4, 2.2, .9)], decay=1.8, total=3.0),
    "Сигнал": dict(notes=[(1000, 0, .2, 1), (1000, .3, .2, 1), (1000, .6, .2, 1)], decay=9.0, total=1.0),
}


def synth_wav(path: str, spec: dict, sr: int = 22050) -> None:
    n = int(sr * spec["total"])
    buf = [0.0] * n
    for freq, t0, dur, amp in spec["notes"]:
        s0 = int(t0 * sr)
        for i in range(int(dur * sr)):
            if s0 + i >= n:
                break
            t = i / sr
            env = math.exp(-t * spec["decay"]) * min(1.0, t * 300)
            buf[s0 + i] += amp * env * (math.sin(2 * math.pi * freq * t)
                                        + 0.35 * math.sin(4 * math.pi * freq * t)
                                        + 0.12 * math.sin(6 * math.pi * freq * t))
    peak = max(1e-9, max(abs(x) for x in buf))
    data = b"".join(struct.pack("<h", int(x / peak * 0.8 * 32767)) for x in buf)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data)


DEFAULT_SETTINGS = {"theme": "Catppuccin Mocha", "view": "month", "sunday_first": False,
                    "show_moon": True, "sound": "Колокольчик", "custom_sound": "", "volume": 80,
                    "repeat_sound": True, "allday_time": "09:00", "tray": True}


class Store:
    def __init__(self):
        self.settings = dict(DEFAULT_SETTINGS)
        self.reminders: list = []
        self.fired: dict = {}
        self.snoozed: list = []
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        for k, dv in DEFAULT_SETTINGS.items():
            v = raw.get("settings", {}).get(k)
            if v is not None and type(v) is type(dv):
                self.settings[k] = v
        self.reminders = [r for r in raw.get("reminders", []) if isinstance(r, dict) and "id" in r and "date" in r]
        self.fired = raw.get("fired", {}) if isinstance(raw.get("fired"), dict) else {}
        self.snoozed = [s for s in raw.get("snoozed", []) if isinstance(s, dict)]

    def save(self) -> None:
        try:
            CONF_DIR.mkdir(parents=True, exist_ok=True)
            tmp = str(DATA_FILE) + ".tmp~"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"settings": self.settings, "reminders": self.reminders,
                           "fired": self.fired, "snoozed": self.snoozed}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, DATA_FILE)
        except OSError:
            pass
# ---- LOGIC END

# ════════════════════════════════════════════════════════════════════════════
#  ТЕМЫ / СТИЛЬ (как в Equestria Notes)
# ════════════════════════════════════════════════════════════════════════════

# Темы общие для всех приложений Equestria OS: см. equestria_kit/themes.py.
# Свои темы — файлы ~/.config/equestria-os/themes/*.json.
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
        p.drawText(QRectF(body.left(), sz * 0.38, w, sz * 0.46), Qt.AlignmentFlag.AlignCenter, str(d.day))
        if sz >= 32:
            m = QRectF(sz * 0.62, sz * 0.60, sz * 0.27, sz * 0.27)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(THEME["base"]))
            p.drawEllipse(m.adjusted(-sz * 0.02, -sz * 0.02, sz * 0.02, sz * 0.02))
            draw_moon(p, m, moon_info(d)["f"])
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


def short_date(d: date) -> str:
    return f"{d.day} {MONTHS_G[d.month - 1][:3]}"


# ════════════════════════════════════════════════════════════════════════════
#  ЛУНА (рисование)
# ════════════════════════════════════════════════════════════════════════════
def draw_moon(p: QPainter, rect: QRectF, f: float) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(THEME["surface2"]))
    p.drawEllipse(rect)
    c, r = rect.center(), rect.width() / 2
    k = math.cos(2 * math.pi * f)  # 1 — новолуние, -1 — полнолуние
    half = QPainterPath()
    half.moveTo(c.x(), c.y() - r)
    half.arcTo(rect, 90, -180 if f < 0.5 else 180)  # растущая — справа, убывающая — слева
    half.closeSubpath()
    ell = QPainterPath()
    ell.addEllipse(QRectF(c.x() - abs(k) * r, c.y() - r, 2 * abs(k) * r, 2 * r))
    lit = half.united(ell) if k < 0 else half.subtracted(ell)
    p.fillPath(lit, QColor(MOON_LIGHT))
    p.restore()


class MoonCard(QWidget):
    def __init__(self):
        super().__init__()
        self.d = date.today()
        self.setFixedHeight(112)

    def set_date(self, d: date) -> None:
        self.d = d
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        p.fillPath(path, QColor(THEME["mantle"]))
        mi = moon_info(self.d)
        draw_moon(p, QRectF(16, (self.height() - 72) / 2, 72, 72), mi["f"])
        x, w = 104, self.width() - 116
        p.setFont(pfont(16, True))
        p.setPen(QColor(THEME["accent"]))
        p.drawText(QRectF(x, 12, w, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, mi["name"])
        p.setFont(pfont(12))
        p.setPen(QColor(THEME["subtext"]))
        lines = [tr("Освещено {:.0f}% · возраст {:.1f} дн.", mi['illum'] * 100, mi['age']),
                 tr("Полнолуние ≈ {}", short_date(next_phase(self.d, 0.5))),
                 tr("Новолуние ≈ {}", short_date(next_phase(self.d, 0.0)))]
        for i, t in enumerate(lines):
            p.drawText(QRectF(x, 40 + i * 20, w, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, t)


# ════════════════════════════════════════════════════════════════════════════
#  ВИДЫ: МЕСЯЦ / НЕДЕЛЯ / ГОД
# ════════════════════════════════════════════════════════════════════════════
class CalView(QWidget):
    selected = pyqtSignal(object)
    activated = pyqtSignal(object)
    shifted = pyqtSignal(int)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.mode = "month"
        self.sel = date.today()
        self.hover = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(700, 520)

    def start_date(self) -> date:
        fw = 6 if self.app.cfg["sunday_first"] else 0
        base = self.sel if self.mode == "week" else self.sel.replace(day=1)
        return base - timedelta(days=(base.weekday() - fw) % 7)

    def rows(self) -> int:
        return 1 if self.mode == "week" else 6

    def _geom(self):
        wn, hdr = 26, 30
        return wn, hdr, (self.width() - wn) / 7, (self.height() - hdr) / self.rows()

    def date_at(self, pos):
        wn, hdr, cw, ch = self._geom()
        x, y = pos.x() - wn, pos.y() - hdr
        if x < 0 or y < 0:
            return None
        c, r = int(x // cw), int(y // ch)
        if c > 6 or r >= self.rows():
            return None
        return self.start_date() + timedelta(days=r * 7 + c)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        th, today = THEME, date.today()
        wn, hdr, cw, ch = self._geom()
        start = self.start_date()
        fw = 6 if self.app.cfg["sunday_first"] else 0
        show_moon = self.app.cfg["show_moon"] and ch >= 64
        f_hdr, f_num, f_chip, f_chip_s = pfont(12, True), pfont(14, True), pfont(12), pfont(12)
        f_chip_s.setStrikeOut(True)
        fm, fm_s = QFontMetrics(f_chip), QFontMetrics(f_chip_s)
        for c in range(7):
            wd = (fw + c) % 7
            p.setFont(f_hdr)
            p.setPen(QColor(th["red"] if wd >= 5 else th["subtext"]))
            p.drawText(QRectF(wn + c * cw, 0, cw, hdr), Qt.AlignmentFlag.AlignCenter, WD_SHORT[wd])
        for r in range(self.rows()):
            d0 = start + timedelta(days=r * 7)
            p.setFont(pfont(11))
            p.setPen(alpha(th["subtext"], 150))
            p.drawText(QRectF(0, hdr + r * ch + 8, wn - 6, 18),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       str((d0 + timedelta(days=3)).isocalendar()[1]))
            for c in range(7):
                d = d0 + timedelta(days=c)
                in_month = self.mode == "week" or d.month == self.sel.month
                cell = QRectF(wn + c * cw + 2, hdr + r * ch + 2, cw - 4, ch - 4)
                bg = th["surface1"] if d == self.hover else (th["surface0"] if in_month else th["mantle"])
                path = QPainterPath()
                path.addRoundedRect(cell, 12, 12)
                p.fillPath(path, QColor(bg))
                if d == self.sel:
                    p.setPen(QPen(QColor(th["accent"]), 2))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawPath(path)
                num = QRectF(cell.left() + 6, cell.top() + 6, 26, 24)
                p.setFont(f_num)
                if d == today:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(th["accent"]))
                    p.drawEllipse(num)
                    p.setPen(QColor(th["base"]))
                else:
                    p.setPen(QColor(th["text"] if in_month else th["surface2"]))
                p.drawText(num, Qt.AlignmentFlag.AlignCenter, str(d.day))
                if show_moon:
                    mi = moon_info(d)
                    size = 20 if mi["major"] else 16
                    draw_moon(p, QRectF(cell.right() - 8 - size, cell.top() + 8 - (size - 16) / 2, size, size), mi["f"])
                evs = self.app.events_on(d)
                if not evs:
                    continue
                y, lh = cell.top() + 34, 19
                maxn = max(1, int((cell.bottom() - y - 2) // lh))
                shown = evs if len(evs) <= maxn else evs[:max(1, maxn - 1)]
                for rem in shown:
                    done = self.app.is_done(rem, d)
                    chip = QRectF(cell.left() + 5, y, cell.width() - 10, lh - 3)
                    cp = QPainterPath()
                    cp.addRoundedRect(chip, 6, 6)
                    p.fillPath(cp, alpha(rem["color"], 35 if done else 80))
                    p.fillRect(QRectF(chip.left(), chip.top() + 3, 3, chip.height() - 6), QColor(rem["color"]))
                    label = ("" if rem.get("all_day") else rem["time"] + " ") + rem["title"]
                    p.setFont(f_chip_s if done else f_chip)
                    p.setPen(QColor(th["subtext"] if done else th["text"]))
                    el = (fm_s if done else fm).elidedText(label, Qt.TextElideMode.ElideRight, int(chip.width() - 14))
                    p.drawText(chip.adjusted(8, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, el)
                    y += lh
                if len(evs) > len(shown):
                    p.setFont(pfont(11))
                    p.setPen(QColor(th["subtext"]))
                    p.drawText(QRectF(cell.left() + 8, y - 1, cell.width() - 12, 16),
                               Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                               tr("ещё {}…", len(evs) - len(shown)))

    def mouseMoveEvent(self, e) -> None:
        d = self.date_at(e.position())
        if d != self.hover:
            self.hover = d
            self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = None
        self.update()

    def mousePressEvent(self, e) -> None:
        self.setFocus()
        d = self.date_at(e.position())
        if d and e.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(d)

    def mouseDoubleClickEvent(self, e) -> None:
        d = self.date_at(e.position())
        if d and e.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(d)
            self.activated.emit(d)

    def wheelEvent(self, e) -> None:
        dy = e.angleDelta().y()
        if dy:
            self.shifted.emit(-1 if dy > 0 else 1)

    def keyPressEvent(self, e) -> None:
        k, d = e.key(), self.sel
        K = Qt.Key
        new = {K.Key_Left: d - timedelta(days=1), K.Key_Right: d + timedelta(days=1),
               K.Key_Up: d - timedelta(days=7), K.Key_Down: d + timedelta(days=7),
               K.Key_PageUp: add_months(d, -1), K.Key_PageDown: add_months(d, 1),
               K.Key_Home: date.today()}.get(k)
        if new:
            self.selected.emit(new)
        elif k in (K.Key_Return, K.Key_Enter):
            self.activated.emit(d)
        else:
            super().keyPressEvent(e)


class YearView(QWidget):
    selected = pyqtSignal(object)
    activated = pyqtSignal(object)
    shifted = pyqtSignal(int)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.sel = date.today()
        self._cells: list = []
        self._titles: list = []
        self.setMinimumSize(700, 520)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        th, today, year = THEME, date.today(), self.sel.year
        self._cells, self._titles = [], []
        fw = 6 if self.app.cfg["sunday_first"] else 0
        cols = 4 if self.width() >= 980 else 3
        mw, mh = self.width() / cols, self.height() / (12 // cols)
        cal = calendar.Calendar(fw)
        for i in range(12):
            m = i + 1
            bx = QRectF((i % cols) * mw + 6, (i // cols) * mh + 6, mw - 12, mh - 12)
            path = QPainterPath()
            path.addRoundedRect(bx, 14, 14)
            p.fillPath(path, QColor(th["mantle"]))
            tr = QRectF(bx.left() + 12, bx.top() + 8, bx.width() - 24, 20)
            self._titles.append((tr, m))
            p.setFont(pfont(14, True))
            p.setPen(QColor(th["accent"] if m == self.sel.month else th["text"]))
            p.drawText(tr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, MONTHS[i])
            gx, gw = bx.left() + 10, bx.width() - 20
            cw, top = gw / 7, bx.top() + 48
            ch = (bx.bottom() - top - 6) / 6
            p.setFont(pfont(10))
            p.setPen(QColor(th["subtext"]))
            for c in range(7):
                p.drawText(QRectF(gx + c * cw, top - 16, cw, 14), Qt.AlignmentFlag.AlignCenter,
                           WD_SHORT[(fw + c) % 7][0])
            for ri, wk in enumerate(cal.monthdayscalendar(year, m)):
                for ci, dd in enumerate(wk):
                    if not dd:
                        continue
                    day = date(year, m, dd)
                    cell = QRectF(gx + ci * cw, top + ri * ch, cw, ch)
                    self._cells.append((cell, day))
                    sq = min(cw, ch) - 2
                    circ = QRectF(cell.center().x() - sq / 2, cell.center().y() - sq / 2, sq, sq)
                    p.setFont(pfont(11, day == today))
                    if day == today:
                        p.setPen(Qt.PenStyle.NoPen)
                        p.setBrush(QColor(th["accent"]))
                        p.drawEllipse(circ)
                        p.setPen(QColor(th["base"]))
                    else:
                        if day == self.sel:
                            p.setPen(QPen(QColor(th["accent"]), 1.5))
                            p.setBrush(Qt.BrushStyle.NoBrush)
                            p.drawEllipse(circ)
                        p.setPen(QColor(th["red"] if day.weekday() >= 5 else th["text"]))
                    p.drawText(cell, Qt.AlignmentFlag.AlignCenter, str(dd))
                    evs = self.app.events_on(day)
                    if evs:
                        p.setPen(Qt.PenStyle.NoPen)
                        p.setBrush(QColor(evs[0]["color"]))
                        p.drawEllipse(QRectF(cell.center().x() - 2, cell.bottom() - 4, 4, 4))

    def _hit(self, pos):
        pt = pos
        for r, m in self._titles:
            if r.contains(pt):
                return date(self.sel.year, m, 1), True
        for r, d in self._cells:
            if r.contains(pt):
                return d, False
        return None, False

    def mousePressEvent(self, e) -> None:
        d, title = self._hit(e.position())
        if d:
            self.selected.emit(d)
            if title:
                self.activated.emit(d)

    def mouseDoubleClickEvent(self, e) -> None:
        d, title = self._hit(e.position())
        if d:
            self.selected.emit(d)
            self.activated.emit(d)

    def wheelEvent(self, e) -> None:
        dy = e.angleDelta().y()
        if dy:
            self.shifted.emit(-1 if dy > 0 else 1)


# ════════════════════════════════════════════════════════════════════════════
#  ДИАЛОГИ
# ════════════════════════════════════════════════════════════════════════════
def make_calendar(sunday_first: bool) -> QCalendarWidget:
    cal = QCalendarWidget()
    cal.setGridVisible(False)
    cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    cal.setFirstDayOfWeek(Qt.DayOfWeek.Sunday if sunday_first else Qt.DayOfWeek.Monday)
    hf = QTextCharFormat()
    hf.setForeground(QColor(THEME["subtext"]))
    hf.setBackground(QColor(THEME["mantle"]))
    cal.setHeaderTextFormat(hf)
    for dow in (Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday):
        f = QTextCharFormat()
        f.setForeground(QColor(THEME["red"]))
        cal.setWeekdayTextFormat(dow, f)
    for name, txt in (("qt_calendar_prevmonth", "◀"), ("qt_calendar_nextmonth", "▶")):
        b = cal.findChild(QToolButton, name)
        if b:
            b.setIcon(QIcon())
            b.setText(txt)
    return cal


class ReminderDialog(QDialog):
    ADV = [(tr("В момент события"), 0), (tr("За 5 минут"), 5), (tr("За 15 минут"), 15), (tr("За 30 минут"), 30),
           (tr("За 1 час"), 60), (tr("За 1 день"), 1440)]
    UNITS = {"daily": tr("дн."), "weekly": tr("нед."), "monthly": tr("мес."), "yearly": tr("г.")}

    def __init__(self, parent, rem: dict | None, day: date):
        super().__init__(parent)
        self.setWindowTitle(tr("Напоминание"))
        self.setMinimumWidth(520)
        self.rem = rem
        self.deleted = False
        r = rem or {}
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        self.title = QLineEdit(r.get("title", ""))
        self.title.setPlaceholderText(tr("Что напомнить?"))
        v.addWidget(self.title)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Когда")))
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setCalendarWidget(make_calendar(bool(parent.cfg.get("sunday_first"))))
        self.date.setDisplayFormat("dd.MM.yyyy")
        sd = date.fromisoformat(r["date"]) if r else day
        self.date.setDate(QDate(sd.year, sd.month, sd.day))
        self.time = QLineEdit()
        self.time.setFixedWidth(80)
        self.time.setMaxLength(5)
        self.time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time.setPlaceholderText(tr("ЧЧ:ММ"))
        self.time.setToolTip(tr("Время, например 14:30 или 1430"))
        self.time.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9:. ]{0,5}")))
        self.time.editingFinished.connect(lambda: self.time.setText(parse_time(self.time.text(), "09:00")))
        self.date.setMinimumWidth(130)
        if r:
            t = dtime.fromisoformat(r.get("time", "09:00"))
        else:
            t = (datetime.now() + timedelta(hours=1)).time().replace(minute=0, second=0, microsecond=0)
        self.time.setText(f"{t.hour:02d}:{t.minute:02d}")
        self.allday = QCheckBox(tr("Весь день"))
        self.allday.setChecked(bool(r.get("all_day", False)))
        self.allday.toggled.connect(self._sync)
        row.addWidget(self.date)
        row.addWidget(self.time)
        row.addWidget(self.allday)
        row.addStretch()
        v.addLayout(row)

        rrow = QHBoxLayout()
        self.repeat = QComboBox()
        for key, label in REPEATS:
            self.repeat.addItem(label, key)
        self.repeat.setCurrentIndex(max(0, self.repeat.findData(r.get("repeat", "none"))))
        self.repeat.currentIndexChanged.connect(self._sync)
        self.every_lbl = QLabel(tr("каждые"))
        self.every = QSpinBox()
        self.every.setRange(1, 999)
        self.every.setValue(int(r.get("every", 1)))
        self.every.setMinimumWidth(70)
        self.unit = QLabel("")
        rrow.addWidget(QLabel(tr("Повтор")))
        rrow.addWidget(self.repeat)
        rrow.addWidget(self.every_lbl)
        rrow.addWidget(self.every)
        rrow.addWidget(self.unit)
        rrow.addStretch()
        v.addLayout(rrow)

        self.wd_box = QWidget()
        wl = QHBoxLayout(self.wd_box)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(QLabel(tr("По дням")))
        self.wd = []
        for i, n in enumerate(WD_SHORT):
            cb = QCheckBox(n)
            cb.setChecked(i in r.get("wdays", []))
            self.wd.append(cb)
            wl.addWidget(cb)
        wl.addStretch()
        v.addWidget(self.wd_box)

        self.until_box = QWidget()
        ul = QHBoxLayout(self.until_box)
        ul.setContentsMargins(0, 0, 0, 0)
        self.until_cb = QCheckBox(tr("Повторять до"))
        self.until = QDateEdit()
        self.until.setCalendarPopup(True)
        self.until.setCalendarWidget(make_calendar(bool(parent.cfg.get("sunday_first"))))
        self.until.setDisplayFormat("dd.MM.yyyy")
        ud = date.fromisoformat(r["until"]) if r.get("until") else add_months(sd, 12)
        self.until.setDate(QDate(ud.year, ud.month, ud.day))
        self.until_cb.setChecked(bool(r.get("until")))
        self.until_cb.toggled.connect(self._sync)
        ul.addWidget(self.until_cb)
        ul.addWidget(self.until)
        ul.addStretch()
        v.addWidget(self.until_box)

        arow = QHBoxLayout()
        self.alert = QCheckBox(tr("Напомнить"))
        self.alert.setChecked(bool(r.get("alert", True)))
        self.alert.toggled.connect(self._sync)
        self.adv = QComboBox()
        for label, mins in self.ADV:
            self.adv.addItem(label, mins)
        self.adv.setCurrentIndex(max(0, self.adv.findData(int(r.get("advance", 0)))))
        self.sound = QCheckBox(tr("Со звуком"))
        self.sound.setChecked(bool(r.get("sound", True)))
        arow.addWidget(self.alert)
        arow.addWidget(self.adv)
        arow.addWidget(self.sound)
        arow.addStretch()
        v.addLayout(arow)

        crow = QHBoxLayout()
        crow.addWidget(QLabel(tr("Цвет")))
        self.group = QButtonGroup(self)
        cur = r.get("color", SWATCHES[0])
        for col in SWATCHES:
            b = QPushButton()
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setProperty("hex", col)
            b.setChecked(col == cur)
            b.setStyleSheet(f"QPushButton {{ background:{col}; border-radius:11px; min-width:22px; max-width:22px;"
                            f" min-height:22px; max-height:22px; padding:0; border:3px solid transparent; }}"
                            f"QPushButton:checked {{ border:3px solid {THEME['text']}; }}")
            self.group.addButton(b)
            crow.addWidget(b)
        crow.addStretch()
        v.addLayout(crow)

        self.notes = QPlainTextEdit(r.get("notes", ""))
        self.notes.setPlaceholderText(tr("Заметка (необязательно)"))
        self.notes.setFixedHeight(80)
        v.addWidget(self.notes)

        brow = QHBoxLayout()
        if rem:
            d = QPushButton(tr("Удалить"))
            d.setObjectName("danger")
            d.clicked.connect(self._delete)
            brow.addWidget(d)
        brow.addStretch()
        cancel = QPushButton(tr("Отмена"))
        cancel.clicked.connect(self.reject)
        ok = QPushButton(tr("Сохранить"))
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        brow.addWidget(cancel)
        brow.addWidget(ok)
        v.addLayout(brow)
        self._sync()
        self.title.setFocus()

    def _sync(self, *_) -> None:
        rep = self.repeat.currentData()
        self.time.setVisible(not self.allday.isChecked())
        for w in (self.every_lbl, self.every, self.unit):
            w.setVisible(rep != "none")
        self.unit.setText(self.UNITS.get(rep, ""))
        self.wd_box.setVisible(rep == "weekly")
        self.until_box.setVisible(rep != "none")
        self.until.setEnabled(self.until_cb.isChecked())
        self.adv.setEnabled(self.alert.isChecked())
        self.sound.setEnabled(self.alert.isChecked())

    def _delete(self) -> None:
        self.deleted = True
        self.accept()

    def result_rem(self) -> dict:
        qd = self.date.date()
        rep = self.repeat.currentData()
        checked = self.group.checkedButton()
        r = dict(self.rem) if self.rem else {"id": uuid.uuid4().hex[:8], "done": [], "skip": []}
        ud = self.until.date()
        r.update({
            "title": self.title.text().strip() or tr("Без названия"),
            "notes": self.notes.toPlainText().strip(),
            "date": date(qd.year(), qd.month(), qd.day()).isoformat(),
            "all_day": self.allday.isChecked(),
            "time": parse_time(self.time.text(), (self.rem or {}).get("time", "09:00")),
            "repeat": rep,
            "every": self.every.value(),
            "wdays": [i for i, cb in enumerate(self.wd) if cb.isChecked()] if rep == "weekly" else [],
            "until": date(ud.year(), ud.month(), ud.day()).isoformat() if rep != "none" and self.until_cb.isChecked() else None,
            "alert": self.alert.isChecked(),
            "advance": self.adv.currentData(),
            "sound": self.sound.isChecked(),
            "color": checked.property("hex") if checked else SWATCHES[0],
        })
        return r


class ReminderPopup(QDialog):
    def __init__(self, app, rem: dict, d: date, occ: datetime):
        super().__init__(None)
        self.app, self.rem, self.d = app, rem, d
        self.setWindowTitle(tr("Напоминание"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(400)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(8)
        hint = QLabel(tr("🔔 НАПОМИНАНИЕ"))
        hint.setObjectName("h2")
        v.addWidget(hint)
        title = QLabel(rem["title"])
        title.setObjectName("h3")
        title.setWordWrap(True)
        v.addWidget(title)
        v.addWidget(self._when(occ))
        if rem.get("notes"):
            n = QLabel(rem["notes"])
            n.setWordWrap(True)
            v.addWidget(n)
        row = QHBoxLayout()
        snooze = QPushButton(tr("Отложить"))
        menu = QMenu(snooze)
        for label, mins in ((tr("На 5 минут"), 5), (tr("На 15 минут"), 15), (tr("На 1 час"), 60), (tr("До завтра"), -1)):
            menu.addAction(label).triggered.connect(lambda _=False, m=mins: self._snooze(m))
        snooze.setMenu(menu)
        done = QPushButton(tr("Выполнено"))
        done.clicked.connect(self._done)
        ok = QPushButton(tr("Закрыть"))
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        row.addWidget(snooze)
        row.addWidget(done)
        row.addStretch()
        row.addWidget(ok)
        v.addLayout(row)
        self.rep_timer = None
        if rem.get("sound", True) and app.cfg["repeat_sound"]:
            self.count = 0
            self.rep_timer = QTimer(self, interval=9000)
            self.rep_timer.timeout.connect(self._again)
            self.rep_timer.start()

    def _when(self, occ: datetime) -> QLabel:
        now = datetime.now()
        day = {0: tr("Сегодня"), 1: tr("Завтра"), -1: tr("Вчера")}.get((occ.date() - now.date()).days,
                                                          f"{occ.day} {MONTHS_G[occ.month - 1]}")
        text = day + (tr(", весь день") if self.rem.get("all_day") else f", {occ:%H:%M}")
        mins = int((occ - now).total_seconds() // 60)
        if not self.rem.get("all_day") and 0 < mins < 1440:
            text += tr("  ·  через {} ч {} мин", mins // 60, mins % 60) if mins >= 60 else tr("  ·  через {} мин", mins)
        lbl = QLabel(text)
        lbl.setObjectName("hint")
        return lbl

    def _again(self) -> None:
        self.count += 1
        if self.count >= 10:
            self.rep_timer.stop()
            return
        self.app.play_sound()

    def _snooze(self, mins: int) -> None:
        self.app.snooze(self.rem, self.d, mins)
        self.accept()

    def _done(self) -> None:
        self.app.set_done(self.rem, self.d, True)
        self.accept()

    def done(self, r) -> None:
        if self.rep_timer:
            self.rep_timer.stop()
        super().done(r)


# ════════════════════════════════════════════════════════════════════════════
#  ЗВУК
# ════════════════════════════════════════════════════════════════════════════
class Sounds:
    def __init__(self):
        self.dir = CONF_DIR / "sounds"
        self.fx: dict = {}

    def path(self, name: str) -> str:
        idx = list(SOUND_SPECS).index(name) if name in SOUND_SPECS else 0
        p = self.dir / f"sound{idx}.wav"
        if not p.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            synth_wav(str(p), list(SOUND_SPECS.values())[idx])
        return str(p)

    def play(self, name: str, volume: int, custom: str = "") -> None:
        try:
            path = custom if custom and os.path.isfile(custom) else self.path(name)
            if QSoundEffect is None:
                QApplication.beep()
                return
            fx = self.fx.get(path)
            if fx is None:
                fx = QSoundEffect()
                fx.setSource(QUrl.fromLocalFile(path))
                self.fx[path] = fx
            fx.setVolume(max(0.0, min(1.0, volume / 100)))
            fx.play()
        except Exception:
            QApplication.beep()


# ════════════════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ════════════════════════════════════════════════════════════════════════════
class ReminderBook:
    """Напоминания без интерфейса: что в какой день, выполнено ли, пропуски,
    «Отложить», какие напоминания пора показать и когда проверять снова.
    Окно только показывает всплывающие окна и играет звук (fire)."""

    def __init__(self, st: "Store", cfg: dict):
        self.st, self.cfg = st, cfg

    def allday_time(self) -> dtime:
        try:
            return dtime.fromisoformat(self.cfg["allday_time"])
        except ValueError:
            return dtime(9, 0)

    def events_on(self, d: date) -> list:
        return sorted((r for r in self.st.reminders if occurs_on(r, d)), key=sort_key)

    @staticmethod
    def is_done(rem: dict, d: date) -> bool:
        return d.isoformat() in rem.get("done", [])

    def find(self, rid: str):
        return next((r for r in self.st.reminders if r["id"] == rid), None)

    @staticmethod
    def set_done(rem: dict, d: date, on: bool) -> None:
        lst = rem.setdefault("done", [])
        iso = d.isoformat()
        if on and iso not in lst:
            lst.append(iso)
        elif not on and iso in lst:
            lst.remove(iso)

    @staticmethod
    def skip(rem: dict, d: date) -> None:
        rem.setdefault("skip", []).append(d.isoformat())

    def delete(self, rem: dict, with_snoozes: bool = True) -> None:
        self.st.reminders = [r for r in self.st.reminders if r["id"] != rem["id"]]
        if with_snoozes:
            self.st.snoozed = [s for s in self.st.snoozed if s.get("id") != rem["id"]]

    def upsert(self, old, new: dict) -> None:
        """Заменить old на new (или добавить new) и не звонить о прошедшем."""
        if old:
            self.st.reminders[self.st.reminders.index(old)] = new
        else:
            self.st.reminders.append(new)
        self.mark_past_fired(new)

    def mark_past_fired(self, rem: dict) -> None:
        """Не звонить сразу о том, что уже в прошлом (при создании/изменении)."""
        now, at = datetime.now(), self.allday_time()
        for key in [k for k in self.st.fired if k.startswith(rem["id"] + "|")]:
            del self.st.fired[key]
        for k in range(-2, 3):
            d = now.date() + timedelta(days=k)
            if occurs_on(rem, d) and occ_dt(rem, d, at) - timedelta(minutes=rem.get("advance", 0)) <= now:
                self.st.fired[f"{rem['id']}|{d.isoformat()}"] = now.isoformat(timespec="seconds")

    def snooze(self, rem: dict, d: date, mins: int) -> None:
        """mins < 0 — «До завтра» (время напоминаний «на весь день»)."""
        if mins < 0:
            at = datetime.combine(date.today() + timedelta(days=1), self.allday_time())
        else:
            at = datetime.now() + timedelta(minutes=mins)
        self.st.snoozed.append({"id": rem["id"], "date": d.isoformat(), "at": at.isoformat(timespec="seconds")})

    def due(self, now: datetime) -> tuple:
        """Что пора показать: ([(напоминание, день, момент)], нужно_сохранить).
        Сначала наступившие «Отложить», затем обычные; показанное помечается."""
        at, st = self.allday_time(), self.st
        out = []
        due = [s for s in st.snoozed if datetime.fromisoformat(s["at"]) <= now]
        if due:
            st.snoozed = [s for s in st.snoozed if s not in due]
            for s in due:
                rem = self.find(s["id"])
                if rem:
                    d = date.fromisoformat(s["date"])
                    out.append((rem, d, occ_dt(rem, d, at)))
        dirty = bool(due)
        for rem in list(st.reminders):
            if not rem.get("alert", True):
                continue
            adv = timedelta(minutes=rem.get("advance", 0))
            for k in range(-2, 3):
                d = now.date() + timedelta(days=k)
                if not occurs_on(rem, d) or self.is_done(rem, d):
                    continue
                key = f"{rem['id']}|{d.isoformat()}"
                if key in st.fired:
                    continue
                occ = occ_dt(rem, d, at)
                if occ - adv <= now and now - occ < timedelta(hours=24):
                    st.fired[key] = now.isoformat(timespec="seconds")
                    dirty = True
                    out.append((rem, d, occ))
        old = (now.date() - timedelta(days=10)).isoformat()
        for key in [k for k in st.fired if k.split("|")[-1] < old]:
            del st.fired[key]
            dirty = True
        return out, dirty

    def next_check(self, now: datetime) -> datetime:
        """Следующая проверка: граница минуты или ближайшее «Отложить»."""
        nxt = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for snz in self.st.snoozed:
            try:
                nxt = min(nxt, max(now, datetime.fromisoformat(snz["at"])))
            except (KeyError, ValueError):
                pass
        return nxt


class MainWindow(QMainWindow):
    def __init__(self, st: Store):
        super().__init__()
        self.st, self.cfg = st, st.settings
        self.book = ReminderBook(st, self.cfg)   # логика напоминаний — отдельно от окна
        self.theme = self.cfg["theme"]
        self.sel = date.today()
        self.mode = self.cfg["view"] if self.cfg["view"] in ("month", "week", "year") else "month"
        self.sounds = Sounds()
        self.popups: list = []
        self.quitting = False
        self._icon_day = None
        self.setWindowTitle("Equestria Calendar")
        self.setMinimumSize(1120, 700)
        self.resize(1320, 800)

        self.save_timer = QTimer(self, singleShot=True, interval=400)
        self.save_timer.timeout.connect(self.st.save)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel("Equestria Calendar")
        title.setObjectName("h2")
        top.addWidget(title)
        top.addStretch()
        self.view_btns = {}
        for mode, label in (("month", tr("Месяц")), ("week", tr("Неделя")), ("year", tr("Год"))):
            b = small_btn(label, True, "Ctrl+1 / Ctrl+2 / Ctrl+3")
            b.clicked.connect(lambda _=False, m=mode: self.set_view(m))
            self.view_btns[mode] = b
            top.addWidget(b)
        theme_btn = small_btn(tr("Тема"))
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        set_btn = small_btn("⚙")
        set_btn.clicked.connect(lambda: self._settings_menu(set_btn))
        top.addSpacing(10)
        top.addWidget(theme_btn)
        top.addWidget(set_btn)
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(22)
        root.addLayout(body, 1)

        left = QVBoxLayout()
        left.setSpacing(8)
        nav = QHBoxLayout()
        prev = small_btn("◀")
        prev.clicked.connect(lambda: self.shift(-1))
        nxt = small_btn("▶")
        nxt.clicked.connect(lambda: self.shift(1))
        today = small_btn(tr("Сегодня"), tip="T")
        today.clicked.connect(lambda: self.set_date(date.today()))
        self.head = QLabel("")
        self.head.setObjectName("big")
        add = QPushButton(tr("＋ Напоминание"))
        add.setObjectName("primary")
        add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add.clicked.connect(lambda: self.edit_reminder(None, self.sel))
        for w in (prev, nxt, today):
            nav.addWidget(w)
        nav.addSpacing(8)
        nav.addWidget(self.head)
        nav.addStretch()
        nav.addWidget(add)
        left.addLayout(nav)
        self.stack = QStackedWidget()
        self.cal = CalView(self)
        self.year = YearView(self)
        self.stack.addWidget(self.cal)
        self.stack.addWidget(self.year)
        for v in (self.cal, self.year):
            v.selected.connect(self.set_date)
            v.shifted.connect(self.shift)
        self.cal.activated.connect(lambda d: self.edit_reminder(None, d))
        self.year.activated.connect(lambda d: (self.set_view("month"), self.set_date(d)))
        left.addWidget(self.stack, 1)
        lw = QWidget()
        lw.setLayout(left)
        body.addWidget(lw, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.day_title = QLabel("")
        self.day_title.setObjectName("h3")
        self.day_sub = QLabel("")
        self.day_sub.setObjectName("hint")
        right.addWidget(self.day_title)
        right.addWidget(self.day_sub)
        self.moon = MoonCard()
        right.addWidget(self.moon)
        h = QLabel(tr("НАПОМИНАНИЯ ДНЯ"))
        h.setObjectName("h2")
        right.addWidget(h)
        self.day_list = QListWidget()
        self.day_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.day_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.day_list.itemChanged.connect(self._day_check)
        self.day_list.itemDoubleClicked.connect(self._day_edit)
        self.day_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.day_list.customContextMenuRequested.connect(self._day_menu)
        right.addWidget(self.day_list, 3)
        h2 = QLabel(tr("БЛИЖАЙШИЕ"))
        h2.setObjectName("h2")
        right.addWidget(h2)
        self.up_list = QListWidget()
        self.up_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.up_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.up_list.itemClicked.connect(self._up_click)
        right.addWidget(self.up_list, 2)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(350)
        body.addWidget(rw)

        def sc(seq, fn):
            QShortcut(QKeySequence(seq), self).activated.connect(fn)
        sc("Ctrl+N", lambda: self.edit_reminder(None, self.sel))
        sc("T", lambda: self.set_date(date.today()))
        sc("Ctrl+1", lambda: self.set_view("month"))
        sc("Ctrl+2", lambda: self.set_view("week"))
        sc("Ctrl+3", lambda: self.set_view("year"))

        # трей
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            menu = QMenu(self)
            menu.addAction(tr("Открыть календарь")).triggered.connect(self.show_window)
            menu.addAction(tr("Выйти")).triggered.connect(self.quit_app)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda r: self.show_window()
                                        if r == QSystemTrayIcon.ActivationReason.Trigger else None)
            self.tray.show()
        self._update_icon()

        # Напоминания — с точностью до минуты, поэтому проверяем ровно на границе
        # минуты (или к ближайшему «Отложить»), а не каждые 15 секунд.
        self.tick_timer = QTimer(self, singleShot=True)
        self.tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.tick_timer.timeout.connect(self._tick)
        self._schedule_tick()
        self.set_view(self.mode, save=False)
        QTimer.singleShot(1500, self.check_due)

    # --- данные
    # --- данные (логика — в ReminderBook; здесь обёртки для видов и всплывающих окон)
    def events_on(self, d: date) -> list:
        return self.book.events_on(d)

    def is_done(self, rem: dict, d: date) -> bool:
        return self.book.is_done(rem, d)

    def find(self, rid: str):
        return self.book.find(rid)

    def _allday_t(self) -> dtime:
        return self.book.allday_time()

    def changed(self) -> None:
        self.save_timer.start()
        self.refresh_all()

    def set_done(self, rem: dict, d: date, on: bool) -> None:
        self.book.set_done(rem, d, on)
        self.changed()

    # --- навигация
    def set_date(self, d: date) -> None:
        self.sel = d
        self.cal.sel = d
        self.year.sel = d
        self.refresh_all()

    def shift(self, n: int) -> None:
        if self.mode == "week":
            self.set_date(self.sel + timedelta(days=7 * n))
        elif self.mode == "year":
            self.set_date(add_months(self.sel, 12 * n))
        else:
            self.set_date(add_months(self.sel, n))

    def set_view(self, mode: str, save: bool = True) -> None:
        self.mode = mode
        self.cal.mode = mode
        for m, b in self.view_btns.items():
            b.setChecked(m == mode)
        self.stack.setCurrentWidget(self.year if mode == "year" else self.cal)
        if save:
            self.cfg["view"] = mode
            self.save_timer.start()
        self.refresh_all()

    # --- отрисовка панелей
    def refresh_all(self) -> None:
        d = self.sel
        if self.mode == "year":
            self.head.setText(str(d.year))
        elif self.mode == "week":
            a = self.cal.start_date()
            b = a + timedelta(days=6)
            self.head.setText(f"{a.day} – {b.day} {MONTHS_G[b.month - 1]} {b.year}" if a.month == b.month
                              else f"{a.day} {MONTHS_G[a.month - 1][:3]} – {b.day} {MONTHS_G[b.month - 1][:3]} {b.year}")
        else:
            self.head.setText(f"{MONTHS[d.month - 1]} {d.year}")
        self.cal.update()
        self.year.update()
        self.day_title.setText(f"{d.day} {MONTHS_G[d.month - 1]} {d.year}")
        self.day_sub.setText(WD_LONG[d.weekday()] + (tr(" · сегодня") if d == date.today() else ""))
        self.moon.set_date(d)
        self._fill_day()
        self._fill_upcoming()

    def _fill_day(self) -> None:
        lst = self.day_list
        lst.blockSignals(True)
        lst.clear()
        evs = self.events_on(self.sel)
        for r in evs:
            done = self.is_done(r, self.sel)
            text = (tr("Весь день") if r.get("all_day") else r["time"]) + " · " + r["title"]
            if r.get("repeat", "none") != "none":
                text += "  🔁"
            if r.get("notes"):
                text += "\n" + r["notes"].split("\n")[0][:60]
            it = QListWidgetItem(text)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if done else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, r["id"])
            pm = QPixmap(12, 12)
            pm.fill(QColor(r["color"]))
            it.setIcon(QIcon(pm))
            if done:
                f = it.font()
                f.setStrikeOut(True)
                it.setFont(f)
            lst.addItem(it)
        if not evs:
            it = QListWidgetItem(tr("Нет напоминаний. Двойной клик по дню — добавить."))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            lst.addItem(it)
        lst.blockSignals(False)

    def _fill_upcoming(self) -> None:
        self.up_list.clear()
        today = date.today()
        n = 0
        for i in range(120):
            d = today + timedelta(days=i)
            for r in self.events_on(d):
                if self.is_done(r, d):
                    continue
                when = tr("Весь день") if r.get("all_day") else r["time"]
                label = tr("Сегодня") if i == 0 else (tr("Завтра") if i == 1 else f"{WD_SHORT[d.weekday()]}, {short_date(d)}")
                it = QListWidgetItem(f"{label} · {when} · {r['title']}")
                it.setData(Qt.ItemDataRole.UserRole, d.isoformat())
                self.up_list.addItem(it)
                n += 1
            if n >= 14:
                break
        if not n:
            it = QListWidgetItem(tr("Ближайших напоминаний нет."))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.up_list.addItem(it)

    def _up_click(self, it) -> None:
        iso = it.data(Qt.ItemDataRole.UserRole)
        if iso:
            self.set_date(date.fromisoformat(iso))

    # --- действия с напоминаниями
    def _day_check(self, it) -> None:
        rem = self.find(it.data(Qt.ItemDataRole.UserRole))
        if rem:
            self.set_done(rem, self.sel, it.checkState() == Qt.CheckState.Checked)

    def _day_edit(self, it) -> None:
        rem = self.find(it.data(Qt.ItemDataRole.UserRole))
        if rem:
            self.edit_reminder(rem, self.sel)

    def _day_menu(self, pos) -> None:
        it = self.day_list.itemAt(pos)
        rem = self.find(it.data(Qt.ItemDataRole.UserRole)) if it else None
        menu = QMenu(self)
        if rem:
            menu.addAction(tr("Изменить…")).triggered.connect(lambda: self.edit_reminder(rem, self.sel))
            if rem.get("repeat", "none") != "none":
                menu.addAction(tr("Пропустить только этот день")).triggered.connect(lambda: self._skip(rem))
            menu.addAction(tr("Удалить…")).triggered.connect(lambda: self._delete(rem))
            menu.addSeparator()
        menu.addAction(tr("Новое напоминание…")).triggered.connect(lambda: self.edit_reminder(None, self.sel))
        menu.exec(self.day_list.viewport().mapToGlobal(pos))

    def _skip(self, rem: dict) -> None:
        self.book.skip(rem, self.sel)
        self.changed()

    def _delete(self, rem: dict) -> None:
        extra = tr("\nВсе повторы тоже будут удалены.") if rem.get("repeat", "none") != "none" else ""
        if QMessageBox.question(self, tr("Удалить"), tr("Удалить «{}»?{}", rem['title'], extra)) != QMessageBox.StandardButton.Yes:
            return
        self.book.delete(rem)
        self.changed()

    def edit_reminder(self, rem, day: date) -> None:
        dlg = ReminderDialog(self, rem, day)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.deleted and rem:
            self._delete_now(rem)
            return
        new = dlg.result_rem()
        self.book.upsert(rem, new)
        self.set_date(date.fromisoformat(new["date"]))
        self.changed()

    def _delete_now(self, rem: dict) -> None:
        self.book.delete(rem, with_snoozes=False)
        self.changed()

    # --- срабатывание
    def play_sound(self) -> None:
        self.sounds.play(self.cfg["sound"], self.cfg["volume"], self.cfg["custom_sound"])

    def snooze(self, rem: dict, d: date, mins: int) -> None:
        self.book.snooze(rem, d, mins)
        self.save_timer.start()

    def fire(self, rem: dict, d: date, occ: datetime) -> None:
        pop = ReminderPopup(self, rem, d, occ)
        self.popups.append(pop)
        pop.finished.connect(lambda _=0, p=pop: self.popups.remove(p) if p in self.popups else None)
        pop.show()
        pop.raise_()
        pop.activateWindow()
        if rem.get("sound", True):
            self.play_sound()

    def check_due(self) -> None:
        to_fire, dirty = self.book.due(datetime.now())
        for rem, d, occ in to_fire:
            self.fire(rem, d, occ)
        if dirty:
            self.save_timer.start()

    def _tick(self) -> None:
        self.check_due()
        if self._icon_day != date.today():
            self._update_icon()
            self.refresh_all()
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        now = datetime.now()
        nxt = self.book.next_check(now)
        self.tick_timer.start(max(50, int((nxt - now).total_seconds() * 1000) + 200))

    # --- трей / иконка / выход
    def _update_icon(self) -> None:
        self._icon_day = date.today()
        ic = make_icon(self._icon_day)
        QApplication.setWindowIcon(ic)
        self.setWindowIcon(ic)
        if self.tray:
            self.tray.setIcon(ic)
            self.tray.setToolTip("Equestria Calendar")

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self.quitting = True
        self.st.save()
        QApplication.quit()

    def closeEvent(self, e) -> None:
        if self.tray and self.cfg["tray"] and not self.quitting:
            e.ignore()
            self.hide()
            return
        self.st.save()
        self.quitting = True
        super().closeEvent(e)
        QApplication.quit()

    # --- меню
    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self.cfg["theme"] = self.theme
        self._update_icon()
        self.refresh_all()
        self.st.save()

    def _toggle(self, key: str, on: bool) -> None:
        self.cfg[key] = on
        self.st.save()
        self.refresh_all()

    def _settings_menu(self, btn) -> None:
        menu = QMenu(self)
        snd = menu.addMenu(tr("Звук напоминаний"))
        for name in SOUND_SPECS:
            a = snd.addAction(tr(name))
            a.setCheckable(True)
            a.setChecked(name == self.cfg["sound"] and not self.cfg["custom_sound"])
            a.triggered.connect(lambda _=False, n=name: self._pick_sound(n))
        a = snd.addAction(tr("Свой файл (WAV)…") + (f" — {os.path.basename(self.cfg['custom_sound'])}" if self.cfg["custom_sound"] else ""))
        a.triggered.connect(self._custom_sound)
        snd.addSeparator()
        snd.addAction(tr("Громкость…")).triggered.connect(self._volume)
        snd.addAction(tr("Проверить звук")).triggered.connect(self.play_sound)
        rs = snd.addAction(tr("Повторять, пока окно напоминания открыто"))
        rs.setCheckable(True)
        rs.setChecked(self.cfg["repeat_sound"])
        rs.toggled.connect(lambda on: self._toggle("repeat_sound", on))
        menu.addAction(tr("Время напоминаний «на весь день»: {}…", self.cfg['allday_time'])).triggered.connect(self._allday_time)
        for key, label in (("sunday_first", tr("Неделя начинается с воскресенья")), ("show_moon", tr("Фазы луны в ячейках"))):
            a = menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.cfg[key])
            a.toggled.connect(lambda on, k=key: self._toggle(k, on))
        auto = Autostart("equestria-calendar", "Equestria Calendar",
                         tr("Календарь с фазами луны и напоминаниями"))
        a = menu.addAction(tr("Запускать вместе с системой"))
        a.setCheckable(True)
        a.setChecked(auto.is_enabled())
        a.toggled.connect(lambda on: self._autostart(auto, on))
        if self.tray:
            a = menu.addAction(tr("Закрытие окна сворачивает в трей"))
            a.setCheckable(True)
            a.setChecked(self.cfg["tray"])
            a.toggled.connect(lambda on: self._toggle("tray", on))
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _autostart(self, auto: Autostart, on: bool) -> None:
        if on and self.tray and not self.cfg["tray"]:
            self._toggle("tray", True)   # при автозапуске календарь живёт в трее
        auto.set_enabled(on)

    def _pick_sound(self, name: str) -> None:
        self.cfg["sound"], self.cfg["custom_sound"] = name, ""
        self.st.save()
        self.play_sound()

    def _custom_sound(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, tr("Звук (WAV)"), str(Path.home()), "WAV (*.wav)")
        if p:
            self.cfg["custom_sound"] = p
            self.st.save()
            self.play_sound()

    def _volume(self) -> None:
        v, ok = QInputDialog.getInt(self, tr("Громкость"), tr("Громкость, %:"), self.cfg["volume"], 0, 100)
        if ok:
            self.cfg["volume"] = v
            self.st.save()
            self.play_sound()

    def _allday_time(self) -> None:
        t, ok = QInputDialog.getText(self, tr("Весь день"), tr("Во сколько напоминать (ЧЧ:ММ):"), text=self.cfg["allday_time"])
        if ok:
            try:
                self.cfg["allday_time"] = dtime.fromisoformat(t.strip()).strftime("%H:%M")
                self.st.save()
            except ValueError:
                QMessageBox.warning(self, tr("Время"), tr("Введите время в формате ЧЧ:ММ, например 09:00."))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Calendar")
    app.setDesktopFileName("equestria-calendar")
    app.setStyle("Fusion")
    st = Store()
    st.settings["theme"] = apply_theme(kit_themes.current_name())
    win = MainWindow(st)
    kit_themes.follow(win._set_theme, lambda: win.theme)
    app.setQuitOnLastWindowClosed(win.tray is None)
    if not ("--hidden" in sys.argv and win.tray):
        win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())