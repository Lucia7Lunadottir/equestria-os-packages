"""Запуск диктофона."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from equestria_kit import themes as kit_themes

from .paths import CONFIG
from .settings import SettingsStore
from .style import apply_theme
from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Recorder")
    app.setStyle("Fusion")
    settings = SettingsStore(CONFIG)
    theme = apply_theme(kit_themes.current_name())
    win = MainWindow(settings.load(), theme, settings)
    kit_themes.follow(win._set_theme, lambda: win.theme)
    win.show()
    return app.exec()
