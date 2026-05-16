#!/usr/bin/env python3
import sys
import urllib.parse
from PyQt6.QtWidgets import (QApplication, QWizard, QWizardPage, QLabel, 
                             QVBoxLayout, QPushButton, QFileDialog, QTextEdit)
from PyQt6.QtCore import QProcess, Qt, QTranslator, QLocale

# Исправленная тема: применяем ко всем QWidget, чтобы перекрыть белые фоны
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
        self.info_label = QLabel(self.tr("Welcome to the installer!\n\nPlease select a .pkg.tar.zst file."))
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
        # Проверяем, был ли передан файл при запуске
        if self.wizard().package_path:
            self.path_label.setText(self.tr("Selected file: ") + self.wizard().package_path)
            self.completeChanged.emit()

    def browse_file(self):
        file, _ = QFileDialog.getOpenFileName(self, self.tr("Select Arch Linux Package"), "", "Arch Packages (*.pkg.tar.zst *.pkg.tar.xz)")
        if file:
            self.wizard().package_path = file
            self.path_label.setText(self.tr("Selected file: ") + file)
            self.completeChanged.emit()

    def isComplete(self):
        return hasattr(self.wizard(), 'package_path') and bool(self.wizard().package_path)

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
        self.start_installation()

    def start_installation(self):
        # Если путь содержит пробелы, pkexec/pacman могут ругаться, но QProcess с массивом аргументов обрабатывает их безопасно
        command = "pkexec"
        args = ["pacman", "-U", "--noconfirm", self.wizard().package_path]

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
        
        # Надежный парсинг аргументов от файловых менеджеров
        self.package_path = ""
        for arg in sys.argv[1:]:
            # Если DE передало file:// (например, KDE Plasma)
            if arg.startswith("file://"):
                arg = urllib.parse.unquote(arg[7:]) # Очищаем и декодируем пробелы (%20)
            
            if arg.endswith('.pkg.tar.zst') or arg.endswith('.pkg.tar.xz'):
                self.package_path = arg
                break

        self.addPage(WelcomePage())
        self.addPage(InstallPage())
        self.addPage(SummaryPage())
        
        # Убрали ModernStyle, теперь тема ляжет ровно!

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    translator = QTranslator()
    locale = QLocale.system().name()
    if translator.load(locale, "/usr/share/equestria-installer/translations/"):
        app.installTranslator(translator)
        
    wizard = EquestriaInstaller()
    wizard.show()
    sys.exit(app.exec())