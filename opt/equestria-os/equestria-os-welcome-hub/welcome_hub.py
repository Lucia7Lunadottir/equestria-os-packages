import sys, os, subprocess, webbrowser
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QComboBox
from PyQt6.QtGui import QFontDatabase, QFont, QIcon
from PyQt6.QtCore import Qt
from localization import catalog, live_i18n, kit_qt
from ui_welcome import Ui_WelcomeHub
from equestria_kit.widgets import font_families

class Item:
    def __init__(self, name, target, launch_type="app"):
        self.name = name
        self.target = target
        self.launch_type = "url" if target.startswith("http") or target.startswith("steam") else launch_type

class main_app(QMainWindow, Ui_WelcomeHub):
    def __init__(self):
        super().__init__()
        catalog.set_language(catalog.lang, persist=False)
        self.setupUi(self)
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        live_i18n.call(self.setWindowTitle, "Equestria OS Welcome")

        f_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            families = font_families(f_path)
            if families:
                self.sidebar_title.setFont(QFont(families[0], 22, QFont.Weight.Bold))
                self.cat_title.setFont(QFont(families[0], 26, QFont.Weight.Bold))

        if os.path.exists(os.path.join(self.base_path, "style.qss")):
            with open(os.path.join(self.base_path, "style.qss"), encoding="utf-8") as stylesheet:
                kit_qt.style(self, stylesheet.read())

        self.setup_autostart_logic()
        self.setup_ui_logic()
        self.refresh_ui()

    def t(self, key):
        return catalog.tr(key)

    def setup_ui_logic(self):
        self.lang_combo = catalog.selector(self)
        self.lang_combo.setObjectName("LangCombo")
        self.lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lang_row1.addWidget(self.lang_combo)

    def change_lang(self, lang):
        catalog.set_language(lang)
        self.lang_combo.setCurrentIndex(self.lang_combo.findData(catalog.lang))

    def refresh_ui(self):
        live_i18n.call(self.autostart_label.setText, self.t("ui.autostart"))

        while self.nav_container.count():
            w = self.nav_container.takeAt(0).widget()
            if w: w.deleteLater()

        categories = [
            ("cat.system", [
                Item(self.t("app.tutorial"), "equestria-os-tutorial", "command"),
                Item(self.t("app.theme"), "equestria-os-character-theme", "command"),
                Item(self.t("app.panel"), "equestria-os-task-panel-changer", "command"),
                Item(self.t("app.store"), "equestria-os-software-center", "command"),
                Item(self.t("app.pkgs"), "equestria-os-package-manager", "command")
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
            btn = live_i18n.call(QPushButton, self.t(cat_key))
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("active", "true" if i == 0 else "false")
            btn.clicked.connect(lambda chk, k=cat_key, it=items, b=btn: self.show_category(k, it, b))
            self.nav_container.addWidget(btn)
            if i == 0: self.show_category(cat_key, items, btn)

    def show_category(self, key, items, sender):
        live_i18n.call(self.cat_title.setText, self.t(key))

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
            btn = live_i18n.call(QPushButton, item.name)
            btn.setObjectName("ItemCard")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda chk, it=item: self.launch(it))
            self.content_layout.addWidget(btn)

    def launch(self, item):
        target = item.target

        if target.startswith("steam://store/"):
            is_steam_running = subprocess.run(["pgrep", "-i", "steam"], capture_output=True).returncode == 0
            if not is_steam_running:
                app_id = target.replace("steam://store/", "").strip("/")
                target = f"https://store.steampowered.com/app/{app_id}/"

        if item.launch_type == "url" or target.startswith("http"):
            subprocess.Popen(["xdg-open", target])
        elif item.launch_type == "command":
            subprocess.Popen(["/bin/bash", "-c", target])
        else:
            subprocess.Popen([target])

    # --- ИСПРАВЛЕННАЯ ЛОГИКА АВТОЗАПУСКА (БЕЗ УДАЛЕНИЯ КОНФИГА) ---
    # Имя файла ОБЯЗАНО совпадать с системным /etc/xdg/autostart/equestria-os-welcome.desktop:
    # XDG переопределяет автозапуск только по одинаковому имени файла.
    AUTOSTART_PATH = os.path.expanduser("~/.config/autostart/equestria-os-welcome.desktop")
    LEGACY_AUTOSTART_PATH = os.path.expanduser("~/.config/autostart/equestria-welcomehub.desktop")

    def _migrate_legacy_autostart(self):
        """Старый файл (equestria-welcomehub.desktop) ничего не переопределял — переносим выбор в правильный."""
        legacy = self.LEGACY_AUTOSTART_PATH
        if not os.path.exists(legacy):
            return
        try:
            with open(legacy, "r", encoding="utf-8") as f:
                content = f.read()
            disabled = "Hidden=true" in content or "X-GNOME-Autostart-enabled=false" in content
            if disabled and not os.path.exists(self.AUTOSTART_PATH):
                self._write_autostart_entry(self.AUTOSTART_PATH, False)
            os.remove(legacy)
        except Exception:
            pass

    def setup_autostart_logic(self):
        self._migrate_legacy_autostart()
        path = self.AUTOSTART_PATH

        if not os.path.exists(path):
            # Пользователь ничего не менял — глобальный /etc/xdg/autostart активен
            is_enabled = True
        else:
            is_enabled = True
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                has_hidden_true = "Hidden=true" in content
                has_gnome_false = "X-GNOME-Autostart-enabled=false" in content
                is_enabled = not (has_hidden_true or has_gnome_false)
                if has_hidden_true != has_gnome_false:
                    # Старый файл от версии с багом: ключи противоречат друг другу
                    # (например Hidden=true, но X-GNOME-Autostart-enabled=true).
                    # Приводим файл к согласованному виду, сохраняя намерение пользователя.
                    self._write_autostart_entry(path, is_enabled)
            except Exception:
                pass

        self.autostart_checkbox.setChecked(is_enabled)
        self.autostart_checkbox.toggled.connect(self.toggle_autostart)

    def _write_autostart_entry(self, path, enable):
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # Используем системный бинарник вместо python3 /путь/к/файлу
        exec_cmd = "equestria-os-welcome"

        gnome_flag = "true" if enable else "false"
        hidden_flag = "false" if enable else "true"

        with open(path, "w", encoding="utf-8") as f:
            f.write("[Desktop Entry]\n"
                    "Type=Application\n"
                    "Name=Equestria OS Welcome Hub\n"
                    f"Exec={exec_cmd}\n"
                    "Icon=equestria-os-logo\n"
                    f"X-GNOME-Autostart-enabled={gnome_flag}\n"
                    f"Hidden={hidden_flag}\n")

    def toggle_autostart(self, enable):
        self._write_autostart_entry(self.AUTOSTART_PATH, enable)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    kit_qt.ThemeManager(app)  # общая тема Equestria OS: следит за переключателем персонажей
    app.setDesktopFileName("equestria-os-welcome")
    icon_path = "/usr/share/pixmaps/equestria-os-logo.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        app.setWindowIcon(QIcon.fromTheme("preferences-desktop-theme"))
    win = main_app()
    win.show()
    sys.exit(app.exec())