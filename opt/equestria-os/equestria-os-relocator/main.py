import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from app import RelocatorApp
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt


def main():
    paths = sys.argv[1:]
    app = QApplication(sys.argv)
    kit_qt.ThemeManager(app)  # общая тема Equestria OS: следит за переключателем персонажей
    app.setDesktopFileName("equestria-os-relocator")
    app.setWindowIcon(QIcon.fromTheme("equestria-os-relocator"))
    win = RelocatorApp(initial_sources=paths)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
