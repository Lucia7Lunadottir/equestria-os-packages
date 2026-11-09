"""closer: settings."""
from __future__ import annotations

from equestria_kit.widgets import load_typed_config
from .entries import MODES
from .paths import CONFIG
from .style import DEFAULT_THEME


DEFAULTS = {"theme": DEFAULT_THEME, "view": "apps", "tree": True, "hide": True, "confirm": True, "reveal": True}


def load_config() -> dict:
    cfg = load_typed_config(CONFIG, DEFAULTS)
    if cfg["view"] not in MODES:
        cfg["view"] = "apps"
    return cfg
