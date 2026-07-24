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
import shutil
import threading

from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QLabel,
                             QProgressBar, QPushButton, QTextEdit, QHBoxLayout)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal

APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
CONFIG_DIR = os.path.expanduser("~/.config/Equestria OS/Proton/")
SYSTEM_PATH = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
SHARED_BASE = os.path.join(APPS_DATA_DIR, "_shared")
SHARED_WINDOWS = os.path.join(SHARED_BASE, "windows")
SHARED_MARKER = os.path.join(SHARED_BASE, ".proton-shared")


def _prefix_windows_path(prefix_path):
    return os.path.join(prefix_path, "pfx", "drive_c", "windows")


def _migrate_windows_to_shared(prefix_path):
    """
    Move pfx/drive_c/windows/ from prefix to _shared/ and replace with a symlink.
    Uses os.rename (atomic, instant on same filesystem — no data is copied).
    Safe to call before umu-run starts (no open file handles yet).
    """
    windows_path = _prefix_windows_path(prefix_path)

    if os.path.islink(windows_path):
        if not os.path.exists(windows_path):
            os.remove(windows_path)
        return

    if not os.path.isdir(windows_path):
        return

    try:
        os.makedirs(SHARED_BASE, exist_ok=True)
        if not os.path.exists(SHARED_WINDOWS):
            shutil.move(windows_path, SHARED_WINDOWS)
            open(SHARED_MARKER, "w").close()
        else:
            shutil.rmtree(windows_path)
        os.symlink(SHARED_WINDOWS, windows_path)
    except Exception:
        pass


def _preseed_shared_windows(prefix_path):
    """
    For a brand-new prefix: pre-create windows/ as a symlink to _shared/ so that
    umu-run skips repopulating the DLLs and only sets up the registry (much faster).
    """
    if not os.path.exists(SHARED_MARKER):
        return
    windows_path = _prefix_windows_path(prefix_path)
    drive_c = os.path.dirname(windows_path)
    os.makedirs(drive_c, exist_ok=True)
    if not os.path.exists(windows_path):
        os.symlink(SHARED_WINDOWS, windows_path)

def apply_game_env(env, settings):
    """
    Per-game env from settings, shared by launcher.py and proton_runner.py.

    xbox_pad: Proton ведёт геймпад через SDL, и игра видит его как Xbox 360 —
    для игр, которые не распознают DualShock/DualSense. Имя ручки зависит от
    движка, поэтому ставим все: PROTON_PREFER_SDL понимает GE-Proton/CachyOS,
    а обычный Proton/UMU-Proton — пару PROTON_DISABLE_HIDRAW +
    PROTON_NO_STEAMINPUT (ровно её Valve включает своим конфигом "sdlinput").
    Нераспознанные переменные движок просто игнорирует.
    proton_version → PROTONPATH: "" = авто, "GE-Proton" = последний GE-Proton
    (umu обновляет), иначе абсолютный путь к закреплённой сборке. Если
    закреплённую сборку удалили — молча падаем в авто, чтобы игра всё равно
    запустилась.

    Важно: в режиме "авто" мы явно ищем уже установленную сборку (сначала
    UMU-Proton, иначе любую) и передаём её АБСОЛЮТНЫЙ ПУТЬ, а не оставляем
    PROTONPATH пустым/неустановленным. У umu-run пустой и отсутствующий
    PROTONPATH трактуются по-разному в зависимости от версии
    (см. umu-launcher#472): часть версий действительно скачивает
    UMU-Proton сама, но по крайней мере в одной наблюдавшейся версии (1.4.0)
    отсутствующий/пустой PROTONPATH сразу приводит к FileNotFoundError,
    даже если подходящая сборка уже стоит в compatibilitytools.d. Если
    ничего не установлено — PROTONPATH всё равно не ставим, чтобы дать
    umu-run шанс скачать что-то самому при наличии сети.
    """
    if settings.get("xbox_pad"):
        env["PROTON_PREFER_SDL"] = "1"
        env["PROTON_DISABLE_HIDRAW"] = "1"
        env["PROTON_NO_STEAMINPUT"] = "1"

    choice = settings.get("proton_version", "")
    if choice == "GE-Proton":
        env["PROTONPATH"] = "GE-Proton"
    elif choice and os.path.isdir(choice):
        env["PROTONPATH"] = choice
    else:
        from app_profiles import installed_protons, latest_proton
        auto_path = latest_proton("UMU-") or (installed_protons()[0][1] if installed_protons() else "")
        if auto_path:
            env["PROTONPATH"] = auto_path
        else:
            env.pop("PROTONPATH", None)
    return env

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

class _BootstrapThread(QThread):
    done = pyqtSignal()

    def __init__(self, prefix_path, profiles, env, log_path):
        super().__init__()
        self.prefix_path = prefix_path
        self.profiles = profiles
        self.env = env
        self.log_path = log_path
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        from app_profiles import ensure_dependencies
        open(self.log_path, "w", encoding="utf-8").close()  # truncate previous run's log
        for profile_id, profile in self.profiles:
            if self.cancel_event.is_set():
                break
            ensure_dependencies(self.prefix_path, profile_id, profile, self.env,
                                 log_path=self.log_path, cancel_event=self.cancel_event)
        self.done.emit()


class BootstrapWindow(QDialog):
    """Shown while one-time winetricks dependencies (.NET, fonts, ...) install,
    so the first launch doesn't look like it hung with no window at all.
    Every step has a hard timeout and there's a Skip button — this can never
    block the user forever, unlike the plain subprocess.run() used before."""

    def __init__(self, prefix_path, profiles, env, log_path):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(520, 320)
        self.setStyleSheet("""
            QDialog { background-color: rgb(24, 24, 37); border: 2px solid rgb(69, 71, 90); border-radius: 12px; }
            QLabel { color: rgb(205, 214, 244); font-family: 'Segoe UI', sans-serif; }
            QProgressBar { border: 1px solid rgb(69, 71, 90); border-radius: 6px; background: rgb(30, 30, 46); height: 12px; text-align: center; color: transparent; }
            QProgressBar::chunk { background-color: rgb(137, 180, 250); border-radius: 5px; }
            QTextEdit { background-color: rgb(17, 17, 27); color: rgb(166, 227, 161); border: 1px solid rgb(49, 50, 68); border-radius: 4px; font-family: monospace; font-size: 10px; }
            QPushButton { background-color: rgb(49, 50, 68); color: white; border: none; border-radius: 6px; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover { background-color: rgb(69, 71, 90); }
        """)
        self.log_path = log_path
        self._log_file = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)

        self.label = QLabel(t("launcher.bootstrap"))
        self.label.setWordWrap(True)
        self.label.setStyleSheet("font-size: 13px;")

        bar = QProgressBar()
        bar.setRange(0, 0)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)

        self.btn_skip = QPushButton(t("launcher.bootstrap_skip"))
        self.btn_skip.clicked.connect(self._on_skip)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.btn_skip)

        layout.addWidget(self.label)
        layout.addWidget(bar)
        layout.addWidget(self.log_view)
        layout.addLayout(btn_row)

        self.thread = _BootstrapThread(prefix_path, profiles, env, log_path)
        self.thread.done.connect(self._on_done)
        self.thread.start()

        self.log_timer = QTimer()
        self.log_timer.timeout.connect(self._tail_log)
        self.log_timer.start(400)

    def _tail_log(self):
        if self._log_file is None:
            try:
                self._log_file = open(self.log_path, "r", encoding="utf-8", errors="ignore")
            except OSError:
                return
        chunk = self._log_file.read()
        if chunk:
            self.log_view.insertPlainText(chunk)
            self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def _on_skip(self):
        self.label.setText(t("launcher.bootstrap_cancelling"))
        self.btn_skip.setEnabled(False)
        self.thread.cancel()

    def _on_done(self):
        self.log_timer.stop()
        if self._log_file:
            self._log_file.close()
        self.accept()


class SplashWindow(QDialog):
    def __init__(self, exe_name, log_path, cmd, env, cwd, debug=False):
        super().__init__()
        self.exe_name = exe_name
        self.log_path = log_path
        self.cmd = cmd
        self.env = env
        self.cwd = cwd
        self.debug = debug
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
        self.setFixedSize(500, 400)
        self.lbl_status.setText(f"Error: Process exited with code {code}")
        self.lbl_status.setStyleSheet("color: rgb(243, 139, 168); font-weight: bold;")
        self.progress.hide()

        self.log_file.seek(0)
        full_log = self.log_file.read()
        self.log_view.setText(self._build_log_text(full_log))
        self.log_view.show()
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

        self.btn_retry.show()
        self.btn_close.show()

    def _build_log_text(self, base_log: str) -> str:
        """Assemble display log: our captured output + proton log if present."""
        lines = [f"=== {self.log_path} ===", base_log.strip()]
        gameid = self.env.get("GAMEID", "")
        if gameid:
            proton_log = os.path.expanduser(f"~/proton_{gameid}.log")
            if os.path.exists(proton_log):
                try:
                    with open(proton_log, "r", encoding="utf-8", errors="ignore") as f:
                        lines += [f"\n=== {proton_log} ===", f.read().strip()]
                except Exception:
                    pass
        return "\n".join(lines)

    def _show_debug_exit_ui(self):
        """Called when game exits with code 0 in debug mode — show log instead of silently closing."""
        self.timer.stop()
        self.setFixedSize(500, 480)
        status = t("launcher.debug_exited")
        self.lbl_status.setText(f"{status}\n{self.log_path}")
        self.lbl_status.setStyleSheet("color: rgb(166, 227, 161); font-weight: bold; font-size: 10px;")
        self.progress.hide()

        self.log_file.seek(0)
        full_log = self.log_file.read()
        self.log_view.setText(self._build_log_text(full_log))
        self.log_view.show()
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

        self.btn_close.show()

    def check_status(self):
        # Проверка завершения процесса
        ret_code = self.proc.poll()
        if ret_code is not None:
            if ret_code == 0:
                if self.debug:
                    self._show_debug_exit_ui()
                else:
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
                    # В debug-режиме не закрываем окно досрочно — ждём реального выхода
                    if not self.debug:
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

    _migrate_windows_to_shared(prefix_path)

    if not os.path.exists(prefix_path):
        os.makedirs(prefix_path, exist_ok=True)
        _preseed_shared_windows(prefix_path)

    env = os.environ.copy()
    env["WINEPREFIX"] = prefix_path
    env["GAMEID"] = app_id

    if settings.get("dxvk_hud"): env["DXVK_HUD"] = "compiler,frametimes,fps"
    if settings.get("fsr"): env["WINE_FULLSCREEN_FSR"] = "1"
    apply_game_env(env, settings)

    from app_profiles import BASE_PROFILE, detect_profile, apply_profile_env, needs_bootstrap
    profiles_to_run = [("base", BASE_PROFILE)]
    profile_id, profile = detect_profile(exe_path)
    if profile:
        profiles_to_run.append((profile_id, profile))
        apply_profile_env(env, profile)

    if any(needs_bootstrap(prefix_path, pid, p, env) for pid, p in profiles_to_run):
        bootstrap_log = os.path.join(APPS_DATA_DIR, f"{app_id}-bootstrap.log")
        BootstrapWindow(prefix_path, profiles_to_run, env, bootstrap_log).exec()

    debug = settings.get("debug_log", False)
    if debug:
        env["DXVK_LOG_LEVEL"] = "info"
        env["VK_LOADER_DEBUG"] = "warn"
        env["WINEDEBUG"] = "err"
        env["PROTON_LOG"] = "1"

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
    splash = SplashWindow(exe_name, log_path, cmd, env, game_dir, debug=debug)
    splash.exec()

    # Post-launch migration: handles the case where umu-run just initialised a brand-new
    # prefix (windows/ didn't exist before launch, so pre-launch migration did nothing).
    # os.rename is atomic on Linux — safe even while the game process is still running.
    _migrate_windows_to_shared(prefix_path)

if __name__ == "__main__":
    main()
