"""notes: app."""
from __future__ import annotations

import sys
from PyQt6.QtWidgets import QApplication
from equestria_kit import themes as kit_themes
from .settings import load_config
from .style import apply_theme
from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Notes")
    app.setDesktopFileName("equestria-notes")
    app.setStyle("Fusion")
    cfg = load_config()
    cfg["theme"] = apply_theme(kit_themes.current_name())
    win = MainWindow(cfg)
    kit_themes.follow(win._set_theme, lambda: win.theme)
    win.show()
    return app.exec()
