"""Auto-Update module — notification settings + auto-install for pg-update."""

import json
import os
import subprocess
import threading

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from base_module import BaseModule

_BTN_ACTION = (
    "QPushButton{background:rgb(45,42,68);color:rgb(200,190,220);"
    "border-radius:6px;padding:6px 18px;font-size:13px;"
    "border:1px solid rgb(80,75,110);}"
    "QPushButton:hover{background:rgb(65,60,95);color:white;}"
    "QPushButton:disabled{background:rgb(35,33,52);color:rgb(90,85,110);}"
)
_WARNING_CARD = (
    "QFrame#WarningCard{background:rgb(55,38,10);border:1px solid rgb(160,100,20);"
    "border-radius:10px;}"
)
_WARNING_TITLE = (
    "QLabel{color:rgb(255,190,60);font-size:14px;font-weight:bold;"
    "background:transparent;}"
)
_WARNING_TEXT = (
    "QLabel{color:rgb(220,175,100);font-size:12px;background:transparent;}"
)

_INTERVALS = [
    ("30min", "OnUnitActiveSec=30min"),
    ("1h",    "OnUnitActiveSec=1h"),
    ("2h",    "OnUnitActiveSec=2h"),
    ("6h",    "OnUnitActiveSec=6h"),
    ("12h",   "OnUnitActiveSec=12h"),
    ("24h",   "OnUnitActiveSec=24h"),
]

_OVERRIDE_DIR  = os.path.expanduser("~/.config/systemd/user/pg-update.timer.d")
_OVERRIDE_FILE = os.path.join(_OVERRIDE_DIR, "override.conf")
_SOURCES_CFG   = os.path.expanduser("~/.config/equestria-settings/pg-update.conf")

# Systemd user units for actual auto-install
_AI_SERVICE_DIR  = os.path.expanduser("~/.config/systemd/user")
_AI_SERVICE_FILE = os.path.join(_AI_SERVICE_DIR, "equestria-autoupdate.service")
_AI_TIMER_FILE   = os.path.join(_AI_SERVICE_DIR, "equestria-autoupdate.timer")

_AI_SERVICE_CONTENT = """\
[Unit]
Description=Equestria OS — automatic system update
After=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'pkexec pacman -Syu --noconfirm >> %h/.local/share/equestria-autoupdate.log 2>&1'
"""

_AI_TIMER_CONTENT = """\
[Unit]
Description=Equestria OS — automatic update timer

[Timer]
OnBootSec=15min
OnUnitActiveSec=24h
Persistent=true

[Install]
WantedBy=timers.target
"""


class _CheckWorker(QObject):
    done = pyqtSignal()

    def run(self):
        try:
            subprocess.run(["/usr/bin/pg-update"], capture_output=True, timeout=60)
        except Exception:
            pass
        self.done.emit()


class _NotifFetcher(QObject):
    done = pyqtSignal(str)

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


class _AutoInstallFetcher(QObject):
    done = pyqtSignal(bool)

    def run(self):
        try:
            r = subprocess.run(
                ["systemctl", "--user", "is-enabled",
                 "equestria-autoupdate.timer"],
                capture_output=True, text=True, timeout=5
            )
            self.done.emit(r.stdout.strip() in ("enabled", "static"))
        except Exception:
            self.done.emit(False)


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

        layout = QVBoxLayout(outer)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        # Title
        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        layout.addWidget(self._desc_lbl)

        # ── Warning card ──────────────────────────────────────────────────────
        warn_card = QFrame()
        warn_card.setObjectName("WarningCard")
        warn_card.setStyleSheet(_WARNING_CARD)
        warn_layout = QVBoxLayout(warn_card)
        warn_layout.setContentsMargins(20, 16, 20, 16)
        warn_layout.setSpacing(8)

        self._warn_title_lbl = QLabel(self.t("auto_update.warning_title"))
        self._warn_title_lbl.setStyleSheet(_WARNING_TITLE)
        warn_layout.addWidget(self._warn_title_lbl)

        self._warn_text_lbl = QLabel(self.t("auto_update.warning_text"))
        self._warn_text_lbl.setStyleSheet(_WARNING_TEXT)
        self._warn_text_lbl.setWordWrap(True)
        warn_layout.addWidget(self._warn_text_lbl)

        # ── Notification card ─────────────────────────────────────────────────
        notif_card = QFrame()
        notif_card.setObjectName("InlineCard")
        notif_layout = QVBoxLayout(notif_card)
        notif_layout.setContentsMargins(20, 16, 20, 16)
        notif_layout.setSpacing(12)

        self._notif_title_lbl = QLabel(self.t("auto_update.notif_title"))
        self._notif_title_lbl.setObjectName("SectionTitle")
        notif_layout.addWidget(self._notif_title_lbl)

        status_row = QHBoxLayout()
        self._enable_cb = QCheckBox(self.t("auto_update.enable"))
        self._enable_cb.stateChanged.connect(self._on_enable_changed)
        status_row.addWidget(self._enable_cb)
        status_row.addStretch()
        self._status_lbl = QLabel("…")
        self._status_lbl.setObjectName("FieldHint")
        status_row.addWidget(self._status_lbl)
        notif_layout.addLayout(status_row)

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
        notif_layout.addLayout(interval_row)

        layout.addWidget(notif_card)

        # ── Sources card ──────────────────────────────────────────────────────
        src_card = QFrame()
        src_card.setObjectName("InlineCard")
        src_layout = QVBoxLayout(src_card)
        src_layout.setContentsMargins(20, 16, 20, 16)
        src_layout.setSpacing(10)

        self._sources_lbl = QLabel(self.t("auto_update.sources_label"))
        self._sources_lbl.setObjectName("SectionTitle")
        src_layout.addWidget(self._sources_lbl)

        self._src_pacman  = QCheckBox(self.t("auto_update.source_pacman"))
        self._src_aur     = QCheckBox(self.t("auto_update.source_aur"))
        self._src_flatpak = QCheckBox(self.t("auto_update.source_flatpak"))
        self._src_snap    = QCheckBox(self.t("auto_update.source_snap"))
        for cb in (self._src_pacman, self._src_aur, self._src_flatpak, self._src_snap):
            cb.stateChanged.connect(self._on_sources_changed)
            src_layout.addWidget(cb)

        layout.addWidget(src_card)

        # ── Warning card ──────────────────────────────────────────────────────
        layout.addWidget(warn_card)

        # ── Auto-install card ─────────────────────────────────────────────────
        ai_card = QFrame()
        ai_card.setObjectName("InlineCard")
        ai_layout = QVBoxLayout(ai_card)
        ai_layout.setContentsMargins(20, 16, 20, 16)
        ai_layout.setSpacing(10)

        self._ai_title_lbl = QLabel(self.t("auto_update.auto_install_title"))
        self._ai_title_lbl.setObjectName("SectionTitle")
        ai_layout.addWidget(self._ai_title_lbl)

        ai_status_row = QHBoxLayout()
        self._ai_cb = QCheckBox(self.t("auto_update.auto_install"))
        self._ai_cb.stateChanged.connect(self._on_auto_install_changed)
        ai_status_row.addWidget(self._ai_cb)
        ai_status_row.addStretch()
        self._ai_status_lbl = QLabel("…")
        self._ai_status_lbl.setObjectName("FieldHint")
        ai_status_row.addWidget(self._ai_status_lbl)
        ai_layout.addLayout(ai_status_row)

        self._ai_hint_lbl = QLabel(self.t("auto_update.auto_install_hint"))
        self._ai_hint_lbl.setObjectName("FieldHint")
        self._ai_hint_lbl.setWordWrap(True)
        ai_layout.addWidget(self._ai_hint_lbl)

        layout.addWidget(ai_card)

        # ── Buttons row ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._check_btn = QPushButton(self.t("auto_update.check_now"))
        self._check_btn.setObjectName("ActionBtn")
        self._check_btn.setStyleSheet(_BTN_ACTION)
        self._check_btn.clicked.connect(self._check_now)
        btn_row.addWidget(self._check_btn)

        self._update_btn = QPushButton(self.t("auto_update.update_system"))
        self._update_btn.setObjectName("ActionBtn")
        self._update_btn.setStyleSheet(_BTN_ACTION)
        self._update_btn.clicked.connect(self._update_system)
        btn_row.addWidget(self._update_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

        self._load_sources()

        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        return wrapper

    def on_shown(self):
        self._fetch_notif_status()
        self._fetch_auto_install_status()

    def apply_language(self):
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._warn_title_lbl.setText(self.t("auto_update.warning_title"))
        self._warn_text_lbl.setText(self.t("auto_update.warning_text"))
        self._notif_title_lbl.setText(self.t("auto_update.notif_title"))
        self._enable_cb.setText(self.t("auto_update.enable"))
        self._interval_lbl.setText(self.t("auto_update.interval_label"))
        self._sources_lbl.setText(self.t("auto_update.sources_label"))
        self._src_pacman.setText(self.t("auto_update.source_pacman"))
        self._src_aur.setText(self.t("auto_update.source_aur"))
        self._src_flatpak.setText(self.t("auto_update.source_flatpak"))
        self._src_snap.setText(self.t("auto_update.source_snap"))
        self._ai_title_lbl.setText(self.t("auto_update.auto_install_title"))
        self._ai_cb.setText(self.t("auto_update.auto_install"))
        self._ai_hint_lbl.setText(self.t("auto_update.auto_install_hint"))
        self._check_btn.setText(self.t("auto_update.check_now"))
        self._update_btn.setText(self.t("auto_update.update_system"))
        for i, (key, _) in enumerate(_INTERVALS):
            self._interval_cb.setItemText(i, self.t(f"auto_update.interval_{key}"))

    # ── Notification timer ────────────────────────────────────────────────────

    def _fetch_notif_status(self):
        fetcher = _NotifFetcher()
        fetcher.done.connect(self._on_notif_status)
        self._notif_fetcher = fetcher
        threading.Thread(target=fetcher.run, daemon=True).start()

    def _on_notif_status(self, state: str):
        active = state == "active"
        self._enable_cb.blockSignals(True)
        self._enable_cb.setChecked(active)
        self._enable_cb.blockSignals(False)
        key = "auto_update.status_active" if active else "auto_update.status_inactive"
        self._status_lbl.setText(self.t(key))
        self._load_interval()

    def _load_interval(self):
        current = "1h"
        if os.path.exists(_OVERRIDE_FILE):
            try:
                with open(_OVERRIDE_FILE) as f:
                    for line in f:
                        if line.strip().startswith("OnUnitActiveSec="):
                            current = line.split("=", 1)[1].strip()
            except Exception:
                pass
        for i, (key, _) in enumerate(_INTERVALS):
            if key == current:
                self._interval_cb.blockSignals(True)
                self._interval_cb.setCurrentIndex(i)
                self._interval_cb.blockSignals(False)
                break

    def _on_enable_changed(self, state):
        action = "enable" if state else "disable"
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
                 "systemctl --user daemon-reload && "
                 "systemctl --user restart pg-update.timer"],
                start_new_session=True
            )
        except Exception as e:
            print(f"[auto_update] failed to write override: {e}")

    # ── Sources ───────────────────────────────────────────────────────────────

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
            (self._src_pacman,  "check_pacman"),
            (self._src_aur,     "check_aur"),
            (self._src_flatpak, "check_flatpak"),
            (self._src_snap,    "check_snap"),
        ]:
            cb.blockSignals(True)
            cb.setChecked(cfg.get(key, False))
            cb.blockSignals(False)

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

    # ── Auto-install ──────────────────────────────────────────────────────────

    def _fetch_auto_install_status(self):
        fetcher = _AutoInstallFetcher()
        fetcher.done.connect(self._on_auto_install_status)
        self._ai_fetcher = fetcher
        threading.Thread(target=fetcher.run, daemon=True).start()

    def _on_auto_install_status(self, enabled: bool):
        self._ai_cb.blockSignals(True)
        self._ai_cb.setChecked(enabled)
        self._ai_cb.blockSignals(False)
        key = "auto_update.status_autoinst_on" if enabled else "auto_update.status_autoinst_off"
        self._ai_status_lbl.setText(self.t(key))

    def _on_auto_install_changed(self, state):
        if state:
            self._enable_auto_install()
        else:
            self._disable_auto_install()

    def _enable_auto_install(self):
        try:
            os.makedirs(_AI_SERVICE_DIR, exist_ok=True)
            with open(_AI_SERVICE_FILE, "w") as f:
                f.write(_AI_SERVICE_CONTENT)
            with open(_AI_TIMER_FILE, "w") as f:
                f.write(_AI_TIMER_CONTENT)
            subprocess.Popen(
                ["bash", "-c",
                 "systemctl --user daemon-reload && "
                 "systemctl --user enable --now equestria-autoupdate.timer"],
                start_new_session=True
            )
            self._ai_status_lbl.setText(self.t("auto_update.status_autoinst_on"))
        except Exception as e:
            print(f"[auto_update] failed to enable auto-install: {e}")

    def _disable_auto_install(self):
        try:
            subprocess.run(
                ["systemctl", "--user", "disable", "--now",
                 "equestria-autoupdate.timer"],
                capture_output=True
            )
            for f in (_AI_TIMER_FILE, _AI_SERVICE_FILE):
                if os.path.exists(f):
                    os.remove(f)
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True
            )
            self._ai_status_lbl.setText(self.t("auto_update.status_autoinst_off"))
        except Exception as e:
            print(f"[auto_update] failed to disable auto-install: {e}")

    # ── Check now ─────────────────────────────────────────────────────────────

    def _check_now(self):
        self._check_btn.setText(self.t("auto_update.checking"))
        self._check_btn.setEnabled(False)
        worker = _CheckWorker()
        worker.done.connect(self._on_check_done)
        self._check_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_check_done(self):
        self._check_btn.setEnabled(True)
        self._check_btn.setText(self.t("auto_update.check_now"))

    # ── Update system ─────────────────────────────────────────────────────────

    def _update_system(self):
        cmd = (
            "LOG=$(mktemp /tmp/equestria_update.XXXXXX.log); "
            "echo '==> [1/2] Updating repositories...'; echo; "
            "pkexec pacman -Syu --noconfirm 2>&1 | tee \"$LOG\"; "
            "EXIT=${PIPESTATUS[0]}; "
            "if [ $EXIT -ne 0 ] && grep -qE "
            "'Operation too slow|failed to retrieve|не удалось получить' \"$LOG\"; then "
            "  echo; echo '==> Mirror failure detected. Re-ranking mirrors...'; "
            "  COUNTRY=$(curl -s --max-time 5 https://ipinfo.io/country 2>/dev/null | tr -d '\\n\\r'); "
            "  [ -z \"$COUNTRY\" ] && COUNTRY='DE,US,FR,GB'; "
            "  pkexec pg-rankmirrors-backend rank \"$COUNTRY\" "
            "    && echo '==> Mirrors updated. Retrying...' || true; "
            "  echo; pkexec pacman -Syu --noconfirm 2>&1 | tee \"$LOG\"; EXIT=${PIPESTATUS[0]}; "
            "fi; "
            "if [ $EXIT -ne 0 ] && grep -q 'are in conflict' \"$LOG\"; then "
            "  echo; echo '==> Package conflict detected. Resolving automatically...'; "
            "  CONFLICT_PKGS=$(grep -oP '(?<=Remove )[^?]+' \"$LOG\" | tr -d ' ' | tr '\\n' ' '); "
            "  if [ -n \"$CONFLICT_PKGS\" ]; then "
            "    echo \"==> Removing conflicting packages: $CONFLICT_PKGS\"; "
            "    pkexec pacman -Rdd --noconfirm $CONFLICT_PKGS; "
            "    echo '==> Retrying update...'; echo; "
            "    pkexec pacman -Syu --noconfirm 2>&1 | tee \"$LOG\"; EXIT=${PIPESTATUS[0]}; "
            "  fi; "
            "fi; "
            "echo; echo '==> [2/2] Updating AUR packages...'; echo; "
            "AUR_PKGS=$(yay -Qua 2>/dev/null | awk '{print $1}'); "
            "if [ -n \"$AUR_PKGS\" ]; then "
            "  for pkg in $AUR_PKGS; do "
            "    echo \"-- $pkg\"; "
            "    yay -S --noconfirm \"$pkg\" "
            "      || echo \"==> Warning: $pkg skipped (build/dependency error)\"; "
            "    echo; "
            "  done; "
            "else "
            "  echo 'AUR packages are up to date.'; "
            "fi; "
            "rm -f \"$LOG\"; "
            "if command -v flatpak >/dev/null; then echo; flatpak update -y; fi; "
            "echo; read -rp 'Done. Press Enter to close...'"
        )
        subprocess.Popen(["konsole", "-e", "bash", "-c", cmd])
