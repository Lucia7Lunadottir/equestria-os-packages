import sys
import os
import json
import csv
import shutil
import subprocess
from dataclasses import dataclass, asdict, field
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFileDialog, QColorDialog, QMessageBox)
from PyQt6.QtGui import QIcon, QPixmap, QColor, QFontDatabase, QFont
from PyQt6.QtCore import Qt
from ui import Ui_MainWindow, APP_STYLE

SYSTEM_PATH = os.path.dirname(os.path.abspath(__file__))
USER_PATH = os.path.expanduser("~/.local/share/EquestriaOS/Themes/")

@dataclass
class KonsoleColorScheme:
    Background: str = "0,0,0"; Foreground: str = "255,255,255"
    Color0: str = "0,0,0"; Color0Intense: str = "100,100,100"
    Color1: str = "170,0,0"; Color1Intense: str = "255,85,85"
    Color2: str = "0,170,0"; Color2Intense: str = "85,255,85"
    Color3: str = "170,85,0"; Color3Intense: str = "255,255,85"
    Color4: str = "0,0,170"; Color4Intense: str = "85,85,255"
    Color5: str = "170,0,170"; Color5Intense: str = "255,85,255"
    Color6: str = "0,170,170"; Color6Intense: str = "85,255,255"
    Color7: str = "170,170,170"; Color7Intense: str = "255,255,255"

@dataclass
class EGCharacter:
    Id: str = ""
    DisplayName: str = ""
    KonsoleProfile: str = ""
    WallpaperPath: str = ""
    KdeColorScheme: str = ""
    AccentColor: str = "#FFFFFF"
    HoverColor: str = "#28233C"
    IconPath: str = ""
    KonsoleTheme: KonsoleColorScheme = field(default_factory=KonsoleColorScheme)

class EGThemeSwitcher(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setWindowTitle("Equestria OS Character Theme")
        self.setStyleSheet(APP_STYLE)

        self.characters = []
        self.active_character = None
        self.editing_character = None
        self.is_creating_new = False
        self.accent_toggle = 0

        self.localized_strings = {}
        self.available_langs = []
        self.current_lang = "en"

        self.init_user_folder()
        self.load_localization_csv()
        self.detect_system_language()

        self.bind_events()
        self.load_characters()

        self.build_language_selector()
        self.build_ui()
        self.update_texts()

    def init_user_folder(self):
        # Создаем базовую папку, если её нет
        os.makedirs(USER_PATH, exist_ok=True)

        # Список того, что РЕАЛЬНО нужно скопировать пользователю
        assets_to_copy = ["characters.json", "Wallpapers", "MLP Cutiemarks"]

        for item in assets_to_copy:
            src = os.path.join(SYSTEM_PATH, item)
            dst = os.path.join(USER_PATH, item)

            # Если это дефолтный файл/папка есть в системе, копируем его
            if os.path.exists(src):
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    # Если файла у пользователя еще нет, копируем
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)

    def load_localization_csv(self):
        loc_path = os.path.join(SYSTEM_PATH, "localization.csv")
        if not os.path.exists(loc_path): return
        with open(loc_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
                self.available_langs = [h.strip() for h in headers[1:]]
                for row in reader:
                    if not row or not row[0].strip(): continue
                    key = row[0].strip()
                    self.localized_strings[key] = {}
                    for i in range(1, len(row)):
                        if i <= len(self.available_langs):
                            self.localized_strings[key][self.available_langs[i-1]] = row[i].strip().replace("\\n", "\n")
            except StopIteration: pass

    def t_str(self, key):
        langs = self.localized_strings.get(key, {})
        return langs.get(self.current_lang, langs.get("en", key))

    def detect_system_language(self):
        sys_lang = os.environ.get("LANG", "en")
        sys_code = sys_lang[:2].lower() if len(sys_lang) >= 2 else "en"
        self.current_lang = sys_code if sys_code in self.available_langs else (self.available_langs[0] if self.available_langs else "en")

    def build_language_selector(self):
        while self.lang_layout.count():
            item = self.lang_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for code in self.available_langs:
            btn = QPushButton(code.upper())
            btn.setProperty("cssClass", "lang-button")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.clicked.connect(lambda _, c=code: self.set_language(c))
            self.lang_layout.addWidget(btn)

    def set_language(self, code):
        self.current_lang = code
        for i in range(self.lang_layout.count()):
            btn = self.lang_layout.itemAt(i).widget()
            if btn:
                btn.setProperty("active", "true" if btn.text().lower() == code else "false")
                btn.style().unpolish(btn); btn.style().polish(btn)
        self.update_texts()

    def update_texts(self):
        self.lbl_title.setText(self.t_str("ui.title"))
        self.lbl_subtitle.setText(self.t_str("ui.subtitle"))
        self.btn_edit.setText(self.t_str("ui.btn_edit"))
        self.btn_duplicate.setText(self.t_str("ui.btn_duplicate"))
        self.btn_create.setText(self.t_str("ui.btn_create_new"))
        self.btn_terminal.setText(self.t_str("ui.btn_open_terminal"))
        self.btn_open_folder.setText(self.t_str("ui.btn_open_folder"))
        self.btn_restore.setText(self.t_str("ui.btn_restore"))
        if self.active_character:
            fmt_str = self.t_str("ui.active_char")
            self.lbl_status.setText(fmt_str.replace("{0}", self.active_character.DisplayName) if "{0}" in fmt_str else fmt_str + " " + self.active_character.DisplayName)
        else:
            self.lbl_status.setText(self.t_str("ui.active_none"))
        self.lbl_ed_title.setText(self.t_str("ui.editor_title"))
        self.lbl_fld_id.setText(self.t_str("ui.fld_id"))
        self.lbl_fld_name.setText(self.t_str("ui.fld_name"))
        self.lbl_fld_wallpaper.setText(self.t_str("ui.fld_wallpaper"))
        self.lbl_fld_icon.setText(self.t_str("ui.fld_icon"))
        self.lbl_ui_colors.setText(self.t_str("ui.lbl_ui_colors"))
        self.lbl_konsole_colors.setText(self.t_str("ui.lbl_konsole_colors"))
        self.btn_delete.setText(self.t_str("ui.btn_delete"))
        self.btn_cancel.setText(self.t_str("ui.btn_cancel"))
        self.btn_save.setText(self.t_str("ui.btn_save"))

    def bind_events(self):
        self.btn_restore.clicked.connect(self.on_restore_defaults)
        self.btn_open_folder.clicked.connect(lambda: self.run_shell(f'xdg-open "{USER_PATH}"'))
        self.btn_terminal.clicked.connect(lambda: self.run_shell("konsole --profile EquestriaOS &"))
        self.btn_edit.clicked.connect(self.on_edit_current)
        self.btn_duplicate.clicked.connect(self.on_duplicate_current)
        self.btn_create.clicked.connect(self.on_create_new)
        self.btn_cancel.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        self.btn_save.clicked.connect(self.save_theme)
        self.btn_delete.clicked.connect(self.confirm_delete_theme)
        self.btn_browse_wall.clicked.connect(self.browse_wallpaper)
        self.btn_browse_icon.clicked.connect(self.browse_icon)

    def load_characters(self):
        json_path = os.path.join(USER_PATH, "characters.json")
        self.characters.clear()
        if os.path.exists(json_path):
            with open(json_path, "r", encoding='utf-8') as f:
                data = json.load(f)
                for c_dict in data.get("Characters", []):
                    theme_dict = c_dict.pop("KonsoleTheme", {})
                    char = EGCharacter(**c_dict)
                    char.KonsoleTheme = KonsoleColorScheme(**theme_dict)
                    self.characters.append(char)

    def build_ui(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        MAX_COLS = 4
        for i, char in enumerate(self.characters):
            btn = QPushButton()
            # ЗДЕСЬ УВЕЛИЧЕНЫ КНОПКИ ПЕРСОНАЖЕЙ (с 160x120 до 190x150)
            btn.setFixedSize(190, 150)

            is_active = self.active_character and self.active_character.Id == char.Id
            border_col = char.AccentColor if char.AccentColor else "transparent"
            hover_col = char.HoverColor if char.HoverColor else "rgb(40, 35, 60)"

            if is_active:
                btn.setStyleSheet(f"QPushButton {{ background-color: rgb(40, 35, 60); border: 3px solid {border_col}; border-radius: 16px; }}")
            else:
                btn.setStyleSheet(f"QPushButton {{ background-color: rgb(30, 25, 45); border: 2px solid {border_col}; border-radius: 16px; }} QPushButton:hover {{ background-color: {hover_col}; }}")

            lo = QVBoxLayout(btn)
            lo.setContentsMargins(8, 12, 8, 12)
            lo.setAlignment(Qt.AlignmentFlag.AlignCenter)

            icon_lbl = QLabel()
            pixmap = QPixmap(os.path.join(USER_PATH, char.IconPath))
            if not pixmap.isNull():
                # ЗДЕСЬ УВЕЛИЧЕНЫ КЬЮТИМАРКИ (с 64x64 до 84x84)
                icon_lbl.setPixmap(pixmap.scaled(84, 84, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            name_lbl = QLabel(char.DisplayName)
            name_lbl.setProperty("cssClass", "char-name")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lo.addWidget(icon_lbl)
            lo.addWidget(name_lbl)

            btn.clicked.connect(lambda checked, c=char: self.on_character_selected(c))
            self.grid_layout.addWidget(btn, i // MAX_COLS, i % MAX_COLS)

    def on_character_selected(self, character):
        self.active_character = character
        self.update_texts()
        self.build_ui()
        self.apply_wallpaper_slideshow(character.WallpaperPath)
        self.apply_kde_theme(character)
        self.apply_fastfetch(character)
        self.apply_konsole_colors(character)
        self.apply_konsole_profile(character)

    def parse_color_string(self, val, is_hex):
        if is_hex: return QColor(val if str(val).startswith('#') else f"#{val}")
        try:
            r, g, b = map(int, str(val).replace(' ', '').split(','))
            return QColor(r, g, b)
        except: return QColor(0, 0, 0)

    def open_editor(self):
        self.stacked_widget.setCurrentIndex(1)
        self.btn_delete.setVisible(not self.is_creating_new)
        self.fld_id.setText(self.editing_character.Id)
        self.fld_name.setText(self.editing_character.DisplayName)
        self.fld_wallpaper.setText(self.editing_character.WallpaperPath)
        self.fld_icon.setText(self.editing_character.IconPath)
        self.build_color_fields()

    def build_color_fields(self):
        for layout in [self.ui_colors_layout, self.konsole_colors_layout]:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()

        def create_color_field(parent_layout, label, attr_name, obj, is_hex, r, c):
            container = QWidget()
            container.setFixedWidth(250)
            lo = QHBoxLayout(container)
            lo.setContentsMargins(8, 4, 8, 4)

            lbl = QLabel(label)
            lbl.setProperty("cssClass", "editor-label")
            btn = QPushButton()
            btn.setFixedSize(40, 24)

            color = self.parse_color_string(getattr(obj, attr_name), is_hex)
            btn.setStyleSheet(f"background-color: {color.name()}; border-radius: 4px; border: 1px solid rgba(255, 255, 255, 0.2);")

            def pick_color():
                new_col = QColorDialog.getColor(color, self, f"Select {label}")
                if new_col.isValid():
                    btn.setStyleSheet(f"background-color: {new_col.name()}; border-radius: 4px; border: 1px solid rgba(255, 255, 255, 0.2);")
                    setattr(obj, attr_name, new_col.name() if is_hex else f"{new_col.red()},{new_col.green()},{new_col.blue()}")

            btn.clicked.connect(pick_color)
            lo.addWidget(lbl)
            lo.addWidget(btn)
            parent_layout.addWidget(container, r, c)

        create_color_field(self.ui_colors_layout, "Accent Color", "AccentColor", self.editing_character, True, 0, 0)
        create_color_field(self.ui_colors_layout, "Hover Color", "HoverColor", self.editing_character, True, 0, 1)

        row, col = 0, 0
        for field_name in self.editing_character.KonsoleTheme.__dataclass_fields__:
            create_color_field(self.konsole_colors_layout, field_name, field_name, self.editing_character.KonsoleTheme, False, row, col)
            col += 1
            if col > 2: col = 0; row += 1

    def on_edit_current(self):
        if not self.active_character: return
        self.is_creating_new = False
        self.editing_character = EGCharacter(**asdict(self.active_character))
        self.editing_character.KonsoleTheme = KonsoleColorScheme(**asdict(self.active_character.KonsoleTheme))
        self.open_editor()

    def on_duplicate_current(self):
        if not self.active_character: return
        self.is_creating_new = True
        self.editing_character = EGCharacter(**asdict(self.active_character))
        self.editing_character.KonsoleTheme = KonsoleColorScheme(**asdict(self.active_character.KonsoleTheme))
        self.editing_character.Id += "_copy"
        self.editing_character.DisplayName += " (Copy)"
        self.open_editor()

    def on_create_new(self):
        self.is_creating_new = True
        self.editing_character = EGCharacter(Id="new_pony", DisplayName="New Pony")
        self.open_editor()

    def save_theme(self):
        self.editing_character.Id = self.fld_id.text()
        self.editing_character.DisplayName = self.fld_name.text()
        self.editing_character.WallpaperPath = self.fld_wallpaper.text()
        self.editing_character.IconPath = self.fld_icon.text()
        self.editing_character.KonsoleProfile = self.editing_character.Id
        self.editing_character.KdeColorScheme = self.editing_character.Id

        if self.is_creating_new: self.characters.append(self.editing_character)
        else:
            idx = next((i for i, c in enumerate(self.characters) if c.Id == self.active_character.Id), -1)
            if idx != -1: self.characters[idx] = self.editing_character

        self.save_json_and_refresh()
        self.on_character_selected(self.editing_character)

    def confirm_delete_theme(self):
        msg = self.t_str("ui.delete_msg")
        msg = msg.replace("{0}", self.editing_character.DisplayName) if "{0}" in msg else msg + " " + self.editing_character.DisplayName
        reply = QMessageBox.question(self, self.t_str("ui.delete_title"), msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.characters = [c for c in self.characters if c.Id != self.editing_character.Id]
            self.save_json_and_refresh()
            if self.active_character and self.active_character.Id == self.editing_character.Id:
                self.active_character = None
                self.update_texts()

    def save_json_and_refresh(self):
        data = {"Characters": [asdict(c) for c in self.characters]}
        with open(os.path.join(USER_PATH, "characters.json"), "w", encoding='utf-8') as f: json.dump(data, f, indent=4)
        self.stacked_widget.setCurrentIndex(0)
        self.build_ui()

    def browse_wallpaper(self):
        start_path = os.path.join(USER_PATH, "Wallpapers")
        os.makedirs(start_path, exist_ok=True)
        path = QFileDialog.getExistingDirectory(self, "Select Wallpaper Folder", start_path)
        if path: self.fld_wallpaper.setText(self.process_picked_folder(path, "Wallpapers"))

    def browse_icon(self):
        start_path = os.path.join(USER_PATH, "MLP Cutiemarks")
        os.makedirs(start_path, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Select Cutiemark", start_path, "Images (*.png *.jpg)")
        if path: self.fld_icon.setText(self.process_picked_file(path, "MLP Cutiemarks"))

    def process_picked_folder(self, absolute_path, target_folder_parent):
        u_path = USER_PATH.replace("\\", "/")
        abs_path = absolute_path.replace("\\", "/").rstrip('/')
        if abs_path.startswith(u_path): return abs_path[len(u_path):].lstrip('/')
        dir_name = os.path.basename(abs_path)
        dest_dir = os.path.join(USER_PATH, target_folder_parent, dir_name)
        shutil.copytree(abs_path, dest_dir, dirs_exist_ok=True)
        return f"{target_folder_parent}/{dir_name}"

    def process_picked_file(self, absolute_path, target_folder):
        u_path = USER_PATH.replace("\\", "/")
        abs_path = absolute_path.replace("\\", "/")
        if abs_path.startswith(u_path): return abs_path[len(u_path):].lstrip('/')
        file_name = os.path.basename(abs_path)
        dest_dir = os.path.join(USER_PATH, target_folder)
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy(abs_path, os.path.join(dest_dir, file_name))
        return f"{target_folder}/{file_name}"

    def on_restore_defaults(self):
        if os.path.exists(USER_PATH): shutil.rmtree(USER_PATH)
        self.init_user_folder()
        self.load_characters()
        self.active_character = None
        self.update_texts()
        self.build_ui()

    def run_shell(self, command):
        subprocess.run(["/bin/bash", "-c", command], capture_output=True)

    def apply_wallpaper_slideshow(self, folder_rel_path):
        full_path = os.path.join(USER_PATH, folder_rel_path).replace("\\", "/")
        script = f"""qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "var allDesktops = desktops(); for (i=0;i<allDesktops.length;i++) {{ d = allDesktops[i]; d.wallpaperPlugin = 'org.kde.slideshow'; d.currentConfigGroup = Array('Wallpaper', 'org.kde.slideshow', 'General'); d.writeConfig('SlidePaths', '{full_path}'); }}" """
        self.run_shell(script)
        lock_script = f"""kwriteconfig6 --file kscreenlockerrc --group Greeter --key WallpaperPlugin "org.kde.slideshow" && kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper --group org.kde.slideshow --group General --key SlidePaths "{full_path}" """
        self.run_shell(lock_script)

    def apply_fastfetch(self, character):

        #====================================
        # REQUIRE PACKAGES
        # 1. fastfetch
        # 2. chafa
        # 3. imagemagick
        #====================================

        ff_dir = os.path.expanduser("~/.config/fastfetch")
        os.makedirs(ff_dir, exist_ok=True)
        color = self.hex_to_fastfetch(character.AccentColor)
        icon_path = os.path.join(USER_PATH, character.IconPath)
        json_content = f"""{{"logo": {{"source": "{icon_path}", "type": "chafa", "chafa": {{"symbols": "block"}}, "width": 18, "height": 8, "padding": {{"right": 2}}}}, "display": {{"separator": "  ", "color": {{"keys": "{color}", "title": "{color}"}}}}, "modules": ["title", "separator", {{"type": "os", "key": "  OS"}}, {{"type": "kernel", "key": "  Kernel"}}, {{"type": "de", "key": "  DE"}}, {{"type": "shell", "key": "  Shell"}}, {{"type": "terminal", "key": "  Terminal"}}, {{"type": "cpu", "key": "  CPU"}}, {{"type": "gpu", "key": "  GPU"}}, {{"type": "memory", "key": "  RAM"}}, {{"type": "disk", "key": "  Disk"}}, {{"type": "uptime", "key": "  Uptime"}}, "separator", {{"type": "colors", "symbol": "circle"}}]}}"""
        with open(os.path.join(ff_dir, "config.jsonc"), "w", encoding='utf-8') as f: f.write(json_content)

    def apply_konsole_colors(self, character):
        if not character.KonsoleTheme: return
        konsole_dir = os.path.expanduser("~/.local/share/konsole")
        os.makedirs(konsole_dir, exist_ok=True)
        c = character.KonsoleTheme
        content = f"[Background]\nColor={c.Background}\n\n[BackgroundIntense]\nColor={c.Color0Intense}\n\n[Color0]\nColor={c.Color0}\n\n[Color0Intense]\nColor={c.Color0Intense}\n\n[Color1]\nColor={c.Color1}\n\n[Color1Intense]\nColor={c.Color1Intense}\n\n[Color2]\nColor={c.Color2}\n\n[Color2Intense]\nColor={c.Color2Intense}\n\n[Color3]\nColor={c.Color3}\n\n[Color3Intense]\nColor={c.Color3Intense}\n\n[Color4]\nColor={c.Color4}\n\n[Color4Intense]\nColor={c.Color4Intense}\n\n[Color5]\nColor={c.Color5}\n\n[Color5Intense]\nColor={c.Color5Intense}\n\n[Color6]\nColor={c.Color6}\n\n[Color6Intense]\nColor={c.Color6Intense}\n\n[Color7]\nColor={c.Color7}\n\n[Color7Intense]\nColor={c.Color7Intense}\n\n[Foreground]\nColor={c.Foreground}\n\n[ForegroundIntense]\nColor={c.Color7Intense}\n\n[General]\nAnchor=0\nDescription={character.DisplayName}\nOpacity=1\nWallpaper=\n"
        with open(os.path.join(konsole_dir, "EquestriaOS.colorscheme"), "w", encoding='utf-8') as f: f.write(content)
        self.run_shell("for s in $(qdbus6 | grep konsole); do for e in $(qdbus6 $s | grep Sessions); do qdbus6 $s $e org.kde.konsole.Session.setColorScheme EquestriaOS 2>/dev/null; done; done")

    def apply_konsole_profile(self, character):
        konsole_dir = os.path.expanduser("~/.local/share/konsole")
        os.makedirs(konsole_dir, exist_ok=True)
        prompt_script = os.path.join(konsole_dir, "eg_character_prompt.sh")

        # ЗДЕСЬ ИСПРАВЛЕН БАГ ВЫВОДА ИМЕНИ ПЕРСОНАЖА В ПРОМПТ!
        script_content = r"""#!/bin/bash
if [ -n "$EG_CHARACTER" ]; then
    export PS1="\[\e[38;5;${EG_CHARACTER_COLOR}m\][${EG_CHARACTER}]\[\e[0m\] \[\e[1;32m\]\u@\h\[\e[0m\]:\[\e[1;34m\]\w\[\e[0m\]$ "
else
    export PS1="\[\e[1;32m\]\u@\h\[\e[0m\]:\[\e[1;34m\]\w\[\e[0m\]$ "
fi
"""
        with open(prompt_script, "w", encoding='utf-8') as f: f.write(script_content)
        self.run_shell(f'chmod +x "{prompt_script}"')

        env_path = os.path.join(konsole_dir, "eg_active.bashrc")
        # Сначала подгружаем дефолтный .bashrc, а потом уже накатываем наши переменные и промпт
        bashrc_source = "if [ -f ~/.bashrc ]; then source ~/.bashrc; fi\n"
        with open(env_path, "w", encoding='utf-8') as f:
            f.write(f'{bashrc_source}export EG_CHARACTER="{character.DisplayName}"\nexport EG_CHARACTER_COLOR="{self.get_ansi_color(character.Id)}"\nsource ~/.local/share/konsole/eg_character_prompt.sh\nfastfetch\n')

        prof_content = f"[Appearance]\nColorScheme=EquestriaOS\nFont=Noto Mono,11,-1,5,50,0,0,0,0,0\n\n[General]\nCommand=/bin/bash --rcfile {env_path}\nName=EquestriaOS\nIcon={os.path.join(USER_PATH, character.IconPath)}\nParent=FALLBACK/\nTerminalColumns=120\nTerminalRows=30\n\n[Interaction Options]\nAutoCopySelectedText=true\n\n[Scrolling]\nHistoryMode=2\nScrollBarPosition=2\n\n[Terminal Features]\nBlinkingCursorEnabled=true\n"
        with open(os.path.join(konsole_dir, "EquestriaOS.profile"), "w", encoding='utf-8') as f: f.write(prof_content)

        konsolerc = os.path.expanduser("~/.config/konsolerc")
        try:
            content = open(konsolerc, "r", encoding='utf-8').read() if os.path.exists(konsolerc) else ""
            if "[Desktop Entry]" in content:
                if "DefaultProfile=" in content:
                    lines = content.split('\n')
                    for i in range(len(lines)):
                        if lines[i].lstrip().startswith("DefaultProfile="): lines[i] = "DefaultProfile=EquestriaOS.profile"; break
                    content = '\n'.join(lines)
                else: content = content.replace("[Desktop Entry]", "[Desktop Entry]\nDefaultProfile=EquestriaOS.profile")
            else: content += "\n[Desktop Entry]\nDefaultProfile=EquestriaOS.profile\n"
            with open(konsolerc, "w", encoding='utf-8') as f: f.write(content)
        except: pass
        self.run_shell("for s in $(qdbus6 | grep konsole); do for e in $(qdbus6 $s | grep Sessions); do qdbus6 $s $e org.kde.konsole.Session.setProfile EquestriaOS 2>/dev/null; done; done")

    def apply_kde_theme(self, character):
        active_name = "EG_Active_A" if self.accent_toggle % 2 == 0 else "EG_Active_B"
        self.accent_toggle += 1
        clean_hex = character.AccentColor.lstrip('#')
        r, g, b = (int(clean_hex[0:2], 16), int(clean_hex[2:4], 16), int(clean_hex[4:6], 16)) if len(clean_hex) == 6 else (255, 255, 255)
        script = f"""TARGET_FILE="$HOME/.local/share/color-schemes/{active_name}.colors"; mkdir -p "$HOME/.local/share/color-schemes/"; if [ -f "$HOME/.local/share/color-schemes/{character.KdeColorScheme}.colors" ]; then cp "$HOME/.local/share/color-schemes/{character.KdeColorScheme}.colors" "$TARGET_FILE"; elif [ -f "/usr/share/color-schemes/{character.KdeColorScheme}.colors" ]; then cp "/usr/share/color-schemes/{character.KdeColorScheme}.colors" "$TARGET_FILE"; else printf '[Colors:Button]\\nBackgroundNormal=239,240,241\\nForegroundNormal=49,54,59\\n[Colors:Selection]\\nBackgroundNormal={r},{g},{b}\\nForegroundNormal=255,255,255\\n[Colors:View]\\nBackgroundNormal=252,252,252\\nForegroundNormal=49,54,59\\n[KDE]\\ncontrast=4\\n' > "$TARGET_FILE"; fi; kwriteconfig6 --file "$TARGET_FILE" --group General --key AccentColor "{r},{g},{b}"; kwriteconfig6 --file "$TARGET_FILE" --group General --key Name "{active_name}"; kwriteconfig6 --file "$TARGET_FILE" --group General --key ColorScheme "{active_name}"; kwriteconfig6 --file kdeglobals --group General --key AccentColor "{r},{g},{b}"; kwriteconfig6 --file kdeglobals --group General --key LastUsedCustomAccentColor "{r},{g},{b}"; plasma-apply-colorscheme "{active_name}" """
        self.run_shell(script)

    def get_ansi_color(self, char_id):
        return {"sunset": "214", "twilight": "135", "rainbow": "39", "rarity": "189", "pinkie": "205", "applejack": "136", "fluttershy": "228"}.get(char_id, "255")

    def hex_to_fastfetch(self, hex_color):
        c = QColor(hex_color)
        h, s, v, _ = c.getHsvF()
        if s < 0.2: return "white" if v > 0.5 else "black"
        h *= 360
        if h < 30: return "red"
        if h < 60: return "yellow"
        if h < 150: return "green"
        if h < 200: return "cyan"
        if h < 260: return "blue"
        if h < 330: return "magenta"
        return "red"

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setDesktopFileName("equestria-theme-switcher.desktop")

    icon_path = "/usr/share/pixmaps/equestria-os-logo.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        app.setWindowIcon(QIcon.fromTheme("preferences-desktop-theme"))

    font_path = os.path.join(SYSTEM_PATH, "equestria_cyrillic.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                # ЗДЕСЬ УВЕЛИЧЕН БАЗОВЫЙ ШРИФТ ПРИЛОЖЕНИЯ (с 11 до 13)
                app.setFont(QFont(families[0], 13))

    window = EGThemeSwitcher()
    window.show()
    sys.exit(app.exec())
