from __future__ import annotations

import os
from pathlib import Path


APP = "equestria-unreal"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / APP
INSTALL_INI = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "Epic" / "UnrealEngine" / "Install.ini"
