"""
settings.py — Equestria OS Software Center
Manages persistent user preferences: language, update flags, source enable/disable.

Config file location: ~/.config/equestria-os-software-center/settings.json
"""

import os
import json
import locale
import subprocess

_CONFIG_DIR = os.path.join(
    os.path.expanduser("~"), ".config", "equestria-os-software-center"
)
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "settings.json")

_DEFAULTS = {
    # Language code, e.g. "en", "ru". Empty string means "detect from system".
    "language": "",

    # Update flags — which sources to include when running system update
    "update_pacman": True,
    "update_aur": True,
    "update_flatpak": True,

    # Source enable flags — whether to load / show each source at all
    "enable_aur": True,
    "enable_flatpak": True,
}


def _detect_system_lang(available_langs: list[str]) -> str:
    """Try to detect the system language and return the best matching code.

    Priority:
    1. $LANGUAGE env var (colon-separated list, e.g. "ru:en")
    2. $LANG env var (e.g. "ru_RU.UTF-8")
    3. `locale` command output
    Fallback: "en"
    """
    candidates = []

    # $LANGUAGE can hold multiple codes separated by colons
    env_language = os.environ.get("LANGUAGE", "")
    for part in env_language.split(":"):
        code = part.split("_")[0].split(".")[0].lower().strip()
        if code:
            candidates.append(code)

    # $LANG: "ru_RU.UTF-8" → "ru"
    env_lang = os.environ.get("LANG", "")
    code = env_lang.split("_")[0].split(".")[0].lower().strip()
    if code and code != "c" and code != "posix":
        candidates.append(code)

    # Try Python's own locale
    try:
        loc = locale.getdefaultlocale()[0] or ""
        code = loc.split("_")[0].lower()
        if code:
            candidates.append(code)
    except Exception:
        pass

    # Try `locale` command
    try:
        res = subprocess.run(["locale"], capture_output=True, text=True, timeout=2)
        for line in res.stdout.splitlines():
            if line.startswith("LANG="):
                code = line.split("=")[1].split("_")[0].split(".")[0].lower().strip()
                if code and code not in ("c", "posix"):
                    candidates.append(code)
                break
    except Exception:
        pass

    # First candidate that matches an available locale file wins
    for c in candidates:
        if c in available_langs:
            return c

    # Partial match: "zh" matches "zh_CN"
    for c in candidates:
        for lang in available_langs:
            if lang.startswith(c):
                return lang

    return "en"


def load_settings() -> dict:
    """Load settings from disk. Missing keys are filled with defaults."""
    settings = dict(_DEFAULTS)
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, encoding="utf-8") as f:
                on_disk = json.load(f)
            for key, default in _DEFAULTS.items():
                if key in on_disk:
                    # Type-check: keep default if type doesn't match
                    if isinstance(on_disk[key], type(default)) or on_disk[key] is None:
                        settings[key] = on_disk[key]
        except Exception:
            pass
    return settings


def save_settings(settings: dict) -> None:
    """Persist settings to disk. Creates directory if needed."""
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    to_save = {k: settings.get(k, v) for k, v in _DEFAULTS.items()}
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def resolve_language(settings: dict, available_langs: list[str]) -> str:
    """Return the language code to use, detecting from system if not set."""
    lang = settings.get("language", "")
    if lang and lang in available_langs:
        return lang
    detected = _detect_system_lang(available_langs)
    return detected if detected in available_langs else "en"
