from __future__ import annotations

from equestria_kit import live_i18n

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap
from PyQt6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget

from equestria_ue.jobs import Job
from equestria_ue.launcher import launch_editor
from equestria_ue.steps import project_steps
from equestria_ue.templates import Template, create_project, read_templates
from equestria_ue.kit import kit_qt, tr
from equestria_ue.ui.widgets import card_frame, small_btn, title_row


class NewProjectPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.tpls: list = []
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(12)
        v.addLayout(title_row(tr("new_project.new_project")))
        top = QHBoxLayout()
        top.setSpacing(8)
        self.combo = QComboBox()
        self.combo.activated.connect(lambda *_: self.load())
        bare = small_btn(tr("new_project.open_editor_without_project"), tr("new_project.has_own_unreal_template_picker"))
        bare.clicked.connect(self.bare)
        top.addWidget(live_i18n.call(QLabel, tr("new_project.engine")))
        top.addWidget(self.combo, 1)
        top.addWidget(bare)
        v.addLayout(top)
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
        self.grid.itemSelectionChanged.connect(self._sel)
        v.addWidget(self.grid, 1)
        self.empty = live_i18n.call(QLabel, "")
        self.empty.setObjectName("hint")
        self.empty.setWordWrap(True)
        v.addWidget(self.empty)
        bar = card_frame()
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(8)
        self.name = QLineEdit("MyProject")
        self.name.setFixedWidth(200)
        self.loc = QLineEdit((win.cfg["project_dirs"] or [str(Path.home() / "UnrealProjects")])[0])
        br = small_btn(tr("common.browse"))
        br.clicked.connect(self._browse)
        self.make = live_i18n.call(QPushButton, tr("new_project.create"))
        self.make.setObjectName("primary")
        self.make.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.make.clicked.connect(self.create)
        for w in (live_i18n.call(QLabel, tr("new_project.name")), self.name, live_i18n.call(QLabel, tr("new_project.folder"))):
            h.addWidget(w)
        h.addWidget(self.loc, 1)
        h.addWidget(br)
        h.addWidget(self.make)
        v.addWidget(bar)
        self.rebuild()

    def engine(self):
        return next((e for e in self.win.engines if e.id == self.combo.currentData()), None)

    def rebuild(self) -> None:
        keep = self.combo.currentData()
        self.combo.clear()
        for e in sorted(self.win.engines, key=lambda e: e.version, reverse=True):
            live_i18n.call(self.combo.addItem, e.title, e.id)
        if keep and self.combo.findData(keep) >= 0:
            self.combo.setCurrentIndex(self.combo.findData(keep))
        self.load()

    def load(self) -> None:
        self.grid.clear()
        eng = self.engine()
        self.tpls = read_templates(eng) if eng else []
        for i, t in enumerate(self.tpls):
            it = live_i18n.call(QListWidgetItem, self._icon(t), t.name + ("\nC++" if t.cpp else "\nBlueprint") + ("" if t.builtin else tr("new_project.via_editor")))
            it.setData(Qt.ItemDataRole.UserRole, i)
            live_i18n.call(self.grid.addItem, it)
        if self.tpls:
            self.grid.setCurrentRow(0)
        live_i18n.call(self.empty.setText, "" if self.tpls else
                           (tr("new_project.install_engine_first") if not eng else ""))
        self._sel()

    def _icon(self, t: Template) -> QIcon:
        W, H = 256, 144
        if t.builtin:
            cols = {"blank_bp": ("#313244", "#585b70", "▢"), "blank_cpp": ("#1e3a5f", "#3b82c4", "{ }"),
                    "light": ("#1f4d36", "#5fbf8a", "☀"), "rt": ("#4a1f5e", "#c77dff", "✦")}[t.key]
            pm = QPixmap(W, H)
            pa = QPainter(pm)
            g = QLinearGradient(0, 0, W, H)
            g.setColorAt(0, QColor(cols[0]))
            g.setColorAt(1, QColor(cols[1]))
            pa.fillRect(pm.rect(), g)
            pa.setPen(QColor("#ffffffd0"))
            f = QFont()
            f.setPointSize(40)
            pa.setFont(f)
            live_i18n.call(pa.drawText, pm.rect(), Qt.AlignmentFlag.AlignCenter, cols[2])
            pa.end()
            return QIcon(pm)
        pm = QPixmap(t.image) if t.image else QPixmap()
        if pm.isNull():
            pm = QPixmap(W, H)
            pm.fill(kit_qt.theme_color("surface1"))
            pa = QPainter(pm)
            pa.setPen(kit_qt.theme_color("subtext"))
            live_i18n.call(pa.drawText, pm.rect(), Qt.AlignmentFlag.AlignCenter, t.name)
            pa.end()
            return QIcon(pm)
        pm = pm.scaled(W, H, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        return QIcon(pm.copy((pm.width() - W) // 2, (pm.height() - H) // 2, W, H))

    def _sel(self) -> None:
        self.make.setEnabled(self.grid.currentItem() is not None)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("new_project.where_create_project"), self.loc.text())
        if d:
            live_i18n.call(self.loc.setText, d)

    def bare(self) -> None:
        eng = self.engine()
        err = launch_editor(self.win.cfg, eng) if eng else tr("new_project.no_engine_selected")
        if err:
            QMessageBox.warning(self, tr("common.could_not_launch"), err)

    def create(self) -> None:
        win, eng = self.win, self.engine()
        it = self.grid.currentItem()
        if not eng or not it:
            return
        tp = self.tpls[it.data(Qt.ItemDataRole.UserRole)]
        if not tp.builtin:
            # Шаблоны Epic берут меши, ввод и варианты из общих пакетов (SharedContentPacks / Variants) —
            # правильно собрать такой проект умеет только сам редактор.
            QMessageBox.information(self, tr("new_project.unreal_editor_will_create"),
                                    tr("new_project.template_uses_shared_content_packs", tp.name))
            err = launch_editor(win.cfg, eng)
            if err:
                QMessageBox.warning(self, tr("common.could_not_launch"), err)
            return
        try:
            up = create_project(tp, self.loc.text().strip(), self.name.text().strip(), eng)
        except Exception as ex:
            QMessageBox.warning(self, tr("new_project.could_not_create_project"), str(ex))
            return
        dirs = [Path(d).resolve() for d in win.cfg["project_dirs"]]
        if not any(d in Path(up).resolve().parents for d in dirs) and up not in win.cfg["extra_projects"]:
            win.cfg["extra_projects"].append(up)
            win.cfg.save()
        win.reload_projects()
        win.go("library")
        if tp.cpp:
            win.add_job(Job(tr("new_project.generating_project"), project_steps("gen", eng, up) + project_steps("build", eng, up)), True)
        elif QMessageBox.question(self, tr("new_project.project_created"), tr("new_project.open_project_editor")) == QMessageBox.StandardButton.Yes:
            err = launch_editor(win.cfg, eng, up)
            if err:
                QMessageBox.warning(self, tr("common.could_not_launch"), err)
