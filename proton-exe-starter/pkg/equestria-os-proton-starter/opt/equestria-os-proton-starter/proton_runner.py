"""
Equestria OS Proton Runner
"""

import sys
import os
import json
import hashlib
import subprocess
import shlex

from PyQt6.QtWidgets import QApplication, QMessageBox

APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
CONFIG_DIR = os.path.expanduser("~/.config/Equestria OS/Proton/")

def show_error(title, text):
    app = QApplication.instance() or QApplication(sys.argv)
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.exec()
    sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("Usage: proton_runner.py <path_to_exe>")
        sys.exit(1)

    app = QApplication.instance() or QApplication(sys.argv)
    exe_path = sys.argv[1]

    if not os.path.exists(exe_path):
        show_error("Error", f"File not found:\n{exe_path}")

    exe_name = os.path.basename(exe_path)
    path_hash = hashlib.md5(exe_path.encode("utf-8")).hexdigest()[:8]
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

    extra_args = shlex.split(settings.get("launch_args", "").strip())
    game_dir = os.path.dirname(exe_path)

    if settings.get("virtual_desktop"):
        screen = app.primaryScreen().size()
        res = f"{screen.width()}x{screen.height()}"
        cmd = ["umu-run", "explorer.exe", f"/desktop=EquestriaOS,{res}", exe_path] + extra_args
    else:
        cmd = ["umu-run", exe_path] + extra_args

    print(f"Launching via UMU: {' '.join(cmd)}")

    # Чтобы консольный запуск тоже имел UI
    from launcher import SplashWindow
    log_path = os.path.join(APPS_DATA_DIR, f"{app_id}.log")
    log_out = open(log_path, "w", encoding="utf-8")

    proc = subprocess.Popen(cmd, env=env, cwd=game_dir, stdout=log_out, stderr=subprocess.STDOUT)

    splash = SplashWindow(exe_name, log_path, proc)
    splash.exec()

if __name__ == "__main__":
    main()
