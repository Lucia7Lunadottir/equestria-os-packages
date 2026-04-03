#!/usr/bin/env python3
"""
Equestria OS Proton Launcher
Entry point for double-clicking .exe files.
"""

import sys
import os
import csv
import json
import hashlib
import subprocess

from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QMessageBox
from PyQt6.QtCore import Qt, QTimer

APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
CONFIG_DIR = os.path.expanduser("~/.config/Equestria OS/Proton/")
SYSTEM_PATH = os.path.dirname(os.path.abspath(__file__))

# ── Localization ──────────────────────────────────────────────────────────────

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

def t(key: str, *args) -> str:
    text = _locales.get(key, {}).get(_lang) or _locales.get(key, {}).get("en") or key
    for i, val in enumerate(args):
        text = text.replace(f"{{{i}}}", str(val))
    return text

# ─────────────────────────────────────────────────────────────────────────────

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

        self.lbl_title = QLabel(t("launcher.title", exe_name))
        self.lbl_title.setStyleSheet("font-size: 15px; font-weight: bold;")

        self.lbl_status = QLabel(t("launcher.init"))
        self.lbl_status.setStyleSheet("color: rgb(180, 170, 210); font-size: 12px;")
        self.lbl_status.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setStyleSheet("""
            QProgressBar { border: 1px solid rgb(69, 71, 90); border-radius: 4px; background: rgb(30, 30, 45); height: 10px; }
            QProgressBar::chunk { background-color: rgb(127, 127, 255); border-radius: 3px; }
        """)

        self.btn_close = QPushButton(t("launcher.btn_close"))
        self.btn_close.setStyleSheet("""
            QPushButton { background-color: rgb(180, 60, 60); color: white; border: none;
                          border-radius: 4px; padding: 6px 18px; font-size: 12px; }
            QPushButton:hover { background-color: rgb(210, 80, 80); }
        """)
        self.btn_close.hide()
        self.btn_close.clicked.connect(self.accept)

        layout.addStretch()
        layout.addWidget(self.lbl_title)
        layout.addSpacing(5)
        layout.addWidget(self.lbl_status)
        layout.addSpacing(10)
        layout.addWidget(self.progress)
        layout.addSpacing(6)
        layout.addWidget(self.btn_close, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addStretch()

        try:
            self.log_file = open(self.log_path, "r", encoding="utf-8", errors="ignore")
        except Exception:
            self.log_file = None

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_log)
        self.timer.start(200)

        # Если игра запускается слишком долго, скрываем окно через 60 секунд
        QTimer.singleShot(60000, self.accept)

    def _show_crash(self, returncode):
        self.setFixedSize(450, 190)
        self.lbl_status.setStyleSheet("color: rgb(240, 100, 100); font-size: 12px;")
        self.lbl_status.setText(t("launcher.crash_text", returncode))
        self.progress.hide()
        self.btn_close.show()
        notify(t("launcher.notify_crash_title"), t("launcher.notify_crash_text", returncode))

    def check_log(self):
        if self.proc.poll() is not None:
            self.timer.stop()
            if self.proc.returncode != 0:
                self._show_crash(self.proc.returncode)
            else:
                self.accept()
            return

        if self.log_file:
            lines = self.log_file.readlines()
            for line in lines:
                line = line.lower()
                if "downloading" in line or "resuming" in line:
                    self.lbl_status.setText(t("launcher.downloading"))
                elif "verifying integrity" in line:
                    self.lbl_status.setText(t("launcher.verifying"))
                elif "upgrading prefix" in line or "setting up" in line:
                    self.lbl_status.setText(t("launcher.setup_prefix"))
                elif "running protonfixes" in line:
                    self.lbl_status.setText(t("launcher.protonfixes"))
                elif "fsync: up and running" in line or "wineserver: starting" in line:
                    self.timer.stop()
                    self.accept()

def main():
    _load_localization()
    _detect_language()

    if len(sys.argv) < 2:
        sys.exit(1)

    app = QApplication(sys.argv)
    exe_path = sys.argv[1]

    if not os.path.exists(exe_path):
        notify(t("proton.msg_error_title"), f"{exe_path}")
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

    log_path = os.path.join(APPS_DATA_DIR, f"{app_id}.log")
    log_out = open(log_path, "w", encoding="utf-8")

    try:
        proc = subprocess.Popen(cmd, env=env, cwd=game_dir, stdout=log_out, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        log_out.close()
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle(t("launcher.umu_missing_title"))
        msg.setText(t("launcher.umu_missing_text"))
        msg.exec()
        sys.exit(1)

    splash = SplashWindow(exe_name, log_path, proc)
    splash.exec()

if __name__ == "__main__":
    main()
