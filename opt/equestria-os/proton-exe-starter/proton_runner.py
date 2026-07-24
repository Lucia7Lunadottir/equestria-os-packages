"""
Equestria OS Proton Runner
"""

import sys
import os
import json
import hashlib
import subprocess
import shlex
import shutil

from PyQt6.QtWidgets import QApplication, QMessageBox

APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
CONFIG_DIR = os.path.expanduser("~/.config/Equestria OS/Proton/")
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

    # Already a symlink — nothing to do
    if os.path.islink(windows_path):
        # Heal broken symlink so umu-run can reinitialise if needed
        if not os.path.exists(windows_path):
            os.remove(windows_path)
        return

    if not os.path.isdir(windows_path):
        return  # Not initialised yet

    try:
        os.makedirs(SHARED_BASE, exist_ok=True)
        if not os.path.exists(SHARED_WINDOWS):
            # First migration: atomically move this prefix's windows/ to _shared/
            shutil.move(windows_path, SHARED_WINDOWS)
            open(SHARED_MARKER, "w").close()
        else:
            # Shared already exists: discard this prefix's copy
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

    # Migrate existing windows/ to shared (atomic rename, no game running yet)
    _migrate_windows_to_shared(prefix_path)

    if not os.path.exists(prefix_path):
        os.makedirs(prefix_path, exist_ok=True)
        _preseed_shared_windows(prefix_path)

    env = os.environ.copy()
    env["WINEPREFIX"] = prefix_path
    env["GAMEID"] = app_id

    if settings.get("dxvk_hud"):
        env["DXVK_HUD"] = "compiler,frametimes,fps"
    if settings.get("fsr"):
        env["WINE_FULLSCREEN_FSR"] = "1"

    from launcher import apply_game_env
    apply_game_env(env, settings)

    from launcher import BootstrapWindow, _load_localization, _detect_language
    _load_localization()
    _detect_language()

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

    print(f"Launching via UMU: {' '.join(cmd)}")

    from launcher import SplashWindow

    log_path = os.path.join(APPS_DATA_DIR, f"{app_id}.log")

    splash = SplashWindow(exe_name, log_path, cmd, env, game_dir, debug=debug)
    splash.exec()

    # Post-launch migration: handles the case where umu-run just initialised a brand-new
    # prefix (windows/ didn't exist before launch, so pre-launch migration did nothing).
    # os.rename is atomic on Linux — safe even while the game process is still running.
    _migrate_windows_to_shared(prefix_path)



if __name__ == "__main__":
    main()
