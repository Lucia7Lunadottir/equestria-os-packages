"""gpu: app."""
from __future__ import annotations

import json
import sys
from PyQt6.QtWidgets import QApplication
from equestria_kit import themes as kit_themes
from .paths import CONFIG
from .style import DEFAULT_THEME, apply_theme
from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria GPU")
    app.setDesktopFileName("equestria-gpu")
    app.setStyle("Fusion")
    cfg = {"theme": DEFAULT_THEME}
    try:
        raw = json.loads(CONFIG.read_text(encoding="utf-8"))
        if isinstance(raw.get("theme"), str):
            cfg["theme"] = raw["theme"]
    except Exception:
        pass
    cfg["theme"] = apply_theme(kit_themes.current_name())
    win = MainWindow(cfg)
    kit_themes.follow(win._set_theme, lambda: win.theme)
    win.show()
    return app.exec()
