import sys
import os
import re
import csv
import json
import shutil
import hashlib
import tempfile
import tarfile
import urllib.request
import urllib.error
from PyQt6.QtWidgets import (QApplication, QMainWindow, QMessageBox, QPushButton,
                             QComboBox, QDialog, QVBoxLayout, QLabel, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from ui import Ui_SettingsWindow

APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
CONFIG_DIR = os.path.expanduser("~/.config/Equestria OS/Proton/")
SYSTEM_PATH = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

# Куда umu кладёт сборки Proton (см. umu_consts.py: STEAM_COMPAT и UMU_COMPAT)
PROTON_COMPAT_DIRS = (
    os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
    os.path.expanduser("~/.local/share/umu/compatibilitytools"),
)


def _proton_sort_key(name):
    # Натуральная сортировка версий, как в самом umu (GE-Proton9-4 < GE-Proton10-1)
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def installed_protons():
    """[(имя, абсолютный путь)] всех установленных сборок Proton, новые сверху."""
    found = {}
    for base in PROTON_COMPAT_DIRS:
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            path = os.path.join(base, entry)
            if os.path.isfile(os.path.join(path, "proton")):
                found.setdefault(entry, path)
    return sorted(found.items(), key=lambda kv: _proton_sort_key(kv[0]), reverse=True)


def latest_proton(prefix):
    """Имя самой новой установленной сборки, начинающейся с prefix, или ""."""
    names = [n for n, _ in installed_protons() if n.startswith(prefix)]
    return names[0] if names else ""


GE_PROTON_REPO = "GloriousEggroll/proton-ge-custom"
GE_PROTON_API_LATEST = f"https://api.github.com/repos/{GE_PROTON_REPO}/releases/latest"


class _GeProtonDownloadThread(QThread):
    """
    Скачивает и распаковывает последний релиз GE-Proton напрямую с GitHub,
    в обход `umu-run`'s встроенной автозагрузки по кодовому имени "GE-Proton".

    На umu-launcher 1.4.0 эта встроенная автозагрузка ненадёжна: даже прямой
    вызов `PROTONPATH=GE-Proton umu-run createprefix` в терминале (без какого-
    либо кода этой программы) падает с FileNotFoundError "Environment
    variable not set or is empty: PROTONPATH", хотя переменная явно
    установлена — воспроизведено и подтверждено вне нашего кода. Поэтому для
    GE-Proton идём в обход: сами разрешаем "latest" через GitHub API и
    распаковываем тарбол в compatibilitytools.d — ровно то же самое место,
    куда положил бы umu, если бы его загрузка работала.
    """
    progress = pyqtSignal(int)          # 0-100
    status = pyqtSignal(str)            # ключ статуса: "checking"|"downloading"|"verifying"|"extracting"
    log_line = pyqtSignal(str)
    finished_ok = pyqtSignal(str)       # имя установленной версии
    finished_err = pyqtSignal(str)      # текст ошибки

    def __init__(self, dest_dir):
        super().__init__()
        self.dest_dir = dest_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.status.emit("checking")
            self.log_line.emit(f"GET {GE_PROTON_API_LATEST}")
            req = urllib.request.Request(
                GE_PROTON_API_LATEST,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "equestria-os-proton"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                release = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            self.finished_err.emit(f"GitHub API: {exc}")
            return

        tag = release.get("tag_name", "")
        asset = next(
            (a for a in release.get("assets", []) if a.get("name", "").endswith(".tar.gz")),
            None,
        )
        if not tag or not asset:
            self.finished_err.emit("GitHub API: не нашёл tar.gz asset в последнем релизе")
            return

        # Уже стоит — скачивать заново незачем
        if os.path.isdir(os.path.join(self.dest_dir, tag)):
            self.finished_ok.emit(tag)
            return

        if self._cancelled:
            return

        url = asset["browser_download_url"]
        total = int(asset.get("size") or 0)
        self.log_line.emit(f"Downloading {url}")
        self.status.emit("downloading")

        tmp_dir = tempfile.mkdtemp(prefix="eq-geproton-dl-")
        tarball_path = os.path.join(tmp_dir, asset["name"])
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "equestria-os-proton"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(tarball_path, "wb") as out:
                downloaded = 0
                chunk = 1024 * 256
                while True:
                    if self._cancelled:
                        return
                    data = resp.read(chunk)
                    if not data:
                        break
                    out.write(data)
                    downloaded += len(data)
                    if total:
                        self.progress.emit(int(downloaded * 100 / total))

            if self._cancelled:
                return

            self.status.emit("extracting")
            self.log_line.emit(f"Extracting to {self.dest_dir}")
            os.makedirs(self.dest_dir, exist_ok=True)
            dest_real = os.path.realpath(self.dest_dir)
            with tarfile.open(tarball_path, "r:gz") as tf:
                # Помимо встроенного filter="data" (PEP 706) добавляем свою
                # проверку containment: у filter="data" есть известный обход
                # (CVE-2025-4517, realpath()/PATH_MAX edge case), где путь,
                # который фильтр посчитал безопасным, на самом деле уводит
                # за пределы dest_dir. Источник — официальный релиз GitHub,
                # но раз тарбол всё равно приходит из внешней сети, лишняя
                # явная проверка ничего не стоит и не мешает нормальной
                # распаковке легитимных архивов GE-Proton.
                for member in tf.getmembers():
                    member_path = os.path.realpath(os.path.join(self.dest_dir, member.name))
                    if not (member_path == dest_real or member_path.startswith(dest_real + os.sep)):
                        raise tarfile.TarError(f"Небезопасный путь в архиве: {member.name}")
                tf.extractall(self.dest_dir, filter="data")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, tarfile.TarError) as exc:
            self.finished_err.emit(str(exc))
            return
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        if not os.path.isdir(os.path.join(self.dest_dir, tag)):
            self.finished_err.emit(f"После распаковки не нашёл {tag} в {self.dest_dir}")
            return

        self.finished_ok.emit(tag)


class ProtonUpdateDialog(QDialog):
    """
    Обновление движка. Для GE-Proton — прямая загрузка последнего релиза с
    GitHub (см. _GeProtonDownloadThread) в обход umu-run. Для UMU-Proton
    механизм не трогаем: она подкачивается штатно при обычном запуске игры,
    и на неё этот баг umu не влияет так же остро (см. commit-сообщения этой
    правки), поэтому по кнопке "Обновить" в режиме "Авто" — тот же путь.
    """

    def __init__(self, parent, tr, mode):
        super().__init__(parent)
        self.tr_ = tr
        self.mode = mode                                  # "" | "GE-Proton"
        self.match_prefix = "GE-" if mode == "GE-Proton" else "UMU-"
        self.before = latest_proton(self.match_prefix)
        self.cancelled = False
        self.dest_dir = PROTON_COMPAT_DIRS[0]

        self.setWindowTitle(tr("proton.update_dialog_title"))
        self.setFixedWidth(420)
        layout = QVBoxLayout(self)
        self.lbl_status = QLabel(tr("proton.update_checking"))
        self.lbl_status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # «занято», пока не увидим проценты
        self.btn_close = QPushButton(tr("proton.btn_cancel"))
        self.btn_close.clicked.connect(self._on_close_clicked)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.progress)
        layout.addWidget(self.btn_close)

        self._log_tail = []

        if self.mode == "GE-Proton":
            self.thread = _GeProtonDownloadThread(self.dest_dir)
            self.thread.progress.connect(self._on_dl_progress)
            self.thread.status.connect(self._on_dl_status)
            self.thread.log_line.connect(self._on_dl_log)
            self.thread.finished_ok.connect(self._on_dl_ok)
            self.thread.finished_err.connect(self._on_dl_err)
            self.thread.start()
        else:
            # UMU-Proton: у пользователя она уже установлена и обновляется
            # штатно при обычном запуске игры через umu-run; отдельного
            # публичного API релизов для неё здесь не задействуем, чтобы не
            # дублировать логику, которая и так работает через launcher.py.
            self._finish_ui()
            current = latest_proton("UMU-")
            info = self.tr_("proton.lbl_version").replace("{0}", current) if current \
                else self.tr_("proton.lbl_version_none")
            self.lbl_status.setText(info)

    def _on_dl_progress(self, percent):
        self.progress.setRange(0, 100)
        self.progress.setValue(percent)

    def _on_dl_status(self, key):
        label_key = {
            "checking": "proton.update_checking",
            "downloading": "launcher.downloading",
            "extracting": "launcher.verifying",
        }.get(key)
        if label_key:
            self.lbl_status.setText(self.tr_(label_key))

    def _on_dl_log(self, line):
        self._log_tail = (self._log_tail + [line])[-15:]

    def _cleanup(self):
        pass  # загрузка идёт во временную папку и чистит её сама (finally в потоке)

    def _finish_ui(self):
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.btn_close.setText(self.tr_("launcher.btn_close"))

    def _on_dl_ok(self, tag):
        self._finish_ui()
        if tag != self.before:
            text = self.tr_("proton.update_success") + "\n" + \
                self.tr_("proton.lbl_version").replace("{0}", tag)
        else:
            text = self.tr_("proton.update_up_to_date").replace("{0}", tag)
        self.lbl_status.setText(text)

    def _on_dl_err(self, message):
        self._finish_ui()
        self.progress.setValue(0)
        tail = "\n".join(self._log_tail[-4:])
        extra = f"\n{message}" + (f"\n{tail}" if tail else "")
        self.lbl_status.setText(self.tr_("proton.update_error") + extra)

    def _on_close_clicked(self):
        if hasattr(self, "thread") and self.thread.isRunning():
            self.cancelled = True
            self.thread.cancel()
            self.thread.wait(2000)
            self.reject()
        else:
            self.accept()

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
        self.setup_lang_selector()
        self.populate_proton_combo()

        self.btn_save.clicked.connect(self.save_settings)
        self.btn_cancel.clicked.connect(self.close)
        self.btn_clear.clicked.connect(self.clear_cache)
        self.combo_proton.currentIndexChanged.connect(self.update_proton_info)
        self.btn_proton_update.clicked.connect(self.run_proton_update)

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

    def setup_lang_selector(self):
        # Компактный выпадающий список языков вместо ряда кнопок
        codes = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LangCombo")
        for code in codes:
            self.lang_combo.addItem(code.upper(), code)
        idx = self.lang_combo.findData(self.current_lang)
        if idx != -1:
            self.lang_combo.setCurrentIndex(idx)
        # activated срабатывает только при выборе пользователем — без рекурсии
        self.lang_combo.activated.connect(
            lambda i: self.change_language(self.lang_combo.itemData(i)))
        self.lang_layout.addWidget(self.lang_combo)

    def change_language(self, code):
        self.current_lang = code
        idx = self.lang_combo.findData(code)
        if idx != -1 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.setCurrentIndex(idx)
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
        self.chk_xbox_pad.setText(self.t_str("proton.chk_xbox_pad"))
        self.chk_debug.setText(self.t_str("proton.chk_debug"))
        self.group_proton.setTitle(self.t_str("proton.group_proton"))
        self.combo_proton.setItemText(0, self.t_str("proton.ver_auto"))
        self.combo_proton.setItemText(1, self.t_str("proton.ver_ge"))
        self.btn_proton_update.setText(self.t_str("proton.btn_update"))
        self.update_proton_info()
        self.group_args.setTitle(self.t_str("proton.group_args"))
        self.group_danger.setTitle(self.t_str("proton.group_danger"))
        self.lbl_danger.setText(self.t_str("proton.lbl_danger"))
        self.btn_clear.setText(self.t_str("proton.btn_clear"))
        self.btn_save.setText(self.t_str("proton.btn_save"))
        self.btn_cancel.setText(self.t_str("proton.btn_cancel"))

    def populate_proton_combo(self, keep_selection=False):
        """Пункты: авто (UMU-Proton), GE-Proton, затем каждая установленная сборка."""
        current = self.combo_proton.currentData() if keep_selection else None
        self.combo_proton.blockSignals(True)
        self.combo_proton.clear()
        self.combo_proton.addItem(self.t_str("proton.ver_auto"), "")
        self.combo_proton.addItem(self.t_str("proton.ver_ge"), "GE-Proton")
        for name, path in installed_protons():
            self.combo_proton.addItem(name, path)
        if current is not None:
            idx = self.combo_proton.findData(current)
            self.combo_proton.setCurrentIndex(idx if idx != -1 else 0)
        self.combo_proton.blockSignals(False)
        self.update_proton_info()

    def update_proton_info(self):
        choice = self.combo_proton.currentData()
        if choice == "GE-Proton":
            name = latest_proton("GE-")
        elif choice:
            name = os.path.basename(choice) if os.path.isdir(choice) else ""
        else:
            name = latest_proton("UMU-")
        if name:
            self.lbl_proton_ver.setText(self.t_str("proton.lbl_version").replace("{0}", name))
        else:
            self.lbl_proton_ver.setText(self.t_str("proton.lbl_version_none"))
        # Обновлять имеет смысл только автоматические режимы; закреплённая
        # версия закреплена намеренно — её не трогаем
        self.btn_proton_update.setEnabled(choice in ("", "GE-Proton"))

    def run_proton_update(self):
        mode = self.combo_proton.currentData()
        if mode not in ("", "GE-Proton"):
            return
        dlg = ProtonUpdateDialog(self, self.t_str, mode)
        dlg.exec()
        self.populate_proton_combo(keep_selection=True)

    def load_settings(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                    self.chk_fps.setChecked(settings.get("dxvk_hud", False))
                    self.chk_desktop.setChecked(settings.get("virtual_desktop", False))
                    self.chk_fsr.setChecked(settings.get("fsr", False))
                    self.chk_xbox_pad.setChecked(settings.get("xbox_pad", False))
                    self.chk_debug.setChecked(settings.get("debug_log", False))
                    self.txt_args.setText(settings.get("launch_args", ""))
                    idx = self.combo_proton.findData(settings.get("proton_version", ""))
                    self.combo_proton.setCurrentIndex(idx if idx != -1 else 0)
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
            "xbox_pad": self.chk_xbox_pad.isChecked(),
            "debug_log": self.chk_debug.isChecked(),
            "launch_args": self.txt_args.text().strip(),
            "proton_version": self.combo_proton.currentData() or ""
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
    app.setDesktopFileName("equestria-os-proton-starter")

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
