"""notes: settings."""
from __future__ import annotations

from equestria_kit.widgets import load_typed_config
from .paths import CONFIG, GLOBAL
from .style import DEFAULT_THEME


DEFAULTS = {"theme": DEFAULT_THEME, "mode": "visual", "source": GLOBAL, "folders": [], "files": [], "last": ""}


def load_config() -> dict:
    cfg = load_typed_config(CONFIG, DEFAULTS)
    cfg["folders"] = [p for p in cfg["folders"] if isinstance(p, str)]
    cfg["files"] = [p for p in cfg["files"] if isinstance(p, str)]
    if cfg["mode"] not in ("visual", "source"):
        cfg["mode"] = "visual"
    return cfg
