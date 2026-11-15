from pathlib import Path
import shlex
import time

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMenu, QPushButton, QSpinBox, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)

import library
from git_tools import GitActions
from controls import Page, open_folder
from installs import version_key
from kit import call, tr

def short(path):
    text = str(path)
    home = str(Path.home())
    return "~" + text[len(home):] if text == home or text.startswith(home + "/") else text


def when(stamp):
    unit, value = library.ago_parts(stamp)
    if unit == "none":
        return ""
    return str(tr("time.date", value) if unit == "date" else tr(f"time.{unit}", value))


class FoldersPanel(QWidget):
    """List of project search folders with add / remove and the search depth. Used in Settings and in a dialog."""

    def __init__(self, page):
        super().__init__()
        self.page = page
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
        value = page.config.get("scan_depth")
        self.depth.setValue(value if isinstance(value, int) else library.DEFAULT_DEPTH)
        self.depth.valueChanged.connect(lambda v: page.save("scan_depth", v))
        row.addWidget(self.depth)
        layout.addLayout(row)
        page.config.changed.connect(self.on_change)
        self.fill()

    def on_change(self, key):
        if key == "scan_dirs":
            self.fill()
        elif key == "scan_depth":
            self.depth.blockSignals(True)
            self.depth.setValue(self.page.config.get("scan_depth"))
            self.depth.blockSignals(False)

    def folders(self):
        return library.scan_dirs(self.page.config.snapshot())

    def fill(self):
        self.view.clear()
        for path in self.folders():
            item = QListWidgetItem(short(path), self.view)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path if Path(path).is_dir() else str(tr("folders.missing")))
        self.remove_button.setEnabled(self.view.count() > 0)

    def add(self):
        path = QFileDialog.getExistingDirectory(self, str(tr("folders.add")), str(Path.home()))
        if path:
            self.page.add_scan_dir(path, refresh=False)
            self.fill()

    def remove(self):
        item = self.view.currentItem()
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            self.page.save("scan_dirs", [p for p in self.folders() if p != path])
            self.fill()


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
        layout.addWidget(FoldersPanel(page), 1)
        done = call(QPushButton, tr("folders.done"))
        done.setObjectName("small")
        done.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(done)
        layout.addLayout(bottom)


class Clickable(QWidget):
    """A plain widget that reacts to a click, so a whole table cell can act like a button."""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.callback()


class Projects(Page):
    def __init__(self, window):
        super().__init__(window)
        self.git_tools = GitActions(self)
        self.items = []
        self.scanning = False
        self.again = False
        self.scanned = 0.0
        self.sort_key = self.config.get("sort_key")
        self.sort_down = bool(self.config.get("sort_down"))
        self.only_versions = set()
        self.search = QLineEdit()
        call(self.search.setPlaceholderText, tr("projects.search"))
        self.search.setMinimumWidth(220)
        self.search.textChanged.connect(self.render)
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

        self.tree = QTreeWidget()
        self.tree.setObjectName("table")
        self.tree.setColumnCount(5)
        self.tree.setRootIsDecorated(False)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tree.setVerticalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)
        self.tree.setHeaderLabels(["", "", "", "", ""])
        for column, key in ((1, "projects.col_name"), (2, "projects.col_version"), (3, "projects.col_modified")):
            call(self.tree.headerItem().setText, column, tr(key))
        header = self.tree.header()
        header.setSectionsClickable(True)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 48), (2, 190), (3, 150), (4, 60)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.tree.setColumnWidth(column, width)
        self.sort_indicator()
        header.sectionClicked.connect(self.header_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.context)
        self.tree.itemDoubleClicked.connect(lambda *_: self.open())
        self.layout_box.addWidget(self.tree, 1)

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
        self.refresh()

    # ---- data ------------------------------------------------------------------------------

    def refresh(self):
        if self.scanning:
            self.again = True
            return
        self.scanning = True
        self.render()
        data = self.config.snapshot()
        self.background(lambda: library.collect(data), self.scanned_result)

    def scanned_result(self, result):
        self.scanning = False
        self.scanned = time.monotonic()
        if isinstance(result, Exception):
            self.jobs.message.emit(str(result))
        else:
            self.items = result
        if self.again:
            self.again = False
            self.refresh()
            return
        self.render()
        self.window.packages.refresh()
        self.window.installs.refresh()
        self.window.update_banners()
        self.window.update_tray_projects()

    def stale(self):
        return time.monotonic() - self.scanned > 20

    def opened(self, project):
        return self.config.get("opened").get(str(project.path), 0)

    def favorites(self):
        return set(self.config.get("favorites"))

    def visible(self):
        query = self.search.text().strip().casefold()
        found = [p for p in self.items
                 if (not query or query in p.name.casefold() or query in str(p.path).casefold()
                     or query in p.version.casefold())
                 and (not self.only_versions or p.version in self.only_versions)]
        if self.sort_key == "name":
            found.sort(key=lambda p: p.name.casefold(), reverse=self.sort_down)
        elif self.sort_key == "version":
            found.sort(key=lambda p: (version_key(p.version), p.name.casefold()), reverse=self.sort_down)
        else:
            found.sort(key=lambda p: max(self.opened(p), p.modified), reverse=self.sort_down)
        if self.sort_key == "favorite":
            stars = self.favorites()
            found.sort(key=lambda p: str(p.path) in stars, reverse=self.sort_down)
        return found

    def header_clicked(self, column):
        key = {0: "favorite", 1: "name", 2: "version", 3: "recent"}.get(column)
        if key:
            self.sort_down = not self.sort_down if key == self.sort_key else (key in ("recent", "favorite"))
            self.sort_key = key
            self.config.set("sort_key", key)
            self.config.set("sort_down", self.sort_down)
            self.sort_indicator()

    def sort_indicator(self):
        header = self.tree.header()
        column = {"favorite": 0, "name": 1, "version": 2, "recent": 3}.get(self.sort_key, 3)
        header.setSortIndicator(column, Qt.SortOrder.DescendingOrder if self.sort_down else Qt.SortOrder.AscendingOrder)
        header.setSortIndicatorShown(True)

    def filter_menu(self):
        menu = QMenu(self)
        for version in sorted({p.version for p in self.items if p.version}, key=version_key, reverse=True):
            action = menu.addAction(version)
            action.setCheckable(True)
            action.setChecked(version in self.only_versions)
            action.toggled.connect(lambda on, v=version: self.toggle_version(v, on))
        if not menu.actions():
            return
        menu.exec(self.version_filter.mapToGlobal(self.version_filter.rect().bottomLeft()))

    def toggle_version(self, version, on):
        (self.only_versions.add if on else self.only_versions.discard)(version)
        self.render()

    # ---- drawing ---------------------------------------------------------------------------

    def render(self, *_):
        current = self.selected(False)
        editors = library.editors(self.config.snapshot())
        shown = self.visible()
        self.tree.clear()
        stars = self.favorites()
        for project in shown:
            item = QTreeWidgetItem(self.tree)
            item.setData(0, Qt.ItemDataRole.UserRole, str(project.path))
            item.setSizeHint(0, QSize(10, 58))
            self.fill_row(item, project, editors, str(project.path) in stars)
            if current == project.path:
                self.tree.setCurrentItem(item)
        dirs = library.scan_dirs(self.config.snapshot())
        if self.scanning:
            call(self.summary.setText, tr("projects.scanning"))
        else:
            call(self.summary.setText, tr("projects.summary", len(shown), ", ".join(short(d) for d in dirs) or "—"))
        has = bool(shown)
        self.tree.setVisible(has)
        self.empty.setVisible(not has and not self.scanning)
        if not has:
            filtered = bool(self.search.text().strip() or self.only_versions) and bool(self.items)
            call(self.empty_title.setText, tr("projects.nothing" if filtered else "projects.empty_title"))
            call(self.empty_hint.setText, tr("projects.empty_hint") if not filtered else "")
            for index in range(self.empty_buttons.count()):
                self.empty_buttons.itemAt(index).widget().setVisible(not filtered)

    def fill_row(self, item, project, editors, starred):
        star = QPushButton("★" if starred else "☆")
        star.setObjectName("star")
        star.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        star.clicked.connect(lambda _=False, p=project: self.toggle_star(p))
        self.tree.setItemWidget(item, 0, star)

        installed = project.version in editors
        body = Clickable(lambda p=project: self.open(p))
        body.setObjectName("rowbody")
        column = QVBoxLayout(body)
        column.setContentsMargins(4, 6, 4, 6)
        column.setSpacing(1)
        name = QLabel(project.name if installed or not project.version else "⚠  " + project.name)
        name.setObjectName("cellname")
        path = QLabel(short(project.path))
        path.setObjectName("hint")
        for label in (name, path):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        body.setToolTip(str(project.path))
        column.addWidget(name)
        column.addWidget(path)
        self.tree.setItemWidget(item, 1, body)

        version = QPushButton(("⚠ " if not installed and project.version else "") + (project.version or "—") + "   ⇅")
        version.setObjectName("cell")
        version.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        version.clicked.connect(lambda _=False, p=project, b=version: self.version_menu(p, editors).exec(
            b.mapToGlobal(b.rect().bottomLeft())))
        cell = QWidget()
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.addWidget(version)
        cell_layout.addStretch()
        self.tree.setItemWidget(item, 2, cell)

        stamp = QLabel(when(max(self.opened(project), project.modified)))
        stamp.setObjectName("hint")
        self.tree.setItemWidget(item, 3, stamp)

        more = QPushButton("⋯")
        more.setObjectName("flat")
        more.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        more.clicked.connect(lambda _=False, p=project, b=more: self.menu(p).exec(b.mapToGlobal(b.rect().bottomLeft())))
        self.tree.setItemWidget(item, 4, more)

    def toggle_star(self, project):
        stars = self.favorites() ^ {str(project.path)}
        self.save("favorites", sorted(stars))
        self.render()

    def version_menu(self, project, editors):
        """Pick the editor version this project is opened with."""
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
        item = self.tree.currentItem()
        if not item:
            return None
        path = Path(item.data(0, Qt.ItemDataRole.UserRole))
        return next((p for p in self.items if p.path == path), None)

    def selected(self, warn=True):
        item = self.tree.currentItem()
        if item:
            return Path(item.data(0, Qt.ItemDataRole.UserRole))
        if warn:
            self.warning(tr("project.select"))
        return None

    def context(self, position):
        item = self.tree.itemAt(position)
        if item:
            self.tree.setCurrentItem(item)
            project = self.current_project()
            if project:
                self.menu(project).exec(self.tree.viewport().mapToGlobal(position))

    def menu(self, project):
        menu = QMenu(self)
        call(menu.addAction, tr("projects.open")).triggered.connect(lambda: self.open(project))
        call(menu.addAction, tr("projects.show_folder")).triggered.connect(lambda: open_folder(project.path))
        call(menu.addAction, tr("projects.copy_path")).triggered.connect(
            lambda: QGuiApplication.clipboard().setText(str(project.path)))
        self.git_tools.add_menu(menu, project)
        call(menu.addAction, tr("args.project")).triggered.connect(lambda: self.edit_project_args(project))
        menu.addSeparator()
        call(menu.addAction, tr("projects.hide")).triggered.connect(lambda: self.hide_project(project))
        return menu

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
        path = Path(path).resolve()
        if library.project_version(path):
            self.config.update("hidden", lambda items: [p for p in items if p != str(path)])
            self.config.update("projects", lambda items: sorted({*items, str(path)}))
            self.window.notify(tr("projects.added_project", path.name), "ok")
        else:
            self.add_scan_dir(str(path))
            self.window.notify(tr("projects.added_folder", path.name), "ok")
        self.search.clear()
        self.refresh()

    def add_scan_dir(self, path, refresh=True):
        dirs = library.scan_dirs(self.config.snapshot())
        if str(path) not in dirs:
            self.save("scan_dirs", [*dirs, str(path)])
        hidden = self.config.get("hidden")
        self.save("hidden", [p for p in hidden if not p.startswith(str(path).rstrip("/") + "/")])
        if refresh:
            self.refresh()

    def manage_folders(self):
        FoldersDialog(self).exec()
        self.refresh()

    def remember_created(self, path):
        self.save("projects", sorted(set(self.config.get("projects")) | {str(path)}))
        self.touch(path)

    def touch(self, path):
        opened = dict(self.config.get("opened"))
        opened[str(path)] = time.time()
        self.save("opened", opened)

    def hide_project(self, project):
        self.save("hidden", sorted({*self.config.get("hidden"), str(project.path)}))
        self.items = [p for p in self.items if p.path != project.path]
        self.window.update_tray_projects()
        self.render()

    # ---- running the editor ------------------------------------------------------------------

    def need_editor(self, version):
        self.window.installs.version.setEditText(version)
        self.window.go("editors")
        self.window.installs.show_install(True)
        self.window.notify(tr("editor.missing", version), "fail")

    def open(self, project=None):
        project = project or self.current_project()
        if not project:
            self.warning(tr("project.select"))
            return
        if not project.version:
            self.warning(tr("project.invalid", project.path))
            return
        editor = library.editors(self.config.snapshot()).get(project.version)
        if not editor:
            self.need_editor(project.version)
            return
        self.start(editor, project)

    def start(self, editor, project):
        try:
            process = library.launch(editor, project.path, self.config.snapshot())
        except (ValueError, OSError) as error:
            self.warning(error)
            return
        self.jobs.message.emit(shlex.join(process.args))
        self.touch(project.path)
        self.window.notify(tr("projects.launching", project.name), "busy", 8000)
        QTimer.singleShot(1200, self.render)
        self.window.editor_started(project.path)

    def upgrade(self, project, version):
        editor = library.editors(self.config.snapshot()).get(version)
        if editor and self.confirm("project.confirm_upgrade", project.name, version):
            self.start(editor, project)


class Packages(Page):
    def __init__(self, window):
        super().__init__(window)
        self.title("nav.packages")
        self.target = QComboBox()
        self.layout_box.addWidget(self.target)
        _, inner = self.card()
        self.label(inner, "package.help")
        self.identifier = QLineEdit()
        self.identifier.setPlaceholderText("com.unity.cinemachine@3.1.0")
        inner.addWidget(self.identifier)
        bar = QHBoxLayout()
        inner.addLayout(bar)
        self.button(bar, "package.install", self.install, "primary")
        self.button(bar, "package.list", lambda: self.command("package.list", ["command", "package", "list"]))
        self.button(bar, "package.pipeline", lambda: self.command("package.pipeline", ["pipeline", "install"]))
        self.button(bar, "package.import", self.import_asset)
        bar.addStretch()
        self.layout_box.addStretch()

    def refresh(self):
        chosen = self.window.projects.selected(False)
        old = self.target.currentData()
        self.target.clear()
        for project in self.window.projects.items:
            if project.version:
                self.target.addItem(f"{project.name}  ·  {project.path}", str(project.path))
        index = self.target.findData(str(chosen) if chosen else old)
        if index >= 0:
            self.target.setCurrentIndex(index)

    def command(self, key, args):
        path = self.target.currentData()
        if not path:
            self.warning(tr("project.select"))
            return
        self.jobs.run(path, tr(key), [*args, "--project-path", path])

    def install(self):
        name = self.identifier.text().strip()
        if name and not name.startswith("-"):
            self.command("package.install", ["command", "package", "add", "--name", name, "--confirm",
                                            "true", "--wait", "true", "--timeout", "300"])
        else:
            self.identifier.setFocus()

    def import_asset(self):
        path = QFileDialog.getOpenFileName(self, str(tr("package.import")), "", "Unity (*.unitypackage)")[0]
        if path:
            self.command("package.import", ["assets", "import", path])
