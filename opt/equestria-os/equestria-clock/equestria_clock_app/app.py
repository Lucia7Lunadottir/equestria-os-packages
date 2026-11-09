"""clock: app."""
from __future__ import annotations

import sys
from PyQt6.QtWidgets import QApplication
from equestria_kit import themes as kit_themes
from equestria_kit.single_instance import SingleInstance
from .paths import APP_NAME, CACHE_DIR
from .settings import Settings
from .style import apply_theme, load_all_themes
from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Clock")
    app.setDesktopFileName("equestria-clock")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    instance = SingleInstance(APP_NAME)
    if not instance.claim():   # уже запущен (в трее) — показываем его окно
        instance.notify_running(show="--hidden" not in sys.argv)
        return 0

    settings = Settings()
    load_all_themes()
    settings["theme"] = apply_theme(kit_themes.current_name())
    win = MainWindow(settings)
    kit_themes.follow(win.set_theme, lambda: win.settings["theme"])
    instance.on_show(win.show_window)
    if not ("--hidden" in sys.argv and win.tray is not None and win.settings["tray"]):
        win.show()
    code = app.exec()
    instance.release()
    return code
