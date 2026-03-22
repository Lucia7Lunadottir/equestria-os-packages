import sys
import os
import csv
import json
import shutil
import hashlib
from PyQt6.QtWidgets import (QApplication, QMainWindow, QMessageBox, QPushButton,
                              QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar)
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from ui import Ui_SettingsWindow

APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
CONFIG_DIR = os.path.expanduser("~/.config/Equestria OS/Proton/")
SYSTEM_PATH = os.path.dirname(os.path.abspath(__file__))

# ─── Update dialog ───────────────────────────────────────────────────────────

class UpdateCheckThread(QThread):
    result = pyqtSignal(str, str, str)  # (installed, latest, url)

    def run(self):
        try:
            sys.path.insert(0, SYSTEM_PATH)
            from proton_updater import get_installed_version, get_latest_release_info
            installed = get_installed_version() or ""
            latest, url = get_latest_release_info()
            self.result.emit(installed, latest or "", url or "")
        except Exception:
            self.result.emit("", "", "")


class UpdateDownloadThread(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(bool, str)

    def __init__(self, version, url):
        super().__init__()
        self._version = version
        self._url = url

    def run(self):
        try:
            sys.path.insert(0, SYSTEM_PATH)
            from proton_updater import download_and_install_with_progress
            download_and_install_with_progress(self._version, self._url, self.progress)
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))


class UpdateProtonDialog(QDialog):
    def __init__(self, t_fn, parent=None):
        super().__init__(parent)
        self.t = t_fn
        self.setWindowTitle(self.t("proton.update_dialog_title"))
        self.setModal(True)
        self.setFixedWidth(420)
        self._latest_version = ""
        self._latest_url = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)

        self.lbl_status = QLabel(self.t("proton.update_checking"))
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet("font-size: 11px; color: rgb(140, 130, 160);")
        self.lbl_progress.setVisible(False)
        layout.addWidget(self.lbl_progress)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_close = QPushButton(self.t("proton.btn_cancel"))
        self.btn_action = QPushButton(self.t("proton.update_btn_install"))
        self.btn_action.setObjectName("btnSave")
        self.btn_action.setVisible(False)
        btn_row.addWidget(self.btn_close)
        btn_row.addWidget(self.btn_action)
        layout.addLayout(btn_row)

        self.btn_close.clicked.connect(self.reject)
        self.btn_action.clicked.connect(self._start_download)

        self._check = UpdateCheckThread()
        self._check.result.connect(self._on_check)
        self._check.start()

    def _on_check(self, installed, latest, url):
        if not latest:
            self.lbl_status.setText(self.t("proton.update_error"))
            return
        self._latest_version = latest
        self._latest_url = url
        if installed == latest:
            txt = self.t("proton.update_up_to_date").replace("{0}", installed)
            self.lbl_status.setText(txt)
        else:
            installed_label = installed if installed else "—"
            txt = (self.t("proton.update_available")
                   .replace("{0}", latest)
                   .replace("{1}", installed_label))
            self.lbl_status.setText(txt)
            self.btn_action.setVisible(True)

    def _start_download(self):
        self.btn_action.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_progress.setVisible(True)

        self._dl = UpdateDownloadThread(self._latest_version, self._latest_url)
        self._dl.progress.connect(self._on_progress)
        self._dl.finished.connect(self._on_finished)
        self._dl.start()

    def _on_progress(self, msg, pct):
        self.lbl_progress.setText(msg)
        self.progress_bar.setValue(pct)

    def _on_finished(self, success, error):
        if success:
            self.lbl_status.setText(self.t("proton.update_success"))
            self.progress_bar.setVisible(False)
            self.lbl_progress.setVisible(False)
            self.btn_close.setEnabled(True)
            self.btn_close.setText("OK")
        else:
            QMessageBox.critical(self, self.t("proton.msg_error_title"),
                                 self.t("proton.msg_error_text").replace("{0}", error))
            self.btn_close.setEnabled(True)
            self.btn_action.setEnabled(True)


# ─── Settings window ─────────────────────────────────────────────────────────

class ProtonSettingsApp(QMainWindow, Ui_SettingsWindow):
    def __init__(self, exe_path):
        super().__init__()
        self.setupUi(self)

        self.exe_path = exe_path
        self.exe_name = os.path.basename(exe_path)

        path_hash = hashlib.md5(exe_path.encode('utf-8')).hexdigest()[:8]
        self.app_id = f"{self.exe_name}_{path_hash}"

        self.prefix_path = os.path.join(APPS_DATA_DIR, self.app_id)
        self.config_file = os.path.join(CONFIG_DIR, f"{self.app_id}.json")

        # Локализация
        self.localized_strings = {}
        self.available_langs = []
        self.current_lang = "en"

        self.load_localization_csv()
        self.detect_system_language()
        self.build_language_selector()

        self.settings = self.load_settings()

        self.update_ui_data()
        self.update_texts()
        self.bind_events()

    def load_localization_csv(self):
        loc_path = os.path.join(SYSTEM_PATH, "localization.csv")
        if not os.path.exists(loc_path):
            return
        with open(loc_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
                self.available_langs = [h.strip() for h in headers[1:]]
                for row in reader:
                    if not row or not row[0].strip():
                        continue
                    key = row[0].strip()
                    self.localized_strings[key] = {}
                    for i in range(1, len(row)):
                        if i <= len(self.available_langs):
                            self.localized_strings[key][self.available_langs[i - 1]] = (
                                row[i].strip().replace("\\n", "\n")
                            )
            except StopIteration:
                pass

    def t_str(self, key):
        langs = self.localized_strings.get(key, {})
        return langs.get(self.current_lang, langs.get("en", key))

    def detect_system_language(self):
        sys_lang = os.environ.get("LANG", "en")
        sys_code = sys_lang[:2].lower() if len(sys_lang) >= 2 else "en"
        self.current_lang = (
            sys_code if sys_code in self.available_langs
            else (self.available_langs[0] if self.available_langs else "en")
        )

    def build_language_selector(self):
        while self.lang_layout.count():
            item = self.lang_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for code in self.available_langs:
            btn = QPushButton(code.upper())
            btn.setProperty("cssClass", "lang-button")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.clicked.connect(lambda _, c=code: self.set_language(c))
            self.lang_layout.addWidget(btn)

    def set_language(self, code):
        self.current_lang = code
        for i in range(self.lang_layout.count()):
            btn = self.lang_layout.itemAt(i).widget()
            if btn:
                btn.setProperty("active", "true" if btn.text().lower() == code else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        self.update_texts()

    def update_texts(self):
        self.setWindowTitle(self.t_str("proton.title"))

        prop_str = self.t_str("proton.properties")
        self.lbl_title.setText(prop_str.replace("{0}", self.exe_name) if "{0}" in prop_str else f"{prop_str} {self.exe_name}")

        self.group_graphics.setTitle(self.t_str("proton.group_graphics"))
        self.chk_fps.setText(self.t_str("proton.chk_fps"))
        self.chk_desktop.setText(self.t_str("proton.chk_desktop"))

        self.group_args.setTitle(self.t_str("proton.group_args"))
        self.txt_args.setPlaceholderText(self.t_str("proton.txt_args_placeholder"))

        self.group_proton.setTitle(self.t_str("proton.group_proton"))
        self.btn_update.setText(self.t_str("proton.btn_update"))

        self.group_danger.setTitle(self.t_str("proton.group_danger"))
        self.lbl_danger.setText(self.t_str("proton.lbl_danger"))
        self.btn_clear.setText(self.t_str("proton.btn_clear"))

        self.btn_cancel.setText(self.t_str("proton.btn_cancel"))
        self.btn_save.setText(self.t_str("proton.btn_save"))
        self._refresh_version_label()

    def load_settings(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if os.path.exists(self.config_file):
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "dxvk_hud": False,
            "virtual_desktop": False,
            "launch_args": ""
        }

    def update_ui_data(self):
        self.lbl_path.setText(self.exe_path)
        self.chk_fps.setChecked(self.settings.get("dxvk_hud", False))
        self.chk_desktop.setChecked(self.settings.get("virtual_desktop", False))
        self.txt_args.setText(self.settings.get("launch_args", ""))
        self._refresh_version_label()

    def _refresh_version_label(self):
        from proton_updater import get_installed_version
        version = get_installed_version()
        if version:
            text = self.t_str("proton.lbl_version").replace("{0}", version)
        else:
            text = self.t_str("proton.lbl_version_none")
        self.lbl_version.setText(text)

    def bind_events(self):
        self.btn_cancel.clicked.connect(self.close)
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_clear.clicked.connect(self.delete_cache)
        self.btn_update.clicked.connect(self.open_update_dialog)

    def open_update_dialog(self):
        dlg = UpdateProtonDialog(self.t_str, self)
        dlg.exec()
        self._refresh_version_label()

    def save_settings(self):
        self.settings["dxvk_hud"] = self.chk_fps.isChecked()
        self.settings["virtual_desktop"] = self.chk_desktop.isChecked()
        self.settings["launch_args"] = self.txt_args.text().strip()

        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=4)

        self.close()

    def delete_cache(self):
        if not os.path.exists(self.prefix_path):
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
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    test_path = sys.argv[1] if len(sys.argv) > 1 else "/home/user/Downloads/setup.exe"

    window = ProtonSettingsApp(test_path)
    window.show()
    sys.exit(app.exec())
