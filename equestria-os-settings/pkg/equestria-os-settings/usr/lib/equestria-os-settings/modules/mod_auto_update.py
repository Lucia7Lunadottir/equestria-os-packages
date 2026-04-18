"""Auto-Update module — inline settings for pg-update."""

import json
import os
import subprocess
import threading

# Direct widget stylesheets — bypass Kvantum which intercepts child-cascade rendering
_BTN_ACTION = (
    "QPushButton{background:rgb(45,42,68);color:rgb(200,190,220);"
    "border-radius:6px;padding:6px 18px;font-size:13px;"
    "border:1px solid rgb(80,75,110);}"
    "QPushButton:hover{background:rgb(65,60,95);color:white;}"
    "QPushButton:disabled{background:rgb(35,33,52);color:rgb(90,85,110);}"
)

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from base_module import BaseModule

_INTERVALS = [
    ("30min", "OnUnitActiveSec=30min"),
    ("1h",    "OnUnitActiveSec=1h"),
    ("2h",    "OnUnitActiveSec=2h"),
    ("6h",    "OnUnitActiveSec=6h"),
    ("12h",   "OnUnitActiveSec=12h"),
    ("24h",   "OnUnitActiveSec=24h"),
]

_OVERRIDE_DIR = os.path.expanduser("~/.config/systemd/user/pg-update.timer.d")
_OVERRIDE_FILE = os.path.join(_OVERRIDE_DIR, "override.conf")
_SOURCES_CFG = os.path.expanduser("~/.config/equestria-settings/pg-update.conf")


class _Fetcher(QObject):
    done = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            r = subprocess.run(
                ["systemctl", "--user", "show", "pg-update.timer",
                 "--property=ActiveState"],
                capture_output=True, text=True, timeout=5
            )
            state = ""
            for line in r.stdout.splitlines():
                if line.startswith("ActiveState="):
                    state = line.split("=", 1)[1].strip()
            self.done.emit(state)
        except Exception:
            self.done.emit("")


class AutoUpdateModule(BaseModule):
    module_id = "mod_auto_update"
    display_name_key = "module.auto_update.name"
    description_key = "module.auto_update.desc"
    category = "system"
    icon = "🔄"
    sort_order = 10
    required_binary = "/usr/bin/pg-update"
    package_name = "pg-update"

    def build_widget(self) -> QWidget:
        outer = QWidget()
        outer.setObjectName("ContentPage")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(outer)
        scroll.setObjectName("ContentPage")

        main_layout = QVBoxLayout(outer)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(24)

        # Title
        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        main_layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        main_layout.addWidget(self._desc_lbl)

        # --- Enable card ---
        enable_card = QFrame()
        enable_card.setObjectName("InlineCard")
        card_layout = QVBoxLayout(enable_card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(12)

        status_row = QHBoxLayout()
        self._enable_cb = QCheckBox(self.t("auto_update.enable"))
        self._enable_cb.stateChanged.connect(self._on_enable_changed)
        status_row.addWidget(self._enable_cb)
        status_row.addStretch()
        self._status_lbl = QLabel("…")
        self._status_lbl.setObjectName("FieldHint")
        status_row.addWidget(self._status_lbl)
        card_layout.addLayout(status_row)

        interval_row = QHBoxLayout()
        self._interval_lbl = QLabel(self.t("auto_update.interval_label"))
        self._interval_lbl.setObjectName("FieldLabel")
        interval_row.addWidget(self._interval_lbl)
        self._interval_cb = QComboBox()
        self._interval_cb.setStyleSheet(
            "QComboBox{background:rgb(40,35,60);color:rgb(220,210,240);"
            "border:1px solid rgb(100,80,150);border-radius:6px;padding:4px 10px;}"
            "QComboBox::drop-down{subcontrol-origin:padding;subcontrol-position:top right;"
            "width:22px;border-left:1px solid rgb(80,60,110);background:rgb(50,44,72);"
            "border-top-right-radius:6px;border-bottom-right-radius:6px;}"
            "QComboBox::down-arrow{width:0;height:0;border-style:solid;"
            "border-width:5px 4px 0 4px;"
            "border-color:rgb(180,160,220) transparent transparent transparent;}"
            "QComboBox QAbstractItemView{background:rgb(40,35,60);color:rgb(220,210,240);"
            "border:1px solid rgb(100,80,150);selection-background-color:rgb(80,60,130);}"
        )
        for key, _ in _INTERVALS:
            self._interval_cb.addItem(self.t(f"auto_update.interval_{key}"), key)
        self._interval_cb.currentIndexChanged.connect(self._on_interval_changed)
        interval_row.addWidget(self._interval_cb)
        interval_row.addStretch()
        card_layout.addLayout(interval_row)

        main_layout.addWidget(enable_card)

        # --- Sources card ---
        src_card = QFrame()
        src_card.setObjectName("InlineCard")
        src_layout = QVBoxLayout(src_card)
        src_layout.setContentsMargins(20, 16, 20, 16)
        src_layout.setSpacing(10)

        self._sources_lbl = QLabel(self.t("auto_update.sources_label"))
        self._sources_lbl.setObjectName("SectionTitle")
        src_layout.addWidget(self._sources_lbl)

        self._src_pacman = QCheckBox(self.t("auto_update.source_pacman"))
        self._src_aur    = QCheckBox(self.t("auto_update.source_aur"))
        self._src_flatpak = QCheckBox(self.t("auto_update.source_flatpak"))
        self._src_snap   = QCheckBox(self.t("auto_update.source_snap"))
        for cb in (self._src_pacman, self._src_aur, self._src_flatpak, self._src_snap):
            cb.stateChanged.connect(self._on_sources_changed)
            src_layout.addWidget(cb)

        main_layout.addWidget(src_card)

        # --- Check now button ---
        btn_row = QHBoxLayout()
        self._check_btn = QPushButton(self.t("auto_update.check_now"))
        self._check_btn.setObjectName("ActionBtn")
        self._check_btn.setStyleSheet(_BTN_ACTION)
        self._check_btn.clicked.connect(self._check_now)
        btn_row.addWidget(self._check_btn)
        btn_row.addStretch()
        main_layout.addLayout(btn_row)

        main_layout.addStretch()

        self._load_sources()

        # Return scroll area as the top-level widget
        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        return wrapper

    def on_shown(self):
        self._fetch_status()

    def apply_language(self):
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._enable_cb.setText(self.t("auto_update.enable"))
        self._interval_lbl.setText(self.t("auto_update.interval_label"))
        self._sources_lbl.setText(self.t("auto_update.sources_label"))
        self._src_pacman.setText(self.t("auto_update.source_pacman"))
        self._src_aur.setText(self.t("auto_update.source_aur"))
        self._src_flatpak.setText(self.t("auto_update.source_flatpak"))
        self._src_snap.setText(self.t("auto_update.source_snap"))
        self._check_btn.setText(self.t("auto_update.check_now"))
        for i, (key, _) in enumerate(_INTERVALS):
            self._interval_cb.setItemText(i, self.t(f"auto_update.interval_{key}"))

    # --- Private ---

    def _fetch_status(self):
        fetcher = _Fetcher()
        fetcher.done.connect(self._on_status)
        self._fetcher = fetcher
        threading.Thread(target=fetcher.run, daemon=True).start()

    def _on_status(self, state: str):
        active = state == "active"
        self._enable_cb.blockSignals(True)
        self._enable_cb.setChecked(active)
        self._enable_cb.blockSignals(False)
        if active:
            self._status_lbl.setText(self.t("auto_update.status_active"))
        else:
            self._status_lbl.setText(self.t("auto_update.status_inactive"))
        self._load_interval()

    def _load_interval(self):
        current = "1h"
        if os.path.exists(_OVERRIDE_FILE):
            try:
                with open(_OVERRIDE_FILE) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("OnUnitActiveSec="):
                            current = line.split("=", 1)[1].strip()
            except Exception:
                pass
        for i, (key, _) in enumerate(_INTERVALS):
            if key == current:
                self._interval_cb.blockSignals(True)
                self._interval_cb.setCurrentIndex(i)
                self._interval_cb.blockSignals(False)
                break

    def _load_sources(self):
        cfg = {"check_pacman": True, "check_aur": True,
               "check_flatpak": False, "check_snap": False}
        if os.path.exists(_SOURCES_CFG):
            try:
                with open(_SOURCES_CFG) as f:
                    cfg.update(json.load(f))
            except Exception:
                pass
        for cb, key in [
            (self._src_pacman, "check_pacman"),
            (self._src_aur,    "check_aur"),
            (self._src_flatpak,"check_flatpak"),
            (self._src_snap,   "check_snap"),
        ]:
            cb.blockSignals(True)
            cb.setChecked(cfg.get(key, False))
            cb.blockSignals(False)

    def _on_enable_changed(self, state):
        enabled = bool(state)
        action = "enable" if enabled else "disable"
        threading.Thread(
            target=lambda: subprocess.run(
                ["systemctl", "--user", action, "--now", "pg-update.timer"],
                capture_output=True
            ),
            daemon=True
        ).start()

    def _on_interval_changed(self, idx):
        _, value = _INTERVALS[idx]
        try:
            os.makedirs(_OVERRIDE_DIR, exist_ok=True)
            with open(_OVERRIDE_FILE, "w") as f:
                f.write("[Timer]\nOnBootSec=\n" + value + "\n")
            subprocess.Popen(
                ["bash", "-c",
                 "systemctl --user daemon-reload && systemctl --user restart pg-update.timer"],
                start_new_session=True
            )
        except Exception as e:
            print(f"[auto_update] failed to write override: {e}")

    def _on_sources_changed(self):
        cfg = {
            "check_pacman":  self._src_pacman.isChecked(),
            "check_aur":     self._src_aur.isChecked(),
            "check_flatpak": self._src_flatpak.isChecked(),
            "check_snap":    self._src_snap.isChecked(),
        }
        try:
            os.makedirs(os.path.dirname(_SOURCES_CFG), exist_ok=True)
            with open(_SOURCES_CFG, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            print(f"[auto_update] failed to save sources: {e}")

    def _check_now(self):
        self._check_btn.setText(self.t("auto_update.checking"))
        self._check_btn.setEnabled(False)

        def thread_fn():
            try:
                subprocess.run(["/usr/bin/pg-update"], capture_output=True, timeout=60)
            except Exception:
                pass
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._on_check_done)

        threading.Thread(target=thread_fn, daemon=True).start()

    def _on_check_done(self):
        self._check_btn.setEnabled(True)
        self._check_btn.setText(self.t("auto_update.check_now"))
