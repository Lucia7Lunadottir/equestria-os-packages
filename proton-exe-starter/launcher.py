#!/usr/bin/env python3
"""
Equestria OS Proton Launcher
Entry point for double-clicking .exe files.
"""

import sys
import os
import json
import hashlib
import subprocess

from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt, QTimer

APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
CONFIG_DIR = os.path.expanduser("~/.config/Equestria OS/Proton/")

def notify(title, text):
    try:
        subprocess.Popen([
            "notify-send",
            "--app-name=Equestria OS",
            "--icon=wine",
            title, text
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass

class SplashWindow(QDialog):
    def __init__(self, exe_name, log_path, proc):
        super().__init__()
        # Делаем окно без рамок, поверх остальных окон
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(450, 160)
        self.setStyleSheet("""
            QDialog { background-color: rgb(18, 18, 28); border: 2px solid rgb(69, 71, 90); border-radius: 8px; }
            QLabel { color: white; font-family: sans-serif; }
        """)

        self.log_path = log_path
        self.proc = proc

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        self.lbl_title = QLabel(f"Запуск: {exe_name}")
        self.lbl_title.setStyleSheet("font-size: 15px; font-weight: bold;")

        self.lbl_status = QLabel("Инициализация UMU-Proton...")
        self.lbl_status.setStyleSheet("color: rgb(180, 170, 210); font-size: 12px;")
        self.lbl_status.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Бесконечный ползунок загрузки
        self.progress.setStyleSheet("""
            QProgressBar { border: 1px solid rgb(69, 71, 90); border-radius: 4px; background: rgb(30, 30, 45); height: 10px; }
            QProgressBar::chunk { background-color: rgb(127, 127, 255); border-radius: 3px; }
        """)

        layout.addStretch()
        layout.addWidget(self.lbl_title)
        layout.addSpacing(5)
        layout.addWidget(self.lbl_status)
        layout.addSpacing(10)
        layout.addWidget(self.progress)
        layout.addStretch()

        # Открываем лог-файл для чтения на лету
        try:
            self.log_file = open(self.log_path, "r", encoding="utf-8", errors="ignore")
        except Exception:
            self.log_file = None

        # Таймер проверяет логи каждые 200 мс
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_log)
        self.timer.start(200)

        # Если игра запускается слишком долго (например, зависла), скрываем окно через 60 секунд
        QTimer.singleShot(60000, self.accept)

    def check_log(self):
        # Если процесс умер
        if self.proc.poll() is not None:
            self.timer.stop()
            self.accept()
            if self.proc.returncode != 0:
                notify("Ошибка запуска", f"Программа завершилась с кодом {self.proc.returncode}.\nПроверьте настройки или очистите кэш.")
            return

        # Читаем новые строки лога
        if self.log_file:
            lines = self.log_file.readlines()
            for line in lines:
                line = line.lower()
                if "downloading" in line or "resuming" in line:
                    self.lbl_status.setText("Скачивание библиотек (только при первом запуске)...")
                elif "verifying integrity" in line:
                    self.lbl_status.setText("Проверка файлов среды...")
                elif "upgrading prefix" in line or "setting up" in line:
                    self.lbl_status.setText("Настройка префикса Windows...")
                elif "running protonfixes" in line:
                    self.lbl_status.setText("Применение патчей совместимости...")
                elif "fsync: up and running" in line or "wineserver: starting" in line:
                    self.timer.stop()
                    self.accept() # Игра запустилась! Закрываем загрузочный экран

def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    app = QApplication(sys.argv)
    exe_path = sys.argv[1]

    if not os.path.exists(exe_path):
        notify("Ошибка", f"Файл не найден:\n{exe_path}")
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

    # ── Среда запуска ──
    env = os.environ.copy()
    env["WINEPREFIX"] = prefix_path
    env["GAMEID"] = app_id

    if settings.get("dxvk_hud"):
        env["DXVK_HUD"] = "compiler,frametimes,fps"
    if settings.get("fsr"):
        env["WINE_FULLSCREEN_FSR"] = "1"

    import shlex
    extra_args = shlex.split(settings.get("launch_args", "").strip())
    game_dir = os.path.dirname(exe_path)

    if settings.get("virtual_desktop"):
        screen = app.primaryScreen().size()
        res = f"{screen.width()}x{screen.height()}"
        cmd = ["umu-run", "explorer.exe", f"/desktop=EquestriaOS,{res}", exe_path] + extra_args
    else:
        cmd = ["umu-run", exe_path] + extra_args

    # ── Пишем логи в файл, чтобы читать их в Splash экране ──
    log_path = os.path.join(APPS_DATA_DIR, f"{app_id}.log")
    log_out = open(log_path, "w", encoding="utf-8")

    proc = subprocess.Popen(cmd, env=env, cwd=game_dir, stdout=log_out, stderr=subprocess.STDOUT)

    # Запускаем красивый экран загрузки
    splash = SplashWindow(exe_name, log_path, proc)
    splash.exec()

if __name__ == "__main__":
    main()
