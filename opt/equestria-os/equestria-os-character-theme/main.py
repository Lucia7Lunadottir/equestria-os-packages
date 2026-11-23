import sys
import os
import json
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path
from dataclasses import dataclass, asdict, field, fields
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFileDialog, QColorDialog, QMessageBox, QComboBox, QCheckBox)
from PyQt6.QtGui import QIcon, QPixmap, QColor, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QEvent
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit import live_i18n
from equestria_kit.widgets import font_families

from ui import Ui_MainWindow, APP_STYLE, ModeSwitch
from character_card import CharacterCard
import kde_laf
import palette_model
import keyboard_look
import asset_sync
from equestria_kit.character_store import CharacterStore
from keyboard_preview import KeyboardPreview

SYSTEM_PATH = os.path.dirname(os.path.abspath(__file__))

# Переводы лежат в locales/<язык>.json рядом с main.py (ключ -> текст)
CATALOG = live_i18n.Catalog("equestria-os-character-theme", __file__)
USER_PATH = os.path.expanduser("~/.local/share/EquestriaOS/Themes/")

_QDBUS_BIN = None

def find_qdbus():
    """Ищет доступный бинарь qdbus: его уже переименовывали (qdbus → qdbus6),
    поэтому перебираем известные имена вместо жёсткой привязки."""
    global _QDBUS_BIN
    if _QDBUS_BIN is None:
        for candidate in ("qdbus6", "qdbus-qt6", "qdbus"):
            if shutil.which(candidate):
                _QDBUS_BIN = candidate
                break
        else:
            _QDBUS_BIN = "qdbus6"
    return _QDBUS_BIN

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
    # Только ПРАВКИ палитры пользователя ({роль: '#rrggbb'}); пусто — стандартные цвета персонажа.
    # Остальное берётся из общей палитры equestria_kit, см. palette_model.py
    UiPalette: dict = field(default_factory=dict)
    # То же для ДНЯ: правки поверх дня, выведенного из ночи, и свой акцент выделения дня
    # (пусто — как ночной AccentColor). Нужны, чтобы KDE-приложения днём читались так, как хочет пользователь.
    UiPaletteDay: dict = field(default_factory=dict)
    AccentColorDay: str = ""
    # Вид на подсветке клавиатуры: {"Color": "#rrggbb", "Rainbow": true}; пусто — цвет акцента.
    # Какой именно эффект даёт «радугу», решает equestria-os-settings. См. keyboard_look.py
    KeyboardBacklight: dict = field(default_factory=dict)

class EGThemeSwitcher(QMainWindow, Ui_MainWindow):
    def __init__(self, title_font_family=None):
        super().__init__()
        self.setupUi(self)
        self.setWindowTitle("Equestria OS Character Theme")
        style = APP_STYLE
        if title_font_family:
            # Шрифт Эквестрии — только на заголовках и именах персонажей;
            # кнопки и описания используют системный, читаемый шрифт
            style += (
                f'\nQLabel[cssClass="title"] {{ font-family: "{title_font_family}"; }}'
                f'\nQLabel[cssClass="char-name"] {{ font-family: "{title_font_family}"; }}'
            )
        # Само приложение тоже в цветах активного персонажа: ThemeManager
        # перекрашивает его сразу после клика по карточке.
        kit_qt.style(self, style)

        self._apply_lock = threading.Lock()
        self.store = CharacterStore(USER_PATH, SYSTEM_PATH)
        self.kbd_preview = KeyboardPreview()
        self.characters = []
        self.active_character = None
        self.editing_character = None
        self.editing_original_id = None
        self.is_creating_new = False

        self.available_langs = []
        self.current_lang = "en"

        self.init_user_folder()
        self.load_localization()
        self.detect_system_language()

        self.day_night = kde_laf.DayNight()


        self.bind_events()
        self.load_characters()
        self.refresh_stale_kde_themes()
        # Отмечаем активного персонажа сразу при запуске (НЕ применяя тему):
        # можно сразу редактировать, не кликая по карточке
        self.restore_active_character()

        self.build_language_selector()
        self.build_ui()
        self.update_texts()

    def init_user_folder(self):
        # Создаем базовую папку, если её нет
        os.makedirs(USER_PATH, exist_ok=True)

        # Список того, что РЕАЛЬНО нужно скопировать пользователю
        assets_to_copy = ["Wallpapers", "MLP Cutiemarks"]   # данные персонажей — в characters.d, их не копируем

        for item in assets_to_copy:
            src = os.path.join(SYSTEM_PATH, item)
            dst = os.path.join(USER_PATH, item)

            # Если это дефолтный файл/папка есть в системе, копируем его
            if os.path.exists(src):
                if os.path.isdir(src):
                    if not os.path.exists(dst):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        # Папка уже есть: докладываем только то, чего у пользователя нет
                        # (новая встроенная тема привозит свою папку обоев и иконку); его файлы не трогаем
                        asset_sync.add_missing(src, dst)
                else:
                    # Если файла у пользователя еще нет, копируем
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)

    def load_localization(self):
        # список языков — найденные файлы locales/*.json, без списка в коде
        self.available_langs = list(CATALOG.languages)

    def t_str(self, key):
        return str(CATALOG.tr(key))

    def detect_system_language(self):
        sys_code = CATALOG.lang
        self.current_lang = sys_code if sys_code in self.available_langs else (self.available_langs[0] if self.available_langs else "en")


    # --- режим «Авто / Светлая / Тёмная» — общий с KDE (см. kde_laf.DayNight)
    def refresh_mode(self):
        """Показать режим KDE: его могли сменить в «Параметрах» или в виджете «Яркость и цвет»."""
        if hasattr(self, "mode_switch"):
            self.mode_switch.set_current(self.day_night.mode())

    def set_mode(self, mode):
        self.mode_switch.set_current(mode)
        # plasma-apply-lookandfeel занимает секунду — в фоне, как и смена персонажа
        threading.Thread(target=self._set_mode_bg, args=(mode,), daemon=True).start()

    def _set_mode_bg(self, mode):
        with self._apply_lock:
            self.day_night.set_mode(mode)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.refresh_mode()
        super().changeEvent(e)

    def _state_path(self):
        return os.path.join(USER_PATH, "state.json")

    def _save_state(self):
        """Запоминает выбранного персонажа, чтобы при следующем запуске
        отметить его сразу, без повторного клика."""
        try:
            with open(self._state_path(), "w", encoding="utf-8") as f:
                json.dump({"active_character":
                           self.active_character.Id if self.active_character else None}, f)
        except OSError:
            pass

    def restore_active_character(self):
        """Восстанавливает отметку активного персонажа при запуске.
        Тема при этом НЕ применяется повторно."""
        active_id = None
        try:
            with open(self._state_path(), encoding="utf-8") as f:
                active_id = json.load(f).get("active_character")
        except (OSError, json.JSONDecodeError):
            pass
        char = next((c for c in self.characters if c.Id == active_id), None)
        if char is None:
            char = self._detect_character_by_accent()
        self.active_character = char

    def _detect_character_by_accent(self):
        """Фолбэк для первого запуска (state.json ещё нет): угадывает
        активного персонажа по акцентному цвету KDE."""
        try:
            res = subprocess.run(
                ["kreadconfig6", "--file", "kdeglobals",
                 "--group", "General", "--key", "AccentColor"],
                capture_output=True, text=True, timeout=3)
            parts = [x.strip() for x in res.stdout.strip().split(",")]
            if len(parts) < 3:
                return None
            rgb = tuple(int(x) for x in parts[:3])
        except Exception:
            return None
        for c in self.characters:
            h = str(c.AccentColor).lstrip("#")
            if len(h) != 6:
                continue
            try:
                if (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)) == rgb:
                    return c
            except ValueError:
                continue
        return None

    # ── Импорт / экспорт тем (.eqtheme = zip: character.json + ассеты) ──

    def export_current_theme(self):
        """Экспортирует персонажа, открытого в редакторе, в один файл .eqtheme
        вместе с обоями и кьютимаркой — для обмена темами."""
        char = self.editing_character
        if not char:
            return
        default = os.path.expanduser(f"~/{char.Id or 'theme'}.eqtheme")
        path, _ = QFileDialog.getSaveFileName(
            self, self.t_str("ui.btn_export"), default,
            "Equestria OS Theme (*.eqtheme)")
        if not path:
            return
        if not path.endswith(".eqtheme"):
            path += ".eqtheme"
        data = self._char_json(char)
        data["FormatVersion"] = 3   # 2: + UiPalette; 3: + UiPaletteDay, AccentColorDay; старые файлы импортируются как раньше
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("character.json",
                           json.dumps(data, indent=4, ensure_ascii=False))
                icon_abs = os.path.join(USER_PATH, char.IconPath) if char.IconPath else ""
                if icon_abs and os.path.isfile(icon_abs):
                    z.write(icon_abs, f"icon/{os.path.basename(icon_abs)}")
                wall_abs = os.path.join(USER_PATH, char.WallpaperPath) if char.WallpaperPath else ""
                if wall_abs and os.path.isdir(wall_abs):
                    for root, _dirs, files in os.walk(wall_abs):
                        for fn in files:
                            fp = os.path.join(root, fn)
                            rel = os.path.relpath(fp, wall_abs)
                            z.write(fp, f"wallpapers/{rel}")
        except OSError as e:
            QMessageBox.warning(self, "", str(e))

    def import_theme(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.t_str("ui.btn_import"), os.path.expanduser("~"),
            "Equestria OS Theme (*.eqtheme *.zip)")
        if not path:
            return
        try:
            char = self._import_theme_file(path)
        except (zipfile.BadZipFile, json.JSONDecodeError, KeyError, OSError, TypeError) as e:
            QMessageBox.warning(self, "", f"{self.t_str('ui.import_error')}\n{e}")
            return
        self.build_ui()
        msg = self.t_str("ui.import_done")
        msg = msg.replace("{0}", char.DisplayName) if "{0}" in msg else f"{msg} {char.DisplayName}"
        QMessageBox.information(self, "", msg)

    def _import_theme_file(self, path):
        """Читает .eqtheme и добавляет персонажа. Id при конфликте получает
        суффикс, ассеты распаковываются в отдельные подпапки персонажа —
        чужая тема не может перезаписать файлы существующих."""
        known_char = {f.name for f in fields(EGCharacter)}
        known_kon = {f.name for f in fields(KonsoleColorScheme)}
        with zipfile.ZipFile(path) as z:
            with z.open("character.json") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise TypeError("character.json: not an object")
            theme_dict = data.pop("KonsoleTheme", {}) or {}
            char = EGCharacter(**{k: v for k, v in data.items() if k in known_char})
            char.KonsoleTheme = KonsoleColorScheme(
                **{k: v for k, v in theme_dict.items() if k in known_kon})
            char.UiPalette = palette_model.clean(char.UiPalette)   # файл чужой: только известные роли и цвета
            char.UiPaletteDay = palette_model.clean(char.UiPaletteDay)
            char.AccentColorDay = palette_model.clean_color(char.AccentColorDay)
            char.KeyboardBacklight = keyboard_look.clean(char.KeyboardBacklight)

            base_id = str(char.Id).strip() or "imported"
            new_id, n = base_id, 2
            while any(c.Id == new_id for c in self.characters):
                new_id = f"{base_id}_{n}"
                n += 1
            char.Id = new_id
            char.KonsoleProfile = new_id
            char.KdeColorScheme = new_id

            members = z.namelist()

            icon_members = [m for m in members
                            if m.startswith("icon/") and not m.endswith("/")]
            char.IconPath = ""
            if icon_members:
                base = os.path.basename(icon_members[0])
                if base:
                    rel = os.path.join("MLP Cutiemarks", f"{new_id}_{base}")
                    dest = os.path.join(USER_PATH, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(icon_members[0]) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    char.IconPath = rel

            wall_members = [m for m in members
                            if m.startswith("wallpapers/") and not m.endswith("/")]
            char.WallpaperPath = ""
            if wall_members:
                wall_rel = os.path.join("Wallpapers", new_id)
                for m in wall_members:
                    rel = os.path.normpath(m[len("wallpapers/"):])
                    # защита от zip-slip: путь не должен выходить за пределы папки
                    if rel.startswith("..") or os.path.isabs(rel):
                        continue
                    dest = os.path.join(USER_PATH, wall_rel, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(m) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                char.WallpaperPath = wall_rel

        self.characters.append(char)
        self.save_json_and_refresh()
        return char


    def build_language_selector(self):
        while self.lang_layout.count():
            item = self.lang_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        # Компактный выпадающий список языков вместо ряда кнопок
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LangCombo")
        for code in self.available_langs:
            self.lang_combo.addItem(CATALOG.language_name(code), code)
        idx = self.lang_combo.findData(self.current_lang)
        if idx != -1:
            self.lang_combo.setCurrentIndex(idx)
        # activated срабатывает только при выборе пользователем — без рекурсии
        self.lang_combo.activated.connect(
            lambda i: self.set_language(self.lang_combo.itemData(i)))
        # Режим «Авто / Светлая / Тёмная» — в том же ряду: это настройка, а не действие
        self.lbl_mode = QLabel()
        self.lbl_mode.setProperty("cssClass", "mode-label")
        self.mode_switch = ModeSwitch(kde_laf.MODES)
        self.mode_switch.changed.connect(self.set_mode)
        self.lang_layout.addWidget(self.lbl_mode)
        self.lang_layout.addWidget(self.mode_switch)
        self.lang_layout.addSpacing(24)
        self.lang_layout.addWidget(self.lang_combo)
        # «Фоны как в KDE» — настройка стиля целиком, поэтому здесь, рядом с режимом
        self.chk_kde_bg = QCheckBox()
        self.chk_kde_bg.setChecked(kde_laf.kde_backgrounds())
        self.chk_kde_bg.toggled.connect(self.on_kde_bg_toggled)
        self.lang_layout.addSpacing(24)
        self.lang_layout.addWidget(self.chk_kde_bg)
        self.update_mode_texts()
        self.refresh_mode()

    def update_mode_texts(self):
        if not hasattr(self, "mode_switch"):
            return
        self.lbl_mode.setText(self.t_str("ui.mode_label"))
        self.chk_kde_bg.setText(self.pal_text("pal.kde_bg"))
        self.chk_kde_bg.setToolTip(self.pal_text("pal.kde_bg_tip"))
        self.mode_switch.set_texts({m: self.t_str(f"ui.mode_{m}") for m in kde_laf.MODES},
                                   {m: self.t_str(f"ui.mode_{m}_tip") for m in kde_laf.MODES})

    def set_language(self, code):
        self.current_lang = CATALOG.set_language(code) or code  # ещё и сохраняет выбор
        idx = self.lang_combo.findData(code)
        if idx != -1 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.setCurrentIndex(idx)
        self.update_texts()
        self.build_ui()  # перестраиваем карточки ради локализованных тултипов ✎

    def update_texts(self):
        self.lbl_title.setText(self.t_str("ui.title"))
        self.lbl_subtitle.setText(self.t_str("ui.subtitle"))
        self.btn_duplicate.setText(self.t_str("ui.btn_duplicate"))
        self.btn_create.setToolTip(self.t_str("ui.btn_create_new"))
        self.btn_import.setToolTip(self.t_str("ui.btn_import"))
        self.btn_export.setText(self.t_str("ui.btn_export"))
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
        self.lbl_ui_colors.setText(self.pal_text("pal.title"))
        self.lbl_pal_hint.setText(self.pal_text("pal.hint"))
        self.btn_pal_reset.setText(self.pal_text("pal.reset"))
        self.btn_pal_reset.setToolTip(self.pal_text("pal.reset_tip"))
        self.btn_pal_reset_day.setText(self.pal_text("pal.reset_day"))
        self.btn_pal_reset_day.setToolTip(self.pal_text("pal.reset_day_tip"))
        self.btn_pal_night.setText(self.pal_text("pal.night"))
        self.btn_pal_day.setText(self.pal_text("pal.day"))
        for b in (self.btn_pal_night, self.btn_pal_day):
            b.setToolTip(self.pal_text("pal.mode_tip"))
        self.lbl_pal_mode_note.setText(self.pal_text("pal.day_auto"))
        self.retranslate_keyboard_block()
        self.on_palette_more_toggled(self.btn_pal_more.isChecked())
        self.palette_preview.set_titles(self.pal_text("pal.night"), self.pal_text("pal.day"))
        self.lbl_konsole_colors.setText(self.t_str("ui.lbl_konsole_colors"))
        self.btn_delete.setText(self.t_str("ui.btn_delete"))
        self.btn_cancel.setText(self.t_str("ui.btn_cancel"))
        self.btn_save.setText(self.t_str("ui.btn_save"))

        self.update_mode_texts()

    def bind_events(self):
        self.btn_restore.clicked.connect(self.on_restore_defaults)
        self.btn_open_folder.clicked.connect(lambda: self.run_shell(f'xdg-open "{USER_PATH}"'))
        self.btn_terminal.clicked.connect(lambda: self.run_shell("konsole --profile EquestriaOS &"))
        self.btn_duplicate.clicked.connect(self.on_duplicate_current)
        self.btn_create.clicked.connect(self.on_create_new)
        self.btn_import.clicked.connect(self.import_theme)
        self.btn_export.clicked.connect(self.export_current_theme)
        self.btn_cancel.clicked.connect(self.cancel_editor)
        self.btn_save.clicked.connect(self.save_theme)
        self.btn_delete.clicked.connect(self.confirm_delete_theme)
        self.btn_browse_wall.clicked.connect(self.browse_wallpaper)
        self.btn_browse_icon.clicked.connect(self.browse_icon)
        self.chk_kbd_rainbow.toggled.connect(self.on_kbd_rainbow_toggled)
        self.btn_kbd_color.clicked.connect(self.on_kbd_pick_color)
        self.btn_kbd_color_auto.clicked.connect(self.on_kbd_color_auto)
        self.btn_pal_more.toggled.connect(self.on_palette_more_toggled)
        self.btn_pal_reset.clicked.connect(self.on_palette_reset)
        self.btn_pal_reset_day.clicked.connect(self.on_palette_reset_day)
        self.btn_pal_night.toggled.connect(self.on_palette_mode_changed)


    def load_characters(self):
        self.characters.clear()
        # Старый общий characters.json конвертируется в файлы по персонажам (сам он
        # сохраняется как characters.json.pre-split). Битый файл не трогаем и не роняем приложение.
        try:
            self.store.migrate_legacy()
        except OSError as e:
            print(f"Не удалось конвертировать characters.json: {e}", file=sys.stderr)
        data = {"Characters": [dict(c) for c in self.store.read()]}
        known_char = {f.name for f in fields(EGCharacter)}
        known_kon = {f.name for f in fields(KonsoleColorScheme)}
        for c_dict in data.get("Characters", []):
            if not isinstance(c_dict, dict):
                continue
            theme_dict = c_dict.pop("KonsoleTheme", {}) or {}
            # Неизвестные поля игнорируем: файл, записанный более новой
            # версией приложения, не должен ломать текущую
            char = EGCharacter(**{k: v for k, v in c_dict.items() if k in known_char})
            char.KonsoleTheme = KonsoleColorScheme(
                **{k: v for k, v in theme_dict.items() if k in known_kon})
            char.UiPalette = palette_model.clean(char.UiPalette)
            char.UiPaletteDay = palette_model.clean(char.UiPaletteDay)
            char.AccentColorDay = palette_model.clean_color(char.AccentColorDay)
            char.KeyboardBacklight = keyboard_look.clean(char.KeyboardBacklight)
            char.AccentColor = kde_laf.migrated_accent(char.Id, char.AccentColor)
            self.characters.append(char)

    def build_ui(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        MAX_COLS = 4
        self.cards = {}
        for i, char in enumerate(self.characters):
            btn = CharacterCard(char.DisplayName, char.AccentColor, os.path.join(USER_PATH, char.IconPath))
            is_active = bool(self.active_character and self.active_character.Id == char.Id)
            btn.set_selected(is_active, animate=False)
            btn.clicked.connect(lambda checked=False, c=char: self.on_character_selected(c))
            self.cards[char.Id] = btn

            # Иконка редактирования в углу карточки: открывает редактор
            # ЭТОГО персонажа, не применяя его тему
            edit_btn = QPushButton("✎", btn)
            edit_btn.setObjectName("CardEditBtn")
            edit_btn.setFixedSize(26, 26)
            edit_btn.move(btn.width() - 26 - 10, 10)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setToolTip(self.t_str("ui.btn_edit"))
            edit_btn.clicked.connect(lambda checked=False, c=char: self.on_edit_character(c))

            self.grid_layout.addWidget(btn, i // MAX_COLS, i % MAX_COLS)

    def _refresh_selection(self):
        """Выбор меняется анимацией на существующих карточках — без перестройки сетки."""
        active = self.active_character.Id if self.active_character else None
        for cid, card in getattr(self, "cards", {}).items():
            card.set_selected(cid == active)

    def on_character_selected(self, character):
        self.active_character = character
        self._save_state()
        self.update_texts()
        self._refresh_selection()
        # Обои, KDE, Konsole и fastfetch применяются через qdbus/kwriteconfig и
        # занимают секунды — в фоне, иначе окно замирает вместе с анимацией выбора.
        # Быстрые клики подряд: применяется только последний выбранный персонаж.
        self._apply_gen = getattr(self, "_apply_gen", 0) + 1
        gen = self._apply_gen
        threading.Thread(target=self._apply_character_bg, args=(character, gen), daemon=True).start()

    def _apply_character_bg(self, character, gen):
        with self._apply_lock:
            if gen != self._apply_gen:
                return
            for step in (lambda: self.apply_wallpaper_slideshow(character.WallpaperPath),
                         lambda: self.apply_kde_theme(character),
                         lambda: self.apply_fastfetch(character),
                         lambda: self.apply_konsole_colors(character),
                         lambda: self.apply_konsole_profile(character)):
                if gen != self._apply_gen:
                    return
                try:
                    step()
                except Exception as e:  # noqa: BLE001 — фоновый поток не должен ронять приложение
                    print(f"[character-theme] {e}", file=sys.stderr)

    def parse_color_string(self, val, is_hex):
        if is_hex: return QColor(val if str(val).startswith('#') else f"#{val}")
        try:
            r, g, b = map(int, str(val).replace(' ', '').split(','))
            return QColor(r, g, b)
        except Exception: return QColor(0, 0, 0)

    def open_editor(self):
        self.stacked_widget.setCurrentIndex(1)
        self.btn_delete.setVisible(not self.is_creating_new)
        self.btn_duplicate.setVisible(not self.is_creating_new)
        self.btn_export.setVisible(not self.is_creating_new)
        self.fld_id.setText(self.editing_character.Id)
        self.fld_name.setText(self.editing_character.DisplayName)
        self.fld_wallpaper.setText(self.editing_character.WallpaperPath)
        self.fld_icon.setText(self.editing_character.IconPath)
        self.build_color_fields()
        self.load_keyboard_block()

    # ── Редактор палитры (логика — в palette_model.py, предпросмотр — в palette_editor.py) ──

    def pal_text(self, key):
        return palette_model.text(key, CATALOG.tr, self.current_lang)

    def _char_dict(self):
        return asdict(self.editing_character)

    @staticmethod
    def _paint_swatch(btn, hex_color):
        btn.setStyleSheet(f"background-color: {hex_color}; border-radius: 4px; "
                          "border: 1px solid rgba(255, 255, 255, 0.2);")

    @property
    def pal_variant(self):
        """Какую половину пары сейчас правим: 'Dark' (ночь) или 'Light' (день)."""
        return palette_model.DAY if self.btn_pal_day.isChecked() else palette_model.NIGHT

    def _pal_label(self, key):
        return self.pal_text("pal.@AccentColorDay" if key == "@AccentColorDay" else f"pal.{key}")

    def _add_palette_field(self, layout, key, row, col):
        container = QWidget()
        container.setFixedWidth(250)
        lo = QHBoxLayout(container)
        lo.setContentsMargins(8, 4, 8, 4)
        label = self._pal_label(key)
        lbl = QLabel(label)
        lbl.setProperty("cssClass", "editor-label")
        lbl.setWordWrap(True)
        btn = QPushButton()
        btn.setFixedSize(40, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        variant = self.pal_variant
        self._paint_swatch(btn, palette_model.value(self._char_dict(), key, variant))

        def pick():
            current = QColor(palette_model.value(self._char_dict(), key, variant))
            new_col = QColorDialog.getColor(current, self, label)
            if not new_col.isValid():
                return
            chd = self._char_dict()
            palette_model.set_value(chd, key, new_col.name(), variant)
            if key.startswith("@"):
                setattr(self.editing_character, key[1:], chd[key[1:]])
            else:
                own = palette_model._own_key(variant)
                setattr(self.editing_character, own, chd[own])
            self.refresh_palette_editor()

        btn.clicked.connect(pick)
        lo.addWidget(lbl)
        lo.addWidget(btn)
        layout.addWidget(container, row, col)
        self._pal_swatches[key] = btn

    def _build_palette_fields(self):
        """Поля палитры для выбранной половины (ночь/день). Пересобираются при переключении."""
        for layout in (self.ui_colors_layout, self.pal_more_layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        self._pal_swatches = {}
        day = self.pal_variant == palette_model.DAY
        groups = palette_model.GROUPS_DAY if day else palette_model.GROUPS
        advanced = palette_model.ADVANCED_DAY if day else palette_model.ADVANCED
        row = 0
        for group, keys in groups:
            heading = QLabel(self.pal_text(f"pal.grp_{group}"))
            heading.setProperty("cssClass", "pal-group")
            self.ui_colors_layout.addWidget(heading, row, 0, 1, 3)
            row += 1
            for n, key in enumerate(keys):
                self._add_palette_field(self.ui_colors_layout, key, row + n // 3, n % 3)
            row += (len(keys) + 2) // 3
        for n, key in enumerate(advanced):
            self._add_palette_field(self.pal_more_layout, key, n // 3, n % 3)
        self.btn_pal_reset_day.setVisible(day)
        self.lbl_pal_mode_note.setVisible(day)

    # ── Подсветка клавиатуры персонажа (данные — в keyboard_look.py) ──

    def retranslate_keyboard_block(self):
        self.lbl_kbd.setText(self.t_str("kbd.title"))
        hint = self.t_str("kbd.hint")
        if not self.kbd_preview.available():   # без пакета настроек выбор сохранится, но нигде не применится
            hint += "\n" + self.t_str("kbd.needs_settings")
        self.lbl_kbd_hint.setText(hint)
        self.btn_kbd_color_auto.setText(self.t_str("kbd.color_auto"))
        self.chk_kbd_rainbow.setText(self.t_str("kbd.rainbow"))
        self.refresh_keyboard_block()

    def load_keyboard_block(self):
        look = keyboard_look.clean(self.editing_character.KeyboardBacklight)
        self.chk_kbd_rainbow.blockSignals(True)
        self.chk_kbd_rainbow.setChecked(bool(look.get("Rainbow")))
        self.chk_kbd_rainbow.blockSignals(False)
        self.refresh_keyboard_block()

    def refresh_keyboard_block(self):
        """Цвет можно менять всегда. Пока свой не выбран, на кнопке цвет акцента — он и будет на клавиатуре."""
        look = self.editing_character.KeyboardBacklight if self.editing_character else {}
        self.btn_kbd_color_auto.setEnabled(bool(look.get("Color")))
        shown = look.get("Color") or (self.editing_character.AccentColor if self.editing_character else "#ffffff")
        self._paint_swatch(self.btn_kbd_color, shown)

    def on_kbd_rainbow_toggled(self, checked):
        look = dict(self.editing_character.KeyboardBacklight)
        if checked:
            look["Rainbow"] = True
        else:
            look.pop("Rainbow", None)
        self.editing_character.KeyboardBacklight = keyboard_look.clean(look)
        self.refresh_keyboard_block()
        self.preview_keyboard()

    def preview_keyboard(self, color=None):
        """Показать вид на клавиатуре до сохранения (если установлен pg-kbd-preview).
        color — цвет, который выбирают прямо сейчас; без него — сохранённый в правке."""
        look = self.editing_character.KeyboardBacklight
        self.kbd_preview.show(color or look.get("Color"), self.editing_character.AccentColor,
                              bool(look.get("Rainbow")))

    def cancel_editor(self):
        self.kbd_preview.restore()   # вернуть то, что на клавиатуре должно быть по-настоящему
        self.stacked_widget.setCurrentIndex(0)

    def closeEvent(self, event):
        if self.stacked_widget.currentIndex() == 1:
            self.kbd_preview.restore()
        super().closeEvent(event)

    def on_kbd_pick_color(self):
        look = self.editing_character.KeyboardBacklight
        dialog = QColorDialog(QColor(look.get("Color") or self.editing_character.AccentColor), self)
        dialog.setWindowTitle(self.t_str("kbd.color"))
        # Цвет сразу виден на клавиатуре, пока выбираешь
        dialog.currentColorChanged.connect(lambda c: self.preview_keyboard(c.name()))
        if dialog.exec() and dialog.currentColor().isValid():
            self.editing_character.KeyboardBacklight = keyboard_look.clean(
                {**look, "Color": dialog.currentColor().name()})
        self.refresh_keyboard_block()
        self.preview_keyboard()   # итог (или прежний вид, если закрыли без выбора)

    def on_kbd_color_auto(self):
        look = dict(self.editing_character.KeyboardBacklight)
        look.pop("Color", None)
        self.editing_character.KeyboardBacklight = look
        self.refresh_keyboard_block()
        self.preview_keyboard()

    def on_kde_bg_toggled(self, checked):
        """«Фоны как в KDE» — общая настройка стиля: фоны окон, списков, кнопок берутся из обычного
        Breeze, цвета персонажей остаются в акценте и выделении. Свои цвета фонов не теряются.
        Пересборка и повторное применение активной темы — в фоне (занимает секунду)."""
        kde_laf.set_kde_backgrounds(bool(checked))
        if hasattr(self, "palette_preview") and getattr(self, "editing_character", None):
            self.refresh_palette_editor()
        threading.Thread(target=self._refresh_kde_bg_bg, daemon=True).start()

    def _refresh_kde_bg_bg(self):
        with self._apply_lock:
            try:
                kde_laf.refresh_user_themes(self.day_night)
            except Exception as e:  # noqa: BLE001
                print(f"Не удалось обновить темы KDE: {e}", file=sys.stderr)

    def on_palette_mode_changed(self, *_):
        self._build_palette_fields()
        self.refresh_palette_editor()

    def refresh_palette_editor(self):
        """Цвета на кнопках, предпросмотр и предупреждения — после любого изменения цвета."""
        chd = self._char_dict()
        variant = self.pal_variant
        for key, btn in self._pal_swatches.items():
            self._paint_swatch(btn, palette_model.value(chd, key, variant))
        self.palette_preview.set_character(chd)
        # предупреждаем о плохо читаемом тексте в выбранной половине (схема KDE всё равно подтянет текст)
        pal = palette_model.day_effective(chd) if variant == palette_model.DAY else palette_model.effective(chd)
        warns = kde_laf.palette_warnings(pal)
        if warns:
            fg, bg, ratio = warns[0]
            msg = self.pal_text("pal.warn")
            for i, v in enumerate((self.pal_text(f"pal.{fg}"), self.pal_text(f"pal.{bg}"), ratio)):
                msg = msg.replace("{" + str(i) + "}", str(v))
            self.lbl_pal_warning.setText(msg)
        self.lbl_pal_warning.setVisible(bool(warns))

    def on_palette_more_toggled(self, checked):
        self.pal_more_container.setVisible(checked)
        self.btn_pal_more.setText(self.pal_text("pal.less" if checked else "pal.more"))

    def on_palette_reset(self):
        """Вернуть стандартные цвета: правки палитры (ночи и дня) убираются, а у встроенного персонажа
        акцент и цвет наведения возвращаются заводскими. Это правка в редакторе — запишется
        по «Сохранить», а «Отмена» вернёт всё как было."""
        char = self.editing_character
        original = self.store.system_character(self.editing_original_id or char.Id)
        char.UiPalette = {}
        char.UiPaletteDay = {}
        char.AccentColorDay = ""
        if original:
            char.AccentColor = str(original.get("AccentColor") or char.AccentColor)
            char.HoverColor = str(original.get("HoverColor") or char.HoverColor)
            char.UiPaletteDay = palette_model.clean(original.get("UiPaletteDay"))
            char.AccentColorDay = palette_model.clean_color(original.get("AccentColorDay"))
        self._build_palette_fields()
        self.refresh_palette_editor()

    def on_palette_reset_day(self):
        """Вернуть только цвета дня: он снова считается из ночной палитры."""
        self.editing_character.UiPaletteDay = {}
        self.editing_character.AccentColorDay = ""
        self._build_palette_fields()
        self.refresh_palette_editor()

    def build_color_fields(self):
        for layout in [self.ui_colors_layout, self.pal_more_layout, self.konsole_colors_layout]:
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

        # Палитра интерфейса: фоны, текст, акценты (+ «Дополнительно»). Редактор открывается на «Ночи».
        self.btn_pal_night.blockSignals(True)
        self.btn_pal_night.setChecked(True)
        self.btn_pal_night.blockSignals(False)
        self._build_palette_fields()
        self.refresh_palette_editor()

        # Цвета терминала Konsole — как раньше
        row, col = 0, 0
        for field_name in self.editing_character.KonsoleTheme.__dataclass_fields__:
            create_color_field(self.konsole_colors_layout, field_name, field_name, self.editing_character.KonsoleTheme, False, row, col)
            col += 1
            if col > 2: col = 0; row += 1

    def on_edit_character(self, character):
        """Открывает редактор для конкретного персонажа (✎ на карточке),
        не делая его активным и не применяя тему."""
        self.is_creating_new = False
        self.editing_original_id = character.Id
        self.editing_character = EGCharacter(**asdict(character))
        self.editing_character.KonsoleTheme = KonsoleColorScheme(**asdict(character.KonsoleTheme))
        self.open_editor()

    def on_duplicate_current(self):
        """Дублирует персонажа, открытого в редакторе."""
        src = self.editing_character
        if not src: return
        self.is_creating_new = True
        self.editing_original_id = None
        new_char = EGCharacter(**asdict(src))
        new_char.KonsoleTheme = KonsoleColorScheme(**asdict(src.KonsoleTheme))
        new_char.Id += "_copy"
        new_char.DisplayName += " (Copy)"
        # у встроенных персонажей палитра привязана к Id — копия должна выглядеть так же, как исходник
        new_char.UiPalette = palette_model.freeze(asdict(src), new_char.Id)
        new_char.UiPaletteDay = palette_model.freeze_day(asdict(src), new_char.Id, new_char.UiPalette)
        self.editing_character = new_char
        self.open_editor()

    def on_create_new(self):
        self.is_creating_new = True
        self.editing_original_id = None
        self.editing_character = EGCharacter(Id="new_pony", DisplayName="New Pony")
        self.open_editor()

    def save_theme(self):
        self.editing_character.Id = self.fld_id.text()
        self.editing_character.DisplayName = self.fld_name.text()
        self.editing_character.WallpaperPath = self.fld_wallpaper.text()
        self.editing_character.IconPath = self.fld_icon.text()
        self.editing_character.KonsoleProfile = self.editing_character.Id
        self.editing_character.KdeColorScheme = self.editing_character.Id
        self.editing_character.UiPalette = palette_model.clean(self.editing_character.UiPalette)
        self.editing_character.UiPaletteDay = palette_model.clean(self.editing_character.UiPaletteDay)
        self.editing_character.AccentColorDay = palette_model.clean_color(self.editing_character.AccentColorDay)
        self.editing_character.KeyboardBacklight = keyboard_look.clean(self.editing_character.KeyboardBacklight)

        if self.is_creating_new: self.characters.append(self.editing_character)
        else:
            idx = next((i for i, c in enumerate(self.characters) if c.Id == self.editing_original_id), -1)
            if idx != -1: self.characters[idx] = self.editing_character

        was_active = (not self.is_creating_new and self.active_character
                      and self.active_character.Id == self.editing_original_id)
        self.save_json_and_refresh()
        if self.is_creating_new or was_active:
            # прежнее поведение: активному пересобираем тему, нового применяем
            self.on_character_selected(self.editing_character)
        else:
            # правка неактивного персонажа не должна трогать текущую тему; но если его пара
            # уже есть в ~/.local — её файлы пересобираются, чтобы не отставали от палитры
            self.update_texts()
            self.rebuild_user_kde_files(self.editing_character)

    def confirm_delete_theme(self):
        msg = self.t_str("ui.delete_msg")
        msg = msg.replace("{0}", self.editing_character.DisplayName) if "{0}" in msg else msg + " " + self.editing_character.DisplayName
        reply = QMessageBox.question(self, self.t_str("ui.delete_title"), msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.characters = [c for c in self.characters if c.Id != self.editing_character.Id]
            self.save_json_and_refresh()
            if self.active_character and self.active_character.Id == self.editing_character.Id:
                self.active_character = None
                self._save_state()
                self.update_texts()

    @staticmethod
    def _char_json(char):
        """Персонаж для записи в JSON: пустые правки палитры (ночи/дня) не пишем (файл остаётся таким же, как раньше)."""
        data = asdict(char)
        for name in ("UiPalette", "UiPaletteDay", "AccentColorDay", "KeyboardBacklight"):
            if not data.get(name):
                data.pop(name, None)
        return data

    def save_json_and_refresh(self):
        # Каждому персонажу — свой файл правки в characters.d (только то, что отличается от встроенного)
        try:
            self.store.write([self._char_json(c) for c in self.characters])
        except OSError as e:
            print(f"Не удалось сохранить персонажей: {e}", file=sys.stderr)
        self.kbd_preview.restore()   # предпросмотр закончен: на клавиатуре снова то, что должно быть
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
        self._save_state()
        self.update_texts()
        self.build_ui()

    def run_shell(self, command):
        subprocess.run(["/bin/bash", "-c", command], capture_output=True)

    def apply_wallpaper_slideshow(self, folder_rel_path):
        full_path = os.path.join(USER_PATH, folder_rel_path).replace("\\", "/")
        qdbus = find_qdbus()
        script = f"""{qdbus} org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "var allDesktops = desktops(); for (i=0;i<allDesktops.length;i++) {{ d = allDesktops[i]; d.wallpaperPlugin = 'org.kde.slideshow'; d.currentConfigGroup = Array('Wallpaper', 'org.kde.slideshow', 'General'); d.writeConfig('SlidePaths', '{full_path}'); }}" """
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
        # Конфиг собирается структурой и сериализуется через json.dump:
        # ручная f-строка ломалась бы на путях с кавычками/бэкслешами
        ff_config = {
            "logo": {
                "source": icon_path,
                "type": "chafa",
                "chafa": {"symbols": "block"},
                "width": 18,
                "height": 8,
                "padding": {"right": 2},
            },
            "display": {
                "separator": "  ",
                "color": {"keys": color, "title": color},
            },
            "modules": [
                "title",
                "separator",
                {"type": "os", "key": "  OS"},
                {"type": "kernel", "key": "  Kernel"},
                {"type": "de", "key": "  DE"},
                {"type": "shell", "key": "  Shell"},
                {"type": "terminal", "key": "  Terminal"},
                {"type": "cpu", "key": "  CPU"},
                {"type": "gpu", "key": "  GPU"},
                {"type": "memory", "key": "  RAM"},
                {"type": "disk", "key": "  Disk"},
                {"type": "uptime", "key": "  Uptime"},
                "separator",
                {"type": "colors", "symbol": "circle"}
            ],
        }
        with open(os.path.join(ff_dir, "config.jsonc"), "w", encoding='utf-8') as f:
            json.dump(ff_config, f, ensure_ascii=False, indent=2)

    def apply_konsole_colors(self, character):
        if not character.KonsoleTheme: return
        konsole_dir = os.path.expanduser("~/.local/share/konsole")
        os.makedirs(konsole_dir, exist_ok=True)
        c = character.KonsoleTheme
        content = f"[Background]\nColor={c.Background}\n\n[BackgroundIntense]\nColor={c.Color0Intense}\n\n[Color0]\nColor={c.Color0}\n\n[Color0Intense]\nColor={c.Color0Intense}\n\n[Color1]\nColor={c.Color1}\n\n[Color1Intense]\nColor={c.Color1Intense}\n\n[Color2]\nColor={c.Color2}\n\n[Color2Intense]\nColor={c.Color2Intense}\n\n[Color3]\nColor={c.Color3}\n\n[Color3Intense]\nColor={c.Color3Intense}\n\n[Color4]\nColor={c.Color4}\n\n[Color4Intense]\nColor={c.Color4Intense}\n\n[Color5]\nColor={c.Color5}\n\n[Color5Intense]\nColor={c.Color5Intense}\n\n[Color6]\nColor={c.Color6}\n\n[Color6Intense]\nColor={c.Color6Intense}\n\n[Color7]\nColor={c.Color7}\n\n[Color7Intense]\nColor={c.Color7Intense}\n\n[Foreground]\nColor={c.Foreground}\n\n[ForegroundIntense]\nColor={c.Color7Intense}\n\n[General]\nAnchor=0\nDescription={character.DisplayName}\nOpacity=1\nWallpaper=\n"
        with open(os.path.join(konsole_dir, "EquestriaOS.colorscheme"), "w", encoding='utf-8') as f: f.write(content)
        # setColorScheme удалён из D-Bus API новых Konsole (остался setProfile);
        # на них вызов тихо пропускается, на старых — обновляет цвета вживую
        qdbus = find_qdbus()
        self.run_shell(f"for s in $({qdbus} | grep konsole); do for e in $({qdbus} $s | grep Sessions); do {qdbus} $s $e org.kde.konsole.Session.setColorScheme EquestriaOS 2>/dev/null; done; done")

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
        except Exception: pass
        qdbus = find_qdbus()
        self.run_shell(f"for s in $({qdbus} | grep konsole); do for e in $({qdbus} $s | grep Sessions); do {qdbus} $s $e org.kde.konsole.Session.setProfile EquestriaOS 2>/dev/null; done; done")
        # Автоматически добавляем хук в ~/.bashrc пользователя
        bashrc_path = os.path.expanduser("~/.bashrc")
        hook_comment = "# EquestriaOS Character Theme Hook\n"
        hook_cmd = "[ -f ~/.local/share/konsole/eg_character_prompt.sh ] && source ~/.local/share/konsole/eg_character_prompt.sh\n"

        try:
            if os.path.exists(bashrc_path):
                with open(bashrc_path, "r", encoding='utf-8') as f:
                    bashrc_content = f.read()

                # Если хука еще нет, аккуратно дописываем его в конец
                if "eg_character_prompt.sh" not in bashrc_content:
                    with open(bashrc_path, "a", encoding='utf-8') as f:
                        f.write(f"\n{hook_comment}{hook_cmd}")
        except Exception as e:
            print(f"Не удалось обновить .bashrc: {e}")





    def apply_kde_theme(self, character):
        """Глобальная тема KDE персонажа — пара «день/ночь» (см. kde_laf.py).

        Пара собирается в ~/.local/share при каждом применении: так работают и
        свои персонажи, и изменённый в редакторе акцент встроенных. KDE получает
        пару в DefaultLight/DarkLookAndFeel и дальше сам меняет её по времени
        суток; --keep-auto не даёт команде выключить эту автоматику.

        Цвета (фон окон, области просмотра, кнопки, текст…) приходят из полной цветовой
        схемы персонажа. После применения проверяется, что KDE действительно взял её цвета;
        если KDE отказался применять тему — возвращается прежняя пара и тема."""
        ch = asdict(character)
        try:
            kde_laf.build(Path.home() / ".local" / "share", [ch], Path(USER_PATH))
        except OSError as e:
            print(f"Не удалось подготовить тему KDE: {e}")
            return
        light = kde_laf.laf_id(character.Id, "Light")
        dark = kde_laf.laf_id(character.Id, "Dark")
        dark_now = self.day_night.is_dark_now()  # до смены пары: была ли активна ночная половина
        prev_pair, prev_theme = self.day_night.pair(), self.day_night.current()
        self.day_night.set_pair(light, dark)
        # Акцент теперь внутри цветовой схемы; старый «свой акцент» перебивал бы её
        subprocess.run(["kwriteconfig6", "--file", "kdeglobals", "--group", "General",
                        "--key", "AccentColor", "--delete"], capture_output=True)
        if not kde_laf.apply_half(self.day_night, ch, "Dark" if dark_now else "Light"):
            print(f"KDE не применил тему {light}/{dark}; возвращаю прежнюю", file=sys.stderr)
            self.day_night.set_pair(*prev_pair)
            if prev_theme:
                self.day_night.apply(prev_theme)
            return
        r, g, b = kde_laf._rgb(character.AccentColor)
        self._recolor_panel_sysmon(r, g, b)

    def rebuild_user_kde_files(self, character):
        """Файлы пары персонажа в ~/.local пересобираются, только если они уже есть и отстали
        от его палитры. Применять ничего не нужно: тема не активна."""
        try:
            kde_laf.StalePairRefresher(Path.home() / ".local" / "share", Path(USER_PATH)).refresh([asdict(character)])
        except Exception as e:  # noqa: BLE001
            print(f"Не удалось обновить файлы темы KDE: {e}", file=sys.stderr)

    def refresh_stale_kde_themes(self):
        """Пары тем в ~/.local от старых версий — пересобрать (см. kde_laf.refresh_user_themes).
        То же делает автозапуск при входе; здесь — на случай, если сессия старше пакета."""
        try:
            kde_laf.refresh_user_themes(self.day_night)
        except OSError as e:
            print(f"Не удалось обновить темы KDE: {e}")

    def _recolor_panel_sysmon(self, r, g, b):
        """Красит график памяти в виджетах системного монитора на панелях
        под акцент персонажа (аргументы qdbus списком — без экранирования)."""
        recolor = (
            "var pn=panels();"
            "for(var i=0;i<pn.length;++i){"
            "var ids=pn[i].widgetIds;"
            "for(var j=0;j<ids.length;++j){"
            "var w=pn[i].widgetById(ids[j]);"
            "if(w.type=='org.kde.plasma.systemmonitor'||w.type=='org.kde.plasma.systemmonitor.memory'){"
            "w.currentConfigGroup=['SensorColors'];"
            f"w.writeConfig('memory/physical/used','{r},{g},{b}');"
            "if(typeof w.reloadConfig==='function'){w.reloadConfig();}"
            "}}}"
        )
        try:
            subprocess.run(
                [find_qdbus(), "org.kde.plasmashell", "/PlasmaShell",
                 "org.kde.PlasmaShell.evaluateScript", recolor],
                capture_output=True, timeout=10)
        except Exception:
            pass

    def get_ansi_color(self, char_id):
        return {"sunset": "220", "twilight": "135", "rainbow": "39", "rarity": "189", "pinkie": "205", "applejack": "136", "fluttershy": "228"}.get(char_id, "255")

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
    kit_qt.ThemeManager(app)  # общая тема Equestria OS: следит за переключателем персонажей
    app.setDesktopFileName("equestria-theme-switcher")

    icon_path = "/usr/share/pixmaps/equestria-os-logo.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        app.setWindowIcon(QIcon.fromTheme("preferences-desktop-theme"))

    font_path = os.path.join(SYSTEM_PATH, "equestria_cyrillic.ttf")
    eq_family = None
    if os.path.exists(font_path):
        families = font_families(font_path)
        if families:
            eq_family = families[0]
    # Базовый шрифт — системный: шрифт Эквестрии плохо читается на кнопках
    # и в описаниях, поэтому он используется только в заголовках и именах
    app.setFont(QFont("sans-serif", 12))

    window = EGThemeSwitcher(title_font_family=eq_family)
    window.show()
    sys.exit(app.exec())
