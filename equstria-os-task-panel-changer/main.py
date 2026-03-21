import sys
import os
import re
import json
import csv
import subprocess
import configparser
import shutil
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QPushButton, QColorDialog, QMessageBox, QFileDialog)
from PyQt6.QtGui import QIcon, QColor, QFontDatabase, QFont
from PyQt6.QtCore import Qt
from ui import Ui_MainWindow, PresetCard, PanelRowWidget

SYSTEM_PATH = os.path.dirname(os.path.abspath(__file__))
USER_PATH = os.path.expanduser("~/.local/share/EquestriaOS/PanelStyles/")
PLASMA_CONFIG = os.path.expanduser("~/.config/plasma-org.kde.plasma.desktop-appletsrc")


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
        self._ed_layout_captured = None   # datetime string or None

        self.char_by_id = {}
        self.cards = {}
        self.localized_strings = {}
        self.available_langs = []
        self.current_lang = "en"

        self._init_data()
        self._build_dynamic_ui()
        self._bind_events()
        self.ui.sld_opacity.setValue(self.panel_opacity)
        self.ui.lbl_opacity_val.setText(f"{self.panel_opacity}%")
        self._update_ui_state()
        self._apply_panel_appearance()

    # ─────────────────────── Initialization ───────────────────────

    def _init_data(self):
        os.makedirs(USER_PATH, exist_ok=True)
        os.makedirs(os.path.join(USER_PATH, "layouts"), exist_ok=True)
        self._load_appearance()
        self._load_presets()
        # Clear saved active preset if it no longer exists
        if self.active_preset_id and not self._get_preset(self.active_preset_id):
            self.active_preset_id = None
        self._load_localization()
        self._detect_system_language()
        self._load_characters()

    def _load_appearance(self):
        path = os.path.join(USER_PATH, "appearance.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.panel_color = data.get("color", self.panel_color)
            self.panel_opacity = data.get("opacity", self.panel_opacity)
            self.panel_is_dark = data.get("is_dark", self.panel_is_dark)
            self.active_preset_id = data.get("active_preset", None)

    def _save_appearance(self):
        with open(os.path.join(USER_PATH, "appearance.json"), "w", encoding="utf-8") as f:
            json.dump({
                "color": self.panel_color,
                "opacity": self.panel_opacity,
                "is_dark": self.panel_is_dark,
                "active_preset": self.active_preset_id,
            }, f)

    def _load_presets(self):
        system_path = os.path.join(SYSTEM_PATH, "presets.json")
        user_path = os.path.join(USER_PATH, "presets.json")
        if not os.path.exists(user_path) and os.path.exists(system_path):
            shutil.copy2(system_path, user_path)
        src = user_path if os.path.exists(user_path) else system_path
        if os.path.exists(src):
            with open(src, "r", encoding="utf-8") as f:
                self.presets = json.load(f).get("presets", [])
        else:
            self.presets = []
        self._migrate_presets()

    def _migrate_presets(self):
        """Fill in missing name/icon/height from the system presets (backward compat)."""
        sys_path = os.path.join(SYSTEM_PATH, "presets.json")
        if not os.path.exists(sys_path):
            return
        with open(sys_path, "r", encoding="utf-8") as f:
            sys_map = {p["id"]: p for p in json.load(f).get("presets", [])}
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
        with open(os.path.join(USER_PATH, "presets.json"), "w", encoding="utf-8") as f:
            json.dump({"presets": self.presets}, f, indent=4, ensure_ascii=False)

    def _get_preset(self, preset_id):
        return next((p for p in self.presets if p["id"] == preset_id), None)

    def _preset_layout_file(self, preset_id):
        return os.path.join(USER_PATH, "layouts", f"{preset_id}.bak")

    def _load_localization(self):
        loc_path = os.path.join(SYSTEM_PATH, "localization.csv")
        if not os.path.exists(loc_path):
            return
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

    def _load_characters(self):
        """Load characters.json as a fallback when preset lacks name/icon."""
        json_path = os.path.join(SYSTEM_PATH, "characters.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.char_by_id = {c["Id"]: c for c in data.get("Characters", [])}

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
        # Main page
        self.ui.btn_color_swatch.clicked.connect(self.open_color_picker)
        self.ui.btn_panel_theme.clicked.connect(self.toggle_panel_theme)
        self.ui.sld_opacity.valueChanged.connect(self.on_opacity_changed)
        self.ui.btn_edit.clicked.connect(lambda: self.open_editor(self.active_preset_id))
        self.ui.btn_new_preset.clicked.connect(lambda: self.open_editor(None))
        self.ui.btn_restore_all.clicked.connect(self.restore_all_defaults)
        # Editor page
        self.ui.btn_ed_color.clicked.connect(self.on_ed_color_click)
        self.ui.sld_ed_opacity.valueChanged.connect(self.on_ed_opacity_changed)
        self.ui.btn_ed_icon.clicked.connect(self.open_icon_picker)
        self.ui.btn_ed_add_panel.clicked.connect(lambda: self._add_panel_row())
        self.ui.btn_ed_theme.clicked.connect(self.toggle_editor_theme)
        self.ui.btn_ed_capture.clicked.connect(self.capture_panels)
        self.ui.btn_ed_restore.clicked.connect(self.restore_single_default)
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
        # Main page
        self.ui.lbl_title.setText(self._t("ui.title"))
        self.ui.lbl_subtitle.setText(self._t("ui.subtitle"))
        self.ui.lbl_panel_color.setText(self._t("ui.panel_color"))
        self.ui.lbl_opacity_label.setText(self._t("ui.opacity"))
        self.ui.btn_color_swatch.setStyleSheet(f"background-color: {self.panel_color};")
        self.ui.btn_panel_theme.setText("🌙" if self.panel_is_dark else "☀️")
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

        # Editor page labels
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
        self.ui.btn_ed_capture.setText(self._t("ui.ed_capture_btn"))
        self.ui.btn_ed_restore.setText(self._t("ui.btn_restore_default"))
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
            self.ui.sld_opacity.setValue(self.panel_opacity)
            self.ui.lbl_opacity_val.setText(f"{self.panel_opacity}%")

        self._apply_panel_appearance()
        self._apply_preset_layout(preset_id)

    def toggle_panel_theme(self):
        self.panel_is_dark = not self.panel_is_dark
        self._apply_panel_appearance()

    def open_color_picker(self):
        color = QColorDialog.getColor(QColor(self.panel_color), self, self._t("ui.cp_title"))
        if color.isValid():
            self.panel_color = color.name()
            self._apply_panel_appearance()

    def on_opacity_changed(self, value):
        self.panel_opacity = value
        self.ui.lbl_opacity_val.setText(f"{value}%")
        self._apply_panel_appearance()

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
            self.ui.btn_ed_restore.setEnabled(False)
            self._add_panel_row(self._default_panel_config())
        else:
            preset = self._get_preset(preset_id)
            if not preset:
                return
            self._ed_color = preset.get("color", "#313060")
            self._ed_opacity = preset.get("opacity", 90)
            self._ed_is_dark = preset.get("is_dark", True)
            self._ed_layout_captured = preset.get("layout_captured")

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
                with open(sys_path, "r", encoding="utf-8") as f:
                    has_default = any(p["id"] == preset_id for p in json.load(f).get("presets", []))
            self.ui.btn_ed_restore.setEnabled(has_default)

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
        """Copy current plasma panel config as this preset's layout."""
        pid = self.editing_preset_id if not self.is_new_preset else self.ui.fld_ed_id.text().strip()
        if not pid:
            QMessageBox.warning(self, "", self._t("ui.err_empty_id"))
            return
        if not os.path.exists(PLASMA_CONFIG):
            QMessageBox.warning(self, "", f"Config not found:\n{PLASMA_CONFIG}")
            return
        layout_file = self._preset_layout_file(pid)
        shutil.copy2(PLASMA_CONFIG, layout_file)
        self._ed_layout_captured = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._update_capture_label()

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
            preset["height"] = panels_config[0]["height"]
            preset["panels_config"] = panels_config

        preset["script"] = self._generate_script_from_panels(panels_config)

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
            self.ui.sld_opacity.setValue(self.panel_opacity)
            self.ui.lbl_opacity_val.setText(f"{self.panel_opacity}%")
            if appearance_changed:
                self._apply_panel_appearance()
            # delay layout only when theme is being reloaded to avoid race condition
            self._apply_preset_layout(self.editing_preset_id, delay=3 if appearance_changed else 0)

        self.ui.stacked_widget.setCurrentIndex(0)

    def cancel_editor(self):
        self.ui.stacked_widget.setCurrentIndex(0)

    # ─────────────────────── Panel rows (editor) ───────────────────────

    def _add_panel_row(self, cfg=None):
        row = PanelRowWidget(cfg)
        row.remove_requested.connect(self._remove_panel_row)
        row.move_up_requested.connect(self._move_panel_row_up)
        row.move_down_requested.connect(self._move_panel_row_down)
        self.ui.ed_panels_layout.addWidget(row)
        self._panel_rows.append(row)

    def _remove_panel_row(self, row):
        if len(self._panel_rows) <= 1:
            return  # always keep at least one panel
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
            "floating": False, "autohide": False,
            "lengthMode": "fill", "launcher": "kickoff",
            "widgets": ["taskbar", "systray", "clock"],
        }

    def _parse_preset_panels_config(self, preset):
        """Return panels_config list from preset, parsing legacy script if needed."""
        if "panels_config" in preset:
            return preset["panels_config"]
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
            cfg["autohide"] = "autohide" in ps
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

    def _generate_script_from_panels(self, panels_config):
        LAUNCHER_MAP = {
            "kickoff":    "org.kde.plasma.kickoff",
            "kicker":     "org.kde.plasma.kicker",
            "kickerdash": "org.kde.plasma.kickerdash",
        }
        ICON = "/usr/share/pixmaps/equestria-os-logo.png"
        parts = ["var a=panels();for(var i=0;i<a.length;i++){a[i].remove();}"]
        for i, p in enumerate(panels_config):
            v = f"p{i}"
            pos      = p.get("position", "bottom")
            height   = p.get("height", 48)
            width_px = p.get("width", 0)
            offset   = p.get("offset", 0)
            align    = p.get("alignment", "center" if p.get("floating") else "left")
            floatP   = p.get("floating", False)
            hide     = p.get("autohide", False)
            lmode    = p.get("lengthMode", "fill")
            launch   = p.get("launcher", "none")
            ww       = p.get("widgets", [])

            parts.append(f"var {v}=new Panel;")
            parts.append(f"{v}.location='{pos}';")
            parts.append(f"{v}.height={height};")
            parts.append(f"{v}.alignment='{align}';")
            if floatP:
                parts.append(f"{v}.floating=true;")
            parts.append(f"{v}.lengthMode='{lmode}';")
            if width_px > 0:
                parts.append(f"{v}.minimumLength={width_px};{v}.maximumLength={width_px};")
            if offset != 0:
                parts.append(f"{v}.offset={offset};")
            if hide:
                parts.append(f"{v}.hiding='autohide';")

            has_launcher = launch in LAUNCHER_MAP
            has_taskbar  = "taskbar" in ww
            has_right    = any(x in ww for x in ("pager", "monitor", "systray", "clock"))

            if has_launcher:
                pid = LAUNCHER_MAP[launch]
                parts.append(f"var k{i}={v}.addWidget('{pid}');")
                parts.append(f"k{i}.currentConfigGroup=['General'];")
                parts.append(f"k{i}.writeConfig('icon','{ICON}');")

            # spacer between launcher and taskbar (or right widgets)
            if has_launcher and (has_taskbar or has_right):
                parts.append(f"{v}.addWidget('org.kde.plasma.panelspacer');")

            if has_taskbar:
                parts.append(f"{v}.addWidget('org.kde.plasma.icontasks');")
                if has_right:
                    parts.append(f"{v}.addWidget('org.kde.plasma.panelspacer');")

            if "pager"   in ww: parts.append(f"{v}.addWidget('org.kde.plasma.pager');")
            if "monitor" in ww: parts.append(f"{v}.addWidget('org.kde.plasma.systemmonitor');")
            if "systray" in ww: parts.append(f"{v}.addWidget('org.kde.plasma.systemtray');")
            if "clock"   in ww: parts.append(f"{v}.addWidget('org.kde.plasma.digitalclock');")

        return "".join(parts)

    def restore_single_default(self):
        if self.is_new_preset or not self.editing_preset_id:
            return
        sys_path = os.path.join(SYSTEM_PATH, "presets.json")
        if not os.path.exists(sys_path):
            return
        with open(sys_path, "r", encoding="utf-8") as f:
            sys_preset = next((p for p in json.load(f).get("presets", []) if p["id"] == self.editing_preset_id), None)
        if not sys_preset:
            return
        # Remove captured layout file if it exists
        layout_file = self._preset_layout_file(self.editing_preset_id)
        if os.path.exists(layout_file):
            os.remove(layout_file)
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
        # Remove all captured layout files
        layouts_dir = os.path.join(USER_PATH, "layouts")
        if os.path.isdir(layouts_dir):
            for f in os.listdir(layouts_dir):
                if f.endswith(".bak"):
                    os.remove(os.path.join(layouts_dir, f))
        self._load_presets()
        if self.active_preset_id and not self._get_preset(self.active_preset_id):
            self.active_preset_id = None
        self._build_preset_cards()
        self._update_ui_state()

    # ─────────────────────── Panel Appearance & Layout ───────────────────────

    def _apply_preset_layout(self, preset_id, delay=0):
        """Apply the panel layout for a preset (config backup if available, else JS script).

        delay: seconds to wait before applying (use when a theme reload is already in progress).
        """
        preset = self._get_preset(preset_id)
        if not preset:
            return
        layout_file = self._preset_layout_file(preset_id)
        if os.path.exists(layout_file):
            # Config-backup approach: restart plasmashell with saved config
            wait = max(delay, 1)
            self._run_shell(
                f"kquitapp6 plasmashell 2>/dev/null; sleep {wait}; "
                f"cp '{layout_file}' '{PLASMA_CONFIG}'; "
                f"nohup plasmashell &>/dev/null &"
            )
        else:
            script = preset.get("script", "")
            if script:
                escaped = script.replace("\\", "\\\\").replace('"', '\\"')
                prefix = f"sleep {delay}; " if delay else ""
                self._run_shell(
                    f'{prefix}qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript "{escaped}"'
                )

    def _apply_panel_appearance(self):
        theme_dir = os.path.expanduser("~/.local/share/plasma/desktoptheme/EquestriaPanel")
        widgets_dir = os.path.join(theme_dir, "widgets")
        os.makedirs(widgets_dir, exist_ok=True)

        metadata = {
            "KPlugin": {"Authors": [{"Name": "EquestriaOS"}], "Id": "EquestriaPanel", "Name": "EquestriaPanel", "Version": "1.0"},
            "X-Plasma-API-Minimum-Version": "6.0",
            "fallbackPackage": "default",
        }
        with open(os.path.join(theme_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)

        text_color = "255,255,255" if self.panel_is_dark else "35,38,41"
        colors_data = (
            f"[Colors:Window]\nForegroundNormal={text_color}\n"
            f"[Colors:View]\nForegroundNormal={text_color}\n"
            f"[Colors:Button]\nForegroundNormal={text_color}\n"
            f"[Colors:Complementary]\nForegroundNormal={text_color}\n"
            f"[Colors:Tooltip]\nForegroundNormal={text_color}\n"
        )
        with open(os.path.join(theme_dir, "colors"), "w", encoding="utf-8") as f:
            f.write(colors_data)

        svg = self._generate_panel_svg(self.panel_color, self.panel_opacity / 100.0)
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
            self._run_shell(cache_clear + "plasma-apply-desktoptheme default; sleep 1; plasma-apply-desktoptheme EquestriaPanel")
        else:
            self._run_shell(cache_clear + "plasma-apply-desktoptheme EquestriaPanel")

        self._update_ui_state()
        for card in self.cards.values():
            card.update_appearance(self.panel_color, self.panel_opacity)

    def _generate_panel_svg(self, hex_color, opacity_float):
        c, op = hex_color, f"{opacity_float:.2f}"
        return (
            '<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<rect id="hint-stretch-borders" width="0" height="0"/>'
            f'<rect id="center" fill="{c}" fill-opacity="{op}" x="6" y="6" width="88" height="88"/>'
            f'<rect id="top" fill="{c}" fill-opacity="{op}" x="6" y="0" width="88" height="6"/>'
            f'<rect id="bottom" fill="{c}" fill-opacity="{op}" x="6" y="94" width="88" height="6"/>'
            f'<rect id="left" fill="{c}" fill-opacity="{op}" x="0" y="6" width="6" height="88"/>'
            f'<rect id="right" fill="{c}" fill-opacity="{op}" x="94" y="6" width="6" height="88"/>'
            f'<rect id="topleft" fill="{c}" fill-opacity="{op}" x="0" y="0" width="6" height="6"/>'
            f'<rect id="topright" fill="{c}" fill-opacity="{op}" x="94" y="0" width="6" height="6"/>'
            f'<rect id="bottomleft" fill="{c}" fill-opacity="{op}" x="0" y="94" width="6" height="6"/>'
            f'<rect id="bottomright" fill="{c}" fill-opacity="{op}" x="94" y="94" width="6" height="6"/>'
            f'<rect id="floating-center" fill="{c}" fill-opacity="{op}" x="8" y="8" width="84" height="84" rx="8" ry="8"/>'
            f'<rect id="floating-top" fill="{c}" fill-opacity="{op}" x="8" y="0" width="84" height="8"/>'
            f'<rect id="floating-bottom" fill="{c}" fill-opacity="{op}" x="8" y="92" width="84" height="8"/>'
            f'<rect id="floating-left" fill="{c}" fill-opacity="{op}" x="0" y="8" width="8" height="84"/>'
            f'<rect id="floating-right" fill="{c}" fill-opacity="{op}" x="92" y="8" width="8" height="84"/>'
            f'<rect id="floating-topleft" fill="{c}" fill-opacity="{op}" x="0" y="0" width="8" height="8"/>'
            f'<rect id="floating-topright" fill="{c}" fill-opacity="{op}" x="92" y="0" width="8" height="8"/>'
            f'<rect id="floating-bottomleft" fill="{c}" fill-opacity="{op}" x="0" y="92" width="8" height="8"/>'
            f'<rect id="floating-bottomright" fill="{c}" fill-opacity="{op}" x="92" y="92" width="8" height="8"/>'
            '</svg>'
        )

    def _run_shell(self, command):
        subprocess.Popen(["/bin/bash", "-c", command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
