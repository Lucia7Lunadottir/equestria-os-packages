#!/usr/bin/env python3
"""Установщик пакетов Equestria OS.

Мастер установки, как в Windows: шаг за шагом.
    equestria-installer <файл>   сразу к установке файла (.pkg.tar.zst, .deb, .rpm, .flatpak, .flatpakref)
    equestria-installer          первая страница: установить из файла или обновить/удалить программу DEB/RPM
    equestria-installer --list-foreign-updates / --update-foreign [имя ...]   без окна (Software Center)

Модули лежат рядом (после установки — /usr/lib/equestria-installer):
    install_wizard.py  страницы мастера
    foreign_apps.py    установленные программы DEB/RPM: проверка обновлений, скачивание
    foreign_cli.py     то же без окна — для кнопки «Обновить систему» в Software Center
    sources.py         репозитории производителей (APT/YUM): версии и скачивание
    pkgmeta.py         чтение .deb/.rpm без запуска их скриптов, источник обновлений
    foreign_bridge.py  установка/удаление DEB/RPM от root (через pkexec)
"""
import os
import sys
import traceback
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from PyQt6.QtCore import QLibraryInfo, QLocale, QTranslator
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from ui_common import QSS, kit_qt, tr
from equestria_kit.i18n import detect_language


def package_from_args(argv: list[str]) -> str:
    for arg in argv:
        if arg.startswith("file://"):
            arg = urllib.parse.unquote(arg[7:])
        from install_wizard import SUPPORTED_EXT
        if arg.endswith(SUPPORTED_EXT):
            return arg
    return ""


def install_excepthook():
    """Исключение в слоте Qt без этого молча завершает PyQt6-приложение."""
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        sys.stderr.write(text)
        if QApplication.instance():
            QMessageBox.critical(None, tr("Установщик Equestria OS"), text[-1500:])
    sys.excepthook = hook


def main():
    import foreign_cli
    code = foreign_cli.main(sys.argv[1:])   # без окна: --list-foreign-updates / --update-foreign
    if code is not None:
        sys.exit(code)
    install_excepthook()
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria OS Package Installer")
    app.setDesktopFileName("equestria-installer")
    icon = QIcon.fromTheme("equestria-installer")
    if icon.isNull():
        icon = QIcon(os.path.join(os.path.dirname(os.path.realpath(__file__)), "Installer.svg"))
    app.setWindowIcon(icon)
    # стандартные кнопки Qt (Далее/Назад/Отмена) — на языке интерфейса
    qt_tr = QTranslator(app)
    if qt_tr.load(QLocale(detect_language()), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(qt_tr)
    kit_qt.ThemeManager(app, QSS)   # общая тема Equestria: следит за переключателем персонажей

    from install_wizard import InstallWizard
    window = InstallWizard(package_from_args(sys.argv[1:]))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
