from __future__ import annotations

import json
import os
from pathlib import Path

from equestria_ue.paths import CACHE_DIR, CONFIG_DIR


DEFAULTS = {
    "lang": "",                          # язык интерфейса; "" — как в системе
    "engines": [],                       # [{"id": "{GUID}", "path": "...", "name": ""}]
    "project_dirs": [str(Path.home() / "Documents" / "Unreal Projects"), str(Path.home() / "UnrealProjects")],
    "extra_projects": [],                # проекты, открытые вручную
    "install_dir": str(Path.home() / "UnrealEngines"),
    "access": "ssh",                     # ssh | https
    "sdl": "x11" if os.environ.get("XDG_SESSION_TYPE") == "wayland" else "auto",
    "args": "",
    "sync_ini": True,
    "deps": True,
    "ddc": str(CACHE_DIR / "DDC"),       # папка Derived Data Cache (общий кеш шейдеров и ассетов)
    "no_tooltips": True,                 # обход бага UE 5.7 на KDE/Xwayland: подсказки крадут фокус, клик проходит со 2-го раза
    "prime": False,                      # гибридный ноутбук: запускать редактор на дискретной NVIDIA
    "ddc_mode": "auto",                  # auto | zen | files | memory — см. launcher.DdcPolicy
    "shader_threads": "fast",            # fast — почти все потоки на шейдеры; ue — как в Unreal (половина)
    "tray": True,
    "cef_gpu": False,                    # встроенный браузер Unreal (Fab) на GPU: на Linux его GPU-процесс падает по кругу
    "ray_tracing": "project",            # project — как в проекте; off — без трассировки лучей в редакторе                        # закрытие окна сворачивает в трей: загрузки и сборка продолжаются
}


class Config:
    def __init__(self):
        self.path = CONFIG_DIR / "settings.json"
        self.data = json.loads(json.dumps(DEFAULTS))
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for k, dv in DEFAULTS.items():
                if k in raw and type(raw[k]) is type(dv):
                    self.data[k] = raw[k]
        except Exception:
            pass
        self.data["engines"] = [e for e in self.data["engines"] if isinstance(e, dict) and "path" in e and "id" in e]

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v
