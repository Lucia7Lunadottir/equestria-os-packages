"""calendar: paths."""
from __future__ import annotations

import os
from pathlib import Path


CONF_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-calendar"


DATA_FILE = CONF_DIR / "calendar.json"
