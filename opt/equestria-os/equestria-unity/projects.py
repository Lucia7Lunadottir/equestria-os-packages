from pathlib import Path
import shlex

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QGuiApplication
from PyQt6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMenu, QPushButton, QSpinBox, QVBoxLayout, QWidget)

import editor_launch
from git_tools import GitActions
from project_table import MODIFIED, NAME, STAR, VERSION, ProjectRow, ProjectTable
from controls import Page, open_folder
from formatting import short
from kit import call, tr
from versions import version_key

class FoldersPanel(QWidget):
    """List of project search folders with add / remove and the search depth. Used in Settings and in a dialog."""

    def __init__(self, catalog):
        super().__init__()
        self.catalog = catalog
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.view = QListWidget()
        self.view.setObjectName("folders")
        self.view.setMinimumHeight(120)
        layout.addWidget(self.view, 1)
        row = QHBoxLayout()
        add = call(QPushButton, tr("folders.add"))
        add.setObjectName("primary")
        add.setProperty("compact", True)
        add.clicked.connect(self.add)
        self.remove_button = call(QPushButton, tr("folders.remove"))
        self.remove_button.setObjectName("small")
        self.remove_button.clicked.connect(self.remove)
        row.addWidget(add)
        row.addWidget(self.remove_button)
        row.addStretch()
        row.addWidget(call(QLabel, tr("folders.depth")))
        self.depth = QSpinBox()
        self.depth.setRange(1, 8)
        self.depth.setValue(catalog.config.get("scan_depth"))
        self.depth.valueChanged.connect(lambda v: catalog.config.set("scan_depth", v))
        row.addWidget(self.depth)
        layout.addLayout(row)
        catalog.config.changed.connect(self.on_change)
        self.fill()

    def on_change(self, key):
        if key == "scan_dirs":
            self.fill()
        elif key == "scan_depth":
            self.depth.blockSignals(True)
            self.depth.setValue(self.catalog.config.get("scan_depth"))
            self.depth.blockSignals(False)

    def fill(self):
        self.view.clear()
        for path in self.catalog.scan_dirs():
            item = QListWidgetItem(short(path), self.view)
            item.setData(Qt.ItemDataRole.UserRole, path)
        self.remove_button.setEnabled(self.view.count() > 0)
        self.update_tooltips()

    def update_tooltips(self):
        for row in range(self.view.count()):
            item = self.view.item(row)
            path = item.data(Qt.ItemDataRole.UserRole)
            item.setToolTip(path if Path(path).is_dir() else str(tr("folders.missing")))

    def add(self):
        path = QFileDialog.getExistingDirectory(self, str(tr("folders.add")), str(Path.home()))
        if path:
            self.catalog.add_scan_dir(path)

    def remove(self):
        item = self.view.currentItem()
        if item:
            self.catalog.remove_scan_dir(item.data(Qt.ItemDataRole.UserRole))


class FoldersDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        call(self.setWindowTitle, tr("folders.title"))
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title = call(QLabel, tr("folders.title"))
        title.setObjectName("title")
        layout.addWidget(title)
        hint = call(QLabel, tr("folders.help"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(FoldersPanel(page.catalog), 1)
        done = call(QPushButton, tr("folders.done"))
        done.setObjectName("small")
        done.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(done)
        layout.addLayout(bottom)


class Projects(Page):
    def __init__(self, window):
        super().__init__(window)
        self.catalog = window.catalog
        self.editors = window.editors
        self.git_tools = GitActions(self)
        self.sort_key = self.config.get("sort_key")
        self.sort_down = bool(self.config.get("sort_down"))
        self.only_versions = set()
        self.search = QLineEdit()
        call(self.search.setPlaceholderText, tr("projects.search"))
        self.search.setMinimumWidth(220)
        self.search.textChanged.connect(self.redraw)
        add = call(QPushButton, tr("projects.add"))
        add.setObjectName("small")
        add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        menu = QMenu(add)
        call(menu.addAction, tr("projects.add_folder")).triggered.connect(self.add)
        call(menu.addAction, tr("projects.folders")).triggered.connect(self.manage_folders)
        call(menu.addAction, tr("projects.clone")).triggered.connect(lambda: self.git_tools.clone())
        for provider in ("GitHub", "GitLab"):
            menu.addAction(provider + "…").triggered.connect(lambda _=False, p=provider: self.git_tools.repositories(p))
        add.setMenu(menu)
        create = call(QPushButton, tr("projects.create"))
        create.setObjectName("primary")
        create.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        create.clicked.connect(lambda: self.window.go("new"))
        self.title("nav.projects", self.search, add, create)

        bar = self.row()
        self.version_filter = call(QPushButton, tr("projects.filter_version"))
        self.version_filter.setObjectName("small")
        self.version_filter.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.version_filter.clicked.connect(self.filter_menu)
        bar.addWidget(self.version_filter)
        self.summary = QLabel()
        self.summary.setObjectName("hint")
        bar.addWidget(self.summary)
        bar.addStretch()

        self.table = ProjectTable()
        self.table.model().modelReset.connect(self.sort_indicator)
        self.table.header().sectionClicked.connect(self.header_clicked)
        self.table.star_clicked.connect(self.toggle_star)
        self.table.open_requested.connect(self.open)
        self.table.version_requested.connect(lambda project, point: self.version_menu(project).exec(point))
        self.table.git_requested.connect(self.open_git)
        self.table.menu_requested.connect(lambda project, point: self.menu(project).exec(point))
        self.layout_box.addWidget(self.table, 1)

        self.empty = QFrame()
        self.empty.setObjectName("hero")
        box = QVBoxLayout(self.empty)
        box.setContentsMargins(32, 32, 32, 32)
        box.setSpacing(10)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title = QLabel()
        self.empty_title.setObjectName("big")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint = QLabel()
        self.empty_hint.setObjectName("hint")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self.empty_title)
        box.addWidget(self.empty_hint)
        self.empty_buttons = QHBoxLayout()
        self.empty_buttons.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.button(self.empty_buttons, "projects.add_folder", self.add, "primary")
        self.button(self.empty_buttons, "projects.create", lambda: self.window.go("new"))
        box.addLayout(self.empty_buttons)
        self.layout_box.addWidget(self.empty, 1)
        self.catalog.changed.connect(self.redraw)
        self.editors.changed.connect(self.redraw)
        self.config.changed.connect(lambda key: key in ("favorites", "opened", "sort_key", "sort_down")
                                    and self.redraw())
        self.redraw()

    # ---- data ------------------------------------------------------------------------------

    def visible(self):
        query = self.search.text().strip().casefold()
        opened = self.config.get("opened")
        last = lambda p: max(opened.get(str(p.path), 0), p.modified)
        found = [p for p in self.catalog.items
                 if (not query or query in p.name.casefold() or query in str(p.path).casefold()
                     or query in p.version.casefold())
                 and (not self.only_versions or p.version in self.only_versions)]
        if self.sort_key == "name":
            found.sort(key=lambda p: p.name.casefold(), reverse=self.sort_down)
        elif self.sort_key == "version":
            found.sort(key=lambda p: (version_key(p.version), p.name.casefold()), reverse=self.sort_down)
        else:
            found.sort(key=last, reverse=self.sort_down)
        if self.sort_key == "favorite":
            stars = self.catalog.favorites()
            found.sort(key=lambda p: str(p.path) in stars, reverse=self.sort_down)
        return found

    def header_clicked(self, column):
        key = {STAR: "favorite", NAME: "name", VERSION: "version", MODIFIED: "recent"}.get(column)
        if key:
            self.sort_down = not self.sort_down if key == self.sort_key else (key in ("recent", "favorite"))
            self.sort_key = key
            self.sort_indicator()
            self.config.set("sort_key", key)
            self.config.set("sort_down", self.sort_down)  # either change redraws the table

    def sort_indicator(self):
        header = self.table.header()
        column = {"favorite": STAR, "name": NAME, "version": VERSION, "recent": MODIFIED}.get(self.sort_key, MODIFIED)
        header.setSortIndicator(column, Qt.SortOrder.DescendingOrder if self.sort_down else Qt.SortOrder.AscendingOrder)
        header.setSortIndicatorShown(True)

    def filter_menu(self):
        menu = QMenu(self)
        for version in sorted(self.catalog.versions(), key=version_key, reverse=True):
            action = menu.addAction(version)
            action.setCheckable(True)
            action.setChecked(version in self.only_versions)
            action.toggled.connect(lambda on, v=version: self.toggle_version(v, on))
        if not menu.actions():
            return
        menu.exec(self.version_filter.mapToGlobal(self.version_filter.rect().bottomLeft()))

    def toggle_version(self, version, on):
        (self.only_versions.add if on else self.only_versions.discard)(version)
        self.redraw()

    # ---- drawing ---------------------------------------------------------------------------

    def redraw(self, *_):
        """Rebuild the table rows from the catalog, the search box and the version filter."""
        editors = self.editors.all()
        shown = self.visible()
        stars = self.catalog.favorites()
        opened = self.config.get("opened")
        rows = [ProjectRow(project, str(project.path) in stars, project.version in editors,
                           max(opened.get(str(project.path), 0), project.modified)) for project in shown]
        self.table.show_rows(rows, keep=self.selected(False))
        dirs = self.catalog.scan_dirs()
        scanning = self.catalog.scanning
        if scanning:
            call(self.summary.setText, tr("projects.scanning"))
        else:
            call(self.summary.setText, tr("projects.summary", len(shown), ", ".join(short(d) for d in dirs) or "—"))
        has = bool(shown)
        self.table.setVisible(has)
        self.empty.setVisible(not has and not scanning)
        if not has:
            filtered = bool(self.search.text().strip() or self.only_versions) and bool(self.catalog.items)
            call(self.empty_title.setText, tr("projects.nothing" if filtered else "projects.empty_title"))
            call(self.empty_hint.setText, tr("projects.empty_hint") if not filtered else "")
            for index in range(self.empty_buttons.count()):
                self.empty_buttons.itemAt(index).widget().setVisible(not filtered)

    def toggle_star(self, project):
        self.catalog.toggle_favorite(project)

    def version_menu(self, project):
        """Pick the editor version this project is opened with."""
        editors = self.editors.all()
        menu = QMenu(self)
        if project.version and project.version not in editors:
            call(menu.addAction, tr("projects.install", project.version)).triggered.connect(
                lambda: self.need_editor(project.version))
            menu.addSeparator()
        for version in sorted(editors, key=version_key, reverse=True):
            action = menu.addAction(version + ("   ✓" if version == project.version else ""))
            action.triggered.connect(lambda _=False, v=version: self.open_with(project, v))
        return menu

    def open_with(self, project, version):
        if version == project.version:
            self.open(project)
        else:
            self.upgrade(project, version)

    # ---- selection and menus -----------------------------------------------------------------

    def current_project(self):
        return self.table.current_project()

    def selected(self, warn=True):
        project = self.table.current_project()
        if project is not None:
            return project.path
        if warn:
            self.warning(tr("project.select"))
        return None

    def menu(self, project):
        menu = QMenu(self)
        call(menu.addAction, tr("projects.open")).triggered.connect(lambda: self.open(project))
        call(menu.addAction, tr("projects.show_folder")).triggered.connect(lambda: open_folder(project.path))
        call(menu.addAction, tr("projects.copy_path")).triggered.connect(
            lambda: QGuiApplication.clipboard().setText(str(project.path)))
        call(menu.addAction, tr("git.panel")).triggered.connect(lambda: self.open_git(project, QCursor.pos()))
        call(menu.addAction, tr("args.project")).triggered.connect(lambda: self.edit_project_args(project))
        menu.addSeparator()
        call(menu.addAction, tr("projects.hide")).triggered.connect(lambda: self.hide_project(project))
        return menu

    def open_git(self, project, point):
        menu = self.git_tools.open(project)
        if menu is not None:
            menu.exec(point)

    # ---- adding projects and folders -----------------------------------------------------------

    def edit_project_args(self, project):
        key = str(project.path.resolve())
        args = self.config.get("project_arguments")
        self.edit_arguments("args.project", args.get(key, ""),
                            lambda value: self.save("project_arguments", {**args, key: value}))

    def add(self):
        path = self.folder("projects.add_folder", str(Path.home()))
        if path:
            self.add_path(path)

    def add_path(self, path):
        """A project folder is added as a project; any other folder becomes a search folder."""
        name = Path(path).resolve().name
        added = self.catalog.add(path)
        self.window.notify(tr("projects.added_project" if added else "projects.added_folder", name), "ok")
        self.search.clear()

    def manage_folders(self):
        FoldersDialog(self).exec()

    def hide_project(self, project):
        self.catalog.hide(project)

    # ---- running the editor ------------------------------------------------------------------

    def need_editor(self, version):
        self.window.notify(tr("editor.missing", version), "fail")
        self.window.go("editors")
        self.window.installs.request_install(version)

    def open(self, project=None):
        project = project or self.current_project()
        if not project:
            self.warning(tr("project.select"))
            return
        if not project.version:
            self.warning(tr("project.invalid", project.path))
            return
        editor = self.editors.get(project.version)
        if not editor:
            self.need_editor(project.version)
            return
        self.start(editor, project)

    def start(self, editor, project):
        try:
            process = editor_launch.launch(editor, project.path, self.config.snapshot())
        except (ValueError, OSError) as error:
            self.warning(error)
            return
        self.jobs.message.emit(shlex.join(process.args))
        self.catalog.touch(project.path)
        self.window.notify(tr("projects.launching", project.name), "busy", 8000)
        self.window.editor_started(project.path)

    def upgrade(self, project, version):
        editor = self.editors.get(version)
        if editor and self.confirm("project.confirm_upgrade", project.name, version):
            self.start(editor, project)
