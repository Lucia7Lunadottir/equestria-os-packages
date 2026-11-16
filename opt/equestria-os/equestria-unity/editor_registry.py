"""Installed Unity Editors, looked up once and shared by every page."""
from PyQt6.QtCore import QObject, pyqtSignal

from editor_locator import EditorLocator
from versions import version_key

WATCHED = ("editors", "editor_root")  # settings that change where Editors are found


class EditorRegistry(QObject):
    """version -> Editor executable. Pages read it instead of scanning the disk on every redraw."""
    changed = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.found = EditorLocator(config.snapshot()).editors()
        config.changed.connect(lambda key: key in WATCHED and self.reload())

    def reload(self):
        """Look at the disk again: an Editor may have been installed or removed, here or in another program."""
        found = EditorLocator(self.config.snapshot()).editors()
        if found != self.found:
            self.found = found
            self.changed.emit()

    def all(self):
        return dict(self.found)

    def get(self, version):
        return self.found.get(version)

    def __contains__(self, version):
        return version in self.found

    def versions(self):
        """Installed versions, newest first."""
        return sorted(self.found, key=version_key, reverse=True)
