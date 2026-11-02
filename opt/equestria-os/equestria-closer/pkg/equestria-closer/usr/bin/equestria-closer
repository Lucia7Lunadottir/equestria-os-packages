#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Equestria Closer — найти окно, закрыть его, закрыть принудительно или убить всё дерево процессов (PyQt6).

• Режим «Приложения» — программы с графикой (в т.ч. Python/PyQt), как в системном мониторе.
  Подписи понятные: у Unity — папка проекта, у Python — имя скрипта.
• Клик по пункту выводит его окно вперёд (Hyprland, Sway, X11; KDE Wayland — через kdotool).
• Список окон: Hyprland (hyprctl), Sway (swaymsg), X11 (wmctrl или xprop).
  В GNOME/KDE на Wayland видны только окна XWayland — для остального есть «Приложения» и «Все процессы».
• «Выбрать окно»: на X11 — кликом по окну; на Wayland — берёт активное окно через 3 секунды.
• «Закрыть» — вежливо (как крестик). «Принудительно» — сразу убить процесс.
  Кнопка «Включая дерево процессов» применяет действие ко всем дочерним процессам.
"""
from __future__ import annotations

import json
from abc import ABC
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, Qt, QTimer, pyqtClassInfo, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                             QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit.widgets import load_typed_config, small_btn
from equestria_kit import themes as kit_themes
from equestria_kit import i18n as kit_i18n

tr = kit_i18n.install("equestria-closer", __file__)

try:
    from PyQt6.QtDBus import QDBusConnection, QDBusInterface
    HAVE_DBUS = True
except ImportError:  # без QtDBus KDE-режим просто недоступен
    HAVE_DBUS = False

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-closer" / "settings.json"

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
QMainWindow, QDialog, QMessageBox { background: @base@; }
QWidget { color: @text@; font-size: 15px; }
QLabel { background: transparent; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#h2 { color: @accent@; font-size: 14px; font-weight: 700; }
QLabel#out { font-size: 18px; font-weight: 700; }
QPushButton { background: @surface0@; border: none; border-radius: 10px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @base@; }
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#primary:disabled { background: @surface1@; color: @surface2@; }
QPushButton#danger { background: @red@; color: @base@; }
QPushButton#danger:hover { background: @red_hover@; }
QPushButton#danger:disabled { background: @surface1@; color: @surface2@; }
QPushButton#small { padding: 6px 12px; font-size: 13px; border-radius: 9px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QLineEdit { background: @surface0@; border: 2px solid transparent; border-radius: 9px;
    padding: 7px 10px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { background: @surface0@; border-radius: 9px; padding: 7px 12px; margin: 2px 0; }
QListWidget::item:hover { background: @surface1@; }
QListWidget::item:selected { background: @surface2@; color: @text@; }
QTreeWidget { background: @mantle@; border: none; border-radius: 10px; padding: 4px; outline: 0; }
QTreeWidget::item { padding: 3px 2px; border-radius: 6px; }
QTreeWidget::item:selected { background: @surface1@; color: @text@; }
QHeaderView::section { background: @surface0@; color: @subtext@; border: none; padding: 5px 8px; font-size: 13px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: @surface1@; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
QToolTip { background: @surface1@; color: @text@; border: none; padding: 4px 8px; }
"""


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME, extras=lambda t: {"red_hover": QColor(t["red"]).lighter(112).name()})


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)


# ════════════════════════════════════════════════════════════════════════════
#  ПРОЦЕССЫ (/proc)
# ════════════════════════════════════════════════════════════════════════════
def scan_procs() -> dict:
    """pid -> {pid, name, state, ppid, uid} для всех процессов."""
    procs: dict = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            uid = os.stat(f"/proc/{entry}").st_uid
            with open(f"/proc/{entry}/stat", "rb") as f:
                raw = f.read().decode(errors="replace")
        except OSError:
            continue
        l, r = raw.find("("), raw.rfind(")")
        rest = raw[r + 2:].split() if r > 0 else []
        if l < 0 or len(rest) < 2:
            continue
        pid = int(entry)
        start = rest[19] if len(rest) > 19 else "0"
        procs[pid] = {"pid": pid, "name": raw[l + 1:r], "state": rest[0], "ppid": int(rest[1]),
                      "uid": uid, "start": start}
    return procs


_GUI_CACHE: dict = {}
_GUI_LIBS = (b"libwayland-client", b"libxcb.so", b"libX11.so")


def is_gui(p: dict) -> bool:
    """Есть ли у процесса графика: подгружены библиотеки Wayland/X11 (как «приложения» в системном мониторе)."""
    key = (p["pid"], p["start"])
    if key not in _GUI_CACHE:
        found = False
        try:
            with open(f"/proc/{p['pid']}/maps", "rb") as f:
                data = f.read()
            found = any(lib in data for lib in _GUI_LIBS)
        except OSError:
            pass
        _GUI_CACHE[key] = found
    return _GUI_CACHE[key]


def prune_gui_cache(procs: dict) -> None:
    alive = {(p["pid"], p["start"]) for p in procs.values()}
    for k in [k for k in _GUI_CACHE if k not in alive]:
        del _GUI_CACHE[k]


def cmd_args(pid: int) -> list:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
    except OSError:
        return []


def app_label(name: str, args: list) -> str:
    """Понятное имя: для Unity — папка проекта, для Python — имя скрипта."""
    low = [a.lower() for a in args]
    if "-projectpath" in low and low.index("-projectpath") + 1 < len(args):
        proj = os.path.basename(args[low.index("-projectpath") + 1].rstrip("/"))
        return f"{name} — {proj}"
    if re.fullmatch(r"python[\d.]*", name.lower()) and len(args) > 1:
        rest = args[1:]
        if rest[0] == "-m" and len(rest) > 1:
            return f"{rest[1]} (python)"
        for a in rest:
            if not a.startswith("-"):
                return f"{os.path.basename(a)} (python)"
    return name


def proc_cwd(pid: int) -> str:
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return ""


STATE_MARK = {"Z": tr(" ⚠ зомби"), "D": tr(" ⚠ завис (D)"), "T": tr(" ⚠ остановлен")}


def cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode(errors="replace").strip()
    except OSError:
        return ""


def tree_pids(root: int, procs: dict) -> list:
    """Сам процесс и все его потомки (родитель всегда раньше детей)."""
    kids: dict = {}
    for p in procs.values():
        kids.setdefault(p["ppid"], []).append(p["pid"])
    order, seen, i = [root], {root}, 0
    while i < len(order):
        for c in sorted(kids.get(order[i], [])):
            if c not in seen:
                seen.add(c)
                order.append(c)
        i += 1
    return order


def send_signal(pids: list, sig: int):
    """Шлёт сигнал, начиная с самых дальних потомков. Возвращает (сколько отправлено, [pid без прав])."""
    ok, denied = 0, []
    for pid in reversed(pids):
        try:
            os.kill(pid, sig)
            ok += 1
        except ProcessLookupError:
            pass
        except PermissionError:
            denied.append(pid)
    return ok, denied


# ════════════════════════════════════════════════════════════════════════════
#  ОКНА (по бэкендам)
# ════════════════════════════════════════════════════════════════════════════
def run(cmd: list, timeout: float = 2.0):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout
    except (OSError, subprocess.SubprocessError):
        return False, ""


def kde_available() -> bool:
    """KDE Plasma с запущенным KWin (работает и на Wayland, и на X11)."""
    if not HAVE_DBUS or "KDE" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        return False
    try:
        bus = QDBusConnection.sessionBus()
        r = bus.interface().isServiceRegistered("org.kde.KWin")
        return bool(r.value() if hasattr(r, "value") else r)
    except Exception:
        return False


# Чем закончилась попытка показать окно (сообщение для каждого случая выбирает окно программы)
REVEAL_SHOWN, REVEAL_FAILED, REVEAL_INVISIBLE, REVEAL_NO_REPLY, REVEAL_NO_WINDOW = range(5)


class WindowBackend(ABC):
    """Как программа видит окна и управляет ими в данной графической среде.
    Новая среда = новый класс в BACKENDS; MainWindow при этом не меняется."""
    id = "none"

    @classmethod
    def available(cls) -> bool:
        return False

    def label(self) -> str:
        return tr("Список окон недоступен (нужен hyprctl, swaymsg, wmctrl или xprop) — используйте «Процессы»")

    def list_windows(self) -> list:
        """Список окон: dict(wid, title, cls, pid, ws)."""
        return []

    def active_window(self):
        """wid активного окна или None."""
        return None

    def close_window(self, wid) -> bool:
        """Вежливая просьба закрыть окно (как нажатие на крестик)."""
        return False

    def focus_window(self, wid) -> bool:
        return False

    def pid_of(self, wid):
        """PID окна, если среда умеет узнать его по wid (иначе None)."""
        return None

    def can_pick_by_click(self) -> bool:
        return False

    def reveal_window(self, wid=None, pid=None) -> bool:
        """Вывести окно на передний план, чтобы увидеть, что это за программа."""
        if wid is not None and self.focus_window(wid):
            return True
        if pid and shutil.which("kdotool"):  # KDE Wayland
            ok, out = run(["kdotool", "search", "--pid", str(pid)])
            ids = out.split()
            if ids:
                return run(["kdotool", "windowactivate", ids[0]])[0]
        return False

    @staticmethod
    def _filter(res: list) -> list:
        return [w for w in res if w["title"] or w["cls"]]

    # --- то, чем пользуется окно программы. Ответ всегда приходит в cb: у большинства
    # сред сразу, у KDE — позже (скрипты KWin отвечают по D-Bus). Окну не нужно знать, какая среда.
    has_windows = True

    def ready(self) -> bool:
        """Среда найдена, но может не подключиться (KDE без D-Bus) — тогда берём следующую."""
        return True

    def request_windows(self, cb) -> None:
        """cb(список окон) или cb(None), если среда не ответила."""
        cb(self.list_windows())

    def request_active(self, cb) -> None:
        """cb({wid, pid}) активного окна или cb(None)."""
        wid = self.active_window()
        cb({"wid": wid, "pid": None} if wid is not None else None)

    def request_close(self, wid, cb) -> None:
        """cb(True), если окну удалось отправить просьбу закрыться."""
        cb(self.close_window(wid))

    def request_reveal(self, wid, pid, tree: list, windows: list, cb) -> None:
        """Показать окно программы; tree — её процесс с потомками ([] — процесса уже нет).
        cb(один из REVEAL_*)."""
        if wid is None and tree:  # окно могло принадлежать дочернему процессу
            own = set(tree)
            wid = next((w["wid"] for w in windows if w["pid"] in own), None)
        if self.reveal_window(wid, pid):
            cb(REVEAL_SHOWN)
        else:
            cb(REVEAL_FAILED if wid is not None else REVEAL_INVISIBLE)


class NoBackend(WindowBackend):
    """Окна недоступны — остаётся вкладка «Процессы»."""
    has_windows = False


class HyprlandBackend(WindowBackend):
    id = "hyprland"

    @classmethod
    def available(cls) -> bool:
        return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"))

    def label(self) -> str:
        return tr("Окна: Hyprland (hyprctl)")

    def list_windows(self) -> list:
        res = []
        try:
            ok, out = run(["hyprctl", "clients", "-j"])
            for c in json.loads(out or "[]"):
                if not c.get("mapped", True):
                    continue
                res.append({"wid": c["address"], "title": c.get("title") or "", "cls": c.get("class") or "",
                            "pid": c.get("pid") or None, "ws": str((c.get("workspace") or {}).get("name", ""))})
        except (ValueError, KeyError, TypeError):
            pass
        return self._filter(res)

    def active_window(self):
        try:
            ok, out = run(["hyprctl", "activewindow", "-j"])
            return (json.loads(out or "{}") or {}).get("address") or None
        except (ValueError, KeyError, TypeError):
            return None

    def close_window(self, wid) -> bool:
        return run(["hyprctl", "dispatch", "closewindow", f"address:{wid}"])[0]

    def focus_window(self, wid) -> bool:
        return run(["hyprctl", "dispatch", "focuswindow", f"address:{wid}"])[0]


class SwayBackend(WindowBackend):
    id = "sway"

    @classmethod
    def available(cls) -> bool:
        return bool(os.environ.get("SWAYSOCK") and shutil.which("swaymsg"))

    def label(self) -> str:
        return tr("Окна: Sway (swaymsg)")

    @staticmethod
    def _tree() -> dict:
        ok, out = run(["swaymsg", "-t", "get_tree"])
        return json.loads(out) if out else {}

    @staticmethod
    def _walk(n: dict, visit) -> None:
        visit(n)
        for ch in n.get("nodes", []) + n.get("floating_nodes", []):
            SwayBackend._walk(ch, visit)

    def list_windows(self) -> list:
        res = []

        def visit(n):
            if n.get("pid") and n.get("type") in ("con", "floating_con") and not n.get("nodes"):
                cls = n.get("app_id") or (n.get("window_properties") or {}).get("class") or ""
                res.append({"wid": n["id"], "title": n.get("name") or "", "cls": cls, "pid": n["pid"], "ws": ""})
        try:
            self._walk(self._tree(), visit)
        except (ValueError, KeyError, TypeError):
            pass
        return self._filter(res)

    def active_window(self):
        found = []
        try:
            self._walk(self._tree(), lambda n: found.append(n["id"]) if n.get("focused") and n.get("pid") else None)
        except (ValueError, KeyError, TypeError):
            return None
        return found[0] if found else None

    def close_window(self, wid) -> bool:
        return run(["swaymsg", f"[con_id={wid}] kill"])[0]

    def focus_window(self, wid) -> bool:
        return run(["swaymsg", f"[con_id={wid}] focus"])[0]


class X11Backend(WindowBackend):
    """X11 (и окна XWayland): wmctrl, а без него — xprop (закрытие тогда сигналом)."""
    id = "x11"

    @classmethod
    def available(cls) -> bool:
        return bool(os.environ.get("DISPLAY") and (shutil.which("wmctrl") or shutil.which("xprop")))

    def label(self) -> str:
        txt = tr("Окна: X11 (wmctrl)") if shutil.which("wmctrl") else tr("Окна: X11 (xprop, закрытие сигналом)")
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            txt += tr(" — видны только окна XWayland, остальные ищите в «Процессах»")
        return txt

    @staticmethod
    def props(wid: int) -> dict:
        ok, out = run(["xprop", "-id", f"0x{wid:x}", "_NET_WM_PID", "WM_CLASS", "_NET_WM_NAME", "WM_NAME"])
        pid, cls, title = None, "", ""
        for line in out.splitlines():
            if line.startswith("_NET_WM_PID"):
                m = re.search(r"=\s*(\d+)", line)
                pid = int(m.group(1)) if m else None
            elif line.startswith("WM_CLASS"):
                parts = re.findall(r'"([^"]*)"', line)
                cls = parts[-1] if parts else ""
            elif line.startswith("_NET_WM_NAME") or (line.startswith("WM_NAME") and not title):
                m = re.search(r'=\s*"(.*)"', line)
                if m:
                    title = m.group(1)
        return {"pid": pid, "cls": cls, "title": title}

    def list_windows(self) -> list:
        res = []
        try:
            if shutil.which("wmctrl"):
                ok, out = run(["wmctrl", "-lpx"])
                for line in out.splitlines():
                    parts = line.split(None, 4)
                    if len(parts) < 5:
                        continue
                    wid, _desk, pid, cls, rest = parts
                    ht = rest.split(None, 1)
                    pid = int(pid)
                    res.append({"wid": int(wid, 16), "title": ht[1] if len(ht) > 1 else "",
                                "cls": cls.split(".")[-1], "pid": pid if pid > 0 else None, "ws": ""})
            else:
                ok, out = run(["xprop", "-root", "_NET_CLIENT_LIST"])
                for h in re.findall(r"0x[0-9a-fA-F]+", out):
                    wid = int(h, 16)
                    pr = self.props(wid)
                    res.append({"wid": wid, "title": pr["title"], "cls": pr["cls"], "pid": pr["pid"], "ws": ""})
        except (ValueError, KeyError, TypeError):
            pass
        return self._filter(res)

    def active_window(self):
        try:
            if shutil.which("xprop"):
                ok, out = run(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
                m = re.search(r"0x[0-9a-fA-F]+", out)
                wid = int(m.group(0), 16) if m else 0
            elif shutil.which("xdotool"):
                ok, out = run(["xdotool", "getactivewindow"])
                wid = int(out.strip()) if out.strip().isdigit() else 0
            else:
                wid = 0
            return wid or None
        except (ValueError, KeyError, TypeError):
            return None

    def close_window(self, wid) -> bool:
        return bool(shutil.which("wmctrl")) and run(["wmctrl", "-ic", f"0x{wid:08x}"])[0]

    def focus_window(self, wid) -> bool:
        return bool(shutil.which("wmctrl")) and run(["wmctrl", "-ia", f"0x{wid:08x}"])[0]

    def pid_of(self, wid):
        return self.props(wid)["pid"] if shutil.which("xprop") else None

    def can_pick_by_click(self) -> bool:
        return bool(shutil.which("xdotool") or shutil.which("xwininfo"))


# --- KDE Plasma: временные скрипты KWin отвечают нам по D-Bus (работает и на Wayland)
KWIN_JS = r'''
(function () {
  var REQ = __REQ__;
  function all() { return workspace.windowList ? workspace.windowList() : workspace.clientList(); }
  function cur() { return workspace.activeWindow !== undefined ? workspace.activeWindow : workspace.activeClient; }
  function info(w) { return {id: String(w.internalId), pid: w.pid, title: String(w.caption), cls: String(w.resourceClass)}; }
  var out = {req: REQ.req, op: REQ.op, ok: false};
  var list = all();
  if (REQ.op === "list") {
    out.windows = [];
    for (var i = 0; i < list.length; i++) { if (list[i].normalWindow) out.windows.push(info(list[i])); }
    out.ok = true;
  } else if (REQ.op === "active") {
    var a = cur();
    if (a) { out.win = info(a); out.ok = true; }
  } else {
    var hit = null;
    for (var j = 0; j < list.length && !hit; j++) {
      if (REQ.id && String(list[j].internalId) === REQ.id) hit = list[j];
    }
    for (var k = 0; k < list.length && !hit && REQ.pids; k++) {
      if (list[k].normalWindow && list[k].pid > 0 && REQ.pids.indexOf(list[k].pid) >= 0) hit = list[k];
    }
    if (hit) {
      if (REQ.op === "activate") {
        hit.minimized = false;
        if (workspace.activeWindow !== undefined) workspace.activeWindow = hit; else workspace.activeClient = hit;
        out.ok = true; out.win = info(hit);
      } else if (REQ.op === "close") { hit.closeWindow(); out.ok = true; }
    }
  }
  callDBus(REQ.svc, "/Closer", "org.equestria.Closer", "report", JSON.stringify(out));
})();
'''

if HAVE_DBUS:
    @pyqtClassInfo("D-Bus Interface", "org.equestria.Closer")
    class _Receiver(QObject):
        """Принимает ответы от скриптов KWin по D-Bus."""
        got = pyqtSignal(str)

        @pyqtSlot(str)
        def report(self, payload: str) -> None:
            self.got.emit(payload)


class KWinBridge(QObject):
    """Управление окнами KDE через временные скрипты KWin (без сторонних программ, работает на Wayland)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pending: dict = {}
        self.n = 0
        self.svc = f"org.equestria.Closer.p{os.getpid()}"
        self.bus = QDBusConnection.sessionBus()
        self.recv = _Receiver(self)
        self.recv.got.connect(self._got)
        self.ok = bool(self.bus.registerService(self.svc)
                       and self.bus.registerObject("/Closer", self.recv,
                                                   QDBusConnection.RegisterOption.ExportAllSlots))

    def _scripting(self):
        return QDBusInterface("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", self.bus)

    def request(self, op: str, cb, **params) -> None:
        """Асинхронно: cb(ответ_dict) или cb(None), если не вышло."""
        if not self.ok:
            cb(None)
            return
        self.n += 1
        req = self.n
        name = f"eqcloser_{os.getpid()}_{req}"
        path = Path(tempfile.gettempdir()) / f"{name}.js"
        body = KWIN_JS.replace("__REQ__", json.dumps({"req": req, "op": op, "svc": self.svc, **params}))
        try:
            path.write_text(body, encoding="utf-8")
        except OSError:
            cb(None)
            return
        reply = self._scripting().call("loadScript", str(path), name)
        args = reply.arguments()
        sid = args[0] if args else None
        started = False
        if isinstance(sid, int) and sid >= 0:
            for obj in (f"/Scripting/Script{sid}", f"/{sid}"):  # Plasma 6 / Plasma 5
                s = QDBusInterface("org.kde.KWin", obj, "org.kde.kwin.Script", self.bus)
                if s.isValid():
                    s.call("run")
                    started = True
                    break
        self.pending[req] = (cb, name, path)
        if started:
            QTimer.singleShot(4000, lambda r=req: self._finish(r, None))
        else:
            self._finish(req, None)

    def _got(self, payload: str) -> None:
        try:
            data = json.loads(payload)
            self._finish(data.get("req"), data)
        except (ValueError, AttributeError):
            pass

    def _finish(self, req, data) -> None:
        item = self.pending.pop(req, None)
        if not item:
            return
        cb, name, path = item
        self._scripting().call("unloadScript", name)
        try:
            path.unlink()
        except OSError:
            pass
        cb(data)


class KdeBackend(WindowBackend):
    """KDE Plasma: окна через скрипты KWin (KWinBridge) — ответы приходят асинхронно."""
    id = "kde"

    def __init__(self):
        self.bridge = KWinBridge()

    @classmethod
    def available(cls) -> bool:
        return kde_available()

    def ready(self) -> bool:
        return self.bridge.ok

    def label(self) -> str:
        return tr("Окна: KDE Plasma (скрипты KWin)")

    def request_windows(self, cb) -> None:
        def got(d) -> None:
            if not d or not d.get("ok"):
                cb(None)
                return
            cb([{"wid": w["id"], "title": w["title"], "cls": w["cls"],
                 "pid": w["pid"] if w["pid"] > 0 else None, "ws": ""} for w in d["windows"]])
        self.bridge.request("list", got)

    def request_active(self, cb) -> None:
        def got(d) -> None:
            w = d.get("win") if d and d.get("ok") else None
            cb({"wid": w["id"], "pid": w["pid"] if w["pid"] > 0 else None} if w else None)
        self.bridge.request("active", got)

    def request_close(self, wid, cb) -> None:
        self.bridge.request("close", lambda r: cb(bool(r and r.get("ok"))), id=str(wid))

    def request_reveal(self, wid, pid, tree: list, windows: list, cb) -> None:
        def got(r) -> None:
            if r and r.get("ok"):
                cb(REVEAL_SHOWN)
            else:
                cb(REVEAL_NO_REPLY if r is None else REVEAL_NO_WINDOW)
        self.bridge.request("activate", got, pids=tree or ([pid] if pid else []), id=str(wid) if wid else "")


# Порядок = приоритет, если доступно несколько сред.
BACKENDS = (HyprlandBackend, SwayBackend, KdeBackend, X11Backend)


def detect_backend() -> WindowBackend:
    for cls in BACKENDS:
        if cls.available():
            backend = cls()
            if backend.ready():
                return backend
    return NoBackend()


# ════════════════════════════════════════════════════════════════════════════
#  СПИСОК: что показывать в каждом режиме
# ════════════════════════════════════════════════════════════════════════════
MODES = ("apps", "windows", "procs")


def build_entries(mode: str, procs: dict, windows: list) -> list:
    """Пункты списка для режима «Приложения» / «Окна» / «Все процессы».
    Пункт: key, title, cls, pid, wid, cmd, label, text (+ wtitles — заголовки окон программы)."""
    if mode == "windows":
        return [_window_entry(w) for w in sorted(windows, key=lambda w: (w["cls"].lower(), w["title"].lower()))]
    entries = []
    uid, me = os.getuid(), os.getpid()
    # окна по PID (с учётом дочерних процессов) — чтобы подписать приложение заголовком окна
    by_pid: dict = {}
    for w in windows:
        if w["pid"]:
            by_pid.setdefault(w["pid"], []).append(w)
    for p in sorted(procs.values(), key=lambda p: (p["name"].lower(), p["pid"])):
        pid = p["pid"]
        if p["uid"] != uid or pid == me:
            continue
        if mode == "apps":
            parent = procs.get(p["ppid"])
            if not is_gui(p) or (parent and parent["uid"] == uid and is_gui(parent)):
                continue  # только «корни» графических программ
        args = cmd_args(pid)
        if not args:
            continue
        cmd = " ".join(args)
        label = app_label(p["name"], args)
        mark = STATE_MARK.get(p["state"], "")
        wins = [w for q in tree_pids(pid, procs) for w in by_pid.get(q, [])] \
            if mode == "apps" else by_pid.get(pid, [])
        wid = wins[0]["wid"] if wins else None
        if mode == "apps":
            sub = (wins[0]["title"] + (f" (+{len(wins) - 1})" if len(wins) > 1 else "")) if wins else cmd[:90]
            text = f"{label}{mark}\n{sub or cmd[:90]} · PID {pid}"
        else:
            text = f"{label}{mark} · PID {pid}\n{cmd[:110]}"
        entries.append({"key": f"p:{pid}", "title": label, "cls": "", "pid": pid, "wid": wid,
                        "cmd": cmd, "label": label, "text": text,
                        "wtitles": " ".join(w["title"] for w in wins)})
    return entries


def _window_entry(w: dict) -> dict:
    pid = w["pid"]
    text = f"{w['title'] or '(без названия)'}\n{w['cls'] or '—'} · PID {pid or '?'}"
    if w["ws"]:
        text += f" · WS {w['ws']}"
    return {"key": f"w:{w['wid']}", "title": w["title"], "cls": w["cls"], "pid": pid,
            "wid": w["wid"], "cmd": "", "label": w["title"], "text": text}


# ════════════════════════════════════════════════════════════════════════════
#  «ВЫБРАТЬ ОКНО»
# ════════════════════════════════════════════════════════════════════════════
class WindowPicker(QObject):
    """Узнаёт, по какому окну кликнул пользователь.
    X11 — сам клик (xdotool selectwindow / xwininfo); остальные среды — ждём,
    какое окно станет активным. Итог — сигнал finished({wid, pid}) или finished(None)."""
    finished = pyqtSignal(object)

    POLL_MS = 300
    POLL_KEEP_ACTIVE = 17   # ≈5 с без изменений — берём уже активное окно
    POLL_GIVE_UP = 70       # ≈21 с — сдаёмся

    def __init__(self, wm: WindowBackend, parent=None):
        super().__init__(parent)
        self.wm = wm
        self.running = False
        self.pick_proc = None
        self._poll_n = 0
        self._poll_base = None

    def start(self, hidden: bool) -> None:
        """hidden — окно программы только что спряталось: даём ему исчезнуть."""
        self.running = True
        if self.wm.can_pick_by_click():
            QTimer.singleShot(250 if hidden else 0, self._x11_pick)
        else:
            QTimer.singleShot(450 if hidden else 0, self._poll_begin)

    def _finish(self, info) -> None:
        if not self.running:
            return
        self.running = False
        self.finished.emit(info)

    # --- X11: клик по окну
    def _x11_pick(self) -> None:
        cmd = ["xdotool", "selectwindow"] if shutil.which("xdotool") else ["xwininfo"]
        self.pick_proc = QProcess(self)
        self.pick_proc.finished.connect(self._x11_picked)
        self.pick_proc.errorOccurred.connect(lambda _e: self._finish(None))
        self.pick_proc.start(cmd[0], cmd[1:])
        QTimer.singleShot(30000, self._pick_timeout)  # страховка: не висеть вечно

    def _pick_timeout(self) -> None:
        if self.pick_proc is not None and self.pick_proc.state() != QProcess.ProcessState.NotRunning:
            self.pick_proc.kill()

    def _x11_picked(self, code, _status) -> None:
        out = bytes(self.pick_proc.readAllStandardOutput()).decode(errors="ignore")
        wid = None
        m = re.search(r"Window id:\s*(0x[0-9a-fA-F]+)", out)
        if m:
            wid = int(m.group(1), 16)
        elif out.strip().isdigit():
            wid = int(out.strip())
        self.pick_proc = None
        self._finish({"wid": wid, "pid": None} if wid is not None else None)

    # --- остальные среды: следим, какое окно станет активным
    def _poll_begin(self) -> None:
        self._poll_n = 0
        self.wm.request_active(self._poll_base_got)

    def _poll_base_got(self, info) -> None:
        self._poll_base = info  # окно, активное до клика
        QTimer.singleShot(self.POLL_MS, self._poll_tick)

    def _poll_tick(self) -> None:
        if self.running:
            self._poll_n += 1
            self.wm.request_active(self._poll_got)

    def _poll_got(self, info) -> None:
        if not self.running:
            return
        base = self._poll_base
        if info and (not base or info["wid"] != base["wid"]):
            self._finish(info)  # активным стало другое окно — это и есть выбор
        elif self._poll_n >= self.POLL_KEEP_ACTIVE and base:
            self._finish(base)
        elif self._poll_n >= self.POLL_GIVE_UP:
            self._finish(None)
        else:
            QTimer.singleShot(self.POLL_MS, self._poll_tick)


# ════════════════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ════════════════════════════════════════════════════════════════════════════
HINT = tr("Выберите окно слева. «Закрыть» — вежливо, «Принудительно» — сразу убить процесс.")


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.theme = cfg["theme"]
        self.wm = detect_backend()          # стратегия работы с окнами для этой среды
        self.picker = WindowPicker(self.wm, self)
        self.picker.finished.connect(self._pick_done)
        self.mode = cfg["view"]
        self.procs: dict = {}
        self.windows: list = []
        self.entries: list = []
        self.by_key: dict = {}
        self.sel_key = None
        self._tree_sig = None
        self._refreshing = False
        self.save_timer = QTimer(self, singleShot=True, interval=400)
        self.save_timer.timeout.connect(self.save)
        self.toast_timer = QTimer(self, singleShot=True, interval=5000)
        self.setWindowTitle("Equestria Closer")
        self.setMinimumSize(940, 640)
        self.resize(1060, 720)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(10)
        root.addLayout(self._build_header())
        body = QHBoxLayout()
        body.setSpacing(22)
        root.addLayout(body, 1)
        body.addWidget(self._build_list_column())
        body.addLayout(self._build_details_column(), 1)
        self._bind_shortcuts()

        self.timer = QTimer(self, interval=3000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self._set_mode(self.mode, save=False)

    @property
    def picking(self) -> bool:
        return self.picker.running

    # --- построение окна
    def _build_header(self) -> QHBoxLayout:
        top = QHBoxLayout()
        title = QLabel("Equestria Closer")
        title.setObjectName("h2")
        theme_btn = small_btn(tr("Тема"))
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        top.addWidget(title)
        top.addStretch()
        top.addWidget(theme_btn)
        return top

    def _build_list_column(self) -> QWidget:
        """Левая колонка: выбор окна, режимы, поиск и список."""
        left = QVBoxLayout()
        left.setSpacing(8)
        row = QHBoxLayout()
        self.pick_btn = QPushButton(tr("Выбрать окно"))
        self.pick_btn.setObjectName("primary")
        self.pick_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pick_btn.setToolTip(tr("X11: кликните по окну. Wayland: через 3 секунды возьму активное окно."))
        self.pick_btn.clicked.connect(self.start_pick)
        self.refresh_btn = QPushButton(tr("Обновить"))
        self.refresh_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.pick_btn, 1)
        row.addWidget(self.refresh_btn, 1)
        left.addLayout(row)
        mrow = QHBoxLayout()
        self.mode_btns = {}
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for mode, label, tip in (("apps", tr("Приложения"), tr("Программы с окнами, как в системном мониторе")),
                                 ("windows", tr("Окна"), tr("Только окна, которые видит оконный менеджер")),
                                 ("procs", tr("Все процессы"), tr("Все ваши процессы"))):
            b = small_btn(label, True, tip)
            grp.addButton(b)
            mrow.addWidget(b)
            b.clicked.connect(lambda _=False, m=mode: self._set_mode(m))
            self.mode_btns[mode] = b
        mrow.addStretch()
        left.addLayout(mrow)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Поиск по названию, классу, PID…"))
        self.search.textChanged.connect(self._rebuild_list)
        left.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._on_select)
        self.list.itemClicked.connect(lambda _it: self._on_click())
        left.addWidget(self.list, 1)
        self.src_label = QLabel("")
        self.src_label.setObjectName("hint")
        self.src_label.setWordWrap(True)
        left.addWidget(self.src_label)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(400)
        return lw

    def _build_details_column(self) -> QVBoxLayout:
        """Правая колонка: сведения о выбранном, дерево процессов, параметры и действия."""
        right = QVBoxLayout()
        right.setSpacing(8)
        self.d_title = QLabel(tr("Окно не выбрано"))
        self.d_title.setObjectName("out")
        self.d_title.setWordWrap(True)
        self.d_info = QLabel("")
        self.d_info.setObjectName("hint")
        self.d_info.setWordWrap(True)
        self.d_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.addWidget(self.d_title)
        right.addWidget(self.d_info)
        trow = QHBoxLayout()
        tl = QLabel(tr("Дерево процессов"))
        tl.setObjectName("h2")
        self.tree_count = QLabel("")
        self.tree_count.setObjectName("hint")
        trow.addWidget(tl)
        trow.addStretch()
        trow.addWidget(self.tree_count)
        right.addLayout(trow)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([tr("Процесс"), "PID", tr("Команда")])
        self.tree.setColumnWidth(0, 210)
        self.tree.setColumnWidth(1, 70)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        right.addWidget(self.tree, 1)
        orow = QHBoxLayout()
        orow.setSpacing(6)
        self.tree_btn = small_btn(tr("Включая дерево процессов"), True,
                                  tr("Действие применится к процессу окна и ко всем его дочерним процессам"))
        self.hide_btn = small_btn(tr("Скрывать окно при выборе"), True,
                                  tr("Окно прячется на время выбора и возвращается после"))
        self.confirm_btn = small_btn(tr("Спрашивать подтверждение"), True,
                                     tr("Для принудительного закрытия и закрытия дерева"))
        self.reveal_btn_opt = small_btn(tr("Показывать окно при клике"), True,
                                        tr("Клик по пункту списка выводит его окно на передний план"))
        orow2 = QHBoxLayout()
        orow2.setSpacing(6)
        for b, key, lay in ((self.reveal_btn_opt, "reveal", orow), (self.tree_btn, "tree", orow),
                            (self.hide_btn, "hide", orow2), (self.confirm_btn, "confirm", orow2)):
            b.setChecked(bool(self.cfg[key]))
            b.toggled.connect(lambda on, k=key: self._opt(k, on))
            lay.addWidget(b)
        orow.addStretch()
        orow2.addStretch()
        right.addLayout(orow)
        right.addLayout(orow2)
        arow = QHBoxLayout()
        arow.setSpacing(10)
        self.show_btn = QPushButton(tr("Показать окно"))
        self.show_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.show_btn.setToolTip(tr("Вывести окно на передний план — так видно, что это за программа"))
        self.show_btn.clicked.connect(lambda: self.reveal(True))
        arow.addWidget(self.show_btn, 1)
        self.close_btn = QPushButton(tr("Закрыть"))
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.clicked.connect(lambda: self.act(False))
        self.kill_btn = QPushButton(tr("Принудительно"))
        self.kill_btn.setObjectName("danger")
        self.kill_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.kill_btn.clicked.connect(lambda: self.act(True))
        arow.addWidget(self.close_btn, 1)
        arow.addWidget(self.kill_btn, 1)
        right.addLayout(arow)
        self.toast = QLabel(HINT)
        self.toast.setObjectName("hint")
        self.toast.setWordWrap(True)
        self.toast_timer.timeout.connect(lambda: self.toast.setText(HINT))
        right.addWidget(self.toast)
        return right

    def _bind_shortcuts(self) -> None:
        # горячие клавиши работают только когда фокус в списке (чтобы Delete в поиске ничего не закрыл)
        for seq, force in (("Delete", False), ("Shift+Delete", True)):
            sc = QShortcut(QKeySequence(seq), self.list)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(lambda f=force: self.act(f))
        QShortcut(QKeySequence("F5"), self).activated.connect(self.refresh)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(lambda: self.search.setFocus())

    # --- режимы и список
    def _set_mode(self, mode: str, save: bool = True) -> None:
        self.mode = mode
        self.mode_btns[mode].setChecked(True)
        self.sel_key = None
        self.src_label.setText({
            "apps": tr("Программы с графикой (как в системном мониторе); окна подставляются, если их видно. ")
                    + self.wm.label(),
            "windows": self.wm.label(),
            "procs": tr("Все ваши процессы, у которых есть команда запуска."),
        }[mode])
        if save:
            self.cfg["view"] = mode
            self.save_timer.start()
        self.refresh()

    def refresh(self) -> None:
        if self.picking:
            return
        self.procs = scan_procs()
        prune_gui_cache(self.procs)
        self._refreshing = True       # ответ, пришедший сразу, попадёт в ближайший _build
        self.wm.request_windows(self._windows_arrived)
        self._refreshing = False
        self._build()

    def _windows_arrived(self, wins) -> None:
        if wins is None or wins == self.windows:
            return
        self.windows = wins
        if not self._refreshing and not self.picking:
            self._build()  # асинхронный ответ (KDE) — список уже показан, обновляем

    def _build(self) -> None:
        self.entries = build_entries(self.mode, self.procs, self.windows)
        self.by_key = {e["key"]: e for e in self.entries}
        self._rebuild_list()

    def _rebuild_list(self, *_) -> None:
        q = self.search.text().strip().lower()
        sb = self.list.verticalScrollBar().value()
        self.list.blockSignals(True)
        self.list.clear()
        cur = None
        for e in self.entries:
            hay = f"{e['title']} {e['cls']} {e['pid'] or ''} {e['cmd']} {e.get('wtitles', '')}".lower()
            if q and q not in hay:
                continue
            it = QListWidgetItem(e["text"])
            it.setData(Qt.ItemDataRole.UserRole, e["key"])
            self.list.addItem(it)
            if e["key"] == self.sel_key:
                cur = it
        if cur:
            self.list.setCurrentItem(cur)
        self.list.blockSignals(False)
        self.list.verticalScrollBar().setValue(sb)
        if self.sel_key not in self.by_key:
            self.sel_key = None
        self._show_details()

    def _on_select(self) -> None:
        items = self.list.selectedItems()
        self.sel_key = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        self._show_details()

    def _show_details(self) -> None:
        e = self.by_key.get(self.sel_key)
        tree_on = self.tree_btn.isChecked()
        self.close_btn.setText(tr("Закрыть всё дерево") if tree_on else tr("Закрыть"))
        self.kill_btn.setText(tr("Убить всё дерево") if tree_on else tr("Принудительно"))
        if not e:
            self.d_title.setText(tr("Окно не выбрано") if self.mode == "windows" else tr("Процесс не выбран"))
            self.d_info.setText("")
            self._clear_tree()
            self.close_btn.setEnabled(False)
            self.kill_btn.setEnabled(False)
            self.show_btn.setEnabled(False)
            return
        pid = e["pid"]
        p = self.procs.get(pid) if pid else None
        self.d_title.setText(e["title"] or p["name"] if p else (e["title"] or tr("(без названия)")))
        self.d_info.setText(self._details_text(e, p))
        self.show_btn.setEnabled(True)
        alive = bool(p)
        self.close_btn.setEnabled(alive or e["wid"] is not None)
        self.kill_btn.setEnabled(alive)
        if alive:
            self._fill_tree(pid)
        else:
            self._clear_tree()

    def _details_text(self, e: dict, p) -> str:
        pid = e["pid"]
        head = f"PID: {pid or 'неизвестен'}"
        if p:
            head += tr(" · Процесс: {}", p['name'])
            if p["state"] in STATE_MARK:
                head += STATE_MARK[p["state"]]
        if e["cls"]:
            head += tr(" · Класс: {}", e['cls'])
        lines = [head]
        if pid:
            lines.append(tr("Команда: ") + (cmdline(pid)[:300] or "—"))
            cwd = proc_cwd(pid)
            if cwd:
                lines.append(tr("Папка запуска: ") + cwd)
        else:
            lines.append(tr("PID неизвестен — доступно только вежливое закрытие окна."))
        if e.get("wtitles"):
            lines.append(tr("Окна: ") + e["wtitles"][:200])
        return "\n".join(lines)

    def _clear_tree(self) -> None:
        self.tree.clear()
        self.tree_count.setText("")
        self._tree_sig = None

    def _fill_tree(self, pid: int) -> None:
        pids = tree_pids(pid, self.procs)
        self.tree_count.setText(tr("Всего процессов: {}", len(pids)))
        sig = (pid, tuple(pids))
        if sig == self._tree_sig:
            return  # дерево не изменилось — не перестраиваем (сохраняется прокрутка и выделение)
        self._tree_sig = sig
        self.tree.clear()
        nodes: dict = {}
        for q in pids[:600]:
            pr = self.procs[q]
            it = QTreeWidgetItem([pr["name"], str(q), cmdline(q)[:200]])
            parent = nodes.get(pr["ppid"])
            if parent is not None and q != pid:
                parent.addChild(it)
            else:
                self.tree.addTopLevelItem(it)
            nodes[q] = it
        self.tree.expandAll()

    # --- показать окно выбранного пункта
    def _on_click(self) -> None:
        if self.cfg["reveal"]:
            self.reveal(False)

    def reveal(self, explicit: bool) -> None:
        e = self.by_key.get(self.sel_key)
        if not e:
            return
        pid = e["pid"]
        label = e["label"] or e["cls"] or pid
        tree = tree_pids(pid, self.procs) if pid in self.procs else []

        def done(result) -> None:
            if result == REVEAL_SHOWN:
                self._toast(tr("Показано окно: {}", label))
            elif result == REVEAL_NO_REPLY:
                self._toast(tr("KWin не ответил — не удалось вывести окно вперёд."))
            elif result == REVEAL_NO_WINDOW:
                self._toast(tr("У «{}» нет открытого окна (возможно, свёрнуто в трей или это фоновый процесс).", label))
            elif result == REVEAL_FAILED or explicit:
                self._toast(tr("Не удалось вывести окно вперёд."))
            else:
                self._toast(tr("Окно этой программы не видно через оконный менеджер, поэтому показать его нельзя. "
                            "В KDE Wayland поможет утилита kdotool."))
        self.wm.request_reveal(e["wid"], pid, tree, self.windows, done)

    # --- выбор окна
    def start_pick(self) -> None:
        if self.mode == "procs":
            self._set_mode("apps")
        if not self.wm.has_windows:
            self._toast(tr("Определить окно кликом не получится: нет hyprctl, swaymsg, wmctrl или xprop. "
                        "Ищите программу в «Приложениях»."))
            return
        hide = bool(self.cfg["hide"])
        self.pick_btn.setEnabled(False)
        if self.wm.can_pick_by_click():
            self._toast(tr("Кликните по нужному окну…"))
        else:
            self._toast(tr("Кликните по нужному окну — программа возьмёт то, что станет активным."))
        if hide:
            self.hide()
        self.picker.start(hide)

    def _pick_done(self, info) -> None:
        wid = info["wid"] if info else None
        self.pick_btn.setEnabled(True)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.refresh()
        pid = (info or {}).get("pid")
        if pid is None and wid is not None:
            pid = next((w["pid"] for w in self.windows if w["wid"] == wid), None)
        if pid is None and wid is not None:
            pid = self.wm.pid_of(wid)  # кликнули по дочернему окну — узнаём процесс
        if pid == os.getpid():
            self._toast(tr("Выбрано окно самой программы — переключитесь на другое и повторите."))
            return
        key = self._entry_for(wid, pid)
        if key not in self.by_key:
            self._toast(tr("Окно не определено. Попробуйте ещё раз или найдите его в списке."))
            return
        self.sel_key = key
        self._rebuild_list()
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.list.scrollToItem(self.list.item(i))
                break
        self._toast(tr("Выбрано: {}", self.by_key[key]['label'] or self.by_key[key]['cls']))

    def _entry_for(self, wid, pid):
        """Ключ пункта списка, к которому относится выбранное окно (или None)."""
        if self.mode == "windows":
            return f"w:{wid}" if f"w:{wid}" in self.by_key else None
        if pid:
            cand = [e for e in self.entries if e["pid"] and pid in tree_pids(e["pid"], self.procs)]
            return cand[0]["key"] if cand else None
        return None

    # --- закрытие
    def _ask(self, text: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(tr("Подтверждение"))
        box.setText(text)
        yes = box.addButton(tr("Да"), QMessageBox.ButtonRole.AcceptRole)
        no = box.addButton(tr("Отмена"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(no)
        box.exec()
        return box.clickedButton() is yes

    def act(self, force: bool) -> None:
        e = self.by_key.get(self.sel_key)
        if not e:
            self._toast(tr("Сначала выберите окно или процесс в списке."))
            return
        tree = self.tree_btn.isChecked()
        pid = e["pid"]
        pname = (self.procs.get(pid) or {}).get("name", "")
        name = e["title"] or pname or tr("процесс")
        if len(name) > 60:
            name = name[:57] + "…"
        if not force and not tree and e["wid"] is not None:
            self._close_window(e["wid"], pid, name)
        else:
            self._signal_processes(pid, name, force, tree)

    def _close_window(self, wid, pid, name: str) -> None:
        """Вежливое закрытие одного окна — как нажатие на крестик; не вышло — SIGTERM процессу."""
        def done(ok: bool) -> None:
            if ok:
                self._toast(tr("Окну «{}» отправлена просьба закрыться. Если оно спрашивает «сохранить?» — ответьте в нём.", name))
            elif pid in self.procs:
                send_signal([pid], signal.SIGTERM)
                self._toast(tr("Закрыть окно напрямую не вышло — отправил процессу «{}» сигнал SIGTERM.", name))
            else:
                self._toast(tr("Не удалось закрыть окно."))
            QTimer.singleShot(1200, self.refresh)
        self.wm.request_close(wid, done)

    def _signal_processes(self, pid, name: str, force: bool, tree: bool) -> None:
        if not pid or pid not in self.procs:
            self._toast(tr("Процесс не найден — возможно, он уже закрылся."))
            self.refresh()
            return
        pids = tree_pids(pid, self.procs) if tree else [pid]
        me = os.getpid()
        pids = [p for p in pids if p > 1 and p != me]
        if not pids:
            self._toast(tr("Это сама программа или системный процесс — не трогаю."))
            return
        sig = signal.SIGKILL if force else signal.SIGTERM
        if (force or tree) and self.cfg["confirm"]:
            msg = (tr("Принудительно завершить") if force else tr("Попросить завершиться")) + f" «{name}» (PID {pid})"
            if len(pids) > 1:
                msg += tr(" и ещё {} дочерних процессов", len(pids) - 1)
            msg += "?" + (tr(" Несохранённые данные пропадут.") if force else "")
            if not self._ask(msg):
                return
        ok, denied = send_signal(pids, sig)
        text = tr("{} отправлен: {} проц.", 'SIGKILL' if force else 'SIGTERM', ok)
        if denied:
            text += tr(" · нет прав для PID: {}", ', '.join(map(str, denied[:5])))
        if not force:
            text += tr(" Если не закрылось — используйте «Принудительно».")
        self._toast(text)
        QTimer.singleShot(900, self.refresh)

    def _toast(self, text: str) -> None:
        self.toast.setText(text if len(text) <= 200 else text[:197] + "…")
        self.toast_timer.start()

    # --- тема / настройки
    def _opt(self, key: str, val) -> None:
        self.cfg[key] = val
        self.save_timer.start()
        if key == "tree":
            self._show_details()

    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self.cfg["theme"] = self.theme
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


DEFAULTS = {"theme": DEFAULT_THEME, "view": "apps", "tree": True, "hide": True, "confirm": True, "reveal": True}


def load_config() -> dict:
    cfg = load_typed_config(CONFIG, DEFAULTS)
    if cfg["view"] not in MODES:
        cfg["view"] = "apps"
    return cfg


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Closer")
    app.setDesktopFileName("equestria-closer")
    app.setStyle("Fusion")
    cfg = load_config()
    cfg["theme"] = apply_theme(kit_themes.current_name())
    win = MainWindow(cfg)
    kit_themes.follow(win._set_theme, lambda: win.theme)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())