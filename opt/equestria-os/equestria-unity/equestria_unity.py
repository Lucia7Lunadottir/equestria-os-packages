#!/usr/bin/env python3
from pathlib import Path
import sys
import library

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox,
                             QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from store import Store
from kit import APP_ID, ROOT, LauncherThemes, SingleInstance, call, catalog, qt, tr
from installs import Installs
from jobs import Jobs
from equestria_kit.live_i18n import join_text, format_text
from newproject import NewProject
from preferences import Account, Settings
from projects import Packages, Projects
from services import Services

NAV = (("projects", "nav.projects"), ("templates", "nav.templates"), ("editors", "nav.editors"))
TOP = (("packages", "nav.packages"), ("account", "nav.account"), ("settings", "nav.settings"))


class Launcher(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.setWindowTitle("Equestria Unity")
        self.resize(1180, 740)
        self.setAcceptDrops(True)
        self.config = Store(qt.JsonConfig(APP_ID), self)
        library.migrate_editor_profiles(self.config)
        self.custom_themes = LauncherThemes(self.config.get("themes"))
        self.manager = qt.ThemeManager(app, (ROOT / "style.qss").read_text())
        self.jobs = Jobs(self)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_notice)

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
        self.banner_box = QVBoxLayout()
        self.banner_box.setContentsMargins(16, 14, 16, 0)
        self.banner_box.setSpacing(8)
        body.addLayout(self.banner_box)
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
        self.jobs.activity.connect(self.job_status)
        self.jobs.progress.connect(self.job_progress)
        self.jobs.finished.connect(self.job_finished)
        self.job_status()
        self.config.changed.connect(self.setting_changed)
        self.config.failed.connect(lambda text: self.notify(text, "fail", 15000))
        self.go("projects")
        self.exiting = False
        self.tray = QSystemTrayIcon(QIcon(str(ROOT / f"{APP_ID}.svg")), self)
        self.tray.setToolTip(self.windowTitle())
        menu = QMenu(self)
        self.last_project = None
        self.project_menu = call(menu.addMenu, tr("nav.projects"))
        self.update_tray_projects()
        menu.addSeparator()
        call(menu.addAction, tr("tray.show")).triggered.connect(self.bring_forward)
        call(menu.addAction, tr("tray.hide")).triggered.connect(self.hide_to_tray)
        menu.addSeparator()
        call(menu.addAction, tr("tray.quit")).triggered.connect(self.quit_from_tray)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        self.account.load()

    def setting_changed(self, key):
        """Every setting is changed through the store, so every window that shows it is updated from here."""
        if key in ("projects", "hidden", "scan_dirs", "scan_depth"):
            self.projects.refresh()
        elif key in ("favorites", "opened", "sort_key", "sort_down"):
            self.projects.render()
        elif key in ("editors", "editor_root", "editor_profiles"):
            self.installs.refresh()
            self.new.refresh()
            self.projects.render()
        elif key == "tray_projects":
            self.update_tray_projects()
        if key in ("banners_enabled", "dismissed_banners", "scan_dirs", "editors", "editor_root"):
            self.update_banners()
        self.pages["settings"].refresh()

    # ---- banners: dismissible hints at the top of the page -------------------------------------

    def banners(self):
        """Hints that depend on the launcher's real state: (id, text, button label, action)."""
        found = []
        if not library.executable("unity"):
            found.append(("cli", tr("banner.cli"), tr("cli.download"), self.show_cli_settings))
        if not library.scan_dirs(self.config.snapshot()) and not self.projects.items:
            found.append(("folders", tr("banner.folders"), tr("projects.add_folder"), self.projects.add))
        have = library.editors(self.config.snapshot())
        missing = sorted({p.version for p in self.projects.items if p.version and p.version not in have})
        if missing:
            found.append(("editors:" + ",".join(missing), tr("banner.editors", len(missing), ", ".join(missing[:3])),
                          tr("editor.install_button"), self.install_missing))
        return found

    def install_missing(self):
        self.go("editors")
        self.installs.show_install(True)

    def update_banners(self):
        while self.banner_box.count():
            widget = self.banner_box.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        if not self.config.get("banners_enabled"):
            return
        dismissed = set(self.config.get("dismissed_banners"))
        for key, text, action, callback in self.banners():
            if key in dismissed:
                continue
            frame = QFrame()
            frame.setObjectName("banner")
            row = QHBoxLayout(frame)
            row.setContentsMargins(14, 8, 8, 8)
            row.setSpacing(10)
            label = call(QLabel, text)
            label.setWordWrap(True)
            row.addWidget(label, 1)
            button = call(QPushButton, action)
            button.setObjectName("small")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _=False, c=callback: c())
            row.addWidget(button)
            close = QPushButton("✕")
            close.setObjectName("flat")
            close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            close.clicked.connect(lambda _=False, k=key: self.dismiss_banner(k))
            row.addWidget(close)
            self.banner_box.addWidget(frame)

    def dismiss_banner(self, key):
        self.config.update("dismissed_banners", lambda items: [*items, key])

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.bring_forward()

    def hide_to_tray(self):
        if not self.tray.isVisible() or not self.tray.isSystemTrayAvailable():
            return False
        self.hide()
        return True

    def update_tray_projects(self):
        enabled = self.config.get("tray_projects")
        self.project_menu.menuAction().setVisible(enabled)
        self.project_menu.clear()
        self.tray.setToolTip(self.windowTitle())
        if not enabled:
            return
        if self.last_project:
            self.tray.setToolTip(f"{self.windowTitle()} · {self.last_project.name}")
        projects = sorted(self.projects.items, key=lambda p: (self.projects.opened(p), p.modified), reverse=True)
        for project in projects:
            action = self.project_menu.addAction(f"{project.name}  ·  {project.version}")
            action.setToolTip(str(project.path))
            action.triggered.connect(lambda checked=False, p=project: self.open_tray_project(p))
        self.project_menu.setEnabled(bool(projects))

    def open_tray_project(self, project):
        self.bring_forward()
        self.projects.open(project)

    def editor_started(self, path):
        self.last_project = Path(path)
        self.update_tray_projects()
        if self.config.get("editor_to_tray"):
            self.hide_to_tray()

    def quit_from_tray(self):
        self.bring_forward()
        self.exiting = True
        self.close()

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

        self.pill = QFrame()
        self.pill.setObjectName("pill")
        pill = QHBoxLayout(self.pill)
        pill.setContentsMargins(14, 6, 8, 6)
        pill.setSpacing(10)
        self.notice = QLabel()
        pill.addWidget(self.notice)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.setFixedWidth(90)
        pill.addWidget(self.busy)
        self.cancel = call(QPushButton, tr("jobs.cancel_short"))
        self.cancel.setObjectName("flat")
        self.cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cancel.clicked.connect(self.cancel_job)
        pill.addWidget(self.cancel)
        self.details = call(QPushButton, tr("jobs.details"))
        self.details.setObjectName("flat")
        self.details.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.details.clicked.connect(lambda: self.log.setChecked(True))
        pill.addWidget(self.details)
        layout.addWidget(self.pill)
        self.pill.setVisible(False)
        layout.addStretch()

        self.cli_shortcut = call(QPushButton, tr("cli.download"))
        self.cli_shortcut.clicked.connect(self.show_cli_settings)
        self.cli_shortcut.setVisible(not library.executable("unity"))
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
        self.log.toggled.connect(self.show_log)
        layout.addWidget(self.log)
        return bar

    def show_cli_settings(self):
        self.pages["settings"].select("settings.advanced")
        self.go("settings")

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
            layout.addWidget(button)
            self.nav[key] = button
        layout.addStretch()
        return side

    def show_log(self, on):
        self.output.setVisible(on)

    def notify(self, text, level="", ms=5000):
        """Show a short message in the top bar. level: '', 'busy', 'ok' or 'fail'."""
        if self.jobs.active() and level != "fail":
            return  # a running operation owns the bar
        call(self.notice.setText, text)
        self.pill.setProperty("lvl", level)
        self.pill.style().unpolish(self.pill)
        self.pill.style().polish(self.pill)
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.setVisible(level == "busy")
        self.cancel.setVisible(False)
        self.details.setVisible(level == "fail")
        self.pill.setVisible(True)
        self.hide_timer.start(ms)

    def hide_notice(self):
        if not self.jobs.active():
            self.pill.setVisible(False)

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
        self.update_banners()
        if key == "projects":
            if self.projects.stale() and not self.projects.scanning:
                page.refresh()
        elif hasattr(page, "refresh"):
            page.refresh()

    # ---- background operations -----------------------------------------------------------------

    def job_progress(self, key, percent):
        if key in self.jobs.running:
            self.busy.setRange(0, 100)
            self.busy.setValue(percent)
            self.busy.setTextVisible(False)
            call(self.notice.setText, format_text("{} · {}%", self.jobs.running[key][0], percent))

    def job_status(self):
        """Operations in progress are always visible in the top bar, not only in the log."""
        if self.jobs.active():
            self.busy.setRange(0, 0)
            self.hide_timer.stop()
            names = join_text(" · ", (name for name, _ in self.jobs.active().values()))
            call(self.notice.setText, tr("jobs.working", names))
            self.pill.setProperty("lvl", "")
            self.pill.style().unpolish(self.pill)
            self.pill.style().polish(self.pill)
            self.busy.setVisible(True)
            self.cancel.setVisible(True)
            self.details.setVisible(True)
            self.pill.setVisible(True)
        elif self.pill.property("lvl") in (None, "", "busy") and not self.hide_timer.isActive():
            self.pill.setVisible(False)

    def job_finished(self, title, ok):
        if self.isHidden() and self.config.get("job_notifications") and self.tray.isSystemTrayAvailable():
            self.tray.showMessage(self.windowTitle(), ("✓  " if ok else "✗  ") + title)
        self.notify(("✓  " if ok else "✗  ") + title, "ok" if ok else "fail", 6000 if ok else 20000)

    def cancel_job(self):
        active = {f"{name}  ·  {key}": proc for key, (name, proc) in self.jobs.active().items()}
        if not active:
            return
        title, ok = QInputDialog.getItem(self, self.windowTitle(), str(tr("jobs.select")), list(active), editable=False)
        if ok and title in active and QMessageBox.question(
            self, self.windowTitle(), tr("jobs.confirm_cancel", title), defaultButton=QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            if any(proc is active[title] for _, proc in self.jobs.active().values()):
                active[title].terminate()

    # ---- window events ---------------------------------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Drop a folder: a project is added, any other folder becomes a search folder."""
        from pathlib import Path
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                self.projects.add_path(path)
        self.go("projects")

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow() \
                and self.stack.currentWidget() is self.projects and self.projects.stale() \
                and not self.projects.scanning:
            self.projects.refresh()
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow() and self.account.stale():
            self.account.load()  # signed in / out elsewhere (Hub, terminal) while the launcher was in the background
        super().changeEvent(event)

    def closeEvent(self, event):
        if not self.exiting and self.config.get("close_to_tray") and self.hide_to_tray():
            event.ignore()
            return
        if self.jobs.active():
            self.exiting = False
            QMessageBox.information(self, self.windowTitle(), tr("jobs.running"))
            event.ignore()
        elif any(page.workers for page in self.pages.values()):
            event.ignore()
            self.hide()
            QTimer.singleShot(100, self.close)
        else:
            self.tray.hide()
            event.accept()
            if self.exiting:
                QApplication.quit()

    def bring_forward(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()


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
    instance.on_show(window.bring_forward)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
