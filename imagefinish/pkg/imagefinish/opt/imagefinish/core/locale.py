"""
Localization module.

Usage:
    from core.locale import tr
    label = tr("menu.file")

Adding a new language:
    Drop a JSON file into the  locales/  folder (e.g. locales/de.json).
    It will appear automatically in the Language menu on next launch.
"""

import json
import os
from glob import glob

_APP_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCALES_DIR  = os.path.join(_APP_DIR, "locales")
_SETTINGS_FILE = os.path.join(_APP_DIR, "settings.json")

_strings: dict = {}
_current: str  = "en"


# ── Public API ────────────────────────────────────────────────────────────────

def tr(key: str, **kwargs) -> str:
    """Return translated string; falls back to key itself."""
    text = _strings.get(key, key)
    return text.format(**kwargs) if kwargs else text


def available_languages() -> list[tuple[str, str]]:
    """Return [(code, native_name), ...] for all *.json files in locales/."""
    result = []
    for path in sorted(glob(os.path.join(_LOCALES_DIR, "*.json"))):
        code = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("_name", code)
        except Exception:
            name = code
        result.append((code, name))
    return result


def load(lang: str) -> bool:
    """Load locale *lang*. Returns True on success."""
    global _strings, _current
    path = os.path.join(_LOCALES_DIR, f"{lang}.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            _strings = json.load(f)
        _current = lang
        _save_setting(lang)
        return True
    except Exception:
        return False


def current() -> str:
    return _current


# ── Internal ─────────────────────────────────────────────────────────────────

def _save_setting(lang: str) -> None:
    try:
        data: dict = {}
        if os.path.exists(_SETTINGS_FILE):
            with open(_SETTINGS_FILE, encoding="utf-8") as f:
                data = json.load(f)
        data["language"] = lang
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_setting() -> str:
    try:
        if os.path.exists(_SETTINGS_FILE):
            with open(_SETTINGS_FILE, encoding="utf-8") as f:
                return json.load(f).get("language", "en")
    except Exception:
        pass
    return "en"


# Auto-load on import
load(_load_setting())
