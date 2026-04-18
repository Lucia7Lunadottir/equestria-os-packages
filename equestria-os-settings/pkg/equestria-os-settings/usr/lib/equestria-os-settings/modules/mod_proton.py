"""Windows Games & Apps module — Proton/Wine settings + cache cleaner."""

import json
import os
import shutil
import threading

_BTN_ACTION = (
    "QPushButton{background:rgb(45,42,68);color:rgb(200,190,220);"
    "border-radius:6px;padding:6px 18px;font-size:13px;"
    "border:1px solid rgb(80,75,110);}"
    "QPushButton:hover{background:rgb(65,60,95);color:white;}"
    "QPushButton:disabled{background:rgb(35,33,52);color:rgb(90,85,110);}"
)
_BTN_OPEN = (
    "QPushButton{background:transparent;color:rgb(180,160,220);"
    "border:1px solid rgb(80,70,115);border-radius:6px;"
    "padding:4px 14px;font-size:12px;}"
    "QPushButton:hover{background:rgb(45,42,68);color:rgb(210,190,245);}"
)
_BTN_DELETE = (
    "QPushButton{background:rgb(90,40,40);color:rgb(255,180,180);"
    "border-radius:6px;padding:6px 14px;font-size:13px;"
    "border:1px solid rgb(140,60,60);}"
    "QPushButton:hover{background:rgb(140,50,50);color:white;"
    "border:1px solid rgb(180,80,80);}"
)

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from base_module import BaseModule

_APPS_DATA_DIR = os.path.expanduser("~/.local/share/Equestria OS/ProtonApps/")
_CONFIG_DIR    = os.path.expanduser("~/.config/Equestria OS/Proton/")
_DEFAULTS_FILE = os.path.join(_CONFIG_DIR, "defaults.json")

_MESA_CACHE_DIRS = [
    os.path.expanduser("~/.cache/mesa_shader_cache"),
    os.path.expanduser("~/.cache/mesa"),
    os.path.expanduser("~/.cache/radeonsi"),
    os.path.expanduser("~/.cache/AMD"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dir_size(path: str) -> int:
    total = 0
    for dirpath, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def _fmt_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _find_shader_files(prefix_path: str) -> list:
    found = []
    for root, _, files in os.walk(prefix_path):
        for f in files:
            if f.endswith(".dxvk-cache") or f.endswith(".vkd3d-cache"):
                found.append(os.path.join(root, f))
    username = os.environ.get("USER", "steamuser")
    for sub in [
        os.path.join(prefix_path, "pfx", "drive_c", "users", username,
                     "AppData", "Local", "D3DSCache"),
        os.path.join(prefix_path, "pfx", "drive_c", "users", username,
                     "Local Settings", "Application Data", "dxvk"),
    ]:
        if os.path.isdir(sub):
            found.append(sub)
    return found


def _load_defaults() -> dict:
    if os.path.exists(_DEFAULTS_FILE):
        try:
            with open(_DEFAULTS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"dxvk": True, "vkd3d": True, "esync": True, "fsync": True}


def _save_defaults(cfg: dict):
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_DEFAULTS_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------------------
# App row widget
# ---------------------------------------------------------------------------

class _AppRow(QFrame):
    removed = pyqtSignal(object)   # emits self

    def __init__(self, app_id: str, prefix_path: str, t_func):
        super().__init__()
        self._t = t_func
        self.app_id = app_id
        self.prefix_path = prefix_path

        parts = app_id.rsplit("_", 1)
        self.display_name = parts[0] if len(parts) == 2 and len(parts[1]) == 8 else app_id

        self.setObjectName("InlineCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        info = QVBoxLayout()
        self._name_lbl = QLabel(self.display_name)
        self._name_lbl.setObjectName("FieldLabel")
        self._size_lbl = QLabel()
        self._size_lbl.setObjectName("FieldHint")
        info.addWidget(self._name_lbl)
        info.addWidget(self._size_lbl)
        layout.addLayout(info)
        layout.addStretch()

        self._shaders_btn = QPushButton(self._t("cleaner.btn_clear_shaders"))
        self._shaders_btn.setObjectName("ActionBtn")
        self._shaders_btn.setStyleSheet(_BTN_ACTION)
        self._shaders_btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._shaders_btn.clicked.connect(self._clear_shaders)

        self._prefix_btn = QPushButton(self._t("cleaner.btn_clear_prefix"))
        self._prefix_btn.setObjectName("DeleteBtn")
        self._prefix_btn.setStyleSheet(_BTN_DELETE)
        self._prefix_btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._prefix_btn.clicked.connect(self._clear_prefix)

        layout.addWidget(self._shaders_btn)
        layout.addWidget(self._prefix_btn)

        self._refresh_size()

    def retranslate(self, t_func):
        self._t = t_func
        self._shaders_btn.setText(self._t("cleaner.btn_clear_shaders"))
        self._prefix_btn.setText(self._t("cleaner.btn_clear_prefix"))
        self._refresh_size()

    def _refresh_size(self):
        size = _get_dir_size(self.prefix_path) if os.path.isdir(self.prefix_path) else 0
        self._size_lbl.setText(f"{self._t('cleaner.size')}: {_fmt_size(size)}")

    def _clear_shaders(self):
        shaders = _find_shader_files(self.prefix_path)
        if not shaders:
            QMessageBox.information(self, self._t("cleaner.msg_info_title"),
                                    self._t("cleaner.shaders_not_found"))
            return
        total = sum(
            _get_dir_size(s) if os.path.isdir(s) else os.path.getsize(s)
            for s in shaders
        )
        msg = (self._t("cleaner.msg_confirm_shaders")
               .replace("{0}", self.display_name)
               .replace("{1}", _fmt_size(total)))
        if QMessageBox.question(self, self._t("cleaner.msg_confirm_title"), msg,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            for s in shaders:
                shutil.rmtree(s) if os.path.isdir(s) else os.remove(s)
            self._refresh_size()
            QMessageBox.information(self, self._t("cleaner.msg_success_title"),
                                    self._t("cleaner.shaders_cleared"))
        except Exception as e:
            QMessageBox.critical(self, self._t("cleaner.msg_error_title"), str(e))

    def _clear_prefix(self):
        if not os.path.isdir(self.prefix_path):
            QMessageBox.information(self, self._t("cleaner.msg_info_title"),
                                    self._t("cleaner.prefix_not_found"))
            return
        msg = self._t("cleaner.msg_confirm_prefix").replace("{0}", self.display_name)
        if QMessageBox.question(self, self._t("cleaner.msg_confirm_title"), msg,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            shutil.rmtree(self.prefix_path)
            QMessageBox.information(self, self._t("cleaner.msg_success_title"),
                                    self._t("cleaner.prefix_cleared"))
            self.removed.emit(self)
        except Exception as e:
            QMessageBox.critical(self, self._t("cleaner.msg_error_title"), str(e))


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class ProtonModule(BaseModule):
    module_id = "mod_proton"
    display_name_key = "module.proton.name"
    description_key = "module.proton.desc"
    category = "software"
    icon = "🎮"
    sort_order = 30
    required_binary = "/usr/bin/equestria-proton-settings"
    package_name = "equestria-os-proton-starter"

    def build_widget(self) -> QWidget:
        outer = QWidget()
        outer.setObjectName("ContentPage")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(outer)

        main = QVBoxLayout(outer)
        main.setContentsMargins(40, 30, 40, 30)
        main.setSpacing(24)

        # Title
        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        main.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        main.addWidget(self._desc_lbl)

        # --- Default settings card ---
        defaults_card = QFrame()
        defaults_card.setObjectName("InlineCard")
        dc = QVBoxLayout(defaults_card)
        dc.setContentsMargins(20, 16, 20, 16)
        dc.setSpacing(10)

        self._defaults_lbl = QLabel(self.t("proton.defaults_title"))
        self._defaults_lbl.setObjectName("SectionTitle")
        dc.addWidget(self._defaults_lbl)

        self._cb_dxvk  = QCheckBox(self.t("proton.cb_dxvk"))
        self._cb_vkd3d = QCheckBox(self.t("proton.cb_vkd3d"))
        self._cb_esync = QCheckBox(self.t("proton.cb_esync"))
        self._cb_fsync = QCheckBox(self.t("proton.cb_fsync"))
        for cb in (self._cb_dxvk, self._cb_vkd3d, self._cb_esync, self._cb_fsync):
            cb.stateChanged.connect(self._save_defaults)
            dc.addWidget(cb)

        open_row = QHBoxLayout()
        self._open_btn = QPushButton(self.t("proton.open_btn"))
        self._open_btn.setObjectName("OpenAppBtn")
        self._open_btn.setStyleSheet(_BTN_OPEN)
        self._open_btn.clicked.connect(
            lambda: self.launch_app("/usr/bin/equestria-proton-settings"))
        open_row.addWidget(self._open_btn)
        open_row.addStretch()
        dc.addLayout(open_row)
        main.addWidget(defaults_card)

        # --- Cache cleaner section ---
        self._cleaner_title = QLabel(self.t("cleaner.section_title"))
        self._cleaner_title.setObjectName("SectionTitle")
        main.addWidget(self._cleaner_title)

        # App prefixes
        self._apps_header = QLabel(self.t("cleaner.group_apps"))
        self._apps_header.setObjectName("FieldLabel")
        main.addWidget(self._apps_header)

        self._apps_container = QVBoxLayout()
        self._apps_container.setSpacing(6)
        self._app_rows: list[_AppRow] = []
        main.addLayout(self._apps_container)

        self._empty_lbl = QLabel(self.t("cleaner.no_apps"))
        self._empty_lbl.setObjectName("FieldHint")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main.addWidget(self._empty_lbl)

        # Refresh button
        refresh_row = QHBoxLayout()
        self._refresh_btn = QPushButton(self.t("cleaner.btn_refresh"))
        self._refresh_btn.setObjectName("ActionBtn")
        self._refresh_btn.setStyleSheet(_BTN_ACTION)
        self._refresh_btn.clicked.connect(self._load_apps)
        refresh_row.addWidget(self._refresh_btn)
        refresh_row.addStretch()
        main.addLayout(refresh_row)

        # Mesa global cache
        mesa_card = QFrame()
        mesa_card.setObjectName("InlineCard")
        mc = QHBoxLayout(mesa_card)
        mc.setContentsMargins(16, 12, 16, 12)
        self._mesa_lbl = QLabel()
        self._mesa_lbl.setObjectName("FieldLabel")
        mc.addWidget(self._mesa_lbl)
        mc.addStretch()
        self._mesa_btn = QPushButton(self.t("cleaner.btn_clear_mesa"))
        self._mesa_btn.setObjectName("ActionBtn")
        self._mesa_btn.setStyleSheet(_BTN_ACTION)
        self._mesa_btn.clicked.connect(self._clear_mesa)
        mc.addWidget(self._mesa_btn)
        main.addWidget(mesa_card)

        main.addStretch()

        self._load_defaults()
        self._load_apps()

        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        return wrapper

    def on_shown(self):
        self._load_apps()

    def apply_language(self):
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._defaults_lbl.setText(self.t("proton.defaults_title"))
        self._cb_dxvk.setText(self.t("proton.cb_dxvk"))
        self._cb_vkd3d.setText(self.t("proton.cb_vkd3d"))
        self._cb_esync.setText(self.t("proton.cb_esync"))
        self._cb_fsync.setText(self.t("proton.cb_fsync"))
        self._open_btn.setText(self.t("proton.open_btn"))
        self._cleaner_title.setText(self.t("cleaner.section_title"))
        self._apps_header.setText(self.t("cleaner.group_apps"))
        self._empty_lbl.setText(self.t("cleaner.no_apps"))
        self._refresh_btn.setText(self.t("cleaner.btn_refresh"))
        self._mesa_btn.setText(self.t("cleaner.btn_clear_mesa"))
        for row in self._app_rows:
            row.retranslate(self.t)
        self._refresh_mesa_label()

    # --- Private ---

    def _load_defaults(self):
        cfg = _load_defaults()
        for cb, key in [
            (self._cb_dxvk,  "dxvk"),
            (self._cb_vkd3d, "vkd3d"),
            (self._cb_esync, "esync"),
            (self._cb_fsync, "fsync"),
        ]:
            cb.blockSignals(True)
            cb.setChecked(cfg.get(key, True))
            cb.blockSignals(False)

    def _save_defaults(self):
        try:
            _save_defaults({
                "dxvk":  self._cb_dxvk.isChecked(),
                "vkd3d": self._cb_vkd3d.isChecked(),
                "esync": self._cb_esync.isChecked(),
                "fsync": self._cb_fsync.isChecked(),
            })
        except Exception as e:
            print(f"[proton] save failed: {e}")

    def _load_apps(self):
        # Clear old rows
        for row in self._app_rows:
            self._apps_container.removeWidget(row)
            row.deleteLater()
        self._app_rows.clear()

        if not os.path.isdir(_APPS_DATA_DIR):
            self._empty_lbl.show()
            self._refresh_mesa_label()
            return

        entries = sorted(
            e for e in os.listdir(_APPS_DATA_DIR)
            if os.path.isdir(os.path.join(_APPS_DATA_DIR, e))
        )

        if not entries:
            self._empty_lbl.show()
        else:
            self._empty_lbl.hide()
            for app_id in entries:
                prefix_path = os.path.join(_APPS_DATA_DIR, app_id)
                row = _AppRow(app_id, prefix_path, self.t)
                row.removed.connect(self._on_row_removed)
                self._apps_container.addWidget(row)
                self._app_rows.append(row)

        self._refresh_mesa_label()

    def _on_row_removed(self, row: _AppRow):
        self._app_rows.remove(row)
        self._apps_container.removeWidget(row)
        row.deleteLater()
        if not self._app_rows:
            self._empty_lbl.show()

    def _refresh_mesa_label(self):
        total = sum(_get_dir_size(d) for d in _MESA_CACHE_DIRS if os.path.isdir(d))
        size_str = _fmt_size(total) if total > 0 else "—"
        self._mesa_lbl.setText(
            f"{self.t('cleaner.lbl_mesa')} ({size_str})"
        )

    def _clear_mesa(self):
        dirs_exist = [d for d in _MESA_CACHE_DIRS if os.path.isdir(d)]
        if not dirs_exist:
            QMessageBox.information(None, self.t("cleaner.msg_info_title"),
                                    self.t("cleaner.mesa_not_found"))
            return
        if QMessageBox.question(None, self.t("cleaner.msg_confirm_title"),
                                self.t("cleaner.msg_confirm_mesa"),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            for d in dirs_exist:
                shutil.rmtree(d)
            self._refresh_mesa_label()
            QMessageBox.information(None, self.t("cleaner.msg_success_title"),
                                    self.t("cleaner.mesa_cleared"))
        except Exception as e:
            QMessageBox.critical(None, self.t("cleaner.msg_error_title"), str(e))
