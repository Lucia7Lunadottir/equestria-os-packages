"""Where Unity keeps things on Linux, and where the launcher finds programs. Read at call time, so tests can move them."""
import json
import os
import shutil
from pathlib import Path

HUB = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "unityhub"
DEFAULT_ROOT = Path.home() / "Unity/Hub/Editor"


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def executable(name):
    """A program from PATH, or from ~/.local/bin where the launcher installs the Unity CLI."""
    found = shutil.which(name)
    if not found:
        candidate = Path.home() / ".local/bin" / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            found = str(candidate)
    return found
