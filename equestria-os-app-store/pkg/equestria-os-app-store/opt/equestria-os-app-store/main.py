import sys, os, subprocess, threading, json, urllib.request, urllib.parse
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from ui_pkg import Ui_PackageManager, AppRow

class AppData:
    def __init__(self, name, version, desc, source, installed=False):
        self.name = name
        self.version = version
        self.desc = desc if desc else "No description provided."
        self.source = source
        self.installed = installed
        self.category = self._guess_category()

    def _guess_category(self):
        text = (self.name + " " + self.desc).lower()
        if any(x in text for x in ["game", "emulator", "minecraft"]): return "Games"
        if any(x in text for x in ["browser", "web", "internet", "network"]): return "Internet"
        if any(x in text for x in ["video", "audio", "player", "music", "media"]): return "Media"
        if any(x in text for x in ["draw", "paint", "image", "graphics", "photo"]): return "Graphics"
        if any(x in text for x in ["nvidia", "amd", "driver", "vulkan", "firmware"]): return "Drivers"
        if any(x in text for x in ["theme", "plasma", "kde", "extension", "widget"]): return "Extensions"
        return "Software"

class main_app(QMainWindow, Ui_PackageManager):
    install_finished = pyqtSignal(bool, str)
    search_finished = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        self.install_finished.connect(self.on_install_finished)
        self.search_finished.connect(self.on_search_finished)

        f_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            fid = QFontDatabase.addApplicationFont(f_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                self.title_label.setFont(QFont(families[0], 28, QFont.Weight.Bold))
                self.modal_title.setFont(QFont(families[0], 22, QFont.Weight.Bold))

        q_path = os.path.join(self.base_path, "style.qss")
        if os.path.exists(q_path): self.setStyleSheet(open(q_path, "r").read())

        icon_path = os.path.join(self.base_path, "equestria-os-logo.png")
        if os.path.exists(icon_path): self.setWindowIcon(QIcon(icon_path))

        QApplication.setDesktopFileName("equestria-os-store")

        self.langs_db = {
            "ui.title": {"en": "✨ Equestria OS App Store", "ru": "✨ Магазин Equestria OS", "de": "✨ Equestria OS App Store", "fr": "✨ Magasin Equestria OS", "es": "✨ Tienda Equestria OS", "pt": "✨ Loja Equestria OS", "pl": "✨ Sklep Equestria OS", "uk": "✨ Магазин Equestria OS", "zh": "✨ Equestria OS 商店", "ja": "✨ Equestria OS ストア"},
            "cat.all": {"en": "All", "ru": "Все", "de": "Alle", "fr": "Tous", "es": "Todos", "pt": "Todos", "pl": "Wszystkie", "uk": "Всі", "zh": "全部", "ja": "すべて"},
            "cat.games": {"en": "Games", "ru": "Игры", "de": "Spiele", "fr": "Jeux", "es": "Juegos", "pt": "Jogos", "pl": "Gry", "uk": "Ігри", "zh": "游戏", "ja": "ゲーム"},
            "cat.internet": {"en": "Internet", "ru": "Интернет", "de": "Internet", "fr": "Internet", "es": "Internet", "pt": "Internet", "pl": "Internet", "uk": "Інтернет", "zh": "互联网", "ja": "インターネット"},
            "cat.media": {"en": "Media", "ru": "Медиа", "de": "Medien", "fr": "Médias", "es": "Medios", "pt": "Mídia", "pl": "Media", "uk": "Медіа", "zh": "媒体", "ja": "メディア"},
            "cat.graphics": {"en": "Graphics", "ru": "Графика", "de": "Grafik", "fr": "Graphismes", "es": "Gráficos", "pt": "Gráficos", "pl": "Grafika", "uk": "Графіка", "zh": "图形", "ja": "グラフィックス"},
            "cat.drivers": {"en": "Drivers", "ru": "Драйверы", "de": "Treiber", "fr": "Pilotes", "es": "Controladores", "pt": "Drivers", "pl": "Sterowniki", "uk": "Драйвери", "zh": "驱动", "ja": "ドライバー"},
            "cat.extensions": {"en": "Extensions", "ru": "Расширения", "de": "Erweiterungen", "fr": "Extensions", "es": "Extensiones", "pt": "Extensões", "pl": "Rozszerzenia", "uk": "Розширення", "zh": "扩展", "ja": "拡張機能"},
            "cat.software": {"en": "Software", "ru": "Программы", "de": "Software", "fr": "Logiciels", "es": "Software", "pt": "Software", "pl": "Oprogramowanie", "uk": "Програми", "zh": "软件", "ja": "ソフトウェア"},
            "btn.install": {"en": "Install", "ru": "Установить", "de": "Installieren", "fr": "Installer", "es": "Instalar", "pt": "Instalar", "pl": "Zainstaluj", "uk": "Встановити", "zh": "安装", "ja": "インストール"},
            "btn.installed": {"en": "Installed", "ru": "Установлено", "de": "Installiert", "fr": "Installé", "es": "Instalado", "pt": "Instalado", "pl": "Zainstalowano", "uk": "Встановлено", "zh": "已安装", "ja": "インストール済み"},
            "btn.cancel": {"en": "Cancel", "ru": "Отмена", "de": "Abbrechen", "fr": "Annuler", "es": "Cancelar", "pt": "Cancelar", "pl": "Anuluj", "uk": "Скасувати", "zh": "取消", "ja": "キャンセル"},
            "btn.search": {"en": "🔍 Search", "ru": "🔍 Поиск", "de": "🔍 Suchen", "fr": "🔍 Rechercher", "es": "🔍 Buscar", "pt": "🔍 Pesquisar", "pl": "🔍 Szukaj", "uk": "🔍 Пошук", "zh": "🔍 搜索", "ja": "🔍 検索"},
            "modal.install_confirm": {"en": "Install {0}?", "ru": "Установить {0}?", "de": "{0} installieren?", "fr": "Installer {0} ?", "es": "¿Instalar {0}?", "pt": "Instalar {0}?", "pl": "Zainstalować {0}?", "uk": "Встановити {0}?", "zh": "安装 {0}？", "ja": "{0} をインストールしますか？"},
            "modal.wait": {"en": "Downloading {0}... Please wait.", "ru": "Установка {0}... Пожалуйста, подождите.", "de": "Herunterladen {0}...", "fr": "Téléchargement de {0}...", "es": "Descargando {0}...", "pt": "Baixando {0}...", "pl": "Pobieranie {0}...", "uk": "Встановлення {0}... Будь ласка, зачекайте.", "zh": "正在下载 {0}...", "ja": "{0} をダウンロードしています..."}
        }

        self.current_lang = os.getenv("LANG", "en")[:2]
        if self.current_lang not in self.langs_db["ui.title"]: self.current_lang = "en"

        self.all_apps = []
        self.app_to_install = None

        self.setup_logic()
        self.apply_localization()
        self.refresh_installed_list()


    def resizeEvent(self, event):
        self.modal_overlay.resize(event.size())
        super().resizeEvent(event)


    def t(self, key):
        return self.langs_db.get(key, {}).get(self.current_lang, self.langs_db.get(key, {}).get("en", key))

    def setup_logic(self):
        self.btn_search.clicked.connect(self.perform_search)
        self.search_field.returnPressed.connect(self.perform_search)
        self.category_dropdown.currentTextChanged.connect(self.apply_filters)

        self.btn_confirm_cancel.clicked.connect(self.hide_modal)
        self.btn_confirm_action.clicked.connect(self.execute_install)

        codes = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
        for code in codes:
            btn = QPushButton(code.upper())
            btn.setObjectName("LangBtn")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda chk, c=code: self.change_lang(c))
            self.lang_layout.addWidget(btn)

    def change_lang(self, lang):
        self.current_lang = lang
        for i in range(self.lang_layout.count()):
            btn = self.lang_layout.itemAt(i).widget()
            if btn and isinstance(btn, QPushButton):
                btn.setProperty("active", "true" if btn.text().lower() == lang else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        self.apply_localization()

    def apply_localization(self):
        self.title_label.setText(self.t("ui.title"))
        self.setWindowTitle(self.t("ui.title"))
        self.btn_search.setText(self.t("btn.search"))

        self.category_dropdown.blockSignals(True)
        self.category_dropdown.clear()
        self.category_dropdown.addItems([
            self.t("cat.all"), self.t("cat.games"), self.t("cat.internet"),
            self.t("cat.media"), self.t("cat.graphics"), self.t("cat.drivers"),
            self.t("cat.extensions"), self.t("cat.software")
        ])
        self.category_dropdown.blockSignals(False)
        self.btn_confirm_cancel.setText(self.t("btn.cancel"))
        self.build_list()

    def hide_modal(self):
        self.modal_overlay.hide()
        self.progress_bar.hide() # Скрываем прогресс-бар при закрытии
        self.btn_confirm_action.show()
        self.btn_confirm_cancel.show()

    def refresh_installed_list(self):
        self.search_field.setPlaceholderText("Loading installed packages...")
        def _fetch():
            pkgs = []
            env = os.environ.copy()
            env["LANG"] = "C"
            r = subprocess.run(["pacman", "-Qi"], capture_output=True, text=True, env=env)

            current_pkg = {}
            for line in r.stdout.splitlines():
                if line.startswith("Name"): current_pkg["name"] = line.split(":", 1)[1].strip()
                elif line.startswith("Version"): current_pkg["version"] = line.split(":", 1)[1].strip()
                elif line.startswith("Description"): current_pkg["desc"] = line.split(":", 1)[1].strip()
                elif line.strip() == "":
                    if "name" in current_pkg:
                        pkgs.append(AppData(current_pkg["name"], current_pkg.get("version", ""), current_pkg.get("desc", ""), "pacman", True))
                    current_pkg = {}

            if "name" in current_pkg:
                pkgs.append(AppData(current_pkg["name"], current_pkg.get("version", ""), current_pkg.get("desc", ""), "pacman", True))

            self.search_finished.emit(pkgs)
        threading.Thread(target=_fetch, daemon=True).start()

    def perform_search(self):
        query = self.search_field.text().strip()
        if len(query) < 2: return
        self.btn_search.setEnabled(False)

        # Сбрасываем фильтр категорий на "Все" при новом поиске
        self.category_dropdown.blockSignals(True)
        self.category_dropdown.setCurrentIndex(0)
        self.category_dropdown.blockSignals(False)

        def _search():
            results = []
            env = os.environ.copy()
            env["LANG"] = "C"

            try:
                r_pac = subprocess.run(["pacman", "-Ss", query], capture_output=True, text=True, env=env)
                lines = r_pac.stdout.splitlines()
                for i in range(0, len(lines), 2):
                    if i+1 < len(lines):
                        header = lines[i].split()
                        repo_name = header[0].split("/")
                        desc = lines[i+1].strip()
                        results.append(AppData(repo_name[1], header[1], desc, "pacman", False))
            except Exception as e: pass

            try:
                url = f"https://aur.archlinux.org/rpc/?v=5&type=search&arg={urllib.parse.quote(query)}"
                req = urllib.request.urlopen(url)
                data = json.loads(req.read().decode('utf-8'))
                for item in data.get("results", []):
                    results.append(AppData(item["Name"], item["Version"], item.get("Description", ""), "aur", False))
            except Exception as e: pass

            installed_check = subprocess.run(["pacman", "-Qq"], capture_output=True, text=True).stdout.splitlines()
            installed_set = set(installed_check)

            for app in results:
                if app.name in installed_set:
                    app.installed = True

            self.search_finished.emit(results)

        threading.Thread(target=_search, daemon=True).start()

    def on_search_finished(self, results):
        self.all_apps = results
        self.btn_search.setEnabled(True)
        self.search_field.setPlaceholderText("Search apps, games, drivers...")
        self.build_list()

    def build_list(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        for app in self.all_apps:
            btn_text = self.t("btn.installed") if app.installed else self.t("btn.install")
            row = AppRow(app, btn_text, self.show_confirm)
            self.list_layout.addWidget(row)

        self.apply_filters()

    def apply_filters(self):
        cat = self.category_dropdown.currentText()
        for i in range(self.list_layout.count()):
            widget = self.list_layout.itemAt(i).widget()
            if isinstance(widget, AppRow):
                cat_match = (cat == self.t("cat.all") or cat == self.t("cat." + widget.pkg_data.category.lower()))
                widget.setVisible(cat_match)

    def show_confirm(self, app):
        if app.installed: return

        self.app_to_install = app
        self.modal_text.setText(self.t("modal.install_confirm").format(app.name))

        self.btn_confirm_action.setText(self.t("btn.install"))
        self.btn_confirm_action.setObjectName("ModalInstallBtn")
        self.btn_confirm_action.style().unpolish(self.btn_confirm_action)
        self.btn_confirm_action.style().polish(self.btn_confirm_action)

        self.progress_bar.hide()
        self.btn_confirm_action.show()
        self.btn_confirm_cancel.show()

        self.modal_overlay.show()
        self.modal_overlay.raise_()

    def execute_install(self):
        if not self.app_to_install: return
        app_name = self.app_to_install.name

        # Меняем текст и прячем кнопки
        self.modal_text.setText(self.t("modal.wait").format(app_name))
        self.btn_confirm_action.hide()
        self.btn_confirm_cancel.hide()

        # Включаем бесконечный ползунок (0 до 0 - режим ожидания)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()

        # Запускаем команду (pkexec попросит пароль)
        if self.app_to_install.source == "aur":
            cmd = f"konsole -e yay -S --noconfirm {app_name}"
        else:
            cmd = f"pkexec pacman -S --noconfirm {app_name}"

        def _run():
            proc = subprocess.run(["/bin/bash", "-c", cmd])
            self.install_finished.emit(proc.returncode == 0, app_name)

        threading.Thread(target=_run, daemon=True).start()

    def on_install_finished(self, success, app_name):
        self.hide_modal()
        if success:
            for app in self.all_apps:
                if app.name == app_name:
                    app.installed = True
            self.build_list()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = main_app()
    win.show()
    sys.exit(app.exec())
