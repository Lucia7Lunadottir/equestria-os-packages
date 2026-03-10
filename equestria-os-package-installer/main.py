import sys, os, csv, subprocess, threading
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QListWidgetItem
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from ui_store import Ui_AppStore, AppRow

class PackageState:
    NotInstalled = 0
    Installed = 1
    UpdateAvailable = 2

class StoreApp:
    def __init__(self, pkg_name, display_name, cat_key, desc_key):
        self.package_name = pkg_name
        self.display_name = display_name
        self.category_key = cat_key
        self.desc_key = desc_key
        self.is_selected = False
        self.state = PackageState.NotInstalled

class main_app(QMainWindow, Ui_AppStore):
    status_check_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        self.status_check_finished.connect(self.on_status_check_finished)

        # ФИКС 1: ШРИФТ ПРИМЕНЯЕТСЯ ТОЛЬКО К ЗАГОЛОВКАМ
        f_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            fid = QFontDatabase.addApplicationFont(f_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                # Больше нет self.setFont() !
                self.categories_lbl.setFont(QFont(families[0], 24, QFont.Weight.Bold))
                self.modal_title.setFont(QFont(families[0], 20, QFont.Weight.Bold))

        q_path = os.path.join(self.base_path, "style.qss")
        if os.path.exists(q_path): self.setStyleSheet(open(q_path, "r").read())
        QApplication.setDesktopFileName("equestria-app-store")

        self.localized_strings = {
            "ui.categories": {"en": "Categories", "ru": "Категории"},
            "ui.all": {"en": "All Apps", "ru": "Все приложения", "uk": "Всі"},
            "ui.update_all": {"en": "Update System", "ru": "Обновить систему", "uk": "Оновити систему"},
            "ui.update_title": {"en": "System Update", "ru": "Обновление"},
            "ui.update_desc": {"en": "Update all system packages (Pacman, AUR, Flatpak, Snap)?", "ru": "Обновить все системные пакеты (Pacman, AUR, Flatpak, Snap)?"},
            "ui.cancel": {"en": "Cancel", "ru": "Отмена"},
            "ui.confirm": {"en": "Update", "ru": "Обновить"},
            "ui.install_btn_empty": {"en": "Select Apps to Install", "ru": "Выберите для установки"},
            "ui.install_btn_sel": {"en": "Install {0} Apps", "ru": "Установить {0} шт.", "uk": "Встановити {0}"},
            "ui.install_btn_upd": {"en": "Install/Update {0} Apps", "ru": "Установить/Обновить {0} шт."},
            "ui.installed": {"en": "Installed", "ru": "Установлено", "uk": "Встановлено"},
            "ui.update": {"en": "Update", "ru": "Обновление", "uk": "Оновлення"}
        }

        self.lang_map = {"en": "en", "ru": "ru", "de": "de", "fr": "fr", "es": "es", "pt": "pt", "pl": "pl", "uk": "uk", "zh": "zh", "ja": "ja"}
        self.current_lang = os.getenv("LANG", "en")[:2]
        if self.current_lang not in self.lang_map: self.current_lang = "en"

        self.all_apps = []
        self.categories = ["ui.all"]
        self.current_category = "ui.all"

        self.load_csv_data()
        self.setup_logic()
        self.update_ui_for_language()
        self.check_statuses_async()

    def t(self, key):
        return self.localized_strings.get(key, {}).get(self.current_lang, self.localized_strings.get(key, {}).get("en", key))

    def load_csv_data(self):
        loc_path = os.path.join(self.base_path, "EquestriaLocalizations.csv")
        if os.path.exists(loc_path):
            with open(loc_path, newline='', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                headers = next(reader, [])
                for row in reader:
                    if len(row) > 1:
                        key = row[0]
                        if key not in self.localized_strings: self.localized_strings[key] = {}
                        for i in range(1, len(row)):
                            if i < len(headers):
                                lang_code = headers[i].lower()
                                self.localized_strings[key][lang_code] = row[i]

        apps_path = os.path.join(self.base_path, "EquestriaApps.csv")
        if os.path.exists(apps_path):
            with open(apps_path, newline='', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                next(reader, None)
                for row in reader:
                    if len(row) >= 4:
                        self.all_apps.append(StoreApp(row[0], row[1], row[2], row[3]))
                        if row[2] not in self.categories:
                            self.categories.append(row[2])

    def setup_logic(self):
        # ФИКС 3: РАЗБИВАЕМ ЯЗЫКИ НА ДВА РЯДА ЧТОБЫ НЕ ПЛЫЛИ
        codes = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
        for i, code in enumerate(codes):
            btn = QPushButton(code.upper())
            btn.setProperty("cssClass", "lang-button")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda chk, c=code: self.change_lang(c))

            if i < 5:
                self.lang_layout_top.addWidget(btn)
            else:
                self.lang_layout_bottom.addWidget(btn)

        self.category_list.itemSelectionChanged.connect(self.on_category_selected)
        self.btn_install.clicked.connect(self.execute_installation)

        self.btn_update_all.clicked.connect(lambda: (self.modal_overlay.show(), self.modal_overlay.raise_()))
        self.btn_cancel_update.clicked.connect(self.modal_overlay.hide)
        self.btn_confirm_update.clicked.connect(self.execute_system_update)

        self.build_app_list()

    def resizeEvent(self, event):
        self.modal_overlay.resize(event.size())
        super().resizeEvent(event)

    def change_lang(self, lang):
        self.current_lang = lang
        # Обновляем оба ряда кнопок
        for layout in [self.lang_layout_top, self.lang_layout_bottom]:
            for i in range(layout.count()):
                btn = layout.itemAt(i).widget()
                if isinstance(btn, QPushButton):
                    btn.setProperty("active", "true" if btn.text().lower() == lang else "false")
                    btn.style().unpolish(btn); btn.style().polish(btn)
        self.update_ui_for_language()

    def update_ui_for_language(self):
        self.setWindowTitle("Equestria App Store")
        self.categories_lbl.setText(self.t("ui.categories"))
        self.btn_update_all.setText(self.t("ui.update_all"))
        self.modal_title.setText(self.t("ui.update_title"))
        self.modal_text.setText(self.t("ui.update_desc"))
        self.btn_cancel_update.setText(self.t("ui.cancel"))
        self.btn_confirm_update.setText(self.t("ui.confirm"))

        self.category_list.blockSignals(True)
        self.category_list.clear()
        for cat in self.categories:
            item = QListWidgetItem(self.t(cat))
            item.setData(Qt.ItemDataRole.UserRole, cat)
            self.category_list.addItem(item)
            if cat == self.current_category:
                item.setSelected(True)
        self.category_list.blockSignals(False)

        for i in range(self.app_list_layout.count()):
            widget = self.app_list_layout.itemAt(i).widget()
            if isinstance(widget, AppRow):
                widget.lbl_desc.setText(self.t(widget.app_data.desc_key))
                self.update_app_status_ui(widget)

        self.update_install_button_text()

    def on_category_selected(self):
        selected = self.category_list.selectedItems()
        if selected:
            self.current_category = selected[0].data(Qt.ItemDataRole.UserRole)
            self.filter_apps()

    def build_app_list(self):
        while self.app_list_layout.count():
            w = self.app_list_layout.takeAt(0).widget()
            if w: w.deleteLater()

        for app in self.all_apps:
            row = AppRow(app, self.on_app_toggled)
            self.app_list_layout.addWidget(row)
        self.filter_apps()

    def filter_apps(self):
        for i in range(self.app_list_layout.count()):
            widget = self.app_list_layout.itemAt(i).widget()
            if isinstance(widget, AppRow):
                cat_match = (self.current_category == "ui.all" or widget.app_data.category_key == self.current_category)
                widget.setVisible(cat_match)

    def on_app_toggled(self, app_data, is_checked):
        app_data.is_selected = is_checked
        self.update_install_button_text()

    def update_install_button_text(self):
        count = sum(1 for a in self.all_apps if a.is_selected)
        if count > 0:
            has_updates = any(a.state == PackageState.UpdateAvailable for a in self.all_apps if a.is_selected)
            base_text = self.t("ui.install_btn_upd") if has_updates else self.t("ui.install_btn_sel")
            self.btn_install.setText(base_text.format(count))
            self.btn_install.setEnabled(True)
        else:
            self.btn_install.setText(self.t("ui.install_btn_empty"))
            self.btn_install.setEnabled(False)

    def update_app_status_ui(self, widget: AppRow):
        app = widget.app_data
        lbl = widget.lbl_status
        lbl.setProperty("cssClass", "")

        is_installed = (app.state == PackageState.Installed)
        widget.checkbox.setEnabled(not is_installed)
        if is_installed:
            app.is_selected = False
            widget.checkbox.blockSignals(True)
            widget.checkbox.setChecked(False)
            widget.checkbox.blockSignals(False)

        if app.state == PackageState.Installed:
            lbl.setText(self.t("ui.installed"))
            lbl.setProperty("cssClass", "status-installed")
            lbl.show()
        elif app.state == PackageState.UpdateAvailable:
            lbl.setText(self.t("ui.update"))
            lbl.setProperty("cssClass", "status-update")
            lbl.show()
        else:
            lbl.hide()

        lbl.style().unpolish(lbl); lbl.style().polish(lbl)

    def check_statuses_async(self):
        def _task():
            installed = self.get_cmd_output("yay -Qq")
            updates = self.get_cmd_output("yay -Quq")

            for app in self.all_apps:
                check_name = app.package_name.split(' ')[0]
                if check_name in installed:
                    app.state = PackageState.UpdateAvailable if check_name in updates else PackageState.Installed
                else:
                    app.state = PackageState.NotInstalled
            self.status_check_finished.emit()

        threading.Thread(target=_task, daemon=True).start()

    def get_cmd_output(self, cmd):
        res = set()
        try:
            proc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
            for line in proc.stdout.splitlines():
                if line.strip(): res.add(line.strip())
        except: pass
        return res

    def on_status_check_finished(self):
        for i in range(self.app_list_layout.count()):
            widget = self.app_list_layout.itemAt(i).widget()
            if isinstance(widget, AppRow):
                self.update_app_status_ui(widget)
        self.update_install_button_text()

    def execute_installation(self):
        selected = [a.package_name for a in self.all_apps if a.is_selected]
        if not selected: return

        pkg_list = " ".join(selected)
        cmd = f"yay -S --needed {pkg_list}"
        full_cmd = f"{cmd}; echo -e '\\nTransaction finished. Press Enter to close...'; read"
        subprocess.Popen(["konsole", "-e", "bash", "-c", full_cmd])

        for a in self.all_apps: a.is_selected = False
        for i in range(self.app_list_layout.count()):
            widget = self.app_list_layout.itemAt(i).widget()
            if isinstance(widget, AppRow):
                widget.checkbox.blockSignals(True)
                widget.checkbox.setChecked(False)
                widget.checkbox.blockSignals(False)

        self.update_install_button_text()
        QTimer.singleShot(5000, self.check_statuses_async)

    def execute_system_update(self):
        self.modal_overlay.hide()
        # Добавляем --noconfirm для автоматизации и --overwrite для решения конфликтов
        # Также добавлена проверка на наличие snap, чтобы не сыпать ошибками
        # Исправленный вариант
        cmd = (
            "bash -c \"echo -e '\\e[1;35m✨ Starting Equestria OS Global Update...\\e[0m\\n'; "
            "yay -Syu --noconfirm --overwrite '/usr/*'; "
            "echo -e '\\n\\e[1;34m✨ Updating Flatpaks...\\e[0m\\n'; "
            "if command -v flatpak >/dev/null; then flatpak update -y; else echo 'Flatpak not installed'; fi; "
            "echo -e '\\n\\e[1;32m✨ Updating Snaps...\\e[0m\\n'; "
            "if command -v snap >/dev/null; then pkexec snap refresh; else echo 'Snap not installed'; fi; "
            "echo -e '\\n\\e[1;33m✅ System update finished! Press Enter to close...\\e[0m'; read\""
        )

        subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])
        QTimer.singleShot(5000, self.check_statuses_async)

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
