"""Значки на рабочем столе: вид рабочего стола «Папка» (со значками) или «Рабочий стол».

У Plasma нет D-Bus-метода для смены вида рабочего стола, поэтому меняется
ключ plugin его контейнера через kwriteconfig6 между остановкой и запуском
plasmashell (ShellRestart). Делается это только если вид действительно нужно
сменить — обычное применение пресета оболочку не перезапускает.
"""
from __future__ import annotations

import configparser
import os
import re

from plasma import KdeConfig

APPLETSRC = "plasma-org.kde.plasma.desktop-appletsrc"
WITH_ICONS, WITHOUT_ICONS = "org.kde.plasma.folder", "org.kde.desktopcontainment"


class DesktopIcons:
    def __init__(self, path: str = os.path.expanduser(f"~/.config/{APPLETSRC}")):
        self.path = path

    def _desktops(self) -> dict[str, str]:
        """{номер контейнера: plugin} для всех рабочих столов (только чтение)."""
        cp = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
        cp.optionxform = str
        try:
            cp.read(self.path, encoding="utf-8")
        except (configparser.Error, OSError):
            return {}
        out = {}
        for section in cp.sections():
            m = re.fullmatch(r"Containments\]\[(\d+)", section)
            if m and cp[section].get("plugin") in (WITH_ICONS, WITHOUT_ICONS):
                out[m.group(1)] = cp[section]["plugin"]
        return out

    def edits_for(self, hide: bool) -> list[list[str]]:
        """Команды kwriteconfig6, приводящие рабочие столы к нужному виду
        (пустой список — менять нечего)."""
        target = WITHOUT_ICONS if hide else WITH_ICONS
        return [KdeConfig.write_cmd(APPLETSRC, ["Containments", cid], "plugin", target)
                for cid, plugin in self._desktops().items() if plugin != target]
