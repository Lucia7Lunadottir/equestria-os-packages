"""ASUS TUF and some ROG laptops, through the kernel's asus-wmi driver (verified on a TUF Gaming F15).

The driver offers /sys/class/leds/*kbd_backlight*/kbd_rgb_mode: "<cmd> <mode> <r> <g> <b> <speed>"
(cmd 0 = apply now, cmd 1 = apply and save in the laptop's BIOS). The file is writable by root only.
"""

import os

from . import base
from .access import Access, HelperChannel, WriteChannel
from .base import EFFECTS, EFFECTS_BY_ID, Effect, RgbBackend, RgbSetting

# Effects the keyboard firmware really draws through this interface. Checked by hand on an ASUS TUF Gaming F15
# (FX507VV): the driver also accepts others, but that keyboard does not draw them.
KERNEL_VERIFIED = frozenset({"static", "breathe", "rainbow_cycle", "pulse"})


def kernel_file() -> str | None:
    for led in base.led_dirs():
        path = os.path.join(led, "kbd_rgb_mode")
        if os.path.exists(path):
            return path
    return None


class DirectChannel(WriteChannel):
    """Plain write into kbd_rgb_mode: works when the optional udev rule made the file writable."""

    silent = True

    @staticmethod
    def usable() -> bool:
        path = kernel_file()
        return path is not None and os.access(path, os.W_OK)

    def write_rgb(self, cmd, mode, rgb, speed) -> bool:
        path = kernel_file()
        if path is None:
            return False
        try:
            with open(path, "w") as f:
                f.write(f"{cmd} {mode} {rgb[0]} {rgb[1]} {rgb[2]} {speed}\n")
            return True
        except OSError:
            return False


class KernelWmiBackend(RgbBackend):
    id = "asus_wmi"
    priority = 10
    firmware_save = True                # cmd 1 writes the look into the laptop's memory
    can_unlock_direct_access = True

    def __init__(self, channel: WriteChannel):
        self.channel = channel

    @classmethod
    def detect(cls, access: Access) -> "KernelWmiBackend | None":
        if kernel_file() is None:
            return None
        return cls(DirectChannel() if DirectChannel.usable() else access.helper)

    def effects(self) -> tuple[Effect, ...]:
        return tuple(e for e in EFFECTS if e.id in KERNEL_VERIFIED and e.kernel_mode is not None)

    @property
    def silent(self) -> bool:
        return self.channel.silent

    def apply(self, setting: RgbSetting, save: bool = False) -> bool:
        effect = EFFECTS_BY_ID.get(setting.effect)
        if effect is None or effect.kernel_mode is None:
            return False
        try:
            rgb = setting.scaled_rgb()
        except ValueError:
            return False
        return self.channel.write_rgb(1 if save else 0, effect.kernel_mode, rgb, setting.speed)
