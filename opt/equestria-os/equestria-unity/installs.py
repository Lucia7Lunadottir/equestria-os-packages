import os
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                             QPushButton, QVBoxLayout, QWidget)

from controls import Page, chip, open_folder, tile
from editor_locator import install_size
from install_plan import size_text
from install_wizard import InstallWizard
from kit import call, tr
from versions import RELEASE, release_title, version_key

PLATFORMS = {"AndroidPlayer": "Android", "LinuxStandaloneSupport": "Linux", "WebGLSupport": "Web",
             "WindowsStandaloneSupport": "Windows", "iOSSupport": "iOS", "MacStandaloneSupport": "Mac",
             "OSXStandaloneSupport": "Mac", "tvOSSupport": "tvOS", "LuminSupport": "Lumin", "VisionOSPlayer": "visionOS"}


def modules_of(editor):
    """Platform modules installed next to this Editor (like the chips in Unity Hub)."""
    names = {PLATFORMS[p.name] for p in (editor.parent / "Data/PlaybackEngines").glob("*") if p.name in PLATFORMS}
    return sorted(names)


class Installs(Page):
    def __init__(self, window):
        super().__init__(window)
        self.editors = window.editors
        self.catalog = window.catalog
        self.releases = window.release_info
        self.releases.updated.connect(self.refresh)
        self.sizes = {}          # Editor folder -> bytes on disk, measured once per session
        self.measuring = set()
        self.search = QLineEdit()
        call(self.search.setPlaceholderText, tr("editor.search"))
        self.search.setMinimumWidth(200)
        self.search.textChanged.connect(self.refresh)
        locate = call(QPushButton, tr("editor.locate"))
        locate.setObjectName("small")
        locate.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        locate.clicked.connect(self.locate)
        self.install_button = call(QPushButton, tr("editor.install_button"))
        self.install_button.setObjectName("primary")
        self.install_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.install_button.clicked.connect(lambda: self.open_wizard())
        self.title("nav.editors", self.search, locate, self.install_button)

        self.installed = QListWidget()
        self.installed.setObjectName("plist")
        self.installed.setSpacing(6)
        self.installed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.installed.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.layout_box.addWidget(self.installed, 1)
        self.editors.changed.connect(self.refresh)
        self.catalog.changed.connect(self.refresh)
        self.config.changed.connect(lambda key: key == "editor_profiles" and self.refresh())
        self.refresh()

    def refresh(self, *_):
        found = self.editors.all()
        counts = self.catalog.usage()
        query = self.search.text().strip().casefold()
        self.installed.clear()
        for version in self.editors.versions():
            if query and query not in version.casefold() and query not in str(found[version]).casefold():
                continue
            item = QListWidgetItem(self.installed)
            item.setSizeHint(QSize(100, 104))
            self.installed.setItemWidget(item, self.make_card(version, found[version], counts.get(version, 0)))

    def make_card(self, version, exe, count):
        card = QWidget()
        card.setObjectName("rowbody")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)
        picture = QLabel()
        picture.setPixmap(tile("U", version, 44, 44, 12))
        picture.setFixedSize(44, 44)
        layout.addWidget(picture, 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(4)
        top = QHBoxLayout()
        name = QLabel(f"{release_title(version)}  ({version})")
        name.setObjectName("rowname")
        top.addWidget(name)
        top.addWidget(chip(tr("editor.projects_count", count)))
        info = self.releases.get(version)
        if info.get("stream"):
            top.addWidget(chip(info["stream"], "ok" if info["stream"] == "LTS" else ""))
        label = self.releases.label(version)
        if label:
            alert = call(QPushButton, "⚠  " + tr("editor.security" if label.kind == "security" else "editor.warning"))
            alert.setObjectName("alert")
            alert.setProperty("lvl", "fail" if label.kind == "security" else "warn")
            alert.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            alert.setToolTip(label.text)
            if label.link:
                alert.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(label.link)))
            top.addWidget(alert)
        latest = info.get("latest", "")
        if latest and version_key(latest) > version_key(version) and latest not in self.editors:
            update = call(QPushButton, tr("editor.update_to", latest))
            update.setObjectName("update")
            update.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            update.clicked.connect(lambda: self.request_install(latest))
            top.addWidget(update)
        top.addStretch()
        column.addLayout(top)
        line = QHBoxLayout()
        path = QLabel(str(exe))
        path.setObjectName("hint")
        line.addWidget(path)
        size = self.size_of(exe)
        if size is not None:
            line.addWidget(call(QLabel, "·  " + size_text(size)))
            line.itemAt(line.count() - 1).widget().setObjectName("hint")
        line.addStretch()
        column.addLayout(line)
        chips = QHBoxLayout()
        for platform in modules_of(exe):
            chips.addWidget(chip(platform))
        chips.addStretch()
        column.addLayout(chips)
        layout.addLayout(column, 1)
        manage = call(QPushButton, tr("editor.manage") + "  ▾")
        manage.setObjectName("small")
        manage.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        menu = QMenu(manage)
        call(menu.addAction, tr("editor.add_modules")).triggered.connect(lambda: self.open_wizard(version=version))
        call(menu.addAction, tr("editor.updates")).triggered.connect(lambda: self.updates(version))
        call(menu.addAction, tr("projects.show_folder")).triggered.connect(lambda: open_folder(exe.parents[1]))
        profile_key = str(exe.resolve())
        profile = self.config.get("editor_profiles").get(profile_key, {})
        x11 = call(menu.addAction, tr("settings.x11"))
        x11.setCheckable(True)
        x11.setChecked(bool(profile.get("x11")))
        x11.toggled.connect(lambda checked: self.save_profile(profile_key, "x11", checked))
        call(menu.addAction, tr("args.editor")).triggered.connect(lambda: self.edit_profile_args(profile_key))
        menu.addSeparator()
        call(menu.addAction, tr("editor.uninstall")).triggered.connect(lambda: self.uninstall(version))
        manage.setMenu(menu)
        layout.addWidget(manage, 0, Qt.AlignmentFlag.AlignTop)
        return card

    def size_of(self, exe):
        """Bytes on disk, or None while it is being measured (the cards are redrawn when it is known)."""
        folder = str(exe.parents[1])
        if folder not in self.sizes and folder not in self.measuring:
            self.measuring.add(folder)

            def measured(result):
                self.measuring.discard(folder)
                if not isinstance(result, Exception):
                    self.sizes[folder] = result
                    self.refresh()
            self.background(lambda: install_size(exe), measured)
        return self.sizes.get(folder)

    def save_profile(self, engine, key, value):
        self.config.update("editor_profiles", lambda profiles: {
            **profiles, engine: {**profiles.get(engine, {}), key: value}})

    def edit_profile_args(self, engine):
        profile = self.config.get("editor_profiles").get(engine, {})
        self.edit_arguments("args.editor", profile.get("arguments", ""),
                            lambda value: self.save_profile(engine, "arguments", value))

    def locate(self):
        exe = QFileDialog.getOpenFileName(self, tr("editor.locate"), "", "Unity (Unity);;All (*)")[0]
        if not exe:
            return
        if not os.access(exe, os.X_OK):
            self.warning(tr("editor.invalid"))
            return
        version = self.text("editor.version", Path(exe).parents[1].name)
        if RELEASE.fullmatch(version):
            self.save("editors", {**self.config.get("editors"), version: exe})
        elif version:
            self.warning(tr("editor.invalid"))

    def set_folder(self):
        path = self.folder("editor.folder")
        if path:
            self.cli.set_install_path(path, lambda _: self.save("editor_root", path))

    # ---- installing ---------------------------------------------------------------------------------

    def open_wizard(self, **options):
        """Install an Editor (no options), add modules / install a known version (version=), or browse one line."""
        wizard = InstallWizard(self.cli, self.editors, self.tasks, self, failed=self.warning, **options)
        if wizard.exec():
            self.window.log.setChecked(True)
        wizard.deleteLater()

    def request_install(self, version):
        """Install the version a project needs: the wizard opens on its module list."""
        self.open_wizard(version=version)

    def updates(self, current):
        """Every patch of the same line (e.g. 6000.6.*), newest first; installed ones are marked."""
        self.open_wizard(search=".".join(current.split(".")[:2]) + ".")

    def uninstall(self, version):
        if self.config.get("no_confirm_remove") or self.confirm("editor.confirm_remove", version):
            folder = str(self.editors.get(version).parents[1]) if version in self.editors else None
            self.sizes.pop(folder, None)
            self.cli.uninstall(version, lambda _: self.editors.reload())
