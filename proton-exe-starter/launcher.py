#!/usr/bin/env python3
"""
Equestria OS Proton Launcher (Enhanced)
"""

import sys
import os
import csv
import json
import hashlib
import subprocess
import re
import shlex

from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QLabel,
                             QProgressBar, QPushButton, QTextEdit, QHBoxLayout)
from PyQt6.QtCore import Qt, QTimer

APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
CONFIG_DIR = os.path.expanduser("~/.config/Equestria OS/Proton/")
SYSTEM_PATH = os.path.dirname(os.path.abspath(__file__))

_locales: dict = {}
_lang: str = "en"

def _load_localization():
    global _locales
    csv_path = os.path.join(SYSTEM_PATH, "localization.csv")
    if not os.path.exists(csv_path): return
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

def t(key: str, *args) -> str:
    text = _locales.get(key, {}).get(_lang) or _locales.get(key, {}).get("en") or key
    for i, val in enumerate(args):
        text = text.replace(f"{{{i}}}", str(val))
    return text

class SplashWindow(QDialog):
    def __init__(self, exe_name, log_path, cmd, env, cwd):
        super().__init__()
        self.exe_name = exe_name
        self.log_path = log_path
        self.cmd = cmd
        self.env = env
        self.cwd = cwd
        self.proc = None
        self.log_file = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(500, 180)
        self.setStyleSheet("""
            QDialog { background-color: rgb(24, 24, 37); border: 2px solid rgb(69, 71, 90); border-radius: 12px; }
            QLabel { color: rgb(205, 214, 244); font-family: 'Segoe UI', sans-serif; }
            QProgressBar { border: 1px solid rgb(69, 71, 90); border-radius: 6px; background: rgb(30, 30, 46); height: 12px; text-align: center; color: transparent; }
            QProgressBar::chunk { background-color: rgb(137, 180, 250); border-radius: 5px; }
            QTextEdit { background-color: rgb(17, 17, 27); color: rgb(243, 139, 168); border: 1px solid rgb(49, 50, 68); border-radius: 4px; font-family: monospace; font-size: 10px; }
            QPushButton { background-color: rgb(49, 50, 68); color: white; border: none; border-radius: 6px; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover { background-color: rgb(69, 71, 90); }
            QPushButton#btnRetry { background-color: rgb(166, 227, 161); color: rgb(17, 17, 27); }
            QPushButton#btnClose { background-color: rgb(243, 139, 168); color: rgb(17, 17, 27); }
        """)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(25, 25, 25, 25)

        self.lbl_title = QLabel(t("launcher.title", exe_name))
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: rgb(137, 180, 250);")

        self.lbl_status = QLabel(t("launcher.init"))
        self.lbl_status.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        # Скрытая панель логов
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.hide()

        # Кнопки
        self.btn_layout = QHBoxLayout()
        self.btn_retry = QPushButton(t("launcher.retry"))
        self.btn_retry.setObjectName("btnRetry")
        self.btn_retry.hide()
        self.btn_retry.clicked.connect(self.start_process)

        self.btn_close = QPushButton(t("launcher.btn_close"))
        self.btn_close.setObjectName("btnClose")
        self.btn_close.hide()
        self.btn_close.clicked.connect(self.reject)

        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.btn_retry)
        self.btn_layout.addWidget(self.btn_close)

        self.layout.addWidget(self.lbl_title)
        self.layout.addWidget(self.lbl_status)
        self.layout.addWidget(self.progress)
        self.layout.addWidget(self.log_view)
        self.layout.addLayout(self.btn_layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_status)

        self.start_process()

    def start_process(self):
        # Очистка старого процесса если есть
        if self.proc:
            self.proc.terminate()

        self.setFixedSize(500, 180)
        self.log_view.hide()
        self.btn_retry.hide()
        self.btn_close.hide()
        self.progress.show()
        self.progress.setValue(0)
        self.lbl_status.setText(t("launcher.init"))
        self.lbl_status.setStyleSheet("color: rgb(205, 214, 244);")

        # Открываем лог на запись (очищаем старый)
        log_out = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(self.cmd, env=self.env, cwd=self.cwd, stdout=log_out, stderr=subprocess.STDOUT)

        # Открываем лог на чтение
        if self.log_file: self.log_file.close()
        self.log_file = open(self.log_path, "r", encoding="utf-8", errors="ignore")

        self.timer.start(200)

    def _show_error_ui(self, code):
        self.timer.stop()
        self.setFixedSize(500, 400) # Увеличиваем окно
        self.lbl_status.setText(f"Error: Process exited with code {code}")
        self.lbl_status.setStyleSheet("color: rgb(243, 139, 168); font-weight: bold;")
        self.progress.hide()

        # Показываем лог
        self.log_file.seek(0)
        full_log = self.log_file.read()
        self.log_view.setText(full_log)
        self.log_view.show()
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

        self.btn_retry.show()
        self.btn_close.show()

    def check_status(self):
        # Проверка завершения процесса
        ret_code = self.proc.poll()
        if ret_code is not None:
            if ret_code == 0:
                self.accept()
            else:
                self._show_error_ui(ret_code)
            return

        # Чтение логов и поиск прогресса
        if self.log_file:
            lines = self.log_file.readlines()
            for line in lines:
                l_lower = line.lower()

                # Ищем проценты: [ 15%] или 15%
                match = re.search(r"(\d+)%", line)
                if match:
                    percent = int(match.group(1))
                    self.progress.setValue(percent)

                # Статусы
                if "downloading" in l_lower:
                    self.lbl_status.setText(t("launcher.downloading"))
                elif "verifying" in l_lower:
                    self.lbl_status.setText(t("launcher.verifying"))
                elif "setting up" in l_lower or "prefix" in l_lower:
                    self.lbl_status.setText(t("launcher.setup_prefix"))
                elif "fsync: up and running" in l_lower or "wineserver: starting" in l_lower:
                    self.timer.stop()
                    self.accept()

def main():
    _load_localization()
    _detect_language()

    if len(sys.argv) < 2: sys.exit(1)

    app = QApplication(sys.argv)
    exe_path = sys.argv[1]

    if not os.path.exists(exe_path):
        sys.exit(1)

    exe_name = os.path.basename(exe_path)
    path_hash = hashlib.md5(exe_path.encode('utf-8')).hexdigest()[:8]
    app_id = f"{exe_name}_{path_hash}"
    prefix_path = os.path.join(APPS_DATA_DIR, app_id)
    config_file = os.path.join(CONFIG_DIR, f"{app_id}.json")

    settings = {}
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            settings = json.load(f)

    os.makedirs(prefix_path, exist_ok=True)
    env = os.environ.copy()
    env["WINEPREFIX"] = prefix_path
    env["GAMEID"] = app_id

    if settings.get("dxvk_hud"): env["DXVK_HUD"] = "compiler,frametimes,fps"
    if settings.get("fsr"): env["WINE_FULLSCREEN_FSR"] = "1"

    extra_args = shlex.split(settings.get("launch_args", "").strip())
    game_dir = os.path.dirname(exe_path)

    if settings.get("virtual_desktop"):
        screen = app.primaryScreen().size()
        res = f"{screen.width()}x{screen.height()}"
        cmd = ["umu-run", "explorer.exe", f"/desktop=EquestriaOS,{res}", exe_path] + extra_args
    else:
        cmd = ["umu-run", exe_path] + extra_args

    log_path = os.path.join(APPS_DATA_DIR, f"{app_id}.log")

    # Запускаем SplashWindow
    splash = SplashWindow(exe_name, log_path, cmd, env, game_dir)
    splash.exec()

if __name__ == "__main__":
    main()
