#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Equestria Recorder — запись звука с микрофона в WAV и простая обрезка (PyQt6).

Выбор микрофона, папки, усиления; индикатор громкости; обрезка записи; темы.
Темы: словарь _T ниже (12 цветов в порядке KEYS) — просто добавьте строку.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import time
import wave
from array import array
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QDesktopServices, QLinearGradient,
                         QPainter, QPalette, QPen)
from PyQt6.QtMultimedia import (QAudioFormat, QAudioOutput, QAudioSource,
                                QMediaDevices, QMediaPlayer)
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog,
                             QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QLayout, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMenu, QMessageBox, QPushButton,
                             QSlider, QVBoxLayout, QWidget)

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from functools import partial
from equestria_kit import widgets as kit_widgets

card = partial(kit_widgets.card, upper=True, margins=(16, 10, 16, 12), spacing=6)
from equestria_kit import themes as kit_themes
from equestria_kit import i18n as kit_i18n

tr = kit_i18n.install("equestria-recorder", __file__)

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-recorder" / "settings.json"

# ════════════════════════════════════════════════════════════════════════════
#  ТЕМЫ
# ════════════════════════════════════════════════════════════════════════════

# Темы общие для всех приложений Equestria OS: см. equestria_kit/themes.py.
# Свои темы — файлы ~/.config/equestria-os/themes/*.json.
KEYS = kit_themes.KEYS
THEMES = kit_themes.THEMES
DEFAULT_THEME = kit_themes.DEFAULT_THEME
THEME: dict = dict(THEMES[DEFAULT_THEME])

QSS = """
QMainWindow, QDialog { background: @base@; }
QWidget { color: @text@; font-size: 15px; }
QLabel { background: transparent; }
QLabel#time { font-size: 48px; font-weight: 700; }
QLabel#h2 { color: @accent@; font-size: 13px; font-weight: 700; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#db { color: @subtext@; min-width: 64px; }
QLabel#warn { color: @red@; font-weight: 700; font-size: 13px; }
QFrame#card { background: @mantle@; border-radius: 14px; }
QPushButton { background: @surface0@; border: none; border-radius: 12px;
    padding: 10px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#rec { background: @red@; color: @base@; font-size: 17px; padding: 14px; }
QPushButton#rec:hover { background: @red@; }
QPushButton#rec:disabled { background: @surface1@; color: @surface2@; }
QPushButton#primary { background: @accent@; color: @base@; }
QPushButton#primary:hover { background: @accent@; }
QPushButton#small { padding: 6px 14px; font-size: 13px; border-radius: 10px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QLineEdit { background: @surface0@; border: 2px solid transparent; border-radius: 10px;
    padding: 8px 12px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QComboBox { padding: 6px 10px; }
QComboBox QAbstractItemView { background: @surface0@; color: @text@; outline: 0;
    selection-background-color: @surface1@; selection-color: @text@; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { background: @surface0@; border-radius: 8px; padding: 8px 12px; margin: 2px 0; }
QListWidget::item:selected { background: @surface1@; color: @accent@; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSlider::groove:horizontal { height: 6px; background: @surface1@; border-radius: 3px; }
QSlider::sub-page:horizontal { background: @accent@; border-radius: 3px; }
QSlider::handle:horizontal { background: @accent@; width: 16px; height: 16px;
    margin: -5px 0; border-radius: 8px; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
"""


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME)


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)


# ════════════════════════════════════════════════════════════════════════════
#  ИНДИКАТОР ГРОМКОСТИ
# ════════════════════════════════════════════════════════════════════════════
def to_level(peak: int) -> float:
    """Пик (0..32768) -> 0..1 по шкале -60..0 дБ."""
    db = 20 * math.log10(max(peak, 1) / 32768)
    return max(0.0, min(1.0, (db + 60) / 60))


class LevelMeter(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(26)
        self.target = self.level = self.peak = 0.0
        self.hold = 0
        t = QTimer(self)
        t.setInterval(30)
        t.timeout.connect(self._tick)
        t.start()

    def set_level(self, lv: float) -> None:
        self.target = max(self.target, lv)

    def _tick(self) -> None:
        self.level = self.target if self.target > self.level else max(self.target, self.level - 0.04)
        self.target = 0.0
        if self.level >= self.peak:
            self.peak, self.hold = self.level, 30
        elif self.hold > 0:
            self.hold -= 1
        else:
            self.peak = max(self.level, self.peak - 0.015)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(THEME["surface0"]))
        p.drawRoundedRect(r, 8, 8)
        w = r.width() * self.level
        if w > 1:
            g = QLinearGradient(0, 0, r.width(), 0)
            g.setColorAt(0.0, QColor(THEME["green"]))
            g.setColorAt(0.7, QColor(THEME["green"]))
            g.setColorAt(0.85, QColor(THEME["yellow"]))
            g.setColorAt(1.0, QColor(THEME["red"]))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(0, 0, w, r.height()), 8, 8)
        if self.peak > 0.02:
            p.setBrush(QColor(THEME["text"]))
            p.drawRoundedRect(QRectF(r.width() * self.peak - 2, 3, 3, r.height() - 6), 1.5, 1.5)


# ════════════════════════════════════════════════════════════════════════════
#  МЕЛОЧИ
# ════════════════════════════════════════════════════════════════════════════
def fmt_time(sec: float) -> str:
    s = int(sec)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_t(sec: float) -> str:
    return f"{int(sec // 60):02d}:{sec % 60:04.1f}"


def wav_len(path: Path) -> str:
    try:
        with wave.open(str(path), "rb") as w:
            return fmt_time(w.getnframes() / w.getframerate())
    except Exception:
        return "?"


def confirm(parent, text: str, yes: str) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(tr("Подтверждение"))
    box.setText(text)
    ok = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(tr("Отмена"), QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is ok


# ════════════════════════════════════════════════════════════════════════════
#  ОБРЕЗКА
# ════════════════════════════════════════════════════════════════════════════
class Waveform(QWidget):
    """Волна звука с двумя маркерами (начало и конец выделения)."""
    changed = pyqtSignal()
    PAD = 10
    GAP = 0.002

    def __init__(self, peaks):
        super().__init__()
        self.peaks = peaks
        self.s, self.e = 0.0, 1.0
        self.cut = False
        self.play = None
        self.drag = None
        self.setMinimumHeight(130)
        self.setCursor(Qt.CursorShape.SplitHCursor)

    def set_range(self, s: float, e: float) -> None:
        s = max(0.0, min(s, e - self.GAP))
        e = min(1.0, max(e, s + self.GAP))
        self.s, self.e = s, e
        self.update()

    def _x(self, f: float) -> float:
        return self.PAD + f * (self.width() - 2 * self.PAD)

    def _f(self, x: float) -> float:
        return max(0.0, min(1.0, (x - self.PAD) / max(1, self.width() - 2 * self.PAD)))

    def _move(self, f: float) -> None:
        if self.drag == "s":
            self.set_range(f, self.e)
        else:
            self.set_range(self.s, f)
        self.changed.emit()

    def mousePressEvent(self, ev) -> None:
        f = self._f(ev.position().x())
        self.drag = "s" if abs(f - self.s) <= abs(f - self.e) else "e"
        self._move(f)

    def mouseMoveEvent(self, ev) -> None:
        if self.drag:
            self._move(self._f(ev.position().x()))

    def mouseReleaseEvent(self, ev) -> None:
        self.drag = None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(THEME["mantle"]))
        p.drawRoundedRect(QRectF(0, 0, W, H), 10, 10)
        n, span, mid = len(self.peaks), W - 2 * self.PAD, H / 2
        pen = QPen()
        pen.setWidthF(max(1.0, span / n * 0.7))
        for i, pk in enumerate(self.peaks):
            f = (i + 0.5) / n
            kept = (self.s <= f <= self.e) != self.cut
            pen.setColor(QColor(THEME["accent"] if kept else THEME["surface2"]))
            p.setPen(pen)
            hh = max(1.0, pk * (mid - 10))
            x = self.PAD + f * span
            p.drawLine(QPointF(x, mid - hh), QPointF(x, mid + hh))
        col = QColor(THEME["red"] if self.cut else THEME["accent"])
        col.setAlpha(50)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRect(QRectF(self._x(self.s), 0, self._x(self.e) - self._x(self.s), H))
        p.setPen(QPen(QColor(THEME["text"]), 2))
        p.setBrush(QColor(THEME["text"]))
        for f in (self.s, self.e):
            x = self._x(f)
            p.drawLine(QPointF(x, 0), QPointF(x, H))
            p.drawEllipse(QPointF(x, 9), 6, 6)
            p.drawEllipse(QPointF(x, H - 9), 6, 6)
        if self.play is not None:
            p.setPen(QPen(QColor(THEME["yellow"]), 2))
            x = self._x(max(0.0, min(1.0, self.play)))
            p.drawLine(QPointF(x, 0), QPointF(x, H))


class TrimDialog(QDialog):
    def __init__(self, win, path: Path):
        super().__init__(win)
        self.win, self.path = win, path
        self.result_path: Path | None = None
        self.ok = False
        self.playing = False
        self.seen_playing = False
        self.setWindowTitle(tr("Обрезка записи"))
        self.setMinimumWidth(540)
        try:
            self._load()
        except Exception as e:
            QMessageBox.warning(win, tr("Обрезка"), tr("Не удалось открыть файл:\n{}", e))
            return
        self.ok = True

        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        title = QLabel(path.name)
        title.setObjectName("h2")
        v.addWidget(title)
        hint = QLabel(tr("Потяните маркеры на волне или введите секунды. "
                      "Яркая часть — то, что останется в файле."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.wave = Waveform(self.peaks)
        self.wave.changed.connect(self._from_wave)
        v.addWidget(self.wave)

        self.sp_s, self.sp_e = self._spin(0.0), self._spin(self.dur)
        self.sp_s.editingFinished.connect(self._from_spins)
        self.sp_e.editingFinished.connect(self._from_spins)
        row = QHBoxLayout()
        for cap, sp in ((tr("Начало, сек"), self.sp_s), (tr("Конец, сек"), self.sp_e)):
            col = QVBoxLayout()
            col.setSpacing(2)
            lab = QLabel(cap)
            lab.setObjectName("hint")
            col.addWidget(lab)
            col.addWidget(sp)
            row.addLayout(col, 1)
        v.addLayout(row)

        self.keep_btn = QPushButton(tr("Оставить выделенное"))
        self.cut_btn = QPushButton(tr("Вырезать выделенное"))
        for b, cut in ((self.keep_btn, False), (self.cut_btn, True)):
            b.setObjectName("small")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, c=cut: self._set_mode(c))
        self.keep_btn.setChecked(True)
        mrow = QHBoxLayout()
        mrow.addWidget(self.keep_btn)
        mrow.addWidget(self.cut_btn)
        v.addLayout(mrow)
        self.info = QLabel("")
        self.info.setObjectName("hint")
        v.addWidget(self.info)

        self.prev_btn = QPushButton(tr("▶  Прослушать выделенное"))
        self.prev_btn.clicked.connect(self._toggle_preview)
        v.addWidget(self.prev_btn)
        brow = QHBoxLayout()
        cancel = QPushButton(tr("Отмена"))
        cancel.clicked.connect(self.reject)
        repl = QPushButton(tr("Заменить оригинал"))
        repl.clicked.connect(lambda: self._save(True))
        save = QPushButton(tr("Сохранить копией"))
        save.setObjectName("primary")
        save.clicked.connect(lambda: self._save(False))
        brow.addWidget(cancel)
        brow.addStretch()
        brow.addWidget(repl)
        brow.addWidget(save)
        v.addLayout(brow)

        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._update_info()

    # --- загрузка
    def _load(self) -> None:
        with wave.open(str(self.path), "rb") as w:
            self.nch, sw, self.rate, n = (w.getnchannels(), w.getsampwidth(),
                                          w.getframerate(), w.getnframes())
            if sw != 2:
                raise ValueError(tr("Поддерживаются только 16-битные WAV"))
            data = w.readframes(n)
        self.fw = 2 * self.nch
        self.nframes = len(data) // self.fw
        if self.nframes == 0:
            raise ValueError(tr("Файл пустой"))
        self.data = data[:self.nframes * self.fw]
        self.dur = self.nframes / self.rate
        arr = array("h")
        arr.frombytes(self.data)
        ch = arr[0::self.nch]
        L, bins = len(ch), min(700, max(50, len(ch)))
        self.peaks = []
        for i in range(bins):
            a, b = i * L // bins, (i + 1) * L // bins
            seg = ch[a:b:max(1, (b - a) // 64)]
            pk = max(max(seg), -min(seg)) if len(seg) else 0
            self.peaks.append((pk / 32768) ** 0.6)

    def _spin(self, value: float) -> QLineEdit:
        """Поле для секунд (обычное текстовое поле: со спинбоксами QSS глючит)."""
        e = QLineEdit(f"{value:.2f}")
        e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return e

    def _num(self, edit: QLineEdit, fallback: float) -> float:
        try:
            v = float(edit.text().replace(",", ".").strip())
        except ValueError:
            return fallback
        return max(0.0, min(self.dur, v))

    # --- синхронизация
    def _from_wave(self) -> None:
        for sp, f in ((self.sp_s, self.wave.s), (self.sp_e, self.wave.e)):
            sp.setText(f"{f * self.dur:.2f}")
        self._update_info()

    def _from_spins(self) -> None:
        s = self._num(self.sp_s, self.wave.s * self.dur)
        e = self._num(self.sp_e, self.wave.e * self.dur)
        self.wave.set_range(s / self.dur, e / self.dur)
        self._from_wave()

    def _set_mode(self, cut: bool) -> None:
        self.cut_btn.setChecked(cut)
        self.keep_btn.setChecked(not cut)
        self.wave.cut = cut
        self.wave.update()
        self._update_info()

    def _update_info(self) -> None:
        sel = (self.wave.e - self.wave.s) * self.dur
        rest = self.dur - sel if self.wave.cut else sel
        self.info.setText(tr("Было: {}     Выделено: {}     Останется: {}", fmt_t(self.dur), fmt_t(sel), fmt_t(rest)))

    # --- прослушивание
    def _toggle_preview(self) -> None:
        if self.playing:
            self._stop_preview()
            return
        self.playing, self.seen_playing = True, False
        self.prev_btn.setText(tr("■  Стоп"))
        self.win.play_path(self.path, int(self.wave.s * self.dur * 1000))

    def _stop_preview(self) -> None:
        self.playing = False
        self.win.player.stop()
        self.wave.play = None
        self.wave.update()
        self.prev_btn.setText(tr("▶  Прослушать выделенное"))

    def _tick(self) -> None:
        if not self.playing or self.win._pending_start is not None:
            return
        pos = self.win.player.position() / 1000
        if self.win.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.seen_playing = True
        elif self.seen_playing:
            self._stop_preview()
            return
        if pos >= self.wave.e * self.dur:
            self._stop_preview()
            return
        self.wave.play = pos / self.dur
        self.wave.update()

    # --- сохранение
    def _write(self, path: Path, out: bytes) -> None:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(self.nch)
            w.setsampwidth(2)
            w.setframerate(self.rate)
            w.writeframes(out)

    def _save(self, replace: bool) -> None:
        si, ei = int(self.wave.s * self.nframes), int(self.wave.e * self.nframes)
        fw = self.fw
        out = (self.data[:si * fw] + self.data[ei * fw:]) if self.wave.cut else self.data[si * fw:ei * fw]
        if not out:
            QMessageBox.warning(self, tr("Обрезка"), tr("Получится пустой файл — измените выделение."))
            return
        self._stop_preview()
        try:
            if replace:
                if not confirm(self, tr("Оригинал будет перезаписан, вернуть его не получится."),
                               tr("Заменить")):
                    return
                tmp = self.path.with_name(self.path.stem + ".tmp")
                self._write(tmp, out)
                os.replace(tmp, self.path)
                self.result_path = self.path
            else:
                new = self.path.with_name(f"{self.path.stem}_trim.wav")
                k = 2
                while new.exists():
                    new = self.path.with_name(f"{self.path.stem}_trim{k}.wav")
                    k += 1
                self._write(new, out)
                self.result_path = new
        except OSError as e:
            QMessageBox.warning(self, tr("Обрезка"), tr("Не удалось сохранить: {}", e.strerror))
            return
        self.accept()

    def done(self, r: int) -> None:
        if self.ok:
            self._stop_preview()
        super().done(r)


# ════════════════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self, cfg: dict, theme: str):
        super().__init__()
        self.cfg, self.theme = cfg, theme
        self.setWindowTitle("Equestria Recorder")
        self.resize(480, 820)
        self.setMinimumSize(440, 720)

        self.src = None
        self.io = None
        self.fmt = None
        self.wav = None
        self.path: Path | None = None
        self.state = "idle"  # idle / rec / pause
        self.frames = 0
        self.gain = int(cfg.get("gain", 100)) / 100
        self.folder = Path(cfg.get("folder") or (Path.home() / "Music" if (Path.home() / "Music").is_dir() else Path.home()))

        self.audio_out = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_out)
        self._pending_start: int | None = None
        self.player.playbackStateChanged.connect(self._play_state)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(
            lambda err, msg: self.status.setText(tr("Ошибка воспроизведения: {}", msg)))

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("Equestria Recorder")
        title.setObjectName("h2")
        theme_btn = QPushButton(tr("Тема"))
        theme_btn.setObjectName("small")
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        top.addWidget(title)
        top.addStretch()
        top.addWidget(theme_btn)
        root.addLayout(top)

        # микрофон
        self.dev = QComboBox()
        self.dev.setMinimumHeight(34)
        self.dev.currentIndexChanged.connect(self._device_changed)
        refresh = QPushButton("⟳")
        refresh.setObjectName("small")
        refresh.setToolTip(tr("Обновить список микрофонов"))
        refresh.setFixedSize(40, 34)
        refresh.clicked.connect(self._fill_devices)
        drow = QHBoxLayout()
        drow.addWidget(self.dev, 1)
        drow.addWidget(refresh)
        root.addWidget(card(tr("Микрофон"), drow))

        # уровень
        self.meter = LevelMeter()
        self.db_label = QLabel(tr("−∞ дБ"))
        self.db_label.setObjectName("db")
        self.db_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        mrow = QHBoxLayout()
        mrow.addWidget(self.meter, 1)
        mrow.addWidget(self.db_label)
        self.warn = QLabel("")
        self.warn.setObjectName("warn")
        root.addWidget(card(tr("Уровень сигнала"), mrow, header=self.warn))

        # усиление
        self.gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.gain_slider.setRange(0, 300)
        self.gain_slider.setValue(int(self.gain * 100))
        self.gain_label = QLabel(f"{int(self.gain * 100)}%")
        self.gain_label.setMinimumWidth(48)
        self.gain_slider.valueChanged.connect(self._gain_changed)
        grow = QHBoxLayout()
        grow.addWidget(self.gain_slider, 1)
        grow.addWidget(self.gain_label)
        root.addWidget(card(tr("Громкость микрофона (усиление)"), grow))

        # папка
        self.folder_edit = QLineEdit(str(self.folder))
        self.folder_edit.setReadOnly(True)
        pick = QPushButton(tr("Выбрать…"))
        pick.clicked.connect(self._pick_folder)
        frow = QHBoxLayout()
        frow.addWidget(self.folder_edit, 1)
        frow.addWidget(pick)
        root.addWidget(card(tr("Куда сохранять"), frow))

        # запись
        self.time_label = QLabel("00:00")
        self.time_label.setObjectName("time")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status = QLabel(tr("Готово к записи"))
        self.status.setObjectName("hint")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rec_btn = QPushButton(tr("●  Запись"))
        self.rec_btn.setObjectName("rec")
        self.rec_btn.clicked.connect(self.toggle)
        self.stop_btn = QPushButton(tr("■  Стоп"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        brow = QHBoxLayout()
        brow.addWidget(self.rec_btn, 2)
        brow.addWidget(self.stop_btn, 1)
        root.addWidget(self.time_label)
        root.addWidget(self.status)
        root.addLayout(brow)

        # записи
        self.list = QListWidget()
        self.list.setMinimumHeight(120)
        self.play_btn = QPushButton(tr("▶  Слушать"))
        self.play_btn.clicked.connect(self.play_selected)
        trim_btn = QPushButton(tr("✂  Обрезать"))
        trim_btn.clicked.connect(self.trim_selected)
        open_btn = QPushButton(tr("Папка"))
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder))))
        lrow = QHBoxLayout()
        lrow.addWidget(self.play_btn, 1)
        lrow.addWidget(trim_btn, 1)
        lrow.addWidget(open_btn)
        lab = QLabel(tr("ЗАПИСИ"))
        lab.setObjectName("h2")
        root.addWidget(lab)
        root.addWidget(self.list, 1)
        root.addLayout(lrow)

        self.devices = QMediaDevices(self)
        self.devices.audioOutputsChanged.connect(self._refresh_output)
        self.devices.audioInputsChanged.connect(self._fill_devices)
        self._fill_devices()
        self._scan_folder()

    # --- темы
    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        for w in self.findChildren(QWidget):
            w.update()
        self._save()

    def _save(self) -> None:
        self.cfg.update(theme=self.theme, folder=str(self.folder), gain=int(self.gain * 100),
                        device=self.dev.currentData().description() if self.dev.currentData() else "")
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # --- микрофон
    def _fill_devices(self) -> None:
        if self.state != "idle":
            return
        self.dev.blockSignals(True)
        self.dev.clear()
        devs = QMediaDevices.audioInputs()
        default = QMediaDevices.defaultAudioInput()
        want = self.cfg.get("device", "")
        sel = 0
        for i, d in enumerate(devs):
            self.dev.addItem(d.description(), d)
            if (want and d.description() == want) or (not want and d.id() == default.id()):
                sel = i
        self.dev.setCurrentIndex(sel if devs else -1)
        self.dev.blockSignals(False)
        if not devs:
            self.status.setText(tr("Микрофон не найден"))
        self._device_changed()

    def _device_changed(self) -> None:
        self._stop_source()
        d = self.dev.currentData()
        if not d:
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(44100)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not d.isFormatSupported(fmt):
            fmt = d.preferredFormat()
        if fmt.sampleFormat() not in (QAudioFormat.SampleFormat.Int16, QAudioFormat.SampleFormat.Float):
            self.status.setText(tr("Этот микрофон выдаёт неподдерживаемый формат"))
            return
        self.fmt = fmt
        self.src = QAudioSource(d, fmt, self)
        self.io = self.src.start()
        if self.io is None:
            self.status.setText(tr("Не удалось открыть микрофон (проверьте доступ)"))
            return
        self.io.readyRead.connect(self._on_ready)
        if self.state == "idle":
            self.status.setText(tr("Готово к записи"))
        self._save()

    def _stop_source(self) -> None:
        if self.src:
            self.src.stop()
            self.src.deleteLater()
        self.src = self.io = None

    def _gain_changed(self, v: int) -> None:
        self.gain = v / 100
        self.gain_label.setText(f"{v}%")
        self._save()

    # --- данные с микрофона
    def _on_ready(self) -> None:
        data = bytes(self.io.readAll())
        if not data:
            return
        if self.fmt.sampleFormat() == QAudioFormat.SampleFormat.Float:
            f = array("f")
            f.frombytes(data[:len(data) // 4 * 4])
            g = self.gain
            arr = array("h", (int(max(-1.0, min(1.0, x * g)) * 32767) for x in f))
        else:
            arr = array("h")
            arr.frombytes(data[:len(data) // 2 * 2])
            if self.gain != 1:
                g = self.gain
                arr = array("h", (max(-32768, min(32767, int(x * g))) for x in arr))
        if not arr:
            return
        peak = max(max(arr), -min(arr))
        self.meter.set_level(to_level(peak))
        self.db_label.setText(tr("{:.0f} дБ", 20 * math.log10(peak / 32768)) if peak else tr("−∞ дБ"))
        self.warn.setText(tr("ПЕРЕГРУЗКА") if peak >= 32700 else "")
        if self.state == "rec" and self.wav:
            self.wav.writeframes(arr.tobytes())
            self.frames += len(arr) // self.fmt.channelCount()
            self.time_label.setText(fmt_time(self.frames / self.fmt.sampleRate()))

    # --- запись
    def toggle(self) -> None:
        if self.state == "idle":
            if not self.fmt or not self.io:
                return
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
                self.path = self.folder / f"recording_{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.wav"
                self.wav = wave.open(str(self.path), "wb")
            except OSError as e:
                self.status.setText(tr("Не могу создать файл: {}", e.strerror))
                return
            self.wav.setnchannels(self.fmt.channelCount())
            self.wav.setsampwidth(2)
            self.wav.setframerate(self.fmt.sampleRate())
            self.frames, self.state = 0, "rec"
        elif self.state == "rec":
            self.state = "pause"
        else:
            self.state = "rec"
        self._apply_state()

    def _apply_state(self) -> None:
        busy = self.state != "idle"
        self.rec_btn.setText({"idle": tr("●  Запись"), "rec": tr("❚❚  Пауза"), "pause": tr("●  Продолжить")}[self.state])
        self.stop_btn.setEnabled(busy)
        self.dev.setEnabled(not busy)
        self.status.setText({"idle": tr("Готово к записи"), "rec": tr("Идёт запись…"),
                             "pause": tr("Пауза")}[self.state])

    def stop(self) -> None:
        if self.state == "idle":
            return
        if self.wav:
            self.wav.close()
            self.wav = None
        self.state = "idle"
        self._apply_state()
        if self.path:
            self._add_item(self.path, top=True)
            self.status.setText(tr("Сохранено: {}", self.path.name))
        self.time_label.setText("00:00")

    # --- папка и список
    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Папка для записей"), str(self.folder))
        if d:
            self.folder = Path(d)
            self.folder_edit.setText(d)
            self._save()
            self._scan_folder()

    def _add_item(self, path: Path, top: bool = False) -> None:
        it = QListWidgetItem(f"{path.name}    {wav_len(path)}")
        it.setData(Qt.ItemDataRole.UserRole, str(path))
        self.list.insertItem(0, it) if top else self.list.addItem(it)
        if top:
            self.list.setCurrentItem(it)

    def _scan_folder(self) -> None:
        self.list.clear()
        try:
            files = sorted(self.folder.glob("recording_*.wav"), reverse=True)[:20]
        except OSError:
            files = []
        for f in files:
            self._add_item(f)

    # --- воспроизведение
    def _refresh_output(self) -> None:
        """Всегда играть на текущем устройстве вывода (наушники могли отключить)."""
        self.audio_out.setDevice(QMediaDevices.defaultAudioOutput())

    def play_path(self, path: Path, start_ms: int = 0) -> None:
        self._refresh_output()
        self.player.stop()
        self.player.setSource(QUrl())  # сброс, чтобы тот же файл загрузился заново
        self._pending_start = start_ms if start_ms > 0 else None
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        if self._pending_start is None:
            self.player.play()

    def _media_status(self, st) -> None:
        loaded = st in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)
        if self._pending_start is not None and loaded:
            ms, self._pending_start = self._pending_start, None
            self.player.setPosition(ms)
            self.player.play()

    def play_selected(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
            return
        it = self.list.currentItem()
        if it:
            self.play_path(Path(it.data(Qt.ItemDataRole.UserRole)))
        else:
            self.status.setText(tr("Выберите запись в списке"))

    def _play_state(self, st) -> None:
        playing = st == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setText(tr("■  Стоп") if playing else tr("▶  Слушать"))

    # --- обрезка
    def trim_selected(self) -> None:
        it = self.list.currentItem()
        if not it:
            self.status.setText(tr("Выберите запись в списке"))
            return
        self.player.stop()
        dlg = TrimDialog(self, Path(it.data(Qt.ItemDataRole.UserRole)))
        if not dlg.ok:
            return
        if dlg.exec() and dlg.result_path:
            self._scan_folder()
            for i in range(self.list.count()):
                item = self.list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == str(dlg.result_path):
                    self.list.setCurrentItem(item)
            self.status.setText(tr("Сохранено: {}", dlg.result_path.name))

    def closeEvent(self, e) -> None:
        self.stop()
        self.player.stop()
        self._stop_source()
        self._save()
        e.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Recorder")
    app.setStyle("Fusion")
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}
    theme = apply_theme(kit_themes.current_name())
    win = MainWindow(cfg, theme)
    kit_themes.follow(win._set_theme, lambda: win.theme)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())