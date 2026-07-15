import sys
import os
import json
import csv
import subprocess
import shutil
import time
import threading

from PyQt6.QtWidgets import (QApplication, QMainWindow, QListWidgetItem,
                              QPushButton, QLabel, QVBoxLayout, QWidget, QComboBox,
                              QMessageBox)
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import (Qt, QThread, QTimer, QFileSystemWatcher, QProcess, QEvent,
                          pyqtSignal)

from models import EssentialData, StoreData
from utils import (FLATPAK_APPSTREAM, cleanup_screenshot_cache,
                   normalize_key, merge_packages, _GENERIC_PACMAN_DESC, guess_cat)
from workers import (AppStoreLoader, FlatpakLoader,
                     AURSearchThread, AURPopularLoader, AURUpgradableLoader,
                     ScreenshotDownloadThread, LocalAppStreamLoader,
                     PacmanInfoLoader)
from ui_software import Ui_SoftwareCenter, EssentialAppRow, StoreAppRow, AppDetailWidget
from settings import load_settings, save_settings, resolve_language
from settings_dialog import SettingsDialog

# All code comments inside the script are written in English as requested

class main_app(QMainWindow, Ui_SoftwareCenter):
    # object, а не int: размер кэша в байтах не влезает в C-int сигнала (16 ГБ > 2^31)
    cache_size_ready = pyqtSignal(object)
    db_refresh_done = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.setupUi(self)
        self.setWindowTitle("Equestria Software Center")

        self.langs = []
        self.localizations = {}

        # Load persistent settings first so language and source flags are ready
        self._settings = load_settings()
        self.current_lang = ""  # resolved after discover_langs()

        self.essentials_data = []
        self.store_packages = []
        self.flatpak_packages = []
        self.aur_packages = []
        self.flatpak_installed = set()
        self.flatpak_upgradable = set()
        self.installed_packages = set()
        self.upgradable_packages = set()
        self.aur_installed = {}
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
        self._aur_all_search_thread = None
        self._aur_all_search_gen = 0
        self._screenshot_threads = []
        self._screenshot_gen = 0
        self._pacman_info_thread = None
        self._vercmp_cache = {}
        self._last_status_refresh = 0.0
        self._cache_size = None  # None = ещё не посчитан, кнопка без размера
        self._db_refresh_running = False

        self.init_resources()
        cleanup_screenshot_cache()
        self.discover_langs()
        
        # Resolve language: saved preference → system locale → "en"
        self.current_lang = resolve_language(self._settings, self.langs)
        self.load_localizations()
        self.refresh_system_status()
        self.load_essentials_csv()
        self.setup_logic()
        self.update_ui_texts()

        self.cache_size_ready.connect(self.on_cache_size_ready)
        self.refresh_cache_size()
        self.db_refresh_done.connect(self._on_refresh_db_finished)

        if self.needs_pacman_init():
            self.run_pacman_init()
        else:
            self.start_loaders()
            self._check_db_staleness()

    # -------------------------------------------------------------------------
    # Startup helpers
    # -------------------------------------------------------------------------

    def needs_pacman_init(self):
        """Проверяет кэш pacman. Возвращает True, если баз нет."""
        sync_dir = "/var/lib/pacman/sync"
        return not os.path.exists(sync_dir) or not any(f.endswith('.db') for f in os.listdir(sync_dir))

    # Каталог App Store читает ТОЛЬКО локально синхронизированные базы
    # pacman — свежий пакет в репозитории останется невидимым, пока кто-то
    # не запустит 'pacman -Sy'. Раньше это происходило только при самом первом
    # запуске (когда баз ещё не было вообще), и дальше требовало терминала.
    DB_STALE_HOURS = 24

    def _sync_db_age_hours(self):
        sync_dir = "/var/lib/pacman/sync"
        try:
            dbs = [f for f in os.listdir(sync_dir) if f.endswith(".db")]
            if not dbs:
                return None
            newest = max(os.path.getmtime(os.path.join(sync_dir, f)) for f in dbs)
            return (time.time() - newest) / 3600
        except OSError:
            return None

    def _check_db_staleness(self):
        age = self._sync_db_age_hours()
        if age is not None and age >= self.DB_STALE_HOURS:
            self.db_stale_lbl.setText(self.t("ui.db_stale").format(int(age)))
            self.db_stale_banner.show()
        else:
            self.db_stale_banner.hide()

    def refresh_pacman_db(self):
        """Ручное обновление баз pacman (кнопка/баннер) — без полного
        'Update System': только синхронизация, установленные пакеты не трогает.

        Запускается в Konsole тем же способом, что и 'Update System' и
        'Clean Package Cache' в этом приложении — subprocess.Popen без
        отслеживания через QProcess. Это НЕ случайность: дочерний процесс
        на Linux переживает закрытие родителя (проверено эмпирически),
        так что закрытие Software Center или переход на другую страницу
        Настроек не прерывает синхронизацию — она просто закончится в уже
        открытом окне Konsole."""
        if self._db_refresh_running:
            return
        self._db_refresh_running = True

        self.btn_refresh_db.setEnabled(False)
        self.btn_refresh_db_banner.setEnabled(False)
        self.db_stale_lbl.setText(self.t("ui.refresh_db_running"))
        self.db_refresh_progress.show()
        self.db_stale_banner.show()

        cmd = (
            "echo '=== Refreshing package database (pacman -Sy) ==='; echo; "
            "pkexec pacman -Sy --noconfirm; "
            "echo; read -rp 'Done. Press Enter to close...'"
        )
        proc = subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])

        def _wait():
            ok = proc.wait() == 0
            self.db_refresh_done.emit(ok)
        threading.Thread(target=_wait, daemon=True).start()

    def _on_refresh_db_finished(self, ok: bool):
        self._db_refresh_running = False
        self.btn_refresh_db.setEnabled(True)
        self.btn_refresh_db_banner.setEnabled(True)
        self.db_refresh_progress.hide()

        if ok:
            self.db_stale_banner.hide()
            self.start_loaders()
            self.refresh_system_status()
        else:
            self.db_stale_lbl.setText(self.t("ui.refresh_db_error"))

    def run_pacman_init(self):
        """Запускает обновление баз в konsole и ждет завершения."""
        self.store_loading_lbl.setText("Initialising database... Please wait for Konsole.")
        self.store_loading_lbl.show()

        cmd = (
            "echo 'First start loading: initializing pacman database...'; "
            "pkexec pacman -Sy --noconfirm; "
            "echo; read -rp 'Database has been updated! Press Enter to close...'"
        )

        self._init_process = QProcess(self)
        self._init_process.finished.connect(self.start_loaders)
        self._init_process.start("konsole", ["-e", "bash", "-c", cmd])

    def start_loaders(self):
        """Запускает все рабочие потоки для получения данных."""
        self.store_loading_lbl.setText(self.t("ui.loading"))

        self.loader = AppStoreLoader()
        self.loader.finished.connect(self.on_store_loaded)
        self.loader.start()

        if (self._settings.get("enable_flatpak", True)
                and shutil.which("flatpak") and os.path.exists(FLATPAK_APPSTREAM)):
            self.flatpak_loader = FlatpakLoader()
            self.flatpak_loader.finished.connect(self.on_flatpak_loaded)
            self.flatpak_loader.start()

        if self._settings.get("enable_aur", True):
            self._aur_popular_thread = AURPopularLoader()
            self._aur_popular_thread.finished.connect(self._on_aur_popular_loaded)
            self._aur_popular_thread.start()

        # Проверка обновлений AUR идёт всегда: enable_aur выключает только
        # автообновление, но установленные AUR-пакеты должны показывать
        # свои обновления в любом случае.
        self._aur_upgradable_loader = AURUpgradableLoader()
        self._aur_upgradable_loader.finished.connect(self._on_aur_upgradable_loaded)
        self._aur_upgradable_loader.start()

        self._flatpak_watcher = QFileSystemWatcher()
        flatpak_dir = os.path.dirname(FLATPAK_APPSTREAM)
        if os.path.exists(flatpak_dir):
            self._flatpak_watcher.addPath(flatpak_dir)
        self._flatpak_watcher.directoryChanged.connect(self._on_flatpak_dir_changed)

    def closeEvent(self, event):
        threads = [
            getattr(self, '_aur_search_thread', None),
            getattr(self, '_aur_popular_thread', None),
            getattr(self, '_aur_all_search_thread', None),
            getattr(self, '_aur_upgradable_loader', None),
            getattr(self, '_pacman_info_thread', None),
            getattr(self, 'loader', None),
            getattr(self, 'flatpak_loader', None),
        ]
        threads += getattr(self, '_screenshot_threads', [])
        for t in threads:
            if t is not None and t.isRunning():
                t.quit()
                t.wait(500)
        event.accept()

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
                # Qt's QSS url() treats a bare local path literally rather than
                # percent-decoding it, so %20-escaping spaces actually breaks
                # local file resolution (verified) -- pass the raw path.
                base = self.base_path.replace("\\", "/")
                qss = (f.read()
                       .replace("{{TITLE_FONT}}", f'"{self.custom_font_family}"')
                       .replace("{{BASE_PATH}}", base))
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

            res_foreign = subprocess.run(["pacman", "-Qm"], capture_output=True, text=True)
            self.aur_installed = {}
            for line in res_foreign.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    self.aur_installed[parts[0]] = parts[1]

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

    def event(self, e):
        # After installs/updates run in a detached konsole, statuses go stale;
        # re-read system state whenever the window regains focus.
        if e.type() == QEvent.Type.WindowActivate:
            self._refresh_status_throttled()
        return super().event(e)

    def _refresh_status_throttled(self):
        now = time.monotonic()
        if now - self._last_status_refresh < 10:
            return
        self._last_status_refresh = now

        old_aur_installed = dict(self.aur_installed)
        # pacman -Qu never sees AUR packages, so their upgradable flags
        # (found by yay at startup) must survive the refresh — but only
        # while the installed version is unchanged.
        aur_flagged = {n for n in self.upgradable_packages if n in old_aur_installed}
        self.refresh_system_status()
        self.upgradable_packages |= {
            n for n in aur_flagged
            if self.aur_installed.get(n) == old_aur_installed.get(n)
        }

        self.load_essentials_csv()
        if self.store_packages or self.aur_packages:
            self.filter_store()

    def _compute_status(self, pkg):
        """Sets pkg.status from the current installed/upgradable system state."""
        if pkg.source_type == "flatpak":
            if pkg.app_id in self.flatpak_upgradable:
                pkg.status = "upgradable"
            elif pkg.app_id in self.flatpak_installed:
                pkg.status = "installed"
            else:
                pkg.status = "available"
            return
        if pkg.name in self.upgradable_packages:
            pkg.status = "upgradable"
        elif pkg.name in self.installed_packages:
            if pkg.source_type == "aur" and self._aur_version_newer(pkg.name, pkg.version):
                pkg.status = "upgradable"
            else:
                pkg.status = "installed"
        else:
            pkg.status = "available"

    def _aur_version_newer(self, name, rpc_version):
        """Fallback update check: AUR RPC version vs installed (pacman -Qm).

        Covers the window before/without `yay -Qu --aur` results.
        """
        installed = self.aur_installed.get(name)
        if not installed or not rpc_version or installed == rpc_version:
            return False
        key = (rpc_version, installed)
        cached = self._vercmp_cache.get(key)
        if cached is None:
            cached = False
            try:
                res = subprocess.run(["vercmp", rpc_version, installed],
                                     capture_output=True, text=True)
                cached = int(res.stdout.strip() or 0) > 0
            except Exception:
                pass
            self._vercmp_cache[key] = cached
        return cached

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
        self.btn_refresh_db.clicked.connect(self.refresh_pacman_db)
        self.btn_refresh_db_banner.clicked.connect(self.refresh_pacman_db)

        # FIXED: Create an elegant Dropdown selection for the left sidebar area
        self.lang_dropdown = QComboBox()
        self.lang_dropdown.setObjectName("CategoryDropdown") # Inherits default styling framework cleanly
        for lang in self.langs:
            self.lang_dropdown.addItem(lang.upper(), lang)
        
        # Set accurate visual marker mapping current system state index
        idx = self.lang_dropdown.findData(self.current_lang)
        if idx != -1:
            self.lang_dropdown.setCurrentIndex(idx)
        self.lang_dropdown.currentIndexChanged.connect(self._on_main_lang_dropdown_changed)
        
        # Insert dropdown into the layout container grid panel
        self.lang_layout.addWidget(self.lang_dropdown, 0, 0)

        # FIXED: Cleanly inject settings action trigger directly into the navigation layout container
        self._btn_settings = QPushButton("⚙  " + self.t("settings.title"))
        self._btn_settings.setObjectName("NavBtn") # Matches visual alignment patterns perfectly
        self._btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_settings.clicked.connect(self.open_settings_dialog)
        
        if hasattr(self, 'left_panel') and self.left_panel.layout() is not None:
            # Structurally stacks the item right above system diagnostic button sets
            self.left_panel.layout().insertWidget(self.left_panel.layout().count() - 3, self._btn_settings)

        self.page_detail = AppDetailWidget(self._go_back_from_detail)
        self.stacked_widget.addWidget(self.page_detail)

    def _on_main_lang_dropdown_changed(self):
        """Monitors sidebar language selector transactions to sync UI localized fields."""
        selected_lang = self.lang_dropdown.currentData()
        if not selected_lang or selected_lang == self.current_lang:
            return
        self.current_lang = selected_lang
        self._settings["language"] = self.current_lang
        save_settings(self._settings)
        self.load_localizations()
        self.update_ui_texts()
        self.load_essentials_csv()
        if self.store_packages:
            self.filter_store()

    def change_language(self):
        # Legacy stub preserved to avoid external reference disruptions
        pass

    def open_settings_dialog(self):
        dlg = SettingsDialog(
            parent=self,
            settings=self._settings,
            available_langs=self.langs,
            t=self.t,
            on_save=self._apply_settings,
        )
        dlg.exec()

    def _apply_settings(self, new_settings: dict):
        old_enable_aur = self._settings.get("enable_aur", True)
        old_enable_flatpak = self._settings.get("enable_flatpak", True)

        self._settings = new_settings
        save_settings(self._settings)

        # Language payload updates tracking
        new_lang = resolve_language(new_settings, self.langs)
        if new_lang != self.current_lang:
            self.current_lang = new_lang
            self.load_localizations()
            self.update_ui_texts()
            self.load_essentials_csv()
            if self.store_packages:
                self.filter_store()
            
            # FIXED: Synchronize main UI dropdown selection index seamlessly
            self.lang_dropdown.blockSignals(True)
            idx = self.lang_dropdown.findData(self.current_lang)
            if idx != -1:
                self.lang_dropdown.setCurrentIndex(idx)
            self.lang_dropdown.blockSignals(False)

        # Source runtime validation tracking flags updates
        enable_aur = new_settings.get("enable_aur", True)
        enable_flatpak = new_settings.get("enable_flatpak", True)

        if enable_aur and not old_enable_aur:
            if not self._aur_popular_cached:
                self._aur_popular_thread = AURPopularLoader()
                self._aur_popular_thread.finished.connect(self._on_aur_popular_loaded)
                self._aur_popular_thread.start()
            self._aur_upgradable_loader = AURUpgradableLoader()
            self._aur_upgradable_loader.finished.connect(self._on_aur_upgradable_loaded)
            self._aur_upgradable_loader.start()
        elif not enable_aur and old_enable_aur:
            self._aur_popular_cached = []
            self._aur_query_cache = {}
            self.aur_packages = []
            self._rebuild_merged()
            self.filter_store()

        if enable_flatpak and not old_enable_flatpak:
            if shutil.which("flatpak") and os.path.exists(FLATPAK_APPSTREAM):
                self.flatpak_loader = FlatpakLoader()
                self.flatpak_loader.finished.connect(self.on_flatpak_loaded)
                self.flatpak_loader.start()
        elif not enable_flatpak and old_enable_flatpak:
            self.flatpak_packages = []
            self._rebuild_merged()
            self.filter_store()

    def update_ui_texts(self):
        self.cat_header.setText(self.t("ui.essentials_header"))
        self.store_header.setText(self.t("ui.store_header"))
        self.btn_switch_store.setText(self.t("ui.search_all"))
        self.btn_integrity_check.setText(self.t("ui.integrity_check"))
        self.apply_cache_btn_text()
        self.btn_update_sys.setText(self.t("ui.update_all"))
        self.search_store.setPlaceholderText(self.t("ui.search_placeholder"))
        self.btn_prev_page.setText(self.t("ui.prev_page"))
        self.btn_next_page.setText(self.t("ui.next_page"))
        self.store_loading_lbl.setText(self.t("ui.loading"))
        
        # FIXED: Update internal configurations overlay button label smoothly
        if hasattr(self, "_btn_settings"):
            self._btn_settings.setText("⚙  " + self.t("settings.title"))

        self.combo_source.blockSignals(True)
        self.combo_source.setItemText(0, self.t("ui.source_all"))
        self.combo_source.setItemText(1, self.t("ui.source_pacman"))
        self.combo_source.setItemText(2, self.t("ui.source_aur"))
        self.combo_source.setItemText(3, self.t("ui.source_flatpak"))
        self.combo_source.setItemText(4, self.t("ui.source_updates"))
        self.combo_source.blockSignals(False)
        self.update_install_button_text()

        if not self._db_refresh_running:
            self.btn_refresh_db.setText(self.t("ui.refresh_db_sidebar_btn"))
        self.btn_refresh_db.setToolTip(self.t("ui.refresh_db_tooltip"))
        self.btn_refresh_db_banner.setText(self.t("ui.refresh_db_btn"))
        if self.db_stale_banner.isVisible() and not self._db_refresh_running:
            self._check_db_staleness()

    def on_cat_clicked(self, item):
        self.stacked_widget.setCurrentIndex(0)
        self.render_essentials(item.data(Qt.ItemDataRole.UserRole))

    # -------------------------------------------------------------------------
    # Store data loading
    # -------------------------------------------------------------------------

    def _rebuild_merged(self):
        self._merged_packages = merge_packages(self.store_packages, self.flatpak_packages)
        if self._aur_popular_cached:
            pacman_names = {normalize_key(p.name) for p in self.store_packages}
            for aur_pkg in self._aur_popular_cached:
                if normalize_key(aur_pkg.name) not in pacman_names:
                    self._merged_packages.append(aur_pkg)

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
            if self._current_source == "all" and text.strip():
                if self._aur_debounce_timer:
                    self._aur_debounce_timer.stop()
                self._aur_debounce_timer = QTimer()
                self._aur_debounce_timer.setSingleShot(True)
                self._aur_debounce_timer.timeout.connect(
                    lambda t=text.strip(): self._trigger_aur_search_for_all(t)
                )
                self._aur_debounce_timer.start(600)

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
            query = self.search_store.text().strip()
            if query and query in self._aur_query_cache:
                self._append_aur_to_all(self._aur_query_cache[query])
        else:
            self._filter_packages(self.store_packages, source)

    @staticmethod
    def _norm(s):
        return s.lower().replace('-', ' ').replace('_', ' ').replace('.', ' ')

    def _filter_packages(self, packages, source="all"):
        query = self.search_store.text().lower().strip()
        query_norm = self._norm(query)
        cat = self.combo_store.currentText()
        self.filtered_store_packages = []

        for pkg in packages:
            self._compute_status(pkg)

            if source == "updates" and pkg.status != "upgradable":
                continue
            if query:
                name_norm = self._norm(pkg.name)
                desc_norm = self._norm(pkg.desc)
                if (query not in pkg.name.lower() and query_norm not in name_norm
                        and query not in pkg.desc.lower() and query_norm not in desc_norm):
                    continue
            if cat != "All" and pkg.category != cat:
                continue
            self.filtered_store_packages.append(pkg)

        if source == "updates":
            covered = {p.name for p in self.filtered_store_packages}
            for name, version in self.aur_installed.items():
                if name not in self.upgradable_packages or name in covered:
                    continue
                pkg = StoreData(name, version, "AUR package", "AUR", source_type="aur")
                pkg.status = "upgradable"
                pkg.category = guess_cat(name)
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
            for pkg in pkgs:
                self._compute_status(pkg)
            self.aur_packages = pkgs
            self.filtered_store_packages = list(pkgs)
            self.current_page = 1
            self.render_store_page()
        else:
            self._rebuild_merged()
            if self._current_source == "all":
                self.filter_store()

    def _on_aur_upgradable_loaded(self, pkgs):
        if pkgs:
            self.upgradable_packages |= pkgs
            self.filter_store()

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
        if gen != self._aur_search_gen or self._current_source != "aur":
            return
        for pkg in pkgs:
            self._compute_status(pkg)
        self.aur_packages = pkgs
        self.filtered_store_packages = list(pkgs)
        self.current_page = 1
        self.render_store_page()

    def _trigger_aur_search_for_all(self, query):
        if self._current_source != "all" or not query:
            return
        if query in self._aur_query_cache:
            self._append_aur_to_all(self._aur_query_cache[query])
            return
        self._aur_all_search_gen += 1
        gen = self._aur_all_search_gen
        self._aur_all_search_thread = AURSearchThread(query)
        self._aur_all_search_thread.finished.connect(
            lambda pkgs, g=gen, q=query: self._on_aur_results_for_all(pkgs, g, q)
        )
        self._aur_all_search_thread.start()

    def _on_aur_results_for_all(self, pkgs, gen, query):
        if gen != self._aur_all_search_gen or self._current_source != "all":
            return
        if query != self.search_store.text().strip():
            return
        self._aur_query_cache[query] = pkgs
        self._append_aur_to_all(pkgs)

    def _append_aur_to_all(self, aur_pkgs):
        if self._current_source != "all":
            return
        cat = self.combo_store.currentText()
        existing = {normalize_key(p.name) for p in self.filtered_store_packages}
        added = False
        for pkg in aur_pkgs:
            if normalize_key(pkg.name) not in existing:
                if cat != "All" and pkg.category != cat:
                    continue
                self._compute_status(pkg)
                self.filtered_store_packages.append(pkg)
                added = True
        if added:
            self.render_store_page()

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def _show_store_message(self, msg):
        # store_loading_lbl must survive: update_ui_texts() calls setText on it
        while self.layout_store.count() > 0:
            item = self.layout_store.takeAt(0)
            if item.widget() and item.widget() != self.store_loading_lbl:
                item.widget().deleteLater()
        self.store_loading_lbl.hide()
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
        if total == 0 and not self.store_loading_lbl.isVisible():
            key = "ui.no_updates" if self._current_source == "updates" else "ui.nothing_found"
            lbl = QLabel(self.t(key))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #a6adc8; font-size: 16px;")
            self.layout_store.addWidget(lbl)
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

        for p in alts.values():
            self._compute_status(p)

        self.page_detail.load_package_group(
            alts_dict=alts,
            default_source=pkg_data.source_type,
            t_func=self.t,
            installed_set=self.installed_packages,
            flatpak_installed_set=self.flatpak_installed,
            upgradable_set=self.upgradable_packages,
            flatpak_upgradable_set=self.flatpak_upgradable,
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
            if getattr(pkg, 'status', '') == "upgradable":
                cmd = f"flatpak update -y {pkg.app_id}; echo; read -rp 'Done. Press Enter to close...'"
            else:
                cmd = f"flatpak install -y flathub {pkg.app_id}; echo; read -rp 'Done. Press Enter to close...'"
        elif pkg.source_type == "aur":
            cmd = f"yay -S --noconfirm {pkg.name}; echo; read -rp 'Done. Press Enter to close...'"
        else:
            if getattr(pkg, 'status', '') == "upgradable":
                cmd = f"pkexec pacman -Syu --noconfirm {pkg.name}; echo; read -rp 'Done. Press Enter to close...'"
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

    def fmt_size(self, n):
        units = {"ru": ["Б", "КБ", "МБ", "ГБ"],
                 "uk": ["Б", "КБ", "МБ", "ГБ"]}.get(self.current_lang, ["B", "KB", "MB", "GB"])
        size = float(n)
        unit = units[0]
        for unit in units:
            if size < 1024 or unit == units[-1]:
                break
            size /= 1024
        return f"{int(size)} {unit}" if unit == units[0] else f"{size:.1f} {unit}"

    @staticmethod
    def calc_cache_size():
        """Суммарный размер кэша пакетов: /var/cache/pacman/pkg + ~/.cache/yay."""
        total = 0
        try:
            with os.scandir("/var/cache/pacman/pkg") as it:
                for e in it:
                    try:
                        if e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
        yay_dir = os.path.expanduser("~/.cache/yay")
        for root, dirs, files in os.walk(yay_dir, onerror=lambda e: None):
            for f in files:
                try:
                    total += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
        return total

    def refresh_cache_size(self):
        threading.Thread(
            target=lambda: self.cache_size_ready.emit(self.calc_cache_size()),
            daemon=True).start()

    def on_cache_size_ready(self, size):
        self._cache_size = size
        self.apply_cache_btn_text()

    def apply_cache_btn_text(self):
        if self._cache_size:
            self.btn_cache_clean.setText(
                self.t("ui.cache_clean_size").replace("{0}", self.fmt_size(self._cache_size)))
        else:
            self.btn_cache_clean.setText(self.t("ui.cache_clean"))

    def execute_cache_clean(self):
        # Обычная очистка оставляет копии установленных версий (у pacman это
        # страховка для отката без интернета) — поэтому даём выбор режима.
        box = QMessageBox(self)
        box.setWindowTitle(self.t("ui.cache_clean"))
        size_txt = self.fmt_size(self._cache_size) if self._cache_size else "?"
        box.setText(self.t("cache.mode_text").replace("{0}", size_txt))
        btn_normal = box.addButton(self.t("cache.mode_normal"), QMessageBox.ButtonRole.AcceptRole)
        btn_full = box.addButton(self.t("cache.mode_full"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = box.addButton(self.t("ui.cancel"), QMessageBox.ButtonRole.RejectRole)
        # Системный QMessageBox светлый — натягиваем стили приложения (см. style.qss)
        btn_normal.setObjectName("DetailActionBtn")
        btn_full.setObjectName("CacheCleanBtn")
        btn_cancel.setObjectName("DetailBackBtn")
        for b in (btn_normal, btn_full, btn_cancel):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumSize(110, 36)
            # QSS по objectName не применится без переполировки: имя задано после создания
            b.style().unpolish(b)
            b.style().polish(b)
        box.exec()
        if box.clickedButton() is not btn_normal and box.clickedButton() is not btn_full:
            return

        if box.clickedButton() is btn_full:
            # Полная: весь кэш pacman, включая копии установленных пакетов
            pacman_step = (
                "if command -v paccache >/dev/null 2>&1; then "
                "  pkexec bash -c 'rm -rf /var/cache/pacman/pkg/download-*; paccache -rvk0'; "
                "else "
                # pacman -Scc --noconfirm отвечает на вопрос по умолчанию «нет» — не подходит
                "  pkexec bash -c 'rm -rf /var/cache/pacman/pkg/download-*; "
                "find /var/cache/pacman/pkg -maxdepth 1 -type f -name \"*.pkg.tar*\" -delete'; "
                "fi; "
            )
        else:
            pacman_step = (
                "if command -v paccache >/dev/null 2>&1; then "
                "  pkexec bash -c 'rm -rf /var/cache/pacman/pkg/download-*; paccache -rvk2; paccache -rvuk0'; "
                "else "
                "  pkexec bash -c 'rm -rf /var/cache/pacman/pkg/download-*; pacman -Sc --noconfirm'; "
                "fi; "
            )

        cmd = (
            "echo '=== Package Cache Cleanup ==='; echo; "
            "echo '[1/3] Pacman cache...'; "
            + pacman_step +
            "echo; "
            "if command -v yay >/dev/null 2>&1; then "
            "  echo '[2/3] AUR build cache (yay)...'; "
            "  yay -Sc --noconfirm; "
            "  echo 'Removing yay build directory (~/.cache/yay)...'; "
            "  rm -rf ~/.cache/yay/; echo 'Done.'; echo; "
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
        proc = subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])

        # Когда konsole закрыта — пересчитать размер на кнопке
        def _wait_and_rescan():
            proc.wait()
            self.refresh_cache_size()
        threading.Thread(target=_wait_and_rescan, daemon=True).start()

    def execute_system_update(self):
        do_pacman = self._settings.get("update_pacman", True)
        do_aur = self._settings.get("update_aur", True) and self._settings.get("enable_aur", True)
        do_flatpak = (self._settings.get("update_flatpak", True)
                      and self._settings.get("enable_flatpak", True))

        steps = []
        step_n = 0

        if do_pacman:
            step_n += 1
            steps.append(
                f"echo '==> [{step_n}] Updating official repositories (pacman)...'; echo; "
                "LOG=$(mktemp /tmp/equestria_update.XXXXXX.log); "
                "pkexec pacman -Syu --noconfirm 2>&1 | tee \"$LOG\"; "
                "EXIT=${PIPESTATUS[0]}; "
                "if [ $EXIT -ne 0 ] && grep -qE "
                "'Operation too slow|failed to retrieve|не удалось получить' \"$LOG\"; then "
                "  echo; echo '==> Mirror failure detected. Re-ranking mirrors...'; "
                "  COUNTRY=$(curl -s --max-time 5 https://ipinfo.io/country 2>/dev/null | tr -d '\\n\\r'); "
                "  [ -z \"$COUNTRY\" ] && COUNTRY='DE,US,FR,GB'; "
                "  pkexec pg-rankmirrors-backend rank \"$COUNTRY\" "
                "    && echo '==> Mirrors updated. Retrying...' || true; "
                "  echo; pkexec pacman -Syu --noconfirm 2>&1 | tee \"$LOG\"; EXIT=${PIPESTATUS[0]}; "
                "fi; "
                "if [ $EXIT -ne 0 ] && grep -q 'are in conflict' \"$LOG\"; then "
                "  echo; echo '==> Package conflict detected. Resolving automatically...'; "
                "  CONFLICT_PKGS=$(grep -oP '(?<=Remove )[^?]+' \"$LOG\" | tr -d ' ' | tr '\\n' ' '); "
                "  if [ -n \"$CONFLICT_PKGS\" ]; then "
                "    pkexec pacman -Rdd --noconfirm $CONFLICT_PKGS; "
                "    echo '==> Retrying update...'; echo; "
                "    pkexec pacman -Syu --noconfirm 2>&1 | tee \"$LOG\"; "
                "  fi; "
                "fi; "
                "rm -f \"$LOG\"; echo; "
            )

        if do_aur:
            step_n += 1
            steps.append(
                f"echo '==> [{step_n}] Updating AUR packages (yay)...'; echo; "
                "if command -v yay >/dev/null 2>&1; then "
                "  AUR_PKGS=$(yay -Qua 2>/dev/null | awk '{print $1}'); "
                "  if [ -n \"$AUR_PKGS\" ]; then "
                "    for pkg in $AUR_PKGS; do "
                "      echo \"-- $pkg\"; "
                "      yay -S --noconfirm \"$pkg\" "
                "        || echo \"==> Warning: $pkg skipped (build/dependency error)\"; "
                "      echo; "
                "    done; "
                "  else "
                "    echo 'AUR packages are up to date.'; "
                "  fi; "
                "else "
                "  echo 'yay not found — skipping AUR update.'; "
                "fi; echo; "
            )

        if do_flatpak:
            step_n += 1
            steps.append(
                f"echo '==> [{step_n}] Updating Flatpak apps...'; echo; "
                "if command -v flatpak >/dev/null 2>&1; then "
                "  flatpak update -y; "
                "else "
                "  echo 'flatpak not installed — skipping.'; "
                "fi; echo; "
            )

        if not steps:
            cmd = "echo 'No update sources are enabled. Enable at least one in Settings.'; echo; read -rp 'Press Enter to close...'"
        else:
            total = step_n
            cmd = (
                f"echo '=== Equestria OS System Update ({total} step(s)) ==='; echo; "
                + "".join(steps)
                + "echo 'All done!'; echo; read -rp 'Done. Press Enter to close...'"
            )

        subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setDesktopFileName("equestria-os-software-center")
    win = main_app()
    win.show()
    sys.exit(app.exec())