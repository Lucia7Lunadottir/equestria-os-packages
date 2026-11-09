"""notes: paths."""
from __future__ import annotations

import os
from pathlib import Path


CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-notes" / "settings.json"


EXTS = (".md", ".markdown", ".txt")


GLOBAL, FILES = "global", "@files"
