"""closer: picker."""
from __future__ import annotations

import re
import shutil
from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal
from .backends import WindowBackend


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
