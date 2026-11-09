"""Настройки диктофона в JSON-файле."""
from __future__ import annotations

import json
from pathlib import Path


class SettingsStore:
    """Читает и пишет словарь настроек; повреждённый или чужой файл — пустые настройки."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        try:
            cfg = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return cfg if isinstance(cfg, dict) else {}

    def save(self, cfg: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
