from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from equestria_ue.kit import kit_qt  # noqa: F401 — подключает equestria_kit (и при запуске из исходников)
from equestria_kit.single_instance import SingleInstance
from equestria_ue.theme import install_theme
from equestria_ue.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Unreal Launcher")
    app.setDesktopFileName("equestria-unreal")
    # одна копия: повторный запуск (лаунчер свёрнут в трей) показывает уже открытое окно
    instance = SingleInstance("equestria-unreal")
    if not instance.claim():
        instance.notify_running()
        return
    app.setQuitOnLastWindowClosed(False)   # окно может прятаться в трей; выход — MainWindow.quit_app
    install_theme(app)
    win = MainWindow()
    instance.on_show(win.show_window)
    win.show()
    code = app.exec()
    instance.release()
    sys.exit(code)


if __name__ == "__main__":
    main()
