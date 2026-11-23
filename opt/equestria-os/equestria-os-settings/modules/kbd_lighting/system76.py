"""System76 laptops (kernel driver system76_acpi). EXPERIMENTAL: written from the driver's source, not yet
tried on a real laptop.

/sys/class/leds/system76_acpi::kbd_backlight/color holds the colour as six hex digits "RRGGBB" (max FFFFFF);
`brightness` (0..255) next to it is the page's brightness-level slider and is not touched here.
Only a static colour: the driver has no animations.
"""

import os

from . import base
from .access import Access
from .base import STATIC, Effect, RgbBackend, RgbSetting

_LED_NAME = "system76_acpi::kbd_backlight"


class System76Backend(RgbBackend):
    id = "system76"
    priority = 60
    experimental = True
    can_unlock_direct_access = True

    def __init__(self, access: Access, led_dir: str):
        self.access, self.led_dir = access, led_dir

    @classmethod
    def detect(cls, access: Access) -> "System76Backend | None":
        for led in base.led_dirs(_LED_NAME):
            if os.path.exists(os.path.join(led, "color")):
                return cls(access, led)
        return None

    def effects(self) -> tuple[Effect, ...]:
        return (STATIC,)

    @property
    def silent(self) -> bool:
        return self.access.can_write_directly(self.led_dir, "color")

    def apply(self, setting: RgbSetting, save: bool = False) -> bool:
        if setting.effect != STATIC.id:
            return False
        try:
            r, g, b = setting.scaled_rgb()
        except ValueError:
            return False
        return self.access.write_led_attr(self.led_dir, "color", "%02X%02X%02X" % (r, g, b))
