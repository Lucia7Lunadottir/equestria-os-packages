import os
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from app import SettingsWindow
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt

BASE_PATH = os.path.dirname(os.path.abspath(__file__))


def main():
    app = QApplication(sys.argv)
    kit_qt.ThemeManager(app)  # общая тема Equestria OS: следит за переключателем персонажей
    app.setDesktopFileName("equestria-os-settings")

    icon_path = os.path.join(BASE_PATH, "equestria-os-settings.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = SettingsWindow(BASE_PATH)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
