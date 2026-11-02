from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget

from equestria_ue.engines import Engine
from equestria_ue.jobs import Job
from equestria_ue.kit import tr
from equestria_ue.launcher import launch_editor
from equestria_ue.projects import Project, resolve_engine, set_association
from equestria_ue.steps import project_steps
from equestria_ue.ui.widgets import card_frame, make_icon, open_folder, small_btn, title_row
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
        self.search.setPlaceholderText(tr("Поиск проекта…"))
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self.fill)
        b_open = small_btn(tr("Открыть .uproject…"))
        b_open.clicked.connect(self.open_file)
        b_dir = small_btn(tr("＋ Папка проектов"))
        b_dir.clicked.connect(self.add_dir)
        b_ref = small_btn(tr("Обновить"))
        b_ref.clicked.connect(win.reload_projects)
        v.addLayout(title_row(tr("Библиотека"), self.search, b_open, b_dir, b_ref))
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
        self.empty = QLabel()
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
        self.name = QLabel(tr("Выберите проект"))
        self.name.setObjectName("rowname")
        self.info = QLabel("")
        self.info.setObjectName("hint")
        col.addWidget(self.name)
        col.addWidget(self.info)
        self.combo = QComboBox()
        self.combo.setMinimumWidth(210)
        self.go = QPushButton(tr("Запустить"))
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
            lab = f"UE {eng.ver}" if eng else (tr("UE {} — не установлен", pr.assoc) if pr.assoc else tr("версия не указана"))
            it = QListWidgetItem(make_icon(pr), f"{pr.name}\n{lab}{'  ·  C++' if pr.cpp else ''}")
            it.setData(Qt.ItemDataRole.UserRole, pr.path)
            self.grid.addItem(it)
            self.by_path[pr.path] = pr
            if pr.path == keep:
                self.grid.setCurrentItem(it)
        self.grid.blockSignals(False)
        has = self.grid.count() > 0
        self.grid.setVisible(has)
        self.empty.setVisible(not has)
        self.empty.setText(tr("Проектов не найдено.\nДобавьте папку с проектами или откройте .uproject вручную.")
                           if not q else tr("Ничего не найдено."))
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
            self.name.setText(tr("Выберите проект"))
            self.info.setText("")
            return
        self.name.setText(pr.name)
        self.info.setText(pr.path)
        res = resolve_engine(pr, self.win.engines)
        for e in sorted(self.win.engines, key=lambda e: e.version, reverse=True):
            self.combo.addItem(e.title + ("" if e.built else tr(" (не собран)")), e.id)
        if res:
            self.combo.setCurrentIndex(self.combo.findData(res.id))
        if not self.win.engines:
            self.combo.addItem(tr("Движки не установлены"))
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
            QMessageBox.information(self, tr("Нет движка"), tr("Сначала установите Unreal Engine на вкладке «Каталог»."))
            self.win.go("catalog")
            return
        if not confirm_launch(self):
            return
        err = launch_editor(self.win.cfg, eng, pr.path)
        if err:
            QMessageBox.warning(self, tr("Не удалось запустить"), err)

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
        m.addAction(tr("Запустить")).triggered.connect(lambda: self.launch())
        sub = m.addMenu(tr("Открыть в версии…"))
        for e in sorted(self.win.engines, key=lambda e: e.version, reverse=True):
            sub.addAction(e.title).triggered.connect(lambda _=False, x=e: self.launch(x))
        sub2 = m.addMenu(tr("Сменить версию проекта на…"))
        for e in sorted(self.win.engines, key=lambda e: e.version, reverse=True):
            sub2.addAction(e.title).triggered.connect(lambda _=False, x=e: self.set_version(pr, x))
        eng = self.engine_choice()
        if pr.cpp and eng:
            m.addSeparator()
            m.addAction(tr("Сгенерировать файлы проекта")).triggered.connect(
                lambda: self.win.add_job(Job(tr("Файлы проекта {}", pr.name), project_steps("gen", eng, pr.path)), True))
            m.addAction(tr("Собрать редактор проекта (Development)")).triggered.connect(
                lambda: self.win.add_job(Job(tr("Сборка {}", pr.name), project_steps("build", eng, pr.path)), True))
        m.addSeparator()
        m.addAction(tr("Показать в папке")).triggered.connect(lambda: open_folder(str(Path(pr.path).parent)))
        m.addAction(tr("Копировать путь")).triggered.connect(lambda: QGuiApplication.clipboard().setText(pr.path))
        return m

    def set_version(self, pr: Project, eng: Engine) -> None:
        if QMessageBox.question(self, tr("Сменить версию"),
                                tr("Проект «{}» будет привязан к {}.\nФайл .uproject изменится "
                                   "(копия сохранится как .uproject.bak). Движок откроет проект и предложит конвертировать "
                                   "его — перед этим сделайте резервную копию, особенно при понижении версии.\n\nПродолжить?",
                                   pr.name, eng.title)) != QMessageBox.StandardButton.Yes:
            return
        if not set_association(pr, eng.id):
            QMessageBox.warning(self, tr("Ошибка"), tr("Не удалось записать .uproject."))
        self.fill()

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Открыть проект"), str(Path.home()), "Unreal Project (*.uproject)")
        if path:
            if path not in self.win.cfg["extra_projects"]:
                self.win.cfg["extra_projects"].append(path)
                self.win.cfg.save()
            self.win.reload_projects()

    def add_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Папка с проектами"), str(Path.home()))
        if d and d not in self.win.cfg["project_dirs"]:
            self.win.cfg["project_dirs"].append(d)
            self.win.cfg.save()
            self.win.reload_projects()
