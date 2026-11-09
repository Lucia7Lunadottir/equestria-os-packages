"""clock: paths."""
from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "equestria-clock"


CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP_NAME


CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / APP_NAME
