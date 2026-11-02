from __future__ import annotations

import uuid
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                             QStackedWidget, QVBoxLayout, QWidget)

from equestria_ue.config import Config
from equestria_ue.engines import inspect_engine, read_install_ini, sync_install_ini
from equestria_ue.jobs import Job, JobManager, Worker
from equestria_ue.projects import scan_projects
from equestria_ue.store import EpicStore
from equestria_ue.kit import LANGUAGES, kit_qt, set_language, tr
from equestria_ue.ui.catalog import CatalogPage
from equestria_ue.ui.downloads import DownloadsPage
from equestria_ue.ui.engines_page import EnginesPage
from equestria_ue.ui.library import ProjectsPage
from equestria_ue.launcher import launch_editor
from equestria_ue.ui.settings import SettingsPage
from equestria_ue.ui.store_page import StorePage
from equestria_ue.ui.tray import LauncherTray, app_icon
from equestria_ue.ui.vram_check import confirm_launch
from equestria_ue.versions import PREBUILT_SIZE, fetch_tags


class MainWindow(QMainWindow):
    # подписи переводятся при показе (tr в _retranslate) — язык меняется на лету
    NAV = [("library", "Библиотека"), ("new", "Новый проект (окно Unreal)"), ("engines", "Движки"), ("catalog", "Каталог"),
           ("store", "Магазин Epic"), ("downloads", "Загрузки"), ("settings", "Настройки")]
    PAGES = (("library", ProjectsPage), ("engines", EnginesPage), ("catalog", CatalogPage),
             ("store", StorePage), ("downloads", DownloadsPage), ("settings", SettingsPage))

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Equestria · Unreal Launcher")
        self.resize(1120, 720)
        self.cfg = Config()
        set_language(self.cfg["lang"])
        self.engines: list = []
        self.projects: list = []
        self.versions = None
        self.versions_err = ""
        self.access_ok = None
        self.checking = False
        self._workers: list = []
        self.jobs = JobManager()
        self.pages = {}
        self.store = EpicStore(self)
        self.tray: LauncherTray | None = None
        self._quitting = False
        self.setWindowIcon(app_icon())

        root = QWidget()
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(12, 18, 12, 14)
        sv.setSpacing(4)
        logo = QLabel("UNREAL\nLauncher")
        logo.setObjectName("title")
        sv.addWidget(logo)
        sv.addSpacing(14)
        self.nav = {}
        for key, _text in self.NAV:
            b = QPushButton()
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            sv.addWidget(b)
            self.nav[key] = b
        sv.addStretch()
        self.mini = QLabel("")
        self.mini.setObjectName("hint")
        self.mini.setWordWrap(True)
        sv.addWidget(self.mini)
        self.lang = QComboBox()
        self.lang.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lang.addItem("", "")
        for code, name in LANGUAGES:
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(self.cfg["lang"])))
        self.lang.activated.connect(lambda i: self.set_lang(self.lang.itemData(i)))
        sv.addWidget(self.lang)
        h.addWidget(side)

        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        self._build_pages()
        self._retranslate()
        kit_qt.on_theme_change(lambda _: self.pages["library"].fill())   # заглушки проектов рисуются в цветах темы

        self.jobs.changed.connect(self._mini)
        self.store.changed.connect(self._mini)
        self.set_tray(self.cfg["tray"])
        self.reload_engines()
        self.go("library")
        # фоновое сканирование проектов и запрос версий
        QTimer.singleShot(50, self.reload_projects)
        QTimer.singleShot(400, lambda: self.fetch_versions(False))

    def _build_pages(self) -> None:
        for key, cls in self.PAGES:
            p = cls(self)
            self.pages[key] = p
            self.stack.addWidget(p)

    def _retranslate(self) -> None:
        for key, text in self.NAV:
            self.nav[key].setText(tr(text))
        self.lang.setItemText(0, tr("Как в системе"))
        self._mini()

    def set_lang(self, code: str) -> None:
        """Сменить язык интерфейса без перезапуска: страницы пересоздаются заново."""
        self.cfg["lang"] = code
        self.cfg.save()
        set_language(code)
        current = next((k for k, p in self.pages.items() if p is self.stack.currentWidget()), "library")
        log = self.pages["downloads"].log.toPlainText()
        if self.store.view is not None:
            self.store.view.setParent(None)          # веб-страница Epic живёт дольше страницы «Магазин»
        for p in self.pages.values():
            self.stack.removeWidget(p)
            p.deleteLater()
        self.pages = {}
        self._build_pages()
        self.pages["downloads"].log.setPlainText(log)
        self.pages["library"].fill()
        self._retranslate()
        self.go(current)

    # --- навигация
    def go(self, key: str) -> None:
        if key == "new":                    # у Unreal уже есть свой экран создания проектов — просто открываем его
            self._open_unreal_browser()
            return
        for k, b in self.nav.items():
            b.setChecked(k == key)
        self.stack.setCurrentWidget(self.pages[key])

    def _open_unreal_browser(self) -> None:
        built = sorted((e for e in self.engines if e.built), key=lambda e: e.version, reverse=True)
        if not built:
            QMessageBox.information(self, tr("Нет движка"), tr("Сначала установите или подключите Unreal Engine («Каталог»)."))
            return
        if not confirm_launch(self):
            return
        err = launch_editor(self.cfg, built[0])
        if err:
            QMessageBox.warning(self, tr("Не удалось запустить"), err)

    def _mini(self) -> None:
        j, d = self.jobs, self.store.dl
        if d:
            pc = int(d["recv"] * 100 / (d["total"] or PREBUILT_SIZE))
            self.mini.setText(f"⬇ {d['name']}\n{min(pc, 100)}%")
        else:
            self.mini.setText(f"⏳ {j.current.title}\n{int(j.progress)}%" if j.current else "")
        if self.tray:
            self.tray.update_tooltip(self.mini.text())

    # --- данные
    def register_engine(self, path: str) -> None:
        path = str(Path(path).resolve())
        if not any(Path(e["path"]).resolve() == Path(path) for e in self.cfg["engines"]):
            self.cfg["engines"].append({"id": "{" + str(uuid.uuid4()).upper() + "}", "path": path})
            self.cfg.save()
        self.reload_engines()

    def reload_engines(self) -> None:
        ours = [e for e in (inspect_engine(x) for x in self.cfg["engines"]) if e]
        # движки из Epic Install.ini тоже показываем
        known = {e.path for e in ours}
        for gid, p in read_install_ini().items():
            if p not in known:
                eng = inspect_engine({"id": gid, "path": p})
                if eng:
                    ours.append(eng)
                    known.add(p)
        self.engines = ours
        if self.cfg["sync_ini"]:
            try:
                sync_install_ini(self.engines)
            except Exception:
                pass
        for k in ("library", "engines", "catalog"):
            p = self.pages.get(k)
            if p is None:
                continue
            p.rebuild()

    def reload_projects(self) -> None:
        d, x = list(self.cfg["project_dirs"]), list(self.cfg["extra_projects"])
        w = Worker(lambda: scan_projects(d, x))
        self._workers.append(w)

        def done(r):
            if isinstance(r, list):
                self.projects = r
                self.pages["library"].fill()
            self._workers.remove(w)

        w.done.connect(done)
        w.start()

    def fetch_versions(self, manual: bool) -> None:
        if self.checking:
            return
        self.checking = True
        self.pages["catalog"].rebuild()
        access = self.cfg["access"]
        w = Worker(lambda: fetch_tags(access))
        self._workers.append(w)

        def done(r):
            self.checking = False
            if isinstance(r, Exception):
                r = (None, str(r))
            vs, err = r
            if vs:
                self.versions, self.access_ok, self.versions_err = vs, True, ""
            elif manual or self.access_ok is not None:
                self.access_ok, self.versions_err = False, err
            self._workers.remove(w)
            self.pages["catalog"].rebuild()
            self.pages["engines"].rebuild()

        w.done.connect(done)
        w.start()

    def add_job(self, job: Job, goto_downloads: bool = False) -> None:
        orig = job.on_done

        def wrapped():
            if orig:
                orig()
            self.reload_engines()
            self.reload_projects()

        job.on_done = wrapped
        self.jobs.add(job)
        if goto_downloads:
            self.go("downloads")

    # --- трей и выход
    def set_tray(self, on: bool) -> None:
        """Включить/выключить значок в трее (настройка «Сворачивать в трей»)."""
        if on and self.tray is None and LauncherTray.available():
            self.tray = LauncherTray(self)
            self._mini()
        elif not on and self.tray is not None:
            self.tray.remove()
            self.tray = None

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        """Настоящий выход (меню трея или закрытие окна без трея).
        Редактор Unreal при этом не закрывается — он запущен отдельно."""
        if self.jobs.current or self.store.dl:
            self.show_window()
            r = QMessageBox.question(self, tr("Идёт задача"),
                                     tr("Установка или сборка ещё выполняется. Закрыть лаунчер и остановить её?"))
            if r != QMessageBox.StandardButton.Yes:
                return
            self.jobs.cancel()
            self.store.cancel()
        self._quitting = True
        self.close()
        QApplication.quit()

    def closeEvent(self, e) -> None:
        if self._quitting:
            e.accept()
        elif self.tray is not None:
            e.ignore()           # окно прячется, лаунчер работает дальше в трее
            self.hide()
            self.tray.hidden_hint()
        else:
            e.ignore()
            self.quit_app()
