"""Find installed Unity Editors: in Hub's install folders, the launcher's folder and the ones located by hand."""
import os
from pathlib import Path

import unity_paths


class EditorLocator:
    def __init__(self, settings):
        self.settings = settings

    def roots(self):
        """Install folders, the one Unity Hub uses for new Editors first."""
        secondary = unity_paths.read_json(unity_paths.HUB / "secondaryInstallPath.json", "")
        return [Path(p) for p in (secondary, self.settings.get("editor_root"), unity_paths.DEFAULT_ROOT)
                if isinstance(p, (str, Path)) and p]

    def editors(self):
        """version -> Editor executable. An Editor located by hand wins over a found one."""
        result = {}
        for root in reversed(self.roots()):
            for exe in root.glob("*/Editor/Unity"):
                if exe.is_file() and os.access(exe, os.X_OK):
                    result[exe.parents[1].name] = exe
        for version, path in self.settings.get("editors", {}).items():
            exe = Path(path)
            if exe.is_file() and os.access(exe, os.X_OK):
                result[version] = exe
        return result


def install_size(exe):
    """Bytes the Editor's folder takes on disk (the folder that holds Editor/Unity). Slow: run it in the background."""
    total = 0
    for folder, _, files in os.walk(Path(exe).parents[1]):
        for name in files:
            try:
                total += os.lstat(os.path.join(folder, name)).st_size
            except OSError:
                pass
    return total


def migrate_editor_profiles(store):
    """Older versions had one global X11 switch; it now lives in each editor's profile."""
    enabled = store.take_legacy("x11")
    if enabled:
        profiles = store.get("editor_profiles")
        for exe in EditorLocator(store.snapshot()).editors().values():
            profiles.setdefault(str(exe.resolve()), {}).setdefault("x11", True)
        store.set("editor_profiles", profiles)
