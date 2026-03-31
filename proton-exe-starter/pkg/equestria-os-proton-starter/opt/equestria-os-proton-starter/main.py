import sys
import os
import csv
import json
import shutil
import hashlib
from PyQt6.QtWidgets import (QApplication, QMainWindow, QMessageBox, QPushButton)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from ui import Ui_SettingsWindow

APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
CONFIG_DIR = os.path.expanduser("~/.config/Equestria OS/Proton/")
SYSTEM_PATH = os.path.dirname(os.path.abspath(__file__))

class LauncherApp(QMainWindow, Ui_SettingsWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.locales = {}
        self.current_lang = "en"
        self.exe_path = ""
        self.exe_name = ""
        self.app_id = ""
        self.prefix_path = ""
        self.config_file = ""

        self.load_localization()
        self.detect_language()
        self.setup_lang_buttons()

        self.btn_save.clicked.connect(self.save_settings)
        self.btn_cancel.clicked.connect(self.close)
        self.btn_clear.clicked.connect(self.clear_cache)

        if len(sys.argv) > 1:
            self.exe_path = sys.argv[1]
            self.exe_name = os.path.basename(self.exe_path)
            path_hash = hashlib.md5(self.exe_path.encode('utf-8')).hexdigest()[:8]
            self.app_id = f"{self.exe_name}_{path_hash}"
            self.prefix_path = os.path.join(APPS_DATA_DIR, self.app_id)
            self.config_file = os.path.join(CONFIG_DIR, f"{self.app_id}.json")

            self.lbl_path.setText(self.exe_path)
            self.load_settings()
        else:
            self.lbl_path.setText(self.t_str("proton.properties").replace("{0}", "—"))

        self.update_ui_text()

    def load_localization(self):
        csv_path = os.path.join(SYSTEM_PATH, "localization.csv")
        if not os.path.exists(csv_path):
            return
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row["key"]
                self.locales[key] = {lang: text for lang, text in row.items() if lang != "key"}

    def detect_language(self):
        lang = os.environ.get("LANG", "en")
        for l in ["ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]:
            if lang.startswith(l):
                self.current_lang = l
                return
        self.current_lang = "en"

    def t_str(self, key):
        return self.locales.get(key, {}).get(self.current_lang, key)

    def setup_lang_buttons(self):
        langs = {"en": "🇬🇧", "ru": "🇷🇺", "de": "🇩🇪", "fr": "🇫🇷",
                 "es": "🇪🇸", "pt": "🇵🇹", "pl": "🇵🇱", "uk": "🇺🇦",
                 "zh": "🇨🇳", "ja": "🇯🇵"}
        for code, flag in langs.items():
            btn = QPushButton(flag)
            btn.setFixedSize(28, 28)
            btn.setToolTip(code.upper())
            btn.clicked.connect(lambda checked, c=code: self.change_language(c))
            self.lang_layout.addWidget(btn)

    def change_language(self, code):
        self.current_lang = code
        self.update_ui_text()

    def update_ui_text(self):
        self.setWindowTitle(self.t_str("proton.title"))
        self.lbl_title.setText(self.t_str("proton.title"))
        if self.exe_name:
            self.lbl_path.setText(self.t_str("proton.properties").replace("{0}", self.exe_name))
        self.group_graphics.setTitle(self.t_str("proton.group_graphics"))
        self.chk_fps.setText(self.t_str("proton.chk_fps"))
        self.chk_desktop.setText(self.t_str("proton.chk_desktop"))
        self.chk_fsr.setText(self.t_str("proton.chk_fsr"))
        self.group_args.setTitle(self.t_str("proton.group_args"))
        self.group_danger.setTitle(self.t_str("proton.group_danger"))
        self.lbl_danger.setText(self.t_str("proton.lbl_danger"))
        self.btn_clear.setText(self.t_str("proton.btn_clear"))
        self.btn_save.setText(self.t_str("proton.btn_save"))
        self.btn_cancel.setText(self.t_str("proton.btn_cancel"))

    def load_settings(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                    self.chk_fps.setChecked(settings.get("dxvk_hud", False))
                    self.chk_desktop.setChecked(settings.get("virtual_desktop", False))
                    self.chk_fsr.setChecked(settings.get("fsr", False))
                    self.txt_args.setText(settings.get("launch_args", ""))
            except Exception:
                pass

    def save_settings(self):
        if not self.app_id:
            self.close()
            return

        os.makedirs(CONFIG_DIR, exist_ok=True)
        settings = {
            "dxvk_hud": self.chk_fps.isChecked(),
            "virtual_desktop": self.chk_desktop.isChecked(),
            "fsr": self.chk_fsr.isChecked(),
            "launch_args": self.txt_args.text().strip()
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
        self.close()

    def clear_cache(self):
        if not self.prefix_path or not os.path.exists(self.prefix_path):
            QMessageBox.information(self, self.t_str("proton.msg_empty_title"), self.t_str("proton.msg_empty_text"))
            return

        del_txt = self.t_str("proton.msg_delete_text").replace("{0}", self.exe_name)
        reply = QMessageBox.question(
            self, self.t_str("proton.msg_delete_title"), del_txt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                shutil.rmtree(self.prefix_path)
                QMessageBox.information(self, self.t_str("proton.msg_success_title"), self.t_str("proton.msg_success_text"))
            except Exception as e:
                err_txt = self.t_str("proton.msg_error_text").replace("{0}", str(e))
                QMessageBox.critical(self, self.t_str("proton.msg_error_title"), err_txt)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    icon_path = "/usr/share/pixmaps/equestria-os-proton-starter.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        app.setWindowIcon(QIcon.fromTheme("preferences-desktop-theme"))

    qss_path = os.path.join(SYSTEM_PATH, "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r") as f:
            app.setStyleSheet(f.read())

    window = LauncherApp()
    window.show()
    sys.exit(app.exec())
