"""The sections of the Settings window. Each is a class: build() lays it out once, refresh() shows the stored values.
A new section is a new subclass added to SECTIONS; the window itself does not change."""
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, qVersion
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
                             QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

import cli_download
import unity_paths
from account_views import LicenseList
from editor_locator import EditorLocator
from equestria_kit import themes
from kit import ROOT, VERSION, LanguageSelector, call, qt, tr
from projects import FoldersPanel


class SettingsSection(QScrollArea):
    KEY = ""   # translation key of the title, also the section's name

    def __init__(self, settings):
        super().__init__()
        self.settings = settings            # the Settings page: dialogs, background work, the window
        self.config = settings.config
        self.launcher = settings.window
        self.checks = {}
        self.setObjectName("sectionScroll")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        panel = QWidget()
        panel.setObjectName("rowbody")
        self.box = QVBoxLayout(panel)
        self.box.setContentsMargins(24, 18, 24, 18)
        self.box.setSpacing(0)
        self.box.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        label = call(QLabel, tr(self.KEY))
        label.setObjectName("title")
        self.header.addWidget(label)
        self.header.addStretch()
        self.box.addLayout(self.header)
        self.box.addSpacing(10)
        self.setWidget(panel)
        self.build()

    def build(self):
        raise NotImplementedError

    def opened(self):
        """The user switched to this section."""

    def refresh(self):
        """Show the stored values; nothing here keeps its own copy of a setting."""
        for key, box in self.checks.items():
            box.blockSignals(True)
            box.setChecked(self.config.get(key))
            box.blockSignals(False)

    # ---- building blocks --------------------------------------------------------------------------

    def block(self, title_key, hint_key=None):
        """One setting group: heading, short explanation, then the controls (returned layout)."""
        frame = QFrame()
        frame.setObjectName("block")
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(0, 14, 0, 16)
        inner.setSpacing(8)
        self.settings.label(inner, title_key, "rowname")
        if hint_key:
            self.settings.label(inner, hint_key)
        self.box.addWidget(frame)
        return inner

    @staticmethod
    def action_row(layout):
        row = QHBoxLayout()
        row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(row)
        return row

    @staticmethod
    def path_row(layout, callback):
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

    def check(self, layout, label, key):
        checkbox = call(QCheckBox, tr(label))
        checkbox.setChecked(self.config.get(key))
        self.checks[key] = checkbox
        checkbox.toggled.connect(lambda enabled: self.config.set(key, enabled))
        layout.addWidget(checkbox)

    def button(self, layout, key, callback, name="small"):
        return self.settings.button(layout, key, callback, name)


class LicensesSection(SettingsSection):
    KEY = "license.status"

    def build(self):
        account = self.launcher.account
        self.button(self.header, "license.refresh", self.opened)
        add = call(QPushButton, tr("license.add"))
        add.setObjectName("primary")
        add.setProperty("compact", True)
        add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        menu = QMenu(add)
        call(menu.addAction, tr("license.personal")).triggered.connect(account.activate)
        call(menu.addAction, tr("license.file")).triggered.connect(account.license_file)
        add.setMenu(menu)
        self.header.addWidget(add)
        self.box.addWidget(LicenseList(self.launcher.account_state))

    def opened(self):
        self.launcher.account_state.load()


class ProjectsSection(SettingsSection):
    KEY = "nav.projects"

    def build(self):
        self.block("folders.title", "folders.help").addWidget(FoldersPanel(self.launcher.catalog))


class InstallsSection(SettingsSection):
    KEY = "settings.installs"

    def build(self):
        inner = self.block("settings.editor_location", "settings.editor_location_help")
        self.editor_path = self.path_row(inner, self.launcher.installs.set_folder)
        inner = self.block("settings.download_location", "settings.download_location_help")
        self.download_path = self.path_row(inner, self.choose_downloads)
        self.button(self.action_row(inner), "settings.download_reset", lambda: self.config.set("download_dir", ""))
        inner = self.block("settings.retries", "settings.retries_help")
        self.retries = QSpinBox()
        self.retries.setRange(-1, 10)  # -1: the Unity CLI decides
        self.retries.valueChanged.connect(lambda v: self.config.set("install_retries", v if v >= 0 else None))
        self.action_row(inner).addWidget(self.retries)
        inner = self.block("settings.remove_title")
        self.check(inner, "settings.confirm_remove", "no_confirm_remove")

    def choose_downloads(self):
        path = self.settings.folder("settings.download_location", self.download_path.text())
        if path:
            self.config.set("download_dir", path)

    def refresh(self):
        super().refresh()
        self.retries.setSpecialValueText(str(tr("settings.retries_default")))
        retries = self.config.get("install_retries")
        self.retries.blockSignals(True)
        self.retries.setValue(-1 if retries is None else retries)
        self.retries.blockSignals(False)
        self.editor_path.setText(str(EditorLocator(self.config.snapshot()).roots()[0]))
        self.download_path.setText(str(self.config.get("download_dir") or tempfile.gettempdir()))


class TemplatesSection(SettingsSection):
    KEY = "nav.templates"

    def build(self):
        inner = self.block("settings.template_location", "settings.template_location_help")
        self.template_path = self.path_row(inner, self.choose_templates)

    def choose_templates(self):
        path = self.settings.folder("settings.template_dir", self.template_path.text())
        if path:
            self.config.set("template_root", path)
            self.launcher.new.load(force=True)

    def refresh(self):
        self.template_path.setText(str(self.config.get("template_root") or unity_paths.HUB / "Templates"))


class AppearanceSection(SettingsSection):
    KEY = "settings.appearance"

    def build(self):
        inner = self.block("settings.theme", "settings.theme_help")
        row = self.action_row(inner)
        self.theme = self.button(row, "settings.theme", self.choose_theme)
        self.button(row, "settings.import_theme", self.import_theme)
        inner = self.block("tray.when", "settings.tray_help")
        self.check(inner, "tray.editor", "editor_to_tray")
        self.check(inner, "tray.close", "close_to_tray")
        inner = self.block("settings.language", "settings.language_help")
        self.language_combo = LanguageSelector(self, self.settings.language_changed)
        self.action_row(inner).addWidget(self.language_combo)

    def choose_theme(self):
        manager = self.launcher.manager
        qt.theme_menu(self, self.theme, manager.name, manager.apply)

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
            self.config.set("themes", custom)
            self.launcher.custom_themes.reload(custom)
            self.launcher.manager.apply(qt.pick_theme(name))
        except (OSError, ValueError, KeyError, TypeError):
            self.settings.warning(tr("settings.bad_theme"))


class NotificationsSection(SettingsSection):
    KEY = "settings.notifications"

    def build(self):
        inner = self.block("settings.notifications", "settings.notify_help")
        self.check(inner, "settings.job_alerts", "job_notifications")
        inner = self.block("settings.banners", "settings.banners_help")
        self.check(inner, "settings.show_banners", "banners_enabled")
        self.dismissed = QLabel()
        inner.addWidget(self.dismissed)
        self.button(self.action_row(inner), "settings.banners_restore", lambda: self.config.set("dismissed_banners", []))

    def refresh(self):
        super().refresh()
        call(self.dismissed.setText, tr("settings.dismissed", len(self.config.get("dismissed_banners"))))


class PrivacySection(SettingsSection):
    KEY = "settings.privacy"

    def build(self):
        self.check(self.block("settings.privacy", "settings.privacy_help"), "tray.list", "tray_projects")


class AdvancedSection(SettingsSection):
    KEY = "settings.advanced"

    def build(self):
        self.downloading_cli = False
        inner = self.block("settings.cli_title", "settings.cli_help")
        self.cli_status = QLabel()
        inner.addWidget(self.cli_status)
        self.cli_button = self.button(self.action_row(inner), "cli.download", self.download_cli, "primary")
        inner = self.block("settings.launch_title", "settings.launch_help")
        inner.addWidget(QLabel("XDG_SESSION_TYPE = " + os.environ.get("XDG_SESSION_TYPE", "—")))
        row = self.action_row(inner)
        self.settings.label(row, "settings.renderer", "")
        self.renderer = QComboBox()
        call(self.renderer.addItem, tr("settings.default"), "")
        self.renderer.addItem("Vulkan", "-force-vulkan")
        self.renderer.addItem("OpenGL Core", "-force-glcore")
        self.renderer.currentIndexChanged.connect(lambda: self.config.set("renderer", self.renderer.currentData()))
        row.addWidget(self.renderer)
        self.settings.label(inner, "args.global")
        self.arguments = QLineEdit(self.config.get("arguments"))
        self.arguments.editingFinished.connect(self.save_arguments)
        inner.addWidget(self.arguments)
        inner = self.block("settings.tools_title")
        row = self.action_row(inner)
        self.button(row, "tool.picker", lambda: self.tool("equestria-color-picker", "equestria_color_picker.py"))
        self.button(row, "tool.log", lambda: self.tool("equestria-unity-log", "logwatch.py"))

    def refresh(self):
        self.renderer.blockSignals(True)
        self.renderer.setCurrentIndex(max(0, self.renderer.findData(self.config.get("renderer"))))
        self.renderer.blockSignals(False)
        if not self.arguments.hasFocus():
            self.arguments.setText(self.config.get("arguments"))
        path = self.launcher.cli.executable()
        if self.downloading_cli:
            call(self.cli_status.setText, tr("cli.downloading"))
        elif path:
            self.cli_status.setText(f"Unity CLI · {path}")
        else:
            call(self.cli_status.setText, tr("cli.missing"))
        self.cli_button.setEnabled(not self.downloading_cli)
        self.cli_button.setVisible(not path)

    def download_cli(self):
        destination = Path.home() / ".local/bin/unity"
        if self.downloading_cli or not self.settings.confirm("cli.confirm", destination):
            return
        self.downloading_cli = True
        self.refresh()

        def completed(result):
            self.downloading_cli = False
            self.settings.refresh()
            window = self.launcher
            window.cli_shortcut.setVisible(not window.cli.executable())
            window.banners.update_banners()
            if isinstance(result, Exception):
                self.settings.warning(str(result))
            else:
                window.notify(tr("cli.ready", result), "ok")

        self.settings.background(lambda: cli_download.download(destination), completed)

    def save_arguments(self):
        try:
            shlex.split(self.arguments.text())
        except ValueError as error:
            self.settings.warning(error)
            self.arguments.setText(self.config.get("arguments"))
            return
        self.config.set("arguments", self.arguments.text())

    def tool(self, name, script):
        exe = unity_paths.executable(name)
        source = ROOT.parent / name / script
        if not exe and not source.is_file():
            self.settings.warning(tr("tool.missing", name))
            return
        try:
            subprocess.Popen([exe] if exe else [sys.executable, str(source)], start_new_session=True)
        except OSError as error:
            self.settings.warning(error)


class AboutSection(SettingsSection):
    KEY = "settings.about"

    def build(self):
        inner = self.block("settings.versions", "settings.versions_help")
        self.versions = QLabel()
        self.versions.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inner.addWidget(self.versions)

    def refresh(self):
        path = self.launcher.cli.executable()
        self.versions.setText(f"Equestria Unity {VERSION}\nQt {qVersion()}\nPython {sys.version.split()[0]}\n"
                              f"Unity CLI {path or '—'}")


SECTIONS = (LicensesSection, ProjectsSection, InstallsSection, TemplatesSection, AppearanceSection,
            NotificationsSection, PrivacySection, AdvancedSection, AboutSection)
