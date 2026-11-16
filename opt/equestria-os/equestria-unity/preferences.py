import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import Qt, qVersion
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget, QStackedWidget, QScrollArea, QPlainTextEdit, QFrame, QSpinBox

import library
import cli_download
from controls import Page, chip
from projects import FoldersPanel
from kit import ROOT, call, catalog, qt, tr
from equestria_kit import themes


class Settings(Page):
    """Settings window laid out like Unity Hub: section list on the left, blocks with a heading and a hint on the right."""

    def __init__(self, window):
        super().__init__(window)
        self.layout_box.setContentsMargins(0, 0, 0, 0)
        self.layout_box.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(24, 18, 18, 14)
        head.setSpacing(12)
        title = call(QLabel, tr("nav.settings"))
        title.setObjectName("title")
        head.addWidget(title)
        head.addWidget(chip("Equestria Unity 1.5"))
        head.addStretch()
        close = QPushButton("✕")
        close.setObjectName("flat")
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.clicked.connect(lambda: window.settings_dialog.close())
        head.addWidget(close)
        self.layout_box.addLayout(head)
        line = QFrame()
        line.setObjectName("divider")
        line.setFixedHeight(1)
        self.layout_box.addWidget(line)
        body = QHBoxLayout()
        body.setSpacing(0)
        self.layout_box.addLayout(body, 1)
        self.side = QVBoxLayout()
        self.side.setContentsMargins(12, 14, 12, 12)
        self.side.setSpacing(2)
        self.side.setAlignment(Qt.AlignmentFlag.AlignTop)
        side = QWidget()
        side.setFixedWidth(220)
        side.setLayout(self.side)
        body.addWidget(side)
        self.sections = QStackedWidget()
        body.addWidget(self.sections, 1)
        self.tabs = {}
        self.downloading_cli = False
        self.checks = {}

        licenses = self.section("license.status")
        refresh = self.button(licenses.header, "license.refresh", self.read_licenses)
        add = call(QPushButton, tr("license.add"))
        add.setObjectName("primary")
        add.setProperty("compact", True)
        add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        menu = QMenu(add)
        call(menu.addAction, tr("license.personal")).triggered.connect(window.account.activate)
        call(menu.addAction, tr("license.file")).triggered.connect(window.account.license_file)
        add.setMenu(menu)
        licenses.header.addWidget(add)
        frame, inner = self.card(licenses)
        self.license_info = QPlainTextEdit()
        self.license_info.setReadOnly(True)
        self.license_info.setMinimumHeight(180)
        call(self.license_info.setPlaceholderText, tr("license.view"))
        inner.addWidget(self.license_info)

        projects = self.section("nav.projects")
        inner = self.block(projects, "folders.title", "folders.help")
        inner.addWidget(FoldersPanel(window.projects))

        installs = self.section("settings.installs")
        inner = self.block(installs, "settings.editor_location", "settings.editor_location_help")
        self.editor_path = self.path_row(inner, window.installs.set_folder)
        inner = self.block(installs, "settings.download_location", "settings.download_location_help")
        self.download_path = self.path_row(inner, self.choose_downloads)
        self.button(self.actions(inner), "settings.download_reset", self.reset_downloads)
        inner = self.block(installs, "settings.retries", "settings.retries_help")
        self.retries = QSpinBox()
        self.retries.setRange(-1, 10)
        call(self.retries.setSpecialValueText, tr("settings.default"))
        saved = self.config.get("install_retries")
        self.retries.setValue(saved if isinstance(saved, int) and saved >= 0 else -1)
        self.retries.valueChanged.connect(lambda v: self.save("install_retries", v if v >= 0 else None))
        self.actions(inner).addWidget(self.retries)
        inner = self.block(installs, "settings.remove_title")
        self.check(inner, "settings.confirm_remove", "no_confirm_remove", False)

        templates = self.section("nav.templates")
        inner = self.block(templates, "settings.template_location", "settings.template_location_help")
        self.template_path = self.path_row(inner, self.choose_templates)

        appearance = self.section("settings.appearance")
        inner = self.block(appearance, "settings.theme", "settings.theme_help")
        row = self.actions(inner)
        self.theme = self.button(row, "settings.theme", self.choose_theme)
        self.button(row, "settings.import_theme", self.import_theme)
        inner = self.block(appearance, "tray.when", "settings.tray_help")
        self.check(inner, "tray.editor", "editor_to_tray", False)
        self.check(inner, "tray.close", "close_to_tray", True)
        inner = self.block(appearance, "settings.language", "settings.language_help")
        self.language_combo = catalog.selector(self, after=self.refresh)
        self.actions(inner).addWidget(self.language_combo)

        alerts = self.section("settings.notifications")
        inner = self.block(alerts, "settings.notifications", "settings.notify_help")
        self.check(inner, "settings.job_alerts", "job_notifications", True)
        inner = self.block(alerts, "settings.banners", "settings.banners_help")
        self.check(inner, "settings.show_banners", "banners_enabled", True)
        self.dismissed = QLabel()
        inner.addWidget(self.dismissed)
        self.button(self.actions(inner), "settings.banners_restore", self.restore_banners)

        privacy = self.section("settings.privacy")
        inner = self.block(privacy, "settings.privacy", "settings.privacy_help")
        self.check(inner, "tray.list", "tray_projects", True)

        advanced = self.section("settings.advanced")
        inner = self.block(advanced, "settings.cli_title", "settings.cli_help")
        self.cli_status = QLabel()
        inner.addWidget(self.cli_status)
        self.cli_button = self.button(self.actions(inner), "cli.download", self.download_cli, "primary")
        inner = self.block(advanced, "settings.launch_title", "settings.launch_help")
        inner.addWidget(QLabel("XDG_SESSION_TYPE = " + os.environ.get("XDG_SESSION_TYPE", "—")))
        row = self.actions(inner)
        self.label(row, "settings.renderer", "")
        self.renderer = QComboBox()
        call(self.renderer.addItem, tr("settings.default"), "")
        self.renderer.addItem("Vulkan", "-force-vulkan")
        self.renderer.addItem("OpenGL Core", "-force-glcore")
        self.renderer.setCurrentIndex(max(0, self.renderer.findData(self.config.get("renderer"))))
        self.renderer.currentIndexChanged.connect(lambda: self.save("renderer", self.renderer.currentData()))
        row.addWidget(self.renderer)
        self.label(inner, "args.global")
        self.arguments = QLineEdit(self.config.get("arguments"))
        self.arguments.editingFinished.connect(self.save_arguments)
        inner.addWidget(self.arguments)
        inner = self.block(advanced, "settings.tools_title")
        row = self.actions(inner)
        self.button(row, "tool.picker", lambda: self.tool("equestria-color-picker", "equestria_color_picker.py"))
        self.button(row, "tool.log", lambda: self.tool("equestria-unity-log", "logwatch.py"))

        about = self.section("settings.about")
        inner = self.block(about, "settings.versions", "settings.versions_help")
        self.versions = QLabel()
        self.versions.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inner.addWidget(self.versions)
        self.select("settings.appearance")

    def section(self, key):
        """Add a section: a button in the left list and a scrollable page. Returns its layout (`.header` = buttons by the title)."""
        tab = call(QPushButton, tr(key))
        tab.setObjectName("nav")
        tab.setCheckable(True)
        tab.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.side.addWidget(tab)
        panel = QWidget()
        panel.setObjectName("rowbody")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        head = QHBoxLayout()
        head.setSpacing(8)
        label = call(QLabel, tr(key))
        label.setObjectName("title")
        head.addWidget(label)
        head.addStretch()
        layout.header = head
        layout.addLayout(head)
        layout.addSpacing(10)
        scroll = QScrollArea()
        scroll.setObjectName("sectionScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        index = self.sections.addWidget(scroll)
        self.tabs[key] = (index, tab)
        tab.clicked.connect(lambda: self.select(key))
        return layout

    def block(self, layout, title_key, hint_key=None):
        """One setting group: heading, short explanation, then the controls (returned layout)."""
        frame = QFrame()
        frame.setObjectName("block")
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(0, 14, 0, 16)
        inner.setSpacing(8)
        self.label(inner, title_key, "rowname")
        if hint_key:
            self.label(inner, hint_key)
        layout.addWidget(frame)
        return inner

    def path_row(self, layout, callback):
        row = QHBoxLayout()
        field = QLineEdit()
        field.setReadOnly(True)
        row.addWidget(field, 1)
        folder = QPushButton("📁")
        folder.setObjectName("small")
        folder.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        folder.clicked.connect(lambda: callback())
        row.addWidget(folder)
        layout.addLayout(row)
        return field

    def select(self, key):
        self.sections.setCurrentIndex(self.tabs[key][0])
        for name, (_, tab) in self.tabs.items():
            tab.setChecked(name == key)
        if key == "license.status":
            self.read_licenses()
        self.refresh()

    def actions(self, layout):
        row = QHBoxLayout()
        row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(row)
        return row

    def check(self, layout, label, key, default):
        checkbox = call(QCheckBox, tr(label))
        checkbox.setChecked(self.config.get(key))
        self.checks[key] = checkbox
        checkbox.toggled.connect(lambda enabled: self.save(key, enabled))
        layout.addWidget(checkbox)

    def choose_downloads(self):
        path = self.folder("settings.download_location", self.download_path.text())
        if path:
            self.save("download_dir", path)
            self.refresh()

    def reset_downloads(self):
        self.save("download_dir", "")
        self.refresh()

    def restore_banners(self):
        self.save("dismissed_banners", [])

    def choose_templates(self):
        path = self.folder("settings.template_dir", self.template_path.text())
        if path:
            self.save("template_root", path)
            self.refresh()
            self.window.new.load(force=True)

    def read_licenses(self):
        self.window.account.load()

    def refresh(self):
        """Show the current stored values: nothing here keeps its own copy of a setting."""
        for key, box in self.checks.items():
            box.blockSignals(True)
            box.setChecked(self.config.get(key))
            box.blockSignals(False)
        self.renderer.blockSignals(True)
        self.renderer.setCurrentIndex(max(0, self.renderer.findData(self.config.get("renderer"))))
        self.renderer.blockSignals(False)
        if not self.arguments.hasFocus():
            self.arguments.setText(self.config.get("arguments"))
        retries = self.config.get("install_retries")
        self.retries.blockSignals(True)
        self.retries.setValue(-1 if retries is None else retries)
        self.retries.blockSignals(False)
        self.editor_path.setText(str(library.editor_roots(self.config.snapshot())[0]))
        self.download_path.setText(str(self.config.get("download_dir") or tempfile.gettempdir()))
        call(self.dismissed.setText, tr("settings.dismissed", len(self.config.get("dismissed_banners"))))
        self.template_path.setText(str(self.config.get("template_root") or library.HUB / "Templates"))
        path = library.executable("unity")
        if self.downloading_cli:
            call(self.cli_status.setText, tr("cli.downloading"))
        elif path:
            self.cli_status.setText(f"Unity CLI · {path}")
        else:
            call(self.cli_status.setText, tr("cli.missing"))
        self.versions.setText(f"Equestria Unity 1.5\nQt {qVersion()}\nPython {sys.version.split()[0]}\n"
                              f"Unity CLI {path or '—'}")
        self.cli_button.setEnabled(not self.downloading_cli)
        self.cli_button.setVisible(not path)

    def download_cli(self):
        destination = Path.home() / ".local/bin/unity"
        if self.downloading_cli or not self.confirm("cli.confirm", destination):
            return
        self.downloading_cli = True
        self.refresh()

        def completed(result):
            self.downloading_cli = False
            self.refresh()
            self.window.cli_shortcut.setVisible(not library.executable("unity"))
            self.window.update_banners()
            if isinstance(result, Exception):
                self.warning(str(result))
            else:
                self.window.notify(tr("cli.ready", result), "ok")

        self.background(lambda: cli_download.download(destination), completed)

    def save_arguments(self):
        try:
            shlex.split(self.arguments.text())
        except ValueError as error:
            self.warning(error)
            self.arguments.setText(self.config.get("arguments"))
            return
        self.save("arguments", self.arguments.text())

    def import_theme(self):
        path = QFileDialog.getOpenFileName(self, tr("settings.import_theme"), "", "JSON (*.json)")[0]
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            name = data["name"]
            colors = data["colors"]
            if not isinstance(name, str) or not name.strip() or not isinstance(colors, dict) or not colors:
                raise ValueError
            if any(k not in themes.KEYS or not isinstance(v, str) or not v.startswith("#") or not QColor(v).isValid()
                   for k, v in colors.items()):
                raise ValueError
            custom = {**self.config.get("themes"), name: colors}
            self.save("themes", custom)
            self.window.custom_themes.reload(custom)
            self.window.manager.apply(qt.pick_theme(name))
        except (OSError, ValueError, KeyError, TypeError):
            self.warning(tr("settings.bad_theme"))

    def choose_theme(self):
        qt.theme_menu(self, self.theme, self.window.manager.name, self.window.manager.apply)

    def tool(self, name, script):
        exe = library.executable(name)
        source = ROOT.parent / name / script
        if not exe and not source.is_file():
            self.warning(tr("tool.missing", name))
            return
        try:
            subprocess.Popen([exe] if exe else [sys.executable, str(source)], start_new_session=True)
        except OSError as error:
            self.warning(error)


class Account(Page):
    """Unity ID and license. The text shown here and in Settings → Licenses always comes from one place: the CLI."""

    def __init__(self, window):
        super().__init__(window)
        self.state = {"auth": "", "license": ""}
        self.loaded_at = 0.0
        self.title("nav.account")
        _, account = self.card()
        self.label(account, "account.heading", "rowname")
        self.auth_view = self.view(account)
        actions = QHBoxLayout()
        account.addLayout(actions)
        self.button(actions, "account.login", lambda: self.run("account.login", ["auth", "login"]), "primary")
        manage = call(QPushButton, tr("account.manage"))
        manage.setObjectName("small")
        menu = QMenu(manage)
        call(menu.addAction, tr("account.accounts")).triggered.connect(
            lambda: self.run("account.accounts", ["auth", "accounts"]))
        call(menu.addAction, tr("account.switch")).triggered.connect(self.switch)
        menu.addSeparator()
        call(menu.addAction, tr("account.logout")).triggered.connect(self.logout)
        manage.setMenu(menu)
        actions.addWidget(manage)
        self.button(actions, "license.refresh", self.load)
        actions.addStretch()

        _, licenses = self.card()
        self.label(licenses, "license.status", "rowname")
        self.license_view = self.view(licenses)
        actions = QHBoxLayout()
        licenses.addLayout(actions)
        self.button(actions, "license.personal", self.activate)
        self.button(actions, "license.file", self.license_file)
        actions.addStretch()
        self.layout_box.addStretch()

    def view(self, layout):
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setMinimumHeight(96)
        box.setMaximumHeight(170)
        call(box.setPlaceholderText, tr("account.empty"))
        layout.addWidget(box)
        return box

    def refresh(self):
        self.load()

    def stale(self):
        return time.monotonic() - self.loaded_at > 30

    def load(self):
        """Ask the CLI who is signed in and which license is active, then update every place that shows it."""
        self.loaded_at = time.monotonic()
        cli = library.executable("unity")
        if not cli:
            for name in self.state:
                self.got(name, str(tr("cli.hint")))
            return
        base = ["--no-pager", "--no-color", "--non-interactive"]
        for key, args, name in (("auth-status", ["auth", "status"], "auth"),
                                ("license-status", ["license", "status"], "license")):
            self.jobs.run_process(key, tr("account.status"), cli, base + args,
                                  lambda data, n=name: self.got(n, data.decode(errors="replace").strip()),
                                  capture=True, failed=lambda text, n=name: self.got(n, str(text)), quiet=True)

    def got(self, name, text):
        self.state[name] = text
        views = {"auth": [self.auth_view], "license": [self.license_view, self.window.pages["settings"].license_info]}
        for view in views[name]:
            view.setPlainText(text)

    def run(self, key, args):
        """Run an account command; whatever it changes is re-read afterwards so no screen shows old data."""
        self.jobs.run("account", tr(key), args, lambda _: self.load(), failed=lambda _: self.load())

    def switch(self):
        account = self.text("account.email")
        if account and not account.startswith("-"):
            self.run("account.switch", ["auth", "switch", account])

    def logout(self):
        if self.confirm("account.confirm_logout"):
            self.run("account.logout", ["auth", "logout", "--yes"])

    def activate(self):
        if self.confirm("license.confirm"):
            self.run("license.personal", ["license", "activate", "--personal", "--accept-eula"])

    def license_file(self):
        path = QFileDialog.getOpenFileName(self, tr("license.file"), "", "Unity (*.ulf *.xml)")[0]
        if path:
            self.run("license.file", ["license", "activate", "--file", path])
