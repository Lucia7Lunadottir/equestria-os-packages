"""Пресеты панели: внешний вид + раскладка.

  системные    <приложение>/presets.json (только чтение)
  свои         ~/.local/share/EquestriaOS/PanelStyles/presets.json
  снятые       ~/.local/share/EquestriaOS/PanelStyles/layouts/<id>.json

Ключи JSON прежние (color_dark/color_light/desktop_icons_hidden/...), чтобы
пресеты старых версий читались как есть. Раскладка — "panels" (см. panel_layout).
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime

from panel_layout import LegacySnapshotConverter, PanelLayout

SYSTEM_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DIR = os.path.expanduser("~/.local/share/EquestriaOS/PanelStyles")
DEFAULT_DAY, DEFAULT_NIGHT = "#dacac1", "#313060"


@dataclass
class Preset:
    id: str
    name: str = ""
    desc_key: str = ""
    desc: str = ""
    icon: str = ""
    char_id: str = ""
    color_day: str = DEFAULT_DAY
    color_night: str = DEFAULT_NIGHT
    opacity: int = 90
    hide_desktop_icons: bool = False
    panels: list = field(default_factory=list)   # раскладка по умолчанию
    layout_captured: str = ""                   # когда снята своя раскладка
    legacy_script: str = ""                     # свои пресеты старых версий без "panels"

    @classmethod
    def from_json(cls, d: dict) -> "Preset":
        legacy = d.get("color")
        return cls(
            id=d["id"], name=d.get("name", ""), desc_key=d.get("desc_key", ""), desc=d.get("desc", ""),
            icon=d.get("icon", ""), char_id=d.get("char_id", ""),
            color_day=d.get("color_light", legacy or DEFAULT_DAY),
            color_night=d.get("color_dark", legacy or DEFAULT_NIGHT),
            opacity=int(d.get("opacity", 90)), hide_desktop_icons=bool(d.get("desktop_icons_hidden", False)),
            panels=d.get("panels", []), layout_captured=d.get("layout_captured", ""),
            legacy_script="" if d.get("panels") else d.get("script", ""),
        )

    def to_json(self) -> dict:
        d = {"id": self.id, "char_id": self.char_id or self.id, "color_dark": self.color_night,
             "color_light": self.color_day, "opacity": self.opacity,
             "desktop_icons_hidden": self.hide_desktop_icons, "panels": self.panels}
        for key in ("name", "desc_key", "desc", "icon", "layout_captured"):
            if getattr(self, key):
                d[key] = getattr(self, key)
        if self.legacy_script and not self.panels:
            d["script"] = self.legacy_script
        return d


class PresetStore:
    def __init__(self, system_dir: str = SYSTEM_DIR, user_dir: str = USER_DIR):
        self.system_file = os.path.join(system_dir, "presets.json")
        self.user_dir = user_dir
        self.user_file = os.path.join(user_dir, "presets.json")
        self.layouts_dir = os.path.join(user_dir, "layouts")
        self.presets: list[Preset] = []

    # ── загрузка / сохранение ──
    @staticmethod
    def _read(path: str) -> list[dict]:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f).get("presets", [])
        except (OSError, ValueError):
            return []

    def system_presets(self) -> dict[str, dict]:
        return {p["id"]: p for p in self._read(self.system_file)}

    def load(self) -> None:
        os.makedirs(self.layouts_dir, exist_ok=True)
        if not os.path.exists(self.user_file) and os.path.exists(self.system_file):
            shutil.copy2(self.system_file, self.user_file)
        system = self.system_presets()
        self.presets = []
        for raw in self._read(self.user_file):
            preset = Preset.from_json(raw)
            # пресеты старых версий: раскладку по умолчанию берём из системного
            if not preset.panels and preset.id in system:
                preset.panels = system[preset.id].get("panels", [])
                preset.legacy_script = ""
            self.presets.append(preset)
        self._migrate_snapshots()

    def save(self) -> None:
        tmp = self.user_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"presets": [p.to_json() for p in self.presets]}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.user_file)

    def get(self, preset_id: str) -> Preset | None:
        return next((p for p in self.presets if p.id == preset_id), None)

    # ── раскладки ──
    def _captured_file(self, preset_id: str) -> str:
        return os.path.join(self.layouts_dir, f"{preset_id}.json")

    def layout_for(self, preset: Preset) -> PanelLayout | None:
        try:
            with open(self._captured_file(preset.id), encoding="utf-8") as f:
                return PanelLayout(json.load(f).get("panels", []))
        except (OSError, ValueError):
            pass
        return PanelLayout(preset.panels) if preset.panels else None

    def save_captured(self, preset_id: str, layout: PanelLayout) -> str:
        with open(self._captured_file(preset_id), "w", encoding="utf-8") as f:
            json.dump(layout.to_json(), f, indent=2, ensure_ascii=False)
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def drop_captured(self, preset_id: str) -> None:
        path = self._captured_file(preset_id)
        if os.path.exists(path):
            os.remove(path)

    def _migrate_snapshots(self) -> None:
        """Снимки старых версий (.bak — копия всего конфига Plasma) переводятся
        в раскладку; сами файлы переезжают в layouts/legacy-backup."""
        backup = os.path.join(self.layouts_dir, "legacy-backup")
        converter = LegacySnapshotConverter()
        for name in os.listdir(self.layouts_dir):
            if not name.endswith(".bak"):
                continue
            pid, bak = name[:-4], os.path.join(self.layouts_dir, name)
            shellrc = bak + "_shellrc"
            if not os.path.exists(self._captured_file(pid)):
                layout = converter.convert(bak, shellrc if os.path.exists(shellrc) else None)
                if layout.panels:
                    self.save_captured(pid, layout)
            os.makedirs(backup, exist_ok=True)
            for path in (bak, shellrc):
                if os.path.exists(path):
                    shutil.move(path, os.path.join(backup, os.path.basename(path)))

    # ── изменение набора ──
    def has_default(self, preset_id: str) -> bool:
        return preset_id in self.system_presets()

    def restore_default(self, preset_id: str) -> Preset | None:
        raw = self.system_presets().get(preset_id)
        if not raw:
            return None
        self.drop_captured(preset_id)
        fresh = Preset.from_json(raw)
        self.presets = [fresh if p.id == preset_id else p for p in self.presets]
        self.save()
        return fresh

    def restore_all(self) -> None:
        for name in os.listdir(self.layouts_dir):
            if name.endswith(".json"):
                os.remove(os.path.join(self.layouts_dir, name))
        if os.path.exists(self.system_file):
            shutil.copy2(self.system_file, self.user_file)
        self.load()

    def add(self, preset: Preset) -> None:
        self.presets.append(preset)
        self.save()

    def delete(self, preset_id: str) -> None:
        self.presets = [p for p in self.presets if p.id != preset_id]
        self.drop_captured(preset_id)
        self.save()
