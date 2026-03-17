"""
ImageFinish — A PyQt6 image editor inspired by Photoshop.

Usage:
    python main.py

Requirements:
    pip install PyQt6
"""

import sys
import os
import glob

# Make sure sibling packages are importable when running from any CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QFontDatabase
from ui.main_window import MainWindow

_APP_DIR   = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR  = os.path.join(_APP_DIR, "fonts")
BRUSHES_DIR = os.path.join(_APP_DIR, "brushes")
PATTERNS_DIR = os.path.join(_APP_DIR, "patterns")


def _load_custom_fonts():
    """Загружает все .ttf/.otf шрифты из папки fonts/."""
    os.makedirs(FONTS_DIR, exist_ok=True)
    os.makedirs(BRUSHES_DIR, exist_ok=True)
    os.makedirs(PATTERNS_DIR, exist_ok=True)
    patterns = ("**/*.ttf", "**/*.otf", "**/*.TTF", "**/*.OTF")
    loaded = 0
    for pat in patterns:
        for path in glob.glob(os.path.join(FONTS_DIR, pat), recursive=True):
            if QFontDatabase.addApplicationFont(path) != -1:
                loaded += 1
    if loaded:
        print(f"[fonts] Загружено кастомных шрифтов: {loaded}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ImageFinish")
    app.setApplicationVersion("1.1.0")
    icon_path = os.path.join(os.getcwd(), 'icon.png')
    app.setWindowIcon(QIcon(icon_path))

    _load_custom_fonts()

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
