import sys, os, glob, json, subprocess, threading
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtGui import QFontDatabase, QFont, QIcon
from PyQt6.QtCore import Qt, pyqtSignal
from ui_mirrors import Ui_RankMirrors, CountryRow

class main_app(QMainWindow, Ui_RankMirrors):
    countries_loaded = pyqtSignal(list, str)
    mirrors_loaded = pyqtSignal(str)
    operation_finished = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.setWindowTitle("Equestria OS Mirrors")

        # --- Locales ---
        self.langs: dict = self._load_locales()
        self.current_lang = self._detect_lang()

        # Сигналы
        self.countries_loaded.connect(self.on_countries_loaded)
        self.mirrors_loaded.connect(self.on_mirrors_loaded)
        self.operation_finished.connect(self.on_operation_finished)

        # UI События
        self.search_field.textChanged.connect(self.filter_list)
        self.btn_apply.clicked.connect(self.on_apply_clicked)
        self.btn_restore.clicked.connect(self.on_restore_clicked)
        self.chk_auto.toggled.connect(self.on_auto_toggled)

        # Данные
        self.all_countries = []
        self.selected_codes = set()

        # Шрифты
        f_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            fid = QFontDatabase.addApplicationFont(f_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                self.title_label.setFont(QFont(families[0], 22, QFont.Weight.Bold))

        if os.path.exists(os.path.join(self.base_path, "style.qss")):
            self.setStyleSheet(open(os.path.join(self.base_path, "style.qss")).read())

        self._retranslate_ui()
        self.update_apply_button()
        self._check_timer_state()
        self.load_data()

    # ── Localization ──────────────────────────────────────────────────────────

    def _load_locales(self) -> dict:
        langs = {}
        locales_dir = os.path.join(self.base_path, "locales")
        for path in sorted(glob.glob(os.path.join(locales_dir, "*.json"))):
            code = os.path.basename(path).removesuffix(".json")
            try:
                with open(path, encoding="utf-8") as f:
                    langs[code] = json.load(f)
            except Exception as e:
                print(f"[pg-rankmirrors] locale load failed: {path}: {e}")
        return langs

    def _detect_lang(self) -> str:
        for env in ("LANGUAGE", "LANG", "LC_ALL", "LC_MESSAGES"):
            code = (os.getenv(env) or "")[:2]
            if code in self.langs:
                return code
        return "en"

    def t(self, key: str) -> str:
        return (
            self.langs.get(self.current_lang, {}).get(key)
            or self.langs.get("en", {}).get(key, key)
        )

    def change_lang(self, code: str):
        if code not in self.langs:
            return
        self.current_lang = code
        self._retranslate_ui()
        self.rebuild_list(self.all_countries)

    def _retranslate_ui(self):
        self.title_label.setText(self.t("title"))
        self.lbl_select.setText(self.t("select_countries"))
        self.search_field.setPlaceholderText(self.t("search_placeholder"))
        self.lbl_selected_count.setText(self.t("selected_count").replace("{0}", str(len(self.selected_codes))))
        self.lbl_current.setText(self.t("current_mirrors"))
        if not self.lbl_current_mirrors.text():
            self.lbl_current_mirrors.setText(self.t("loading"))
        self.chk_auto.setText(self.t("auto_update"))
        self.btn_restore.setText(self.t("btn_restore"))
        self.btn_apply.setText(self.t("btn_apply"))
        self.lbl_loading.setText(self.t("wait"))

    # ── Backend calls ─────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        self.loading_overlay.resize(event.size())
        super().resizeEvent(event)

    def set_loading(self, active, text=None):
        if active:
            self.lbl_loading.setText(text or self.t("wait"))
            self.loading_overlay.show()
            self.loading_overlay.raise_()
        else:
            self.loading_overlay.hide()

    def set_status(self, msg):
        self.lbl_status.setText(msg)

    def run_command(self, cmd_list):
        try:
            proc = subprocess.run(cmd_list, capture_output=True, text=True)
            return proc.stdout.strip()
        except Exception as e:
            return f'{{"error": "{str(e)}" }}'

    def load_data(self):
        self.set_loading(True, self.t("loading_countries"))

        def fetch_countries():
            out = self.run_command(["pg-rankmirrors-backend", "list-countries"])
            try:
                data = json.loads(out)
                if isinstance(data, list):
                    self.countries_loaded.emit(data, "")
                else:
                    self.countries_loaded.emit([], self.t("unexpected_json"))
            except Exception as e:
                self.countries_loaded.emit([], str(e))
        threading.Thread(target=fetch_countries, daemon=True).start()

        def fetch_current():
            out = self.run_command(["pg-rankmirrors-backend", "current"])
            self.mirrors_loaded.emit(out if out else self.t("no_mirrors"))
        threading.Thread(target=fetch_current, daemon=True).start()

    # ── Data handlers ─────────────────────────────────────────────────────────

    def on_countries_loaded(self, data, error):
        self.set_loading(False)
        if error:
            self.set_status(f"Error: {error}")
            return
        self.all_countries = sorted(data, key=lambda x: x.get("name", "").lower())
        self.rebuild_list(self.all_countries)
        self.set_status(self.t("loaded_n_countries").replace("{0}", str(len(self.all_countries))))

    def on_mirrors_loaded(self, text):
        self.lbl_current_mirrors.setText(text)

    def rebuild_list(self, countries):
        while self.countries_layout.count():
            w = self.countries_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        mirrors_label = self.t("mirrors_count")
        for c in countries:
            row = CountryRow(c, self.on_country_toggled, mirrors_label)
            if c["code"] in self.selected_codes:
                row.checkbox.blockSignals(True)
                row.checkbox.setChecked(True)
                row.checkbox.blockSignals(False)
            self.countries_layout.addWidget(row)

        self.update_selected_count()

    def on_country_toggled(self, code, is_checked):
        if is_checked:
            self.selected_codes.add(code)
        else:
            self.selected_codes.discard(code)
        self.update_selected_count()
        self.update_apply_button()

    def update_selected_count(self):
        self.lbl_selected_count.setText(
            self.t("selected_count").replace("{0}", str(len(self.selected_codes)))
        )

    def update_apply_button(self):
        self.btn_apply.setEnabled(len(self.selected_codes) > 0)

    def filter_list(self, query):
        q = query.lower()
        filtered = self.all_countries if not q else [
            c for c in self.all_countries
            if q in c["name"].lower() or q in c["code"].lower()
        ]
        self.rebuild_list(filtered)

    # ── Actions ───────────────────────────────────────────────────────────────

    def on_apply_clicked(self):
        codes = ",".join(self.selected_codes)
        self.set_loading(True, self.t("ranking"))
        self.btn_apply.setEnabled(False)
        self.btn_restore.setEnabled(False)

        def _apply():
            out = self.run_command(["pkexec", "pg-rankmirrors-backend", "rank", codes])
            self.operation_finished.emit(True, out)
        threading.Thread(target=_apply, daemon=True).start()

    def on_restore_clicked(self):
        self.set_loading(True, self.t("restoring"))
        self.btn_apply.setEnabled(False)
        self.btn_restore.setEnabled(False)

        def _restore():
            out = self.run_command(["pkexec", "pg-rankmirrors-backend", "restore"])
            self.operation_finished.emit(False, out)
        threading.Thread(target=_restore, daemon=True).start()

    def on_operation_finished(self, is_apply, result_json):
        self.set_loading(False)
        self.update_apply_button()
        self.btn_restore.setEnabled(True)

        try:
            data = json.loads(result_json)
            status = data.get("status", "")
            err_msg = data.get("error") or data.get("message", "Unknown error")

            if is_apply:
                self.set_status(self.t("mirrors_updated") if status == "done"
                                else f"Error: {err_msg}")
            else:
                self.set_status(self.t("backup_restored") if status == "restored"
                                else f"Error: {err_msg}")
        except Exception:
            self.set_status(self.t("parse_error"))

        threading.Thread(
            target=lambda: self.mirrors_loaded.emit(
                self.run_command(["pg-rankmirrors-backend", "current"])
            ),
            daemon=True
        ).start()

    def _check_timer_state(self):
        try:
            r = subprocess.run(["systemctl", "is-enabled", "pg-rankmirrors.timer"],
                               capture_output=True, text=True)
            enabled = r.stdout.strip() == "enabled"
            self.chk_auto.blockSignals(True)
            self.chk_auto.setChecked(enabled)
            self.chk_auto.blockSignals(False)
        except Exception:
            pass

    def on_auto_toggled(self, checked):
        cmd = "enable-auto" if checked else "disable-auto"
        threading.Thread(
            target=lambda: self.run_command(["pkexec", "pg-rankmirrors-backend", cmd]),
            daemon=True
        ).start()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    icon_path = "/usr/share/pixmaps/equestria-os-logo.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        app.setWindowIcon(QIcon.fromTheme("preferences-desktop-theme"))

    win = main_app()
    win.show()
    sys.exit(app.exec())
