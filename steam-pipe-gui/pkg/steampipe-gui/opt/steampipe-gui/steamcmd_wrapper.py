import os
import re
from PyQt6.QtCore import pyqtSignal, QObject, QProcess
from depot_manager import DepotManager

class SteamCmdWrapper(QObject):
    log_output = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    login_state_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.is_logged_in = False
        self.logged_in_user = None
        self.steamcmd_path = self.find_steamcmd()
        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._handle_finished)
        self.current_action = None

    def find_steamcmd(self):
        candidates = [
            os.path.expanduser("~/sdk/tools/ContentBuilder/builder_linux/steamcmd.sh"),
            os.path.expanduser("~/SteamworksSDK/tools/ContentBuilder/builder_linux/steamcmd.sh"),
            "/usr/bin/steamcmd",
            "/usr/games/steamcmd",
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def try_set_sdk_folder(self, sdk_folder: str) -> bool:
        candidates = [
            os.path.join(sdk_folder, "tools", "ContentBuilder", "builder_linux", "steamcmd.sh"),
            os.path.join(sdk_folder, "builder_linux", "steamcmd.sh"),
            os.path.join(sdk_folder, "steamcmd.sh"),
        ]
        for p in candidates:
            if os.path.exists(p):
                self.steamcmd_path = p
                self.log(f"[OK] steamcmd: {p}")
                return True
        self.log(f"[ERROR] steamcmd.sh not found in: {sdk_folder}")
        return False

    def login(self, username, password, guard):
        if not self.steamcmd_path:
            self.log("[ERROR] steamcmd not found. Set SDK folder in Settings.")
            return

        self.current_action = "login"
        self.logged_in_user = username
        self.status_changed.emit("Logging in...")

        args = ["+login", username, password]
        if guard:
            args.append(guard)
        args.append("+quit")

        self.process.start(self.steamcmd_path, args)

    def build(self, app_id, desc, content_path, branch, set_live):
        if not self.is_logged_in:
            self.log("[ERROR] Please log in first.")
            return

        try:
            vdf_path = DepotManager.create_simple_vdf(app_id, desc, content_path, branch, set_live)
            self.log(f"[INFO] VDF created: {vdf_path}")
        except Exception as e:
            self.log(f"[ERROR] VDF error: {e}")
            return

        self.current_action = "build"
        self.status_changed.emit("Uploading...")
        args = ["+login", self.logged_in_user, "+run_app_build", vdf_path, "+quit"]
        self.process.start(self.steamcmd_path, args)

    def logout(self):
        self.is_logged_in = False
        self.logged_in_user = None
        self.login_state_changed.emit(False)
        self.status_changed.emit("Not connected")
        self.log("[INFO] Logged out.")

    def log(self, message: str):
        clean_msg = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', message)
        if clean_msg.strip():
            self.log_output.emit(clean_msg.strip())

    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace')
        for line in data.splitlines():
            self.log(line)
            if self.current_action == "login":
                if "Logged in OK" in line or "Login Successful" in line or "Unloading Steam API" in line:
                    self.is_logged_in = True
                    self.login_state_changed.emit(True)
                    self.status_changed.emit(f"✓ {self.logged_in_user}")
                elif "Two-factor code mismatch" in line or "Invalid Steam Guard" in line:
                    self.log("[ERROR] Invalid Steam Guard code.")
                    self.status_changed.emit("Steam Guard error")
                elif "Invalid Password" in line or "FAILED login" in line:
                    self.log("[ERROR] Invalid username or password.")
                    self.status_changed.emit("Login failed")

    def _handle_stderr(self):
        data = self.process.readAllStandardError().data().decode('utf-8', errors='replace')
        for line in data.splitlines():
            self.log(f"[STDERR] {line}")

    def _handle_finished(self):
        if self.current_action == "build":
            self.status_changed.emit(f"✓ {self.logged_in_user}" if self.is_logged_in else "Ready")
        self.current_action = None
