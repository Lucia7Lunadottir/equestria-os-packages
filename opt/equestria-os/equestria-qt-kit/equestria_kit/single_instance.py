# -*- coding: utf-8 -*-
"""
Одна копия приложения на пользователя (для приложений с треем).

Повторный запуск (из меню, ярлыка, виджета) не открывает второе приложение,
а будит уже работающее: оно показывает своё окно. Запуск с --hidden
(автозапуск) уже работающую копию не трогает.

    instance = SingleInstance("equestria-clock")
    if not instance.claim():
        instance.notify_running(show="--hidden" not in sys.argv)
        return 0                         # копия уже работает — она и покажет окно
    ...
    instance.on_show(win.show_window)    # после создания окна

Приложению, которое открывает документы («Открыть с помощью» в KDE), вторая
копия передаёт и аргументы — их получает обработчик on_args (вместо on_show):

    if not instance.claim():
        instance.notify_running(args=[os.path.abspath(p) for p in files])
        return 0
    instance.on_args(win.open_files_from_instance)

Кто «первый», решает QLockFile (не путается, если два запуска совпали по
времени, и сам снимается, если прошлая копия упала); окно будит QLocalServer.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QByteArray, QLockFile
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

_SHOW = b"show"
_ARGS = b"args"   # «args» + токен + JSON-список аргументов (по строке на каждое)


def runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("XDG_CACHE_HOME")
                or Path.home() / ".cache")


class SingleInstance:
    def __init__(self, app_id: str):
        self.app_id = app_id
        self.server_name = f"{app_id}-{os.getuid()}"
        self._lock = QLockFile(str(runtime_dir() / f"{app_id}.lock"))
        self._lock.setStaleLockTime(0)   # «протухшим» считается только замок умершего процесса
        self._server: QLocalServer | None = None
        self._show: Callable[[], object] | None = None
        self._args: Callable[[list], object] | None = None

    def claim(self) -> bool:
        """True — это первая копия (замок взят, ждём сигналов от следующих)."""
        if not self._lock.tryLock(100):
            return False
        QLocalServer.removeServer(self.server_name)   # сокет, оставшийся от упавшей копии
        self._server = QLocalServer()
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._accept)
        if not self._server.listen(self.server_name):
            print(f"[equestria_kit] {self.app_id}: {self._server.errorString()}")
        return True

    def notify_running(self, show: bool = True, timeout_ms: int = 1500,
                       args: list | None = None) -> bool:
        """Из второй копии: попросить первую показать окно. Токен активации Wayland
        передаётся ей, иначе KWin не даст окну выйти на передний план.
        args — аргументы для обработчика on_args (пути — уже абсолютные: у второй
        копии своя рабочая папка)."""
        if not show and args is None:
            return True
        sock = QLocalSocket()
        sock.connectToServer(self.server_name)
        if not sock.waitForConnected(timeout_ms):
            return False
        token = os.environ.get("XDG_ACTIVATION_TOKEN", "")
        if args is None:
            sock.write(_SHOW + b"\n" + token.encode() + b"\n")
        else:
            sock.write(_ARGS + b"\n" + token.encode() + b"\n"
                       + json.dumps(list(args), ensure_ascii=False).encode() + b"\n")
        sock.waitForBytesWritten(timeout_ms)
        sock.disconnectFromServer()
        return True

    def on_show(self, fn: Callable[[], object]) -> None:
        """Что делать, когда повторный запуск просит показать окно."""
        self._show = fn

    def on_args(self, fn: Callable[[list], object]) -> None:
        """Что делать с аргументами повторного запуска (fn(args) сама показывает окно)."""
        self._args = fn

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        self._lock.unlock()

    def _accept(self) -> None:
        while self._server is not None and self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            buf = QByteArray()

            def read(s=sock, b=buf) -> None:
                b.append(s.readAll())
                need = 3 if b.startsWith(_ARGS + b"\n") else 2   # «show»/«args» + токен (+ аргументы)
                if b.count(b"\n") >= need:
                    self._handle(bytes(b.data()))
                    s.disconnectFromServer()

            sock.readyRead.connect(read)
            sock.disconnected.connect(sock.deleteLater)

    def _handle(self, data: bytes) -> None:
        cmd, _, rest = data.partition(b"\n")
        token, _, payload = rest.partition(b"\n")
        if cmd == _ARGS and self._args is not None:
            try:
                args = json.loads(payload.split(b"\n", 1)[0].decode(errors="ignore"))
            except ValueError:
                return
            call = lambda: self._args([str(a) for a in args] if isinstance(args, list) else [])
        elif cmd in (_SHOW, _ARGS) and self._show is not None:
            call = self._show
        else:
            return
        token = token.decode(errors="ignore")
        if token:   # Qt (Wayland) берёт токен из окружения при activateWindow()
            os.environ["XDG_ACTIVATION_TOKEN"] = token
        try:
            call()
        except Exception as e:  # noqa: BLE001 — слот Qt: исключение уронит PyQt6
            print(f"[equestria_kit] {self.app_id}: {cmd.decode(errors='ignore')}: {e}")
