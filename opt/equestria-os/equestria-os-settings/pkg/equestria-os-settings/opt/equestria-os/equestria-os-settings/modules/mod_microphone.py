"""Microphone module — built-in mic gain control and drop/stutter diagnostics."""

import os
import re
import subprocess
import tempfile
import threading

from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from base_module import BaseModule

# ── Styles ────────────────────────────────────────────────────────────────────

_BTN_ACTION = (
    "QPushButton{background:rgb(45,42,68);color:rgb(200,190,220);"
    "border-radius:6px;padding:6px 18px;font-size:13px;"
    "border:1px solid rgb(80,75,110);}"
    "QPushButton:hover{background:rgb(65,60,95);color:white;}"
    "QPushButton:disabled{background:rgb(35,33,52);color:rgb(90,85,110);}"
)
_BTN_DANGER = (
    "QPushButton{background:rgb(90,40,40);color:rgb(255,180,180);"
    "border-radius:6px;padding:6px 14px;font-size:13px;"
    "border:1px solid rgb(140,60,60);}"
    "QPushButton:hover{background:rgb(140,50,50);color:white;}"
    "QPushButton:disabled{background:rgb(35,33,52);color:rgb(90,85,110);}"
)
_RESULT_OK = "QLabel{color:rgb(140,220,160);font-size:12px;background:transparent;}"
_RESULT_ERR = "QLabel{color:rgb(255,130,130);font-size:12px;background:transparent;}"
_STATUS_MONO = (
    "QLabel{color:rgb(170,165,195);font-size:12px;font-family:monospace;"
    "background:rgb(20,18,33);border:1px solid rgb(50,47,72);"
    "border-radius:6px;padding:8px 12px;}"
)
_WARN_STYLE = "QLabel{color:rgb(220,185,80);font-size:12px;background:transparent;}"

# Safe defaults offered by the "reset" button — moderate gain instead of the
# maxed-out boost+capture stack that turns the internal mic into a noise
# amplifier (30dB boost + 30dB capture gain = ~60dB of hiss and room noise).
_SAFE_BOOST_PCT = 33
_SAFE_CAPTURE_PCT = 70

# Signature of the KWin/WirePlumber-independent bug this module diagnoses:
# several apps holding the microphone at once (voice chat, browser tabs with
# mic permission, always-on push-to-talk clients) makes WirePlumber
# repeatedly reconfigure the audio graph, which is heard as short dropouts/
# stutter regardless of which physical microphone is active.
_LINK_FAIL_PATTERN = "PipeWire links failed to activate"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _list_alsa_card_indices() -> list[str]:
    try:
        out = subprocess.run(["aplay", "-l"], capture_output=True, text=True, timeout=5)
        indices = []
        for line in out.stdout.splitlines():
            if line.startswith("card "):
                idx = line.split(":")[0].replace("card", "").strip()
                if idx and idx not in indices:
                    indices.append(idx)
        return indices
    except Exception:
        return []


def _detect_mic_controls() -> tuple[str, str, str] | None:
    """Return (card_idx, boost_control_or_empty, capture_control_or_empty)."""
    for idx in _list_alsa_card_indices():
        try:
            out = subprocess.run(
                ["amixer", "-c", idx, "scontrols"],
                capture_output=True, text=True, timeout=5
            )
        except Exception:
            continue
        names = re.findall(r"'([^']+)'", out.stdout)
        boost = next(
            (n for n in names if "mic boost" in n.lower() and "headset" not in n.lower()),
            None
        ) or next((n for n in names if "mic boost" in n.lower()), None)
        capture = "Capture" if "Capture" in names else None
        if boost or capture:
            return idx, boost or "", capture or ""
    return None


def _get_mixer_percent(card_idx: str, control: str) -> int | None:
    if not card_idx or not control:
        return None
    try:
        out = subprocess.run(
            ["amixer", "-c", card_idx, "get", control],
            capture_output=True, text=True, timeout=5
        )
        m = re.search(r"\[(\d+)%\]", out.stdout)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _set_mixer_percent(card_idx: str, control: str, percent: int) -> bool:
    if not card_idx or not control:
        return False
    try:
        r = subprocess.run(
            ["amixer", "-c", card_idx, "set", control, f"{percent}%"],
            capture_output=True, text=True, timeout=5
        )
        return r.returncode == 0
    except Exception:
        return False


def _get_source_clients() -> list[str]:
    """Names of apps currently recording from the default microphone."""
    try:
        out = subprocess.run(
            ["pactl", "list", "source-outputs"],
            capture_output=True, text=True, timeout=5
        )
        names = []
        current_app = None
        current_media = None
        for raw in out.stdout.splitlines():
            line = raw.strip()
            if line.startswith("Source Output #"):
                if current_app or current_media:
                    names.append(current_app or current_media)
                current_app = None
                current_media = None
            elif line.startswith("application.name ="):
                current_app = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("media.name =") and current_media is None:
                current_media = line.split("=", 1)[1].strip().strip('"')
        if current_app or current_media:
            names.append(current_app or current_media)
        return names
    except Exception:
        return []


def _count_link_failures(window: str = "-1 hour") -> int:
    try:
        out = subprocess.run(
            ["journalctl", "-g", _LINK_FAIL_PATTERN, "--since", window,
             "-o", "cat", "--no-pager"],
            capture_output=True, text=True, timeout=10
        )
        return len([l for l in out.stdout.splitlines() if l.strip()])
    except Exception:
        return 0


# ── Workers ───────────────────────────────────────────────────────────────────

class _MicInfoWorker(QObject):
    done = pyqtSignal(dict)

    def run(self):
        info: dict = {}
        detected = _detect_mic_controls()
        card, boost_ctrl, capture_ctrl = detected if detected else (None, None, None)
        info["card"] = card
        info["boost_ctrl"] = boost_ctrl
        info["capture_ctrl"] = capture_ctrl
        info["boost_pct"] = _get_mixer_percent(card, boost_ctrl) if card else None
        info["capture_pct"] = _get_mixer_percent(card, capture_ctrl) if card else None
        info["clients"] = _get_source_clients()
        info["link_failures_1h"] = _count_link_failures("-1 hour")
        self.done.emit(info)


class _CmdWorker(QObject):
    done = pyqtSignal(bool, str)

    def __init__(self, cmd: list[str], timeout: int = 30):
        super().__init__()
        self._cmd = cmd
        self._timeout = timeout

    def run(self):
        try:
            proc = subprocess.run(
                self._cmd,
                capture_output=True, text=True, timeout=self._timeout
            )
            ok = proc.returncode == 0
            out = (proc.stdout + proc.stderr).strip()
            self.done.emit(ok, out)
        except subprocess.TimeoutExpired:
            self.done.emit(False, "Command timed out.")
        except Exception as e:
            self.done.emit(False, str(e))


class _MicTestWorker(QObject):
    done = pyqtSignal(bool, str)

    def run(self):
        tmp_path = os.path.join(tempfile.gettempdir(), f"equestria-mic-test-{os.getpid()}.wav")
        try:
            rec = subprocess.run(
                ["timeout", "3", "pw-record", tmp_path],
                capture_output=True, text=True, timeout=8
            )
            # returncode 124 = `timeout` killed pw-record after 3s — expected.
            if rec.returncode not in (0, 124):
                self.done.emit(False, rec.stderr.strip())
                return
            play = subprocess.run(
                ["pw-play", tmp_path],
                capture_output=True, text=True, timeout=8
            )
            ok = play.returncode == 0
            self.done.emit(ok, "" if ok else play.stderr.strip())
        except Exception as e:
            self.done.emit(False, str(e))
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ── Module ────────────────────────────────────────────────────────────────────

class MicrophoneModule(BaseModule):
    module_id = "mod_microphone"
    display_name_key = "module.microphone.name"
    description_key = "module.microphone.desc"
    category = "system"
    icon = "🎙"
    sort_order = 16
    required_binary = "/usr/bin/amixer"
    package_name = "alsa-utils"

    def __init__(self, t_func, base_path: str):
        super().__init__(t_func, base_path)
        self._mic_card = None
        self._boost_ctrl = None
        self._capture_ctrl = None
        self._boost_slider = None
        self._boost_value_lbl = None
        self._boost_name_lbl = None
        self._capture_slider = None
        self._capture_value_lbl = None
        self._capture_name_lbl = None

    # ── Build ─────────────────────────────────────────────────────────────────

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

        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        layout.addWidget(self._desc_lbl)

        self._build_level_card(layout)
        self._build_stability_card(layout)

        layout.addStretch()

        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        return wrapper

    # ── Level card (built-in mic boost/gain) ─────────────────────────────────

    def _build_level_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._level_title_lbl = QLabel(self.t("mic.level_title"))
        self._level_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._level_title_lbl)

        self._level_desc_lbl = QLabel(self.t("mic.level_desc"))
        self._level_desc_lbl.setObjectName("FieldHint")
        self._level_desc_lbl.setWordWrap(True)
        layout.addWidget(self._level_desc_lbl)

        self._level_not_found_lbl = QLabel(self.t("mic.level_not_found"))
        self._level_not_found_lbl.setStyleSheet(_WARN_STYLE)
        self._level_not_found_lbl.setWordWrap(True)
        self._level_not_found_lbl.hide()
        layout.addWidget(self._level_not_found_lbl)

        self._sliders_container = QVBoxLayout()
        self._sliders_container.setSpacing(8)
        layout.addLayout(self._sliders_container)

        btn_row = QHBoxLayout()
        self._reset_btn = QPushButton(self.t("mic.btn_reset_safe"))
        self._reset_btn.setStyleSheet(_BTN_ACTION)
        self._reset_btn.clicked.connect(self._reset_to_safe)
        btn_row.addWidget(self._reset_btn)

        self._save_btn = QPushButton(self.t("mic.btn_save"))
        self._save_btn.setStyleSheet(_BTN_ACTION)
        self._save_btn.clicked.connect(self._save_mixer_state)
        btn_row.addWidget(self._save_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._save_result_lbl = QLabel("")
        self._save_result_lbl.setObjectName("FieldHint")
        self._save_result_lbl.setWordWrap(True)
        layout.addWidget(self._save_result_lbl)

        self._save_hint_lbl = QLabel(self.t("mic.save_hint"))
        self._save_hint_lbl.setStyleSheet(_WARN_STYLE)
        self._save_hint_lbl.setWordWrap(True)
        layout.addWidget(self._save_hint_lbl)

        parent_layout.addWidget(card)

    # ── Stability card (drops/stutter, any microphone) ───────────────────────

    def _build_stability_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._stab_title_lbl = QLabel(self.t("mic.stability_title"))
        self._stab_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._stab_title_lbl)

        self._stab_desc_lbl = QLabel(self.t("mic.stability_desc"))
        self._stab_desc_lbl.setObjectName("FieldHint")
        self._stab_desc_lbl.setWordWrap(True)
        layout.addWidget(self._stab_desc_lbl)

        self._stab_status_lbl = QLabel(self.t("mic.loading"))
        self._stab_status_lbl.setStyleSheet(_STATUS_MONO)
        self._stab_status_lbl.setWordWrap(True)
        self._stab_status_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._stab_status_lbl)

        btn_row = QHBoxLayout()
        self._test_btn = QPushButton(self.t("mic.btn_test"))
        self._test_btn.setStyleSheet(_BTN_ACTION)
        self._test_btn.clicked.connect(self._test_mic)
        btn_row.addWidget(self._test_btn)

        self._restart_btn = QPushButton(self.t("mic.btn_restart_audio"))
        self._restart_btn.setStyleSheet(_BTN_DANGER)
        self._restart_btn.clicked.connect(self._restart_audio)
        btn_row.addWidget(self._restart_btn)

        self._refresh_btn = QPushButton(self.t("mic.refresh"))
        self._refresh_btn.setStyleSheet(_BTN_ACTION)
        self._refresh_btn.clicked.connect(self._refresh_all)
        btn_row.addWidget(self._refresh_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._test_result_lbl = QLabel("")
        self._test_result_lbl.setObjectName("FieldHint")
        self._test_result_lbl.setWordWrap(True)
        layout.addWidget(self._test_result_lbl)

        self._restart_result_lbl = QLabel("")
        self._restart_result_lbl.setObjectName("FieldHint")
        self._restart_result_lbl.setWordWrap(True)
        layout.addWidget(self._restart_result_lbl)

        parent_layout.addWidget(card)

    # ── Slider helper ─────────────────────────────────────────────────────────

    def _make_slider_row(self, parent_layout, label_text: str, initial_percent: int, apply_fn):
        row = QHBoxLayout()

        name_lbl = QLabel(label_text)
        name_lbl.setObjectName("FieldLabel")
        name_lbl.setMinimumWidth(160)
        row.addWidget(name_lbl)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(max(0, min(100, initial_percent)))
        row.addWidget(slider, stretch=1)

        value_lbl = QLabel(f"{slider.value()}%")
        value_lbl.setObjectName("FieldLabel")
        value_lbl.setMinimumWidth(40)
        row.addWidget(value_lbl)

        debounce = QTimer(slider)
        debounce.setSingleShot(True)
        debounce.setInterval(150)

        def _apply():
            threading.Thread(target=apply_fn, args=(slider.value(),), daemon=True).start()

        debounce.timeout.connect(_apply)

        def _on_value_changed(v: int):
            value_lbl.setText(f"{v}%")
            debounce.start()

        slider.valueChanged.connect(_on_value_changed)
        parent_layout.addLayout(row)
        return slider, value_lbl, name_lbl

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_shown(self) -> None:
        self._refresh_all()

    def apply_language(self) -> None:
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._level_title_lbl.setText(self.t("mic.level_title"))
        self._level_desc_lbl.setText(self.t("mic.level_desc"))
        self._level_not_found_lbl.setText(self.t("mic.level_not_found"))
        if self._boost_name_lbl is not None:
            self._boost_name_lbl.setText(self.t("mic.boost_label"))
        if self._capture_name_lbl is not None:
            self._capture_name_lbl.setText(self.t("mic.capture_label"))
        self._reset_btn.setText(self.t("mic.btn_reset_safe"))
        self._save_btn.setText(self.t("mic.btn_save"))
        self._save_hint_lbl.setText(self.t("mic.save_hint"))
        self._stab_title_lbl.setText(self.t("mic.stability_title"))
        self._stab_desc_lbl.setText(self.t("mic.stability_desc"))
        self._test_btn.setText(self.t("mic.btn_test"))
        self._restart_btn.setText(self.t("mic.btn_restart_audio"))
        self._refresh_btn.setText(self.t("mic.refresh"))
        self._refresh_all()

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _refresh_all(self):
        self._refresh_btn.setEnabled(False)
        self._stab_status_lbl.setText(self.t("mic.loading"))

        worker = _MicInfoWorker()
        worker.done.connect(self._on_info_ready)
        self._info_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_info_ready(self, info: dict):
        self._refresh_btn.setEnabled(True)
        self._populate_level(info)
        self._populate_stability(info)

    # ── Populate level card ───────────────────────────────────────────────────

    def _populate_level(self, info: dict):
        card_idx = info.get("card")
        boost_ctrl = info.get("boost_ctrl")
        capture_ctrl = info.get("capture_ctrl")

        if not card_idx or (not boost_ctrl and not capture_ctrl):
            self._level_not_found_lbl.show()
            self._reset_btn.setEnabled(False)
            self._save_btn.setEnabled(False)
            return

        self._level_not_found_lbl.hide()
        self._reset_btn.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._mic_card = card_idx
        self._boost_ctrl = boost_ctrl
        self._capture_ctrl = capture_ctrl

        if boost_ctrl:
            if self._boost_slider is None:
                self._boost_slider, self._boost_value_lbl, self._boost_name_lbl = self._make_slider_row(
                    self._sliders_container, self.t("mic.boost_label"),
                    info.get("boost_pct") or 0,
                    lambda v: _set_mixer_percent(self._mic_card, self._boost_ctrl, v)
                )
            elif info.get("boost_pct") is not None:
                self._boost_slider.blockSignals(True)
                self._boost_slider.setValue(info["boost_pct"])
                self._boost_value_lbl.setText(f"{info['boost_pct']}%")
                self._boost_slider.blockSignals(False)

        if capture_ctrl:
            if self._capture_slider is None:
                self._capture_slider, self._capture_value_lbl, self._capture_name_lbl = self._make_slider_row(
                    self._sliders_container, self.t("mic.capture_label"),
                    info.get("capture_pct") or 0,
                    lambda v: _set_mixer_percent(self._mic_card, self._capture_ctrl, v)
                )
            elif info.get("capture_pct") is not None:
                self._capture_slider.blockSignals(True)
                self._capture_slider.setValue(info["capture_pct"])
                self._capture_value_lbl.setText(f"{info['capture_pct']}%")
                self._capture_slider.blockSignals(False)

    # ── Populate stability card ───────────────────────────────────────────────

    def _populate_stability(self, info: dict):
        clients = info.get("clients", [])
        failures = info.get("link_failures_1h", 0)

        lines = [f"{self.t('mic.link_failures_label')}: {failures}", ""]
        if clients:
            lines.append(self.t("mic.clients_label"))
            for c in clients:
                lines.append(f"  • {c}")
        else:
            lines.append(self.t("mic.clients_none"))

        self._stab_status_lbl.setText("\n".join(lines))

    # ── Actions: level card ───────────────────────────────────────────────────

    def _reset_to_safe(self):
        if self._boost_slider is not None:
            self._boost_slider.setValue(_SAFE_BOOST_PCT)
        if self._capture_slider is not None:
            self._capture_slider.setValue(_SAFE_CAPTURE_PCT)

    def _save_mixer_state(self):
        self._save_btn.setEnabled(False)
        self._save_result_lbl.setText(self.t("mic.saving"))
        self._save_result_lbl.setStyleSheet("")

        worker = _CmdWorker(["pkexec", "alsactl", "store"], timeout=15)
        worker.done.connect(self._on_save_done)
        self._save_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_save_done(self, ok: bool, output: str):
        self._save_btn.setEnabled(True)
        self._save_result_lbl.setText(self.t("mic.save_ok") if ok else self.t("mic.save_err"))
        self._save_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)

    # ── Actions: stability card ───────────────────────────────────────────────

    def _confirm(self, title: str, msg: str) -> bool:
        return QMessageBox.question(
            self._widget, title, msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes

    def _test_mic(self):
        self._test_btn.setEnabled(False)
        self._test_result_lbl.setText(self.t("mic.testing"))
        self._test_result_lbl.setStyleSheet("")

        worker = _MicTestWorker()
        worker.done.connect(self._on_test_done)
        self._test_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_test_done(self, ok: bool, output: str):
        self._test_btn.setEnabled(True)
        self._test_result_lbl.setText(self.t("mic.test_done") if ok else self.t("mic.test_err"))
        self._test_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)

    def _restart_audio(self):
        if not self._confirm(
            self.t("mic.confirm_title"),
            self.t("mic.confirm_restart_audio")
        ):
            return

        self._restart_btn.setEnabled(False)
        self._restart_result_lbl.setText(self.t("mic.restarting"))
        self._restart_result_lbl.setStyleSheet("")

        worker = _CmdWorker(
            ["systemctl", "--user", "restart", "wireplumber", "pipewire-pulse", "pipewire"],
            timeout=20
        )
        worker.done.connect(self._on_restart_done)
        self._restart_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_restart_done(self, ok: bool, output: str):
        self._restart_btn.setEnabled(True)
        self._restart_result_lbl.setText(self.t("mic.action_ok") if ok else self.t("mic.action_err"))
        self._restart_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)
        self._refresh_all()
