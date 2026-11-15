import os
import re
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton, QVBoxLayout, QWidget)

import library
from controls import Page, chip, open_folder, tile
from kit import call, tr
from releases import ReleaseBrowser
from install_plan import Components, fetch_manifest, linux_download, size_text

from versions import RELEASE, version_key

MODULE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.+\-]*")

PLATFORMS = {"AndroidPlayer": "Android", "LinuxStandaloneSupport": "Linux", "WebGLSupport": "Web",
             "WindowsStandaloneSupport": "Windows", "iOSSupport": "iOS", "MacStandaloneSupport": "Mac",
             "OSXStandaloneSupport": "Mac", "tvOSSupport": "tvOS", "LuminSupport": "Lumin", "VisionOSPlayer": "visionOS"}


def modules_of(editor):
    """Platform modules installed next to this Editor (like the chips in Unity Hub)."""
    names = {PLATFORMS[p.name] for p in (editor.parent / "Data/PlaybackEngines").glob("*") if p.name in PLATFORMS}
    return sorted(names)


def title_of(version):
    match = RELEASE.fullmatch(version)
    if not match:
        return f"Unity {version}"
    major, minor = int(match.group(1)), match.group(2)
    return f"Unity {major // 1000 if major >= 6000 else major}.{minor}"


class Installs(Page):
    def __init__(self, window):
        super().__init__(window)
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
        self.install_button.clicked.connect(self.releases)
        self.title("nav.editors", self.search, locate, self.install_button)

        self.installed = QListWidget()
        self.installed.setObjectName("plist")
        self.installed.setSpacing(6)
        self.installed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.installed.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.layout_box.addWidget(self.installed, 1)

        self.form, inner = self.card()
        heading = call(QLabel, tr("editor.install_title"))
        heading.setObjectName("h2")
        inner.addWidget(heading)
        bar = QHBoxLayout()
        self.version = QComboBox()
        self.version.setEditable(True)
        self.version.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.version.lineEdit().setPlaceholderText("6000.6.9f1")
        bar.addWidget(self.version, 1)
        self.button(bar, "editor.releases", self.releases)
        inner.addLayout(bar)
        self.modules = QLineEdit()
        call(self.modules.setPlaceholderText, tr("editor.module_ids"))
        inner.addWidget(self.modules)
        self.eula = call(QCheckBox, tr("editor.eula"))
        inner.addWidget(self.eula)
        bar = QHBoxLayout()
        self.button(bar, "editor.module_list", lambda: self.install("list"))
        self.button(bar, "editor.preview", lambda: self.install("preview"))
        self.button(bar, "editor.modules", lambda: self.install("modules"))
        bar.addStretch()
        self.button(bar, "editor.install", lambda: self.install("install"), "primary")
        inner.addLayout(bar)
        self.form.setVisible(False)
        self.versions = []
        self.refresh()

    def show_install(self, on):
        self.form.setVisible(on)

    def refresh(self, *_):
        found = library.editors(self.config.snapshot())
        self.versions = sorted(found, key=version_key, reverse=True)
        counts = {}
        for project in self.window.projects.items:
            counts[project.version] = counts.get(project.version, 0) + 1
        query = self.search.text().strip().casefold()
        self.installed.clear()
        for version in self.versions:
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
        name = QLabel(f"{title_of(version)}  ({version})")
        name.setObjectName("rowname")
        top.addWidget(name)
        top.addWidget(chip(str(tr("editor.projects_count", count))))
        top.addStretch()
        column.addLayout(top)
        path = QLabel(str(exe))
        path.setObjectName("hint")
        column.addWidget(path)
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
        call(menu.addAction, tr("editor.add_modules")).triggered.connect(lambda: self.add_modules(version))
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

    def save_profile(self, engine, key, value):
        self.config.update("editor_profiles", lambda profiles: {
            **profiles, engine: {**profiles.get(engine, {}), key: value}})

    def edit_profile_args(self, engine):
        profile = self.config.get("editor_profiles").get(engine, {})
        self.edit_arguments("args.editor", profile.get("arguments", ""),
                            lambda value: self.save_profile(engine, "arguments", value))

    def add_modules(self, version):
        self.version.setEditText(version)
        self.show_install(True)
        self.pick_modules(version, review=True)

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
            self.refresh()
        elif version:
            self.warning(tr("editor.invalid"))

    def set_folder(self):
        path = self.folder("editor.folder")
        if path:
            def updated(_):
                self.save("editor_root", path)
                self.refresh()
            self.jobs.run("install", tr("editor.folder"), ["install-path", "--set", path], updated)

    def releases(self):
        dialog = ReleaseBrowser(self.versions, self)
        if dialog.exec():
            self.version.setEditText(dialog.selected)
            self.modules.clear()
            self.eula.setChecked(False)
            self.show_install(True)
            self.pick_modules(dialog.selected, dialog.selected_release, review=True)
        dialog.deleteLater()

    def updates(self, current):
        line = current.split(".")[:2]

        def newer(data):
            matches = []
            for entry in data["items"]:
                version = entry["version"]
                if version.split(".")[:2] == line and RELEASE.fullmatch(version):
                    if version_key(version) > version_key(current) and version not in self.versions:
                        matches.append(version)
            if matches:
                self.show_install(True)
                self.version.clear()
                self.version.addItems(sorted(matches, key=version_key, reverse=True))
                self.version.showPopup()
            else:
                self.jobs.message.emit(str(tr("editor.no_update", current)))

        self.jobs.run("releases", tr("editor.updates"), ["releases", "--limit", "100",
                      "--operating-system", "linux"], newer, structured=True)

    def pick_modules(self, version, release=None, *, review=False):
        installed = version in self.versions

        def show(entries):
            if self.version.currentText().strip() != version:
                return
            chosen = self.modules.text().replace(",", " ").split()
            dialog = Components(version, entries, chosen, self.eula.isChecked(), self)
            if dialog.exec():
                modules = dialog.selection()
                self.modules.setText(" ".join(modules))
                self.eula.setChecked(dialog.eula.isChecked())
                if review:
                    self.review(version, modules, installed)
            dialog.deleteLater()

        if installed:
            self.jobs.run("module-list", tr("editor.module_list"),
                          ["install-modules", "--editor-version", version, "--list"],
                          lambda data: show(data["items"]), structured=True, failed=self.warning)
        elif release:
            try:
                manifest = linux_download(release)
            except ValueError as error:
                self.warning(error)
                return
            show(manifest["modules"])
        else:
            self.window.notify(tr("release.loading"), "busy")
            def received(result):
                if isinstance(result, Exception):
                    self.warning(result)
                else:
                    show(result["modules"])
            self.background(lambda: fetch_manifest(version), received)

    def install(self, action):
        version = self.version.currentText().strip()
        if not RELEASE.fullmatch(version):
            self.warning(tr("editor.invalid"))
            return
        if action == "modules" and version not in self.versions:
            self.warning(tr("editor.select"))
            return
        if action != "preview":
            self.pick_modules(version, review=action != "list")
            return
        modules = self.modules.text().replace(",", " ").split()
        self.review(version, modules, version in self.versions and bool(modules), preview=True)

    def review(self, version, modules, installed, *, preview=False):
        if any(not MODULE.fullmatch(module) for module in modules) or (installed and not modules):
            self.warning(tr("editor.module_ids"))
            return
        args = ["install-modules", "--editor-version", version] if installed else ["install", version, "--resume"]
        if modules:
            args.extend(["--module", *modules, "--no-child-modules"])
        if self.eula.isChecked():
            args.append("--accept-eula")

        def planned(data):
            size = size_text(data.get("totalDownloadSize"))
            components = [str(m.get("name") or m.get("id")) for m in (data.get("modules") or [])
                          if isinstance(m, dict) and (m.get("name") or m.get("id"))]
            selected = ", ".join(dict.fromkeys([*modules, *components])) or str(tr("install.editor_only"))
            summary = tr("install.summary", version, selected, size)
            if preview:
                self.jobs.message.emit(str(summary))
                self.window.log.setChecked(True)
            elif self.confirm("install.confirm", summary):
                self.window.log.setChecked(True)
                self.jobs.run("install", tr("install.active", version), args + ["--yes"],
                              lambda _: self.refresh(), failed=self.warning)

        self.jobs.run("install-plan", tr("editor.preview"), args + ["--dry-run", "--yes"],
                      planned, structured=True, failed=self.warning)

    def uninstall(self, version):
        if self.config.get("no_confirm_remove") or self.confirm("editor.confirm_remove", version):
            self.jobs.run("install", tr("editor.uninstall"), ["uninstall", version, "--yes"],
                          lambda _: self.refresh())
