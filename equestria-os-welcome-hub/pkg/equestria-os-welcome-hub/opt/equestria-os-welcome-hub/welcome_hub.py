import sys, os, subprocess, webbrowser
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton
from PyQt6.QtGui import QFontDatabase, QFont, QIcon
from PyQt6.QtCore import Qt
from ui_welcome import Ui_WelcomeHub

class Item:
    def __init__(self, name, target, launch_type="app"):
        self.name = name
        self.target = target
        self.launch_type = "url" if target.startswith("http") or target.startswith("steam") else launch_type

class main_app(QMainWindow, Ui_WelcomeHub):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        self.setWindowTitle("Equestria OS Welcome")

        f_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            fid = QFontDatabase.addApplicationFont(f_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                self.sidebar_title.setFont(QFont(families[0], 22, QFont.Weight.Bold))
                self.cat_title.setFont(QFont(families[0], 26, QFont.Weight.Bold))

        if os.path.exists(os.path.join(self.base_path, "style.qss")):
            self.setStyleSheet(open(os.path.join(self.base_path, "style.qss")).read())

        # ФИКС: ПОЛНАЯ ЛОКАЛИЗАЦИЯ ИЗ ТВОЕГО C# ФАЙЛА
        self.strings = {
            "cat.system": {"en":"🛠️ System", "ru":"🛠️ Система", "de":"🛠️ System", "fr":"🛠️ Système", "es":"🛠️ Sistema", "pt":"🛠️ Sistema", "pl":"🛠️ System", "uk":"🛠️ Система", "zh":"🛠️ 系统", "ja":"🛠️ システム"},
            "cat.music": {"en":"🎵 Music", "ru":"🎵 Музыка", "de":"🎵 Musik", "fr":"🎵 Musique", "es":"🎵 Música", "pt":"🎵 Música", "pl":"🎵 Muzyka", "uk":"🎵 Музика", "zh":"🎵 音乐", "ja":"🎵 音楽"},
            "cat.games": {"en":"🎮 Games", "ru":"🎮 Игры", "de":"🎮 Spiele", "fr":"🎮 Jeux", "es":"🎮 Juegos", "pt":"🎮 Jogos", "pl":"🎮 Gry", "uk":"🎮 Ігри", "zh":"🎮 游戏", "ja":"🎮 ゲーム"},
            "cat.social": {"en":"🐴 Pony Social", "ru":"🐴 Пони-соцсети", "de":"🐴 Pony Soziales", "fr":"🐴 Social Pony", "es":"🐴 Social Pony", "pt":"🐴 Social Pony", "pl":"🐴 Kucyk Social", "uk":"🐴 Поні-соцмережі", "zh":"🐴 小马社区", "ja":"🐴 ポニーSNS"},
            "cat.support": {"en":"🆘 Support", "ru":"🆘 Поддержка", "de":"🆘 Support", "fr":"🆘 Aide", "es":"🆘 Soporte", "pt":"🆘 Suporte", "pl":"🆘 Wsparcie", "uk":"🆘 Підтримка", "zh":"🆘 支持", "ja":"🆘 サポート"},
            "ui.autostart": {"en":"Launch on startup", "ru":"Запускать при старте", "de":"Beim Start ausführen", "fr":"Lancer au démarrage", "es":"Iniciar al arrancar", "pt":"Iniciar na inicialização", "pl":"Uruchom przy starcie", "uk":"Запускати при старті", "zh":"开机启动", "ja":"起動時に実行"},

            # --- НОВЫЕ КЛЮЧИ ДЛЯ ПРИЛОЖЕНИЙ (ВСЕ 10 ЯЗЫКОВ) ---
            "app.theme": {"en":"Equestria OS Theme Switcher", "ru":"Переключатель тем Equestria OS", "de":"Equestria-OS-Theme-Wechsler", "fr":"Sélecteur de thèmes Equestria OS", "es":"Selector de temas de Equestria OS", "pt":"Seletor de temas Equestria OS", "pl":"Przełącznik motywów Equestria OS", "uk":"Перемикач тем Equestria OS", "zh":"Equestria OS主题切换器", "ja":"Equestria OSテーマスイッチャー"},
            "app.panel": {"en":"Equestria OS Task Panel Changer", "ru":"Настройка панели задач Equestria OS", "de":"Equestria OS Taskleisten-Konfigurator", "fr":"Gestionnaire de barre des tâches Equestria OS", "es":"Configurador de barra de tareas Equestria OS", "pt":"Configurador de barra de tarefas Equestria OS", "pl":"Konfigurator paska zadań Equestria OS", "uk":"Налаштування панелі завдань Equestria OS", "zh":"Equestria OS任务栏配置器", "ja":"Equestria OSタスクバー設定"},
            "app.essentials": {"en":"Equestria OS Essentials", "ru":"Базовые программы Equestria OS", "de":"Equestria OS Essentials", "fr":"Les Essentiels Equestria OS", "es":"Esenciales de Equestria OS", "pt":"Essenciais do Equestria OS", "pl":"Niezbędnik Equestria OS", "uk":"Базові програми Equestria OS", "zh":"Equestria OS 必备软件", "ja":"Equestria OS 必須アプリ"},
            "app.store": {"en":"Equestria OS App Store", "ru":"Магазин Equestria OS", "de":"Equestria OS App Store", "fr":"Boutique Equestria OS", "es":"Tienda Equestria OS", "pt":"Loja Equestria OS", "pl":"Sklep Equestria OS", "uk":"Магазин Equestria OS", "zh":"Equestria OS 应用商店", "ja":"Equestria OS アプリストア"},
            "app.pkgs": {"en":"Equestria OS Packages", "ru":"Пакеты Equestria OS", "de":"Equestria OS Pakete", "fr":"Paquets Equestria OS", "es":"Paquetes de Equestria OS", "pt":"Pacotes do Equestria OS", "pl":"Pakiety Equestria OS", "uk":"Пакети Equestria OS", "zh":"Equestria OS软件包", "ja":"Equestria OSパッケージ"}
        }

        self.current_lang = os.getenv("LANG", "en")[:2]
        if self.current_lang not in ["en", "ru", "uk", "de", "fr", "es", "pt", "pl", "zh", "ja"]: self.current_lang = "en"

        self.setup_autostart_logic()
        self.setup_ui_logic()
        self.refresh_ui()

    def t(self, key): return self.strings.get(key, {}).get(self.current_lang, self.strings.get(key, {}).get("en", key))

    def setup_ui_logic(self):
        codes = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
        for i, code in enumerate(codes):
            btn = QPushButton(code.upper())
            btn.setProperty("cssClass", "lang-button")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda chk, c=code: self.change_lang(c))
            if i < 5: self.lang_row1.addWidget(btn)
            else: self.lang_row2.addWidget(btn)

    def change_lang(self, lang):
        self.current_lang = lang
        for layout in [self.lang_row1, self.lang_row2]:
            for i in range(layout.count()):
                btn = layout.itemAt(i).widget()
                if isinstance(btn, QPushButton):
                    btn.setProperty("active", "true" if btn.text().lower() == lang else "false")
                    btn.style().unpolish(btn); btn.style().polish(btn)
        self.refresh_ui()

    def refresh_ui(self):
        self.autostart_label.setText(self.t("ui.autostart"))

        while self.nav_container.count():
            w = self.nav_container.takeAt(0).widget()
            if w: w.deleteLater()

        categories = [
            ("cat.system", [
                Item(self.t("app.theme"), "python3 /opt/equestria-os-character-theme/main.py", "command"),
                Item(self.t("app.panel"), "python3 /opt/equestria-os-task-panel-changer/main.py", "command"),
                Item(self.t("app.essentials"), "python3 /opt/equestria-os-essentials/main.py", "command"),
                Item(self.t("app.store"), "python3 /opt/equestria-os-app-store/main.py", "command"),
                Item(self.t("app.pkgs"), "python3 /opt/equestria-os-package-manager/main.py", "command")
            ]),
            ("cat.music", [
                Item("Jyc Row", "https://www.youtube.com/@JycRow"),
                Item("4everfreebrony", "https://www.youtube.com/@4everfreebrony"),
                Item("Frozen Night", "https://www.youtube.com/@FrozenNightMusic"),
                Item("ponyphonic", "https://www.youtube.com/@ponyphonic"),
                Item("Ponies At Dawn", "https://www.youtube.com/@PoniesAtDawn"),
                Item("Merger Brony", "https://www.youtube.com/@MergerBrony"),
                Item("PrinceWhateverer", "https://www.youtube.com/@PrinceWhateverer"),
                Item("Nicolas Dominique", "https://www.youtube.com/@NicolasDominique"),
                Item("Blackened Blue", "https://www.youtube.com/@BlackenedBlue"),
                Item("Vylet Pony", "https://www.youtube.com/@VyletPony"),
                Item("Faulty", "https://www.youtube.com/@faulty_music"),
                Item("Francis Vace", "https://www.youtube.com/@FrancisVace"),
                Item("Stablebound", "https://www.youtube.com/@stablebound"),
                Item("Tidals", "https://www.youtube.com/@Tidals"),
                Item("Never Shaded", "https://www.youtube.com/@NeverShaded"),
                Item("MelodyBrony", "https://www.youtube.com/@MelodyBrony"),
                Item("Aurelleah", "https://www.youtube.com/@Aurelleah"),
                Item("Loophoof", "https://www.youtube.com/@loophoof"),
                Item("Tw3Lv3", "https://www.youtube.com/@Tw3Lv3"),
                Item("Spinning Gears", "https://www.youtube.com/@SpinningGearsMusic"),
                Item("Metajoker", "https://www.youtube.com/@Metajoker")
            ]),
            ("cat.games", [
                Item("Pony Town", "https://pony.town/"),
                Item("Legends of Equestria", "yay -S legends-of-equestria", "command"),
                Item("World Without Time (Steam)", "steam://store/4219000/"),
                Item("Ambient.White — demo (Proton)", "https://ambientproject.net/downloads/"),
                Item("Them's Fightin' Herds (Steam)", "https://store.steampowered.com/app/574980/Thems_Fightin_Herds/"),
                Item("Remains (Steam)", "https://store.steampowered.com/app/3908900/Remains/"),
                Item("My Little Karaoke: Singing is Magic", "https://www.mylittlekaraoke.com"),
                Item("Fighting is Magic: Aurora (Proton)", "https://windowslogic.itch.io/fighting-is-magic-aurora"),
                Item("Equestria at War — Hearts of Iron IV (Steam)", "https://steamcommunity.com/sharedfiles/filedetails/?id=1826643372")
            ]),
            ("cat.social", [
                Item("Derpibooru", "https://derpibooru.org/"),
                Item("FIMFiction", "https://www.fimfiction.net/"),
                Item("Equestria Daily", "https://www.equestriadaily.com/"),
                Item("MLPForums", "https://mlpforums.com/"),
                Item("Pony.social (Mastodon)", "https://pony.social/"),
                Item("r/mylittlepony", "https://www.reddit.com/r/mylittlepony/"),
                Item("Bronycon Archive", "https://bronycon.org/"),
                Item("MLP Merch", "https://www.mlpmerch.com/")
            ]),
            ("cat.support", [
                Item("Arch Wiki", "https://wiki.archlinux.org/"),
                Item("Arch Forums", "https://bbs.archlinux.org/"),
                Item("Psyche Games", "https://psyche-games.com/equestria-os.php")
            ])
        ]

        for i, (cat_key, items) in enumerate(categories):
            btn = QPushButton(self.t(cat_key))
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("active", "true" if i == 0 else "false")
            btn.clicked.connect(lambda chk, k=cat_key, it=items, b=btn: self.show_category(k, it, b))
            self.nav_container.addWidget(btn)
            if i == 0: self.show_category(cat_key, items, btn)

    def show_category(self, key, items, sender):
        self.cat_title.setText(self.t(key))

        for i in range(self.nav_container.count()):
            widget = self.nav_container.itemAt(i).widget()
            widget.setProperty("active", "false")
            widget.style().unpolish(widget)

        sender.setProperty("active", "true")
        sender.style().polish(sender)

        while self.content_layout.count():
            w = self.content_layout.takeAt(0).widget()
            if w: w.deleteLater()

        for item in items:
            btn = QPushButton(item.name)
            btn.setObjectName("ItemCard")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda chk, it=item: self.launch(it))
            self.content_layout.addWidget(btn)

    def launch(self, item):
        target = item.target

        # --- Умная обработка Steam-ссылок ---
        if target.startswith("steam://store/"):
            # Ищем активный процесс Steam (pgrep вернет код 0, если найдет)
            is_steam_running = subprocess.run(["pgrep", "-i", "steam"], capture_output=True).returncode == 0

            if not is_steam_running:
                # Если Steam не открыт (или не установлен), делаем браузерную ссылку
                app_id = target.replace("steam://store/", "").strip("/")
                target = f"https://store.steampowered.com/app/{app_id}/"

        # --- Запуск ---
        if item.launch_type == "url" or target.startswith("http"):
            # xdg-open гарантированно откроет браузер по умолчанию (Opera)
            subprocess.Popen(["xdg-open", target])
        elif item.launch_type == "command":
            subprocess.Popen(["/bin/bash", "-c", target])
        else:
            subprocess.Popen([target])

    # --- АВТОЗАПУСК: СОЗДАНИЕ И УДАЛЕНИЕ ФАЙЛА В LINUX ---
    def setup_autostart_logic(self):
        path = os.path.expanduser("~/.config/autostart/equestria-welcomehub.desktop")

        # При старте проверяем, есть ли уже файл, и ставим галочку
        self.autostart_checkbox.setChecked(os.path.exists(path))
        self.autostart_checkbox.toggled.connect(self.toggle_autostart)

    def toggle_autostart(self, enable):
        path = os.path.expanduser("~/.config/autostart/equestria-welcomehub.desktop")
        if enable:
            # Создаем скрытую папку autostart, если её нет, и пишем файл
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write("[Desktop Entry]\nType=Application\nName=Equestria OS Welcome Hub\n" +
                        "Exec=python3 " + os.path.abspath(__file__) + "\nIcon=equestria-os\n" +
                        "X-GNOME-Autostart-enabled=true\nHidden=false\n")
        else:
            # Если галочку сняли - удаляем файл автозапуска
            if os.path.exists(path):
                os.remove(path)

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
