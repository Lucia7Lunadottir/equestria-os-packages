#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Equestria Picker — пипетка и копирование цвета в нужном формате (PyQt6).

• Пипетка: на Wayland — через xdg-desktop-portal (GNOME, KDE и др.; нужен python3-gobject),
  запасные варианты: hyprpicker, grim + slurp. На X11/Windows/macOS — своя пипетка с лупой.
• Копирование: ~70 готовых форматов (Web, Unity, Unreal, Godot, Qt, Android, Flutter, Apple, код…)
  и свои шаблоны. Клик по формату копирует его и делает «основным» (Ctrl+C, автокопия после пипетки).
"""
from __future__ import annotations

import colorsys
import json
import math
import os
import re
import shutil
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QPointF, QProcess, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QCursor, QFontDatabase, QGuiApplication,
                         QKeySequence, QLinearGradient, QPainter, QPainterPath,
                         QPalette, QPen)
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QFrame, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMenu, QPushButton, QSizePolicy, QSlider,
                             QVBoxLayout, QWidget)

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit.widgets import load_typed_config, small_btn
from equestria_kit import themes as kit_themes
from equestria_kit import i18n as kit_i18n

tr = kit_i18n.install("equestria-color-picker", __file__)

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-picker" / "settings.json"

# ════════════════════════════════════════════════════════════════════════════
#  ТЕМЫ / СТИЛЬ
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
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#h2 { color: @accent@; font-size: 14px; font-weight: 700; }
QLabel#out { font-size: 16px; font-weight: 600; }
QPushButton { background: @surface0@; border: none; border-radius: 10px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @base@; }
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#primary:disabled { background: @surface1@; color: @surface2@; }
QPushButton#small { padding: 6px 12px; font-size: 13px; border-radius: 9px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QLineEdit { background: @surface0@; border: 2px solid transparent; border-radius: 9px;
    padding: 7px 10px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QLineEdit[error="true"] { border-color: @red@; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { background: @surface0@; border-radius: 9px; padding: 7px 12px; margin: 2px 0; }
QListWidget::item:hover { background: @surface1@; }
QListWidget::item:selected { background: @surface1@; color: @text@; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QSlider::groove:horizontal { height: 6px; background: @surface1@; border-radius: 3px; }
QSlider::sub-page:horizontal { background: @accent@; border-radius: 3px; }
QSlider::handle:horizontal { background: @accent@; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
QToolTip { background: @surface1@; color: @text@; border: none; padding: 4px 8px; }
"""


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME)


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)


# ════════════════════════════════════════════════════════════════════════════
#  ЦВЕТ → ПОЛЯ ДЛЯ ШАБЛОНОВ
# ════════════════════════════════════════════════════════════════════════════
def lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def oklch(lr: float, lg: float, lb: float):
    l = (0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb) ** (1 / 3)
    m = (0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb) ** (1 / 3)
    s = (0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    b = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    C = math.hypot(a, b)
    H = math.degrees(math.atan2(b, a)) % 360 if C > 1e-4 else 0.0
    return L, C, H


def fnum(x: float, p: int, trim: bool) -> str:
    s = f"{x:.{p}f}"
    if trim:
        s = s.rstrip("0")
        if s.endswith("."):
            s += "0"
    return s


def fields(r: int, g: int, b: int, A: int, p: int = 3, trim: bool = True, upper: bool = True) -> dict:
    rf, gf, bf, af = r / 255, g / 255, b / 255, A / 255
    f = lambda x: fnum(x, p, trim)
    hh, ll, sl = colorsys.rgb_to_hls(rf, gf, bf)
    hv, sv, vv = colorsys.rgb_to_hsv(rf, gf, bf)
    lr, lg, lb = lin(rf), lin(gf), lin(bf)
    k = 1 - max(rf, gf, bf)
    cmy = (0, 0, 0) if k >= 1 else [(1 - x - k) / (1 - k) for x in (rf, gf, bf)]
    L, C, H = oklch(lr, lg, lb)
    hx = f"{r:02x}{g:02x}{b:02x}"
    short = hx[0] + hx[2] + hx[4] if (hx[0] == hx[1] and hx[2] == hx[3] and hx[4] == hx[5]) else hx
    case = str.upper if upper else str.lower
    return dict(
        r=r, g=g, b=b, a=A, ap=round(af * 100),
        rf=f(rf), gf=f(gf), bf=f(bf), af=f(af),
        lr=f(lr), lg=f(lg), lb=f(lb),
        hex=case(hx), hexa=case(hx + f"{A:02x}"), ahex=case(f"{A:02x}" + hx), hexs=case(short),
        int=(r << 16) | (g << 8) | b,
        h=round(hh * 360) % 360, s=round(sl * 100), l=round(ll * 100),
        sv=round(sv * 100), v=round(vv * 100),
        hf=f(hv), sf=f(sv), vf=f(vv), lf=f(ll), slf=f(sl),
        c=round(cmy[0] * 100), m=round(cmy[1] * 100), y=round(cmy[2] * 100), k=round(k * 100),
        ol=f"{L * 100:.1f}", oc=f"{C:.4f}", oh=f"{H:.2f}",
    )


def try_render(tpl: str, fl: dict):
    try:
        return tpl.format_map(fl)
    except Exception:
        return None


def luminance(r: int, g: int, b: int) -> float:
    return 0.2126 * lin(r / 255) + 0.7152 * lin(g / 255) + 0.0722 * lin(b / 255)


def contrast(l1: float, l2: float) -> float:
    a, b = max(l1, l2), min(l1, l2)
    return (a + 0.05) / (b + 0.05)


def grade(ratio: float) -> str:
    return "AAA" if ratio >= 7 else "AA" if ratio >= 4.5 else "AA Large" if ratio >= 3 else "✗"


def parse_hex(text: str):
    """RGB(A) по правилам CSS: 3/4/6/8 цифр. Возвращает (r,g,b,a|None) или None."""
    t = text.strip().lstrip("#")
    if t.lower().startswith("0x"):
        t = t[2:]
    if not re.fullmatch(r"[0-9a-fA-F]+", t) or len(t) not in (3, 4, 6, 8):
        return None
    if len(t) in (3, 4):
        t = "".join(ch * 2 for ch in t)
    v = [int(t[i:i + 2], 16) for i in range(0, len(t), 2)]
    return v[0], v[1], v[2], (v[3] if len(v) == 4 else None)


class ColorState:
    """Текущий цвет: HSV + альфа. Оттенок хранится отдельно, поэтому не теряется,
    когда цвет становится серым или чёрным (как в пипетках графических редакторов)."""

    def __init__(self):
        self.h, self.s, self.v, self.a = 0.0, 1.0, 1.0, 1.0

    def rgb(self):
        return tuple(round(x * 255) for x in colorsys.hsv_to_rgb(min(self.h, 0.9999), self.s, self.v))

    def alpha255(self) -> int:
        return round(self.a * 255)

    def hex8(self) -> str:
        r, g, b = self.rgb()
        return f"{r:02x}{g:02x}{b:02x}{self.alpha255():02x}"

    def set_rgb(self, r, g, b, a=None) -> None:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > 0 and v > 0:
            self.h = h
        self.s, self.v = s, v
        if a is not None:
            self.a = a / 255

    def load_hex(self, h8: str) -> None:
        p = parse_hex(h8)
        if p:
            self.set_rgb(p[0], p[1], p[2], 255 if p[3] is None else p[3])

    def fields(self, precision: int, trim: bool, upper: bool) -> dict:
        r, g, b = self.rgb()
        return fields(r, g, b, self.alpha255(), precision, trim, upper)


# ════════════════════════════════════════════════════════════════════════════
#  ФОРМАТЫ КОПИРОВАНИЯ  (категория, название, шаблон)
#  Поля: {r}{g}{b}{a} 0–255 · {rf}{gf}{bf}{af} 0–1 · {lr}{lg}{lb} линейные · {hex}{hexa}{ahex}{hexs}
#        {int} · {h}{s}{l} HSL · {sv}{v} HSV · {hf}{sf}{vf}{lf}{slf} дроби · {c}{m}{y}{k} · {ap} · {ol}{oc}{oh}
# ════════════════════════════════════════════════════════════════════════════
BUILTIN = [
    (tr("Веб"), "#RRGGBB", "#{hex}"),
    (tr("Веб"), "#RRGGBBAA", "#{hexa}"),
    (tr("Веб"), tr("#RGB (если возможно)"), "#{hexs}"),
    (tr("Веб"), tr("RRGGBB (без #)"), "{hex}"),
    (tr("Веб"), "rgb()", "rgb({r}, {g}, {b})"),
    (tr("Веб"), "rgba()", "rgba({r}, {g}, {b}, {af})"),
    (tr("Веб"), tr("rgb() современный"), "rgb({r} {g} {b} / {ap}%)"),
    (tr("Веб"), "hsl()", "hsl({h}, {s}%, {l}%)"),
    (tr("Веб"), "hsla()", "hsla({h}, {s}%, {l}%, {af})"),
    (tr("Веб"), "oklch()", "oklch({ol}% {oc} {oh})"),
    (tr("Веб"), tr("CSS-переменная"), "--color: #{hex};"),
    (tr("Веб"), "Tailwind bg-[…]", "bg-[#{hex}]"),
    ("Unity", "Color (float)", "new Color({rf}f, {gf}f, {bf}f, {af}f)"),
    ("Unity", "Color32 (0–255)", "new Color32({r}, {g}, {b}, {a})"),
    ("Unity", tr("Color (линейный)"), "new Color({lr}f, {lg}f, {lb}f, {af}f)"),
    ("Unity", tr("Hex в Inspector (RRGGBBAA)"), "{hexa}"),
    ("Unity", "ColorUtility.TryParseHtmlString", 'ColorUtility.TryParseHtmlString("#{hexa}", out Color color);'),
    ("Unity", "Color.HSVToRGB", "Color.HSVToRGB({hf}f, {sf}f, {vf}f)"),
    ("Unity", "Vector4", "new Vector4({rf}f, {gf}f, {bf}f, {af}f)"),
    ("Unity", "Rich Text", "<color=#{hexa}></color>"),
    ("Unity", "USS / UI Toolkit", "color: rgba({r}, {g}, {b}, {af});"),
    ("Unity", "Shader float4", "float4({rf}, {gf}, {bf}, {af})"),
    ("Unreal", tr("FLinearColor (линейный)"), "(R={lr},G={lg},B={lb},A={af})"),
    ("Unreal", tr("FLinearColor (как есть, sRGB)"), "(R={rf},G={gf},B={bf},A={af})"),
    ("Unreal", "FColor", "FColor({r}, {g}, {b}, {a})"),
    ("Unreal", "FLinearColor C++", "FLinearColor({lr}f, {lg}f, {lb}f, {af}f)"),
    ("Unreal", tr("FColor из Hex"), 'FColor::FromHex(TEXT("{hexa}"))'),
    ("Godot", "Color()", "Color({rf}, {gf}, {bf}, {af})"),
    ("Godot", "Color8()", "Color8({r}, {g}, {b}, {a})"),
    ("Godot", tr("Color из hex"), 'Color("#{hexa}")'),
    ("Godot", "Color.from_hsv", "Color.from_hsv({hf}, {sf}, {vf}, {af})"),
    ("Qt / QML", "Qt.rgba()", "Qt.rgba({rf}, {gf}, {bf}, {af})"),
    ("Qt / QML", "QColor (0–255)", "QColor({r}, {g}, {b}, {a})"),
    ("Qt / QML", "QML #AARRGGBB", '"#{ahex}"'),
    ("Qt / QML", "QColor::fromRgbF", "QColor::fromRgbF({rf}, {gf}, {bf}, {af})"),
    ("Qt / QML", "QSS rgba()", "rgba({r}, {g}, {b}, {a})"),
    ("Android", "#AARRGGBB", "#{ahex}"),
    ("Android", "Color.argb()", "Color.argb({a}, {r}, {g}, {b})"),
    ("Android", tr("XML-ресурс"), '<color name="color">#{ahex}</color>'),
    ("Android", "Compose Color", "Color(0x{ahex})"),
    ("Android", "Color.parseColor", 'Color.parseColor("#{ahex}")'),
    ("Flutter", "Color(0xAARRGGBB)", "Color(0x{ahex})"),
    ("Flutter", "Color.fromARGB", "Color.fromARGB({a}, {r}, {g}, {b})"),
    ("Flutter", "Color.fromRGBO", "Color.fromRGBO({r}, {g}, {b}, {af})"),
    ("Apple", "UIColor", "UIColor(red: {rf}, green: {gf}, blue: {bf}, alpha: {af})"),
    ("Apple", "SwiftUI Color", "Color(red: {rf}, green: {gf}, blue: {bf}, opacity: {af})"),
    ("Apple", "NSColor", "NSColor(srgbRed: {rf}, green: {gf}, blue: {bf}, alpha: {af})"),
    ("Apple", "#colorLiteral", "#colorLiteral(red: {rf}, green: {gf}, blue: {bf}, alpha: {af})"),
    (tr("Код"), "GLSL vec3", "vec3({rf}, {gf}, {bf})"),
    (tr("Код"), "GLSL vec4", "vec4({rf}, {gf}, {bf}, {af})"),
    (tr("Код"), tr("Массив float"), "[{rf}, {gf}, {bf}, {af}]"),
    (tr("Код"), tr("Кортеж 0–255"), "({r}, {g}, {b})"),
    (tr("Код"), tr("Кортеж RGBA 0–255"), "({r}, {g}, {b}, {a})"),
    (tr("Код"), "0xRRGGBB", "0x{hex}"),
    (tr("Код"), tr("Целое число"), "{int}"),
    (tr("Код"), "Java Color", "new Color({r}, {g}, {b})"),
    (tr("Код"), tr("ANSI escape (текст)"), "\\x1b[38;2;{r};{g};{b}m"),
    (tr("Код"), "LaTeX xcolor", "\\definecolor{{color}}{{RGB}}{{{r},{g},{b}}}"),
    (tr("Модели"), "RGB", "{r}, {g}, {b}"),
    (tr("Модели"), "HSL", "{h}°, {s}%, {l}%"),
    (tr("Модели"), "HSV", "{h}°, {sv}%, {v}%"),
    (tr("Модели"), "CMYK", "{c}%, {m}%, {y}%, {k}%"),
    (tr("Модели"), "Linear RGB", "{lr}, {lg}, {lb}"),
    (tr("Модели"), "OKLCH", "{ol}%, {oc}, {oh}°"),
]
MY = tr("Мои")
CATS = [tr("Все")] + list(dict.fromkeys(c for c, _, _ in BUILTIN)) + [MY]
DEFAULT_PRIMARY = tr("Веб|#RRGGBB")
HELP_FIELDS = (tr("Поля: {r} {g} {b} {a} (0–255) · {rf} {gf} {bf} {af} (0–1) · {lr} {lg} {lb} (линейные) · "
               "{hex} {hexa} {ahex} {hexs} · {int} · {h} {s} {l} (HSL) · {sv} {v} (HSV) · "
               "{hf} {sf} {vf} {lf} · {c} {m} {y} {k} · {ap} · {ol} {oc} {oh}. Для символа «{» пишите «{{»."))


class FormatBook:
    """Форматы копирования: встроенные + свои (cfg["customs"]) и основной (cfg["primary"]).
    Хранит всё прямо в словаре настроек — окну остаётся только сохранить его."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.formats: dict[str, tuple] = {}   # id -> (категория, название, шаблон, свой ли)

    def reload(self) -> None:
        self.formats = {f"{c}|{n}": (c, n, t, False) for c, n, t in BUILTIN}
        for cf in self.cfg["customs"]:
            self.formats[cf["id"]] = (MY, cf["name"], cf["tpl"], True)
        if self.cfg["primary"] not in self.formats:
            self.cfg["primary"] = DEFAULT_PRIMARY

    @property
    def primary(self) -> str:
        return self.cfg["primary"]

    @primary.setter
    def primary(self, fid: str) -> None:
        self.cfg["primary"] = fid

    def matching(self, cat: str, query: str) -> list:
        """id форматов категории cat ("Все" — любой), где query есть в названии, категории или шаблоне."""
        q = query.strip().lower()
        out = []
        for fid, (c, n, t, _custom) in self.formats.items():
            if cat != tr("Все") and c != cat:
                continue
            if q and q not in n.lower() and q not in c.lower() and q not in t.lower():
                continue
            out.append(fid)
        return out

    def render(self, fid: str, fl: dict):
        """Значение формата или None, если в шаблоне ошибка."""
        return try_render(self.formats[fid][2], fl)

    def save_custom(self, fid, name: str, tpl: str) -> str:
        """Изменить свой формат fid или (fid=None) добавить новый; возвращает его id."""
        if fid:
            for cf in self.cfg["customs"]:
                if cf["id"] == fid:
                    cf["name"], cf["tpl"] = name, tpl
        else:
            fid = f"custom|{int(time.time() * 1000)}"
            self.cfg["customs"].append({"id": fid, "name": name, "tpl": tpl})
        self.reload()
        return fid

    def delete_custom(self, fid: str) -> None:
        self.cfg["customs"] = [c for c in self.cfg["customs"] if c["id"] != fid]
        self.reload()


# ════════════════════════════════════════════════════════════════════════════
#  ПИПЕТКА ЭКРАНА
# ════════════════════════════════════════════════════════════════════════════
PORTAL_SCRIPT = r'''
import os, sys
try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    token = "eqpick%d" % os.getpid()
    path = "/org/freedesktop/portal/desktop/request/%s/%s" % (bus.get_unique_name()[1:].replace(".", "_"), token)
    loop = GLib.MainLoop()
    out = {"code": 1}
    def on_resp(conn, sender, obj, iface, sig, params):
        code, res = params.unpack()
        if code == 0 and "color" in res:
            r, g, b = res["color"]
            print(r, g, b)
            out["code"] = 0
        elif code == 1:
            out["code"] = 2
        loop.quit()
    bus.signal_subscribe("org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
                         path, None, Gio.DBusSignalFlags.NONE, on_resp)
    bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                  "org.freedesktop.portal.Screenshot", "PickColor",
                  GLib.Variant("(sa{sv})", ("", {"handle_token": GLib.Variant("s", token)})),
                  None, Gio.DBusCallFlags.NONE, -1, None)
    loop.run()
    sys.exit(out["code"])
except Exception:
    sys.exit(1)
'''
WAYLAND_HELP = (tr("Не удалось взять цвет с экрана в Wayland. Нужен один из вариантов: "
                "python3-gobject + xdg-desktop-portal (GNOME/KDE), hyprpicker (Hyprland) "
                "или grim + slurp (sway и др.)."))


class PickStep:
    """Один способ взять цвет с экрана в Wayland. Новый способ = новый подкласс в PICK_STEPS."""
    kind = ""

    def available(self) -> bool:
        return True

    def command(self) -> list:
        raise NotImplementedError

    def handle(self, picker: "ScreenPicker", code: int, out: bytes) -> None:
        """Разобрать ответ программы: picker.picked / cancelled / failed / next_step / run."""
        raise NotImplementedError


class PortalStep(PickStep):
    """xdg-desktop-portal (GNOME, KDE и др.), нужен python3-gobject."""
    kind = "portal"

    def command(self) -> list:
        py = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else (shutil.which("python3") or sys.executable)
        return [py, "-c", PORTAL_SCRIPT]

    def handle(self, picker, code, out):
        try:
            r, g, b = (float(x) for x in out.decode().split()[:3])
            if code == 0:
                picker.picked.emit(QColor.fromRgbF(r, g, b))
                return
        except ValueError:
            pass
        if code == 2:
            picker.cancelled.emit()
        else:
            picker.next_step()


class HyprpickerStep(PickStep):
    kind = "hypr"

    def available(self) -> bool:
        return bool(shutil.which("hyprpicker"))

    def command(self) -> list:
        return ["hyprpicker", "-f", "hex"]

    def handle(self, picker, code, out):
        m = re.search(rb"#?([0-9a-fA-F]{6})", out)
        if m:
            picker.picked.emit(QColor("#" + m.group(1).decode()))
        else:
            picker.cancelled.emit()


class SlurpStep(PickStep):
    """slurp выбирает точку, затем grim снимает этот пиксель."""
    kind = "slurp"

    def available(self) -> bool:
        return bool(shutil.which("slurp") and shutil.which("grim"))

    def command(self) -> list:
        return ["slurp", "-p"]

    def handle(self, picker, code, out):
        geom = out.decode(errors="ignore").strip()
        if code != 0 or not geom:
            picker.cancelled.emit()
        else:
            picker.run(GrimStep(geom))


class GrimStep(PickStep):
    kind = "grim"

    def __init__(self, geom: str):
        self.geom = geom

    def command(self) -> list:
        return ["grim", "-g", self.geom, "-t", "ppm", "-"]

    def handle(self, picker, code, out):
        if out.startswith(b"P6") and len(out) >= 3:
            r, g, b = out[-3], out[-2], out[-1]
            picker.picked.emit(QColor(r, g, b))
        else:
            picker.failed.emit(WAYLAND_HELP)


PICK_STEPS = (PortalStep, HyprpickerStep, SlurpStep)  # порядок = порядок попыток


class ScreenPicker(QObject):
    """Пипетка для Wayland: пробует способы из PICK_STEPS по очереди, пока один не сработает."""
    picked = pyqtSignal(QColor)
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps: list = []
        self.procs: list = []

    def start(self) -> None:
        self.steps = [step for step in (cls() for cls in PICK_STEPS) if step.available()]
        self.next_step()

    def run(self, step: PickStep) -> None:
        cmd = step.command()
        proc = QProcess(self)
        proc.setProperty("handled", False)
        proc.finished.connect(lambda code, _st, p=proc, st=step: self._finished(p, st, code))
        proc.errorOccurred.connect(lambda err, p=proc: self._error(p, err))
        self.procs.append(proc)
        proc.start(cmd[0], cmd[1:])

    def next_step(self) -> None:
        if not self.steps:
            self.failed.emit(WAYLAND_HELP)
            return
        self.run(self.steps.pop(0))

    def _error(self, proc: QProcess, err) -> None:
        if err == QProcess.ProcessError.FailedToStart and not proc.property("handled"):
            proc.setProperty("handled", True)
            self.next_step()

    def _finished(self, proc: QProcess, step: PickStep, code: int) -> None:
        if proc.property("handled"):
            return
        proc.setProperty("handled", True)
        step.handle(self, code, bytes(proc.readAllStandardOutput()))


class Overlay(QWidget):
    """Пипетка с лупой для X11/Windows/macOS: полноэкранный снимок + клик."""
    picked = pyqtSignal(QColor)
    cancelled = pyqtSignal()

    def __init__(self, screen):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.shot = screen.grabWindow(0)
        self.img = self.shot.toImage()
        self.dpr = self.shot.devicePixelRatio() or 1.0
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.pos_ = self.mapFromGlobal(QCursor.pos())
        self._done = False

    def color_at(self, pt) -> QColor:
        x = min(max(int(pt.x() * self.dpr), 0), self.img.width() - 1)
        y = min(max(int(pt.y() * self.dpr), 0), self.img.height() - 1)
        return self.img.pixelColor(x, y)

    def paintEvent(self, _):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.shot)
        n, zoom = 9, 12
        size = n * zoom
        x = self.pos_.x() + 24
        y = self.pos_.y() + 24
        if x + size > self.width():
            x = self.pos_.x() - 24 - size
        if y + size + 28 > self.height():
            y = self.pos_.y() - 24 - size - 28
        for j in range(n):
            for i in range(n):
                c = self.color_at(QPointF(self.pos_.x() + i - n // 2, self.pos_.y() + j - n // 2))
                p.fillRect(int(x + i * zoom), int(y + j * zoom), zoom, zoom, c)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawRect(int(x + (n // 2) * zoom), int(y + (n // 2) * zoom), zoom, zoom)
        p.setPen(QPen(QColor("#000000"), 1))
        p.drawRect(int(x), int(y), size, size)
        cur = self.color_at(self.pos_)
        p.fillRect(int(x), int(y + size), size, 28, QColor(0, 0, 0, 200))
        p.setPen(QColor("#ffffff"))
        p.drawText(int(x), int(y + size), size, 28, Qt.AlignmentFlag.AlignCenter, cur.name().upper())

    def mouseMoveEvent(self, e):
        self.pos_ = e.position().toPoint()
        self.update()

    def mousePressEvent(self, e):
        if self._done:
            return
        self._done = True
        if e.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self.color_at(e.position().toPoint()))
        else:
            self.cancelled.emit()
        self.close()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and not self._done:
            self._done = True
            self.cancelled.emit()
            self.close()


# ════════════════════════════════════════════════════════════════════════════
#  ВИДЖЕТЫ ВЫБОРА ЦВЕТА
# ════════════════════════════════════════════════════════════════════════════
class SVBox(QWidget):
    changed = pyqtSignal(float, float)

    def __init__(self):
        super().__init__()
        self.h, self.s, self.v = 0.0, 1.0, 1.0
        self.setMinimumSize(240, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_hsv(self, h, s, v):
        self.h, self.s, self.v = h, s, v
        self.update()

    def _rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(2, 2, -2, -2)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._rect()
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        p.setClipPath(path)
        p.fillRect(r, QColor.fromHsvF(min(self.h, 0.9999), 1, 1))
        g = QLinearGradient(r.left(), 0, r.right(), 0)
        g.setColorAt(0, QColor(255, 255, 255))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(r, g)
        g2 = QLinearGradient(0, r.top(), 0, r.bottom())
        g2.setColorAt(0, QColor(0, 0, 0, 0))
        g2.setColorAt(1, QColor(0, 0, 0))
        p.fillRect(r, g2)
        p.setClipping(False)
        pt = QPointF(r.left() + self.s * r.width(), r.top() + (1 - self.v) * r.height())
        p.setPen(QPen(QColor(0, 0, 0, 170), 1))
        p.drawEllipse(pt, 8.5, 8.5)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawEllipse(pt, 7, 7)

    def _pick(self, e):
        r = self._rect()
        pos = e.position()
        self.s = min(max((pos.x() - r.left()) / r.width(), 0.0), 1.0)
        self.v = 1 - min(max((pos.y() - r.top()) / r.height(), 0.0), 1.0)
        self.update()
        self.changed.emit(self.s, self.v)

    mousePressEvent = _pick
    mouseMoveEvent = _pick


class HueBar(QWidget):
    changed = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.h = 0.0
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_hue(self, h):
        self.h = h
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 4, -2, -4)
        g = QLinearGradient(r.left(), 0, r.right(), 0)
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF(min(i / 6, 0.9999), 1, 1))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, 7, 7)
        x = r.left() + self.h * r.width()
        p.setPen(QPen(QColor(0, 0, 0, 170), 1))
        p.setBrush(QColor.fromHsvF(min(self.h, 0.9999), 1, 1))
        p.drawEllipse(QPointF(x, self.height() / 2), 9, 9)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawEllipse(QPointF(x, self.height() / 2), 8, 8)

    def _pick(self, e):
        r = QRectF(self.rect()).adjusted(2, 4, -2, -4)
        self.h = min(max((e.position().x() - r.left()) / r.width(), 0.0), 1.0)
        self.update()
        self.changed.emit(self.h)

    mousePressEvent = _pick
    mouseMoveEvent = _pick


class Swatch(QWidget):
    def __init__(self):
        super().__init__()
        self.color = QColor("#cba6f7")
        self.setFixedHeight(86)

    def set_color(self, c: QColor):
        self.color = c
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        p.setClipPath(path)
        sz = 10
        for y in range(0, self.height(), sz):
            for x in range(0, self.width(), sz):
                p.fillRect(x, y, sz, sz, QColor("#bdbdbd") if (x // sz + y // sz) % 2 == 0 else QColor("#ffffff"))
        p.fillRect(self.rect(), self.color)


def flag(edit: QLineEdit, bad: bool) -> None:
    edit.setProperty("error", bad)
    edit.style().unpolish(edit)
    edit.style().polish(edit)


class FormatDialog(QDialog):
    def __init__(self, parent, fields_fn, name: str = "", tpl: str = ""):
        super().__init__(parent)
        self.fields_fn = fields_fn
        self.setWindowTitle(tr("Свой формат"))
        self.setMinimumWidth(600)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(10)
        self.name = QLineEdit(name)
        self.name.setPlaceholderText(tr("Название, например: Моя игра"))
        self.tpl = QLineEdit(tpl)
        self.tpl.setPlaceholderText(tr("Шаблон, например: new Color({rf}f, {gf}f, {bf}f)"))
        hint = QLabel(HELP_FIELDS)
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.preview = QLabel("")
        self.preview.setObjectName("out")
        self.preview.setWordWrap(True)
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row = QHBoxLayout()
        cancel = QPushButton(tr("Отмена"))
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton(tr("Сохранить"))
        self.ok.setObjectName("primary")
        self.ok.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(self.ok)
        for w in (self.name, self.tpl, hint, self.preview):
            v.addWidget(w)
        v.addLayout(row)
        self.name.textChanged.connect(self._update)
        self.tpl.textChanged.connect(self._update)
        self._update()

    def _update(self) -> None:
        res = try_render(self.tpl.text(), self.fields_fn()) if self.tpl.text() else None
        self.preview.setText(res if res is not None else (tr("— введите шаблон —") if not self.tpl.text()
                                                          else tr("⚠ ошибка в шаблоне (неизвестное поле или скобки)")))
        flag(self.tpl, bool(self.tpl.text()) and res is None)
        self.ok.setEnabled(res is not None and bool(self.name.text().strip()))

    def result_data(self):
        return self.name.text().strip(), self.tpl.text()


# ════════════════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.theme = cfg["theme"]
        self.color = ColorState()
        self.book = FormatBook(cfg)
        self.overlay = None
        self.picker = ScreenPicker(self)
        self.picker.picked.connect(self._screen_picked)
        self.picker.cancelled.connect(self._pick_finished)
        self.picker.failed.connect(self._pick_failed)
        self.save_timer = QTimer(self, singleShot=True, interval=400)
        self.save_timer.timeout.connect(self.save)
        self.toast_timer = QTimer(self, singleShot=True, interval=3500)
        self.setWindowTitle("Equestria Picker")
        self.setMinimumSize(920, 660)
        self.resize(1040, 740)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel("Equestria Picker")
        title.setObjectName("h2")
        theme_btn = small_btn(tr("Тема"))
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        top.addWidget(title)
        top.addStretch()
        top.addWidget(theme_btn)
        root.addLayout(top)
        body = QHBoxLayout()
        body.setSpacing(22)
        root.addLayout(body, 1)
        body.addWidget(self._build_color_column())
        body.addLayout(self._build_formats_column(), 1)

        self.color.load_hex(cfg["color"])
        self._reload_formats()
        self._rebuild_history()
        self._changed(None)

    # --- построение окна
    def _build_color_column(self) -> QWidget:
        """Левая колонка: пипетка, образец, выбор цвета, поля HEX/RGBA, контраст, история."""
        left = QVBoxLayout()
        left.setSpacing(10)
        row = QHBoxLayout()
        self.pick_btn = QPushButton(tr("Пипетка"))
        self.pick_btn.setObjectName("primary")
        self.pick_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pick_btn.clicked.connect(self.start_pick)
        self.copy_btn = QPushButton(tr("Копировать"))
        self.copy_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.copy_btn.clicked.connect(lambda: self.copy_format(self.book.primary))
        row.addWidget(self.pick_btn, 1)
        row.addWidget(self.copy_btn, 1)
        left.addLayout(row)
        self.swatch = Swatch()
        left.addWidget(self.swatch)
        self.sv = SVBox()
        self.sv.changed.connect(self._sv_changed)
        left.addWidget(self.sv, 1)
        self.hue = HueBar()
        self.hue.changed.connect(self._hue_changed)
        left.addWidget(self.hue)
        arow = QHBoxLayout()
        arow.addWidget(QLabel(tr("Альфа")))
        self.alpha = QSlider(Qt.Orientation.Horizontal)
        self.alpha.setRange(0, 255)
        self.alpha.setValue(255)
        self.alpha.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.alpha.valueChanged.connect(self._alpha_changed)
        arow.addWidget(self.alpha, 1)
        left.addLayout(arow)
        erow = QHBoxLayout()
        self.hex_edit = QLineEdit()
        self.hex_edit.setPlaceholderText("#RRGGBB")
        self.hex_edit.textEdited.connect(self._hex_edited)
        erow.addWidget(self.hex_edit, 2)
        self.rgb_edits = []
        for lab in "RGBA":
            e = QLineEdit()
            e.setPlaceholderText(lab)
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e.setMaximumWidth(58)
            e.textEdited.connect(self._rgb_edited)
            self.rgb_edits.append(e)
            erow.addWidget(e)
        left.addLayout(erow)
        self.contrast_label = QLabel("")
        self.contrast_label.setObjectName("hint")
        self.contrast_label.setWordWrap(True)
        left.addWidget(self.contrast_label)
        hrow = QHBoxLayout()
        hl = QLabel(tr("История"))
        hl.setObjectName("h2")
        clr = small_btn(tr("Очистить"))
        clr.clicked.connect(self._clear_history)
        hrow.addWidget(hl)
        hrow.addStretch()
        hrow.addWidget(clr)
        left.addLayout(hrow)
        self.hist_box = QWidget()
        self.hist_lay = QHBoxLayout(self.hist_box)
        self.hist_lay.setContentsMargins(0, 0, 0, 0)
        self.hist_lay.setSpacing(6)
        left.addWidget(self.hist_box)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(400)
        return lw

    def _build_formats_column(self) -> QVBoxLayout:
        """Правая колонка: поиск и список форматов, параметры, свой формат."""
        cfg = self.cfg
        right = QVBoxLayout()
        right.setSpacing(8)
        frow = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Поиск формата…"))
        self.search.textChanged.connect(self._rebuild_list)
        self.cat = QComboBox()
        self.cat.addItems(CATS)
        self.cat.currentIndexChanged.connect(self._rebuild_list)
        frow.addWidget(self.search, 1)
        frow.addWidget(self.cat)
        right.addLayout(frow)
        self.list = QListWidget()
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(lambda it: self.copy_format(it.data(Qt.ItemDataRole.UserRole)))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        right.addWidget(self.list, 1)
        self.toast = QLabel(tr("Клик по формату — скопировать и сделать основным (★)."))
        self.toast.setObjectName("hint")
        self.toast.setWordWrap(True)
        self.toast_timer.timeout.connect(lambda: self.toast.setText(tr("Клик по формату — скопировать и сделать основным (★).")))
        right.addWidget(self.toast)
        orow = QHBoxLayout()
        orow.setSpacing(6)
        self.opt_auto = small_btn(tr("Автокопия после пипетки"), True)
        self.opt_upper = small_btn(tr("HEX ЗАГЛАВНЫМИ"), True)
        self.opt_trim = small_btn(tr("Обрезать нули"), True)
        self.opt_hide = small_btn(tr("Скрывать окно при выборе"), True,
                                  tr("Окно прячется на время пипетки и возвращается после выбора"))
        for b, key in ((self.opt_auto, "autocopy"), (self.opt_hide, "hide"),
                       (self.opt_upper, "upper"), (self.opt_trim, "trim")):
            b.setChecked(bool(cfg[key]))
            b.toggled.connect(lambda on, k=key: self._opt(k, on))
            orow.addWidget(b)
        self.prec = QComboBox()
        for n in (2, 3, 4, 6):
            self.prec.addItem(tr("Знаков: {}", n), n)
        self.prec.setCurrentIndex(max(0, self.prec.findData(int(cfg["precision"]))))
        self.prec.currentIndexChanged.connect(lambda _: self._opt("precision", self.prec.currentData()))
        orow.addWidget(self.prec)
        orow.addStretch()
        add = small_btn(tr("＋ Свой формат"))
        add.clicked.connect(lambda: self._edit_custom(None))
        orow.addWidget(add)
        right.addLayout(orow)
        return right

    # --- состояние цвета
    def fields(self) -> dict:
        return self.color.fields(int(self.cfg["precision"]), bool(self.cfg["trim"]), bool(self.cfg["upper"]))

    # --- синхронизация UI
    def _changed(self, source) -> None:
        c = self.color
        r, g, b = c.rgb()
        A = c.alpha255()
        self.swatch.set_color(QColor(r, g, b, A))
        self.sv.set_hsv(c.h, c.s, c.v)
        if source != "hue":
            self.hue.set_hue(c.h)
        self.alpha.blockSignals(True)
        self.alpha.setValue(A)
        self.alpha.blockSignals(False)
        if source != "hex":
            hx = f"#{r:02x}{g:02x}{b:02x}" + (f"{A:02x}" if A != 255 else "")
            self.hex_edit.setText(hx.upper() if self.cfg["upper"] else hx)
            flag(self.hex_edit, False)
        if source != "rgb":
            for e, val in zip(self.rgb_edits, (r, g, b, A)):
                e.setText(str(val))
                flag(e, False)
        lum = luminance(r, g, b)
        cw, cb = contrast(lum, 1.0), contrast(lum, 0.0)
        self.contrast_label.setText(tr("Контраст: с белым {:.2f}:1 ({}) · с чёрным {:.2f}:1 ({})", cw, grade(cw), cb, grade(cb)))
        self._update_values()
        self.cfg["color"] = c.hex8()
        self.save_timer.start()

    def _sv_changed(self, s, v):
        self.color.s, self.color.v = s, v
        self._changed("sv")

    def _hue_changed(self, h):
        self.color.h = h
        self._changed("hue")

    def _alpha_changed(self, val):
        self.color.a = val / 255
        self._changed("alpha")

    def _hex_edited(self, text):
        p = parse_hex(text)
        flag(self.hex_edit, bool(text.strip()) and p is None)
        if p:
            self.color.set_rgb(p[0], p[1], p[2], p[3])
            self._changed("hex")

    def _rgb_edited(self, _):
        try:
            vals = [int(e.text()) for e in self.rgb_edits]
            ok = all(0 <= x <= 255 for x in vals)
        except ValueError:
            ok = False
        for e in self.rgb_edits:
            flag(e, not ok and bool(e.text().strip()))
        if ok:
            self.color.set_rgb(*vals)
            self._changed("rgb")

    # --- форматы
    def _reload_formats(self) -> None:
        self.book.reload()
        self._rebuild_list()

    def _rebuild_list(self, *_) -> None:
        self.list.clear()
        for fid in self.book.matching(self.cat.currentText(), self.search.text()):
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, fid)
            self.list.addItem(it)
        self._update_values()

    def _update_values(self) -> None:
        if not self.book.formats:
            return
        fl = self.fields()
        for i in range(self.list.count()):
            it = self.list.item(i)
            fid = it.data(Qt.ItemDataRole.UserRole)
            c, n, _t, _ = self.book.formats[fid]
            val = self.book.render(fid, fl)
            star = "★ " if fid == self.book.primary else ""
            head = n if self.cat.currentText() != tr("Все") else f"{c} · {n}"
            it.setText(f"{star}{head}\n{val if val is not None else '⚠ ошибка шаблона'}")

    def value_of(self, fid: str):
        return self.book.render(fid, self.fields())

    def copy_format(self, fid: str) -> None:
        if fid not in self.book.formats:
            return
        val = self.value_of(fid)
        if val is None:
            self._toast(tr("⚠ Ошибка в шаблоне — исправьте его (ПКМ → Изменить)."))
            return
        QGuiApplication.clipboard().setText(val)
        self.book.primary = fid
        self._toast(tr("Скопировано: {}", val))
        self._add_history()
        self._update_values()
        self.save_timer.start()

    def _toast(self, text: str) -> None:
        self.toast.setText(text if len(text) <= 160 else text[:157] + "…")
        self.toast_timer.start()

    def _list_menu(self, pos) -> None:
        it = self.list.itemAt(pos)
        if not it:
            return
        fid = it.data(Qt.ItemDataRole.UserRole)
        c, n, t, custom = self.book.formats[fid]
        menu = QMenu(self)
        menu.addAction(tr("Копировать")).triggered.connect(lambda: self.copy_format(fid))
        menu.addAction(tr("Сделать основным (без копирования)")).triggered.connect(lambda: self._make_primary(fid))
        menu.addAction(tr("Свой формат на основе этого…")).triggered.connect(lambda: self._edit_custom(None, n, t))
        if custom:
            menu.addAction(tr("Изменить…")).triggered.connect(lambda: self._edit_custom(fid))
            menu.addAction(tr("Удалить")).triggered.connect(lambda: self._delete_custom(fid))
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def _make_primary(self, fid: str) -> None:
        self.book.primary = fid
        self._update_values()
        self.save_timer.start()

    def _edit_custom(self, fid, name: str = "", tpl: str = "") -> None:
        if fid:
            _, name, tpl, _ = self.book.formats[fid]
        dlg = FormatDialog(self, self.fields, name, tpl)
        if not dlg.exec():
            return
        self.book.save_custom(fid, *dlg.result_data())
        self._rebuild_list()
        self.cat.setCurrentText(MY)
        self.save()

    def _delete_custom(self, fid: str) -> None:
        self.book.delete_custom(fid)
        self._rebuild_list()
        self.save()

    def _opt(self, key: str, val) -> None:
        self.cfg[key] = val
        self._changed(None)

    # --- история
    def _add_history(self) -> None:
        h8 = self.color.hex8()
        hist = [x for x in self.cfg["history"] if x != h8]
        self.cfg["history"] = ([h8] + hist)[:18]
        self._rebuild_history()

    def _clear_history(self) -> None:
        self.cfg["history"] = []
        self._rebuild_history()
        self.save()

    def _rebuild_history(self) -> None:
        while self.hist_lay.count():
            w = self.hist_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        for h8 in self.cfg["history"]:
            p = parse_hex(h8)
            if not p:
                continue
            b = QPushButton()
            b.setFixedSize(24, 24)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip("#" + h8.upper())
            b.setStyleSheet(f"QPushButton {{ background: rgba({p[0]},{p[1]},{p[2]},{p[3] / 255:.3f});"
                            f" border: 1px solid {THEME['surface2']}; border-radius: 6px; padding: 0; }}")
            b.clicked.connect(lambda _=False, x=h8: self._restore(x))
            self.hist_lay.addWidget(b)
        self.hist_lay.addStretch()

    def _restore(self, h8: str) -> None:
        self.color.load_hex(h8)
        self._changed(None)

    # --- пипетка
    def start_pick(self) -> None:
        self.pick_btn.setEnabled(False)
        hide = bool(self.cfg["hide"])
        if hide:
            self.hide()  # окно вернётся само в _pick_finished
        if QGuiApplication.platformName() == "wayland":
            self._toast(tr("Выберите цвет на экране (Esc — отмена)…"))
            # даём окну время исчезнуть, чтобы оно не попало в кадр
            QTimer.singleShot(250 if hide else 0, self.picker.start)
        else:
            QTimer.singleShot(250 if hide else 0, self._start_overlay)

    def _start_overlay(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.overlay = Overlay(screen)
        self.overlay.picked.connect(self._screen_picked)
        self.overlay.cancelled.connect(self._pick_finished)
        self.overlay.showFullScreen()
        self.overlay.activateWindow()
        self.overlay.setFocus()

    def _screen_picked(self, c: QColor) -> None:
        self.color.set_rgb(c.red(), c.green(), c.blue(), 255)
        self._changed(None)
        self._add_history()
        self._pick_finished()
        if self.cfg["autocopy"]:
            self.copy_format(self.book.primary)

    def _pick_failed(self, msg: str) -> None:
        self._toast(msg)
        self._pick_finished()

    def _pick_finished(self) -> None:
        # освобождаем оверлей только после выхода из его обработчика события
        QTimer.singleShot(0, lambda: setattr(self, "overlay", None))
        self.pick_btn.setEnabled(True)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    # --- тема / настройки
    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self.cfg["theme"] = self.theme
        self._rebuild_history()
        self.save()

    def save(self) -> None:
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def closeEvent(self, e) -> None:
        self.save()
        super().closeEvent(e)

    def keyPressEvent(self, e) -> None:
        if e.matches(QKeySequence.StandardKey.Copy):
            self.copy_format(self.book.primary)
        else:
            super().keyPressEvent(e)


DEFAULTS = {"theme": DEFAULT_THEME, "primary": DEFAULT_PRIMARY, "precision": 3, "trim": True,
            "upper": True, "autocopy": True, "hide": True, "history": [], "customs": [], "color": "cba6f7ff"}


def load_config() -> dict:
    cfg = load_typed_config(CONFIG, DEFAULTS)
    cfg["customs"] = [c for c in cfg["customs"]
                      if isinstance(c, dict) and {"id", "name", "tpl"} <= c.keys()]
    return cfg


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Picker")
    app.setDesktopFileName("equestria-picker")
    app.setStyle("Fusion")
    cfg = load_config()
    cfg["theme"] = apply_theme(kit_themes.current_name())
    win = MainWindow(cfg)
    kit_themes.follow(win._set_theme, lambda: win.theme)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())