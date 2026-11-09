from __future__ import annotations

from equestria_kit import live_i18n

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget

from equestria_ue.engines import Engine
from equestria_ue.jobs import Job
from equestria_ue.kit import tr
from equestria_ue.launcher import RunningEditors, already_open_message, launch_editor
from equestria_ue.projects import Project, resolve_engine, set_association
from equestria_ue.steps import project_steps
from equestria_ue.ui.widgets import card_frame, make_icon, open_folder, show_launching, small_btn, title_row
from equestria_ue.ui.vram_check import confirm_launch


class ProjectsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.by_path: dict = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(14)
        self.search = QLineEdit()
        live_i18n.call(self.search.setPlaceholderText, tr("library.search_projects"))
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self.fill)
        b_open = small_btn(tr("library.open_uproject"))
        b_open.clicked.connect(self.open_file)
        b_dir = small_btn(tr("library.projects_folder"))
        b_dir.clicked.connect(self.add_dir)
        b_ref = small_btn(tr("library.refresh"))
        b_ref.clicked.connect(win.reload_projects)
        v.addLayout(title_row(tr("common.library"), self.search, b_open, b_dir, b_ref))
        self.grid = QListWidget()
        self.grid.setObjectName("grid")
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setIconSize(QSize(256, 144))
        self.grid.setGridSize(QSize(284, 226))
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setSpacing(8)
        self.grid.setWordWrap(True)
        self.grid.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._ctx)
        self.grid.itemSelectionChanged.connect(self._sel)
        self.grid.itemDoubleClicked.connect(lambda _: self.launch())
        self.empty = live_i18n.call(QLabel, )
        self.empty.setObjectName("hint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.grid, 1)
        v.addWidget(self.empty, 1)

        bar = card_frame("hero")
        h = QHBoxLayout(bar)
        h.setContentsMargins(18, 14, 18, 14)
        h.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.name = live_i18n.call(QLabel, tr("library.select_project"))
        self.name.setObjectName("rowname")
        self.info = live_i18n.call(QLabel, "")
        self.info.setObjectName("hint")
        col.addWidget(self.name)
        col.addWidget(self.info)
        self.combo = QComboBox()
        self.combo.setMinimumWidth(210)
        self.go = live_i18n.call(QPushButton, tr("library.launch"))
        self.go.setObjectName("primary")
        self.go.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.go.clicked.connect(lambda: self.launch())
        self.more = small_btn("⋯")
        self.more.clicked.connect(self._more)
        h.addLayout(col, 1)
        h.addWidget(self.combo)
        h.addWidget(self.go)
        h.addWidget(self.more)
        v.addWidget(bar)
        self.fill()

    def rebuild(self) -> None:
        self.fill()

    # --- наполнение
    def fill(self, *_) -> None:
        q = self.search.text().strip().lower()
        keep = self.current().path if self.current() else ""
        self.grid.blockSignals(True)
        self.grid.clear()
        self.by_path = {}
        for pr in self.win.projects:
            if q and q not in pr.name.lower():
                continue
            eng = resolve_engine(pr, self.win.engines)
            lab = f"UE {eng.ver}" if eng else (tr("library.ue_not_installed", pr.assoc) if pr.assoc else tr("library.version_not_specified"))
            it = live_i18n.call(QListWidgetItem, make_icon(pr), live_i18n.format_text('{0}\n{1}{2}', pr.name, lab, '  ·  C++' if pr.cpp else ''))
            it.setData(Qt.ItemDataRole.UserRole, pr.path)
            live_i18n.call(self.grid.addItem, it)
            self.by_path[pr.path] = pr
            if pr.path == keep:
                self.grid.setCurrentItem(it)
        self.grid.blockSignals(False)
        has = self.grid.count() > 0
        self.grid.setVisible(has)
        self.empty.setVisible(not has)
        live_i18n.call(self.empty.setText, tr("library.no_projects_found_add_projects")
                           if not q else tr("library.nothing_found"))
        self._sel()

    def current(self):
        it = self.grid.currentItem()
        return self.by_path.get(it.data(Qt.ItemDataRole.UserRole)) if it else None

    def _sel(self) -> None:
        pr = self.current()
        self.combo.clear()
        for w in (self.combo, self.go, self.more):
            w.setEnabled(pr is not None)
        if not pr:
            live_i18n.call(self.name.setText, tr("library.select_project"))
            live_i18n.call(self.info.setText, "")
            return
        live_i18n.call(self.name.setText, pr.name)
        live_i18n.call(self.info.setText, pr.path)
        res = resolve_engine(pr, self.win.engines)
        for e in sorted(self.win.engines, key=lambda e: e.version, reverse=True):
            live_i18n.call(self.combo.addItem, e.title + ("" if e.built else tr("library.not_built")), e.id)
        if res:
            self.combo.setCurrentIndex(self.combo.findData(res.id))
        if not self.win.engines:
            live_i18n.call(self.combo.addItem, tr("library.no_engines_installed"))
            self.go.setEnabled(False)

    # --- действия
    def engine_choice(self):
        return next((e for e in self.win.engines if e.id == self.combo.currentData()), None)

    def launch(self, eng=None) -> None:
        pr = self.current()
        eng = eng or self.engine_choice()
        if not pr:
            return
        if not eng:
            QMessageBox.information(self, tr("common.no_engine"), tr("common.install_unreal_engine_catalog_tab"))
            self.win.go("catalog")
            return
        if RunningEditors.is_open(pr.path):
            QMessageBox.information(self, tr("common.project_already_open"), already_open_message(pr.path))
            return
        if not confirm_launch(self):
            return
        err = launch_editor(self.win.cfg, eng, pr.path)
        if err:
            QMessageBox.warning(self, tr("common.could_not_launch"), err)
        else:
            show_launching(self.go)

    def _more(self) -> None:
        pr = self.current()
        if pr:
            self._menu(pr).exec(self.more.mapToGlobal(self.more.rect().bottomLeft()))

    def _ctx(self, pos) -> None:
        if self.grid.itemAt(pos):
            pr = self.current()
            if pr:
                self._menu(pr).exec(self.grid.viewport().mapToGlobal(pos))

    def _menu(self, pr: Project) -> QMenu:
        m = QMenu(self)
        live_i18n.call(m.addAction, tr("library.launch")).triggered.connect(lambda: self.launch())
        sub = live_i18n.call(m.addMenu, tr("library.open_version"))
        for e in sorted(self.win.engines, key=lambda e: e.version, reverse=True):
            live_i18n.call(sub.addAction, e.title).triggered.connect(lambda _=False, x=e: self.launch(x))
        sub2 = live_i18n.call(m.addMenu, tr("library.change_project_version"))
        for e in sorted(self.win.engines, key=lambda e: e.version, reverse=True):
            live_i18n.call(sub2.addAction, e.title).triggered.connect(lambda _=False, x=e: self.set_version(pr, x))
        eng = self.engine_choice()
        if pr.cpp and eng:
            m.addSeparator()
            live_i18n.call(m.addAction, tr("library.generate_project_files")).triggered.connect(
                lambda: self.win.add_job(Job(tr("library.project_files", pr.name), project_steps("gen", eng, pr.path)), True))
            live_i18n.call(m.addAction, tr("library.build_project_editor_development")).triggered.connect(
                lambda: self.win.add_job(Job(tr("common.building", pr.name), project_steps("build", eng, pr.path)), True))
        m.addSeparator()
        live_i18n.call(m.addAction, tr("common.show_folder")).triggered.connect(lambda: open_folder(str(Path(pr.path).parent)))
        live_i18n.call(m.addAction, tr("library.copy_path")).triggered.connect(lambda: live_i18n.call(QGuiApplication.clipboard().setText, pr.path))
        return m

    def set_version(self, pr: Project, eng: Engine) -> None:
        if QMessageBox.question(self, tr("library.change_version"),
                                tr("library.project_will_bound_uproject_file",
                                   pr.name, eng.title)) != QMessageBox.StandardButton.Yes:
            return
        if not set_association(pr, eng.id):
            QMessageBox.warning(self, tr("library.error"), tr("library.could_not_write_uproject_file"))
        self.fill()

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("library.open_project"), str(Path.home()), "Unreal Project (*.uproject)")
        if path:
            if path not in self.win.cfg["extra_projects"]:
                self.win.cfg["extra_projects"].append(path)
                self.win.cfg.save()
            self.win.reload_projects()

    def add_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("common.projects_folder"), str(Path.home()))
        if d and d not in self.win.cfg["project_dirs"]:
            self.win.cfg["project_dirs"].append(d)
            self.win.cfg.save()
            self.win.reload_projects()
