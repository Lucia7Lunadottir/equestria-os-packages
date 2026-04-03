import sys
import os
import json
import csv
import subprocess
import shutil

from PyQt6.QtWidgets import (QApplication, QMainWindow, QListWidgetItem,
                              QPushButton, QLabel, QVBoxLayout, QWidget)
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QThread, QTimer, QFileSystemWatcher

from models import EssentialData, StoreData
from utils import (FLATPAK_APPSTREAM, cleanup_screenshot_cache,
                   normalize_key, merge_packages, _GENERIC_PACMAN_DESC)
from workers import (AppStoreLoader, FlatpakLoader,
                     AURSearchThread, AURPopularLoader,
                     ScreenshotDownloadThread, LocalAppStreamLoader,
                     PacmanInfoLoader)
from ui_software import Ui_SoftwareCenter, EssentialAppRow, StoreAppRow, AppDetailWidget


class main_app(QMainWindow, Ui_SoftwareCenter):
    def __init__(self):
        super().__init__()
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.setupUi(self)
        self.setWindowTitle("Equestria Software Center")

        self.current_lang = "ru"
        self.langs = []
        self.localizations = {}

        self.essentials_data = []
        self.store_packages = []
        self.flatpak_packages = []
        self.aur_packages = []
        self.flatpak_installed = set()
        self.flatpak_upgradable = set()
        self.installed_packages = set()
        self.upgradable_packages = set()
        self.selected_essentials = set()

        self.filtered_store_packages = []
        self.current_page = 1
        self.items_per_page = 50

        self._current_source = "all"
        self._merged_packages = []
        self._aur_search_thread = None
        self._aur_popular_thread = None
        self._aur_debounce_timer = None
        self._aur_search_gen = 0
        self._aur_popular_cached = []
        self._aur_query_cache = {}
        self._screenshot_threads = []
        self._screenshot_gen = 0
        self._pacman_info_thread = None

        self.init_resources()
        cleanup_screenshot_cache()
        self.discover_langs()
        self.load_localizations()
        self.refresh_system_status()
        self.load_essentials_csv()
        self.setup_logic()
        self.update_ui_texts()

        self.loader = AppStoreLoader()
        self.loader.finished.connect(self.on_store_loaded)
        self.loader.start()

        if shutil.which("flatpak") and os.path.exists(FLATPAK_APPSTREAM):
            self.flatpak_loader = FlatpakLoader()
            self.flatpak_loader.finished.connect(self.on_flatpak_loaded)
            self.flatpak_loader.start()

        self._flatpak_watcher = QFileSystemWatcher()
        flatpak_dir = os.path.dirname(FLATPAK_APPSTREAM)
        if os.path.exists(flatpak_dir):
            self._flatpak_watcher.addPath(flatpak_dir)
        self._flatpak_watcher.directoryChanged.connect(self._on_flatpak_dir_changed)

    # -------------------------------------------------------------------------
    # Startup helpers
    # -------------------------------------------------------------------------

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
            self.langs = sorted(f[:-5] for f in os.listdir(locale_dir) if f.endswith(".json"))
        if not self.langs:
            self.langs = ["en", "ru"]

    def refresh_system_status(self):
        try:
            res = subprocess.run(["pacman", "-Qq"], capture_output=True, text=True)
            self.installed_packages = set(res.stdout.splitlines())
            res_upd = subprocess.run(["pacman", "-Qu"], capture_output=True, text=True)
            self.upgradable_packages = {line.split()[0] for line in res_upd.stdout.splitlines() if line}

            self.flatpak_upgradable = set()
            if shutil.which("flatpak"):
                res_flat = subprocess.run(
                    ["flatpak", "list", "--updates", "--columns=application"],
                    capture_output=True, text=True
                )
                self.flatpak_upgradable = {
                    line.strip() for line in res_flat.stdout.splitlines() if line.strip()
                }
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Localization
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Essentials tab
    # -------------------------------------------------------------------------

    def load_essentials_csv(self):
        csv_path = os.path.join(self.base_path, "EquestriaApps.csv")
        if not os.path.exists(csv_path):
            return
        self.essentials_data = []
        cats = set()
        with open(csv_path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f, delimiter=';'):
                app = EssentialData(row['PackageName'], row['DisplayName'],
                                    row['CategoryKey'], row['DescKey'])
                app.is_installed = app.package_name in self.installed_packages
                self.essentials_data.append(app)
                cats.add(app.category_key)

        self.cat_list.clear()
        item_all = QListWidgetItem(self.t("ui.all"))
        item_all.setData(Qt.ItemDataRole.UserRole, "All")
        self.cat_list.addItem(item_all)
        for c in sorted(cats):
            item = QListWidgetItem(
                self.t(c) if c in self.localizations else c.replace("cat.", "").capitalize()
            )
            item.setData(Qt.ItemDataRole.UserRole, c)
            self.cat_list.addItem(item)
        self.render_essentials("All")

    def render_essentials(self, filter_cat_key="All"):
        while self.layout_essentials.count():
            item = self.layout_essentials.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for app in self.essentials_data:
            if filter_cat_key == "All" or app.category_key == filter_cat_key:
                app.display_desc = self.t(app.desc_key)
                row = EssentialAppRow(app, self.toggle_essential)
                if app.is_installed:
                    row.checkbox.blockSignals(True)
                    row.checkbox.setChecked(True)
                    row.checkbox.blockSignals(False)
                    row.checkbox.setEnabled(False)
                    row.lbl_name.setText(f"{app.display_name} ({self.t('ui.installed')})")
                self.layout_essentials.addWidget(row)

    def toggle_essential(self, app_data, is_checked):
        if is_checked:
            self.selected_essentials.add(app_data.package_name)
        else:
            self.selected_essentials.discard(app_data.package_name)
        self.update_install_button_text()

    def update_install_button_text(self):
        count = len(self.selected_essentials)
        txt = (self.t("ui.install_btn_sel").replace("{0}", str(count))
               if count > 0 else self.t("ui.install_btn_empty"))
        self.btn_install_essentials.setText(txt)
        self.btn_install_essentials.setEnabled(count > 0)

    # -------------------------------------------------------------------------
    # UI wiring
    # -------------------------------------------------------------------------

    def setup_logic(self):
        self.btn_switch_store.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        self.cat_list.itemClicked.connect(self.on_cat_clicked)
        self.search_store.textChanged.connect(self._on_search_changed)
        self.combo_store.currentIndexChanged.connect(self.filter_store)
        self.combo_source.currentIndexChanged.connect(self._on_source_changed)
        self.btn_prev_page.clicked.connect(self.go_prev_page)
        self.btn_next_page.clicked.connect(self.go_next_page)
        self.btn_update_sys.clicked.connect(self.execute_system_update)
        self.btn_integrity_check.clicked.connect(self.execute_integrity_check)
        self.btn_cache_clean.clicked.connect(self.execute_cache_clean)
        self.btn_install_essentials.clicked.connect(self.install_selected_essentials)

        for i, lang in enumerate(self.langs):
            btn = QPushButton(lang.upper())
            btn.setObjectName("LangBtn")
            btn.setProperty("lang", lang)
            btn.clicked.connect(self.change_language)
            self.lang_layout.addWidget(btn, i // 5, i % 5)

        self.page_detail = AppDetailWidget(self._go_back_from_detail)
        self.stacked_widget.addWidget(self.page_detail)

    def change_language(self):
        self.current_lang = self.sender().property("lang")
        self.load_localizations()
        self.update_ui_texts()
        self.load_essentials_csv()
        if self.store_packages:
            self.filter_store()
        for i in range(self.lang_layout.count()):
            btn = self.lang_layout.itemAt(i).widget()
            if btn:
                is_active = "true" if btn.property("lang") == self.current_lang else "false"
                btn.setProperty("active", is_active)
                btn.style().unpolish(btn)
                btn.style().polish(btn)

    def update_ui_texts(self):
        self.cat_header.setText(self.t("ui.essentials_header"))
        self.store_header.setText(self.t("ui.store_header"))
        self.btn_switch_store.setText(self.t("ui.search_all"))
        self.btn_integrity_check.setText(self.t("ui.integrity_check"))
        self.btn_cache_clean.setText(self.t("ui.cache_clean"))
        self.btn_update_sys.setText(self.t("ui.update_all"))
        self.search_store.setPlaceholderText(self.t("ui.search_placeholder"))
        self.btn_prev_page.setText(self.t("ui.prev_page"))
        self.btn_next_page.setText(self.t("ui.next_page"))
        self.store_loading_lbl.setText(self.t("ui.loading"))
        self.combo_source.blockSignals(True)
        self.combo_source.setItemText(0, self.t("ui.source_all"))
        self.combo_source.setItemText(1, self.t("ui.source_pacman"))
        self.combo_source.setItemText(2, self.t("ui.source_aur"))
        self.combo_source.setItemText(3, self.t("ui.source_flatpak"))
        self.combo_source.setItemText(4, self.t("ui.source_updates"))
        self.combo_source.blockSignals(False)
        self.update_install_button_text()

    def on_cat_clicked(self, item):
        self.stacked_widget.setCurrentIndex(0)
        self.render_essentials(item.data(Qt.ItemDataRole.UserRole))

    # -------------------------------------------------------------------------
    # Store data loading
    # -------------------------------------------------------------------------

    def _rebuild_merged(self):
        self._merged_packages = merge_packages(self.store_packages, self.flatpak_packages)

    def on_store_loaded(self, packages):
        self.store_packages = packages
        self._rebuild_merged()
        self.store_loading_lbl.hide()
        self.filter_store()

    def on_flatpak_loaded(self, packages):
        self.flatpak_packages = packages
        try:
            res = subprocess.run(
                ["flatpak", "list", "--app", "--columns=application"],
                capture_output=True, text=True
            )
            self.flatpak_installed = {
                line.strip() for line in res.stdout.splitlines() if line.strip()
            }
        except Exception:
            self.flatpak_installed = set()
        self._rebuild_merged()
        if self._current_source in ("flatpak", "all"):
            self.filter_store()

    def _on_flatpak_dir_changed(self, _path):
        if os.path.exists(FLATPAK_APPSTREAM):
            self.flatpak_loader = FlatpakLoader()
            self.flatpak_loader.finished.connect(self.on_flatpak_loaded)
            self.flatpak_loader.start()

    # -------------------------------------------------------------------------
    # Filtering / search
    # -------------------------------------------------------------------------

    def _on_source_changed(self, index):
        source_map = {0: "all", 1: "pacman", 2: "aur", 3: "flatpak", 4: "updates"}
        self._current_source = source_map.get(index, "all")
        self.filter_store()

    def _on_search_changed(self, text):
        if self._current_source == "aur":
            if self._aur_debounce_timer:
                self._aur_debounce_timer.stop()
            self._aur_debounce_timer = QTimer()
            self._aur_debounce_timer.setSingleShot(True)
            self._aur_debounce_timer.timeout.connect(
                lambda: self._trigger_aur_search(text)
            )
            self._aur_debounce_timer.start(500)
        else:
            self.filter_store()

    def filter_store(self):
        source = self._current_source
        if source == "aur":
            query = self.search_store.text().strip()
            if query:
                self._trigger_aur_search(query)
            elif self._aur_popular_cached:
                self._on_aur_popular_loaded(self._aur_popular_cached)
            else:
                self._load_aur_popular()
            return
        if source == "flatpak":
            if not shutil.which("flatpak"):
                self._show_flatpak_bootstrap_prompt(no_binary=True)
                return
            if not self.flatpak_packages:
                if not os.path.exists(FLATPAK_APPSTREAM):
                    self._show_flatpak_bootstrap_prompt()
                    return
                self._show_store_message(self.t("ui.loading"))
                return
            self._filter_packages(self.flatpak_packages)
            return
        if source == "updates":
            self._filter_packages(self._merged_packages, source)
            return
        if source == "all":
            self._filter_packages(self._merged_packages, source)
        else:
            self._filter_packages(self.store_packages, source)

    def _filter_packages(self, packages, source="all"):
        query = self.search_store.text().lower()
        cat = self.combo_store.currentText()
        self.filtered_store_packages = []

        for pkg in packages:
            if pkg.source_type == "flatpak":
                if pkg.app_id in self.flatpak_upgradable:
                    pkg.status = "upgradable"
                elif pkg.app_id in self.flatpak_installed:
                    pkg.status = "installed"
                else:
                    pkg.status = "available"
            else:
                if pkg.name in self.upgradable_packages:
                    pkg.status = "upgradable"
                elif pkg.name in self.installed_packages:
                    pkg.status = "installed"
                else:
                    pkg.status = "available"

            if source == "updates" and pkg.status != "upgradable":
                continue
            if query and query not in pkg.name.lower() and query not in pkg.desc.lower():
                continue
            if cat != "All" and pkg.category != cat:
                continue
            self.filtered_store_packages.append(pkg)

        self.current_page = 1
        self.render_store_page()

    # -------------------------------------------------------------------------
    # AUR helpers
    # -------------------------------------------------------------------------

    def _load_aur_popular(self):
        self._show_store_message(self.t("ui.loading"))
        self._aur_popular_thread = AURPopularLoader()
        self._aur_popular_thread.finished.connect(self._on_aur_popular_loaded)
        self._aur_popular_thread.start()

    def _on_aur_popular_loaded(self, pkgs):
        self._aur_popular_cached = pkgs
        if self._current_source == "aur" and not self.search_store.text().strip():
            self.aur_packages = pkgs
            self.filtered_store_packages = list(pkgs)
            self.current_page = 1
            self.render_store_page()

    def _trigger_aur_search(self, query):
        if not query:
            self._show_store_message(self.t("ui.aur_placeholder"))
            return
        if query in self._aur_query_cache:
            self._on_aur_results(self._aur_query_cache[query], self._aur_search_gen, query)
            return
        self._aur_search_gen += 1
        gen = self._aur_search_gen
        self._aur_search_thread = AURSearchThread(query)
        self._aur_search_thread.finished.connect(
            lambda pkgs, g=gen, q=query: self._on_aur_results(pkgs, g, q)
        )
        self._aur_search_thread.start()

    def _on_aur_results(self, pkgs, gen, query=None):
        if query:
            self._aur_query_cache[query] = pkgs
        if gen != self._aur_search_gen:
            return
        self.aur_packages = pkgs
        self.filtered_store_packages = list(pkgs)
        self.current_page = 1
        self.render_store_page()

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def _show_store_message(self, msg):
        while self.layout_store.count() > 0:
            item = self.layout_store.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        lbl = QLabel(msg)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #a6adc8; font-size: 16px;")
        self.layout_store.addWidget(lbl)
        self.lbl_page_info.setText("")
        self.btn_prev_page.setEnabled(False)
        self.btn_next_page.setEnabled(False)

    def _show_flatpak_bootstrap_prompt(self, no_binary=False):
        while self.layout_store.count() > 0:
            item = self.layout_store.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        if no_binary:
            lbl_title = QLabel(self.t("ui.flatpak_not_installed_title"))
            lbl_title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; background: transparent;")
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lbl_desc = QLabel(self.t("ui.flatpak_not_installed_desc"))
            lbl_desc.setStyleSheet("color: #a6adc8; font-size: 14px; background: transparent;")
            lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_desc.setWordWrap(True)

            btn = QPushButton(self.t("ui.flatpak_install_btn"))
            btn.setObjectName("DetailActionBtn")
            btn.setFixedWidth(250)
            btn.setMinimumHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(self._run_flatpak_install)
            layout.addWidget(lbl_title)
            layout.addWidget(lbl_desc)
            layout.addSpacing(20)
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            lbl_title = QLabel(self.t("ui.flatpak_not_setup"))
            lbl_title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; background: transparent;")
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lbl_desc = QLabel(self.t("ui.flatpak_init_desc"))
            lbl_desc.setStyleSheet("color: #a6adc8; font-size: 14px; background: transparent;")
            lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_desc.setWordWrap(True)

            btn = QPushButton(self.t("ui.flatpak_init_btn"))
            btn.setObjectName("DetailActionBtn")
            btn.setFixedWidth(250)
            btn.setMinimumHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(self._run_flatpak_bootstrap)
            layout.addWidget(lbl_title)
            layout.addWidget(lbl_desc)
            layout.addSpacing(20)
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.layout_store.addWidget(container)
        self.lbl_page_info.setText("")
        self.btn_prev_page.setEnabled(False)
        self.btn_next_page.setEnabled(False)

    def _run_flatpak_install(self):
        cmd = "pkexec pacman -S --noconfirm flatpak; echo; read -rp 'Done. Press Enter to close...'"
        subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])

    def _run_flatpak_bootstrap(self):
        cmd = (
            "pkexec flatpak remote-add --if-not-exists flathub "
            "https://dl.flathub.org/repo/flathub.flatpakrepo && "
            "flatpak update; echo; read -rp 'Done. Press Enter to close...'"
        )
        subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])

    def render_store_page(self):
        while self.layout_store.count() > 0:
            item = self.layout_store.takeAt(0)
            if item.widget() and item.widget() != self.store_loading_lbl:
                item.widget().deleteLater()
        total = len(self.filtered_store_packages)
        pages = max(1, (total + self.items_per_page - 1) // self.items_per_page)
        start = (self.current_page - 1) * self.items_per_page
        for pkg in self.filtered_store_packages[start:start + self.items_per_page]:
            if pkg.status == "upgradable":
                txt = self.t("ui.update")
            elif pkg.status == "installed":
                txt = self.t("ui.installed")
            else:
                txt = self.t("ui.install")
            row = StoreAppRow(pkg, txt, self.install_package, on_row_click=self.open_app_detail)
            if pkg.status == "upgradable":
                row.btn_action.setStyleSheet("background-color: #f9e2af; color: #11111b;")
            elif pkg.status == "installed":
                row.btn_action.setEnabled(False)
            self.layout_store.addWidget(row)
        page_txt = (self.t("ui.page_info")
                    .replace("{0}", str(self.current_page))
                    .replace("{1}", str(pages))
                    .replace("{2}", str(total)))
        self.lbl_page_info.setText(page_txt)
        self.btn_prev_page.setEnabled(self.current_page > 1)
        self.btn_next_page.setEnabled(self.current_page < pages)

    def go_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.render_store_page()
            self.scroll_store.verticalScrollBar().setValue(0)

    def go_next_page(self):
        pages = (len(self.filtered_store_packages) + self.items_per_page - 1) // self.items_per_page
        if self.current_page < pages:
            self.current_page += 1
            self.render_store_page()
            self.scroll_store.verticalScrollBar().setValue(0)

    # -------------------------------------------------------------------------
    # App detail
    # -------------------------------------------------------------------------

    def open_app_detail(self, pkg_data):
        target_name = normalize_key(pkg_data.name)
        target_app_id = (normalize_key(pkg_data.app_id.split('.')[-1])
                         if pkg_data.app_id else target_name)

        alts = {pkg_data.source_type: pkg_data}

        if "pacman" not in alts:
            for p in self.store_packages:
                if normalize_key(p.name) in (target_name, target_app_id):
                    alts["pacman"] = p
                    break

        if "flatpak" not in alts:
            for p in self.flatpak_packages:
                p_key = normalize_key(p.app_id.split('.')[-1]) if p.app_id else ""
                if normalize_key(p.name) in (target_name, target_app_id) or \
                        p_key in (target_name, target_app_id):
                    alts["flatpak"] = p
                    break

        if "aur" not in alts:
            for p in self.aur_packages:
                if normalize_key(p.name) in (target_name, target_app_id):
                    alts["aur"] = p
                    break

        self.page_detail.load_package_group(
            alts_dict=alts,
            default_source=pkg_data.source_type,
            t_func=self.t,
            installed_set=self.installed_packages,
            flatpak_installed_set=self.flatpak_installed,
            upgradable_set=self.upgradable_packages,
            on_install=self.install_package,
            on_remove=self.remove_package,
            on_source_changed=self._load_detail_content,
        )
        self.stacked_widget.setCurrentIndex(2)

    def _go_back_from_detail(self):
        self.stacked_widget.setCurrentIndex(1)

    def _load_detail_content(self, pkg_data):
        """Called whenever the source selector changes in the detail view."""
        self._load_detail_screenshots(pkg_data)
        self._load_pacman_desc_if_needed(pkg_data)

    def _load_pacman_desc_if_needed(self, pkg_data):
        """If the package is from Pacman and has a generic description, fetch it on-demand."""
        if pkg_data.source_type != "pacman":
            return
        if pkg_data.desc not in (_GENERIC_PACMAN_DESC, ""):
            return
        self._pacman_info_thread = PacmanInfoLoader(pkg_data.name)
        self._pacman_info_thread.finished.connect(
            lambda desc, p=pkg_data: self._on_pacman_desc_loaded(desc, p)
        )
        self._pacman_info_thread.start()

    def _on_pacman_desc_loaded(self, desc, pkg_data):
        if not desc:
            return
        pkg_data.desc = desc
        # Update the label only if this package is still the one being shown
        try:
            self.page_detail.lbl_desc.setText(desc)
        except RuntimeError:
            pass

    # -------------------------------------------------------------------------
    # Screenshots
    # -------------------------------------------------------------------------

    def _load_detail_screenshots(self, pkg_data):
        self._screenshot_threads = []
        self._screenshot_gen += 1
        gen = self._screenshot_gen
        self.page_detail.clear_screenshots()

        if pkg_data.source_type == "flatpak":
            if pkg_data.screenshot_urls:
                self._start_screenshot_downloads(pkg_data.screenshot_urls, gen)
            else:
                self.page_detail.show_no_screenshots(self.t)
        elif pkg_data.source_type == "aur":
            self.page_detail.show_no_screenshots(self.t)
        else:
            if pkg_data.screenshot_urls:
                self._start_screenshot_downloads(pkg_data.screenshot_urls, gen)
            else:
                loader = LocalAppStreamLoader(pkg_data.name)
                loader.finished.connect(
                    lambda urls, g=gen: self._on_local_appstream_loaded(urls, pkg_data, g)
                )
                loader.start()
                self._screenshot_threads.append(loader)

    def _on_local_appstream_loaded(self, urls, pkg_data, gen):
        if gen != self._screenshot_gen:
            return
        pkg_data.screenshot_urls = urls
        if urls:
            self._start_screenshot_downloads(urls, gen)
        else:
            self.page_detail.show_no_screenshots(self.t)

    def _start_screenshot_downloads(self, urls, gen):
        self.page_detail.clear_screenshots()
        for url in urls[:5]:
            lbl = self.page_detail.add_screenshot_placeholder()
            t = ScreenshotDownloadThread(url)
            t.done.connect(lambda u, path, l=lbl, g=gen: self._on_screenshot_done(u, path, l, g))
            t.start()
            self._screenshot_threads.append(t)

    def _on_screenshot_done(self, _url, path, lbl, gen):
        if gen != self._screenshot_gen:
            return
        if not path:
            try:
                lbl.setText("")
            except RuntimeError:
                pass
            return
        try:
            self.page_detail.set_screenshot_image(lbl, path)
        except RuntimeError:
            pass

    # -------------------------------------------------------------------------
    # Package actions
    # -------------------------------------------------------------------------

    def install_package(self, pkg):
        if pkg.source_type == "flatpak":
            cmd = f"flatpak install -y flathub {pkg.app_id}; echo; read -rp 'Done. Press Enter to close...'"
        elif pkg.source_type == "aur":
            cmd = f"yay -S --noconfirm {pkg.name}; echo; read -rp 'Done. Press Enter to close...'"
        else:
            cmd = f"pkexec pacman -S --noconfirm {pkg.name}; echo; read -rp 'Done. Press Enter to close...'"
        subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])

    def remove_package(self, pkg):
        if pkg.source_type == "flatpak":
            cmd = f"flatpak uninstall -y {pkg.app_id}; echo; read -rp 'Done. Press Enter to close...'"
        else:
            cmd = f"pkexec pacman -Rs --noconfirm {pkg.name}; echo; read -rp 'Done. Press Enter to close...'"
        subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])

    def install_selected_essentials(self):
        if self.selected_essentials:
            pkgs = ' '.join(self.selected_essentials)
            subprocess.Popen(["konsole", "-e", "bash", "-c",
                              f"pkexec pacman -S --noconfirm {pkgs}; "
                              "echo; read -rp 'Done. Press Enter to close...'"])

    def execute_integrity_check(self):
        cmd = (
            "echo '=== System File Integrity Check ==='; echo; "
            "echo '[1/2] Pacman + AUR packages (pacman -Qkk)...'; echo; "
            "result=$(pacman -Qkk 2>&1 | grep -v ': 0 missing files, 0 altered files'); "
            "if [ -z \"$result\" ]; then "
            "  echo 'All pacman/AUR files are intact.'; "
            "else "
            "  echo 'Issues found:'; echo; echo \"$result\"; "
            "fi; "
            "echo; "
            "if command -v flatpak >/dev/null 2>&1; then "
            "  echo '[2/2] Flatpak (flatpak repair --user)...'; echo; "
            "  flatpak repair --user; "
            "else "
            "  echo '[2/2] Flatpak not installed, skipping.'; "
            "fi; "
            "echo; read -rp 'Done. Press Enter to close...'"
        )
        subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])

    def execute_cache_clean(self):
        cmd = (
            "echo '=== Package Cache Cleanup ==='; echo; "
            "echo '[1/3] Pacman cache...'; "
            "if command -v paccache >/dev/null 2>&1; then "
            "  pkexec bash -c 'rm -rf /var/cache/pacman/pkg/download-*; paccache -rvk2; paccache -rvuk0'; "
            "else "
            "  pkexec bash -c 'rm -rf /var/cache/pacman/pkg/download-*; pacman -Sc --noconfirm'; "
            "fi; "
            "echo; "
            "if command -v yay >/dev/null 2>&1; then "
            "  echo '[2/3] AUR build cache (yay)...'; "
            "  yay -Sc --noconfirm; echo; "
            "else "
            "  echo '[2/3] yay not found, skipping AUR cache.'; echo; "
            "fi; "
            "if command -v flatpak >/dev/null 2>&1; then "
            "  echo '[3/3] Flatpak unused runtimes...'; "
            "  flatpak uninstall --unused -y; echo; "
            "else "
            "  echo '[3/3] Flatpak not installed, skipping.'; echo; "
            "fi; "
            "echo 'All done!'; echo; read -rp 'Press Enter to close...'"
        )
        subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])

    def execute_system_update(self):
        cmd = (
            "LOG=$(mktemp /tmp/equestria_update.XXXXXX.log); "
            "yay -Syu --noconfirm 2>&1 | tee \"$LOG\"; "
            "EXIT=${PIPESTATUS[0]}; "
            "if [ $EXIT -ne 0 ] && grep -qE "
            "'Operation too slow|failed to retrieve|не удалось получить' \"$LOG\"; then "
            "  echo; echo '==> Mirror failure detected. Re-ranking mirrors...'; "
            "  COUNTRY=$(curl -s --max-time 5 https://ipinfo.io/country 2>/dev/null | tr -d '\\n\\r'); "
            "  [ -z \"$COUNTRY\" ] && COUNTRY='DE,US,FR,GB'; "
            "  pkexec pg-rankmirrors-backend rank \"$COUNTRY\" "
            "    && echo '==> Mirrors updated. Retrying update...' "
            "    || echo '==> Mirror re-ranking failed, retrying anyway...'; "
            "  echo; "
            "  yay -Syu --noconfirm; "
            "fi; "
            "rm -f \"$LOG\"; "
            "if command -v flatpak >/dev/null; then flatpak update -y; fi; "
            "echo; read -rp 'Done. Press Enter to close...'"
        )
        subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setDesktopFileName("equestria-os-software-center")
    win = main_app()
    win.show()
    sys.exit(app.exec())
