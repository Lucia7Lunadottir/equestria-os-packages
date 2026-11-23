"""ASUS ROG keyboards driven by asusd (`asusctl aura effect ...`). NOT tried on a real ROG laptop.

Used where the kernel cannot colour the keyboard. Needs a running asusd; works without a password.
asusd remembers the effect by itself, so there is no separate "save into the laptop" step.
"""

import shutil
import subprocess

from .access import Access
from .base import EFFECTS, EFFECTS_BY_ID, Effect, RgbBackend, RgbSetting

_SPEED_WORDS = ("low", "med", "high")


class AsusctlBackend(RgbBackend):
    id = "asusctl"
    priority = 20
    experimental = True

    @classmethod
    def detect(cls, access: Access) -> "AsusctlBackend | None":
        if shutil.which("asusctl") is None:
            return None
        try:
            r = subprocess.run(["systemctl", "is-active", "asusd.service"],
                               capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return None
        return cls() if r.stdout.strip() == "active" else None

    def effects(self) -> tuple[Effect, ...]:
        return EFFECTS

    @property
    def silent(self) -> bool:
        return True

    def apply(self, setting: RgbSetting, save: bool = False) -> bool:
        effect = EFFECTS_BY_ID.get(setting.effect)
        if effect is None:
            return False
        argv = ["asusctl", "aura", "effect", effect.asusctl]
        if effect.uses_color:
            try:
                argv += ["--colour", "%02x%02x%02x" % setting.scaled_rgb()]
            except ValueError:
                return False
        if effect.uses_speed and effect.id != "static":
            argv += ["--speed", _SPEED_WORDS[min(2, max(0, setting.speed))]]
        try:
            return subprocess.run(argv, capture_output=True, timeout=10).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
