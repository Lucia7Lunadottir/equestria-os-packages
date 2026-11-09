"""calc: paths."""
from __future__ import annotations

import os
from pathlib import Path


CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-calc" / "settings.json"
