"""Связь с KDE Plasma только через официальные интерфейсы.

  PlasmaShell — D-Bus plasmashell: evaluateScript, dumpCurrentLayoutJS, режим правки.
  KdeConfig   — kreadconfig6 / kwriteconfig6 (никогда не переписываем файлы KDE сами).
  DayNight    — какая половина пары глобальных тем («день/ночь») сейчас активна.
  ShellRestart — перезапуск plasmashell через его службу systemd; нужен только
                 для смены вида рабочего стола (значки), у этого нет D-Bus-метода.
"""
from __future__ import annotations

import json
import subprocess

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal
from PyQt6.QtDBus import (QDBusConnection, QDBusInterface, QDBusMessage, QDBusPendingCallWatcher,
                          QDBusPendingReply)

SERVICE, PATH, IFACE = "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell"


class PlasmaShell(QObject):
    """Обёртка над D-Bus-объектом /PlasmaShell."""

    script_finished = pyqtSignal(bool, str)  # успех, текст ошибки

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watchers = []

    def _iface(self) -> QDBusInterface:
        return QDBusInterface(SERVICE, PATH, IFACE, QDBusConnection.sessionBus())

    def is_running(self) -> bool:
        reply = QDBusConnection.sessionBus().interface().isServiceRegistered(SERVICE)
        return bool(reply.value())

    def evaluate(self, script: str) -> None:
        """Выполнить скрипт Plasma асинхронно; итог — сигнал script_finished."""
        call = self._iface().asyncCall("evaluateScript", script)
        watcher = QDBusPendingCallWatcher(call, self)
        self._watchers.append(watcher)
        watcher.finished.connect(self._on_script_done)

    def _on_script_done(self, watcher: QDBusPendingCallWatcher):
        self._watchers.remove(watcher)
        reply = QDBusPendingReply(watcher)  # у watcher в PyQt6 нет reply()
        watcher.deleteLater()
        if reply.isError():
            self.script_finished.emit(False, reply.error().message())
        else:
            self.script_finished.emit(True, "")

    def dump_layout(self) -> dict | None:
        """Текущая раскладка в формате KDE (тот же, что для раскладок глобальных тем)."""
        reply = self._iface().call("dumpCurrentLayoutJS")
        if reply.type() == QDBusMessage.MessageType.ErrorMessage or not reply.arguments():
            return None
        raw = reply.arguments()[0]
        text = bytes(raw).decode("utf-8") if not isinstance(raw, str) else raw
        return parse_layout_dump(text)

    def set_edit_mode(self, on: bool = True) -> None:
        iface = self._iface()
        iface.call("evaluateScript", "lockCorona(false);")
        iface.setProperty("editMode", on)


def parse_layout_dump(text: str) -> dict | None:
    """Достать объект layout из JS, который отдаёт dumpCurrentLayoutJS."""
    start = text.find("var layout = ")
    end = text.rfind("plasma.loadSerializedLayout")
    if start < 0 or end < 0:
        return None
    body = text[start + len("var layout = "):end].strip().rstrip(";").strip()
    try:
        return json.loads(body)
    except ValueError:
        return None


class KdeConfig:
    """kreadconfig6 / kwriteconfig6: файлы KDE пишет только сама KDE."""

    @staticmethod
    def read(file: str, groups: list[str], key: str, default: str = "") -> str:
        cmd = ["kreadconfig6", "--file", file]
        for g in groups:
            cmd += ["--group", g]
        cmd += ["--key", key, "--default", default]
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return default

    @staticmethod
    def write_cmd(file: str, groups: list[str], key: str, value: str) -> list[str]:
        cmd = ["kwriteconfig6", "--file", file]
        for g in groups:
            cmd += ["--group", g]
        return cmd + ["--key", key, value]


class DayNight:
    """Сейчас ночь или день — так же решает сама KDE и переключатель персонажей."""

    @staticmethod
    def is_dark_now() -> bool:
        current = KdeConfig.read("kdeglobals", ["KDE"], "LookAndFeelPackage")
        dark = KdeConfig.read("kdeglobals", ["KDE"], "DefaultDarkLookAndFeel")
        return bool(current) and (current == dark or current.endswith("-Dark")
                                  or current == "org.kde.breezedark.desktop")


class ShellRestart(QObject):
    """Остановить plasmashell, выполнить правку его конфига, запустить снова.

    Plasma держит конфиг в памяти и при выходе записывает его, поэтому править
    можно только между остановкой и запуском. Используется служба systemd
    plasma-plasmashell.service — так же, как это делает сама сессия Plasma."""

    finished = pyqtSignal(bool)
    UNIT = "plasma-plasmashell.service"
    WAIT_STEPS = 60  # × 250 мс

    def __init__(self, shell: PlasmaShell, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._edits: list[list[str]] = []
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._poll)
        self._left = 0

    def run(self, edits: list[list[str]]) -> None:
        self._edits = edits
        self._step(["systemctl", "--user", "stop", self.UNIT], self._apply_edits)

    def _step(self, cmd, then):
        proc = QProcess(self)
        proc.finished.connect(lambda *_: (proc.deleteLater(), then()))
        proc.start(cmd[0], cmd[1:])

    def _apply_edits(self):
        for cmd in self._edits:
            subprocess.run(cmd, capture_output=True)
        self._step(["systemctl", "--user", "start", self.UNIT], self._wait_shell)

    def _wait_shell(self):
        self._left = self.WAIT_STEPS
        self._timer.start()

    def _poll(self):
        self._left -= 1
        if self._shell.is_running():
            self._timer.stop()
            # объект /PlasmaShell появляется чуть позже имени службы
            QTimer.singleShot(1500, lambda: self.finished.emit(True))
        elif self._left <= 0:
            self._timer.stop()
            self.finished.emit(False)
