# -*- coding: utf-8 -*-
"""
Запуск вместе с системой для приложений Equestria OS.

Стандартный механизм freedesktop: файл ~/.config/autostart/<app>.desktop —
его понимают KDE Plasma, GNOME, XFCE и остальные. Приложение запускается
с ключом --hidden, чтобы сразу уйти в трей и не открывать окно.

    auto = Autostart("equestria-clock", "Equestria Clock")
    auto.is_enabled()        # включён ли
    auto.set_enabled(True)   # включить / выключить
"""
from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path


def autostart_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart"


class Autostart:
    def __init__(self, app_id: str, name: str, comment: str = "", icon: str = "",
                 args: tuple = ("--hidden",)):
        self.app_id, self.name, self.comment = app_id, name, comment
        self.icon = icon or app_id
        self.args = args
        self.path = autostart_dir() / f"{app_id}.desktop"

    def command(self) -> str:
        """Установленная программа (/usr/bin/<app>) или, при запуске из исходников,
        python3 + путь к скрипту."""
        exe = shutil.which(self.app_id)
        if exe:
            parts = [exe]
        else:
            parts = [sys.executable, str(Path(sys.argv[0]).resolve())]
        return " ".join(shlex.quote(p) for p in [*parts, *self.args])

    def is_enabled(self) -> bool:
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return False
        lines = {ln.strip().lower() for ln in text.splitlines()}
        return "hidden=true" not in lines and "x-gnome-autostart-enabled=false" not in lines

    def set_enabled(self, on: bool) -> bool:
        """True — получилось (папку/файл удалось записать или удалить)."""
        try:
            if not on:
                self.path.unlink(missing_ok=True)
                return True
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={self.name}\n"
                + (f"Comment={self.comment}\n" if self.comment else "")
                + f"Exec={self.command()}\n"
                f"Icon={self.icon}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n"
                "X-KDE-autostart-after=panel\n", encoding="utf-8")
            return True
        except OSError:
            return False
