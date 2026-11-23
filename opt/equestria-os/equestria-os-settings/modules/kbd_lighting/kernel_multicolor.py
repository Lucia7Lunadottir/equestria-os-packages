"""Any laptop whose keyboard backlight is a standard kernel multicolor LED. EXPERIMENTAL: written from the kernel
documentation, not yet tried on a real laptop (docs.kernel.org/leds/leds-class-multicolor.html).

The LED directory name ends in ":kbd_backlight" and has:
  multi_index          colour order, e.g. "green blue red"
  multi_intensity      one integer per colour, all written together
  multi_max_intensity  the most each colour accepts (e.g. 50 on Uniwill/TUXEDO)
Only a static colour: such LEDs have no built-in animations. The overall brightness (`brightness`) is the
page's brightness-level slider and is not touched here.
"""

import os

from . import base
from .access import Access
from .base import STATIC, Effect, RgbBackend, RgbSetting

_CHANNELS = ("red", "green", "blue")


def _read(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


class KernelMulticolorBackend(RgbBackend):
    id = "kernel_multicolor"
    priority = 50
    experimental = True
    can_unlock_direct_access = True

    def __init__(self, access: Access, led_dir: str):
        self.access, self.led_dir = access, led_dir

    @classmethod
    def detect(cls, access: Access) -> "KernelMulticolorBackend | None":
        for led in base.led_dirs():
            if os.path.exists(os.path.join(led, "multi_intensity")) and os.path.exists(os.path.join(led, "multi_index")):
                return cls(access, led)
        return None

    def effects(self) -> tuple[Effect, ...]:
        return (STATIC,)

    @property
    def silent(self) -> bool:
        return self.access.can_write_directly(self.led_dir, "multi_intensity")

    def _values(self, rgb: tuple[int, int, int]) -> str | None:
        order = (_read(os.path.join(self.led_dir, "multi_index")) or "").split()
        if not order:
            return None
        maxima = (_read(os.path.join(self.led_dir, "multi_max_intensity")) or "").split()
        wanted = dict(zip(_CHANNELS, rgb))
        out = []
        for i, name in enumerate(order):
            top = int(maxima[i]) if i < len(maxima) and maxima[i].isdigit() else 255
            out.append(str(round(wanted.get(name, 0) * top / 255)))    # a colour we have no value for (white…) stays off
        return " ".join(out)

    def apply(self, setting: RgbSetting, save: bool = False) -> bool:
        if setting.effect != STATIC.id:
            return False
        try:
            values = self._values(setting.scaled_rgb())
        except ValueError:
            return False
        return values is not None and self.access.write_led_attr(self.led_dir, "multi_intensity", values)
