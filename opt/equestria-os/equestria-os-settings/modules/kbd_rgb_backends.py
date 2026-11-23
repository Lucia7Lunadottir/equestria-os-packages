"""Compatibility layer: the keyboard-lighting code now lives in the `kbd_lighting` package (one backend per file).

The settings page, the theme service, the theme editor's preview helper and the tests keep importing the
old names from here; new code should import from `kbd_lighting` directly.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kbd_lighting import base as _base  # noqa: E402
from kbd_lighting.access import HELPER_PATH, RULE_PATH, Access, HelperChannel, WriteChannel  # noqa: E402,F401
from kbd_lighting.asus_wmi import KERNEL_VERIFIED, DirectChannel, KernelWmiBackend, kernel_file  # noqa: E402,F401
from kbd_lighting.asusctl import AsusctlBackend  # noqa: E402,F401
from kbd_lighting.base import (EFFECTS, EFFECTS_BY_ID, Effect, RgbBackend, RgbSetting,  # noqa: E402,F401
                               SettingsStore, config_dir, firmware_look, parse_hex)
from kbd_lighting.controller import RgbController, backend_classes  # noqa: E402,F401
