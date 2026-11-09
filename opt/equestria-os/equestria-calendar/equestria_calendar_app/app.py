"""calendar: app."""
from __future__ import annotations

import sys
from PyQt6.QtWidgets import QApplication
from equestria_kit import themes as kit_themes
from equestria_kit.single_instance import SingleInstance
from .storage import Store
from .style import apply_theme
from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Calendar")
    app.setDesktopFileName("equestria-calendar")
    app.setStyle("Fusion")
    instance = SingleInstance("equestria-calendar")
    if not instance.claim():   # уже запущен (в трее) — показываем его окно
        instance.notify_running(show="--hidden" not in sys.argv)
        return 0
    st = Store()
    st.settings["theme"] = apply_theme(kit_themes.current_name())
    win = MainWindow(st)
    kit_themes.follow(win._set_theme, lambda: win.theme)
    instance.on_show(win.show_window)
    app.setQuitOnLastWindowClosed(win.tray is None)
    if not ("--hidden" in sys.argv and win.tray):
        win.show()
    code = app.exec()
    instance.release()
    return code
