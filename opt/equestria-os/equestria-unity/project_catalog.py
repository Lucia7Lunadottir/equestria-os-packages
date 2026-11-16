"""Every known Unity project, scanned in the background and shared by every page."""
import time
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from project_scanner import ProjectScanner, project_version, scan_dirs
from controls import Background

WATCHED = ("projects", "hidden", "scan_dirs", "scan_depth")  # settings that change which projects exist
STALE_AFTER = 20  # seconds; a newer scan is made when the window is shown again after this


class ProjectCatalog(QObject):
    """The project list and everything remembered about projects (favorites, last opened, hidden)."""
    changed = pyqtSignal()       # the list changed or a scan started
    failed = pyqtSignal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.tasks = Background(self)
        self.items = []
        self.scanning = False
        self.again = False
        self.scanned = 0.0
        config.changed.connect(lambda key: key in WATCHED and self.refresh())

    # ---- scanning -------------------------------------------------------------------------------

    def refresh(self):
        if self.scanning:
            self.again = True
            return
        self.scanning = True
        self.changed.emit()
        data = self.config.snapshot()
        self.tasks.run(lambda: ProjectScanner(data).collect(), self.scanned_result)

    def scanned_result(self, result):
        self.scanning = False
        self.scanned = time.monotonic()
        if isinstance(result, Exception):
            self.failed.emit(str(result))
        else:
            self.items = result
        if self.again:
            self.again = False
            self.refresh()
            return
        self.changed.emit()

    def stale(self):
        return not self.scanning and time.monotonic() - self.scanned > STALE_AFTER

    # ---- reading --------------------------------------------------------------------------------

    def find(self, path):
        path = Path(path)
        return next((p for p in self.items if p.path == path), None)

    def versions(self):
        """Editor versions the projects need."""
        return {p.version for p in self.items if p.version}

    def usage(self):
        """version -> number of projects that use it."""
        counts = {}
        for project in self.items:
            counts[project.version] = counts.get(project.version, 0) + 1
        return counts

    def opened(self, project):
        return self.config.get("opened").get(str(project.path), 0)

    def favorites(self):
        return set(self.config.get("favorites"))

    def scan_dirs(self):
        return scan_dirs(self.config.snapshot())

    # ---- changing -------------------------------------------------------------------------------

    def add(self, path):
        """A project folder is added as a project, any other folder becomes a search folder.
        Returns True for a project, False for a search folder."""
        path = Path(path).resolve()
        if project_version(path):
            self.config.update("hidden", lambda items: [p for p in items if p != str(path)])
            self.config.update("projects", lambda items: sorted({*items, str(path)}))
            return True
        self.add_scan_dir(str(path))
        return False

    def add_scan_dir(self, path):
        dirs = self.scan_dirs()
        if str(path) not in dirs:
            self.config.set("scan_dirs", [*dirs, str(path)])
        inside = str(path).rstrip("/") + "/"
        self.config.update("hidden", lambda items: [p for p in items if not p.startswith(inside)])

    def remove_scan_dir(self, path):
        self.config.set("scan_dirs", [p for p in self.scan_dirs() if p != path])

    def hide(self, project):
        self.items = [p for p in self.items if p.path != project.path]
        self.config.update("hidden", lambda items: sorted({*items, str(project.path)}))
        self.changed.emit()

    def toggle_favorite(self, project):
        self.config.set("favorites", sorted(self.favorites() ^ {str(project.path)}))

    def touch(self, path):
        self.config.update("opened", lambda opened: {**opened, str(path): time.time()})

    def remember_created(self, path):
        self.config.update("projects", lambda items: sorted({*items, str(path)}))
        self.touch(path)
