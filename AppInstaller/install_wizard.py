"""Мастер установки — как мастера установки в Windows: шаг за шагом.

Два пути с первой страницы:
  установить из файла   Выбор → Установка → Готово
                        (.pkg.tar.zst/.pkg.tar.xz — pacman, .deb/.rpm — foreign_bridge.py,
                         .flatpak/.flatpakref — flatpak)
  обновить или удалить  Выбор → Программы DEB/RPM → Загрузка → Установка → Готово
                                                  → Удаление → Готово
"""
from __future__ import annotations

import json
import shutil
import sys

import os

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
                             QLabel, QProgressBar, QPushButton, QRadioButton, QScrollArea, QTextEdit, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget, QWizard, QWizardPage)

from foreign_apps import Download, InstalledPackage, UpdateCheck
from ui_common import BRIDGE, colored, tr

PACMAN_EXT = (".pkg.tar.zst", ".pkg.tar.xz")
FOREIGN_EXT = (".deb", ".rpm")
FLATPAK_EXT = (".flatpak", ".flatpakref")
SUPPORTED_EXT = PACMAN_EXT + FOREIGN_EXT + FLATPAK_EXT

# страницы мастера
PAGE_WELCOME, PAGE_INSTALL, PAGE_APPS, PAGE_DOWNLOAD, PAGE_REMOVE, PAGE_SUMMARY = range(6)


def format_size(n) -> str:
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


class WelcomePage(QWizardPage):
    """Что сделать: установить программу из файла или обновить/удалить уже установленную."""

    def __init__(self):
        super().__init__()
        self.setTitle(tr("Установщик пакетов Equestria OS"))
        self.setSubTitle(tr("Мастер установки локальных пакетов"))
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.rb_file = QRadioButton(tr("Установить программу из файла"))
        self.rb_apps = QRadioButton(tr("Обновить или удалить программу из пакета DEB или RPM"))
        self.rb_file.setChecked(True)
        group = QButtonGroup(self)
        for rb in (self.rb_file, self.rb_apps):
            group.addButton(rb)
            rb.toggled.connect(self._mode_changed)
        layout.addWidget(self.rb_file)
        file_row = QWidget()
        fr = QVBoxLayout(file_row)
        fr.setContentsMargins(28, 0, 0, 0)
        hint = QLabel(tr("Поддерживаются .pkg.tar.zst, .deb, .rpm, .flatpak и .flatpakref."))
        hint.setObjectName("hint")
        fr.addWidget(hint)
        self.btn_browse = QPushButton(tr("Обзор…"))
        self.btn_browse.setObjectName("primary")
        self.btn_browse.clicked.connect(self.browse_file)
        fr.addWidget(self.btn_browse, 0, Qt.AlignmentFlag.AlignLeft)
        self.path_label = QLabel("")
        self.path_label.setObjectName("path")
        self.path_label.setWordWrap(True)
        fr.addWidget(self.path_label)
        layout.addWidget(file_row)
        layout.addSpacing(8)
        layout.addWidget(self.rb_apps)
        apps_hint = QLabel(tr("Программы из пакетов DEB и RPM не обновляются вместе с системой — "
                              "их обновления проверяются здесь."))
        apps_hint.setObjectName("hint")
        apps_hint.setWordWrap(True)
        apps_hint.setContentsMargins(28, 0, 0, 0)
        layout.addWidget(apps_hint)
        layout.addStretch()

    def initializePage(self):
        if self.wizard().package_path:
            self.path_label.setText(tr("Выбранный файл: {}", self.wizard().package_path))

    def _mode_changed(self):
        self.btn_browse.setEnabled(self.rb_file.isChecked())
        self.completeChanged.emit()

    def browse_file(self):
        patterns = " ".join(f"*{e}" for e in SUPPORTED_EXT)
        file, _ = QFileDialog.getOpenFileName(self, tr("Выбор пакета"), "", f"{tr('Поддерживаемые пакеты')} ({patterns})")
        if file:
            self.wizard().package_path = file
            self.path_label.setText(tr("Выбранный файл: {}", file))
            self.completeChanged.emit()

    def isComplete(self):
        return self.rb_apps.isChecked() or bool(self.wizard().package_path)

    def nextId(self):
        return PAGE_APPS if self.rb_apps.isChecked() else PAGE_INSTALL


class DependencyConfirmDialog(QDialog):
    """Какие пакеты foreign_bridge.py («plan») хочет скачать ради недостающих
    библиотек — по флажку на кандидата, до того как что-либо скачано.

    Совпадение имени библиотеки по базе файлов pacman бывает неоднозначным или
    указывает на неожиданно большой пакет — пользователь видит это заранее."""

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Недостающие зависимости"))
        self.setMinimumWidth(460)
        self._checkboxes = []
        layout = QVBoxLayout(self)
        intro = QLabel(tr("Этому пакету нужны библиотеки, которых ещё нет в системе. "
                          "Посмотрите, что будет скачано, прежде чем продолжить:"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        rows = QWidget()
        rows_layout = QVBoxLayout(rows)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        for lib, candidates in plan.get("missing", {}).items():
            for i, candidate in enumerate(candidates):
                size = candidate.get("size")
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                cb = QCheckBox()
                # по умолчанию — только первый кандидат на библиотеку: ставить все
                # пакеты, которые её «предлагают», — неверное умолчание
                cb.setChecked(i == 0)
                cb.pkg_name, cb.pkg_size = candidate["pkg"], size or 0
                cb.toggled.connect(self._update_total)
                row_layout.addWidget(cb)
                # отдельная метка: текст флажка нельзя выделить и скопировать
                lbl = QLabel(f"{candidate['pkg']} ({candidate['repo']}) — {lib} — "
                             f"{format_size(size) if size else tr('размер неизвестен')}")
                lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                row_layout.addWidget(lbl, 1)
                rows_layout.addWidget(row)
                self._checkboxes.append(cb)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(rows)
        scroll.setMaximumHeight(220)
        layout.addWidget(scroll)

        unresolved = plan.get("unresolved", [])
        if unresolved:
            warn = QLabel(tr("Не найден пакет для: {} — программа может не запуститься.", ", ".join(unresolved)))
            warn.setObjectName("warn")
            warn.setWordWrap(True)
            warn.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(warn)

        self.lbl_total = QLabel()
        layout.addWidget(self.lbl_total)
        self._update_total()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Установить"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_total(self):
        total = sum(cb.pkg_size for cb in self._checkboxes if cb.isChecked())
        self.lbl_total.setText(tr("Всего к загрузке: {}", format_size(total)))

    def approved_packages(self):
        return list(dict.fromkeys(cb.pkg_name for cb in self._checkboxes if cb.isChecked()))


class InstallPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(tr("Установка"))
        self.setSubTitle(tr("Пакет устанавливается в систему…"))
        layout = QVBoxLayout(self)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)
        self.process = None
        self.succeeded = False

    @property
    def path(self) -> str:
        return self.wizard().package_path

    def nextId(self):
        return PAGE_SUMMARY

    def log(self, text: str, role: str | None = None):
        self.log_output.append(colored(text, role) if role else text)

    def initializePage(self):
        for b in (QWizard.WizardButton.BackButton, QWizard.WizardButton.NextButton, QWizard.WizardButton.CancelButton):
            self.wizard().button(b).setEnabled(False)
        self.log_output.clear()
        self.log(tr("Подготовка к установке: {}", self.path) + "\n")
        # .deb/.rpm: зависимости pacman не знает — сначала план (без root, ничего не
        # скачивается), пользователь подтверждает кандидатов до шага с pkexec
        if self.path.endswith(FOREIGN_EXT):
            self.run_dependency_plan()
        else:
            self.start_installation()

    def run_dependency_plan(self, retried_after_sync=False):
        self._plan_output = ""
        self._plan_process = QProcess(self)
        self._plan_process.readyReadStandardOutput.connect(self._on_plan_stdout)
        self._plan_process.readyReadStandardError.connect(
            lambda: self.log(self._plan_process.readAllStandardError().data().decode().strip(), "red"))
        self._plan_process.finished.connect(lambda *_: self._on_plan_finished(retried_after_sync))
        self._plan_process.start(sys.executable, [BRIDGE, "plan", self.path])

    def _on_plan_stdout(self):
        data = self._plan_process.readAllStandardOutput().data().decode()
        self._plan_output += data
        for line in data.splitlines():
            if not line.startswith("PLAN_JSON:"):
                self.log(line.strip())

    def _on_plan_finished(self, retried_after_sync):
        plan = None
        for line in self._plan_output.splitlines():
            if line.startswith("PLAN_JSON:"):
                try:
                    plan = json.loads(line[len("PLAN_JSON:"):])
                except ValueError:
                    plan = None
                break
        if plan is None:
            self.log(tr("Не удалось проверить зависимости — установка без них."), "red")
            self.start_installation()
            return
        if plan.get("file_db_stale") and not retried_after_sync:
            self.log(tr("Синхронизация базы зависимостей (нужен пароль администратора)…"))
            self._sync_process = QProcess(self)
            self._sync_process.finished.connect(lambda *_: self.run_dependency_plan(retried_after_sync=True))
            self._sync_process.start("pkexec", [sys.executable, BRIDGE, "sync-file-db"])
            return
        if plan.get("missing") or plan.get("unresolved"):
            dialog = DependencyConfirmDialog(plan, self.wizard())
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.start_installation(dialog.approved_packages())
            else:
                self.log(tr("Установка отменена."), "red")
                self.process_finished(1, QProcess.ExitStatus.NormalExit)
            return
        self.start_installation()

    def start_installation(self, approved_deps=None):
        if self.path.endswith(PACMAN_EXT):
            command, args = "pkexec", ["pacman", "-U", "--noconfirm", self.path]
        elif self.path.endswith(FLATPAK_EXT):
            if not shutil.which("flatpak"):
                self.log(tr("Flatpak не установлен в системе."), "red")
                self.process_finished(1, QProcess.ExitStatus.NormalExit)
                return
            # без pkexec: flatpak сам повышает права через polkit; от root он
            # поставил бы программу в данные root, а не пользователя
            command, args = "flatpak", ["install", "--noninteractive", "-y"]
            if self.path.endswith(".flatpak"):
                args.append("--bundle")
            args.append(self.path)
        else:
            command, args = "pkexec", [sys.executable, BRIDGE, "install", self.path]
            if approved_deps:
                args.append(",".join(approved_deps))
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(
            lambda: self.log(self.process.readAllStandardOutput().data().decode().strip()))
        self.process.readyReadStandardError.connect(
            lambda: self.log(self.process.readAllStandardError().data().decode().strip(), "red"))
        self.process.finished.connect(self.process_finished)
        self.process.start(command, args)

    def process_finished(self, exit_code, _status):
        self.succeeded = exit_code == 0
        if self.succeeded:
            self.log("\n" + tr("Установка успешно завершена!"), "green")
            if self.path.endswith(FOREIGN_EXT):
                self._refresh_app_menu()
        else:
            self.log("\n" + tr("Ошибка установки. Код: {}", exit_code), "red")
        self.wizard().button(QWizard.WizardButton.NextButton).setEnabled(True)

    @staticmethod
    def _refresh_app_menu():
        """Кеш меню KDE — в $HOME пользователя: kbuildsycoca6 из-под pkexec (root)
        обновил бы кеш root, поэтому он запускается здесь, без повышения прав."""
        if shutil.which("kbuildsycoca6"):
            QProcess.startDetached("kbuildsycoca6", ["--noincremental"])


class AppsPage(QWizardPage):
    """Программы из пакетов DEB и RPM: версии, доступные обновления, что сделать."""
    COLS = ("Программа", "Установлена", "Доступна", "Источник обновлений")

    def __init__(self):
        super().__init__()
        self.setTitle(tr("Программы из пакетов DEB и RPM"))
        self.setSubTitle(tr("Выберите программу и что с ней сделать."))
        self.packages: list[InstalledPackage] = []
        self._check = None
        layout = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr(c) for c in self.COLS])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in (1, 2, 3):
            self.tree.header().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        row.addWidget(self.status, 1)
        self.btn_check = QPushButton(tr("↻ Проверить обновления"))
        self.btn_check.clicked.connect(self.check_updates)
        row.addWidget(self.btn_check)
        layout.addLayout(row)
        actions = QHBoxLayout()
        self.rb_update = QRadioButton(tr("Обновить"))
        self.rb_remove = QRadioButton(tr("Удалить"))
        group = QButtonGroup(self)
        for rb in (self.rb_update, self.rb_remove):
            group.addButton(rb)
            rb.toggled.connect(self.completeChanged)
            actions.addWidget(rb)
        actions.addStretch()
        layout.addLayout(actions)

    def initializePage(self):
        self.packages = InstalledPackage.load_all()
        self._fill()
        if not self.packages:
            self.status.setText(tr("Пакетов DEB и RPM, установленных этим установщиком, пока нет."))
        else:
            self.check_updates()

    def current(self) -> InstalledPackage | None:
        items = self.tree.selectedItems()
        if not items:
            return None
        key = items[0].data(0, Qt.ItemDataRole.UserRole)
        return next((p for p in self.packages if p.manifest == key), None)

    def _fill(self):
        selected = self.current()
        self.tree.clear()
        for p in self.packages:
            if p.error:
                available = tr("ошибка: {}", p.error[:60])
            elif p.latest is None:
                available = tr("проверка…") if (self._check and p.source) else "—"
            elif p.has_update:
                available = "⬆ " + p.latest.version
            else:
                available = tr("актуальна")
            item = QTreeWidgetItem([p.name, p.display_version, available, p.source_text])
            item.setData(0, Qt.ItemDataRole.UserRole, p.manifest)
            item.setToolTip(3, p.source.get("url", "") if p.source else "")
            self.tree.addTopLevelItem(item)
            if selected and p.manifest == selected.manifest:
                item.setSelected(True)
        self._selection_changed()

    def _selection_changed(self):
        p = self.current()
        can_update = bool(p and p.has_update)
        self.rb_update.setEnabled(can_update)
        self.rb_remove.setEnabled(p is not None)
        if self.rb_update.isChecked() and not can_update:
            self.rb_remove.setChecked(p is not None)   # нечего обновлять — остаётся только удаление
        elif can_update and not self.rb_remove.isChecked():
            self.rb_update.setChecked(True)
        self.completeChanged.emit()

    def check_updates(self):
        if self._check or not self.packages:
            return
        self.status.setText(tr("Проверка обновлений…"))
        self.btn_check.setEnabled(False)
        self._check = UpdateCheck(self.packages)
        self._check.finished.connect(self._checked)   # finished — когда поток уже завершён
        self._fill()
        self._check.start()

    def _checked(self):
        self._check = None
        self.btn_check.setEnabled(True)
        updates = [p for p in self.packages if p.has_update]
        errors = [p for p in self.packages if p.error]
        if updates:
            self.status.setText(tr("Обновления есть: {}", ", ".join(p.name for p in updates)))
        elif errors:
            self.status.setText(tr("Не удалось проверить: {}", ", ".join(p.name for p in errors)))
        else:
            self.status.setText(tr("Все программы актуальны."))
        self._fill()

    def isComplete(self):
        p = self.current()
        return bool(p and ((self.rb_update.isChecked() and p.has_update) or self.rb_remove.isChecked()))

    def validatePage(self):
        self.wizard().selected_app = self.current()
        return True

    def nextId(self):
        return PAGE_DOWNLOAD if self.rb_update.isChecked() else PAGE_REMOVE


class DownloadPage(QWizardPage):
    """Скачивание новой версии с сайта производителя и сверка контрольной суммы;
    затем мастер сам переходит к установке."""

    def __init__(self):
        super().__init__()
        self.setTitle(tr("Загрузка обновления"))
        layout = QVBoxLayout(self)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        layout.addWidget(self.bar)
        layout.addStretch()
        self._job = None
        self._done = False

    def initializePage(self):
        app = self.wizard().selected_app
        self._done = False
        self.setSubTitle(tr("{}: версия {}", app.name, app.latest.version))
        self.label.setText(tr("Скачивание {}… {}%", app.name, 0))
        self.bar.setValue(0)
        self._job = Download(app.latest)
        self._job.progress.connect(self._progress)
        self._job.finished.connect(self._finished)   # finished — когда поток уже завершён
        self._job.start()

    def _progress(self, pc: int):
        self.bar.setValue(pc)
        self.label.setText(tr("Скачивание {}… {}%", self.wizard().selected_app.name, pc))

    def _finished(self):
        job, self._job = self._job, None
        if job.error or not job.path:
            self.label.setText(colored(tr("Не удалось скачать: {}", job.error), "red"))
            return
        self.wizard().package_path = job.path
        self.wizard().downloaded = job.path
        self._done = True
        self.completeChanged.emit()
        self.wizard().next()   # сразу к установке, как в мастерах Windows

    def isComplete(self):
        return self._done

    def nextId(self):
        return PAGE_INSTALL


class RemovePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(tr("Удаление"))
        layout = QVBoxLayout(self)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)
        self._done = False

    def initializePage(self):
        app = self.wizard().selected_app
        self.setSubTitle(tr("Удаление «{}» и всех её файлов…", app.name))
        self._done = False
        self.log_output.clear()
        for b in (QWizard.WizardButton.BackButton, QWizard.WizardButton.CancelButton):
            self.wizard().button(b).setEnabled(False)
        self.proc = QProcess(self)
        self.proc.readyReadStandardOutput.connect(
            lambda: self.log_output.append(self.proc.readAllStandardOutput().data().decode().strip()))
        self.proc.readyReadStandardError.connect(
            lambda: self.log_output.append(colored(self.proc.readAllStandardError().data().decode().strip(), "red")))
        self.proc.finished.connect(self._finished)
        self.proc.start("pkexec", [sys.executable, BRIDGE, "uninstall", app.manifest])

    def _finished(self, code, _status):
        name = self.wizard().selected_app.name
        self.log_output.append("\n" + (colored(tr("Удалено: {}", name), "green") if code == 0
                                       else colored(tr("Не удалось удалить."), "red")))
        if code == 0:
            InstallPage._refresh_app_menu()
        self._done = True
        self.completeChanged.emit()

    def isComplete(self):
        return self._done

    def nextId(self):
        return PAGE_SUMMARY


class SummaryPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(tr("Готово"))
        layout = QVBoxLayout(self)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def initializePage(self):
        text = tr("Установщик Equestria OS закончил работу.\n\nОкно можно закрыть.")
        if self.wizard().package_path.endswith(FOREIGN_EXT) and not self.wizard().downloaded:
            text += "\n\n" + tr("Программы из пакетов DEB и RPM не обновляются вместе с системой. "
                                "Проверить их обновления можно в установщике, если открыть его без файла.")
        self.label.setText(text)


class InstallWizard(QWizard):
    def __init__(self, package_path: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Установщик Equestria OS"))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.resize(680, 500)
        self.package_path = package_path
        self.selected_app: InstalledPackage | None = None
        self.downloaded = ""          # скачанное обновление — удаляется после работы
        self.setPage(PAGE_WELCOME, WelcomePage())
        self.setPage(PAGE_INSTALL, InstallPage())
        self.setPage(PAGE_APPS, AppsPage())
        self.setPage(PAGE_DOWNLOAD, DownloadPage())
        self.setPage(PAGE_REMOVE, RemovePage())
        self.setPage(PAGE_SUMMARY, SummaryPage())
        # файл уже выбран (открыт из Dolphin) — сразу к установке
        self.setStartId(PAGE_INSTALL if package_path else PAGE_WELCOME)
        self.finished.connect(self._cleanup)

    def _cleanup(self, *_):
        if self.downloaded:
            try:
                os.remove(self.downloaded)
            except OSError:
                pass
