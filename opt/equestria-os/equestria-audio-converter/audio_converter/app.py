"""Запуск программы. Файлы из командной строки (или «Открыть с помощью…») сразу попадают в список."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from ._kit import kit_themes
from .file_list import to_local_path
from .style import apply_theme
from .window import MainWindow, load_config


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("Equestria Converter")
    app.setStyle("Fusion")
    win = MainWindow(load_config(), apply_theme(kit_themes.current_name()))
    win.add_files([to_local_path(a) for a in argv[1:] if not a.startswith("-")])
    win.show()
    kit_themes.follow(win._set_theme, lambda: win.theme)
    return app.exec()
