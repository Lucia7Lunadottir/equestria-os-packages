import sys, os, json, csv, subprocess
from PyQt6.QtWidgets import QApplication, QMainWindow, QListWidgetItem, QPushButton
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from ui_software import Ui_SoftwareCenter, EssentialAppRow, StoreAppRow

class EssentialData:
    def __init__(self, pkg, display, cat, desc):
        self.package_name = pkg
        self.display_name = display
        self.category_key = cat.strip()
        self.desc_key = desc
        self.is_selected = False
        self.is_installed = False

class StoreData:
    def __init__(self, name, version, desc, source):
        self.name = name
        self.version = version
        self.desc = desc
        self.source = source
        self.category = "Software"
        self.status = "available"

class main_app(QMainWindow, Ui_SoftwareCenter):
    def __init__(self):
        super().__init__()
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.setupUi(self)

        self.current_lang = "ru"
        self.langs = []
        self.localizations = {}

        self.essentials_data = []
        self.store_packages = []
        self.installed_packages = set()
        self.upgradable_packages = set()
        self.selected_essentials = set()

        self.filtered_store_packages = []
        self.current_page = 1
        self.items_per_page = 50

        self.init_resources()
        self.discover_langs()
        self.load_localizations()
        self.refresh_system_status()
        self.load_essentials_csv()
        self.setup_logic()
        self.update_ui_texts()

        self.loader = AppStoreLoader()
        self.loader.finished.connect(self.on_store_loaded)
        self.loader.start()

    def init_resources(self):
        self.custom_font_family = "sans-serif"
        f_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            fid = QFontDatabase.addApplicationFont(f_path)
            if fid != -1:
                self.custom_font_family = QFontDatabase.applicationFontFamilies(fid)[0]
                self.title_label.setFont(QFont(self.custom_font_family, 24))

        icon_path = os.path.join(self.base_path, "equestria-os-software-center.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        qss_path = os.path.join(self.base_path, "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                qss = f.read().replace("{{TITLE_FONT}}", f'"{self.custom_font_family}"')
                self.setStyleSheet(qss)

    def discover_langs(self):
        locale_dir = os.path.join(self.base_path, "locales")
        if os.path.isdir(locale_dir):
            self.langs = sorted(
                f[:-5] for f in os.listdir(locale_dir) if f.endswith(".json")
            )
        if not self.langs:
            self.langs = ["en", "ru"]

    def refresh_system_status(self):
        try:
            res_inst = subprocess.run(["pacman", "-Qq"], capture_output=True, text=True)
            self.installed_packages = set(res_inst.stdout.splitlines())
            res_upd = subprocess.run(["pacman", "-Qu"], capture_output=True, text=True)
            self.upgradable_packages = {line.split()[0] for line in res_upd.stdout.splitlines() if line}
        except: pass

    def load_localizations(self):
        locale_dir = os.path.join(self.base_path, "locales")
        lang_file = os.path.join(locale_dir, f"{self.current_lang}.json")
        if not os.path.exists(lang_file):
            lang_file = os.path.join(locale_dir, "en.json")
        if os.path.exists(lang_file):
            with open(lang_file, encoding="utf-8") as f:
                self.localizations = json.load(f)
        else:
            self.localizations = {}

    def t(self, key):
        return self.localizations.get(key, key)

    def load_essentials_csv(self):
        csv_path = os.path.join(self.base_path, "EquestriaApps.csv")
        if not os.path.exists(csv_path): return
        self.essentials_data = []
        cats = set()
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                app = EssentialData(row['PackageName'], row['DisplayName'], row['CategoryKey'], row['DescKey'])
                app.is_installed = app.package_name in self.installed_packages
                self.essentials_data.append(app)
                cats.add(app.category_key)
        self.cat_list.clear()
        item_all = QListWidgetItem(self.t("ui.all"))
        item_all.setData(Qt.ItemDataRole.UserRole, "All")
        self.cat_list.addItem(item_all)
        for c in sorted(cats):
            item = QListWidgetItem(self.t(c) if c in self.localizations else c.replace("cat.", "").capitalize())
            item.setData(Qt.ItemDataRole.UserRole, c)
            self.cat_list.addItem(item)
        self.render_essentials("All")

    def render_essentials(self, filter_cat_key="All"):
        while self.layout_essentials.count():
            item = self.layout_essentials.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for app in self.essentials_data:
            if filter_cat_key == "All" or app.category_key == filter_cat_key:
                app.display_desc = self.t(app.desc_key)
                row = EssentialAppRow(app, self.toggle_essential)
                if app.is_installed:
                    # Блокируем сигнал чтобы setChecked не добавил пакет в selected_essentials
                    row.checkbox.blockSignals(True)
                    row.checkbox.setChecked(True)
                    row.checkbox.blockSignals(False)
                    row.checkbox.setEnabled(False)
                    row.lbl_name.setText(f"{app.display_name} ({self.t('ui.installed')})")
                self.layout_essentials.addWidget(row)

    def toggle_essential(self, app_data, is_checked):
        if is_checked: self.selected_essentials.add(app_data.package_name)
        else: self.selected_essentials.discard(app_data.package_name)
        self.update_install_button_text()

    def update_install_button_text(self):
        count = len(self.selected_essentials)
        txt = self.t("ui.install_btn_sel").replace("{0}", str(count)) if count > 0 else self.t("ui.install_btn_empty")
        self.btn_install_essentials.setText(txt)
        self.btn_install_essentials.setEnabled(count > 0)

    def setup_logic(self):
        self.btn_switch_store.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        self.cat_list.itemClicked.connect(self.on_cat_clicked)
        self.search_store.textChanged.connect(self.filter_store)
        self.combo_store.currentIndexChanged.connect(self.filter_store)
        self.btn_prev_page.clicked.connect(self.go_prev_page)
        self.btn_next_page.clicked.connect(self.go_next_page)
        self.btn_update_sys.clicked.connect(self.execute_system_update)
        self.btn_install_essentials.clicked.connect(self.install_selected_essentials)
        for i, lang in enumerate(self.langs):
            btn = QPushButton(lang.upper())
            btn.setObjectName("LangBtn")
            btn.setProperty("lang", lang)
            btn.clicked.connect(self.change_language)
            self.lang_layout.addWidget(btn, i // 5, i % 5)

    def change_language(self):
        self.current_lang = self.sender().property("lang")
        self.load_localizations()
        self.update_ui_texts()
        self.load_essentials_csv()
        # Перерисовать страницу магазина если она уже загружена
        if self.store_packages:
            self.filter_store()
        for i in range(self.lang_layout.count()):
            btn = self.lang_layout.itemAt(i).widget()
            if btn:
                btn.setProperty("active", "true" if btn.property("lang") == self.current_lang else "false")
                btn.style().unpolish(btn); btn.style().polish(btn)

    def update_ui_texts(self):
        self.cat_header.setText(self.t("ui.essentials_header"))
        self.store_header.setText(self.t("ui.store_header"))
        self.btn_switch_store.setText(self.t("ui.search_all"))
        self.btn_update_sys.setText(self.t("ui.update_all"))
        self.search_store.setPlaceholderText(self.t("ui.search_placeholder"))
        self.btn_prev_page.setText(self.t("ui.prev_page"))
        self.btn_next_page.setText(self.t("ui.next_page"))
        self.store_loading_lbl.setText(self.t("ui.loading"))
        self.update_install_button_text()

    def on_cat_clicked(self, item):
        self.stacked_widget.setCurrentIndex(0)
        self.render_essentials(item.data(Qt.ItemDataRole.UserRole))

    def on_store_loaded(self, packages):
        self.store_packages = packages
        self.store_loading_lbl.hide()
        self.filter_store()

    def filter_store(self):
        query, cat = self.search_store.text().lower(), self.combo_store.currentText()
        self.filtered_store_packages = []
        for pkg in self.store_packages:
            pkg.status = "upgradable" if pkg.name in self.upgradable_packages else ("installed" if pkg.name in self.installed_packages else "available")
            if query and query not in pkg.name.lower() and query not in pkg.desc.lower(): continue
            if cat != "All" and pkg.category != cat: continue
            self.filtered_store_packages.append(pkg)
        self.current_page = 1
        self.render_store_page()

    def render_store_page(self):
        while self.layout_store.count() > 0:
            item = self.layout_store.takeAt(0)
            if item.widget() and item.widget() != self.store_loading_lbl: item.widget().deleteLater()
        total = len(self.filtered_store_packages)
        pages = max(1, (total + self.items_per_page - 1) // self.items_per_page)
        start, end = (self.current_page - 1) * self.items_per_page, self.current_page * self.items_per_page
        for pkg in self.filtered_store_packages[start:end]:
            if pkg.status == "upgradable":
                txt = self.t("ui.update")
            elif pkg.status == "installed":
                txt = self.t("ui.installed")
            else:
                txt = self.t("ui.install")
            row = StoreAppRow(pkg, txt, self.install_package)
            if pkg.status == "upgradable": row.btn_action.setStyleSheet("background-color: #f9e2af; color: #11111b;")
            elif pkg.status == "installed": row.btn_action.setEnabled(False)
            self.layout_store.addWidget(row)
        page_txt = self.t("ui.page_info").replace("{0}", str(self.current_page)).replace("{1}", str(pages)).replace("{2}", str(total))
        self.lbl_page_info.setText(page_txt)
        self.btn_prev_page.setEnabled(self.current_page > 1)
        self.btn_next_page.setEnabled(self.current_page < pages)

    def go_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self.render_store_page(); self.scroll_store.verticalScrollBar().setValue(0)
    def go_next_page(self):
        if self.current_page < (len(self.filtered_store_packages)+49)//50: self.current_page += 1; self.render_store_page(); self.scroll_store.verticalScrollBar().setValue(0)

    def install_package(self, pkg): subprocess.Popen(["konsole", "-e", "bash", "-c", f"pkexec pacman -S --noconfirm {pkg.name}; read"])
    def remove_package(self, pkg): subprocess.Popen(["konsole", "-e", "bash", "-c", f"pkexec pacman -Rs --noconfirm {pkg.name}; read"])
    def install_selected_essentials(self):
        if self.selected_essentials: subprocess.Popen(["konsole", "-e", "bash", "-c", f"pkexec pacman -S --noconfirm {' '.join(self.selected_essentials)}; read"])
    def execute_system_update(self): subprocess.Popen(["konsole", "-e", "bash", "-c", "yay -Syu --noconfirm; if command -v flatpak >/dev/null; then flatpak update -y; fi; read"])

def guess_cat(n):
    n = n.lower()
    if any(x in n for x in ["game", "steam", "lutris", "wine"]): return "Games"
    if any(x in n for x in ["browser", "firefox", "network", "chat", "discord"]): return "Internet"
    if any(x in n for x in ["vlc", "audio", "video", "media", "music"]): return "Media"
    if any(x in n for x in ["image", "photo", "gimp", "graphics"]): return "Graphics"
    if any(x in n for x in ["nvidia", "mesa", "driver", "kernel"]): return "Drivers"
    return "Software"

class AppStoreLoader(QThread):
    finished = pyqtSignal(list)
    def run(self):
        pkgs = []
        try:
            res = subprocess.run(["pacman", "-Sl"], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                p = line.split()
                if len(p) >= 3:
                    d = StoreData(p[1], p[2], "Arch Repository", "pacman")
                    d.category = guess_cat(p[1]); pkgs.append(d)
        except: pass
        self.finished.emit(pkgs)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setDesktopFileName("equestria-os-software-center")
    win = main_app(); win.show()
    sys.exit(app.exec())
