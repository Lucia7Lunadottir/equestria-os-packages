#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Equestria GPU — менеджер драйверов видеокарт (PyQt6, Arch / Equestria OS).

• Показывает КАЖДУЮ видеокарту отдельно: поколение, драйвер, версии, Vulkan, температуру.
• Подбирает ветку драйвера по поколению: Turing+ → nvidia-open-dkms (590+),
  Maxwell/Pascal/Volta → equestria-nvidia-580xx, Kepler → 470xx, Fermi → 390xx.
• Диагностика «почему не работает DX12 / DLSS» с кнопками исправления.
• Установка идёт через pg-gpu-sync (pkexec), вывод — в окне журнала.
• Генератор параметров запуска Steam (PRIME, NVAPI/DLSS, DXR, DX11-откат).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import weakref
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QPointF, QProcess, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QFontDatabase, QGuiApplication, QIcon,
                         QPainter, QPalette, QPen, QPixmap, QPolygonF)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                             QPlainTextEdit, QPushButton, QScrollArea,
                             QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit.widgets import card as _card, scrolled, small_btn


def card(title: str = ""):
    """Карточка + её layout (так удобнее строить страницы этого приложения)."""
    f = _card(title)
    return f, f.layout()
from equestria_kit import themes as kit_themes
from equestria_kit import i18n as kit_i18n

tr = kit_i18n.install("equestria-gpu", __file__)

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-gpu" / "settings.json"

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
QWidget { color: @text@; font-size: 14px; }
QLabel { background: transparent; }
QLabel#title { font-size: 17px; font-weight: 700; color: @accent@; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#h2 { color: @accent@; font-size: 14px; font-weight: 700; }
QLabel#rowname { font-size: 15px; font-weight: 600; }
QLabel#out { font-size: 16px; font-weight: 600; }
QLabel#dot { font-size: 18px; color: @subtext@; }
QLabel#dot[lvl="ok"] { color: @green@; }
QLabel#dot[lvl="warn"] { color: @yellow@; }
QLabel#dot[lvl="fail"] { color: @red@; }
QLabel#chip { background: @surface0@; border-radius: 10px; padding: 5px 12px; font-weight: 600; color: @subtext@; }
QLabel#chip[lvl="ok"] { color: @green@; }
QLabel#chip[lvl="warn"] { color: @yellow@; }
QLabel#chip[lvl="fail"] { color: @red@; }

QTabWidget::pane { border: none; }
QTabBar { background: transparent; }
QTabBar::tab { background: transparent; color: @subtext@; padding: 9px 20px; border: none;
    border-bottom: 3px solid transparent; font-size: 15px; font-weight: 600; }
QTabBar::tab:selected { color: @accent@; border-bottom: 3px solid @accent@; }
QTabBar::tab:hover:!selected { color: @text@; }

QPushButton { background: @surface0@; border: none; border-radius: 10px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @base@; }
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#primary:disabled { background: @surface1@; color: @surface2@; }
QPushButton#small { padding: 6px 12px; font-size: 13px; border-radius: 9px; }

QFrame#card { background: @surface0@; border-radius: 14px; }
QCheckBox { spacing: 10px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; background: @mantle@; border: 2px solid @surface2@; }
QCheckBox::indicator:checked { background: @accent@; border-color: @accent@; image: url("@icon:check_mark@"); }
QCheckBox::indicator:disabled { background: @mantle@; border-color: @surface1@; }
QCheckBox:disabled { color: @surface2@; }

QLineEdit { background: @mantle@; border: 2px solid transparent; border-radius: 9px; padding: 8px 12px;
    selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QPlainTextEdit { background: @crust@; border: none; border-radius: 10px; padding: 8px;
    selection-background-color: @accent@; selection-color: @base@; font-size: 13px; }

QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { background: @surface0@; border-radius: 10px; padding: 8px 10px; margin: 3px 0; }
QListWidget::item:hover { background: @surface1@; }
QListWidget::item:selected { background: @surface2@; color: @text@; }
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


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME)


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)


# ════════════════════════════════════════════════════════════════════════════
#  ПОКОЛЕНИЯ И ВЕТКИ ДРАЙВЕРОВ
# ════════════════════════════════════════════════════════════════════════════
def _f(name, branch, vk, dx11, dx12, note=""):
    """dx11/dx12: 1 — да, 2 — ограниченно, 0 — нет."""
    return dict(name=name, branch=branch, vk=vk, dx11=dx11, dx12=dx12, note=note)


FAMILIES = {
    "GB": _f("Blackwell (RTX 50)", "open", "1.3+", 1, 1),
    "AD": _f("Ada Lovelace (RTX 40)", "open", "1.3+", 1, 1),
    "GA": _f("Ampere (RTX 30)", "open", "1.3+", 1, 1),
    "TU": _f("Turing (RTX 20 / GTX 16)", "open", "1.3+", 1, 1),
    "GV": _f("Volta (Titan V)", "580", "1.3", 1, 1),
    "GP": _f("Pascal (GTX 10)", "580", "1.3", 1, 1,
             tr("DX12 на Pascal идёт через VKD3D-Proton и работает только на драйвере 580.xx "
             "(ветки 590+ и nvidia-open эту архитектуру не поддерживают). Нужны Proton 9+ / Proton-GE.")),
    "GM": _f("Maxwell (GTX 9xx / 750)", "580", "1.3", 1, 1,
             tr("У Maxwell 1-го поколения (GTX 750 / 750 Ti, GM107/GM108) уровень DX12 урезан — часть игр не запустится.")),
    "GK": _f("Kepler (GTX 6xx / 7xx)", "470", "1.2", 2, 0,
             tr("Драйвер 470 даёт только Vulkan 1.2: DX12 невозможен, DX9–11 — лишь со старым DXVK (≤ 1.10.3).")),
    "GF": _f("Fermi (GT/GTX 4xx / 5xx)", "390", "", 0, 0,
             tr("Fermi: только OpenGL 4.5, Vulkan нет — DXVK/Proton не работают.")),
    "TESLA": _f("Tesla (GeForce 8xx — 3xx)", "none", "", 0, 0,
                tr("Для этих карт в Arch нет проприетарных драйверов, используется nouveau.")),
}

BRANCHES = {
    "open": dict(dkms="nvidia-open-dkms", utils="nvidia-utils", lib32="lib32-nvidia-utils",
                 label="nvidia-open-dkms (590+)"),
    "580": dict(dkms="equestria-nvidia-580xx-dkms", utils="equestria-nvidia-580xx-utils",
                lib32="lib32-equestria-nvidia-580xx-utils", label="equestria-nvidia-580xx (580.xx)"),
    "470": dict(dkms="nvidia-470xx-dkms", utils="nvidia-470xx-utils", lib32=None, label="nvidia-470xx (470.xx)"),
    "390": dict(dkms="nvidia-390xx-dkms", utils="nvidia-390xx-utils", lib32=None, label="nvidia-390xx (390.xx)"),
    "none": dict(dkms=None, utils=None, lib32=None, label=tr("nouveau (открытый драйвер)")),
}
WHY = {
    "open": tr("Открытые модули ядра NVIDIA с GSP-прошивкой — для Turing и новее. Это единственная ветка 590+, "
            "в ней работают DX12, DLSS и трассировка лучей."),
    "580": tr("Последняя ветка драйвера (580.xx), где ещё поддерживаются Maxwell / Pascal / Volta. "
           "nvidia-open и ветки 590+ на этих картах не запускаются (kernel panic) — поэтому нужен именно этот пакет."),
    "470": tr("Последняя ветка с поддержкой Kepler. Vulkan 1.2, DX12 нет. Пакеты берутся из офлайн-кэша pg-gpu-sync."),
    "390": tr("Последняя ветка с поддержкой Fermi. Только OpenGL, без Vulkan. Пакеты берутся из офлайн-кэша pg-gpu-sync."),
    "none": tr("Для этого поколения проприетарных драйверов нет — работает nouveau."),
}
BRANCH_GPUS = {
    "open": tr("Turing и новее — GeForce RTX 20 / 30 / 40 / 50, GTX 16xx (1650, 1660), Quadro RTX, ноутбучные RTX"),
    "580": tr("Maxwell, Pascal, Volta — GTX 750 / 750 Ti, GTX 9xx, GTX 10xx (1050, 1060, 1070, 1080), "
           "Titan X / Xp / V, ноутбучные 9xxM / 10xx. Работает и на RTX, но без новых возможностей"),
    "470": tr("Kepler — GTX 650 / 660 / 670 / 680 / 760 / 770 / 780, Titan, GT 6xx / 7xx, ноутбучные 6xxM / 7xxM"),
    "390": tr("Fermi — GTX 460 / 470 / 480 / 550 Ti / 560 / 570 / 580, GT 4xx / 5xx, ноутбучные 4xxM / 5xxM"),
    "none": tr("Любая карта как запасной вариант; для GeForce 8xxx — GT 3xx (Tesla) и старее — единственный"),
}
BRANCH_PKGS = {b: {x for x in (d["dkms"], d["utils"], d["lib32"]) if x} for b, d in BRANCHES.items()}
EXTRA_PKGS = {"nvidia-dkms", "nvidia", "nvidia-lts", "nvidia-open", "nvidia-open-lts", "equestria-nvidia-dkms"}


def foreign_pkgs(branch: str, pkgs: dict) -> list:
    own = BRANCH_PKGS.get(branch, set())
    out = []
    for b, s in BRANCH_PKGS.items():
        if b != branch:
            out += [p for p in s if p in pkgs and p not in own]
    for p in EXTRA_PKGS:
        if p not in pkgs:
            continue
        if branch == "open" and p in ("nvidia-open", "nvidia-open-lts"):
            continue
        if branch == "580" and p == "equestria-nvidia-dkms":
            continue
        out.append(p)
    return sorted(set(out))


def nv_family(chip: str) -> str:
    c = chip.upper()
    if c[:2] in FAMILIES and c[2:3].isdigit():
        return c[:2]
    if c.startswith(("GT", "NV", "MCP")) or re.match(r"G\d", c):
        return "TESLA"
    return ""


# ════════════════════════════════════════════════════════════════════════════
#  СБОР ДАННЫХ О СИСТЕМЕ
# ════════════════════════════════════════════════════════════════════════════
def sh(cmd: list, timeout: int = 10) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def read(path: str) -> str:
    try:
        return Path(path).read_text(errors="ignore")
    except OSError:
        return ""


@dataclass
class Gpu:
    addr: str
    vid: str
    did: str
    vendor: str
    name: str
    chip: str
    driver: str = ""
    modules: list = field(default_factory=list)
    boot: bool = False
    fam: str = ""
    rtx: bool = False
    checks: list = field(default_factory=list)

    @property
    def branch(self) -> str:
        return FAMILIES[self.fam]["branch"] if self.fam in FAMILIES else "none"

    @property
    def fam_name(self) -> str:
        return FAMILIES[self.fam]["name"] if self.fam in FAMILIES else ""

    @property
    def worst(self) -> str:
        for lvl in ("fail", "warn"):
            if any(c.level == lvl for c in self.checks):
                return lvl
        return "ok"


@dataclass
class Sys:
    kernel: str = ""
    session: str = ""
    pkgs: dict = field(default_factory=dict)
    dkms: list = field(default_factory=list)
    multilib: bool = False
    vk: list = field(default_factory=list)
    vk_tool: bool = False
    smi: dict = field(default_factory=dict)
    nv_version: str = ""
    modeset: str = ""
    env: dict = field(default_factory=dict)
    avail: dict = field(default_factory=dict)
    gpus: list = field(default_factory=list)

    def vk_for(self, g: Gpu):
        for d in self.vk:
            if d.get("vendorID", "").lower() == "0x" + g.vid:
                return d
        return None

    def pkgver(self, name: str) -> str:
        v = self.pkgs.get(name, "")
        return re.sub(r"^\d+:", "", v).rsplit("-", 1)[0] if v else ""


VENDORS = {"10de": "nvidia", "1002": "amd", "1022": "amd", "8086": "intel"}
VENDOR_LABEL = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel", "other": tr("Другой")}


def probe_gpus() -> list:
    gpus, cur = [], None
    rx = re.compile(r"(\S+)\s+.+?\s+\[(03[0-9a-f]{2})\]:\s+(.+?)\s+\[([0-9a-f]{4}):([0-9a-f]{4})\]")
    for line in sh(["lspci", "-nnDk"]).splitlines():
        if line and not line[0].isspace():
            cur = None
            m = rx.match(line)
            if not m or m.group(2) not in ("0300", "0302", "0380"):
                continue
            desc, vid, did = m.group(3), m.group(4), m.group(5)
            mk = re.search(r"\[([^\[\]]+)\]\s*$", desc)
            chip = ""
            if vid == "10de":
                cm = re.search(r"NVIDIA Corporation\s+(\S+)", desc)
                chip = cm.group(1) if cm else ""
            g = Gpu(m.group(1), vid, did, VENDORS.get(vid, "other"), mk.group(1) if mk else desc, chip)
            g.boot = read(f"/sys/bus/pci/devices/{g.addr}/boot_vga").strip() == "1"
            if g.vendor == "nvidia":
                g.fam = nv_family(chip)
                n = g.name.upper()
                g.rtx = g.fam in ("GA", "AD", "GB") or (g.fam == "TU" and "RTX" in n)
            gpus.append(g)
            cur = g
        elif cur is not None:
            s = line.strip()
            if s.startswith("Kernel driver in use:"):
                cur.driver = s.split(":", 1)[1].strip()
            elif s.startswith("Kernel modules:"):
                cur.modules = [x.strip() for x in s.split(":", 1)[1].split(",")]
    return gpus


def probe_vulkan() -> list:
    devs, cur = [], None
    for line in sh(["vulkaninfo", "--summary"], 25).splitlines():
        if re.match(r"\s*GPU\d+:", line):
            cur = {}
            devs.append(cur)
        elif cur is not None:
            m = re.match(r"\s*(\w+)\s*=\s*(.+)", line)
            if m:
                cur[m.group(1)] = m.group(2).strip()
    return devs


def probe_smi() -> dict:
    keys = ("bus", "name", "driver", "vram", "temp", "power", "util", "clock", "pstate")
    q = "pci.bus_id,name,driver_version,memory.total,temperature.gpu,power.draw,utilization.gpu,clocks.gr,pstate"
    res = {}
    for line in sh(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"], 8).splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= len(keys):
            res[p[0][-7:].lower()] = dict(zip(keys, p))
    return res


def probe_env() -> dict:
    files = ["/etc/environment"] + sorted(glob.glob("/etc/environment.d/*.conf")) \
        + sorted(glob.glob(str(Path.home() / ".config/environment.d/*.conf")))
    env = {}
    for f in files:
        for line in read(f).splitlines():
            m = re.match(r"\s*(?:export\s+)?([A-Za-z_]\w*)=(.*)", line)
            if m and not line.lstrip().startswith("#"):
                env[m.group(1)] = m.group(2).strip().strip("\"'")
    for k in ("VK_ICD_FILENAMES", "VK_DRIVER_FILES", "__GLX_VENDOR_LIBRARY_NAME", "GBM_BACKEND"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


DRIVER_CACHE = "/usr/share/pg-gpu-sync/drivers"


def cached_pkg(name: str) -> str:
    files = sorted(glob.glob(f"{DRIVER_CACHE}/{name}-[0-9]*.pkg.tar.zst"), key=os.path.getmtime)
    return files[-1] if files else ""


def probe_avail(S: Sys) -> dict:
    """Откуда можно взять каждый пакет драйвера: installed / repo / cache / ''."""
    names = sorted({p for s in BRANCH_PKGS.values() for p in s})
    found = set(re.findall(r"^Name\s*:\s*(\S+)", sh(["pacman", "-Si", *names], 20), re.M))
    return {p: ("installed" if p in S.pkgs else "repo" if p in found else "cache" if cached_pkg(p) else "")
            for p in names}


def probe_system() -> Sys:
    S = Sys()
    S.kernel = os.uname().release
    S.session = os.environ.get("XDG_SESSION_TYPE", "?")
    for line in sh(["pacman", "-Q"], 20).splitlines():
        a = line.split(None, 1)
        if len(a) == 2:
            S.pkgs[a[0]] = a[1]
    S.multilib = bool(re.search(r"^\[multilib\]", read("/etc/pacman.conf"), re.M))
    for line in sh(["dkms", "status"]).splitlines():
        m = re.match(r"(\S+?)/(\S+?),\s*(\S+?),\s*(\S+?):\s*(\w+)", line.strip())
        if m:
            S.dkms.append((m.group(1), m.group(2), m.group(3), m.group(5)))
    S.vk_tool = bool(shutil.which("vulkaninfo"))
    S.vk = probe_vulkan() if S.vk_tool else []
    S.smi = probe_smi() if shutil.which("nvidia-smi") else {}
    first = (read("/proc/driver/nvidia/version").splitlines() or [""])[0]
    m = re.search(r"(\d{3}\.\d+(?:\.\d+)?)", first)
    S.nv_version = m.group(1) if m else ""
    S.modeset = read("/sys/module/nvidia_drm/parameters/modeset").strip()
    S.env = probe_env()
    S.avail = probe_avail(S)
    S.gpus = probe_gpus()
    for g in S.gpus:
        g.checks = checks_for(g, S)
    return S


# ════════════════════════════════════════════════════════════════════════════
#  ПРОВЕРКИ
# ════════════════════════════════════════════════════════════════════════════
LVL_ORDER = {"fail": 0, "warn": 1, "info": 2, "ok": 3}
# --reset-mode: рекомендуемый драйвер = снова автоподбор (снимает сохранённый выбор nouveau,
# иначе служба pg-gpu-watch при загрузке перестала бы следить за драйвером)
SYNC = (tr("Установить рекомендуемый драйвер"), "sync", ["--reset-mode"])


@dataclass
class Check:
    level: str
    title: str
    detail: str
    fix: tuple | None = None


def headers_pkg(kernel: str) -> str:
    m = re.search(r"-(lts|zen|hardened|rt|cachyos)", kernel)
    return f"linux-{m.group(1)}-headers" if m else "linux-headers"


def api_tuple(s: str) -> tuple:
    m = re.match(r"(\d+)\.(\d+)", s or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


class CheckContext:
    """Всё, что нужно правилам про одну карту, + собранные результаты."""

    def __init__(self, g: Gpu, S: Sys):
        self.g, self.S = g, S
        self.fam = FAMILIES.get(g.fam)
        self.br = BRANCHES[g.branch]
        self.dkms_pkg = self.br["dkms"]
        self.results: list = []

    def add(self, lvl: str, title: str, detail: str, fix=None) -> None:
        self.results.append(Check(lvl, title, detail, fix))

    def unpack(self) -> tuple:
        return self.g, self.S, self.fam, self.br, self.dkms_pkg, self.add


class Rule(ABC):
    """Одна проверка диагностики (Open/Closed: новая проверка — новый класс в
    RULES, существующие не трогаются). vendors — к каким картам применима."""
    vendors: tuple = ("nvidia",)

    def applies(self, ctx: CheckContext) -> bool:
        return ctx.g.vendor in self.vendors

    @abstractmethod
    def run(self, ctx: CheckContext) -> None: ...


class KernelDriverRule(Rule):
    """1. Драйвер ядра: Какой драйвер ядра обслуживает карту."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if g.driver == "nvidia":
            add("ok", tr("Драйвер ядра: nvidia"), tr("Карта работает на драйвере NVIDIA{}.", ' ' + S.nv_version if S.nv_version else ''))
        elif g.driver == "nouveau":
            if g.branch == "none":
                add("info", tr("Драйвер ядра: nouveau"), tr("Для этого поколения nouveau — штатный вариант."))
            else:
                add("fail", tr("Карта работает на nouveau, а не на драйвере NVIDIA"),
                    tr("Под nouveau нет NVAPI и DLSS, а DX12 (VKD3D-Proton) работает ограниченно или не запускается. Для вашей карты нужен {}.", br['label']), SYNC)
        elif not g.driver:
            add("fail", tr("Драйвер ядра не загружен"),
                tr("Видеокарта не привязана ни к одному драйверу — игры уйдут на программный рендер."), SYNC)
        else:
            add("info", tr("Драйвер ядра: {}", g.driver), tr("Нестандартный драйвер (например, vfio-pci для проброса в виртуальную машину)."))


class BranchPackagesRule(Rule):
    """2. Пакеты ветки: Установлен ли пакет нужной ветки и нет ли пакетов чужой ветки."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if dkms_pkg:
            have = (dkms_pkg in S.pkgs or (g.branch == "open" and ("nvidia-open" in S.pkgs or "nvidia-open-lts" in S.pkgs))
                    or (g.branch == "580" and "equestria-nvidia-dkms" in S.pkgs))
            if have:
                add("ok", tr("Пакет драйвера установлен: {}", dkms_pkg if dkms_pkg in S.pkgs else tr('совместимый аналог')),
                    tr("Ветка для {}: {}.", g.fam_name, br['label']))
            else:
                add("fail", tr("Не установлен рекомендуемый пакет {}", dkms_pkg),
                    tr("Для {} нужен {}. {}", g.fam_name, br['label'], WHY[g.branch]), SYNC)
            bad = foreign_pkgs(g.branch, S.pkgs)
            if bad:
                add("fail", tr("Установлены пакеты другой ветки драйвера"),
                    tr("{} несовместимы с {}: ветки взаимоисключающие", ', '.join(bad), g.fam_name)
                    + (tr(" (nvidia-open на Pascal/Maxwell/Volta вызывает kernel panic).") if g.branch == "580" else "."), SYNC)
        elif g.branch == "none":
            bad = [p for p in BRANCH_PKGS["open"] | BRANCH_PKGS["580"] if p in S.pkgs]
            if bad:
                add("warn", tr("Установлены драйверы, которые эта карта не поддерживает"), ", ".join(bad), SYNC)


class DkmsRule(Rule):
    """3. DKMS и заголовки ядра: Собран ли DKMS-модуль для текущего ядра (и есть ли заголовки)."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        uses_dkms = bool(dkms_pkg) and (dkms_pkg in S.pkgs or "equestria-nvidia-dkms" in S.pkgs)
        if uses_dkms:
            mine = [d for d in S.dkms if d[0] == "nvidia" and d[2] == S.kernel]
            if any(d[3] == "installed" for d in mine):
                add("ok", tr("DKMS-модуль собран для ядра {}", S.kernel), tr("Модули nvidia готовы к загрузке."))
            else:
                hp = headers_pkg(S.kernel)
                if not Path(f"/usr/lib/modules/{S.kernel}/build").exists():
                    add("fail", tr("Нет заголовков для ядра {}", S.kernel),
                        tr("DKMS не может собрать модуль без {}. После установки пересоберите DKMS.", hp),
                        (tr("Установить {}", hp), "pkgs", [hp]))
                else:
                    add("fail", tr("DKMS-модуль не собран для ядра {}", S.kernel),
                        tr("Драйвер установлен, но модуль ядра отсутствует — после перезагрузки карта останется без драйвера."),
                        (tr("Пересобрать DKMS и initramfs"), "dkms", []))


class VersionMatchRule(Rule):
    """4. Версии модуль/библиотеки: Совпадают ли версии модуля ядра и пользовательских библиотек."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        uv = S.pkgver(br["utils"] if br["utils"] in S.pkgs else "nvidia-utils")
        if S.nv_version and uv:
            if S.nv_version == uv:
                add("ok", tr("Версии совпадают: {}", uv), tr("Модуль ядра и пользовательские библиотеки одной версии."))
            else:
                add("fail", tr("Модуль ядра {} ≠ библиотеки {}", S.nv_version, uv),
                    tr("Драйвер обновили, но модуль ядра старый. Перезагрузите систему — иначе будет ошибка "
                    "«Driver/library version mismatch», а Vulkan/DX12 не заработают."))


class ModesetRule(Rule):
    """5. DRM modeset: nvidia_drm.modeset и файл nvidia_icd.json."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if g.driver == "nvidia":
            if S.modeset == "Y":
                add("ok", "nvidia_drm.modeset=1", tr("Wayland, PRIME и корректный вывод в играх включены."))
            else:
                add("warn", tr("nvidia_drm.modeset выключен"),
                    tr("Для Wayland, гибридной графики и стабильного вывода нужен modeset=1 — pg-gpu-sync пропишет его."), SYNC)
            if not Path("/usr/share/vulkan/icd.d/nvidia_icd.json").exists():
                add("fail", tr("Нет файла nvidia_icd.json"),
                    tr("Vulkan-загрузчик не знает о драйвере NVIDIA — не работают ни DXVK (DX9–11), ни VKD3D-Proton (DX12)."), SYNC)


class NvidiaVulkanRule(Rule):
    """6. Vulkan: Vulkan-загрузчик, видит ли Vulkan карту, мешающие переменные окружения."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if g.branch in ("open", "580", "470"):
            miss = [p for p in ("vulkan-icd-loader", "lib32-vulkan-icd-loader") if p not in S.pkgs
                    and (p == "vulkan-icd-loader" or S.multilib)]
            if miss:
                add("warn", tr("Не установлен Vulkan-загрузчик"), ", ".join(miss) + tr(" — без него игры не увидят Vulkan."),
                    (tr("Установить ") + " ".join(miss), "pkgs", miss))
            vk = S.vk_for(g)
            if not S.vk_tool:
                add("info", tr("vulkaninfo не найден"), tr("Установите vulkan-tools — тогда здесь появится проверка Vulkan."),
                    (tr("Установить vulkan-tools"), "pkgs", ["vulkan-tools"]))
            elif not vk:
                add("fail", tr("Vulkan не видит эту видеокарту"),
                    tr("Без Vulkan игры пишут «DX12 не поддерживается» или падают при старте. Частые причины: драйвер не "
                    "загружен, нет nvidia_icd.json, переменная VK_ICD_FILENAMES скрывает драйвер NVIDIA."), SYNC)
            else:
                api = vk.get("apiVersion", "?")
                if api_tuple(api) >= (1, 3):
                    add("ok", tr("Vulkan {} (драйвер {})", api.split()[0], vk.get('driverName', '?')),
                        tr("Этого достаточно для DXVK 2.x и VKD3D-Proton (DX12)."))
                elif g.branch == "470":
                    add("info", f"Vulkan {api.split()[0]}", tr("Предел драйвера 470: DX12 недоступен, DX9–11 — только со старым DXVK ≤ 1.10.3."))
                else:
                    add("warn", tr("Vulkan {} — ниже 1.3", api.split()[0]),
                        tr("Для VKD3D-Proton нужен Vulkan 1.3: обновите драйвер своей ветки."), SYNC)
        for k in ("VK_ICD_FILENAMES", "VK_DRIVER_FILES"):
            v = S.env.get(k)
            if v and "nvidia" not in v.lower():
                add("warn", tr("Переменная {} скрывает драйвер NVIDIA", k), tr("{}={}. Уберите её из /etc/environment или environment.d.", k, v))


class Lib32Rule(Rule):
    """7. 32-битные библиотеки: 32-битные библиотеки для Steam/Wine."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if br["lib32"]:
            if not S.multilib:
                add("warn", tr("Репозиторий [multilib] не включён"),
                    tr("Без него не поставить 32-битные библиотеки драйвера — Steam и 32-битные игры работают хуже. "
                    "Раскомментируйте [multilib] в /etc/pacman.conf."))
            elif br["lib32"] not in S.pkgs:
                add("warn", tr("Нет 32-битных библиотек ({})", br['lib32']),
                    tr("Нужны Steam, Wine и 32-битным играм (в т.ч. DX9/DX11-играм)."), SYNC)
            else:
                add("ok", tr("32-битные библиотеки драйвера установлены"), br["lib32"])
        elif g.branch in ("470", "390"):
            add("info", tr("32-битные библиотеки недоступны"), tr("Для этой ветки драйвера lib32-пакетов не существует."))


class DlssRule(Rule):
    """8. DLSS / RT: Файлы DLSS (NGX) на RTX или пояснение, почему DLSS нет."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if g.rtx:
            wine = Path("/usr/lib/nvidia/wine/nvngx.dll").exists()
            so = bool(glob.glob("/usr/lib/libnvidia-ngx.so*"))
            if wine and so:
                add("ok", tr("Файлы DLSS (NGX) на месте"), tr("libnvidia-ngx.so и nvngx.dll найдены."))
            else:
                add("warn", tr("Не найдены файлы DLSS (NGX)"),
                    tr("nvidia-utils кладёт libnvidia-ngx.so и nvngx.dll в /usr/lib и /usr/lib/nvidia/wine. "
                    "Без них DLSS в Proton недоступен — переустановите nvidia-utils."))
            add("info", tr("Чтобы DLSS заработал в Proton"),
                tr("Нужны: игра запущена именно на NVIDIA (а не на встроенной графике), Proton 9+ / Proton-GE / Experimental и "
                "переменные PROTON_ENABLE_NVAPI=1 DXVK_ENABLE_NVAPI=1 — готовая строка есть на вкладке «Игры»."))
        else:
            add("info", tr("DLSS и RT на этой карте недоступны"),
                tr("DLSS и аппаратная трассировка требуют RTX (тензорные/RT-ядра). У GTX 10xx и 16xx их нет — "
                "используйте FSR или XeSS в настройках игры, они работают на любых картах."))


class Dx12Rule(Rule):
    """9. DX12 и особенности поколения: Поддержка DX12 у поколения карты."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if fam:
            txt = {1: tr("DX12 поддерживается через VKD3D-Proton."), 2: tr("DX12 — ограниченно."), 0: tr("DX12 недоступен.")}[fam["dx12"]]
            add("ok" if fam["dx12"] == 1 and g.driver == "nvidia" else "info", "DX12 (VKD3D-Proton)",
                txt + (" " + fam["note"] if fam["note"] else ""))


class HybridGraphicsRule(Rule):
    """10. Гибридная графика: Гибридная графика: PRIME, nvidia-prime, глобальный рендер на NVIDIA."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if any(o.vendor != "nvidia" for o in S.gpus):
            add("info", tr("Гибридная графика (встроенная + NVIDIA)"),
                tr("Игры нужно запускать на NVIDIA: prime-run %command%. Если игра попала на встроенную графику, "
                "DX12 «пропадает», а DLSS недоступен — это самая частая причина проблем на ноутбуках с RTX."))
            if "nvidia-prime" not in S.pkgs:
                add("warn", tr("Не установлен nvidia-prime"), tr("Нужен для prime-run (запуск программ на NVIDIA)."),
                    (tr("Установить nvidia-prime"), "pkgs", ["nvidia-prime"]))
            if S.env.get("__GLX_VENDOR_LIBRARY_NAME") == "nvidia":
                add("info", tr("Рабочий стол целиком идёт на NVIDIA"),
                    tr("Глобально выставлено __GLX_VENDOR_LIBRARY_NAME=nvidia — это быстрее для игр, но сильнее расходует батарею."))


class MesaDriverRule(Rule):
    """AMD / Intel: открытый драйвер ядра и пакеты Vulkan/Mesa."""
    vendors = ("amd", "intel")
    EXPECTED = {"amd": ("amdgpu", "vulkan-radeon"), "intel": ("i915", "vulkan-intel")}

    def run(self, ctx: CheckContext) -> None:
        g, S = ctx.g, ctx.S
        exp = self.EXPECTED[g.vendor]
        good = (exp[0], "xe") if g.vendor == "intel" else (exp[0],)
        if g.driver in good:
            ctx.add("ok", tr("Драйвер ядра: {}", g.driver), tr("Открытый драйвер Mesa/ядра — всё штатно."))
        else:
            ctx.add("warn", tr("Драйвер ядра: {}", g.driver or tr('не загружен')), tr("Ожидался {}.", tr(' или ').join(good)))
        miss = [p for p in (exp[1], "mesa") + (("lib32-" + exp[1], "lib32-mesa") if S.multilib else ()) if p not in S.pkgs]
        if miss:
            ctx.add("warn", tr("Не хватает пакетов Vulkan/Mesa"), ", ".join(miss),
                    (tr("Установить ") + " ".join(miss), "pkgs", miss))
        else:
            ctx.add("ok", tr("Пакеты Vulkan/Mesa установлены"), exp[1])


class MesaVulkanRule(Rule):
    """Любая не-NVIDIA карта: видит ли её Vulkan и хватает ли версии для DX12."""

    def applies(self, ctx: CheckContext) -> bool:
        return ctx.g.vendor != "nvidia"

    def run(self, ctx: CheckContext) -> None:
        g, S = ctx.g, ctx.S
        vk = S.vk_for(g)
        if not S.vk_tool:
            ctx.add("info", tr("vulkaninfo не найден"), tr("Установите vulkan-tools для проверки Vulkan."),
                    (tr("Установить vulkan-tools"), "pkgs", ["vulkan-tools"]))
        elif vk:
            api = vk.get("apiVersion", "?")
            ok = api_tuple(api) >= (1, 3)
            ctx.add("ok" if ok else "warn", f"Vulkan {api.split()[0]}",
                    tr("Достаточно для DX12 через VKD3D-Proton.") if ok else tr("Для DX12 нужен Vulkan 1.3."))
        else:
            ctx.add("warn", tr("Vulkan не видит эту видеокарту"), tr("Проверьте установку vulkan-radeon / vulkan-intel."))


# Порядок = порядок строк на вкладке «Диагностика».
RULES: tuple = (KernelDriverRule(), BranchPackagesRule(), DkmsRule(), VersionMatchRule(), ModesetRule(),
                NvidiaVulkanRule(), Lib32Rule(), DlssRule(), Dx12Rule(), HybridGraphicsRule(),
                MesaDriverRule(), MesaVulkanRule())


def checks_for(g: Gpu, S: Sys) -> list:
    ctx = CheckContext(g, S)
    for rule in RULES:
        if rule.applies(ctx):
            rule.run(ctx)
    return ctx.results


# ════════════════════════════════════════════════════════════════════════════
#  СВОДКА, ПАРАМЕТРЫ ЗАПУСКА, КОМАНДЫ
# ════════════════════════════════════════════════════════════════════════════
def capabilities(g: Gpu, S: Sys) -> list:
    vk = S.vk_for(g)
    api = vk.get("apiVersion", "").split()[0] if vk else ""
    if g.vendor != "nvidia":
        ok = api_tuple(api) >= (1, 3)
        return [(f"{'✓' if api else '✗'} Vulkan {api or '—'}", "ok" if api else "fail"),
                (f"{'✓' if ok else '✗'} DX12 (VKD3D)", "ok" if ok else "warn")]
    fam = FAMILIES.get(g.fam)
    drv = g.driver == "nvidia"
    if not fam:
        return [(tr("? Поколение не определено"), "warn")]

    def chip(label, val):
        sym = {1: "✓", 2: "~", 0: "✗"}[val]
        lvl = "fail" if val == 0 else ("ok" if val == 1 and drv else "warn")
        return (f"{sym} {label}", lvl)

    return [chip("DX9–11 (DXVK)", fam["dx11"]), chip("DX12 (VKD3D)", fam["dx12"]),
            (f"{'✓' if (api or fam['vk']) else '✗'} Vulkan {api or fam['vk'] or '—'}",
             ("ok" if drv else "warn") if (api or fam["vk"]) else "fail"),
            chip("DLSS", 1 if g.rtx else 0), chip("Ray Tracing", 1 if g.rtx else 0)]


def overview_rows(g: Gpu, S: Sys) -> list:
    r = [(tr("Модель"), g.name), (tr("Производитель"), VENDOR_LABEL[g.vendor]),
         ("PCI", f"{g.addr}  [{g.vid}:{g.did}]" + (tr("  чип {}", g.chip) if g.chip else ""))]
    if g.vendor == "nvidia":
        r.append((tr("Поколение"), g.fam_name or tr("не определено (будет nouveau)")))
    r.append((tr("Роль"), tr("Основная (boot VGA)") if g.boot else tr("Дополнительная") + (" (PRIME offload)" if len(S.gpus) > 1 else "")))
    r.append((tr("Драйвер сейчас"), g.driver or tr("не загружен")))
    if g.vendor == "nvidia":
        r.append((tr("Рекомендуемая ветка"), BRANCHES[g.branch]["label"]))
        inst = [f"{p} {S.pkgs[p]}" for p in sorted(S.pkgs) if p in BRANCH_PKGS["open"] | BRANCH_PKGS["580"]
                | BRANCH_PKGS["470"] | BRANCH_PKGS["390"] | EXTRA_PKGS | {"nvidia-settings", "nvidia-prime"}]
        r.append((tr("Установлено"), "\n".join(inst) or tr("— драйверов NVIDIA нет")))
        if S.nv_version:
            r.append((tr("Версия модуля ядра"), S.nv_version))
    vk = S.vk_for(g)
    r.append(("Vulkan", f"{vk.get('apiVersion', '?')}  ·  {vk.get('driverName', '')}" if vk else tr("не определён")))
    sm = S.smi.get(g.addr[-7:].lower())
    if sm:
        r += [("VRAM", tr("{} МиБ", sm['vram'])), (tr("Температура"), f"{sm['temp']} °C"), (tr("Нагрузка"), f"{sm['util']} %"),
              (tr("Мощность"), tr("{} Вт", sm['power'])), (tr("Частота ядра"), tr("{} МГц", sm['clock'])), ("P-state", sm["pstate"])]
    r.append((tr("Сессия"), S.session))
    return r


def launch_options(g: Gpu, S: Sys, f: dict) -> str:
    env, pre = [], []
    if f.get("prime"):
        if g.vendor == "nvidia":
            env += ["__NV_PRIME_RENDER_OFFLOAD=1", "__VK_LAYER_NV_optimus=NVIDIA_only", "__GLX_VENDOR_LIBRARY_NAME=nvidia",
                    'DXVK_FILTER_DEVICE_NAME="NVIDIA"', 'VKD3D_FILTER_DEVICE_NAME="NVIDIA"']
        else:
            env += ["DRI_PRIME=1", f"MESA_VK_DEVICE_SELECT={g.vid}:{g.did}"]
    if f.get("nvapi"):
        env += ["PROTON_ENABLE_NVAPI=1", "DXVK_ENABLE_NVAPI=1"]
    if f.get("dxr"):
        env.append("VKD3D_CONFIG=dxr")
    if f.get("nod3d12"):
        env.append("PROTON_NO_D3D12=1")
    if f.get("hud"):
        pre.append("mangohud")
    if f.get("gamemode"):
        pre.append("gamemoderun")
    return " ".join(env + pre + ["%command%"])


def tips_for(g: Gpu) -> str:
    base = (tr("Как применить: Steam → игра → Свойства → Параметры запуска → вставить строку.\n"
            "Для Proton выбирайте Proton 9+, Proton-GE или Proton Experimental."))
    fam = FAMILIES.get(g.fam)
    if g.vendor == "nvidia" and fam:
        extra = {
            "GP": tr("GTX 10xx: если игра не стартует на DX12 — переключите её на DX11 в настройках или включите «Принудительно DX11». "
                  "DLSS и RT на Pascal недоступны (нет RTX-ядер)."),
            "GM": tr("Maxwell: DX12 только ограниченно; при вылетах используйте «Принудительно DX11»."),
            "GK": tr("Kepler: DX12 невозможен. Для DX9–11 нужен старый DXVK ≤ 1.10.3 (Proton ≤ 6.x / Proton-GE 6.x)."),
            "GF": tr("Fermi: Vulkan отсутствует, Proton/DXVK работать не будут. Подойдут лишь OpenGL-игры и родной Linux."),
        }.get(g.fam, "")
        if g.rtx:
            extra = (tr("RTX: включайте NVAPI для DLSS; DXR (трассировка) — отдельной галочкой. "
                     "На ноутбуках с гибридной графикой обязательно запускайте игру через PRIME (галочка выше)."))
        return (extra + "\n\n" if extra else "") + base
    return base


COMPAT = {"open": ({"TU", "GA", "AD", "GB"}, set()),
          "580": ({"GM", "GP", "GV"}, {"TU", "GA", "AD", "GB"}),
          "470": ({"GK"}, set()),
          "390": ({"GF"}, set()),
          "none": ({"TESLA", ""}, {"GF", "GK", "GM", "GP", "GV", "TU", "GA", "AD", "GB"})}


def compat(g: Gpu, branch: str) -> str:
    """rec — рекомендуется, ok — работает, no — не подходит."""
    rec, ok = COMPAT[branch]
    return "rec" if g.fam in rec else "ok" if g.fam in ok else "no"


def branch_status(S: Sys, branch: str) -> tuple:
    """(текст, доступен ли для установки)."""
    if branch == "none":
        return tr("встроен в ядро"), True
    br = BRANCHES[branch]
    st = [S.avail.get(br["dkms"], ""), S.avail.get(br["utils"], "")]
    if all(st):
        if st[0] == "installed":
            return tr("установлен ({})", S.pkgs.get(br['dkms'], '')), True
        return (tr("в репозитории") if "repo" in st else tr("в офлайн-кэше")), True
    return tr("нет ни в репозиториях, ни в офлайн-кэше"), False


def build_branch_cmd(S: Sys, branch: str, o: dict) -> list:
    """Ручная установка выбранной ветки: чистим чужую, ставим свою, собираем DKMS."""
    br = BRANCHES[branch]
    rm = [p for p in foreign_pkgs(branch, S.pkgs) if p not in ("nvidia-utils", "lib32-nvidia-utils")]
    rm += [p for p in ("xf86-video-nouveau", "vulkan-nouveau", "lib32-vulkan-nouveau") if p in S.pkgs]
    want = [br["dkms"], br["utils"]]
    if br["lib32"] and S.multilib and o.get("b32", True):
        want.append(br["lib32"])
    if o.get("settings", True) and branch in ("open", "580"):
        want.append("nvidia-settings")
    if any(g.vendor != "nvidia" for g in S.gpus):
        want.append("nvidia-prime")
    want += ["dkms", headers_pkg(S.kernel)]
    repo, cache = [], []
    for p in dict.fromkeys(want):
        if p in S.pkgs:
            continue
        if S.avail.get(p) == "cache":
            cache.append(cached_pkg(p))
        else:
            repo.append(p)
    q = lambda xs: " ".join(shlex.quote(x) for x in xs)
    lines = []
    if rm:
        lines.append(f"pacman -Rns --noconfirm {q(rm)} || true")
    if cache:
        lines.append(f"yes | pacman -U --needed --overwrite '*' {q(cache)}")
    if repo:
        lines.append(f"yes | pacman -S --needed --overwrite '*' {q(repo)}")
    lines += ["mkdir -p /etc/modprobe.d",
              "[ -f /etc/modprobe.d/nvidia.conf ] || printf 'options nvidia_drm modeset=1\\n' > /etc/modprobe.d/nvidia.conf",
              "printf 'blacklist nouveau\\noptions nouveau modeset=0\\n' > /etc/modprobe.d/blacklist-nouveau.conf",
              "dkms autoinstall",
              "if command -v mkinitcpio >/dev/null 2>&1; then mkinitcpio -P; fi",
              tr("echo; echo 'Готово. Перезагрузите систему, чтобы загрузился новый драйвер.'")]
    return ["pkexec", "sh", "-c", "\n".join(lines)]


def build_cmd(kind: str, arg, o: dict):
    if kind == "raw":
        return arg
    if kind == "sync":
        a = list(arg or [])
        if o.get("b32", True):
            a.append("--32")
        if not o.get("settings", True):
            a.append("--no-settings")
        if o.get("nodkms"):
            a.append("--no-dkms")
        return ["pkexec", "sh", "-c", 'printf "y\\n" | pg-gpu-sync "$@"', "sh", *a]
    if kind == "pkgs":
        return ["pkexec", "pacman", "-S", "--needed", "--noconfirm", *arg]
    if kind == "dkms":
        return ["pkexec", "sh", "-c",
                "dkms autoinstall; if command -v mkinitcpio >/dev/null 2>&1; then mkinitcpio -P; fi"]
    return None


# ════════════════════════════════════════════════════════════════════════════
#  ВИДЖЕТЫ
# ════════════════════════════════════════════════════════════════════════════
def lvl_color(lvl: str) -> str:
    # цвета текущей темы — и в отдельном окне, и внутри «Настроек»
    return kit_qt.theme_color({"ok": "green", "warn": "yellow", "fail": "red"}.get(lvl, "subtext")).name()


def dot_icon(lvl: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(lvl_color(lvl)))
    p.drawEllipse(1, 1, 12, 12)
    p.end()
    return QIcon(pm)


def lvl_label(text: str, lvl: str, name: str = "chip") -> QLabel:
    lab = QLabel(text)
    lab.setObjectName(name)
    lab.setProperty("lvl", lvl)
    return lab


def clean_line(s: str) -> str:
    s = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)
    return s.split("\r")[-1] if "\r" in s else s


class RunDialog(QDialog):
    """Окно журнала: запускает команду и показывает вывод в реальном времени."""

    def __init__(self, parent, title: str, cmd: list):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 540)
        self.buf = ""
        self.running = True
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(10)
        head = QLabel(title)
        head.setObjectName("title")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(6000)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.status = QLabel(tr("Выполняется… Система попросит пароль администратора."))
        self.status.setObjectName("hint")
        self.btn = QPushButton(tr("Отмена"))
        self.btn.clicked.connect(self._click)
        row = QHBoxLayout()
        row.addWidget(self.status, 1)
        row.addWidget(self.btn)
        v.addWidget(head)
        v.addWidget(self.log, 1)
        v.addLayout(row)
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)
        self.log.appendPlainText("$ " + " ".join(shlex.quote(x) for x in cmd))
        self.proc.start(cmd[0], cmd[1:])

    def _emit(self, text: str, flush: bool = False) -> None:
        self.buf += text
        lines = self.buf.split("\n")
        self.buf = "" if flush else lines.pop()
        for ln in lines:
            ln = clean_line(ln)
            if ln.strip() or flush:
                self.log.appendPlainText(ln)

    def _read(self) -> None:
        self._emit(bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace"))

    def _finished(self, code, _status) -> None:
        self._emit(bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace"), flush=True)
        self.running = False
        self.btn.setText(tr("Закрыть"))
        if code == 0:
            self.status.setText(tr("Готово. Если менялся драйвер — перезагрузите систему."))
        elif code in (126, 127):
            self.status.setText(tr("Авторизация отклонена или pkexec недоступен (нужен polkit)."))
        else:
            self.status.setText(tr("Завершено с кодом {}. Подробности — в журнале выше.", code))

    def _error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self.running = False
            self.log.appendPlainText(tr("Не удалось запустить pkexec. Установите polkit."))
            self.btn.setText(tr("Закрыть"))
            self.status.setText(tr("Ошибка запуска."))

    def _click(self) -> None:
        if self.running:
            self.proc.terminate()
        else:
            self.accept()

    def reject(self) -> None:
        if self.running:
            self.proc.terminate()
            self.proc.waitForFinished(1500)
        super().reject()


class GpuPage(QTabWidget):
    def __init__(self, win, g: Gpu):
        super().__init__()
        self.win, self.g, self.S = win, g, win.S
        self.setDocumentMode(True)
        self.addTab(self._overview(), tr("Обзор"))
        self.addTab(self._diag(), tr("Диагностика ({})", sum(c.level in ('fail', 'warn') for c in g.checks)))
        if g.vendor == "nvidia":
            self.addTab(self._driver(), tr("Драйвер"))
        self.addTab(self._games(), tr("Игры"))

    # --- обзор
    def _overview(self) -> QWidget:
        g, S = self.g, self.S
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 12, 8, 12)
        v.setSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(8)
        for text, lvl in capabilities(g, S):
            row.addWidget(lvl_label(text, lvl))
        row.addStretch()
        v.addLayout(row)
        f, c = card(tr("Видеокарта"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(7)
        for i, (k, val) in enumerate(overview_rows(g, S)):
            kl = QLabel(k)
            kl.setObjectName("hint")
            vl = QLabel(val)
            vl.setWordWrap(True)
            vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(kl, i, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(vl, i, 1)
        grid.setColumnStretch(1, 1)
        c.addLayout(grid)
        v.addWidget(f)
        v.addStretch()
        return scrolled(body)

    # --- диагностика
    def _diag(self) -> QWidget:
        cs = sorted(self.g.checks, key=lambda c: LVL_ORDER[c.level])
        nf = sum(c.level == "fail" for c in cs)
        nw = sum(c.level == "warn" for c in cs)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 12, 8, 12)
        v.setSpacing(8)
        lvl = "fail" if nf else "warn" if nw else "ok"
        v.addWidget(lvl_label(tr("Проблем: {}   ·   предупреждений: {}", nf, nw) if (nf or nw) else tr("Всё в порядке"), lvl))
        for c in cs:
            v.addWidget(self._row(c))
        v.addStretch()
        return scrolled(body)

    def _row(self, c: Check) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        h = QHBoxLayout(f)
        h.setContentsMargins(16, 12, 14, 12)
        h.setSpacing(12)
        h.addWidget(lvl_label("●", c.level, "dot"), 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(c.title)
        t.setObjectName("rowname")
        t.setWordWrap(True)
        d = QLabel(c.detail)
        d.setObjectName("hint")
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        h.addLayout(col, 1)
        if c.fix:
            b = small_btn(c.fix[0])
            b.clicked.connect(lambda _=False, fx=c.fix: self.win.do_fix(fx))
            h.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        return f

    # --- драйвер (только NVIDIA)
    def _driver(self) -> QWidget:
        g, S, win = self.g, self.S, self.win
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 12, 8, 12)
        v.setSpacing(12)
        f, c = card(tr("Рекомендуемый драйвер"))
        big = QLabel(BRANCHES[g.branch]["label"])
        big.setObjectName("out")
        why = QLabel(WHY[g.branch])
        why.setObjectName("hint")
        why.setWordWrap(True)
        c.addWidget(big)
        c.addWidget(why)
        if sum(o.vendor == "nvidia" for o in S.gpus) > 1:
            n = QLabel(tr("В системе несколько карт NVIDIA: pg-gpu-sync выбирает драйвер по первой из них."))
            n.setObjectName("hint")
            n.setWordWrap(True)
            c.addWidget(n)
        if not shutil.which("pg-gpu-sync"):
            c.addWidget(lvl_label(tr("pg-gpu-sync не установлен — кнопки ниже недоступны"), "fail"))
            b = small_btn(tr("Установить pg-gpu-sync"))
            b.clicked.connect(lambda: win.do_fix((tr("Установка pg-gpu-sync"), "pkgs", ["pg-gpu-sync"])))
            c.addWidget(b)
        v.addWidget(f)

        f4, c4 = card(tr("Выбор драйвера"))
        h4 = QLabel(tr("Выберите ветку драйвера для этой карты. Зелёная точка — рекомендуется, жёлтая — "
                    "работает, но не оптимальна, красная — не подходит."))
        h4.setObjectName("hint")
        h4.setWordWrap(True)
        c4.addWidget(h4)
        order = ["open", "580", "470", "390", "none"]
        lst = QListWidget()
        lst.setIconSize(QSize(14, 14))
        lst.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lst.setWordWrap(True)
        lst.setFixedHeight(len(order) * 98 + 8)
        tags = {"rec": tr("рекомендуется для вашей карты"), "ok": tr("совместим с вашей картой"),
                "no": tr("не подходит для вашей карты")}
        for b in order:
            cm = compat(g, b)
            it = QListWidgetItem(dot_icon({"rec": "ok", "ok": "warn", "no": "fail"}[cm]),
                                 tr("{}\nПодходит для: {}\n{} · {}", BRANCHES[b]['label'], BRANCH_GPUS[b], tags[cm], branch_status(S, b)[0]))
            it.setData(Qt.ItemDataRole.UserRole, b)
            it.setSizeHint(QSize(0, 92))
            lst.addItem(it)
        lst.setCurrentRow(order.index(g.branch))
        c4.addWidget(lst)
        pick_btn = QPushButton(tr("Установить выбранный драйвер"))
        pick_btn.setObjectName("primary")
        pick_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        def pick():
            it = lst.currentItem()
            if not it:
                return
            b = it.data(Qt.ItemDataRole.UserRole)
            label = BRANCHES[b]["label"]
            text, ok = branch_status(S, b)
            if not ok:
                QMessageBox.warning(win, tr("Драйвер недоступен"),
                                    tr("{}: {}.\nДобавьте пакеты в репозиторий или положите их в {}/.", label, text, DRIVER_CACHE))
                return
            if compat(g, b) == "no" and QMessageBox.question(
                    win, tr("Драйвер не подходит"),
                    tr("{} не рекомендован для {}. Возможны чёрный экран и kernel panic.\nВсё равно установить?", label, g.fam_name or g.name)) != QMessageBox.StandardButton.Yes:
                return
            if b == "none":
                win.do_fix((tr("Переключение на nouveau"), "sync", ["--nouveau"]))
            elif b == g.branch:
                win.do_fix(SYNC)
            else:
                win.do_fix((tr("Установка {}", label), "raw", build_branch_cmd(S, b, win.opts)))

        pick_btn.clicked.connect(pick)
        c4.addWidget(pick_btn)
        v.addWidget(f4)

        f2, c2 = card(tr("Параметры установки"))
        for key, text in (("b32", tr("32-битные библиотеки (Steam, Proton, Wine) — --32")),
                          ("settings", tr("Панель nvidia-settings")),
                          ("nodkms", tr("Без DKMS: пакет nvidia-open (только ядра linux / linux-lts)"))):
            cb = QCheckBox(text)
            cb.setChecked(win.opts[key])
            cb.toggled.connect(lambda on, k=key: win.opts.__setitem__(k, on))
            c2.addWidget(cb)
        v.addWidget(f2)

        f3, c3 = card(tr("Действия"))
        grid = QGridLayout()
        grid.setSpacing(8)
        have = bool(shutil.which("pg-gpu-sync"))
        acts = [(tr("Установить / исправить драйвер"), "sync", [], "pg-gpu-sync", True),
                (tr("Показать план (dry run)"), "sync", ["--test"], "pg-gpu-sync --test", False),
                (tr("Пересобрать DKMS и initramfs"), "dkms", [], "dkms autoinstall && mkinitcpio -P", False),
                (tr("Переключиться на nouveau"), "sync", ["--nouveau"], "pg-gpu-sync --nouveau", False),
                (tr("Вернуться к автоподбору"), "sync", ["--reset-mode"], "pg-gpu-sync --reset-mode", False)]
        for i, (text, kind, arg, tip, primary) in enumerate(acts):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(tip)
            if primary:
                b.setObjectName("primary")
            b.setEnabled(have or kind != "sync")
            b.clicked.connect(lambda _=False, a=(text, kind, arg): win.do_fix(a))
            grid.addWidget(b, i // 2, i % 2)
        c3.addLayout(grid)
        note = QLabel(tr("Установка идёт через pkexec (запросит пароль). После смены драйвера перезагрузите систему."))
        note.setObjectName("hint")
        note.setWordWrap(True)
        c3.addWidget(note)
        v.addWidget(f3)
        v.addStretch()
        return scrolled(body)

    # --- игры
    def _games(self) -> QWidget:
        g, S = self.g, self.S
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 12, 8, 12)
        v.setSpacing(12)
        f, c = card(tr("Параметры запуска Steam"))
        out = QLineEdit()
        out.setReadOnly(True)
        out.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        nv = g.vendor == "nvidia"
        specs = [("prime", tr("Запускать игру на этой карте (гибридная графика / PRIME)"), len(S.gpus) > 1, len(S.gpus) > 1),
                 ("nvapi", tr("NVAPI + DLSS (только RTX)"), nv and g.rtx, nv and g.rtx),
                 ("dxr", tr("Трассировка лучей DX12 — VKD3D_CONFIG=dxr (только RTX)"), nv and g.rtx, False),
                 ("nod3d12", tr("Принудительно DX11 — PROTON_NO_D3D12=1 (если DX12 не стартует)"), True, False),
                 ("hud", tr("MangoHud (оверлей FPS)"), bool(shutil.which("mangohud")), False),
                 ("gamemode", "GameMode", bool(shutil.which("gamemoderun")), False)]
        boxes = {}

        def update():
            out.setText(launch_options(g, S, {k: b.isChecked() for k, b in boxes.items()}))

        for key, text, enabled, checked in specs:
            cb = QCheckBox(text)
            cb.setEnabled(bool(enabled))
            cb.setChecked(bool(enabled and checked))
            cb.toggled.connect(lambda _=False: update())
            boxes[key] = cb
            c.addWidget(cb)
        c.addWidget(out)
        cp = QPushButton(tr("Копировать"))
        cp.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        def copy():
            QGuiApplication.clipboard().setText(out.text())
            cp.setText(tr("Скопировано ✓"))
            QTimer.singleShot(1500, lambda: cp.setText(tr("Копировать")))

        cp.clicked.connect(copy)
        c.addWidget(cp)
        v.addWidget(f)
        f2, c2 = card(tr("Подсказки"))
        t = QLabel(tips_for(g))
        t.setObjectName("hint")
        t.setWordWrap(True)
        c2.addWidget(t)
        v.addWidget(f2)
        v.addStretch()
        update()
        return scrolled(body)


# ════════════════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ════════════════════════════════════════════════════════════════════════════
class GpuPanel(QWidget):
    """Содержимое менеджера: список видеокарт слева, страница выбранной справа,
    действия с драйвером. Один и тот же виджет — в отдельном окне Equestria GPU
    и в «Настройки → Видеокарта».

    embedded=True — внутри чужого окна: стиль ставится только на сам виджет
    (на приложение его ставит хозяин окна), как у остальных модулей «Настроек»."""
    scanned = pyqtSignal(object)

    def __init__(self, embedded: bool = False, parent=None):
        super().__init__(parent)
        self.opts = {"b32": True, "settings": True, "nodkms": False}
        self.S = Sys()
        self._scanning = False
        root = QHBoxLayout(self)
        root.setContentsMargins(*((0, 8, 0, 0) if embedded else (18, 16, 18, 16)))
        root.setSpacing(16)

        side = QVBoxLayout()
        side.setSpacing(8)
        if not embedded:
            title = QLabel("Equestria GPU")
            title.setObjectName("title")
            sub = QLabel(tr("Менеджер драйверов видеокарт"))
            sub.setObjectName("hint")
            side.addWidget(title)
            side.addWidget(sub)
        self.list = QListWidget()
        self.list.setIconSize(QSize(14, 14))
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.currentRowChanged.connect(self._select)
        self.sys_label = QLabel("")
        self.sys_label.setObjectName("hint")
        self.sys_label.setWordWrap(True)
        self.buttons = QHBoxLayout()
        self.refresh_btn = small_btn(tr("Обновить"))
        self.refresh_btn.clicked.connect(self.refresh)
        self.buttons.addWidget(self.refresh_btn)
        side.addWidget(self.list, 1)
        side.addWidget(self.sys_label)
        side.addLayout(self.buttons)
        sw = QWidget()
        sw.setLayout(side)
        sw.setFixedWidth(280 if embedded else 300)
        root.addWidget(sw)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        if embedded:
            kit_qt.style(self, QSS)
            # значки состояния нарисованы в цветах темы — перерисовать при её смене;
            # слабая ссылка: удалённая панель просто пропускается
            ref = weakref.ref(self)

            def _theme_changed(_theme):
                w = ref()
                if w is not None and not sip.isdeleted(w) and w.S.gpus:
                    w.rebuild()
            kit_qt.on_theme_change(_theme_changed)
        self.scanned.connect(self._scan_done)
        self.refresh()

    # --- данные: опрос системы занимает секунды (vulkaninfo до 25 с) — в фоне
    def refresh(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self.refresh_btn.setEnabled(False)
        self.sys_label.setText(tr("Опрашиваю видеокарты…"))
        if not self.S.gpus:
            self._show_message(tr("Опрашиваю видеокарты…"))
        threading.Thread(target=lambda: self.scanned.emit(probe_system()), daemon=True).start()

    def _scan_done(self, S) -> None:
        self._scanning = False
        self.refresh_btn.setEnabled(True)
        self.S = S
        self.rebuild()

    def _show_message(self, text: str) -> None:
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()
        msg = QLabel(text)
        msg.setObjectName("hint")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(msg)

    def rebuild(self) -> None:
        keep = max(0, self.list.currentRow())
        self.list.blockSignals(True)
        self.list.clear()
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()
        S = self.S
        if not S.gpus:
            self._show_message(tr("Видеокарты не найдены.\nУстановите пакет pciutils (lspci) и нажмите «Обновить»."))
        for g in S.gpus:
            sub = g.fam_name or VENDOR_LABEL[g.vendor]
            it = QListWidgetItem(dot_icon(g.worst), f"{g.name}\n{sub}")
            it.setSizeHint(QSize(0, 58))
            self.list.addItem(it)
            self.stack.addWidget(GpuPage(self, g))
        self.sys_label.setText(tr("Ядро {} · сессия {}", S.kernel, S.session)
                               + ("" if shutil.which("pg-gpu-sync") else tr("\npg-gpu-sync не найден")))
        self.list.blockSignals(False)
        if S.gpus:
            self.list.setCurrentRow(min(keep, len(S.gpus) - 1))
            self.stack.setCurrentIndex(self.list.currentRow())

    def _select(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    # --- действия
    def do_fix(self, fix: tuple) -> None:
        label, kind, arg = fix
        if kind == "sync" and not shutil.which("pg-gpu-sync"):
            QMessageBox.information(self, tr("pg-gpu-sync не найден"),
                                    tr("Установите пакет pg-gpu-sync (sudo pacman -S pg-gpu-sync) и повторите."))
            return
        cmd = build_cmd(kind, arg, self.opts)
        if not cmd:
            return
        RunDialog(self, label, cmd).exec()
        self.refresh()


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.theme = cfg["theme"]
        self.setWindowTitle("Equestria GPU")
        self.setMinimumSize(980, 640)
        self.resize(1120, 760)
        self.panel = GpuPanel()
        theme_btn = small_btn(tr("Тема"))
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        self.panel.buttons.addWidget(theme_btn)
        self.setCentralWidget(self.panel)

    # --- тема
    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = self.cfg["theme"] = apply_theme(name)
        self.panel.rebuild()
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria GPU")
    app.setDesktopFileName("equestria-gpu")
    app.setStyle("Fusion")
    cfg = {"theme": DEFAULT_THEME}
    try:
        raw = json.loads(CONFIG.read_text(encoding="utf-8"))
        if isinstance(raw.get("theme"), str):
            cfg["theme"] = raw["theme"]
    except Exception:
        pass
    cfg["theme"] = apply_theme(kit_themes.current_name())
    win = MainWindow(cfg)
    kit_themes.follow(win._set_theme, lambda: win.theme)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())