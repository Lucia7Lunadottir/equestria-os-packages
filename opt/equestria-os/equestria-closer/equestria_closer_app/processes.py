"""closer: processes."""
from __future__ import annotations

import os
import re
from .localization import tr


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


STATE_MARK = {"Z": tr("processes.zombie"), "D": tr("processes.hung_d"), "T": tr("processes.stopped")}


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
