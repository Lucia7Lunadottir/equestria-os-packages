"""notes: app."""
from __future__ import annotations

import os
import sys
from PyQt6.QtWidgets import QApplication
from equestria_kit import themes as kit_themes
from equestria_kit.single_instance import SingleInstance
from .settings import load_config
from .style import apply_theme
from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Notes")
    app.setDesktopFileName("equestria-notes")
    app.setStyle("Fusion")
    # одно окно на пользователя: повторный запуск («Открыть с помощью» в KDE, меню)
    # отдаёт свои файлы уже открытому окну — у второй копии иначе свои настройки
    files = [os.path.abspath(p) for p in app.arguments()[1:]]
    instance = SingleInstance("equestria-notes")
    if not instance.claim():
        if instance.notify_running(args=files):
            return 0
    cfg = load_config()
    cfg["theme"] = apply_theme(kit_themes.current_name())
    win = MainWindow(cfg)
    kit_themes.follow(win._set_theme, lambda: win.theme)
    win.show()
    win.open_files(files)   # файлы из «Открыть с помощью» / командной строки
    instance.on_args(win.open_from_instance)
    return app.exec()
