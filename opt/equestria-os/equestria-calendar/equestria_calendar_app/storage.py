"""calendar: storage."""
from __future__ import annotations

import json
import os
from .localization import catalog
from .paths import CONF_DIR, DATA_FILE


DEFAULT_SETTINGS = {"theme": "Catppuccin Mocha", "view": "month", "sunday_first": False,
                    "show_moon": True, "sound": "sounds.bell", "custom_sound": "", "volume": 80,
                    "repeat_sound": True, "allday_time": "09:00", "tray": True}


def _sound_key(value: str) -> str:
    """Старые версии сохраняли звук его русским (или переведённым) названием — вернуть ключ звука."""
    from .sounds import SOUND_SPECS
    if value in SOUND_SPECS:
        return value
    for key in SOUND_SPECS:
        if any(entries.get(key) == value for entries in catalog.translations.values()):
            return key
    return DEFAULT_SETTINGS["sound"]


class Store:
    def __init__(self):
        self.settings = dict(DEFAULT_SETTINGS)
        self.reminders: list = []
        self.fired: dict = {}
        self.snoozed: list = []
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        for k, dv in DEFAULT_SETTINGS.items():
            v = raw.get("settings", {}).get(k)
            if v is not None and type(v) is type(dv):
                self.settings[k] = v
        self.settings["sound"] = _sound_key(self.settings["sound"])
        self.reminders = [r for r in raw.get("reminders", []) if isinstance(r, dict) and "id" in r and "date" in r]
        self.fired = raw.get("fired", {}) if isinstance(raw.get("fired"), dict) else {}
        self.snoozed = [s for s in raw.get("snoozed", []) if isinstance(s, dict)]

    def save(self) -> None:
        try:
            CONF_DIR.mkdir(parents=True, exist_ok=True)
            tmp = str(DATA_FILE) + ".tmp~"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"settings": self.settings, "reminders": self.reminders,
                           "fired": self.fired, "snoozed": self.snoozed}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, DATA_FILE)
        except OSError:
            pass
