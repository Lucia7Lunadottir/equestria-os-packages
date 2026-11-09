"""color-picker: settings."""
from __future__ import annotations

from equestria_kit.widgets import load_typed_config
from .formats import DEFAULT_PRIMARY
from .paths import CONFIG
from .style import DEFAULT_THEME


DEFAULTS = {"theme": DEFAULT_THEME, "primary": DEFAULT_PRIMARY, "precision": 3, "trim": True,
            "upper": True, "autocopy": True, "hide": True, "history": [], "customs": [], "color": "cba6f7ff"}


def load_config() -> dict:
    cfg = load_typed_config(CONFIG, DEFAULTS)
    cfg["customs"] = [c for c in cfg["customs"]
                      if isinstance(c, dict) and {"id", "name", "tpl"} <= c.keys()]
    return cfg
