"""Picks the backend for this laptop; the settings page, the theme service and the theme editor use only this."""

import importlib
import inspect
import os
import pkgutil
import time

from .access import RULE_PATH, Access
from .base import RgbBackend, RgbSetting, SettingsStore

_NOT_BACKENDS = {"base", "access", "controller"}


def backend_classes() -> list[type[RgbBackend]]:
    """Every backend in this package (one class per file), the one tried first at the front."""
    package = importlib.import_module(__package__)
    found = []
    for info in pkgutil.iter_modules(package.__path__):
        if info.name in _NOT_BACKENDS or info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__package__}.{info.name}")
        found += [c for _, c in inspect.getmembers(module, inspect.isclass)
                  if issubclass(c, RgbBackend) and c is not RgbBackend and c.__module__ == module.__name__]
    return sorted(found, key=lambda c: (c.priority, c.id))


class RgbController:
    def __init__(self, store: SettingsStore | None = None, access: Access | None = None):
        self.store = store or SettingsStore()
        self.access = access or Access()
        self.helper = self.access.helper          # the root helper (kept under its old name for the callers)
        self.backend: RgbBackend | None = self._pick_backend()

    def _pick_backend(self) -> RgbBackend | None:
        for cls in backend_classes():
            try:
                backend = cls.detect(self.access)
            except Exception:       # a broken backend must never stop the others or the page
                backend = None
            if backend is not None:
                return backend
        return None

    def refresh(self) -> None:
        """Re-detect (the udev rule may have been added or removed)."""
        self.backend = self._pick_backend()

    # -- direct (no password) access -----------------------------------------

    @staticmethod
    def direct_access_enabled() -> bool:
        return os.path.exists(RULE_PATH)

    def set_direct_access(self, enable: bool) -> bool:
        ok = self.helper.set_direct_access(enable)
        if ok and enable:
            for _ in range(20):             # udev applies the new permissions asynchronously
                self.refresh()
                if self.backend is not None and self.backend.silent:
                    break
                time.sleep(0.1)
        self.refresh()
        return ok

    # -- applying -------------------------------------------------------------

    def resolve(self, setting: RgbSetting) -> RgbSetting:
        """An effect this keyboard cannot draw is never swapped for another
        animation: the keyboard just gets the plain colour (static)."""
        if self.backend is None:
            return setting
        if any(e.id == setting.effect for e in self.backend.effects()):
            return setting
        return setting.with_(effect="static")

    def apply(self, setting: RgbSetting, save: bool = False) -> bool:
        if self.backend is None:
            return False
        return self.backend.apply(self.resolve(setting), save)

    def close(self) -> None:
        self.access.close()
