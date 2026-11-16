import re
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QPushButton, QVBoxLayout)

import library
from controls import Page, icon
from previews import Previews
from installs import version_key
from kit import call, tr

# Word in the template name -> short mark on its picture. First match wins.
GLYPHS = (("hdrp", "HD"), ("urp", "URP"), ("universal", "URP"), ("2d", "2D"), ("3d", "3D"),
          ("vr", "VR"), ("ar", "AR"), ("xr", "XR"), ("mobile", "▯"))


def glyph(title):
    words = re.findall(r"[a-z0-9]+", title.casefold())
    return next((mark for key, mark in GLYPHS if key in words), "▢")


class NewProject(Page):
    """Pick an editor version and a template, name the project and create it (like Unity Hub)."""

    def __init__(self, window):
        super().__init__(window)
        self.previews = Previews(self)
        self.previews.ready.connect(self.preview_ready)
        self.templates = []
        self.loaded = None
        self.local = []
        self.remote = []
        outer = QHBoxLayout()
        outer.setSpacing(18)
        self.layout_box.addLayout(outer, 1)

        left = QVBoxLayout()
        left.setSpacing(12)
        outer.addLayout(left, 1)
        head = QHBoxLayout()
        back = QPushButton("←")
        back.setObjectName("flat")
        back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        back.clicked.connect(lambda: self.window.go("projects"))
        head.addWidget(back)
        title = call(QLabel, tr("nav.new"))
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch()
        self.button(head, "nav.services", lambda: self.window.go("services"))
        left.addLayout(head)

        top = QHBoxLayout()
        top.setSpacing(10)
        column = QVBoxLayout()
        column.setSpacing(4)
        column.addWidget(call(QLabel, tr("editor.version")))
        self.version = QComboBox()
        self.version.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.version.setMinimumWidth(240)
        self.version.activated.connect(lambda *_: self.load())
        column.addWidget(self.version)
        top.addLayout(column)
        top.addStretch()
        self.search = QLineEdit()
        call(self.search.setPlaceholderText, tr("new.search"))
        self.search.setMinimumWidth(220)
        self.search.textChanged.connect(self.show_cards)
        top.addWidget(self.search, 0, Qt.AlignmentFlag.AlignBottom)
        left.addLayout(top)

        filters = QHBoxLayout()
        self.category = QComboBox()
        for category in ("all", "sample", "learning"):
            call(self.category.addItem, tr("template." + category), category)
        self.category.currentIndexChanged.connect(self.show_cards)
        filters.addWidget(self.category)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        filters.addWidget(self.feedback, 1)
        self.button(filters, "release.retry", lambda: self.load(force=True))
        left.addLayout(filters)

        self.grid = QListWidget()
        self.grid.setObjectName("grid")
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setIconSize(QSize(270, 140))
        self.grid.setGridSize(QSize(300, 206))
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setSpacing(6)
        self.grid.setWordWrap(True)
        self.grid.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.grid.itemSelectionChanged.connect(self.selected)
        self.grid.itemDoubleClicked.connect(lambda *_: self.name.setFocus())
        left.addWidget(self.grid, 1)
        self.empty = QLabel()
        self.empty.setObjectName("hint")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.empty)
        self.to_editors = self.button(left, "new.get_editor", lambda: self.window.go("editors"))

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(340)
        inner = QVBoxLayout(panel)
        inner.setContentsMargins(18, 18, 18, 18)
        inner.setSpacing(8)
        outer.addWidget(panel)
        self.template_name = QLabel()
        self.template_name.setObjectName("big")
        self.template_name.setWordWrap(True)
        inner.addWidget(self.template_name)
        self.about = QLabel()
        self.about.setObjectName("hint")
        self.about.setWordWrap(True)
        self.about.setAlignment(Qt.AlignmentFlag.AlignTop)
        inner.addWidget(self.about)
        inner.addSpacing(10)
        inner.addWidget(call(QLabel, tr("new.name")))
        self.name = QLineEdit()
        self.name.textChanged.connect(self.check)
        inner.addWidget(self.name)
        inner.addWidget(call(QLabel, tr("new.location")))
        line = QHBoxLayout()
        self.location = QLineEdit()
        self.location.textChanged.connect(self.check)
        line.addWidget(self.location, 1)
        self.button(line, "new.browse", self.browse)
        inner.addLayout(line)
        self.result = QLabel()
        self.result.setObjectName("hint")
        self.result.setWordWrap(True)
        inner.addWidget(self.result)
        inner.addStretch()
        self.make = call(QPushButton, tr("new.create"))
        self.make.setObjectName("primary")
        self.make.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.make.clicked.connect(self.create)
        inner.addWidget(self.make)
        self.reset_location()

    # ---- state -----------------------------------------------------------------------------

    def reset_location(self):
        dirs = library.scan_dirs(self.config.snapshot())
        folder = next((d for d in dirs if Path(d).is_dir()), str(Path.home() / "UnityProjects"))
        self.location.setText(folder)
        self.name.setText(library.free_name(folder))

    def refresh(self):
        keep = self.version.currentData()
        found = library.editors(self.config.snapshot())
        self.version.blockSignals(True)
        self.version.clear()
        for name in sorted(found, key=version_key, reverse=True):
            self.version.addItem(name, name)
        index = self.version.findData(keep)
        self.version.setCurrentIndex(max(0, index))
        self.version.blockSignals(False)
        has = bool(found)
        self.grid.setVisible(has)
        self.empty.setVisible(not has)
        self.to_editors.setVisible(not has)
        call(self.empty.setText, tr("editor.none"))
        self.load()

    def load(self, force=False):
        version = self.version.currentData()
        if version == self.loaded and not force:
            self.check()
            return
        self.loaded = version
        self.local, self.remote = [], []
        self.merge()
        if not version:
            self.feedback.clear()
            return
        editor = library.editors(self.config.snapshot()).get(version)
        if editor:
            folder = self.config.get("template_root")
            self.background(lambda: library.templates(editor, folder), lambda result: self.fill_local(version, result))
        call(self.feedback.setText, tr("release.loading"))
        self.jobs.run("templates:" + version, tr("template.browse"), ["templates", "--editor-version", version],
                      lambda data: self.fill_remote(version, data), structured=True,
                      failed=lambda reason: self.catalog_error(version, reason))

    def catalog_error(self, version, reason):
        if version == self.version.currentData():
            call(self.feedback.setText, tr("release.error", reason))

    def fill_local(self, version, result):
        if version == self.version.currentData() and not isinstance(result, Exception):
            self.local = result
            self.merge()

    def fill_remote(self, version, data):
        if version != self.version.currentData():
            return
        items = data["items"]
        if not isinstance(items, list):
            raise ValueError("templates.items")
        self.remote = []
        for entry in items:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"]:
                continue
            archive = entry.get("tar")
            path = Path(archive) if isinstance(archive, str) and archive else None
            preview = next((value for value in (entry.get("previewImage"), entry.get("dynamicIcon"))
                            if isinstance(value, str) and value.startswith("https://")), "")
            self.remote.append(library.Template(str(entry.get("displayName") or entry["name"]),
                               str(entry.get("description") or ""), path if path and path.is_file() else None,
                               entry["name"], str(entry.get("type", "")).lower(),
                               preview))
        call(self.feedback.setText, tr("template.local_only") if not any(t.path is None for t in self.remote) else "")
        self.merge()

    def merge(self):
        local = {t.path: t for t in self.local}
        for template in self.remote:
            archive = local.pop(template.path, None)
            if archive and not template.preview:
                template.preview = archive.preview
        self.templates = [None, *self.remote, *local.values()]
        self.show_cards()

    def show_cards(self, *_):
        """Rebuild the grid from the loaded templates, filtered by the search box."""
        keep = self.template()
        query = self.search.text().strip().casefold()
        self.grid.blockSignals(True)
        self.grid.clear()
        for template in self.templates:
            title = str(tr("project.empty")) if template is None else template.title
            category = self.category.currentData()
            if category != "all" and (not template or template.category != category):
                continue
            if query and query not in title.casefold():
                continue
            preview = self.previews.get(template.preview) if template and template.preview else None
            item = QListWidgetItem(preview or icon("∅" if template is None else glyph(title), title, QSize(270, 140)),
                                   title + ("  ↓" if template and not template.path else ""), self.grid)
            item.setData(Qt.ItemDataRole.UserRole, template)
            item.setSizeHint(QSize(300, 206))
            if template == keep:
                self.grid.setCurrentItem(item)
        if not self.grid.currentItem() and self.grid.count():
            self.grid.setCurrentRow(0)
        self.grid.blockSignals(False)
        self.selected()

    def preview_ready(self, source, image):
        for index in range(self.grid.count()):
            item = self.grid.item(index)
            template = item.data(Qt.ItemDataRole.UserRole)
            if template and template.preview == source:
                item.setIcon(image)

    def template(self):
        item = self.grid.currentItem()
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def selected(self):
        item = self.grid.currentItem()
        template = self.template()
        if not item:
            self.template_name.setText("")
            self.about.setText("")
        else:
            self.template_name.setText(str(tr("project.empty")) if template is None else template.title)
            self.about.setText(str(tr("new.empty_hint")) if template is None else template.description)
        self.check()

    def target(self):
        return Path(self.location.text().strip()).expanduser() / self.name.text().strip()

    def problem(self):
        name = self.name.text().strip()
        if library.bad_name(name):
            return tr("project.bad_name")
        if not self.location.text().strip():
            return tr("project.parent")
        try:
            exists = self.target().exists()
        except (RuntimeError, OSError, ValueError):
            return tr("project.parent")
        if exists:
            return tr("project.exists")
        if not self.version.currentData():
            return tr("editor.none")
        if not self.grid.currentItem():
            return tr("template.select")
        return ""

    def check(self, *_):
        problem = self.problem()
        self.make.setEnabled(not problem)
        if problem:
            self.result.setObjectName("err")
            call(self.result.setText, problem)
        else:
            self.result.setObjectName("hint")
            call(self.result.setText, tr("new.will_create", str(self.target())))
        self.result.style().unpolish(self.result)
        self.result.style().polish(self.result)

    def browse(self):
        path = self.folder("project.parent", self.location.text())
        if path:
            self.location.setText(path)
            self.name.setText(library.free_name(path, self.name.text().strip() or "My project"))

    # ---- create ----------------------------------------------------------------------------

    def create(self):
        if self.problem():
            return
        version = self.version.currentData()
        editor = library.editors(self.config.snapshot()).get(version)
        if not editor:
            self.warning(tr("editor.none"))
            return
        template = self.template()
        path = self.target()
        if template and template.path is None:
            def created(_):
                self.window.projects.remember_created(path)
                self.window.projects.refresh()
                self.window.go("projects")
                self.reset_location()
            self.jobs.run(str(path), tr("new.create"),
                          ["projects", "create", path.name, "--output-dir", str(path.parent),
                           "--editor-version", version, "--template", template.identifier, "--no-cloud"], created)
            return
        try:
            library.launch(editor, path, self.config.snapshot(), create=True,
                           template=template.path if template else None)
        except (ValueError, OSError) as error:
            self.warning(error)
            return
        self.window.projects.remember_created(path)
        self.jobs.message.emit(str(tr("new.started", path.name, version)))
        self.window.go("projects")
        self.reset_location()
        self.window.editor_started(path)
