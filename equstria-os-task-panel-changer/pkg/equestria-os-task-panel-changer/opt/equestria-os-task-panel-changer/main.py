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
from widgets import PresetCard, PanelRowWidget
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
        self.panel_color = "#313060"
        self.panel_opacity = 90
        self.panel_is_dark = True

        self.presets = []
        self.editing_preset_id = None
        self.is_new_preset = False
        self._ed_color = "#313060"
        self._ed_opacity = 90
        self._ed_is_dark = True
        self._panel_rows = []
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

    def _load_appearance(self):
        path = os.path.join(USER_PATH, "appearance.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.panel_color = data.get("color", self.panel_color)
                self.panel_opacity = data.get("opacity", self.panel_opacity)
                self.panel_is_dark = data.get("is_dark", self.panel_is_dark)
                self.active_preset_id = data.get("active_preset", None)
            except (json.JSONDecodeError, OSError):
                pass

    def _save_appearance(self):
        try:
            with open(os.path.join(USER_PATH, "appearance.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "color": self.panel_color,
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
        self._migrate_presets()

    def _migrate_presets(self):
        sys_path = os.path.join(SYSTEM_PATH, "presets.json")
        if not os.path.exists(sys_path):
            return
        try:
            with open(sys_path, "r", encoding="utf-8") as f:
                sys_map = {p["id"]: p for p in json.load(f).get("presets", [])}
        except (json.JSONDecodeError, OSError):
            return
        changed = False
        for preset in self.presets:
            sys_p = sys_map.get(preset["id"])
            if sys_p:
                for field in ("name", "icon", "height"):
                    if field not in preset and field in sys_p:
                        preset[field] = sys_p[field]
                        changed = True
        if changed:
            self._save_presets()

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
        if preset.get("name"):
            return preset["name"]
        char = self.char_by_id.get(preset.get("char_id", ""), {})
        return char.get("DisplayName") or preset["id"]

    def _preset_icon_path(self, preset):
        icon_rel = preset.get("icon") or self.char_by_id.get(preset.get("char_id", ""), {}).get("IconPath", "")
        if not icon_rel:
            return ""
        return icon_rel if os.path.isabs(icon_rel) else os.path.join(SYSTEM_PATH, icon_rel)

    # ─────────────────────── UI Building ───────────────────────

    def _build_dynamic_ui(self):
        self._build_language_selector()
        self._build_preset_cards()

    def _build_language_selector(self):
        while self.ui.lang_layout.count():
            item = self.ui.lang_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for code in self.available_langs:
            btn = QPushButton(code.upper())
            btn.setProperty("cssClass", "lang-button")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.clicked.connect(lambda _, c=code: self.set_language(c))
            self.ui.lang_layout.addWidget(btn)

    def _build_preset_cards(self):
        while self.ui.grid_layout.count():
            item = self.ui.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards.clear()
        all_cards = []

        for preset in self.presets:
            pid = preset["id"]
            card = PresetCard(
                preset_id=pid,
                char_name=self._preset_display_name(preset),
                desc_text=preset.get("desc") or self._t(preset.get("desc_key", pid)),
                icon_path=self._preset_icon_path(preset),
            )
            card.update_appearance(self.panel_color, self.panel_opacity)
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
            for card in all_cards[row_start:row_start + MAX_COLS]:
                row_lo.addWidget(card)
            self.ui.grid_layout.addWidget(row_w)

    # ─────────────────────── Events & State ───────────────────────

    def _bind_events(self):
        self.ui.btn_edit.clicked.connect(lambda: self.open_editor(self.active_preset_id))
        self.ui.btn_new_preset.clicked.connect(lambda: self.open_editor(None))
        self.ui.btn_restore_all.clicked.connect(self.restore_all_defaults)

        self.ui.btn_ed_color.clicked.connect(self.on_ed_color_click)
        self.ui.sld_ed_opacity.valueChanged.connect(self.on_ed_opacity_changed)
        self.ui.btn_ed_icon.clicked.connect(self.open_icon_picker)
        self.ui.btn_ed_add_panel.clicked.connect(lambda: self._add_panel_row())
        self.ui.btn_ed_theme.clicked.connect(self.toggle_editor_theme)
        self.ui.btn_ed_capture.clicked.connect(self.capture_panels)
        self.ui.btn_ed_restore.clicked.connect(self.restore_single_default)
        self.ui.btn_ed_delete.clicked.connect(self.delete_preset)  # НОВАЯ КНОПКА
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
        self.ui.lbl_ed_panels.setText(self._t("ui.ed_panels_label"))
        self.ui.btn_ed_add_panel.setText(self._t("ui.ed_add_panel_btn"))
        self.ui.lbl_ed_opacity_row.setText(self._t("ui.ed_opacity_label"))
        self.ui.lbl_ed_theme_row.setText(self._t("ui.ed_theme_label"))
        self.ui.lbl_ed_layout_row.setText(self._t("ui.ed_layout_label"))

        self.ui.lbl_ed_hide_icons_row.setText("Desktop Icons:")
        self.ui.chk_ed_hide_icons.setText(self._t("ui.hide_icons"))

        self.ui.btn_ed_capture.setText(self._t("ui.ed_capture_btn"))
        self.ui.btn_ed_restore.setText(self._t("ui.btn_restore_default"))
        self.ui.btn_ed_delete.setText(self._t("ui.btn_delete")) # ПЕРЕВОД КНОПКИ
        self.ui.btn_ed_cancel.setText(self._t("ui.btn_cancel"))
        self.ui.btn_ed_save.setText(self._t("ui.btn_save"))
        self.ui.btn_ed_theme.setText(self._t("ui.dark_text") if self._ed_is_dark else self._t("ui.light_text"))
        self._update_capture_label()
        for row in self._panel_rows:
            row.retranslate(self._t)

    def _update_capture_label(self):
        if self._ed_layout_captured:
            fmt = self._t("ui.ed_capture_done")
            text = fmt.replace("{0}", self._ed_layout_captured) if "{0}" in fmt else f"{fmt} {self._ed_layout_captured}"
        else:
            text = self._t("ui.ed_capture_none")
        self.ui.lbl_ed_capture_status.setText(text)

    def on_preset_selected(self, preset_id):
        self.active_preset_id = preset_id
        for pid, card in self.cards.items():
            card.set_active_state(pid == preset_id)

        preset = self._get_preset(preset_id)
        if preset:
            self.panel_color = preset.get("color", self.panel_color)
            self.panel_opacity = preset.get("opacity", self.panel_opacity)
            self.panel_is_dark = preset.get("is_dark", self.panel_is_dark)

        self._pending_layout_preset = preset_id
        self._apply_panel_appearance_immediate()

    # ─────────────────────── Editor ───────────────────────

    def open_editor(self, preset_id):
        self.is_new_preset = (preset_id is None)
        self.editing_preset_id = preset_id
        self._clear_panel_rows()

        if self.is_new_preset:
            self._ed_color = "#313060"
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
            self.ui.btn_ed_delete.setVisible(False) # СКРЫВАЕМ КНОПКУ ПРИ СОЗДАНИИ
            self._add_panel_row(self._default_panel_config())
        else:
            preset = self._get_preset(preset_id)
            if not preset:
                return
            self._ed_color = preset.get("color", "#313060")
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
            self.ui.fld_ed_desc.setText(preset.get("desc") or self._t(preset.get("desc_key", preset_id)))
            self.ui.fld_ed_icon.setText(preset.get("icon", ""))

            sys_path = os.path.join(SYSTEM_PATH, "presets.json")
            has_default = False
            if os.path.exists(sys_path):
                try:
                    with open(sys_path, "r", encoding="utf-8") as f:
                        has_default = any(p["id"] == preset_id for p in json.load(f).get("presets", []))
                except (json.JSONDecodeError, OSError):
                    pass
            self.ui.btn_ed_restore.setEnabled(has_default)
            self.ui.btn_ed_delete.setVisible(True) # ПОКАЗЫВАЕМ ПРИ РЕДАКТИРОВАНИИ

            for cfg in self._parse_preset_panels_config(preset):
                self._add_panel_row(cfg)

        self.ui.btn_ed_color.setStyleSheet(f"background-color: {self._ed_color};")
        self.ui.sld_ed_opacity.setValue(self._ed_opacity)
        self.ui.lbl_ed_opacity_val.setText(f"{self._ed_opacity}%")
        self._update_ui_state()
        self.ui.stacked_widget.setCurrentIndex(1)

    def on_ed_color_click(self):
        color = QColorDialog.getColor(QColor(self._ed_color), self, self._t("ui.cp_title"))
        if color.isValid():
            self._ed_color = color.name()
            self.ui.btn_ed_color.setStyleSheet(f"background-color: {self._ed_color};")

    def on_ed_opacity_changed(self, value):
        self._ed_opacity = value
        self.ui.lbl_ed_opacity_val.setText(f"{value}%")

    def toggle_editor_theme(self):
        self._ed_is_dark = not self._ed_is_dark
        self.ui.btn_ed_theme.setText(self._t("ui.dark_text") if self._ed_is_dark else self._t("ui.light_text"))

    def open_icon_picker(self):
        current = self.ui.fld_ed_icon.text().strip()
        start = SYSTEM_PATH
        if current:
            full = current if os.path.isabs(current) else os.path.join(SYSTEM_PATH, current)
            start = os.path.dirname(full)
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Icon", start, "Images (*.png *.jpg *.svg *.xpm *.ico)"
        )
        if path:
            try:
                rel = os.path.relpath(path, SYSTEM_PATH)
                if not rel.startswith(".."):
                    path = rel
            except ValueError:
                pass
            self.ui.fld_ed_icon.setText(path)

    def capture_panels(self):
        pid = self.editing_preset_id if not self.is_new_preset else self.ui.fld_ed_id.text().strip()
        if not pid:
            QMessageBox.warning(self, "", self._t("ui.err_empty_id"))
            return
        if not os.path.exists(plasma_utils.PLASMA_CONFIG):
            QMessageBox.warning(self, "", f"Config not found:\n{plasma_utils.PLASMA_CONFIG}")
            return
        layout_file = self._preset_layout_file(pid)
        shutil.copy2(plasma_utils.PLASMA_CONFIG, layout_file)
        if os.path.exists(plasma_utils.PLASMA_SHELLRC):
            shutil.copy2(plasma_utils.PLASMA_SHELLRC, layout_file + "_shellrc")
        self._ed_layout_captured = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._update_capture_label()

    def delete_preset(self):
        """Полностью удаляет пресет и его конфигурационные файлы."""
        if self.is_new_preset or not self.editing_preset_id:
            return

        reply = QMessageBox.question(
            self,
            self._t("ui.delete_confirm_title"),
            self._t("ui.delete_confirm_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 1. Удаляем из памяти и сохраняем
            self.presets = [p for p in self.presets if p["id"] != self.editing_preset_id]
            self._save_presets()

            # 2. Удаляем файлы конфигов, если они есть
            layout_file = self._preset_layout_file(self.editing_preset_id)
            if os.path.exists(layout_file):
                os.remove(layout_file)
            shellrc_file = layout_file + "_shellrc"
            if os.path.exists(shellrc_file):
                os.remove(shellrc_file)

            # 3. Если удаленный пресет был активен, сбрасываем статус
            if self.active_preset_id == self.editing_preset_id:
                self.active_preset_id = None
                self._save_appearance()

            # 4. Обновляем UI и возвращаемся на главную
            self._build_preset_cards()
            self._update_ui_state()
            self.ui.stacked_widget.setCurrentIndex(0)

    def save_editor(self):
        panels_config = [row.get_config() for row in self._panel_rows]
        if not panels_config:
            return

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
                "color": self._ed_color,
                "opacity": self._ed_opacity,
                "is_dark": self._ed_is_dark,
                "desktop_icons_hidden": self.ui.chk_ed_hide_icons.isChecked(),
                "height": panels_config[0]["height"],
                "panels_config": panels_config,
                "script": "",
            }
            self.presets.append(preset)
        else:
            preset = self._get_preset(self.editing_preset_id)
            if not preset:
                return
            preset["color"] = self._ed_color
            preset["opacity"] = self._ed_opacity
            preset["is_dark"] = self._ed_is_dark
            preset["desktop_icons_hidden"] = self.ui.chk_ed_hide_icons.isChecked()
            preset["height"] = panels_config[0]["height"]
            preset["panels_config"] = panels_config

        preset["script"] = plasma_utils.generate_script_from_panels(panels_config)

        name = self.ui.fld_ed_name.text().strip()
        if name:
            preset["name"] = name
        desc = self.ui.fld_ed_desc.text().strip()
        if desc:
            preset["desc"] = desc
        elif "desc" in preset:
            del preset["desc"]
        icon = self.ui.fld_ed_icon.text().strip()
        if icon:
            preset["icon"] = icon
        elif "icon" in preset:
            del preset["icon"]
        if self._ed_layout_captured:
            preset["layout_captured"] = self._ed_layout_captured
        elif "layout_captured" in preset:
            del preset["layout_captured"]

        self._save_presets()
        self._build_preset_cards()

        if not self.is_new_preset and self.editing_preset_id == self.active_preset_id:
            appearance_changed = (
                self._ed_color    != self.panel_color or
                self._ed_opacity  != self.panel_opacity or
                self._ed_is_dark  != self.panel_is_dark
            )
            self.panel_color   = self._ed_color
            self.panel_opacity = self._ed_opacity
            self.panel_is_dark = self._ed_is_dark

            self._pending_layout_preset = self.editing_preset_id
            if appearance_changed:
                self._apply_panel_appearance_immediate()
            else:
                self._pending_layout_preset = None
                self._apply_preset_layout(self.editing_preset_id)

        self.ui.stacked_widget.setCurrentIndex(0)

    def cancel_editor(self):
        self.ui.stacked_widget.setCurrentIndex(0)

    # ─────────────────────── Panel rows (editor) ───────────────────────

    def _add_panel_row(self, cfg=None):
        row = PanelRowWidget(cfg)
        row.retranslate(self._t)
        row.remove_requested.connect(self._remove_panel_row)
        row.move_up_requested.connect(self._move_panel_row_up)
        row.move_down_requested.connect(self._move_panel_row_down)
        self.ui.ed_panels_layout.addWidget(row)
        self._panel_rows.append(row)

    def _remove_panel_row(self, row):
        if len(self._panel_rows) <= 1:
            return
        self.ui.ed_panels_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._panel_rows.remove(row)

    def _move_panel_row_up(self, row):
        idx = self._panel_rows.index(row)
        if idx <= 0:
            return
        self._panel_rows[idx], self._panel_rows[idx - 1] = self._panel_rows[idx - 1], self._panel_rows[idx]
        self._rebuild_panels_layout()

    def _move_panel_row_down(self, row):
        idx = self._panel_rows.index(row)
        if idx >= len(self._panel_rows) - 1:
            return
        self._panel_rows[idx], self._panel_rows[idx + 1] = self._panel_rows[idx + 1], self._panel_rows[idx]
        self._rebuild_panels_layout()

    def _rebuild_panels_layout(self):
        for row in self._panel_rows:
            self.ui.ed_panels_layout.removeWidget(row)
        for row in self._panel_rows:
            self.ui.ed_panels_layout.addWidget(row)

    def _clear_panel_rows(self):
        for row in self._panel_rows:
            self.ui.ed_panels_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._panel_rows.clear()

    def _default_panel_config(self, height=48):
        return {
            "position": "bottom", "height": height,
            "width": 0, "offset": 0, "alignment": "left",
            "floating": False, "visibilityMode": "none",
            "lengthMode": "fill", "launcher": "kickoff",
            "widgets": ["taskbar", "systray", "clock"],
        }

    def _parse_preset_panels_config(self, preset):
        # Корректируем старые багнутые конфиги "на лету" перед отдачей UI
        if "panels_config" in preset:
            cfg_list = preset["panels_config"]
            for c in cfg_list:
                vis = c.get("visibilityMode", "none")
                if vis == "windowsbelow": c["visibilityMode"] = "dodgewindows"
                if vis == "windowscover": c["visibilityMode"] = "windowsgobelow"
            return cfg_list

        script = preset.get("script", "")
        if not script:
            return [self._default_panel_config(preset.get("height", 48))]

        panels = []
        for ps in re.split(r'var \w+=new Panel;', script)[1:]:
            cfg = {}
            m = re.search(r"\.location='(\w+)'", ps)
            cfg["position"] = m.group(1) if m else "bottom"
            m = re.search(r'\.height=(\d+)', ps)
            cfg["height"] = int(m.group(1)) if m else preset.get("height", 48)
            cfg["floating"] = "floating=true" in ps

            # Парсим visibilityMode
            m_hide = re.search(r"\.hiding='(\w+)'", ps)
            if m_hide:
                val = m_hide.group(1)
                # Перевод старых скриптов на новые рельсы Plasma 6
                if val == "windowsbelow": val = "dodgewindows"
                if val == "windowscover": val = "windowsgobelow"
                cfg["visibilityMode"] = val
            elif "autohide" in ps:
                cfg["visibilityMode"] = "autohide"
            else:
                cfg["visibilityMode"] = "none"

            m = re.search(r"\.lengthMode='(\w+)'", ps)
            cfg["lengthMode"] = m.group(1) if m else "fill"
            m = re.search(r"\.alignment='(\w+)'", ps)
            cfg["alignment"] = m.group(1) if m else ("center" if cfg.get("floating") else "left")
            m = re.search(r"\.minimumLength=(\d+)", ps)
            cfg["width"] = int(m.group(1)) if m else 0
            m = re.search(r"\.offset=(\d+)", ps)
            cfg["offset"] = int(m.group(1)) if m else 0
            if "plasma.kickerdash'" in ps:
                cfg["launcher"] = "kickerdash"
            elif "plasma.kicker'" in ps:
                cfg["launcher"] = "kicker"
            elif "plasma.kickoff'" in ps:
                cfg["launcher"] = "kickoff"
            else:
                cfg["launcher"] = "none"
            widgets = []
            if "plasma.icontasks'" in ps:    widgets.append("taskbar")
            if "plasma.systemtray'" in ps:   widgets.append("systray")
            if "plasma.digitalclock'" in ps: widgets.append("clock")
            if "plasma.pager'" in ps:        widgets.append("pager")
            if "plasma.systemmonitor'" in ps: widgets.append("monitor")
            cfg["widgets"] = widgets
            panels.append(cfg)
        return panels or [self._default_panel_config(preset.get("height", 48))]

    def restore_single_default(self):
        if self.is_new_preset or not self.editing_preset_id:
            return
        sys_path = os.path.join(SYSTEM_PATH, "presets.json")
        if not os.path.exists(sys_path):
            return
        try:
            with open(sys_path, "r", encoding="utf-8") as f:
                sys_preset = next((p for p in json.load(f).get("presets", []) if p["id"] == self.editing_preset_id), None)
        except (json.JSONDecodeError, OSError):
            return
        if not sys_preset:
            return

        layout_file = self._preset_layout_file(self.editing_preset_id)
        if os.path.exists(layout_file):
            os.remove(layout_file)
        shellrc_file = layout_file + "_shellrc"
        if os.path.exists(shellrc_file):
            os.remove(shellrc_file)
        for i, p in enumerate(self.presets):
            if p["id"] == self.editing_preset_id:
                self.presets[i] = dict(sys_preset)
                break
        self._save_presets()
        self.open_editor(self.editing_preset_id)

    def restore_all_defaults(self):
        title = self._t("ui.restore_all_title")
        msg = self._t("ui.restore_all_msg")
        reply = QMessageBox.question(self, title, msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        sys_path = os.path.join(SYSTEM_PATH, "presets.json")
        user_path = os.path.join(USER_PATH, "presets.json")
        if os.path.exists(sys_path):
            shutil.copy2(sys_path, user_path)

        layouts_dir = os.path.join(USER_PATH, "layouts")
        if os.path.isdir(layouts_dir):
            for f in os.listdir(layouts_dir):
                if f.endswith(".bak") or f.endswith("_shellrc"):
                    os.remove(os.path.join(layouts_dir, f))
        self._load_presets()
        if self.active_preset_id and not self._get_preset(self.active_preset_id):
            self.active_preset_id = None
        self._build_preset_cards()
        self._update_ui_state()

    # ─────────────────────── Panel Appearance & Layout ───────────────────────

    def _apply_panel_appearance(self):
        self._appearance_timer.start()

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
        with open(os.path.join(theme_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)

        if self.panel_is_dark:
            txt = "255,255,255"
            bg = "36,36,36"
            view_bg = "49,54,59"
        else:
            txt = "35,38,41"
            bg = "239,240,241"
            view_bg = "252,252,252"

        colors_data = (
            f"[Colors:Window]\nForegroundNormal={txt}\nBackgroundNormal={bg}\n"
            f"[Colors:View]\nForegroundNormal={txt}\nBackgroundNormal={view_bg}\n"
            f"[Colors:Button]\nForegroundNormal={txt}\nBackgroundNormal={bg}\n"
            f"[Colors:Tooltip]\nForegroundNormal={txt}\nBackgroundNormal={bg}\n"
            f"[Colors:Complementary]\nForegroundNormal={txt}\nBackgroundNormal={bg}\n"
        )
        with open(os.path.join(theme_dir, "colors"), "w", encoding="utf-8") as f:
            f.write(colors_data)

        svg = plasma_utils.generate_panel_svg(self.panel_color, self.panel_opacity / 100.0)
        with open(os.path.join(widgets_dir, "panel-background.svg"), "w", encoding="utf-8") as f:
            f.write(svg)

        self._save_appearance()

        old_dir = os.path.expanduser("~/.local/share/plasma/themes/EquestriaPanel")
        if os.path.exists(old_dir):
            shutil.rmtree(old_dir, ignore_errors=True)

        plasmarc = os.path.expanduser("~/.config/plasmarc")
        cfg = configparser.ConfigParser()
        cfg.read(plasmarc)
        current_theme = cfg.get("Theme", "name", fallback=None)

        cache_clear = "rm -rf ~/.cache/ksvg/ 2>/dev/null; rm -f ~/.cache/plasma_theme_*.kcache 2>/dev/null; "
        if current_theme == "EquestriaPanel":
            cmd = cache_clear + "plasma-apply-desktoptheme default && sleep 0.5 && plasma-apply-desktoptheme EquestriaPanel"
        else:
            cmd = cache_clear + "plasma-apply-desktoptheme EquestriaPanel"

        self._run_shell(cmd, on_finished=self._on_theme_applied)

        self._update_ui_state()
        for card in self.cards.values():
            card.update_appearance(self.panel_color, self.panel_opacity)

    def _on_theme_applied(self):
        if self._pending_layout_preset:
            self._layout_timer.setInterval(1500)
            self._layout_timer.start()

    def _do_apply_pending_layout(self):
        pid = self._pending_layout_preset
        self._pending_layout_preset = None
        if pid:
            self._apply_preset_layout(pid)

    def _apply_preset_layout(self, preset_id):
        preset = self._get_preset(preset_id)
        if not preset:
            return

        layout_file = self._preset_layout_file(preset_id)
        hide_icons = preset.get("desktop_icons_hidden", False)

        panels_cfg = self._parse_preset_panels_config(preset)
        height_script = "var ps=panels(); "
        for i, cfg in enumerate(panels_cfg):
            h = cfg.get("height", 48)
            height_script += f"if(ps.length > {i}) {{ ps[{i}].height = {h}; }} "

        qdbus = plasma_utils.find_qdbus()

        if os.path.exists(layout_file):
            shellrc_file = layout_file + "_shellrc"
            restore_shellrc = f"cp '{shellrc_file}' '{plasma_utils.PLASMA_SHELLRC}'; " if os.path.exists(shellrc_file) else ""

            tmp_script = os.path.join(USER_PATH, ".tmp_height.js")
            try:
                with open(tmp_script, "w", encoding="utf-8") as f:
                    f.write(height_script)
            except OSError:
                tmp_script = None

            height_cmd = ""
            if tmp_script:
                height_cmd = f'{qdbus} org.kde.plasmashell /PlasmaShell evaluateScript "$(cat \'{tmp_script}\')"'

            shutil.copy2(layout_file, plasma_utils.PLASMA_CONFIG)
            plasma_utils.set_desktop_icons_state(hide_icons)

            cmd = (
                f"kquitapp6 plasmashell 2>/dev/null; "
                f"sleep 1; "
                f"killall -9 plasmashell 2>/dev/null; "
                f"sleep 0.5; "
                f"{restore_shellrc}"
                f"nohup plasmashell &>/dev/null & disown; "
                f"sleep 4; "
                f"{height_cmd}"
            )
            self._run_shell(cmd)
        else:
            script = preset.get("script", "")
            if script:
                script += height_script

            changed_containment = plasma_utils.set_desktop_icons_state(hide_icons)

            if changed_containment:
                tmp_script = os.path.join(USER_PATH, ".tmp_eval.js")
                try:
                    with open(tmp_script, "w", encoding="utf-8") as f:
                        f.write(script)
                    cmd = (
                        f"kquitapp6 plasmashell 2>/dev/null; "
                        f"sleep 1; "
                        f"killall -9 plasmashell 2>/dev/null; "
                        f"sleep 0.5; "
                        f"nohup plasmashell &>/dev/null & disown; "
                        f"sleep 4; "
                        f'{qdbus} org.kde.plasmashell /PlasmaShell evaluateScript "$(cat \'{tmp_script}\')"'
                    )
                    self._run_shell(cmd)
                except OSError:
                    pass
            else:
                if script:
                    self._run_evaluate_script(script)

    def _run_evaluate_script(self, script):
        qdbus = plasma_utils.find_qdbus()
        tmp_script = os.path.join(USER_PATH, ".tmp_eval.js")
        try:
            with open(tmp_script, "w", encoding="utf-8") as f:
                f.write(script)
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
                if on_finished:
                    on_finished()
            except RuntimeError:
                pass

        proc.finished.connect(_cleanup)
        proc.start("/bin/bash", ["-c", command])
        self._active_process = proc

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setDesktopFileName("equestria-theme-switcher.desktop")

    icon_path = "/usr/share/pixmaps/equestria-os-logo.png"
    app.setWindowIcon(QIcon(icon_path) if os.path.exists(icon_path) else QIcon.fromTheme("preferences-desktop-theme"))

    font_path = os.path.join(SYSTEM_PATH, "equestria_cyrillic.ttf")
    if os.path.exists(font_path):
        if (font_id := QFontDatabase.addApplicationFont(font_path)) != -1:
            if families := QFontDatabase.applicationFontFamilies(font_id):
                app.setFont(QFont(families[0], 12))

    qss_path = os.path.join(SYSTEM_PATH, "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = TaskPanelApp()
    window.show()
    sys.exit(app.exec())
