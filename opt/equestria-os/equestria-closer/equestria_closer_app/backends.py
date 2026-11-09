"""closer: backends."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from PyQt6.QtCore import QObject, QTimer, pyqtClassInfo, pyqtSignal, pyqtSlot
from abc import ABC
from pathlib import Path
from .localization import tr


try:
    from PyQt6.QtDBus import QDBusConnection, QDBusInterface
    HAVE_DBUS = True
except ImportError:  # без QtDBus KDE-режим просто недоступен
    HAVE_DBUS = False


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


REVEAL_SHOWN, REVEAL_FAILED, REVEAL_INVISIBLE, REVEAL_NO_REPLY, REVEAL_NO_WINDOW = range(5)


class WindowBackend(ABC):
    """Как программа видит окна и управляет ими в данной графической среде.
    Новая среда = новый класс в BACKENDS; MainWindow при этом не меняется."""
    id = "none"

    @classmethod
    def available(cls) -> bool:
        return False

    def label(self) -> str:
        return tr("backends.window_list_unavailable_hyprctl_swaymsg")

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
        return tr("backends.windows_hyprland_hyprctl")

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
        return tr("backends.windows_sway_swaymsg")

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
        txt = tr("backends.windows_x11_wmctrl") if shutil.which("wmctrl") else tr("backends.windows_x11_xprop_closing_by")
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            txt += tr("backends.only_xwayland_windows_visible_look")
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
        return tr("backends.windows_kde_plasma_kwin_scripts")

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


BACKENDS = (HyprlandBackend, SwayBackend, KdeBackend, X11Backend)


def detect_backend() -> WindowBackend:
    for cls in BACKENDS:
        if cls.available():
            backend = cls()
            if backend.ready():
                return backend
    return NoBackend()
