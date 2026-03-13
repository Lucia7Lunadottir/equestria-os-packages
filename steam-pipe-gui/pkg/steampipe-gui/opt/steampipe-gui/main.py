import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Сначала настраиваем всё визуальное (иконки, темы)
    icon_path = "steampipe-gui-logo.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        app.setWindowIcon(QIcon.fromTheme("preferences-desktop-theme"))

    # Потом создаем и показываем окно
    window = MainWindow()
    window.show()

    # И только в самом-самом конце запускаем бесконечный цикл приложения!
    sys.exit(app.exec())
