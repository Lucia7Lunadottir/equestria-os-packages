#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Equestria Converter — конвертер аудио и видео на PyQt6. Нужен ffmpeg.

Режимы:
  • Аудио — любой аудио- или видеофайл -> MP3, OGG, Opus, AAC, FLAC, WAV
    (из видео просто достаётся звук).
  • Видео из аудио — звук + картинка -> MP4 для YouTube и других сайтов;
    можно включить «гистограмму» (столбики или волну), которая играет под звук.

Темы: словарь _T ниже (12 цветов в порядке KEYS) — просто добавьте строку.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, QProcess, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QPalette, QPixmap
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QComboBox,
                             QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLayout,
                             QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMenu, QProgressBar, QPushButton,
                             QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

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

tr = kit_i18n.install("equestria-audio-converter", __file__)

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-converter" / "settings.json"

# ---BEGIN-PURE---  (дальше идёт код без Qt: сборка команд ffmpeg)
@dataclass(frozen=True)
class AudioFormat:
    """Формат звука на выходе. bitrates пуст — формат без потерь (битрейт не выбирается)."""
    name: str
    ext: str
    codec: tuple                 # параметры ffmpeg: кодек (и, если надо, контейнер)
    bitrates: tuple = ()
    default_br: str = ""
    rates: tuple = ()            # допустимые частоты, Гц; () — любая
    mono_only: bool = False


LOSSY_BR = ("320k", "256k", "192k", "160k", "128k", "96k", "64k")
AUDIO_FORMATS = {  # id -> формат; порядок = порядок в списке. id хранится в настройках.
    "mp3": AudioFormat("MP3", "mp3", ("-c:a", "libmp3lame"), ("V0", "V2", "V4") + LOSSY_BR + ("48k", "32k"), "192k",
                       (48000, 44100, 32000, 24000, 22050, 16000)),
    "aac": AudioFormat("AAC (M4A)", "m4a", ("-c:a", "aac"), LOSSY_BR, "192k"),
    "opus": AudioFormat("Opus", "opus", ("-c:a", "libopus"),
                        ("256k", "192k", "160k", "128k", "96k", "64k", "48k", "32k", "24k"), "128k",
                        (48000, 24000, 16000, 12000, 8000)),
    "ogg": AudioFormat("OGG Vorbis", "ogg", ("-c:a", "libvorbis"), LOSSY_BR, "192k"),
    "m4r": AudioFormat(tr("Рингтон iPhone (M4R)"), "m4r", ("-c:a", "aac", "-f", "ipod"), LOSSY_BR, "256k"),
    "wma": AudioFormat("WMA", "wma", ("-c:a", "wmav2"), LOSSY_BR, "192k",
                       (48000, 44100, 32000, 22050, 16000, 11025, 8000)),
    "ac3": AudioFormat("AC3 (Dolby Digital)", "ac3", ("-c:a", "ac3"),
                       ("640k", "448k", "384k", "256k", "192k", "128k"), "448k", (48000, 44100, 32000)),
    "eac3": AudioFormat("E-AC3 (Dolby Digital Plus)", "eac3", ("-c:a", "eac3"),
                        ("640k", "448k", "384k", "256k", "192k", "128k"), "384k", (48000, 44100, 32000)),
    "mp2": AudioFormat("MP2", "mp2", ("-c:a", "mp2"), ("384k", "320k", "256k", "192k", "128k"), "256k",
                       (48000, 44100, 32000)),
    "amr": AudioFormat(tr("AMR (голос, старые телефоны)"), "amr", ("-c:a", "libopencore_amrnb"),
                       ("12.2k", "10.2k", "7.95k", "7.4k", "6.7k", "5.9k", "5.15k", "4.75k"), "12.2k",
                       (8000,), mono_only=True),
    "flac": AudioFormat(tr("FLAC (без потерь)"), "flac", ("-c:a", "flac")),
    "alac": AudioFormat(tr("ALAC — Apple, без потерь (M4A)"), "m4a", ("-c:a", "alac")),
    "wavpack": AudioFormat(tr("WavPack (без потерь)"), "wv", ("-c:a", "wavpack")),
    "wav": AudioFormat(tr("WAV 16 бит (без потерь)"), "wav", ("-c:a", "pcm_s16le")),
    "wav24": AudioFormat(tr("WAV 24 бит (без потерь)"), "wav", ("-c:a", "pcm_s24le")),
    "wav32f": AudioFormat(tr("WAV 32 бит float (без потерь)"), "wav", ("-c:a", "pcm_f32le")),
    "aiff": AudioFormat(tr("AIFF (без потерь)"), "aiff", ("-c:a", "pcm_s16be")),
}
DEFAULT_FORMAT = "mp3"
SAMPLE_RATES = (8000, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 88200, 96000)
CHANNELS = {0: tr("Каналы как в исходнике"), 1: tr("Моно"), 2: tr("Стерео")}
# Выравнивание громкости по EBU R128: −14 LUFS — как на стримингах и YouTube
LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"

# Переменный битрейт MP3 (LAME -q:a): размер подстраивается под сложность звука
VBR_NAMES = {"V0": tr("Переменный, наилучший (V0)"), "V2": tr("Переменный, высокий (V2)"),
             "V4": tr("Переменный, средний (V4)")}
FADES = (0, 1, 2, 3, 5, 10)
SPEEDS = (0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0)
GAINS = (-12, -9, -6, -3, 0, 3, 6, 9, 12)
TAG_KEYS = ("artist", "album", "date", "genre")


def parse_time(text: str) -> float | None:
    """«90», «1:30», «1:02:03.5» → секунды; пусто → 0; ошибка → None."""
    t = text.strip().replace(",", ".")
    if not t:
        return 0.0
    try:
        parts = [float(x) for x in t.split(":")]
    except ValueError:
        return None
    if len(parts) > 3 or any(x < 0 for x in parts) or any(x >= 60 for x in parts[1:]):
        return None
    sec = 0.0
    for x in parts:
        sec = sec * 60 + x
    return sec


def output_length(fx: dict, dur: float | None) -> float | None:
    """Длина результата после обрезки и смены скорости (None — неизвестна)."""
    start, end = fx.get("start", 0.0), fx.get("end", 0.0)
    if end:
        length = end - start if not dur else min(end, dur) - start
    elif dur:
        length = dur - start
    else:
        return None
    return max(0.0, length) / (fx.get("speed") or 1.0)


def audio_filters(fx: dict, dur: float | None, normalize: bool) -> list[str]:
    """Цепочка фильтров ffmpeg: обрезка → задом наперёд → скорость → усиление →
    выравнивание громкости → нарастание и затухание."""
    chain = []
    start, end = fx.get("start", 0.0), fx.get("end", 0.0)
    if start or end:
        chain.append("atrim=" + ":".join(([f"start={start:g}"] if start else []) + ([f"end={end:g}"] if end else [])))
        chain.append("asetpts=PTS-STARTPTS")
    if fx.get("reverse"):
        chain.append("areverse")
    speed = fx.get("speed") or 1.0
    if speed != 1.0:
        chain.append(f"atempo={speed:g}")  # 0.5…2.0 — один фильтр без искажения высоты тона
    if fx.get("gain"):
        chain.append(f"volume={fx['gain']:g}dB")
    if normalize:
        chain.append(LOUDNORM)
    if fx.get("fade_in"):
        chain.append(f"afade=t=in:st=0:d={fx['fade_in']:g}")
    length = output_length(fx, dur)
    if fx.get("fade_out") and length:
        d = min(fx["fade_out"], length)
        chain.append(f"afade=t=out:st={max(0.0, length - d):.3f}:d={d:g}")
    return chain


VIDEO_FORMATS = {  # id -> (название, расширение)
    "mp4": ("MP4 (H.264 + AAC)", "mp4"),
    "webm": ("WebM (VP9 + Opus)", "webm"),
    "mkv": ("MKV (H.264 + AAC)", "mkv"),
}
DEFAULT_VIDEO_FORMAT = "mp4"
RESOLUTIONS = {
    "1920×1080 — YouTube": (1920, 1080),
    "3840×2160 — 4K": (3840, 2160),
    "2560×1440": (2560, 1440),
    "1280×720": (1280, 720),
    "854×480": (854, 480),
    tr("1080×1080 — квадрат"): (1080, 1080),
    tr("1080×1920 — вертикальное"): (1080, 1920),
}
VIZ_STYLES = [tr("Нет"), tr("Столбики"), tr("Волна")]
VIZ_SIZES = {tr("Низкая"): 0.18, tr("Средняя"): 0.28, tr("Высокая"): 0.42}
VIZ_POS = [tr("Внизу"), tr("По центру"), tr("Вверху")]


def format_id(value) -> str:
    """id формата из настроек; старые версии хранили название («MP3», «FLAC (без потерь)»)."""
    if value in AUDIO_FORMATS:
        return value
    for fid, f in AUDIO_FORMATS.items():
        if value == f.name:
            return fid
    return {"FLAC (без потерь)": "flac", "WAV (без потерь)": "wav", "AAC (M4A)": "aac"}.get(value, DEFAULT_FORMAT)


def target_rate(f: AudioFormat, rate: int, src_rate: int | None) -> int:
    """Частота на выходе: выбранная (0 — как в исходнике), но из допустимых для формата."""
    want = rate or src_rate or 0
    if not f.rates:
        return want
    if want in f.rates:
        return want
    if not want:  # ffmpeg сам возьмёт подходящую — кроме кодеков с единственной частотой (AMR)
        return f.rates[0] if len(f.rates) == 1 else 0
    return min(f.rates, key=lambda r: (abs(r - want), -r))


def unique_path(folder: Path, stem: str, ext: str, avoid: Path | None = None) -> Path:
    """Имя файла, которое не затрёт существующий (и не совпадёт с исходником)."""
    p = folder / f"{stem}.{ext}"
    k = 1
    while p.exists() or (avoid is not None and p == avoid):
        p = folder / f"{stem}_{k}.{ext}"
        k += 1
    return p


def audio_cmd(ffmpeg: str, src: str, dst: str, fmt: str, bitrate: str, rate: int = 0,
              channels: int = 0, normalize: bool = False, src_rate: int | None = None,
              fx: dict | None = None, dur: float | None = None, tags: dict | None = None) -> list[str]:
    """Команда ffmpeg для звука. rate/channels 0 — как в исходнике; fx — обработка
    (start, end, fade_in, fade_out, speed, gain, reverse); tags — теги, пустые не трогаются.
    src_rate (частота исходника) нужен при выравнивании громкости — loudnorm сам поднимает
    частоту до 192 кГц — и для форматов с ограниченным набором частот."""
    f = AUDIO_FORMATS[fmt]
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", src,
           "-vn", "-map", "0:a:0", "-map_metadata", "0", *f.codec]
    if f.bitrates:
        br = bitrate if bitrate in f.bitrates else f.default_br
        cmd += ["-q:a", br[1:]] if br in VBR_NAMES else ["-b:a", br]
    chain = audio_filters(fx or {}, dur, normalize)
    if chain:
        cmd += ["-af", ",".join(chain)]
    for key, value in (tags or {}).items():
        if value.strip():
            cmd += ["-metadata", f"{key}={value.strip()}"]
    out_rate = target_rate(f, rate, src_rate if normalize or f.rates else None)
    if out_rate:
        cmd += ["-ar", str(out_rate)]
    ch = 1 if f.mono_only else channels
    if ch:
        cmd += ["-ac", str(ch)]
    return cmd + ["-progress", "pipe:1", "-nostats", dst]


def video_cmd(ffmpeg: str, audio: str, image: str, dst: str, size: tuple[int, int],
              viz: str, viz_size: str, viz_pos: str, viz_color: str, bg: str,
              duration: float | None = None, preview_at: float | None = None,
              vfmt: str = DEFAULT_VIDEO_FORMAT, normalize: bool = False) -> list[str]:
    """Видео из звука и картинки. preview_at задан — получаем один кадр-PNG."""
    W, H = size
    fps = 30 if viz != tr("Нет") else 10
    bgc = "0x" + bg.lstrip("#")
    vc = "0x" + viz_color.lstrip("#")
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    if image:
        cmd += ["-loop", "1", "-framerate", str(fps), "-i", image]
    else:  # без картинки — просто цветной фон
        cmd += ["-f", "lavfi", "-i", f"color=c={bgc}:s={W}x{H}:r={fps}"]
    if preview_at is not None:
        cmd += ["-ss", f"{preview_at:.2f}"]
    cmd += ["-i", audio]
    chain = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
             f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={bgc},setsar=1,format=yuv420p")
    if viz == tr("Нет"):
        fc = chain + "[v]"
    else:
        vw = int(W * 0.8) // 2 * 2
        vh = int(H * VIZ_SIZES[viz_size]) // 2 * 2
        margin = int(H * 0.05)
        y = {tr("Внизу"): f"H-h-{margin}", tr("По центру"): "(H-h)/2", tr("Вверху"): str(margin)}[viz_pos]
        if viz == tr("Столбики"):
            gen = (f"showfreqs=s={vw}x{vh}:mode=bar:fscale=log:ascale=sqrt:"
                   f"win_size=4096:rate={fps}:colors={vc}")
        else:
            gen = f"showwaves=s={vw}x{vh}:mode=cline:draw=full:scale=sqrt:rate={fps}:colors={vc}"
        fc = (f"{chain}[bg];[1:a]{gen},format=rgba,colorkey=0x000000:0.15:0.1[viz];"
              f"[bg][viz]overlay=x=(W-w)/2:y={y}:format=auto,format=yuv420p[v]")
    cmd += ["-filter_complex", fc, "-map", "[v]"]
    if preview_at is not None:  # короткий кусок; в файле остаётся последний кадр
        return cmd + ["-t", "0.6", "-update", "1", dst]
    cmd += ["-map", "1:a:0"]
    if vfmt == "webm":
        cmd += ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "33", "-deadline", "good",
                "-cpu-used", "4", "-row-mt", "1", "-r", str(fps)]
    else:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(fps)]
        if viz == tr("Нет"):
            cmd += ["-tune", "stillimage"]
    if normalize:
        cmd += ["-af", LOUDNORM, "-ar", "48000"]
    if vfmt == "webm":
        cmd += ["-c:a", "libopus", "-b:a", "160k"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    if vfmt == "mp4":
        cmd += ["-movflags", "+faststart"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    return cmd + ["-shortest", "-progress", "pipe:1", "-nostats", dst]


def parse_progress(line: str) -> float | None:
    """Строка из `-progress` -> сколько секунд уже обработано."""
    line = line.strip()
    for key in ("out_time_us=", "out_time_ms="):  # обе — в микросекундах
        if line.startswith(key):
            try:
                return max(0.0, int(line[len(key):]) / 1e6)
            except ValueError:
                return None
    return None


def probe_duration(path: str) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", path], capture_output=True, text=True, timeout=15)
        v = float(r.stdout.strip().splitlines()[0])
        return v if v > 0 else None
    except Exception:
        return None
def probe_sample_rate(path: str) -> int | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        r = subprocess.run([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                            "stream=sample_rate", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=15)
        v = int(r.stdout.strip().splitlines()[0])
        return v if v > 0 else None
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════════
#  БЫСТРЫЙ ЭКСПОРТ — готовые наборы настроек
#  Ключи: mode (0 — аудио, 1 — видео), fmt, br, rate, ch, norm, vfmt, res, viz, viz_size, viz_pos
# ════════════════════════════════════════════════════════════════════════════
BUILTIN_PRESETS = [
    (tr("Музыка — MP3 320 кбит/с"), dict(mode=0, fmt="mp3", br="320k", rate=0, ch=0, norm=False)),
    (tr("Подкаст и голос — MP3 96 кбит/с, моно, ровная громкость"),
     dict(mode=0, fmt="mp3", br="96k", rate=44100, ch=1, norm=True)),
    (tr("Для телефона — AAC 192 кбит/с"), dict(mode=0, fmt="aac", br="192k", rate=0, ch=0, norm=False)),
    (tr("Рингтон iPhone — M4R"), dict(mode=0, fmt="m4r", br="256k", rate=44100, ch=0, norm=True)),
    (tr("Для сайта — Opus 128 кбит/с"), dict(mode=0, fmt="opus", br="128k", rate=0, ch=0, norm=False)),
    (tr("Архив без потерь — FLAC"), dict(mode=0, fmt="flac", br="", rate=0, ch=0, norm=False)),
    (tr("Для монтажа — WAV 24 бит, 48 кГц"), dict(mode=0, fmt="wav24", br="", rate=48000, ch=0, norm=False)),
    (tr("YouTube — видео 1080p со столбиками"),
     dict(mode=1, vfmt="mp4", res="1920×1080 — YouTube", viz=tr("Столбики"), norm=True)),
    (tr("Shorts, Reels, TikTok — вертикальное видео"),
     dict(mode=1, vfmt="mp4", res=tr("1080×1920 — вертикальное"), viz=tr("Волна"), viz_pos=tr("По центру"), norm=True)),
]
# ---END-PURE---

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
QMainWindow { background: @base@; }
QWidget { color: @text@; font-size: 15px; }
QLabel { background: transparent; }
QLabel#h2 { color: @accent@; font-size: 13px; font-weight: 700; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#warn { color: @red@; font-size: 13px; font-weight: 700; }
QLabel#preview { background: @mantle@; color: @subtext@; border-radius: 10px; }
QFrame#card { background: @mantle@; border-radius: 14px; }
QPushButton { background: @surface0@; border: none; border-radius: 12px;
    padding: 10px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @base@; font-size: 17px; padding: 14px; }
QPushButton#primary:hover { background: @accent@; }
QPushButton#primary:disabled { background: @surface1@; color: @surface2@; }
QPushButton#small { padding: 6px 14px; font-size: 13px; border-radius: 10px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QPushButton#mode { padding: 10px 16px; border-radius: 12px; }
QPushButton#mode:checked { background: @accent@; color: @base@; }
QLineEdit { background: @surface0@; border: 2px solid transparent; border-radius: 10px;
    padding: 8px 12px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QLineEdit[error="true"] { border-color: @red@; }
QComboBox { padding: 6px 10px; }
QComboBox QAbstractItemView { background: @surface0@; color: @text@; outline: 0;
    selection-background-color: @surface1@; selection-color: @text@; }
QListWidget { background: @surface0@; border: none; border-radius: 10px; outline: 0; padding: 4px; }
QListWidget::item { background: transparent; border-radius: 6px; padding: 6px 8px; }
QListWidget::item:selected { background: @surface1@; color: @accent@; }
QProgressBar { background: @surface0@; border: none; border-radius: 6px; min-height: 12px; max-height: 12px; }
QProgressBar::chunk { background: @accent@; border-radius: 6px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
"""


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME)


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)


# ════════════════════════════════════════════════════════════════════════════
#  МЕЛОЧИ
# ════════════════════════════════════════════════════════════════════════════
MEDIA_EXT = ("mp3 wav flac ogg opus m4a aac wma aiff mp4 mkv avi mov webm flv wmv m4v ts")
IMAGE_FILTER = tr("Картинки (*.png *.jpg *.jpeg *.webp *.bmp)")
VIZ_COLORS = [(tr("Цвет темы (акцент)"), "accent"), (tr("Светлый"), "text"), (tr("Зелёный"), "green"),
              (tr("Красный"), "red"), (tr("Жёлтый"), "yellow")]


def combo(items, current: str | None = None) -> QComboBox:
    c = QComboBox()
    c.setMinimumHeight(34)
    # длинные пункты («Подкаст и голос — …») не должны раздвигать окно вбок
    c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    c.setMinimumContentsLength(6)
    c.addItems(list(items))
    if current and c.findText(current) >= 0:
        c.setCurrentText(current)
    return c


class DropList(QListWidget):
    """Список файлов, в который можно перетащить файлы мышью."""
    dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, e) -> None:
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()

    def dragMoveEvent(self, e) -> None:
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()

    def dropEvent(self, e) -> None:
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(paths)
            e.acceptProposedAction()


# ════════════════════════════════════════════════════════════════════════════
#  ОЧЕРЕДЬ FFMPEG
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class Job:
    """Один файл очереди. build(длительность) -> команда ffmpeg."""
    src: str
    dst: Path
    name: str
    build: Callable[[float | None], list]
    item: QListWidgetItem | None = None
    length: Callable[[float | None], float | None] | None = None  # длина результата по длине исходника
    dur: float | None = None
    out_dur: float | None = None
    ok: bool | None = None          # None — до этого файла очередь не дошла


class ConvertQueue(QObject):
    """Запускает ffmpeg для файлов по одному, читает прогресс (`-progress pipe:1`),
    умеет отменять. Об окне ничего не знает — сообщает всё сигналами."""
    job_started = pyqtSignal(int, int, object)   # номер файла, всего, Job
    job_progress = pyqtSignal(object, int)       # Job, проценты
    job_done = pyqtSignal(object, list)          # Job (job.ok — итог), последние строки ffmpeg
    finished = pyqtSignal()

    TAIL = 20  # сколько строк вывода ffmpeg хранить для сообщения об ошибке

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs: list[Job] = []
        self.cur = -1
        self.proc: QProcess | None = None
        self.buf = ""
        self.tail: list[str] = []
        self.cancelled = False

    def start(self, jobs: list[Job]) -> None:
        self.jobs = jobs
        self.cancelled = False
        self.cur = 0
        self._start_job()

    def cancel(self) -> None:
        self.cancelled = True
        if self.proc:
            self.proc.kill()

    def counts(self) -> tuple[int, int]:
        """(сколько готово, сколько с ошибкой)."""
        return (sum(1 for j in self.jobs if j.ok),
                sum(1 for j in self.jobs if j.ok is False))

    def _start_job(self) -> None:
        if self.cancelled or self.cur >= len(self.jobs):
            self.finished.emit()
            return
        j = self.jobs[self.cur]
        j.dur = probe_duration(j.src)
        j.out_dur = j.length(j.dur) if j.length else j.dur
        cmd = j.build(j.dur)
        self.buf, self.tail = "", []
        self.job_started.emit(self.cur, len(self.jobs), j)
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(self._proc_error)
        self.proc.start(cmd[0], cmd[1:])

    def _read(self) -> None:
        j = self.jobs[self.cur]
        self.buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        lines = self.buf.split("\n")
        self.buf = lines.pop()
        for line in lines:
            t = parse_progress(line)
            if t is not None:
                if j.out_dur:
                    self.job_progress.emit(j, min(99, int(t / j.out_dur * 100)))
            elif line.strip() and "=" not in line.split(" ")[0]:
                self.tail.append(line.strip())
                self.tail = self.tail[-self.TAIL:]

    def _proc_error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self.tail = [tr("ffmpeg не запустился")]
            self._done(-1, QProcess.ExitStatus.CrashExit)

    def _done(self, code: int, status) -> None:
        if self.cur >= len(self.jobs) or self.proc is None:
            return
        j = self.jobs[self.cur]
        proc, self.proc = self.proc, None
        proc.deleteLater()
        j.ok = code == 0 and status == QProcess.ExitStatus.NormalExit and not self.cancelled
        if not j.ok:
            Path(j.dst).unlink(missing_ok=True)  # убираем недоделанный файл
        self.job_done.emit(j, list(self.tail))
        self.cur += 1
        self._start_job()


# ════════════════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self, cfg: dict, theme: str):
        super().__init__()
        self.cfg, self.theme = cfg, theme
        self.ffmpeg = shutil.which("ffmpeg")
        self.image = str(cfg.get("image", ""))
        if self.image and not Path(self.image).is_file():
            self.image = ""
        self.out_dir = str(cfg.get("folder", ""))
        self.mode = int(cfg.get("mode", 0)) if int(cfg.get("mode", 0)) in (0, 1) else 0
        self.queue = ConvertQueue(self)
        self.queue.job_started.connect(self._job_started)
        self.queue.job_progress.connect(self._job_progress)
        self.queue.job_done.connect(self._job_done)
        self.queue.finished.connect(self._finish)
        self.last_out: Path | None = None
        self.preview_path = Path(tempfile.gettempdir()) / "equestria-converter-preview.png"

        self.setWindowTitle("Equestria Converter")
        self.resize(580, 800)
        self.setMinimumSize(520, 620)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("Equestria Converter")
        title.setObjectName("h2")
        theme_btn = QPushButton(tr("Тема"))
        theme_btn.setObjectName("small")
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        top.addWidget(title)
        top.addStretch()
        top.addWidget(theme_btn)
        root.addLayout(top)

        # прокручиваемая часть
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 6, 0)
        body.setSpacing(8)
        scroll.setWidget(self.body)
        root.addWidget(scroll, 1)

        # режим
        self.mode_btns = []
        mrow = QHBoxLayout()
        for i, name in enumerate((tr("Аудио"), tr("Видео из аудио"))):
            b = QPushButton(name)
            b.setObjectName("mode")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=i: self._set_mode(k))
            self.mode_btns.append(b)
            mrow.addWidget(b, 1)
        body.addLayout(mrow)
        body.addWidget(self._presets_card())

        # файлы
        self.list = DropList()
        self.list.setMinimumHeight(150)
        self.list.dropped.connect(self.add_files)
        add = QPushButton(tr("Добавить файлы…"))
        add.clicked.connect(self._pick_files)
        rm = QPushButton(tr("Убрать"))
        rm.clicked.connect(self._remove_selected)
        clr = QPushButton(tr("Очистить"))
        clr.clicked.connect(self._clear)
        frow = QHBoxLayout()
        frow.addWidget(add, 1)
        frow.addWidget(rm)
        frow.addWidget(clr)
        self.files_hint = QLabel(tr("Перетащите файлы сюда или нажмите «Добавить файлы…»"))
        self.files_hint.setObjectName("hint")
        body.addWidget(card(tr("Файлы"), self.list, frow, self.files_hint))

        # настройки по режимам (+ общая для обоих громкость)
        self.norm = kit_widgets.small_btn(tr("Выровнять громкость (−14 LUFS)"), True,
                                          tr("Тихие и громкие записи станут одинаково громкими — "
                                             "как на стримингах и YouTube (EBU R128)"))
        self.norm.setChecked(bool(self.cfg.get("norm", False)))
        self.stack = QStackedWidget()
        self.stack.addWidget(self._audio_page())
        self.stack.addWidget(self._video_page())
        body.addWidget(self.stack)
        norm_hint = QLabel(tr("Полезно для подкастов, рингтонов и сборников из разных источников."))
        norm_hint.setObjectName("hint")
        norm_hint.setWordWrap(True)
        nrow = QHBoxLayout()
        nrow.addWidget(self.norm)
        nrow.addStretch()
        body.addWidget(card(tr("Громкость"), nrow, norm_hint))

        # куда сохранять
        self.out_edit = QLineEdit()
        self.out_edit.setReadOnly(True)
        pick = QPushButton(tr("Выбрать…"))
        pick.clicked.connect(self._pick_folder)
        reset = QPushButton("×")
        reset.setObjectName("small")
        reset.setToolTip(tr("Сохранять рядом с исходным файлом"))
        reset.clicked.connect(self._reset_folder)
        orow = QHBoxLayout()
        orow.addWidget(self.out_edit, 1)
        orow.addWidget(pick)
        orow.addWidget(reset)
        body.addWidget(card(tr("Куда сохранять"), orow))
        body.addStretch()
        self._show_folder()

        # нижняя панель
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        self.go_btn = QPushButton(tr("Конвертировать"))
        self.go_btn.setObjectName("primary")
        self.go_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton(tr("Отмена"))
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)
        self.open_btn = QPushButton(tr("Папка"))
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_result)
        brow = QHBoxLayout()
        brow.addWidget(self.go_btn, 3)
        brow.addWidget(self.cancel_btn, 1)
        brow.addWidget(self.open_btn)
        root.addWidget(self.bar)
        root.addWidget(self.status)
        root.addLayout(brow)

        self._set_mode(self.mode)
        if not self.ffmpeg:
            self.go_btn.setEnabled(False)
            self.status.setText(tr("Не найден ffmpeg. Установите его: sudo apt install ffmpeg "
                                "(или pacman -S ffmpeg, dnf install ffmpeg) и перезапустите программу."))
            self.status.setObjectName("warn")
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)

    # --- страницы настроек
    def _audio_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self.fmt = combo(())
        for fid, f in AUDIO_FORMATS.items():
            self.fmt.addItem(f.name, fid)
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(format_id(self.cfg.get("fmt")))))
        self.br = combo(())
        self.br.activated.connect(lambda _i: setattr(self, "_last_br", self.br.currentData() or self._last_br))
        self._last_br = str(self.cfg.get("br") or "192k")
        self.rate = combo(())
        self.ch = combo(())
        for k, name in CHANNELS.items():
            self.ch.addItem(name, k)
        self.ch.setCurrentIndex(max(0, self.ch.findData(self.cfg.get("ch", 0))))
        self.fmt.currentIndexChanged.connect(lambda _i: self._fmt_changed())
        row = QHBoxLayout()
        row.addWidget(self.fmt, 2)
        row.addWidget(self.br, 1)
        row2 = QHBoxLayout()
        row2.addWidget(self.rate, 1)
        row2.addWidget(self.ch, 1)
        hint = QLabel(tr("Справа — качество (битрейт). Видеофайлы тоже можно добавлять: из них возьмётся звук."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(card(tr("Формат аудио"), row, row2, hint))
        self._fmt_changed(rate=self.cfg.get("rate", 0))
        v.addWidget(self._fx_card())
        v.addWidget(self._tags_card())
        return w

    def _fx_card(self) -> QWidget:
        """Обработка: обрезка, нарастание/затухание, скорость, усиление, задом наперёд."""
        self.t_start = QLineEdit()
        self.t_start.setPlaceholderText(tr("Начало: 0:00"))
        self.t_end = QLineEdit()
        self.t_end.setPlaceholderText(tr("Конец: до конца файла"))
        for e in (self.t_start, self.t_end):
            e.setToolTip(tr("Время: секунды (90), минуты:секунды (1:30) или часы:минуты:секунды"))
            e.textEdited.connect(lambda _t: self._fx())
        self.fade_in = combo(())
        self.fade_out = combo(())
        for box, none in ((self.fade_in, tr("Без нарастания")), (self.fade_out, tr("Без затухания"))):
            for sec in FADES:
                box.addItem(none if not sec else (tr("Нарастание {} с", sec) if box is self.fade_in
                                                  else tr("Затухание {} с", sec)), sec)
        self.speed = combo(())
        for k in SPEEDS:
            self.speed.addItem(tr("Обычная скорость") if k == 1.0 else tr("Скорость {}×", f"{k:g}"), k)
        self.gain = combo(())
        for g in GAINS:
            self.gain.addItem(tr("Без усиления") if not g else tr("Громкость {} дБ", f"{g:+d}"), g)
        for box, key, default in ((self.fade_in, "fade_in", 0), (self.fade_out, "fade_out", 0),
                                  (self.speed, "speed", 1.0), (self.gain, "gain", 0)):
            box.setCurrentIndex(max(0, box.findData(self.cfg.get(key, default))))
        self.reverse = kit_widgets.small_btn(tr("Задом наперёд"), True)
        reset = kit_widgets.small_btn(tr("Сбросить"))
        reset.clicked.connect(self._reset_fx)
        r1 = QHBoxLayout()
        r1.addWidget(self.t_start, 1)
        r1.addWidget(self.t_end, 1)
        r2 = QHBoxLayout()
        r2.addWidget(self.fade_in, 1)
        r2.addWidget(self.fade_out, 1)
        r3 = QHBoxLayout()
        r3.addWidget(self.speed, 1)
        r3.addWidget(self.gain, 1)
        r4 = QHBoxLayout()
        r4.addWidget(self.reverse)
        r4.addStretch()
        r4.addWidget(reset)
        return card(tr("Обработка"), r1, r2, r3, r4)

    def _tags_card(self) -> QWidget:
        self.tags = {}
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        for key, label, row in (("artist", tr("Исполнитель"), row1), ("album", tr("Альбом"), row1),
                                ("date", tr("Год"), row2), ("genre", tr("Жанр"), row2)):
            e = QLineEdit()
            e.setPlaceholderText(label)
            self.tags[key] = e
            row.addWidget(e, 1)
        hint = QLabel(tr("Пустые поля — теги остаются как в исходном файле."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        return card(tr("Теги"), row1, row2, hint)

    def _fx(self) -> dict | None:
        """Обработка из полей; None — время введено с ошибкой (поле подсвечивается)."""
        start, end = parse_time(self.t_start.text()), parse_time(self.t_end.text())
        bad_end = end is None or (bool(end) and start is not None and end <= start)
        for e, bad in ((self.t_start, start is None), (self.t_end, bad_end)):
            e.setProperty("error", bad)
            e.style().unpolish(e)
            e.style().polish(e)
        if start is None or bad_end:
            return None
        return dict(start=start, end=end, fade_in=self.fade_in.currentData(), fade_out=self.fade_out.currentData(),
                    speed=self.speed.currentData(), gain=self.gain.currentData(), reverse=self.reverse.isChecked())

    def _reset_fx(self) -> None:
        self.t_start.clear()
        self.t_end.clear()
        for box, value in ((self.fade_in, 0), (self.fade_out, 0), (self.speed, 1.0), (self.gain, 0)):
            box.setCurrentIndex(box.findData(value))
        self.reverse.setChecked(False)
        self._fx()

    def _video_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        self.pic = QLabel(tr("Без картинки — будет цветной фон"))
        self.pic.setObjectName("preview")
        self.pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pic.setFixedHeight(170)
        pick = QPushButton(tr("Выбрать картинку…"))
        pick.clicked.connect(self._pick_image)
        drop = QPushButton(tr("Убрать"))
        drop.clicked.connect(self._clear_image)
        prev = QPushButton(tr("Предпросмотр кадра"))
        prev.clicked.connect(self._preview)
        prow = QHBoxLayout()
        prow.addWidget(pick, 1)
        prow.addWidget(drop)
        v.addWidget(card(tr("Картинка для видео"), self.pic, prow, prev))

        self.vfmt = combo(())
        for fid, (name, _ext) in VIDEO_FORMATS.items():
            self.vfmt.addItem(name, fid)
        self.vfmt.setCurrentIndex(max(0, self.vfmt.findData(self.cfg.get("vfmt", DEFAULT_VIDEO_FORMAT))))
        self.res = combo(RESOLUTIONS, self.cfg.get("res"))
        vrow = QHBoxLayout()
        vrow.addWidget(self.vfmt, 1)
        vrow.addWidget(self.res, 1)
        v.addWidget(card(tr("Формат и размер видео"), vrow))

        self.viz = combo(VIZ_STYLES, self.cfg.get("viz", tr("Столбики")))
        self.viz_size = combo(VIZ_SIZES, self.cfg.get("viz_size", tr("Средняя")))
        self.viz_pos = combo(VIZ_POS, self.cfg.get("viz_pos", tr("Внизу")))
        self.viz_color = combo(())
        for name, key in VIZ_COLORS:
            self.viz_color.addItem(name, key)
        i = self.viz_color.findData(self.cfg.get("viz_color", "accent"))
        self.viz_color.setCurrentIndex(max(0, i))
        self.viz.currentIndexChanged.connect(self._viz_changed)
        r1 = QHBoxLayout()
        r1.addWidget(self.viz, 1)
        r1.addWidget(self.viz_color, 1)
        r2 = QHBoxLayout()
        r2.addWidget(self.viz_size, 1)
        r2.addWidget(self.viz_pos, 1)
        self.viz_rows = (self.viz_size, self.viz_pos, self.viz_color)
        v.addWidget(card(tr("Гистограмма под звук"), r1, r2))
        self._viz_changed()
        if self.image:
            self._show_image()
        return w

    # --- быстрый экспорт
    def _presets_card(self) -> QWidget:
        self.preset = combo(())
        self.preset.activated.connect(lambda _i: self._apply_selected_preset())
        self.preset.currentIndexChanged.connect(lambda _i: self._preset_buttons())
        save = QPushButton(tr("Сохранить текущие…"))
        save.clicked.connect(self._save_preset)
        self.preset_del = QPushButton(tr("Удалить"))
        self.preset_del.clicked.connect(self._delete_preset)
        row = QHBoxLayout()
        row.addWidget(save)
        row.addWidget(self.preset_del)
        row.addStretch()
        hint = QLabel(tr("Набор подставляет все настройки ниже — останется нажать «Конвертировать». "
                         "Свои наборы отмечены ★."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self._fill_presets()
        return card(tr("Быстрый экспорт"), self.preset, row, hint)

    def _user_presets(self) -> list:
        raw = self.cfg.get("presets")
        if not isinstance(raw, list):
            return []
        return [p for p in raw if isinstance(p, dict) and isinstance(p.get("name"), str)
                and isinstance(p.get("settings"), dict)]

    def _all_presets(self) -> list:
        """[(название, настройки, свой ли)] — встроенные, затем свои."""
        return ([(n, st, False) for n, st in BUILTIN_PRESETS]
                + [(p["name"], p["settings"], True) for p in self._user_presets()])

    def _fill_presets(self, select: str | None = None) -> None:
        self.preset.blockSignals(True)
        self.preset.clear()
        self.preset.addItem(tr("— выберите набор —"), None)
        for i, (name, _st, user) in enumerate(self._all_presets()):
            self.preset.addItem(("★ " if user else "") + name, i)
            if user and name == select:
                self.preset.setCurrentIndex(self.preset.count() - 1)
        self.preset.blockSignals(False)
        self._preset_buttons()

    def _selected_preset(self):
        i = self.preset.currentData()
        presets = self._all_presets()
        return presets[i] if i is not None and i < len(presets) else None

    def _preset_buttons(self) -> None:
        sel = self._selected_preset()
        self.preset_del.setEnabled(bool(sel and sel[2]))

    def _apply_selected_preset(self) -> None:
        sel = self._selected_preset()
        if sel:
            self.apply_preset(sel[1])
            self.status.setText(tr("Набор «{}» применён.", sel[0]))

    def apply_preset(self, st: dict) -> None:
        """Подставить настройки набора; чего в наборе нет — остаётся как есть."""
        def pick_data(box: QComboBox, value) -> None:
            i = box.findData(value)
            if i >= 0:
                box.setCurrentIndex(i)

        def pick_text(box: QComboBox, value) -> None:
            if isinstance(value, str) and box.findText(value) >= 0:
                box.setCurrentText(value)
        if "fmt" in st:
            self.fmt.blockSignals(True)
            pick_data(self.fmt, format_id(st["fmt"]))
            self.fmt.blockSignals(False)
            self._fmt_changed(br=st.get("br") or None, rate=st.get("rate", 0))
        for key, box in (("ch", self.ch), ("fade_in", self.fade_in), ("fade_out", self.fade_out),
                         ("speed", self.speed), ("gain", self.gain)):
            if key in st:
                pick_data(box, st[key])
        if "norm" in st:
            self.norm.setChecked(bool(st["norm"]))
        if "vfmt" in st:
            pick_data(self.vfmt, st["vfmt"])
        for key, box in (("res", self.res), ("viz", self.viz), ("viz_size", self.viz_size), ("viz_pos", self.viz_pos)):
            if key in st:
                pick_text(box, st[key])
        if "viz_color" in st:
            pick_data(self.viz_color, st["viz_color"])
        if st.get("mode") in (0, 1):
            self._set_mode(st["mode"])  # он же сохраняет настройки
        else:
            self._save()

    def _save_preset(self) -> None:
        sel = self._selected_preset()
        name, ok = QInputDialog.getText(self, tr("Свой набор"), tr("Название набора:"),
                                        text=sel[0] if sel and sel[2] else "")
        name = name.strip()
        if not ok or not name:
            return
        user = [p for p in self._user_presets() if p["name"] != name]
        user.append({"name": name, "settings": self._current_settings()})
        self.cfg["presets"] = user
        self._save()
        self._fill_presets(select=name)
        self.status.setText(tr("Набор «{}» сохранён.", name))

    def _delete_preset(self) -> None:
        sel = self._selected_preset()
        if not sel or not sel[2]:
            return
        self.cfg["presets"] = [p for p in self._user_presets() if p["name"] != sel[0]]
        self._save()
        self._fill_presets()
        self.status.setText(tr("Набор «{}» удалён.", sel[0]))

    # --- темы и настройки
    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self._save()

    def _current_settings(self) -> dict:
        """Все настройки экспорта (то же, что хранит набор быстрого экспорта)."""
        return dict(mode=self.mode, fmt=self.fmt.currentData(), br=self.br.currentData() or self._last_br,
                    rate=self.rate.currentData(), ch=self.ch.currentData(), norm=self.norm.isChecked(),
                    fade_in=self.fade_in.currentData(), fade_out=self.fade_out.currentData(),
                    speed=self.speed.currentData(), gain=self.gain.currentData(),
                    vfmt=self.vfmt.currentData(), res=self.res.currentText(), viz=self.viz.currentText(),
                    viz_size=self.viz_size.currentText(), viz_pos=self.viz_pos.currentText(),
                    viz_color=self.viz_color.currentData())

    def _save(self) -> None:
        self.cfg.update(theme=self.theme, folder=self.out_dir, image=self.image, **self._current_settings())
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _set_mode(self, i: int) -> None:
        self.mode = i
        for k, b in enumerate(self.mode_btns):
            b.setChecked(k == i)
        self.stack.setCurrentIndex(i)
        self._save()

    def _fmt_changed(self, br: str | None = None, rate=None) -> None:
        """Списки битрейта и частоты — только то, что умеет выбранный формат."""
        f = AUDIO_FORMATS[self.fmt.currentData()]
        want_br = br or self._last_br
        want_rate = self.rate.currentData() if rate is None else rate
        self.br.blockSignals(True)
        self.br.clear()
        if f.bitrates:
            for b in f.bitrates:
                self.br.addItem(tr("{} кбит/с", b[:-1]), b)
            self.br.setCurrentIndex(max(0, self.br.findData(want_br if want_br in f.bitrates else f.default_br)))
            if want_br in f.bitrates:
                self._last_br = want_br
        else:
            self.br.addItem(tr("без потерь"), "")
        self.br.setEnabled(bool(f.bitrates))
        self.br.blockSignals(False)
        self.rate.clear()
        self.rate.addItem(tr("Частота как в исходнике"), 0)
        for r in f.rates or SAMPLE_RATES:
            self.rate.addItem(tr("{} кГц", f"{r / 1000:g}"), r)
        self.rate.setCurrentIndex(max(0, self.rate.findData(want_rate)))
        if f.mono_only and self.ch.isEnabled():
            self._ch_before_mono = self.ch.currentData()  # вернём, когда формат снова позволит
            self.ch.setCurrentIndex(self.ch.findData(1))
        elif not f.mono_only and not self.ch.isEnabled():
            self.ch.setCurrentIndex(max(0, self.ch.findData(getattr(self, "_ch_before_mono", 0))))
        self.ch.setEnabled(not f.mono_only)

    def _viz_changed(self) -> None:
        on = self.viz.currentText() != tr("Нет")
        for w in self.viz_rows:
            w.setEnabled(on)

    # --- файлы
    def _pick_files(self) -> None:
        exts = " ".join(f"*.{e}" for e in MEDIA_EXT.split())
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Выберите файлы"), str(Path.home()), tr("Аудио и видео ({});;Все файлы (*)", exts))
        self.add_files(paths)

    def add_files(self, paths) -> None:
        have = {self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())}
        for p in paths:
            if p in have or not Path(p).is_file():
                continue
            it = QListWidgetItem(Path(p).name)
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setToolTip(p)
            self.list.addItem(it)
            have.add(p)
        self._files_changed()

    def _remove_selected(self) -> None:
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))
        self._files_changed()

    def _clear(self) -> None:
        self.list.clear()
        self._files_changed()

    def _files_changed(self) -> None:
        n = self.list.count()
        self.files_hint.setText(tr("Файлов: {}", n) if n else
                                tr("Перетащите файлы сюда или нажмите «Добавить файлы…»"))

    # --- картинка
    def _pick_image(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, tr("Выберите картинку"), str(Path.home()), IMAGE_FILTER)
        if p:
            self.image = p
            self._show_image()
            self._save()

    def _show_image(self) -> None:
        pm = QPixmap(self.image)
        if pm.isNull():
            self.image = ""
            self._clear_image()
            return
        self.pic.setPixmap(pm.scaled(self.pic.width() or 400, self.pic.height(),
                                     Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))

    def _clear_image(self) -> None:
        self.image = ""
        self.pic.setPixmap(QPixmap())
        self.pic.setText(tr("Без картинки — будет цветной фон"))
        self._save()

    # --- папка
    def _show_folder(self) -> None:
        self.out_edit.setText(self.out_dir or tr("Рядом с исходным файлом"))

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Папка для результата"), self.out_dir or str(Path.home()))
        if d:
            self.out_dir = d
            self._show_folder()
            self._save()

    def _reset_folder(self) -> None:
        self.out_dir = ""
        self._show_folder()
        self._save()

    def _open_result(self) -> None:
        if self.last_out:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_out.parent)))

    # --- параметры видео
    def _video_args(self) -> dict:
        key = self.viz_color.currentData()
        return dict(image=self.image, size=RESOLUTIONS[self.res.currentText()],
                    vfmt=self.vfmt.currentData(), normalize=self.norm.isChecked(),
                    viz=self.viz.currentText(), viz_size=self.viz_size.currentText(),
                    viz_pos=self.viz_pos.currentText(), viz_color=THEME[key], bg=THEME["base"])

    def _preview(self) -> None:
        if not self.ffmpeg:
            return
        if not self.list.count():
            self.status.setText(tr("Добавьте аудиофайл — кадр строится по нему."))
            return
        src = self.list.item(0).data(Qt.ItemDataRole.UserRole)
        dur = probe_duration(src)
        at = min(5.0, dur / 2) if dur else 0.0
        self.preview_path.unlink(missing_ok=True)
        cmd = video_cmd(self.ffmpeg, src, dst=str(self.preview_path), preview_at=at,
                        **self._video_args())
        self.status.setText(tr("Строю кадр…"))
        QApplication.processEvents()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except Exception as e:
            self.status.setText(tr("Не удалось построить кадр: {}", e))
            return
        pm = QPixmap(str(self.preview_path))
        if r.returncode != 0 or pm.isNull():
            lines = [x for x in r.stderr.strip().splitlines() if x.strip()]
            self.status.setText(tr("Не удалось построить кадр: ") + (lines[-1] if lines else tr("ошибка ffmpeg")))
            return
        self.pic.setPixmap(pm.scaled(self.pic.width(), self.pic.height(),
                                     Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        self.status.setText(tr("Так будет выглядеть кадр (картинка выше — предпросмотр)."))

    # --- конвертация
    def start(self) -> None:
        n = self.list.count()
        if not n:
            self.status.setText(tr("Сначала добавьте файлы."))
            return
        if self.mode == 0 and self._fx() is None:
            self.status.setText(tr("Проверьте время обрезки: начало и конец — например 0:30 и 2:15."))
            return
        jobs = []
        for i in range(n):
            it = self.list.item(i)
            src = it.data(Qt.ItemDataRole.UserRole)
            sp = Path(src)
            folder = Path(self.out_dir) if self.out_dir else sp.parent
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self.status.setText(tr("Не могу создать папку: {}", e.strerror))
                return
            dst, build, length = self._job_command(src, folder)
            jobs.append(Job(src=src, dst=dst, name=sp.name, build=build, item=it, length=length))
        self._save()
        self.last_out = None
        self._running(True)
        self.queue.start(jobs)

    def _job_command(self, src: str, folder: Path):
        """(куда сохранить, как построить команду ffmpeg, длина результата) — по текущему режиму."""
        sp = Path(src)
        if self.mode == 0:
            st = self._current_settings()
            fmt, br, rate, ch, norm = st["fmt"], st["br"], st["rate"], st["ch"], st["norm"]
            fx = self._fx() or {}
            tags = {k: e.text() for k, e in self.tags.items()}
            dst = unique_path(folder, sp.stem, AUDIO_FORMATS[fmt].ext, avoid=sp)
            return dst, lambda dur: audio_cmd(
                self.ffmpeg, src, str(dst), fmt, br, rate, ch, norm,
                src_rate=probe_sample_rate(src) if (norm or AUDIO_FORMATS[fmt].rates) and not rate else None,
                fx=fx, dur=dur, tags=tags), lambda dur: output_length(fx, dur)
        dst = unique_path(folder, sp.stem, VIDEO_FORMATS[self.vfmt.currentData()][1], avoid=sp)
        args = self._video_args()
        return dst, lambda dur: video_cmd(self.ffmpeg, src, dst=str(dst), duration=dur, **args), None

    def _running(self, on: bool) -> None:
        self.body.setEnabled(not on)
        self.go_btn.setEnabled(not on and bool(self.ffmpeg))
        self.cancel_btn.setEnabled(on)

    @staticmethod
    def _set_item(job: Job, state: str) -> None:
        job.item.setText(f"{job.name}    {state}")

    def _job_started(self, index: int, total: int, job: Job) -> None:
        self.bar.setValue(0)
        self.status.setText(tr("Файл {} из {}: {}", index + 1, total, job.name))
        self._set_item(job, "0%")

    def _job_progress(self, job: Job, pct: int) -> None:
        self.bar.setValue(pct)
        self._set_item(job, f"{pct}%")

    def _job_done(self, job: Job, tail: list) -> None:
        if job.ok:
            self.bar.setValue(100)
            self._set_item(job, tr("✓ готово"))
            self.last_out = job.dst
            self.open_btn.setEnabled(True)
        elif self.queue.cancelled:
            self._set_item(job, tr("отменено"))
        else:
            self._set_item(job, tr("✕ ошибка"))
            job.item.setToolTip("\n".join(tail) or tr("Ошибка ffmpeg"))
            self.status.setText(tr("Ошибка: ") + (tail[-1] if tail else tr("ffmpeg завершился с ошибкой")))

    def cancel(self) -> None:
        self.queue.cancel()

    def _finish(self) -> None:
        done, failed = self.queue.counts()
        total = len(self.queue.jobs)
        self._running(False)
        if self.queue.cancelled:
            self.status.setText(tr("Отменено."))
        elif failed:
            self.status.setText(tr("Готово: {} из {}. С ошибкой: {} (наведите мышь на файл, чтобы увидеть причину).", done, total, failed))
        else:
            self.status.setText(tr("Готово: {} из {}.", done, total))

    def closeEvent(self, e) -> None:
        self.queue.cancel()
        self._save()
        e.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Converter")
    app.setStyle("Fusion")
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}
    theme = apply_theme(kit_themes.current_name())
    win = MainWindow(cfg, theme)
    win.show()
    kit_themes.follow(win._set_theme, lambda: win.theme)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
