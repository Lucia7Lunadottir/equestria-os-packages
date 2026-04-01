import sys, os, json, subprocess, threading
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtGui import QFontDatabase, QFont, QIcon
from PyQt6.QtCore import Qt, pyqtSignal
from ui_mirrors import Ui_RankMirrors, CountryRow

class main_app(QMainWindow, Ui_RankMirrors):
    # Сигналы для связи потоков с интерфейсом
    countries_loaded = pyqtSignal(list, str)
    mirrors_loaded = pyqtSignal(str)
    operation_finished = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.setWindowTitle("Equestria OS Mirrors")

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

        # Шрифты: только заголовок!
        f_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            fid = QFontDatabase.addApplicationFont(f_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                self.title_label.setFont(QFont(families[0], 22, QFont.Weight.Bold))

        if os.path.exists(os.path.join(self.base_path, "style.qss")):
            self.setStyleSheet(open(os.path.join(self.base_path, "style.qss")).read())

        self.update_apply_button()
        self._check_timer_state()
        self.load_data()

    def resizeEvent(self, event):
        self.loading_overlay.resize(event.size())
        super().resizeEvent(event)

    def set_loading(self, active, text="⏳ Please wait..."):
        if active:
            self.lbl_loading.setText(text)
            self.loading_overlay.show()
            self.loading_overlay.raise_()
        else:
            self.loading_overlay.hide()

    def set_status(self, msg):
        self.lbl_status.setText(msg)

    # --- ВЫЗОВЫ БЭКЕНДА  ---
    def run_command(self, cmd_list):
        try:
            proc = subprocess.run(cmd_list, capture_output=True, text=True)
            return proc.stdout.strip()
        except Exception as e:
            return f'{{"error": "{str(e)}" }}'

    def load_data(self):
        self.set_loading(True, "⏳ Loading country list...")

        # Грузим страны
        def fetch_countries():
            out = self.run_command(["pg-rankmirrors-backend", "list-countries"])
            try:
                data = json.loads(out)
                # В C# бэкенд возвращал массив JSON напрямую
                if isinstance(data, list):
                    self.countries_loaded.emit(data, "")
                else:
                    self.countries_loaded.emit([], "Unexpected JSON format.")
            except Exception as e:
                self.countries_loaded.emit([], str(e))
        threading.Thread(target=fetch_countries, daemon=True).start()

        # Грузим текущие зеркала
        def fetch_current():
            out = self.run_command(["pg-rankmirrors-backend", "current"])
            self.mirrors_loaded.emit(out if out else "No mirrors configured.")
        threading.Thread(target=fetch_current, daemon=True).start()

    # --- ОБРАБОТЧИКИ ДАННЫХ ---
    def on_countries_loaded(self, data, error):
        self.set_loading(False)
        if error:
            self.set_status(f"Error: {error}")
            return

        self.all_countries = sorted(data, key=lambda x: x.get("name", "").lower())
        self.rebuild_list(self.all_countries)
        self.set_status(f"Loaded {len(self.all_countries)} countries.")

    def on_mirrors_loaded(self, text):
        self.lbl_current_mirrors.setText(text)

    def rebuild_list(self, countries):
        while self.countries_layout.count():
            w = self.countries_layout.takeAt(0).widget()
            if w: w.deleteLater()

        for c in countries:
            row = CountryRow(c, self.on_country_toggled)
            # Восстанавливаем состояние чекбокса
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
        self.lbl_selected_count.setText(f"Selected countries: {len(self.selected_codes)}")

    def update_apply_button(self):
        self.btn_apply.setEnabled(len(self.selected_codes) > 0)

    def filter_list(self, query):
        q = query.lower()
        if not q:
            filtered = self.all_countries
        else:
            filtered = [c for c in self.all_countries if q in c["name"].lower() or q in c["code"].lower()]
        self.rebuild_list(filtered)

    # --- ПРИМЕНЕНИЕ И ВОССТАНОВЛЕНИЕ  ---
    def on_apply_clicked(self):
        codes = ",".join(self.selected_codes)
        self.set_loading(True, "⏳ Ranking mirrors (this may take a few minutes)...")
        self.btn_apply.setEnabled(False)
        self.btn_restore.setEnabled(False)

        def _apply():
            out = self.run_command(["pkexec", "pg-rankmirrors-backend", "rank", codes])
            self.operation_finished.emit(True, out)
        threading.Thread(target=_apply, daemon=True).start()

    def on_restore_clicked(self):
        self.set_loading(True, "⏳ Restoring backup...")
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
                if status == "done":
                    self.set_status("✓ Mirrors updated successfully!")
                else:
                    self.set_status(f"Error: {err_msg}")
            else:
                if status == "restored":
                    self.set_status("✓ Backup restored.")
                else:
                    self.set_status(f"Error: {err_msg}")
        except:
            self.set_status("Done (could not parse backend response).")

        # Перезагружаем список текущих зеркал в правой панели
        threading.Thread(target=lambda: self.mirrors_loaded.emit(self.run_command(["pg-rankmirrors-backend", "current"])), daemon=True).start()

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
