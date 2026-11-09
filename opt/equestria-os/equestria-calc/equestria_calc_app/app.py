"""calc: app."""
from __future__ import annotations

import json
import sys
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from equestria_kit import themes as kit_themes
from .paths import CONFIG
from .style import DEFAULT_THEME, apply_theme
from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Calc")
    # Без этого окно на Wayland получает имя интерпретатора (python3), и панель задач
    # показывает его как чужое приложение без нашего ярлыка и значка
    app.setDesktopFileName("equestria-calc")
    app.setWindowIcon(QIcon.fromTheme("equestria-calc", QIcon.fromTheme("accessories-calculator")))
    app.setStyle("Fusion")
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        theme, mode = str(cfg.get("theme", DEFAULT_THEME)), int(cfg.get("mode", 0))
    except Exception:
        theme, mode = DEFAULT_THEME, 0
    theme = apply_theme(kit_themes.current_name())
    win = MainWindow(theme, mode)
    win.show()
    kit_themes.follow(win._set_theme, lambda: win.theme)
    return app.exec()
