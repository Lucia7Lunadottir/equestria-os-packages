import os
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from app import SettingsWindow

BASE_PATH = os.path.dirname(os.path.abspath(__file__))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("equestria-os-settings")

    icon_path = os.path.join(BASE_PATH, "equestria-os-settings.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = SettingsWindow(BASE_PATH)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
