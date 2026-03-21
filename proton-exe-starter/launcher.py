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
import threading

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon

APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
CONFIG_DIR = os.path.expanduser("~/.config/Equestria OS/Proton/")
SYSTEM_PATH = os.path.dirname(os.path.abspath(__file__))


# ─── Proton detection ────────────────────────────────────────────────────────

def find_proton():
    """Return path to the proton binary, or None if not found."""
    import glob

    candidates = [
        # Our managed GE-Proton
        os.path.expanduser("~/.local/share/Equestria OS/Proton/latest/proton"),
        # Steam compatibility tools (user-installed GE-Proton)
        *sorted(glob.glob(
            os.path.expanduser("~/.local/share/Steam/compatibilitytools.d/*/proton")
        )),
        # System-wide Steam
        *sorted(glob.glob(
            "/usr/share/steam/compatibilitytools.d/*/proton"
        )),
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


# ─── Background install thread ───────────────────────────────────────────────

class ProtonInstallThread(QThread):
    progress = pyqtSignal(str, int)   # (status_message, 0‒100)
    finished = pyqtSignal(bool, str)  # (success, error_msg)

    def run(self):
        try:
            sys.path.insert(0, SYSTEM_PATH)
            from proton_updater import get_latest_release_info, download_and_install_with_progress

            self.progress.emit("Checking latest Proton version…", 5)
            version, url = get_latest_release_info()
            if not version or not url:
                self.finished.emit(False, "Could not retrieve download URL.")
                return

            self.progress.emit(f"Downloading Proton {version}…", 10)
            download_and_install_with_progress(version, url, self.progress)
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))


# ─── Install dialog ──────────────────────────────────────────────────────────

class InstallProtonDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Equestria OS — Proton Engine")
        self.setModal(True)
        self.setFixedWidth(420)
        self._installed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)

        lbl_title = QLabel("Proton engine not found")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(lbl_title)

        lbl_text = QLabel(
            "To run Windows applications Equestria OS needs the "
            "Proton compatibility layer (~500 MB).\n\n"
            "Install it now?"
        )
        lbl_text.setWordWrap(True)
        layout.addWidget(lbl_text)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 11px; color: rgb(140, 130, 160);")
        self.lbl_status.setVisible(False)
        layout.addWidget(self.lbl_status)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_install = QPushButton("Install Proton")
        self.btn_install.setObjectName("btnSave")
        self.btn_install.setDefault(True)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_install)
        layout.addLayout(btn_row)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_install.clicked.connect(self._start_install)

    def _start_install(self):
        self.btn_install.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_status.setVisible(True)

        self._thread = ProtonInstallThread()
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, msg, pct):
        self.lbl_status.setText(msg)
        self.progress_bar.setValue(pct)

    def _on_finished(self, success, error):
        if success:
            self._installed = True
            self.accept()
        else:
            QMessageBox.critical(self, "Installation failed", f"Could not install Proton:\n{error}")
            self.btn_cancel.setEnabled(True)
            self.btn_install.setEnabled(True)

    def was_installed(self):
        return self._installed


# ─── Helpers ─────────────────────────────────────────────────────────────────

def notify(title, body):
    """Non-blocking KDE / freedesktop desktop notification."""
    try:
        subprocess.Popen(
            ["notify-send", "--app-name=Equestria OS", "--icon=wine", title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        pass


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: launcher.py <path_to_exe>")
        sys.exit(1)

    exe_path = os.path.abspath(sys.argv[1])

    app = QApplication(sys.argv)

    icon_path = "/usr/share/pixmaps/equestria-os-logo.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    qss_path = os.path.join(SYSTEM_PATH, "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    if not os.path.exists(exe_path):
        QMessageBox.critical(None, "File not found", f"File not found:\n{exe_path}")
        sys.exit(1)

    # ── Ensure Proton is available ──────────────────────────────────────────
    proton_bin = find_proton()
    if not proton_bin:
        dlg = InstallProtonDialog()
        dlg.exec()
        if not dlg.was_installed():
            sys.exit(0)
        proton_bin = find_proton()
        if not proton_bin:
            QMessageBox.critical(None, "Error", "Proton not found after installation.")
            sys.exit(1)

    # ── App identity & prefix ───────────────────────────────────────────────
    exe_name = os.path.basename(exe_path)
    path_hash = hashlib.md5(exe_path.encode("utf-8")).hexdigest()[:8]
    app_id = f"{exe_name}_{path_hash}"
    prefix_path = os.path.join(APPS_DATA_DIR, app_id)
    config_file = os.path.join(CONFIG_DIR, f"{app_id}.json")

    is_first_run = not os.path.exists(prefix_path)
    if is_first_run:
        notify(
            "Building Wine environment",
            f"First launch of {exe_name}.\n"
            "The compatibility layer is being prepared — this may take a moment."
        )

    # ── Load per-app settings ───────────────────────────────────────────────
    settings = {}
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            settings = json.load(f)

    os.makedirs(prefix_path, exist_ok=True)

    # ── Environment ─────────────────────────────────────────────────────────
    env = os.environ.copy()
    env["STEAM_COMPAT_DATA_PATH"] = prefix_path
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = os.path.expanduser("~/.local/share/Steam")

    # Prevent Wine from creating Windows-style shortcuts in KDE menus/desktop
    env["WINEDLLOVERRIDES"] = "winemenubuilder.exe=b"

    if settings.get("dxvk_hud"):
        env["DXVK_HUD"] = "fps,devinfo"

    # ── Build launch command ────────────────────────────────────────────────
    import shlex
    extra_args = shlex.split(settings.get("launch_args", "").strip())

    if settings.get("virtual_desktop"):
        # Run inside a Wine virtual desktop window.
        # Resolution matches the primary screen.
        screen = app.primaryScreen().size()
        res = f"{screen.width()}x{screen.height()}"
        cmd = [proton_bin, "run", "explorer.exe",
               f"/desktop=EquestriaOS,{res}", exe_path] + extra_args
    else:
        cmd = [proton_bin, "run", exe_path] + extra_args

    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Background update check (at most once per week)
    subprocess.Popen(
        [sys.executable, os.path.join(SYSTEM_PATH, "proton_updater.py"), "--check"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # Monitor for early crash: if Proton exits within 8 s with non-zero code → notify
    def _monitor_startup():
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            return  # still running after 8 s — normal
        if proc.returncode != 0:
            notify(
                exe_name,
                f"Failed to start (code {proc.returncode}).\n"
                "Try clearing the cache in Proton Settings."
            )

    # daemon=False keeps the process alive until the thread finishes (max 8 s)
    threading.Thread(target=_monitor_startup, daemon=False).start()


if __name__ == "__main__":
    main()
