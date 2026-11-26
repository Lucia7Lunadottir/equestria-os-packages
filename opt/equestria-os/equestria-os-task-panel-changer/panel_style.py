"""Цвет и прозрачность панели — два Plasma-стиля: дневной и ночной.

  EquestriaPanel-Light   фон панели дневным цветом
  EquestriaPanel-Dark    фон панели ночным цветом

В стилях только фон панели (widgets/panel-background.svg). Файла colors нет:
текст, значки и всплывающие окна берут цвета из текущей цветовой схемы,
поэтому всегда совпадают с темой персонажа. Всё остальное (Breeze) стиль
получает через fallbackPackage, обновления Plasma доходят как обычно.

Переключает стили сама KDE: глобальные темы персонажей (kde_laf.py в
equestria-os-character-theme) указывают [plasmarc][Theme] name=EquestriaPanel-*,
так же как Breeze указывает name=default. Базовые версии стилей ставит пакет
equestria-os-character-theme в /usr/share; здесь пишутся свои — в ~/.local.
"""
from __future__ import annotations

import json
import os
import shutil

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

from plasma import DayNight, KdeConfig

STYLE_DAY, STYLE_NIGHT = "EquestriaPanel-Light", "EquestriaPanel-Dark"
USER_THEMES = os.path.expanduser("~/.local/share/plasma/desktoptheme")


def style_metadata(style_id: str, name: str) -> dict:
    # Именно X-Plasma-API, как у Breeze. С X-Plasma-API-Minimum-Version Plasma
    # не берёт из стиля набор Complementary: экран блокировки осветляется,
    # текст в окне выхода тёмный (найдено 2026-11-02, Plasma 6.8).
    return {
        "KPlugin": {"Id": style_id, "Name": name, "Authors": [{"Name": "Equestria OS"}], "Version": "2.0"},
        "X-Plasma-API": "5.0",
        "fallbackPackage": "default",
    }


class PanelBackgroundSvg:
    """SVG фона панели: обычная и «плавающая» панели, маски скругления."""

    RADIUS = 8

    def __init__(self, color: str, opacity: float):
        self.color, self.opacity = color, max(0.0, min(1.0, opacity))

    @staticmethod
    def _rects(prefix: str, x0: int, rx: int = 0, attrs: str = ' class="bg"') -> list[str]:
        e, inner = x0, 100 - 2 * x0
        geo = {
            "center": (e, e, inner, inner), "top": (e, 0, inner, e), "bottom": (e, 100 - e, inner, e),
            "left": (0, e, e, inner), "right": (100 - e, e, e, inner), "topleft": (0, 0, e, e),
            "topright": (100 - e, 0, e, e), "bottomleft": (0, 100 - e, e, e), "bottomright": (100 - e, 100 - e, e, e),
        }
        out = []
        for name, (x, y, w, h) in geo.items():
            round_ = f' rx="{rx}" ry="{rx}"' if rx and name == "center" else ""
            out.append(f'  <rect id="{prefix}{name}" x="{x}" y="{y}" width="{w}" height="{h}"{round_}{attrs}/>')
        return out

    @staticmethod
    def _empty(prefix: str) -> list[str]:
        names = ("top", "bottom", "left", "right", "topleft", "topright", "bottomleft", "bottomright")
        return [f'  <rect id="{prefix}{n}" width="0" height="0" fill="none"/>' for n in names]

    def render(self) -> str:
        r = self.RADIUS
        # Цвет — только у элементов с class="bg": правило CSS сильнее атрибута fill,
        # и без класса маска скругления тоже красилась бы полупрозрачным цветом
        mask = self._rects("mask-", r, r, ' fill="#fff" fill-opacity="1"')
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">',
            f'  <defs><style>.bg {{ fill: {self.color}; fill-opacity: {self.opacity:.2f}; }}</style></defs>',
            '  <rect id="hint-stretch-borders" width="0" height="0" fill="none"/>',
            *self._rects("", 6),
            *self._empty("shadow-"),
            *self._rects("floating-", r, r),
            *self._empty("floating-shadow-"),
            *mask,
            '  <rect id="hint-compose-over-border" width="0" height="0" fill="none"/>',
            '</svg>',
        ]
        return "\n".join(lines) + "\n"


class PanelStyleWriter:
    """Пишет пару стилей в ~/.local/share/plasma/desktoptheme."""

    NAMES = {STYLE_DAY: "Equestria Panel (day)", STYLE_NIGHT: "Equestria Panel (night)"}

    def __init__(self, root: str = USER_THEMES):
        self.root = root

    def write(self, color_day: str, color_night: str, opacity_percent: int) -> None:
        for style_id, color in ((STYLE_DAY, color_day), (STYLE_NIGHT, color_night)):
            pkg = os.path.join(self.root, style_id)
            os.makedirs(os.path.join(pkg, "widgets"), exist_ok=True)
            with open(os.path.join(pkg, "metadata.json"), "w", encoding="utf-8") as f:
                json.dump(style_metadata(style_id, self.NAMES[style_id]), f, indent=4, ensure_ascii=False)
            with open(os.path.join(pkg, "widgets", "panel-background.svg"), "w", encoding="utf-8") as f:
                f.write(PanelBackgroundSvg(color, opacity_percent / 100.0).render())


class LegacyThemeCleanup:
    """Убирает то, что создавали старые версии утилиты (только своё).

      desktoptheme/default        заглушка «Equestria Fallback» — подменяла родной Breeze
                                  и ломала цвета экрана блокировки и окна выхода
      desktoptheme/EquestriaPanel старый стиль с файлом colors (цвета в обход схемы)
      color-schemes/EquestriaPanel.colors  схема, которой затиралась схема персонажа
    """

    def __init__(self, data_home: str = os.path.expanduser("~/.local/share")):
        self.data_home = data_home

    def _ours(self, pkg: str, field: str, value: str) -> bool:
        try:
            with open(os.path.join(pkg, "metadata.json"), encoding="utf-8") as f:
                return json.load(f).get("KPlugin", {}).get(field) == value
        except (OSError, ValueError):
            return False

    def run(self) -> None:
        themes = os.path.join(self.data_home, "plasma", "desktoptheme")
        stub = os.path.join(themes, "default")
        if self._ours(stub, "Name", "Equestria Fallback") and \
                set(os.listdir(stub)) <= {"metadata.json", "settings", "metadata.desktop"}:
            shutil.rmtree(stub, ignore_errors=True)
        old = os.path.join(themes, "EquestriaPanel")
        if self._ours(old, "Id", "EquestriaPanel") and \
                KdeConfig.read("plasmarc", ["Theme"], "name", "default") != "EquestriaPanel":
            shutil.rmtree(old, ignore_errors=True)
        scheme = os.path.join(self.data_home, "color-schemes", "EquestriaPanel.colors")
        if os.path.exists(scheme) and KdeConfig.read("kdeglobals", ["General"], "ColorScheme") != "EquestriaPanel":
            os.remove(scheme)


class PanelStyleManager(QObject):
    """Записать стили и включить нужный для текущего времени суток."""

    applied = pyqtSignal()

    def __init__(self, writer: PanelStyleWriter | None = None, parent=None):
        super().__init__(parent)
        self.writer = writer or PanelStyleWriter()
        self._queue: list[list[str]] = []

    @staticmethod
    def current_style_id() -> str:
        return STYLE_NIGHT if DayNight.is_dark_now() else STYLE_DAY

    def sync_with_day_night(self) -> None:
        """Включён наш стиль, но не той половины дня — включить нужный.

        Так бывает, когда глобальная тема в ~/.local собрана старым
        переключателем персонажей без [plasmarc][Theme]: KDE меняет день/ночь,
        а стиль панели остаётся прежним. Чужой стиль (Breeze и т.п.) не трогаем."""
        active = KdeConfig.read("plasmarc", ["Theme"], "name", "default")
        target = self.current_style_id()
        if active in (STYLE_DAY, STYLE_NIGHT) and active != target:
            QProcess.startDetached("plasma-apply-desktoptheme", [target])

    def apply(self, color_day: str, color_night: str, opacity_percent: int) -> None:
        self.writer.write(color_day, color_night, opacity_percent)
        target = self.current_style_id()
        active = KdeConfig.read("plasmarc", ["Theme"], "name", "default")
        self._queue = []
        if active == target:
            # Тот же стиль с новым SVG: Plasma перерисовывает панель только при
            # смене стиля, поэтому на миг включаем Breeze и возвращаемся
            self._queue.append(["plasma-apply-desktoptheme", "default"])
        self._queue.append(["plasma-apply-desktoptheme", target])
        self._next()

    def _next(self):
        if not self._queue:
            LegacyThemeCleanup().run()  # старый стиль удаляем, когда он уже не активен
            self.applied.emit()
            return
        cmd = self._queue.pop(0)
        proc = QProcess(self)
        proc.finished.connect(lambda *_: (proc.deleteLater(), self._next()))
        proc.start(cmd[0], cmd[1:])
