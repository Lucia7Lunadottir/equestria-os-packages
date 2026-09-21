#!/usr/bin/env python3
import json
import os
import shutil
import sys
import urllib.parse
from PyQt6.QtWidgets import (QApplication, QWizard, QWizardPage, QLabel,
                             QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QTextEdit,
                             QDialog, QCheckBox, QDialogButtonBox, QScrollArea, QWidget)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QProcess, Qt, QTranslator, QLocale

PURPLE_THEME = """
QWidget {
    background-color: #2D1B4E;
    color: #F8F4FF;
}
QLabel {
    font-size: 14px;
    background: transparent;
}
QPushButton {
    background-color: #6A1B9A;
    color: white;
    border: 2px solid #8E24AA;
    border-radius: 5px;
    padding: 6px 15px;
    font-weight: bold;
}
QPushButton:hover { background-color: #8E24AA; }
QPushButton:disabled { background-color: #4A3B5E; border: 2px solid #3A2B4E; color: #9E9E9E; }
QTextEdit { background-color: #1A0B2E; color: #E1BEE7; border: 1px solid #8E24AA; font-family: monospace; }
"""

class WelcomePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(self.tr("Equestria OS Package Installer"))
        self.setSubTitle(self.tr("Local Package Installation Wizard"))


        layout = QVBoxLayout()
        self.info_label = QLabel(self.tr("Welcome to the installer!\n\nPlease select a package file (.pkg.tar.zst, .deb, .rpm, .flatpakref)."))
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.btn_browse = QPushButton(self.tr("Browse"))
        self.btn_browse.clicked.connect(self.browse_file)
        layout.addWidget(self.btn_browse)

        self.path_label = QLabel("")
        self.path_label.setStyleSheet("color: #CE93D8; font-style: italic; margin-top: 10px;")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        self.setLayout(layout)

    def initializePage(self):
        if self.wizard().package_path:
            self.path_label.setText(self.tr("Selected file: ") + self.wizard().package_path)
            self.completeChanged.emit()

    def browse_file(self):
        file, _ = QFileDialog.getOpenFileName(
            self, self.tr("Select Package"), "",
            "Supported Packages (*.pkg.tar.zst *.pkg.tar.xz *.deb *.rpm *.flatpakref)")
        if file:
            self.wizard().package_path = file
            self.path_label.setText(self.tr("Selected file: ") + file)
            self.completeChanged.emit()

    def isComplete(self):
        return hasattr(self.wizard(), 'package_path') and bool(self.wizard().package_path)

class DependencyConfirmDialog(QDialog):
    """Shows exactly which packages foreign_bridge.py's "plan" step wants to
    download to satisfy missing shared libraries, with a checkbox per
    candidate, before anything is actually downloaded or installed.

    Exists because a missing-library-name match against pacman's file
    database can be ambiguous or point at an unexpectedly large package —
    the user gets to see and veto that before it happens, rather than the
    installer silently pulling in whatever it guessed."""

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Missing dependencies"))
        self.setMinimumWidth(440)
        self._checkboxes = []

        layout = QVBoxLayout(self)

        intro = QLabel(self.tr(
            "This package needs libraries that aren't installed yet. "
            "Review what will be downloaded before continuing:"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)

        for lib, candidates in plan.get("missing", {}).items():
            for i, candidate in enumerate(candidates):
                size = candidate.get("size")
                size_text = self._format_size(size) if size else self.tr("unknown size")

                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)

                cb = QCheckBox()
                # Only the first candidate per missing library is ticked by
                # default — if several packages claim to provide the same
                # library, installing all of them isn't the right default.
                cb.setChecked(i == 0)
                cb.pkg_name = candidate["pkg"]
                cb.pkg_size = size or 0
                cb.toggled.connect(self._update_total)
                row_layout.addWidget(cb)

                # A separate, selectable label — QCheckBox's own text can't
                # be selected/copied with the mouse, and package/library
                # names are exactly what someone would want to copy out.
                lbl = QLabel(f"{candidate['pkg']} ({candidate['repo']}) — {lib} — {size_text}")
                lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                lbl.setCursor(Qt.CursorShape.IBeamCursor)
                row_layout.addWidget(lbl, 1)

                list_layout.addWidget(row)
                self._checkboxes.append(cb)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(list_container)
        scroll.setMaximumHeight(220)
        layout.addWidget(scroll)

        unresolved = plan.get("unresolved", [])
        if unresolved:
            warn = QLabel(self.tr("No package found for: ") + ", ".join(unresolved) +
                          self.tr(" — the app may not start correctly."))
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #FF8A80;")
            warn.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(warn)

        self.lbl_total = QLabel()
        layout.addWidget(self.lbl_total)
        self._update_total()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Install"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _format_size(n):
        value = float(n)
        for unit in ("B", "KiB", "MiB", "GiB"):
            if value < 1024 or unit == "GiB":
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024

    def _update_total(self):
        total = sum(cb.pkg_size for cb in self._checkboxes if cb.isChecked())
        self.lbl_total.setText(self.tr("Total download: ") + self._format_size(total))

    def approved_packages(self):
        seen = set()
        approved = []
        for cb in self._checkboxes:
            if cb.isChecked() and cb.pkg_name not in seen:
                seen.add(cb.pkg_name)
                approved.append(cb.pkg_name)
        return approved


class InstallPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(self.tr("Installation"))
        self.setSubTitle(self.tr("Integrating package into the system..."))

        layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)
        self.setLayout(layout)
        self.process = None

    def initializePage(self):
        self.wizard().button(QWizard.WizardButton.BackButton).setEnabled(False)
        self.wizard().button(QWizard.WizardButton.NextButton).setEnabled(False)
        self.wizard().button(QWizard.WizardButton.CancelButton).setEnabled(False)

        self.log_output.clear()
        self.log_output.append(self.tr("Preparing to install: ") + self.wizard().package_path + "\n")

        # .deb/.rpm go through foreign_bridge.py, which can't natively
        # resolve dependencies the way pacman/flatpak do — a missing library
        # name has to be matched against pacman's file database, which can
        # be ambiguous. Plan first (unprivileged, nothing downloaded yet)
        # and let the user see/approve the candidates before any pkexec step.
        if self.wizard().package_path.endswith(('.deb', '.rpm')):
            self.run_dependency_plan()
        else:
            self.start_installation()

    def _bridge_path(self):
        bridge = os.path.join(os.path.dirname(os.path.abspath(__file__)), "foreign_bridge.py")
        if not os.path.isfile(bridge):
            bridge = "/usr/lib/equestria-installer/foreign_bridge.py"
        return bridge

    def run_dependency_plan(self, retried_after_sync=False):
        self._plan_output = ""
        self._plan_process = QProcess()
        self._plan_process.readyReadStandardOutput.connect(self._on_plan_stdout)
        self._plan_process.readyReadStandardError.connect(self.handle_stderr)
        self._plan_process.finished.connect(
            lambda code, status, retried=retried_after_sync: self._on_plan_finished(retried))
        self._plan_process.start(sys.executable, [self._bridge_path(), "plan", self.wizard().package_path])

    def _on_plan_stdout(self):
        data = self._plan_process.readAllStandardOutput().data().decode()
        self._plan_output += data
        for line in data.splitlines():
            if not line.startswith("PLAN_JSON:"):
                self.log_output.append(line.strip())

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
            self.log_output.append(
                "<span style='color: #FF5252;'>" +
                self.tr("Could not check dependencies — installing without them.") + "</span>")
            self.start_installation()
            return

        if plan.get("file_db_stale") and not retried_after_sync:
            self.log_output.append(self.tr("Syncing dependency database (needs admin password)..."))
            self._sync_process = QProcess()
            self._sync_process.finished.connect(lambda *_: self.run_dependency_plan(retried_after_sync=True))
            self._sync_process.start("pkexec", [sys.executable, self._bridge_path(), "sync-file-db"])
            return

        if plan.get("missing") or plan.get("unresolved"):
            dialog = DependencyConfirmDialog(plan, self.wizard())
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.start_installation(dialog.approved_packages())
            else:
                self.log_output.append(
                    "<span style='color: #FF5252;'>" + self.tr("Installation cancelled.") + "</span>")
                self.process_finished(1, QProcess.ExitStatus.NormalExit)
            return

        self.start_installation()

    def start_installation(self, approved_deps=None):
        package_path = self.wizard().package_path

        if package_path.endswith(('.pkg.tar.zst', '.pkg.tar.xz')):
            command = "pkexec"
            args = ["pacman", "-U", "--noconfirm", package_path]
        elif package_path.endswith('.flatpakref'):
            if not shutil.which("flatpak"):
                self.log_output.append(
                    "<span style='color: #FF5252;'>" +
                    self.tr("Flatpak is not installed on this system.") + "</span>")
                self.process_finished(1, QProcess.ExitStatus.NormalExit)
                return
            # No pkexec: flatpak escalates itself via polkit for system-wide
            # installs. Running it as root here would install into root's
            # own Flatpak data instead of the actual desktop user's.
            command = "flatpak"
            args = ["install", "--noninteractive", "-y", package_path]
        else:
            command = "pkexec"
            args = [sys.executable, self._bridge_path(), "install", package_path]
            if approved_deps:
                args.append(",".join(approved_deps))

        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)
        self.process.start(command, args)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.log_output.append(data.strip())

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.log_output.append(f"<span style='color: #FF5252;'>{data.strip()}</span>")

    def process_finished(self, exitCode, exitStatus):
        if exitCode == 0:
            self.log_output.append("\n<span style='color: #69F0AE;'>" + self.tr("Installation successfully completed!") + "</span>")
        else:
            self.log_output.append("\n<span style='color: #FF5252;'>" + self.tr("Installation error. Code: ") + str(exitCode) + "</span>")
        self.wizard().button(QWizard.WizardButton.NextButton).setEnabled(True)

class SummaryPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(self.tr("Completed"))
        layout = QVBoxLayout()
        label = QLabel(self.tr("Equestria OS installer has finished its work.\n\nYou can close the window."))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self.setLayout(layout)

class EquestriaInstaller(QWizard):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(self.tr("Equestria OS Installer"))
        self.setFixedSize(600, 450)
        self.setStyleSheet(PURPLE_THEME)
        app.setApplicationName("Equestria OS Package Installer")
        app.setDesktopFileName("equestria-installer.desktop")
        icon = QIcon.fromTheme("equestria-installer")
        if icon.isNull():
            icon = QIcon(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Installer.svg"))
        app.setWindowIcon(icon)
        self.setWindowIcon(icon)

        self.package_path = ""
        for arg in sys.argv[1:]:
            if arg.startswith("file://"):
                arg = urllib.parse.unquote(arg[7:])

            if arg.endswith(('.pkg.tar.zst', '.pkg.tar.xz', '.deb', '.rpm', '.flatpakref')):
                self.package_path = arg
                break

        self.addPage(WelcomePage())
        self.addPage(InstallPage())
        self.addPage(SummaryPage())

if __name__ == '__main__':
    app = QApplication(sys.argv)


    # Путь к директории с переводами системного пакета
    tx_dir = "/usr/share/equestria-installer/translations/"

    translator = QTranslator()
    current_locale = QLocale.system().name() # Например, "ru_RU" или "en_GB"

    # 1. Пытаемся загрузить точное совпадение (например, ru_RU.qm)
    if not translator.load(current_locale, tx_dir):
        # 2. Если точного совпадения нет, ищем по базовому языку (из "en_GB" берем "en")
        base_lang = current_locale.split('_')[0]
        supported_locales = ['ru_RU', 'uk_UA', 'de_DE', 'en_US', 'es_ES', 'fr_FR', 'pl_PL', 'it_IT', 'kk_KZ', 'zh_CN', 'ja_JP']

        for fallback_locale in supported_locales:
            if fallback_locale.startswith(base_lang):
                translator.load(fallback_locale, tx_dir)
                break

    if not translator.isEmpty():
        app.installTranslator(translator)

    wizard = EquestriaInstaller()
    wizard.show()
    sys.exit(app.exec())
