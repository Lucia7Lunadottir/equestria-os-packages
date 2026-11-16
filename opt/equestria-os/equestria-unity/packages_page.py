"""The Packages page, like Unity's Package Manager: “In project” lists the chosen project's packages from its files;
“Unity Registry” lists what Unity offers for the project's Editor version, and adds a package to manifest.json."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QPushButton, QTreeWidget, QTreeWidgetItem)

from controls import Page, open_folder
from kit import call, tr
from project_packages import EditorPackageCatalog, ProjectPackages

SOURCES = {"registry": "package.source_registry", "builtin": "package.source_builtin", "git": "package.source_git",
           "local": "package.source_local", "embedded": "package.source_embedded",
           "local-tarball": "package.source_tarball"}
PROJECT, REGISTRY = "project", "registry"
ENTRY = Qt.ItemDataRole.UserRole


class Packages(Page):
    def __init__(self, window):
        super().__init__(window)
        self.mode = PROJECT
        self.entries = []          # what the table shows in the current mode
        self.installed = {}        # identifier -> version the project asks for (marks the registry list)
        self.target = QComboBox()
        self.target.setMinimumWidth(320)
        self.target.currentIndexChanged.connect(lambda _: self.load())
        self.title("nav.packages", self.target)

        bar = self.row()
        self.modes = {}
        for mode, key in ((PROJECT, "package.in_project"), (REGISTRY, "package.registry")):
            button = call(QPushButton, tr(key))
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _=False, m=mode: self.switch(m))
            bar.addWidget(button)
            self.modes[mode] = button
        bar.addSpacing(10)
        self.search = QLineEdit()
        call(self.search.setPlaceholderText, tr("package.search"))
        self.search.setMinimumWidth(220)
        self.search.textChanged.connect(lambda _: self.show_entries())
        bar.addWidget(self.search)
        self.all = call(QCheckBox, tr("package.dependencies"))
        self.all.toggled.connect(lambda _: self.show_entries())
        bar.addWidget(self.all)
        bar.addStretch()
        self.button(bar, "license.refresh", self.load)
        self.button(bar, "package.open_manifest", self.open_manifest)

        self.table = QTreeWidget()
        self.table.setObjectName("packages")
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        # A Git or file: package has a whole URL as its version: fixed widths keep it from pushing the names away.
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setColumnCount(4)
        header = self.table.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in ((2, 130), (3, 150)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(column, width)
        self.table.itemSelectionChanged.connect(self.selected_changed)
        self.table.itemDoubleClicked.connect(lambda *_: self.add_selected())
        self.layout_box.addWidget(self.table, 1)
        self.note = QLabel()
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        self.layout_box.addWidget(self.note)

        selection = self.row()
        self.details = QLabel()
        self.details.setObjectName("hint")
        self.details.setWordWrap(True)
        selection.addWidget(self.details, 1)
        self.add_button = self.button(selection, "package.add_to_project", self.add_selected, "primary")

        _, inner = self.card()
        self.label(inner, "package.add_title", "rowname")
        self.label(inner, "package.help")
        line = QHBoxLayout()
        self.identifier = QLineEdit()
        self.identifier.setPlaceholderText("com.unity.cinemachine@3.1.0")
        self.identifier.returnPressed.connect(self.install)
        line.addWidget(self.identifier, 1)
        self.button(line, "package.install", self.install, "primary")
        inner.addLayout(line)
        line = QHBoxLayout()
        self.button(line, "package.pipeline", lambda: self.command(self.cli.pipeline_install))
        self.button(line, "package.import", self.import_asset)
        line.addStretch()
        inner.addLayout(line)
        window.catalog.changed.connect(self.refresh)
        self.switch(PROJECT, load=False)

    # ---- choosing what is shown -----------------------------------------------------------------

    def switch(self, mode, load=True):
        self.mode = mode
        for name, button in self.modes.items():
            button.setChecked(name == mode)
        self.all.setVisible(mode == PROJECT)
        call(self.table.setHeaderLabels, [tr("package.col_name"), tr("package.col_id"),
                                          tr("package.col_version" if mode == PROJECT else "package.col_recommended"),
                                          tr("package.col_source" if mode == PROJECT else "package.col_state")])
        if load:
            self.load()

    def refresh(self):
        chosen = self.window.projects.selected(False)
        old = self.target.currentData()
        self.target.blockSignals(True)
        self.target.clear()
        for project in self.window.catalog.items:
            if project.version:
                self.target.addItem(project.name, str(project.path))
                self.target.setItemData(self.target.count() - 1, str(project.path), Qt.ItemDataRole.ToolTipRole)
        index = self.target.findData(str(chosen) if chosen else old)
        self.target.setCurrentIndex(max(index, 0))
        self.target.blockSignals(False)
        self.load()

    def project(self):
        path = self.target.currentData()
        return self.window.catalog.find(path) if path else None

    def load(self):
        """Read the package files again (they change when the Editor resolves packages) in the background."""
        project = self.project()
        self.entries = []
        packages = ProjectPackages(project.path) if project else None
        if packages is None or not packages.exists():
            call(self.note.setText, tr("package.no_manifest") if project else tr("project.select"))
            self.show_entries()
            return
        call(self.note.setText, tr("account.loading"))
        key = (str(project.path), self.mode)
        if self.mode == PROJECT:
            self.background(packages.entries, lambda result: self.loaded(key, result, {}))
            self.show_entries()
            return
        editor = self.window.editors.get(project.version)
        if editor is None:
            call(self.note.setText, tr("package.need_editor", project.version))
            self.show_entries()
            return
        catalog = EditorPackageCatalog(editor)
        self.background(lambda: (catalog.entries(), packages.wanted()),
                        lambda result: self.loaded(key, *(result if isinstance(result, tuple) else (result, {}))))
        self.show_entries()

    def loaded(self, key, result, installed):
        if key != (self.target.currentData(), self.mode):
            return  # another project or mode was chosen meanwhile
        self.entries = [] if isinstance(result, Exception) else result
        self.installed = installed if isinstance(installed, dict) else {}
        self.note.clear()
        self.show_entries()

    def show_entries(self):
        query = self.search.text().strip().casefold()
        self.table.clear()
        for entry in self.entries:
            if self.mode == PROJECT and not (entry.direct or self.all.isChecked()):
                continue
            if query and query not in entry.title.casefold() and query not in entry.identifier.casefold():
                continue
            if self.mode == PROJECT:
                source = SOURCES.get(entry.source)
                last = tr(source) if source else entry.source
            else:
                have = self.installed.get(entry.identifier)
                last = tr("package.installed", have) if have else ""
            item = call(QTreeWidgetItem, self.table, [entry.title, entry.identifier, entry.version, last])
            item.setData(0, ENTRY, entry)
            item.setToolTip(0, entry.description or entry.title)
            item.setToolTip(2, entry.version)
        shown = bool(self.entries)
        self.table.setVisible(shown)
        self.note.setVisible(not shown)
        self.selected_changed()

    def selected_entry(self):
        item = self.table.currentItem()
        return item.data(0, ENTRY) if item else None

    def selected_changed(self):
        registry = self.mode == REGISTRY
        entry = self.selected_entry() if registry else None
        self.details.setVisible(registry)
        self.add_button.setVisible(registry)
        self.details.setText(entry.description if entry else "")
        self.add_button.setEnabled(entry is not None and entry.identifier not in self.installed)

    # ---- changing the project -------------------------------------------------------------------

    def add_selected(self):
        entry = self.selected_entry()
        project = self.project()
        if self.mode != REGISTRY or entry is None or project is None or entry.identifier in self.installed:
            return
        if not self.confirm("package.confirm_add", entry.title, entry.version):
            return
        try:
            ProjectPackages(project.path).add(entry.identifier, entry.version)
        except (OSError, ValueError) as error:
            self.warning(error)
            return
        self.window.notify(tr("package.added", entry.title), "ok")
        self.load()

    def open_manifest(self):
        project = self.project()
        if project and ProjectPackages(project.path).exists():
            open_folder(ProjectPackages(project.path).manifest_path)
        else:
            self.warning(tr("package.no_manifest"))

    def command(self, operation, *args):
        """Run a package operation of the Unity CLI on the chosen project; the list is read again afterwards."""
        path = self.target.currentData()
        if not path:
            self.warning(tr("project.select"))
            return
        operation(path, *args, done=lambda _: self.load())

    def install(self):
        name = self.identifier.text().strip()
        if name and not name.startswith("-"):
            self.command(self.cli.package_add, name)
        else:
            self.identifier.setFocus()

    def import_asset(self):
        path = QFileDialog.getOpenFileName(self, str(tr("package.import")), "", "Unity (*.unitypackage)")[0]
        if path:
            self.command(self.cli.import_package, path)
