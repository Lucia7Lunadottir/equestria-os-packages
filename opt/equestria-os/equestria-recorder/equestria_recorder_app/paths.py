"""Пути диктофона."""
from __future__ import annotations

import os
from pathlib import Path

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-recorder" / "settings.json"


def default_folder() -> Path:
    """Папка записей по умолчанию: ~/Music, если она есть, иначе домашняя."""
    music = Path.home() / "Music"
    return music if music.is_dir() else Path.home()
