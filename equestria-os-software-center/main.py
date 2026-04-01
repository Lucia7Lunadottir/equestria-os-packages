import sys, os, json, csv, subprocess, gzip, hashlib, shutil, datetime
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.parse import quote
from PyQt6.QtWidgets import (QApplication, QMainWindow, QListWidgetItem, QPushButton,
                              QLabel, QVBoxLayout, QWidget)
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QFileSystemWatcher
from ui_software import Ui_SoftwareCenter, EssentialAppRow, StoreAppRow, AppDetailWidget

FLATPAK_APPSTREAM = "/var/lib/flatpak/appstream/flathub/x86_64/active/appstream.xml.gz"
FLATPAK_ICONS_DIR = "/var/lib/flatpak/appstream/flathub/x86_64/active/icons/128x128"
SCREENSHOT_CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".cache", "equestria-os-software-center", "screenshots"
)


class EssentialData:
    def __init__(self, pkg, display, cat, desc):
        self.package_name = pkg
        self.display_name = display
        self.category_key = cat.strip()
        self.desc_key = desc
        self.is_selected = False
        self.is_installed = False


class StoreData:
    def __init__(self, name, version, desc, source,
                 source_type="pacman", app_id=None,
                 icon_url=None, screenshot_urls=None):
        self.name = name
        self.version = version
        self.desc = desc
        self.source = source
        self.category = "Software"
        self.status = "available"
        self.source_type = source_type   # "pacman" | "aur" | "flatpak"
        self.app_id = app_id             # Flatpak app ID
        self.icon_url = icon_url
        self.screenshot_urls = screenshot_urls or []


def _cleanup_screenshot_cache():
    if not os.path.exists(SCREENSHOT_CACHE_DIR):
        return
    cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
    for fname in os.listdir(SCREENSHOT_CACHE_DIR):
        fpath = os.path.join(SCREENSHOT_CACHE_DIR, fname)
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff:
                os.remove(fpath)
        except Exception:
            pass


def _extract_appstream_text(el):
    parts = []
    if el.text:
        t = el.text.strip()
        if t:
            parts.append(t)
    for child in el:
        child_text = _extract_appstream_text(child)
        if child_text:
            parts.append(child_text)
        if child.tail:
            t = child.tail.strip()
            if t:
                parts.append(t)
    return " ".join(parts)


def guess_cat(n):
    n = n.lower()
    if any(x in n for x in ["game", "steam", "lutris", "wine"]): return "Games"
    if any(x in n for x in ["browser", "firefox", "network", "chat", "discord"]): return "Internet"
    if any(x in n for x in ["vlc", "audio", "video", "media", "music"]): return "Media"
    if any(x in n for x in ["image", "photo", "gimp", "graphics"]): return "Graphics"
    if any(x in n for x in ["nvidia", "mesa", "driver", "kernel"]): return "Drivers"
    return "Software"


# ---------------------------------------------------------------------------
# Background threads
# ---------------------------------------------------------------------------

class FlatpakLoader(QThread):
    finished = pyqtSignal(list)

    def run(self):
        pkgs = []
        if not shutil.which("flatpak") or not os.path.exists(FLATPAK_APPSTREAM):
            self.finished.emit(pkgs)
            return
        try:
            with gzip.open(FLATPAK_APPSTREAM, 'rb') as f:
                data = f.read()
            root = ET.fromstring(data)
            for comp in root.findall('.//component'):
                try:
                    app_id_el = comp.find('id')
                    if app_id_el is None or not app_id_el.text:
                        continue
                    app_id = app_id_el.text

                    # Name — prefer no-lang (default English)
                    name = None
                    for n_el in comp.findall('name'):
                        lang = n_el.get('{http://www.w3.org/XML/1998/namespace}lang')
                        if lang is None and n_el.text:
                            name = n_el.text
                            break
                    if not name:
                        for n_el in comp.findall('name'):
                            if n_el.text:
                                name = n_el.text
                                break
                    if not name:
                        name = app_id

                    # Version
                    version = ""
                    releases = comp.find('releases')
                    if releases is not None:
                        rel = releases.find('release')
                        if rel is not None:
                            version = rel.get('version', '')

                    # Description
                    desc = ""
                    desc_el = comp.find('description')
                    if desc_el is not None:
                        desc = _extract_appstream_text(desc_el)[:200]

                    # Local icon from flatpak cache
                    icon_url = None
                    icon_file = os.path.join(FLATPAK_ICONS_DIR, f"{app_id}.png")
                    if os.path.exists(icon_file):
                        icon_url = icon_file

                    # Screenshots (up to 5, prefer thumbnail <= 800px)
                    screenshot_urls = []
                    screenshots_el = comp.find('screenshots')
                    if screenshots_el is not None:
                        for ss in screenshots_el.findall('screenshot')[:5]:
                            best_url = None
                            for img in ss.findall('image'):
                                img_type = img.get('type', '')
                                try:
                                    w = int(img.get('width', '0') or '0')
                                except ValueError:
                                    w = 0
                                if img_type == 'thumbnail' and w <= 800 and img.text:
                                    best_url = img.text
                                    break
                            if not best_url:
                                img = ss.find('image')
                                if img is not None and img.text:
                                    best_url = img.text
                            if best_url:
                                screenshot_urls.append(best_url)

                    pkg = StoreData(name, version, desc or "Flathub application", "Flathub",
                                    source_type="flatpak", app_id=app_id,
                                    icon_url=icon_url, screenshot_urls=screenshot_urls)
                    pkg.category = guess_cat(name)
                    pkgs.append(pkg)
                except Exception:
                    continue
        except Exception:
            pass
        self.finished.emit(pkgs)


class AURSearchThread(QThread):
    finished = pyqtSignal(list)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        pkgs = []
        try:
            url = f"https://aur.archlinux.org/rpc/v5/search/{quote(self.query)}"
            req = Request(url, headers={'User-Agent': 'equestria-os-software-center/1.0'})
            with urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            for item in data.get('results', [])[:100]:
                pkg = StoreData(
                    item.get('Name', ''),
                    item.get('Version', ''),
                    item.get('Description') or 'AUR package',
                    'AUR',
                    source_type='aur'
                )
                pkg.category = guess_cat(pkg.name)
                pkgs.append(pkg)
        except Exception:
            pass
        self.finished.emit(pkgs)


class ScreenshotDownloadThread(QThread):
    done = pyqtSignal(str, str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        os.makedirs(SCREENSHOT_CACHE_DIR, exist_ok=True)
        sha = hashlib.sha256(self.url.encode()).hexdigest()
        local_path = os.path.join(SCREENSHOT_CACHE_DIR, f"{sha}.jpg")
        if os.path.exists(local_path):
            self.done.emit(self.url, local_path)
            return
        try:
            req = Request(self.url, headers={'User-Agent': 'equestria-os-software-center/1.0'})
            with urlopen(req, timeout=15) as resp:
                with open(local_path, 'wb') as f:
                    f.write(resp.read())
            self.done.emit(self.url, local_path)
        except Exception:
            pass


class LocalAppStreamLoader(QThread):
    finished = pyqtSignal(list)

    def __init__(self, pkg_name):
        super().__init__()
        self.pkg_name = pkg_name

    def run(self):
        urls = []
        search_dirs = ['/usr/share/metainfo', '/usr/share/appdata']
        found_file = None
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                if self.pkg_name in fname and fname.endswith('.xml'):
                    found_file = os.path.join(d, fname)
                    break
            if found_file:
                break
        if not found_file:
            self.finished.emit(urls)
            return
        try:
            tree = ET.parse(found_file)
            root = tree.getroot()
            screenshots_el = root.find('screenshots')
            if screenshots_el is not None:
                for ss in screenshots_el.findall('screenshot')[:5]:
                    for img in ss.findall('image'):
                        if img.text:
                            urls.append(img.text)
                            break
        except Exception:
            pass
        self.finished.emit(urls)


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
                    d.category = guess_cat(p[1])
                    pkgs.append(d)
        except Exception:
            pass
        self.finished.emit(pkgs)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

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
        self.flatpak_packages = []
        self.aur_packages = []
        self.flatpak_installed = set()
        self.installed_packages = set()
        self.upgradable_packages = set()
        self.selected_essentials = set()

        self.filtered_store_packages = []
        self.current_page = 1
        self.items_per_page = 50

        self._current_source = "all"
        self._aur_search_thread = None
        self._aur_debounce_timer = None
        self._aur_search_gen = 0
        self._screenshot_threads = []

        self.init_resources()
        _cleanup_screenshot_cache()
        self.discover_langs()
        self.load_localizations()
        self.refresh_system_status()
        self.load_essentials_csv()
        self.setup_logic()
        self.update_ui_texts()

        self.loader = AppStoreLoader()
        self.loader.finished.connect(self.on_store_loaded)
        self.loader.start()

        # Start Flatpak loader if binary and cache are present
        if shutil.which("flatpak") and os.path.exists(FLATPAK_APPSTREAM):
            self.flatpak_loader = FlatpakLoader()
            self.flatpak_loader.finished.connect(self.on_flatpak_loaded)
            self.flatpak_loader.start()

        # Watch flatpak appstream directory for new cache files
        self._flatpak_watcher = QFileSystemWatcher()
        flatpak_dir = os.path.dirname(FLATPAK_APPSTREAM)
        if os.path.exists(flatpak_dir):
            self._flatpak_watcher.addPath(flatpak_dir)
        self._flatpak_watcher.directoryChanged.connect(self._on_flatpak_dir_changed)

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
        except Exception:
            pass

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
        if not os.path.exists(csv_path):
            return
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
        txt = self.t("ui.install_btn_sel").replace("{0}", str(count)) if count > 0 else self.t("ui.install_btn_empty")
        self.btn_install_essentials.setText(txt)
        self.btn_install_essentials.setEnabled(count > 0)

    def setup_logic(self):
        self.btn_switch_store.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        self.cat_list.itemClicked.connect(self.on_cat_clicked)
        self.search_store.textChanged.connect(self._on_search_changed)
        self.combo_store.currentIndexChanged.connect(self.filter_store)
        self.combo_source.currentIndexChanged.connect(self._on_source_changed)
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
        # AppDetailWidget is page 2
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
                btn.setProperty("active", "true" if btn.property("lang") == self.current_lang else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)

    def update_ui_texts(self):
        self.cat_header.setText(self.t("ui.essentials_header"))
        self.store_header.setText(self.t("ui.store_header"))
        self.btn_switch_store.setText(self.t("ui.search_all"))
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
        self.combo_source.blockSignals(False)
        self.update_install_button_text()

    def on_cat_clicked(self, item):
        self.stacked_widget.setCurrentIndex(0)
        self.render_essentials(item.data(Qt.ItemDataRole.UserRole))

    def on_store_loaded(self, packages):
        self.store_packages = packages
        self.store_loading_lbl.hide()
        self.filter_store()

    def on_flatpak_loaded(self, packages):
        self.flatpak_packages = packages
        try:
            res = subprocess.run(
                ["flatpak", "list", "--app", "--columns=application"],
                capture_output=True, text=True
            )
            self.flatpak_installed = set(
                line.strip() for line in res.stdout.splitlines() if line.strip()
            )
        except Exception:
            self.flatpak_installed = set()
        if self._current_source == "flatpak":
            self.filter_store()

    # --- Source / search handling ---

    def _on_source_changed(self, index):
        source_map = {0: "all", 1: "pacman", 2: "aur", 3: "flatpak"}
        self._current_source = source_map.get(index, "all")
        self.filter_store()

    def _on_search_changed(self, text):
        if self._current_source == "aur":
            if self._aur_debounce_timer:
                self._aur_debounce_timer.stop()
            self._aur_debounce_timer = QTimer()
            self._aur_debounce_timer.setSingleShot(True)
            self._aur_debounce_timer.timeout.connect(lambda: self._trigger_aur_search(text))
            self._aur_debounce_timer.start(500)
        else:
            self.filter_store()

    def filter_store(self):
        source = self._current_source
        if source == "aur":
            query = self.search_store.text().strip()
            if query:
                self._trigger_aur_search(query)
            else:
                self._show_aur_placeholder()
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
        # pacman / all
        self._filter_packages(self.store_packages, source)

    def _filter_packages(self, packages, source="all"):
        query = self.search_store.text().lower()
        cat = self.combo_store.currentText()
        self.filtered_store_packages = []
        for pkg in packages:
            if source == "pacman" and pkg.source_type != "pacman":
                continue
            pkg.status = "upgradable" if pkg.name in self.upgradable_packages else (
                "installed" if pkg.name in self.installed_packages else "available"
            )
            if query and query not in pkg.name.lower() and query not in pkg.desc.lower():
                continue
            if cat != "All" and pkg.category != cat:
                continue
            self.filtered_store_packages.append(pkg)
        self.current_page = 1
        self.render_store_page()

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

    def _show_aur_placeholder(self):
        self._show_store_message(self.t("ui.aur_placeholder"))

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

            btn_install = QPushButton(self.t("ui.flatpak_install_btn"))
            btn_install.setObjectName("DetailActionBtn")
            btn_install.setFixedWidth(250)
            btn_install.setMinimumHeight(40)
            btn_install.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_install.clicked.connect(self._run_flatpak_install)

            layout.addWidget(lbl_title)
            layout.addWidget(lbl_desc)
            layout.addSpacing(20)
            layout.addWidget(btn_install, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            lbl_title = QLabel(self.t("ui.flatpak_not_setup"))
            lbl_title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; background: transparent;")
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lbl_desc = QLabel(self.t("ui.flatpak_init_desc"))
            lbl_desc.setStyleSheet("color: #a6adc8; font-size: 14px; background: transparent;")
            lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_desc.setWordWrap(True)

            btn_init = QPushButton(self.t("ui.flatpak_init_btn"))
            btn_init.setObjectName("DetailActionBtn")
            btn_init.setFixedWidth(250)
            btn_init.setMinimumHeight(40)
            btn_init.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_init.clicked.connect(self._run_flatpak_bootstrap)

            layout.addWidget(lbl_title)
            layout.addWidget(lbl_desc)
            layout.addSpacing(20)
            layout.addWidget(btn_init, alignment=Qt.AlignmentFlag.AlignCenter)

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

    def _on_flatpak_dir_changed(self, path):
        if os.path.exists(FLATPAK_APPSTREAM):
            self.flatpak_loader = FlatpakLoader()
            self.flatpak_loader.finished.connect(self.on_flatpak_loaded)
            self.flatpak_loader.start()

    def _trigger_aur_search(self, query):
        if not query:
            self._show_aur_placeholder()
            return
        self._aur_search_gen += 1
        gen = self._aur_search_gen
        self._aur_search_thread = AURSearchThread(query)
        self._aur_search_thread.finished.connect(
            lambda pkgs, g=gen: self._on_aur_results(pkgs, g)
        )
        self._aur_search_thread.start()

    def _on_aur_results(self, pkgs, gen):
        if gen != self._aur_search_gen:
            return
        self.aur_packages = pkgs
        self.filtered_store_packages = list(pkgs)
        self.current_page = 1
        self.render_store_page()

    def render_store_page(self):
        while self.layout_store.count() > 0:
            item = self.layout_store.takeAt(0)
            if item.widget() and item.widget() != self.store_loading_lbl:
                item.widget().deleteLater()
        total = len(self.filtered_store_packages)
        pages = max(1, (total + self.items_per_page - 1) // self.items_per_page)
        start = (self.current_page - 1) * self.items_per_page
        end = self.current_page * self.items_per_page
        for pkg in self.filtered_store_packages[start:end]:
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
        if self.current_page < (len(self.filtered_store_packages) + 49) // 50:
            self.current_page += 1
            self.render_store_page()
            self.scroll_store.verticalScrollBar().setValue(0)

    # --- App detail ---

    def open_app_detail(self, pkg_data):
        self.page_detail.load_package(
            pkg_data, self.t,
            self.installed_packages, self.flatpak_installed, self.upgradable_packages,
            on_install=self.install_package,
            on_remove=self.remove_package
        )
        self.stacked_widget.setCurrentIndex(2)
        self._load_detail_screenshots(pkg_data)

    def _go_back_from_detail(self):
        self.stacked_widget.setCurrentIndex(1)

    def _load_detail_screenshots(self, pkg_data):
        self._screenshot_threads = []
        self.page_detail.clear_screenshots()
        if pkg_data.source_type == "flatpak":
            if pkg_data.screenshot_urls:
                self._start_screenshot_downloads(pkg_data.screenshot_urls)
            else:
                self.page_detail.show_no_screenshots(self.t)
        elif pkg_data.source_type == "aur":
            self.page_detail.show_no_screenshots(self.t)
        else:
            if pkg_data.screenshot_urls:
                self._start_screenshot_downloads(pkg_data.screenshot_urls)
            else:
                loader = LocalAppStreamLoader(pkg_data.name)
                loader.finished.connect(lambda urls: self._on_local_appstream_loaded(urls, pkg_data))
                loader.start()
                self._screenshot_threads.append(loader)

    def _on_local_appstream_loaded(self, urls, pkg_data):
        pkg_data.screenshot_urls = urls
        if urls:
            self._start_screenshot_downloads(urls)
        else:
            self.page_detail.show_no_screenshots(self.t)

    def _start_screenshot_downloads(self, urls):
        self.page_detail.clear_screenshots()
        for url in urls[:5]:
            lbl = self.page_detail.add_screenshot_placeholder()
            t = ScreenshotDownloadThread(url)
            captured_lbl = lbl
            t.done.connect(lambda u, path, l=captured_lbl: self.page_detail.set_screenshot_image(l, path))
            t.start()
            self._screenshot_threads.append(t)

    # --- Install / remove ---

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
            subprocess.Popen(["konsole", "-e", "bash", "-c",
                              f"pkexec pacman -S --noconfirm {' '.join(self.selected_essentials)}; "
                              "echo; read -rp 'Done. Press Enter to close...'"])

    def execute_system_update(self):
        subprocess.Popen(["konsole", "-e", "bash", "-c",
                          "yay -Syu --noconfirm; "
                          "if command -v flatpak >/dev/null; then flatpak update -y; fi; "
                          "echo; read -rp 'Done. Press Enter to close...'"])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setDesktopFileName("equestria-os-software-center")
    win = main_app()
    win.show()
    sys.exit(app.exec())
