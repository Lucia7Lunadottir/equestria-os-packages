#!/usr/bin/env python3
from pathlib import Path
import sys
import traceback

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                             QPlainTextEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from store import Store
from kit import APP_ID, ROOT, LauncherThemes, SingleInstance, call, catalog, qt, tr
from account_state import AccountState
from banners import BannerBar
from editor_locator import migrate_editor_profiles
from editor_registry import EditorRegistry
from installs import Installs
from jobs import Jobs
from nav_icons import icon as nav_icon
from newproject import NewProject
from preferences import Account, Settings
from project_catalog import ProjectCatalog
from packages_page import Packages
from projects import Projects
from release_info import ReleaseInfo
from services import Services
from status_pill import JobStatusPill
from tray import TrayController
from unity_cli import UnityCli

NAV = (("projects", "nav.projects"), ("templates", "nav.templates"), ("editors", "nav.editors"))
TOP = (("packages", "nav.packages"), ("account", "nav.account"), ("settings", "nav.settings"))


class Launcher(QMainWindow):
    """The window: navigation between pages. State lives in the models, the pieces of the window in their own classes."""

    def __init__(self, app):
        super().__init__()
        self.setWindowTitle("Equestria Unity")
        self.resize(1180, 740)
        self.setAcceptDrops(True)
        self.exiting = False
        self.config = Store(qt.JsonConfig(APP_ID), self)
        migrate_editor_profiles(self.config)
        self.custom_themes = LauncherThemes(self.config.get("themes"))
        self.manager = qt.ThemeManager(app, (ROOT / "style.qss").read_text())
        self.jobs = Jobs(self)
        self.cli = UnityCli(self.jobs, self.config)
        self.catalog = ProjectCatalog(self.config, self)
        self.editors = EditorRegistry(self.config, self)
        self.account_state = AccountState(self.cli, self)
        self.release_info = ReleaseInfo(self)

        root = QWidget()
        self.setCentralWidget(root)
        column = QVBoxLayout(root)
        column.setContentsMargins(10, 6, 10, 10)
        column.setSpacing(8)
        column.addWidget(self.topbar())
        row = QHBoxLayout()
        row.setSpacing(10)
        column.addLayout(row, 1)
        row.addWidget(self.sidebar())

        content = QFrame()
        content.setObjectName("content")
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.banners = BannerBar(self, self.config)
        body.addWidget(self.banners)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(800)
        self.output.setMaximumHeight(170)
        self.output.setVisible(False)
        call(self.output.setPlaceholderText, tr("jobs.output"))
        body.addWidget(self.output)
        row.addWidget(content, 1)

        self.projects = Projects(self)
        self.new = NewProject(self)
        self.installs = Installs(self)
        self.packages = Packages(self)
        self.templates = Services(self)
        self.account = Account(self)
        self.pages = {"projects": self.projects, "new": self.new, "editors": self.installs,
                      "packages": self.packages, "templates": self.new, "services": self.templates,
                      "account": self.account, "settings": Settings(self)}
        for page in dict.fromkeys(self.pages.values()):
            if page is not self.pages["settings"]:
                self.stack.addWidget(page)
        self.settings_dialog = QDialog(self)
        self.settings_dialog.setModal(True)
        call(self.settings_dialog.setWindowTitle, tr("nav.settings"))
        self.settings_dialog.resize(940, 660)
        dialog_body = QVBoxLayout(self.settings_dialog)
        dialog_body.setContentsMargins(0, 0, 0, 0)
        dialog_body.addWidget(self.pages["settings"])

        self.jobs.message.connect(self.output.appendPlainText)
        self.config.failed.connect(lambda text: self.notify(text, "fail", 15000))
        self.catalog.failed.connect(self.jobs.message.emit)
        self.tray = TrayController(self, self.catalog, self.config)
        self.tray.show_window.connect(self.bring_forward)
        self.tray.quit_requested.connect(self.quit_from_tray)
        self.tray.open_project.connect(self.open_tray_project)
        self.jobs.finished.connect(self.tray.finished)
        self.go("projects")
        self.catalog.refresh()
        self.account_state.load()

    # ---- top bar and sidebar ------------------------------------------------------------------

    def topbar(self):
        bar = QFrame()
        bar.setObjectName("topbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 2, 4, 0)
        layout.setSpacing(4)
        logo = QLabel("Equestria  Unity")
        logo.setObjectName("logo")
        layout.addWidget(logo)
        layout.addSpacing(18)
        self.pill = JobStatusPill(self.jobs, lambda: self.log.setChecked(True), self)
        layout.addWidget(self.pill)
        layout.addStretch()

        self.cli_shortcut = call(QPushButton, tr("cli.download"))
        self.cli_shortcut.clicked.connect(self.show_cli_settings)
        self.cli_shortcut.setVisible(not self.cli.executable())
        layout.addWidget(self.cli_shortcut)
        self.top = {}
        for key, label in TOP:
            button = call(QPushButton, tr(label))
            button.setObjectName("flat")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _=False, k=key: self.go(k))
            layout.addWidget(button)
            self.top[key] = button
        self.log = call(QPushButton, tr("jobs.log"))
        self.log.setObjectName("flat")
        self.log.setCheckable(True)
        self.log.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.log.toggled.connect(lambda on: self.output.setVisible(on))
        layout.addWidget(self.log)
        return bar

    def sidebar(self):
        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(176)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(2)
        self.nav = {}
        for key, label in NAV:
            button = call(QPushButton, tr(label))
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _=False, k=key: self.go(k))
            button.setIconSize(QSize(18, 18))
            layout.addWidget(button)
            self.nav[key] = button
        layout.addStretch()
        self.paint_nav_icons()
        self.manager.on_change(lambda _theme: self.paint_nav_icons())
        return side

    def paint_nav_icons(self):
        """The icons take their colours from the theme, so they are drawn again when it changes."""
        for key, button in self.nav.items():
            button.setIcon(nav_icon(key))

    def show_cli_settings(self):
        self.pages["settings"].select("settings.advanced")
        self.go("settings")

    def notify(self, text, level="", ms=5000):
        """Show a short message in the top bar. level: '', 'busy', 'ok' or 'fail'."""
        self.pill.notify(text, level, ms)

    def go(self, key):
        if key == "settings":
            self.pages[key].refresh()
            self.settings_dialog.open()
            return
        for name, button in self.nav.items():
            button.setChecked(name == ("templates" if key in ("services", "new") else key))
        for name, button in self.top.items():
            button.setChecked(name == key)
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        self.banners.update_banners()
        if key == "projects":
            if self.catalog.stale():
                self.catalog.refresh()
        elif hasattr(page, "refresh"):
            page.refresh()

    # ---- tray ------------------------------------------------------------------------------------

    def open_tray_project(self, project):
        self.bring_forward()
        self.projects.open(project)

    def editor_started(self, path):
        self.tray.editor_started(path)

    def quit_from_tray(self):
        self.bring_forward()
        self.exiting = True
        self.close()

    # ---- window events ---------------------------------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Drop a folder: a project is added, any other folder becomes a search folder."""
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                self.projects.add_path(path)
        self.go("projects")

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            # Projects, Editors and the account may have changed elsewhere (Hub, terminal) while in the background.
            if self.stack.currentWidget() is self.projects and self.catalog.stale():
                self.catalog.refresh()
            self.editors.reload()
            if self.account_state.stale():
                self.account_state.load()
        super().changeEvent(event)

    def closeEvent(self, event):
        if not self.exiting and self.config.get("close_to_tray") and self.tray.hide_window():
            event.ignore()
            return
        if self.jobs.busy():
            self.exiting = False
            QMessageBox.information(self, self.windowTitle(), tr("jobs.running"))
            event.ignore()
        elif any(page.workers for page in self.pages.values()) or self.catalog.tasks.busy():
            event.ignore()
            self.hide()
            QTimer.singleShot(100, self.close)
        else:
            self.tray.hide_icon()
            event.accept()
            if self.exiting:
                QApplication.quit()

    def bring_forward(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()


def report_errors(window):
    """PyQt6 ends the whole program on an exception nobody caught in a slot. A mistake behind one button
    must not close the launcher: the error goes to the log and the top bar instead."""
    def hook(kind, error, trace):
        text = "".join(traceback.format_exception(kind, error, trace))
        sys.stderr.write(text)
        try:
            window.jobs.message.emit(text)
            window.notify(tr("app.error", error), "fail", 20000)
        except RuntimeError:
            pass  # the window is already gone
    sys.excepthook = hook


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(str(ROOT / f"{APP_ID}.svg")))
    instance = SingleInstance(APP_ID)
    if not instance.claim():
        instance.notify_running()
        return 0
    catalog.set_language(catalog.lang, persist=False)
    window = Launcher(app)
    report_errors(window)
    instance.on_show(window.bring_forward)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
