"""Раскладка панелей — данные в формате KDE, без правки конфигов Plasma.

Формат панели — тот же, что отдаёт plasmashell (dumpCurrentLayoutJS):
    {"location": "bottom", "height": 2.33, "alignment": "center", "floating": true,
     "hiding": "normal", "lengthMode": "fit", "offset": 0,
     "minimumLength": 0, "maximumLength": 0,
     "applets": [{"plugin": "org.kde.plasma.kickoff", "config": {"/General": {"icon": "..."}}}]}
Размеры — в gridUnit (как у KDE), в пиксели переводит сам скрипт.

Применяется раскладка скриптом Plasma (new Panel / addWidget / writeConfig —
документированный Desktop Scripting API): панели пересоздаются, рабочий стол
и обои не трогаются, plasmashell не перезапускается.
"""
from __future__ import annotations

import configparser
import copy
import json
import os
import re
from abc import ABC, abstractmethod

TASKBARS = ("org.kde.plasma.icontasks", "org.kde.plasma.taskmanager")
MEMORY_MONITORS = ("org.kde.plasma.systemmonitor", "org.kde.plasma.systemmonitor.memory")
DEFAULT_GRID_UNIT = 18


class PanelLayout:
    """Список панелей. Хранится как JSON, применяется скриптом."""

    def __init__(self, panels: list[dict]):
        self.panels = panels

    @classmethod
    def from_dump(cls, dump: dict) -> "PanelLayout":
        return cls(copy.deepcopy(dump.get("panels", [])))

    def copy(self) -> "PanelLayout":
        return PanelLayout(copy.deepcopy(self.panels))

    def applets(self, plugins: tuple[str, ...]):
        for panel in self.panels:
            for applet in panel.get("applets", []):
                if applet.get("plugin") in plugins:
                    yield applet

    def launchers(self) -> str | None:
        for applet in self.applets(TASKBARS):
            value = applet.get("config", {}).get("/General", {}).get("launchers")
            if value:
                return value
        return None

    def to_json(self) -> dict:
        return {"panels": self.panels}


# ─── Поправки раскладки перед применением ───────────────────────────────────

class LayoutPatch(ABC):
    """Одна поправка раскладки (принцип открытости: новые — новыми классами)."""

    @abstractmethod
    def apply(self, layout: PanelLayout) -> None: ...


class LauncherCatalog:
    """Проверка ярлыков панели задач: есть ли такое приложение в системе."""

    DIRS = (os.path.expanduser("~/.local/share/applications"), "/usr/share/applications",
            "/usr/local/share/applications", "/var/lib/flatpak/exports/share/applications",
            os.path.expanduser("~/.local/share/flatpak/exports/share/applications"))

    def exists(self, desktop_name: str) -> bool:
        return any(os.path.exists(os.path.join(d, desktop_name)) for d in self.DIRS)

    def validate(self, launchers: str) -> str:
        valid = []
        for item in (x.strip() for x in launchers.split(",")):
            if not item:
                continue
            if item.startswith("applications:"):
                if self.exists(item.split(":", 1)[1]):
                    valid.append(item)
            elif item.endswith(".desktop") and "://" not in item:
                if self.exists(item):
                    valid.append(f"applications:{item}")
            else:  # preferred://, file:// и прочее — не приложения из меню
                valid.append(item)
        return ",".join(valid)


class KeepUserLaunchers(LayoutPatch):
    """Закреплённые пользователем ярлыки переходят в новую раскладку;
    ярлыки удалённых программ убираются."""

    def __init__(self, current: str | None, catalog: LauncherCatalog | None = None):
        self.current = current
        self.catalog = catalog or LauncherCatalog()

    def apply(self, layout: PanelLayout) -> None:
        user = self.catalog.validate(self.current) if self.current else None
        for applet in layout.applets(TASKBARS):
            general = applet.setdefault("config", {}).setdefault("/General", {})
            value = user if user else general.get("launchers")
            if value:
                general["launchers"] = self.catalog.validate(value)


class MemoryMonitorTitles:
    """Заголовок «Использование памяти» на всех языках (KDE выберет нужный сам)."""

    TITLES = {
        "": "Memory Usage", "de": "Speicherauslastung", "es": "Uso de la memoria",
        "fr": "Utilisation de la mémoire", "ja": "メモリ使用量", "pl": "Użycie pamięci",
        "pt": "Utilização da memória", "ru": "Использование памяти",
        "uk": "Використання пам'яті", "zh_CN": "内存使用",
    }

    @classmethod
    def entries(cls) -> dict:
        # Тот же блок Title/Title[xx], что пишет fix_sysmon_title.sh при входе:
        # сырой заголовок одним языком он бы снова переделывал с перезапуском
        return {("Title" if not lang else f"Title[{lang}]"): text for lang, text in cls.TITLES.items()}


class ConfigureMemoryMonitor(LayoutPatch):
    """Виджет памяти, добавленный скриптом, создаётся пустым (faceproperties
    применяет только добавление мышью) — дописываем сенсоры и вид."""

    SENSORS = {
        "highPrioritySensorIds": '["memory/physical/used"]',
        "lowPrioritySensorIds": '["memory/physical/total"]',
        "totalSensors": '["memory/physical/usedPercent"]',
    }

    def apply(self, layout: PanelLayout) -> None:
        for applet in layout.applets(MEMORY_MONITORS):
            cfg = applet.setdefault("config", {})
            sensors = cfg.setdefault("/Sensors", {})
            if not sensors.get("highPrioritySensorIds"):
                sensors.update(self.SENSORS)
            appearance = cfg.setdefault("/Appearance", {})
            appearance.setdefault("chartFace", "org.kde.ksysguard.piechart")
            appearance.pop("title", None)
            appearance.update(MemoryMonitorTitles.entries())


# ─── Скрипт Plasma ─────────────────────────────────────────────────────────

class LayoutScript:
    """Строит скрипт Desktop Scripting API, пересоздающий панели."""

    HIDING = {"normal": "none", "none": "none", "autohide": "autohide",
              "dodgewindows": "dodgewindows", "windowsgobelow": "windowsgobelow",
              "windowsbelow": "dodgewindows", "windowscover": "windowsgobelow"}

    def __init__(self, layout: PanelLayout):
        self.layout = layout

    @staticmethod
    def _js(value) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _panel(self, i: int, p: dict) -> list[str]:
        v = f"p{i}"
        out = [f"var {v}=new Panel;",
               f"{v}.location={self._js(p.get('location', 'bottom'))};",
               f"{v}.alignment={self._js(p.get('alignment', 'left'))};",
               f"{v}.lengthMode={self._js(p.get('lengthMode', 'fill'))};",
               f"{v}.floating={'true' if p.get('floating') else 'false'};",
               f"{v}.hiding={self._js(self.HIDING.get(p.get('hiding', 'normal'), 'none'))};"]
        if p.get("offset"):
            out.append(f"{v}.offset=Math.round({float(p['offset'])}*gridUnit);")
        if p.get("lengthMode") == "custom":
            for key in ("minimumLength", "maximumLength"):
                if p.get(key):
                    out.append(f"{v}.{key}=Math.round({float(p[key])}*gridUnit);")
        for j, applet in enumerate(p.get("applets", [])):
            w = f"w{i}_{j}"
            out.append(f"var {w}={v}.addWidget({self._js(applet['plugin'])});")
            for group, entries in applet.get("config", {}).items():
                path = [g for g in group.split("/") if g]
                out.append(f"{w}.currentConfigGroup={self._js(path)};")
                for key, value in entries.items():
                    out.append(f"{w}.writeConfig({self._js(key)},{self._js(str(value))});")
            if applet.get("config"):
                out.append(f"if(typeof {w}.reloadConfig==='function'){{{w}.reloadConfig();}}")
        # высоту — в конце: добавление виджетов может её пересчитать
        out.append(f"{v}.height=Math.round({float(p.get('height', 2.5))}*gridUnit);")
        return out

    def build(self) -> str:
        lines = ["var old=panels();for(var i=0;i<old.length;i++){old[i].remove();}"]
        for i, panel in enumerate(self.layout.panels):
            lines += self._panel(i, panel)
        return "\n".join(lines)


# ─── Старые снимки (.bak — копия всего конфига Plasma) ─────────────────────

class LegacySnapshotConverter:
    """Переводит снимок старых версий (копия plasma-org.kde.plasma.desktop-appletsrc
    и plasmashellrc) в раскладку. Берутся только панели; рабочий стол, обои и
    внутренности системного лотка не переносятся (лоток KDE создаёт заново)."""

    LOCATION = {"3": "top", "4": "bottom", "5": "left", "6": "right"}
    ALIGNMENT = {"1": "left", "2": "right", "4": "center", "132": "center"}
    LENGTH = {"0": "fill", "1": "fit", "2": "custom"}
    HIDING = {"0": "normal", "1": "autohide", "2": "dodgewindows", "3": "windowsgobelow"}
    SKIP_APPLET_KEYS = {"SystrayContainmentId"}

    def __init__(self, grid_unit: int = DEFAULT_GRID_UNIT):
        self.grid_unit = grid_unit or DEFAULT_GRID_UNIT

    @staticmethod
    def _read(path: str) -> configparser.ConfigParser:
        cp = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
        cp.optionxform = str
        try:
            cp.read(path, encoding="utf-8")
        except (configparser.Error, OSError):
            pass
        return cp

    def convert(self, appletsrc: str, shellrc: str | None) -> PanelLayout:
        cfg = self._read(appletsrc)
        views = self._read(shellrc) if shellrc and os.path.exists(shellrc) else None
        panels = []
        for section in cfg.sections():
            m = re.fullmatch(r"Containments\]\[(\d+)", section)
            if m and cfg[section].get("plugin") == "org.kde.panel":
                panels.append(self._panel(cfg, views, m.group(1)))
        return PanelLayout(panels)

    def _panel(self, cfg, views, cid: str) -> dict:
        base = f"Containments][{cid}"
        view = f"PlasmaViews][Panel {cid}"
        get = (lambda key, d="": views[view].get(key, d)) if views and views.has_section(view) else (lambda key, d="": d)
        defaults = f"{view}][Defaults"
        thickness = views[defaults].get("thickness") if views and views.has_section(defaults) else None
        panel = {
            "location": self.LOCATION.get(cfg[base].get("location", "4"), "bottom"),
            # KDE пишет alignment, только если он не по центру (умолчание Plasma 6)
            "alignment": self.ALIGNMENT.get(get("alignment", "4"), "center"),
            "floating": get("floating", "0") == "1",
            "lengthMode": self.LENGTH.get(get("panelLengthMode", "0"), "fill"),
            "hiding": self.HIDING.get(get("panelVisibility", "0"), "normal"),
            "height": round(int(thickness or 44) / self.grid_unit, 4),
            "applets": [self._applet(cfg, base, aid) for aid in self._applet_order(cfg, base)],
        }
        return panel

    @staticmethod
    def _applet_order(cfg, base: str) -> list[str]:
        ids = [m.group(1) for s in cfg.sections()
               if (m := re.fullmatch(re.escape(base) + r"\]\[Applets\]\[(\d+)", s))]
        general = f"{base}][General"
        order = cfg[general].get("AppletOrder", "") if cfg.has_section(general) else ""
        ordered = [a for a in order.split(";") if a in ids]
        return ordered + sorted((a for a in ids if a not in ordered), key=int)

    def _applet(self, cfg, base: str, aid: str) -> dict:
        prefix = f"{base}][Applets][{aid}"
        applet = {"plugin": cfg[prefix].get("plugin", ""), "config": {}}
        if applet["plugin"] == "org.kde.plasma.systemtray":
            return applet
        root = f"{prefix}][Configuration"
        for section in cfg.sections():
            if section == root or section.startswith(root + "]["):
                group = "/" + "/".join(section[len(root):].split("][")).strip("/")
                entries = {k: v for k, v in cfg[section].items() if k not in self.SKIP_APPLET_KEYS}
                if entries:
                    applet["config"][group if group != "/" else "/"] = entries
        return applet
