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

from PyQt6.QtCore import QProcess, Qt, QSignalBlocker, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
                             QLabel, QProgressBar, QPushButton, QRadioButton, QScrollArea, QTextEdit, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget, QWizard, QWizardPage)

from foreign_apps import Download, InstalledPackage, UpdateCheck
from ui_common import BRIDGE, colored, tr, catalog, live_i18n, ui_call

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


def run_logged_process(parent, command, args, log, finished, *, stdout=None):
    process = QProcess(parent)

    def stream_reader(read, write):
        pending = b""

        def drain(final=False):
            nonlocal pending
            # A QProcess read can split a UTF-8 character or a PLAN_JSON line.
            lines = (pending + read().data()).splitlines(keepends=True)
            pending = b""
            if lines and not final and not lines[-1].endswith((b"\r", b"\n")):
                pending = lines.pop()
            for line in lines:
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if text:
                    write(text)

        return drain

    read_stdout = stream_reader(process.readAllStandardOutput, stdout or log)
    read_stderr = stream_reader(process.readAllStandardError, lambda text: log(text, "red"))

    def complete(code, status):
        read_stdout(final=True)
        read_stderr(final=True)
        process.deleteLater()
        finished(code, status)

    def on_error(error):
        if error == QProcess.ProcessError.FailedToStart:
            log(process.errorString(), "red")
            complete(-1, QProcess.ExitStatus.CrashExit)

    process.readyReadStandardOutput.connect(read_stdout)
    process.readyReadStandardError.connect(read_stderr)
    process.finished.connect(complete)
    process.errorOccurred.connect(on_error)
    process.start(command, args)


class WelcomePage(QWizardPage):
    """Что сделать: установить программу из файла или обновить/удалить уже установленную."""

    def __init__(self):
        super().__init__()
        ui_call(self.setTitle, tr("install_wizard.equestria_os_package_installer"))
        ui_call(self.setSubTitle, tr("install_wizard.local_package_installation_wizard"))
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.rb_file = ui_call(QRadioButton, tr("install_wizard.install_app_from_file"))
        self.rb_apps = ui_call(QRadioButton, tr("install_wizard.update_remove_app_from_deb"))
        self.rb_file.setChecked(True)
        group = QButtonGroup(self)
        for rb in (self.rb_file, self.rb_apps):
            group.addButton(rb)
            rb.toggled.connect(self._mode_changed)
        layout.addWidget(self.rb_file)
        file_row = QWidget()
        fr = QVBoxLayout(file_row)
        fr.setContentsMargins(28, 0, 0, 0)
        hint = ui_call(QLabel, tr("install_wizard.supported_pkg_tar_zst_deb"))
        hint.setObjectName("hint")
        fr.addWidget(hint)
        self.btn_browse = ui_call(QPushButton, tr("install_wizard.browse"))
        self.btn_browse.setObjectName("primary")
        self.btn_browse.clicked.connect(self.browse_file)
        fr.addWidget(self.btn_browse, 0, Qt.AlignmentFlag.AlignLeft)
        self.path_label = ui_call(QLabel, "")
        self.path_label.setObjectName("path")
        self.path_label.setWordWrap(True)
        fr.addWidget(self.path_label)
        layout.addWidget(file_row)
        layout.addSpacing(8)
        layout.addWidget(self.rb_apps)
        apps_hint = ui_call(QLabel, tr("install_wizard.apps_from_deb_rpm_packages_2"))
        apps_hint.setObjectName("hint")
        apps_hint.setWordWrap(True)
        apps_hint.setContentsMargins(28, 0, 0, 0)
        layout.addWidget(apps_hint)
        layout.addStretch()

    def initializePage(self):
        if self.wizard().package_path:
            ui_call(self.path_label.setText, tr("install_wizard.selected_file", self.wizard().package_path))

    def _mode_changed(self):
        self.btn_browse.setEnabled(self.rb_file.isChecked())
        self.completeChanged.emit()

    def browse_file(self):
        patterns = " ".join(f"*{e}" for e in SUPPORTED_EXT)
        file, _ = QFileDialog.getOpenFileName(self, tr("install_wizard.choose_package"), "", f"{tr("install_wizard.supported_packages")} ({patterns})")
        if file:
            self.wizard().package_path = file
            ui_call(self.path_label.setText, tr("install_wizard.selected_file", file))
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
        ui_call(self.setWindowTitle, tr("install_wizard.missing_dependencies"))
        self.setMinimumWidth(460)
        self._checkboxes = []
        layout = QVBoxLayout(self)
        intro = ui_call(QLabel, tr("install_wizard.package_needs_libraries_not_installed"))
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
                cb = ui_call(QCheckBox, )
                # по умолчанию — только первый кандидат на библиотеку: ставить все
                # пакеты, которые её «предлагают», — неверное умолчание
                cb.setChecked(i == 0)
                cb.pkg_name, cb.pkg_size = candidate["pkg"], size or 0
                cb.toggled.connect(self._update_total)
                row_layout.addWidget(cb)
                # отдельная метка: текст флажка нельзя выделить и скопировать
                lbl = ui_call(QLabel, live_i18n.format_text("{} ({}) — {} — {}", candidate['pkg'], candidate['repo'],
                             lib, format_size(size) if size else tr("install_wizard.size_unknown")))
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
            warn = ui_call(QLabel, tr("common.no_package_found_app_may", ", ".join(unresolved)))
            warn.setObjectName("warn")
            warn.setWordWrap(True)
            warn.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(warn)

        self.lbl_total = ui_call(QLabel, )
        layout.addWidget(self.lbl_total)
        self._update_total()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ui_call(buttons.button(QDialogButtonBox.StandardButton.Ok).setText, tr("install_wizard.install"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_total(self):
        total = sum(cb.pkg_size for cb in self._checkboxes if cb.isChecked())
        ui_call(self.lbl_total.setText, tr("install_wizard.total_download", format_size(total)))

    def approved_packages(self):
        return list(dict.fromkeys(cb.pkg_name for cb in self._checkboxes if cb.isChecked()))


class InstallPage(QWizardPage):
    def __init__(self):
        super().__init__()
        ui_call(self.setTitle, tr("install_wizard.installation"))
        ui_call(self.setSubTitle, tr("install_wizard.installing_package_into_system"))
        layout = QVBoxLayout(self)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)
        self._done = False
        self.succeeded = False

    @property
    def path(self) -> str:
        return self.wizard().package_path

    def nextId(self):
        return PAGE_SUMMARY

    def log(self, text: str, role: str | None = None):
        self.log_output.append(colored(text, role) if role else text)

    def initializePage(self):
        self._done = False
        self.succeeded = False
        self.completeChanged.emit()
        for b in (QWizard.WizardButton.BackButton, QWizard.WizardButton.CancelButton):
            self.wizard().button(b).setEnabled(False)
        self.log_output.clear()
        self.log(tr("install_wizard.preparing_install", self.path) + "\n")
        # .deb/.rpm: зависимости pacman не знает — сначала план (без root, ничего не
        # скачивается), пользователь подтверждает кандидатов до шага с pkexec
        if self.path.endswith(FOREIGN_EXT):
            self.run_dependency_plan()
        else:
            self.start_installation()

    def isComplete(self):
        return self._done

    def validatePage(self):
        return self.isComplete()

    def run_dependency_plan(self, retried_after_sync=False):
        self._plan_json = None
        run_logged_process(
            self, sys.executable, [BRIDGE, "plan", self.path], self.log,
            lambda *_: self._on_plan_finished(retried_after_sync), stdout=self._on_plan_stdout,
        )

    def _on_plan_stdout(self, line):
        if line.startswith("PLAN_JSON:"):
            if self._plan_json is None:
                self._plan_json = line[len("PLAN_JSON:"):]
        else:
            self.log(line)

    def _on_plan_finished(self, retried_after_sync):
        plan = None
        if self._plan_json is not None:
            try:
                plan = json.loads(self._plan_json)
            except ValueError:
                pass
        if plan is None:
            self.log(tr("install_wizard.could_not_check_dependencies_installing"), "red")
            self.start_installation()
            return
        if plan.get("file_db_stale") and not retried_after_sync:
            self.log(tr("install_wizard.syncing_dependency_database_administrator_passwo"))
            run_logged_process(
                self, "pkexec", [sys.executable, BRIDGE, "sync-file-db"], self.log,
                lambda *_: self.run_dependency_plan(retried_after_sync=True),
            )
            return
        if plan.get("missing") or plan.get("unresolved"):
            dialog = DependencyConfirmDialog(plan, self.wizard())
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.start_installation(dialog.approved_packages())
            else:
                self.log(tr("install_wizard.installation_cancelled"), "red")
                self._mark_done()
            return
        self.start_installation()

    def start_installation(self, approved_deps=None):
        if self.path.endswith(PACMAN_EXT):
            command, args = "pkexec", ["pacman", "-U", "--noconfirm", self.path]
        elif self.path.endswith(FLATPAK_EXT):
            if not shutil.which("flatpak"):
                self.log(tr("install_wizard.flatpak_not_installed_system"), "red")
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
        run_logged_process(self, command, args, self.log, self.process_finished)

    def process_finished(self, exit_code, status):
        self.succeeded = status == QProcess.ExitStatus.NormalExit and exit_code == 0
        if self.succeeded:
            self.log("\n" + tr("common.installation_completed_successfully"), "green")
            if self.path.endswith(FOREIGN_EXT):
                self._refresh_app_menu()
        else:
            self.log("\n" + tr("common.installation_error_code", exit_code), "red")
        self._mark_done()

    def _mark_done(self):
        self._done = True
        self.completeChanged.emit()

    @staticmethod
    def _refresh_app_menu():
        """Кеш меню KDE — в $HOME пользователя: kbuildsycoca6 из-под pkexec (root)
        обновил бы кеш root, поэтому он запускается здесь, без повышения прав."""
        if shutil.which("kbuildsycoca6"):
            QProcess.startDetached("kbuildsycoca6", ["--noincremental"])


class AppsPage(QWizardPage):
    """Программы из пакетов DEB и RPM: версии, доступные обновления, что сделать."""
    COLS = ("install_wizard.app", "install_wizard.installed", "install_wizard.available", "install_wizard.update_source")

    def __init__(self):
        super().__init__()
        ui_call(self.setTitle, tr("install_wizard.apps_from_deb_rpm_packages"))
        ui_call(self.setSubTitle, tr("install_wizard.choose_app_what_do_with"))
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
        self.status = ui_call(QLabel, "")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        row.addWidget(self.status, 1)
        self.btn_check = ui_call(QPushButton, tr("install_wizard.check_updates"))
        self.btn_check.clicked.connect(self.check_updates)
        row.addWidget(self.btn_check)
        layout.addLayout(row)
        actions = QHBoxLayout()
        self.rb_update = ui_call(QRadioButton, tr("install_wizard.update"))
        self.rb_remove = ui_call(QRadioButton, tr("install_wizard.remove"))
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
            ui_call(self.status.setText, tr("install_wizard.no_deb_rpm_packages_have"))
        else:
            self.check_updates()

    def current(self) -> InstalledPackage | None:
        items = self.tree.selectedItems()
        if not items:
            return None
        key = items[0].data(0, Qt.ItemDataRole.UserRole)
        return next((p for p in self.packages if p.manifest == key), None)

    def _available(self, p):
        if p.error:
            available = tr("install_wizard.error", p.error[:60])
        elif p.latest is None:
            available = tr("install_wizard.checking") if (self._check and p.source) else "—"
        elif p.has_update:
            available = "⬆ " + p.latest.version
        else:
            available = tr("install_wizard.up_date")
        return available

    def _fill(self):
        selected = self.current()
        self.tree.clear()
        for p in self.packages:
            available = self._available(p)
            item = QTreeWidgetItem([p.name, p.display_version, available, p.source_text])
            item.setData(0, Qt.ItemDataRole.UserRole, p.manifest)
            ui_call(item.setToolTip, 3, p.source.get("url", "") if p.source else "")
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
        ui_call(self.status.setText, tr("install_wizard.checking_updates"))
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
            ui_call(self.status.setText, tr("install_wizard.updates_available", ", ".join(p.name for p in updates)))
        elif errors:
            ui_call(self.status.setText, tr("install_wizard.could_not_check", ", ".join(p.name for p in errors)))
        else:
            ui_call(self.status.setText, tr("common.all_apps_up_date"))
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
        ui_call(self.setTitle, tr("install_wizard.downloading_update"))
        layout = QVBoxLayout(self)
        self.label = ui_call(QLabel, "")
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
        ui_call(self.setSubTitle, tr("install_wizard.version", app.name, app.latest.version))
        ui_call(self.label.setText, tr("install_wizard.downloading", app.name, 0))
        self.bar.setValue(0)
        self._job = Download(app.latest)
        self._job.progress.connect(self._progress)
        self._job.finished.connect(self._finished)   # finished — когда поток уже завершён
        self._job.start()

    def _progress(self, pc: int):
        self.bar.setValue(pc)
        ui_call(self.label.setText, tr("install_wizard.downloading", self.wizard().selected_app.name, pc))

    def _finished(self):
        job, self._job = self._job, None
        if job.error or not job.path:
            ui_call(self.label.setText, colored(tr("common.could_not_download", job.error), "red"))
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
        ui_call(self.setTitle, tr("install_wizard.removal"))
        layout = QVBoxLayout(self)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)
        self._done = False

    def initializePage(self):
        app = self.wizard().selected_app
        ui_call(self.setSubTitle, tr("install_wizard.removing_all_files", app.name))
        self._done = False
        self.log_output.clear()
        for b in (QWizard.WizardButton.BackButton, QWizard.WizardButton.CancelButton):
            self.wizard().button(b).setEnabled(False)
        run_logged_process(
            self, "pkexec", [sys.executable, BRIDGE, "uninstall", app.manifest], self.log, self._finished,
        )

    def log(self, text: str, role: str | None = None):
        self.log_output.append(colored(text, role) if role else text)

    def _finished(self, code, status):
        name = self.wizard().selected_app.name
        if status == QProcess.ExitStatus.NormalExit and code == 0:
            self.log("\n" + tr("install_wizard.removed", name), "green")
            InstallPage._refresh_app_menu()
        else:
            self.log("\n" + tr("install_wizard.could_not_remove"), "red")
        self._done = True
        self.completeChanged.emit()

    def isComplete(self):
        return self._done

    def nextId(self):
        return PAGE_SUMMARY


class SummaryPage(QWizardPage):
    def __init__(self):
        super().__init__()
        ui_call(self.setTitle, tr("install_wizard.finish"))
        layout = QVBoxLayout(self)
        self.label = ui_call(QLabel, )
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def initializePage(self):
        text = tr("install_wizard.equestria_os_installer_has_finished")
        if self.wizard().package_path.endswith(FOREIGN_EXT) and not self.wizard().downloaded:
            text += "\n\n" + tr("install_wizard.apps_from_deb_rpm_packages_3")
        ui_call(self.label.setText, text)


class InstallWizard(QWizard):
    def __init__(self, package_path: str = "", parent=None):
        super().__init__(parent)
        catalog.set_language(catalog.lang, persist=False)
        ui_call(self.setWindowTitle, tr("common.equestria_os_installer"))
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
        self.language_combo = catalog.selector(self, self._language_changed)
        # Reserve the native header's logo area for the language selector.
        # Unlike a side widget, this leaves the full page width available.
        self.language_combo.setMinimumWidth(90)
        self.language_combo.setMaximumWidth(180)
        self.language_combo.setFixedHeight(max(32, self.language_combo.sizeHint().height()))
        self._language_anchor = QPixmap(min(180, max(90, self.language_combo.sizeHint().width())) + 20,
                                        self.language_combo.height() + 20)
        self._language_anchor.fill(Qt.GlobalColor.transparent)
        self.setPixmap(QWizard.WizardPixmap.LogoPixmap, self._language_anchor)
        for page_id in self.pageIds():
            if not self.page(page_id).subTitle():
                self.page(page_id).setSubTitle(" ")
        self.currentIdChanged.connect(lambda _: QTimer.singleShot(0, self._position_language))
        QTimer.singleShot(0, self._position_language)
        self._language_changed()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "language_combo"):
            QTimer.singleShot(0, self._position_language)

    def _position_language(self):
        for label in self.findChildren(QLabel):
            pixmap = label.pixmap()
            if pixmap is not None and pixmap.cacheKey() == self._language_anchor.cacheKey() and label.isVisible():
                self.language_combo.setGeometry(label.mapTo(self, label.rect().topLeft()).x(),
                                                label.mapTo(self, label.rect().topLeft()).y() + 10,
                                                self._language_anchor.width() - 20, self.language_combo.height())
                self.language_combo.raise_()
                return

    def _language_changed(self):
        for button, text in ((QWizard.WizardButton.BackButton, "install_wizard.back"),
                             (QWizard.WizardButton.NextButton, "install_wizard.next"),
                             (QWizard.WizardButton.FinishButton, "install_wizard.finish"),
                             (QWizard.WizardButton.CancelButton, "install_wizard.cancel")):
            self.setButtonText(button, str(tr(text)))
        page = self.page(PAGE_APPS)
        page.tree.setHeaderLabels([str(tr(c)) for c in page.COLS])
        blocker = QSignalBlocker(page.tree)
        packages = {p.manifest: p for p in page.packages}
        for i in range(page.tree.topLevelItemCount()):
            item = page.tree.topLevelItem(i)
            p = packages.get(item.data(0, Qt.ItemDataRole.UserRole))
            if p is not None:
                for col, text in enumerate((p.display_version, page._available(p), p.source_text), 1):
                    item.setText(col, str(text))
        del blocker

    def _cleanup(self, *_):
        if self.downloaded:
            try:
                os.remove(self.downloaded)
            except OSError:
                pass
