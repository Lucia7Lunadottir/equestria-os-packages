"""Keyboard lighting — what the user picks, how it is remembered, and what a backend is (no Qt, no hardware).

One backend = one way of talking to one kind of laptop, one file in this package (see KEYBOARD-BACKENDS.md).
Nothing here knows about a brand: the settings page, the theme service and the theme editor use only these types.
"""

import glob
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, replace
from pathlib import Path

LEDS_ROOT = "/sys/class/leds"      # tests point this at a fake tree


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-os"


def led_dirs(pattern: str = "*kbd_backlight*") -> list[str]:
    """LED class directories of keyboard backlights (a kernel naming rule: the name ends in :kbd_backlight)."""
    return sorted(p for p in glob.glob(os.path.join(LEDS_ROOT, pattern)) if os.path.isdir(p))


# ── What the user picks ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Effect:
    id: str
    label_key: str
    kernel_mode: int | None   # asus-wmi mode number; None = that interface cannot do it
    asusctl: str              # asusctl aura effect <name>
    uses_color: bool
    uses_speed: bool


EFFECTS: tuple[Effect, ...] = (
    Effect("static",        "kbd_backlight.effect_static",        0,    "static",        True,  False),
    Effect("breathe",       "kbd_backlight.effect_breathe",       1,    "breathe",       True,  True),
    Effect("rainbow_cycle", "kbd_backlight.effect_rainbow_cycle", 2,    "rainbow-cycle", False, True),
    Effect("rainbow_wave",  "kbd_backlight.effect_rainbow_wave",  3,    "rainbow-wave",  False, True),
    Effect("stars",         "kbd_backlight.effect_stars",         4,    "stars",         True,  True),
    Effect("rain",          "kbd_backlight.effect_rain",          5,    "rain",          False, True),
    Effect("highlight",     "kbd_backlight.effect_highlight",     6,    "highlight",     True,  True),
    Effect("laser",         "kbd_backlight.effect_laser",         7,    "laser",         True,  True),
    Effect("ripple",        "kbd_backlight.effect_ripple",        8,    "ripple",        True,  True),
    Effect("pulse",         "kbd_backlight.effect_pulse",         10,   "pulse",         True,  False),
    Effect("comet",         "kbd_backlight.effect_comet",         11,   "comet",         True,  False),
    Effect("flash",         "kbd_backlight.effect_flash",         None, "flash",         True,  False),
)
EFFECTS_BY_ID = {e.id: e for e in EFFECTS}
STATIC = EFFECTS_BY_ID["static"]


def parse_hex(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) != 6:
        raise ValueError(f"bad colour {color!r}")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


@dataclass(frozen=True)
class RgbSetting:
    effect: str = "static"
    color: str = "#ff1362"
    speed: int = 1            # 0 slow, 1 medium, 2 fast
    follow_theme: bool = False
    intensity: int = 100      # 1..100 %: "virtual" brightness — scales the colour itself

    def scaled_rgb(self) -> tuple[int, int, int]:
        r, g, b = parse_hex(self.color)
        k = min(100, max(1, self.intensity)) / 100
        return round(r * k), round(g * k), round(b * k)

    def with_(self, **changes) -> "RgbSetting":
        return replace(self, **changes)


class SettingsStore:
    """~/.config/equestria-os/kbd-rgb.json — the page's settings and a record of what the keyboard remembers."""

    def __init__(self, path: Path | None = None):
        self.path = path or config_dir() / "kbd-rgb.json"

    def load(self) -> RgbSetting:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            base = RgbSetting()
            effect = data.get("effect", base.effect)
            color = data.get("color", base.color)
            parse_hex(color)
            speed = int(data.get("speed", base.speed))
            return RgbSetting(
                effect if effect in EFFECTS_BY_ID else base.effect, color,
                min(2, max(0, speed)), bool(data.get("follow_theme", False)),
                min(100, max(1, int(data.get("intensity", base.intensity)))))
        except (OSError, ValueError, TypeError, AttributeError):
            return RgbSetting()

    def _read_raw(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_raw(self, data: dict) -> None:
        """Atomic: the theme service and the preview helper read this file at any moment."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def save(self, setting: RgbSetting) -> None:
        """Remember the page's settings (colour, effect, speed, virtual brightness, follow-theme).
        Other keys of the file (what is written in the keyboard) are kept."""
        data = self._read_raw()
        data.update(asdict(setting))
        self._write_raw(data)

    def load_in_keyboard(self) -> dict | None:
        """The look last written into the keyboard's own memory (cmd 1) by this program; None — never."""
        value = self._read_raw().get("in_keyboard")
        return value if isinstance(value, dict) else None

    def save_in_keyboard(self, look: dict) -> None:
        data = self._read_raw()
        data["in_keyboard"] = look
        self._write_raw(data)


def firmware_look(setting: RgbSetting) -> dict:
    """What the keyboard would show for this setting, reduced to what really matters for the effect
    (an effect without a colour has no colour/brightness; one without speed has no speed)."""
    effect = EFFECTS_BY_ID.get(setting.effect)
    look = {"effect": setting.effect}
    if effect is None or effect.uses_color:
        look["color"] = "#%02x%02x%02x" % setting.scaled_rgb()
    if effect is not None and effect.uses_speed:
        look["speed"] = setting.speed
    return look


# ── What a backend is ─────────────────────────────────────────────────────────

class RgbBackend(ABC):
    """One way of controlling one kind of laptop's keyboard colour. One subclass per file in this package."""

    id: str = ""
    priority: int = 100                 # lower is tried first (a laptop with two interfaces uses the first that fits)
    experimental: bool = False          # written from documentation, not yet tried on a real laptop of that kind
    firmware_save: bool = False         # can the look be written into the laptop's own memory (survives power-off)?
    can_unlock_direct_access: bool = False   # does the optional "no password" udev rule apply to this backend?

    @classmethod
    @abstractmethod
    def detect(cls, access) -> "RgbBackend | None":
        """An instance if this laptop has the hardware this backend drives, else None.
        `access` is a kbd_lighting.access.Access (root helper, direct writes)."""

    @abstractmethod
    def effects(self) -> tuple[Effect, ...]: ...

    @abstractmethod
    def apply(self, setting: RgbSetting, save: bool = False) -> bool: ...

    @property
    @abstractmethod
    def silent(self) -> bool:
        """True when applying never asks for a password (theme following needs this)."""
