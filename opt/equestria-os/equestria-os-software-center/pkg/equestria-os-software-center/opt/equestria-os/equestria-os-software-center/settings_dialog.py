"""
settings_dialog.py — Equestria OS Software Center Settings Dialog Window.
Handles interactive toggles for software sources and explicit language mapping.
"""

import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QGroupBox, QWidget
from PyQt6.QtCore import Qt

# All code comments inside the script are written in English as requested

class SettingsDialog(QDialog):
    """Configuration management setup UI dialog panel overlay."""
    def __init__(self, parent, settings: dict, available_langs: list, t, on_save):
        super().__init__(parent)
        self.settings = dict(settings) # Create shallow copy to prevent dirty states
        self.available_langs = available_langs
        self.t = t
        self.on_save = on_save

        # Bind object name to match your master design framework
        self.setObjectName("SettingsDialog")
        self.setWindowTitle("⚙ " + self.t("settings.title"))
        self.setFixedSize(460, 500)
        
        # Load external style.qss directly from the disk hierarchy
        base_path = os.path.dirname(os.path.abspath(__file__))
        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                qss_content = f.read()
                # Appending local GroupBox container adjustments to match Catppuccin theme
                qss_content += """
                QGroupBox {
                    color: rgb(137, 180, 250);
                    font-weight: bold;
                    border: 1px solid rgb(49, 50, 68);
                    border-radius: 8px;
                    margin-top: 10px;
                    padding-top: 16px;
                }
                QGroupBox QLabel {
                    color: rgb(205, 214, 244);
                    font-size: 13px;
                }
                """
                self.setStyleSheet(qss_content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 20)
        layout.setSpacing(12)

        # 1. Environment Language Mapping Group
        lang_group = QGroupBox(self.t("settings.language_group"), self)
        lang_layout = QVBoxLayout(lang_group)
        
        self.combo_lang = QComboBox(self)
        self.combo_lang.setObjectName("CategoryDropdown") # Reuses your native dropdown styling rules
        self.combo_lang.addItem(self.t("settings.lang_auto"), "")
        
        for lang in self.available_langs:
            self.combo_lang.addItem(lang.upper(), lang)
        
        current_lang = self.settings.get("language", "")
        idx = self.combo_lang.findData(current_lang)
        if idx != -1:
            self.combo_lang.setCurrentIndex(idx)
        lang_layout.addWidget(self.combo_lang)
        layout.addWidget(lang_group)

        # 2. Package Database Visibility Options Group
        src_group = QGroupBox(self.t("settings.sources_group"), self)
        src_layout = QVBoxLayout(src_group)
        
        # Native Toggle: Enable AUR Support
        row_aur, self.chk_enable_aur = self._create_toggle_row(self.t("settings.enable_aur"), self.settings.get("enable_aur", True))
        self.chk_enable_aur.toggled.connect(self._sync_interdependencies)
        
        # Native Toggle: Enable Flatpak Support
        row_flat, self.chk_enable_flatpak = self._create_toggle_row(self.t("settings.enable_flatpak"), self.settings.get("enable_flatpak", True))
        self.chk_enable_flatpak.toggled.connect(self._sync_interdependencies)

        src_layout.addWidget(row_aur)
        src_layout.addWidget(row_flat)
        layout.addWidget(src_group)

        # 3. Automation Update Scope Target Parameters Group
        upd_group = QGroupBox(self.t("settings.updates_group"), self)
        upd_layout = QVBoxLayout(upd_group)

        # Native Toggle: Update Pacman
        row_upd_pac, self.chk_upd_pacman = self._create_toggle_row(self.t("settings.upd_pacman"), self.settings.get("update_pacman", True))
        
        # Native Toggle: Update AUR
        row_upd_aur, self.chk_upd_aur = self._create_toggle_row(self.t("settings.upd_aur"), self.settings.get("update_aur", True))
        
        # Native Toggle: Update Flatpak
        row_upd_flat, self.chk_upd_flatpak = self._create_toggle_row(self.t("settings.upd_flatpak"), self.settings.get("update_flatpak", True))

        upd_layout.addWidget(row_upd_pac)
        upd_layout.addWidget(row_upd_aur)
        upd_layout.addWidget(row_upd_flat)
        layout.addWidget(upd_group)

        layout.addStretch()

        # Bottom actions layout using your existing detail view design button definitions
        buttons = QHBoxLayout()
        self.btn_cancel = QPushButton(self.t("ui.cancel"), self)
        self.btn_cancel.setObjectName("DetailBackBtn") # Inherits sleek blue-bordered style structure
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton(self.t("ui.confirm"), self)
        self.btn_save.setObjectName("DetailActionBtn") # Inherits solid accent click action color
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._commit_settings_payload)

        buttons.addStretch()
        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_save)
        layout.addLayout(buttons)

        self._sync_interdependencies()

    def _create_toggle_row(self, label_text: str, initial_state: bool) -> tuple[QWidget, QPushButton]:
        """Helper to assemble native layout rows mapping directly to your AppToggle style definitions."""
        container = QWidget()
        row_layout = QHBoxLayout(container)
        row_layout.setContentsMargins(5, 2, 5, 2)
        
        lbl = QLabel(label_text, container)
        
        btn = QPushButton("✔", container)
        btn.setObjectName("AppToggle") # Connects directly into your style.qss checkbox engine
        btn.setCheckable(True)
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setChecked(initial_state)
        
        row_layout.addWidget(lbl)
        row_layout.addStretch()
        row_layout.addWidget(btn)
        
        return container, btn

    def _sync_interdependencies(self):
        """Enforces safe state constraints. Prevents updating disabled core branches."""
        aur_visible = self.chk_enable_aur.isChecked()
        self.chk_upd_aur.setEnabled(aur_visible)
        if not aur_visible:
            self.chk_upd_aur.setChecked(False)

        flatpak_visible = self.chk_enable_flatpak.isChecked()
        self.chk_upd_flatpak.setEnabled(flatpak_visible)
        if not flatpak_visible:
            self.chk_upd_flatpak.setChecked(False)

    def _commit_settings_payload(self):
        """Packs updated data layouts and pushes states out to main application slots."""
        self.settings["language"] = self.combo_lang.currentData()
        self.settings["enable_aur"] = self.chk_enable_aur.isChecked()
        self.settings["enable_flatpak"] = self.chk_enable_flatpak.isChecked()
        self.settings["update_pacman"] = self.chk_upd_pacman.isChecked()
        self.settings["update_aur"] = self.chk_upd_aur.isChecked()
        self.settings["update_flatpak"] = self.chk_upd_flatpak.isChecked()

        self.on_save(self.settings)
        self.accept()