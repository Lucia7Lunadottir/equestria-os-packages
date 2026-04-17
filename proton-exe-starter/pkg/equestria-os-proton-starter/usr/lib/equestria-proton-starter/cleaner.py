#!/usr/bin/env python3
"""
Equestria OS Proton Cache Cleaner
"""

import sys
import os
import csv
import shutil

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QGroupBox, QMessageBox,
    QSizePolicy)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
CONFIG_DIR = os.path.expanduser("~/.config/Equestria OS/Proton/")
SYSTEM_PATH = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

MESA_CACHE_DIRS = [
    os.path.expanduser("~/.cache/mesa_shader_cache"),
    os.path.expanduser("~/.cache/mesa"),
    os.path.expanduser("~/.cache/radeonsi"),
    os.path.expanduser("~/.cache/AMD"),
]

_locales: dict = {}
_lang: str = "en"


def _load_localization():
    global _locales
    csv_path = os.path.join(SYSTEM_PATH, "localization.csv")
    if not os.path.exists(csv_path):
        return
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row["key"]
            _locales[key] = {lang: text for lang, text in row.items() if lang != "key"}


def _detect_language():
    global _lang
    lang = os.environ.get("LANG", "en")
    for code in ("ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"):
        if lang.startswith(code):
            _lang = code
            return
    _lang = "en"


def t(key: str) -> str:
    return _locales.get(key, {}).get(_lang) or _locales.get(key, {}).get("en") or key


def get_dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def find_shader_files(prefix_path: str) -> list:
    """Find shader/pipeline cache files and dirs within a Proton prefix."""
    found = []

    # DXVK state cache and VKD3D-Proton pipeline cache
    for root, _, files in os.walk(prefix_path):
        for f in files:
            if f.endswith(".dxvk-cache") or f.endswith(".vkd3d-cache"):
                found.append(os.path.join(root, f))

    # DirectX / D3D shader cache inside the Wine prefix
    username = os.environ.get("USER", "steamuser")
    d3d_cache_paths = [
        os.path.join(prefix_path, "pfx", "drive_c", "users", username,
                     "AppData", "Local", "D3DSCache"),
        os.path.join(prefix_path, "pfx", "drive_c", "users", username,
                     "Local Settings", "Application Data", "dxvk"),
    ]
    for p in d3d_cache_paths:
        if os.path.isdir(p):
            found.append(p)

    return found


class AppCard(QWidget):
    def __init__(self, app_id: str, prefix_path: str, on_removed):
        super().__init__()
        self.app_id = app_id
        self.prefix_path = prefix_path
        self._on_removed = on_removed

        # Readable name: strip the trailing _hash8 part
        parts = app_id.rsplit("_", 1)
        self.display_name = parts[0] if len(parts) == 2 and len(parts[1]) == 8 else app_id

        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        info = QVBoxLayout()
        self.lbl_name = QLabel(self.display_name)
        self.lbl_name.setStyleSheet("font-weight: bold; font-size: 13px;")

        size = get_dir_size(self.prefix_path) if os.path.isdir(self.prefix_path) else 0
        self.lbl_size = QLabel(f"{t('cleaner.size')}: {format_size(size)}")
        self.lbl_size.setStyleSheet("color: rgb(150, 140, 180); font-size: 11px;")

        info.addWidget(self.lbl_name)
        info.addWidget(self.lbl_size)
        layout.addLayout(info)
        layout.addStretch()

        self.btn_shaders = QPushButton(t("cleaner.btn_clear_shaders"))
        self.btn_shaders.setMinimumWidth(130)
        self.btn_shaders.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.btn_shaders.clicked.connect(self._clear_shaders)

        self.btn_prefix = QPushButton(t("cleaner.btn_clear_prefix"))
        self.btn_prefix.setObjectName("btnDanger")
        self.btn_prefix.setMinimumWidth(130)
        self.btn_prefix.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.btn_prefix.clicked.connect(self._clear_prefix)

        layout.addWidget(self.btn_shaders)
        layout.addWidget(self.btn_prefix)

    def _refresh_size(self):
        size = get_dir_size(self.prefix_path) if os.path.isdir(self.prefix_path) else 0
        self.lbl_size.setText(f"{t('cleaner.size')}: {format_size(size)}")

    def _clear_shaders(self):
        shaders = find_shader_files(self.prefix_path)
        if not shaders:
            QMessageBox.information(self, t("cleaner.msg_info_title"), t("cleaner.shaders_not_found"))
            return

        shader_size = sum(
            get_dir_size(s) if os.path.isdir(s) else os.path.getsize(s)
            for s in shaders
        )
        msg = t("cleaner.msg_confirm_shaders") \
            .replace("{0}", self.display_name) \
            .replace("{1}", format_size(shader_size))

        reply = QMessageBox.question(
            self, t("cleaner.msg_confirm_title"), msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            for s in shaders:
                if os.path.isdir(s):
                    shutil.rmtree(s)
                else:
                    os.remove(s)
            self._refresh_size()
            QMessageBox.information(self, t("cleaner.msg_success_title"), t("cleaner.shaders_cleared"))
        except Exception as e:
            QMessageBox.critical(self, t("cleaner.msg_error_title"), str(e))

    def _clear_prefix(self):
        if not os.path.isdir(self.prefix_path):
            QMessageBox.information(self, t("cleaner.msg_info_title"), t("cleaner.prefix_not_found"))
            return

        msg = t("cleaner.msg_confirm_prefix").replace("{0}", self.display_name)
        reply = QMessageBox.question(
            self, t("cleaner.msg_confirm_title"), msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            shutil.rmtree(self.prefix_path)
            QMessageBox.information(self, t("cleaner.msg_success_title"), t("cleaner.prefix_cleared"))
            self._on_removed(self)
        except Exception as e:
            QMessageBox.critical(self, t("cleaner.msg_error_title"), str(e))


class CleanerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("cleaner.title"))
        self.setMinimumSize(640, 520)
        self._app_cards: list[AppCard] = []
        self._build_ui()
        self._load_apps()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Header
        header = QHBoxLayout()
        lbl_title = QLabel(t("cleaner.title"))
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: rgb(137, 180, 250);")
        header.addWidget(lbl_title)
        header.addStretch()
        btn_refresh = QPushButton(t("cleaner.btn_refresh"))
        btn_refresh.clicked.connect(self._load_apps)
        header.addWidget(btn_refresh)
        root.addLayout(header)

        # Apps list
        self.group_apps = QGroupBox(t("cleaner.group_apps"))
        apps_layout = QVBoxLayout(self.group_apps)
        apps_layout.setContentsMargins(0, 4, 0, 4)
        apps_layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setSpacing(0)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.addStretch()

        self.scroll.setWidget(self.scroll_widget)
        apps_layout.addWidget(self.scroll)
        root.addWidget(self.group_apps, 1)

        # Global cache section
        self.group_global = QGroupBox(t("cleaner.group_global"))
        global_layout = QVBoxLayout(self.group_global)

        mesa_row = QHBoxLayout()
        self.lbl_mesa = QLabel()
        mesa_row.addWidget(self.lbl_mesa)
        mesa_row.addStretch()
        self.btn_mesa = QPushButton(t("cleaner.btn_clear_mesa"))
        self.btn_mesa.clicked.connect(self._clear_mesa)
        mesa_row.addWidget(self.btn_mesa)
        global_layout.addLayout(mesa_row)

        root.addWidget(self.group_global)

        # Bottom
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton(t("cleaner.btn_close"))
        btn_close.clicked.connect(self.close)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    def _clear_scroll(self):
        # Remove all widgets except the trailing stretch
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._app_cards.clear()

    def _load_apps(self):
        self._clear_scroll()
        self._refresh_mesa_label()

        if not os.path.isdir(APPS_DATA_DIR):
            self._show_empty()
            return

        entries = sorted(
            e for e in os.listdir(APPS_DATA_DIR)
            if os.path.isdir(os.path.join(APPS_DATA_DIR, e))
        )

        if not entries:
            self._show_empty()
            return

        for i, app_id in enumerate(entries):
            prefix_path = os.path.join(APPS_DATA_DIR, app_id)
            card = AppCard(app_id, prefix_path, self._remove_card)
            if i % 2 == 1:
                card.setObjectName("appCardAlt")
                card.setStyleSheet("#appCardAlt { background-color: rgba(255,255,255,0.03); }")
            self.scroll_layout.insertWidget(i, card)
            self._app_cards.append(card)

    def _remove_card(self, card: "AppCard"):
        self._app_cards.remove(card)
        self.scroll_layout.removeWidget(card)
        card.deleteLater()
        if not self._app_cards:
            self._show_empty()

    def _show_empty(self):
        lbl = QLabel(t("cleaner.no_apps"))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: rgb(150, 140, 180); padding: 30px;")
        self.scroll_layout.insertWidget(0, lbl)

    def _refresh_mesa_label(self):
        total = sum(
            get_dir_size(d) for d in MESA_CACHE_DIRS if os.path.isdir(d)
        )
        size_str = format_size(total) if total > 0 else "—"
        self.lbl_mesa.setText(f"{t('cleaner.lbl_mesa')} ({size_str})")

    def _clear_mesa(self):
        dirs_exist = [d for d in MESA_CACHE_DIRS if os.path.isdir(d)]
        if not dirs_exist:
            QMessageBox.information(self, t("cleaner.msg_info_title"), t("cleaner.mesa_not_found"))
            return

        reply = QMessageBox.question(
            self, t("cleaner.msg_confirm_title"), t("cleaner.msg_confirm_mesa"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            for d in dirs_exist:
                shutil.rmtree(d)
            self._refresh_mesa_label()
            QMessageBox.information(self, t("cleaner.msg_success_title"), t("cleaner.mesa_cleared"))
        except Exception as e:
            QMessageBox.critical(self, t("cleaner.msg_error_title"), str(e))


if __name__ == "__main__":
    _load_localization()
    _detect_language()

    app = QApplication(sys.argv)

    icon_path = "/usr/share/pixmaps/equestria-os-proton-starter.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        app.setWindowIcon(QIcon.fromTheme("user-trash"))

    qss_path = os.path.join(SYSTEM_PATH, "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r") as f:
            app.setStyleSheet(f.read())

    window = CleanerWindow()
    window.show()
    sys.exit(app.exec())
