#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Equestria Clock — будильник, таймер и секундомер для человека за компьютером.

Это обычное окошко (не будит сам компьютер): пока программа запущена
(можно свернуть в трей), будильники и таймер сработают и зазвонят.

Цвета: общие темы Equestria OS (equestria_kit/themes.py). Свои темы — файлы
~/.config/equestria-os/themes/*.json; старый ~/.config/equestria-clock/themes.json тоже читается.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import shutil
import sys
import time
import wave
from array import array
from pathlib import Path

from PyQt6.QtCore import (QObject, QProcess, QRectF, Qt, QTimer, QUrl,
                          pyqtSignal)
from PyQt6.QtGui import (QAction, QColor, QDesktopServices, QFont,
                         QFontDatabase, QIcon, QIntValidator, QPainter,
                         QPalette, QPen, QPixmap, QPolygonF)
from PyQt6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QDialog,
                             QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMenu, QPushButton, QScrollArea,
                             QSizePolicy, QSlider, QSpinBox, QSystemTrayIcon,
                             QTabWidget, QVBoxLayout, QWidget)
from PyQt6.QtCore import QPointF

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit.autostart import Autostart
from equestria_kit.single_instance import SingleInstance
from equestria_kit import themes as kit_themes
from equestria_kit import i18n as kit_i18n

tr = kit_i18n.install("equestria-clock", __file__)

APP_NAME = "equestria-clock"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP_NAME
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / APP_NAME


# Темы общие для всех приложений Equestria OS (equestria_kit/themes.py).
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


# ════════════════════════════════════════════════════════════════════════════
#  ЗВУК
# ════════════════════════════════════════════════════════════════════════════
def _seq_classic():
    beeps = [(880.0, 0.12), (0, 0.08)] * 4 + [(0, 0.3)]
    return beeps * 2 + [(0, 0.7)]


# ключ: (название, ноты [(частота Гц, длительность с)], «затухание»)
BUILTIN_SOUNDS = {
    "chime": (tr("Колокольчик"), [
        (659.25, .28), (783.99, .28), (1046.5, .45), (0, .15),
        (783.99, .28), (1046.5, .28), (1318.5, .70), (0, 1.0)], 5.0),
    "classic": (tr("Классический звонок"), _seq_classic(), 0.5),
    "rainbow": (tr("Радуга"), [
        (523.25, .18), (587.33, .18), (659.25, .18), (783.99, .18), (880.0, .18),
        (1046.5, .30), (880.0, .18), (783.99, .18), (659.25, .18), (587.33, .18),
        (523.25, .50), (0, 1.0)], 3.0),
}


def make_wav(path: Path, seq, decay: float, rate: int = 44100) -> None:
    samples = array("h")
    for freq, dur in seq:
        n = int(rate * dur)
        if freq == 0:
            samples.extend([0] * n)
            continue
        w = 2 * math.pi * freq
        for i in range(n):
            t = i / rate
            env = (min(1.0, t / 0.008) * min(1.0, (dur - t) / 0.015)
                   * math.exp(-decay * t / dur))
            v = (math.sin(w * t) + 0.35 * math.sin(2 * w * t)
                 + 0.12 * math.sin(3 * w * t)) / 1.47
            samples.append(int(v * env * 0.6 * 32767))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(samples.tobytes())


def ensure_builtin(key: str) -> Path:
    path = CACHE_DIR / "sounds" / f"{key}-v1.wav"
    if not path.exists():
        _, seq, decay = BUILTIN_SOUNDS[key]
        make_wav(path, seq, decay)
    return path


def resolve_sound(spec: str | None) -> Path:
    if spec and spec.startswith("builtin:") and spec[8:] in BUILTIN_SOUNDS:
        return ensure_builtin(spec[8:])
    if spec and Path(spec).is_file():
        return Path(spec)
    return ensure_builtin("chime")


class SoundPlayer(QObject):
    """Играет звук через системный pw-play / paplay (без тяжёлого QtMultimedia)."""
    stateChanged = pyqtSignal(bool)  # True — играет

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = None
        self.volume = 80
        self.loop = False
        self.path = ""
        self._active = False

    @staticmethod
    def _tool():
        for name in ("pw-play", "paplay"):
            if shutil.which(name):
                return name
        return None

    def _set_active(self, on: bool) -> None:
        if on != self._active:
            self._active = on
            self.stateChanged.emit(on)

    def _start(self) -> None:
        tool = self._tool()
        if not tool:
            print("Ошибка звука: не найден pw-play или paplay", file=sys.stderr)
            self._set_active(False)
            QApplication.beep()
            return
        v = self.volume / 100
        vol = f"--volume={v:.2f}" if tool == "pw-play" else f"--volume={int(v * 65536)}"
        p = QProcess(self)
        self.proc = p
        p.finished.connect(lambda *_, p=p: self._finished(p))
        p.errorOccurred.connect(lambda *_, p=p: self._failed(p))
        p.start(tool, [vol, self.path])

    def _failed(self, p) -> None:
        if p is self.proc:
            self._set_active(False)
        self._finished(p)

    def _finished(self, p) -> None:
        p.deleteLater()
        if p is not self.proc:
            return
        self.proc = None
        if self._active and self.loop:
            self._start()
        else:
            self._set_active(False)

    def _halt(self) -> None:
        p, self.proc = self.proc, None
        if p is not None:
            p.kill()

    def play(self, spec: str | None, volume: int, loop: bool = True) -> None:
        self._halt()
        self.volume = max(0, min(100, volume))
        self.loop = loop
        self.path = str(resolve_sound(spec))
        self._start()
        self._active = False
        self._set_active(True)

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, volume))  # применится при следующем повторе

    def stop(self) -> None:
        self._halt()
        self._set_active(False)


# ════════════════════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ════════════════════════════════════════════════════════════════════════════
DEFAULT_SETTINGS = {
    "theme": DEFAULT_THEME,
    "sound": "builtin:chime",
    "volume": 80,
    "snooze": 5,
    "tray": True,
    "timer": [0, 5, 0],
    "alarms": [],
}


class Settings:
    def __init__(self):
        self.path = CONFIG_DIR / "settings.json"
        self.data = json.loads(json.dumps(DEFAULT_SETTINGS))
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        for k in DEFAULT_SETTINGS:
            if k in raw:
                self.data[k] = raw[k]
        good = []
        for a in self.data["alarms"]:
            try:
                h, m = map(int, str(a["time"]).split(":"))
                assert 0 <= h < 24 and 0 <= m < 60
                good.append({
                    "time": f"{h:02d}:{m:02d}",
                    "label": str(a.get("label", "")),
                    "days": sorted({int(d) for d in a.get("days", []) if 0 <= int(d) <= 6}),
                    "enabled": bool(a.get("enabled", True)),
                    "sound": str(a.get("sound", "")),
                })
            except Exception:
                continue
        self.data["alarms"] = good

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(self.path)
        except Exception as e:
            print("Не удалось сохранить настройки:", e, file=sys.stderr)

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v


# ════════════════════════════════════════════════════════════════════════════
#  МЕЛОЧИ: форматирование
# ════════════════════════════════════════════════════════════════════════════
DAYS_SHORT = [tr("Пн"), tr("Вт"), tr("Ср"), tr("Чт"), tr("Пт"), tr("Сб"), tr("Вс")]
WEEKDAYS = [tr("понедельник"), tr("вторник"), tr("среда"), tr("четверг"), tr("пятница"), tr("суббота"), tr("воскресенье")]
MONTHS = [tr("января"), tr("февраля"), tr("марта"), tr("апреля"), tr("мая"), tr("июня"), tr("июля"), tr("августа"),
          tr("сентября"), tr("октября"), tr("ноября"), tr("декабря")]


def describe_days(days) -> str:
    s = set(days)
    if not s:
        return tr("Один раз")
    if len(s) == 7:
        return tr("Каждый день")
    if s == {0, 1, 2, 3, 4}:
        return tr("По будням")
    if s == {5, 6}:
        return tr("По выходным")
    return " ".join(DAYS_SHORT[d] for d in sorted(s))


def next_fire(alarms, now: dt.datetime):
    best = None
    for a in alarms:
        if not a["enabled"]:
            continue
        h, m = map(int, a["time"].split(":"))
        for off in range(8):
            cand = dt.datetime.combine(now.date() + dt.timedelta(days=off), dt.time(h, m))
            if cand > now and (not a["days"] or cand.weekday() in a["days"]):
                if best is None or cand < best[1]:
                    best = (a, cand)
                break
    return best


def fmt_in(minutes: int) -> str:
    d, rem = divmod(minutes, 1440)
    h, m = divmod(rem, 60)
    parts = []
    if d:
        parts.append(tr("{} дн", d))
    if h:
        parts.append(tr("{} ч", h))
    if m or not parts:
        parts.append(tr("{} мин", m))
    return tr("через ") + " ".join(parts)


def fmt_hms(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_sw(ms: float) -> str:
    cs = int(ms // 10)
    s, cs = divmod(cs, 100)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}" if h else f"{m:02d}:{s:02d}.{cs:02d}"


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


# ════════════════════════════════════════════════════════════════════════════
#  СВОИ ВИДЖЕТЫ
# ════════════════════════════════════════════════════════════════════════════
class Switch(QAbstractButton):
    """Переключатель вкл/выкл."""

    def __init__(self, checked: bool = False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(THEME["accent"] if on else THEME["surface2"]))
        p.drawRoundedRect(self.rect(), 13, 13)
        p.setBrush(QColor(THEME["base"] if on else THEME["text"]))
        x = self.width() - 23 if on else 3
        p.drawEllipse(x, 3, 20, 20)


class RingWidget(QWidget):
    """Круг с прогрессом и крупным текстом в середине."""

    def __init__(self):
        super().__init__()
        self.fraction = 1.0
        self.text = "00:00"
        self.sub = ""
        self.color_key = "accent"
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_state(self, fraction, text, sub="", color_key="accent"):
        self.fraction, self.text, self.sub, self.color_key = fraction, text, sub, color_key
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 24
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        pen = QPen(QColor(THEME["surface1"]), max(8.0, side * 0.045))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawEllipse(rect)
        if self.fraction > 0:
            pen.setColor(QColor(THEME[self.color_key]))
            p.setPen(pen)
            p.drawArc(rect, 90 * 16, -int(360 * 16 * min(1.0, self.fraction)))
        f = QFont(self.font())
        f.setBold(True)
        f.setPixelSize(int(side * (0.2 if len(self.text) <= 5 else 0.14)))
        p.setFont(f)
        p.setPen(QColor(THEME["text"]))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)
        if self.sub:
            f2 = QFont(self.font())
            f2.setPixelSize(max(11, int(side * 0.06)))
            p.setFont(f2)
            p.setPen(QColor(THEME["subtext"]))
            p.drawText(rect.translated(0, side * 0.17), Qt.AlignmentFlag.AlignCenter, self.sub)


class PadSpin(QSpinBox):
    def textFromValue(self, v: int) -> str:
        return f"{v:02d}"


class _NumEdit(QLineEdit):
    """Поле числа: колесо мыши и стрелки ↑/↓ меняют значение."""

    def __init__(self, field):
        super().__init__()
        self._field = field

    def wheelEvent(self, e):
        self._field.step(1 if e.angleDelta().y() > 0 else -1)
        e.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Up:
            self._field.step(1)
        elif e.key() == Qt.Key.Key_Down:
            self._field.step(-1)
        else:
            super().keyPressEvent(e)


class TimeField(QWidget):
    """Число с кнопками ▲ ▼ (часы, минуты, секунды)."""
    changed = pyqtSignal()

    def __init__(self, maximum: int, wrap: bool = False, caption: str = ""):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        up, down = QPushButton("▲"), QPushButton("▼")
        for b in (up, down):
            b.setObjectName("step")
            b.setAutoRepeat(True)
            b.setAutoRepeatDelay(400)
            b.setAutoRepeatInterval(80)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.maximum = maximum
        self.wrap = wrap
        self.edit = _NumEdit(self)
        self.edit.setObjectName("bigedit")
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.setMaxLength(len(str(maximum)))
        self.edit.setValidator(QIntValidator(0, maximum, self))
        self.edit.setText("00")
        self.edit.textEdited.connect(lambda _: self.changed.emit())
        self.edit.editingFinished.connect(lambda: self.setValue(self.value()))
        up.clicked.connect(lambda: self.step(1))
        down.clicked.connect(lambda: self.step(-1))
        v.addWidget(up)
        v.addWidget(self.edit)
        v.addWidget(down)
        if caption:
            c = QLabel(caption)
            c.setObjectName("subtle")
            c.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(c)

    def value(self) -> int:
        try:
            return max(0, min(self.maximum, int(self.edit.text() or 0)))
        except ValueError:
            return 0

    def setValue(self, v: int) -> None:
        v = max(0, min(self.maximum, int(v)))
        old = self.edit.text()
        self.edit.setText(f"{v:02d}")
        if old != self.edit.text():
            self.changed.emit()

    def step(self, d: int) -> None:
        v = self.value() + d
        if self.wrap:
            v = 0 if v > self.maximum else (self.maximum if v < 0 else v)
        self.setValue(v)


class SoundPicker(QWidget):
    """Выбор мелодии: встроенные или свой файл + кнопка прослушивания."""
    changed = pyqtSignal()

    def __init__(self, win, allow_default: bool):
        super().__init__()
        self.win = win
        self._previewing = False
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.combo = QComboBox()
        if allow_default:
            self.combo.addItem(tr("Как в настройках"), "")
        for key, (name, _, _) in BUILTIN_SOUNDS.items():
            self.combo.addItem(name, f"builtin:{key}")
        self.combo.addItem(tr("Свой файл…"), "__file__")
        self._prev = 0
        self.combo.activated.connect(self._activated)
        self.btn = QPushButton("▶")
        self.btn.setObjectName("icon")
        self.btn.setToolTip(tr("Прослушать"))
        self.btn.clicked.connect(self._preview)
        h.addWidget(self.combo, 1)
        h.addWidget(self.btn)
        win.player.stateChanged.connect(self._state)

    def value(self) -> str:
        v = self.combo.currentData()
        return "" if v == "__file__" else (v or "")

    def _is_custom(self, data) -> bool:
        return bool(data) and not str(data).startswith("builtin:") and data != "__file__"

    def set_value(self, v: str) -> None:
        if self._is_custom(v):
            for i in reversed(range(self.combo.count())):
                if self._is_custom(self.combo.itemData(i)):
                    self.combo.removeItem(i)
            self.combo.insertItem(self.combo.count() - 1, Path(v).name, v)
        idx = self.combo.findData(v)
        self.combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._prev = self.combo.currentIndex()

    def _activated(self, i: int) -> None:
        if self.combo.itemData(i) == "__file__":
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Выберите мелодию"), str(Path.home()),
                tr("Аудио (*.mp3 *.ogg *.wav *.flac *.opus *.m4a);;Все файлы (*)"))
            if path:
                self.set_value(path)
            else:
                self.combo.setCurrentIndex(self._prev)
        self._prev = self.combo.currentIndex()
        self.changed.emit()

    def _preview(self) -> None:
        if self._previewing:
            self.win.player.stop()
            return
        self._previewing = True
        self.btn.setText("■")
        self.win.player.play(self.value() or self.win.settings["sound"],
                             self.win.settings["volume"], loop=False)

    def _state(self, playing: bool) -> None:
        if not playing:
            self._previewing = False
        self.btn.setText("■" if (playing and self._previewing) else "▶")


# ════════════════════════════════════════════════════════════════════════════
#  ОКНА СООБЩЕНИЙ
# ════════════════════════════════════════════════════════════════════════════
class RingDialog(QDialog):
    """Окно «звонит!» поверх всех окон."""
    snoozed = pyqtSignal()

    def __init__(self, title: str, text: str, snooze_min: int = 0):
        super().__init__(None)
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(400)
        v = QVBoxLayout(self)
        v.setContentsMargins(32, 28, 32, 28)
        v.setSpacing(10)
        t = QLabel(title)
        t.setObjectName("ringtitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setWordWrap(True)
        s = QLabel(text)
        s.setObjectName("subtle")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)
        v.addWidget(s)
        v.addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)
        if snooze_min:
            b = QPushButton(tr("Отложить на {} мин", snooze_min))
            b.clicked.connect(self._snooze)
            row.addWidget(b)
        stop = QPushButton(tr("Стоп"))
        stop.setObjectName("primary")
        stop.setDefault(True)
        stop.clicked.connect(self.accept)
        row.addWidget(stop)
        v.addLayout(row)

    def _snooze(self) -> None:
        self.snoozed.emit()
        self.accept()


class AlarmDialog(QDialog):
    def __init__(self, win, alarm: dict | None):
        super().__init__(win)
        self.setWindowTitle(tr("Будильник"))
        self.setMinimumWidth(420)
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(14)

        if alarm:
            h, m = map(int, alarm["time"].split(":"))
        else:
            n = dt.datetime.now() + dt.timedelta(minutes=5)
            h, m = n.hour, n.minute
        self.hour = TimeField(23, wrap=True, caption=tr("часы"))
        self.minute = TimeField(59, wrap=True, caption=tr("минуты"))
        self.hour.setValue(h)
        self.minute.setValue(m)
        trow = QHBoxLayout()
        trow.addStretch()
        trow.addWidget(self.hour)
        colon = QLabel(":")
        colon.setObjectName("colon")
        colon.setAlignment(Qt.AlignmentFlag.AlignTop)
        colon.setContentsMargins(0, 28, 0, 0)
        trow.addWidget(colon)
        trow.addWidget(self.minute)
        trow.addStretch()
        v.addLayout(trow)

        self.name = QLineEdit(alarm["label"] if alarm else "")
        self.name.setPlaceholderText(tr("Название (необязательно)"))
        v.addWidget(self.name)

        self.day_btns = []
        drow = QHBoxLayout()
        drow.setSpacing(6)
        for i, d in enumerate(DAYS_SHORT):
            b = QPushButton(d)
            b.setObjectName("day")
            b.setCheckable(True)
            b.setChecked(bool(alarm) and i in alarm["days"])
            self.day_btns.append(b)
            drow.addWidget(b)
        v.addLayout(drow)
        hint = QLabel(tr("Дни не выбраны — будильник сработает один раз."))
        hint.setObjectName("subtle")
        v.addWidget(hint)

        self.sound = SoundPicker(win, allow_default=True)
        self.sound.set_value(alarm["sound"] if alarm else "")
        v.addWidget(self.sound)

        row = QHBoxLayout()
        row.setSpacing(10)
        cancel = QPushButton(tr("Отмена"))
        cancel.clicked.connect(self.reject)
        ok = QPushButton(tr("Сохранить"))
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        v.addLayout(row)

    def result_data(self) -> dict:
        return {
            "time": f"{self.hour.value():02d}:{self.minute.value():02d}",
            "label": self.name.text().strip(),
            "days": [i for i, b in enumerate(self.day_btns) if b.isChecked()],
            "enabled": True,
            "sound": self.sound.value(),
        }


# ════════════════════════════════════════════════════════════════════════════
#  ВКЛАДКА «БУДИЛЬНИК»
# ════════════════════════════════════════════════════════════════════════════
class AlarmRow(QFrame):
    def __init__(self, alarm: dict, on_toggle, on_edit, on_delete):
        super().__init__()
        self.setObjectName("card")
        h = QHBoxLayout(self)
        h.setContentsMargins(18, 12, 12, 12)
        h.setSpacing(12)
        t = QLabel(alarm["time"])
        t.setObjectName("rowtime")
        mid = QVBoxLayout()
        mid.setSpacing(0)
        name = QLabel(alarm["label"] or tr("Будильник"))
        name.setObjectName("rowname")
        days = QLabel(describe_days(alarm["days"]))
        days.setObjectName("subtle")
        mid.addWidget(name)
        mid.addWidget(days)
        sw = Switch(alarm["enabled"])
        sw.toggled.connect(on_toggle)
        edit = QPushButton("✎")
        edit.setObjectName("flat")
        edit.setToolTip(tr("Изменить"))
        edit.clicked.connect(on_edit)
        rm = QPushButton("✕")
        rm.setObjectName("flat")
        rm.setToolTip(tr("Удалить"))
        rm.clicked.connect(on_delete)
        h.addWidget(t)
        h.addLayout(mid, 1)
        h.addWidget(sw)
        h.addWidget(edit)
        h.addWidget(rm)
        if not alarm["enabled"]:
            for w in (t, name, days):
                w.setEnabled(False)


class AlarmTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 14, 0, 0)
        v.setSpacing(12)
        top = QHBoxLayout()
        self.next_label = QLabel()
        self.next_label.setObjectName("subtle")
        add = QPushButton(tr("＋ Новый будильник"))
        add.setObjectName("primary")
        add.clicked.connect(lambda: self.edit(None))
        top.addWidget(self.next_label, 1)
        top.addWidget(add)
        v.addLayout(top)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("scrollbody")
        self.rows = QVBoxLayout(body)
        self.rows.setContentsMargins(0, 0, 6, 0)
        self.rows.setSpacing(10)
        self.rows.addStretch()
        scroll.setWidget(body)
        v.addWidget(scroll, 1)
        self.refresh()

    @property
    def alarms(self):
        return self.win.settings["alarms"]

    def refresh(self) -> None:
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.alarms:
            e = QLabel(tr("Будильников пока нет.\nНажмите «Новый будильник»."))
            e.setObjectName("subtle")
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e.setContentsMargins(0, 50, 0, 0)
            self.rows.insertWidget(0, e)
        for i, a in enumerate(self.alarms):
            row = AlarmRow(a, lambda on, i=i: self.toggle(i, on),
                           lambda _=False, i=i: self.edit(i),
                           lambda _=False, i=i: self.delete(i))
            self.rows.insertWidget(i, row)
        self.update_next()

    def update_next(self) -> None:
        nf = next_fire(self.alarms, dt.datetime.now())
        if not nf:
            self.next_label.setText(tr("Нет включённых будильников"))
            return
        a, when = nf
        mins = math.ceil((when - dt.datetime.now()).total_seconds() / 60)
        self.next_label.setText(tr("Ближайший: {}", fmt_in(max(1, mins))))

    def toggle(self, i: int, on: bool) -> None:
        self.alarms[i]["enabled"] = on
        self.win.settings.save()
        self.refresh()

    def edit(self, i) -> None:
        dlg = AlarmDialog(self.win, self.alarms[i] if i is not None else None)
        if dlg.exec():
            data = dlg.result_data()
            if i is None:
                self.alarms.append(data)
            else:
                self.alarms[i] = data
            self.alarms.sort(key=lambda a: a["time"])
            self.win.settings.save()
            self.refresh()

    def delete(self, i: int) -> None:
        del self.alarms[i]
        self.win.settings.save()
        self.refresh()


# ════════════════════════════════════════════════════════════════════════════
#  ВКЛАДКА «ТАЙМЕР»
# ════════════════════════════════════════════════════════════════════════════
class TimerTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.state = "idle"  # idle / running / paused
        self.total_ms = 0
        self.remaining_ms = 0.0
        self.end = 0.0

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(12)
        self.ring = RingWidget()
        v.addWidget(self.ring, 1)

        self.setup = QWidget()
        sv = QVBoxLayout(self.setup)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.h = TimeField(99, caption=tr("часы"))
        self.m = TimeField(59, caption=tr("минуты"))
        self.s = TimeField(59, caption=tr("секунды"))
        hh, mm, ss = win.settings["timer"]
        self.h.setValue(int(hh))
        self.m.setValue(int(mm))
        self.s.setValue(int(ss))
        row.addStretch()
        for f in (self.h, self.m, self.s):
            row.addWidget(f)
            f.changed.connect(self._fields_changed)
        row.addStretch()
        sv.addLayout(row)
        pres = QHBoxLayout()
        pres.setSpacing(8)
        for label, secs in [(tr("1 мин"), 60), (tr("5 мин"), 300), (tr("10 мин"), 600),
                            (tr("15 мин"), 900), (tr("30 мин"), 1800), (tr("1 час"), 3600)]:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, s=secs: self._preset(s))
            pres.addWidget(b)
        sv.addLayout(pres)
        v.addWidget(self.setup)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.start_btn = QPushButton(tr("Старт"))
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.toggle)
        self.reset_btn = QPushButton(tr("Сброс"))
        self.reset_btn.clicked.connect(self.reset)
        btns.addWidget(self.start_btn, 1)
        btns.addWidget(self.reset_btn)
        v.addLayout(btns)

        self.clock = QTimer(self)
        self.clock.setInterval(100)
        self.clock.timeout.connect(self.tick)
        self._apply_state()

    def _fields_total(self) -> int:
        return self.h.value() * 3600 + self.m.value() * 60 + self.s.value()

    def _preset(self, secs: int) -> None:
        self.h.setValue(secs // 3600)
        self.m.setValue(secs % 3600 // 60)
        self.s.setValue(secs % 60)

    def _fields_changed(self) -> None:
        if self.state == "idle":
            self._apply_state()

    def _apply_state(self) -> None:
        st = self.state
        # таймер просыпается только пока идёт отсчёт
        if st == "running":
            self.clock.start()
        else:
            self.clock.stop()
        self.setup.setVisible(st == "idle")
        self.start_btn.setText({"idle": tr("Старт"), "running": tr("Пауза"), "paused": tr("Продолжить")}[st])
        self.reset_btn.setEnabled(st != "idle")
        if st == "idle":
            total = self._fields_total()
            self.ring.set_state(1.0, fmt_hms(total),
                                tr("установлено") if total else tr("задайте время"))
        else:
            self._paint()

    def _paint(self) -> None:
        secs = math.ceil(self.remaining_ms / 1000)
        frac = self.remaining_ms / self.total_ms if self.total_ms else 0
        paused = self.state == "paused"
        self.ring.set_state(frac, fmt_hms(secs), tr("пауза") if paused else tr("осталось"),
                            "yellow" if paused else "accent")

    def toggle(self) -> None:
        if self.state == "idle":
            total = self._fields_total()
            if total <= 0:
                return
            self.win.settings["timer"] = [self.h.value(), self.m.value(), self.s.value()]
            self.win.settings.save()
            self.total_ms = total * 1000
            self.remaining_ms = float(self.total_ms)
            self.end = time.monotonic() + total
            self.state = "running"
        elif self.state == "running":
            self.remaining_ms = max(0.0, (self.end - time.monotonic()) * 1000)
            self.state = "paused"
        else:
            self.end = time.monotonic() + self.remaining_ms / 1000
            self.state = "running"
        self._apply_state()

    def reset(self) -> None:
        self.state = "idle"
        self._apply_state()

    def tick(self) -> None:
        if self.state != "running":
            return
        rem = (self.end - time.monotonic()) * 1000
        if rem <= 0:
            total = self.total_ms // 1000
            self.state = "idle"
            self._apply_state()
            self.win.ring(tr("Таймер"), tr("Время вышло: {}", fmt_hms(total)), None)
            return
        self.remaining_ms = rem
        # окно скрыто — кольцо не рисуем и просыпаемся реже, но к концу отсчёта точно
        if self.isVisible():
            self.clock.setInterval(100)
            self._paint()
        else:
            self.clock.setInterval(int(min(1000, max(20, rem))))


# ════════════════════════════════════════════════════════════════════════════
#  ВКЛАДКА «СЕКУНДОМЕР»
# ════════════════════════════════════════════════════════════════════════════
class StopwatchTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.running = False
        self.base_ms = 0.0
        self.t0 = 0.0
        self.last_lap_ms = 0.0
        self.lap_count = 0

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 24, 0, 0)
        v.setSpacing(14)
        self.display = QLabel(fmt_sw(0))
        self.display.setObjectName("swdisplay")
        self.display.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.display)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.start_btn = QPushButton(tr("Старт"))
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.toggle)
        self.lap_btn = QPushButton(tr("Круг"))
        self.lap_btn.clicked.connect(self.lap)
        self.reset_btn = QPushButton(tr("Сброс"))
        self.reset_btn.clicked.connect(self.reset)
        btns.addWidget(self.start_btn, 1)
        btns.addWidget(self.lap_btn)
        btns.addWidget(self.reset_btn)
        v.addLayout(btns)

        self.laps = QListWidget()
        self.laps.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.laps.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.laps.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        v.addWidget(self.laps, 1)

        self.clock = QTimer(self)
        self.clock.setInterval(30)
        self.clock.timeout.connect(self._tick)
        self._buttons()

    def elapsed(self) -> float:
        return self.base_ms + ((time.monotonic() - self.t0) * 1000 if self.running else 0)

    def _buttons(self) -> None:
        self.start_btn.setText(tr("Стоп") if self.running else tr("Старт"))
        self.lap_btn.setEnabled(self.running)
        self.reset_btn.setEnabled(not self.running and self.elapsed() > 0)

    def _tick(self) -> None:
        if self.display.isVisible():
            self.clock.setInterval(30)
            self.display.setText(fmt_sw(self.elapsed()))
        else:
            self.clock.setInterval(1000)   # время всё равно считается от t0, не от тиков

    def toggle(self) -> None:
        if self.running:
            self.base_ms = self.elapsed()
            self.running = False
            self.clock.stop()
            self._tick()
        else:
            self.t0 = time.monotonic()
            self.running = True
            self.clock.start()
        self._buttons()

    def lap(self) -> None:
        total = self.elapsed()
        self.lap_count += 1
        text = f"{self.lap_count:>2}   +{fmt_sw(total - self.last_lap_ms)}   {fmt_sw(total)}"
        self.last_lap_ms = total
        self.laps.insertItem(0, QListWidgetItem(text))

    def reset(self) -> None:
        self.running = False
        self.clock.stop()
        self.base_ms = 0.0
        self.last_lap_ms = 0.0
        self.lap_count = 0
        self.laps.clear()
        self._tick()
        self._buttons()


# ════════════════════════════════════════════════════════════════════════════
#  ВКЛАДКА «НАСТРОЙКИ»
# ════════════════════════════════════════════════════════════════════════════
def card_row(title: str, widget: QWidget | None = None, hint: str = "") -> QFrame:
    c = QFrame()
    c.setObjectName("card")
    v = QVBoxLayout(c)
    v.setContentsMargins(18, 14, 18, 14)
    v.setSpacing(8)
    top = QHBoxLayout()
    t = QLabel(title)
    t.setObjectName("rowname")
    top.addWidget(t, 1)
    v.addLayout(top)
    if hint:
        h = QLabel(hint)
        h.setObjectName("subtle")
        h.setWordWrap(True)
        v.addWidget(h)
    if widget is not None:
        v.addWidget(widget)
    return c


class SettingsTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        st = win.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 14, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("scrollbody")
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(10)

        # тема
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        self.theme_combo = QComboBox()
        self.theme_combo.activated.connect(self._theme_chosen)
        bl.addWidget(self.theme_combo)
        trow = QHBoxLayout()
        trow.setSpacing(8)
        edit = QPushButton(tr("Править свои темы"))
        edit.clicked.connect(self._edit_themes)
        reload_ = QPushButton(tr("Перечитать темы"))
        reload_.clicked.connect(self._reload_themes)
        trow.addWidget(edit)
        trow.addWidget(reload_)
        bl.addLayout(trow)
        v.addWidget(card_row(tr("Цветовая тема"), box))
        self._fill_themes()
        kit_themes.on_list_change(self._fill_themes)   # новая тема из редактора тем — сразу в списке

        # мелодия
        self.sound = SoundPicker(win, allow_default=False)
        self.sound.set_value(st["sound"])
        self.sound.changed.connect(self._sound_changed)
        v.addWidget(card_row(tr("Мелодия по умолчанию"), self.sound))

        # громкость
        vbox = QWidget()
        vl = QHBoxLayout(vbox)
        vl.setContentsMargins(0, 0, 0, 0)
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(int(st["volume"]))
        self.vol_label = QLabel(f"{st['volume']}%")
        self.vol_label.setMinimumWidth(44)
        self.vol.valueChanged.connect(self._volume)
        self.vol.sliderReleased.connect(win.settings.save)
        vl.addWidget(self.vol, 1)
        vl.addWidget(self.vol_label)
        v.addWidget(card_row(tr("Громкость"), vbox))

        # откладывание
        self.snooze = QComboBox()
        for n in (1, 2, 5, 10, 15, 20, 30):
            self.snooze.addItem(tr("{} мин", n), n)
        idx = self.snooze.findData(int(st["snooze"]))
        self.snooze.setCurrentIndex(idx if idx >= 0 else 2)
        self.snooze.activated.connect(self._snooze)
        v.addWidget(card_row(tr("Кнопка «Отложить» откладывает на"), self.snooze))

        # трей
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_sw = Switch(bool(st["tray"]))
            self.tray_sw.toggled.connect(self._tray)
            c = card_row(tr("Не закрывать, а прятать в трей"),
                         hint=tr("Пока программа в трее, будильники и таймер продолжают работать. "
                              "Полностью выйти можно через меню значка в трее."))
            c.layout().itemAt(0).layout().addWidget(self.tray_sw)
            v.addWidget(c)
        # запуск вместе с системой (сразу в трей)
        self.autostart = Autostart("equestria-clock", "Equestria Clock",
                                   tr("Будильник, таймер и секундомер"))
        self.auto_sw = Switch(self.autostart.is_enabled())
        self.auto_sw.toggled.connect(self._autostart)
        c = card_row(tr("Запускать вместе с системой"),
                     hint=tr("Часы стартуют свёрнутыми в трей, чтобы будильники работали сразу после входа."))
        c.layout().itemAt(0).layout().addWidget(self.auto_sw)
        v.addWidget(c)
        v.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def _autostart(self, on: bool) -> None:
        if on and not self.win.settings["tray"]:
            # без трея окно при автозапуске пришлось бы показывать — включаем трей
            self.win.settings["tray"] = True
            self.win.settings.save()
            if hasattr(self, "tray_sw"):
                self.tray_sw.setChecked(True)
        self.autostart.set_enabled(on)

    # --- темы
    def _fill_themes(self) -> None:
        self.theme_combo.clear()
        for name in ALL_THEMES:
            self.theme_combo.addItem(name, name)
        i = self.theme_combo.findData(self.win.settings["theme"])
        self.theme_combo.setCurrentIndex(max(0, i))

    def _theme_chosen(self, i: int) -> None:
        self.win.set_theme(self.theme_combo.itemData(i))

    def _edit_themes(self) -> None:
        path = CONFIG_DIR / "themes.json"
        if not path.exists():
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            example = {"Моя тема": dict(THEMES[DEFAULT_THEME])}
            path.write_text(json.dumps(example, ensure_ascii=False, indent=2), encoding="utf-8")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _reload_themes(self) -> None:
        load_all_themes()
        self._fill_themes()
        self.win.set_theme(self.theme_combo.currentData())

    # --- прочее
    def _sound_changed(self) -> None:
        self.win.settings["sound"] = self.sound.value() or "builtin:chime"
        self.win.settings.save()

    def _volume(self, val: int) -> None:
        self.vol_label.setText(f"{val}%")
        self.win.settings["volume"] = val
        self.win.player.set_volume(val)
        if not self.vol.isSliderDown():
            self.win.settings.save()

    def _snooze(self, i: int) -> None:
        self.win.settings["snooze"] = self.snooze.itemData(i)
        self.win.settings.save()

    def _tray(self, on: bool) -> None:
        self.win.settings["tray"] = on
        self.win.settings.save()


# ════════════════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.player = SoundPlayer(self)
        self.player.set_volume(int(settings["volume"]))
        self._rings: list[RingDialog] = []
        self.snoozes: list[dict] = []
        self._last_minute = ""
        self._quitting = False
        self._tray_hint_shown = False

        self.setWindowTitle("Equestria Clock")
        self.setWindowIcon(make_icon())
        self.resize(580, 740)
        self.setMinimumSize(500, 620)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(2)
        self.clock_label = QLabel()
        self.clock_label.setObjectName("bigclock")
        self.date_label = QLabel()
        self.date_label.setObjectName("subtle")
        root.addWidget(self.clock_label)
        root.addWidget(self.date_label)

        self.alarm_tab = AlarmTab(self)
        self.timer_tab = TimerTab(self)
        self.sw_tab = StopwatchTab(self)
        self.settings_tab = SettingsTab(self)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.alarm_tab, tr("Будильник"))
        self.tabs.addTab(self.timer_tab, tr("Таймер"))
        self.tabs.addTab(self.sw_tab, tr("Секундомер"))
        self.tabs.addTab(self.settings_tab, tr("Настройки"))
        root.addWidget(self.tabs, 1)

        # значок в трее
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(make_icon(), self)
            self.tray.setToolTip("Equestria Clock")
            menu = QMenu()
            show = QAction(tr("Показать"), self)
            show.triggered.connect(self.show_window)
            quit_ = QAction(tr("Выход"), self)
            quit_.triggered.connect(self.quit_app)
            menu.addAction(show)
            menu.addAction(quit_)
            self._tray_menu = menu
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._tray_clicked)
            self.tray.show()

        # Главный «тик» — одиночный таймер, который сам назначает следующий запуск:
        # окно открыто → ровно на следующей секунде (для цифр на экране);
        # окно в трее → на следующей минуте или к ближайшему «Отложить» (будильникам
        # секунды не нужны), так программа в фоне почти не будит процессор.
        self.clock = QTimer(self)
        self.clock.setSingleShot(True)
        self.clock.setTimerType(Qt.TimerType.PreciseTimer)
        self.clock.timeout.connect(self.tick)
        self.tick()

    # --- тема
    def set_theme(self, name: str) -> None:
        self.settings["theme"] = apply_theme(name)
        self.settings.save()
        for w in self.findChildren(QWidget):
            w.update()
        self.setWindowIcon(make_icon())

    # --- трей
    def _tray_clicked(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True
        self.settings.save()
        self.player.stop()
        QApplication.quit()

    def closeEvent(self, e):
        if self.tray and self.settings["tray"] and not self._quitting:
            e.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.showMessage(tr("Equestria Clock продолжает работать"),
                                      tr("Будильники сработают, пока программа в трее."))
        else:
            e.accept()
            self.quit_app()

    # --- звонок
    def ring(self, title: str, text: str, sound: str | None, snooze_cb=None) -> None:
        self.player.play(sound or self.settings["sound"], int(self.settings["volume"]))
        dlg = RingDialog(title, text, int(self.settings["snooze"]) if snooze_cb else 0)
        if snooze_cb:
            dlg.snoozed.connect(snooze_cb)
        dlg.finished.connect(lambda _=0, d=dlg: self._ring_closed(d))
        self._rings.append(dlg)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        if self.tray:
            self.tray.showMessage(title, text)

    def _ring_closed(self, dlg: RingDialog) -> None:
        if dlg in self._rings:
            self._rings.remove(dlg)
        if not self._rings:
            self.player.stop()

    def _fire_alarm(self, a: dict) -> None:
        title = a["label"] or tr("Будильник")

        def snooze():
            mins = int(self.settings["snooze"])
            self.snoozes.append({
                "at": dt.datetime.now() + dt.timedelta(minutes=mins),
                "alarm": a,
            })

        self.ring(title, a["time"], a["sound"], snooze_cb=snooze)

    # --- главный «тик»
    def _on_screen(self) -> bool:
        return self.isVisible() and not self.isMinimized()

    def _schedule_tick(self, now: dt.datetime) -> None:
        if self._on_screen():
            ms = 1000 - now.microsecond // 1000 + 5
        else:
            nxt = now.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
            if self.snoozes:
                nxt = min(nxt, min(s["at"] for s in self.snoozes))
            ms = max(50, int((nxt - now).total_seconds() * 1000) + 5)
        self.clock.start(ms)

    def showEvent(self, e):
        super().showEvent(e)
        self.tick()   # окно снова видно — сразу показываем точное время и тикаем посекундно

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.WindowStateChange and not self.isMinimized():
            self.tick()

    def tick(self) -> None:
        now = dt.datetime.now()
        if self._on_screen():
            self.clock_label.setText(now.strftime("%H:%M:%S"))
            self.date_label.setText(
                f"{WEEKDAYS[now.weekday()].capitalize()}, {now.day} {MONTHS[now.month - 1]}")

        for s in list(self.snoozes):
            if now >= s["at"]:
                self.snoozes.remove(s)
                self._fire_alarm(s["alarm"])

        key = now.strftime("%Y-%m-%d %H:%M")
        if key != self._last_minute:
            self._last_minute = key
            hhmm = now.strftime("%H:%M")
            changed = False
            for a in self.settings["alarms"]:
                if a["enabled"] and a["time"] == hhmm and (not a["days"] or now.weekday() in a["days"]):
                    self._fire_alarm(a)
                    if not a["days"]:  # одноразовый — выключаем
                        a["enabled"] = False
                        changed = True
            if changed:
                self.settings.save()
                self.alarm_tab.refresh()
            else:
                self.alarm_tab.update_next()
        self._schedule_tick(now)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Clock")
    app.setDesktopFileName("equestria-clock")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    instance = SingleInstance(APP_NAME)
    if not instance.claim():   # уже запущен (в трее) — показываем его окно
        instance.notify_running(show="--hidden" not in sys.argv)
        return 0

    settings = Settings()
    load_all_themes()
    settings["theme"] = apply_theme(kit_themes.current_name())
    win = MainWindow(settings)
    kit_themes.follow(win.set_theme, lambda: win.settings["theme"])
    instance.on_show(win.show_window)
    if not ("--hidden" in sys.argv and win.tray is not None and win.settings["tray"]):
        win.show()
    code = app.exec()
    instance.release()
    return code


if __name__ == "__main__":
    sys.exit(main())