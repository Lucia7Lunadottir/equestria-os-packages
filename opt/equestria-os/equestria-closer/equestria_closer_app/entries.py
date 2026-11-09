"""closer: entries."""
from __future__ import annotations

import os
from .processes import STATE_MARK, app_label, cmd_args, is_gui, tree_pids


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
    text = f"{w['title'] or "common.untitled"}\n{w['cls'] or '—'} · PID {pid or '?'}"
    if w["ws"]:
        text += f" · WS {w['ws']}"
    return {"key": f"w:{w['wid']}", "title": w["title"], "cls": w["cls"], "pid": pid,
            "wid": w["wid"], "cmd": "", "label": w["title"], "text": text}
