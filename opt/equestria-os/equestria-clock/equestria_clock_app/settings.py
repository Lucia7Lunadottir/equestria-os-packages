"""clock: settings."""
from __future__ import annotations

import json
import sys
from .paths import CONFIG_DIR
from .style import DEFAULT_THEME


DEFAULT_SETTINGS = {
    "theme": DEFAULT_THEME,
    "sound": "builtin:chime",
    "volume": 80,
    "snooze": 5,
    "tray": True,
    "timer": [0, 5, 0],
    "alarms": [],
}


class Settings:
    def __init__(self):
        self.path = CONFIG_DIR / "settings.json"
        self.data = json.loads(json.dumps(DEFAULT_SETTINGS))
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        for k in DEFAULT_SETTINGS:
            if k in raw:
                self.data[k] = raw[k]
        good = []
        for a in self.data["alarms"]:
            try:
                h, m = map(int, str(a["time"]).split(":"))
                assert 0 <= h < 24 and 0 <= m < 60
                good.append({
                    "time": f"{h:02d}:{m:02d}",
                    "label": str(a.get("label", "")),
                    "days": sorted({int(d) for d in a.get("days", []) if 0 <= int(d) <= 6}),
                    "enabled": bool(a.get("enabled", True)),
                    "sound": str(a.get("sound", "")),
                })
            except Exception:
                continue
        self.data["alarms"] = good

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(self.path)
        except Exception as e:
            print("Could not save settings:", e, file=sys.stderr)

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v
