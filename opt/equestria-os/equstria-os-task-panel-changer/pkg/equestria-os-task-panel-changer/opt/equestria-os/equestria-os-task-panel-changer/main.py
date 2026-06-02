import sys
import os
import re
import json
import csv
import shutil
import configparser
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QPushButton, QColorDialog, QMessageBox, QFileDialog)
from PyQt6.QtGui import QIcon, QColor, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QTimer, QProcess

from ui import Ui_MainWindow
from widgets import PresetCard
import plasma_utils

SYSTEM_PATH = os.path.dirname(os.path.abspath(__file__))
USER_PATH = os.path.expanduser("~/.local/share/EquestriaOS/PanelStyles/")

class TaskPanelApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle("Equestria OS Task Panel Styles")

        self.active_preset_id = None
        self.panel_color_dark = "#313060"
        self.panel_color_light = "#dacac1"
        self.panel_opacity = 90
        self.panel_is_dark = True

        self.presets = []
        self.editing_preset_id = None
        self.is_new_preset = False
        self._ed_color_dark = "#313060"
        self._ed_color_light = "#dacac1"
        self._ed_opacity = 90
        self._ed_is_dark = True
        self._ed_layout_captured = None

        self.char_by_id = {}
        self.cards = {}
        self.localized_strings = {}
        self.available_langs = []
        self.current_lang = "en"

        self._appearance_timer = QTimer(self)
        self._appearance_timer.setSingleShot(True)
        self._appearance_timer.setInterval(400)
        self._appearance_timer.timeout.connect(self._do_apply_panel_appearance)

        self._pending_layout_preset = None
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._do_apply_pending_layout)

        self._active_process = None

        self._init_data()
        self._build_dynamic_ui()
        self._bind_events()
        self._update_ui_state()
        self._apply_panel_appearance()

    def _detect_plasma_theme_dark(self) -> bool:
        """Интеллектуально определяет глобальный режим оформления KDE (Темный/Светлый)."""
        try:
            kdeglobals_path = os.path.expanduser("~/.config/kdeglobals")
            if os.path.exists(kdeglobals_path):
                config = configparser.ConfigParser()
                config.read(kdeglobals_path)
                scheme = config.get("KDE", "ColorScheme", fallback="").lower()
                if "light" in scheme or "breezelight" in scheme:
                    return False
        except Exception:
            pass
        return True

    @property
    def _active_panel_color(self):
        return self.panel_color_dark if self.panel_is_dark else self.panel_color_light

    # ─────────────────────── Initialization ───────────────────────

    def _init_data(self):
        os.makedirs(USER_PATH, exist_ok=True)
        os.makedirs(os.path.join(USER_PATH, "layouts"), exist_ok=True)
        self._load_appearance()
        self._load_presets()
        if self.active_preset_id and not self._get_preset(self.active_preset_id):
            self.active_preset_id = None
        self._load_localization()
        self._detect_system_language()
        self._load_characters()

        self.panel_is_dark = self._detect_plasma_theme_dark()

    def _load_appearance(self):
        path = os.path.join(USER_PATH, "appearance.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _legacy = data.get("color", None)
                self.panel_color_dark = data.get("color_dark", _legacy or self.panel_color_dark)
                self.panel_color_light = data.get("color_light", _legacy or self.panel_color_light)
                self.panel_opacity = data.get("opacity", self.panel_opacity)
                self.panel_is_dark = data.get("is_dark", self.panel_is_dark)
                self.active_preset_id = data.get("active_preset", None)
            except (json.JSONDecodeError, OSError):
                pass

    def _save_appearance(self):
        try:
            with open(os.path.join(USER_PATH, "appearance.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "color_dark": self.panel_color_dark,
                    "color_light": self.panel_color_light,
                    "opacity": self.panel_opacity,
                    "is_dark": self.panel_is_dark,
                    "active_preset": self.active_preset_id,
                }, f)
        except OSError:
            pass

    def _load_presets(self):
        system_path = os.path.join(SYSTEM_PATH, "presets.json")
        user_path = os.path.join(USER_PATH, "presets.json")
        if not os.path.exists(user_path) and os.path.exists(system_path):
            shutil.copy2(system_path, user_path)
        src = user_path if os.path.exists(user_path) else system_path
        if os.path.exists(src):
            try:
                with open(src, "r", encoding="utf-8") as f:
                    self.presets = json.load(f).get("presets", [])
            except (json.JSONDecodeError, OSError):
                self.presets = []
        else:
            self.presets = []

    def _save_presets(self):
        try:
            with open(os.path.join(USER_PATH, "presets.json"), "w", encoding="utf-8") as f:
                json.dump({"presets": self.presets}, f, indent=4, ensure_ascii=False)
        except OSError:
            pass

    def _get_preset(self, preset_id):
        return next((p for p in self.presets if p["id"] == preset_id), None)

    def _preset_layout_file(self, preset_id):
        return os.path.join(USER_PATH, "layouts", f"{preset_id}.bak")

    def _load_localization(self):
        loc_path = os.path.join(SYSTEM_PATH, "localization.csv")
        if not os.path.exists(loc_path):
            return
        try:
            with open(loc_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                try:
                    headers = next(reader)
                    self.available_langs = [h.strip() for h in headers[1:]]
                    for row in reader:
                        if row and row[0].strip():
                            key = row[0].strip()
                            self.localized_strings[key] = {
                                self.available_langs[i - 1]: row[i].strip().replace("\\n", "\n")
                                for i in range(1, len(row)) if i <= len(self.available_langs)
                            }
                except StopIteration:
                    pass
        except OSError:
            pass

    def _load_characters(self):
        json_path = os.path.join(SYSTEM_PATH, "characters.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.char_by_id = {c["Id"]: c for c in data.get("Characters", [])}
            except (json.JSONDecodeError, OSError, KeyError):
                pass

    def _detect_system_language(self):
        sys_code = os.environ.get("LANG", "en")[:2].lower()
        self.current_lang = sys_code if sys_code in self.available_langs else (self.available_langs[0] if self.available_langs else "en")

    def _t(self, key):
        langs = self.localized_strings.get(key, {})
        return langs.get(self.current_lang, langs.get("en", key))

    def _preset_display_name(self, preset):
        if preset.get("name"): return preset["name"]
        char = self.char_by_id.get(preset.get("char_id", ""), {})
        return char.get("DisplayName") or preset["id"]

    def _preset_icon_path(self, preset):
        icon_rel = preset.get("icon") or self.char_by_id.get(preset.get("char_id", ""), {}).get("IconPath", "")
        if not icon_rel: return ""
        return icon_rel if os.path.isabs(icon_rel) else os.path.join(SYSTEM_PATH, icon_rel)

    # ─────────────────────── UI Building ───────────────────────

    def _build_dynamic_ui(self):
        self._build_language_selector()
        self._build_preset_cards()

    def _build_language_selector(self):
        while self.ui.lang_layout.count():
            item = self.ui.lang_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for code in self.available_langs:
            btn = QPushButton(code.upper())
            btn.setProperty("cssClass", "lang-button")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.clicked.connect(lambda _, c=code: self.set_language(c))
            self.ui.lang_layout.addWidget(btn)

    def _build_preset_cards(self):
        while self.ui.grid_layout.count():
            item = self.ui.grid_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.cards.clear()
        all_cards = []

        for preset in self.presets:
            pid = preset["id"]
            desc_key = preset.get("desc_key")
            final_desc = self._t(desc_key) if desc_key in self.localized_strings else (preset.get("desc") or pid)
            
            card = PresetCard(
                preset_id=pid,
                char_name=self._preset_display_name(preset),
                desc_text=final_desc,
                icon_path=self._preset_icon_path(preset),
            )
            card.update_appearance(self._active_panel_color, self.panel_opacity)
            card.set_active_state(pid == self.active_preset_id)
            card.clicked.connect(lambda checked, p=pid: self.on_preset_selected(p))
            self.cards[pid] = card
            all_cards.append(card)

        MAX_COLS = 4
        for row_start in range(0, len(all_cards), MAX_COLS):
            row_w = QWidget()
            row_lo = QHBoxLayout(row_w)
            row_lo.setContentsMargins(0, 0, 0, 0)
            row_lo.setSpacing(14)
            row_lo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            for card in all_cards[row_start:row_start + MAX_COLS]: row_lo.addWidget(card)
            self.ui.grid_layout.addWidget(row_w)

    # ─────────────────────── Events & State ───────────────────────

    def _bind_events(self):
        self.ui.btn_edit.clicked.connect(lambda: self.open_editor(self.active_preset_id))
        self.ui.btn_new_preset.clicked.connect(lambda: self.open_editor(None))
        self.ui.btn_restore_all.clicked.connect(self.restore_all_defaults)

        self.ui.btn_ed_color_dark.clicked.connect(lambda: self.on_ed_color_click("dark"))
        self.ui.btn_ed_color_light.clicked.connect(lambda: self.on_ed_color_click("light"))
        self.ui.sld_ed_opacity.valueChanged.connect(self.on_ed_opacity_changed)
        self.ui.btn_ed_icon.clicked.connect(self.open_icon_picker)
        self.ui.btn_ed_theme_dark.clicked.connect(lambda: self._set_editor_theme(True))
        self.ui.btn_ed_theme_light.clicked.connect(lambda: self._set_editor_theme(False))
        self.ui.btn_ed_open_kde.clicked.connect(self.enter_plasma_edit_mode)
        self.ui.btn_ed_capture.clicked.connect(self.capture_panels)
        self.ui.btn_ed_restore.clicked.connect(self.restore_single_default)
        self.ui.btn_ed_delete.clicked.connect(self.delete_preset)
        self.ui.btn_ed_cancel.clicked.connect(self.cancel_editor)
        self.ui.btn_ed_save.clicked.connect(self.save_editor)

    def set_language(self, code):
        self.current_lang = code
        for i in range(self.ui.lang_layout.count()):
            btn = self.ui.lang_layout.itemAt(i).widget()
            if btn:
                btn.setProperty("active", "true" if btn.text().lower() == code else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        self._build_preset_cards()
        self._update_ui_state()

    def _update_ui_state(self):
        self.ui.lbl_title.setText(self._t("ui.title"))
        self.ui.lbl_subtitle.setText(self._t("ui.subtitle"))
        self.ui.btn_edit.setText(self._t("ui.btn_edit"))
        self.ui.btn_new_preset.setText(self._t("ui.btn_new"))
        self.ui.btn_restore_all.setText(self._t("ui.btn_restore_all"))

        if self.active_preset_id:
            preset = self._get_preset(self.active_preset_id)
            char_name = self._preset_display_name(preset) if preset else self.active_preset_id
            fmt = self._t("ui.active_preset")
            self.ui.lbl_status.setText(fmt.replace("{0}", char_name) if "{0}" in fmt else f"{fmt} {char_name}")
            self.ui.btn_edit.setEnabled(True)
        else:
            self.ui.lbl_status.setText(self._t("ui.active_none"))
            self.ui.btn_edit.setEnabled(False)

        self.ui.lbl_ed_id_row.setText(self._t("ui.ed_preset_id"))
        self.ui.lbl_ed_name_row.setText(self._t("ui.ed_name_label"))
        self.ui.lbl_ed_desc_row.setText(self._t("ui.ed_desc_label"))
        self.ui.lbl_ed_icon_row.setText(self._t("ui.ed_icon_label"))
        self.ui.lbl_ed_color_row.setText(self._t("ui.ed_color_label"))
        self.ui.lbl_ed_opacity_row.setText(self._t("ui.ed_opacity_label"))
        self.ui.lbl_ed_layout_row.setText(self._t("ui.ed_layout_label"))
        self.ui.lbl_ed_hide_icons_row.setText(self._t("ui.ed_hide_icons_label"))
        self.ui.chk_ed_hide_icons.setText(self._t("ui.hide_icons"))

        self.ui.lbl_ed_theme_row.setText(self._t("ui.ed_theme_label"))
        self.ui.btn_ed_theme_dark.setText(self._t("ui.dark_panel"))
        self.ui.btn_ed_theme_light.setText(self._t("ui.light_panel"))

        kde_label = self._t("ui.ed_kde_label")
        if kde_label == "ui.ed_kde_label":
            kde_label = "KDE Plasma Editor:" if self.current_lang == "en" else "Настройка KDE:"
        self.ui.lbl_ed_kde_row.setText(kde_label)

        kde_btn = self._t("ui.ed_open_kde_btn")
        if kde_btn == "ui.ed_open_kde_btn":
            kde_btn = "🛠 Enter KDE Panel Edit Mode" if self.current_lang == "en" else "🛠 Войти в режим настройки панелей KDE"
        self.ui.btn_ed_open_kde.setText(kde_btn)

        self.ui.btn_ed_capture.setText(self._t("ui.ed_capture_btn"))
        self.ui.btn_ed_restore.setText(self._t("ui.btn_restore_default"))
        self.ui.btn_ed_delete.setText(self._t("ui.btn_delete"))
        self.ui.btn_ed_cancel.setText(self._t("ui.btn_cancel"))
        self.ui.btn_ed_save.setText(self._t("ui.btn_save"))
        self._update_theme_buttons()
        self._update_capture_label()

    def _update_capture_label(self):
        if self._ed_layout_captured:
            fmt = self._t("ui.ed_capture_done")
            text = fmt.replace("{0}", self._ed_layout_captured) if "{0}" in fmt else f"{fmt} {self._ed_layout_captured}"
        else:
            text = self._t("ui.ed_capture_none")
        self.ui.lbl_ed_capture_status.setText(text)

    def on_preset_selected(self, preset_id):
        self.active_preset_id = preset_id
        for pid, card in self.cards.items(): card.set_active_state(pid == preset_id)

        preset = self._get_preset(preset_id)
        if preset:
            _legacy = preset.get("color", None)
            self.panel_color_dark = preset.get("color_dark", _legacy or self.panel_color_dark)
            self.panel_color_light = preset.get("color_light", _legacy or self.panel_color_light)
            self.panel_opacity = preset.get("opacity", self.panel_opacity)
            self.panel_is_dark = preset.get("is_dark", self.panel_is_dark)

        self._pending_layout_preset = preset_id
        self._apply_panel_appearance_immediate()

    # ─────────────────────── Editor ───────────────────────

    def open_editor(self, preset_id):
        self.is_new_preset = (preset_id is None)
        self.editing_preset_id = preset_id

        if self.is_new_preset:
            self._ed_color_dark = "#313060"
            self._ed_color_light = "#dacac1"
            self._ed_opacity = 90
            self._ed_is_dark = True
            self._ed_layout_captured = None
            self.ui.lbl_ed_title.setText(self._t("ui.ed_title_new"))
            self.ui.fld_ed_id.setText("")
            self.ui.fld_ed_id.setReadOnly(False)
            self.ui.fld_ed_name.setText("")
            self.ui.fld_ed_desc.setText("")
            self.ui.fld_ed_icon.setText("")
            self.ui.chk_ed_hide_icons.setChecked(False)
            self.ui.btn_ed_restore.setEnabled(False)
            self.ui.btn_ed_delete.setVisible(False)
        else:
            preset = self._get_preset(preset_id)
            if not preset: return
            _legacy = preset.get("color", "#313060")
            self._ed_color_dark = preset.get("color_dark", _legacy)
            self._ed_color_light = preset.get("color_light", _legacy)
            self._ed_opacity = preset.get("opacity", 90)
            self._ed_is_dark = preset.get("is_dark", True)
            self._ed_layout_captured = preset.get("layout_captured")
            self.ui.chk_ed_hide_icons.setChecked(preset.get("desktop_icons_hidden", False))

            display_name = self._preset_display_name(preset)
            fmt = self._t("ui.ed_title_edit")
            self.ui.lbl_ed_title.setText(fmt.replace("{0}", display_name) if "{0}" in fmt else f"{fmt} {display_name}")

            self.ui.fld_ed_id.setText(preset_id)
            self.ui.fld_ed_id.setReadOnly(True)
            self.ui.fld_ed_name.setText(display_name)
            desc_key = preset.get("desc_key")
            self.ui.fld_ed_desc.setText(self._t(desc_key) if desc_key in self.localized_strings else (preset.get("desc") or ""))
            self.ui.fld_ed_icon.setText(preset.get("icon", ""))

            sys_path = os.path.join(SYSTEM_PATH, "presets.json")
            has_default = False
            if os.path.exists(sys_path):
                try:
                    with open(sys_path, "r", encoding="utf-8") as f:
                        has_default = any(p["id"] == preset_id for p in json.load(f).get("presets", []))
                except (json.JSONDecodeError, OSError): pass
            self.ui.btn_ed_restore.setEnabled(has_default)
            self.ui.btn_ed_delete.setVisible(True)

        self.ui.btn_ed_color_dark.setStyleSheet(f"background-color: {self._ed_color_dark};")
        self.ui.btn_ed_color_light.setStyleSheet(f"background-color: {self._ed_color_light};")
        self.ui.sld_ed_opacity.setValue(self._ed_opacity)
        self.ui.lbl_ed_opacity_val.setText(f"{self._ed_opacity}%")
        self._update_theme_buttons()
        self._update_ui_state()
        self.ui.stacked_widget.setCurrentIndex(1)

    def _set_editor_theme(self, is_dark: bool):
        self._ed_is_dark = is_dark
        self._update_theme_buttons()

    def _update_theme_buttons(self):
        for btn, active in [
            (self.ui.btn_ed_theme_dark, self._ed_is_dark),
            (self.ui.btn_ed_theme_light, not self._ed_is_dark),
        ]:
            if hasattr(self.ui, 'btn_ed_theme_dark'):
                btn.setProperty("active", "true" if active else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)

    def enter_plasma_edit_mode(self):
        qdbus = plasma_utils.find_qdbus()
        cmd = (
            f"{qdbus} org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript 'lockCorona(false);'; "
            f"{qdbus} org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.editMode true; "
            f"{qdbus} org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript 'toggleEditMode();' 2>/dev/null"
        )
        self._run_shell(cmd)

    def on_ed_color_click(self, which: str):
        current = self._ed_color_dark if which == "dark" else self._ed_color_light
        color = QColorDialog.getColor(QColor(current), self, self._t("ui.cp_title"))
        if color.isValid():
            if which == "dark":
                self._ed_color_dark = color.name()
                self.ui.btn_ed_color_dark.setStyleSheet(f"background-color: {self._ed_color_dark};")
            else:
                self._ed_color_light = color.name()
                self.ui.btn_ed_color_light.setStyleSheet(f"background-color: {self._ed_color_light};")

    def on_ed_opacity_changed(self, value):
        self._ed_opacity = value
        self.ui.lbl_ed_opacity_val.setText(f"{value}%")

    def open_icon_picker(self):
        current = self.ui.fld_ed_icon.text().strip()
        start = SYSTEM_PATH
        if current:
            full = current if os.path.isabs(current) else os.path.join(SYSTEM_PATH, current)
            start = os.path.dirname(full)
        path, _ = QFileDialog.getOpenFileName(self, "Select Icon", start, "Images (*.png *.jpg *.svg *.xpm *.ico)")
        if path:
            try:
                rel = os.path.relpath(path, SYSTEM_PATH)
                if not rel.startswith(".."): path = rel
            except ValueError: pass
            self.ui.fld_ed_icon.setText(path)

    

    def capture_panels(self):
        pid = self.editing_preset_id if not self.is_new_preset else self.ui.fld_ed_id.text().strip()
        if not pid:
            QMessageBox.warning(self, "", self._t("ui.err_empty_id"))
            return
        if not os.path.exists(plasma_utils.PLASMA_CONFIG):
            QMessageBox.warning(self, "", f"Config not found:\n{plasma_utils.PLASMA_CONFIG}")
            return

        import subprocess
        import time
        try:
            subprocess.run(["kquitapp6", "plasmashell"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass
        
        time.sleep(1.5)

        layout_file = self._preset_layout_file(pid)
        try:
            shutil.copy2(plasma_utils.PLASMA_CONFIG, layout_file)
            if os.path.exists(plasma_utils.PLASMA_SHELLRC):
                shutil.copy2(plasma_utils.PLASMA_SHELLRC, layout_file + "_shellrc")
            self._ed_layout_captured = datetime.now().strftime("%Y-%m-%d %H:%M")
        except OSError as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить: {e}")

        QProcess.startDetached("plasmashell")
        self._update_capture_label()

    def delete_preset(self):
        if self.is_new_preset or not self.editing_preset_id: return
        reply = QMessageBox.question(
            self, self._t("ui.delete_confirm_title"), self._t("ui.delete_confirm_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.presets = [p for p in self.presets if p["id"] != self.editing_preset_id]
            self._save_presets()

            layout_file = self._preset_layout_file(self.editing_preset_id)
            if os.path.exists(layout_file): os.remove(layout_file)
            shellrc_file = layout_file + "_shellrc"
            if os.path.exists(shellrc_file): os.remove(shellrc_file)

            if self.active_preset_id == self.editing_preset_id:
                self.active_preset_id = None
                self._save_appearance()

            self._build_preset_cards()
            self._update_ui_state()
            self.ui.stacked_widget.setCurrentIndex(0)

    def save_editor(self):
        if self.is_new_preset:
            new_id = self.ui.fld_ed_id.text().strip()
            if not new_id:
                QMessageBox.warning(self, "", self._t("ui.err_empty_id"))
                return
            if self._get_preset(new_id):
                QMessageBox.warning(self, "", self._t("ui.err_duplicate_id").replace("{0}", new_id))
                return
            preset = {
                "id": new_id,
                "char_id": new_id,
                "desc_key": f"preset.{new_id}",
                "color_dark": self._ed_color_dark,
                "color_light": self._ed_color_light,
                "opacity": self._ed_opacity,
                "is_dark": self._ed_is_dark,
                "desktop_icons_hidden": self.ui.chk_ed_hide_icons.isChecked(),
                "height": 48,
                "panels_config": [],
                "script": "",
            }
            self.presets.append(preset)
        else:
            preset = self._get_preset(self.editing_preset_id)
            if not preset: return
            preset["color_dark"] = self._ed_color_dark
            preset["color_light"] = self._ed_color_light
            preset["opacity"] = self._ed_opacity
            preset["is_dark"] = self._ed_is_dark
            preset["desktop_icons_hidden"] = self.ui.chk_ed_hide_icons.isChecked()

        name = self.ui.fld_ed_name.text().strip()
        if name: preset["name"] = name
        desc = self.ui.fld_ed_desc.text().strip()
        if desc:
            preset["desc"] = desc
        elif "desc" in preset: del preset["desc"]
        icon = self.ui.fld_ed_icon.text().strip()
        if icon:
            preset["icon"] = icon
        elif "icon" in preset: del preset["icon"]
        if self._ed_layout_captured:
            preset["layout_captured"] = self._ed_layout_captured
        elif "layout_captured" in preset: del preset["layout_captured"]

        self._save_presets()
        self._build_preset_cards()

        if not self.is_new_preset and self.editing_preset_id == self.active_preset_id:
            appearance_changed = (
                self._ed_color_dark  != self.panel_color_dark or
                self._ed_color_light != self.panel_color_light or
                self._ed_opacity     != self.panel_opacity or
                self._ed_is_dark     != self.panel_is_dark
            )
            self.panel_color_dark  = self._ed_color_dark
            self.panel_color_light = self._ed_color_light
            self.panel_opacity     = self._ed_opacity
            self.panel_is_dark     = self._ed_is_dark

            self._pending_layout_preset = self.editing_preset_id
            if appearance_changed:
                self._apply_panel_appearance_immediate()
            else:
                self._pending_layout_preset = None
                self._apply_preset_layout(self.editing_preset_id)

        self.ui.stacked_widget.setCurrentIndex(0)

    def cancel_editor(self): self.ui.stacked_widget.setCurrentIndex(0)

    def _parse_preset_panels_config(self, preset):
        if "panels_config" in preset: return preset["panels_config"]
        return [{"position": "bottom", "height": preset.get("height", 48)}]

    def restore_single_default(self):
        if self.is_new_preset or not self.editing_preset_id: return
        sys_path = os.path.join(SYSTEM_PATH, "presets.json")
        if not os.path.exists(sys_path): return
        try:
            with open(sys_path, "r", encoding="utf-8") as f:
                sys_preset = next((p for p in json.load(f).get("presets", []) if p["id"] == self.editing_preset_id), None)
        except (json.JSONDecodeError, OSError): return
        if not sys_preset: return

        layout_file = self._preset_layout_file(self.editing_preset_id)
        if os.path.exists(layout_file): os.remove(layout_file)
        shellrc_file = layout_file + "_shellrc"
        if os.path.exists(shellrc_file): os.remove(shellrc_file)
        
        for i, p in enumerate(self.presets):
            if p["id"] == self.editing_preset_id:
                self.presets[i] = dict(sys_preset)
                break
        self._save_presets()
        self.open_editor(self.editing_preset_id)

    def restore_all_defaults(self):
        title = self._t("ui.restore_all_title")
        msg = self._t("ui.restore_all_msg")
        reply = QMessageBox.question(self, title, msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        
        sys_path = os.path.join(SYSTEM_PATH, "presets.json")
        user_path = os.path.join(USER_PATH, "presets.json")
        if os.path.exists(sys_path): shutil.copy2(sys_path, user_path)

        layouts_dir = os.path.join(USER_PATH, "layouts")
        if os.path.isdir(layouts_dir):
            for f in os.listdir(layouts_dir):
                if f.endswith(".bak") or f.endswith("_shellrc"): os.remove(os.path.join(layouts_dir, f))
        self._load_presets()
        if self.active_preset_id and not self._get_preset(self.active_preset_id): self.active_preset_id = None
        self._build_preset_cards()
        self._update_ui_state()

    # ─────────────────────── Panel Appearance & Layout ───────────────────────

    def _apply_panel_appearance(self): self._appearance_timer.start()

    def _apply_panel_appearance_immediate(self):
        self._appearance_timer.stop()
        self._do_apply_panel_appearance()

    def _do_apply_panel_appearance(self):
        theme_dir = os.path.expanduser("~/.local/share/plasma/desktoptheme/EquestriaPanel")
        widgets_dir = os.path.join(theme_dir, "widgets")
        os.makedirs(widgets_dir, exist_ok=True)

        metadata = {
            "KPlugin": {
                "Authors": [{"Name": "EquestriaOS"}],
                "Id": "EquestriaPanel",
                "Name": "EquestriaPanel",
                "Version": "1.0"
            },
            "X-Plasma-API-Minimum-Version": "6.0",
            "fallbackPackage": "default",
        }
        with open(os.path.join(theme_dir, "metadata.json"), "w", encoding="utf-8") as f: json.dump(metadata, f, indent=4)

        if self.panel_is_dark:
            txt, txt_inactive = "252,252,252", "161,169,177"
            bg, bg_alt = "36,36,36", "41,44,48"
            view_bg, view_bg_alt = "49,54,59", "29,31,34"
            wm_bg, wm_blend, wm_fg = "39,44,49", "252,252,252", "252,252,252"
            wm_ibg, wm_iblend, wm_ifg = "32,36,40", "161,169,177", "161,169,177"
            header_bg, header_bg_alt = "41,44,48", "32,35,38"
            sel_fg, sel_link = "252,252,252", "253,188,75"
            color_scheme = "Breeze Dark"
        else:
            txt, txt_inactive = "35,38,41", "112,125,138"
            bg, bg_alt = "239,240,241", "227,229,231"
            view_bg, view_bg_alt = "252,252,252", "247,247,247"
            wm_bg, wm_blend, wm_fg = "227,229,231", "227,229,231", "35,38,41"
            wm_ibg, wm_iblend, wm_ifg = "239,240,241", "239,240,241", "112,125,138"
            header_bg, header_bg_alt = "222,224,226", "239,240,241"
            sel_fg, sel_link = "255,255,255", "41,128,185"
            color_scheme = "Breeze Light"

        lnk, neg, neu, pos, vis = "29,153,243", "218,68,83", "246,116,0", "39,174,96", "155,89,182"

        colors_data = "\n".join([
            f"[General]", f"ColorScheme={color_scheme}", f"Name=EquestriaPanel", f"shadeSortColumn=true", "",
            f"[KDE]", f"contrast=4", "",
            f"[Colors:Window]", f"BackgroundNormal={bg}", f"BackgroundAlternate={bg_alt}", f"ForegroundNormal={txt}", f"ForegroundInactive={txt_inactive}", f"ForegroundLink={lnk}", f"ForegroundNegative={neg}", f"ForegroundNeutral={neu}", f"ForegroundPositive={pos}", f"ForegroundVisited={vis}", "",
            f"[Colors:View]", f"BackgroundNormal={view_bg}", f"BackgroundAlternate={view_bg_alt}", f"ForegroundNormal={txt}", f"ForegroundInactive={txt_inactive}", f"ForegroundLink={lnk}", f"ForegroundNegative={neg}", f"ForegroundNeutral={neu}", f"ForegroundPositive={pos}", f"ForegroundVisited={vis}", "",
            f"[Colors:Button]", f"BackgroundNormal={bg}", f"BackgroundAlternate={bg_alt}", f"ForegroundNormal={txt}", f"ForegroundInactive={txt_inactive}", f"ForegroundLink={lnk}", f"ForegroundNegative={neg}", f"ForegroundNeutral={neu}", f"ForegroundPositive={pos}", f"ForegroundVisited={vis}", "",
            f"[Colors:Tooltip]", f"BackgroundNormal={bg}", f"BackgroundAlternate={bg_alt}", f"ForegroundNormal={txt}", f"ForegroundInactive={txt_inactive}", f"ForegroundLink={lnk}", f"ForegroundNegative={neg}", f"ForegroundNeutral={neu}", f"ForegroundPositive={pos}", f"ForegroundVisited={vis}", "",
            f"[Colors:Complementary]", f"BackgroundNormal=42,46,50", f"BackgroundAlternate=27,30,32", f"ForegroundNormal=252,252,252", f"ForegroundInactive=161,169,177", f"ForegroundLink=29,153,243", f"ForegroundNegative=218,68,83", f"ForegroundNeutral=246,116,0", f"ForegroundPositive=39,174,96", f"ForegroundVisited=155,89,182", "",
            f"[Colors:Header]", f"BackgroundNormal={header_bg}", f"BackgroundAlternate={header_bg_alt}", f"ForegroundNormal={txt}", f"ForegroundInactive={txt_inactive}", f"ForegroundLink={lnk}", f"ForegroundNegative={neg}", f"ForegroundNeutral={neu}", f"ForegroundPositive={pos}", f"ForegroundVisited={vis}", "",
            f"[Colors:Selection]", f"BackgroundAlternate={bg_alt}", f"ForegroundNormal={sel_fg}", f"ForegroundInactive={txt_inactive}", f"ForegroundLink={sel_link}", f"ForegroundNegative={neg}", f"ForegroundNeutral={neu}", f"ForegroundPositive={pos}", f"ForegroundVisited={vis}", "",
            f"[WM]", f"activeBackground={wm_bg}", f"activeBlend={wm_blend}", f"activeForeground={wm_fg}", f"inactiveBackground={wm_ibg}", f"inactiveBlend={wm_iblend}", f"inactiveForeground={wm_ifg}",
        ]) + "\n"
        with open(os.path.join(theme_dir, "colors"), "w", encoding="utf-8") as f: f.write(colors_data)

        color_schemes_dir = os.path.expanduser("~/.local/share/color-schemes")
        os.makedirs(color_schemes_dir, exist_ok=True)
        with open(os.path.join(color_schemes_dir, "EquestriaPanel.colors"), "w", encoding="utf-8") as f: f.write(colors_data)

        svg = plasma_utils.generate_panel_svg(self._active_panel_color, self.panel_opacity / 100.0)
        with open(os.path.join(widgets_dir, "panel-background.svg"), "w", encoding="utf-8") as f: f.write(svg)

        self._save_appearance()

        old_dir = os.path.expanduser("~/.local/share/plasma/themes/EquestriaPanel")
        if os.path.exists(old_dir): shutil.rmtree(old_dir, ignore_errors=True)

        plasmarc = os.path.expanduser("~/.config/plasmarc")
        cfg = configparser.ConfigParser()
        cfg.read(plasmarc)
        current_theme = cfg.get("Theme", "name", fallback=None)

        plasma_utils.apply_system_theme_fixes()

        cache_clear = "rm -rf ~/.cache/ksvg/ 2>/dev/null; rm -f ~/.cache/plasma_theme_*.kcache 2>/dev/null; "
        apply_colorscheme = "plasma-apply-colorscheme EquestriaPanel 2>/dev/null; "
        if current_theme == "EquestriaPanel":
            cmd = cache_clear + apply_colorscheme + "plasma-apply-desktoptheme default && sleep 0.5 && plasma-apply-desktoptheme EquestriaPanel"
        else:
            cmd = cache_clear + apply_colorscheme + "plasma-apply-desktoptheme EquestriaPanel"

        self._run_shell(cmd, on_finished=self._on_theme_applied)
        self._update_ui_state()
        for card in self.cards.values(): card.update_appearance(self._active_panel_color, self.panel_opacity)

    def _on_theme_applied(self):
        if self._pending_layout_preset:
            self._layout_timer.setInterval(1500)
            self._layout_timer.start()

    def _do_apply_pending_layout(self):
        pid = self._pending_layout_preset
        self._pending_layout_preset = None
        if pid: self._apply_preset_layout(pid)

    def _apply_preset_layout(self, preset_id):
        preset = self._get_preset(preset_id)
        if not preset: return

        layout_file = self._preset_layout_file(preset_id)
        hide_icons = preset.get("desktop_icons_hidden", False)
        qdbus = plasma_utils.find_qdbus()

        if os.path.exists(layout_file):
            shellrc_file = layout_file + "_shellrc"
            restore_shellrc = f"cp '{shellrc_file}' '{plasma_utils.PLASMA_SHELLRC}'; " if os.path.exists(shellrc_file) else ""

            # 1. СНАЧАЛА синхронно закрываем plasmashell, чтобы она выгрузила текущую сессию на диск
            import subprocess
            import time
            try:
                subprocess.run(["kquitapp6", "plasmashell"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            except Exception:
                pass
            
            # Обязательная пауза для завершения операций ввода-вывода подсистемы KDE
            time.sleep(1.5)

            # 2. ТЕПЕРЬ, когда живые иконки сохранены на диск, производим чтение и инжекцию в структуру нового пресета
            plasma_utils.preserve_user_launchers(layout_file, plasma_utils.PLASMA_CONFIG)

            # Подготовка скрипта изменения геометрии
            panels_cfg = self._parse_preset_panels_config(preset)
            height_script = "var ps=panels(); "
            for i, cfg in enumerate(panels_cfg):
                height_script += f"if(ps.length > {i}) {{ ps[{i}].height = {cfg.get('height', 48)}; }} "

            tmp_script = os.path.join(USER_PATH, ".tmp_height.js")
            try:
                with open(tmp_script, "w", encoding="utf-8") as f: 
                    f.write(height_script)
            except OSError: 
                tmp_script = None

            height_cmd = f'{qdbus} org.kde.plasmashell /PlasmaShell evaluateScript "$(cat \'{tmp_script}\')"' if tmp_script else ""

            # 3. Запускаем оболочку обратно с уже модифицированным файлом конфигурации
            cmd = f"{restore_shellrc}nohup plasmashell &>/dev/null & disown; sleep 4; {height_cmd}"
            self._run_shell(cmd)
        else:
            script = preset.get("script", "")
            if script:
                changed_containment = plasma_utils.set_desktop_icons_state(hide_icons)
                if changed_containment:
                    tmp_script = os.path.join(USER_PATH, ".tmp_eval.js")
                    try:
                        with open(tmp_script, "w", encoding="utf-8") as f: f.write(script)
                        cmd = (
                            f"kquitapp6 plasmashell 2>/dev/null; sleep 1.5; "
                            f"nohup plasmashell &>/dev/null & disown; sleep 4; "
                            f'{qdbus} org.kde.plasmashell /PlasmaShell evaluateScript "$(cat \'{tmp_script}\')"'
                        )
                        self._run_shell(cmd)
                    except OSError: pass
                else:
                    self._run_evaluate_script(script)

    def _run_evaluate_script(self, script):
        qdbus = plasma_utils.find_qdbus()
        tmp_script = os.path.join(USER_PATH, ".tmp_eval.js")
        try:
            with open(tmp_script, "w", encoding="utf-8") as f: f.write(script)
            cmd = f'{qdbus} org.kde.plasmashell /PlasmaShell evaluateScript "$(cat \'{tmp_script}\')"'
            self._run_shell(cmd)
        except OSError:
            escaped = script.replace("\\", "\\\\").replace('"', '\\"')
            self._run_shell(f'{qdbus} org.kde.plasmashell /PlasmaShell evaluateScript "{escaped}"')

    def _run_shell(self, command, on_finished=None):
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        def _cleanup(exit_code, exit_status):
            try:
                self._active_process = None
                if on_finished: on_finished()
            except RuntimeError: pass
        proc.finished.connect(_cleanup)
        proc.start("/bin/bash", ["-c", command])
        self._active_process = proc

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setDesktopFileName("equestria-os-task-panel-changer")
    icon_path = "/usr/share/pixmaps/equestria-os-logo.png"
    app.setWindowIcon(QIcon(icon_path) if os.path.exists(icon_path) else QIcon.fromTheme("preferences-desktop-theme"))

    font_path = os.path.join(SYSTEM_PATH, "equestria_cyrillic.ttf")
    if os.path.exists(font_path): QFontDatabase.addApplicationFont(font_path)
    app.setFont(QFont("sans-serif", 11))

    qss_path = os.path.join(SYSTEM_PATH, "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f: app.setStyleSheet(f.read())

    window = TaskPanelApp()
    window.show()
    sys.exit(app.exec())