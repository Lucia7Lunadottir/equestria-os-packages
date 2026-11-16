"""The one place where launcher settings live.

Every setting is declared once below with its type and default. The rest of the program reads with
`store.get(key)` and writes with `store.set(key, value)`: values are checked on the way in, copies are
returned so nobody changes the stored data by accident, the file is saved after every change and
`changed(key)` tells the windows to update themselves. A broken or hand-edited settings file cannot
crash the launcher: a value of the wrong type is replaced by its default.
"""
import copy
from dataclasses import dataclass
from typing import Any, Callable

from PyQt6.QtCore import QObject, pyqtSignal

NOTHING = object()


def _strings(value):
    return all(isinstance(item, str) for item in value)


def _text_map(value):
    return all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())


def _number_map(value):
    return all(isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool) for k, v in value.items())


def _dict_map(value):
    return all(isinstance(k, str) and isinstance(v, dict) for k, v in value.items())


@dataclass(frozen=True)
class Field:
    types: tuple
    default: Any
    valid: Callable[[Any], bool] = lambda value: True

    def accepts(self, value):
        if isinstance(value, bool) and bool not in self.types:
            return False  # True/False must not pass for numbers
        return isinstance(value, self.types) and (value is None or self.valid(value))

    def fresh(self):
        return copy.deepcopy(self.default)


NONE = type(None)
FIELDS = {
    # projects
    "projects": Field((list,), [], _strings),            # projects added by hand
    "hidden": Field((list,), [], _strings),              # projects removed from the list
    "favorites": Field((list,), [], _strings),
    "opened": Field((dict,), {}, _number_map),           # path -> time it was last opened
    "scan_dirs": Field((list, NONE), None, lambda v: _strings(v)),  # None = not chosen yet, use the usual folders
    "scan_depth": Field((int,), 3, lambda v: 1 <= v <= 8),
    "sort_key": Field((str,), "recent", lambda v: v in ("recent", "name", "version", "favorite")),
    "sort_down": Field((bool,), True),
    "project_arguments": Field((dict,), {}, _text_map),
    # editors and downloads
    "editor_root": Field((str, NONE), None),
    "editors": Field((dict,), {}, _text_map),            # editors added by hand: version -> path
    "editor_profiles": Field((dict,), {}, _dict_map),
    "download_dir": Field((str,), ""),                   # "" = the system temporary folder
    "install_retries": Field((int, NONE), None, lambda v: 0 <= v <= 10),
    "template_root": Field((str, NONE), None),
    "no_confirm_remove": Field((bool,), False),
    # launching
    "arguments": Field((str,), ""),
    "renderer": Field((str,), "", lambda v: v in ("", "-force-vulkan", "-force-glcore")),
    # look and behaviour
    "themes": Field((dict,), {}, _dict_map),
    "tray_projects": Field((bool,), True),
    "editor_to_tray": Field((bool,), False),
    "close_to_tray": Field((bool,), True),
    "job_notifications": Field((bool,), True),
    "banners_enabled": Field((bool,), True),
    "dismissed_banners": Field((list,), [], _strings),
}


class Store(QObject):
    changed = pyqtSignal(str)   # the key that changed
    failed = pyqtSignal(str)    # the file could not be written

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.repaired = []
        for key, field in FIELDS.items():
            if key in config.data and not field.accepts(config.data[key]):
                config.data[key] = field.fresh()
                self.repaired.append(key)
        if self.repaired:
            self.write()

    def get(self, key):
        field = FIELDS[key]  # an unknown key is a typo in the code: fail loudly
        value = self.config.data.get(key, NOTHING)
        return field.fresh() if value is NOTHING else copy.deepcopy(value)

    def set(self, key, value):
        field = FIELDS[key]
        if not field.accepts(value):
            self.failed.emit(f"{key}: invalid value {value!r}")
            return False
        if self.get(key) == value:
            return True
        self.config.data[key] = copy.deepcopy(value)
        self.write()
        self.changed.emit(key)
        return True

    def update(self, key, function):
        """Change a list or dict setting: store.update("hidden", lambda items: [*items, path])."""
        return self.set(key, function(self.get(key)))

    def snapshot(self):
        """A plain dict with every setting, safe to hand to a background thread."""
        return {key: self.get(key) for key in FIELDS}

    def take_legacy(self, key):
        """Remove and return a key that older versions wrote and no longer belongs to the settings."""
        value = self.config.data.pop(key, NOTHING)
        if value is not NOTHING:
            self.write()
        return None if value is NOTHING else value

    def write(self):
        try:
            self.config.save()
        except OSError as error:
            self.failed.emit(str(error))
