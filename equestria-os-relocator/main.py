import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from app import RelocatorApp


def main():
    paths = sys.argv[1:]
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon.fromTheme("equestria-os-relocator"))
    win = RelocatorApp(initial_sources=paths)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
