"""The system tray icon: show / hide the launcher, its recent projects, notifications about finished work."""
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from kit import APP_ID, ROOT, call, tr


class TrayController(QObject):
    open_project = pyqtSignal(object)   # a project chosen in the tray menu
    show_window = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, window, catalog, config):
        super().__init__(window)
        self.window = window
        self.catalog = catalog
        self.config = config
        self.last_project = None
        self.icon = QSystemTrayIcon(QIcon(str(ROOT / f"{APP_ID}.svg")), window)
        menu = QMenu(window)
        self.project_menu = call(menu.addMenu, tr("nav.projects"))
        menu.addSeparator()
        call(menu.addAction, tr("tray.show")).triggered.connect(self.show_window)
        call(menu.addAction, tr("tray.hide")).triggered.connect(self.hide_window)
        menu.addSeparator()
        call(menu.addAction, tr("tray.quit")).triggered.connect(self.quit_requested)
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self.activated)
        catalog.changed.connect(self.update_projects)
        config.changed.connect(lambda key: key in ("tray_projects", "opened") and self.update_projects())
        self.update_projects()
        self.icon.show()

    def activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window.emit()

    def available(self):
        return self.icon.isVisible() and self.icon.isSystemTrayAvailable()

    def hide_window(self):
        """Hide the launcher into the tray. False when there is no tray to come back from."""
        if not self.available():
            return False
        self.window.hide()
        return True

    def update_projects(self):
        enabled = self.config.get("tray_projects")
        title = self.window.windowTitle()
        self.project_menu.menuAction().setVisible(enabled)
        self.project_menu.clear()
        self.icon.setToolTip(title)
        if not enabled:
            return
        if self.last_project:
            self.icon.setToolTip(f"{title} · {self.last_project.name}")
        opened = self.config.get("opened")
        projects = sorted(self.catalog.items, key=lambda p: (opened.get(str(p.path), 0), p.modified), reverse=True)
        for project in projects:
            action = self.project_menu.addAction(f"{project.name}  ·  {project.version}")
            action.setToolTip(str(project.path))
            action.triggered.connect(lambda checked=False, p=project: self.open_project.emit(p))
        self.project_menu.setEnabled(bool(projects))

    def editor_started(self, path):
        self.last_project = Path(path)
        self.update_projects()
        if self.config.get("editor_to_tray"):
            self.hide_window()

    def finished(self, title, ok):
        """A desktop notification, only while the window is hidden and the user wants them."""
        if self.window.isHidden() and self.config.get("job_notifications") and self.icon.isSystemTrayAvailable():
            self.icon.showMessage(self.window.windowTitle(), ("✓  " if ok else "✗  ") + str(title))

    def hide_icon(self):
        self.icon.hide()
