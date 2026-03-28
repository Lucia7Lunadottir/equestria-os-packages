"""
Equestria OS Proton Runner
Used by main.py (settings) to launch an exe directly without the installer GUI.
For the full double-click flow use launcher.py instead.
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


def find_proton():
    """Return path to the proton binary, or None."""
    import glob

    candidates = [
        os.path.expanduser("~/.local/share/Equestria OS/Proton/latest/proton"),
        *sorted(glob.glob(
            os.path.expanduser("~/.local/share/Steam/compatibilitytools.d/*/proton")
        )),
        *sorted(glob.glob("/usr/share/steam/compatibilitytools.d/*/proton")),
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


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

    exe_path = os.path.abspath(sys.argv[1])

    if not os.path.exists(exe_path):
        show_error("File not found", f"File not found:\n{exe_path}")

    proton_bin = find_proton()
    if not proton_bin:
        show_error(
            "Proton not installed",
            "Equestria Proton engine not found.\n"
            "Please run the Proton installer first."
        )

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
    env["STEAM_COMPAT_DATA_PATH"] = prefix_path
    steam_path = os.path.expanduser("~/.local/share/Steam")
    os.makedirs(steam_path, exist_ok=True) # Создаем папку-заглушку, если её нет
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = steam_path
    env["WINEDLLOVERRIDES"] = "winemenubuilder.exe=b"

    if settings.get("dxvk_hud"):
        env["DXVK_HUD"] = "fps,devinfo"

    extra_args = shlex.split(settings.get("launch_args", "").strip())

    game_dir = os.path.dirname(exe_path)

    if settings.get("virtual_desktop"):
        app = QApplication.instance() or QApplication(sys.argv)
        screen = app.primaryScreen().size()
        res = f"{screen.width()}x{screen.height()}"
        cmd = [proton_bin, "run", "explorer.exe",
               f"/desktop=EquestriaOS,{res}", exe_path] + extra_args
    else:
        cmd = [proton_bin, "run", exe_path] + extra_args

    print(f"Running: {' '.join(cmd)}")
    subprocess.Popen(cmd, env=env, cwd=game_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
